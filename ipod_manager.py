import contextlib
import datetime
import json
import os
import platform
import shutil
import tempfile
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

# Ensure pygpod is in the import path
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pygpod
from pygpod.device.device import Device
from pygpod.device.models import lookup_model
from pygpod.device.mountpoint import validate_mountpoint, init_ipod

logger = logging.getLogger("ipod_manager")
logging.basicConfig(level=logging.INFO)

import artwork
import converter
import settings
import tag_editor
from folder_library import AUDIO_EXTS, FolderLibrary
from library_db import DB_FILENAME, LibraryDB

CONFIG_PATH: Optional[str] = None  # None = settings.config_path() (theo KLMM_DATA_DIR)
MACOS_VOLUMES = Path("/Volumes")
LINUX_MOUNT_GLOBS = [(Path("/media"), "*/*"), (Path("/run/media"), "*/*"), (Path("/mnt"), "*")]
# GetDriveTypeW: 2 = removable, 3 = fixed (iPod hiện là một trong hai).
# Bỏ ổ mạng (4: share mất kết nối làm treo khi quét) và ổ quang (5: hộp thoại "No disk").
_IPOD_DRIVE_TYPES = {2, 3}


class ScanBusy(RuntimeError):
    """Đang có một lần quét thư viện khác chạy."""


def _windows_drives() -> List[str]:
    """Gốc các ổ removable/fixed đang có trên Windows, ví dụ ['C:\\', 'E:\\']."""
    import ctypes
    import string

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    bitmask = kernel32.GetLogicalDrives()
    drives = []
    for i, letter in enumerate(string.ascii_uppercase):
        if bitmask & (1 << i):
            root = f"{letter}:\\"
            if kernel32.GetDriveTypeW(root) in _IPOD_DRIVE_TYPES:
                drives.append(root)
    return drives


def _candidate_mountpoints(system: str) -> List[str]:
    if system == "Windows":
        return _windows_drives()
    if system == "Darwin":
        bases = [(MACOS_VOLUMES, "*")]
    elif system == "Linux":
        bases = LINUX_MOUNT_GLOBS
    else:
        return []
    candidates = []
    for base, pattern in bases:
        try:
            candidates.extend(str(p) for p in sorted(base.glob(pattern)) if p.is_dir())
        except OSError:
            continue
    return candidates


def default_virtual_path() -> str:
    """Thư viện mặc định: iPod ảo trong data dir (tính lúc gọi: KLMM_DATA_DIR có thể đổi)."""
    return str(settings.data_dir() / "virtual_ipod")


def find_ipod_mountpoints(system: Optional[str] = None) -> List[str]:
    """Các mountpoint chứa cấu trúc iPod (iPod_Control/iTunes) theo hệ điều hành."""
    system = system or platform.system()
    return [mp for mp in _candidate_mountpoints(system) if validate_mountpoint(mp)]


# ---------------------------------------------------------------- cache nhận diện iPod qua USB
# iPod có SysInfo thiếu model/serial: pygpod hỏi USB (Windows: 3 lần PowerShell, ~2.5 s mỗi lần
# nạp) để lấy model + FirewireGuid (cần cho checksum HASH58). Kết quả chỉ phụ thuộc chiếc iPod
# -> cache theo volume serial của ổ + đường dẫn mount.
_original_usb_fallback = Device._try_usb_fallback
_usb_hook_lock = threading.Lock()


def _volume_key(path: str) -> str:
    """Định danh ổ chứa `path` ("" nếu không xác định được — không cache)."""
    if platform.system() != "Windows":
        return ""
    import ctypes

    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    serial = ctypes.c_uint32(0)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
        ctypes.c_wchar_p(root), None, 0, ctypes.byref(serial), None, None, None, 0
    )
    if not ok:
        return ""
    return f"{serial.value:08X}|{os.path.normcase(os.path.abspath(path))}"


def _read_device_cache(cache_file: Path) -> Dict[str, Any]:
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def open_ipod_database(mountpoint: str, cache_file: Path) -> "pygpod.Database":
    """pygpod.Database(mountpoint) nhưng dùng lại kết quả dò USB đã cache cho cùng ổ."""
    key = _volume_key(mountpoint)
    cache = _read_device_cache(cache_file) if key else {}

    def cached_fallback(sysinfo: Any) -> Any:
        entry = cache.get(key) if key else None
        if entry:
            logger.info("Using cached USB device info for %s", mountpoint)
            return lookup_model(entry["model_number"]), dict(entry.get("updates", {}))
        result = _original_usb_fallback(sysinfo)
        if result and key:
            info, updates = result
            cache[key] = {"model_number": info.model_number, "updates": dict(updates)}
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            except OSError:
                logger.warning("Cannot write %s", cache_file, exc_info=True)
        return result

    # Thay tạm hook của pygpod (khoá: Flask chạy nhiều luồng), luôn trả lại như cũ
    with _usb_hook_lock:
        saved = Device.__dict__["_try_usb_fallback"]
        Device._try_usb_fallback = staticmethod(cached_fallback)
        try:
            return pygpod.Database(mountpoint)
        finally:
            Device._try_usb_fallback = saved


def load_config() -> Dict[str, Any]:
    """Cài đặt hiện tại (xem settings.py). CONFIG_PATH = None -> theo KLMM_DATA_DIR lúc gọi."""
    return settings.load_settings(CONFIG_PATH)


