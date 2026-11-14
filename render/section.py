"""Renders one section: background + scrolling notes + keyboard strip + title."""
import collections
import os
import subprocess
import threading

from config import FFMPEG, FFPROBE, FPS, H, SCROLL_PX_PER_FRAME, STRIP_H, STRIP_Y, W, WORK_DIR
from render.keyboard_strip import stream_section
from render.notes_layer import render_roll
from render.scene import make_background, make_distance_layers, make_title_card

ENC_ARGS = [
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
    "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
    "-x264-params", "aq-mode=3:keyint=60:min-keyint=60:scenecut=0",
    "-threads", "2", "-filter_complex_threads", "2",
    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
    "-color_range", "tv", "-an",
]


def section_paths(index, work_dir):
    stem = os.path.join(work_dir, f"s{index:02d}")
    return {
        "stem": stem,
        "bg": stem + "_bg.png",
        "roll": stem + "_roll.png",
        "title": stem + "_title.png",
        "out": stem + ".mp4",
    }


def render_section(task):
    section, notes, work_dir, seed, resume = task
    paths = section_paths(section["index"], work_dir)
    if resume and _valid_section(paths["out"], section["frames"]):
        return paths["out"], True

    bg = make_background(section["palette"], seed + section["index"])
    bg.save(paths["bg"])
    title = make_title_card(section["name"], section["palette"])
    title.save(paths["title"])
    render_roll(section, notes, paths["roll"])
    dof_mask, dist_grad = make_distance_layers(section["index"], work_dir)
    _encode(section, notes, paths, seed, dof_mask, dist_grad)
    if not _valid_section(paths["out"], section["frames"]):
        raise RuntimeError(f"section {section['index']} produced an invalid file")
    return paths["out"], False


def _encode(section, notes, paths, seed, dof_mask, dist_grad):
    frames = section["frames"]
    filter_graph = (
        "[0:v]format=gbrp,loop=loop=-1:size=1:start=0[bg]; "
        f"[1:v]format=gbrp,loop=loop=-1:size=1:start=0,crop={W}:{H}:0:(ih-{H})-{SCROLL_PX_PER_FRAME}*n[roll]; "
        "[roll]split[sharp][soft]; "
        "[soft]scale=480:270:flags=bilinear,gblur=sigma=1.8:steps=2,"
        "scale=1920:1080:flags=bilinear,format=gbrp[far]; "
        # far feeds two filters; an explicit split is required or the blend
        # framesync ends the graph after the first frame (notes freeze).
        "[far]split[far1][far2]; "
        "[4:v]format=gray,loop=loop=-1:size=1:start=0[dofm]; "
        "[sharp][far1][dofm]maskedmerge[dof]; "
        "[dof][far2]blend=all_mode=screen:all_opacity=0.34:shortest=1[bloom]; "
        "[5:v]format=gbrp,loop=loop=-1:size=1:start=0[dist]; "
        "[bloom][dist]blend=all_mode=multiply:shortest=1[dim]; "
        "[bg][dim]blend=all_mode=screen:shortest=1[lit]; "
        f"[lit][3:v]overlay=0:{STRIP_Y}:eof_action=repeat[v1]; "
        "[2:v]format=rgba,loop=loop=-1:size=1:start=0,"
        "fade=t=in:st=0:d=0.45:alpha=1,fade=t=out:st=1.55:d=0.55:alpha=1[t]; "
        "[v1][t]overlay=0:0:enable='lte(t,2.2)'[v2]; "
        "[v2]eq=contrast=1.04:saturation=1.12:gamma=1.05,format=yuv420p[v]"
    )
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "warning", "-nostats",
        "-framerate", str(FPS), "-i", paths["bg"],
        "-framerate", str(FPS), "-i", paths["roll"],
        "-framerate", str(FPS), "-i", paths["title"],
        "-f", "rawvideo", "-pixel_format", "rgba",
        "-video_size", f"{W}x{STRIP_H}", "-framerate", str(FPS), "-i", "pipe:0",
        "-framerate", str(FPS), "-i", dof_mask,
        "-framerate", str(FPS), "-i", dist_grad,
        "-filter_complex", filter_graph,
        "-map", "[v]", "-frames:v", str(frames), "-r", str(FPS),
        *ENC_ARGS, paths["out"],
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    tail = collections.deque(maxlen=60)

    def drain():
        for line in proc.stderr:
            tail.append(line.decode("utf-8", "replace"))

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        stream_section(section, notes, proc.stdin, seed)
    except BrokenPipeError:
        pass
    proc.wait()
    reader.join(timeout=5)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg section {section['index']} failed:\n" + "".join(tail)[-3000:])


def _valid_section(path, frames):
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        return False
    try:
        res = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "stream=nb_frames", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=30)
        return int(res.stdout.strip() or 0) == frames
    except Exception:
        return False
