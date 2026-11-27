"""Convert bằng ffmpeg: dựng lệnh, tìm ffmpeg, convert thật, nhận diện ALAC, cache stream."""

import os

import pytest
from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

import converter
from conftest import TEST_ARTIST, TEST_TITLE, needs_ffmpeg

META = {"title": "Tên bài", "artist": "Ca sĩ"}


def args_after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


# ---------------------------------------------------------------- dựng lệnh
def test_build_command_mp3_bitrate():
    cmd = converter.build_command("ffmpeg", "in.m4a", "out.mp3", "mp3", {"bitrate_kbps": 320}, META)

    assert cmd[0] == "ffmpeg" and cmd[-1] == "out.mp3"
    assert args_after(cmd, "-i") == "in.m4a"
    assert args_after(cmd, "-c:a") == "libmp3lame"
    assert args_after(cmd, "-b:a") == "320k"
    assert "title=Tên bài" in cmd and "artist=Ca sĩ" in cmd


def test_build_command_flac_level_and_sample_rate():
    cmd = converter.build_command(
        "ffmpeg", "in.m4a", "out.flac", "flac", {"flac_level": 8, "sample_rate": 48000}, {}
    )

    assert args_after(cmd, "-c:a") == "flac"
    assert args_after(cmd, "-compression_level") == "8"
    assert args_after(cmd, "-ar") == "48000"
    assert "-b:a" not in cmd


def test_build_command_keep_sample_rate_by_default():
    cmd = converter.build_command("ffmpeg", "a", "b.m4a", "alac", {"sample_rate": 0}, {})
    assert "-ar" not in cmd
    assert args_after(cmd, "-c:a") == "alac"


def test_build_command_wav_has_no_cover_stream():
    cmd = converter.build_command("ffmpeg", "a", "b.wav", "wav", {}, {})
    assert args_after(cmd, "-c:a") == "pcm_s16le"
    assert "0:v?" not in cmd


def test_build_command_rejects_unknown_format():
    with pytest.raises(ValueError):
        converter.build_command("ffmpeg", "a", "b", "ogg", {}, {})


def test_formats_listing():
    ids = [f["id"] for f in converter.list_formats()]
    assert ids == ["original", "mp3", "aac", "flac", "alac", "wav"]
    mp3 = next(f for f in converter.list_formats() if f["id"] == "mp3")
    assert mp3["lossy"] is True and 320 in mp3["bitrates"]


def test_output_filename_sanitized():
    name = converter.output_filename({"artist": "AC/DC", "title": 'What?: "Live"'}, ".mp3")
    assert name == "AC_DC - What__ _Live_.mp3"


def test_output_filename_defaults():
    assert converter.output_filename({}, ".flac") == "Unknown Artist - Unknown Title.flac"


# ---------------------------------------------------------------- tìm ffmpeg
def test_find_ffmpeg_prefers_configured_path(tmp_path, monkeypatch):
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv("KLMM_FFMPEG", str(tmp_path / "other.exe"))
    assert converter.find_ffmpeg(str(exe)) == str(exe)


