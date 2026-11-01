"""Tile stills into a labeled contact sheet: sheet.py out.png img1 label1 img2 label2 ..."""
import sys
from PIL import Image, ImageDraw

out, rest = sys.argv[1], sys.argv[2:]
pairs = list(zip(rest[::2], rest[1::2]))
W = 360
ims = []
for p, lab in pairs:
    im = Image.open(p).convert("RGB")
    im = im.resize((W, int(im.height * W / im.width)))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 22], fill=(0, 0, 0))
    d.text((6, 4), lab, fill=(255, 255, 255))
    ims.append(im)
cols = min(4, len(ims))
rows = (len(ims) + cols - 1) // cols
H = ims[0].height
sheet = Image.new("RGB", (cols * W, rows * H), (20, 20, 20))
for i, im in enumerate(ims):
    sheet.paste(im, ((i % cols) * W, (i // cols) * H))
sheet.save(out)
print(out)
