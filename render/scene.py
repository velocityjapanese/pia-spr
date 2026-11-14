"""Static scene elements: background, title cards, 88-key keyboard base."""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import (
    ASSETS_DIR, FONT_DIR, KEYBOARD_H, KEYBOARD_MARGIN_X, KEYBOARD_Y_IN_STRIP,
    PALETTES, STRIP_H, STRIP_Y, W, H,
)

WHITE_PCS = {0, 2, 4, 5, 7, 9, 11}
LOW_KEY, HIGH_KEY = 21, 108

_font_cache = {}
_key_cache = None


def _set_axes(font, size, weight):
    """Sets variable-font axes (Inter exposes opsz+wght, Cormorant only wght)."""
    try:
        axes = font.get_variation_axes()
    except Exception:
        return
    values = []
    for axis in axes:
        name = axis.get("name", "")
        if isinstance(name, bytes):
            name = name.decode("utf-8", "ignore")
        name = name.lower()
        if "weight" in name or name == "wght":
            values.append(weight)
        elif "optical" in name or name == "opsz":
            values.append(float(size))
        else:
            values.append(axis.get("default", 0))
    try:
        font.set_variation_by_axes(values)
    except Exception:
        try:
            font.set_variation_by_name("Bold" if weight >= 600 else "Regular")
        except Exception:
            pass


def load_font(kind, size):
    key = (kind, size)
    if key in _font_cache:
        return _font_cache[key]
    if kind == "serif":
        path = os.path.join(FONT_DIR, "CormorantGaramond.ttf")
        font = ImageFont.truetype(path, size)
        _set_axes(font, size, 500)
    else:
        path = os.path.join(FONT_DIR, "Inter.ttf")
        font = ImageFont.truetype(path, size)
        _set_axes(font, size, 700)
    _font_cache[key] = font
    return font


def palette(name):
    return PALETTES.get(name, PALETTES["midnight"])


def mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def scale(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def key_table():
    global _key_cache
    if _key_cache is not None:
        return _key_cache
    usable = W - 2 * KEYBOARD_MARGIN_X
    white_w = usable / 52.0
    keys = []
    white_count = 0
    for pitch in range(LOW_KEY, HIGH_KEY + 1):
        pc = pitch % 12
        if pc in WHITE_PCS:
            x = KEYBOARD_MARGIN_X + white_count * white_w
            keys.append({"pitch": pitch, "black": False, "x": x, "w": white_w,
                         "center": x + white_w / 2})
            white_count += 1
        else:
            bw = white_w * 0.62
            center = KEYBOARD_MARGIN_X + white_count * white_w
            keys.append({"pitch": pitch, "black": True, "x": center - bw / 2, "w": bw,
                         "center": center})
    _key_cache = keys
    return keys


def make_background(palette_name, seed=0):
    pal = palette(palette_name)
    rng = np.random.default_rng(seed + 11)
    top = np.array(pal["bg_top"], dtype=np.float32)
    bottom = np.array(pal["bg_bottom"], dtype=np.float32)
    accent = np.array(pal["accent"], dtype=np.float32)

    y = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None]
    t = y ** 1.25
    grad = top[None, None, :] * (1 - t[:, :, None]) + bottom[None, None, :] * t[:, :, None]
    img = np.repeat(grad, W, axis=1)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W * 0.5) / (W * 0.62)) ** 2 + ((yy - H * 0.18) / (H * 0.55)) ** 2)
    glow = np.clip(1.0 - r, 0, 1)[:, :, None] ** 2.2
    img += accent * glow * 0.095

    band = np.exp(-((yy - (HIT_Y_GLOBAL - 20)) / 130.0) ** 2)[:, :, None]
    img += accent * band * 0.09
    bokeh = rng.random((16, 3))
    for k in range(16):
        bx = rng.uniform(0, W)
        by = rng.uniform(H * 0.1, H * 0.75)
        rad = rng.uniform(90, 260)
        rr = np.sqrt(((xx - bx) / rad) ** 2 + ((yy - by) / rad) ** 2)
        img += accent * np.clip(1 - rr, 0, 1)[:, :, None] ** 2.4 * bokeh[k, 0] * 0.075

    _add_beams(img, accent, yy, xx)

    n_stars = 190
    sx = rng.integers(0, W, n_stars)
    sy = rng.integers(0, int(H * 0.72), n_stars)
    bright = rng.uniform(10, 60, n_stars)
    tint = rng.uniform(0.65, 1.0, n_stars)
    for i in range(n_stars):
        c = accent * (bright[i] / 255.0) * tint[i]
        img[sy[i], sx[i]] = np.clip(img[sy[i], sx[i]] + c, 0, 255)
        if bright[i] > 30:
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                y2, x2 = sy[i] + dy, sx[i] + dx
                if 0 <= y2 < H and 0 <= x2 < W:
                    img[y2, x2] = np.clip(img[y2, x2] + c * 0.35, 0, 255)

    vign = 1.0 - 0.52 * np.clip(r - 0.18, 0, 1) ** 1.5
    img *= vign[:, :, None]
    img += rng.normal(0, 1.6, img.shape)

    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    _draw_brand(pil, pal)
    return pil.convert("RGB")


