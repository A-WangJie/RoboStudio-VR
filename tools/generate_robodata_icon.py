"""Render the RD companion icon using RoboStudio's existing monogram style."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from generate_studio_icon import FONT, SCALE

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'VR remote control/QuestControllerClient/Assets/Branding'

def render():
    OUT.mkdir(parents=True, exist_ok=True)
    size = 512 * SCALE
    letters = Image.new('RGBA', (size, size))
    d = ImageDraw.Draw(letters)
    font = ImageFont.truetype(FONT, 235 * SCALE)
    d.text((52*SCALE, 122*SCALE), 'R', font=font, fill='#304957')
    d.text((221*SCALE, 122*SCALE), 'D', font=font, fill='#d6a400')
    d.polygon([(89*SCALE,378*SCALE),(418*SCALE,378*SCALE),
               (410*SCALE,391*SCALE),(81*SCALE,391*SCALE)], fill='#304957')
    icon = Image.new('RGBA', (size,size))
    d=ImageDraw.Draw(icon)
    d.rounded_rectangle((20*SCALE,24*SCALE,492*SCALE,496*SCALE),106*SCALE,'#d8dde1')
    d.rounded_rectangle((20*SCALE,16*SCALE,492*SCALE,488*SCALE),106*SCALE,'#f7f7f7','#cbd2d7',2*SCALE)
    d.rounded_rectangle((30*SCALE,26*SCALE,482*SCALE,478*SCALE),97*SCALE,None,'#ffffff',2*SCALE)
    icon.alpha_composite(letters)
    icon.resize((512,512),getattr(Image, "Resampling", Image).LANCZOS).save(OUT/'RoboDataIcon.png')
    # Keep the adaptive foreground inside Android's mask-safe central area.
    foreground=Image.new('RGBA',(512,512))
    foreground.alpha_composite(letters.resize((400,400),getattr(Image, "Resampling", Image).LANCZOS),(56,56))
    foreground.save(OUT/'RoboDataForeground.png')
    Image.new('RGB',(512,512),'#f7f7f7').save(OUT/'RoboDataBackground.png')

if __name__ == '__main__':
    render()
