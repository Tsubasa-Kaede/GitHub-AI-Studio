# -*- coding: utf-8 -*-
"""生成 GitHub Social Preview 图（1280x640，与应用同一终端视觉）。"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "social-preview.png"

BG = (7, 11, 18, 255)
PANEL = (16, 23, 38, 255)
BORDER = (74, 138, 244, 90)
ACCENT = (74, 138, 244, 255)
TEXT = (232, 236, 245, 255)
TEXT_2 = (166, 176, 200, 255)
TEXT_3 = (110, 122, 148, 255)
STAR = (240, 136, 62, 255)

W, H = 1280, 640


def font(name: str, size: int):
    return ImageFont.truetype(name, size)


def main() -> None:
    img = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(img)

    yahei = r"C:\Windows\Fonts\msyh.ttc"
    yahei_bd = r"C:\Windows\Fonts\msyhbd.ttc"
    mono = r"C:\Windows\Fonts\consola.ttf"

    # 右侧抽象看板（三层卡片 + 列表行，示意 Master-Detail）
    px, py = 760, 96
    d.rounded_rectangle([px, py, px + 440, py + 448], 18, fill=PANEL, outline=BORDER, width=2)
    for row in range(5):
        y = py + 36 + row * 84
        d.rounded_rectangle([px + 28, y, px + 200, y + 52], 9, fill=(24, 33, 55, 255))
        d.ellipse([px + 44, y + 21, px + 54, y + 31], fill=ACCENT)
        d.rounded_rectangle([px + 224, y + 6, px + 412, y + 46], 9, fill=(13, 19, 33, 255),
                            outline=(48, 54, 61, 255), width=1)
    d.rounded_rectangle([px + 224, py + 130, px + 412, py + 300], 9, fill=(13, 19, 33, 255),
                        outline=(48, 54, 61, 255), width=1)
    d.text((px + 244, py + 156), "定位", font=font(yahei_bd, 22), fill=TEXT)
    d.text((px + 244, py + 196), "亮点", font=font(yahei_bd, 22), fill=TEXT)
    d.text((px + 366, py + 152), "★ 165.3k", font=font(yahei_bd, 22), fill=STAR)

    # 左侧品牌区
    d.rounded_rectangle([96, 96, 164, 164], 18, fill=PANEL, outline=ACCENT, width=2)
    # 终端风箭头：矢量绘制，避免字体缺字形
    d.line([(120, 114), (142, 130), (120, 146)], fill=ACCENT, width=7, joint="curve")
    d.text((184, 100), "GitHub-AI-Studio", font=font(yahei_bd, 46), fill=TEXT)
    d.text((188, 158), "ghai --studio · 本地 GitHub 智能化管理控制台",
           font=font(yahei, 20), fill=TEXT_3)

    d.text((100, 240), "每天 30 秒，", font=font(yahei_bd, 56), fill=TEXT)
    d.text((100, 308), "AI 帮你读完 GitHub 热榜", font=font(yahei_bd, 56), fill=ACCENT)

    # 三个特性 chip
    chips = ["免安装 EXE", "中文研读看板", "锁屏推送"]
    x = 100
    for c in chips:
        w = int(d.textlength(c, font=font(yahei, 26))) + 44
        d.rounded_rectangle([x, 420, x + w, 472], 9, fill=(24, 33, 55, 255),
                            outline=(151, 167, 201, 60), width=1)
        d.text((x + 22, 430), c, font=font(yahei, 26), fill=TEXT_2)
        x += w + 16

    d.text((100, 540), "github.com/Tsubasa-Kaede/GitHub-AI-Studio",
           font=font(mono, 24), fill=TEXT_3)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "PNG")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
