"""
PianoSpheric Automated Long-Form Publishing Pipeline
Full End-to-End Orchestrator:
1. Composes & renders 15-Minute Full HD (1080p 16:9) multi-movement piano suite
2. Fully synced sheet music cards & 88-key visualizer with PianoSpheric branding
3. Generates high-CTR 1280x720 thumbnail with logo and cosmic hook
4. Generates high-converting SEO metadata & chapter timestamps via Pollinations AI
5. Uploads to YouTube on Mon / Wed / Fri
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

load_dotenv()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, 'output')
FINAL_EXPORT_DIR = os.path.join(os.path.dirname(PROJECT_DIR), 'FINAL_EXPORTED_VIDEOS')
PUBLISHED_LOG = os.path.join(PROJECT_DIR, 'published_videos.json')

CHANNEL_NAME = os.getenv("CHANNEL_NAME", "PianoSpheric")
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

def save_published_entry(video_file, yt_id=None, fb_id=None, title="", chapters=None):
    history = get_published_history()
    fb_page_id = os.getenv("FB_PAGE_ID", "")
    entry = {
        "video_file": os.path.basename(video_file),
        "youtube_id": yt_id,
        "youtube_url": f"https://youtu.be/{yt_id}" if yt_id else None,
        "facebook_id": fb_id,
        "facebook_url": f"https://www.facebook.com/{fb_page_id}/videos/{fb_id}" if (fb_id and fb_page_id) else None,
        "title": title,
        "chapters": chapters or [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    history.append(entry)
    with open(PUBLISHED_LOG, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"[LOG] Saved publication record to {PUBLISHED_LOG}")

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
        f"{duration_mins}-MINUTE CALM, ETHEREAL, RELAXING PIANO SUITES & 432Hz COSMIC HARMONIES.\n\n"
        "STRICT GUIDELINES:\n"
        f"- The song is titled: '{song_title}'. Duration: {duration_mins} Minutes.\n"
        "- Generate a high-CTR YouTube title (max 95 chars) formatted for long-form relaxation videos, e.g. "
        f"'{duration_mins} Min Relaxing Piano | {song_title} · 432Hz Deep Sleep & Study (1080p HD)'\n"
        "- Generate an engaging, atmospheric description (4-6 sentences) inviting listeners to relax, meditate, "
        f"work, or sleep, asking viewers what they are focusing on today, and encouraging subscriptions to {CHANNEL_NAME}.\n"
        f"- The description MUST include this exact chapter timestamp list:\n{chapters_formatted}\n\n"
        "- Include relevant hashtags: #piano #relaxingpiano #studymusic #sleepmusic #432hz #pianospheric #ambientpiano #deepfocus #meditation\n\n"
        "Return ONLY a valid JSON object without markdown fences, with this exact schema:\n"
        "{\n"
        '  "title": "<title under 95 chars>",\n'
        '  "description": "<rich description including timestamps>",\n'
        '  "tags": ["piano", "relaxing piano", "study music", "sleep music", "piano visualizer", "pianospheric", "meditation piano", "calm piano", "peaceful piano", "ambient piano", "deep focus", "15 min piano", "instrumental piano"]\n'
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
                return data.get("title"), data.get("description"), data.get("tags")
        except Exception as e:
            print(f"[AI NOTE] Pollinations API request error: {e}")

    # Fallback template
    print("[AI] Using high-converting built-in SEO metadata template.")
    title = f"{duration_mins} Min Relaxing Piano Suite | {song_title} · 432Hz Sleep & Study (1080p HD)"
    desc = (
        f"Immerse yourself in 15 minutes of serene, celestial piano music composed to help you relax, "
        f"study, relieve stress, and drift into deep sleep.\n\n"
        f"✨ Featured Piece: {song_title}\n\n"
        f"Timestamps:\n{chapters_formatted}\n\n"
        f"🎹 Welcome to {CHANNEL_NAME}. Subscribe for new relaxing piano suites released every Monday, Wednesday, and Friday.\n\n"
        f"#piano #relaxingpiano #studymusic #sleepmusic #pianospheric #432hz #deepfocus #ambientpiano"
    )
    tags = [
        "piano", "relaxing piano", "study music", "sleep music", "piano visualizer",
        "pianospheric", "meditation piano", "calm piano", "peaceful piano", "ambient piano",
        "deep focus", "15 min piano", "instrumental piano", "stress relief"
    ]
    return title, desc, tags

def should_publish_to_youtube(force_yt=None):
    """
    YouTube Schedule: Monday (0), Wednesday (2), Friday (4) UTC.
    Facebook Schedule: Daily.
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

    weekday = datetime.now(timezone.utc).weekday()
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday]

    # Monday (0), Wednesday (2), Friday (4)
    if weekday in (0, 2, 4):
        return True, f"Scheduled Day ({day_name}): YouTube upload is ENABLED."
    else:
        return False, f"Off-Day ({day_name}): YouTube upload is SKIPPED (Facebook will still upload)."

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
        video_path = generate_longform_video(
            mood='relaxing',
            minutes=minutes,
            output_filename=out_name
        )

    # Load chapters if generated
    chapters_txt = video_path.replace('.mp4', '_chapters.txt')
    chapters_export = os.path.join(FINAL_EXPORT_DIR, os.path.basename(video_path).replace('.mp4', '_chapters.txt'))
    if not os.path.exists(chapters_txt) and os.path.exists(chapters_export):
        chapters_txt = chapters_export

    chapters = []
    if os.path.exists(chapters_txt):
        with open(chapters_txt, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and line[0].isdigit() and ':' in line[:5]:
                    parts = line.split(' ', 1)
                    chapters.append({"time": parts[0], "title": parts[1] if len(parts) > 1 else ""})
    if not chapters:
        chapters = [
            {"time": "00:00", "title": "Movement I: Celestial Peace"},
            {"time": "00:30", "title": "Movement II: Cosmic Reverie"}
        ]

    # Step 3: Generate Thumbnail
    print(f"\n>>> [2/5] Creating 1280x720 Thumbnail...")
    thumb_path = os.path.join(OUTPUT_DIR, f"thumb_{timestamp}.jpg")
    create_pianospheric_thumbnail(video_path, thumb_path)

    # Step 4: Generate SEO Metadata
    print(f"\n>>> [3/5] Generating SEO Metadata...")
    song_title = f"{minutes} Minutes of Relaxing Piano Suite" if minutes > 1 else "Peaceful Cosmic Piano Suite"
    title, desc, tags = generate_seo_metadata(song_title, chapters, duration_mins=max(1, minutes))
    print(f"  • Title: {title}")

    if dry_run:
        print("\n[DRY RUN] Finished without uploading. Video saved at:", video_path)
        save_published_entry(video_path, yt_id=None, fb_id=None, title=title, chapters=chapters)
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
    save_published_entry(video_path, yt_id=yt_video_id, fb_id=fb_video_id, title=title, chapters=chapters)

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
