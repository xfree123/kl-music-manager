"""Bảo vệ backend localhost: chặn DNS rebinding / CSRF, ffmpeg_path an toàn, AppleScript không chèn lệnh."""

import importlib
import json
import os
import sys

import pytest

import os_integration
import settings


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("sec")
    (data_dir / "config.json").write_text(
        json.dumps({"library_source": "default"}), encoding="utf-8"
    )
    old = os.environ.get("KLMM_DATA_DIR")
    os.environ["KLMM_DATA_DIR"] = str(data_dir)
    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    yield app_module.app.test_client()
    sys.modules.pop("app", None)
    if old is None:
        os.environ.pop("KLMM_DATA_DIR", None)
    else:
        os.environ["KLMM_DATA_DIR"] = old


# ---------------------------------------------------------------- Host / Origin
@pytest.mark.parametrize("host", ["127.0.0.1:5055", "localhost:5055", "localhost", "[::1]:5055"])
def test_local_host_allowed(client, host):
    assert client.get("/api/settings", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example.com", "evil.example.com:5055", "127.0.0.1.evil.com"]
)
def test_foreign_host_rejected(client, host):
    # DNS rebinding: tên miền lạ trỏ về 127.0.0.1 -> Host vẫn là tên miền lạ.
    assert client.get("/api/settings", headers={"Host": host}).status_code == 403
    res = client.put("/api/settings", json={"read_only": False}, headers={"Host": host})
    assert res.status_code == 403


def test_same_origin_write_allowed(client):
    res = client.put(
        "/api/settings",
        json={"read_only": False},
        headers={"Host": "127.0.0.1:5055", "Origin": "http://127.0.0.1:5055"},
    )
    assert res.status_code == 200


@pytest.mark.parametrize(
    "origin", ["http://evil.example.com", "null", "http://localhost:6000", "https://127.0.0.1:5055"]
)
def test_cross_origin_write_rejected(client, origin):
    # CSRF: form/no-cors fetch từ trang khác gửi kèm Origin của trang đó.
    headers = {"Host": "127.0.0.1:5055", "Origin": origin}
    assert client.post("/api/tracks/reveal/1", headers=headers).status_code == 403
    assert client.post("/api/maintenance/clear-cache", headers=headers).status_code == 403


# ---------------------------------------------------------------- ffmpeg_path
@pytest.mark.parametrize(
    "value",
    ["", "ffmpeg", "/usr/local/bin/ffmpeg", r"C:\Tools\ffmpeg\bin\ffmpeg.exe", "D:/x/FFmpeg-7.exe"],
)
def test_ffmpeg_path_accepts_ffmpeg(value, tmp_path):
    cfg = tmp_path / "config.json"
    assert settings.update_settings({"ffmpeg_path": value}, cfg)["ffmpeg_path"] == value


@pytest.mark.parametrize(
    "value",
    [
        r"\\attacker\share\ffmpeg.exe",
        "//attacker/share/ffmpeg",
        r"C:\Windows\System32\cmd.exe",
        "/bin/sh",
        r"C:\x\ffmpeg.exe\..\calc.exe",
        5,
    ],
)
def test_ffmpeg_path_rejects_other_programs(value, tmp_path):
    with pytest.raises(settings.SettingsError):
        settings.update_settings({"ffmpeg_path": value}, tmp_path / "config.json")


# ---------------------------------------------------------------- AppleScript
def test_macos_reveal_passes_path_as_argument(monkeypatch):
    calls = []
    monkeypatch.setattr(os_integration.subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    path = '/Users/me/Music/x" & (do shell script "touch /tmp/pwned") & ".mp3'

    os_integration.reveal_in_file_manager(path, system="Darwin")

    cmd = calls[0]
    assert cmd[0] == "osascript"
    assert cmd[-1] == path  # đường dẫn là đối số riêng (argv), không nằm trong mã AppleScript
    script = " ".join(cmd[:-1])
    assert "do shell script" not in script
    assert "item 1 of argv" in script
