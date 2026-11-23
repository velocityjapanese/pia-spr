"""Engraved, time-synced scrolling paper score for the floating score panel.

The notation is built from the same notes the audio is rendered from, so the
staff and the performance cannot drift. Each section is engraved once into a
tall RGBA roll; ffmpeg crops it at a constant slow rate, putting every bar
under the playhead exactly when it sounds. The paper stays bright and opaque,
and the noteheads light up as they are played.
"""
import bisect
import io
import json
import os
import re
from collections import defaultdict

import numpy as np
import resvg_py
import verovio
from PIL import Image, ImageDraw, ImageFilter

from config import FPS
from render.scene import load_font, palette

PANEL_X, PANEL_Y = 960, 32
# One large static system per page. The panel is taller than the old scrolling
# strip so the notation can be read like a printed sheet instead of racing by.
PANEL_W, PANEL_H = 900, 520
FRAME_PAD = 26
HEADER_H = 58
INSET = 16
WIN_X = PANEL_X + INSET
WIN_Y = PANEL_Y + HEADER_H
WIN_W = PANEL_W - 2 * INSET
WIN_H = PANEL_H - HEADER_H - INSET
SPEED = 18.0                     # vertical layout spacing per second of music
SCROLL_DRIFT = 4.0               # slow crawl while a system is playing
SCROLL_DRIFT_MAX = 52.0          # cap before the run-up to the next system
SCROLL_TRANSITION = 1.6          # seconds to scroll the next system into place
PLAYHEAD = 0.32                  # fraction of the window at the reading line
TARGET_SYSTEM_SEC = 11.5         # old scroll spacing: 3-4 bars per system
QUANT = 0.25                     # 16th-note grid

SCORE_RGB = (34, 29, 22)
PANEL_RGB = (241, 225, 198)
PANEL_ALPHA = 255

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
    "scale": 88,
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
    """Return (roll_png, frame_png, notes_json, crop_expr) or None."""
    try:
        return _build(section, notes, work_dir)
    except Exception as exc:
        print(f"[score] section {section['index']}: score panel disabled ({exc})")
        return None


def _scroll_crop_expr(systems, section_start, pad):
    """Crop-y expression: crawl while a system plays, scroll to the next one.

    The old constant scroll moved a whole system height during playback, so
    the sounding note climbed to the top of the panel. This keeps the current
    system near the reading line: a 3 px/s drift while it plays, then a smooth
    one-second run-up so the next system is in place before its first note.
    """
    rel = [s["start"] - section_start for s in systems]
    last = systems[-1]
    expr = (f"({last['roll_y'] - pad:.3f}+"
            f"{SCROLL_DRIFT:.3f}*(t-{rel[-1]:.4f}))")
    for i in range(len(systems) - 2, -1, -1):
        s0, s1 = rel[i], rel[i + 1]
        y0 = systems[i]["roll_y"] - pad
        trans_start = max(s0, s1 - SCROLL_TRANSITION)
        y_end = y0 + min(SCROLL_DRIFT * max(0.0, trans_start - s0),
                         SCROLL_DRIFT_MAX)
        target_next = systems[i + 1]["roll_y"] - pad
        p = f"((t-{trans_start:.4f})/{SCROLL_TRANSITION:.4f})"
        smooth = f"({p}*{p}*(3-2*{p}))"
        drift = (f"({y0:.3f}+min({SCROLL_DRIFT:.3f}*(t-{s0:.4f}),"
                 f"{SCROLL_DRIFT_MAX:.3f}))")
        lerp = f"({y_end:.3f}+({target_next - y_end:.3f})*{smooth})"
        expr = (f"if(lt(t,{s1:.4f}),"
                f"if(lt(t,{trans_start:.4f}),{drift},{lerp}),{expr})")
    return expr