def track_os_path(track: Any, mountpoint: str) -> str:
    """Đường dẫn file thật của bài trên iPod ("" nếu bài không có đường dẫn)."""
    parts = [p for p in (track.ipod_path or "").split(":") if p]
    return os.path.join(mountpoint, *parts) if parts else ""


def _iso(value: Any) -> Optional[str]:
    try:
        return value.isoformat() if value else None
    except (AttributeError, ValueError, OverflowError):
        return None


def track_record(track: Any, mountpoint: str) -> Dict[str, Any]:
    """Thông tin một bài cho export danh sách / thư viện."""
    return {
        "id": track.track_id,
        "title": track.title or "",
        "artist": track.artist or "",
        "album": track.album or "",
        "album_artist": track.albumartist or "",
        "genre": track.genre or "",
        "composer": track.composer or "",
        "year": track.year or 0,
        "track_number": track.track_number or 0,
        "total_tracks": track.total_tracks or 0,
        "disc_number": track.cd_number or 0,
        "duration_s": (track.duration_ms or 0) // 1000,
        "bitrate_kbps": track.bitrate or 0,
        "sample_rate": track.samplerate or 0,
        "file_type": track.filetype_str or "",
        "file_size": track.file_size or 0,
        "rating": (track.rating or 0) // 20,
        "play_count": track.play_count or 0,
        "date_added": _iso(track.time_added),
        "ipod_path": track.ipod_path or "",
        "file_path": track_os_path(track, mountpoint),
    }


