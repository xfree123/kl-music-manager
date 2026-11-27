"""Tải ffmpeg bản "essentials" (gyan.dev, GPLv3, static) để đóng kèm bộ cài Windows.

Chạy: python packaging/fetch_ffmpeg.py
Kết quả: packaging/vendor-ffmpeg/ffmpeg.exe + giấy phép (gitignored).
Kiểm SHA-256 với file .sha256 do gyan.dev công bố; sai -> dừng, không giải nén.
build.py tự dùng bản này nếu có (trước KLMM_FFMPEG_SRC / PATH).
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
ROOT = Path(__file__).resolve().parent
DEST = ROOT / "vendor-ffmpeg"
DOWNLOAD_DIR = ROOT / "out" / "ffmpeg-download"
KEEP = {"ffmpeg.exe", "LICENSE", "README.txt"}

log = logging.getLogger("fetch_ffmpeg")


def download(url: str, target: Path) -> None:
    log.info("Downloading %s", url)
    req = urllib.request.Request(url, headers={"User-Agent": "KL-Music-Manager-build"})
    with urllib.request.urlopen(req, timeout=120) as res, open(target, "wb") as f:
        shutil.copyfileobj(res, f)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)
    DOWNLOAD_DIR.mkdir(parents=True)
    archive = DOWNLOAD_DIR / "ffmpeg.zip"
    download(URL, archive)
    download(URL + ".sha256", DOWNLOAD_DIR / "ffmpeg.zip.sha256")
    expected = (DOWNLOAD_DIR / "ffmpeg.zip.sha256").read_text(encoding="utf-8").split()[0].lower()
    actual = sha256(archive)
    if actual != expected:
        log.error("SHA-256 mismatch: expected %s, got %s", expected, actual)
        return 1
    log.info("SHA-256 OK %s", actual)

    shutil.rmtree(DEST, ignore_errors=True)
    DEST.mkdir()
    with zipfile.ZipFile(archive) as z:
        version = ""
        for info in z.infolist():
            name = Path(info.filename).name
            if not version and info.filename.endswith("/"):
                version = info.filename.split("/")[0]
            # Chỉ lấy đúng các file cần, theo tên (không giải nén đường dẫn tùy ý từ zip)
            if name in KEEP and not info.is_dir():
                (DEST / name).write_bytes(z.read(info))
    (DEST / "VERSION.txt").write_text(f"{version}\nsha256 {actual}\n{URL}\n", encoding="utf-8")
    missing = KEEP - {p.name for p in DEST.iterdir()}
    if missing:
        log.error("Missing in archive: %s", ", ".join(sorted(missing)))
        return 1
    log.info("ffmpeg essentials ready in %s (%s)", DEST, version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
