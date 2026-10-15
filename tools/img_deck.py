#!/usr/bin/env python3
"""
img_deck.py — build a servable deck from a talk whose every slide IS a picture.

WHY THIS EXISTS

  The desk had one path to a published deck: draft -> md_to_dc.py -> a Claude Design
  canvas -> dc_to_deck.py -> talk_bundle.py. That path exists because a typographic
  deck needs design: type, grid, palette, a layout pass a person makes by hand.

  A talk can also be built the other way round. `recess-talk`'s figures knob is
  `spec-written-by-desk-generated-by-author`: the desk writes a written specification
  per slide, the author generates the image, and EVERY slide — the title, the movement
  markers, the claims — is one of those images, with its words carved or lettered
  inside the frame. There is no type to lay out, because there is no type.

  Put that deck through the canvas and the design pass has nothing to do, while the
  verification step (`md_to_dc.py verify`, which holds a canvas to the draft word for
  word) has nothing to read: the words are pixels. So the canvas is not a step that
  was skipped here; it is a step with no work in it. This tool is the short path for
  that case, and it ends in exactly the directory `talk_bundle.py` already expects.

  (Eric, 2026-10-15: *"can you create a new path to creating a deck out of images"*.)

  CHOOSING A PATH. A deck with text set as type on a slide goes through the canvas,
  because something has to decide how that type looks. A deck whose slides are
  finished pictures comes through here. A deck that mixes the two goes through the
  canvas: this tool refuses a slide it cannot render as one image, by design, rather
  than quietly rendering half of it.

  INPUT   talks/<slug>/draft.md    the script; the deck dialect of md_to_marp.py
          talks/<slug>/talk.yaml   title, size, and the talk's metadata
          talks/<slug>/assets/…    one image per slide
          --runtime <path>         deck-stage.js, vendored from the site project

  OUTPUT  <out>/deck.html          standalone: <deck-stage> + one <section> per slide
          <out>/notes.json         per-slide speaker notes, for a phone remote
          <out>/deck-stage.js
          <out>/assets/…           only the images the slides actually reference

  USAGE   python3 tools/img_deck.py <talk-dir> <out-dir> --runtime <deck-stage.js>
                  [--check] [--width N] [--quality N] [--keep-png]

          --check  verify and report, write nothing. Use it before a publish.
          --width    longest edge of the SERVED image (default 1600; 0 keeps the original)
          --quality  JPEG quality of the served image (default 82)
          --keep-png copy the masters through untouched instead

THE DESK KEEPS THE MASTERS; THE DECK SHIPS WHAT A PHONE CAN LOAD

  Generated images arrive as big PNGs — this talk's twenty-three are 2.3 MB each, 54 MB
  for one deck, which is not a page, it is a download. So the served copies are resized
  to `--width` and written as JPEG, while `talks/<slug>/assets/` keeps the originals: a
  slide can always be regenerated from the master, and the master is what the alt text
  was read against. A deck that cannot be served is not a deck, and a master that has
  been squeezed to serve it cannot be checked.

THE CONTRACT, AND THE ONE THING IT REFUSES

  EVERY SLIDE CARRIES EXACTLY ONE IMAGE. A slide with none, or with two, is a FAULT
  and the run stops naming it. That is the whole gate, and it is strict on purpose:
  a deck of pictures has no fallback rendering. A slide whose picture is missing is
  not a plainer slide, it is a blank one, and a blank slide in a published deck looks
  deliberate. `md_to_marp.py --check` can afford to warn here because its decks still
  render the words; this one cannot.

  The ALT TEXT of each image becomes the slide's accessible text, so the words a
  sighted viewer reads off the stone reach a screen reader as text. That is the only
  route they have: in this deck the slide's words are pixels. An empty alt is a FAULT
  for the same reason (framework/docs/ALT-TEXT.md).

  The SPEAKER NOTES are the draft's prose paragraphs, unchanged — the same notes
  md_to_marp.py puts in the Marp comments and dc_to_deck.py lifts out of the canvas.
  The draft stays the one source of the spoken script whichever path is used.

EXIT  0 built (or --check clean) · 1 usage · 2 a fault — the message names the slide
"""

import html
import json
import os
import re
import shutil
import struct
import sys

try:
    from PIL import Image
except ImportError:                                  # pragma: no cover - CI installs it
    Image = None

