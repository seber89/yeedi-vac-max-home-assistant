"""Render the project's original geometric vacuum icon (requires Pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw

image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.ellipse((20, 20, 236, 236), fill="#147d92")
draw.ellipse((34, 34, 222, 222), outline="white", width=6)
draw.rounded_rectangle((94, 61, 162, 84), radius=10, fill="white")
draw.arc((55, 65, 201, 207), 25, 155, fill="white", width=6)
target = Path(__file__).resolve().parents[1] / "custom_components/yeedi_vac_max/brand/icon.png"
target.parent.mkdir(parents=True, exist_ok=True)
image.save(target)
