"""
High-CTR YouTube Thumbnail Generator for PianoSpheric (1280x720)
Generates cinematic, aesthetic thumbnails with glowing hooks and branding badge.
"""
import os
import random
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

PIANO_HOOKS = [
    {
        "kicker": "★ 15 MIN RELAXING PIANO SUITE",
        "title1": "DEEP SLEEP",
        "title2": "& PEACE",
        "sub": "Stress Relief · Meditation · Deep Focus",
        "badge": "432Hz COSMIC HARMONY"
    },
    {
        "kicker": "✨ 15 MINUTES TO RESET YOUR MIND",
        "title1": "CALM YOUR",
        "title2": "MIND & SOUL",
        "sub": "Deep Focus · Anxiety Relief · Sleep",
        "badge": "CALM & SERENITY"
    },
    {
        "kicker": "🌙 CELESTIAL PIANO DREAMS",
        "title1": "PEACEFUL",
        "title2": "REVERIE",
        "sub": "Atmospheric Melodies for Deep Rest",
        "badge": "PURE HARMONY"
    },
    {
        "kicker": "🌌 INFINITE FALLING NOTES",
        "title1": "COSMIC",
        "title2": "SERENITY",
        "sub": "Healing Frequencies · Rest & Heal",
        "badge": "15 MIN SUITE"
    }
]

