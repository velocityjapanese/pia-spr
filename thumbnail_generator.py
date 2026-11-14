"""High-CTR 1280x720 thumbnail built from a real rendered frame.

No sheet-music card: the frame already carries the falling-note ribbons and
the lit keyboard. Branding, kicker, dominant title and a gold frame are drawn
on top with bundled OFL fonts, so this works on Linux CI as well as Windows.
"""
import json
import os
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

from config import FFMPEG, FINAL_EXPORT_DIR, OUTPUT_DIR
from render.scene import load_font, palette

TW, TH = 1280, 720


def _load_meta(video_path):
    stem = os.path.splitext(video_path)[0]
    candidates = [
        stem + "_meta.json",
        os.path.join(FINAL_EXPORT_DIR, os.path.basename(stem) + "_meta.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f), p
            except Exception:
                pass
    return {}, None


def _hero_section(meta):
    sections = meta.get("sections") or []
    for s in sections:
        if s.get("role") == "climax":
            return s
    return sections[min(2, len(sections) - 1)] if sections else None


def _extract_hero(video_path, meta):
    stem = os.path.splitext(video_path)[0]
    for cand in (stem + "_hero.jpg",
                 os.path.join(FINAL_EXPORT_DIR, os.path.basename(stem) + "_hero.jpg")):
        if os.path.exists(cand):
            return cand, False

    section = _hero_section(meta)
    duration = float(meta.get("duration", 0) or 0)
    if not duration:
        duration = _probe_duration(video_path)
    if section:
        t = section["start"] + 25
    else:
        t = duration * 0.5 if duration < 30 else duration * 0.38
    t = max(0.5, min(t, max(0.5, duration - 0.5)))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = os.path.join(OUTPUT_DIR, "_thumb_raw.jpg")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", video_path,
                    "-frames:v", "1", "-q:v", "2", out], check=False)
    if not os.path.exists(out) or os.path.getsize(out) < 1024:
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "0.5", "-i", video_path,
                        "-frames:v", "1", "-q:v", "2", out], check=False)
    return out, True


def _probe_duration(video_path):
    try:
        from config import FFPROBE
        res = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", video_path],
                             capture_output=True, text=True, timeout=30)
        return float(res.stdout.strip() or 0)
    except Exception:
        return 0.0


def _split_title(title):
    words = title.split()
    if len(words) < 3:
        return title.upper(), ""
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = abs(len(a) - len(b))
        if best is None or score < best[0]:
            best = (score, a, b)
    return best[1].upper(), best[2].upper()


def _build_hook(meta, minutes):
    title = meta.get("title") or "Relaxing Piano Suite"
    t1, t2 = _split_title(title)
    kicker = f"{minutes} MIN RELAXING PIANO" if minutes else "RELAXING PIANO SUITE"
    return {
        "kicker": kicker,
        "title1": t1,
        "title2": t2,
        "sub": "ORIGINAL COMPOSITION · DEEP FOCUS · SLEEP",
        "badge": "CINEMATIC PIANO",
    }


def _fit_title(draw, lines, max_w, start=78, minimum=42):
    size = start
    while size > minimum:
        font = load_font("sans", size)
        if all(draw.textlength(line, font=font) <= max_w for line in lines if line):
            return font, size
        size -= 2
    return load_font("sans", minimum), minimum


