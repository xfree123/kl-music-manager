# PyInstaller spec: backend Flask của KL Music Manager (onedir).
# Build: python packaging/build.py (gọi pyinstaller với --distpath/--workpath trong packaging/out)
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 — SPECPATH do PyInstaller cung cấp

hidden = (
    collect_submodules("pygpod")  # import trễ bên trong pygpod (device.usb, hash...)
    + collect_submodules("mutagen")  # mutagen.File nạp module định dạng động
)

a = Analysis(  # noqa: F821
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "static"), "static")],
    hiddenimports=hidden,
    # Pillow: bỏ AVIF (~7.7 MB), Tk, quản lý màu ICC — app chỉ đọc/thu nhỏ JPEG/PNG/WebP
    excludes=["tkinter", "pytest", "ruff", "PIL._avif", "PIL.AvifImagePlugin", "PIL._imagingtk", "PIL.ImageTk", "PIL._imagingcms", "PIL.ImageCms"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KL-Music-Manager-Backend",
    console=True,  # Electron chạy với windowsHide; stdout/stderr vào backend.log
    upx=False,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    name="KL-Music-Manager-Backend",
    upx=False,
)
