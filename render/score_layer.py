"""Engraved, time-synced score strip for the floating score panel.

The notation is built from the same notes the audio is rendered from, so the
staff and the performance cannot drift. Each section is engraved once into a
tall RGBA strip; ffmpeg crops it at a constant rate, putting every bar under
the playhead exactly when it sounds.
"""
import bisect
import io
import json
import os
import re
from collections import defaultdict

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
SPEED = 15.0                     # score pixels per second
CROP_EXPR = f"(n*{int(SPEED)}/{FPS})"
PLAYHEAD = 0.55                  # fraction of the window above the cursor
TARGET_SYSTEM_SEC = 11.5
QUANT = 0.25                     # 16th-note grid

SCORE_RGB = (236, 242, 250)
PANEL_RGB = (10, 13, 20)
PANEL_ALPHA = 202

DIVISIONS = 4                    # per quarter note -> 16th-note grid
BAR16 = 16

_TONIC_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10,
    "B": 11,
}
_SPELL_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_SPELL_FLAT = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")

# quarterLength -> (MusicXML type, dots). Anything else is split and tied.
_TYPE = {
    4.0: ("whole", 0),
    3.0: ("half", 1),
    2.0: ("half", 0),
    1.5: ("quarter", 1),
    1.0: ("quarter", 0),
    0.75: ("eighth", 1),
    0.5: ("eighth", 0),
    0.25: ("16th", 0),
}
_NOTATABLE = (4.0, 3.0, 2.0, 1.5, 1.0, 0.75, 0.5, 0.25)

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
    return (stem + "_roll.png", stem + "_frame.png", stem + "_notes.json")


def build_score_assets(section, notes, work_dir):
    """Return (roll_png, frame_png) or None if engraving is unavailable."""
    try:
        return _build(section, notes, work_dir)
    except Exception as exc:
        print(f"[score] section {section['index']}: score panel disabled ({exc})")
        return None


