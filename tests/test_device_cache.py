"""Cache kết quả dò USB của pygpod theo volume serial: mở lại cùng iPod không gọi PowerShell nữa
(đo trên iPod thật: 2.48 s / 2.98 s thời gian nạp là 3 lần gọi PowerShell)."""

import json

import pygpod
import pytest
from pygpod.device import device as device_mod
from pygpod.device.models import lookup_model

import ipod_manager


@pytest.fixture
def virtual_ipod(tmp_path):
    from pygpod.device.mountpoint import init_ipod

    ipod = tmp_path / "ipod"
    ipod.mkdir()
    init_ipod(str(ipod), model="classic_6g", music_dirs=2)
    return ipod


@pytest.fixture
def fake_usb(monkeypatch):
    """Thay phần dò USB thật (PowerShell) bằng hàm đếm số lần gọi."""
    calls = []
    info = lookup_model("MB029")  # iPod Classic 6G 80GB

    def fake(sysinfo):
        calls.append(1)
        return info, {"FirewireGuid": "000A270012345678", "SerialNumber": "8K738WALY5N"}

    monkeypatch.setattr(ipod_manager, "_original_usb_fallback", fake)
    return calls


def test_usb_fallback_cached_per_volume(virtual_ipod, tmp_path, monkeypatch, fake_usb):
    cache_file = tmp_path / "device_cache.json"
    monkeypatch.setattr(ipod_manager, "_volume_key", lambda path: "VOL-1234")

    first = ipod_manager.open_ipod_database(str(virtual_ipod), cache_file)
    second = ipod_manager.open_ipod_database(str(virtual_ipod), cache_file)

    assert len(fake_usb) == 1  # lần 2 lấy từ cache
    assert first.device.model == second.device.model
    assert second.device.sysinfo.raw.get("FirewireGuid") == "000A270012345678"
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["VOL-1234"]["model_number"] == lookup_model("MB029").model_number


def test_different_volume_not_reused(virtual_ipod, tmp_path, monkeypatch, fake_usb):
    cache_file = tmp_path / "device_cache.json"
    keys = iter(["VOL-A", "VOL-B"])
    monkeypatch.setattr(ipod_manager, "_volume_key", lambda path: next(keys))

    ipod_manager.open_ipod_database(str(virtual_ipod), cache_file)
    ipod_manager.open_ipod_database(str(virtual_ipod), cache_file)

    assert len(fake_usb) == 2


def test_no_volume_key_means_no_cache(virtual_ipod, tmp_path, monkeypatch, fake_usb):
    cache_file = tmp_path / "device_cache.json"
    monkeypatch.setattr(ipod_manager, "_volume_key", lambda path: "")

    ipod_manager.open_ipod_database(str(virtual_ipod), cache_file)
    ipod_manager.open_ipod_database(str(virtual_ipod), cache_file)

    assert len(fake_usb) == 2
    assert not cache_file.exists()


def test_failed_usb_detection_is_not_cached(virtual_ipod, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ipod_manager, "_original_usb_fallback", lambda s: calls.append(1))
    monkeypatch.setattr(ipod_manager, "_volume_key", lambda path: "VOL-X")
    cache_file = tmp_path / "device_cache.json"

    ipod_manager.open_ipod_database(str(virtual_ipod), cache_file)
    ipod_manager.open_ipod_database(str(virtual_ipod), cache_file)

    assert len(calls) == 2  # không có kết quả -> thử lại lần sau (iPod có thể vừa cắm)


def test_pygpod_hook_restored_after_open(virtual_ipod, tmp_path, monkeypatch, fake_usb):
    monkeypatch.setattr(ipod_manager, "_volume_key", lambda path: "VOL-1")
    before = device_mod.Device._try_usb_fallback
    ipod_manager.open_ipod_database(str(virtual_ipod), tmp_path / "c.json")
    assert device_mod.Device._try_usb_fallback == before
    assert isinstance(pygpod.Database, type)


def test_volume_key_real_drive_on_windows():
    import platform

    if platform.system() != "Windows":
        pytest.skip("volume serial chỉ đọc trên Windows")
    key = ipod_manager._volume_key("C:\\")
    assert key and key.startswith("C:") is False and len(key) >= 4
