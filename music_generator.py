import os
import random
import mido
from mido import Message, MidiFile, MidiTrack, MetaMessage

ROOT_NOTES = {
    'A': 57, 'Bb': 58, 'B': 59, 'C': 60, 'Db': 61, 'D': 62, 
    'Eb': 63, 'E': 64, 'F': 65, 'F#': 66, 'G': 67, 'Ab': 68
}

MINOR_INTERVALS = [0, 2, 3, 5, 7, 8, 10]
MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11]
DORIAN_INTERVALS = [0, 2, 3, 5, 7, 9, 10]

CHORD_PROGRESSIONS = [
    [0, 5, 2, 6],   # i - VI - III - VII
    [0, 3, 6, 4],   # i - iv - VII - v
    [5, 6, 0, 4],   # VI - VII - i - v
    [0, 5, 3, 6],   # i - VI - iv - VII
    [0, 6, 5, 4],   # i - VII - VI - v (Andalusian / dramatic)
]

def get_scale_notes(root_midi, intervals, octaves=4):
    notes = []
    for oct_offset in range(-1, octaves):
        base = root_midi + (oct_offset * 12)
        for interval in intervals:
            notes.append(base + interval)
    return sorted(list(set(notes)))

def compose_longform_piece(output_path, mood='emotional', tempo_bpm=None, num_bars=16):
    """
    Composes a multi-section long-form piano piece (16 to 32 measures):
    - Section A: Main Theme & Gentle Arpeggios (Bars 1-8)
    - Section B: Harmonic Climax with higher register & triplet runs (Bars 9-16)
    - Full 88-key piano voicing and pedal damper simulation
    """
    if not tempo_bpm:
        tempo_bpm = random.randint(68, 76)

    root_name = random.choice(list(ROOT_NOTES.keys()))
    root_midi = ROOT_NOTES[root_name]

    intervals = DORIAN_INTERVALS if random.random() < 0.3 else MINOR_INTERVALS
    scale_notes = get_scale_notes(root_midi, intervals, octaves=5)
    prog_pattern = random.choice(CHORD_PROGRESSIONS)

    bar_ticks = 480 * 4 # 1920 ticks per bar
    mid = MidiFile(type=1, ticks_per_beat=480)

    # Track 0: Tempo
    tempo_track = MidiTrack()
    mid.tracks.append(tempo_track)
    tempo_track.append(MetaMessage('set_tempo', tempo=int(60_000_000 / tempo_bpm), time=0))
    tempo_track.append(MetaMessage('time_signature', numerator=4, denominator=4, time=0))

    # Track 1: Right Hand
    rh_track = MidiTrack()
    mid.tracks.append(rh_track)
    rh_track.append(MetaMessage('track_name', name='Right Hand', time=0))
    rh_track.append(Message('program_change', channel=0, program=0, time=0))

    # Track 2: Left Hand
    lh_track = MidiTrack()
    mid.tracks.append(lh_track)
    lh_track.append(MetaMessage('track_name', name='Left Hand', time=0))
    lh_track.append(Message('program_change', channel=1, program=0, time=0))
    lh_track.append(Message('control_change', channel=1, control=64, value=127, time=0))

    rh_events = []
    lh_events = []

    for bar_idx in range(num_bars):
        bar_start = bar_idx * bar_ticks
        prog_step = prog_pattern[bar_idx % len(prog_pattern)]

        # Pedal lift and press at every measure
        lh_events.append((bar_start, 'pedal', 0, 0))
        lh_events.append((bar_start + 25, 'pedal', 64, 127))

        # Root and harmony
        chord_root_interval = intervals[prog_step % len(intervals)]
        chord_root = (root_midi - 24) + chord_root_interval
        chord_fifth = chord_root + 7
        chord_octave = chord_root + 12
        chord_tenth = chord_octave + (intervals[(prog_step + 2) % len(intervals)] - chord_root_interval) % 12 + 12

        # In second section (bars 8+), add low bass octaves for grand cinematic impact
        if bar_idx >= 8:
            lh_pattern = [chord_root - 12, chord_root, chord_fifth, chord_octave, chord_tenth, chord_octave, chord_tenth, chord_fifth]
        else:
            lh_pattern = [chord_root, chord_fifth, chord_octave, chord_tenth, chord_octave, chord_fifth, chord_octave, chord_fifth]

        step_dur = bar_ticks // len(lh_pattern)
        for s_idx, note_val in enumerate(lh_pattern):
            t_on = bar_start + s_idx * step_dur + random.randint(-4, 4)
            t_off = t_on + step_dur + random.randint(150, 300)
            base_vel = 62 + random.randint(-4, 4)
            if s_idx in [0, 1]:
                base_vel += 15
            lh_events.append((t_on, 'note_on', note_val, base_vel))
            lh_events.append((t_off, 'note_off', note_val, 0))

        # Right Hand Melody
        available_chord_tones = [chord_octave + 12, chord_tenth, chord_fifth + 12, chord_octave + 24]
        available_scale_tones = [n for n in scale_notes if 60 <= n <= 88]

        # In climax (bars 8-15), play higher octave with sweeping expression
        reg_shift = 12 if bar_idx >= 8 else 0
        beat_dur = bar_ticks // 4

        for b in range(4):
            t_beat = bar_start + b * beat_dur
            r_pick = random.random()

            if r_pick < 0.40:
                # Two eighth notes
                n1 = random.choice(available_chord_tones) + reg_shift
                n2 = min(available_scale_tones, key=lambda x: abs(x - (n1 + random.choice([-2, 2, 1, -1]))))
                rh_events.append((t_beat, 'note_on', n1, random.randint(78, 92)))
                rh_events.append((t_beat + 210, 'note_off', n1, 0))
                rh_events.append((t_beat + 240, 'note_on', n2, random.randint(74, 86)))
                rh_events.append((t_beat + 440, 'note_off', n2, 0))
            elif r_pick < 0.65 and bar_idx >= 8:
                # Flowing triplet arpeggio run
                trip_step = beat_dur // 3
                start_n = random.choice(available_chord_tones) + reg_shift
                for tr_i in range(3):
                    t_tr = t_beat + tr_i * trip_step
                    tr_n = start_n + (tr_i * 2)
                    rh_events.append((t_tr, 'note_on', tr_n, 82 + tr_i * 4))
                    rh_events.append((t_tr + trip_step - 20, 'note_off', tr_n, 0))
            else:
                # Emotive singing sustained tone
                anchor_n = random.choice(available_chord_tones) + reg_shift
                dur = beat_dur if b < 3 else (beat_dur * 2)
                rh_events.append((t_beat, 'note_on', anchor_n, random.randint(82, 95)))
                rh_events.append((t_beat + dur - 30, 'note_off', anchor_n, 0))

    def compile_track(events, track, channel):
        events.sort(key=lambda x: x[0])
        last_t = 0
        for t, etype, val1, val2 in events:
            delta = max(0, t - last_t)
            last_t = t
            if etype == 'pedal':
                track.append(Message('control_change', channel=channel, control=val1, value=val2, time=delta))
            elif etype == 'note_on':
                track.append(Message('note_on', channel=channel, note=val1, velocity=val2, time=delta))
            elif etype == 'note_off':
                track.append(Message('note_off', channel=channel, note=val1, velocity=0, time=delta))
        track.append(MetaMessage('end_of_track', time=480))

    compile_track(rh_events, rh_track, channel=0)
    compile_track(lh_events, lh_track, channel=1)

    mid.save(output_path)
    title = f"{root_name} Minor - Infinite Reverie"
    print(f"Composed Long-form Piano Piece: {title} ({num_bars} bars, {tempo_bpm} BPM)")
    return {"title": title, "key": root_name, "tempo": tempo_bpm, "bars": num_bars}

