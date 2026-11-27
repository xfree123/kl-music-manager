"""Import vào iPod: file iPod không phát được (FLAC, OGG, Opus, WAV chứa DTS…) được chuyển định
dạng trước khi chép (cài đặt `ipod_import_convert`, mặc định "auto")."""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mutagen import File as MutagenFile
from mutagen.mp4 import MP4

import converter
from conftest import FFMPEG, make_alac, make_audio, needs_ffmpeg
from test_dts_wav import make_dts_wav, make_wav

pytestmark = needs_ffmpeg


def make_flac(dest: Path, rate=96000, title="Sóng Hi-Res", seconds=2) -> Path:
    """FLAC 24-bit (s32) nhiều kênh tùy rate, có tag."""
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
           "-i", f"sine=frequency=440:duration={seconds}:sample_rate={rate}",
           "-ac", "2", "-c:a", "flac", "-sample_fmt", "s32",
           "-metadata", f"title={title}", "-metadata", "artist=Hà Lê", "-metadata", "album=Lossless"]  # fmt: skip
    subprocess.run([*cmd, str(dest)], check=True)
    return dest


# ---------------------------------------------------------------- chọn định dạng đích
@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    d = tmp_path_factory.mktemp("src")
    return {
        "flac96": make_flac(d / "hires.flac"),
        "flac44": make_flac(d / "cd.flac", rate=44100),
        "ogg": make_audio(d / "a.ogg", {"title": "Vorbis"}),
        "opus": make_audio(d / "a.opus", {"title": "Opus"}),
        "mp3": make_audio(d / "a.mp3", {"title": "MP3"}),
        "alac": make_alac(d / "a.m4a"),
        "wav": make_wav(d / "pcm.wav", b"\x01\x02" * 4000),
        "dts": make_dts_wav(d / "dts.wav"),
    }


def test_playable_formats_are_kept(sources):
    for key in ("mp3", "alac", "wav"):
        assert converter.ipod_playable(str(sources[key])), key
        assert converter.ipod_import_target(str(sources[key]), "auto") is None, key
    for key in ("flac96", "ogg", "opus", "dts"):
        assert not converter.ipod_playable(str(sources[key])), key


def test_auto_lossless_to_alac_16bit_stereo(sources):
    fmt, opts = converter.ipod_import_target(str(sources["flac96"]), "auto")
    assert fmt == "alac"
    assert opts == {"channels": 2, "sample_fmt": "s16p", "sample_rate": 44100}  # 96 kHz -> 44.1
    fmt, opts = converter.ipod_import_target(str(sources["flac44"]), "auto")
    assert fmt == "alac" and opts["sample_rate"] == 0  # giữ nguyên 44.1 kHz


def test_auto_lossy_to_aac(sources):
    for key in ("ogg", "opus", "dts"):
        fmt, opts = converter.ipod_import_target(str(sources[key]), "auto")
        assert fmt == "aac" and opts["bitrate_kbps"] == 256 and opts["channels"] == 2, key


def test_fixed_modes_and_off(sources):
    flac = str(sources["flac96"])
    assert converter.ipod_import_target(flac, "aac")[0] == "aac"
    fmt, opts = converter.ipod_import_target(flac, "mp3")
    assert fmt == "mp3" and opts["bitrate_kbps"] == 320
    assert converter.ipod_import_target(str(sources["ogg"]), "alac")[0] == "alac"
    assert converter.ipod_import_target(flac, "off") is None
    assert converter.ipod_import_target(str(sources["mp3"]), "mp3") is None  # đã phát được


def test_build_command_ogg_opus_tags_from_audio_stream():
    for src in ("a.ogg", "b.opus", "c.OGA"):
        cmd = converter.build_command("ffmpeg", src, "x.m4a", "aac", {}, {})
        assert cmd[cmd.index("-map_metadata") + 1] == "0:s:a:0", src
    cmd = converter.build_command("ffmpeg", "a.flac", "x.m4a", "aac", {}, {})
    assert cmd[cmd.index("-map_metadata") + 1] == "0"


def test_build_command_sample_fmt():
    cmd = converter.build_command("ffmpeg", "a.flac", "b.m4a", "alac", {"sample_fmt": "s16p"}, {})
    assert cmd[cmd.index("-sample_fmt") + 1] == "s16p"


