"""Render the Home Assistant PNG assets with Pillow 12.3.0.

Install the artwork dependency with `python -m pip install Pillow==12.3.0`
and run `python scripts/make_icons.py` from the repository root.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCALE = 4
INK = "#edfdf8"
MINT = "#85ffe2"


def scaled(box: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(point * SCALE for point in box)


def panel(width: int, height: int, radius: int) -> Image.Image:
    size = (width * SCALE, height * SCALE)
    canvas = Image.new("RGBA", size)
    draw = ImageDraw.Draw(canvas)
    top, bottom = (14, 47, 49), (8, 24, 34)
    for y in range(size[1]):
        fraction = y / (size[1] - 1)
        color = tuple(round(a + (b - a) * fraction) for a, b in zip(top, bottom, strict=True))
        draw.line((0, y, size[0] - 1, y), fill=(*color, 255))
    mask = Image.new("L", size)
    frame = (0, 0, size[0] - 1, size[1] - 1)
    ImageDraw.Draw(mask).rounded_rectangle(frame, radius * SCALE, fill=255)
    canvas.putalpha(mask)
    draw.rounded_rectangle(scaled((1, 1, width - 1, height - 1)), radius * SCALE,
                           outline="#245458", width=SCALE)
    return canvas


def bridge(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    """A signal trace joins both sides of an electrical bridge."""
    unit = size * SCALE / 100

    def points(*coordinates: tuple[int, int]) -> list[tuple[int, int]]:
        return [(round(x * SCALE + u * unit), round(y * SCALE + v * unit))
                for u, v in coordinates]

    for u in (18, 82):
        draw.rounded_rectangle(points((u - 3, 42), (u + 3, 76)),
                               radius=round(3 * unit), fill="#b0d9d8")
        draw.rounded_rectangle(points((u - 11, 73), (u + 11, 78)),
                               radius=round(2 * unit), fill="#5e969a")

    signal = points((11, 48), (32, 48), (42, 31), (52, 63), (64, 48), (89, 48))
    line_width = round(6 * unit)
    draw.line(signal, fill=MINT, width=line_width, joint="curve")
    for endpoint in (signal[0], signal[-1]):
        cx, cy = endpoint
        radius = round(6 * unit)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=MINT)


def finish(canvas: Image.Image, target: Path) -> None:
    size = (canvas.width // SCALE, canvas.height // SCALE)
    canvas.resize(size, Image.Resampling.LANCZOS).save(target, optimize=True)
    print(f"wrote {target.name} ({size[0]} × {size[1]})")


def main() -> None:
    addon = Path(__file__).resolve().parents[1] / "sma_energy_bridge"
    icon = panel(256, 256, 55)
    bridge(ImageDraw.Draw(icon), 22, 17, 212)
    finish(icon, addon / "icon.png")

    logo = panel(250, 100, 19)
    draw = ImageDraw.Draw(logo)
    bridge(draw, 8, 8, 83)
    draw.line(scaled((93, 26, 93, 74)), fill="#34666a", width=SCALE)
    eyebrow = ImageFont.load_default(size=13 * SCALE)
    name = ImageFont.load_default(size=21 * SCALE)
    draw.text(scaled((107, 38)), "SMA", font=eyebrow, fill=MINT, anchor="ls")
    draw.text(scaled((106, 65)), "Energy Bridge", font=name, fill=INK, anchor="ls",
              stroke_width=1, stroke_fill=INK)
    finish(logo, addon / "logo.png")


if __name__ == "__main__":
    main()
