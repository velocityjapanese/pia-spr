import os
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import time
import json
import random
import argparse
from datetime import datetime
import shutil

from music_generator import compose_longform_piece, compose_longform_suite
from audio_renderer import render_midi_to_audio
from score_renderer import create_longform_score_card, generate_synced_score_sequence
from visualizer_renderer import render_longform_visualizer
from compositor import composite_longform_video

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output')
FINAL_EXPORT_DIR = os.path.join(os.path.dirname(PROJECT_DIR), 'FINAL_EXPORTED_VIDEOS')
HISTORY_FILE = os.path.join(PROJECT_DIR, 'longform_history.json')


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _trim_midi_copy(src_path, dst_path, seconds):
    """Copy first N seconds of a MIDI file (for looped background-viz renders).

    Same idea as lfi-bngo's loop-block assembly: render one short segment once,
    then stream_loop it to full length in the composite. Notes stuck at the cut
    get an all-notes-off per channel so the short clip ends cleanly.
    """
    import mido
    mid = mido.MidiFile(src_path)
    total_sec = float(mid.length) if getattr(mid, 'length', 0) else 0.0
    if total_sec <= 0 or seconds <= 0 or seconds >= total_sec:
        shutil.copy2(src_path, dst_path)
        return dst_path
    total_ticks = max(sum(m.time for m in t) for t in mid.tracks)
    cutoff = int(total_ticks * (seconds / total_sec))
    out = mido.MidiFile(type=mid.type, ticks_per_beat=mid.ticks_per_beat)
    for track in mid.tracks:
        nt = mido.MidiTrack()
        at = 0
        for msg in track:
            at += msg.time
            if at > cutoff:
                break
            nt.append(msg.copy())
        for ch in range(16):
            nt.append(mido.Message('control_change', channel=ch, control=123, value=0, time=0))
        out.tracks.append(nt)
    out.save(dst_path)
    return dst_path


