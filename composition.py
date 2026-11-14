"""Seeded motif-based piano composer.

Every run produces a deterministic piece from a seed: key, harmony, motif,
accompaniment pattern, performance humanisation and section plan all derive
from it. Output is a type-1 MIDI file plus timeline.json, which is the single
source of truth shared by the audio renderer and the video renderer.
"""
import json
import math
import os
import random
from dataclasses import dataclass

from mido import Message, MetaMessage, MidiFile, MidiTrack

from config import FPS, OUTPUT_DIR

TPB = 480

TONIC_PC = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11,
}

MODES = {
    "aeolian": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "ionian": [0, 2, 4, 5, 7, 9, 11],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
}

MINOR_PROGS = [
    [0, 5, 2, 6], [0, 3, 6, 4], [5, 6, 0, 4],
    [0, 5, 3, 6], [0, 2, 5, 4], [3, 4, 0, 5], [0, 6, 5, 4],
]
MAJOR_PROGS = [
    [0, 5, 3, 4], [0, 3, 5, 4], [5, 3, 0, 4], [0, 4, 5, 3], [3, 4, 5, 0],
]

# Two-bar onset templates (beats 0..8). Durations are derived from gaps.
ONSET_TEMPLATES = [
    [0, 1, 1.5, 2.5, 4, 5, 5.5, 6.5],
    [0, 1.5, 2, 3, 4, 4.5, 5, 6],
    [0, 2, 3, 4, 5.5, 6],
    [0, 1, 2, 3, 4, 4.5, 5, 5.5, 6],
    [0, 0.75, 1.5, 2, 3, 3.5, 4.5, 5, 6, 6.5],
    [0, 1, 2.5, 3, 4, 5, 6, 7],
    [0, 0.5, 1, 2, 2.5, 3.5, 4, 5, 6, 6.5],
]

STEP_CHOICES = [-2, -1, -1, -1, 0, 1, 1, 1, 2, 3, -3]

PATTERNS = {
    "quarters": ["root", "fifth", "oct", "fifth"],
    "quarters_soft": ["root", "oct", "fifth", "third"],
    "alberti": ["root", "fifth", "third", "fifth", "oct", "fifth", "third", "fifth"],
    "broken": ["root", "fifth", "oct", "third", "tenth", "oct", "fifth", "third"],
    "arpeggio": ["root", "third", "fifth", "oct", "tenth", "oct", "fifth", "third"],
    "tenths": ["root", "tenth", "fifth", "tenth", "oct", "tenth", "fifth", "tenth"],
}

SECTION_NAMES = [
    "Awakening", "Drift", "Radiance", "Cascade", "Stillness", "Return",
    "Reverie", "Ascent", "Tide", "Dusk", "Embers", "Horizon", "Snowfall",
]

# The theme opens the piece: full texture from the first bar so the first
# 30 seconds hook instead of drifting. The sparse intro returns later as an
# interlude before the coda.
ROLES = [
    {"role": "theme",     "bpm": 0,  "register": 4, "vel": 72, "pattern": "alberti",       "skip": 0.0},
    {"role": "variation", "bpm": 2,  "register": 4, "vel": 76, "pattern": "broken",        "skip": 0.0},
    {"role": "contrast",  "bpm": -5, "register": 4, "vel": 68, "pattern": "tenths",        "skip": 0.1},
    {"role": "climax",    "bpm": 4,  "register": 5, "vel": 88, "pattern": "arpeggio",      "skip": 0.0},
    {"role": "intro",     "bpm": -4, "register": 4, "vel": 58, "pattern": "quarters_soft", "skip": 0.35},
    {"role": "coda",      "bpm": -8, "register": 4, "vel": 56, "pattern": "quarters_soft", "skip": 0.4},
]

TITLE_A = ["Nocturne", "Reverie", "Elegy", "Aubade", "Serenade", "Lullaby",
           "Ballad", "Prelude", "Hymn", "Meditation", "Vespers", "Interlude",
           "Evensong", "Solace", "Cantilena", "Barcarolle", "Idyll", "Melodie",
           "Romanza", "Pastorale", "Valse", "Etude"]
