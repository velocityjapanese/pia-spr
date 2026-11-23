"""Note-accurate playhead and note glow for the scrolling paper score.

The sheet crawls slowly while a system plays, then scrolls the next system
into place before its first note. The playhead glides from notehead to
notehead using Verovio's own time->position map, so it sits on the sounding
note instead of drifting at a fixed scroll rate. Sounding noteheads get a soft
blue halo, which reads as a highlighter on the cream paper without hiding the
ink.

Frames are sparse RGBA (transparent except the playhead and glows), encoded
losslessly with qtrle so the main ffmpeg can overlay them on the paper page.
"""
import bisect
import json
import os
import subprocess

import numpy as np

from config import FFMPEG, FPS
from render.score_layer import WIN_H, WIN_W

LINE_RADIUS = 5
_LINE_ALPHA = (0, 45, 105, 165, 215, 255, 215, 165, 105, 45, 0)
_CORE_RGB = (92, 40, 28)

GLOW_W, GLOW_H = 58, 44
GLOW_IN = 0.10                   # seconds to ramp a new onset up
GLOW_OUT = 0.22                  # seconds to let a released onset fade
_GLOW_RGB = (86, 158, 214)          # soft blue, so it stands off the warm paper


def _glow_mask():
    """Soft warm halo: wide enough to read as light, not as an orange bubble."""
    yy, xx = np.mgrid[-1:1:complex(GLOW_H), -1:1:complex(GLOW_W)]
    r = np.sqrt(xx ** 2 + (yy * 1.18) ** 2)
    ring = np.exp(-((r - 0.50) / 0.32) ** 2) * 85.0
    halo = np.clip(1.0 - r, 0.0, 1.0) ** 2 * 34.0
    return np.clip(ring + halo, 0.0, 120.0).astype(np.float32)


GLOW = _glow_mask()


def cursor_video_path(work_dir, index):
    return os.path.join(work_dir, f"s{index:02d}_cursor.mov")


def build_cursor_video(section, notes_path, work_dir):
    try:
        return _build(section, notes_path, work_dir)
    except Exception as exc:
        print(f"[score] section {section['index']}: cursor disabled ({exc})")
        return None


