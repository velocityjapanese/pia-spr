import os
import subprocess

import mido

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
MIDIVIZ_EXE = os.path.join(PROJECT_DIR, 'bin', 'MIDIVisualizer', 'MIDIVisualizer.exe')


def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _midi_duration_sec(midi_path, default=900.0):
    try:
        mid = mido.MidiFile(midi_path)
        return max(1.0, float(mid.length) + 1.0)
    except Exception:
        return float(default)


def render_fallback_visualizer(midi_path, output_video, framerate=30, width=1920, height=1080):
    """Lightweight CPU fallback: dark cosmic background video with matching duration."""
    duration = _midi_duration_sec(midi_path)
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', f'color=c=0x0a0c12:s={width}x{height}:d={duration:.1f}:r={framerate}',
        '-filter_complex',
        '[0:v]vignette=angle=PI/5,eq=contrast=1.1:saturation=1.2[v]',
        '-map', '[v]',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
        '-t', f'{duration:.1f}',
        output_video,
    ]
    print(f"Rendering fallback visualizer ({duration:.0f}s, {width}x{height}@{framerate}fps)...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1200)
    if not os.path.exists(output_video) or os.path.getsize(output_video) == 0:
        raise RuntimeError(f"Fallback visualizer failed: {result.stderr[-2000:]}")
    print(f"Fallback visualizer ready ({os.path.getsize(output_video)} bytes)")
    return output_video


def render_longform_visualizer(midi_path, output_video=None, framerate=30, width=1920, height=1080, timeout_sec=None):
    """
    Renders 16:9 Landscape YouTube Piano Visualizer (1920x1080).
    Tunable for CI: PIA_VIZ_QUALITY, PIA_VIZ_PARTICLES, PIA_VIZ_TIMEOUT_SEC,
    PIA_VIZ_DISABLE_FX=1 (drops blur/wave/particles for speed),
    PIA_VIZ_FALLBACK=1 (skip MIDIVisualizer entirely).
    """
    if not output_video:
        output_video = os.path.splitext(midi_path)[0] + '_viz.mp4'

    if os.getenv('PIA_VIZ_FALLBACK', '').lower() in ('1', 'true', 'yes'):
        return render_fallback_visualizer(midi_path, output_video, framerate, width, height)

    quality = os.getenv('PIA_VIZ_QUALITY', 'HIGH').strip() or 'HIGH'
    particles = _env_int('PIA_VIZ_PARTICLES', 96)
    disable_fx = os.getenv('PIA_VIZ_DISABLE_FX', '').lower() in ('1', 'true', 'yes')
    if timeout_sec is None:
        timeout_sec = _env_int('PIA_VIZ_TIMEOUT_SEC', 4200)

    show_particles = '0' if disable_fx else '1'
    show_blur = '0' if disable_fx else '1'
    show_wave = '0' if disable_fx else '1'

    cmd = [
        MIDIVIZ_EXE,
        '--midi', midi_path,
        '--export', output_video,
        '--format', 'MPEG4',
        '--size', str(width), str(height),
        '--framerate', str(framerate),
        '--hide-window', '1',
        '--preroll', '0.0',
        '--postroll', '1.0',
        '--min-key', '21',
        '--max-key', '108',
        '--quality', quality,
        '--smooth', '1',
        '--show-pedal', '0',
        '--show-score', '0',
        '--show-keyboard', '1',
        '--show-notes', '1',
        '--show-particles', show_particles,
        '--particles-count', str(particles),
        '--particles-size', '4.0',
        '--particles-turbulences', '2.5',
        '--particles-speed', '1.5',
        '--particles-expansion', '1.3',
        '--show-flashes', '1',
        '--flashes-size', '1.8',
        '--flashes-halo-intensity', '1.5',
        '--flashes-halo-outer', '0.7',
        '--show-blur', show_blur,
        '--show-blur-notes', show_blur,
        '--blur-attenuation', '0.82',
        '--show-wave', show_wave,
        '--wave-amplitude', '1.5',
        '--wave-frequency', '2.2',
        '--wave-noise-intensity', '1.3',
        '--wave-opacity', '0.85',
        '--lock-colors', '1',
        '--color-major', '1.0', '0.78', '0.15',
        '--color-minor', '0.95', '0.65', '0.1',
        '--color-particles', '1.0', '0.85', '0.3',
        '--color-flashes', '1.0', '0.8', '0.2',
        '--color-wave', '1.0', '0.8', '0.2',
    ]

    print(f"Rendering 16:9 Long-Form Visualizer: {midi_path} -> {output_video}")
    print(f"[viz] quality={quality} particles={particles} fx_disabled={disable_fx} timeout={timeout_sec}s")
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        print(f"[viz] MIDIVisualizer timed out after {timeout_sec}s, using fallback renderer.")
        return render_fallback_visualizer(midi_path, output_video, framerate, width, height)
    if not os.path.exists(output_video) or os.path.getsize(output_video) == 0:
        err = (result.stderr or '')[-2000:]
        print(f"[viz] MIDIVisualizer failed ({err}), using fallback renderer.")
        return render_fallback_visualizer(midi_path, output_video, framerate, width, height)

    print(f"16:9 Visualizer rendered successfully ({os.path.getsize(output_video)} bytes)")
    return output_video


if __name__ == '__main__':
    render_longform_visualizer('longform_test.mid')