def _build(section, notes, work_dir):
    key_name = section.get("key") or "C major"
    fifths, mode_str = _key_fifths(key_name)
    bpm = float(section["bpm"])
    sec_dur = float(section["end"]) - float(section["start"])
    bar_sec = 240.0 / bpm
    total_bars = max(1, int(round(sec_dur / bar_sec)))
    target = max(1, min(6, int(round(TARGET_SYSTEM_SEC / bar_sec))))
    # Floor rather than round: a short remainder system would render smaller
    # than the rest, so keep every system at least `target` bars.
    systems = max(1, total_bars // target)
    base, extra = divmod(total_bars, systems)
    sizes = [base + 1] * extra + [base] * (systems - extra)

    pad = int(round(WIN_H * PLAYHEAD))
    height = pad + int(round(sec_dur * SPEED)) + WIN_H + 8
    # Opaque warm paper with a very light grain, so the score reads as a
    # printed sheet instead of glowing lines on a dark rectangle.
    paper = np.empty((height, WIN_W, 4), dtype=np.uint8)
    paper[:, :, :3] = PANEL_RGB
    paper[:, :, 3] = PANEL_ALPHA
    grain = np.random.default_rng(7).normal(0, 2.2, (height, WIN_W, 1))
    paper[:, :, :3] = np.clip(paper[:, :, :3].astype(np.float32) + grain,
                              0, 255).astype(np.uint8)
    roll = Image.fromarray(paper, "RGBA")

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

        # Trim Verovio's transparent page margins before scaling. The ink then
        # fills the scroll band, so notes are larger at the same crawl speed.
        ow, oh = img.size
        bbox = img.getchannel("A").getbbox()
        if bbox:
            bx0, by0, bx1, by1 = bbox
            img = img.crop(bbox)
            nw, nh = img.size
            for onset in onsets:
                heads = [((hx * ow - bx0) / nw, (hy * oh - by0) / nh)
                         for hx, hy in onset["heads"]]
                onset["heads"] = heads
                if heads:
                    onset["x"] = sum(h[0] for h in heads) / len(heads)
                else:
                    onset["x"] = (onset["x"] * ow - bx0) / nw

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

    for i, sys_ in enumerate(sys_geom):
        sys_["end"] = (sys_geom[i + 1]["start"] if i + 1 < len(sys_geom)
                       else float(section["end"]))

    roll_path, frame_path, notes_path = panel_paths(work_dir, section["index"])
    roll.save(roll_path)
    with open(notes_path, "w", encoding="utf-8") as fh:
        json.dump({"layout_speed": SPEED, "pad": pad,
                   "drift": SCROLL_DRIFT, "drift_max": SCROLL_DRIFT_MAX,
                   "transition": SCROLL_TRANSITION, "systems": sys_geom}, fh)
    _make_frame(section, bpm, key_name).save(frame_path)
    crop_expr = _scroll_crop_expr(sys_geom, float(section["start"]), pad)
    return roll_path, frame_path, notes_path, crop_expr


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

    # Drop shadow only outside the panel. The notation window is transparent,
    # so a shadow canvas covering the panel interior would show through it and
    # tint the cream paper almost black.
    shadow_pad = 28
    shadow = Image.new("RGBA", (PANEL_W + 2 * shadow_pad,
                                PANEL_H + 2 * shadow_pad), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (shadow_pad, shadow_pad, shadow_pad + PANEL_W - 1,
         shadow_pad + PANEL_H - 1), radius=16, fill=(0, 0, 0, 155))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    shadow.paste((0, 0, 0, 0), (shadow_pad, shadow_pad,
                                shadow_pad + PANEL_W, shadow_pad + PANEL_H))
    canvas.alpha_composite(shadow, (FRAME_PAD - shadow_pad - 4,
                                    FRAME_PAD - shadow_pad + 6))

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

    # Soft paper-coloured fades at the window edges hide the scroll cut without
    # darkening the sheet.
    fade_h = 24
    for i in range(fade_h):
        alpha = int(220 * (1 - i / fade_h) ** 1.2)
        draw.line((INSET, HEADER_H + i, INSET + WIN_W - 1, HEADER_H + i),
                  fill=PANEL_RGB + (alpha,))
        draw.line((INSET, HEADER_H + WIN_H - 1 - i, INSET + WIN_W - 1,
                   HEADER_H + WIN_H - 1 - i), fill=PANEL_RGB + (alpha,))

    # Larger header type: the old 10-17 px labels were unreadable at video size.
    pill_text = "SHEET MUSIC"
    pill_font = load_font("sans", 15)
    pill_text_w = draw.textlength(pill_text, font=pill_font)
    pill_w, pill_h = int(pill_text_w) + 30, 32
    pill_x, pill_y = 18, 13
    draw.rounded_rectangle((pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
                           radius=8, fill=(78, 54, 34, 235),
                           outline=(198, 158, 94, 205), width=1)
    draw.text((pill_x + 15, pill_y + 7), pill_text, font=pill_font,
              fill=(246, 236, 216, 250))

    name_x = pill_x + pill_w + 20
    draw.text((name_x, 4), section["name"], font=load_font("serif", 32),
              fill=(62, 44, 28, 255))

    meta = f"{key_name}  ·  {int(round(bpm))} BPM"
    meta_font = load_font("sans", 17)
    meta_w = draw.textlength(meta, font=meta_font)
    draw.text((PANEL_W - 20 - meta_w, 23), meta, font=meta_font,
              fill=(100, 72, 46, 240))

    canvas.alpha_composite(img, (FRAME_PAD, FRAME_PAD))
    return canvas
