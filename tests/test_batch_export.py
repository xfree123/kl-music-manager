"""Export nhiều bài (trang Manage): thư mục đích, cách xếp thư mục, thư mục con, bỏ qua file đã có,
và đặt tên file an toàn khi nhiều bài export song song."""

import importlib
import json
import os
import sys
import threading
from pathlib import Path

import pytest

import converter
from conftest import FFMPEG, make_audio, needs_ffmpeg

pytestmark = needs_ffmpeg


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    import pygpod
    from pygpod.device.mountpoint import init_ipod

    root = tmp_path_factory.mktemp("batch")
    data_dir, ipod_dir = root / "data", root / "ipod"
    data_dir.mkdir()
    ipod_dir.mkdir()
    init_ipod(str(ipod_dir), model="classic_6g", music_dirs=2)
    db = pygpod.Database(str(ipod_dir))
    ids = {}
    for name, tags in {
        "a": {"title": "Mưa", "artist": "Hà Anh: Tuấn", "album": "Live / 2020"},
        "b": {"title": "Mưa", "artist": "Hà Anh: Tuấn", "album": "Studio"},  # trùng tên file
        "c": {"title": "Nắng", "artist": "", "album": ""},
    }.items():
        ids[name] = db.add_track(str(make_audio(root / f"{name}.mp3", tags))).track_id
    db.save()
    (data_dir / "config.json").write_text(
        json.dumps(
            {
                "ipod_path": str(ipod_dir),
                "export_dir": str(root / "default-export"),
                "ffmpeg_path": FFMPEG,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    old = os.environ.get("KLMM_DATA_DIR")
    os.environ["KLMM_DATA_DIR"] = str(data_dir)
    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    yield {"client": app_module.app.test_client(), "ids": ids, "root": root, "app": app_module}
    sys.modules.pop("app", None)
    if old is None:
        os.environ.pop("KLMM_DATA_DIR", None)
    else:
        os.environ["KLMM_DATA_DIR"] = old


def export(env, key, **body):
    return env["client"].post(
        f"/api/tracks/export/{env['ids'][key]}", json={"format": "original", **body}
    )


def test_safe_component():
    assert converter.safe_component('Hà Anh: Tuấn / "Live"?') == "Hà Anh_ Tuấn _ _Live__"
    for bad in ("", "  ", ".", "..", "...", None):
        assert converter.safe_component(bad) == "Unknown"
    assert converter.safe_component(bad, "Unknown Album") == "Unknown Album"
    assert converter.safe_component("x" * 300) == "x" * 120
    assert converter.safe_component("Tên. ") == "Tên"


def test_artist_album_layout_with_subfolder_and_custom_dest(env, tmp_path):
    res = export(env, "a", dest_dir=str(tmp_path), layout="artist_album", subfolder="Yêu thích")
    assert res.status_code == 200, res.get_json()
    data = res.get_json()
    assert data["success"] is True and data["skipped"] is False
    expected = tmp_path / "Yêu thích" / "Hà Anh_ Tuấn" / "Live _ 2020" / "Hà Anh_ Tuấn - Mưa.mp3"
    assert Path(data["path"]) == expected and expected.is_file()
    # Thư mục gốc của lần export (cho nút Show Folder), không phải thư mục album của bài cuối
    assert Path(data["root"]) == tmp_path / "Yêu thích"


def test_missing_tags_use_unknown_folders(env, tmp_path):
    data = export(env, "c", dest_dir=str(tmp_path), layout="artist_album").get_json()
    rel = Path(data["path"]).relative_to(tmp_path)
    assert rel.parts[:2] == ("Unknown Artist", "Unknown Album")


def test_subfolder_cannot_escape_destination(env, tmp_path):
    for sub in ("..", "../..", "C:\\Windows", "/etc"):
        data = export(env, "a", dest_dir=str(tmp_path / "out"), subfolder=sub).get_json()
        path = Path(data["path"]).resolve()
        assert (tmp_path / "out").resolve() in path.parents, (sub, path)


def test_skip_existing(env, tmp_path):
    first = export(env, "a", dest_dir=str(tmp_path), skip_existing=True).get_json()
    second = export(env, "a", dest_dir=str(tmp_path), skip_existing=True).get_json()
    assert second["success"] is True and second["skipped"] is True
    assert second["path"] == first["path"] and Path(second["root"]) == tmp_path
    assert len(list(tmp_path.iterdir())) == 1  # không sinh "(2)"
    third = export(env, "a", dest_dir=str(tmp_path)).get_json()  # mặc định: không bỏ qua
    assert third["skipped"] is False and third["path"].endswith(" (2).mp3")


def test_bad_layout_400(env, tmp_path):
    assert export(env, "a", dest_dir=str(tmp_path), layout="genre").status_code == 400


def test_old_style_call_unchanged(env):
    data = export(env, "a").get_json()
    path = Path(data["path"])
    assert path.parent == env["root"] / "default-export" and data["skipped"] is False
    assert Path(data["root"]) == env["root"] / "default-export"


def test_parallel_exports_with_same_name_do_not_overwrite(env, tmp_path):
    manager = env["app"].manager
    results, errors = [], []
    barrier = threading.Barrier(2)

    def run(key, fmt):
        try:
            barrier.wait()
            results.append(manager.export_track_to(env["ids"][key], fmt, {}, str(tmp_path))["path"])
        except Exception as e:  # noqa: BLE001 - báo lỗi luồng phụ về luồng test
            errors.append(e)

    threads = [threading.Thread(target=run, args=(k, "mp3")) for k in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(set(results)) == 2 and all(Path(p).stat().st_size > 0 for p in results)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "Hà Anh_ Tuấn - Mưa (2).mp3",
        "Hà Anh_ Tuấn - Mưa.mp3",
    ]
