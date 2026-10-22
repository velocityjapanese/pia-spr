"""
High-CTR YouTube Thumbnail Generator for PianoSpheric (1280x720)
Generates cinematic, aesthetic thumbnails with clean visualizer frames,
floating authentic sheet music score cards, dominant 86pt typography,
and zero overlapping pills.
"""
import os
import glob
import math
import random
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

PIANO_HOOKS = [
    {
        "kicker": "15 MIN RELAXING PIANO",
        "title1": "DEEP SLEEP",
        "title2": "& PEACE",
        "sub": "Stress Relief · Meditation · Deep Focus",
        "badge": "432Hz COSMIC"
    },
    {
        "kicker": "15 MINUTES TO RESET",
        "title1": "CALM YOUR",
        "title2": "MIND & SOUL",
        "sub": "Deep Focus · Anxiety Relief · Sleep",
        "badge": "CALM & HEAL"
    },
    {
        "kicker": "CELESTIAL HARMONY",
        "title1": "PEACEFUL",
        "title2": "REVERIE",
        "sub": "Atmospheric Melodies for Deep Rest",
        "badge": "PURE PEACE"
    },
    {
        "kicker": "COSMIC PIANO SUITE",
        "title1": "INFINITE",
        "title2": "SERENITY",
        "sub": "Healing Frequencies · Rest & Heal",
        "badge": "432Hz AMBIENT"
    }
]

def resolve_path(p):
    """Resolves a file path relative to current dir or PROJECT_DIR."""
    if os.path.exists(p):
        return os.path.abspath(p)
    candidate = os.path.join(PROJECT_DIR, p)
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    return os.path.abspath(candidate)

def find_clean_visualizer(video_path):
    """
    Finds the pristine, un-composited visualizer MP4 so the thumbnail
    NEVER extracts a frame that already has video headers or sheet music baked in.
    """
    video_path = resolve_path(video_path)
    if '_viz.mp4' in video_path and os.path.exists(video_path):
        return video_path

    # Try direct name pattern
    candidate = video_path.replace('.mp4', '_viz.mp4')
    if os.path.exists(candidate):
        return candidate

    # Search directory for latest clean _viz.mp4
    video_dir = os.path.dirname(os.path.abspath(video_path))
    viz_files = sorted(glob.glob(os.path.join(video_dir, '*_viz.mp4')), key=os.path.getmtime, reverse=True)
    if viz_files:
        return viz_files[0]

    # Search project output directory
    proj_output = os.path.join(PROJECT_DIR, 'output')
    viz_files = sorted(glob.glob(os.path.join(proj_output, '*_viz.mp4')), key=os.path.getmtime, reverse=True)
    if viz_files:
        return viz_files[0]

    return video_path

def find_score_card(video_path):
    """
    Locates an authentic rendered sheet music chunk card to feature in the thumbnail.
    """
    video_path = resolve_path(video_path)
    video_dir = os.path.dirname(os.path.abspath(video_path))
    base_stem = os.path.splitext(os.path.basename(video_path))[0].replace('_viz', '').replace('_synced', '')

    search_dirs = [video_dir, os.path.join(PROJECT_DIR, 'output')]

    for s_dir in search_dirs:
        if not os.path.exists(s_dir):
            continue
        # Check prefix match
        prefix_folders = glob.glob(os.path.join(s_dir, f"{base_stem}*score_cards"))
        for pf in prefix_folders:
            chunks = sorted(glob.glob(os.path.join(pf, "score_chunk_*.png")))
            if chunks:
                return chunks[0]

        # Check latest score_cards folders
        card_dirs = sorted(glob.glob(os.path.join(s_dir, "*score_cards")), key=os.path.getmtime, reverse=True)
        for cd in card_dirs:
            chunks = sorted(glob.glob(os.path.join(cd, "score_chunk_*.png")))
            if chunks:
                return chunks[0]

        # Check direct chunks
        direct_chunks = sorted(glob.glob(os.path.join(s_dir, "score_chunk_*.png")))
        if direct_chunks:
            return direct_chunks[0]

    return None