# ---------------------------------------------------------------- import thật vào iPod ảo
@pytest.fixture(scope="module")
def env(tmp_path_factory, sources):
    from pygpod.device.mountpoint import init_ipod

    root = tmp_path_factory.mktemp("ipodconv")
    data_dir, ipod_dir, music = root / "data", root / "ipod", root / "Music"
    data_dir.mkdir()
    ipod_dir.mkdir()
    music.mkdir()
    init_ipod(str(ipod_dir), model="classic_6g", music_dirs=2)
    (data_dir / "config.json").write_text(
        json.dumps({"ipod_path": str(ipod_dir), "ffmpeg_path": FFMPEG}, ensure_ascii=False),
        encoding="utf-8",
    )
    old = os.environ.get("KLMM_DATA_DIR")
    os.environ["KLMM_DATA_DIR"] = str(data_dir)
    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    yield {"client": app_module.app.test_client(), "music": music, "app": app_module}
    sys.modules.pop("app", None)
    if old is None:
        os.environ.pop("KLMM_DATA_DIR", None)
    else:
        os.environ["KLMM_DATA_DIR"] = old


@pytest.fixture
def client(env):
    c = env["client"]
    yield c
    c.put("/api/settings", json={"ipod_import_convert": "auto"})
    c.post("/api/library/source", json={"source": "ipod"})


def import_one(client, path):
    res = client.post("/api/tracks/import-paths", json={"paths": [str(path)]})
    assert res.status_code == 200
    return res.get_json()["results"][0]


def track_by_id(client, track_id):
    return next(t for t in client.get("/api/tracks").get_json() if t["id"] == track_id)


def test_default_setting_is_auto(client):
    assert client.get("/api/settings").get_json()["ipod_import_convert"] == "auto"
    assert client.put("/api/settings", json={"ipod_import_convert": "wma"}).status_code == 400


def test_import_flac_becomes_alac_with_tags(client, sources):
    r = import_one(client, sources["flac96"])
    assert r["ok"] is True and r["converted"] == "FLAC → ALAC", r
    t = track_by_id(client, r["track_id"])
    assert t["title"] == "Sóng Hi-Res" and t["artist"] == "Hà Lê" and t["album"] == "Lossless"
    path = Path(t["file_path"])
    assert path.suffix.lower() == ".m4a"
    info = MP4(str(path)).info
    assert info.codec == "alac" and info.bits_per_sample == 16
    assert info.sample_rate == 44100 and info.channels == 2
    assert sources["flac96"].exists()  # file gốc không bị đụng tới


def test_import_ogg_becomes_aac_mp3_kept(client, sources):
    r = import_one(client, sources["ogg"])
    assert r["ok"] and r["converted"] == "Vorbis → AAC"
    t = track_by_id(client, r["track_id"])
    assert MP4(t["file_path"]).info.codec.startswith("mp4a")
    assert t["title"] == "Vorbis"  # tag OGG nằm ở metadata luồng audio, phải giữ được
    r = import_one(client, sources["mp3"])
    assert r["ok"] and r.get("converted") is None
    assert Path(track_by_id(client, r["track_id"])["file_path"]).suffix.lower() == ".mp3"


def test_mode_mp3_and_off(client, sources):
    client.put("/api/settings", json={"ipod_import_convert": "mp3"})
    r = import_one(client, sources["flac44"])
    assert r["converted"] == "FLAC → MP3"
    assert Path(track_by_id(client, r["track_id"])["file_path"]).suffix.lower() == ".mp3"
    client.put("/api/settings", json={"ipod_import_convert": "off"})
    r = import_one(client, sources["opus"])
    # off = hành vi cũ: không chuyển; pygpod từ chối định dạng iPod không phát được
    assert r["ok"] is False and "not supported by iPod" in r["error"]


def test_upload_route_reports_conversion(client, sources):
    with open(sources["flac44"], "rb") as f:
        res = client.post(
            "/api/tracks/add",
            data={"file": (f, "upload.flac")},
            content_type="multipart/form-data",
        )
    data = res.get_json()
    assert data["success"] is True and data["converted"] == "FLAC → ALAC"


def test_no_ffmpeg_refuses_unplayable_file(client, sources, monkeypatch):
    before = len(client.get("/api/tracks").get_json())
    monkeypatch.setattr(converter, "find_ffmpeg", lambda *a, **k: None)
    r = import_one(client, sources["ogg"])
    assert r["ok"] is False and "ffmpeg" in r["error"]
    assert len(client.get("/api/tracks").get_json()) == before
    r = import_one(client, sources["mp3"])  # file phát được vẫn import bình thường
    assert r["ok"] is True


def test_folder_library_keeps_original_format(client, env, sources):
    assert (
        client.post(
            "/api/library/source", json={"source": "folder", "folder": str(env["music"])}
        ).status_code
        == 200
    )
    r = import_one(client, sources["flac44"])
    assert r["ok"] and r.get("converted") is None
    assert MutagenFile(str(next(env["music"].rglob("*.flac")))) is not None
