"""
High-CTR YouTube Thumbnail Generator for PianoSpheric (1280x720)
Generates cinematic, aesthetic thumbnails with mathematically bounded text containers,
vector icons (zero broken glyphs/emojis), and official brand styling.
"""
import os
import math
import random
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

PIANO_HOOKS = [
    {
        "kicker": "15 MIN RELAXING PIANO SUITE",
        "title1": "DEEP SLEEP",
        "title2": "& PEACE",
        "sub": "Stress Relief · Meditation · Deep Focus",
        "badge": "432Hz COSMIC HARMONY"
    },
    {
        "kicker": "15 MINUTES TO RESET YOUR MIND",
        "title1": "CALM YOUR",
        "title2": "MIND & SOUL",
        "sub": "Deep Focus · Anxiety Relief · Sleep",
        "badge": "CALM & SERENITY"
    },
    {
        "kicker": "CELESTIAL PIANO DREAMS",
        "title1": "PEACEFUL",
        "title2": "REVERIE",
        "sub": "Atmospheric Melodies for Deep Rest",
        "badge": "PURE HARMONY"
    },
    {
        "kicker": "INFINITE FALLING NOTES",
        "title1": "COSMIC",
        "title2": "SERENITY",
        "sub": "Healing Frequencies · Rest & Heal",
        "badge": "15 MIN SUITE"
    }
]

def draw_star(draw, cx, cy, r_out, r_in, fill):
    """Draws a crisp geometric 5-point star vector."""
    pts = []
    for i in range(10):
        angle = i * (math.pi / 5) - (math.pi / 2)
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(pts, fill=fill)

