"""FluidSynth rendering plus a mastering chain for a realistic grand piano."""
import glob
import json
import os
import re
import struct
import subprocess

import numpy as np

from config import FFMPEG, PROJECT_DIR, SAMPLE_RATE, SOUNDFONT_DIR, WORK_DIR, find_fluidsynth


def resolve_soundfont():
    preferred = os.getenv("PIANO_SF2", "").strip()
    if preferred and os.path.exists(preferred):
        return preferred
    for pattern in ("Salamander*.sf2", "*Salamander*.sf2", "Yamaha_Grand.sf2"):
        hits = sorted(glob.glob(os.path.join(SOUNDFONT_DIR, pattern)))
        for hit in hits:
            if os.path.getsize(hit) > 10 * 1024 * 1024:
                return hit
    hits = [p for p in glob.glob(os.path.join(SOUNDFONT_DIR, "*.sf2"))
            if "timgm6mb" not in os.path.basename(p).lower()]
    if hits:
        return sorted(hits, key=os.path.getsize, reverse=True)[0]
    fallback = os.path.join(SOUNDFONT_DIR, "TimGM6mb.sf2")
    if os.path.exists(fallback):
        print("[audio] WARNING: using the 6 MB TimGM6mb fallback soundfont.")
        return fallback
    raise RuntimeError("No soundfont found in soundfonts/")


def _write_wav_f32(path, mono, sample_rate):
    data = np.asarray(mono, dtype="<f4").tobytes()
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + len(data)))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 3, 1, sample_rate,
                            sample_rate * 4, 4, 32))
        f.write(b"data")
        f.write(struct.pack("<I", len(data)))
        f.write(data)


def ensure_hall_ir(path, seconds=2.0):
    """Build a diffuse stereo-stage hall IR.

    No discrete early reflections: a handful of spikes at fixed delays is
    what makes a synthetic reverb sound like a small tiled room. Energy is
    normalised to 1 so afir's wet gain maps directly to reverb level.
    """
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rng = np.random.default_rng(11)
    n = int(seconds * SAMPLE_RATE)
    t = np.arange(n, dtype=np.float64) / SAMPLE_RATE

    noise = rng.standard_normal(n)
    # Split into bands whose tails decay at different rates, so the high
    # end dies away first the way air absorption works in a real hall.
    k = max(8, int(0.018 * SAMPLE_RATE))
    low = np.convolve(noise, np.ones(k) / k, mode="same")
    high = noise - low
    ir = (low * np.exp(-t * 2.6) * 0.95
          + high * np.exp(-t * 7.0) * 0.28)

    # Soft onset: no dry-sounding slap, just a gently swelling diffuse field.
    attack = int(0.035 * SAMPLE_RATE)
    ir[:attack] *= np.linspace(0.0, 1.0, attack) ** 1.5

    fade_len = int(0.4 * SAMPLE_RATE)
    ir[-fade_len:] *= np.linspace(1.0, 0.0, fade_len)
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-12
    _write_wav_f32(path, ir, SAMPLE_RATE)
    return path


def render_audio(midi_path, output_wav, work_dir=None):
    fluid = find_fluidsynth()
    if not fluid:
        raise RuntimeError("fluidsynth not found (install it or keep bin/fluidsynth)")
    sf2 = resolve_soundfont()
    work_dir = work_dir or os.path.dirname(output_wav)
    os.makedirs(work_dir, exist_ok=True)
    raw_wav = os.path.join(work_dir, os.path.basename(output_wav).replace(".wav", "_raw.wav"))

    cmd = [
        fluid, "-ni", "-q",
        "-F", raw_wav, "-T", "wav", "-O", "float",
        "-r", str(SAMPLE_RATE), "-g", "0.8",
        "-o", "synth.polyphony=256",
        "-o", "synth.cpu-cores=2",
        "-o", "synth.chorus.active=0",
        # FluidSynth's built-in room is a cheap metallic Schroeder reverb;
        # the convolution hall below replaces it entirely.
        "-o", "synth.reverb.active=0",
        sf2, midi_path,
    ]
    print(f"[audio] FluidSynth: {os.path.basename(sf2)} -> {os.path.basename(raw_wav)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(raw_wav) or os.path.getsize(raw_wav) < 1024:
        raise RuntimeError(f"FluidSynth failed:\n{res.stderr[-2000:]}")

    master_audio(raw_wav, output_wav, work_dir)
    return output_wav


def master_audio(raw_wav, output_wav, work_dir):
    # v2: single convolution hall, close-miked clarity, no post-reverb boost.
    ir = ensure_hall_ir(os.path.join(WORK_DIR, "hall_clean_2.0s.wav"))
    processed = os.path.join(work_dir, os.path.basename(output_wav).replace(".wav", "_proc.wav"))

    chain = (
        # 26 Hz keeps the lowest A of a concert grand, the lowpass tames the
        # brittle top of sampled attacks without dulling the sustain.
        "[0:a]highpass=f=26,lowpass=f=18000,"
        "equalizer=f=110:t=q:w=0.8:g=0.8,"
        "equalizer=f=280:t=q:w=1.0:g=-1.4,"
        "equalizer=f=850:t=q:w=1.2:g=-0.8,"
        "equalizer=f=2600:t=q:w=1.2:g=0.9,"
        "equalizer=f=9500:t=q:w=1.0:g=0.7,"
        "acompressor=threshold=0.2:ratio=1.5:attack=30:release=400:knee=8:makeup=1,"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,asplit[dry][conv];"
        "[1:a]aformat=sample_fmts=fltp:channel_layouts=mono[ir];"
        # Some ffmpeg builds drop afir's dry path entirely (dry behaves like
        # a multiplier), so the dry/wet mix is done explicitly with amix.
        # The IR is energy-normalised: wet=0.2 is simply "20% of the direct
        # sound", not a room-sized wash.
        "[conv][ir]afir=dry=1:wet=1:gtype=none:irnorm=-1:irfmt=mono:irlink=1:maxir=3,"
        "volume=0.2[wv];"
        "[dry][wv]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        "stereowiden=delay=11:feedback=0.12:crossfeed=0.18:drymix=0.85,"
        "alimiter=limit=0.95:attack=5:release=80:level=0,"
        "aresample=48000:resampler=soxr:precision=28"
    )
    cmd = [FFMPEG, "-y", "-v", "error", "-i", raw_wav, "-i", ir,
           "-filter_complex", chain, "-c:a", "pcm_f32le", processed]
    _run(cmd, "tone/reverb mastering")

    measured = _measure_loudness(processed)
    apply_chain = (
        "loudnorm=I=-16:TP=-1.5:LRA=11"
        f":measured_I={measured['input_i']}:measured_LRA={measured['input_lra']}"
        f":measured_TP={measured['input_tp']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true,"
        "aresample=48000:resampler=soxr:precision=28"
    )
    cmd = [FFMPEG, "-y", "-v", "error", "-i", processed,
           "-af", apply_chain, "-c:a", "pcm_s24le", output_wav]
    _run(cmd, "loudness normalisation")
    print(f"[audio] Mastered {os.path.basename(output_wav)} "
          f"({measured['input_i']} LUFS -> -16 LUFS)")
    return output_wav


def _measure_loudness(path):
    cmd = [FFMPEG, "-hide_banner", "-nostats", "-i", path,
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    if not match:
        raise RuntimeError("Could not measure loudness:\n" + res.stderr[-1500:])
    return json.loads(match.group(0))


def _run(cmd, label):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed during {label}:\n{res.stderr[-2000:]}")


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "output/preview_42.mid"
    render_audio(src, src.replace(".mid", "_audio.wav"))
