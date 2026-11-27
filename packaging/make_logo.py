"""Vẽ logo / icon app của KL Music Manager (tác phẩm của project, cùng giấy phép GPL).

Ô vuông bo góc nền gradient (màu accent của giao diện) + cặp nốt móc đơn màu trắng.
Vẽ ở độ phân giải cao rồi thu nhỏ (LANCZOS) để khử răng cưa. Muốn đổi màu/hình:
sửa hằng số bên dưới rồi chạy `python packaging/make_logo.py`.

Xuất:
  static/icons/app-icon.png     256x256 (icon cửa sổ, About, favicon)
  static/icons/app-icon-32.png  32x32   (menu, header)
  packaging/icon-512.png        512x512 (electron-builder tạo .ico/.icns từ file này)
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 2048  # canvas vẽ

TOP_LEFT: Tuple[int, int, int] = (0x38, 0xBD, 0xF8)  # sky-400
BOTTOM_RIGHT: Tuple[int, int, int] = (0x4F, 0x46, 0xE5)  # indigo-600
NOTE = (255, 255, 255, 255)


def gradient() -> Image.Image:
    """Gradient chéo từ góc trên-trái tới dưới-phải."""
    small = Image.new("RGB", (256, 256))
    px = small.load()
    for y in range(256):
        for x in range(256):
            t = (x + y) / 510
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP_LEFT, BOTTOM_RIGHT))
    return small.resize((S, S), Image.BICUBIC).convert("RGBA")


def rounded_mask(margin: int, radius: int) -> Image.Image:
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (margin, margin, S - margin, S - margin), radius=radius, fill=255
    )
    return mask


def note_head(cx: int, cy: int, rx: int, ry: int, angle: float) -> Image.Image:
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=NOTE)
    return layer.rotate(angle, center=(cx, cy), resample=Image.BICUBIC)


def draw_notes() -> Image.Image:
    """Cặp nốt móc đơn nối bằng thanh nghiêng."""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    stem_w = 92
    left_x, right_x = 840, 1440  # mép phải của thân nốt
    left_bottom, right_bottom = 1450, 1330
    beam_top_left, beam_top_right = 560, 440
    beam_h = 210
    d = ImageDraw.Draw(layer)
    # thân nốt
    d.rectangle((left_x - stem_w, beam_top_left + 40, left_x, left_bottom), fill=NOTE)
    d.rectangle((right_x - stem_w, beam_top_right + 40, right_x, right_bottom), fill=NOTE)
    # thanh nối (hình bình hành)
    d.polygon(
        [
            (left_x - stem_w, beam_top_left),
            (right_x, beam_top_right),
            (right_x, beam_top_right + beam_h),
            (left_x - stem_w, beam_top_left + beam_h),
        ],
        fill=NOTE,
    )
    # đầu nốt (elip nghiêng)
    for x, y in ((left_x - 150, left_bottom), (right_x - 150, right_bottom)):
        layer = Image.alpha_composite(layer, note_head(x, y, 205, 150, 25))
    return layer


def render() -> Image.Image:
    margin, radius = 96, 430
    mask = rounded_mask(margin, radius)
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # bóng đổ nhẹ phía dưới
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(mask.point(lambda v: v * 0.35))
    shadow = shadow.transform((S, S), Image.AFFINE, (1, 0, 0, 0, 1, -24)).filter(
        ImageFilter.GaussianBlur(28)
    )
    base = Image.alpha_composite(base, shadow)
    tile = gradient()
    tile.putalpha(mask)
    base = Image.alpha_composite(base, tile)
    notes = draw_notes()
    note_shadow = Image.new("RGBA", (S, S), (20, 20, 60, 0))
    note_shadow.putalpha(notes.getchannel("A").point(lambda v: v * 0.28))
    note_shadow = note_shadow.transform((S, S), Image.AFFINE, (1, 0, -10, 0, 1, -18)).filter(
        ImageFilter.GaussianBlur(18)
    )
    base = Image.alpha_composite(base, note_shadow)
    return Image.alpha_composite(base, notes)


def main() -> None:
    img = render()
    icons = ROOT / "static" / "icons"
    icons.mkdir(parents=True, exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(icons / "app-icon.png", optimize=True)
    img.resize((32, 32), Image.LANCZOS).save(icons / "app-icon-32.png", optimize=True)
    img.resize((512, 512), Image.LANCZOS).save(ROOT / "packaging" / "icon-512.png", optimize=True)


if __name__ == "__main__":
    main()
