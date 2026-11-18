"""Maakt alle Android-iconen uit app-icon.png (vierkant, liefst 512x512 of groter)."""
import pathlib, sys
from PIL import Image, ImageDraw
root = pathlib.Path(__file__).resolve().parent
src = Image.open(sys.argv[1] if len(sys.argv) > 1 else root.parent / "app-icon.png").convert("RGBA")
w, h = src.size
side = min(w, h)
src = src.crop(((w - side) // 2, (h - side) // 2, (w - side) // 2 + side, (h - side) // 2 + side))
res = root / "app/src/main/res"
legacy = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
for d, px in legacy.items():
    out = res / f"mipmap-{d}"
    out.mkdir(parents=True, exist_ok=True)
    sq = src.resize((px, px), Image.LANCZOS)
    sq.save(out / "ic_launcher.png")
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, px - 1, px - 1), fill=255)
    rnd = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    rnd.paste(sq, (0, 0), mask)
    rnd.save(out / "ic_launcher_round.png")
    # adaptieve voorgrond: 108dp canvas, icoon in de veilige zone van 72dp
    fg = round(px * 108 / 48)
    inner = round(fg * 72 / 108)
    canvas = Image.new("RGBA", (fg, fg), (0, 0, 0, 0))
    canvas.paste(src.resize((inner, inner), Image.LANCZOS), ((fg - inner) // 2, (fg - inner) // 2))
    canvas.save(out / "ic_launcher_foreground.png")
# achtergrondkleur van het adaptieve icoon = kleur linksboven in jouw afbeelding
r, g, b, *_ = src.getpixel((2, 2))
(res / "values").mkdir(parents=True, exist_ok=True)
(res / "values/ic_bg.xml").write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<resources><color name="ic_bg">#{r:02X}{g:02X}{b:02X}</color></resources>\n')
any_ = res / "mipmap-anydpi-v26"
any_.mkdir(parents=True, exist_ok=True)
xml = '<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n  <background android:drawable="@color/ic_bg" />\n  <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n</adaptive-icon>\n'
(any_ / "ic_launcher.xml").write_text(xml)
(any_ / "ic_launcher_round.xml").write_text(xml)
print("Iconen gemaakt.")
