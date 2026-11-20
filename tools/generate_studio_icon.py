"""Render the RoboStudio RS desktop monogram (Pillow + system DejaVu font)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SCALE = 4
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"


def render():
    image = Image.new("RGBA", (512 * SCALE, 512 * SCALE))
    draw = ImageDraw.Draw(image)

    def box(bounds, radius, fill, outline=None, width=1):
        draw.rounded_rectangle(tuple(v * SCALE for v in bounds), radius * SCALE,
                               fill, outline, width * SCALE)

    box((20, 24, 492, 496), 106, "#d8dde1")
    box((20, 16, 492, 488), 106, "#f7f7f7", "#cbd2d7", 2)
    box((30, 26, 482, 478), 97, None, "#ffffff", 2)
    font = ImageFont.truetype(FONT, 245 * SCALE)
    # Optical spacing keeps both letters distinct at dock / taskbar sizes.
    draw.text((58 * SCALE, 118 * SCALE), "R", font=font, fill="#304957")
    draw.text((233 * SCALE, 118 * SCALE), "S", font=font, fill="#d6a400")
    # A short, slanted baseline echoes the forward-leaning letterforms.
    draw.polygon([(89 * SCALE, 378 * SCALE), (410 * SCALE, 378 * SCALE),
                  (402 * SCALE, 391 * SCALE), (81 * SCALE, 391 * SCALE)],
                 fill="#304957")
    image = image.resize((512, 512), getattr(Image, "Resampling", Image).LANCZOS)
    image.save(ROOT / "desktop/icon.png")
    image.save(ROOT / "desktop/robostudio-rs.png")
    image.save(ROOT / "desktop/icon.ico", sizes=[(16, 16), (24, 24), (32, 32),
                                                  (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    render()