def create_pianospheric_thumbnail(video_path, output_thumb_path, hook_dict=None,
                                  minutes=None, episode=None):
    if not os.path.isabs(output_thumb_path):
        output_thumb_path = os.path.abspath(output_thumb_path)
    os.makedirs(os.path.dirname(os.path.abspath(output_thumb_path)), exist_ok=True)

    meta, _ = _load_meta(video_path)
    hero_path, temp_hero = _extract_hero(video_path, meta)
    if not os.path.exists(hero_path):
        raise FileNotFoundError(f"Could not extract a hero frame from {video_path}")
    print(f"[thumbnail] Hero frame: {os.path.basename(hero_path)}")

    if minutes is None:
        minutes = round(meta.get("duration", 0) / 60) or None

    pal_name = "midnight"
    section = _hero_section(meta)
    if section and section.get("palette"):
        pal_name = section["palette"]
    pal = palette(pal_name)

    img = Image.open(hero_path).convert("RGB")
    scale = max(TW / img.width, TH / img.height)
    img = img.resize((int(img.width * scale + 0.5), int(img.height * scale + 0.5)),
                     Image.Resampling.LANCZOS)
    left = (img.width - TW) // 2
    top = (img.height - TH) // 2
    img = img.crop((left, top, left + TW, top + TH))
    img = ImageEnhance.Color(img).enhance(1.28)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Brightness(img).enhance(1.05)

    overlay = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for x in range(900):
        alpha = int(232 * (1.0 - (x / 900) ** 1.25))
        draw.line([(x, 0), (x, TH)], fill=(5, 7, 12, alpha))
    for y in range(TH - 130, TH):
        alpha = int(70 * ((y - (TH - 130)) / 130.0) ** 1.6)
        draw.line([(0, y), (TW, y)], fill=(4, 5, 9, alpha))

    # Hide the channel mark baked into the hero frame behind our brand row.
    patch = np.zeros((120, 430, 4), dtype=np.uint8)
    px = 1.0 - (np.arange(430, dtype=np.float32) / 430.0) ** 1.6
    py = 1.0 - (np.arange(120, dtype=np.float32) / 120.0) ** 1.8
    patch[..., 0:3] = (5, 7, 12)
    patch[..., 3] = (235 * py[:, None] * px[None, :]).astype(np.uint8)
    overlay.alpha_composite(Image.fromarray(patch, "RGBA"), (0, 0))

    hook = dict(_build_hook(meta, minutes))
    if hook_dict:
        hook.update(hook_dict)

    # Brand row --------------------------------------------------------------
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")
    logo_size = 44
    lx, ly = 54, 40
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize(
            (logo_size, logo_size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (logo_size, logo_size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, logo_size, logo_size), fill=255)
        circ = Image.new("RGBA", (logo_size, logo_size), (0, 0, 0, 0))
        circ.paste(logo, (0, 0), mask=mask)
        overlay.alpha_composite(circ, (lx, ly))
        draw.ellipse((lx - 2, ly - 2, lx + logo_size + 2, ly + logo_size + 2),
                     outline=tuple(pal["accent"]) + (90,), width=1)

    f_brand = load_font("sans", 23)
    f_badge = load_font("sans", 14)
    brand_text = "PianoSpheric"
    tx = lx + logo_size + 14
    b_bbox = draw.textbbox((0, 0), brand_text, font=f_brand)
    b_th = b_bbox[3] - b_bbox[1]
    ty = ly + (logo_size - b_th) // 2 - b_bbox[1]
    draw.text((tx + 2, ty + 2), brand_text, font=f_brand, fill=(0, 0, 0, 200))
    draw.text((tx, ty), brand_text, font=f_brand, fill=(255, 255, 255, 255))

    vx = tx + int(draw.textlength(brand_text, font=f_brand)) + 10
    vy = ly + (logo_size - 17) // 2
    draw.ellipse((vx, vy, vx + 17, vy + 17), fill=(29, 155, 240, 255))
    draw.line((vx + 4, vy + 9, vx + 7, vy + 12), fill=(255, 255, 255, 255), width=2)
    draw.line((vx + 7, vy + 12, vx + 12, vy + 5), fill=(255, 255, 255, 255), width=2)

    badge_text = hook.get("badge", "CINEMATIC PIANO")
    bw = int(draw.textlength(badge_text, font=f_badge)) + 26
    bx = vx + 30
    draw.rounded_rectangle((bx, ly + 8, bx + bw, ly + 36), radius=14,
                           fill=(8, 10, 16, 210), outline=tuple(pal["accent"]) + (170,), width=1)
    draw.text((bx + 13, ly + 15), badge_text, font=f_badge,
              fill=tuple(pal["accent"]) + (255,))

    # Kicker -----------------------------------------------------------------
    f_kicker = load_font("sans", 18)
    kicker = hook.get("kicker", "RELAXING PIANO SUITE")
    ky = 214
    kw = int(draw.textlength(kicker, font=f_kicker)) + 30
    draw.rounded_rectangle((54, ky, 54 + kw, ky + 36), radius=8,
                           fill=tuple(pal["accent"]) + (238,))
    draw.text((54 + 15, ky + 8), kicker, font=f_kicker, fill=(8, 10, 16, 255))

    # Title ------------------------------------------------------------------
    lines = [hook.get("title1", ""), hook.get("title2", "")]
    f_main, size = _fit_title(draw, lines, max_w=760)
    t_y = ky + 58
    for i, line in enumerate(lines):
        if not line:
            continue
        y = t_y + i * int(size * 1.02)
        for ox, oy in ((-3, -3), (3, -3), (-3, 3), (3, 3), (0, 6), (0, 9)):
            draw.text((56 + ox, y + oy), line, font=f_main, fill=(0, 0, 0, 235))
        fill = (255, 255, 255, 255) if i == 0 else tuple(pal["rh"]) + (255,)
        draw.text((56, y), line, font=f_main, fill=fill)

    # Subtitle ---------------------------------------------------------------
    f_sub = load_font("serif", 30)
    sub = hook.get("sub", "")
    sub_y = t_y + int(size * 2.1) + 12
    if sub:
        draw.text((57, sub_y + 2), sub, font=f_sub, fill=(0, 0, 0, 220))
        draw.text((56, sub_y), sub, font=f_sub, fill=(226, 232, 242, 255))

    # Episode chip -----------------------------------------------------------
    if episode:
        f_ep = load_font("sans", 15)
        ep_text = f"EP. {int(episode):02d}"
        ep_w = int(draw.textlength(ep_text, font=f_ep)) + 26
        ex = TW - 54 - ep_w
        ey = 40
        draw.rounded_rectangle((ex, ey, ex + ep_w, ey + 32), radius=8,
                               fill=(8, 10, 16, 205), outline=tuple(pal["accent"]) + (120,), width=1)
        draw.text((ex + 13, ey + 8), ep_text, font=f_ep,
                  fill=tuple(pal["accent"]) + (225,))

    # Frame ------------------------------------------------------------------
    draw.rectangle([(0, 0), (TW - 1, TH - 1)],
                   outline=tuple(pal["accent"]) + (120,), width=3)

    final = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    final.save(output_thumb_path, "JPEG", quality=92)

    if temp_hero and os.path.exists(hero_path):
        os.remove(hero_path)

    print(f"[thumbnail] Saved: {output_thumb_path}")
    return output_thumb_path


if __name__ == "__main__":
    import sys
    create_pianospheric_thumbnail(sys.argv[1], sys.argv[2])
