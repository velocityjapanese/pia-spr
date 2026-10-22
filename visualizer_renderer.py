import os
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
MIDIVIZ_EXE = os.path.join(PROJECT_DIR, 'bin', 'MIDIVisualizer', 'MIDIVisualizer.exe')

def render_longform_visualizer(midi_path, output_video=None, framerate=30, width=1920, height=1080):
    """
    Renders 16:9 Landscape YouTube Piano Visualizer (1920x1080):
    - Full concert grand piano keyboard across the entire screen
    - 256 radiant golden sparks per burst
    - Key strike halo flares and motion trails
    - Golden energy wave along the keyboard edge
    """
    if not output_video:
        output_video = os.path.splitext(midi_path)[0] + '_viz.mp4'

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
        # Full 88-key / 6-octave concert grand keyboard
        '--min-key', '21',
        '--max-key', '108',
        # Quality & anti-aliasing
        '--quality', 'HIGH_RES',
        '--smooth', '1',
        # Clean HUD
        '--show-pedal', '0',
        '--show-score', '0',
        '--show-keyboard', '1',
        '--show-notes', '1',
        # Particle fireworks
        '--show-particles', '1',
        '--particles-count', '256',
        '--particles-size', '4.0',
        '--particles-turbulences', '2.5',
        '--particles-speed', '1.5',
        '--particles-expansion', '1.3',
        # Key strike flashes
        '--show-flashes', '1',
        '--flashes-size', '1.8',
        '--flashes-halo-intensity', '1.5',
        '--flashes-halo-outer', '0.7',
        # Cinematic motion blur
        '--show-blur', '1',
        '--show-blur-notes', '1',
        '--blur-attenuation', '0.82',
        # Fiery energy wave
        '--show-wave', '1',
        '--wave-amplitude', '1.5',
        '--wave-frequency', '2.2',
        '--wave-noise-intensity', '1.3',
        '--wave-opacity', '0.85',
        # Golden Amber Palette
        '--lock-colors', '1',
        '--color-major', '1.0', '0.78', '0.15',
        '--color-minor', '0.95', '0.65', '0.1',
        '--color-particles', '1.0', '0.85', '0.3',
        '--color-flashes', '1.0', '0.8', '0.2',
        '--color-wave', '1.0', '0.8', '0.2',
    ]

    print(f"Rendering 16:9 Long-Form Visualizer: {midi_path} -> {output_video}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if not os.path.exists(output_video) or os.path.getsize(output_video) == 0:
        raise RuntimeError(f"MIDIVisualizer failed: {result.stderr}")

    print(f"16:9 Visualizer rendered successfully ({os.path.getsize(output_video)} bytes)")
    return output_video

if __name__ == '__main__':
    render_longform_visualizer('longform_test.mid')
