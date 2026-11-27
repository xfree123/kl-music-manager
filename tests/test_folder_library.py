"""Thư viện thư mục: quét, tag, id ổn định, cache, playlist .m3u8, import, sửa tag, xoá."""

import io
import os
import shutil
from pathlib import Path

import pytest
from mutagen import File as MutagenFile
from PIL import Image

import artwork
import folder_library
from conftest import LIB_MP3_TITLE, make_audio, make_music_folder, needs_ffmpeg

pytestmark = needs_ffmpeg


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    return make_music_folder(tmp_path_factory.mktemp("lib_template"))


@pytest.fixture
def root(template, tmp_path):
    dest = tmp_path / "Music"
    shutil.copytree(template, dest)
    return dest


@pytest.fixture
def lib(root, tmp_path):
    library = folder_library.FolderLibrary(str(root), cache_dir=str(tmp_path / "cache"))
    library.scan()
    return library


def by_title(lib, title):
    return next(t for t in lib.tracks() if t["title"] == title)


# ---------------------------------------------------------------- quét + tag
def test_scan_finds_audio_only(lib):
    titles = sorted(t["title"] for t in lib.tracks())
    assert titles == sorted([LIB_MP3_TITLE, "Bài FLAC", "untagged"])  # không tag -> tên file


def test_tags_parsed(lib):
    t = by_title(lib, LIB_MP3_TITLE)
    assert t["artist"] == "Hồng Nhung"
    assert t["album"] == "Nghe Mưa"
    assert t["album_artist"] == "Hồng Nhung"
    assert t["composer"] == "Trịnh Công Sơn"
    assert t["genre"] == "Nhạc Việt"
    assert t["year"] == 2001
    assert t["track_number"] == 1
    assert t["duration"] == 2
    assert t["file_size"] > 0
    assert Path(t["file_path"]).name == "01 Tình thôi xót xa.mp3"


def test_untagged_defaults(lib):
    t = by_title(lib, "untagged")
    assert t["artist"] == "" and t["album"] == "" and t["year"] == 0


def test_ids_are_stable_and_js_safe(lib, root, tmp_path):
    again = folder_library.FolderLibrary(str(root), cache_dir=str(tmp_path / "other-cache"))
    again.scan()
    assert {t["id"] for t in lib.tracks()} == {t["id"] for t in again.tracks()}
    assert all(0 < t["id"] < 2**53 for t in lib.tracks())


def test_records_for_export(lib):
    rec = next(r for r in lib.records() if r["title"] == LIB_MP3_TITLE)
    assert rec["file_type"] == "MPEG audio file"
    assert rec["bitrate_kbps"] > 0 and rec["sample_rate"] == 44100
    assert rec["duration_s"] == 2


