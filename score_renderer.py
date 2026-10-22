import os
import mido
import music21
import verovio
import resvg_py
from PIL import Image, ImageDraw, ImageFont

def get_bar_timestamps(midi_path):
    """
    Computes exact timestamps (in seconds) for every measure boundary in the MIDI file,
    correctly accounting for all tempo changes across movements.
    """
    mid = mido.MidiFile(midi_path)
    bar_ticks = mid.ticks_per_beat * 4
    tempo_map = []
    abs_tick = 0
    for msg in mid.tracks[0]:
        abs_tick += msg.time
        if msg.type == 'set_tempo':
            tempo_map.append((abs_tick, msg.tempo))
    if not tempo_map or tempo_map[0][0] > 0:
        tempo_map.insert(0, (0, 500000))
        
    total_ticks = max(sum(m.time for m in t) for t in mid.tracks)
    num_bars = int(total_ticks / bar_ticks)
    
    bar_seconds = [0.0]
    curr_tick = 0
    curr_sec = 0.0
    tempo_idx = 0
    
    for b in range(1, num_bars + 1):
        target_tick = b * bar_ticks
        while curr_tick < target_tick:
            next_tempo_tick = tempo_map[tempo_idx + 1][0] if (tempo_idx + 1 < len(tempo_map)) else total_ticks + 1000
            step_end_tick = min(target_tick, next_tempo_tick)
            delta_ticks = step_end_tick - curr_tick
            curr_tempo = tempo_map[tempo_idx][1]
            curr_sec += mido.tick2second(delta_ticks, mid.ticks_per_beat, curr_tempo)
            curr_tick = step_end_tick
            if curr_tick == next_tempo_tick and tempo_idx + 1 < len(tempo_map):
                tempo_idx += 1
        bar_seconds.append(curr_sec)
    return bar_seconds

