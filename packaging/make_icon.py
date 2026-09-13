# -*- coding: utf-8 -*-
"""生成应用图标 assets/app.ico（深色圆角底 + 工作台蓝星形，与托盘图标同一视觉）。"""

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# 基于 128 坐标的星形轮廓（与 tray.py 托盘图标一致）
STAR_128 = [(64, 16), (72, 46), (104, 54), (72, 62), (64, 96), (56, 62), (24, 54), (56, 46)]
BG = (16, 23, 38, 255)        # surface 深底
ACCENT = (74, 138, 244, 255)  # 主色工作台蓝
CORE = (240, 242, 245, 255)   # 星心留白


def build(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=max(2, size // 7),
        fill=BG, outline=ACCENT, width=max(1, size // 32),
    )
    scale = size / 128
    d.polygon([(x * scale, y * scale) for x, y in STAR_128], fill=ACCENT)
    d.ellipse(
        [54 * scale, 42 * scale, 74 * scale, 62 * scale], fill=CORE,
    )
    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    base = build(256)
    base.save(
        ASSETS / "app.ico", format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"icon written: {ASSETS / 'app.ico'}")


if __name__ == "__main__":
    main()