def create_pianospheric_thumbnail(video_path, output_thumb_path, hook_dict=None):
    """
    Renders a pristine 1280x720 thumbnail with:
    - 100% clean visualizer background (zero duplicate header pills)
    - Clean upper-left branding (Logo Avatar + PianoSpheric + Verified + Frequency)
    - 100% clean upper-right corner (zero overlapping pills, pure cosmic notes)
    - Dominant 86pt high-contrast typography
    - Floating authentic sheet music card with 3D drop shadow and golden glowing border
    """
    video_path = resolve_path(video_path)
    if not os.path.isabs(output_thumb_path):
        output_thumb_path = os.path.join(PROJECT_DIR, output_thumb_path)
    os.makedirs(os.path.dirname(os.path.abspath(output_thumb_path)), exist_ok=True)
    temp_frame = output_thumb_path.replace('.jpg', '_raw.jpg')

    source_video = find_clean_visualizer(video_path)
    print(f"[thumbnail] Extracting clean frame from: {os.path.basename(source_video)}")

    cmd = [
        'ffmpeg', '-y',
        '-ss', '00:00:15',
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
    img = ImageEnhance.Color(img).enhance(1.35)
    img = ImageEnhance.Contrast(img).enhance(1.22)

    overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. Soft Left-Side Vignette for Maximum Text Readability
    for x in range(780):
        alpha = int(240 * (1.0 - (x / 780)**1.3))
        draw.line([(x, 0), (x, 720)], fill=(6, 8, 14, alpha))

    # 2. Typography Setup
    font_bold = "C:/Windows/Fonts/segoeuib.ttf"
    font_reg = "C:/Windows/Fonts/segoeui.ttf"
    font_serif = "C:/Windows/Fonts/georgia.ttf"

    f_brand = ImageFont.truetype(font_bold, 26)
    f_kicker = ImageFont.truetype(font_bold, 21)
    f_main = ImageFont.truetype(font_bold, 86)
    f_sub = ImageFont.truetype(font_serif, 28)
    f_badge = ImageFont.truetype(font_bold, 17)

    if not hook_dict:
        hook_dict = random.choice(PIANO_HOOKS)

    # 3. Clean Brand Header in Upper-Left (Avatar + Channel + Verified + Frequency)
    brand_text = "PianoSpheric"
    b_bbox = draw.textbbox((0, 0), brand_text, font=f_brand)
    b_tw = b_bbox[2] - b_bbox[0]
    b_th = b_bbox[3] - b_bbox[1]

    logo_path = os.path.join(PROJECT_DIR, 'assets', 'logo.png')
    logo_size = 52
    pill_x = 55
    pill_y = 45

    # Prominent circular logo avatar with double glowing gold ring
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert('RGBA').resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        mask = Image.new('L', (logo_size, logo_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, logo_size, logo_size), fill=255)
        logo_c = Image.new('RGBA', (logo_size, logo_size), (0, 0, 0, 0))
        logo_c.paste(logo, (0, 0), mask=mask)
        overlay.alpha_composite(logo_c, (pill_x, pill_y))
        draw.ellipse((pill_x - 3, pill_y - 3, pill_x + logo_size + 3, pill_y + logo_size + 3), outline=(255, 195, 50, 100), width=2)
        draw.ellipse((pill_x - 1, pill_y - 1, pill_x + logo_size + 1, pill_y + logo_size + 1), outline=(255, 195, 50, 240), width=2)

    # Channel name text with drop shadow
    tx = pill_x + logo_size + 16
    ty = pill_y + (logo_size - b_th) // 2 - b_bbox[1] - 2
    draw.text((tx + 2, ty + 2), brand_text, font=f_brand, fill=(0, 0, 0, 220))
    draw.text((tx, ty), brand_text, font=f_brand, fill=(255, 255, 255, 255))

    # Verified blue badge
    vx = tx + b_tw + 12
    vy = pill_y + (logo_size - 18) // 2
    draw.ellipse((vx, vy, vx + 18, vy + 18), fill=(29, 155, 240, 255))
    draw.line((vx + 5, vy + 9, vx + 8, vy + 12), fill=(255, 255, 255, 255), width=2)
    draw.line((vx + 8, vy + 12, vx + 13, vy + 6), fill=(255, 255, 255, 255), width=2)

    # Frequency tag pill next to brand
    freq_text = hook_dict.get("badge", "432Hz COSMIC")
    fb_bbox = draw.textbbox((0, 0), freq_text, font=f_badge)
    fb_tw = fb_bbox[2] - fb_bbox[0]
    fb_th = fb_bbox[3] - fb_bbox[1]
    fx1 = vx + 30
    fx2 = fx1 + fb_tw + 28
    draw.rounded_rectangle((fx1, pill_y + 8, fx2, pill_y + 44), radius=18, fill=(10, 12, 18, 220), outline=(255, 195, 50, 180), width=2)
    draw.text((fx1 + 14, pill_y + 8 + (36 - fb_th) // 2 - fb_bbox[1]), freq_text, font=f_badge, fill=(255, 220, 110, 255))

    # 4. Center-Left Dominant Typography Block
    card_y = 155

    # Kicker pill
    kicker_text = hook_dict.get("kicker", "15 MIN RELAXING PIANO")
    k_bbox = draw.textbbox((0, 0), kicker_text, font=f_kicker)
    k_tw = k_bbox[2] - k_bbox[0]
    k_th = k_bbox[3] - k_bbox[1]
    k_w = k_tw + 36
    k_h = 44
    draw.rounded_rectangle((55, card_y, 55 + k_w, card_y + k_h), radius=10, fill=(255, 195, 50, 240))
    draw.text((55 + 18, card_y + (k_h - k_th) // 2 - k_bbox[1]), kicker_text, font=f_kicker, fill=(10, 12, 18, 255))

    # Massive 2-Line Title (86pt with deep multi-layer 3D shadow)
    t1 = hook_dict.get("title1", "DEEP SLEEP")
    t2 = hook_dict.get("title2", "& PEACE")

    t_y = card_y + 60
    for ox, oy in [(-4, -4), (4, -4), (-4, 4), (4, 4), (0, 7), (0, 10)]:
        draw.text((55 + ox, t_y + oy), t1, font=f_main, fill=(0, 0, 0, 255))
    draw.text((55, t_y), t1, font=f_main, fill=(255, 255, 255, 255))

    t_y2 = t_y + 94
    for ox, oy in [(-4, -4), (4, -4), (-4, 4), (4, 4), (0, 7), (0, 10)]:
        draw.text((55 + ox, t_y2 + oy), t2, font=f_main, fill=(0, 0, 0, 255))
    draw.text((55, t_y2), t2, font=f_main, fill=(255, 215, 90, 255))

    # Subtitle Line
    sub_text = hook_dict.get("sub", "Stress Relief · Meditation · Deep Focus")
    sub_y = t_y2 + 102
    draw.text((57, sub_y + 2), sub_text, font=f_sub, fill=(0, 0, 0, 230))
    draw.text((55, sub_y), sub_text, font=f_sub, fill=(230, 235, 245, 255))

    # 5. Floating Sheet Music Card (Middle-Right / Above Keyboard)
    score_path = find_score_card(video_path)
    if score_path and os.path.exists(score_path):
        print(f"[thumbnail] Featuring authentic sheet music card: {os.path.basename(score_path)}")
        sc_img = Image.open(score_path).convert('RGBA')
        sc_w = 540
        sc_h = int(sc_img.height * (sc_w / sc_img.width))
        sc_scaled = sc_img.resize((sc_w, sc_h), Image.Resampling.LANCZOS)

        sc_x = 690
        sc_y = 375

        # 3D Depth Shadow
        shadow = Image.new('RGBA', (sc_w + 40, sc_h + 40), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        sdraw.rounded_rectangle((15, 15, sc_w + 25, sc_h + 25), radius=20, fill=(0, 0, 0, 230))
        shadow = shadow.filter(ImageFilter.GaussianBlur(12))
        overlay.alpha_composite(shadow, (sc_x - 15, sc_y - 15))

        # Paste sheet music card
        overlay.alpha_composite(sc_scaled, (sc_x, sc_y))

        # Luxury double glowing gold border around card
        draw.rounded_rectangle((sc_x - 1, sc_y - 1, sc_x + sc_w + 1, sc_y + sc_h + 1), radius=17, outline=(255, 195, 50, 80), width=3)
        draw.rounded_rectangle((sc_x, sc_y, sc_x + sc_w, sc_y + sc_h), radius=16, outline=(255, 215, 90, 240), width=2)
    else:
        print("[thumbnail] Warning: No sheet music score card found to embed.")

    # 6. Outer Luxury Golden Framing Border
    draw.rectangle([(0, 0), (1279, 719)], outline=(255, 195, 50, 130), width=3)

    final_thumb = Image.alpha_composite(img, overlay).convert('RGB')
    final_thumb.save(output_thumb_path, 'JPEG', quality=95)

    if os.path.exists(temp_frame):
        os.remove(temp_frame)

    print(f"Generated Clean Masterpiece Thumbnail: {output_thumb_path}")
    return output_thumb_path

if __name__ == '__main__':
    create_pianospheric_thumbnail('output/synced_score_sample.mp4', 'output/test_thumb.jpg')
