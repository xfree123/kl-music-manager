"""Tích hợp với hệ điều hành: hiện file trong trình quản lý file, mở bằng app mặc định.

Mọi lệnh gọi OS của app đi qua module này để app.py không phụ thuộc nền tảng.
Hỗ trợ: Windows, macOS (Darwin), Linux (xdg-open).
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def reveal_command(path: str, system: Optional[str] = None) -> List[str]:
    """Lệnh mở trình quản lý file tại thư mục chứa `path` (chọn sẵn file nếu OS hỗ trợ)."""
    system = system or platform.system()
    if system == "Windows":
        # Explorer cần "/select,<path>" là MỘT đối số.
        return ["explorer", f"/select,{path}"]
    if system == "Darwin":
        return ["open", "-R", path]
    # Linux: xdg-open không chọn được file, mở thư mục cha.
    return ["xdg-open", str(Path(path).parent)]


def _reveal_macos_finder(path: str) -> bool:
    """Dùng lại cửa sổ Finder đang mở phía trước và chọn file. True nếu thành công."""
    applescript = f'''
    tell application "Finder"
        set fileAlias to (POSIX file "{path}") as alias
        if (count of Finder windows) is 0 then
            reveal fileAlias
        else
            set target of Finder window 1 to container of fileAlias
            select fileAlias
        end if
        activate
    end tell
    '''
    try:
        # Timeout ngắn: tránh treo khi người dùng bỏ qua hộp thoại cấp quyền của macOS.
        subprocess.run(
            ["osascript", "-e", applescript], check=True, timeout=1.5, capture_output=True
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def reveal_in_file_manager(path: str, system: Optional[str] = None) -> None:
    """Hiện file trong Finder / Explorer / trình quản lý file.

    Raises:
        OSError: không chạy được lệnh của hệ điều hành.
    """
    system = system or platform.system()
    if system == "Darwin" and _reveal_macos_finder(path):
        return
    # Không chờ và không kiểm tra exit code: explorer.exe trả 1 kể cả khi thành công.
    if system == "Windows":
        # Truyền chuỗi lệnh tự ghép: nếu truyền list, subprocess bọc nháy cả cụm
        # "/select,C:\a b\c.mp3" (khi có dấu cách) và Explorer mở Documents thay vì chọn file.
        subprocess.Popen(f'explorer /select,"{path}"')
        return
    subprocess.Popen(reveal_command(path, system))


def open_with_default_app(path: str, system: Optional[str] = None) -> None:
    """Mở file bằng ứng dụng mặc định của hệ điều hành.

    Raises:
        OSError: không chạy được lệnh / không có app gắn với loại file.
    """
    system = system or platform.system()
    if system == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]  # chỉ có trên Windows
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
