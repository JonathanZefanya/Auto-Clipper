"""F-20: buat ikon aplikasi (PNG + ICO multi-ukuran) tanpa Tauri CLI — cukup Pillow dari venv backend.

    backend\\.venv\\Scripts\\python.exe frontend-desktop\\scripts\\make_icons.py
Hasil: frontend-desktop/src-tauri/icons/{32x32,128x128,128x128@2x,icon}.png + icon.ico
(alternatif: `npx tauri icon app-icon.png` setelah Tauri CLI terpasang).
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src-tauri" / "icons"
ACCENT = (124, 77, 255)   # ≈ accent-600 UI
S = 1024


def draw_icon() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=ACCENT)
    # gunting (selaras ikon "scissors" di UI): dua cincin + dua bilah
    w = 58
    for cx, cy in ((330, 330), (330, 694)):
        d.ellipse([cx - 120, cy - 120, cx + 120, cy + 120], outline="white", width=w)
    d.line([(415, 610), (800, 230)], fill="white", width=w)
    d.line([(560, 560), (800, 800)], fill="white", width=w)
    d.line([(415, 415), (510, 510)], fill="white", width=w)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = draw_icon()
    base.save(OUT.parent.parent / "app-icon.png")   # sumber untuk `npx tauri icon` bila perlu
    for name, size in (("32x32.png", 32), ("128x128.png", 128), ("128x128@2x.png", 256), ("icon.png", 512)):
        base.resize((size, size), Image.LANCZOS).save(OUT / name)
    base.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"ikon dibuat di {OUT}")


if __name__ == "__main__":
    main()
