"""API Flask: cài đặt, export có convert, export thư viện, stream định dạng không hỗ trợ.

Chạy trên virtual iPod trong thư mục tạm (KLMM_DATA_DIR + ipod_path) — không quét ổ thật.
"""

import importlib
import json
import os
import sys
from pathlib import Path

import pytest
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3

from conftest import FFMPEG, TEST_TITLE, make_alac, needs_ffmpeg

pytestmark = needs_ffmpeg


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    import pygpod
    from pygpod.device.mountpoint import init_ipod

    root = tmp_path_factory.mktemp("api")
    data_dir, ipod_dir, export_dir = root / "data", root / "ipod", root / "Nhạc export"
    data_dir.mkdir()
    ipod_dir.mkdir()
    init_ipod(str(ipod_dir), model="classic_6g", music_dirs=2)
    db = pygpod.Database(str(ipod_dir))
    track = db.add_track(str(make_alac(root / "song.m4a")), title=TEST_TITLE)
    db.save()

    (data_dir / "config.json").write_text(
        json.dumps(
            {
                "ipod_path": str(ipod_dir),
                "export_dir": str(export_dir),
                "ffmpeg_path": FFMPEG,
                "stream_unsupported": False,  # mặc định đổi thành True; test ở đây cần tắt
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
        "track_id": track.track_id,
        "export_dir": export_dir,
        "data_dir": data_dir,
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
    # Trả cài đặt về trạng thái đầu cho test sau
    c.put("/api/settings", json={"read_only": False, "stream_unsupported": False})


# ---------------------------------------------------------------- cài đặt
def test_get_settings(env, client):
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.get_json()
    assert data["export_dir"] == str(env["export_dir"])
    assert data["export_format"] == "original"


def test_put_settings_validates(client):
    res = client.put("/api/settings", json={"export_format": "ogg"})
    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_read_only_toggle_applies_immediately_and_can_be_turned_off(client):
    assert client.put("/api/settings", json={"read_only": True}).status_code == 200
    assert client.post("/api/playlists/create", json={"name": "x"}).status_code == 403
    assert client.get("/api/device").get_json()["is_read_only"] is True

    res = client.put("/api/settings", json={"read_only": False})  # phải được phép khi read-only
    assert res.status_code == 200
    assert client.get("/api/device").get_json()["is_read_only"] is False


def test_settings_persisted_to_data_dir(env, client):
    client.put("/api/settings", json={"export_options": {"bitrate_kbps": 256}})
    saved = json.loads((env["data_dir"] / "config.json").read_text(encoding="utf-8"))
    assert saved["export_options"]["bitrate_kbps"] == 256


def test_about_reports_identity_from_version_py(client):
    import version

    data = client.get("/api/about").get_json()
    assert data["name"] == version.APP_NAME and data["version"] == version.VERSION
    assert data["author"] == version.AUTHOR
    assert data["homepage"] == version.HOMEPAGE


def test_formats_endpoint(client):
    data = client.get("/api/formats").get_json()
    assert data["ffmpeg_available"] is True
    assert [f["id"] for f in data["formats"]][:2] == ["original", "mp3"]


# ---------------------------------------------------------------- export bài hát
def test_export_convert_to_folder(env, client):
    res = client.post(
        f"/api/tracks/export/{env['track_id']}",
        json={"format": "mp3", "options": {"bitrate_kbps": 192}, "destination": "folder"},
    )
    assert res.status_code == 200, res.get_json()
    path = Path(res.get_json()["path"])
    assert path.parent == env["export_dir"] and path.suffix == ".mp3"
    assert abs(MP3(str(path)).info.bitrate - 192000) < 8000
    assert MutagenFile(str(path), easy=True)["title"] == [TEST_TITLE]


def test_export_original_to_folder_copies(env, client):
    res = client.post(
        f"/api/tracks/export/{env['track_id']}",
        json={"format": "original", "destination": "folder"},
    )
    assert res.status_code == 200
    assert Path(res.get_json()["path"]).suffix == ".m4a"


def test_export_download_returns_attachment(env, client):
    res = client.post(
        f"/api/tracks/export/{env['track_id']}", json={"format": "flac", "destination": "download"}
    )
    assert res.status_code == 200
    assert res.mimetype in ("audio/flac", "audio/x-flac")
    assert "attachment" in res.headers["Content-Disposition"]


def test_export_allowed_in_read_only(env, client):
    client.put("/api/settings", json={"read_only": True})
    res = client.post(f"/api/tracks/export/{env['track_id']}", json={"format": "original"})
    assert res.status_code == 200


def test_export_bad_format_400(env, client):
    res = client.post(f"/api/tracks/export/{env['track_id']}", json={"format": "ogg"})
    assert res.status_code == 400


def test_export_unknown_track_404(client):
    assert client.post("/api/tracks/export/999999", json={"format": "mp3"}).status_code == 404


# ---------------------------------------------------------------- export thư viện
def test_library_tracks_json(client):
    data = client.get("/api/library/tracks?format=json").get_json()
    assert data["count"] == 1
    t = data["tracks"][0]
    assert t["title"] == TEST_TITLE
    assert {"artist", "album", "duration_s", "file_type", "bitrate_kbps", "date_added"} <= set(t)


def test_library_tracks_html(client):
    res = client.get("/api/library/tracks?format=html")
    assert res.mimetype == "text/html"
    assert "Bài hát thử &lt;b&gt;&amp;&lt;/b&gt;" in res.get_data(as_text=True)


def test_library_tracks_by_playlist(client):
    data = client.get("/api/library/tracks?format=json&playlist=NoSuchPlaylist")
    assert data.status_code == 404


def test_library_info_json_and_folder(env, client):
    data = client.get("/api/library/info?format=json").get_json()
    assert data["totals"]["tracks"] == 1
    assert data["playlists"]

    res = client.get("/api/library/info?format=html&destination=folder")
    path = Path(res.get_json()["path"])
    assert path.parent == env["export_dir"] and path.suffix == ".html"
    assert "<!DOCTYPE html>" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- stream
def test_play_alac_serves_original_when_stream_disabled(env, client):
    res = client.get(f"/api/tracks/play/{env['track_id']}", headers={"Range": "bytes=0-99"})
    assert res.status_code == 206
    assert res.mimetype == "audio/mp4"


def test_play_alac_transcodes_when_stream_enabled(env, client):
    client.put("/api/settings", json={"stream_unsupported": True})
    res = client.get(f"/api/tracks/play/{env['track_id']}", headers={"Range": "bytes=0-99"})
    assert res.status_code == 206
    assert res.mimetype in ("audio/flac", "audio/x-flac")
    assert res.get_data()[:4] == b"fLaC"