class IPodManager:
    # Mặc định ở cấp lớp: đối tượng tạo không qua __init__ (test) vẫn là nguồn iPod
    folder: Optional[FolderLibrary] = None

    def __init__(self):
        self.config = load_config()
        self.read_only = self.config["read_only"]
        self.mountpoint: str = ""
        self.db: Optional[pygpod.Database] = None
        self.folder: Optional[FolderLibrary] = None  # khác None = nguồn là thư mục nhạc
        self._ipod_artwork: Optional[artwork.IPodArtwork] = None
        self.art_cache = artwork.ArtworkCache()
        self._library_db: Optional[LibraryDB] = None
        self.scan_lock = threading.Lock()  # chỉ 1 lần quét / dựng lại thư viện cùng lúc
        self.detect_device()

    @property
    def library_db(self) -> LibraryDB:
        """CSDL thư viện (<data dir>/library_cache/library.db), mở lần đầu khi cần."""
        if self._library_db is None:
            self._library_db = LibraryDB(settings.data_dir() / "library_cache" / DB_FILENAME)
        return self._library_db

    @property
    def source(self) -> str:
        return "folder" if self.folder is not None else "ipod"

    def open_folder(self, path: str) -> bool:
        """Dùng thư mục nhạc làm nguồn thư viện (quét + cache tag). False nếu không mở được."""
        try:
            library = FolderLibrary(path, db=self.library_db)
            library.scan()
        except OSError as e:
            logger.error(f"Cannot open music folder {path}: {e}")
            return False
        self.folder, self.db, self.mountpoint = library, None, path
        self._ipod_artwork = None
        self.art_cache.clear()
        return True

    def detect_device(self) -> str:
        """Nguồn thư viện theo cài đặt: thư mục nhạc, hoặc iPod (đường dẫn cấu hình / dò ổ /
        iPod ảo)."""
        self.folder = None
        self._ipod_artwork = None
        self.art_cache.clear()
        folder = self.config.get("library_folder")
        if self.config.get("library_source") == "default":
            logger.info("Using the default library (virtual iPod)")
            return self._open_virtual()
        if self.config.get("library_source") == "folder" and folder:
            if self.open_folder(folder):
                logger.info(f"Using music folder library: {folder}")
                return self.mountpoint
            logger.warning(f"Music folder {folder} unavailable; falling back to iPod")

        # 1. If path is explicitly specified in config, use it
        specified_path = self.config.get("ipod_path")
        if specified_path:
            logger.info(f"Using user-specified iPod path from config: {specified_path}")
            self.mountpoint = specified_path
            self.load_db()
            return self.mountpoint

        # 2. Scan mounted volumes (/Volumes, drive letters, /media) for a physical iPod
        for path in find_ipod_mountpoints():
            logger.info(f"Detected physical iPod connected at: {path}")
            self.mountpoint = path
            self.load_db()
            return self.mountpoint

        # 3. Không có iPod thật -> thư viện mặc định (iPod ảo)
        logger.info("No physical iPod detected; using the default library (virtual iPod)")
        return self._open_virtual()

    def _open_virtual(self) -> str:
        """Mở thư viện mặc định (iPod ảo trong data dir); tạo mới (trống) nếu chưa có."""
        path = default_virtual_path()
        self.mountpoint = path
        if not os.path.exists(path):
            if self.read_only:
                logger.warning(f"Default library {path} does not exist and read_only is active")
                return ""
            os.makedirs(path, exist_ok=True)
        if not validate_mountpoint(path):
            if self.read_only:
                logger.error(f"{path} is not a valid iPod folder and read_only is active")
                return ""
            logger.info("Initializing an empty default library (virtual iPod)...")
            init_ipod(path, model="classic_6g", music_dirs=20)
        self.load_db()
        return self.mountpoint

    def load_db(self):
        """Load the iTunesDB database from the current mountpoint."""
        try:
            self.db = open_ipod_database(self.mountpoint, settings.data_dir() / "device_cache.json")
            logger.info(f"Successfully loaded iTunesDB from {self.mountpoint}")
        except Exception as e:
            logger.error(f"Error loading database from {self.mountpoint}: {e}")
            self.db = None

    def get_device_info(self) -> Dict[str, Any]:
        """Get connected device information and storage stats."""
        if self.folder is not None:
            try:
                usage = shutil.disk_usage(self.mountpoint)
                total, free = usage.total, usage.free
            except OSError:
                total = free = 0
            playlists = self.folder.playlists()
            return {
                "source": "folder",
                "model": f"Music Folder: {Path(self.mountpoint).name or self.mountpoint}",
                "mountpoint": self.mountpoint,
                "host_os": platform.system(),
                "is_virtual": False,
                "is_read_only": self.read_only,
                "total_space": total,
                "free_space": free,
                "used_space": total - free,
                "tracks_count": len(playlists[0]["track_ids"]),
                "playlists_count": len(playlists),
            }

        is_virtual = self.is_default
        model = "Virtual iPod Classic (6G)" if is_virtual else "iPod Device"

        if self.db and self.db.device:
            model = self.db.device.model
            if is_virtual:
                model = f"Virtual {model}"

        # Disk space calculations
        total_space = 0
        free_space = 0
        used_space = 0

        try:
            usage = shutil.disk_usage(self.mountpoint)
            total_space = usage.total
            free_space = usage.free
            used_space = total_space - free_space
        except Exception as e:
            logger.error(f"Failed to read disk stats: {e}")
            # Fallback mock stats for virtual
            total_space = 80 * 1024 * 1024 * 1024  # 80 GB
            free_space = 72 * 1024 * 1024 * 1024  # 72 GB
            used_space = total_space - free_space

        return {
            "source": "ipod",
            "model": model,
            "mountpoint": self.mountpoint,
            "host_os": platform.system(),
            "is_virtual": is_virtual,
            "is_read_only": self.read_only,
            "total_space": total_space,
            "free_space": free_space,
            "used_space": used_space,
            "tracks_count": len(self.db.tracks) if self.db else 0,
            "playlists_count": len(self.db.playlists) if self.db else 0,
        }

    def get_tracks(self) -> List[Dict[str, Any]]:
        """Get all tracks in the database."""
        if self.folder is not None:
            return self.folder.tracks()
        if not self.db:
            return []

        tracks_list = []
        for track in self.db.tracks:
            # Safely resolve path
            ipod_file_path = ""
            if track.ipod_path:
                # Convert colon separated iPod path (e.g. :iPod_Control:Music:F00:SNG1.mp3) to real path
                parts = [p for p in track.ipod_path.split(":") if p]
                if parts:
                    ipod_file_path = os.path.join(self.mountpoint, *parts)

            tracks_list.append(
                {
                    "id": track.track_id,
                    "title": track.title or "Unknown Title",
                    "artist": track.artist or "Unknown Artist",
                    "album": track.album or "Unknown Album",
                    "album_artist": track.albumartist or "",
                    "composer": track.composer or "",
                    "genre": track.genre or "Unknown Genre",
                    "duration": track.duration_ms // 1000 if track.duration_ms else 0,
                    "rating": track.rating // 20
                    if track.rating
                    else 0,  # rating is 0-100, normalize to 0-5 stars
                    "play_count": track.play_count or 0,
                    "year": track.year or 0,
                    "track_number": track.track_number or 0,
                    "file_size": track.file_size or 0,
                    "file_path": ipod_file_path,
                }
            )
        return tracks_list

    def get_playlists(self) -> List[Dict[str, Any]]:
        """Get all playlists in the database."""
        if self.folder is not None:
            return self.folder.playlists()
        if not self.db:
            return []

        playlists_list = []
        for pl in self.db.playlists:
            playlists_list.append(
                {
                    "id": id(
                        pl
                    ),  # Pygpod Playlist object doesn't have a unique numeric ID property, we use Python's memory id
                    "name": pl.name,
                    "is_master": pl.is_master,
                    "is_smart": pl.is_smart,
                    "track_ids": pl.track_ids or [],
                }
            )
        return playlists_list

    def add_track(
        self, local_file_path: str, metadata: Dict[str, Any], playlist: Optional[str] = None
    ) -> Optional[int]:
        """Thêm bài vào thư viện (iPod: copy lên iPod; thư mục: copy vào Artist/Album/).
        `playlist`: thêm luôn vào playlist này (tạo nếu chưa có). Trả id bài, None nếu lỗi."""
        return self.add_track_detailed(local_file_path, metadata, playlist)["track_id"]

    def add_track_detailed(
        self, local_file_path: str, metadata: Dict[str, Any], playlist: Optional[str] = None
    ) -> Dict[str, Any]:
        """Như add_track, trả {"track_id": id | None, "converted": "FLAC → ALAC" | None,
        "error": str | None}. iPod: file iPod không phát được được chuyển định dạng trước
        (cài đặt ipod_import_convert); thiếu ffmpeg thì không chép."""
        result: Dict[str, Any] = {"track_id": None, "converted": None, "error": None}
        if self.folder is not None:
            try:
                result["track_id"] = self.folder.import_file(
                    local_file_path, playlist=playlist, metadata=metadata
                )
            except (OSError, ValueError) as e:
                logger.error(f"Failed to import {local_file_path}: {e}")
                result["error"] = str(e)
            return result
        if not self.db:
            result["error"] = "No iPod database is open"
            return result

        mode = self.config.get("ipod_import_convert", "auto")
        target = converter.ipod_import_target(local_file_path, mode)
        if target is None:
            result["track_id"], result["error"] = self._add_ipod_track(
                local_file_path, metadata, playlist
            )
        else:
            fmt, options = target
            source_codec = (
                tag_editor.read_file(local_file_path)["codec"]
                or Path(local_file_path).suffix.lstrip(".").upper()
            )
            label = f"{source_codec} → {converter.FORMAT_LABELS[fmt]}"
            ffmpeg = self.ffmpeg_path()
            if not ffmpeg:
                result["error"] = (
                    f"The iPod cannot play {source_codec} files and ffmpeg was not found "
                    "to convert them (set its path in Settings)"
                )
                return result
            work = tempfile.mkdtemp(prefix="klmm_ipod_")
            try:
                ext = converter.FORMATS[fmt].ext
                converted = os.path.join(work, Path(local_file_path).stem + ext)
                converter.convert(local_file_path, converted, fmt, options, {}, ffmpeg)
                logger.info(f"Converted for iPod ({label}): {local_file_path}")
                result["track_id"], result["error"] = self._add_ipod_track(
                    converted, metadata, playlist
                )
                result["converted"] = label
            except converter.ConversionError as e:
                logger.error(f"Cannot convert {local_file_path} for the iPod: {e}")
                result["error"] = f"Conversion failed ({label}): {e}"
                return result
            finally:
                shutil.rmtree(work, ignore_errors=True)
        if result["track_id"] is None and not result["error"]:
            result["error"] = "Import failed (see log)"
        return result

    def _add_ipod_track(
        self, local_file_path: str, metadata: Dict[str, Any], playlist: Optional[str]
    ) -> Tuple[Optional[int], Optional[str]]:
        """Chép 1 file vào iPod + playlist; trả (id, None) hoặc (None, lỗi). pygpod tự từ chối
        định dạng iPod không phát được (FLAC, OGG, Opus…)."""
        try:
            # Overrides provided in metadata
            kwargs = {}
            for field in ["title", "artist", "album", "genre", "year", "comment", "track_number"]:
                if field in metadata and metadata[field]:
                    kwargs[field] = metadata[field]

            if metadata.get("rating"):
                kwargs["rating"] = int(metadata["rating"]) * 20  # 0-5 stars to 0-100

            track = self.db.add_track(local_file_path, **kwargs)
            if playlist:
                # Không dùng `or`: Playlist có __len__ nên playlist rỗng là falsy
                target = self.find_playlist(playlist)
                if target is None:
                    target = self.db.create_playlist(playlist)
                self.db.add_track_to_playlist(target, track)
            self.db.save()
            return track.track_id, None
        except Exception as e:
            logger.error(f"Failed to add track: {e}")
            return None, str(e) or "Import failed (see log)"

    def import_paths(
        self, paths: List[str], playlist: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Import nhiều file / thư mục (quét đệ quy, chỉ file âm thanh). Kết quả từng file."""
        files: List[str] = []
        for p in paths:
            if os.path.isdir(p):
                for dirpath, dirnames, filenames in os.walk(p):
                    dirnames.sort()
                    files += [
                        os.path.join(dirpath, f)
                        for f in sorted(filenames)
                        if os.path.splitext(f)[1].lower() in AUDIO_EXTS
                    ]
            else:
                files.append(p)
        results = []
        for f in files:
            if not os.path.isfile(f) or os.path.splitext(f)[1].lower() not in AUDIO_EXTS:
                results.append({"path": f, "ok": False, "error": "Not a supported audio file"})
                continue
            r = self.add_track_detailed(f, {}, playlist=playlist)
            if r["track_id"] is not None:
                results.append(
                    {"path": f, "ok": True, "track_id": r["track_id"], "converted": r["converted"]}
                )
            else:
                results.append({"path": f, "ok": False, "error": r["error"]})
        return results

    def remove_track(self, track_id: int) -> bool:
        """Remove a track from the database and delete its file on the device."""
        if self.folder is not None:
            return self.folder.delete_track(track_id)
        if not self.db:
            return False

        try:
            track = self.db.get_track(track_id)
            if not track:
                logger.error(f"Track with ID {track_id} not found")
                return False

            self.db.remove_track(track, delete_file=True)
            self.db.save()
            return True
        except Exception as e:
            logger.error(f"Failed to remove track: {e}")
            return False

    def export_track(self, track_id: int, export_dir: str) -> Optional[str]:
        """Export track from the iPod back to a directory on the Mac."""
        if self.folder is not None:
            try:
                return self.export_track_as(track_id, "original", {}, export_dir)
            except (KeyError, OSError) as e:
                logger.error(f"Failed to export track: {e}")
                return None
        if not self.db:
            return None

        try:
            track = self.db.get_track(track_id)
            if not track:
                return None

            # Find the actual path of the file on the iPod
            parts = [p for p in track.ipod_path.split(":") if p]
            src_path = os.path.join(self.mountpoint, *parts)

            if not os.path.exists(src_path):
                # If virtual or file missing, look for it in welcome path or fallback
                return None

            os.makedirs(export_dir, exist_ok=True)
            # Create a clean filename: "Artist - Title.ext"
            ext = os.path.splitext(src_path)[1] or ".mp3"
            clean_name = (
                f"{track.artist or 'Unknown Artist'} - {track.title or 'Unknown Title'}{ext}"
            )
            # Replace invalid filesystem characters
            for char in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
                clean_name = clean_name.replace(char, "_")

            dest_path = os.path.join(export_dir, clean_name)
            shutil.copy2(src_path, dest_path)
            return dest_path
        except Exception as e:
            logger.error(f"Failed to export track: {e}")
            return None

    def update_track_metadata(self, track_id: int, metadata: Dict[str, Any]) -> bool:
        """Update metadata fields for a specific track."""
        if self.folder is not None:
            changes = {k: v for k, v in metadata.items() if k != "rating"}  # file không có rating
            ok = self.folder.update_tags(track_id, changes)
            if ok:
                self.art_cache.clear()
            return ok
        if not self.db:
            return False

        try:
            track = self.db.get_track(track_id)
            if not track:
                return False

            if "title" in metadata:
                track.title = metadata["title"]
            if "artist" in metadata:
                track.artist = metadata["artist"]
            if "album" in metadata:
                track.album = metadata["album"]
            if "album_artist" in metadata:
                track.albumartist = metadata["album_artist"] or ""
            if "composer" in metadata:
                track.composer = metadata["composer"] or ""
            if "genre" in metadata:
                track.genre = metadata["genre"]
            if "year" in metadata:
                track.year = int(metadata["year"]) if metadata["year"] else 0
            if "track_number" in metadata:
                track.track_number = (
                    int(metadata["track_number"]) if metadata["track_number"] else 0
                )
            if "rating" in metadata:
                track.rating = int(metadata["rating"]) * 20

            self.db.save()
            return True
        except Exception as e:
            logger.error(f"Failed to update metadata: {e}")
            return False

    def create_playlist(self, name: str) -> bool:
        """Create a new playlist."""
        if self.folder is not None:
            return self.folder.create_playlist(name)
        if not self.db:
            return False
        try:
            self.db.create_playlist(name)
            self.db.save()
            return True
        except Exception as e:
            logger.error(f"Failed to create playlist: {e}")
            return False

    def delete_playlist(self, playlist_name: str) -> bool:
        """Delete a playlist by name."""
        if self.folder is not None:
            return self.folder.delete_playlist(playlist_name)
        if not self.db:
            return False
        try:
            target_pl = None
            for pl in self.db.playlists:
                if pl.name == playlist_name and not pl.is_master:
                    target_pl = pl
                    break
            if target_pl is not None:
                self.db.delete_playlist(target_pl)
                self.db.save()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete playlist: {e}")
            return False

    def add_track_to_playlist(self, playlist_name: str, track_id: int) -> bool:
        """Add track to a playlist."""
        if self.folder is not None:
            return self.folder.add_to_playlist(playlist_name, track_id)
        if not self.db:
            return False
        try:
            track = self.db.get_track(track_id)
            target_pl = None
            for pl in self.db.playlists:
                if pl.name == playlist_name:
                    target_pl = pl
                    break
            if track is not None and target_pl is not None:
                self.db.add_track_to_playlist(target_pl, track)
                self.db.save()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to add track to playlist: {e}")
            return False

    def remove_track_from_playlist(self, playlist_name: str, track_id: int) -> bool:
        """Remove a track from a playlist."""
        if self.folder is not None:
            return self.folder.remove_from_playlist(playlist_name, track_id)
        if not self.db:
            return False
        try:
            track = self.db.get_track(track_id)
            target_pl = None
            for pl in self.db.playlists:
                if pl.name == playlist_name:
                    target_pl = pl
                    break
            if track is not None and target_pl is not None:
                self.db.remove_track_from_playlist(target_pl, track)
                self.db.save()
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove track from playlist: {e}")
            return False

    def repair_db(self) -> bool:
        """Recalculate hashes and checksums of the database (thư mục: quét lại)."""
        if self.folder is not None:
            try:
                self.folder.scan()
                self.art_cache.clear()
                return True
            except OSError as e:
                logger.error(f"Rescan failed: {e}")
                return False
        if not self.db:
            return False
        try:
            self.db.save()  # pygpod automatically recalculates checksums and hashes on save
            return True
        except Exception as e:
            logger.error(f"Database repair failed: {e}")
            return False

    # ------------------------------------------------------------ settings / export / stream
    def apply_settings(self, new_config: Dict[str, Any]) -> None:
        """Áp cài đặt mới ngay (read-only có hiệu lực cho request kế tiếp)."""
        self.config = new_config
        self.read_only = new_config["read_only"]

    def ffmpeg_path(self) -> Optional[str]:
        return converter.find_ffmpeg(self.config.get("ffmpeg_path", ""))

    def find_playlist(self, name: str) -> Optional[Any]:
        if not self.db:
            return None
        return next((pl for pl in self.db.playlists if pl.name == name), None)

    def get_track_records(self, playlist_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Bản ghi chi tiết của toàn bộ bài, hoặc các bài trong một playlist (theo thứ tự)."""
        if self.folder is not None:
            if playlist_name is None:
                return self.folder.records()
            pl = next((p for p in self.folder.playlists() if p["name"] == playlist_name), None)
            if pl is None:
                raise KeyError(playlist_name)
            return self.folder.records(pl["track_ids"])
        if not self.db:
            return []
        if playlist_name is None:
            tracks = list(self.db.tracks)
        else:
            pl = self.find_playlist(playlist_name)
            if pl is None:
                raise KeyError(playlist_name)
            by_id = {t.track_id: t for t in self.db.tracks}
            tracks = [by_id[i] for i in (pl.track_ids or []) if i in by_id]
        return [track_record(t, self.mountpoint) for t in tracks]

    EXPORT_LAYOUTS = ("flat", "artist_album")

    def export_track_as(
        self, track_id: int, fmt: str, options: Dict[str, Any], dest_dir: str
    ) -> str:
        """Export một bài (convert nếu fmt khác "original") vào dest_dir; trả đường dẫn file.

        Raises: như export_track_to.
        """
        return self.export_track_to(track_id, fmt, options, dest_dir)["path"]

    def export_track_to(
        self,
        track_id: int,
        fmt: str,
        options: Dict[str, Any],
        dest_dir: str,
        layout: str = "flat",
        subfolder: str = "",
        skip_existing: bool = False,
    ) -> Dict[str, Any]:
        """Export một bài vào dest_dir[/subfolder][/Artist/Album]; trả {"path", "skipped", "root"}
        (root = dest_dir[/subfolder]).

        Gọi song song an toàn: tên file đích được giữ chỗ nguyên tử (không 2 bài ghi cùng file).
        skip_existing: file cùng tên đã có -> không ghi, trả skipped=True.

        Raises:
            KeyError: không có bài / file không tồn tại trên iPod.
            ValueError: định dạng / layout không hỗ trợ.
            converter.ConversionError: ffmpeg lỗi / không có ffmpeg.
        """
        if fmt not in converter.FORMATS:
            raise ValueError(f"Unsupported format: {fmt}")
        if layout not in self.EXPORT_LAYOUTS:
            raise ValueError(f"Unsupported layout: {layout}")
        meta = self._track_meta(track_id)
        if meta is None:
            raise KeyError(track_id)
        src = meta["path"]

        folder = Path(dest_dir)
        if subfolder:
            folder /= converter.safe_component(subfolder)
        root = str(folder)  # thư mục gốc của lần export (nút Show Folder mở thư mục này)
        if layout == "artist_album":
            artist = meta.get("album_artist") or meta.get("artist")
            folder /= converter.safe_component(artist, "Unknown Artist")
            folder /= converter.safe_component(meta.get("album"), "Unknown Album")
        folder.mkdir(parents=True, exist_ok=True)
        ext = converter.FORMATS[fmt].ext or (os.path.splitext(src)[1] or ".mp3")
        target = str(folder / converter.output_filename(meta, ext))
        if skip_existing and os.path.exists(target):
            return {"path": target, "skipped": True, "root": root}
        dest = _reserve_path(target)
        try:
            if fmt == "original":
                shutil.copy2(src, dest)
            else:
                tags = {
                    "title": meta["title"],
                    "artist": meta["artist"],
                    "album": meta["album"],
                    "album_artist": meta["album_artist"],
                    "genre": meta["genre"],
                    "date": meta["year"] or None,
                    "track": meta["track_number"] or None,
                }
                converter.convert(src, dest, fmt, options, tags, self.ffmpeg_path())
        except BaseException:
            Path(dest).unlink(missing_ok=True)  # bỏ chỗ đã giữ (file rỗng / dở)
            raise
        return {"path": dest, "skipped": False, "root": root}

    def track_file(self, track_id: int) -> Optional[str]:
        """Đường dẫn file thật của bài (cả 2 nguồn), None nếu không có bài hoặc file đã mất."""
        meta = self._track_meta(track_id)
        return meta["path"] if meta else None

    def _track_meta(self, track_id: int) -> Optional[Dict[str, Any]]:
        if self.folder is not None:
            t = self.folder.get(track_id)
            if t is None or not os.path.exists(t["file_path"]):
                return None
            return {**t, "path": t["file_path"], "file_type": self.folder.file_type(track_id)}
        track = self.db.get_track(track_id) if self.db else None
        if track is None:
            return None
        src = track_os_path(track, self.mountpoint)
        if not src or not os.path.exists(src):
            return None
        return {
            "path": src,
            "title": track.title or "",
            "artist": track.artist or "",
            "album": track.album or "",
            "album_artist": track.albumartist or "",
            "composer": track.composer or "",
            "genre": track.genre or "",
            "year": track.year or 0,
            "track_number": track.track_number or 0,
            "file_type": track.filetype_str or "",
            "dbid": track.dbid,
            "mhii_link": track.mhii_link or 0,
        }

    def artwork_jpeg(self, track_id: int) -> Optional[bytes]:
        """Ảnh bìa JPEG (≤600 px): nhúng trong file -> ảnh cùng thư mục -> ArtworkDB iPod."""
        key = f"{self.source}:{self.mountpoint}:{track_id}"
        hit, cached = self.art_cache.get(key)
        if hit:
            return cached
        meta = self._track_meta(track_id)
        data = artwork.artwork_for_file(meta["path"]) if meta else None
        if data is None and meta is not None and self.folder is None:
            if self._ipod_artwork is None:
                self._ipod_artwork = artwork.IPodArtwork(self.mountpoint)
            data = self._ipod_artwork.get(meta["dbid"], meta["mhii_link"])
        result = artwork.to_jpeg(data) if data else None
        self.art_cache.put(key, result)
        return result

    @property
    def is_default(self) -> bool:
        """Đang mở thư viện mặc định (iPod ảo trong data dir)."""
        return (
            self.folder is None
            and bool(self.mountpoint)
            and os.path.normcase(os.path.abspath(self.mountpoint))
            == os.path.normcase(os.path.abspath(default_virtual_path()))
        )

    def source_info(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "is_default": self.is_default,
            "connected_ipods": find_ipod_mountpoints(),
            "folder": self.config.get("library_folder", ""),
            "recent_folders": self.config.get("recent_folders", []),
            "mountpoint": self.mountpoint,
        }

    def set_source(self, source: str, folder: str = "") -> None:
        """Chuyển nguồn thư viện và lưu vào cài đặt.

        Raises:
            ValueError: source không hợp lệ / thư mục không tồn tại hoặc không quét được.
        """
        if source == "folder":
            if not folder or not os.path.isdir(folder):
                raise ValueError(f"Folder not found: {folder}")
            if not self.open_folder(folder):
                raise ValueError(f"Cannot open folder: {folder}")
            recent = [folder] + [f for f in self.config.get("recent_folders", []) if f != folder]
            changes = {
                "library_source": "folder",
                "library_folder": folder,
                "recent_folders": recent[: settings.MAX_RECENT_FOLDERS],
            }
        elif source in ("ipod", "default"):
            changes = {"library_source": source}
        else:
            raise ValueError(f"Unknown library source: {source}")
        self.config = settings.update_settings(changes, CONFIG_PATH)
        if source in ("ipod", "default"):
            self.detect_device()

    # ------------------------------------------------------------ thông tin file + ảnh bìa
    def track_details(self, track_id: int) -> Optional[Dict[str, Any]]:
        """Thông số file (codec, bitrate, sample rate, bit depth, kênh, dung lượng) + tag đầy đủ.
        None nếu không có bài / file."""
        meta = self._track_meta(track_id)
        if meta is None:
            return None
        path = meta["path"]
        info = tag_editor.read_file(path, with_lyrics=True)
        if self.folder is not None:
            tags = {f: info[f] for f in tag_editor.FIELDS}
            tags["title"] = tags["title"] or meta["title"]
        else:
            tags = {f: meta.get(f, info[f]) for f in tag_editor.FIELDS}
        return {
            "id": track_id,
            "source": self.source,
            "codec": info["codec"],
            "bitrate_kbps": info["bitrate_kbps"],
            "sample_rate": info["sample_rate"],
            "channels": info["channels"],
            "bits_per_sample": info["bits_per_sample"],
            "duration_s": info["duration_s"],
            "file_size": os.path.getsize(path),
            "file_type": meta["file_type"],
            "extension": Path(path).suffix.lower().lstrip("."),
            "has_cover": info["has_cover"],
            "cover_editable": self.folder is not None,
            "tags": tags,
        }

    def set_track_cover(
        self, track_id: int, image: Optional[bytes], apply_album: bool = False
    ) -> int:
        """Đặt (image=None: xoá) ảnh bìa nhúng; chỉ thư viện thư mục. Trả số file đã ghi.

        Raises:
            ValueError: nguồn iPod / ảnh không hợp lệ / định dạng không ghi được.
            LookupError: không có bài.
        """
        if self.folder is None:
            raise ValueError("Cover editing is only available for folder libraries")
        count = self.folder.set_cover(track_id, image, apply_album)
        if count == 0:
            raise LookupError(f"Track {track_id} not found")
        self.art_cache.clear()
        return count

    # ------------------------------------------------------------ nhiều thư viện
    @contextlib.contextmanager
    def _scanning(self) -> Iterator[None]:
        if not self.scan_lock.acquire(blocking=False):
            raise ScanBusy("A library scan is already in progress")
        try:
            yield
        finally:
            self.scan_lock.release()

    def _active_library_id(self) -> Optional[int]:
        return self.folder.library_id if self.folder is not None else None

    def _library(self, library_id: int) -> Dict[str, Any]:
        lib = self.library_db.get_library(library_id)
        if lib is None:
            raise LookupError(f"Library {library_id} not found")
        return lib

    def _library_info(self, lib: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **lib,
            "active": lib["id"] == self._active_library_id(),
            "available": os.path.isdir(lib["root"]),
        }

    def list_libraries(self) -> List[Dict[str, Any]]:
        return [self._library_info(lib) for lib in self.library_db.libraries()]

    def _scan_one(self, lib: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """Quét 1 thư viện (đang mở: quét bản trong bộ nhớ). Raises OSError nếu mất thư mục."""
        active = lib["id"] == self._active_library_id()
        if active:
            stats = self.folder.scan(force=force)
            self.art_cache.clear()
        else:
            stats = FolderLibrary(lib["root"], db=self.library_db).scan(force=force)
        return {**stats, "active": active}

    def create_library(self, name: str, root: str) -> Dict[str, Any]:
        """Đăng ký thư mục làm thư viện và quét. Raises ValueError, ScanBusy."""
        if not root or not os.path.isdir(root):
            raise ValueError(f"Folder not found: {root}")
        with self._scanning():
            lib = self.library_db.add_library(name, root)
            self._scan_one(lib)
        return self._library_info(self._library(lib["id"]))

    def rename_library(self, library_id: int, name: str) -> Dict[str, Any]:
        self._library(library_id)
        self.library_db.rename_library(library_id, name)
        return self._library_info(self._library(library_id))

    def remove_library(self, library_id: int) -> bool:
        """Gỡ thư viện + metadata đã lập chỉ mục (không xoá file). Thư viện đang mở thì chuyển về
        thư viện mặc định. Trả True nếu đã chuyển. Raises LookupError nếu không có."""
        self._library(library_id)
        active = library_id == self._active_library_id()
        self.library_db.remove_library(library_id)
        if active:
            self.set_source("default")
        return active

    def open_library(self, library_id: int) -> None:
        self.set_source("folder", self._library(library_id)["root"])

    def scan_library(self, library_id: int, force: bool = False) -> Dict[str, Any]:
        """Quét lại (force=True: đọc lại tag mọi file). Raises LookupError, ScanBusy, OSError."""
        lib = self._library(library_id)
        with self._scanning():
            return self._scan_one(lib, force=force)

    def clear_library(self, library_id: int) -> Dict[str, Any]:
        """Xoá metadata đã lập chỉ mục (không đổi file nhạc); thư viện đang mở thì quét lại ngay."""
        lib = self._library(library_id)
        with self._scanning():
            self.library_db.clear_tracks(library_id)
            if lib["id"] == self._active_library_id():
                return self._scan_one(lib)
        return {"added": 0, "changed": 0, "removed": 0, "total": 0, "active": False}

    def _auto_rescan_due(self) -> bool:
        if not self.config.get("auto_rescan_idle"):
            return False
        try:
            last = datetime.datetime.fromisoformat(self.config.get("last_auto_rescan", ""))
        except ValueError:
            return True
        hours = self.config.get("auto_rescan_interval_hours", 24)
        return datetime.datetime.now() - last >= datetime.timedelta(hours=hours)

    def rescan_all(self, only_if_due: bool = False) -> Dict[str, Any]:
        """Quét tăng dần mọi thư viện còn thư mục. only_if_due: chỉ chạy khi bật quét lúc rảnh
        và đã quá khoảng cách cài đặt (Electron gọi khi máy rảnh)."""
        if only_if_due and not self._auto_rescan_due():
            return {"skipped": True}
        total = {"added": 0, "changed": 0, "removed": 0, "total": 0}
        active_changed, scanned = False, 0
        with self._scanning():
            for lib in self.library_db.libraries():
                if not os.path.isdir(lib["root"]):
                    continue
                try:
                    stats = self._scan_one(lib)
                except OSError:
                    logger.warning("Rescan failed for %s", lib["root"], exc_info=True)
                    continue
                scanned += 1
                for key in total:
                    total[key] += stats[key]
                if stats["active"] and (stats["added"] or stats["changed"] or stats["removed"]):
                    active_changed = True
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self.config = settings.update_settings({"last_auto_rescan": now}, CONFIG_PATH)
        return {"skipped": False, **total, "libraries": scanned, "active_changed": active_changed}

    # ------------------------------------------------------------ dọn dẹp
    def _stream_cache_dir(self) -> Path:
        return settings.data_dir() / "stream_cache"

    def maintenance_info(self) -> Dict[str, Any]:
        cache = self._stream_cache_dir()
        stream_bytes = 0
        if cache.is_dir():
            stream_bytes = sum(p.stat().st_size for p in cache.iterdir() if p.is_file())
        return {
            "db_path": str(self.library_db.path),
            "db_bytes": self.library_db.file_size(),
            "artwork_cache_items": len(self.art_cache),
            "stream_cache_bytes": stream_bytes,
            "libraries": self.list_libraries(),
        }

    def clear_cache(self) -> int:
        """Xoá cache ảnh bìa (bộ nhớ) + file chuyển mã trong stream_cache/. Trả số byte đã giải
        phóng (file đang phát / bị khoá thì bỏ qua)."""
        self.art_cache.clear()
        self._ipod_artwork = None
        freed = 0
        cache = self._stream_cache_dir()
        if cache.is_dir():
            for p in cache.iterdir():
                if not p.is_file():
                    continue
                size = p.stat().st_size
                try:
                    p.unlink()
                    freed += size
                except OSError:
                    logger.info("Cache file in use, kept: %s", p)
        return freed

    def stream_path(self, track_id: int) -> Optional[str]:
        """File để phát trong app: bản gốc, hoặc bản FLAC chuyển mã nếu bật stream_unsupported
        và trình duyệt không giải mã được (ALAC). None nếu không có bài/file."""
        meta = self._track_meta(track_id)
        if meta is None:
            return None
        src = meta["path"]
        if self.config.get("stream_unsupported") and converter.is_browser_unsupported(
            src, meta["file_type"]
        ):
            ffmpeg = self.ffmpeg_path()
            if ffmpeg:
                cache = str(settings.data_dir() / "stream_cache")
                try:
                    return converter.transcode_for_stream(src, cache, ffmpeg)
                except converter.ConversionError as e:
                    logger.error(f"Stream transcode failed for {src}: {e}")
            else:
                logger.warning("stream_unsupported is on but ffmpeg was not found")
        return src


def _reserve_path(path: str) -> str:
    """Đường dẫn chưa có (thêm " (2)", " (3)"...) và tạo luôn file rỗng (O_EXCL) để giữ chỗ:
    2 luồng export cùng tên không thể chọn cùng một đường dẫn."""
    base, ext = os.path.splitext(path)
    candidate, n = path, 2
    while True:
        try:
            os.close(os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return candidate
        except FileExistsError:
            candidate = f"{base} ({n}){ext}"
            n += 1
