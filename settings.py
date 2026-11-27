"""Cấu hình ứng dụng (config.json): mặc định, validate, đọc/ghi UTF-8.

Thư mục dữ liệu = env KLMM_DATA_DIR (bản Electron đóng gói đặt %APPDATA%/KL Music Manager),
không có thì là thư mục chứa code (tương thích với cách chạy `python app.py`).
"""

from __future__ import annotations

import copy
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

import converter

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


class SettingsError(ValueError):
    """Giá trị cài đặt không hợp lệ."""


DEFAULTS: Dict[str, Any] = {
    "ipod_path": "",
    "read_only": False,
    "export_dir": str(Path.home() / "Music" / "KL Music Manager"),
    "export_format": "original",
    "export_options": {"bitrate_kbps": 320, "sample_rate": 0, "flac_level": 5},
    # Player cần stream ALAC để chuyển bài liên tục; không có ffmpeg thì vẫn rơi về System Player
    "stream_unsupported": True,
    # Import vào iPod: file iPod không phát được (FLAC, OGG, Opus, WAV-DTS) chuyển sang
    # auto (lossless -> ALAC, lossy -> AAC) | aac | mp3 | alac | off (chép nguyên)
    "ipod_import_convert": "auto",
    "ffmpeg_path": "",
    "library_source": "ipod",  # "ipod" | "folder" | "default" (iPod ảo trong data dir)
    "library_folder": "",
    "recent_folders": [],
    # Quét lại thư viện khi máy rảnh (chỉ bản Electron biết máy rảnh); mặc định tắt
    "auto_rescan_idle": False,
    "auto_rescan_idle_minutes": 15,
    "auto_rescan_interval_hours": 24,
    "last_auto_rescan": "",  # ISO, app tự ghi
}
MAX_RECENT_FOLDERS = 5


def data_dir() -> Path:
    env = os.environ.get("KLMM_DATA_DIR")
    return Path(env) if env else Path(__file__).resolve().parent


def config_path() -> Path:
    return data_dir() / "config.json"


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_iso_or_empty(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    if v == "":
        return True
    try:
        datetime.datetime.fromisoformat(v)
    except ValueError:
        return False
    return True


def _is_ffmpeg_path(v: Any) -> bool:
    """Rỗng (tự dò) hoặc đường dẫn cục bộ tới file tên ffmpeg*: chặn trỏ tới chương trình khác
    hay đường dẫn mạng (UNC) — giá trị này được chạy bằng subprocess khi export."""
    if not isinstance(v, str):
        return False
    if v == "":
        return True
    if v.startswith(("\\\\", "//")):
        return False
    parts = v.replace("\\", "/").split("/")
    if ".." in parts:
        return False
    return parts[-1].lower().startswith("ffmpeg")


_OPTION_RULES = {
    "bitrate_kbps": lambda v: _is_int(v) and v in converter.ALL_BITRATES,
    "sample_rate": lambda v: _is_int(v) and v in converter.SAMPLE_RATES,
    "flac_level": lambda v: _is_int(v) and v in converter.FLAC_LEVELS,
}
_RULES = {
    "ipod_path": lambda v: isinstance(v, str),
    "read_only": lambda v: isinstance(v, bool),
    "export_dir": lambda v: isinstance(v, str) and v.strip() != "",
    "export_format": lambda v: v in converter.FORMATS,
    "stream_unsupported": lambda v: isinstance(v, bool),
    "ipod_import_convert": lambda v: v in converter.IPOD_IMPORT_MODES,
    "ffmpeg_path": _is_ffmpeg_path,
    "library_source": lambda v: v in ("ipod", "folder", "default"),
    "library_folder": lambda v: isinstance(v, str),
    "recent_folders": lambda v: (
        isinstance(v, list)
        and len(v) <= MAX_RECENT_FOLDERS
        and all(isinstance(p, str) and p for p in v)
    ),
    "auto_rescan_idle": lambda v: isinstance(v, bool),
    "auto_rescan_idle_minutes": lambda v: _is_int(v) and 5 <= v <= 240,
    "auto_rescan_interval_hours": lambda v: _is_int(v) and 1 <= v <= 168,
    "last_auto_rescan": _is_iso_or_empty,
}


def _merge(base: Dict[str, Any], changes: Dict[str, Any], strict: bool) -> Dict[str, Any]:
    """Áp `changes` lên `base`. strict=True: lỗi -> SettingsError; False: bỏ giá trị sai."""
    result = copy.deepcopy(base)

    def reject(msg: str) -> None:
        if strict:
            raise SettingsError(msg)
        logger.warning("Ignoring invalid setting: %s", msg)

    for key, value in changes.items():
        if key == "export_options":
            if not isinstance(value, dict):
                reject("export_options must be an object")
                continue
            for opt, opt_value in value.items():
                rule = _OPTION_RULES.get(opt)
                if rule is None:
                    reject(f"unknown export option '{opt}'")
                elif not rule(opt_value):
                    reject(f"invalid value for export_options.{opt}: {opt_value!r}")
                else:
                    result["export_options"][opt] = opt_value
        elif key in _RULES:
            if _RULES[key](value):
                result[key] = value
            else:
                reject(f"invalid value for {key}: {value!r}")
        else:
            reject(f"unknown setting '{key}'")
    return result


def save_settings(values: Dict[str, Any], path: Optional[PathLike] = None) -> None:
    """Ghi atomically (file tạm rồi thay thế) để không hỏng config khi bị ngắt giữa chừng."""
    target = Path(path) if path else config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(values, indent=4, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)


def load_settings(path: Optional[PathLike] = None) -> Dict[str, Any]:
    """Đọc cài đặt; thiếu file thì tạo file mặc định; key thiếu/sai lấy mặc định."""
    target = Path(path) if path else config_path()
    if not target.exists():
        try:
            save_settings(DEFAULTS, target)
        except OSError as e:
            logger.error(f"Failed to create default config: {e}")
        return copy.deepcopy(DEFAULTS)
    try:
        # utf-8-sig: chấp nhận BOM (Notepad, PowerShell 5.1 Out-File) thay vì rơi về mặc định
        raw = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        logger.error(f"Failed to read config {target}: {e}")
        return copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        logger.error(f"Config {target} is not a JSON object; using defaults")
        return copy.deepcopy(DEFAULTS)
    return _merge(DEFAULTS, raw, strict=False)


def update_settings(changes: Dict[str, Any], path: Optional[PathLike] = None) -> Dict[str, Any]:
    """Validate và lưu thay đổi. Raises SettingsError (file giữ nguyên) nếu có giá trị sai."""
    if not isinstance(changes, dict):
        raise SettingsError("settings payload must be an object")
    updated = _merge(load_settings(path), changes, strict=True)
    save_settings(updated, path)
    return updated
