"""Per-frame 88-key keyboard strip with press glow and rising sparks.

Frames are generated in numpy and streamed as rgb24 rawvideo into ffmpeg,
so nothing touches disk for the animation layer.
"""
import math
import queue
import random
import threading

import numpy as np

from config import FPS, KEYBOARD_H, KEYBOARD_Y_IN_STRIP, W
from render.scene import key_table, make_glow_sprite, make_keyboard_base, make_spark_sprite, palette

KB_TOP = KEYBOARD_Y_IN_STRIP
KB_BOTTOM = KEYBOARD_Y_IN_STRIP + KEYBOARD_H


def _clip_add(roi, add):
    roi[:] = np.minimum(roi.astype(np.uint16) + add.astype(np.uint16), 255).astype(np.uint8)


class StripGenerator:
    def __init__(self, section, notes, seed=0):
        pal = palette(section["palette"])
        self.base = make_keyboard_base(section["palette"])
        self.keys = {k["pitch"]: k for k in key_table()}
        self.key_color = np.array(pal["key_glow"], dtype=np.float32)
        self.spark_color = np.array(pal["accent"], dtype=np.float32)
        self.glow = make_glow_sprite(96)
        self.spark = make_spark_sprite(14)
        self.section = section
        self.rng = random.Random(seed * 7919 + section["index"] * 104729)

        sec_start, sec_end = section["start"], section["end"]
        self.notes = [n for n in notes if n["start"] <= sec_end and n["end"] >= sec_start - 0.4]
        self.active = []
        self.next_idx = 0
        self.particles = []
        self.frame_events = {}
        for n in self.notes:
            f = int(round((n["start"] - sec_start) * FPS))
            if 0 <= f < section["frames"]:
                self.frame_events.setdefault(f, []).append(n)

    def frames(self):
        sec = self.section
        frames = sec["frames"]
        dt = 1.0 / FPS
        for i in range(frames):
            t = sec["start"] + i * dt
            strip = self.base.copy()
            pressed = self._pressed(t)
            for pitch, intensity in pressed.items():
                self._paint_key(strip, pitch, intensity)

            for n in self.frame_events.get(i, ()):
                self._spawn(n, t)
            self._update_particles(strip, dt)
            yield strip.tobytes()

    def _pressed(self, t):
        while self.next_idx < len(self.notes) and self.notes[self.next_idx]["start"] <= t:
            self.active.append(self.notes[self.next_idx])
            self.next_idx += 1
        self.active = [n for n in self.active if n["end"] + 0.25 >= t]
        pressed = {}
        for n in self.active:
            if t < n["start"]:
                continue
            rel = t - n["start"]
            attack = min(1.0, rel / 0.012)
            sustain = 0.5 + 0.5 * math.exp(-rel / 0.55)
            value = attack * sustain * (n["vel"] / 127.0)
            if t > n["end"]:
                value *= math.exp(-(t - n["end"]) / 0.13)
            if value > pressed.get(n["pitch"], 0.0):
                pressed[n["pitch"]] = value
        return pressed

    def _paint_key(self, strip, pitch, intensity):
        key = self.keys.get(pitch)
        if key is None:
            return
        x0 = max(0, int(key["x"]))
        x1 = min(W, int(key["x"] + key["w"]))
        y0, y1 = KB_TOP, KB_BOTTOM
        if key["black"]:
            y1 = KB_TOP + int(KEYBOARD_H * 0.64)

        body = self.key_color * (intensity * 0.55)
        _clip_add(strip[y0:y1, x0:x1, :3], body)

        if y1 - y0 > 6:
            band = np.broadcast_to((self.key_color * intensity * 0.9).astype(np.uint16),
                                   (4, x1 - x0, 3))
            _clip_add(strip[y0:y0 + 4, x0:x1, :3], band)

        cx = int(key["center"])
        gx0 = max(0, cx - 48)
        gy0 = max(0, KB_TOP - 72)
        gx1 = min(W, cx + 48)
        gy1 = min(strip.shape[0], KB_TOP + 26)
        gh, gw = gy1 - gy0, gx1 - gx0
        if gh > 0 and gw > 0:
            sy = (np.arange(gh) + (gy0 - (KB_TOP - 72))) / 96.0
            sx = (np.arange(gw) + (gx0 - (cx - 48))) / 96.0
            alpha = self.glow[(np.clip(sy * 95, 0, 95)).astype(int)][:, (np.clip(sx * 95, 0, 95)).astype(int)]
            add = (alpha[:, :, None] * self.key_color[None, None, :] * intensity * 1.15).astype(np.uint16)
            _clip_add(strip[gy0:gy1, gx0:gx1, :3], add)

        # Polished fallboard: a wide, soft echo of the key light above the keys.
        rx0 = max(0, cx - 92)
        rx1 = min(W, cx + 92)
        ry0 = max(0, KB_TOP - 152)
        ry1 = KB_TOP - 34
        rh, rw = ry1 - ry0, rx1 - rx0
        if rh > 0 and rw > 0:
            sy = (np.arange(rh) + (ry0 - (KB_TOP - 152))) / 150.0
            sx = (np.arange(rw) + (rx0 - (cx - 92))) / 184.0
            alpha = self.glow[(np.clip(sy * 95, 0, 95)).astype(int)][:, (np.clip(sx * 95, 0, 95)).astype(int)]
            add = (alpha[:, :, None] * self.key_color[None, None, :] * intensity * 0.34).astype(np.uint16)
            _clip_add(strip[ry0:ry1, rx0:rx1, :3], add)

    def _spawn(self, note, t):
        key = self.keys.get(note["pitch"])
        if key is None:
            return
        count = 2 + int(note["vel"] / 55)
        for _ in range(count):
            self.particles.append({
                "x": key["center"] + self.rng.uniform(-key["w"] * 0.45, key["w"] * 0.45),
                "y": KB_TOP - self.rng.uniform(2, 14),
                "vx": self.rng.uniform(-24, 24),
                "vy": -self.rng.uniform(70, 180),
                "life": self.rng.uniform(0.45, 0.95),
                "age": 0.0,
                "size": self.rng.uniform(0.45, 0.95),
            })

    def _update_particles(self, strip, dt):
        alive = []
        sprite = self.spark
        sh = sprite.shape[0]
        for p in self.particles:
            p["age"] += dt
            if p["age"] >= p["life"]:
                continue
            p["x"] += p["vx"] * dt
            p["vy"] += 42 * dt
            p["y"] += p["vy"] * dt
            life = 1.0 - p["age"] / p["life"]
            x = int(p["x"])
            y = int(p["y"])
            half = sh // 2
            x0, y0 = x - half, y - half
            x1, y1 = x0 + sh, y0 + sh
            if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= strip.shape[0]:
                continue
            cx0, cy0 = max(0, x0), max(0, y0)
            cx1, cy1 = min(W, x1), min(strip.shape[0], y1)
            sub = sprite[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
            add = (sub[:, :, None] * self.spark_color[None, None, :]
                   * (life ** 1.4) * 210).astype(np.uint16)
            _clip_add(strip[cy0:cy1, cx0:cx1, :3], add)
            alive.append(p)
        self.particles = alive


class PipeWriter:
    """Writes frames to a subprocess stdin on a background thread."""

    def __init__(self, stream, maxsize=4):
        self.stream = stream
        self.q = queue.Queue(maxsize=maxsize)
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def write(self, data):
        while not self.error:
            try:
                self.q.put(data, timeout=0.5)
                return
            except queue.Full:
                continue

    def close(self):
        while True:
            try:
                self.q.put(None, timeout=0.5)
                break
            except queue.Full:
                continue
        self.thread.join()

    def _run(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            if self.error is not None:
                continue
            try:
                self.stream.write(item)
            except (BrokenPipeError, ValueError, OSError) as exc:
                self.error = exc


def stream_section(section, notes, stream, seed=0):
    gen = StripGenerator(section, notes, seed)
    writer = PipeWriter(stream)
    try:
        for frame in gen.frames():
            writer.write(frame)
    finally:
        writer.close()
        try:
            stream.close()
        except Exception:
            pass