def create_pianospheric_thumbnail(video_path, output_thumb_path, hook_dict=None):
    """
    Extracts a pristine frame from the piano visualizer, applies cinematic enhancements,
    and composites the PianoSpheric logo badge, glowing accents, and high-CTR text overlay.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_thumb_path)), exist_ok=True)
    temp_frame = output_thumb_path.replace('.jpg', '_raw.jpg')

    # If an unobstructed _viz.mp4 exists, extract from that for zero-clutter background
    viz_candidate = video_path.replace('.mp4', '_viz.mp4')
    source_video = viz_candidate if os.path.exists(viz_candidate) else video_path

    # Extract dynamic frame at 12s (where notes & keys are radiant)
    cmd = [
        'ffmpeg', '-y',
        '-ss', '00:00:12',
        '-i', source_video,
        '-vframes', '1',
        '-q:v', '2',
        temp_frame
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(temp_frame):
        base_img = Image.open(temp_frame).convert('RGBA')
    else:
        base_img = Image.new('RGBA', (1920, 1080), (10, 12, 18, 255))

    # Resize to standard YouTube thumbnail (1280x720) & enhance
    img = base_img.resize((1280, 720), Image.Resampling.LANCZOS)
    img = ImageEnhance.Color(img).enhance(1.3)
    img = ImageEnhance.Contrast(img).enhance(1.18)

    overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Cinematic Gradient Vignette (creates dark contrast for text on left, keeps glowing keyboard on right)
    for x in range(780):
        alpha = int(225 * (1.0 - (x / 780)**1.25))
        draw.line([(x, 0), (x, 720)], fill=(8, 10, 16, alpha))

    for y in range(160):
        alpha = int(140 * (1.0 - (y / 160)))
        draw.line([(0, y), (1280, y)], fill=(8, 10, 16, alpha))

    # 2. Select hook
    if not hook_dict:
        hook_dict = random.choice(PIANO_HOOKS)

    font_bold = "C:/Windows/Fonts/segoeuib.ttf"
    font_serif = "C:/Windows/Fonts/georgia.ttf"

    f_brand = ImageFont.truetype(font_bold, 24)
    f_hook_top = ImageFont.truetype(font_bold, 24)
    f_main = ImageFont.truetype(font_bold, 64)
    f_sub = ImageFont.truetype(font_serif, 28)
    f_badge = ImageFont.truetype(font_bold, 17)

    # 3. Top Left Branding Pill with Circular Logo
    logo_path = os.path.join(PROJECT_DIR, 'assets', 'logo.png')
    brand_w = int(draw.textlength("PianoSpheric", font=f_brand)) + 92
    draw.rounded_rectangle((45, 35, 45 + brand_w, 90), radius=28, fill=(10, 12, 18, 235), outline=(255, 195, 50, 190), width=2)
    
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert('RGBA').resize((40, 40), Image.Resampling.LANCZOS)
        mask = Image.new('L', (40, 40), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 40, 40), fill=255)
        logo_c = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
        logo_c.paste(logo, (0, 0), mask=mask)
        overlay.alpha_composite(logo_c, (56, 42))
        draw.ellipse((55, 41, 97, 83), outline=(255, 195, 50, 240), width=2)
        # Verified badge
        bv_x = 45 + brand_w - 24
        draw.ellipse((bv_x - 7, 62 - 7, bv_x + 7, 62 + 7), fill=(29, 155, 240, 255))
        draw.line((bv_x - 3, 62, bv_x - 1, 65), fill=(255, 255, 255, 255), width=2)
        draw.line((bv_x - 1, 65, bv_x + 4, 59), fill=(255, 255, 255, 255), width=2)
        tx = 108
    else:
        tx = 70
    draw.text((tx, 48), "PianoSpheric", font=f_brand, fill=(255, 255, 255, 255))

    # 4. Top Right Frequency / Mood Badge
    badge_text = hook_dict.get("badge", "432Hz COSMIC HARMONY")
    bw = int(draw.textlength(badge_text, font=f_badge)) + 36
    draw.rounded_rectangle((1235 - bw, 38, 1235, 84), radius=23, fill=(10, 12, 18, 230), outline=(255, 195, 50, 180), width=2)
    draw.ellipse((1235 - bw + 16, 56, 1235 - bw + 26, 66), fill=(255, 195, 50, 255))
    draw.text((1235 - bw + 34, 49), badge_text, font=f_badge, fill=(255, 220, 110, 255))

    # 5. Center-Left Main Typography Card & Hooks
    card_y = 180

    # Kicker / Topic Pill
    kicker_text = hook_dict.get("kicker", "★ 15 MIN RELAXING PIANO SUITE")
    kw = int(draw.textlength(kicker_text, font=f_hook_top)) + 36
    draw.rounded_rectangle((50, card_y, 50 + kw, card_y + 48), radius=12, fill=(255, 195, 50, 235))
    draw.text((68, card_y + 9), kicker_text, font=f_hook_top, fill=(10, 12, 18, 255))

    # Massive Main Title Line 1 & Line 2
    t_y = card_y + 70
    t1 = hook_dict.get("title1", "DEEP SLEEP")
    t2 = hook_dict.get("title2", "& PEACE")

    for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 5), (0, 7)]:
        draw.text((50 + ox, t_y + oy), t1, font=f_main, fill=(0, 0, 0, 240))
    draw.text((50, t_y), t1, font=f_main, fill=(255, 255, 255, 255))

    t_y2 = t_y + 72
    for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 5), (0, 7)]:
        draw.text((50 + ox, t_y2 + oy), t2, font=f_main, fill=(0, 0, 0, 240))
    draw.text((50, t_y2), t2, font=f_main, fill=(255, 215, 90, 255))

    # Subtitle line
    sub_y = t_y2 + 82
    sub = hook_dict.get("sub", "Stress Relief · Meditation · Deep Focus")
    draw.text((53, sub_y + 2), sub, font=f_sub, fill=(0, 0, 0, 210))
    draw.text((52, sub_y), sub, font=f_sub, fill=(225, 230, 240, 245))

    # 6. Bottom Right Duration Badge
    draw.rounded_rectangle((1080, 640, 1235, 685), radius=10, fill=(10, 12, 18, 230), outline=(255, 255, 255, 80), width=1)
    draw.text((1095, 648), "15:00 · 1080p HD", font=f_badge, fill=(255, 255, 255, 240))

    # 7. Luxury Outer Golden Border Framing
    draw.rectangle([(0, 0), (1279, 719)], outline=(255, 195, 50, 120), width=3)

    final_thumb = Image.alpha_composite(img, overlay).convert('RGB')
    final_thumb.save(output_thumb_path, 'JPEG', quality=95)

    if os.path.exists(temp_frame):
        os.remove(temp_frame)

    print(f"Generated High-CTR Masterpiece Thumbnail: {output_thumb_path}")
    return output_thumb_path

if __name__ == '__main__':
    create_pianospheric_thumbnail('output/synced_score_sample.mp4', 'output/test_thumb.jpg')
