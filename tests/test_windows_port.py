"""Hành vi phụ thuộc hệ điều hành: dò iPod, mở/hiện file, dung lượng, config.

Không gọi OS thật: truyền system=... và monkeypatch các điểm chạm OS.
"""

import json
import platform
import shutil
from pathlib import Path

import pytest

import ipod_manager
import os_integration


def make_fake_ipod(root: Path) -> Path:
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    return root


# ---------------------------------------------------------------- dò mountpoint
def test_find_mountpoints_windows_uses_drive_letters(tmp_path, monkeypatch):
    ipod = make_fake_ipod(tmp_path / "E")
    usb_stick = tmp_path / "F"
    usb_stick.mkdir()
    monkeypatch.setattr(ipod_manager, "_windows_drives", lambda: [str(usb_stick), str(ipod)])

    assert ipod_manager.find_ipod_mountpoints(system="Windows") == [str(ipod)]


def test_find_mountpoints_macos_scans_volumes(tmp_path, monkeypatch):
    make_fake_ipod(tmp_path / "MyiPod")
    (tmp_path / "Macintosh HD").mkdir()
    monkeypatch.setattr(ipod_manager, "MACOS_VOLUMES", tmp_path)

    assert ipod_manager.find_ipod_mountpoints(system="Darwin") == [str(tmp_path / "MyiPod")]


def test_find_mountpoints_unknown_system_is_empty():
    assert ipod_manager.find_ipod_mountpoints(system="Plan9") == []


# ---------------------------------------------------------------- mở / hiện file
def test_reveal_command_windows_selects_file_in_explorer():
    path = r"E:\iPod_Control\Music\F00\ABCD.mp3"
    assert os_integration.reveal_command(path, "Windows") == ["explorer", f"/select,{path}"]


def test_reveal_command_macos_uses_open_r():
    assert os_integration.reveal_command("/Volumes/iPod/a.mp3", "Darwin") == [
        "open",
        "-R",
        "/Volumes/iPod/a.mp3",
    ]


def test_reveal_command_linux_opens_parent_folder():
    cmd = os_integration.reveal_command("/media/u/IPOD/iPod_Control/a.mp3", "Linux")
    assert cmd == ["xdg-open", str(Path("/media/u/IPOD/iPod_Control"))]


def test_reveal_windows_quotes_only_the_path(monkeypatch):
    # Explorer cần /select,"<đường dẫn>". subprocess với list sẽ bọc nháy cả cụm
    # "/select,C:\a b\c.mp3" -> Explorer bỏ qua và mở Documents (lỗi người dùng gặp với thư mục nhạc).
    calls = []
    monkeypatch.setattr(os_integration.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))
    path = r"C:\Users\me\Music\Hồng Nhung\Nghe Mưa\01 Tình thôi xót xa.mp3"

    os_integration.reveal_in_file_manager(path, system="Windows")

    assert calls == [f'explorer /select,"{path}"']


def test_open_with_default_app_windows_uses_startfile(monkeypatch):
    opened = []
    monkeypatch.setattr(os_integration.os, "startfile", opened.append, raising=False)

    os_integration.open_with_default_app(r"E:\a.mp3", system="Windows")

    assert opened == [r"E:\a.mp3"]


def test_open_with_default_app_macos_runs_open(monkeypatch):
    calls = []
    monkeypatch.setattr(os_integration.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))

    os_integration.open_with_default_app("/Volumes/iPod/a.mp3", system="Darwin")

    assert calls == [["open", "/Volumes/iPod/a.mp3"]]


# ---------------------------------------------------------------- device info
@pytest.fixture
def bare_manager(tmp_path):
    """IPodManager không chạy __init__ (không dò thiết bị, không tạo virtual_ipod)."""
    m = ipod_manager.IPodManager.__new__(ipod_manager.IPodManager)
    m.config = {"ipod_path": str(tmp_path), "read_only": True}
    m.read_only = True
    m.mountpoint = str(tmp_path)
    m.db = None
    return m


def test_device_info_reports_real_disk_usage(bare_manager, tmp_path):
    info = bare_manager.get_device_info()
    usage = shutil.disk_usage(tmp_path)

    assert info["total_space"] == usage.total
    assert info["free_space"] == usage.free


def test_device_info_reports_host_os(bare_manager):
    assert bare_manager.get_device_info()["host_os"] == platform.system()


# ---------------------------------------------------------------- config
def test_load_config_reads_utf8_path(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    ipod_path = r"D:\Nhạc iPod"
    cfg.write_text(
        json.dumps({"ipod_path": ipod_path, "read_only": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(ipod_manager, "CONFIG_PATH", str(cfg))

    assert ipod_manager.load_config()["ipod_path"] == ipod_path