def _build(section, notes, work_dir):
    key_name = section.get("key") or "C major"
    fifths, mode_str = _key_fifths(key_name)
    bpm = float(section["bpm"])
    sec_dur = float(section["end"]) - float(section["start"])
    bar_sec = 240.0 / bpm
    total_bars = max(1, int(round(sec_dur / bar_sec)))
    target = max(1, min(6, int(round(TARGET_SYSTEM_SEC / bar_sec))))
    # Floor rather than round: a remainder system of one or two bars renders
    # far smaller than the rest, so keep every system at least `target` bars.
    systems = max(1, total_bars // target)
    base, extra = divmod(total_bars, systems)
    sizes = [base + 1] * extra + [base] * (systems - extra)

    pad = int(round(WIN_H * PLAYHEAD))
    height = pad + int(round(sec_dur * SPEED)) + WIN_H + 8
    roll = Image.new("RGBA", (WIN_W, height), PANEL_RGB + (PANEL_ALPHA,))

    bar_start = 0
    sys_geom = []
    for count in sizes:
        bar_end = bar_start + count
        sys_start = bar_start * bar_sec
        sys_dur = (bar_end - bar_start) * bar_sec
        block_h = max(48, int(round(sys_dur * SPEED)))

        engraved = _engrave_system(section, notes, bar_start, bar_end, fifths,
                                   mode_str, work_dir)
        bar_start = bar_end
        if engraved is None:
            continue
        img, onsets = engraved

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
        sys_geom.append({
            "start": float(section["start"]) + sys_start,
            "roll_y": y,
            "img_x": x,
            "img_w": img.width,
            "img_h": img.height,
            "onsets": onsets,
        })

    roll_path, frame_path, notes_path = panel_paths(work_dir, section["index"])
    roll.save(roll_path)
    with open(notes_path, "w", encoding="utf-8") as fh:
        json.dump({"speed": SPEED, "pad": pad, "systems": sys_geom}, fh)
    _make_frame(section, bpm, key_name).save(frame_path)
    return roll_path, frame_path, notes_path


def _key_fifths(key_name):
    tonic, _, mode = key_name.partition(" ")
    mode = (mode or "major").strip()
    pc = _TONIC_PC.get(tonic, 0)
    major_fifths = ((pc * 7 + 6) % 12) - 6
    if mode in ("ionian", "major"):
        return major_fifths, "major"
    minor_fifths = (((pc + 3) * 7 + 6) % 12) - 6
    if mode == "dorian":
        return minor_fifths + 1, "minor"
    return minor_fifths, "minor"


def _pitch_xml(midi, fifths):
    table = _SPELL_SHARP if fifths >= 0 else _SPELL_FLAT
    name = table[midi % 12]
    alter = 1 if name.endswith("#") else (-1 if name.endswith("b") else 0)
    xml = f"<step>{name[0]}</step>"
    if alter:
        xml += f"<alter>{alter}</alter>"
    return xml + f"<octave>{midi // 12 - 1}</octave>"


def _split_duration(q16):
    ql = q16 / float(DIVISIONS)
    pieces = []
    for cand in _NOTATABLE:
        while ql >= cand - 1e-9:
            pieces.append(cand)
            ql -= cand
    return pieces


def _notes_xml(item, voice, fifths):
    durations = _split_duration(item["e16"] - item["s16"])
    out = []
    for k, ql in enumerate(durations):
        typ, dots = _TYPE[ql]
        dur16 = int(round(ql * DIVISIONS))
        tie_in = item["tie_in"] if k == 0 else True
        tie_out = item["tie_out"] if k == len(durations) - 1 else True
        for j, midi in enumerate(item["pitches"]):
            out.append("<note>")
            if j:
                out.append("<chord/>")
            out.append("<pitch>")
            out.append(_pitch_xml(midi, fifths))
            out.append("</pitch>")
            out.append(f"<duration>{dur16}</duration>")
            if tie_in:
                out.append('<tie type="stop"/>')
            if tie_out:
                out.append('<tie type="start"/>')
            out.append(f"<voice>{voice}</voice>")
            out.append(f"<type>{typ}</type>")
            out.extend("<dot/>" for _ in range(dots))
            if voice > 1:
                out.append("<stem>down</stem>")
            if tie_in or tie_out:
                out.append("<notations>")
                if tie_in:
                    out.append('<tied type="stop"/>')
                if tie_out:
                    out.append('<tied type="start"/>')
                out.append("</notations>")
            out.append("</note>")
    return "".join(out)


def _rests_xml(start16, end16, voice):
    out = []
    for ql in _split_duration(end16 - start16):
        typ, dots = _TYPE[ql]
        dur16 = int(round(ql * DIVISIONS))
        out.append("<note><rest/>")
        out.append(f"<duration>{dur16}</duration>")
        out.append(f"<voice>{voice}</voice>")
        out.append(f"<type>{typ}</type>")
        out.extend("<dot/>" for _ in range(dots))
        out.append("</note>")
    return "".join(out)


def _segments(section, notes, bar_start, bar_end):
    beat_sec = 60.0 / float(section["bpm"])
    sec_start = float(section["start"])
    start_beat = bar_start * 4.0
    end_beat = bar_end * 4.0
    per_hand = {"R": [], "L": []}
    for note in notes:
        hand = note["hand"]
        if hand not in per_hand:
            continue
        local = (note["start"] - sec_start) / beat_sec
        if local < start_beat - QUANT or local >= end_beat:
            continue
        start = round(local / QUANT) * QUANT
        if start < start_beat:
            start = start_beat
        if start >= end_beat:
            continue
        end = round((note["end"] - sec_start) / beat_sec / QUANT) * QUANT
        end = min(max(end, start + QUANT), end_beat)

        # Split at bar lines and tie across them; a held note that crosses a
        # barline must become two notated notes or the measure is stretched.
        seg_start = start
        first = True
        while seg_start < end - 1e-9:
            boundary = (int(seg_start // 4) + 1) * 4.0
            seg_end = min(end, boundary)
            per_hand[hand].append({
                "start": seg_start,
                "end": seg_end,
                "t": float(note["start"]),
                "pitch": int(note["pitch"]),
                "tie_in": not first,
                "tie_out": seg_end < end - 1e-9,
            })
            first = False
            seg_start = seg_end
    return per_hand


def _bar_items(segments, bar):
    bar_start = bar * 4.0
    groups = defaultdict(list)
    for seg in segments:
        if seg["end"] <= bar_start + 1e-9 or seg["start"] >= bar_start + 4.0 - 1e-9:
            continue
        s16 = int(round((seg["start"] - bar_start) * DIVISIONS))
        e16 = int(round((seg["end"] - bar_start) * DIVISIONS))
        s16 = max(0, min(BAR16 - 1, s16))
        e16 = max(s16 + 1, min(BAR16, e16))
        groups[(s16, e16, seg["tie_in"], seg["tie_out"])].append(seg["pitch"])
    return [{"s16": s16, "e16": e16, "tie_in": tie_in, "tie_out": tie_out,
             "pitches": sorted(set(pitches))}
            for (s16, e16, tie_in, tie_out), pitches in groups.items()]


def _voices(items):
    voices = []
    for item in sorted(items, key=lambda i: (i["s16"], -i["e16"])):
        for voice in voices:
            if all(i["e16"] <= item["s16"] or item["e16"] <= i["s16"]
                   for i in voice):
                voice.append(item)
                break
        else:
            voices.append([item])
    for voice in voices:
        voice.sort(key=lambda i: i["s16"])
    return voices


def _forward_xml(start16, end16):
    return (f"<forward><duration>{end16 - start16}</duration></forward>")


def _measure_xml(number, items, fifths, attrs=None):
    voices = _voices(items) or [[]]
    out = [f'<measure number="{number}">']
    if attrs:
        out.append(attrs)
    for vi, voice in enumerate(voices):
        pos = 0
        # Second voices are holdovers/overlaps; silent forward gaps keep their
        # timing without littering the staff with rests.
        for item in voice:
            if item["s16"] > pos:
                if vi == 0:
                    out.append(_rests_xml(pos, item["s16"], vi + 1))
                else:
                    out.append(_forward_xml(pos, item["s16"]))
            out.append(_notes_xml(item, vi + 1, fifths))
            pos = item["e16"]
        if pos < BAR16:
            if vi == 0:
                out.append(_rests_xml(pos, BAR16, vi + 1))
            else:
                out.append(_forward_xml(pos, BAR16))
        if vi != len(voices) - 1:
            out.append(f"<backup><duration>{BAR16}</duration></backup>")
    out.append("</measure>")
    return "".join(out)


def _score_xml(bar_start, bar_end, per_hand, fifths, mode_str):
    attrs = {
        "R": (f"<attributes><divisions>{DIVISIONS}</divisions>"
              f"<key><fifths>{fifths}</fifths><mode>{mode_str}</mode></key>"
              "<time><beats>4</beats><beat-type>4</beat-type></time>"
              "<clef><sign>G</sign><line>2</line></clef></attributes>"),
        "L": (f"<attributes><divisions>{DIVISIONS}</divisions>"
              f"<key><fifths>{fifths}</fifths><mode>{mode_str}</mode></key>"
              "<time><beats>4</beats><beat-type>4</beat-type></time>"
              "<clef><sign>F</sign><line>4</line></clef></attributes>"),
    }
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 '
        'Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
        '<score-partwise version="4.0">',
        '<part-list>',
        '<part-group type="start" number="1">'
        '<group-symbol>brace</group-symbol><group-barline>yes</group-barline>'
        '</part-group>',
        '<score-part id="P1"><part-name>Right Hand</part-name></score-part>',
        '<score-part id="P2"><part-name>Left Hand</part-name></score-part>',
        '<part-group type="stop" number="1"/>',
        '</part-list>',
    ]
    for pid, hand in (("P1", "R"), ("P2", "L")):
        out.append(f'<part id="{pid}">')
        for i, bar in enumerate(range(bar_start, bar_end)):
            out.append(_measure_xml(i + 1, _bar_items(per_hand[hand], bar),
                                    fifths, attrs[hand] if i == 0 else None))
        out.append("</part>")
    out.append("</score-partwise>")
    return "".join(out)


def _engrave_system(section, notes, bar_start, bar_end, fifths, mode_str,
                    work_dir):
    per_hand = _segments(section, notes, bar_start, bar_end)
    if not per_hand["R"] and not per_hand["L"]:
        return None
    xml = _score_xml(bar_start, bar_end, per_hand, fifths, mode_str)

    xml_path = os.path.join(work_dir,
                            f"score_tmp_{section['index']}_{bar_start}.xml")
    with open(xml_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    try:
        tk = verovio.toolkit()
        tk.setOptions(_VEROVIO_OPTS)
        tk.loadFile(xml_path)
        svg = tk.renderToSVG(1)
        timemap = tk.renderToTimemap()
        png = resvg_py.svg_to_bytes(svg_string=svg)
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass

    glyphs = Image.open(io.BytesIO(png)).convert("RGBA")
    white = Image.new("RGBA", glyphs.size, SCORE_RGB + (255,))
    white.putalpha(glyphs.getchannel("A"))

    # Exact time -> position map for the cursor: Verovio tells us at which
    # beat each notehead is drawn, and the SVG tells us where it is.
    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    vw, vh = (float(vb.group(1)), float(vb.group(2))) if vb else (1.0, 1.0)
    head_at = {}
    for m in re.finditer(
            r'<g id="(\w+)" class="note">\s*<g class="notehead">\s*'
            r'<use [^>]*transform="translate\(([-\d.]+),\s*([-\d.]+)\)', svg):
        head_at[m.group(1)] = (float(m.group(2)) / vw, float(m.group(3)) / vh)
    # Sounding time of every notated onset, from the unquantized performance.
    onset_t = defaultdict(list)
    for segs in per_hand.values():
        for seg in segs:
            if not seg["tie_in"]:
                q = round(seg["start"] - bar_start * 4.0, 4)
                onset_t[q].append(seg["t"])

    by_beat = defaultdict(list)
    for event in timemap:
        q = round(float(event.get("qstamp", 0.0)), 4)
        if q not in onset_t:
            continue
        for gid in event.get("on", []):
            if gid in head_at:
                by_beat[q].append(head_at[gid])
    onsets = []
    for q, heads in sorted(by_beat.items()):
        xs = [hx for hx, _ in heads]
        onsets.append({
            "t": sum(onset_t[q]) / len(onset_t[q]),
            "x": sum(xs) / len(xs),
            "heads": heads,
        })
    onsets.sort(key=lambda o: o["t"])
    if not onsets:
        return None
    # How long each onset is actually sounding: highlight every note of the
    # chord until the last of them is released, so nothing lights up and then
    # scrolls away while it is still playing.
    ends = sorted((float(n["start"]), float(n["end"])) for n in notes)
    for onset in onsets:
        hold = onset["t"] + 0.4
        i = bisect.bisect_left(ends, (onset["t"] - 0.06, -1e9))
        while i < len(ends) and ends[i][0] <= onset["t"] + 0.06:
            hold = max(hold, ends[i][1])
            i += 1
        onset["hold"] = hold
    return white, onsets


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
