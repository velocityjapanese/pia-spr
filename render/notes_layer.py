"""Per-section tall piano-roll bitmap: glass ribbons with baked bloom."""
import numpy as np
from PIL import Image

from config import H, HIT_Y, SCROLL_PX_PER_FRAME, SCROLL_PX_PER_SEC, W
from render.scene import key_table, palette, scale

FALL_SECONDS = (H - HIT_Y) / SCROLL_PX_PER_SEC

CAP_ROWS = 9          # rounded end rows
RIM_F = 1.00          # bright glass edge
BODY_F = 0.64         # translucent interior
SPEC_F = 0.16         # inner specular streak


def render_roll(section, notes, out_path):
    frames = section["frames"]
    h_tall = H + frames * SCROLL_PX_PER_FRAME
    roll = np.zeros((h_tall, W, 3), dtype=np.uint16)

    pal = palette(section["palette"])
    keys = {k["pitch"]: k for k in key_table()}
    sec_start = section["start"]
    sec_end = section["end"]

    by_pitch = {}
    for n in notes:
        if n["start"] > sec_end + FALL_SECONDS + 0.5:
            continue
        if n["end"] < sec_start - 0.6:
            continue
        by_pitch.setdefault(n["pitch"], []).append(n)

    for pitch, group in by_pitch.items():
        key = keys.get(pitch)
        if key is None:
            continue
        group.sort(key=lambda n: n["start"])
        spans = []
        for n in group:
            if spans and n["start"] < spans[-1]["end"]:
                # Overlapping same-pitch notes would stack additively and clip
                # to white, so render them as one span at the highest velocity.
                spans[-1]["end"] = max(spans[-1]["end"], n["end"])
                spans[-1]["vel"] = max(spans[-1]["vel"], n["vel"])
            else:
                spans.append(dict(n))

        for n in spans:
            tau = n["start"] - sec_start
            y_bottom = int(round(h_tall - (H - HIT_Y) - SCROLL_PX_PER_SEC * tau))
            height = max(12, int(round((n["end"] - n["start"]) * SCROLL_PX_PER_SEC)))
            y_top = y_bottom - height

            if y_bottom < 0 or y_top > h_tall:
                continue
            y0c = max(0, y_top)
            y1c = min(h_tall, y_bottom)
            if y1c <= y0c:
                continue

            base = pal["lh"] if n["hand"] == "L" else pal["rh"]
            vf = 0.55 + 0.45 * (n["vel"] / 127.0)
            core = np.array(scale(base, (vf + 0.12) * 1.28), dtype=np.float32)
            halo = np.array(scale(base, vf * 0.66), dtype=np.float32)

            w = max(13, int(round(key["w"] * 0.84)))
            cx = int(round(key["center"]))
            x0 = cx - w // 2
            x1 = x0 + w

            # Side bloom. The glass body is screened (not added) so adjacent
            # keys never stack into a flat white band.
            _add_rect(roll, x0 - 9, x0, y0c, y1c, halo, 0.30)
            _add_rect(roll, x1, x1 + 9, y0c, y1c, halo, 0.30)
            _add_rect(roll, x0 - 3, x0, y0c, y1c, halo, 0.50)
            _add_rect(roll, x1, x1 + 3, y0c, y1c, halo, 0.50)

            # Soft cap bloom at both ends.
            if y0c > 8:
                _add_rect(roll, x0 + 3, x1 - 3, y0c - 7, y0c, halo, 0.38)
            if y1c < h_tall - 8:
                _add_rect(roll, x0 + 3, x1 - 3, y1c, y1c + 7, halo, 0.38)

            f_top = 0.58 + 0.38 * vf      # leading edge glows toward the keys
            f_bot = 0.34 + 0.36 * vf
            _add_ribbon(roll, x0, x1, y0c, y1c, core, f_top, f_bot, cap=CAP_ROWS)

    rgb = np.clip(roll, 0, 255).astype(np.uint8)
    del roll
    Image.fromarray(rgb, "RGB").save(out_path, "PNG", compress_level=1)
    return out_path


def _ribbon_profile(width):
    """Horizontal intensity: bright rims, translucent body, inner specular."""
    prof = np.full(width, BODY_F, dtype=np.float32)
    if width >= 7:
        prof[0] = 0.30
        prof[1] = RIM_F
        prof[width - 2] = RIM_F
        prof[width - 1] = 0.30
        spec = max(3, int(width * 0.34))
        prof[spec:spec + 2] += SPEC_F
    elif width >= 3:
        prof[0] = 0.60
        prof[width - 1] = 0.60
        prof[width // 2] += SPEC_F
    return np.clip(prof, 0, 1)


def _cap_mask(height, width, cap):
    """Multiplicative mask that rounds both ends of a ribbon."""
    mask = np.ones((height, width), dtype=np.float32)
    cap = int(min(cap, height // 2, max(2, width // 2)))
    if cap < 2:
        return mask
    for i in range(cap):
        # circular inset, softened toward the tip
        t = (i + 1) / cap
        inset = int(round(cap * (1.0 - np.sqrt(max(0.0, 1.0 - (1.0 - t) ** 2)))))
        fade = 0.40 + 0.60 * t
        for row in (i, height - 1 - i):
            if inset:
                mask[row, :inset] = 0.0
                mask[row, width - inset:] = 0.0
            mask[row] *= fade
    return mask


def _add_ribbon(roll, x0, x1, y0, y1, color, head_f, tail_f, cap=CAP_ROWS):
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(roll.shape[1], x1)
    y1 = min(roll.shape[0], y1)
    if x1 <= x0 or y1 <= y0:
        return
    width = x1 - x0
    height = y1 - y0

    vp = np.linspace(head_f, tail_f, height, dtype=np.float32)
    hp = _ribbon_profile(width)
    add = color[None, None, :] * (vp[:, None, None] * hp[None, :, None])
    if height >= 2 * cap and width >= 4:
        add *= _cap_mask(height, width, cap)[:, :, None]

    add = np.clip(add, 0, 255).astype(np.uint16)
    roi = roll[y0:y1, x0:x1]
    roi[:] = 255 - ((255 - roi) * (255 - add)) // 255


def _add_rect(roll, x0, x1, y0, y1, color, intensity):
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(roll.shape[1], x1)
    y1 = min(roll.shape[0], y1)
    if x1 <= x0 or y1 <= y0:
        return
    add = np.clip(color[None, None, :] * intensity, 0, 255).astype(np.uint16)
    roi = roll[y0:y1, x0:x1]
    roi[:] = 255 - ((255 - roi) * (255 - add)) // 255