SLIDE_RE = re.compile(r'<!--\s*slide(?:\s*:\s*(.*?))?\s*-->')
DESIGN_RE = re.compile(r'<!--\s*design\s*:\s*(.*?)\s*-->', re.S)
MOVEMENT_RE = re.compile(r'^##\s+(.*)$')
FIG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)\s*$')


def die(code, msg):
    print(f'img_deck: {msg}', file=sys.stderr)
    sys.exit(code)


def read_manifest(path):
    man = {}
    if not os.path.exists(path):
        return man
    for ln in open(path, encoding='utf-8'):
        s = ln.split('#', 1)[0].rstrip()
        if not s or s.startswith(' ') or ':' not in s:
            continue
        k, v = s.split(':', 1)
        man[k.strip()] = v.strip().strip('"').strip("'")
    return man


def body_of(text):
    """Everything below the first `---` line; the header above it is scaffold."""
    lines = text.split('\n')
    for i, l in enumerate(lines):
        if l.strip() == '---':
            return '\n'.join(lines[i + 1:])
    return text


def assert_complete_png(path):
    """A truncated PNG renders as a broken slide and nothing upstream notices.
    Same check dc_to_deck.py makes, for the same reason."""
    with open(path, 'rb') as fh:
        if fh.read(8) != b'\x89PNG\r\n\x1a\n':
            return                                   # not a PNG; nothing to assert
        fh.seek(-12, os.SEEK_END)
        tail = fh.read(12)
    if tail[4:8] != b'IEND':
        die(2, f'{os.path.basename(path)}: PNG is truncated (no IEND)')


def png_size(path):
    try:
        with open(path, 'rb') as fh:
            head = fh.read(24)
        if head[:8] != b'\x89PNG\r\n\x1a\n':
            return None
        return struct.unpack('>II', head[16:24])
    except OSError:
        return None


def parse(text):
    """-> [{'label', 'movement', 'img', 'alt', 'notes': [str], 'design': [str]}]

    A movement heading opens a slide, as it does in md_to_marp.py; so does an
    explicit `<!-- slide -->`. Everything else is the image, the script, or scaffold.
    """
    slides, cur = [], None
    para, movement = [], ''

    def flush():
        nonlocal para
        if para and cur is not None:
            cur['notes'].append(' '.join(s.strip() for s in para))
        para = []

    for raw in body_of(text).split('\n'):
        line = raw.rstrip()
        m = MOVEMENT_RE.match(line)
        if m:
            flush()
            movement = m.group(1).strip()
            cur = {'label': movement, 'movement': movement, 'kind': 'section',
                   'img': None, 'alt': '', 'notes': [], 'design': []}
            slides.append(cur)
            continue
        m = SLIDE_RE.search(line)
        if m:
            flush()
            cur = {'label': (m.group(1) or '').strip(), 'movement': movement,
                   'kind': 'slide', 'img': None, 'alt': '', 'notes': [], 'design': []}
            slides.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith('<!--'):
            dm = DESIGN_RE.search(line)
            if dm:
                flush()
                cur['design'].append(dm.group(1).strip())
            continue
        if not line.strip():
            flush()
            continue
        f = FIG_RE.match(line.strip())
        if f:
            flush()
            if cur['img'] is not None:
                cur['_second'] = f.group(2)
            cur['img'], cur['alt'] = f.group(2), f.group(1)
            continue
        if line.startswith('>') or re.match(r'^\s*([-*]|\d+\.)\s+', line) or line.startswith('#'):
            flush()
            cur.setdefault('ontext', []).append(line.strip())
            continue
        para.append(line)
    flush()
    return slides


