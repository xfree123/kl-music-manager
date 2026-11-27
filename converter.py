"""Convert âm thanh bằng ffmpeg: export sang định dạng khác và chuyển mã để stream.

ffmpeg được tìm theo thứ tự: đường dẫn trong cài đặt -> bản đóng kèm (env KLMM_FFMPEG,
do Electron đặt) -> PATH.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import tag_editor

logger = logging.getLogger(__name__)

CONVERT_TIMEOUT_S = 600
STREAM_CACHE_MAX_BYTES = 1024 * 1024 * 1024  # 1 GB
INVALID_FILENAME_CHARS = '/\\:*?"<>|'
SAMPLE_RATES = (0, 44100, 48000, 96000)  # 0 = giữ nguyên
FLAC_LEVELS = range(0, 9)


class ConversionError(Exception):
    """ffmpeg chạy lỗi hoặc không có ffmpeg."""


@dataclass(frozen=True)
class AudioFormat:
    id: str
    label: str
    ext: str  # "" = giữ đuôi gốc
    codec: Optional[str]  # None = không convert
    lossy: bool = False
    bitrates: Tuple[int, ...] = field(default_factory=tuple)
    default_bitrate: Optional[int] = None
    cover: bool = True  # định dạng chứa được ảnh bìa


FORMATS: Dict[str, AudioFormat] = {
    f.id: f
    for f in (
        AudioFormat("original", "Original (no conversion)", "", None),
        AudioFormat("mp3", "MP3", ".mp3", "libmp3lame", True, (128, 160, 192, 256, 320), 320),
        AudioFormat("aac", "AAC (.m4a)", ".m4a", "aac", True, (128, 160, 192, 256, 320), 256),
        AudioFormat("flac", "FLAC (lossless)", ".flac", "flac"),
        AudioFormat("alac", "ALAC / Apple Lossless (.m4a)", ".m4a", "alac"),
        AudioFormat("wav", "WAV (PCM 16-bit)", ".wav", "pcm_s16le", cover=False),
    )
}
ALL_BITRATES = sorted({b for f in FORMATS.values() for b in f.bitrates})


def list_formats() -> List[Dict[str, Any]]:
    """Danh sách định dạng cho UI."""
    return [
        {
            "id": f.id,
            "label": f.label,
            "ext": f.ext,
            "lossy": f.lossy,
            "bitrates": list(f.bitrates),
            "default_bitrate": f.default_bitrate,
        }
        for f in FORMATS.values()
    ]


def find_ffmpeg(configured: str = "") -> Optional[str]:
    """Đường dẫn ffmpeg dùng được, hoặc None."""
    if configured and Path(configured).is_file():
        return configured
    bundled = os.environ.get("KLMM_FFMPEG", "")
    if bundled and Path(bundled).is_file():
        return bundled
    return shutil.which("ffmpeg")


def output_filename(meta: Dict[str, Any], ext: str) -> str:
    """Tên file export dạng "Artist - Title.ext", bỏ ký tự không hợp lệ trên Windows/macOS."""
    name = f"{meta.get('artist') or 'Unknown Artist'} - {meta.get('title') or 'Unknown Title'}"
    for ch in INVALID_FILENAME_CHARS:
        name = name.replace(ch, "_")
    return name.strip().rstrip(".") + ext


def safe_component(text: Optional[str], fallback: str = "Unknown", max_len: int = 120) -> str:
    """Một thành phần đường dẫn (tên thư mục) an toàn: thay ký tự không hợp lệ, bỏ "."/".." và
    dấu chấm / khoảng trắng cuối (Windows), cắt dài; rỗng -> fallback."""
    name = str(text or "")
    for ch in INVALID_FILENAME_CHARS:
        name = name.replace(ch, "_")
    name = name.strip()[:max_len].rstrip(". ")
    return name or fallback


def build_command(
    ffmpeg: str,
    src: str,
    dest: str,
    fmt: str,
    options: Dict[str, Any],
    metadata: Dict[str, Any],
) -> List[str]:
    """Dựng lệnh ffmpeg (thuần, không chạy gì)."""
    f = FORMATS.get(fmt)
    if f is None or f.codec is None:
        raise ValueError(f"Unsupported conversion format: {fmt}")
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", src]
    cmd += ["-map", "0:a:0"]
    if f.cover:
        # Ảnh bìa nếu có ("?" = không lỗi khi file không có ảnh)
        cmd += ["-map", "0:v?", "-c:v", "copy", "-disposition:v", "attached_pic"]
    # OGG / Opus giữ tag ở metadata của luồng audio (không phải metadata chung) -> lấy từ đó
    ogg = Path(src).suffix.lower() in (".ogg", ".oga", ".opus")
    cmd += ["-map_metadata", "0:s:a:0" if ogg else "0"]
    for key, value in metadata.items():
        if value not in (None, ""):
            cmd += ["-metadata", f"{key}={value}"]
    cmd += ["-c:a", f.codec]
    if f.lossy:
        cmd += ["-b:a", f"{int(options.get('bitrate_kbps') or f.default_bitrate)}k"]
    if fmt == "flac":
        cmd += ["-compression_level", str(int(options.get("flac_level", 5)))]
    if fmt == "mp3":
        cmd += ["-id3v2_version", "3"]  # ID3v2.3: Windows Explorer / thiết bị cũ đọc được
    if options.get("sample_rate"):
        cmd += ["-ar", str(int(options["sample_rate"]))]
    if options.get("channels"):
        cmd += ["-ac", str(int(options["channels"]))]
    if options.get("sample_fmt"):
        cmd += ["-sample_fmt", str(options["sample_fmt"])]
    cmd.append(dest)
    return cmd


def convert(
    src: str,
    dest: str,
    fmt: str,
    options: Dict[str, Any],
    metadata: Dict[str, Any],
    ffmpeg: Optional[str],
) -> str:
    """Convert `src` -> `dest`. Ghi vào file tạm rồi đổi tên: lỗi thì không để lại file dở.

    Raises:
        ConversionError: không có ffmpeg, ffmpeg lỗi hoặc quá thời gian.
    """
    if not ffmpeg:
        raise ConversionError("ffmpeg not found. Set its path in Settings.")
    dest_path = Path(dest)
    # Tên tạm riêng cho mỗi lần gọi: 2 lần convert cùng đích không ghi đè file tạm của nhau
    tmp = dest_path.with_name(f".{dest_path.stem}.{uuid.uuid4().hex[:8]}.part{dest_path.suffix}")
    cmd = build_command(ffmpeg, src, str(tmp), fmt, options, metadata)
    logger.info("Converting %s -> %s (%s)", src, dest, fmt)
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=CONVERT_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as e:
        tmp.unlink(missing_ok=True)
        raise ConversionError(f"ffmpeg timed out after {CONVERT_TIMEOUT_S}s") from e
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise ConversionError(f"Cannot run ffmpeg: {e}") from e
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        err = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()[-5:]
        raise ConversionError("ffmpeg failed: " + " | ".join(err))
    os.replace(tmp, dest_path)
    return str(dest_path)


# ---------------------------------------------------------------- import vào iPod
IPOD_IMPORT_MODES = ("auto", "aac", "mp3", "alac", "off")
_IPOD_KEEP_EXTS = (".mp3", ".m4a", ".m4b", ".mp4", ".aac", ".aif", ".aiff", ".aifc")
_LOSSLESS_CODECS = ("FLAC", "PCM", "ALAC")
_IPOD_MAX_RATE = 48000
FORMAT_LABELS = {"alac": "ALAC", "aac": "AAC", "mp3": "MP3"}


def ipod_playable(path: str) -> bool:
    """iPod phát được file này không (MP3, AAC / ALAC, WAV PCM, AIFF). WAV chứa DTS: không."""
    suffix = Path(path).suffix.lower()
    if suffix in _IPOD_KEEP_EXTS:
        return True
    if suffix in (".wav", ".wave"):
        return tag_editor.wav_dts_info(path) is None
    return False


def ipod_import_target(path: str, mode: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """(định dạng, options) để chuyển file trước khi chép vào iPod; None = chép nguyên.

    mode "auto": nguồn lossless (FLAC…) -> ALAC 16-bit; nguồn lossy (Vorbis, Opus, DTS) -> AAC
    256 kbps. "aac" / "mp3" / "alac": luôn định dạng đó. "off": không chuyển (hành vi cũ).
    Luôn stereo; sample rate > 48 kHz -> 44.1 kHz (iPod không phát được).
    """
    if mode == "off" or ipod_playable(path):
        return None
    info = tag_editor.read_file(path)
    if mode in ("aac", "mp3", "alac"):
        fmt = mode
    else:
        fmt = "alac" if info["codec"] in _LOSSLESS_CODECS else "aac"
    options: Dict[str, Any] = {"channels": 2}
    options["sample_rate"] = 44100 if info["sample_rate"] > _IPOD_MAX_RATE else 0
    if fmt == "alac":
        options["sample_fmt"] = "s16p"
    else:
        options["bitrate_kbps"] = FORMATS[fmt].default_bitrate
    return fmt, options


def is_browser_unsupported(path: str, filetype_str: str = "") -> bool:
    """True nếu trình duyệt (Chromium/Firefox) không giải mã được file: ALAC, hoặc WAV chứa
    luồng DTS (header khai PCM -> trình duyệt phát ra nhiễu trắng).

    Đọc codec từ header bằng mutagen vì iTunesDB không đáng tin (pygpod ghi ALAC là "AAC").
    """
    if "lossless" in (filetype_str or "").lower():
        return True
    suffix = Path(path).suffix.lower()
    if suffix in (".wav", ".wave"):
        return tag_editor.wav_dts_info(path) is not None
    if suffix not in (".m4a", ".mp4", ".m4b"):
        return False
    try:
        from mutagen.mp4 import MP4

        return MP4(path).info.codec == "alac"
    except Exception:
        logger.debug("Cannot probe codec of %s", path, exc_info=True)
        return False


def transcode_for_stream(src: str, cache_dir: str, ffmpeg: Optional[str]) -> str:
    """Chuyển mã sang FLAC trong cache (dùng lại nếu đã có) để trình duyệt phát và tua được."""
    st = os.stat(src)
    key = hashlib.sha1(f"{os.path.abspath(src)}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{key}.flac"
    # Trình duyệt gửi nhiều request Range song song cho cùng bài: chỉ 1 luồng chuyển mã,
    # các luồng khác chờ rồi dùng lại file cache.
    with _stream_lock(str(out)):
        if out.exists():
            os.utime(out)  # đánh dấu mới dùng (cho prune_cache)
            return str(out)
        # Stereo: phát trong app luôn ra 2 kênh; tránh trình duyệt từ chối FLAC 6.1/7.1 (DTS)
        convert(src, str(out), "flac", {"flac_level": 0, "channels": 2}, {}, ffmpeg)
    prune_cache(str(cache), STREAM_CACHE_MAX_BYTES, keep=str(out))
    return str(out)


_stream_locks: Dict[str, threading.Lock] = {}
_stream_locks_guard = threading.Lock()


def _stream_lock(path: str) -> threading.Lock:
    with _stream_locks_guard:
        return _stream_locks.setdefault(path, threading.Lock())


def prune_cache(cache_dir: str, max_bytes: int, keep: str = "") -> None:
    """Xoá file cũ nhất (theo mtime) tới khi tổng dung lượng <= max_bytes."""
    files = sorted(
        (p for p in Path(cache_dir).iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime
    )
    total = sum(p.stat().st_size for p in files)
    for p in files:
        if total <= max_bytes:
            break
        if str(p) == keep:
            continue
        total -= p.stat().st_size
        try:
            p.unlink()
        except OSError:
            logger.warning("Cannot remove cached file %s", p)
