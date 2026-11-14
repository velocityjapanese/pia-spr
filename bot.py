"""PianoSpheric v2 orchestrator: compose -> audio -> cinematic render -> mux."""
import argparse
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

from audio import render_audio
from composition import compose
from config import FINAL_EXPORT_DIR, FPS, OUTPUT_DIR, WORK_DIR
from render.master import assemble
from render.section import render_section

HISTORY_FILE = os.path.join(OUTPUT_DIR, "longform_history.json")


def generate_longform_video(mood="relaxing", title=None, bars=16, tempo=None,
                            minutes=None, output_filename=None, seed=None,
                            resume=False, workers=2, avoid_titles=None):
    minutes = minutes or 15
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(FINAL_EXPORT_DIR, exist_ok=True)
    base_name = f"longform_piano_{stamp}"

    print("\n" + "=" * 68)
    print(f"[PIANOSPHERIC] {minutes}-minute cinematic piano render  (seed={seed or 'random'})")
    print("=" * 68)

    t0 = time.time()
    history = _read_history()
    titles = {h.get("title") for h in history if h.get("title")} | set(avoid_titles or ())
    comp = compose(minutes, seed=seed, output_dir=OUTPUT_DIR, base_name=base_name,
                   avoid_titles=titles)
    if seed is not None and any(h.get("seed") == seed for h in history):
        print(f"[compose] NOTE: seed {seed} was used in a previous render.")
    song_title = title or comp["title"]
    timeline = json.load(open(comp["timeline_path"], encoding="utf-8"))
    sections, notes = timeline["sections"], timeline["notes"]

    print(f"\n>>> 1/4  Composed: {song_title}  ({timeline['key']}, "
          f"{timeline['duration']/60:.1f} min, {len(notes)} notes)")

    audio_path = os.path.join(OUTPUT_DIR, f"{base_name}.wav")
    render_audio(comp["midi_path"], audio_path, work_dir=WORK_DIR)
    print(f">>> 2/4  Audio mastered: {os.path.basename(audio_path)}")

    print(f">>> 3/4  Rendering {len(sections)} sections (2 workers)...")
    tasks = [(s, notes, WORK_DIR, comp["seed"], resume) for s in sections]
    section_files = [None] * len(sections)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(render_section, t): t[0]["index"] for t in tasks}
        for fut in as_completed(futures):
            idx = futures[fut]
            path, skipped = fut.result()
            section_files[idx] = path
            state = "reused" if skipped else "rendered"
            print(f"    section {idx + 1}/{len(sections)} {state}: {os.path.basename(path)}")

    if output_filename:
        final_mp4 = os.path.join(OUTPUT_DIR, output_filename)
    else:
        final_mp4 = os.path.join(OUTPUT_DIR, f"{base_name}_16x9.mp4")
    hero_path = final_mp4.replace(".mp4", "_hero.jpg")
    hero_section = next((s for s in sections if s["role"] == "climax"),
                        sections[min(2, len(sections) - 1)])
    hero_time = hero_section["start"] + 25

    print(">>> 4/4  Assembling master...")
    info = assemble(section_files, audio_path, final_mp4, WORK_DIR,
                    hero_time=hero_time, hero_path=hero_path)

    export_copy = os.path.join(FINAL_EXPORT_DIR, os.path.basename(final_mp4))
    shutil.copy2(final_mp4, export_copy)
    shutil.copy2(hero_path, os.path.join(FINAL_EXPORT_DIR, os.path.basename(hero_path)))

    meta = {
        "title": song_title,
        "seed": comp["seed"],
        "key": timeline["key"],
        "base_bpm": timeline["base_bpm"],
        "duration": timeline["duration"],
        "sections": sections,
        "chapters": comp["chapters"],
        "attribution": (
            "Original composition. Piano samples: Salamander Grand Piano V3 by "
            "Alexander Holm, CC BY 3.0 "
            "(https://creativecommons.org/licenses/by/3.0/); audio rendered from "
            "the samples with FluidSynth."
        ),
    }
    meta_path = final_mp4.replace(".mp4", "_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    shutil.copy2(meta_path, os.path.join(FINAL_EXPORT_DIR, os.path.basename(meta_path)))

    chapters_path = final_mp4.replace(".mp4", "_chapters.txt")
    with open(chapters_path, "w", encoding="utf-8") as f:
        f.write(f"=== {song_title} ===\n\n")
        for ch in comp["chapters"]:
            f.write(f"{ch['time']} {ch['title']}\n")

    shutil.copy2(comp["timeline_path"],
                 os.path.join(FINAL_EXPORT_DIR, os.path.basename(comp["timeline_path"])))

    elapsed = time.time() - t0
    _append_history({
        "timestamp": stamp, "seed": comp["seed"], "title": song_title,
        "key": timeline["key"], "minutes": round(timeline["duration"] / 60, 2),
        "output_file": final_mp4, "render_seconds": round(elapsed, 1),
    })

    print("\n" + "=" * 68)
    print(f"[DONE] {song_title}  ({elapsed/60:.1f} min render)")
    print(f"  video     : {final_mp4}")
    print(f"  hero frame: {hero_path}")
    print(f"  chapters  : {chapters_path}")
    print("=" * 68 + "\n")
    return final_mp4


def run_smoke(seed=42):
    """Render 3 seconds of the first section and assert motion + frame count."""
    import subprocess
    from config import FFMPEG, FFPROBE

    smoke_dir = os.path.join(WORK_DIR, "smoke")
    os.makedirs(smoke_dir, exist_ok=True)
    comp = compose(1, seed=seed, output_dir=OUTPUT_DIR, base_name=f"smoke_{seed}")
    timeline = json.load(open(comp["timeline_path"], encoding="utf-8"))
    section = dict(timeline["sections"][0])
    section["index"] = 99
    section["frames"] = 90
    section["end"] = section["start"] + 3.0
    path, _ = render_section((section, timeline["notes"], smoke_dir, comp["seed"], False))

    probe = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=nb_frames,width,height",
                            "-of", "csv=p=0", path], capture_output=True, text=True)
    print("[smoke] ffprobe:", probe.stdout.strip())
    # Hash only the piano-roll region: the keyboard strip animates on its own,
    # so a full-frame hash can pass while the notes are frozen.
    md5 = subprocess.run([FFMPEG, "-v", "error", "-i", path,
                          "-vf", "crop=iw:ih*600/1080:0:0", "-frames:v", "46",
                          "-f", "framemd5", "-"], capture_output=True, text=True)
    hashes = [ln.split(",")[-1].strip() for ln in md5.stdout.splitlines() if not ln.startswith("#")]
    if len(set(hashes)) < len(hashes) - 1:
        raise RuntimeError("smoke test: piano roll frames repeat (scroll not working)")
    print(f"[smoke] {len(hashes)} roll frames sampled, {len(set(hashes))} unique -> scroll OK")

    frame_path = os.path.join(OUTPUT_DIR, "_smoke_frame.jpg")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "1.6", "-i", path,
                    "-frames:v", "1", "-q:v", "2", frame_path],
                   capture_output=True)
    print(f"[smoke] frame: {frame_path}")
    print(f"[smoke] PASS: {path}")
    return path


def _read_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _append_history(record):
    history = _read_history()
    history.append(record)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def main():
    ap = argparse.ArgumentParser(description="PianoSpheric cinematic piano generator")
    ap.add_argument("--minutes", type=int, default=15)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--title")
    ap.add_argument("--output")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        run_smoke(args.seed or 42)
        return

    generate_longform_video(minutes=args.minutes, title=args.title, seed=args.seed,
                            output_filename=args.output, resume=args.resume,
                            workers=args.workers)


if __name__ == "__main__":
    main()
