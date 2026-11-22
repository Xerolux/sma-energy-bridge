"""Generate the app icon (256x256) and logo (250x100) as PNG files.

Pure standard library (zlib + struct), no image tooling required. Run from the
repository root:

    python scripts/make_icons.py

The motif is an abstract energy bridge: a white bridge deck with two pillars
over a dark navy background and a yellow lightning bolt as the energy payload.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

NAVY = (18, 38, 63)
WHITE = (240, 244, 248)
YELLOW = (247, 197, 46)


class Canvas:
    def __init__(self, width: int, height: int, background: tuple[int, int, int]):
        self.width = width
        self.height = height
        self.pixels = [[background] * width for _ in range(height)]

    def rect(self, x0: int, y0: int, x1: int, y1: int,
             color: tuple[int, int, int]) -> None:
        for y in range(max(0, y0), min(self.height, y1)):
            for x in range(max(0, x0), min(self.width, x1)):
                self.pixels[y][x] = color

    def rounded(self, x0: int, y0: int, x1: int, y1: int, radius: int,
                color: tuple[int, int, int]) -> None:
        self.rect(x0 + radius, y0, x1 - radius, y1, color)
        self.rect(x0, y0 + radius, x1, y1 - radius, color)
        for dy in range(radius):
            for dx in range(radius):
                if dx * dx + dy * dy <= radius * radius:
                    for cx, cy in ((x0 + radius, y0 + radius),
                                   (x1 - 1 - radius, y0 + radius),
                                   (x0 + radius, y1 - 1 - radius),
                                   (x1 - 1 - radius, y1 - 1 - radius)):
                        self.pixels[cy + dy][cx + dx] = color

    def polygon(self, points: list[tuple[int, int]],
                color: tuple[int, int, int]) -> None:
        ys = [p[1] for p in points]
        for y in range(max(0, min(ys)), min(self.height, max(ys) + 1)):
            crossings: list[float] = []
            for index, (x0, y0) in enumerate(points):
                x1, y1 = points[(index + 1) % len(points)]
                if y0 == y1:
                    continue
                if y0 <= y < y1 or y1 <= y < y0:
                    crossings.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            crossings.sort()
            for even, odd in zip(crossings[::2], crossings[1::2], strict=False):
                self.rect(round(even), y, round(odd) + 1, y + 1, color)

    def png(self, path: Path) -> None:
        raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel)
                       for row in self.pixels)

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (struct.pack(">I", len(data)) + tag + data
                    + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                         + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
        print(f"wrote {path} ({path.stat().st_size} bytes)")


def draw_bridge(canvas: Canvas, deck_y: int, deck_h: int, left: int, right: int,
                pillar_w: int, pillar_h: int) -> None:
    canvas.rect(left, deck_y, right, deck_y + deck_h, WHITE)
    first_pillar = left + (right - left) // 5
    second_pillar = right - (right - left) // 5 - pillar_w
    canvas.rect(first_pillar, deck_y + deck_h, first_pillar + pillar_w,
                deck_y + deck_h + pillar_h, WHITE)
    canvas.rect(second_pillar, deck_y + deck_h, second_pillar + pillar_w,
                deck_y + deck_h + pillar_h, WHITE)


def main() -> None:
    addon_dir = Path(__file__).resolve().parents[1] / "sma_energy_bridge"

    icon = Canvas(256, 256, NAVY)
    icon.rounded(0, 0, 256, 256, 48, NAVY)
    draw_bridge(icon, deck_y=150, deck_h=14, left=36, right=220, pillar_w=18, pillar_h=62)
    icon.polygon([(148, 34), (110, 124), (136, 124), (118, 186),
                  (176, 104), (146, 104), (168, 34)], YELLOW)
    icon.png(addon_dir / "icon.png")

    logo = Canvas(250, 100, NAVY)
    logo.rounded(0, 0, 250, 100, 18, NAVY)
    draw_bridge(logo, deck_y=56, deck_h=8, left=16, right=160, pillar_w=10, pillar_h=30)
    logo.polygon([(118, 12), (92, 58), (108, 58), (96, 92),
                  (132, 48), (114, 48), (128, 12)], YELLOW)
    logo.png(addon_dir / "logo.png")


if __name__ == "__main__":
    main()
