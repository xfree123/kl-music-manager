"""Đóng gói KL Music Manager: backend (PyInstaller) + ffmpeg + Electron (electron-builder).

Chạy: npm run dist   (hoặc python packaging/build.py [--skip-backend] [--no-ffmpeg])
Kết quả: dist/ (installer NSIS + win-unpacked trên Windows).

Chuẩn bị (một lần): `npm install` và `python packaging/fetch_ffmpeg.py` (ffmpeg essentials, tĩnh).
ffmpeg đóng kèm: packaging/vendor-ffmpeg/, rồi env KLMM_FFMPEG_SRC, rồi ffmpeg trên PATH;
bản build "shared" (cần DLL avcodec-*.dll cạnh exe) bị từ chối vì chỉ ffmpeg.exe được đóng gói.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "packaging" / "out"
WIN = sys.platform == "win32"

log = logging.getLogger("build")


def run(cmd: list[str]) -> None:
    log.info("$ %s", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True, shell=False)


def check_node_modules(root: Path) -> None:
    """Dừng sớm với hướng dẫn rõ ràng nếu chưa `npm install` (electron-builder cần electron
    cài sẵn trong node_modules để biết phiên bản chính xác)."""
    nm = root / "node_modules"
    if not (nm / "electron").is_dir() or not (nm / "electron-builder").is_dir():
        raise SystemExit("node_modules missing: run `npm install` in the project folder first")
    if not (nm / "electron" / "dist").is_dir():
        raise SystemExit(
            "Electron binary not downloaded: run `node node_modules/electron/install.js`"
        )


def is_shared_ffmpeg(exe: Path) -> bool:
    """Bản ffmpeg "shared" có avcodec-*.dll / avutil-*.dll nằm cạnh exe."""
    folder = Path(exe).parent
    return any(folder.glob("avcodec-*.dll")) or any(folder.glob("avutil-*.dll"))


def build_backend() -> None:
    run(
        [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", str(OUT / "backend-dist"),
            "--workpath", str(OUT / "pyinstaller-work"),
            str(ROOT / "packaging" / "kl-music-manager-backend.spec"),
        ]
    )  # fmt: skip


VENDOR_FFMPEG = ROOT / "packaging" / "vendor-ffmpeg" / "ffmpeg.exe"


def stage_ffmpeg() -> None:
    # Ưu tiên bản essentials đã kiểm SHA-256 (python packaging/fetch_ffmpeg.py, ~110 MB thay vì
    # ~190 MB của bản full); sau đó KLMM_FFMPEG_SRC; cuối cùng ffmpeg trên PATH.
    vendor = str(VENDOR_FFMPEG) if WIN and VENDOR_FFMPEG.is_file() else ""
    src = vendor or os.environ.get("KLMM_FFMPEG_SRC") or shutil.which("ffmpeg")
    if not src:
        raise SystemExit(
            "ffmpeg not found: run `python packaging/fetch_ffmpeg.py`, "
            "set KLMM_FFMPEG_SRC or put ffmpeg on PATH"
        )
    if is_shared_ffmpeg(Path(src)):
        raise SystemExit(
            f"{src} is a shared ffmpeg build (needs its DLLs) and would not run when bundled: "
            "run `python packaging/fetch_ffmpeg.py` (static essentials build)"
        )
    dest = OUT / "ffmpeg"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    shutil.copy2(src, dest / Path(src).name.lower())
    # Bản build GPL: kèm giấy phép (cùng thư mục với exe, hoặc cạnh thư mục bin/)
    exe_dir = Path(src).resolve().parent
    for lic in ("LICENSE", "LICENSE.txt", "README.txt", "VERSION.txt"):
        for candidate in (exe_dir / lic, exe_dir.parent / lic):
            if candidate.is_file():
                shutil.copy2(candidate, dest / f"ffmpeg-{lic}")
                break
    log.info("ffmpeg staged from %s", src)


def make_icon() -> None:
    """Icon bộ cài 512x512 (logo tự vẽ, sinh lại bằng packaging/make_logo.py)."""
    shutil.copy2(ROOT / "packaging" / "icon-512.png", OUT / "icon.png")


def build_electron(output: Optional[str] = None) -> None:
    npx = "npx.cmd" if WIN else "npx"
    target = (
        ["--win", "nsis", "dir"]
        if WIN
        else (["--mac"] if sys.platform == "darwin" else ["--linux"])
    )
    extra = [f"--config.directories.output={output}"] if output else []
    run([npx, "electron-builder", *target, "--publish", "never", *extra])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--skip-backend", action="store_true", help="dùng lại backend đã build")
    p.add_argument("--no-ffmpeg", action="store_true", help="không đóng kèm ffmpeg")
    p.add_argument("--out", help="thư mục output thay cho dist/ (không ghi đè bản build khác)")
    args = p.parse_args()
    check_node_modules(ROOT)
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.skip_backend:
        build_backend()
    if args.no_ffmpeg:
        shutil.rmtree(OUT / "ffmpeg", ignore_errors=True)
        (OUT / "ffmpeg").mkdir()
    else:
        stage_ffmpeg()
    make_icon()
    build_electron(args.out)


if __name__ == "__main__":
    main()