def verify(talk_dir, slides):
    """-> [fault strings]. Everything that would make a published deck wrong."""
    faults = []
    for i, s in enumerate(slides, 1):
        where = f"slide {i}" + (f" ({s['label']})" if s['label'] else '')
        if not s['img']:
            faults.append(
                f"{where}: no image. EVERY SLIDE IN AN IMAGE DECK CARRIES ONE — a slide "
                f"without a picture renders blank, not plainer."
                + (f" It still carries text that would have to be set as type: "
                   f"{s['ontext'][0][:48]!r}. A slide like that belongs on the canvas path "
                   f"(md_to_dc.py), not here." if s.get('ontext') else ''))
            continue
        if s.get('_second'):
            faults.append(f"{where}: two images ({s['img']} and {s['_second']}) — "
                          f"one slide, one picture.")
        if s.get('ontext'):
            faults.append(
                f"{where}: carries BOTH a picture and text to be set as type "
                f"({s['ontext'][0][:48]!r}). This path cannot lay out type over an image; "
                f"either the words belong inside the picture, or the deck belongs on the "
                f"canvas path.")
        if not s['alt'].strip():
            faults.append(
                f"{where}: image has empty alt text. In THIS deck the slide's words are "
                f"pixels, so the alt is the only route they have to a screen reader "
                f"(framework/docs/ALT-TEXT.md).")
        path = os.path.join(talk_dir, s['img'])
        if not os.path.exists(path):
            faults.append(f"{where}: missing image {s['img']}")
            continue
        if path.lower().endswith('.png'):
            assert_complete_png(path)
        if not s['notes']:
            faults.append(f"{where}: no spoken script over it. A slide the speaker says "
                          f"nothing about is usually a mistake; say something or cut it.")
    return faults


def serve_copy(src, dst_dir, width, quality):
    """Write the served copy of one master. -> (filename, bytes).

    Resized and re-encoded, never cropped: the deck's stage is the images' own aspect,
    so a crop here would silently cut a carved word off the edge of a slide.
    """
    base = os.path.splitext(os.path.basename(src))[0]
    if not width or Image is None:
        out = os.path.join(dst_dir, os.path.basename(src))
        shutil.copy2(src, out)
        return os.path.basename(src), os.path.getsize(out)
    im = Image.open(src)
    im = im.convert('RGB')
    if max(im.size) > width:
        scale = width / max(im.size)
        im = im.resize((round(im.width * scale), round(im.height * scale)),
                       Image.LANCZOS)
    name = base + '.jpg'
    out = os.path.join(dst_dir, name)
    im.save(out, 'JPEG', quality=quality, optimize=True, progressive=True)
    return name, os.path.getsize(out)


def build(talk_dir, out_dir, runtime, check=False, width=1600, quality=82):
    slug = os.path.basename(os.path.normpath(talk_dir))
    draft = os.path.join(talk_dir, 'draft.md')
    if not os.path.exists(draft):
        die(1, f'{slug}: no draft.md')
    if not check and os.path.realpath(talk_dir) == os.path.realpath(out_dir):
        die(2, 'source and output are the same directory')
    man = read_manifest(os.path.join(talk_dir, 'talk.yaml'))
    slides = parse(open(draft, encoding='utf-8').read())
    if not slides:
        die(2, f'{slug}: no slides found')

    faults = verify(talk_dir, slides)
    print(f'img_deck — {slug}: {len(slides)} slide(s), '
          f'{len({s["img"] for s in slides if s["img"]})} image(s)')
    for i, s in enumerate(slides, 1):
        n = len(' '.join(s['notes']).split())
        print(f'  {i:2d}  {(s["img"] or "— NO IMAGE"):42s} {n:4d} spoken words'
              f'   {s["label"][:28]}')
    if faults:
        print()
        for f in faults:
            print(f'FAULT  {f}', file=sys.stderr)
        die(2, f'{len(faults)} fault(s) — nothing written')
    if check:
        print('\n--check: clean. Every slide carries one image, with alt text and a script.')
        return {'slides': len(slides)}

    # Size the stage from the first image, so the deck's box matches the pictures
    # rather than a number somebody typed. Every image in a set like this is one shape.
    stage_w, stage_h = png_size(os.path.join(talk_dir, slides[0]['img'])) or (1536, 1024)

    if not os.path.exists(runtime):
        die(1, f'no deck-stage.js at {runtime}')

    referenced = list(dict.fromkeys(s['img'] for s in slides))
    if width and Image is None:
        die(2, 'Pillow is needed to size the served images; '
               'install it, or pass --keep-png to copy the masters through')
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, 'assets'), exist_ok=True)
    served, total = {}, 0
    for rel in referenced:
        name, n = serve_copy(os.path.join(talk_dir, rel),
                             os.path.join(out_dir, 'assets'), width, quality)
        served[rel] = name
        total += n
    shutil.copy2(runtime, os.path.join(out_dir, 'deck-stage.js'))

    title = man.get('title', slug)
    sections = []
    for i, s in enumerate(slides):
        name = served[s['img']]
        label = html.escape(s['label'] or f'Slide {i + 1}', quote=True)
        alt = html.escape(' '.join(s['alt'].split()), quote=True)
        sections.append(
            f'<section data-label="{label}">'
            f'<img src="assets/{html.escape(name, quote=True)}" alt="{alt}">'
            f'</section>')

    deck_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="robots" content="noindex">