# ---------------------------------------------------------------- cache
def test_cache_reused_when_files_unchanged(lib, root, tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("mutagen should not be called for cached files")

    monkeypatch.setattr(folder_library, "read_tags", boom)
    cached = folder_library.FolderLibrary(str(root), cache_dir=str(tmp_path / "cache"))
    cached.scan()
    assert len(cached.tracks()) == 3


def test_cache_rereads_changed_file(lib, root, tmp_path):
    flac = root / "Thanh Lam" / "Album B" / "song.flac"
    make_audio(flac, {"title": "Đã đổi", "artist": "Thanh Lam", "album": "Album B"}, seconds=3)
    os.utime(flac, (1, 1))  # chắc chắn mtime khác lần quét trước
    rescanned = folder_library.FolderLibrary(str(root), cache_dir=str(tmp_path / "cache"))
    rescanned.scan()
    assert "Đã đổi" in [t["title"] for t in rescanned.tracks()]


# ---------------------------------------------------------------- playlist
def test_playlists_master_and_m3u8(lib):
    pls = {p["name"]: p for p in lib.playlists()}
    master = next(p for p in lib.playlists() if p["is_master"])
    assert len(master["track_ids"]) == 3
    assert pls["Yêu thích"]["track_ids"] == [by_title(lib, LIB_MP3_TITLE)["id"]]
    assert pls["Yêu thích"]["is_master"] is False


def test_create_add_remove_delete_playlist(lib, root):
    flac_id = by_title(lib, "Bài FLAC")["id"]
    assert lib.create_playlist("Mới") is True
    m3u = root / "Playlists" / "Mới.m3u8"
    assert m3u.exists()

    assert lib.add_to_playlist("Mới", flac_id) is True
    assert "song.flac" in m3u.read_text(encoding="utf-8")
    assert next(p for p in lib.playlists() if p["name"] == "Mới")["track_ids"] == [flac_id]

    assert lib.remove_from_playlist("Mới", flac_id) is True
    assert next(p for p in lib.playlists() if p["name"] == "Mới")["track_ids"] == []

    assert lib.delete_playlist("Mới") is True
    assert not m3u.exists()


def test_playlist_names_are_sanitized(lib, root):
    assert lib.create_playlist("a/b:c") is True
    assert (root / "Playlists" / "a_b_c.m3u8").exists()
    assert lib.create_playlist("") is False


# ---------------------------------------------------------------- import / sửa / xoá
def test_import_copies_into_artist_album(lib, root, tmp_path):
    src = make_audio(
        tmp_path / "in" / "new.mp3", {"title": "Bài mới", "artist": "AC/DC", "album": "Back: In"}
    )

    track_id = lib.import_file(str(src), playlist="Yêu thích")

    dest = root / "AC_DC" / "Back_ In" / "new.mp3"
    assert dest.exists() and src.exists()  # copy, không move
    assert lib.get(track_id)["title"] == "Bài mới"
    assert track_id in next(p for p in lib.playlists() if p["name"] == "Yêu thích")["track_ids"]


def test_import_untagged_and_duplicate_name(lib, root, tmp_path):
    src = make_audio(tmp_path / "in" / "x.flac", {})
    first = lib.import_file(str(src))
    second = lib.import_file(str(src))
    assert first != second
    folder = root / "Unknown Artist" / "Unknown Album"
    assert sorted(p.name for p in folder.iterdir()) == ["x (2).flac", "x.flac"]


def test_import_rejects_non_audio(lib, tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        lib.import_file(str(txt))


def test_update_tags_writes_file(lib):
    t = by_title(lib, "Bài FLAC")
    assert (
        lib.update_tags(t["id"], {"title": "Tên mới", "year": "1999", "track_number": "4"}) is True
    )
    f = MutagenFile(t["file_path"], easy=True)
    assert f["title"] == ["Tên mới"] and f["date"] == ["1999"] and f["tracknumber"] == ["4"]
    assert lib.get(t["id"])["title"] == "Tên mới"


def test_delete_track_removes_file_and_playlist_entry(lib):
    t = by_title(lib, LIB_MP3_TITLE)
    assert lib.delete_track(t["id"]) is True
    assert not Path(t["file_path"]).exists()
    assert lib.get(t["id"]) is None
    assert next(p for p in lib.playlists() if p["name"] == "Yêu thích")["track_ids"] == []


def test_file_path_unknown_id(lib):
    assert lib.file_path(123) is None


# ---------------------------------------------------------------- SQLite (library_db)
def test_metadata_stored_in_sqlite(lib, tmp_path):
    cache = tmp_path / "cache"
    assert (cache / "library.db").exists()
    assert not list(cache.glob("*.json"))
    registered = lib.db.get_library(lib.library_id)
    assert registered["name"] == "Music" and registered["track_count"] == 3


def test_scan_reports_changes(lib, root, tmp_path):
    make_audio(root / "New" / "n.mp3", {"title": "Mới"})
    (root / "Loose" / "untagged.m4a").unlink()
    stats = lib.scan()
    assert stats == {"added": 1, "changed": 0, "removed": 1, "total": 3}


def test_force_scan_rereads_every_file(lib, monkeypatch):
    calls = []
    real = folder_library.read_tags
    monkeypatch.setattr(folder_library, "read_tags", lambda p: calls.append(p) or real(p))
    lib.scan()
    assert calls == []
    stats = lib.scan(force=True)
    assert len(calls) == 3 and stats["changed"] == 3


def test_set_cover_for_whole_album(lib, root, tmp_path):
    first = by_title(lib, LIB_MP3_TITLE)
    src = make_audio(
        tmp_path / "in" / "02.mp3",
        {
            "title": "Bài 2",
            "artist": "Hồng Nhung",
            "album": "Nghe Mưa",
            "album_artist": "Hồng Nhung",
        },
    )
    second = lib.import_file(str(src))
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "purple").save(buf, format="PNG")
    assert lib.set_cover(first["id"], buf.getvalue(), apply_album=True) == 2
    assert artwork.embedded_artwork(lib.file_path(second)) is not None
    assert lib.remove_cover(second) == 1
    assert artwork.embedded_artwork(lib.file_path(second)) is None
    assert artwork.embedded_artwork(lib.file_path(first["id"])) is not None