def render_score_card_image(grand_score, tk, temp_xml_path, card_w=700, card_h=240, bar_label="Measures 1–2"):
    grand_score.write('musicxml', temp_xml_path)
    tk.loadFile(temp_xml_path)
    svg = tk.renderToSVG(1)
    png_bytes = resvg_py.svg_to_bytes(svg_string=svg)

    temp_bw = temp_xml_path.replace('.xml', '_bw.png')
    with open(temp_bw, 'wb') as f:
        f.write(png_bytes)

    # Invert to crisp white on transparent
    img = Image.open(temp_bw).convert('RGBA')
    r, g, b, a = img.split()
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    white_score = Image.new('RGBA', img.size, (255, 255, 255, 255))
    out.paste(white_score, mask=a)

    # Dark obsidian glass card container
    card = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    draw.rounded_rectangle((0, 0, card_w, card_h), radius=16, fill=(10, 12, 16, 230), outline=(255, 195, 50, 160), width=2)

    # Header tags inside card
    font_tag = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 13)
    font_bar = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)

    # Golden "SHEET MUSIC" pill
    draw.rounded_rectangle((20, 14, 125, 34), radius=8, fill=(255, 195, 50, 50), outline=(255, 195, 50, 200), width=1)
    draw.text((29, 16), "SHEET MUSIC", font=font_tag, fill=(255, 220, 110, 255))

    # Measure label (e.g. Measures 3-4)
    draw.text((140, 16), bar_label, font=font_bar, fill=(210, 215, 225, 230))

    # Scale notation to fit inside card
    target_score_w = card_w - 40
    sc_scale = target_score_w / out.width
    target_score_h = int(out.height * sc_scale)
    sc_scaled = out.resize((target_score_w, target_score_h), Image.Resampling.LANCZOS)
    card.alpha_composite(sc_scaled, (20, 38 + (card_h - 40 - target_score_h) // 2))

    if os.path.exists(temp_xml_path):
        os.remove(temp_xml_path)
    if os.path.exists(temp_bw):
        os.remove(temp_bw)

    return card

def generate_synced_score_sequence(midi_path, output_dir, bars_per_slide=2):
    """
    Renders an evolving, fully synced sequence of sheet music cards.
    Each card displays exactly 2 measures as they are played, flipping in sync with the song.
    Writes score_concat.txt for instant FFmpeg demuxing.
    """
    os.makedirs(output_dir, exist_ok=True)
    bar_seconds = get_bar_timestamps(midi_path)
    total_bars = len(bar_seconds) - 1

    midi_score = music21.converter.parse(midi_path)
    parts = list(midi_score.parts)
    if len(parts) >= 2:
        rh_source = list(parts[0].flatten().notesAndRests)
        lh_source = list(parts[1].flatten().notesAndRests)
    else:
        all_notes = list(midi_score.flatten().notesAndRests)
        rh_source = [n for n in all_notes if getattr(n, 'pitch', None) and n.pitch.midi >= 60]
        lh_source = [n for n in all_notes if getattr(n, 'pitch', None) and n.pitch.midi < 60]

    tk = verovio.toolkit()
    tk.setOptions({
        'pageWidth': 1100,
        'pageHeight': 380,
        'scale': 60,
        'adjustPageHeight': 1,
        'header': 'none',
        'footer': 'none',
        'breaks': 'none',
        'font': 'Leipzig'
    })

    num_slides = (total_bars + bars_per_slide - 1) // bars_per_slide
    concat_lines = ["ffconcat version 1.0\n"]
    card_w, card_h = 700, 240

    print(f"Generating Synced Sheet Music Sequence: {num_slides} measure cards ({total_bars} total bars)...")

    for slide_idx in range(num_slides):
        start_bar = slide_idx * bars_per_slide
        end_bar = min(start_bar + bars_per_slide, total_bars)
        start_offset = start_bar * 4.0
        end_offset = end_bar * 4.0

        rh_part = music21.stream.Part(id='RH')
        rh_part.append(music21.clef.TrebleClef())
        rh_part.append(music21.meter.TimeSignature('4/4'))

        lh_part = music21.stream.Part(id='LH')
        lh_part.append(music21.clef.BassClef())
        lh_part.append(music21.meter.TimeSignature('4/4'))

        for elem in rh_source:
            if start_offset <= elem.offset < end_offset:
                rh_part.insert(elem.offset - start_offset, elem)
        for elem in lh_source:
            if start_offset <= elem.offset < end_offset:
                lh_part.insert(elem.offset - start_offset, elem)

        rh_part.makeMeasures(inPlace=True)
        lh_part.makeMeasures(inPlace=True)
        grand = music21.stream.Score()
        grand.insert(0, rh_part)
        grand.insert(0, lh_part)
        grand.insert(0, music21.layout.StaffGroup([rh_part, lh_part], name='Piano', symbol='brace', barTogether='Mensurstrich'))

        temp_xml = os.path.join(output_dir, f"temp_chunk_{slide_idx}.xml")
        card_img = render_score_card_image(
            grand, tk, temp_xml, card_w=card_w, card_h=card_h, 
            bar_label=f"Measures {start_bar+1}–{end_bar}"
        )

        card_png_name = f"score_chunk_{slide_idx:03d}.png"
        card_png_path = os.path.join(output_dir, card_png_name)
        card_img.save(card_png_path)

        # Duration in seconds for this slide
        dur_sec = bar_seconds[end_bar] - bar_seconds[start_bar]
        if dur_sec <= 0.05:
            dur_sec = 4.0

        # Note: in ffconcat, relative file names work when ffmpeg runs in output_dir or absolute paths
        concat_lines.append(f"file '{card_png_name}'\n")
        concat_lines.append(f"duration {dur_sec:.6f}\n")

    # Repeat last frame for EOF handling as required by ffconcat
    last_card_name = f"score_chunk_{num_slides-1:03d}.png"
    concat_lines.append(f"file '{last_card_name}'\n")

    concat_file_path = os.path.join(output_dir, "score_concat.txt")
    with open(concat_file_path, 'w', encoding='utf-8') as f:
        f.writelines(concat_lines)

    print(f"Synced Sheet Music Sequence ready: {num_slides} cards -> {concat_file_path}")
    return concat_file_path

def create_longform_score_card(midi_path, output_png, max_bars=2):
    """
    Renders a compact, high-resolution dark-mode floating sheet music card
    specifically designed for 16:9 horizontal YouTube videos.
    """
    midi_score = music21.converter.parse(midi_path)
    grand_score = music21.stream.Score()

    rh_part = music21.stream.Part()
    rh_part.id = 'RH'
    rh_part.append(music21.clef.TrebleClef())
    rh_part.append(music21.meter.TimeSignature('4/4'))

    lh_part = music21.stream.Part()
    lh_part.id = 'LH'
    lh_part.append(music21.clef.BassClef())
    lh_part.append(music21.meter.TimeSignature('4/4'))

    parts = list(midi_score.parts)
    if len(parts) >= 2:
        rh_source = parts[0].flatten().notesAndRests
        lh_source = parts[1].flatten().notesAndRests
    else:
        all_notes = midi_score.flatten().notesAndRests
        rh_source = [n for n in all_notes if getattr(n, 'pitch', None) and n.pitch.midi >= 60]
        lh_source = [n for n in all_notes if getattr(n, 'pitch', None) and n.pitch.midi < 60]

    for elem in rh_source:
        if elem.offset < max_bars * 4:
            rh_part.insert(elem.offset, elem)
    for elem in lh_source:
        if elem.offset < max_bars * 4:
            lh_part.insert(elem.offset, elem)

    rh_part.makeMeasures(inPlace=True)
    lh_part.makeMeasures(inPlace=True)
    grand_score.insert(0, rh_part)
    grand_score.insert(0, lh_part)

    staff_group = music21.layout.StaffGroup([rh_part, lh_part], name='Piano', symbol='brace', barTogether='Mensurstrich')
    grand_score.insert(0, staff_group)

    xml_path = output_png.replace('.png', '.xml')
    grand_score.write('musicxml', xml_path)

    # Verovio SVG
    tk = verovio.toolkit()
    tk.setOptions({
        'pageWidth': 1100,
        'pageHeight': 380,
        'scale': 60,
        'adjustPageHeight': 1,
        'header': 'none',
        'footer': 'none',
        'breaks': 'none',
        'font': 'Leipzig'
    })
    tk.loadFile(xml_path)
    svg = tk.renderToSVG(1)

    png_bytes = resvg_py.svg_to_bytes(svg_string=svg)
    temp_bw = output_png.replace('.png', '_bw.png')
    with open(temp_bw, 'wb') as f:
        f.write(png_bytes)

    # Invert to white on black
    img = Image.open(temp_bw).convert('RGBA')
    r, g, b, a = img.split()
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    white_score = Image.new('RGBA', img.size, (255, 255, 255, 255))
    out.paste(white_score, mask=a)

    # Frame into a dark glassmorphic floating pill card (700 x 240)
    card_w, card_h = 700, 240
    card = Image.new('RGBA', (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    # Rounded frosted dark container with gold border
    draw.rounded_rectangle((0, 0, card_w, card_h), radius=16, fill=(12, 12, 16, 220), outline=(255, 195, 50, 140), width=2)
    
    # Pill tag
    font_tag = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
    draw.rounded_rectangle((20, 14, 115, 34), radius=8, fill=(255, 195, 50, 40), outline=(255, 195, 50, 180), width=1)
    draw.text((28, 16), "SHEET MUSIC", font=font_tag, fill=(255, 215, 90, 255))

    # Scale score to fit inside card
    target_score_w = card_w - 40
    sc_scale = target_score_w / out.width
    target_score_h = int(out.height * sc_scale)
    sc_scaled = out.resize((target_score_w, target_score_h), Image.Resampling.LANCZOS)
    card.alpha_composite(sc_scaled, (20, 38 + (card_h - 40 - target_score_h) // 2))

    card.save(output_png)

    if os.path.exists(xml_path):
        os.remove(xml_path)
    if os.path.exists(temp_bw):
        os.remove(temp_bw)

    print(f"Generated 16:9 Longform Floating Score Card: {output_png}")
    return output_png

if __name__ == '__main__':
    create_longform_score_card('longform_test.mid', 'longform_score_card.png')
