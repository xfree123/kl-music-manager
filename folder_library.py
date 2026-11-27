"""Thư viện nhạc là một thư mục trên máy: quét đệ quy, đọc tag (mutagen), playlist .m3u8.

- id bài = 48 bit đầu của sha1(đường dẫn tương đối) -> ổn định giữa các lần quét, an toàn với số JS.
- Metadata lưu trong SQLite (library_db, <cache_dir>/library.db, dùng chung cho mọi thư viện),
  so theo kích thước + mtime -> mở lại nhanh; force=True đọc lại tag mọi file.
- Playlist = file .m3u/.m3u8 bất kỳ trong thư mục; playlist mới tạo ở <thư mục>/Playlists/.
- Import = copy vào <thư mục>/<Artist>/<Album>/<tên file>.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import converter
import tag_editor
from library_db import DB_FILENAME, LibraryDB

logger = logging.getLogger(__name__)

AUDIO_EXTS = (
    ".mp3",
    ".m4a",
    ".m4b",
    ".aac",
    ".flac",
    ".wav",
    ".ogg",
    ".oga",
    ".opus",
    ".aif",
    ".aiff",
)
PLAYLIST_EXTS = (".m3u", ".m3u8")
PLAYLISTS_DIR = "Playlists"
_FILE_TYPES = {
    ".mp3": "MPEG audio file",
    ".aac": "AAC audio file",
    ".flac": "FLAC audio file",
    ".wav": "WAV audio file",
    ".ogg": "Ogg Vorbis audio file",
    ".oga": "Ogg Vorbis audio file",
    ".opus": "Opus audio file",
    ".aif": "AIFF audio file",
    ".aiff": "AIFF audio file",
}


def track_id_for(relpath: str) -> int:
    key = relpath.replace("\\", "/").lower()
    return int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:12], 16) or 1


def read_tags(path: str) -> Dict[str, Any]:
    """Tag + thông số âm thanh của một file (không gồm lyrics). Không đọc được thì giá trị rỗng."""
    return tag_editor.read_file(path)


def _file_type(path: str, codec: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in (".m4a", ".m4b"):
        return "Apple Lossless audio file" if codec == "alac" else "AAC audio file"
    return _FILE_TYPES.get(ext, "Audio file")


def safe_name(text: str, default: str) -> str:
    name = (text or "").strip()
    for ch in converter.INVALID_FILENAME_CHARS:
        name = name.replace(ch, "_")
    name = name.strip().rstrip(".")
    return name or default


def _unique_path(path: Path) -> Path:
    candidate, n = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def _norm(path: Union[str, Path]) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


class FolderLibrary:
    def __init__(
        self, root: str, cache_dir: Optional[str] = None, db: Optional[LibraryDB] = None
    ) -> None:
        """db: CSDL dùng chung (ipod_manager); không có thì mở <cache_dir>/library.db;
        cả hai đều None -> chỉ giữ trong bộ nhớ."""
        self.root = Path(root)
        if db is None and cache_dir:
            db = LibraryDB(Path(cache_dir) / DB_FILENAME)
        self.db = db
        self.library_id: Optional[int] = None
        if db is not None:
            found = db.library_for_root(self.root)
            if found is None:
                found = db.add_library(self.root.name or str(self.root), self.root)
            self.library_id = found["id"]
        self._lock = threading.RLock()
        self._entries: Dict[int, Dict[str, Any]] = {}  # id -> entry (relpath, size, mtime_ns, tags)
        self._by_path: Dict[str, int] = {}  # đường dẫn tuyệt đối chuẩn hoá -> id
        self._playlists: Dict[str, Path] = {}  # tên -> file .m3u8

    # ------------------------------------------------------------ quét
    def _make_entry(
        self, path: Path, cached: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], bool]:
        """(entry, đã đọc lại tag?) — dùng tag trong DB nếu size + mtime khớp."""
        st = path.stat()
        relpath = path.relative_to(self.root).as_posix()
        if cached and cached.get("size") == st.st_size and cached.get("mtime_ns") == st.st_mtime_ns:
            tags, reread = cached["tags"], False
        else:
            tags, reread = read_tags(str(path)), True
        entry = {"relpath": relpath, "size": st.st_size, "mtime_ns": st.st_mtime_ns, "tags": tags}
        return entry, reread

    def _add_entry(self, entry: Dict[str, Any]) -> int:
        track_id = track_id_for(entry["relpath"])
        self._entries[track_id] = entry
        self._by_path[_norm(self.root / entry["relpath"])] = track_id
        return track_id

    def _persist(self, entry: Dict[str, Any]) -> None:
        if self.db is not None:
            self.db.upsert_track(self.library_id, entry["relpath"], entry)

    def _refresh(self, path: Path) -> int:
        """Đọc lại 1 file sau khi ghi (tag / ảnh bìa) -> bộ nhớ + DB."""
        entry, _ = self._make_entry(path)
        track_id = self._add_entry(entry)
        self._persist(entry)
        return track_id

    def scan(self, force: bool = False) -> Dict[str, int]:
        """Quét thư mục, đồng bộ DB. force=True: đọc lại tag mọi file.

        Returns: {"added", "changed", "removed", "total"} so với dữ liệu đã lưu.
        """
        if not self.root.is_dir():
            raise FileNotFoundError(str(self.root))
        cache = self.db.load_tracks(self.library_id) if self.db is not None else {}
        entries: Dict[str, Dict[str, Any]] = {}
        playlists: Dict[str, Path] = {}
        added = changed = 0
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for name in sorted(filenames):
                path = Path(dirpath) / name
                ext = path.suffix.lower()
                if ext in PLAYLIST_EXTS:
                    in_main = path.parent == self.root / PLAYLISTS_DIR
                    if path.stem not in playlists or in_main:
                        playlists[path.stem] = path
                elif ext in AUDIO_EXTS and not name.startswith("."):
                    try:
                        relpath = path.relative_to(self.root).as_posix()
                        cached = None if force else cache.get(relpath)
                        entry, reread = self._make_entry(path, cached)
                    except OSError:
                        logger.warning("Cannot read %s", path, exc_info=True)
                        continue
                    entries[relpath] = entry
                    if relpath not in cache:
                        added += 1
                    elif reread:
                        changed += 1
        removed = sum(1 for rel in cache if rel not in entries)
        with self._lock:
            self._entries, self._by_path, self._playlists = {}, {}, playlists
            for entry in entries.values():
                self._add_entry(entry)
            if self.db is not None:
                self.db.replace_tracks(self.library_id, entries)
                self.db.set_last_scan(self.library_id)
        logger.info("Scanned %s: %d tracks, %d playlists", self.root, len(entries), len(playlists))
        return {"added": added, "changed": changed, "removed": removed, "total": len(entries)}

    # ------------------------------------------------------------ đọc
    def file_path(self, track_id: int) -> Optional[str]:
        entry = self._entries.get(track_id)
        return str(self.root / entry["relpath"]) if entry else None

    def _track_dict(self, track_id: int, entry: Dict[str, Any]) -> Dict[str, Any]:
        t = entry["tags"]
        return {
            "id": track_id,
            "title": t["title"] or Path(entry["relpath"]).stem,
            "artist": t["artist"],
            "album": t["album"],
            "album_artist": t["album_artist"],
            "composer": t["composer"],
            "genre": t["genre"],
            "duration": int(round(t["duration_s"])),
            "rating": 0,
            "play_count": 0,
            "year": t["year"],
            "track_number": t["track_number"],
            "file_size": entry["size"],
            "file_path": str(self.root / entry["relpath"]),
        }

    def _sorted_ids(self) -> List[int]:
        return sorted(self._entries, key=lambda i: self._entries[i]["relpath"].lower())

    def tracks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._track_dict(i, self._entries[i]) for i in self._sorted_ids()]

    def get(self, track_id: int) -> Optional[Dict[str, Any]]:
        entry = self._entries.get(track_id)
        return self._track_dict(track_id, entry) if entry else None

    def file_type(self, track_id: int) -> str:
        entry = self._entries.get(track_id)
        return _file_type(entry["relpath"], entry["tags"].get("codec", "")) if entry else ""

    def record(self, track_id: int) -> Optional[Dict[str, Any]]:
        """Bản ghi chi tiết cho export (cùng dạng ipod_manager.track_record)."""
        entry = self._entries.get(track_id)
        if entry is None:
            return None
        t, base = entry["tags"], self._track_dict(track_id, entry)
        return {
            "id": track_id,
            "title": base["title"],
            "artist": t["artist"],
            "album": t["album"],
            "album_artist": t["album_artist"],
            "genre": t["genre"],
            "composer": t["composer"],
            "year": t["year"],
            "track_number": t["track_number"],
            "total_tracks": t["total_tracks"],
            "disc_number": t["disc_number"],
            "duration_s": int(t["duration_s"]),
            "bitrate_kbps": t["bitrate_kbps"],
            "sample_rate": t["sample_rate"],
            "file_type": self.file_type(track_id),
            "file_size": entry["size"],
            "rating": 0,
            "play_count": 0,
            "date_added": None,
            "ipod_path": "",
            "file_path": base["file_path"],
        }

    def records(self, track_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        with self._lock:
            ids = (
                self._sorted_ids()
                if track_ids is None
                else [i for i in track_ids if i in self._entries]
            )
            return [r for r in (self.record(i) for i in ids) if r]

    # ------------------------------------------------------------ playlist
    def _read_playlist(self, path: Path) -> List[Union[int, str]]:
        """Mục trong playlist: id bài nếu khớp thư viện, chuỗi gốc nếu không (giữ nguyên khi ghi)."""
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError:
            return []
        items: List[Union[int, str]] = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            ref = line.replace("\\", os.sep).replace("/", os.sep)
            target = ref if os.path.isabs(ref) else os.path.join(path.parent, ref)
            track_id = self._by_path.get(_norm(target))
            items.append(track_id if track_id is not None else line)
        return items

    def _write_playlist(self, path: Path, items: List[Union[int, str]]) -> None:
        lines = ["#EXTM3U"]
        for item in items:
            if isinstance(item, int):
                entry = self._entries.get(item)
                if entry is None:
                    continue
                t = entry["tags"]
                title = t["title"] or Path(entry["relpath"]).stem
                label = f"{t['artist']} - {title}" if t["artist"] else title
                lines.append(f"#EXTINF:{int(t['duration_s'])},{label}")
                rel = os.path.relpath(self.root / entry["relpath"], path.parent)
                lines.append(rel.replace(os.sep, "/"))
            else:
                lines.append(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def playlists(self) -> List[Dict[str, Any]]:
        with self._lock:
            result = [
                {
                    "id": 0,
                    "name": self.root.name or str(self.root),
                    "is_master": True,
                    "is_smart": False,
                    "track_ids": self._sorted_ids(),
                }
            ]
            for name in sorted(self._playlists, key=str.lower):
                path = self._playlists[name]
                ids = [i for i in self._read_playlist(path) if isinstance(i, int)]
                result.append(
                    {
                        "id": track_id_for(str(path)),
                        "name": name,
                        "is_master": False,
                        "is_smart": False,
                        "track_ids": ids,
                    }
                )
            return result

    def create_playlist(self, name: str) -> bool:
        clean = safe_name(name, "")
        if not clean:
            return False
        with self._lock:
            if clean in self._playlists:
                return True
            path = self.root / PLAYLISTS_DIR / f"{clean}.m3u8"
            self._write_playlist(path, [])
            self._playlists[clean] = path
            return True

    def delete_playlist(self, name: str) -> bool:
        with self._lock:
            path = self._playlists.pop(name, None)
            if path is None:
                return False
            try:
                path.unlink()
            except OSError:
                logger.error("Cannot delete playlist %s", path, exc_info=True)
                self._playlists[name] = path
                return False
            return True

    def add_to_playlist(self, name: str, track_id: int) -> bool:
        with self._lock:
            path = self._playlists.get(name)
            if path is None or track_id not in self._entries:
                return False
            items = self._read_playlist(path)
            if track_id not in items:
                items.append(track_id)
                self._write_playlist(path, items)
            return True

    def remove_from_playlist(self, name: str, track_id: int) -> bool:
        with self._lock:
            path = self._playlists.get(name)
            if path is None:
                return False
            items = self._read_playlist(path)
            if track_id not in items:
                return False
            self._write_playlist(path, [i for i in items if i != track_id])
            return True

    # ------------------------------------------------------------ ghi
    def import_file(
        self, src: str, playlist: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Copy file vào <Artist>/<Album>/ và thêm vào thư viện (và playlist nếu có). Trả id.

        Raises:
            ValueError: không phải file âm thanh hỗ trợ.
            OSError: không copy được.
        """
        source = Path(src)
        if source.suffix.lower() not in AUDIO_EXTS or not source.is_file():
            raise ValueError(f"Not a supported audio file: {source.name}")
        tags = read_tags(str(source))
        meta = {k: v for k, v in (metadata or {}).items() if v not in (None, "")}
        artist = (
            meta.get("album_artist") or meta.get("artist") or tags["album_artist"] or tags["artist"]
        )
        album = meta.get("album") or tags["album"]
        dest_dir = (
            self.root / safe_name(artist, "Unknown Artist") / safe_name(album, "Unknown Album")
        )
        with self._lock:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = _unique_path(dest_dir / source.name)
            shutil.copy2(source, dest)
            track_id = self._refresh(dest)
            tag_changes = {k: v for k, v in meta.items() if k in tag_editor.FIELDS}
            if tag_changes:
                self.update_tags(track_id, tag_changes)
            if playlist:
                if playlist not in self._playlists:
                    self.create_playlist(playlist)
                self.add_to_playlist(safe_name(playlist, playlist), track_id)
        return track_id

    def update_tags(self, track_id: int, metadata: Dict[str, Any]) -> bool:
        """Ghi tag vào file (các trường trong tag_editor.FIELDS; key khác bị bỏ qua)."""
        changes = {k: v for k, v in metadata.items() if k in tag_editor.FIELDS}
        with self._lock:
            path = self.file_path(track_id)
            if path is None:
                return False
            try:
                tag_editor.write_tags(path, changes)
            except Exception as e:
                logger.error(f"Cannot write tags to {path}: {e}")
                return False
            self._refresh(Path(path))
            return True

    def _album_ids(self, track_id: int) -> List[int]:
        """Các bài cùng album (cùng tên album + album artist/artist, không phân biệt hoa thường)."""
        t = self._entries[track_id]["tags"]
        album = (t.get("album") or "").casefold()
        if not album:
            return [track_id]
        owner = (t.get("album_artist") or t.get("artist") or "").casefold()
        return [
            i
            for i in self._sorted_ids()
            if (self._entries[i]["tags"].get("album") or "").casefold() == album
            and (
                self._entries[i]["tags"].get("album_artist")
                or self._entries[i]["tags"].get("artist")
                or ""
            ).casefold()
            == owner
        ]

    def set_cover(self, track_id: int, image: Optional[bytes], apply_album: bool = False) -> int:
        """Nhúng ảnh bìa (ảnh bất kỳ -> JPEG) vào bài, hoặc cả album. image=None = xoá ảnh.

        Returns: số file đã ghi (0 nếu không có bài).
        Raises: ValueError (ảnh không hợp lệ / định dạng không ghi được), OSError, MutagenError.
        """
        jpeg = tag_editor.normalize_cover(image) if image is not None else None
        with self._lock:
            if track_id not in self._entries:
                return 0
            ids = self._album_ids(track_id) if apply_album else [track_id]
            for i in ids:
                path = self.file_path(i)
                tag_editor.set_cover(path, jpeg)
                self._refresh(Path(path))
            return len(ids)

    def remove_cover(self, track_id: int, apply_album: bool = False) -> int:
        return self.set_cover(track_id, None, apply_album)

    def delete_track(self, track_id: int) -> bool:
        """Xoá file khỏi đĩa và khỏi mọi playlist."""
        with self._lock:
            path = self.file_path(track_id)
            if path is None:
                return False
            for pl_path in list(self._playlists.values()):
                items = self._read_playlist(pl_path)
                if track_id in items:
                    self._write_playlist(pl_path, [i for i in items if i != track_id])
            try:
                os.remove(path)
            except OSError as e:
                logger.error(f"Cannot delete {path}: {e}")
                return False
            entry = self._entries.pop(track_id, None)
            self._by_path.pop(_norm(path), None)
            if self.db is not None and entry is not None:
                self.db.delete_track(self.library_id, entry["relpath"])
            return True