HIT_Y_GLOBAL = STRIP_Y + KEYBOARD_Y_IN_STRIP


def _add_beams(img, accent, yy, xx):
    """Soft volumetric beams raking down the dark stage."""
    for x_top, slope, width, strength in (
        (W * 0.16, 0.62, 110, 0.050),
        (W * 0.58, -0.38, 150, 0.038),
        (W * 0.86, 0.85, 80, 0.030),
    ):
        d = (yy - slope * (xx - x_top)) / width
        fade = np.clip(1.0 - yy / (H * 1.15), 0.0, 1.0)
        img += accent * (np.exp(-d * d) * fade)[:, :, None] * strength

    haze_y = H * 0.74
    haze = np.exp(-((yy - haze_y) / 240.0) ** 2)[:, :, None]
    img += accent * haze * 0.022


def make_distance_layers(index, work_dir):
    """Screen-space depth stack: blur mask (white = far) and distance dim.

    Both are single-frame PNGs; the section encoder loops them, so they are
    decoded once and reused for every frame.
    """
    os.makedirs(work_dir, exist_ok=True)
    mask_path = os.path.join(work_dir, f"s{index:02d}_dof.png")
    grad_path = os.path.join(work_dir, f"s{index:02d}_dist.png")
    # Focus plane sits just above the keyboard: fully sharp from ~500 px down.
    yy = np.arange(H, dtype=np.float32)[:, None]
    mask_col = (np.clip(1.0 - yy / 500.0, 0.0, 1.0) ** 1.3 * 255).astype(np.uint8)
    Image.fromarray(np.repeat(mask_col, W, axis=1), "L").save(mask_path, compress_level=1)
    grad_col = (np.linspace(0.62, 1.0, H, dtype=np.float32)[:, None] * 255).astype(np.uint8)
    Image.fromarray(np.repeat(grad_col, W, axis=1), "L").save(grad_path, compress_level=1)
    return mask_path, grad_path


def _draw_brand(img, pal):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x, y, size = 62, 46, 34
    logo_path = os.path.join(ASSETS_DIR, "logo.png")
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        circ = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        circ.paste(logo, (0, 0), mask=mask)
        overlay.alpha_composite(circ, (x, y))
    font = load_font("sans", 15)
    tx = x + size + 14
    ty = y + (size - 15) // 2 - 3
    text = "PIANOSPHERIC"
    draw_tracked(draw, tx, ty, text, font, pal["title"] + (185,), tracking=4)
    img.alpha_composite(overlay)


def draw_tracked(draw, x, y, text, font, fill, tracking=0):
    cursor = x
    for ch in text:
        draw.text((cursor, y), ch, font=font, fill=fill)
        cursor += draw.textlength(ch, font=font) + tracking
    return cursor


def make_title_card(section_name, palette_name, width=W, height=H):
    pal = palette(palette_name)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    numeral, _, name = section_name.partition(". ")
    if not name:
        name, numeral = section_name, ""

    f_num = load_font("sans", 19)
    f_name = load_font("serif", 64)

    label = f"MOVEMENT {numeral}".strip()
    label_w = sum(ImageDraw.Draw(img).textlength(c, font=f_num) + 7 for c in label) - 7
    lx = (width - label_w) / 2
    ly = 96
    draw = ImageDraw.Draw(img)
    draw_tracked(draw, lx, ly, label, f_num, pal["accent"] + (215,), tracking=7)

    name_w = draw.textlength(name, font=f_name)
    nx = (width - name_w) / 2
    ny = 124
    draw.text((nx + 2, ny + 2), name, font=f_name, fill=(0, 0, 0, 140))
    draw.text((nx, ny), name, font=f_name, fill=pal["title"] + (255,))

    line_y = ny + 86
    draw.line([(width / 2 - 46, line_y), (width / 2 + 46, line_y)],
              fill=pal["accent"] + (90,), width=1)
    return img


