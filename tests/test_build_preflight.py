"""packaging/build.py: kiểm tra trước khi build (báo lỗi rõ thay vì build hỏng)."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_build():
    spec = importlib.util.spec_from_file_location("klmm_build", ROOT / "packaging" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = _load_build()


def test_missing_node_modules_is_reported(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="npm install"):
        build.check_node_modules(tmp_path)


def test_electron_without_binary_is_reported(tmp_path):
    (tmp_path / "node_modules" / "electron").mkdir(parents=True)
    (tmp_path / "node_modules" / "electron-builder").mkdir(parents=True)
    with pytest.raises(SystemExit, match="electron/install.js"):
        build.check_node_modules(tmp_path)


def test_installed_node_modules_pass(tmp_path):
    (tmp_path / "node_modules" / "electron" / "dist").mkdir(parents=True)
    (tmp_path / "node_modules" / "electron-builder").mkdir(parents=True)
    build.check_node_modules(tmp_path)


def test_shared_ffmpeg_build_is_detected(tmp_path):
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"MZ")
    assert build.is_shared_ffmpeg(exe) is False
    (tmp_path / "avcodec-62.dll").write_bytes(b"MZ")
    assert build.is_shared_ffmpeg(exe) is True


def test_stage_ffmpeg_refuses_shared_build(tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "ffmpeg.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    (exe.parent / "avutil-60.dll").write_bytes(b"MZ")
    monkeypatch.setattr(build, "VENDOR_FFMPEG", tmp_path / "missing.exe")
    monkeypatch.setattr(build, "OUT", tmp_path / "out")
    monkeypatch.setenv("KLMM_FFMPEG_SRC", str(exe))
    with pytest.raises(SystemExit, match="fetch_ffmpeg.py"):
        build.stage_ffmpeg()
