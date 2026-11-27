"""Export danh sách nhạc / thông tin thư viện ra JSON và HTML."""

import json

import library_export

RECORDS = [
    {
        "id": 1,
        "title": "<script>alert(1)</script>",
        "artist": "Trịnh Công Sơn",
        "album": "Ca khúc da vàng",
        "genre": "Nhạc Việt",
        "year": 1970,
        "duration_s": 245,
        "file_type": "Apple Lossless audio file",
        "file_size": 30_000_000,
        "bitrate_kbps": 980,
        "play_count": 3,
    },
    {
        "id": 2,
        "title": "Song B",
        "artist": "Artist B",
        "album": "Album B",
        "genre": "Pop",
        "year": 2001,
        "duration_s": 200,
        "file_type": "MPEG audio file",
        "file_size": 8_000_000,
        "bitrate_kbps": 320,
        "play_count": 0,
    },
]
DEVICE = {
    "model": "iPod Classic 1st Gen (6G) (80GB)",
    "mountpoint": "D:\\",
    "total_space": 80,
    "free_space": 20,
}
PLAYLISTS = [
    {"name": "iPod", "is_master": True, "track_ids": [1, 2]},
    {"name": "Yêu thích", "is_master": False, "track_ids": [1]},
]


def test_tracks_json_roundtrip():
    data = json.loads(library_export.tracks_json(RECORDS, title="All tracks"))
    assert data["title"] == "All tracks"
    assert data["count"] == 2
    assert data["tracks"] == RECORDS
    assert "exported_at" in data


def test_tracks_html_escapes_and_keeps_unicode():
    page = library_export.tracks_html(RECORDS, title="Danh sách <nhạc>")
    assert page.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8">' in page
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "Trịnh Công Sơn" in page
    assert "Danh sách &lt;nhạc&gt;" in page
    assert "4:05" in page  # 245 giây


def test_library_info_totals():
    info = library_export.library_info(DEVICE, RECORDS, PLAYLISTS)

    assert info["device"]["model"] == DEVICE["model"]
    assert info["totals"]["tracks"] == 2
    assert info["totals"]["duration_s"] == 445
    assert info["totals"]["size_bytes"] == 38_000_000
    assert info["totals"]["artists"] == 2
    assert info["totals"]["albums"] == 2
    assert info["by_file_type"] == {"Apple Lossless audio file": 1, "MPEG audio file": 1}
    assert {"name": "Yêu thích", "track_count": 1, "is_master": False} in info["playlists"]


def test_library_info_html():
    info = library_export.library_info(DEVICE, RECORDS, PLAYLISTS)
    page = library_export.library_info_html(info)
    assert "iPod Classic 1st Gen (6G) (80GB)" in page
    assert "Yêu thích" in page
    assert "Apple Lossless audio file" in page
