"""tag_editor: đọc thông số file + tag mở rộng, ghi tag, đặt/xoá ảnh bìa (MP3, FLAC, M4A)."""

import io
import subprocess

import pytest
from PIL import Image

import artwork
import tag_editor
from conftest import FFMPEG, make_audio, make_cover, needs_ffmpeg

pytestmark = needs_ffmpeg

EXTS = [".mp3", ".flac", ".m4a"]


def png_bytes(color="red", size=(40, 30)):
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, format="PNG")
    return out.getvalue()


@pytest.fixture(params=EXTS)
def audio(request, tmp_path):
    return make_audio(
        tmp_path / f"song{request.param}",
        {"title": "Gốc", "artist": "Ca sĩ", "album": "Album", "track": "3/12"},
    )


# ---------------------------------------------------------------- thông số file
@pytest.mark.parametrize(
    "ext,codec,lossless", [(".mp3", "MP3", False), (".flac", "FLAC", True), (".m4a", "ALAC", True)]
)
def test_stream_info(tmp_path, ext, codec, lossless):
    f = make_audio(tmp_path / f"a{ext}", {"title": "x"})
    info = tag_editor.read_file(str(f))
    assert info["codec"] == codec
    assert info["sample_rate"] == 44100
    assert info["channels"] == 1  # lavfi sine = mono
    assert info["bitrate_kbps"] > 0
    assert round(info["duration_s"]) == 2
    assert (info["bits_per_sample"] == 16) is lossless


def test_aac_codec_name(tmp_path):
    dest = tmp_path / "aac.m4a"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "sine=duration=1:sample_rate=44100", "-c:a", "aac", "-ac", "2", str(dest)],
        check=True,
    )  # fmt: skip
    info = tag_editor.read_file(str(dest))
    assert info["codec"] == "AAC" and info["channels"] == 2


def test_unreadable_file_returns_empty_info(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio")
    info = tag_editor.read_file(str(bad))
    assert info["title"] == "" and info["codec"] == "" and info["duration_s"] == 0


# ---------------------------------------------------------------- tag mở rộng
def test_read_existing_tags(audio):
    info = tag_editor.read_file(str(audio))
    assert info["title"] == "Gốc" and info["artist"] == "Ca sĩ"
    assert info["track_number"] == 3 and info["total_tracks"] == 12
    assert info["has_cover"] is False


def test_write_extended_fields_roundtrip(audio):
    changes = {
        "title": "Tên mới",
        "album_artist": "Nhiều ca sĩ",
        "composer": "Trịnh Công Sơn",
        "genre": "Nhạc Việt",
        "year": 1999,
        "track_number": 4,
        "total_tracks": 11,
        "disc_number": 2,
        "total_discs": 3,
        "bpm": 96,
        "comment": "Bản thu 1999",
        "lyrics": "Dòng 1\nDòng 2",
    }
    tag_editor.write_tags(str(audio), changes)
    info = tag_editor.read_file(str(audio), with_lyrics=True)
    for key, value in changes.items():
        assert info[key] == value, key
    assert info["artist"] == "Ca sĩ"  # trường không gửi thì giữ nguyên


def test_empty_value_removes_field(audio):
    tag_editor.write_tags(str(audio), {"comment": "x", "bpm": 100})
    tag_editor.write_tags(str(audio), {"comment": "", "bpm": 0, "album": None})
    info = tag_editor.read_file(str(audio))
    assert info["comment"] == "" and info["bpm"] == 0 and info["album"] == ""


def test_track_number_keeps_total(audio):
    tag_editor.write_tags(str(audio), {"track_number": 5})
    info = tag_editor.read_file(str(audio))
    assert info["track_number"] == 5 and info["total_tracks"] == 12


def test_lyrics_only_read_on_request(audio):
    tag_editor.write_tags(str(audio), {"lyrics": "La la"})
    assert "lyrics" not in tag_editor.read_file(str(audio))
    assert tag_editor.read_file(str(audio), with_lyrics=True)["lyrics"] == "La la"


def test_write_untagged_file(tmp_path):
    f = make_audio(tmp_path / "bare.m4a", {})
    tag_editor.write_tags(str(f), {"title": "Có tên", "bpm": 120})
    info = tag_editor.read_file(str(f))
    assert info["title"] == "Có tên" and info["bpm"] == 120


def test_write_rejects_unknown_field(audio):
    with pytest.raises(ValueError):
        tag_editor.write_tags(str(audio), {"rating": 5})


# ---------------------------------------------------------------- ảnh bìa
def test_set_and_remove_cover(audio):
    jpeg = tag_editor.normalize_cover(png_bytes())
    assert jpeg[:2] == b"\xff\xd8"  # PNG RGBA -> JPEG
    tag_editor.set_cover(str(audio), jpeg)
    assert tag_editor.read_file(str(audio))["has_cover"] is True
    assert artwork.embedded_artwork(str(audio)) == jpeg
    tag_editor.write_tags(str(audio), {"title": "Sau ảnh"})  # sửa tag không làm mất ảnh
    assert artwork.embedded_artwork(str(audio)) == jpeg

    tag_editor.remove_cover(str(audio))
    assert artwork.embedded_artwork(str(audio)) is None
    assert tag_editor.read_file(str(audio))["has_cover"] is False


def test_set_cover_replaces_existing(tmp_path):
    cover = make_cover(tmp_path / "c.jpg", "green")
    f = make_audio(tmp_path / "with.mp3", {"title": "x"}, cover=cover)
    new = tag_editor.normalize_cover(png_bytes("blue"))
    tag_editor.set_cover(str(f), new)
    assert artwork.embedded_artwork(str(f)) == new


def test_normalize_cover_limits_size_and_rejects_non_image():
    big = tag_editor.normalize_cover(png_bytes(size=(3000, 1500)))
    assert max(Image.open(io.BytesIO(big)).size) == tag_editor.COVER_MAX_SIZE
    with pytest.raises(ValueError):
        tag_editor.normalize_cover(b"not an image")


@pytest.mark.parametrize("ext,codec", [(".ogg", "Vorbis"), (".opus", "Opus")])
def test_ogg_tags_and_cover(tmp_path, ext, codec):
    f = make_audio(tmp_path / f"o{ext}", {"title": "Ogg"})
    assert tag_editor.read_file(str(f))["codec"] == codec
    tag_editor.write_tags(str(f), {"album_artist": "AA", "track_number": 2, "total_tracks": 9})
    info = tag_editor.read_file(str(f))
    assert info["album_artist"] == "AA" and (info["track_number"], info["total_tracks"]) == (2, 9)
    assert info["bits_per_sample"] == 0  # lossy
    jpeg = tag_editor.normalize_cover(png_bytes())
    tag_editor.set_cover(str(f), jpeg)
    assert tag_editor.read_file(str(f))["has_cover"] is True
    assert artwork.embedded_artwork(str(f)) == jpeg  # METADATA_BLOCK_PICTURE
    tag_editor.remove_cover(str(f))
    assert artwork.embedded_artwork(str(f)) is None
