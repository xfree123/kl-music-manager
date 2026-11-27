"""Cấu hình ứng dụng: mặc định, validate, lưu UTF-8, thư mục dữ liệu."""

import json
from pathlib import Path

import pytest

import settings


def test_missing_file_creates_defaults(tmp_path):
    cfg = tmp_path / "config.json"

    loaded = settings.load_settings(cfg)

    assert loaded == settings.DEFAULTS
    assert json.loads(cfg.read_text(encoding="utf-8")) == settings.DEFAULTS


def test_defaults_cover_all_options():
    d = settings.DEFAULTS
    assert d["export_format"] == "original"
    assert d["read_only"] is False
    # Đổi từ False -> True ở task player (2026-11-26, đã duyệt): player cần stream ALAC
    assert d["stream_unsupported"] is True
    assert set(d["export_options"]) == {"bitrate_kbps", "sample_rate", "flac_level"}
    assert d["export_dir"]  # có thư mục mặc định
    assert d["library_source"] == "ipod"
    assert d["library_folder"] == "" and d["recent_folders"] == []


@pytest.mark.parametrize(
    "change",
    [{"library_source": "cloud"}, {"recent_folders": ["a"] * 6}, {"recent_folders": [""]}],
)
def test_library_settings_validated(tmp_path, change):
    with pytest.raises(settings.SettingsError):
        settings.update_settings(change, tmp_path / "config.json")


def test_ipod_import_convert_setting(tmp_path):
    assert settings.DEFAULTS["ipod_import_convert"] == "auto"
    for mode in ("auto", "aac", "mp3", "alac", "off"):
        cfg = settings.update_settings({"ipod_import_convert": mode}, tmp_path / "config.json")
        assert cfg["ipod_import_convert"] == mode
    with pytest.raises(settings.SettingsError):
        settings.update_settings({"ipod_import_convert": "wma"}, tmp_path / "config.json")


def test_library_source_accepts_default(tmp_path):
    updated = settings.update_settings({"library_source": "default"}, tmp_path / "config.json")
    assert updated["library_source"] == "default"


def test_partial_and_invalid_values_fall_back_to_defaults(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"ipod_path": "E:\\", "read_only": True, "export_format": "ogg"}),
        encoding="utf-8",
    )

    loaded = settings.load_settings(cfg)

    assert loaded["ipod_path"] == "E:\\"
    assert loaded["read_only"] is True
    assert loaded["export_format"] == "original"  # "ogg" không hợp lệ
    assert loaded["export_options"] == settings.DEFAULTS["export_options"]


def test_update_saves_utf8_and_reloads(tmp_path):
    cfg = tmp_path / "config.json"
    export_dir = str(tmp_path / "Nhạc xuất")

    updated = settings.update_settings(
        {"export_dir": export_dir, "export_format": "mp3", "export_options": {"bitrate_kbps": 192}},
        cfg,
    )

    assert updated["export_dir"] == export_dir
    assert updated["export_options"]["bitrate_kbps"] == 192
    assert (
        updated["export_options"]["flac_level"] == settings.DEFAULTS["export_options"]["flac_level"]
    )
    assert settings.load_settings(cfg) == updated
    assert "Nhạc xuất" in cfg.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "change",
    [
        {"export_format": "ogg"},
        {"read_only": "yes"},
        {"export_options": {"bitrate_kbps": 1000}},
        {"export_options": {"flac_level": 12}},
        {"export_options": {"sample_rate": 12345}},
        {"export_dir": ""},
        {"no_such_key": 1},
    ],
)
def test_update_rejects_invalid_and_keeps_file(tmp_path, change):
    cfg = tmp_path / "config.json"
    before = settings.load_settings(cfg)

    with pytest.raises(settings.SettingsError):
        settings.update_settings(change, cfg)

    assert settings.load_settings(cfg) == before


def test_config_with_utf8_bom_is_read(tmp_path):
    # Notepad / PowerShell 5.1 `Out-File -Encoding utf8` ghi BOM: không được rơi về mặc định
    # (mặc định read_only=False sẽ âm thầm tắt chế độ bảo vệ).
    cfg = tmp_path / "config.json"
    cfg.write_bytes(b"\xef\xbb\xbf" + json.dumps({"read_only": True}).encode("utf-8"))

    assert settings.load_settings(cfg)["read_only"] is True


def test_data_dir_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KLMM_DATA_DIR", str(tmp_path))
    assert settings.data_dir() == tmp_path
    assert settings.config_path() == tmp_path / "config.json"


def test_data_dir_defaults_to_repo_root(monkeypatch):
    monkeypatch.delenv("KLMM_DATA_DIR", raising=False)
    assert settings.data_dir() == Path(settings.__file__).resolve().parent


def test_auto_rescan_defaults_off():
    d = settings.DEFAULTS
    assert d["auto_rescan_idle"] is False
    assert d["auto_rescan_idle_minutes"] == 15
    assert d["auto_rescan_interval_hours"] == 24
    assert d["last_auto_rescan"] == ""


@pytest.mark.parametrize(
    "change",
    [
        {"auto_rescan_idle": "yes"},
        {"auto_rescan_idle_minutes": 4},
        {"auto_rescan_idle_minutes": 241},
        {"auto_rescan_interval_hours": 0},
        {"auto_rescan_interval_hours": 169},
        {"last_auto_rescan": "hôm qua"},
    ],
)
def test_auto_rescan_settings_validated(tmp_path, change):
    with pytest.raises(settings.SettingsError):
        settings.update_settings(change, tmp_path / "config.json")


def test_auto_rescan_settings_accepted(tmp_path):
    updated = settings.update_settings(
        {
            "auto_rescan_idle": True,
            "auto_rescan_idle_minutes": 30,
            "auto_rescan_interval_hours": 6,
            "last_auto_rescan": "2026-11-26T10:00:00",
        },
        tmp_path / "config.json",
    )
    assert updated["auto_rescan_idle"] is True and updated["auto_rescan_idle_minutes"] == 30
