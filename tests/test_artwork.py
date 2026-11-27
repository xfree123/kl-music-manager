"""Ảnh bìa: nhúng trong file, cover.jpg cùng thư mục, ArtworkDB của iPod, resize JPEG."""

import io
import shutil

import pytest
from PIL import Image

import artwork
from conftest import make_audio, make_cover, needs_ffmpeg

pytestmark = needs_ffmpeg


def is_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def test_embedded_mp3_flac_m4a(tmp_path):
    cover = make_cover(tmp_path / "c.png", "red")
    for name in ("a.mp3", "a.flac", "a.m4a"):
        f = make_audio(tmp_path / name, {"title": "x"}, cover=cover)
        data = artwork.embedded_artwork(str(f))
        assert data, name
        assert is_image(data).size == (64, 64)


def test_no_embedded(tmp_path):
    f = make_audio(tmp_path / "plain.flac", {"title": "x"})
    assert artwork.embedded_artwork(str(f)) is None
    assert artwork.embedded_artwork(str(tmp_path / "missing.mp3")) is None


@pytest.mark.parametrize("name", ["cover.jpg", "Folder.JPG", "front.png"])
def test_folder_artwork(tmp_path, name):
    f = make_audio(tmp_path / "song.flac", {})
    make_cover(tmp_path / name, "yellow")
    assert is_image(artwork.folder_artwork(str(f))).size == (64, 64)


def test_folder_artwork_none(tmp_path):
    f = make_audio(tmp_path / "song.flac", {})
    assert artwork.folder_artwork(str(f)) is None


def test_to_jpeg_resizes_large_image(tmp_path):
    big = make_cover(tmp_path / "big.png", "white", size=1500)
    out = artwork.to_jpeg(big.read_bytes(), max_size=600)
    img = is_image(out)
    assert img.format == "JPEG" and max(img.size) == 600


def test_to_jpeg_rejects_garbage():
    assert artwork.to_jpeg(b"not an image") is None


def test_ipod_artworkdb_roundtrip(tmp_path):
    """pygpod ghi ArtworkDB khi add bài có ảnh nhúng -> IPodArtwork đọc lại được theo dbid."""
    import pygpod
    from pygpod.device.mountpoint import init_ipod

    ipod = tmp_path / "ipod"
    ipod.mkdir()
    init_ipod(str(ipod), model="classic_6g", music_dirs=2)
    cover = make_cover(tmp_path / "c.png", "red", size=400)
    src = make_audio(tmp_path / "s.mp3", {"title": "x"}, cover=cover)
    db = pygpod.Database(str(ipod))
    track = db.add_track(str(src))
    db.save()

    art = artwork.IPodArtwork(str(ipod))
    data = art.get(track.dbid)
    assert data is not None
    img = is_image(data)
    assert min(img.size) >= 128  # chọn định dạng lớn nhất
    r, g, b = img.convert("RGB").getpixel((img.size[0] // 2, img.size[1] // 2))
    assert r > 180 and g < 80 and b < 80  # vẫn là màu đỏ sau RGB565
    assert art.get(12345) is None


def test_ipod_artwork_by_mhii_link(tmp_path):
    """iTunes mới gắn ảnh theo album: bài trỏ tới ảnh qua mhii_link (= image_id), không qua dbid."""
    import pygpod
    from pygpod.device.mountpoint import init_ipod

    ipod = tmp_path / "ipod"
    ipod.mkdir()
    init_ipod(str(ipod), model="classic_6g", music_dirs=2)
    src = make_audio(
        tmp_path / "s.mp3", {"title": "x"}, cover=make_cover(tmp_path / "c.png", "red", 300)
    )
    db = pygpod.Database(str(ipod))
    db.add_track(str(src))
    db.save()
    track = pygpod.Database(str(ipod)).tracks[0]
    assert track.mhii_link

    art = artwork.IPodArtwork(str(ipod))
    assert art.get(dbid=999, image_id=track.mhii_link) is not None
    assert art.get(dbid=999, image_id=0) is None


def test_ipod_artwork_without_db(tmp_path):
    assert artwork.IPodArtwork(str(tmp_path)).get(1) is None


def test_artwork_for_file_prefers_embedded_then_folder(tmp_path):
    cover = make_cover(tmp_path / "c.png", "red")
    emb = make_audio(tmp_path / "d1" / "e.mp3", {}, cover=cover)
    make_cover(tmp_path / "d1" / "cover.jpg", "yellow", size=32)
    plain = make_audio(tmp_path / "d2" / "p.flac", {})
    shutil.copy(tmp_path / "d1" / "cover.jpg", tmp_path / "d2" / "cover.jpg")

    assert is_image(artwork.artwork_for_file(str(emb))).size == (64, 64)  # ảnh nhúng thắng
    assert is_image(artwork.artwork_for_file(str(plain))).size == (32, 32)
    assert artwork.artwork_for_file(str(make_audio(tmp_path / "d3" / "n.flac", {}))) is None
