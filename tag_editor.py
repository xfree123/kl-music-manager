"""Đọc / ghi tag file nhạc (mutagen, không dùng chế độ "easy" để có comment, lyrics, BPM, ảnh bìa).

Hỗ trợ ghi: ID3 (MP3, WAV, AIFF), MP4 (M4A/M4B: AAC, ALAC), Vorbis comment (FLAC, OGG Vorbis/Opus).
`read_file` trả cả thông số luồng âm thanh (codec, bitrate, sample rate, bit depth, kênh).
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional, Tuple

import artwork

logger = logging.getLogger(__name__)

TEXT_FIELDS = (
    "title",
    "artist",
    "album",
    "album_artist",
    "genre",
    "composer",
    "comment",
    "lyrics",
)
INT_FIELDS = ("year", "track_number", "total_tracks", "disc_number", "total_discs", "bpm")
FIELDS = TEXT_FIELDS + INT_FIELDS
COVER_MAX_SIZE = 1200
_LOSSY = {"MP3", "AAC", "Vorbis", "Opus", "DTS"}

# Trường văn bản đơn giản -> khoá theo định dạng
_ID3_TEXT = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "album_artist": "TPE2",
    "genre": "TCON",
    "composer": "TCOM",
    "year": "TDRC",
    "bpm": "TBPM",
}
_MP4_TEXT = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "album_artist": "aART",
    "genre": "\xa9gen",
    "composer": "\xa9wrt",
    "year": "\xa9day",
    "comment": "\xa9cmt",
    "lyrics": "\xa9lyr",
}
_VORBIS_TEXT = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "album_artist": "albumartist",
    "genre": "genre",
    "composer": "composer",
    "year": "date",
    "bpm": "bpm",
    "comment": "comment",
    "lyrics": "lyrics",
}
_VORBIS_PAIRS = {
    "track": ("tracknumber", ("tracktotal", "totaltracks")),
    "disc": ("discnumber", ("disctotal", "totaldiscs")),
}


def _leading_int(text: Any) -> int:
    digits = ""
    for ch in str(text or "").strip():
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else 0


def _split_pair(text: Any) -> Tuple[int, int]:
    """'3/12' -> (3, 12); '3' -> (3, 0)."""
    s = str(text or "")
    if "/" in s:
        a, b = s.split("/", 1)
        return _leading_int(a), _leading_int(b)
    return _leading_int(s), 0


def _kind(audio: Any) -> str:
    name = type(audio).__name__
    if name in ("MP3", "EasyMP3", "WAVE", "AIFF", "TrueAudio"):
        return "id3"
    if name in ("MP4", "EasyMP4"):
        return "mp4"
    if name in ("FLAC", "OggVorbis", "OggOpus", "OggFLAC", "OggSpeex"):
        return "vorbis"
    return ""


def _codec(audio: Any) -> str:
    name = type(audio).__name__
    info = getattr(audio, "info", None)
    if name in ("MP4", "EasyMP4"):
        codec = str(getattr(info, "codec", "") or "").lower()
        if codec == "alac":
            return "ALAC"
        if codec.startswith("mp4a"):
            return "AAC"
        return codec.upper()
    return {
        "MP3": "MP3",
        "EasyMP3": "MP3",
        "FLAC": "FLAC",
        "OggFLAC": "FLAC",
        "OggVorbis": "Vorbis",
        "OggOpus": "Opus",
        "WAVE": "PCM",
        "AIFF": "PCM",
        "AAC": "AAC",
    }.get(name, name)


# ---------------------------------------------------------------- DTS trong WAV
# DTS-CD / DTS-WAV: header khai PCM 16 bit nhưng dữ liệu là luồng DTS. Trình duyệt phát như PCM
# -> nhiễu trắng. Nhận diện bằng sync word ở đầu chunk data (sau đoạn im lặng nếu có).
_DTS_SYNCS = {
    b"\x7f\xfe\x80\x01": (16, ">"),
    b"\xfe\x7f\x01\x80": (16, "<"),
    b"\x1f\xff\xe8\x00": (14, ">"),
    b"\xff\x1f\x00\xe8": (14, "<"),
}
# Số kênh theo AMODE (0–15); AMODE lớn hơn = do người dùng định nghĩa
_DTS_AMODE_CHANNELS = (1, 2, 2, 2, 2, 3, 3, 4, 4, 5, 6, 6, 6, 7, 8, 8)
_DTS_PROBE_BYTES = 64 * 1024


def _wav_data_offset(f: Any) -> Optional[int]:
    """Vị trí đầu chunk data nếu là WAV PCM (format 1 hoặc EXTENSIBLE), không thì None."""
    head = f.read(12)
    if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
        return None
    pcm = False
    while True:
        chunk = f.read(8)
        if len(chunk) < 8:
            return None
        cid, size = chunk[:4], int.from_bytes(chunk[4:], "little")
        if cid == b"data":
            return f.tell() if pcm else None
        if cid == b"fmt ":
            body = f.read(size)
            pcm = len(body) >= 2 and int.from_bytes(body[:2], "little") in (1, 0xFFFE)
            size -= len(body)
        f.seek(size + (size & 1), 1)


def _dts_bits(raw: bytes, width: int, order: str) -> str:
    """Bỏ đóng gói word 14/16 bit -> chuỗi bit của luồng DTS."""
    count = len(raw) // 2
    words = [
        int.from_bytes(raw[i * 2 : i * 2 + 2], "big" if order == ">" else "little")
        for i in range(count)
    ]
    mask = (1 << width) - 1
    return "".join(format(w & mask, f"0{width}b") for w in words)


def wav_dts_info(path: str) -> Optional[Dict[str, int]]:
    """{"channels": n} nếu file WAV thực chất chứa luồng DTS, không thì None."""
    try:
        with open(path, "rb") as f:
            offset = _wav_data_offset(f)
            if offset is None:
                return None
            data = f.read(_DTS_PROBE_BYTES)
    except OSError:
        return None
    start = len(data) - len(data.lstrip(b"\x00"))
    start -= start % 2  # sync luôn nằm ở đầu word 16 bit
    found = _DTS_SYNCS.get(data[start : start + 4])
    if found is None:
        return None
    width, order = found
    bits = _dts_bits(data[start : start + 16], width, order)
    if bits[:32] != "01111111111111101000000000000001" or len(bits) < 87:
        return None
    amode = int(bits[60:66], 2)
    channels = _DTS_AMODE_CHANNELS[amode] if amode < len(_DTS_AMODE_CHANNELS) else 0
    if channels:
        channels += 1 if int(bits[85:87], 2) in (1, 2) else 0  # LFE
        channels += 1 if bits[83] == "1" and int(bits[80:83], 2) == 0 else 0  # XCh (6.1)
    return {"channels": channels}


def _open(path: str) -> Any:
    from mutagen import File as MutagenFile

    return MutagenFile(path)


def _empty_info(with_lyrics: bool) -> Dict[str, Any]:
    info: Dict[str, Any] = {f: "" for f in TEXT_FIELDS}
    info.update({f: 0 for f in INT_FIELDS})
    info.update(
        {
            "duration_s": 0.0,
            "bitrate_kbps": 0,
            "sample_rate": 0,
            "channels": 0,
            "bits_per_sample": 0,
            "codec": "",
            "has_cover": False,
        }
    )
    if not with_lyrics:
        del info["lyrics"]
    return info


# ---------------------------------------------------------------- đọc
def _read_id3(tags: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field, frame_id in _ID3_TEXT.items():
        frame = tags.get(frame_id)
        if frame is None:
            continue
        if frame_id == "TCON" and getattr(frame, "genres", None):
            out[field] = frame.genres[0]
        elif frame.text:
            out[field] = str(frame.text[0])
    for prefix, field in (("COMM", "comment"), ("USLT", "lyrics")):
        frames = [f for f in tags.getall(prefix) if getattr(f, "desc", "") == ""]
        if frames:
            text = frames[0].text
            out[field] = text if isinstance(text, str) else (str(text[0]) if text else "")
    for frame_id, (num, total) in (("TRCK", ("track_number", "total_tracks")),
                                   ("TPOS", ("disc_number", "total_discs"))):  # fmt: skip
        frame = tags.get(frame_id)
        if frame is not None and frame.text:
            out[num], out[total] = _split_pair(frame.text[0])
    out["has_cover"] = bool(tags.getall("APIC"))
    return out


def _read_mp4(tags: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field, key in _MP4_TEXT.items():
        values = tags.get(key)
        if values:
            out[field] = str(values[0])
    for key, (num, total) in (("trkn", ("track_number", "total_tracks")),
                              ("disk", ("disc_number", "total_discs"))):  # fmt: skip
        values = tags.get(key)
        if values:
            out[num], out[total] = int(values[0][0] or 0), int(values[0][1] or 0)
    tmpo = tags.get("tmpo")
    if tmpo:
        out["bpm"] = int(tmpo[0])
    out["has_cover"] = bool(tags.get("covr"))
    return out


def _vorbis_first(tags: Any, *keys: str) -> str:
    for key in keys:
        values = tags.get(key)
        if values:
            return str(values[0])
    return ""


def _read_vorbis(audio: Any, tags: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field, key in _VORBIS_TEXT.items():
        extra = {"comment": ("description",), "lyrics": ("unsyncedlyrics",)}.get(field, ())
        value = _vorbis_first(tags, key, *extra)
        if value:
            out[field] = value
    for pair, (num, totals) in _VORBIS_PAIRS.items():
        n, t = _split_pair(_vorbis_first(tags, num))
        total = _leading_int(_vorbis_first(tags, *totals)) or t
        out[f"{pair}_number"] = n
        out[f"total_{pair}s"] = total
    pictures = getattr(audio, "pictures", None)
    out["has_cover"] = bool(pictures) or bool(tags.get("metadata_block_picture"))
    return out


def read_file(path: str, with_lyrics: bool = False) -> Dict[str, Any]:
    """Tag (mọi trường trong FIELDS) + thông số luồng + has_cover. Lỗi đọc -> giá trị rỗng."""
    info = _empty_info(with_lyrics=True)
    try:
        audio = _open(path)
    except Exception:
        logger.debug("Cannot read %s", path, exc_info=True)
        audio = None
    if audio is not None:
        tags, kind = audio.tags, _kind(audio)
        parsed: Dict[str, Any] = {}
        if tags is not None:
            try:
                if kind == "id3":
                    parsed = _read_id3(tags)
                elif kind == "mp4":
                    parsed = _read_mp4(tags)
                elif kind == "vorbis":
                    parsed = _read_vorbis(audio, tags)
            except Exception:
                logger.warning("Cannot parse tags of %s", path, exc_info=True)
        for field, value in parsed.items():
            if field in INT_FIELDS:
                info[field] = _leading_int(value)
            elif field == "has_cover":
                info[field] = bool(value)
            else:
                info[field] = str(value).strip() if field != "lyrics" else str(value)
        stream = getattr(audio, "info", None)
        codec = _codec(audio)
        dts = wav_dts_info(path) if type(audio).__name__ == "WAVE" else None
        if dts is not None:
            codec = "DTS"
        info["codec"] = codec
        if stream is not None:
            info["duration_s"] = float(getattr(stream, "length", 0) or 0)
            info["bitrate_kbps"] = int((getattr(stream, "bitrate", 0) or 0) / 1000)
            info["sample_rate"] = int(getattr(stream, "sample_rate", 0) or 0)
            info["channels"] = int(getattr(stream, "channels", 0) or 0)
            bits = getattr(stream, "bits_per_sample", 0) or getattr(stream, "sample_size", 0)
            info["bits_per_sample"] = 0 if codec in _LOSSY else int(bits or 0)
        if dts is not None and dts["channels"]:
            info["channels"] = dts["channels"]
    if not with_lyrics:
        del info["lyrics"]
    return info


# ---------------------------------------------------------------- ghi
def _clean(field: str, value: Any) -> Any:
    """Chuẩn hoá giá trị: text -> str đã strip ('' = xoá); số -> int (0 = xoá)."""
    if field not in FIELDS:
        raise ValueError(f"Unknown tag field: {field}")
    if field in INT_FIELDS:
        if value in (None, ""):
            return 0
        try:
            number = int(str(value).strip())
        except ValueError:
            raise ValueError(f"Invalid number for {field}: {value!r}") from None
        if number < 0:
            raise ValueError(f"Invalid number for {field}: {value!r}")
        return number
    text = "" if value is None else str(value)
    return text if field == "lyrics" else text.strip()


def _pair_text(n: int, total: int) -> str:
    if not n and not total:
        return ""
    return f"{n}/{total}" if total else str(n)


def _write_id3(tags: Any, changes: Dict[str, Any], merged: Dict[str, Any]) -> None:
    from mutagen import id3

    for field, frame_id in _ID3_TEXT.items():
        if field not in changes:
            continue
        tags.delall(frame_id)
        value = changes[field]
        if value not in ("", 0):
            tags.add(getattr(id3, frame_id)(encoding=3, text=[str(value)]))
    for prefix, field in (("COMM", "comment"), ("USLT", "lyrics")):
        if field not in changes:
            continue
        for key in [k for k in tags.keys() if k.startswith(prefix + ":")]:
            if getattr(tags[key], "desc", "") == "":
                del tags[key]
        if changes[field]:
            frame = getattr(id3, prefix)(encoding=3, lang="eng", desc="", text=changes[field])
            tags.add(frame)
    for frame_id, num, total in (("TRCK", "track_number", "total_tracks"),
                                 ("TPOS", "disc_number", "total_discs")):  # fmt: skip
        if num in changes or total in changes:
            tags.delall(frame_id)
            text = _pair_text(merged[num], merged[total])
            if text:
                tags.add(getattr(id3, frame_id)(encoding=3, text=[text]))


def _write_mp4(tags: Any, changes: Dict[str, Any], merged: Dict[str, Any]) -> None:
    for field, key in _MP4_TEXT.items():
        if field not in changes:
            continue
        value = changes[field]
        if value not in ("", 0):
            tags[key] = [str(value)]
        elif key in tags:
            del tags[key]
    for key, num, total in (("trkn", "track_number", "total_tracks"),
                            ("disk", "disc_number", "total_discs")):  # fmt: skip
        if num in changes or total in changes:
            if merged[num] or merged[total]:
                tags[key] = [(merged[num], merged[total])]
            elif key in tags:
                del tags[key]
    if "bpm" in changes:
        if changes["bpm"]:
            tags["tmpo"] = [changes["bpm"]]
        elif "tmpo" in tags:
            del tags["tmpo"]


def _vorbis_set(tags: Any, key: str, value: Any) -> None:
    if value not in ("", 0, None):
        tags[key] = [str(value)]
    elif key in tags:
        del tags[key]


def _write_vorbis(tags: Any, changes: Dict[str, Any], merged: Dict[str, Any]) -> None:
    for field, key in _VORBIS_TEXT.items():
        if field not in changes:
            continue
        for alias in {"comment": ("description",), "lyrics": ("unsyncedlyrics",)}.get(field, ()):
            if alias in tags:
                del tags[alias]
        _vorbis_set(tags, key, changes[field])
    for pair, (num_key, totals) in _VORBIS_PAIRS.items():
        num, total = f"{pair}_number", f"total_{pair}s"
        if num in changes or total in changes:
            _vorbis_set(tags, num_key, merged[num])
            for alias in totals[1:]:
                if alias in tags:
                    del tags[alias]
            _vorbis_set(tags, totals[0], merged[total])


def _load_for_write(path: str) -> Tuple[Any, str]:
    audio = _open(path)
    kind = _kind(audio) if audio is not None else ""
    if not kind:
        raise ValueError(f"Editing tags is not supported for this file type: {path}")
    if audio.tags is None:
        audio.add_tags()
    return audio, kind


def _save(audio: Any, kind: str) -> None:
    if kind == "id3":
        audio.save(v2_version=3)  # ID3v2.3: tương thích iPod / Windows Explorer cũ
    else:
        audio.save()


def write_tags(path: str, changes: Dict[str, Any]) -> None:
    """Ghi các trường trong `changes` (giá trị rỗng / 0 / None = xoá trường). Trường khác giữ nguyên.

    Raises:
        ValueError: trường lạ, số không hợp lệ, hoặc định dạng không ghi tag được.
        mutagen.MutagenError / OSError: lỗi đọc ghi file.
    """
    clean = {field: _clean(field, value) for field, value in changes.items()}
    if not clean:
        return
    current = read_file(path, with_lyrics=True)
    merged = {**current, **clean}
    audio, kind = _load_for_write(path)
    if kind == "id3":
        _write_id3(audio.tags, clean, merged)
    elif kind == "mp4":
        _write_mp4(audio.tags, clean, merged)
    else:
        _write_vorbis(audio.tags, clean, merged)
    _save(audio, kind)


# ---------------------------------------------------------------- ảnh bìa
def normalize_cover(data: bytes) -> bytes:
    """Ảnh bất kỳ (JPEG/PNG/…) -> JPEG cạnh dài <= COVER_MAX_SIZE. Raises ValueError nếu không phải ảnh."""
    jpeg = artwork.to_jpeg(data, max_size=COVER_MAX_SIZE)
    if jpeg is None:
        raise ValueError("Not a valid image")
    return jpeg


def _flac_picture(jpeg: bytes) -> Any:
    from mutagen.flac import Picture

    pic = Picture()
    pic.type, pic.mime, pic.desc, pic.data = 3, "image/jpeg", "Cover", jpeg
    return pic


def set_cover(path: str, jpeg: Optional[bytes]) -> None:
    """Đặt ảnh bìa trước (JPEG đã chuẩn hoá); None = xoá mọi ảnh nhúng.

    Raises: như write_tags.
    """
    audio, kind = _load_for_write(path)
    tags = audio.tags
    if kind == "id3":
        from mutagen.id3 import APIC

        tags.delall("APIC")
        if jpeg:
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=jpeg))
    elif kind == "mp4":
        from mutagen.mp4 import MP4Cover

        if jpeg:
            tags["covr"] = [MP4Cover(jpeg, imageformat=MP4Cover.FORMAT_JPEG)]
        elif "covr" in tags:
            del tags["covr"]
    elif hasattr(audio, "clear_pictures"):  # FLAC
        audio.clear_pictures()
        if jpeg:
            audio.add_picture(_flac_picture(jpeg))
    else:  # Ogg: METADATA_BLOCK_PICTURE (base64)
        if "metadata_block_picture" in tags:
            del tags["metadata_block_picture"]
        if jpeg:
            raw = _flac_picture(jpeg).write()
            tags["metadata_block_picture"] = [base64.b64encode(raw).decode("ascii")]
    _save(audio, kind)


def remove_cover(path: str) -> None:
    set_cover(path, None)
