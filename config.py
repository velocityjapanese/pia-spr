"""Shared constants and paths for the PianoSpheric pipeline."""
import os
import shutil

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
WORK_DIR = os.path.join(OUTPUT_DIR, "work")
FINAL_EXPORT_DIR = os.path.join(os.path.dirname(PROJECT_DIR), "FINAL_EXPORTED_VIDEOS")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
SOUNDFONT_DIR = os.path.join(PROJECT_DIR, "soundfonts")

CHANNEL_NAME = (os.getenv("CHANNEL_NAME") or "PianoSpheric").strip() or "PianoSpheric"
SAMPLE_RATE = 48000

# ---------------------------------------------------------------------------
# Video / scene geometry
# ---------------------------------------------------------------------------
W, H = 1920, 1080
FPS = 30
SCROLL_PX_PER_FRAME = 4          # 120 px / second
SCROLL_PX_PER_SEC = SCROLL_PX_PER_FRAME * FPS
HIT_Y = 800                      # note bottoms meet the top of the keyboard

STRIP_Y = 640                    # keyboard strip (overlay) top
STRIP_H = 440
KEYBOARD_Y_IN_STRIP = 160        # global 800
KEYBOARD_H = 240
FLOOR_H = STRIP_H - KEYBOARD_Y_IN_STRIP - KEYBOARD_H   # 40 px

KEYBOARD_MARGIN_X = 64
KEYBOARD_TOP_SHADOW = 34         # felt / fallboard shadow above the keys

# ---------------------------------------------------------------------------
# Palettes. Values are RGB. Notes are screened onto a near-black background,
# so mid-brightness colours read as luminous without clipping.
# ---------------------------------------------------------------------------
PALETTES = {
    "midnight": {
        "bg_top": (4, 7, 16),
        "bg_bottom": (14, 24, 52),
        "lh": (92, 146, 214),
        "rh": (176, 216, 255),
        "accent": (222, 238, 255),
        "key_glow": (120, 180, 255),
        "title": (236, 243, 255),
    },
    "ember": {
        "bg_top": (9, 6, 4),
        "bg_bottom": (40, 22, 10),
        "lh": (176, 96, 44),
        "rh": (255, 188, 112),
        "accent": (255, 228, 176),
        "key_glow": (255, 178, 92),
        "title": (255, 242, 220),
    },
    "lavender": {
        "bg_top": (7, 5, 15),
        "bg_bottom": (30, 18, 52),
        "lh": (124, 98, 192),
        "rh": (206, 176, 255),
        "accent": (240, 228, 255),
        "key_glow": (176, 148, 255),
        "title": (244, 238, 255),
    },
    "forest": {
        "bg_top": (3, 9, 8),
        "bg_bottom": (14, 38, 32),
        "lh": (54, 132, 100),
        "rh": (142, 228, 192),
        "accent": (220, 255, 242),
        "key_glow": (110, 220, 180),
        "title": (234, 255, 246),
    },
    "ocean": {
        "bg_top": (2, 7, 14),
        "bg_bottom": (10, 30, 56),
        "lh": (36, 108, 162),
        "rh": (116, 198, 240),
        "accent": (216, 244, 255),
        "key_glow": (92, 180, 240),
        "title": (230, 248, 255),
    },
    "rose": {
        "bg_top": (11, 4, 8),
        "bg_bottom": (44, 16, 30),
        "lh": (166, 76, 108),
        "rh": (255, 158, 182),
        "accent": (255, 228, 236),
        "key_glow": (255, 140, 172),
        "title": (255, 240, 244),
    },
}

PALETTE_ORDER = ["midnight", "ember", "lavender", "forest", "ocean", "rose"]


# ---------------------------------------------------------------------------
# External tools
# ---------------------------------------------------------------------------
def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    local = os.path.join(PROJECT_DIR, "bin", "ffmpeg", "ffmpeg.exe")
    return local if os.path.exists(local) else "ffmpeg"


def find_ffprobe():
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    local = os.path.join(PROJECT_DIR, "bin", "ffmpeg", "ffprobe.exe")
    return local if os.path.exists(local) else "ffprobe"


def find_fluidsynth():
    exe = shutil.which("fluidsynth")
    if exe:
        return exe
    local = os.path.join(
        PROJECT_DIR, "bin", "fluidsynth", "fluidsynth-v2.6.1-win10-x64-cpp11", "bin", "fluidsynth.exe"
    )
    return local if os.path.exists(local) else None


FFMPEG = find_ffmpeg()
FFPROBE = find_ffprobe()
