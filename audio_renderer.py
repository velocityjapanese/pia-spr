import os
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
FLUIDSYNTH_EXE = os.path.join(PROJECT_DIR, 'bin', 'fluidsynth', 'fluidsynth-v2.6.1-win10-x64-cpp11', 'bin', 'fluidsynth.exe')
DEFAULT_SF2 = os.path.join(PROJECT_DIR, 'soundfonts', 'Yamaha_Grand.sf2')

def render_midi_to_audio(midi_path, output_wav=None, sf2_path=None, sample_rate=44100):
    if not output_wav:
        output_wav = os.path.splitext(midi_path)[0] + '.wav'
    if not sf2_path:
        sf2_path = DEFAULT_SF2

    cmd = [
        FLUIDSYNTH_EXE,
        '-ni',
        '-F', output_wav,
        '-r', str(sample_rate),
        '-g', '0.85',
        sf2_path,
        midi_path
    ]

    print(f"Rendering studio audio with FluidSynth: {midi_path} -> {output_wav}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if not os.path.exists(output_wav) or os.path.getsize(output_wav) == 0:
        raise RuntimeError(f"FluidSynth failed: {result.stderr}")

    print(f"Audio synthesized successfully ({os.path.getsize(output_wav)} bytes)")
    return output_wav

if __name__ == '__main__':
    render_midi_to_audio('longform_test.mid')
