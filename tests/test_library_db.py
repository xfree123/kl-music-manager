"""library_db: SQLite lưu danh sách thư viện + metadata bài (thay cache JSON)."""

import sqlite3

import pytest

import library_db


def entry(title, size=100, mtime=1, **extra):
    tags = {
        "title": title,
        "artist": "Ca sĩ",
        "album": "Album",
        "album_artist": "",
        "genre": "Nhạc Việt",
        "composer": "",
        "year": 2001,
        "track_number": 1,
        "total_tracks": 10,
        "disc_number": 0,
        "duration_s": 2.5,
        "bitrate_kbps": 128,
        "sample_rate": 44100,
        "channels": 2,
        "bits_per_sample": 0,
        "codec": "MP3",
        **extra,
    }
    return {"size": size, "mtime_ns": mtime, "tags": tags}


@pytest.fixture
def db(tmp_path):
    d = library_db.LibraryDB(tmp_path / "library.db")
    yield d
    d.close()


def test_schema_version_and_indexes(db, tmp_path):
    assert db.schema_version() == library_db.SCHEMA_VERSION == 1
    con = sqlite3.connect(tmp_path / "library.db")
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    con.close()
    assert {"idx_tracks_artist", "idx_tracks_album", "idx_tracks_genre", "idx_tracks_year"} <= names


def test_add_rename_remove_library(db, tmp_path):
    lib = db.add_library("Nhạc Việt", str(tmp_path / "Music"))
    assert lib["id"] > 0 and lib["name"] == "Nhạc Việt" and lib["track_count"] == 0
    assert db.library_for_root(str(tmp_path / "Music"))["id"] == lib["id"]
    assert db.rename_library(lib["id"], "Đổi tên") is True
    assert db.get_library(lib["id"])["name"] == "Đổi tên"
    assert [x["name"] for x in db.libraries()] == ["Đổi tên"]
    assert db.remove_library(lib["id"]) is True
    assert db.libraries() == [] and db.get_library(lib["id"]) is None
    assert db.remove_library(lib["id"]) is False


def test_duplicate_root_and_empty_name_rejected(db, tmp_path):
    db.add_library("A", str(tmp_path / "Music"))
    with pytest.raises(ValueError):
        db.add_library("B", str(tmp_path / "Music"))
    with pytest.raises(ValueError):
        db.add_library("  ", str(tmp_path / "Other"))
    with pytest.raises(ValueError):
        db.rename_library(db.libraries()[0]["id"], "")


def test_tracks_saved_per_library_and_reloaded(db, tmp_path):
    a = db.add_library("A", str(tmp_path / "a"))["id"]
    b = db.add_library("B", str(tmp_path / "b"))["id"]
    db.replace_tracks(a, {"x.mp3": entry("X", comment="hay", bpm=120), "y.mp3": entry("Y")})
    db.replace_tracks(b, {"z.mp3": entry("Z")})
    db.close()

    again = library_db.LibraryDB(tmp_path / "library.db")
    try:
        loaded = again.load_tracks(a)
        assert sorted(loaded) == ["x.mp3", "y.mp3"]
        assert loaded["x.mp3"]["tags"]["title"] == "X"
        assert loaded["x.mp3"]["tags"]["comment"] == "hay"  # trường phụ -> cột extra (JSON)
        assert loaded["x.mp3"]["tags"]["bpm"] == 120
        assert loaded["x.mp3"]["size"] == 100 and loaded["x.mp3"]["mtime_ns"] == 1
        assert sorted(again.load_tracks(b)) == ["z.mp3"]
        assert {x["name"]: x["track_count"] for x in again.libraries()} == {"A": 2, "B": 1}
    finally:
        again.close()


def test_replace_upsert_delete_clear(db, tmp_path):
    a = db.add_library("A", str(tmp_path / "a"))["id"]
    db.replace_tracks(a, {"x.mp3": entry("X"), "y.mp3": entry("Y")})
    db.replace_tracks(a, {"x.mp3": entry("X2", mtime=2)})  # y biến mất
    assert sorted(db.load_tracks(a)) == ["x.mp3"]
    db.upsert_track(a, "n.mp3", entry("N"))
    db.delete_track(a, "x.mp3")
    assert list(db.load_tracks(a)) == ["n.mp3"]
    db.clear_tracks(a)
    assert db.track_count(a) == 0 and db.get_library(a) is not None


def test_remove_library_deletes_its_tracks(db, tmp_path):
    a = db.add_library("A", str(tmp_path / "a"))["id"]
    db.replace_tracks(a, {"x.mp3": entry("X")})
    db.remove_library(a)
    assert db.track_count(a) == 0


def test_last_scan_and_file_size(db, tmp_path):
    a = db.add_library("A", str(tmp_path / "a"))["id"]
    db.set_last_scan(a, "2026-11-26T10:00:00")
    assert db.get_library(a)["last_scan"] == "2026-11-26T10:00:00"
    assert db.file_size() > 0
