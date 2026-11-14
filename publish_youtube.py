"""
YouTube Upload & Thumbnail Publishing Module for PianoSpheric
Uses OAuth 2.0 refresh token to upload 1080p Full HD Piano Music videos and set custom thumbnails.
"""
import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _read_yt_triplet():
    client_id = (os.getenv("YOUTUBE_CLIENT_ID") or os.getenv("YT_CLIENT_ID", "")).strip()
    client_secret = (os.getenv("YOUTUBE_CLIENT_SECRET") or os.getenv("YT_CLIENT_SECRET", "")).strip()
    refresh_token = (os.getenv("YOUTUBE_REFRESH_TOKEN") or os.getenv("YT_REFRESH_TOKEN", "")).strip()
    token_uri = os.getenv("YOUTUBE_TOKEN_URI", "https://oauth2.googleapis.com/token").strip()
    return client_id, client_secret, refresh_token, token_uri


def get_authenticated_service():
    """Authenticate using refresh token from environment variables or local token file."""
    client_id, client_secret, refresh_token, token_uri = _read_yt_triplet()

    if not all([client_id, client_secret, refresh_token]):
        possible_token_paths = [
            Path(PROJECT_DIR) / "token_PianoSpheric.json",
            Path(r"C:\Users\kreg9\Downloads\kreggscode\open code\bots\youtube refresh tokens bot\token_PianoSpheric.json"),
        ]
        for p in possible_token_paths:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        client_id = data.get("client_id", "")
                        client_secret = data.get("client_secret", "")
                        refresh_token = data.get("refresh_token", "")
                        token_uri = data.get("token_uri", token_uri)
                        print(f"[youtube] Loaded credentials from: {p.name}")
                        break
                except Exception as e:
                    print(f"[youtube] Error reading {p}: {e}")

    if all([client_id, client_secret, refresh_token]):
        print("[youtube] Credentials loaded (values not logged).")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Missing YouTube credentials! Set YT_CLIENT_ID, YT_CLIENT_SECRET, and YT_REFRESH_TOKEN."
        )

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube"]
    )

    try:
        creds.refresh(Request())
    except Exception as e:
        if "invalid_grant" in str(e).lower():
            print("\n[youtube] AUTH ERROR: Refresh token has EXPIRED or been REVOKED.")
        raise

    return build("youtube", "v3", credentials=creds)


def validate_youtube_credentials(timeout_sec=30):
    """Fast pre-render auth check: refresh the OAuth token with a short timeout.

    Returns (ok, reason). Never prints secret values. Used by the pipeline
    preflight so a dead token fails in seconds instead of after a full render.
    """
    client_id, client_secret, refresh_token, token_uri = _read_yt_triplet()
    if not all([client_id, client_secret, refresh_token]):
        # Also accept the local token-file fallback used by get_authenticated_service.
        for p in (Path(PROJECT_DIR) / "token_PianoSpheric.json",):
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    client_id = client_id or data.get("client_id", "")
                    client_secret = client_secret or data.get("client_secret", "")
                    refresh_token = refresh_token or data.get("refresh_token", "")
                    token_uri = data.get("token_uri", token_uri) or token_uri
                    break
                except Exception:
                    pass
    if not all([client_id, client_secret, refresh_token]):
        return False, "missing YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN"
    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    try:
        import socket
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout_sec)
        try:
            creds.refresh(Request())
        finally:
            socket.setdefaulttimeout(old_timeout)
    except Exception as e:
        msg = str(e).lower()
        if "invalid_grant" in msg:
            return False, "refresh token EXPIRED or REVOKED (invalid_grant) - reconnect YouTube OAuth and update secrets"
        return False, f"token refresh failed: {e}"[:300]
    return True, "token refresh OK"


def _clean_tags(tags, limit=15, max_total=500):
    """YouTube rejects videos whose tags exceed 500 characters, and tags must
    describe the actual content (no '432hz'/'binaural' claims this audio does
    not make). Dedupe, cap and drop unsupported claims."""
    banned = ("432hz", "432 hz", "binaural", "subliminal", "8d audio")
    clean, seen, total = [], set(), 0
    for tag in tags or ():
        if not isinstance(tag, str):
            continue
        tag = tag.strip().strip(",")
        if not tag or len(tag) > 60 or tag.lower() in seen:
            continue
        if any(word in tag.lower() for word in banned):
            continue
        if total + len(tag) > max_total:
            break
        seen.add(tag.lower())
        clean.append(tag)
        total += len(tag)
    return clean[:limit] or ["piano", "relaxing piano"]


def upload_to_youtube(video_path, title, description, tags=None, category_id="10", privacy_status="public"):
    """
    Uploads long-form video to YouTube. Category 10 = Music.
    Bounded resumable loop: fails loudly instead of hanging to the job timeout.
    """
    upload_yt = os.getenv("UPLOAD_YOUTUBE", "true").lower()
    if upload_yt in ("false", "0", "no"):
        print("[youtube] Skipping YouTube upload (UPLOAD_YOUTUBE=false).")
        return None

    if tags is None:
        tags = [
            "piano", "relaxing piano", "study music", "sleep music", "piano visualizer",
            "pianospheric", "meditation piano", "calm piano", "peaceful piano",
            "ambient piano", "deep focus", "15 min piano", "instrumental piano"
        ]
    tags = _clean_tags(tags)

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": category_id
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
            # containsSyntheticMedia is deliberately unset: YouTube requires
            # disclosure only for realistic depictions of real people/events,
            # and animated piano visuals are exempt.
        }
    }

    media = MediaFileUpload(
        str(video_path),
        chunksize=10 * 1024 * 1024,
        resumable=True,
        mimetype="video/mp4"
    )

    print(f"[youtube] Uploading Video: {title}")
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    try:
        max_attempts = int(os.getenv("PIA_YT_MAX_CHUNKS", "2000"))
    except Exception:
        max_attempts = 2000
    try:
        deadline_sec = float(os.getenv("PIA_YT_UPLOAD_TIMEOUT_SEC", "5400"))
    except Exception:
        deadline_sec = 5400.0
    start = time.time()
    response = None
    attempts = 0
    while response is None:
        attempts += 1
        if attempts > max_attempts or (time.time() - start) > deadline_sec:
            raise RuntimeError(
                f"YouTube upload stalled (attempts={attempts}, elapsed={time.time() - start:.0f}s). "
                "Aborting instead of hanging to the job timeout."
            )
        status, response = request.next_chunk(num_retries=5)
        if status:
            pct = int(status.progress() * 100)
            print(f"  --> Upload progress: {pct}%")

    video_id = response.get("id")
    print(f"[youtube] Upload Complete! Video ID: {video_id}")
    print(f"[youtube] URL: https://youtu.be/{video_id}")
    return video_id


def set_video_thumbnail(video_id, thumbnail_path):
    """Sets custom thumbnail on uploaded YouTube video."""
    if not os.path.exists(thumbnail_path):
        print(f"[youtube] Thumbnail path not found: {thumbnail_path}")
        return False

    youtube = get_authenticated_service()
    print(f"[youtube] Setting custom thumbnail for Video ID: {video_id}...")
    try:
        media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
        print("[youtube] Thumbnail successfully set!")
        return True
    except Exception as e:
        print(f"[youtube] Failed to set thumbnail: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--validate":
        ok, reason = validate_youtube_credentials()
        print(f"[youtube] validate: ok={ok} ({reason})")
        sys.exit(0 if ok else 2)
    if len(sys.argv) > 3:
        upload_to_youtube(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print("Usage: python publish_youtube.py <video_path> <title> <description> | --validate")