def _build(section, notes_path, work_dir):
    with open(notes_path, encoding="utf-8") as fh:
        data = json.load(fh)
    systems = [s for s in data["systems"] if s["onsets"]]
    if not systems:
        return None
    for s in systems:
        s["onsets"].sort(key=lambda o: o["t"])
        s["times"] = [o["t"] for o in s["onsets"]]
    starts = [s["start"] for s in systems]
    scroll_meta = {
        "pad": float(data.get("pad", 0.0)),
        "drift": float(data.get("drift", 0.0)),
        "drift_max": float(data.get("drift_max", 0.0)),
        "transition": float(data.get("transition", 0.0)),
    }

    accent = np.array((156, 74, 46), dtype=np.float32)
    core = np.array((96, 42, 30), dtype=np.float32)
    t0 = float(section["start"])
    frames = int(section["frames"])
    out = cursor_video_path(work_dir, section["index"])

    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgba",
           "-s", f"{WIN_W}x{WIN_H}", "-framerate", str(FPS),
           "-i", "pipe:0", "-c:v", "qtrle", "-pix_fmt", "rgba",
           "-r", str(FPS), out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for n in range(frames):
            t = t0 + n / FPS
            layer = _compose(t, systems, starts, accent, core, scroll_meta)
            proc.stdin.write(layer.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError(f"cursor encode failed ({proc.returncode})")
    return out


def _scroll_y(t, idx, systems, meta):
    """Same staircase scroll as the ffmpeg crop expression."""
    sys_ = systems[idx]
    pad = meta["pad"]
    drift = meta["drift"]
    y0 = sys_["roll_y"] - pad
    s0 = sys_["start"]
    s1 = sys_.get("end")
    if s1 is None or idx >= len(systems) - 1:
        return y0 + drift * (t - s0)
    trans_start = max(s0, s1 - meta["transition"])
    if t < trans_start:
        return y0 + min(drift * (t - s0), meta["drift_max"])
    y_end = y0 + min(drift * (trans_start - s0), meta["drift_max"])
    target_next = systems[idx + 1]["roll_y"] - pad
    p = min(1.0, max(0.0, (t - trans_start) / meta["transition"]))
    smooth = p * p * (3 - 2 * p)
    return y_end + (target_next - y_end) * smooth


def _compose(t, systems, starts, accent, core, scroll_meta):
    layer = np.zeros((WIN_H, WIN_W, 4), dtype=np.float32)

    # The system currently under the cursor. bisect_right makes the boundary
    # frame belong to the next system, matching the scroll expression.
    idx = bisect.bisect_right(starts, t) - 1
    if idx < 0:
        idx = 0
    idx = min(idx, len(systems) - 1)
    sys_ = systems[idx]
    times = sys_["times"]
    scroll = _scroll_y(t, idx, systems, scroll_meta)

    img_x = sys_["img_x"]
    img_w = sys_["img_w"]
    img_h = sys_["img_h"]
    y_top = sys_["roll_y"] - scroll
    y_bot = y_top + img_h
    if y_bot < 0 or y_top > WIN_H:
        return np.clip(layer, 0, 255).astype(np.uint8)

    # Glide from the last sounding onset to the next one.
    pos = bisect.bisect_right(times, t) - 1
    if pos < 0:
        x_norm = sys_["onsets"][0]["x"]
    else:
        current = sys_["onsets"][pos]
        x_norm = current["x"]
        if pos + 1 < len(times):
            nxt = sys_["onsets"][pos + 1]
            span = nxt["t"] - current["t"]
            if span > 1e-6:
                p = min(1.0, max(0.0, (t - current["t"]) / span))
                smooth = p * p * (3 - 2 * p)
                x_norm = current["x"] + (nxt["x"] - current["x"]) * smooth

    # Teal glow on every notehead that is currently sounding. A held chord
    # keeps glowing until the last note of the chord is released.
    for onset in sys_["onsets"]:
        start = onset["t"]
        hold = onset.get("hold", start + 0.4)
        if t < start or t > hold + GLOW_OUT:
            continue
        mul = min(1.0, (t - start) / GLOW_IN if GLOW_IN else 1.0,
                  (hold + GLOW_OUT - t) / GLOW_OUT if GLOW_OUT else 1.0)
        if mul <= 0.0:
            continue
        for hx, hy in onset["heads"]:
            cx = int(round(img_x + hx * img_w))
            cy = int(round(y_top + hy * img_h))
            _paste_glow(layer, cx, cy, mul)

    # Playhead line on top of the glows.
    cx = int(round(img_x + x_norm * img_w))
    _draw_line(layer, cx, y_top, y_bot, accent, core)

    return np.clip(layer, 0, 255).astype(np.uint8)


def _paste_glow(layer, cx, cy, mul):
    x0 = cx - GLOW_W // 2
    y0 = cy - GLOW_H // 2
    x1, y1 = x0 + GLOW_W, y0 + GLOW_H
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(WIN_W, x1), min(WIN_H, y1)
    if x1 <= x0 or y1 <= y0:
        return
    mask = GLOW[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)] * np.float32(mul)
    sub = layer[y0:y1, x0:x1]
    sub[..., 3] = np.maximum(sub[..., 3], mask)
    hit = mask > 0.5
    for c in range(3):
        sub[..., c] = np.where(hit, _GLOW_RGB[c], sub[..., c])


def _draw_line(layer, cx, y_top, y_bot, accent, core):
    y0 = max(0, int(y_top))
    y1 = min(WIN_H, int(y_bot))
    if y1 <= y0:
        return
    rows = np.arange(y0, y1, dtype=np.float32)
    taper = np.minimum(1.0, (rows - y_top + 1) / 14.0)
    taper = np.minimum(taper, (y_bot - rows) / 14.0).clip(0.0, 1.0)
    for dx, base in enumerate(_LINE_ALPHA):
        if base <= 0:
            continue
        x = cx - LINE_RADIUS + dx
        if not 0 <= x < WIN_W:
            continue
        alpha = (base * taper).astype(np.float32)
        col = layer[y0:y1, x]
        col[..., 3] = np.maximum(col[..., 3], alpha)
        rgb = core if abs(dx - LINE_RADIUS) <= 1 else accent
        hit = alpha > 0
        for c in range(3):
            col[..., c] = np.where(hit, rgb[c], col[..., c])