def create_pianospheric_thumbnail(video_path, output_thumb_path, hook_dict=None):
    """
    Renders a mathematically bounded, flawless 1280x720 thumbnail:
    - Text is strictly contained inside containers with generous padding
    - Vector stars and dots replace unreliable Unicode emoji symbols
    - Visualizer background enhanced with cinematic lighting
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_thumb_path)), exist_ok=True)
    temp_frame = output_thumb_path.replace('.jpg', '_raw.jpg')

    # Prefer raw visualizer video if available for clean, non-cluttered background
    viz_candidate = video_path.replace('.mp4', '_viz.mp4')
    source_video = viz_candidate if os.path.exists(viz_candidate) else video_path

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

    img = base_img.resize((1280, 720), Image.Resampling.LANCZOS)
    img = ImageEnhance.Color(img).enhance(1.3)
    img = ImageEnhance.Contrast(img).enhance(1.18)

    overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Cinematic Left Gradient (creates dark space for text readability while keeping keys glowing)
    for x in range(800):
        alpha = int(230 * (1.0 - (x / 800)**1.3))
        draw.line([(x, 0), (x, 720)], fill=(8, 10, 16, alpha))
    for y in range(160):
        alpha = int(140 * (1.0 - (y / 160)))
        draw.line([(0, y), (1280, y)], fill=(8, 10, 16, alpha))

    # 2. Fonts
    font_bold = "C:/Windows/Fonts/segoeuib.ttf"
    font_reg = "C:/Windows/Fonts/segoeui.ttf"
    font_serif = "C:/Windows/Fonts/georgia.ttf"

    f_brand = ImageFont.truetype(font_bold, 22)
    f_kicker = ImageFont.truetype(font_bold, 22)
    f_main = ImageFont.truetype(font_bold, 64)
    f_sub = ImageFont.truetype(font_serif, 26)
    f_badge = ImageFont.truetype(font_bold, 16)

    # 3. Brand Pill (Top Left)
    brand_text = "PianoSpheric"
    b_bbox = draw.textbbox((0, 0), brand_text, font=f_brand)
    b_tw = b_bbox[2] - b_bbox[0]
    b_th = b_bbox[3] - b_bbox[1]

    logo_path = os.path.join(PROJECT_DIR, 'assets', 'logo.png')
    logo_size = 40
    b_pad_l = 14
    gap_logo = 12
    gap_badge = 10
    badge_d = 16
    b_pad_r = 20

    pill_w = b_pad_l + logo_size + gap_logo + b_tw + gap_badge + badge_d + b_pad_r
    pill_h = 56
    pill_x = 45
    pill_y = 35

    draw.rounded_rectangle((pill_x, pill_y, pill_x + pill_w, pill_y + pill_h), radius=28, fill=(10, 12, 18, 240), outline=(255, 195, 50, 190), width=2)

    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert('RGBA').resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        mask = Image.new('L', (logo_size, logo_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, logo_size, logo_size), fill=255)
        logo_c = Image.new('RGBA', (logo_size, logo_size), (0, 0, 0, 0))
        logo_c.paste(logo, (0, 0), mask=mask)
        overlay.alpha_composite(logo_c, (pill_x + b_pad_l, pill_y + (pill_h - logo_size) // 2))
        draw.ellipse((pill_x + b_pad_l - 1, pill_y + (pill_h - logo_size) // 2 - 1, pill_x + b_pad_l + logo_size + 1, pill_y + (pill_h - logo_size) // 2 + logo_size + 1), outline=(255, 195, 50, 240), width=1)

    tx = pill_x + b_pad_l + logo_size + gap_logo
    ty = pill_y + (pill_h - b_th) // 2 - b_bbox[1]
    draw.text((tx, ty), brand_text, font=f_brand, fill=(255, 255, 255, 255))

    vx = tx + b_tw + gap_badge
    vy = pill_y + (pill_h - badge_d) // 2
    draw.ellipse((vx, vy, vx + badge_d, vy + badge_d), fill=(29, 155, 240, 255))
    draw.line((vx + 4, vy + 8, vx + 7, vy + 11), fill=(255, 255, 255, 255), width=2)
    draw.line((vx + 7, vy + 11, vx + 12, vy + 5), fill=(255, 255, 255, 255), width=2)

    # 4. Top Right Frequency / Mood Badge (Mathematically Bounded)
    if not hook_dict:
        hook_dict = random.choice(PIANO_HOOKS)

    top_badge_text = hook_dict.get("badge", "432Hz COSMIC HARMONY")
    tb_bbox = draw.textbbox((0, 0), top_badge_text, font=f_badge)
    tb_tw = tb_bbox[2] - tb_bbox[0]
    tb_th = tb_bbox[3] - tb_bbox[1]

    tb_pad_l = 18
    tb_dot_d = 10
    tb_gap = 10
    tb_pad_r = 22
    tb_w = tb_pad_l + tb_dot_d + tb_gap + tb_tw + tb_pad_r
    tb_h = 46
    tb_x2 = 1235
    tb_x1 = tb_x2 - tb_w
    tb_y = 40

    draw.rounded_rectangle((tb_x1, tb_y, tb_x2, tb_y + tb_h), radius=23, fill=(10, 12, 18, 235), outline=(255, 195, 50, 180), width=2)

    dot_x = tb_x1 + tb_pad_l
    dot_y = tb_y + (tb_h - tb_dot_d) // 2
    draw.ellipse((dot_x, dot_y, dot_x + tb_dot_d, dot_y + tb_dot_d), fill=(255, 195, 50, 255))

    tb_tx = dot_x + tb_dot_d + tb_gap
    tb_ty = tb_y + (tb_h - tb_th) // 2 - tb_bbox[1]
    draw.text((tb_tx, tb_ty), top_badge_text, font=f_badge, fill=(255, 220, 110, 255))

    # 5. Kicker Pill with Geometric Vector Star
    kicker_text = hook_dict.get("kicker", "15 MIN RELAXING PIANO SUITE")
    k_bbox = draw.textbbox((0, 0), kicker_text, font=f_kicker)
    k_tw = k_bbox[2] - k_bbox[0]
    k_th = k_bbox[3] - k_bbox[1]

    k_pad_l = 20
    k_star_w = 16
    k_gap = 12
    k_pad_r = 24
    k_w = k_pad_l + k_star_w + k_gap + k_tw + k_pad_r
    k_h = 46
    k_x = 55
    k_y = 180

    draw.rounded_rectangle((k_x, k_y, k_x + k_w, k_y + k_h), radius=12, fill=(255, 195, 50, 240))

    star_cx = k_x + k_pad_l + k_star_w // 2
    star_cy = k_y + k_h // 2
    draw_star(draw, star_cx, star_cy, 8, 3.5, (10, 12, 18, 255))

    k_tx = k_x + k_pad_l + k_star_w + k_gap
    k_ty = k_y + (k_h - k_th) // 2 - k_bbox[1]
    draw.text((k_tx, k_ty), kicker_text, font=f_kicker, fill=(10, 12, 18, 255))

    # 6. Massive Main Title with Deep 3D Shadow
    t1 = hook_dict.get("title1", "DEEP SLEEP")
    t2 = hook_dict.get("title2", "& PEACE")

    t_y = k_y + 70
    for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 5), (0, 7)]:
        draw.text((55 + ox, t_y + oy), t1, font=f_main, fill=(0, 0, 0, 240))
    draw.text((55, t_y), t1, font=f_main, fill=(255, 255, 255, 255))

    t_y2 = t_y + 74
    for ox, oy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 5), (0, 7)]:
        draw.text((55 + ox, t_y2 + oy), t2, font=f_main, fill=(0, 0, 0, 240))
    draw.text((55, t_y2), t2, font=f_main, fill=(255, 215, 90, 255))

    # 7. Subtitle
    sub_text = hook_dict.get("sub", "Stress Relief · Meditation · Deep Focus")
    sub_y = t_y2 + 82
    draw.text((57, sub_y + 2), sub_text, font=f_sub, fill=(0, 0, 0, 220))
    draw.text((55, sub_y), sub_text, font=f_sub, fill=(230, 235, 245, 255))

    # 8. Bottom Right Duration Badge
    dur_text = "15:00 · 1080p HD"
    d_bbox = draw.textbbox((0, 0), dur_text, font=f_badge)
    d_tw = d_bbox[2] - d_bbox[0]
    d_th = d_bbox[3] - d_bbox[1]

    d_w = d_tw + 36
    d_h = 42
    d_x2 = 1235
    d_x1 = d_x2 - d_w
    d_y = 640

    draw.rounded_rectangle((d_x1, d_y, d_x2, d_y + d_h), radius=10, fill=(10, 12, 18, 235), outline=(255, 255, 255, 100), width=1)
    draw.text((d_x1 + 18, d_y + (d_h - d_th) // 2 - d_bbox[1]), dur_text, font=f_badge, fill=(255, 255, 255, 240))

    # 9. Outer Framing Border
    draw.rectangle([(0, 0), (1279, 719)], outline=(255, 195, 50, 130), width=3)

    final_thumb = Image.alpha_composite(img, overlay).convert('RGB')
    final_thumb.save(output_thumb_path, 'JPEG', quality=95)

    if os.path.exists(temp_frame):
        os.remove(temp_frame)

    print(f"Generated Flawless Thumbnail: {output_thumb_path}")
    return output_thumb_path

if __name__ == '__main__':
    create_pianospheric_thumbnail('output/synced_score_sample.mp4', 'output/test_thumb.jpg')
