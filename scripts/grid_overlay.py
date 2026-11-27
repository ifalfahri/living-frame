#!/usr/bin/env python3
"""
Draw a crisp normalized [0.0..1.0] coordinate grid over any input image so an
agent or developer can read exact landmark coordinates (eyes, pivots, light
sources, cloth roots, foreground cutouts) before slicing 2.5D depth plates.

Usage:
    python3 scripts/grid_overlay.py path/to/source.jpg [path/to/grid.png]
"""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageDraw


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 grid_overlay.py <input_image> [output_grid.png]")
        sys.exit(1)

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) >= 3 else src.with_name(f"{src.stem}_grid.png")

    im = Image.open(src).convert("RGB")
    w, h = im.size
    draw = ImageDraw.Draw(im)

    for i in range(1, 20):
        x = int(w * i / 20)
        color = (255, 240, 60) if i % 2 == 0 else (180, 180, 180)
        draw.line([(x, 0), (x, h)], fill=color, width=1)
        if i % 2 == 0:
            draw.rectangle([(x + 1, 2), (x + 28, 16)], fill=(12, 14, 20))
            draw.text((x + 3, 3), f"{i / 20:.1f}", fill=(255, 240, 60))

    for j in range(1, 20):
        y = int(h * j / 20)
        color = (255, 240, 60) if j % 2 == 0 else (180, 180, 180)
        draw.line([(0, y), (w, y)], fill=color, width=1)
        if j % 2 == 0:
            draw.rectangle([(2, y + 1), (28, y + 15)], fill=(12, 14, 20))
            draw.text((4, y + 2), f"{j / 20:.1f}", fill=(255, 240, 60))

    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst)
    print(f"Saved coordinate grid ({w}x{h}, aspect={w/h:.4f}) -> {dst}")


if __name__ == "__main__":
    main()
