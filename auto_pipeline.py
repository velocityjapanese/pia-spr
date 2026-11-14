"""
PianoSpheric Automated Long-Form Publishing Pipeline
Full End-to-End Orchestrator:
1. Composes & renders a 15-minute 1080p cinematic piano suite (new piece every run)
2. Falling-note visualisation with lit 88-key keyboard (no sheet-music overlay)
3. Generates a 1280x720 thumbnail from a real frame of the render
4. Generates SEO metadata & chapter timestamps via Pollinations AI
5. Uploads to YouTube daily (one original suite per run)
6. Uploads to Facebook Page daily
7. Saves publication history & cleans up temporary video files
"""
import os
import sys
import json
import random
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

load_dotenv()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output')
FINAL_EXPORT_DIR = os.path.join(os.path.dirname(PROJECT_DIR), 'FINAL_EXPORTED_VIDEOS')
PUBLISHED_LOG = os.path.join(PROJECT_DIR, 'published_videos.json')

CHANNEL_NAME = (os.getenv("CHANNEL_NAME") or "PianoSpheric").strip() or "PianoSpheric"
POLLINATIONS_KEY = (os.getenv("POLLINATIONS_API_KEY") or "").strip()
GEN_API = "https://gen.pollinations.ai"

from bot import generate_longform_video
from thumbnail_generator import create_pianospheric_thumbnail
from publish_youtube import upload_to_youtube, set_video_thumbnail
from publish_facebook import upload_to_facebook

