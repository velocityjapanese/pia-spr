import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def create_longform_header(width=1920, height=120, channel_name="Piano Spheric", song_title="Original Composition • G Minor"):
    """
    Creates a modern, ultra-crisp 16:9 YouTube video top overlay.
    Left: Channel Branding Pill (Piano Spheric) with verified badge
    Right: Song Title & Key indicator with high-contrast, crystal-clear typography
    """
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_bold = "C:/Windows/Fonts/segoeuib.ttf"
    font_reg = "C:/Windows/Fonts/segoeui.ttf"
    f_chan = ImageFont.truetype(font_bold, 22)
    f_title = ImageFont.truetype(font_bold, 22)
    f_symbol = ImageFont.truetype(font_reg, 18)

    # 1. Left Channel Branding Pill (Piano Spheric)
    pill_w = int(draw.textlength(channel_name, font=f_chan)) + 86
    draw.rounded_rectangle((50, 28, 50 + pill_w, 82), radius=27, fill=(10, 12, 18, 235), outline=(255, 195, 50, 180), width=2)
    
    # Mini gold celestial icon
    draw.ellipse((65, 41, 91, 67), fill=(255, 195, 50, 45), outline=(255, 195, 50, 230), width=2)
    draw.text((102, 42), channel_name, font=f_chan, fill=(255, 255, 255, 255))
    
    # Verified badge
    bv_x = 50 + pill_w - 24
    draw.ellipse((bv_x - 7, 55 - 7, bv_x + 7, 55 + 7), fill=(29, 155, 240, 255))
    draw.line((bv_x - 3, 55, bv_x - 1, 58), fill=(255, 255, 255, 255), width=2)
    draw.line((bv_x - 1, 58, bv_x + 4, 52), fill=(255, 255, 255, 255), width=2)

    # 2. Right Song Title Pill (Crystal-Clear High Contrast)
    title_text_w = int(draw.textlength(song_title, font=f_title))
    title_w = title_text_w + 70
    t_x = width - title_w - 50

    # Frosted Obsidian Container with warm amber border
    draw.rounded_rectangle((t_x, 28, width - 50, 82), radius=27, fill=(10, 12, 18, 235), outline=(255, 195, 50, 160), width=2)
    
    # Live Glowing Indicator Dot
    draw.ellipse((t_x + 20, 50, t_x + 30, 60), fill=(255, 195, 50, 255))
    
    # Text with soft shadow for maximum legibility
    draw.text((t_x + 43, 43), song_title, font=f_title, fill=(0, 0, 0, 180)) # shadow
    draw.text((t_x + 42, 42), song_title, font=f_title, fill=(255, 255, 255, 255)) # crisp white

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
