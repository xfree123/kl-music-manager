"""API khi nguồn là thư mục nhạc: chuyển nguồn, ảnh bìa, phát, import nhiều file, sửa/xoá, read-only."""

import datetime
import importlib
import io
import json
import os
import sys
from pathlib import Path

import pytest
from mutagen import File as MutagenFile

from conftest import FFMPEG, LIB_MP3_TITLE, make_audio, make_cover, make_music_folder, needs_ffmpeg

pytestmark = needs_ffmpeg


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    import pygpod
    from pygpod.device.mountpoint import init_ipod

    root = tmp_path_factory.mktemp("apilib")
    data_dir, music, ipod = root / "data", root / "Music", root / "ipod"
    data_dir.mkdir()
    make_music_folder(music)
    # iPod ảo có 1 bài kèm ảnh bìa (để thử chuyển nguồn + ArtworkDB)
    ipod.mkdir()
    init_ipod(str(ipod), model="classic_6g", music_dirs=2)
    db = pygpod.Database(str(ipod))
    cover = make_cover(root / "c.png", "red", size=300)
    ipod_track = db.add_track(
        str(make_audio(root / "ipod.mp3", {"title": "iPod song"}, cover=cover))
    )
    db.save()

    (data_dir / "config.json").write_text(
        json.dumps(
            {
                "ipod_path": str(ipod),
                "library_source": "folder",
                "library_folder": str(music),
                "export_dir": str(root / "export"),
                "ffmpeg_path": FFMPEG,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    old = os.environ.get("KLMM_DATA_DIR")
    os.environ["KLMM_DATA_DIR"] = str(data_dir)
    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    yield {
        "client": app_module.app.test_client(),
        "music": music,
        "ipod": ipod,
        "ipod_track_id": ipod_track.track_id,
        "root": root,
    }
    sys.modules.pop("app", None)
    if old is None:
        os.environ.pop("KLMM_DATA_DIR", None)
    else:
        os.environ["KLMM_DATA_DIR"] = old


@pytest.fixture
def client(env):
    c = env["client"]
    yield c
    c.put("/api/settings", json={"read_only": False})
    c.post("/api/library/source", json={"source": "folder", "folder": str(env["music"])})


def tracks(client):
    return client.get("/api/tracks").get_json()


def tid(client, title):
    return next(t["id"] for t in tracks(client) if t["title"] == title)


# ---------------------------------------------------------------- nguồn
def test_device_info_for_folder(env, client):
    info = client.get("/api/device").get_json()
    assert info["source"] == "folder"
    assert info["mountpoint"] == str(env["music"])
    assert info["tracks_count"] == 3
    assert info["is_virtual"] is False


def test_tracks_have_search_fields(client):
    t = next(t for t in tracks(client) if t["title"] == LIB_MP3_TITLE)
    assert t["album_artist"] == "Hồng Nhung" and t["composer"] == "Trịnh Công Sơn"


def test_switch_source_to_ipod_and_back(env, client):
    res = client.post("/api/library/source", json={"source": "ipod"})
    assert res.status_code == 200
    assert client.get("/api/device").get_json()["source"] == "ipod"
    assert [t["title"] for t in tracks(client)] == ["iPod song"]

    res = client.post("/api/library/source", json={"source": "folder", "folder": str(env["music"])})
    assert res.status_code == 200
    src = client.get("/api/library/source").get_json()
    assert src["source"] == "folder" and src["recent_folders"][0] == str(env["music"])


def test_switch_source_rejects_missing_folder(env, client):
    res = client.post(
        "/api/library/source", json={"source": "folder", "folder": str(env["root"] / "nope")}
    )
    assert res.status_code == 400


def test_switch_source_allowed_in_read_only(env, client):
    client.put("/api/settings", json={"read_only": True})
    assert client.post("/api/library/source", json={"source": "ipod"}).status_code == 200


# ---------------------------------------------------------------- ảnh bìa + phát
def test_artwork_endpoint(client):
    res = client.get(f"/api/tracks/{tid(client, LIB_MP3_TITLE)}/artwork")
    assert res.status_code == 200 and res.mimetype == "image/jpeg"
    assert "max-age" in res.headers.get("Cache-Control", "")
    assert (
        client.get(f"/api/tracks/{tid(client, 'Bài FLAC')}/artwork").status_code == 200
    )  # cover.jpg
    assert client.get(f"/api/tracks/{tid(client, 'untagged')}/artwork").status_code == 404


def test_artwork_from_ipod_artworkdb(env, client):
    client.post("/api/library/source", json={"source": "ipod"})
    res = client.get(f"/api/tracks/{env['ipod_track_id']}/artwork")
    assert res.status_code == 200 and res.mimetype == "image/jpeg"


def test_play_folder_tracks(client):
    res = client.get(
        f"/api/tracks/play/{tid(client, LIB_MP3_TITLE)}", headers={"Range": "bytes=0-9"}
    )
    assert res.status_code == 206 and res.mimetype == "audio/mpeg"
    # ALAC + stream_unsupported (mặc định true) -> FLAC
    res = client.get(f"/api/tracks/play/{tid(client, 'untagged')}", headers={"Range": "bytes=0-3"})
    assert res.status_code == 206 and res.get_data() == b"fLaC"


def test_export_from_folder(env, client):
    res = client.post(
        f"/api/tracks/export/{tid(client, 'Bài FLAC')}",
        json={"format": "mp3", "destination": "folder"},
    )
    assert res.status_code == 200
    assert Path(res.get_json()["path"]).exists()


def test_library_info_for_folder(client):
    info = client.get("/api/library/info?format=json").get_json()
    assert info["totals"]["tracks"] == 3
    assert info["device"]["source"] == "folder"


# ---------------------------------------------------------------- import
def test_upload_with_playlist_and_safe_temp_name(env, client):
    src = make_audio(
        env["root"] / "up" / "up.mp3", {"title": "Tải lên", "artist": "Ca sĩ", "album": "Đĩa"}
    )
    data = {"file": (io.BytesIO(src.read_bytes()), "../../evil.mp3"), "playlist": "Yêu thích"}
    res = client.post("/api/tracks/add", data=data, content_type="multipart/form-data")
    body = res.get_json()
    assert res.status_code == 200 and body["success"], body
    assert (env["music"] / "Ca sĩ" / "Đĩa" / "evil.mp3").exists()
    assert not (env["root"].parent / "evil.mp3").exists()
    pl = next(p for p in client.get("/api/playlists").get_json() if p["name"] == "Yêu thích")
    assert body["track_id"] in pl["track_ids"]


def test_import_paths_recursive(env, client):
    folder = env["root"] / "batch"
    make_audio(folder / "a.mp3", {"title": "Batch A", "artist": "X", "album": "Y"})
    make_audio(folder / "sub" / "b.flac", {"title": "Batch B", "artist": "X", "album": "Y"})
    (folder / "readme.txt").write_text("x", encoding="utf-8")

    res = client.post(
        "/api/tracks/import-paths", json={"paths": [str(folder)], "playlist": "Yêu thích"}
    )
    body = res.get_json()
    assert res.status_code == 200
    assert sorted(Path(r["path"]).name for r in body["results"] if r["ok"]) == ["a.mp3", "b.flac"]
    titles = [t["title"] for t in tracks(client)]
    assert "Batch A" in titles and "Batch B" in titles


def test_import_into_ipod_playlist(env, client):
    client.post("/api/library/source", json={"source": "ipod"})
    client.post("/api/playlists/create", json={"name": "Chạy bộ"})
    src = make_audio(env["root"] / "ip" / "run.mp3", {"title": "Run"})
    res = client.post("/api/tracks/import-paths", json={"paths": [str(src)], "playlist": "Chạy bộ"})
    assert res.get_json()["results"][0]["ok"] is True
    pl = next(p for p in client.get("/api/playlists").get_json() if p["name"] == "Chạy bộ")
    assert len(pl["track_ids"]) == 1


# ---------------------------------------------------------------- sửa / xoá / playlist / read-only
def test_update_metadata_writes_tags(client):
    track_id = tid(client, "Bài FLAC")
    res = client.post(f"/api/tracks/update/{track_id}", json={"title": "FLAC đổi tên", "rating": 0})
    assert res.get_json()["success"] is True
    t = next(t for t in tracks(client) if t["id"] == track_id)
    assert t["title"] == "FLAC đổi tên"
    assert MutagenFile(t["file_path"], easy=True)["title"] == ["FLAC đổi tên"]


def test_playlist_endpoints_folder(env, client):
    assert client.post("/api/playlists/create", json={"name": "PL mới"}).get_json()["success"]
    track_id = tid(client, "untagged")
    assert client.post(f"/api/playlists/PL mới/add/{track_id}").get_json()["success"]
    assert (env["music"] / "Playlists" / "PL mới.m3u8").exists()
    assert client.delete("/api/playlists/PL mới").get_json()["success"]


def test_read_only_blocks_writes_in_folder_mode(env, client):
    client.put("/api/settings", json={"read_only": True})
    track_id = tid(client, "untagged")
    assert (
        client.post("/api/tracks/import-paths", json={"paths": [str(env["music"])]}).status_code
        == 403
    )
    assert client.post(f"/api/tracks/update/{track_id}", json={"title": "x"}).status_code == 403
    assert client.delete(f"/api/tracks/{track_id}").status_code == 403


def test_delete_track_removes_file(client):
    t = next(t for t in tracks(client) if t["title"] == "untagged")
    assert client.delete(f"/api/tracks/{t['id']}").get_json()["success"] is True
    assert not Path(t["file_path"]).exists()


# ---------------------------------------------------------------- thông tin file (details)
def png_upload(color="purple"):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, format="PNG")
    buf.seek(0)
    return buf


def test_details_folder_track(client):
    t = next(t for t in tracks(client) if t["title"] == LIB_MP3_TITLE)
    d = client.get(f"/api/tracks/{t['id']}/details").get_json()
    assert d["source"] == "folder" and d["cover_editable"] is True
    assert d["codec"] == "MP3" and d["sample_rate"] == 44100 and d["channels"] == 1
    assert d["bitrate_kbps"] > 0 and d["file_size"] == Path(t["file_path"]).stat().st_size
    assert d["file_type"] == "MPEG audio file" and d["extension"] == "mp3"
    assert d["tags"]["composer"] == "Trịnh Công Sơn" and d["tags"]["total_tracks"] == 10
    assert d["has_cover"] is True


def test_details_ipod_track_and_unknown(env, client):
    client.post("/api/library/source", json={"source": "ipod"})
    d = client.get(f"/api/tracks/{env['ipod_track_id']}/details").get_json()
    assert d["source"] == "ipod" and d["codec"] == "MP3" and d["cover_editable"] is False
    assert d["tags"]["title"] == "iPod song"
    assert client.get("/api/tracks/999999/details").status_code == 404


def test_update_extended_metadata(client):
    track_id = tid(client, LIB_MP3_TITLE)
    body = {"comment": "Ghi chú", "bpm": 90, "disc_number": 1, "total_discs": 2, "lyrics": "Mưa"}
    assert client.post(f"/api/tracks/update/{track_id}", json=body).get_json()["success"]
    tags = client.get(f"/api/tracks/{track_id}/details").get_json()["tags"]
    assert {k: tags[k] for k in body} == body


def test_update_ipod_album_artist_and_composer(env, client):
    client.post("/api/library/source", json={"source": "ipod"})
    track_id = env["ipod_track_id"]
    body = {"album_artist": "Nhiều ca sĩ", "composer": "Phú Quang"}
    assert client.post(f"/api/tracks/update/{track_id}", json=body).get_json()["success"]
    t = next(t for t in tracks(client) if t["id"] == track_id)
    assert t["album_artist"] == "Nhiều ca sĩ" and t["composer"] == "Phú Quang"


# ---------------------------------------------------------------- ảnh bìa
def test_set_and_remove_artwork(client):
    track_id = tid(client, LIB_MP3_TITLE)
    before = client.get(f"/api/tracks/{track_id}/artwork").get_data()
    res = client.post(
        f"/api/tracks/{track_id}/artwork",
        data={"image": (png_upload(), "cover.png")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200 and res.get_json() == {"success": True, "updated": 1}
    after = client.get(f"/api/tracks/{track_id}/artwork")
    assert after.status_code == 200 and after.get_data() != before

    assert client.delete(f"/api/tracks/{track_id}/artwork").get_json()["success"] is True
    assert client.get(f"/api/tracks/{track_id}/artwork").status_code == 404  # không có cover.jpg


def test_artwork_rejects_bad_input_ipod_and_read_only(env, client):
    track_id = tid(client, LIB_MP3_TITLE)
    url = f"/api/tracks/{track_id}/artwork"
    bad = {"image": (io.BytesIO(b"not an image"), "x.png")}
    assert client.post(url, data=bad, content_type="multipart/form-data").status_code == 400
    assert client.post(url, data={}, content_type="multipart/form-data").status_code == 400

    client.put("/api/settings", json={"read_only": True})
    up = {"image": (png_upload(), "c.png")}
    assert client.post(url, data=up, content_type="multipart/form-data").status_code == 403
    assert client.delete(url).status_code == 403
    client.put("/api/settings", json={"read_only": False})

    client.post("/api/library/source", json={"source": "ipod"})
    up = {"image": (png_upload(), "c.png")}
    ipod_url = f"/api/tracks/{env['ipod_track_id']}/artwork"
    assert client.post(ipod_url, data=up, content_type="multipart/form-data").status_code == 400


# ---------------------------------------------------------------- nhiều thư viện
@pytest.fixture
def second_folder(env):
    folder = env["root"] / "Second"
    if not folder.exists():
        make_audio(folder / "A" / "one.mp3", {"title": "Thư viện 2", "genre": "Jazz"})
    return folder


def libraries(client):
    return client.get("/api/libraries").get_json()


def test_opened_folder_is_registered_as_library(env, client):
    libs = libraries(client)
    music = next(x for x in libs if x["root"] == str(env["music"]))
    assert music["active"] is True and music["available"] is True and music["track_count"] > 0


def test_library_crud_and_open(env, client, second_folder):
    res = client.post("/api/libraries", json={"name": "Thứ hai", "root": str(second_folder)})
    assert res.status_code == 200, res.get_json()
    lib = res.get_json()["library"]
    assert lib["name"] == "Thứ hai" and lib["track_count"] == 1 and lib["active"] is False

    dup = client.post("/api/libraries", json={"name": "Lặp", "root": str(second_folder)})
    assert dup.status_code == 400
    missing = client.post("/api/libraries", json={"name": "X", "root": str(env["root"] / "nope")})
    assert missing.status_code == 400

    assert client.put(f"/api/libraries/{lib['id']}", json={"name": "Jazz"}).status_code == 200
    assert client.put(f"/api/libraries/{lib['id']}", json={"name": ""}).status_code == 400

    assert client.post(f"/api/libraries/{lib['id']}/open").status_code == 200
    assert [t["title"] for t in tracks(client)] == ["Thư viện 2"]
    active = next(x for x in libraries(client) if x["active"])
    assert active["name"] == "Jazz"
    # Gỡ thư viện đang mở -> chuyển về thư viện mặc định (task batch-export 2026-11-27, đã duyệt;
    # trước đây trả 400)
    res = client.delete(f"/api/libraries/{lib['id']}")
    assert res.status_code == 200 and res.get_json()["switched"] is True
    assert client.get("/api/library/source").get_json()["is_default"] is True
    assert (second_folder / "A" / "one.mp3").exists()  # gỡ thư viện không xoá file
    assert all(x["id"] != lib["id"] for x in libraries(client))

    lib = client.post("/api/libraries", json={"name": "Jazz", "root": str(second_folder)})
    lib = lib.get_json()["library"]
    music = next(x for x in libraries(client) if x["root"] == str(env["music"]))
    assert client.post(f"/api/libraries/{music['id']}/open").status_code == 200
    res = client.delete(f"/api/libraries/{lib['id']}")
    assert res.status_code == 200 and res.get_json()["switched"] is False
    assert (second_folder / "A" / "one.mp3").exists()
    assert all(x["id"] != lib["id"] for x in libraries(client))


def test_default_library_is_empty_virtual_ipod_even_with_ipod_connected(env, client, monkeypatch):
    import ipod_manager

    monkeypatch.setattr(ipod_manager, "find_ipod_mountpoints", lambda *a, **k: [str(env["ipod"])])
    res = client.post("/api/library/source", json={"source": "default"})
    assert res.status_code == 200, res.get_json()
    info = client.get("/api/library/source").get_json()
    virtual = env["root"] / "data" / "virtual_ipod"
    assert info["is_default"] is True and info["source"] == "ipod"
    assert Path(info["mountpoint"]) == virtual
    assert info["connected_ipods"] == [str(env["ipod"])]
    assert (virtual / "iPod_Control").is_dir()
    assert tracks(client) == []  # thư viện mặc định tạo mới thì trống
    assert client.get("/api/device").get_json()["is_virtual"] is True

    # Chọn iPod -> mở iPod theo cấu hình, không còn là thư viện mặc định
    assert client.post("/api/library/source", json={"source": "ipod"}).status_code == 200
    info = client.get("/api/library/source").get_json()
    assert info["is_default"] is False and Path(info["mountpoint"]) == env["ipod"]


def test_clear_rebuild_scan_library(env, client, second_folder):
    lib = client.post("/api/libraries", json={"name": "Tạm", "root": str(second_folder)})
    lib_id = lib.get_json()["library"]["id"]
    try:
        assert client.post(f"/api/libraries/{lib_id}/clear").status_code == 200
        assert next(x for x in libraries(client) if x["id"] == lib_id)["track_count"] == 0
        stats = client.post(f"/api/libraries/{lib_id}/scan").get_json()
        assert stats["added"] == 1 and stats["total"] == 1
        stats = client.post(f"/api/libraries/{lib_id}/rebuild").get_json()
        assert stats["changed"] == 1 and stats["total"] == 1
        assert client.post("/api/libraries/424242/scan").status_code == 404
    finally:
        client.delete(f"/api/libraries/{lib_id}")


def test_library_maintenance_allowed_in_read_only(env, client):
    music = next(x for x in libraries(client) if x["active"])
    client.put("/api/settings", json={"read_only": True})
    assert client.post(f"/api/libraries/{music['id']}/scan").status_code == 200
    assert client.post("/api/maintenance/clear-cache").status_code == 200
    assert client.post("/api/libraries/rescan", json={}).status_code == 200


def test_scan_in_progress_returns_409(env, client):
    manager = sys.modules["app"].manager
    music = next(x for x in libraries(client) if x["active"])
    assert manager.scan_lock.acquire(blocking=False)
    try:
        assert client.post(f"/api/libraries/{music['id']}/scan").status_code == 409
        assert client.post("/api/libraries/rescan", json={}).status_code == 409
    finally:
        manager.scan_lock.release()


# ---------------------------------------------------------------- dọn dẹp + quét khi rảnh
def test_maintenance_info_and_clear_cache(env, client):
    cache = env["root"] / "data" / "stream_cache"
    cache.mkdir(exist_ok=True)
    (cache / "old.flac").write_bytes(b"x" * 1000)
    info = client.get("/api/maintenance").get_json()
    assert info["db_bytes"] > 0 and info["stream_cache_bytes"] >= 1000
    assert any(x["root"] == str(env["music"]) for x in info["libraries"])
    res = client.post("/api/maintenance/clear-cache").get_json()
    assert res["success"] is True and res["freed_bytes"] >= 1000
    assert not any(cache.iterdir())
    assert client.get("/api/maintenance").get_json()["stream_cache_bytes"] == 0


def test_rescan_all_only_if_due(env, client):
    url = "/api/libraries/rescan"
    client.put("/api/settings", json={"auto_rescan_idle": False})
    assert client.post(url, json={"only_if_due": True}).get_json() == {"skipped": True}

    now = datetime.datetime.now().isoformat(timespec="seconds")
    client.put("/api/settings", json={"auto_rescan_idle": True, "last_auto_rescan": now})
    assert client.post(url, json={"only_if_due": True}).get_json() == {"skipped": True}

    client.put("/api/settings", json={"last_auto_rescan": "2000-01-01T00:00:00"})
    res = client.post(url, json={"only_if_due": True}).get_json()
    assert res["skipped"] is False and res["total"] > 0 and "active_changed" in res
    assert client.get("/api/settings").get_json()["last_auto_rescan"] > "2000"

    res = client.post(url, json={}).get_json()  # bấm tay: luôn chạy
    assert res["skipped"] is False
    client.put("/api/settings", json={"auto_rescan_idle": False})
