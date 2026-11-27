"""Tài nguyên giao diện: icon, logo, font đều là bản tự do (Lucide ISC, logo tự vẽ, font OFL).

Không còn icon kế thừa từ bản gốc; font đóng kèm phải đủ ký tự tiếng Việt có dấu.
"""

import re
import struct
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
ICONS = STATIC / "icons"

ALLOWED_ICON_FILES = {"sprite.svg", "LICENSE-lucide.txt", "app-icon.png", "app-icon-32.png"}

VIETNAMESE = "ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ"
VIETNAMESE = VIETNAMESE + VIETNAMESE.upper()


def _frontend_sources():
    files = [STATIC / "index.html", STATIC / "style.css", STATIC / "app.js"]
    files += sorted((STATIC / "js").glob("*.js"))
    files += [STATIC / "help" / "index.html"]
    files += sorted((ROOT / "electron").glob("*.js"))
    files += [ROOT / "packaging" / "build.py", ROOT / "package.json"]
    return [f for f in files if f.exists()]


def test_icon_folder_has_only_free_assets():
    present = {p.name for p in ICONS.iterdir()}
    assert "sprite.svg" in present
    assert present <= ALLOWED_ICON_FILES, f"file icon lạ/cũ: {sorted(present - ALLOWED_ICON_FILES)}"


def test_no_reference_to_old_png_icons():
    bad = []
    for f in _frontend_sources():
        for m in re.finditer(r"icons[/\\'\", ]+([\w.-]+\.png)", f.read_text(encoding="utf-8")):
            if m.group(1) not in ALLOWED_ICON_FILES:
                bad.append(f"{f.relative_to(ROOT)}: {m.group(1)}")
    assert not bad, bad


def _sprite_symbols() -> Set[str]:
    return set(
        re.findall(r'<symbol[^>]*\bid="([a-z0-9-]+)"', (ICONS / "sprite.svg").read_text("utf-8"))
    )


def _used_icons() -> Set[str]:
    used: Set[str] = set()
    for f in _frontend_sources():
        text = f.read_text(encoding="utf-8")
        used.update(re.findall(r"sprite\.svg#([a-z0-9-]+)", text))
        for line in text.splitlines():
            m = re.search(r"setIcon\([^,]+,(.*)", line)
            if m:  # tên icon nằm sau tham số đầu (phần tử svg)
                used.update(re.findall(r"'([a-z0-9-]+)'", m.group(1)))
    return used


def test_every_used_icon_exists_in_sprite():
    used = _used_icons()
    assert len(used) >= 20, used
    missing = used - _sprite_symbols()
    assert not missing, f"icon chưa có trong sprite: {sorted(missing)}"


def test_sprite_symbols_use_current_color():
    text = (ICONS / "sprite.svg").read_text("utf-8")
    assert 'stroke="currentColor"' in text
    assert "<script" not in text


def _cmap(path: Path) -> Set[int]:
    data = path.read_bytes()
    num = struct.unpack(">H", data[4:6])[0]
    tables = {}
    for i in range(num):
        rec = data[12 + 16 * i : 28 + 16 * i]
        tables[rec[:4].decode("latin-1")] = struct.unpack(">I", rec[8:12])[0]
    off = tables["cmap"]
    count = struct.unpack(">H", data[off + 2 : off + 4])[0]
    cps: Set[int] = set()
    for i in range(count):
        sub = off + struct.unpack(">I", data[off + 8 + 8 * i : off + 12 + 8 * i])[0]
        fmt = struct.unpack(">H", data[sub : sub + 2])[0]
        if fmt == 4:
            segx2 = struct.unpack(">H", data[sub + 6 : sub + 8])[0]
            n = segx2 // 2
            ends = struct.unpack(f">{n}H", data[sub + 14 : sub + 14 + segx2])
            starts = struct.unpack(f">{n}H", data[sub + 16 + segx2 : sub + 16 + 2 * segx2])
            for a, b in zip(starts, ends):
                cps.update(range(a, b + 1))
        elif fmt == 12:
            groups = struct.unpack(">I", data[sub + 12 : sub + 16])[0]
            for j in range(groups):
                a, b, _ = struct.unpack(">III", data[sub + 16 + 12 * j : sub + 28 + 12 * j])
                cps.update(range(a, b + 1))
    return cps


def _bundled_font() -> Path:
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    m = re.search(r"@font-face\s*{[^}]*url\('([^']+)'\)", css)
    assert m, "style.css không có @font-face"
    return STATIC / m.group(1)


def test_bundled_font_covers_vietnamese():
    font = _bundled_font()
    assert font.exists(), font
    cps = _cmap(font)
    missing = [c for c in VIETNAMESE if ord(c) not in cps]
    assert not missing, f"{font.name} thiếu {len(missing)} ký tự tiếng Việt: {''.join(missing)}"


def test_font_license_shipped_and_outfit_gone():
    assert (STATIC / "fonts" / "OFL.txt").exists()
    for f in [STATIC / "style.css", STATIC / "index.html"]:
        assert "Outfit" not in f.read_text(encoding="utf-8"), f


def test_app_icon_is_large_enough():
    from PIL import Image

    with Image.open(ICONS / "app-icon.png") as im:
        assert im.size == (256, 256) and im.mode == "RGBA"
    with Image.open(ROOT / "packaging" / "icon-512.png") as im:
        assert im.size == (512, 512)