def compose_longform_suite(output_path, target_minutes=20, mood='relaxing'):
    """
    Composes a non-repeating, multi-movement Piano Suite for long-form YouTube (e.g. 20 minutes):
    - 6 distinct movements with changing keys, modes, tempos, and melodic themes.
    - Continuous evolving harmony so the viewer experiences fresh, non-repetitive music throughout.
    - Generates precise YouTube Chapter Timestamps.
    """
    MOVEMENT_TITLES = [
        ("Whispers of the Night", "D", MINOR_INTERVALS, 68),
        ("River of Stars", "G", MINOR_INTERVALS, 72),
        ("Golden Twilight", "Bb", MAJOR_INTERVALS, 66),
        ("Ocean of Dreams", "E", DORIAN_INTERVALS, 70),
        ("Midnight Cadenza", "A", MINOR_INTERVALS, 74),
        ("Peaceful Return", "D", MINOR_INTERVALS, 64)
    ]

    total_target_seconds = target_minutes * 60
    num_movements = len(MOVEMENT_TITLES)
    seconds_per_mov = total_target_seconds / num_movements

    mid = MidiFile(type=1, ticks_per_beat=480)

    tempo_track = MidiTrack()
    mid.tracks.append(tempo_track)
    rh_track = MidiTrack()
    mid.tracks.append(rh_track)
    lh_track = MidiTrack()
    mid.tracks.append(lh_track)

    rh_track.append(MetaMessage('track_name', name='Right Hand', time=0))
    rh_track.append(Message('program_change', channel=0, program=0, time=0))
    lh_track.append(MetaMessage('track_name', name='Left Hand', time=0))
    lh_track.append(Message('program_change', channel=1, program=0, time=0))
    lh_track.append(Message('control_change', channel=1, control=64, value=127, time=0))

    rh_events = []
    lh_events = []
    tempo_events = []

    current_tick = 0
    current_time_sec = 0.0
    chapters = []

    for mov_idx, (m_name, root_name, intervals, bpm) in enumerate(MOVEMENT_TITLES):
        bar_ticks = 480 * 4
        sec_per_bar = (60.0 / bpm) * 4
        num_bars = int(seconds_per_mov / sec_per_bar)
        
        # Record chapter timestamp
        mins = int(current_time_sec // 60)
        secs = int(current_time_sec % 60)
        timestamp_str = f"{mins:02d}:{secs:02d}"
        chapter_title = f"Movement {mov_idx+1}: {m_name} ({root_name})"
        chapters.append({"time": timestamp_str, "seconds": current_time_sec, "title": chapter_title})

        tempo_events.append((current_tick, int(60_000_000 / bpm)))

        root_midi = ROOT_NOTES[root_name]
        scale_notes = get_scale_notes(root_midi, intervals, octaves=5)
        prog_pattern = random.choice(CHORD_PROGRESSIONS)

        for bar_idx in range(num_bars):
            bar_start = current_tick + bar_idx * bar_ticks
            prog_step = prog_pattern[bar_idx % len(prog_pattern)]

            # Pedal refresh
            lh_events.append((bar_start, 'pedal', 0, 0))
            lh_events.append((bar_start + 25, 'pedal', 64, 127))

            # Left Hand Harmony
            chord_root_interval = intervals[prog_step % len(intervals)]
            chord_root = (root_midi - 24) + chord_root_interval
            chord_fifth = chord_root + 7
            chord_octave = chord_root + 12
            chord_tenth = chord_octave + (intervals[(prog_step + 2) % len(intervals)] - chord_root_interval) % 12 + 12

            # Dynamic accompaniment pattern based on section
            if bar_idx < 4:
                # Sparse intro
                lh_pattern = [chord_root, chord_fifth, chord_octave, chord_fifth]
            elif bar_idx >= (num_bars - 8):
                # Rich bass octaves
                lh_pattern = [chord_root - 12, chord_root, chord_fifth, chord_octave, chord_tenth, chord_octave, chord_tenth, chord_fifth]
            else:
                lh_pattern = [chord_root, chord_fifth, chord_octave, chord_tenth, chord_octave, chord_fifth, chord_octave, chord_fifth]

            step_dur = bar_ticks // len(lh_pattern)
            for s_idx, note_val in enumerate(lh_pattern):
                t_on = bar_start + s_idx * step_dur + random.randint(-4, 4)
                t_off = t_on + step_dur + random.randint(150, 300)
                base_vel = 58 + random.randint(-4, 4)
                if s_idx in [0, 1]:
                    base_vel += 14
                lh_events.append((t_on, 'note_on', note_val, base_vel))
                lh_events.append((t_off, 'note_off', note_val, 0))

            # Right Hand Melody
            available_chord_tones = [chord_octave + 12, chord_tenth, chord_fifth + 12, chord_octave + 24]
            available_scale_tones = [n for n in scale_notes if 60 <= n <= 88]
            reg_shift = 12 if bar_idx >= (num_bars // 2) else 0
            beat_dur = bar_ticks // 4

            for b in range(4):
                t_beat = bar_start + b * beat_dur
                r_pick = random.random()

                if r_pick < 0.45:
                    n1 = random.choice(available_chord_tones) + reg_shift
                    n2 = min(available_scale_tones, key=lambda x: abs(x - (n1 + random.choice([-2, 2, 1, -1]))))
                    rh_events.append((t_beat, 'note_on', n1, random.randint(75, 90)))
                    rh_events.append((t_beat + 210, 'note_off', n1, 0))
                    rh_events.append((t_beat + 240, 'note_on', n2, random.randint(72, 85)))
                    rh_events.append((t_beat + 440, 'note_off', n2, 0))
                elif r_pick < 0.65 and bar_idx >= (num_bars // 2):
                    trip_step = beat_dur // 3
                    start_n = random.choice(available_chord_tones) + reg_shift
                    for tr_i in range(3):
                        t_tr = t_beat + tr_i * trip_step
                        tr_n = start_n + (tr_i * 2)
                        rh_events.append((t_tr, 'note_on', tr_n, 78 + tr_i * 4))
                        rh_events.append((t_tr + trip_step - 20, 'note_off', tr_n, 0))
                else:
                    anchor_n = random.choice(available_chord_tones) + reg_shift
                    dur = beat_dur if b < 3 else (beat_dur * 2)
                    rh_events.append((t_beat, 'note_on', anchor_n, random.randint(78, 92)))
                    rh_events.append((t_beat + dur - 30, 'note_off', anchor_n, 0))

        current_tick += num_bars * bar_ticks
        current_time_sec += num_bars * sec_per_bar

    # Compile Tempo Track
    tempo_events.sort(key=lambda x: x[0])
    last_tt = 0
    for tick, tempo_val in tempo_events:
        delta = max(0, tick - last_tt)
        last_tt = tick
        tempo_track.append(MetaMessage('set_tempo', tempo=tempo_val, time=delta))
    tempo_track.append(MetaMessage('end_of_track', time=480))

    def compile_track(events, track, channel):
        events.sort(key=lambda x: x[0])
        last_t = 0
        for t, etype, val1, val2 in events:
            delta = max(0, t - last_t)
            last_t = t
            if etype == 'pedal':
                track.append(Message('control_change', channel=channel, control=val1, value=val2, time=delta))
            elif etype == 'note_on':
                track.append(Message('note_on', channel=channel, note=val1, velocity=val2, time=delta))
            elif etype == 'note_off':
                track.append(Message('note_off', channel=channel, note=val1, velocity=0, time=delta))
        track.append(MetaMessage('end_of_track', time=480))

    compile_track(rh_events, rh_track, channel=0)
    compile_track(lh_events, lh_track, channel=1)

    mid.save(output_path)
    total_mins = round(current_time_sec / 60, 1)
    suite_title = f"{target_minutes} Minutes of Relaxing Piano Suite"
    print(f"Composed Multi-Movement Longform Suite: {suite_title} ({total_mins} mins, {len(chapters)} movements)")

    return {
        "title": suite_title,
        "duration_sec": current_time_sec,
        "chapters": chapters
    }

if __name__ == '__main__':
    compose_longform_piece('longform_test.mid', num_bars=16)
