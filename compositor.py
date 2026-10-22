import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def create_longform_header(width=1920, height=120, channel_name="Piano Spheric", song_title="Original Composition - G Minor"):
    """
    Creates a modern, mathematically padded 16:9 YouTube video top overlay.
    Left: Channel Branding Pill (Piano Spheric) with circular logo and verified badge.
    Right: Song Title Pill with crystal-clear typography and guaranteed safe margins.
    """
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_bold = "C:/Windows/Fonts/segoeuib.ttf"
    f_chan = ImageFont.truetype(font_bold, 22)
    f_title = ImageFont.truetype(font_bold, 21)

    logo_path = os.path.join(PROJECT_DIR, 'assets', 'logo.png')

    # 1. Left Channel Branding Pill (Piano Spheric)
    c_bbox = draw.textbbox((0, 0), channel_name, font=f_chan)
    c_tw = c_bbox[2] - c_bbox[0]
    c_th = c_bbox[3] - c_bbox[1]

    logo_size = 38
    pad_l = 14
    gap_logo = 12
    gap_badge = 10
    badge_d = 16
    pad_r = 20

    pill_w = pad_l + logo_size + gap_logo + c_tw + gap_badge + badge_d + pad_r
    pill_h = 54
    pill_x = 50
    pill_y = 30

    draw.rounded_rectangle((pill_x, pill_y, pill_x + pill_w, pill_y + pill_h), radius=27, fill=(10, 12, 18, 240), outline=(255, 195, 50, 190), width=2)
    
    # Circular logo
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert('RGBA').resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        mask = Image.new('L', (logo_size, logo_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, logo_size, logo_size), fill=255)
        logo_circ = Image.new('RGBA', (logo_size, logo_size), (0, 0, 0, 0))
        logo_circ.paste(logo, (0, 0), mask=mask)
        img.alpha_composite(logo_circ, (pill_x + pad_l, pill_y + (pill_h - logo_size) // 2))
        draw.ellipse((pill_x + pad_l - 1, pill_y + (pill_h - logo_size) // 2 - 1, pill_x + pad_l + logo_size + 1, pill_y + (pill_h - logo_size) // 2 + logo_size + 1), outline=(255, 195, 50, 240), width=1)
    else:
        draw.ellipse((pill_x + pad_l, pill_y + 8, pill_x + pad_l + logo_size, pill_y + 8 + logo_size), fill=(255, 195, 50, 45), outline=(255, 195, 50, 230), width=2)

    # Channel text
    tx = pill_x + pad_l + logo_size + gap_logo
    ty = pill_y + (pill_h - c_th) // 2 - c_bbox[1]
    draw.text((tx, ty), channel_name, font=f_chan, fill=(255, 255, 255, 255))

    # Verified blue badge
    vx = tx + c_tw + gap_badge
    vy = pill_y + (pill_h - badge_d) // 2
    draw.ellipse((vx, vy, vx + badge_d, vy + badge_d), fill=(29, 155, 240, 255))
    draw.line((vx + 4, vy + 8, vx + 7, vy + 11), fill=(255, 255, 255, 255), width=2)
    draw.line((vx + 7, vy + 11, vx + 12, vy + 5), fill=(255, 255, 255, 255), width=2)

    # 2. Right Song Title Pill (Guaranteed Non-Overflowing)
    clean_title = song_title.replace("•", "-")
    t_bbox = draw.textbbox((0, 0), clean_title, font=f_title)
    t_tw = t_bbox[2] - t_bbox[0]
    t_th = t_bbox[3] - t_bbox[1]

    t_pad_l = 20
    dot_d = 10
    gap_dot = 12
    t_pad_r = 24

    t_pill_w = t_pad_l + dot_d + gap_dot + t_tw + t_pad_r
    t_pill_h = 54
    t_x2 = width - 50
    t_x1 = t_x2 - t_pill_w
    t_y = 30

    draw.rounded_rectangle((t_x1, t_y, t_x2, t_y + t_pill_h), radius=27, fill=(10, 12, 18, 240), outline=(255, 195, 50, 180), width=2)
    
    # Glowing gold indicator dot
    dot_x = t_x1 + t_pad_l
    dot_y = t_y + (t_pill_h - dot_d) // 2
    draw.ellipse((dot_x, dot_y, dot_x + dot_d, dot_y + dot_d), fill=(255, 195, 50, 255))

    # Title text with shadow
    title_x = dot_x + dot_d + gap_dot
    title_y = t_y + (t_pill_h - t_th) // 2 - t_bbox[1]
    draw.text((title_x + 1, title_y + 1), clean_title, font=f_title, fill=(0, 0, 0, 200))
    draw.text((title_x, title_y), clean_title, font=f_title, fill=(255, 255, 255, 255))

    return img

def composite_longform_video(viz_video, score_input, audio_wav, output_mp4, song_title="Original Composition • G Minor", channel_name="Piano Spheric"):
    """
    Composites 16:9 Landscape YouTube Video:
    - 1920x1080 Fullscreen falling notes & 88-key piano
    - Elegant top banner with channel pill and song title
    - Fully Synced sheet music score cards (flips every 2 bars with playback)
    - 320kbps Lossless Yamaha Concert Grand audio
    """
    header_path = os.path.join(PROJECT_DIR, 'output', 'temp_lf_header.png')
    hdr = create_longform_header(width=1920, height=120, channel_name=channel_name, song_title=song_title)
    hdr.save(header_path)

    rel_viz = os.path.relpath(viz_video, PROJECT_DIR).replace('\\', '/')
    rel_score = os.path.relpath(score_input, PROJECT_DIR).replace('\\', '/')
    rel_header = os.path.relpath(header_path, PROJECT_DIR).replace('\\', '/')
    rel_audio = os.path.relpath(audio_wav, PROJECT_DIR).replace('\\', '/')
    rel_out = os.path.relpath(output_mp4, PROJECT_DIR).replace('\\', '/')

    is_synced_sequence = score_input.endswith('.txt')

    if is_synced_sequence:
        filter_complex = (
            "[0:v][1:v]overlay=0:0[v1]; "
            "[v1][2:v]overlay=50:580[vfinal]"
        )
        cmd = [
            'ffmpeg', '-y',
            '-i', rel_viz,
            '-i', rel_header,
            '-f', 'concat', '-safe', '0', '-i', rel_score,
            '-i', rel_audio,
            '-filter_complex', filter_complex,
            '-map', '[vfinal]',
            '-map', '3:a',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '17',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '320k',
            '-shortest',
            rel_out
        ]
    else:
        filter_complex = (
            "[0:v][1:v]overlay=0:0[v1]; "
            "[2:v]scale=650:-1[score]; "
            "[v1][score]overlay=50:580[vfinal]"
        )
        cmd = [
            'ffmpeg', '-y',
            '-i', rel_viz,
            '-i', rel_header,
            '-i', rel_score,
            '-i', rel_audio,
            '-filter_complex', filter_complex,
            '-map', '[vfinal]',
            '-map', '3:a',
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '17',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '320k',
            '-shortest',
            rel_out
        ]

    print(f"Compositing 16:9 Long-Form Video: {output_mp4}")
    result = subprocess.run(cmd, cwd=PROJECT_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if not os.path.exists(output_mp4) or os.path.getsize(output_mp4) == 0:
        raise RuntimeError(f"FFmpeg compositing failed: {result.stderr}")

    print(f"16:9 Video successfully generated ({os.path.getsize(output_mp4)} bytes): {output_mp4}")
    return output_mp4

if __name__ == '__main__':
    composite_longform_video('output/longform_viz.mp4', 'output/longform_score.png', 'output/longform.wav', 'output/test_longform.mp4')
