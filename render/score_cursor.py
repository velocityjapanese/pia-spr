"""Note-accurate follow cursor for the score panel.

The panel scrolls at a constant speed, but engraved notation does not space
notes evenly in time, so a fixed playhead line cannot point at the sounding
note. This module draws a cursor using Verovio's own time->position map: at
every onset the cursor sits exactly on that notehead, and between onsets it
glides to the next one.

Frames are sparse RGBA (transparent except the cursor), encoded losslessly
with qtrle so the main ffmpeg can overlay them on the notation strip.
"""
import bisect
import json
import os
import subprocess

import numpy as np

from config import FFMPEG, FPS
from render.scene import palette
from render.score_layer import SPEED, WIN_H, WIN_W

GLOW_W, GLOW_H = 63, 43
LINE_RADIUS = 5
GLOW_IN = 0.12                   # seconds to ramp a new onset up
GLOW_OUT = 0.20                  # seconds to let a released onset fade
_LINE_ALPHA = (0, 45, 105, 165, 215, 255, 215, 165, 105, 45, 0)
_CORE_RGB = (255, 249, 252)


def _glow_mask():
    yy, xx = np.mgrid[-1:1:complex(GLOW_H), -1:1:complex(GLOW_W)]
    r2 = xx ** 2 + (yy * 1.3) ** 2
    halo = np.clip(1.0 - r2, 0.0, 1.0) ** 1.6 * 185.0
    core = np.clip(1.0 - (xx / 0.34) ** 2 - (yy / 0.42) ** 2, 0.0, 1.0) ** 0.8 * 255.0
    return halo.astype(np.float32), core.astype(np.float32)


GLOW, CORE = _glow_mask()


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

    accent = palette(section["palette"])["accent"]
    accent = np.array(accent, dtype=np.float32)
    core = np.array((255, 246, 250), dtype=np.float32)
    t0 = float(section["start"])
    frames = int(section["frames"])
    out = cursor_video_path(work_dir, section["index"])

    flat = []
    for si, s in enumerate(systems):
        for o in s["onsets"]:
            o.setdefault("hold", o["t"] + 0.4)
            flat.append((o["t"], o["hold"], si, o))
    flat.sort(key=lambda r: r[0])
    state = {"k": 0, "live": []}

    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgba",
           "-s", f"{WIN_W}x{WIN_H}", "-framerate", str(FPS),
           "-i", "pipe:0", "-c:v", "qtrle", "-pix_fmt", "rgba",
           "-r", str(FPS), out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for n in range(frames):
            t = t0 + n / FPS
            layer = _compose(t, t0, systems, starts, accent, core, flat, state)
            proc.stdin.write(layer.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode:
        raise RuntimeError(f"cursor encode failed ({proc.returncode})")
    return out


def _compose(t, t0, systems, starts, accent, core, flat, state):
    layer = np.zeros((WIN_H, WIN_W, 4), dtype=np.float32)
    scroll = (t - t0) * SPEED

    # Every onset still sounding keeps its noteheads lit, so a held chord
    # stays highlighted until the notes are actually released.
    k = state["k"]
    live = [a for a in state["live"] if a[1] + GLOW_OUT >= t]
    while k < len(flat) and flat[k][0] <= t:
        if flat[k][1] + GLOW_OUT >= t:
            live.append(flat[k])
        k += 1
    state["k"] = k
    state["live"] = live
    for ot, hold, si, onset in live:
        sys_ = systems[si]
        y_top = sys_["roll_y"] - scroll
        if y_top + sys_["img_h"] < 0 or y_top > WIN_H:
            continue
        mul = min(1.0, (t - ot) / GLOW_IN, (hold + GLOW_OUT - t) / GLOW_OUT)
        if mul <= 0.0:
            continue
        for hx, hy in onset["heads"]:
            cx = int(round(sys_["img_x"] + hx * sys_["img_w"]))
            cy = int(round(y_top + hy * sys_["img_h"]))
            _paste_glow(layer, cx, cy, accent, mul)

    idx = bisect.bisect_right(starts, t) - 1
    if idx < 0:
        idx = 0
    sys_ = systems[min(idx, len(systems) - 1)]
    times = sys_["times"]

    # Glide from the last sounding onset to the next one.
    pos = bisect.bisect_right(times, t) - 1
    if pos < 0:
        x_norm = sys_["onsets"][0]["x"]
    else:
        current = sys_["onsets"][pos]
        x_norm = current["x"]
        if pos + 1 < len(sys_["onsets"]):
            nxt = sys_["onsets"][pos + 1]
            span = nxt["t"] - current["t"]
            if span > 1e-6:
                p = min(1.0, max(0.0, (t - current["t"]) / span))
                smooth = p * p * (3 - 2 * p)
                x_norm = current["x"] + (nxt["x"] - current["x"]) * smooth

    y_top = sys_["roll_y"] - scroll
    y_bot = y_top + sys_["img_h"]
    if y_bot < 0 or y_top > WIN_H:
        return np.clip(layer, 0, 255).astype(np.uint8)

    # Vertical cursor line through the staff.
    cx = int(round(sys_["img_x"] + x_norm * sys_["img_w"]))
    _draw_line(layer, cx, y_top, y_bot, accent, core)

    return np.clip(layer, 0, 255).astype(np.uint8)


def _paste_glow(layer, cx, cy, accent, mul=1.0):
    x0 = cx - GLOW_W // 2
    y0 = cy - GLOW_H // 2
    x1, y1 = x0 + GLOW_W, y0 + GLOW_H
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(WIN_W, x1), min(WIN_H, y1)
    if x1 <= x0 or y1 <= y0:
        return
    mask = GLOW[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
    core = CORE[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
    sub = layer[y0:y1, x0:x1]
    sub[..., 3] = np.maximum(sub[..., 3],
                             np.maximum(mask, core) * np.float32(mul))
    hit = mask > 0
    for c in range(3):
        sub[..., c] = np.where(hit, accent[c], sub[..., c])
    chit = core > 0
    for c in range(3):
        sub[..., c] = np.where(chit, _CORE_RGB[c], sub[..., c])


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