def make_keyboard_base(palette_name):
    pal = palette(palette_name)
    S = 2
    w, h = W * S, STRIP_H * S
    canvas = np.zeros((h, w, 4), dtype=np.uint8)

    kb_y = KEYBOARD_Y_IN_STRIP * S
    kb_h = KEYBOARD_H * S
    floor_y = kb_y + kb_h

    ivory_top = np.array((231, 223, 207), dtype=np.float32)
    ivory_bot = np.array((185, 173, 155), dtype=np.float32)
    grad = np.linspace(0, 1, kb_h, dtype=np.float32)[:, None, None]
    white_grad = ivory_top[None, None, :] * (1 - grad) + ivory_bot[None, None, :] * grad

    keys = key_table()
    for k in keys:
        if k["black"]:
            continue
        x0 = int(round(k["x"] * S))
        x1 = int(round((k["x"] + k["w"]) * S)) - 2
        canvas[kb_y:floor_y, x0:max(x0 + 1, x1), :3] = white_grad
        canvas[kb_y:floor_y, x0:max(x0 + 1, x1), 3] = 255

    sep = np.array((150, 144, 134), dtype=np.uint8)
    for k in keys:
        if k["black"]:
            continue
        x1 = int(round((k["x"] + k["w"]) * S)) - 1
        if 0 <= x1 < w:
            canvas[kb_y:floor_y, x1, :3] = sep
        if 0 <= x1 - 1 < w:
            side = canvas[kb_y:floor_y, x1 - 1, :3].astype(np.float32) * 0.84
            canvas[kb_y:floor_y, x1 - 1, :3] = side.astype(np.uint8)

    black_top = np.array((38, 38, 44), dtype=np.float32)
    black_bot = np.array((12, 12, 16), dtype=np.float32)
    bh = int(kb_h * 0.64)
    bg = np.linspace(0, 1, bh, dtype=np.float32)[:, None, None]
    black_grad = black_top[None, None, :] * (1 - bg) + black_bot[None, None, :] * bg
    for k in keys:
        if not k["black"]:
            continue
        x0 = int(round(k["x"] * S))
        x1 = int(round((k["x"] + k["w"]) * S))
        canvas[kb_y:kb_y + bh, x0:x1, :3] = black_grad
        canvas[kb_y:kb_y + bh, x0:x1, 3] = 255
        canvas[kb_y:kb_y + 3, x0 + 2:x1 - 2, :3] = (108, 108, 118)
        # glossy shoulder and shaded cheek
        canvas[kb_y + 3:kb_y + bh - 6, x0 + 1:x0 + 3, :3] = (72, 72, 82)
        canvas[kb_y + 3:kb_y + bh - 4, x1 - 2:x1, :3] = (20, 20, 24)
        canvas[kb_y + bh - 2:kb_y + bh, x0:x1, :3] = (6, 6, 9)

    shadow = np.linspace(0, 1, kb_y, dtype=np.float32)[:, None] ** 2.0
    canvas[:kb_y, :, :3] = 0
    canvas[:kb_y, :, 3] = (shadow * 110).astype(np.uint8)
    accent = np.array(pal["accent"], dtype=np.float32)
    edge = np.exp(-((np.arange(kb_y) - kb_y) / 26.0) ** 2)[:, None]
    canvas[:kb_y, :, :3] = np.clip(accent[None, None, :] * edge[:, :, None] * 0.05, 0, 255).astype(np.uint8)

    # Felt strip at the back of the keybed: the classic grand-piano detail.
    felt_h = max(2, 5 * S)
    fy = max(0, kb_y - felt_h)
    canvas[fy:kb_y, :, :3] = (54, 17, 20)
    canvas[fy:fy + max(1, S), :, :3] = (96, 32, 36)
    canvas[fy:kb_y, :, 3] = 255

    # Gentle horizontal light falloff across the keybed.
    xf = 1.03 - 0.12 * ((np.linspace(0.0, 1.0, w, dtype=np.float32) - 0.5) * 2.0) ** 2
    keys_roi = canvas[kb_y:floor_y, :, :3].astype(np.float32) * xf[None, :, None]
    canvas[kb_y:floor_y, :, :3] = np.clip(keys_roi, 0, 255).astype(np.uint8)

    floor_grad = np.linspace(0, 1, h - floor_y, dtype=np.float32)[:, None, None]
    floor_col = (np.array((12, 12, 15), np.float32)[None, None, :] * (1 - floor_grad)
                 + np.array((4, 4, 6), np.float32)[None, None, :] * floor_grad)
    canvas[floor_y:, :, :3] = floor_col.astype(np.uint8)
    canvas[floor_y:, :, 3] = 255
    canvas[floor_y:floor_y + 2, :, :3] = (34, 34, 40)
    glow_line = np.exp(-((np.arange(h - floor_y) - 6) / 12.0) ** 2)[:, None, None]
    canvas[floor_y:, :, :3] = np.clip(
        canvas[floor_y:, :, :3].astype(np.float32) + accent[None, None, :] * glow_line * 0.05, 0, 255
    ).astype(np.uint8)

    pil = Image.fromarray(canvas, "RGBA").resize((W, STRIP_H), Image.Resampling.LANCZOS)
    return np.array(pil, dtype=np.uint8)


def make_glow_sprite(size=48):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    alpha = np.clip(1.0 - r, 0, 1) ** 2.0
    return alpha.astype(np.float32)


def make_spark_sprite(size=14):
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2.0
    r = np.sqrt((xx - c) ** 2 + (yy - c) ** 2) / c
    return np.clip(1.0 - r, 0, 1) ** 2.4


def make_hero_frame(video_path, out_path, timestamp):
    from config import FFMPEG
    import subprocess
    cmd = [FFMPEG, "-y", "-v", "error", "-ss", f"{timestamp:.2f}", "-i", video_path,
           "-frames:v", "1", "-q:v", "2", out_path]
    subprocess.run(cmd, check=True)
    return out_path