<style>
  html, body {{ height: 100%; margin: 0; background: #000; }}
  deck-stage:not(:defined) {{ visibility: hidden; }}
  /* Every slide is one picture at the stage's own aspect, so it fills the slide
     exactly and nothing is cropped or letterboxed inside the frame. */
  section {{ width: 100%; height: 100%; margin: 0; }}
  section img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
</style>
</head>
<body>
<deck-stage width="{stage_w}" height="{stage_h}">
{chr(10).join(sections)}
</deck-stage>
<script src="deck-stage.js"></script>
<script>
/* Bridge between deck-stage and whatever page embeds this deck — the same relay
   dc_to_deck.py emits, so a deck built either way drives the same page. */
(function () {{
  var stage = document.querySelector('deck-stage');
  var embedded = window.parent !== window;

  window.addEventListener('message', function (e) {{
    var d = e.data;
    if (!d || typeof d !== 'object') return;
    if (e.source === window && typeof d.slideIndexChanged === 'number') {{
      if (embedded) {{
        parent.postMessage({{
          type: 'deck:slide',
          index: d.slideIndexChanged,
          total: d.deckTotal,
        }}, '*');
      }}
      return;
    }}
    if (e.source !== window && d.type === 'deck:cmd' && stage) {{
      if (d.action === 'next') stage.next();
      else if (d.action === 'prev') stage.prev();
      else if (d.action === 'goto' && typeof d.index === 'number') stage.goTo(d.index);
    }}
  }});

  function announce() {{
    if (!embedded || !stage) return;
    parent.postMessage({{
      type: 'deck:ready',
      total: stage.querySelectorAll(':scope > section').length,
    }}, '*');
  }}
  if (document.readyState === 'complete') announce();
  else window.addEventListener('load', announce);
}})();
</script>
</body>
</html>
"""
    with open(os.path.join(out_dir, 'deck.html'), 'w', encoding='utf-8') as fh:
        fh.write(deck_html)

    notes = [{'index': i,
              'label': s['label'] or f'Slide {i + 1}',
              'notes': '\n\n'.join(s['notes'])}
             for i, s in enumerate(slides)]
    with open(os.path.join(out_dir, 'notes.json'), 'w', encoding='utf-8') as fh:
        json.dump({'slug': slug, 'title': title,
                   'slideCount': len(notes), 'slides': notes},
                  fh, indent=2, ensure_ascii=False)

    words = sum(len(' '.join(s['notes']).split()) for s in slides)
    masters = sum(os.path.getsize(os.path.join(talk_dir, r)) for r in referenced)
    print(f'\nwrote {out_dir}: deck.html ({len(slides)} slides at {stage_w}x{stage_h}), '
          f'notes.json ({words} spoken words), deck-stage.js, '
          f'{len(referenced)} asset(s)')
    print(f'  served {total/1e6:.1f} MB from {masters/1e6:.1f} MB of masters'
          + (f' (longest edge {width}px, JPEG q{quality})' if width else ' (masters copied)'))
    if total > 20e6:
        print('  WARNING: over 20 MB is a download rather than a page — '
              'lower --width or --quality', file=sys.stderr)
    return {'slides': len(slides), 'assets': len(referenced), 'words': words,
            'bytes': total}


def main():
    args, runtime, check = [], None, False
    width, quality = 1600, 82
    it = iter(sys.argv[1:])
    for a in it:
        if a == '--runtime':
            runtime = next(it, None)
        elif a == '--check':
            check = True
        elif a == '--keep-png':
            width = 0
        elif a == '--width':
            width = int(next(it, '1600'))
        elif a == '--quality':
            quality = int(next(it, '82'))
        elif a.startswith('-'):
            die(1, f'unknown option {a}')
        else:
            args.append(a)
    if check and len(args) == 1:
        args.append('')
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    if not check and not runtime:
        die(1, '--runtime <deck-stage.js> is required to build '
               '(the runtime is vendored from the site project)')
    build(args[0], args[1], runtime or '', check=check, width=width, quality=quality)


if __name__ == '__main__':
    main()
