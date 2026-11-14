"""Concatenate sections, add the audio tail, mux audio, export a hero frame."""
import json
import os
import subprocess

from config import FFMPEG, FFPROBE, FPS, H, W


def assemble(section_files, audio_path, out_path, work_dir, hero_time=60.0,
             hero_path=None):
    os.makedirs(work_dir, exist_ok=True)
    video_only = os.path.join(work_dir, "video_only.mp4")
    video_full = os.path.join(work_dir, "video_full.mp4")

    _concat(section_files, video_only, work_dir, "sections.txt")
    video_dur = _duration(video_only)
    audio_dur = _duration(audio_path)
    tail = audio_dur - video_dur

    files = list(section_files)
    if tail > 0.5:
        outro = _make_outro(section_files[-1], tail, work_dir)
        files.append(outro)
        _concat(files, video_full, work_dir, "sections_outro.txt")
    else:
        video_full = video_only

    print(f"[master] video={video_dur:.2f}s audio={audio_dur:.2f}s tail={max(0.0, tail):.2f}s")
    _mux(video_full, audio_path, out_path)

    info = probe(out_path)
    if abs(info["video_dur"] - info["audio_dur"]) > 0.3:
        raise RuntimeError(f"A/V duration mismatch: {info['video_dur']} vs {info['audio_dur']}")
    if (info["width"], info["height"]) != (W, H):
        raise RuntimeError(f"unexpected resolution: {info['width']}x{info['height']}")

    hero = hero_path or os.path.join(os.path.dirname(out_path), "hero.jpg")
    t = min(max(1.0, hero_time), max(1.0, info["video_dur"] - 1.0))
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", out_path, "-ss", f"{t:.2f}",
                    "-frames:v", "1", "-q:v", "2", hero], check=True)
    print(f"[master] final: {os.path.basename(out_path)}  {info['video_dur']:.1f}s  "
          f"{info['width']}x{info['height']}@{info['fps']:.2f}")
    return {"video": out_path, "hero": hero, **info}


def _concat(files, out_path, work_dir, list_name):
    list_path = os.path.join(work_dir, list_name)
    with open(list_path, "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        for p in files:
            f.write("file '" + os.path.abspath(p).replace("\\", "/").replace("'", r"'\''") + "'\n")
    res = subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
                          "-i", list_path, "-c", "copy", out_path],
                         capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError("concat failed:\n" + res.stderr[-2000:])


def _make_outro(last_section, tail, work_dir):
    last_frame = os.path.join(work_dir, "outro_last.png")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-sseof", "-0.08", "-i", last_section,
                    "-frames:v", "1", last_frame], check=True)
    frames = max(15, int(round(tail * FPS)))
    outro = os.path.join(work_dir, "outro.mp4")
    fade_start = 0.45
    fade_dur = max(0.8, tail - fade_start - 0.45)
    vf = (f"loop=loop=-1:size=1:start=0,fade=t=out:st={fade_start:.2f}:d={fade_dur:.2f},"
          "format=yuv420p")
    res = subprocess.run([FFMPEG, "-y", "-v", "error", "-framerate", str(FPS), "-i", last_frame,
                          "-vf", vf, "-frames:v", str(frames), "-r", str(FPS),
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                          "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
                          "-x264-params", "keyint=60:min-keyint=60:scenecut=0",
                          "-an", outro], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("outro render failed:\n" + res.stderr[-1500:])
    return outro


def _mux(video, audio, out_path):
    res = subprocess.run([FFMPEG, "-y", "-v", "error", "-i", video, "-i", audio,
                          "-map", "0:v:0", "-map", "1:a:0",
                          "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                          "-movflags", "+faststart", "-shortest", out_path],
                         capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError("mux failed:\n" + res.stderr[-2000:])


def _duration(path):
    res = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                          "-of", "json", path], capture_output=True, text=True, timeout=60)
    return float(json.loads(res.stdout)["format"]["duration"])


def probe(path):
    res = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate:format=duration",
                          "-of", "json", path], capture_output=True, text=True, timeout=60)
    data = json.loads(res.stdout)
    info = {"video_dur": float(data["format"]["duration"]), "audio_dur": 0.0,
            "width": 0, "height": 0, "fps": 0.0}
    for s in data["streams"]:
        if s["codec_type"] == "video" and not info["width"]:
            info["width"] = int(s["width"])
            info["height"] = int(s["height"])
            num, _, den = s["r_frame_rate"].partition("/")
            info["fps"] = float(num) / float(den or 1)
        if s["codec_type"] == "audio":
            info["audio_dur"] = float(data["format"]["duration"])
    return info
