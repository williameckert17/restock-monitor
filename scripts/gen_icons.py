#!/usr/bin/env python3
"""
Generate all platform icon files from the Pokepad SVG source.

Usage:
    python3 scripts/gen_icons.py

Outputs (all under web/static/icons/):
    pokepad-1024.png   — master PNG (1024×1024)
    pokepad-512.png    — web-app icon
    favicon.ico        — browser favicon (16, 32, 48 embedded)
    pokepad.ico        — Windows app icon (16, 32, 48, 256 embedded)
    pokepad.icns       — macOS app icon (via iconutil)

Requires: Pillow  (pip install Pillow)
macOS only for .icns: uses /usr/bin/iconutil
"""
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")

ROOT    = Path(__file__).parent.parent
SVG     = ROOT / "web/static/icons/pokepad.svg"
OUTDIR  = ROOT / "web/static/icons"
OUTDIR.mkdir(parents=True, exist_ok=True)

# ── Pixel-accurate SVG renderer ───────────────────────────────────────────────
# The SVG is a 20×20 pixel-art grid.  We scale each rect by (size/20),
# snapping to integers so pixels stay crisp at every output size.

SVG_NS = "http://www.w3.org/2000/svg"

def _hex(color: str):
    c = color.lstrip("#")
    return tuple(int(c[i:i+2], 16) for i in (0, 2, 4)) + (255,)

def render(size: int) -> Image.Image:
    scale  = size / 20
    img    = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw   = ImageDraw.Draw(img)
    tree   = ET.parse(SVG)
    for elem in tree.iter(f"{{{SVG_NS}}}rect"):
        fill = elem.get("fill", "none")
        if fill in ("none", ""):
            continue
        x  = round(float(elem.get("x",      0)) * scale)
        y  = round(float(elem.get("y",      0)) * scale)
        x2 = round((float(elem.get("x", 0)) + float(elem.get("width",  0))) * scale)
        y2 = round((float(elem.get("y", 0)) + float(elem.get("height", 0))) * scale)
        if x2 > x and y2 > y:
            draw.rectangle([x, y, x2 - 1, y2 - 1], fill=_hex(fill))
    return img

# ── Render master sizes ───────────────────────────────────────────────────────

print("Rendering master PNGs…")
masters = {}
for sz in (16, 32, 48, 64, 128, 256, 512, 1024):
    masters[sz] = render(sz)
    print(f"  {sz}×{sz}")

# ── Save named outputs ────────────────────────────────────────────────────────

masters[1024].save(OUTDIR / "pokepad-1024.png")
masters[512].save(OUTDIR / "pokepad-512.png")
print("Saved pokepad-1024.png, pokepad-512.png")

# ── favicon.ico — 16, 32, 48 ─────────────────────────────────────────────────

favicon_path = OUTDIR / "favicon.ico"
masters[16].save(
    favicon_path,
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48)],
)
print("Saved favicon.ico (16, 32, 48)")

# ── pokepad.ico — 16, 32, 48, 256 ────────────────────────────────────────────

ico_path = OUTDIR / "pokepad.ico"
masters[16].save(
    ico_path,
    format="ICO",
    sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
)
print("Saved pokepad.ico (16, 32, 48, 256)")

# ── pokepad.icns — macOS (iconutil) ──────────────────────────────────────────

if shutil.which("iconutil"):
    icns_sizes = {
        "icon_16x16":        16,
        "icon_16x16@2x":     32,
        "icon_32x32":        32,
        "icon_32x32@2x":     64,
        "icon_128x128":      128,
        "icon_128x128@2x":   256,
        "icon_256x256":      256,
        "icon_256x256@2x":   512,
        "icon_512x512":      512,
        "icon_512x512@2x":   1024,
    }
    with tempfile.TemporaryDirectory(suffix=".iconset") as iconset:
        for name, sz in icns_sizes.items():
            masters[sz].save(Path(iconset) / f"{name}.png")
        result = subprocess.run(
            ["iconutil", "-c", "icns", "-o", str(OUTDIR / "pokepad.icns"), iconset],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("Saved pokepad.icns")
        else:
            print(f"iconutil error: {result.stderr.strip()}")
else:
    print("iconutil not found — skipping .icns (macOS only)")

print("\nDone.  All icons in:", OUTDIR)
