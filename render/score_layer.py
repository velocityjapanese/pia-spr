"""Engraved, time-synced score strip for the floating score panel.

The notation is built from the same notes the audio is rendered from, so the
staff and the performance cannot drift. Each section is engraved once into a
tall RGBA strip; ffmpeg crops it at a constant rate, putting every bar under
the playhead exactly when it sounds.
"""
import io
import os
from collections import defaultdict

import music21
import resvg_py
import verovio
from PIL import Image, ImageDraw, ImageFilter

from config import FPS
from render.scene import load_font, palette

PANEL_X, PANEL_Y = 960, 52
PANEL_W, PANEL_H = 888, 372
FRAME_PAD = 26
HEADER_H = 46
INSET = 16
WIN_X = PANEL_X + INSET
WIN_Y = PANEL_Y + HEADER_H
WIN_W = PANEL_W - 2 * INSET
WIN_H = PANEL_H - HEADER_H - INSET
SPEED = 18.0                     # score pixels per second
CROP_EXPR = f"(n*{int(SPEED)}/{FPS})"
PLAYHEAD = 0.34
TARGET_SYSTEM_SEC = 10.5
QUANT = 0.25                     # 16th-note grid

SCORE_RGB = (236, 242, 250)
PANEL_RGB = (10, 13, 20)
PANEL_ALPHA = 202

_VEROVIO_OPTS = {
    "pageWidth": 1100,
    "pageHeight": 380,
    "scale": 60,
    "adjustPageHeight": 1,
    "header": "none",
    "footer": "none",
    "breaks": "none",
    "font": "Leipzig",
    "pageMarginTop": 0,
    "pageMarginBottom": 0,
    "pageMarginLeft": 0,
    "pageMarginRight": 0,
}


def panel_paths(work_dir, index):
    stem = os.path.join(work_dir, f"s{index:02d}_score")
    return stem + "_roll.png", stem + "_frame.png"


def build_score_assets(section, notes, work_dir):
    """Return (roll_png, frame_png) or None if engraving is unavailable."""
    try:
        return _build(section, notes, work_dir)
    except Exception as exc:
        print(f"[score] section {section['index']}: score panel disabled ({exc})")
        return None


