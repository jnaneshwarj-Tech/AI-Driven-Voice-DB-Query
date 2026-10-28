"""Derive the auth-page VTU emblem assets from the operator-supplied logo.

vtu-logo.jpg    : the original, used on a white plate (colours stay accurate).
vtu-emblem.png  : same emblem with the surrounding white removed, so it can sit
                  directly on the themed ground as a watermark without a white box.
"""
from PIL import Image, ImageDraw, ImageFilter
import os

SRC = r"C:\Users\manoj\Downloads\vtu logo.jpg"
PUB = r"C:\Users\manoj\Desktop\major\frontend\public"
MAGIC = (1, 2, 3)

im = Image.open(SRC).convert("RGB")
im.save(os.path.join(PUB, "vtu-logo.jpg"), quality=92)

filled = im.copy()
w, h = im.size
seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
         (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
for seed in seeds:
    ImageDraw.floodfill(filled, seed, MAGIC, thresh=34)

rgba = im.convert("RGBA")
px = rgba.load()
fp = filled.load()
for y in range(h):
    for x in range(w):
        if fp[x, y] == MAGIC:
            px[x, y] = (255, 255, 255, 0)

alpha = rgba.split()[3].filter(ImageFilter.GaussianBlur(0.6))
rgba.putalpha(alpha)
rgba.save(os.path.join(PUB, "vtu-emblem.png"), optimize=True)

for name in ("vtu-logo.jpg", "vtu-emblem.png"):
    p = os.path.join(PUB, name)
    print(name, os.path.getsize(p), Image.open(p).size, Image.open(p).mode)
