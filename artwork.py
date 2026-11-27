"""Ảnh bìa: nhúng trong file -> ảnh cùng thư mục -> ArtworkDB của iPod; trả JPEG đã thu nhỏ."""

from __future__ import annotations

import io
import logging
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

FOLDER_IMAGE_NAMES = ("cover", "folder", "front", "album", "albumart")
FOLDER_IMAGE_EXTS = (".jpg", ".jpeg", ".png")
DEFAULT_MAX_SIZE = 600


def embedded_artwork(path: str) -> Optional[bytes]:
    """Ảnh nhúng trong file (ID3 APIC, MP4 covr, FLAC/Vorbis picture), None nếu không có."""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path)
    except Exception:
        logger.debug("Cannot read tags of %s", path, exc_info=True)
        return None
    if audio is None:
        return None
    pictures = getattr(audio, "pictures", None)  # FLAC
    if pictures:
        front = [p for p in pictures if getattr(p, "type", None) == 3]
        return bytes((front or pictures)[0].data)
    tags = audio.tags
    if tags is None:
        return None
    if hasattr(tags, "getall"):  # ID3
        apics = tags.getall("APIC")
        if apics:
            front = [a for a in apics if getattr(a, "type", None) == 3]
            return bytes((front or apics)[0].data)
        return None
    covr = tags.get("covr") if hasattr(tags, "get") else None  # MP4
    if covr:
        return bytes(covr[0])
    blocks = tags.get("metadata_block_picture") if hasattr(tags, "get") else None  # Ogg
    if blocks:
        try:
            import base64

            from mutagen.flac import Picture

            pics = [Picture(base64.b64decode(b)) for b in blocks]
        except Exception:
            logger.debug("Bad METADATA_BLOCK_PICTURE in %s", path, exc_info=True)
            return None
        front = [p for p in pics if p.type == 3]
        return bytes((front or pics)[0].data)
    return None


def folder_artwork(path: str) -> Optional[bytes]:
    """cover/folder/front.(jpg|png) trong thư mục chứa file (không phân biệt hoa thường)."""
    directory = Path(path).parent
    try:
        candidates = {p.name.lower(): p for p in directory.iterdir() if p.is_file()}
    except OSError:
        return None
    for name in FOLDER_IMAGE_NAMES:
        for ext in FOLDER_IMAGE_EXTS:
            p = candidates.get(name + ext)
            if p is not None:
                try:
                    return p.read_bytes()
                except OSError:
                    logger.debug("Cannot read %s", p, exc_info=True)
    return None


def artwork_for_file(path: str) -> Optional[bytes]:
    return embedded_artwork(path) or folder_artwork(path)


def to_jpeg(data: bytes, max_size: int = DEFAULT_MAX_SIZE) -> Optional[bytes]:
    """Chuẩn hoá ảnh bất kỳ thành JPEG cạnh dài <= max_size. None nếu không phải ảnh."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        logger.debug("Invalid artwork image data", exc_info=True)
        return None
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((max_size, max_size))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue()


class IPodArtwork:
    """Đọc thumbnail trong iPod_Control/Artwork/ArtworkDB theo dbid của bài (chỉ đọc)."""

    def __init__(self, mountpoint: str) -> None:
        self.artwork_dir = os.path.join(mountpoint, "iPod_Control", "Artwork")
        self._thumbs: Dict[int, Dict[str, int]] = {}  # song_id (dbid bài) -> thumbnail
        self._by_image: Dict[int, Dict[str, int]] = {}  # image_id (track.mhii_link) -> thumbnail
        self._load()

    def _load(self) -> None:
        db_path = os.path.join(self.artwork_dir, "ArtworkDB")
        if not os.path.isfile(db_path):
            return
        try:
            from pygpod.db.artwork_parser import parse_artworkdb

            with open(db_path, "rb") as f:
                root = parse_artworkdb(f.read())
        except Exception:
            logger.warning("Cannot parse %s", db_path, exc_info=True)
            return
        for mhsd in root.children:
            if mhsd.fields.get("mhsd_type") != 1 or not mhsd.children:
                continue
            for mhii in mhsd.children[0].children:
                best = None
                for mhod in mhii.children:  # mhod type 2 bọc mhni (thumbnail)
                    for mhni in mhod.children:
                        f = mhni.fields
                        if not f.get("format_id") or not f.get("image_size"):
                            continue
                        if best is None or f.get("image_width", 0) > best.get("image_width", 0):
                            best = f
                if best is not None:
                    self._thumbs[mhii.fields["song_id"]] = best
                    self._by_image[mhii.fields.get("image_id", 0)] = best

    def get(self, dbid: int, image_id: int = 0) -> Optional[bytes]:
        """PNG của thumbnail lớn nhất cho bài (tra theo dbid, rồi theo mhii_link), None nếu không có."""
        f = self._thumbs.get(dbid) or (self._by_image.get(image_id) if image_id else None)
        if f is None:
            return None
        try:
            from pygpod.model.artwork import ArtworkThumbnail

            for ithmb_index in (1, 2, 3):
                thumb = ArtworkThumbnail()
                thumb.format_id = f["format_id"]
                thumb.width = f.get("image_width", 0)
                thumb.height = f.get("image_height", 0)
                thumb.image_offset = f.get("ithumb_offset", 0)
                thumb.image_size = f["image_size"]
                thumb.ithmb_file = ithmb_index
                art = thumb.to_artwork(self.artwork_dir)
                img = art.to_pil_image() if art else None
                if img is not None:
                    out = io.BytesIO()
                    img.save(out, format="PNG")
                    return out.getvalue()
        except Exception:
            logger.debug("Cannot decode iPod artwork for dbid %s", dbid, exc_info=True)
        return None


class ArtworkCache:
    """LRU nhỏ trong bộ nhớ: key -> JPEG (None = đã biết là không có ảnh)."""

    def __init__(self, capacity: int = 300) -> None:
        self.capacity = capacity
        self._data: "OrderedDict[str, Optional[bytes]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> "tuple[bool, Optional[bytes]]":
        with self._lock:
            if key not in self._data:
                return False, None
            self._data.move_to_end(key)
            return True, self._data[key]

    def put(self, key: str, value: Optional[bytes]) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.capacity:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