def test_find_ffmpeg_bundled_then_path(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled.exe"
    bundled.write_bytes(b"")
    monkeypatch.setenv("KLMM_FFMPEG", str(bundled))
    assert converter.find_ffmpeg("") == str(bundled)

    monkeypatch.delenv("KLMM_FFMPEG")
    monkeypatch.setattr(converter.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    assert converter.find_ffmpeg("") == "/usr/bin/ffmpeg"


def test_find_ffmpeg_none(tmp_path, monkeypatch):
    monkeypatch.delenv("KLMM_FFMPEG", raising=False)
    monkeypatch.setattr(converter.shutil, "which", lambda name: None)
    assert converter.find_ffmpeg(str(tmp_path / "missing.exe")) is None


# ---------------------------------------------------------------- convert thật
@needs_ffmpeg
@pytest.mark.parametrize(
    "fmt, options, check",
    [
        ("mp3", {"bitrate_kbps": 192}, lambda f: abs(MP3(f).info.bitrate - 192000) < 8000),
        ("aac", {"bitrate_kbps": 128}, lambda f: MP4(f).info.codec.startswith("mp4a")),
        (
            "flac",
            {"flac_level": 5, "sample_rate": 48000},
            lambda f: FLAC(f).info.sample_rate == 48000,
        ),
        ("alac", {}, lambda f: MP4(f).info.codec == "alac"),
        ("wav", {}, lambda f: MutagenFile(f).info.channels >= 1),
    ],
)
def test_convert_real(alac_file, tmp_path, fmt, options, check):
    dest = tmp_path / f"out{converter.FORMATS[fmt].ext}"

    out = converter.convert(str(alac_file), str(dest), fmt, options, {}, converter.find_ffmpeg(""))

    assert out == str(dest) and dest.stat().st_size > 0
    assert check(str(dest))


@needs_ffmpeg
@pytest.mark.parametrize("fmt", ["mp3", "flac", "aac", "alac"])
def test_convert_keeps_tags_and_cover(alac_file, tmp_path, fmt):
    dest = tmp_path / f"out{converter.FORMATS[fmt].ext}"
    converter.convert(str(alac_file), str(dest), fmt, {}, {}, converter.find_ffmpeg(""))

    tags = MutagenFile(str(dest), easy=True)
    assert tags["title"] == [TEST_TITLE]
    assert tags["artist"] == [TEST_ARTIST]
    full = MutagenFile(str(dest))
    if fmt == "mp3":
        assert full.tags.getall("APIC")
    elif fmt == "flac":
        assert full.pictures
    else:
        assert full.tags.get("covr")


@needs_ffmpeg
def test_convert_overrides_metadata(alac_file, tmp_path):
    dest = tmp_path / "out.mp3"
    converter.convert(
        str(alac_file), str(dest), "mp3", {}, {"title": "Mới"}, converter.find_ffmpeg("")
    )
    assert MutagenFile(str(dest), easy=True)["title"] == ["Mới"]


@needs_ffmpeg
def test_convert_error_raises_and_leaves_no_partial_file(tmp_path):
    src = tmp_path / "broken.m4a"
    src.write_bytes(b"not audio")
    dest = tmp_path / "out.mp3"

    with pytest.raises(converter.ConversionError):
        converter.convert(str(src), str(dest), "mp3", {}, {}, converter.find_ffmpeg(""))

    assert list(tmp_path.iterdir()) == [src]


# ---------------------------------------------------------------- nhận diện + stream
@needs_ffmpeg
def test_is_browser_unsupported(alac_file, tmp_path):
    mp3 = tmp_path / "x.mp3"
    converter.convert(str(alac_file), str(mp3), "mp3", {}, {}, converter.find_ffmpeg(""))

    assert converter.is_browser_unsupported(str(alac_file), "AAC audio file") is True
    assert converter.is_browser_unsupported(str(mp3), "MPEG audio file") is False
    assert converter.is_browser_unsupported("missing.m4a", "Apple Lossless audio file") is True


@needs_ffmpeg
def test_stream_transcode_is_cached(alac_file, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    ffmpeg = converter.find_ffmpeg("")
    real_convert = converter.convert
    calls = []
    monkeypatch.setattr(
        converter, "convert", lambda *a, **kw: calls.append(a) or real_convert(*a, **kw)
    )

    first = converter.transcode_for_stream(str(alac_file), str(cache), ffmpeg)
    second = converter.transcode_for_stream(str(alac_file), str(cache), ffmpeg)

    assert first == second and first.endswith(".flac")
    assert FLAC(first).info.sample_rate == 44100
    assert len(calls) == 1  # lần 2 dùng lại cache, không chạy ffmpeg


@needs_ffmpeg
def test_stream_transcode_concurrent_requests(alac_file, tmp_path, monkeypatch):
    """Trình duyệt gửi nhiều request Range cùng lúc cho bài chưa có cache: tất cả phải nhận
    cùng file, chỉ chuyển mã 1 lần (trước đây: 2 ffmpeg ghi cùng file .part -> WinError 32 -> 500)."""
    import threading

    cache = tmp_path / "cache"
    ffmpeg = converter.find_ffmpeg("")
    real_convert = converter.convert
    calls = []
    monkeypatch.setattr(
        converter, "convert", lambda *a, **kw: calls.append(a) or real_convert(*a, **kw)
    )
    results, errors = [], []
    start = threading.Barrier(4)

    def worker():
        start.wait()
        try:
            results.append(converter.transcode_for_stream(str(alac_file), str(cache), ffmpeg))
        except Exception as e:  # noqa: BLE001 — test cần ghi lại mọi lỗi
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(set(results)) == 1 and len(results) == 4
    assert len(calls) == 1
    assert FLAC(results[0]).info.sample_rate == 44100


def test_prune_cache_removes_oldest(tmp_path):
    for i, name in enumerate(["a.flac", "b.flac", "c.flac"]):
        f = tmp_path / name
        f.write_bytes(b"x" * 100)
        os.utime(f, (1000 + i, 1000 + i))

    converter.prune_cache(str(tmp_path), max_bytes=250)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.flac", "c.flac"]
