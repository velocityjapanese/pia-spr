"""
High-CTR YouTube Thumbnail Generator for PianoSpheric (1280x720)
Generates cinematic, aesthetic thumbnails with glowing hooks and branding badge.
"""
import os
import random
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

PIANO_HOOKS = [
    {"main": "15 MIN RELAXING PIANO", "sub": "Deep Sleep · Stress Relief · Study", "badge": "432Hz COSMIC"},
    {"main": "PEACEFUL PIANO SUITE", "sub": "Ethereal Melodies for Deep Focus", "badge": "PURE HARMONY"},
    {"main": "MOONLIGHT MEDITATION", "sub": "Calm Your Mind in 15 Minutes", "badge": "CELESTIAL SOUND"},
    {"main": "COSMIC PIANO JOURNEY", "sub": "Infinite Falling Notes & Serenity", "badge": "REST & HEAL"},
    {"main": "GENTLE PIANO DREAMS", "sub": "Soft Atmospheric Keys for Anxiety Relief", "badge": "DEEP FOCUS"}
]

def create_pianospheric_thumbnail(video_path, output_thumb_path, main_text=None, sub_text=None, badge_text=None):
    """
    Extracts a frame from the piano video, applies cinematic enhancements,
    and composites the PianoSpheric logo badge and high-CTR text overlay.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_thumb_path)), exist_ok=True)
    temp_frame = output_thumb_path.replace('.jpg', '_raw.jpg')

    # 1. Extract dynamic frame at 15s (where falling notes & keys are radiant)
    cmd = [
        'ffmpeg', '-y',
        '-ss', '00:00:15',
        '-i', video_path,
        '-vframes', '1',
        '-q:v', '2',
        temp_frame
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(temp_frame):
        base_img = Image.open(temp_frame).convert('RGBA')
    else:
        # Fallback dark background
        base_img = Image.new('RGBA', (1920, 1080), (10, 12, 18, 255))

    # Resize to standard YouTube thumbnail (1280x720)
    img = base_img.resize((1280, 720), Image.Resampling.LANCZOS)
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.25)
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.15)

    overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Dark bottom & top gradient for text pop
    for y in range(220):
        alpha = int(170 * (1 - y / 220))
        draw.line([(0, y), (1280, y)], fill=(5, 6, 10, alpha))
    for y in range(480, 720):
        alpha = int(210 * ((y - 480) / 240))
        draw.line([(0, y), (1280, y)], fill=(5, 6, 10, alpha))

    # Select hook
    if not main_text:
        hook = random.choice(PIANO_HOOKS)
        main_text = hook["main"]
        sub_text = hook["sub"]
        badge_text = hook["badge"]

    font_bold = "C:/Windows/Fonts/segoeuib.ttf"
    font_reg = "C:/Windows/Fonts/segoeui.ttf"

    f_badge = ImageFont.truetype(font_bold, 18)
    f_main = ImageFont.truetype(font_bold, 52)
    f_sub = ImageFont.truetype(font_reg, 24)
    f_brand = ImageFont.truetype(font_bold, 22)

    # Top Left Branding Pill with Logo
    logo_path = os.path.join(PROJECT_DIR, 'assets', 'logo.png')
    brand_w = int(draw.textlength("PianoSpheric", font=f_brand)) + 80
    draw.rounded_rectangle((40, 35, 40 + brand_w, 85), radius=25, fill=(10, 12, 18, 230), outline=(255, 195, 50, 180), width=2)
    
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert('RGBA').resize((36, 36), Image.Resampling.LANCZOS)
        mask = Image.new('L', (36, 36), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 36, 36), fill=255)
        logo_c = Image.new('RGBA', (36, 36), (0, 0, 0, 0))
        logo_c.paste(logo, (0, 0), mask=mask)
        overlay.alpha_composite(logo_c, (50, 42))
        draw.ellipse((49, 41, 87, 79), outline=(255, 195, 50, 240), width=1)
        text_bx = 96
    else:
        text_bx = 60
    draw.text((text_bx, 46), "PianoSpheric", font=f_brand, fill=(255, 255, 255, 255))

    # Top Right Badge (e.g. 432Hz COSMIC)
    if badge_text:
        bw = int(draw.textlength(badge_text, font=f_badge)) + 36
        draw.rounded_rectangle((1240 - bw, 35, 1240, 80), radius=22, fill=(255, 195, 50, 230))
        draw.text((1240 - bw + 18, 45), badge_text, font=f_badge, fill=(10, 12, 18, 255))

    # Bottom Text Container
    # Main Hook Title
    main_y = 560
    # Soft glowing shadow
    for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 4)]:
        draw.text((50 + ox, main_y + oy), main_text, font=f_main, fill=(0, 0, 0, 220))
    # Crisp white letters with gold emphasis
    draw.text((50, main_y), main_text, font=f_main, fill=(255, 255, 255, 255))

    # Subtitle
    if sub_text:
        draw.text((52, main_y + 68), sub_text, font=f_sub, fill=(255, 215, 90, 240))

    final_thumb = Image.alpha_composite(img, overlay).convert('RGB')
    final_thumb.save(output_thumb_path, 'JPEG', quality=95)

    if os.path.exists(temp_frame):
        os.remove(temp_frame)

    print(f"Generated High-CTR Thumbnail: {output_thumb_path}")
    return output_thumb_path

if __name__ == '__main__':
    create_pianospheric_thumbnail('output/synced_score_sample.mp4', 'output/test_thumb.jpg')