TITLE_B = ["of the", "for the", "in the", "beneath the", "beyond the", "upon the"]
TITLE_C = ["Silver Rain", "Quiet Dawn", "Sleeping Stars", "Distant Shore",
           "Fading Light", "Velvet Sky", "Winter Lake", "Silent Forest",
           "Moonlit River", "Hollow Moon", "Gentle Tide", "Amber Dusk",
           "Snowfall", "Endless Blue", "First Light", "Paper Lanterns",
           "Drowned Garden", "Pale Horizon", "Quiet Harbor", "Distant Bells",
           "Silver Meadow", "Glass Horizon", "Amber Rain", "Northern Lights",
           "Fallen Snow", "Tidal Glass", "Hollow Vale", "Starless Sea",
           "Velvet Rain", "Crystal Tide", "Sleeping Garden", "Evening Star"]

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


@dataclass
class Section:
    index: int
    name: str
    role: str
    start_beat: int
    bars: int
    bpm: int
    tonic: int
    mode: str
    intervals: list
    prog: list
    pattern: str
    register: int
    vel: int
    skip: float
    palette: str


def _scale_pitch(tonic, intervals, degree, octave):
    return tonic + 12 * (octave + 1) + intervals[degree % 7] + 12 * (degree // 7)


def _scale_pitches(tonic, intervals, lo, hi):
    out = []
    for octave in range(1, 8):
        for d in range(7):
            p = _scale_pitch(tonic, intervals, d, octave)
            if lo <= p <= hi:
                out.append(p)
    return sorted(set(out))


def _chord_pitches(tonic, intervals, root_deg, lo, hi):
    out = []
    for k in (0, 2, 4):
        for octave in range(1, 8):
            p = _scale_pitch(tonic, intervals, root_deg + k, octave)
            if lo <= p <= hi:
                out.append(p)
    return sorted(set(out))


def _nearest(pitches, target):
    return min(pitches, key=lambda p: abs(p - target))


def _voicing(tonic, intervals, root_deg, base_octave=2):
    root = _scale_pitch(tonic, intervals, root_deg, base_octave)
    third = _scale_pitch(tonic, intervals, root_deg + 2, base_octave)
    fifth = _scale_pitch(tonic, intervals, root_deg + 4, base_octave)
    return {"root": root, "third": third, "fifth": fifth,
            "oct": root + 12, "tenth": third + 12}


def _make_motif(rng, length):
    deltas = [0]
    for _ in range(length - 1):
        d = rng.choice(STEP_CHOICES)
        if abs(deltas[-1]) >= 4 and abs(d) > 2:
            d = rng.choice([-1, 1])
        deltas.append(d)
    return deltas


def _transform(deltas, kind):
    if kind == "inv":
        return [-d for d in deltas]
    if kind == "retro":
        return list(reversed(deltas))
    return list(deltas)


def _snap(pitch, scale_ps, chord_ps, strong):
    pitch = _nearest(scale_ps, pitch)
    if strong and chord_ps:
        ct = _nearest(chord_ps, pitch)
        if abs(ct - pitch) <= 2:
            pitch = ct
    return pitch


def _build_plan(rng, target_minutes, seed):
    tonic_name = rng.choice(["A", "D", "E", "F", "G", "Bb", "C", "B"])
    tonic = TONIC_PC[tonic_name]
    mode = rng.choices(["aeolian", "dorian", "ionian"], weights=[6, 2, 2])[0]
    base_bpm = rng.randint(60, 72)
    intervals = MODES[mode]

    names = rng.sample(SECTION_NAMES, len(ROLES))
    palettes = list(PALETTE_ORDER_SHUFFLE(rng))

    weights = [0.19, 0.18, 0.16, 0.19, 0.14, 0.14]
    total_sec = target_minutes * 60.0
    sections = []
    beat_cursor = 0
    for i, role in enumerate(ROLES):
        bpm = max(50, min(84, base_bpm + role["bpm"]))
        bar_sec = 4 * 60.0 / bpm
        target = total_sec * weights[i]
        bars = max(4, int(round(target / bar_sec / 4.0)) * 4)
        if i == len(ROLES) - 1:
            bars = max(8, bars)

        sec_tonic, sec_mode, sec_intervals = tonic, mode, intervals
        if role["role"] == "contrast":
            if intervals in (MODES["aeolian"], MODES["dorian"]):
                sec_tonic, sec_mode, sec_intervals = (tonic + 3) % 12, "ionian", MODES["ionian"]
            else:
                sec_tonic, sec_mode, sec_intervals = (tonic - 3) % 12, "aeolian", MODES["aeolian"]

        pool = MINOR_PROGS if sec_intervals != MODES["ionian"] else MAJOR_PROGS
        prog = rng.choice(pool)

        sections.append(Section(
            index=i,
            name=f"{ROMAN[i]}. {names[i]}",
            role=role["role"],
            start_beat=beat_cursor,
            bars=bars,
            bpm=bpm,
            tonic=sec_tonic,
            mode=sec_mode,
            intervals=sec_intervals,
            prog=prog,
            pattern=role["pattern"],
            register=role["register"],
            vel=role["vel"],
            skip=role["skip"],
            palette=palettes[i % len(palettes)],
        ))
        beat_cursor += bars * 4

    return tonic_name, mode, base_bpm, sections


def PALETTE_ORDER_SHUFFLE(rng):
    order = ["midnight", "ember", "lavender", "forest", "ocean", "rose"]
    rng.shuffle(order)
    return order


def _generate_section(section, rng, motif_deltas, variant_plan, notes, pedal,
                      sec_start_sec, sec_start_tick):
    tonic, intervals = section.tonic, section.intervals
    scale_ps = _scale_pitches(tonic, intervals, 55, 98)
    beats_per_sec = section.bpm / 60.0
    sec_per_beat = 60.0 / section.bpm
    chord_bars = 2 if section.role in ("intro", "coda") else 1
    register_center = 12 * (section.register + 1) + tonic
    pattern = PATTERNS[section.pattern]
    step_beats = 4.0 / len(pattern)
    prev_pitch = _nearest(scale_ps, register_center + 4)

    blocks = section.bars // 2
    for block in range(blocks):
        bar0 = block * 2
        kind, shift = variant_plan[block % len(variant_plan)]
        deltas = _transform(motif_deltas, kind)

        onsets = ONSET_TEMPLATES[(block + section.index) % len(ONSET_TEMPLATES)]
        if len(onsets) != len(deltas):
            onsets = ONSET_TEMPLATES[0][:len(deltas)]

        chord0 = section.prog[(bar0 // chord_bars) % len(section.prog)]
        chord_ps0 = _chord_pitches(tonic, intervals, chord0, 60, 98)
        start_target = prev_pitch + shift
        start_pitch = _nearest(chord_ps0 or scale_ps, start_target)

        pitch = start_pitch
        for idx, onset in enumerate(onsets):
            bar = bar0 + int(onset // 4)
            if bar >= section.bars:
                break
            local_beat = onset % 4
            strong = local_beat in (0, 2)
            chord_deg = section.prog[(bar // chord_bars) % len(section.prog)]
            chord_ps = _chord_pitches(tonic, intervals, chord_deg, 55, 98)

            if idx > 0:
                pitch = _snap(pitch + deltas[idx], scale_ps, chord_ps, strong)
            else:
                pitch = _snap(pitch, scale_ps, chord_ps, True)
            if pitch < 55:
                pitch += 12
            elif pitch > 96:
                pitch -= 12

            if section.skip and rng.random() < section.skip and idx not in (0, len(onsets) - 1):
                prev_pitch = pitch
                continue

            next_onset = onsets[idx + 1] if idx + 1 < len(onsets) else 8.0
            dur_beats = max(0.5, min(2.2, next_onset - onset + 0.35))

            phrase_pos = (block % 4) / 4.0
            arc = math.sin(math.pi * min(1.0, phrase_pos + 0.15))
            vel = section.vel + (7 if strong else 0) + int(8 * arc) + rng.randint(-4, 4)
            vel = max(30, min(110, vel))

            jitter = rng.gauss(0, 10) / 1000.0
            on_sec = sec_start_sec + (bar * 4 + local_beat) * sec_per_beat + jitter
            on_tick = sec_start_tick + round((bar * 4 + local_beat) * TPB
                                             + jitter * beats_per_sec * TPB)
            off_tick = on_tick + round(dur_beats * TPB)
            notes.append({"pitch": pitch, "hand": "R", "vel": vel,
                          "on_sec": on_sec, "dur_sec": dur_beats * sec_per_beat,
                          "on_tick": on_tick, "off_tick": max(on_tick + 30, off_tick)})

            if section.role == "climax" and idx % 2 == 0:
                notes.append({"pitch": min(108, pitch + 12), "hand": "R",
                              "vel": max(30, vel - 14), "on_sec": on_sec + 0.012,
                              "dur_sec": dur_beats * sec_per_beat,
                              "on_tick": on_tick + 12,
                              "off_tick": max(on_tick + 42, off_tick)})

            prev_pitch = pitch

        # Left hand accompaniment for both bars of the block
        for bar in (bar0, bar0 + 1):
            if bar >= section.bars:
                break
            chord_deg = section.prog[(bar // chord_bars) % len(section.prog)]
            v = _voicing(tonic, intervals, chord_deg)
            if v["root"] < 28:
                v = {k: val + 12 for k, val in v.items()}
            bar_beat = bar * 4
            on_tick = sec_start_tick + bar_beat * TPB
            pedal.append((max(0, on_tick - 8), 0))
            pedal.append((on_tick + 4, 127))

            if section.role == "climax":
                bass = v["root"] - 12
                if bass >= 28:
                    _add_lh(notes, bass, 90, sec_start_sec, bar, 0.0, sec_per_beat,
                            sec_start_tick, section.bpm, beats=2.0, rng=rng)

            for s_idx, key in enumerate(pattern):
                pitch = v[key]
                if s_idx == len(pattern) - 1 and section.role in ("intro", "coda"):
                    continue
                offset = s_idx * step_beats
                vel = 50 + (9 if s_idx % 2 == 0 else 0) + rng.randint(-4, 3)
                dur = step_beats * 1.6
                _add_lh(notes, pitch, vel, sec_start_sec, bar, offset, sec_per_beat,
                        sec_start_tick, section.bpm, beats=dur, rng=rng)

        # Final tonic chord at the end of the coda
        if section.role == "coda" and block == blocks - 1:
            bar = section.bars - 1
            chord_deg = section.prog[(bar // chord_bars) % len(section.prog)]
            chord_ps = _chord_pitches(tonic, intervals, 0, 55, 98)
            for p in chord_ps[:2] + [chord_ps[0] + 12]:
                _add_lh(notes, p, 60, sec_start_sec, bar, 2.0, sec_per_beat,
                        sec_start_tick, section.bpm, beats=4.0, rng=rng)
            v = _voicing(tonic, intervals, 0)
            _add_lh(notes, v["root"], 72, sec_start_sec, bar, 2.0, sec_per_beat,
                    sec_start_tick, section.bpm, beats=4.0, rng=rng)


def _add_lh(notes, pitch, vel, sec_start_sec, bar, beat_offset, sec_per_beat,
            sec_start_tick, bpm, beats, rng):
    on_beat = bar * 4 + beat_offset
    jitter = max(-0.004, min(0.014, rng.gauss(0.004, 0.005)))
    notes.append({
        "pitch": pitch, "hand": "L", "vel": max(28, min(104, vel)),
        "on_sec": sec_start_sec + on_beat * sec_per_beat + jitter,
        "dur_sec": beats * sec_per_beat,
        "on_tick": sec_start_tick + round(on_beat * TPB + jitter * bpm / 60.0 * TPB),
        "off_tick": sec_start_tick + round((on_beat + beats) * TPB),
    })


def compose(target_minutes=15, seed=None, output_dir=None, base_name=None,
            avoid_titles=()):
    if seed is None:
        seed = random.SystemRandom().randrange(1, 2 ** 31)
    rng = random.Random(seed)
    output_dir = output_dir or OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    base_name = base_name or f"piece_{seed}"

    tonic_name, mode, base_bpm, sections = _build_plan(rng, target_minutes, seed)
    motif_len = rng.choice([6, 7, 8, 8, 9])
    motif_deltas = _make_motif(rng, motif_len)

    variant_cycle = [
        ("id", 0), ("trans", 2), ("id", 0), ("trans", -2),
        ("inv", 0), ("trans", 3), ("id", 0), ("trans", -3),
    ]

    notes = []
    pedal = []
    sec_start_sec = 0.0
    sec_start_tick = 0
    timeline_sections = []
    chapters = []

    for sec in sections:
        variant_plan = variant_cycle
        if sec.role in ("intro", "coda"):
            variant_plan = [("id", 0)] * 4
        elif sec.role == "variation":
            variant_plan = [("inv", 0), ("id", 2), ("retro", 0), ("inv", 2)]
        elif sec.role == "contrast":
            variant_plan = [("inv", 0), ("inv", -2), ("id", 2), ("retro", 0)]

        _generate_section(sec, rng, motif_deltas, variant_plan, notes, pedal,
                          sec_start_sec, sec_start_tick)

        sec_sec = sec.bars * 4 * 60.0 / sec.bpm
        start_frame = round(sec_start_sec * FPS)
        end_sec = sec_start_sec + sec_sec
        end_frame = round(end_sec * FPS)
        timeline_sections.append({
            "index": sec.index,
            "name": sec.name,
            "role": sec.role,
            "start": round(sec_start_sec, 4),
            "end": round(end_sec, 4),
            "start_frame": start_frame,
            "frames": end_frame - start_frame,
            "bpm": sec.bpm,
            "palette": sec.palette,
            "register": sec.register,
            "key": f"{tonic_name} {mode}",
        })
        chapters.append({"time": _mmss(sec_start_sec), "title": sec.name})

        sec_start_sec = end_sec
        sec_start_tick += sec.bars * 4 * TPB

    total_sec = sec_start_sec
    notes.sort(key=lambda n: (n["on_sec"], n["pitch"]))
    title = _make_title(rng, avoid_titles)

    midi_path = os.path.join(output_dir, f"{base_name}.mid")
    _write_midi(midi_path, sections, notes, pedal, total_sec, base_bpm)

    timeline = {
        "version": 2,
        "seed": seed,
        "title": title,
        "key": f"{tonic_name} {mode}",
        "base_bpm": base_bpm,
        "duration": round(total_sec, 3),
        "fps": FPS,
        "sections": timeline_sections,
        "notes": [
            {"start": round(n["on_sec"], 4), "end": round(n["on_sec"] + n["dur_sec"], 4),
             "pitch": n["pitch"], "vel": n["vel"], "hand": n["hand"]}
            for n in notes
        ],
    }
    timeline_path = os.path.join(output_dir, f"{base_name}_timeline.json")
    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=1)

    print(f"[compose] seed={seed}  {title}  ({tonic_name} {mode}, {base_bpm} BPM, "
          f"{len(sections)} sections, {len(notes)} notes, {total_sec/60:.1f} min)")

    return {
        "seed": seed,
        "title": title,
        "key": f"{tonic_name} {mode}",
        "duration": total_sec,
        "midi_path": midi_path,
        "timeline_path": timeline_path,
        "chapters": chapters,
        "sections": timeline_sections,
    }


def _write_midi(path, sections, notes, pedal, total_sec, base_bpm):
    mid = MidiFile(type=1, ticks_per_beat=TPB)
    tempo_track = MidiTrack()
    mid.tracks.append(tempo_track)

    tick = 0
    tempo_track.append(MetaMessage("set_tempo", tempo=int(60_000_000 / base_bpm), time=0))
    tempo_track.append(MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    for sec in sections:
        sec_tick = sec.start_beat * TPB
        delta = max(0, sec_tick - tick)
        tempo_track.append(MetaMessage("set_tempo", tempo=int(60_000_000 / sec.bpm), time=delta))
        tick = sec_tick
    tempo_track.append(MetaMessage("end_of_track", time=TPB))

    def build_track(hand, channel, with_pedal):
        track = MidiTrack()
        track.append(MetaMessage("track_name", name="Right Hand" if hand == "R" else "Left Hand", time=0))
        track.append(Message("program_change", channel=channel, program=0, time=0))
        events = []
        for n in notes:
            if n["hand"] != hand:
                continue
            events.append((n["on_tick"], 1, "on", n["pitch"], n["vel"]))
            events.append((n["off_tick"], 0, "off", n["pitch"], 0))
        if with_pedal:
            for ptick, value in pedal:
                events.append((ptick, 1, "cc", 64, value))
        events.sort(key=lambda e: (e[0], e[1]))
        last = 0
        for t, _, kind, a, b in events:
            delta = max(0, t - last)
            last = t
            if kind == "on":
                track.append(Message("note_on", channel=channel, note=a, velocity=b, time=delta))
            elif kind == "off":
                track.append(Message("note_off", channel=channel, note=a, velocity=0, time=delta))
            else:
                track.append(Message("control_change", channel=channel, control=a, value=b, time=delta))
        track.append(MetaMessage("end_of_track", time=TPB))
        return track

    mid.tracks.append(build_track("R", 0, False))
    mid.tracks.append(build_track("L", 1, True))
    mid.save(path)


def _make_title(rng, avoid=()):
    avoid = set(avoid or ())
    title = ""
    for _ in range(60):
        title = f"{rng.choice(TITLE_A)} {rng.choice(TITLE_B)} {rng.choice(TITLE_C)}"
        if title not in avoid:
            return title
    return f"{title} No. {rng.randint(2, 99)}"


def _mmss(seconds):
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


if __name__ == "__main__":
    import sys
    mins = 3
    sd = None
    if "--minutes" in sys.argv:
        mins = int(sys.argv[sys.argv.index("--minutes") + 1])
    if "--seed" in sys.argv:
        sd = int(sys.argv[sys.argv.index("--seed") + 1])
    compose(mins, sd, base_name=f"preview_{sd or 'auto'}")