def _build(section, notes, work_dir):
    key_name = section.get("key") or "C major"
    tonic, _, mode = key_name.partition(" ")
    key_sig = music21.key.Key(tonic, mode or "major").sharps
    bpm = float(section["bpm"])
    sec_dur = float(section["end"]) - float(section["start"])
    bar_sec = 240.0 / bpm
    total_bars = max(1, int(round(sec_dur / bar_sec)))
    target = max(1, min(6, int(round(TARGET_SYSTEM_SEC / bar_sec))))
    systems = max(1, int(round(total_bars / target)))
    base, extra = divmod(total_bars, systems)
    sizes = [base + 1] * extra + [base] * (systems - extra)

    pad = int(round(WIN_H * PLAYHEAD))
    height = pad + int(round(sec_dur * SPEED)) + WIN_H + 8
    roll = Image.new("RGBA", (WIN_W, height), PANEL_RGB + (PANEL_ALPHA,))

    bar_start = 0
    for count in sizes:
        bar_end = bar_start + count
        sys_start = bar_start * bar_sec
        sys_dur = (bar_end - bar_start) * bar_sec
        block_h = max(48, int(round(sys_dur * SPEED)))

        img = _engrave_system(section, notes, bar_start, bar_end, key_sig, bpm,
                              work_dir)
        bar_start = bar_end
        if img is None:
            continue

        max_w, max_h = WIN_W - 26, max(24, block_h - 12)
        scale = min(max_w / img.width, max_h / img.height)
        scale = max(0.35, min(scale, 1.35))
        if abs(scale - 1.0) > 0.01:
            img = img.resize((max(1, int(img.width * scale)),
                              max(1, int(img.height * scale))),
                             Image.Resampling.LANCZOS)

        x = (WIN_W - img.width) // 2
        y = pad + int(round(sys_start * SPEED)) + max(0, (block_h - img.height) // 2)
        roll.alpha_composite(img, (x, y))

    roll_path, frame_path = panel_paths(work_dir, section["index"])
    roll.save(roll_path)
    _make_frame(section, bpm, key_name).save(frame_path)
    return roll_path, frame_path


def _engrave_system(section, notes, bar_start, bar_end, key_sig, bpm, work_dir):
    start_beat = bar_start * 4.0
    end_beat = bar_end * 4.0
    beat_sec = 60.0 / bpm
    sec_start = float(section["start"])

    rh = music21.stream.Part(id="RH")
    lh = music21.stream.Part(id="LH")
    for part, clef in ((rh, music21.clef.TrebleClef()),
                       (lh, music21.clef.BassClef())):
        part.append(clef)
        part.append(music21.meter.TimeSignature("4/4"))
        part.append(music21.key.KeySignature(key_sig))

    groups = defaultdict(list)
    for note in notes:
        local = (note["start"] - sec_start) / beat_sec
        if local < start_beat - QUANT or local >= end_beat:
            continue
        offset = round(local / QUANT) * QUANT
        if offset < start_beat:
            offset = start_beat
        if offset >= end_beat:
            continue
        dur = max(QUANT, round((note["end"] - note["start"]) / beat_sec / QUANT) * QUANT)
        dur = min(dur, end_beat - offset)
        groups[(note["hand"], offset - start_beat)].append((note["pitch"], dur))

    if not groups:
        return None

    for (hand, offset), items in groups.items():
        part = rh if hand == "R" else lh
        pitches = sorted({pitch for pitch, _ in items})
        dur = max(value for _, value in items)
        if len(pitches) == 1:
            element = music21.note.Note(pitches[0], quarterLength=dur)
        else:
            element = music21.chord.Chord(pitches, quarterLength=dur)
        part.insert(offset, element)

    for part in (rh, lh):
        part.makeMeasures(inPlace=True)

    score = music21.stream.Score()
    score.insert(0, rh)
    score.insert(0, lh)
    score.insert(0, music21.layout.StaffGroup([rh, lh], name="",
                                              symbol="brace",
                                              barTogether="Mensurstrich"))

    xml_path = os.path.join(work_dir,
                            f"score_tmp_{section['index']}_{bar_start}.xml")
    score.write("musicxml", xml_path)
    try:
        tk = verovio.toolkit()
        tk.setOptions(_VEROVIO_OPTS)
        tk.loadFile(xml_path)
        svg = tk.renderToSVG(1)
        png = resvg_py.svg_to_bytes(svg_string=svg)
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass

    glyphs = Image.open(io.BytesIO(png)).convert("RGBA")
    white = Image.new("RGBA", glyphs.size, SCORE_RGB + (255,))
    white.putalpha(glyphs.getchannel("A"))
    return white


def _make_frame(section, bpm, key_name):
    pal = palette(section["palette"])
    canvas = Image.new("RGBA", (PANEL_W + 2 * FRAME_PAD,
                                PANEL_H + 2 * FRAME_PAD), (0, 0, 0, 0))

    shadow = Image.new("RGBA", (PANEL_W, PANEL_H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (0, 0, PANEL_W - 1, PANEL_H - 1), radius=16, fill=(0, 0, 0, 155))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    canvas.alpha_composite(shadow, (FRAME_PAD - 4, FRAME_PAD + 6))

    img = Image.new("RGBA", (PANEL_W, PANEL_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((0, 0, PANEL_W - 1, PANEL_H - 1), radius=14,
                           fill=PANEL_RGB + (235,))
    draw.rectangle((INSET, HEADER_H, INSET + WIN_W - 1, HEADER_H + WIN_H - 1),
                   fill=(0, 0, 0, 0))
    draw.rounded_rectangle((0, 0, PANEL_W - 1, PANEL_H - 1), radius=14,
                           outline=pal["accent"] + (110,), width=1)
    draw.rectangle((INSET, HEADER_H, INSET + WIN_W - 1, HEADER_H + WIN_H - 1),
                   outline=pal["accent"] + (40,), width=1)

    # Soft fades at the window edges so notation does not hard-cut while scrolling.
    fade_h = 24
    for i in range(fade_h):
        alpha = int(228 * (1 - i / fade_h) ** 1.3)
        draw.line((INSET, HEADER_H + i, INSET + WIN_W - 1, HEADER_H + i),
                  fill=PANEL_RGB + (alpha,))
        draw.line((INSET, HEADER_H + WIN_H - 1 - i, INSET + WIN_W - 1,
                   HEADER_H + WIN_H - 1 - i), fill=PANEL_RGB + (alpha,))

    play_y = HEADER_H + int(round(WIN_H * PLAYHEAD))
    draw.rectangle((INSET + 1, play_y - 3, INSET + WIN_W - 2, play_y + 3),
                   fill=pal["accent"] + (16,))
    draw.line((INSET + 10, play_y, INSET + WIN_W - 10, play_y),
              fill=pal["accent"] + (145,), width=1)
    draw.polygon([(INSET + 1, play_y - 5), (INSET + 9, play_y),
                  (INSET + 1, play_y + 5)], fill=pal["accent"] + (220,))

    pill_w, pill_h = 108, 20
    draw.rounded_rectangle((18, 13, 18 + pill_w, 13 + pill_h), radius=6,
                           fill=pal["accent"] + (32,),
                           outline=pal["accent"] + (150,), width=1)
    draw.text((27, 16), "SHEET MUSIC", font=load_font("sans", 10),
              fill=pal["accent"] + (235,))

    draw.text((146, 11), section["name"], font=load_font("serif", 17),
              fill=pal["title"] + (245,))

    meta = f"{key_name}  ·  {int(round(bpm))} BPM"
    meta_font = load_font("sans", 11)
    meta_w = draw.textlength(meta, font=meta_font)
    draw.text((PANEL_W - 18 - meta_w, 16), meta, font=meta_font,
              fill=pal["title"] + (150,))

    canvas.alpha_composite(img, (FRAME_PAD, FRAME_PAD))
    return canvas
