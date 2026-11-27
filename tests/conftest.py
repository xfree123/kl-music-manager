import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Layout phẳng: app.py, ipod_manager.py, os_integration.py nằm ở gốc repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg không có trên PATH")

TEST_TITLE = "Bài hát thử <b>&</b>"
TEST_ARTIST = "Nghệ sĩ Việt"


def make_alac(dest: Path, seconds: int = 2) -> Path:
    """File ALAC .m4a có tag tiếng Việt và ảnh bìa (sinh bằng ffmpeg lavfi)."""
    cover = dest.with_suffix(".png")
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "color=c=red:s=64x64", "-frames:v", "1", str(cover)],
        check=True,
    )  # fmt: skip
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=44100",
         "-i", str(cover),
         "-map", "0:a", "-map", "1:v", "-c:a", "alac", "-c:v", "png",
         "-disposition:v:0", "attached_pic",
         "-metadata", f"title={TEST_TITLE}", "-metadata", f"artist={TEST_ARTIST}",
         "-metadata", "album=Album thử",
         str(dest)],
        check=True,
    )  # fmt: skip
    cover.unlink()
    return dest


@pytest.fixture(scope="session")
def alac_file(tmp_path_factory) -> Path:
    if FFMPEG is None:
        pytest.skip("ffmpeg không có trên PATH")
    return make_alac(tmp_path_factory.mktemp("media") / "sine.m4a")


def make_cover(dest: Path, color: str = "blue", size: int = 64) -> Path:
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         f"color=c={color}:s={size}x{size}", "-frames:v", "1", str(dest)],
        check=True,
    )  # fmt: skip
    return dest


def make_audio(dest: Path, tags: dict, cover: Path = None, seconds: int = 2) -> Path:
    """File âm thanh (codec theo đuôi: mp3/flac/m4a=ALAC/ogg=Vorbis/opus) có tag, tùy chọn ảnh
    bìa nhúng."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    codec = {".mp3": "libmp3lame", ".flac": "flac", ".m4a": "alac", ".ogg": "libvorbis",
             ".opus": "libopus"}[dest.suffix]  # fmt: skip
    rate = 48000 if dest.suffix == ".opus" else 44100  # Opus chỉ nhận 48 kHz
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}:sample_rate={rate}"]  # fmt: skip
    if cover:
        cmd += ["-i", str(cover), "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg" if dest.suffix == ".mp3" else "png",
                "-disposition:v:0", "attached_pic"]  # fmt: skip
    cmd += ["-c:a", codec]
    if dest.suffix == ".mp3":
        cmd += ["-id3v2_version", "3"]
    for k, v in tags.items():
        cmd += ["-metadata", f"{k}={v}"]
    subprocess.run([*cmd, str(dest)], check=True)
    return dest


LIB_MP3_TITLE = "Tình thôi xót xa"


def make_music_folder(root: Path) -> Path:
    """Thư viện mẫu:
    Hồng Nhung/Nghe Mưa/01 Tình thôi xót xa.mp3  (tag đủ, ảnh bìa nhúng)
    Thanh Lam/Album B/song.flac                   (không ảnh nhúng, có cover.jpg cùng thư mục)
    Loose/untagged.m4a                            (ALAC, không tag)
    notes.txt                                     (không phải nhạc)
    Playlists/Yêu thích.m3u8                      (chứa bài mp3)
    """
    root.mkdir(parents=True, exist_ok=True)
    cover = make_cover(root / "_cover_src.jpg", "green")
    mp3 = make_audio(
        root / "Hồng Nhung" / "Nghe Mưa" / "01 Tình thôi xót xa.mp3",
        {"title": LIB_MP3_TITLE, "artist": "Hồng Nhung", "album": "Nghe Mưa",
         "album_artist": "Hồng Nhung", "genre": "Nhạc Việt", "track": "1/10", "date": "2001",
         "composer": "Trịnh Công Sơn"},
        cover=cover,
    )  # fmt: skip
    make_audio(
        root / "Thanh Lam" / "Album B" / "song.flac",
        {"title": "Bài FLAC", "artist": "Thanh Lam", "album": "Album B"},
    )
    make_cover(root / "Thanh Lam" / "Album B" / "cover.jpg", "yellow")
    make_audio(root / "Loose" / "untagged.m4a", {})
    cover.unlink()
    (root / "notes.txt").write_text("not music", encoding="utf-8")
    pl = root / "Playlists"
    pl.mkdir()
    rel = os.path.relpath(mp3, pl).replace(os.sep, "/")
    (pl / "Yêu thích.m3u8").write_text(f"#EXTM3U\n{rel}\n", encoding="utf-8")
    return root