def generate_longform_video(mood='emotional', title=None, bars=16, tempo=None, minutes=None, output_filename=None):
    """
    Executes the 16:9 Landscape Long-Form YouTube Piano Video Pipeline:
    1. Compose multi-section piano composition (or 20-min suite)
    2. Synthesize studio Grand Piano audio (WAV)
    3. Engrave 16:9 floating sheet music card
    4. Render 1920x1080 88-key golden falling notes visualizer
    5. Composite into 16:9 Full HD MP4 + export YouTube Chapters

    CI tuning: PIA_BARS_PER_SLIDE (default 4, was 2) halves the
    verovio/music21 score-card count so a 15-min suite (~257 bars)
    renders ~65 cards instead of ~129.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(FINAL_EXPORT_DIR, exist_ok=True)

    base_name = f"longform_piano_{timestamp}"
    midi_path = os.path.join(OUTPUT_DIR, f"{base_name}.mid")
    audio_path = os.path.join(OUTPUT_DIR, f"{base_name}.wav")
    score_path = os.path.join(OUTPUT_DIR, f"{base_name}_score.png")
    viz_path = os.path.join(OUTPUT_DIR, f"{base_name}_viz.mp4")

    if output_filename:
        final_mp4 = os.path.join(OUTPUT_DIR, output_filename)
    else:
        final_mp4 = os.path.join(OUTPUT_DIR, f"{base_name}_16x9.mp4")

    print("\n" + "="*65)
    print(f"[LONG-FORM 16:9 BOT] STARTING PIPELINE: {base_name}")
    if minutes:
        print(f"   Mode: Multi-Movement Suite ({minutes} Minutes) | 1920x1080 (16:9)")
    else:
        print(f"   Mode: Single Piece ({bars} Bars) | 1920x1080 (16:9)")
    print("="*65 + "\n")

    start_time = time.time()
    chapters_info = None

    def stage(name, fn):
        t0 = time.time()
        print(f">>> {name}...")
        out = fn()
        print(f"    [stage done in {time.time() - t0:.1f}s]")
        return out

    # Step 1: Music Composition
    def _compose():
        nonlocal song_title, chapters_info
        if minutes:
            comp_info = compose_longform_suite(midi_path, target_minutes=minutes, mood=mood)
            song_title = title if title else comp_info['title']
            chapters_info = comp_info.get('chapters', [])
        else:
            comp_info = compose_longform_piece(midi_path, mood=mood, tempo_bpm=tempo, num_bars=bars)
            song_title = title if title else comp_info['title']
    song_title = title or "PianoSpheric Suite"
    stage("Step 1/5: Composing Long-Form Piano Music", _compose)

    # Step 2: Audio Synthesis
    print("\n>>> Step 2/5: Synthesizing Studio Grand Piano Audio (FluidSynth)...")
    t_audio = time.time()
    render_midi_to_audio(midi_path, audio_path)
    print(f"    [stage done in {time.time() - t_audio:.1f}s]")

    # Step 3: Synchronized Sheet Music Engraving
    print("\n>>> Step 3/5: Engraving Fully Synced Sheet Music Sequence...")
    bars_per_slide = _env_int('PIA_BARS_PER_SLIDE', 4)
    print(f"    bars_per_slide={bars_per_slide}")
    t_score = time.time()
    score_cards_dir = os.path.join(OUTPUT_DIR, f"{base_name}_score_cards")
    score_input = generate_synced_score_sequence(midi_path, score_cards_dir, bars_per_slide=bars_per_slide)
    print(f"    [stage done in {time.time() - t_score:.1f}s]")

    # Step 4: 16:9 Visualizer (loop-block fast path, lfi-bngo style)
    print("\n>>> Step 4/5: Rendering 16:9 Fullscreen Visualizer (1920x1080, 88 Keys)...")
    viz_seconds = _env_int('PIA_VIZ_SECONDS', 0)
    viz_src = midi_path
    if viz_seconds > 0:
        viz_src = os.path.join(OUTPUT_DIR, f"{base_name}_vizsrc.mid")
        _trim_midi_copy(midi_path, viz_src, viz_seconds)
        os.environ['PIA_VIZ_LOOP'] = '1'
        print(f"    [viz loop mode] rendering {viz_seconds}s background block, looped to full length in composite")
    t_viz = time.time()
    render_longform_visualizer(viz_src, viz_path, framerate=30, width=1920, height=1080)
    print(f"    [stage done in {time.time() - t_viz:.1f}s]")

    # Step 5: Video Compositing
    print("\n>>> Step 5/5: Compositing 16:9 Full HD Video (FFmpeg)...")
    t_comp = time.time()
    composite_longform_video(viz_path, score_input, audio_wav=audio_path, output_mp4=final_mp4, song_title=song_title, channel_name="PianoSpheric")
    print(f"    [stage done in {time.time() - t_comp:.1f}s]")

    # Export to FINAL_EXPORTED_VIDEOS
    export_copy = os.path.join(FINAL_EXPORT_DIR, os.path.basename(final_mp4))
    shutil.copy2(final_mp4, export_copy)

    # Export Chapters File if available
    chapters_file = None
    if chapters_info:
        chapters_file = export_copy.replace('.mp4', '_chapters.txt')
        with open(chapters_file, 'w', encoding='utf-8') as f:
            f.write(f"=== {song_title} ===\n\n")
            f.write("YouTube Video Description Timestamps:\n")
            for ch in chapters_info:
                f.write(f"{ch['time']} {ch['title']}\n")
        print(f"Generated YouTube Chapters file: {chapters_file}")

    elapsed = round(time.time() - start_time, 2)
    print("\n" + "="*65)
    print(f"[SUCCESS] 16:9 Long-Form Video ready in {elapsed}s")
    print(f"Local file: {final_mp4}")
    print(f"Exported to: {export_copy}")
    if chapters_file:
        print(f"YouTube Chapters: {chapters_file}")
    print("="*65 + "\n")

    record = {
        "timestamp": timestamp,
        "title": song_title,
        "bars": bars,
        "duration_sec": elapsed,
        "output_file": final_mp4,
        "export_copy": export_copy
    }
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = []
    history.append(record)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2)

    return final_mp4

def main():
    parser = argparse.ArgumentParser(description="16:9 Landscape Long-Form Piano Video Generator")
    parser.add_argument('--title', help="Song title (e.g. 'Nocturne in C Minor')")
    parser.add_argument('--mood', default='emotional', choices=['emotional', 'cinematic', 'romantic', 'relaxing'])
    parser.add_argument('--bars', type=int, default=16, help="Number of musical bars (for short pieces, e.g. 16-32)")
    parser.add_argument('--minutes', type=int, help="Target duration in minutes (e.g. --minutes 20 for full multi-movement suite)")
    parser.add_argument('--tempo', type=int, help="Tempo in BPM")
    parser.add_argument('--output', help="Output filename")
    args = parser.parse_args()

    generate_longform_video(
        mood=args.mood,
        title=args.title,
        bars=args.bars,
        minutes=args.minutes,
        tempo=args.tempo,
        output_filename=args.output
    )

if __name__ == '__main__':
    main()