def get_published_history():
    if os.path.exists(PUBLISHED_LOG):
        try:
            with open(PUBLISHED_LOG, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_published_entry(video_file, yt_id=None, fb_id=None, title="", chapters=None,
                         seed=None, piece_title=None):
    history = get_published_history()
    fb_page_id = os.getenv("FB_PAGE_ID", "")
    entry = {
        "video_file": os.path.basename(video_file),
        "youtube_id": yt_id,
        "youtube_url": f"https://youtu.be/{yt_id}" if yt_id else None,
        "facebook_id": fb_id,
        "facebook_url": f"https://www.facebook.com/{fb_page_id}/videos/{fb_id}" if (fb_id and fb_page_id) else None,
        "title": title,
        "piece_title": piece_title,
        "seed": seed,
        "chapters": chapters or [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    history.append(entry)
    with open(PUBLISHED_LOG, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"[LOG] Saved publication record to {PUBLISHED_LOG}")


def load_render_meta(video_file):
    """Reads the composition metadata written next to the rendered video."""
    stem = os.path.splitext(os.path.abspath(video_file))[0]
    for path in (stem + "_meta.json",
                 os.path.join(FINAL_EXPORT_DIR, os.path.basename(stem) + "_meta.json")):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[META NOTE] Could not read {path}: {e}")
    return {}

def generate_seo_metadata(song_title, chapters, duration_mins=15):
    """
    Generates high-converting YouTube title, rich description with timestamps, and tags.
    """
    timestamp_lines = []
    for ch in chapters:
        timestamp_lines.append(f"{ch.get('time', '00:00')} {ch.get('title', '')}")
    chapters_formatted = "\n".join(timestamp_lines)

    prompt = (
        f"You are the creative director for '{CHANNEL_NAME}', an aesthetic YouTube channel featuring "
        f"{duration_mins}-MINUTE CALM, CINEMATIC, RELAXING ORIGINAL PIANO SUITES.\n\n"
        "STRICT GUIDELINES:\n"
        f"- The piece is titled: '{song_title}'. Duration: {duration_mins} Minutes.\n"
        "- Generate a high-CTR YouTube title (max 95 chars) formatted for long-form relaxation videos, e.g. "
        f"'{duration_mins} Min Relaxing Piano | {song_title} · Original Cinematic Piano (1080p HD)'\n"
        "- Generate an engaging, atmospheric description (4-6 sentences) inviting listeners to relax, meditate, "
        f"work, or sleep, asking viewers what they are focusing on today, and encouraging subscriptions to {CHANNEL_NAME}.\n"
        f"- The description MUST include this exact chapter timestamp list:\n{chapters_formatted}\n\n"
        "- Include relevant hashtags: #piano #relaxingpiano #studymusic #sleepmusic #pianospheric #ambientpiano #deepfocus #meditation #originalmusic\n\n"
        "Return ONLY a valid JSON object without markdown fences, with this exact schema:\n"
        "{\n"
        '  "title": "<title under 95 chars>",\n'
        '  "description": "<rich description including timestamps>",\n'
        '  "tags": ["piano", "relaxing piano", "study music", "sleep music", "piano visualizer", "pianospheric", "meditation piano", "calm piano", "peaceful piano", "ambient piano", "deep focus", "instrumental piano", "original composition"]\n'
        "}"
    )

    if POLLINATIONS_KEY:
        try:
            print("[AI] Requesting SEO metadata from Pollinations API...")
            res = requests.post(
                f"{GEN_API}/v1/chat/completions",
                headers={"Authorization": f"Bearer {POLLINATIONS_KEY}", "Content-Type": "application/json"},
                json={"model": "gemini-fast", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7},
                timeout=20
            )
            if res.status_code == 200:
                raw_txt = res.json()["choices"][0]["message"]["content"].strip()
                if raw_txt.startswith("```json"):
                    raw_txt = raw_txt[7:]
                if raw_txt.startswith("```"):
                    raw_txt = raw_txt[3:]
                if raw_txt.endswith("```"):
                    raw_txt = raw_txt[:-3]
                data = json.loads(raw_txt.strip())
                title = (data.get("title") or "").strip()
                if title and len(title) <= 100 and "piano" in title.lower():
                    return title, data.get("description"), data.get("tags")
                print("[AI NOTE] Title rejected (too long or missing 'piano'); using template.")
        except Exception as e:
            print(f"[AI NOTE] Pollinations API request error: {e}")

    # Fallback template
    print("[AI] Using high-converting built-in SEO metadata template.")
    title = f"{duration_mins} Min Relaxing Piano | {song_title} · Original Cinematic Piano (1080p HD)"
    desc = (
        f"Immerse yourself in {duration_mins} minutes of serene, cinematic piano music composed to help you relax, "
        f"study, relieve stress, and drift into deep sleep.\n\n"
        f"✨ Featured Piece: {song_title}\n\n"
        f"Timestamps:\n{chapters_formatted}\n\n"
        f"🎹 Welcome to {CHANNEL_NAME}. Subscribe for a brand-new original piano suite every day.\n\n"
        f"#piano #relaxingpiano #studymusic #sleepmusic #pianospheric #ambientpiano #deepfocus #originalmusic"
    )
    tags = [
        "piano", "relaxing piano", "study music", "sleep music", "piano visualizer",
        "pianospheric", "meditation piano", "calm piano", "peaceful piano", "ambient piano",
        "deep focus", "instrumental piano", "original composition", "stress relief"
    ]
    return title, desc, tags

def should_publish_to_youtube(force_yt=None):
    """
    YouTube Schedule: every day (one original suite per run).
    Facebook Schedule: daily.
    """
    if force_yt is True:
        return True, "Manual override: YouTube forced to TRUE"
    if force_yt is False:
        return False, "Manual override: YouTube forced to FALSE"

    env_choice = os.getenv("UPLOAD_YOUTUBE", "").lower()
    if env_choice in ("true", "1", "yes"):
        return True, "Env override: UPLOAD_YOUTUBE=true"
    if env_choice in ("false", "0", "no"):
        return False, "Env override: UPLOAD_YOUTUBE=false"

    day_name = datetime.now(timezone.utc).strftime("%A")
    return True, f"Daily schedule ({day_name}): YouTube upload is ENABLED."

def run_pipeline(minutes=15, force_yt=None, dry_run=False, video_path=None):
    """
    Master execution pipeline.
    """
    print("\n" + "="*70)
    print(f"[{CHANNEL_NAME.upper()} AUTOMATION] STARTING DAILY LONG-FORM PIPELINE")
    print(f"Target Duration: {minutes} Minutes | Channel: {CHANNEL_NAME}")
    print("="*70 + "\n")

    # Step 1: Check YouTube Schedule
    upload_yt, schedule_reason = should_publish_to_youtube(force_yt)
    print(f"[SCHEDULE] {schedule_reason}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Step 2: Render or Use Existing Video
    if video_path and os.path.exists(video_path):
        print(f"\n>>> [1/5] Using Existing Video File: {video_path}")
        video_path = os.path.abspath(video_path)
    else:
        print(f"\n>>> [1/5] Rendering {minutes}-Minute Long-form Piano Suite...")
        out_name = f"PianoSpheric_{minutes}min_{timestamp}.mp4"
        used_titles = {e.get("piece_title") for e in get_published_history()
                       if e.get("piece_title")}
        video_path = generate_longform_video(
            mood='relaxing',
            minutes=minutes,
            output_filename=out_name,
            avoid_titles=used_titles
        )

    # Load composition metadata (title, seed, chapters) from the render
    meta = load_render_meta(video_path)
    song_title = meta.get("title") or f"{minutes} Minutes of Relaxing Piano"
    seed = meta.get("seed")
    attribution = meta.get("attribution",
                           "Piano: Salamander Grand Piano (Alexander Holm), CC-BY 3.0.")
    if seed is not None:
        print(f"[SEED] {seed}  |  {song_title}")
    print(f"[CREDIT] {attribution}")

    # Chapters: prefer the composition's exact section map
    chapters = []
    if meta.get("chapters"):
        chapters = [{"time": c["time"], "title": c["title"]} for c in meta["chapters"]]
    else:
        chapters_txt = video_path.replace('.mp4', '_chapters.txt')
        chapters_export = os.path.join(FINAL_EXPORT_DIR, os.path.basename(video_path).replace('.mp4', '_chapters.txt'))
        if not os.path.exists(chapters_txt) and os.path.exists(chapters_export):
            chapters_txt = chapters_export
        if os.path.exists(chapters_txt):
            with open(chapters_txt, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and line[0].isdigit() and ':' in line[:5]:
                        parts = line.split(' ', 1)
                        chapters.append({"time": parts[0], "title": parts[1] if len(parts) > 1 else ""})
    if not chapters:
        chapters = [
            {"time": "00:00", "title": "Movement I: Awakening"},
            {"time": "00:30", "title": "Movement II: Drift"}
        ]

    # Step 3: Generate Thumbnail
    print(f"\n>>> [2/5] Creating 1280x720 Thumbnail...")
    thumb_path = os.path.join(OUTPUT_DIR, f"thumb_{timestamp}.jpg")
    duration_mins = max(1, round(meta.get("duration", minutes * 60) / 60))
    create_pianospheric_thumbnail(video_path, thumb_path, minutes=duration_mins,
                                  episode=len(get_published_history()) + 1)

    # Step 4: Generate SEO Metadata
    print(f"\n>>> [3/5] Generating SEO Metadata...")
    title, desc, tags = generate_seo_metadata(song_title, chapters, duration_mins=duration_mins)
    chapter_block = "Timestamps:\n" + "\n".join(f"{c['time']} {c['title']}" for c in chapters)
    if not all(f"{c['time']} {c['title']}" in desc for c in chapters):
        desc = f"{desc}\n\n{chapter_block}"
    if attribution not in desc:
        desc = f"{desc}\n\n{attribution}"
    print(f"  • Title: {title}")

    if dry_run:
        print("\n[DRY RUN] Finished without uploading. Video saved at:", video_path)
        print("[DRY RUN] Publication log untouched.")
        return True

    # Step 5: Upload to Platforms
    # YouTube Upload (Mon, Wed, Fri)
    yt_video_id = None
    if upload_yt:
        print(f"\n>>> [4/5] Uploading to YouTube ({CHANNEL_NAME})...")
        try:
            yt_video_id = upload_to_youtube(video_path, title, desc, tags=tags)
            if yt_video_id:
                set_video_thumbnail(yt_video_id, thumb_path)
                print(f"🎉 SUCCESS! Published to YouTube: https://youtu.be/{yt_video_id}")
        except Exception as e:
            print(f"[YOUTUBE NOTE] YouTube upload error: {e}")
    else:
        print(f"\n>>> [4/5] ⏸️ Skipping YouTube upload per schedule.")

    # Facebook Upload (Daily)
    fb_video_id = None
    print(f"\n>>> [5/5] Uploading to Facebook Page...")
    try:
        fb_res = upload_to_facebook(video_path, title, desc)
        if fb_res:
            fb_video_id = fb_res.get("id")
            print(f"🎉 SUCCESS! Published to Facebook: {fb_video_id}")
    except Exception as e_fb:
        print(f"[FACEBOOK NOTE] Facebook upload error: {e_fb}")

    # Save to Published Log
    save_published_entry(video_path, yt_id=yt_video_id, fb_id=fb_video_id,
                         title=title, chapters=chapters, seed=seed,
                         piece_title=song_title)

    # Export copy to FINAL_EXPORTED_VIDEOS already handled by bot.py
    print("\n" + "="*70)
    print(f"[PIPELINE COMPLETE] {CHANNEL_NAME} Execution Finished!")
    print(f"Video file: {video_path}")
    print(f"Thumbnail: {thumb_path}")
    if yt_video_id:
        print(f"YouTube URL: https://youtu.be/{yt_video_id}")
    if fb_video_id:
        print(f"Facebook Video ID: {fb_video_id}")
    print("="*70 + "\n")

    return True

if __name__ == '__main__':
    mins = 15
    force = None
    dry = "--dry-run" in sys.argv
    vid_input = None

    if "--force-yt" in sys.argv:
        force = True
    elif "--skip-yt" in sys.argv:
        force = False

    for idx, arg in enumerate(sys.argv):
        if arg == "--minutes" and idx + 1 < len(sys.argv):
            mins = int(sys.argv[idx + 1])
        elif arg == "--video" and idx + 1 < len(sys.argv):
            vid_input = sys.argv[idx + 1]

    run_pipeline(minutes=mins, force_yt=force, dry_run=dry, video_path=vid_input)
