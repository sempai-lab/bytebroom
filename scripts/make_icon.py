"""Draw the ByteBroom icon (src/bytebroom/assets/bytebroom.ico + .png).

Usage:  python scripts/make_icon.py      (needs Pillow)
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "bytebroom" / "assets"
S = 1024  # draw big, then downscale for smooth edges


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def main() -> None:
    # diagonal gradient background (indigo -> teal)
    top, bottom = (79, 70, 229), (13, 148, 136)
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(S):
        for x in range(S):
            px[x, y] = lerp(top, bottom, (x + y) / (2 * S - 2))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=220, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    white, soft = (255, 255, 255, 255), (255, 255, 255, 170)

    # handle
    d.line((735, 215, 470, 545), fill=white, width=64)
    d.ellipse((703, 183, 767, 247), fill=white)
    # binding
    d.polygon([(410, 500), (520, 590), (480, 640), (370, 550)], fill=white)
    # bristles (fan)
    d.polygon([(372, 560), (478, 646), (360, 860), (215, 745)], fill=white)
    for i in range(1, 5):  # bristle gaps
        t = i / 5
        a = lerp((372, 560), (478, 646), t)
        b = lerp((215, 745), (360, 860), t)
        d.line((a, b), fill=lerp(top, bottom, 0.75) + (255,), width=10)

    # sparkles ("clean bytes")
    def sparkle(cx, cy, r, color):
        k = r // 4
        d.polygon([(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
                   (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], fill=color)

    sparkle(705, 640, 95, white)
    sparkle(820, 800, 55, soft)
    sparkle(590, 790, 42, soft)

    OUT.mkdir(parents=True, exist_ok=True)
    big = img.resize((256, 256), Image.LANCZOS)
    big.save(OUT / "bytebroom.png")
    big.save(OUT / "bytebroom.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                           (64, 64), (128, 128), (256, 256)])
    print(f"wrote {OUT / 'bytebroom.ico'}")


if __name__ == "__main__":
    main()
