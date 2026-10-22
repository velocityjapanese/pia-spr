"""
Facebook Page Video Upload Script for PianoSpheric
Uses Facebook Graph API to upload pristine 1080p piano videos to the PianoSpheric Facebook Page.
Supports chunked resumable upload with automatic retries and graceful fallback.
"""
import os
import sys
import json
import time
import requests
from dotenv import load_dotenv

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

GRAPH_API_VERSION = "v21.0"
CHUNK_SIZE = 80 * 1024 * 1024

def get_facebook_credentials():
    """Retrieve Facebook Page ID and Page Access Token from environment."""
    page_id = (os.getenv('FB_PAGE_ID') or os.getenv('FACEBOOK_PAGE_ID') or '').strip()
    access_token = (os.getenv('FB_PAGE_ACCESS_TOKEN') or os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN') or '').strip()

    if not page_id or not access_token:
        return None, None

    return page_id, access_token

def upload_video_resumable(video_path, title, description, page_id, access_token):
    file_size = os.path.getsize(video_path)
    print(f"[facebook] Starting resumable upload for '{title}' ({file_size / (1024 * 1024):.2f} MB)...")

    start_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/videos"
    start_payload = {
        "upload_phase": "start",
        "file_size": file_size,
        "access_token": access_token
    }

    start_resp = None
    for s_attempt in range(1, 4):
        try:
            resp = requests.post(start_url, data=start_payload, timeout=60)
            if resp.status_code == 200:
                start_resp = resp.json()
                break
        except Exception as e:
            print(f"[facebook] Start attempt {s_attempt} error: {e}")
        time.sleep(3 * s_attempt)

    if not start_resp or "upload_session_id" not in start_resp:
        raise RuntimeError(f"Resumable upload START phase failed: {start_resp}")

    upload_session_id = start_resp["upload_session_id"]
    video_id = start_resp.get("video_id")
    start_offset = int(start_resp.get("start_offset", 0))

    with open(video_path, "rb") as f:
        while start_offset < file_size:
            pct = min(100, int((start_offset / file_size) * 100))
            print(f"[facebook] Upload progress: {pct}% (offset {start_offset:,} bytes)")

            f.seek(start_offset)
            chunk_data = f.read(CHUNK_SIZE)
            chunk_len = len(chunk_data)

            chunk_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/videos"
            files = {"video_file_chunk": ("chunk.bin", chunk_data, "application/octet-stream")}
            data = {
                "upload_phase": "transfer",
                "upload_session_id": upload_session_id,
                "start_offset": start_offset,
                "access_token": access_token
            }

            resp = requests.post(chunk_url, data=data, files=files, timeout=120)
            if resp.status_code == 200:
                c_data = resp.json()
                start_offset = int(c_data.get("start_offset", start_offset + chunk_len))
            else:
                raise RuntimeError(f"Transfer failed: {resp.text}")

    # Finish phase
    finish_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/videos"
    finish_payload = {
        "upload_phase": "finish",
        "upload_session_id": upload_session_id,
        "title": title,
        "description": description,
        "access_token": access_token
    }

    f_resp = requests.post(finish_url, data=finish_payload, timeout=90)
    if f_resp.status_code == 200:
        fdata = f_resp.json()
        final_id = fdata.get("id") or video_id
        print(f"🎉 [facebook] Uploaded! Video ID: {final_id}")
        return {"id": final_id, "success": True}
    else:
        raise RuntimeError(f"Finish phase failed: {f_resp.text}")

def upload_to_facebook(video_path, title, description):
    page_id, access_token = get_facebook_credentials()
    if not page_id or not access_token:
        print("[facebook] ℹ️ Facebook credentials not yet configured (FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN). Skipping upload.")
        return None

    return upload_video_resumable(video_path, title, description, page_id, access_token)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python publish_facebook.py <video_path> [title] [description]")
        sys.exit(1)
    upload_to_facebook(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "PianoSpheric", sys.argv[3] if len(sys.argv) > 3 else "")
