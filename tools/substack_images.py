#!/usr/bin/env python3
"""
substack_images.py — upload a piece's images to Substack BEFORE composing, and record them.

WHY THIS EXISTS

  md_to_substack inlines every image the manifest has no Substack URL for, as a data: URI
  in the one compose snippet. That is fine for a hero and a figure or two. It is not fine
  for a piece that is mostly pictures: the-top-step (2026-10-15, twenty generated PNGs)
  converted to a snippet of ~65 MB, which no carry reaches a page with. It was published by
  uploading the images by hand through Substack's own endpoint and writing the URLs into
  `images:` — after which the converter emitted `<img src="<url>">` and the snippet was 30 KB.

  This is that, as the path. Upload first, record, then compose: the converter already reuses
  a recorded URL (publish skill, 0b-images), so nothing else changes.

USAGE

  python3 substack_images.py pieces/<slug> --out <dir>
        writes <dir>/upload<k>.js, one per carry-sized batch of the images that have no URL
        under `images:` yet. Each is a guarded snippet (the account guard, as every Substack
        snippet here): carry it with pane_carry.py, run it on any non-editor page of the
        publication (/publish/home), and it POSTs each image to /api/v1/image and returns
        {"<assets/path>": "<url>", …}. Save each result as <dir>/upload<k>.result.json.

  python3 substack_images.py pieces/<slug> --record <dir>
        reads every upload<k>.result.json in <dir> and writes the URLs into `images:` in
        publish.yaml. Refuses if a result is missing, holds an error, or names an image the
        draft does not use. Then run md_to_substack as usual.

  The upload is the served copy (web_images: 1600 px JPEG q82); the masters stay in assets/.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import web_images  # noqa: E402

IMG_RE = re.compile(r'!\[[^\]]*\]\((assets/[^)\s]+)\)')


def drafted_images(piece):
    raw = open(os.path.join(piece, 'draft.md'), encoding='utf-8').read()
    body = raw.split('\n---\n', 1)[1] if '\n---\n' in raw else raw
    seen = []
    for p in IMG_RE.findall(body):
        if p not in seen:
            seen.append(p)
    return seen


def recorded(piece):
    """{local path: url} from the manifest's `images:` block."""
    try:
        import yaml
        man = yaml.safe_load(open(os.path.join(piece, 'publish.yaml'), encoding='utf-8')) or {}
        imgs = man.get('images') or {}
        return {str(k): str(v) for k, v in imgs.items()} if isinstance(imgs, dict) else {}
    except Exception:                                              # noqa: BLE001
        return {}


UPLOAD_JS = """(async () => {
  const items = %s;
  if (document.querySelector('.ProseMirror'))
    return JSON.stringify({refused: 'a composer is open — run this on /publish/home, not in an editor'});
  const out = {};
  for (const it of items) {
    const r = await fetch('/api/v1/image', {method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({image: it.dataUri})});
    let j = {}; try { j = await r.json(); } catch (e) {}
    out[it.path] = j.url || ('ERROR ' + r.status);
  }
  return JSON.stringify(out);
})()"""


def cmd_out(piece, out):
    have = recorded(piece)
    todo = [p for p in drafted_images(piece) if p not in have]
    if not todo:
        print(f"every image draft.md uses already has a URL under `images:` — nothing to upload")
        return 0
    os.makedirs(out, exist_ok=True)
    items = [{'path': p, 'dataUri': web_images.data_uri(os.path.join(piece, p))} for p in todo]
    import substack_account as sa
    groups = web_images.batches(items)
    for k, g in enumerate(groups, 1):
        js = sa.guarded(piece, UPLOAD_JS % json.dumps(g), 'substack_images')
        path = os.path.join(out, f'upload{k}.js')
        open(path, 'w', encoding='utf-8').write(js)
        print(f"wrote {path}  ({len(js):,} bytes, {len(g)} image(s): "
              + ', '.join(os.path.basename(i['path']) for i in g) + ')')
    print(f"\n{len(todo)} image(s) in {len(groups)} batch(es). Carry each with pane_carry.py, run it on "
          f"/publish/home, save what it returns as upload<k>.result.json beside it, then:\n"
          f"  python3 framework/tools/substack_images.py {piece} --record {out}")
    return 0


def cmd_record(piece, out):
    used = set(drafted_images(piece))
    have = recorded(piece)
    scripts = sorted(f for f in os.listdir(out) if re.match(r'upload\d+\.js$', f))
    got = {}
    for s in scripts:
        res = os.path.join(out, s.replace('.js', '.result.json'))
        if not os.path.exists(res):
            print(f"REFUSING: {s} has no result ({os.path.basename(res)}) — run it first")
            return 3
        data = json.load(open(res, encoding='utf-8'))
        if isinstance(data, str):
            data = json.loads(data)
        if 'refused' in data:
            print(f"REFUSING: {s} was refused: {data['refused']}")
            return 3
        for k, v in data.items():
            if k not in used:
                print(f"REFUSING: {s} returned {k}, which draft.md does not use")
                return 3
            if not str(v).startswith('https://'):
                print(f"REFUSING: {k} did not upload ({v})")
                return 3
            got[k] = v
    missing = sorted(used - set(have) - set(got))
    if missing:
        print("REFUSING: still no URL for " + ', '.join(missing))
        return 3
    path = os.path.join(piece, 'publish.yaml')
    text = open(path, encoding='utf-8').read()
    lines = ''.join(f"  {k}: {v}\n" for k, v in got.items() if k not in have)
    if re.search(r'^images:\s*(#.*)?$', text, re.M):
        text = re.sub(r'^(images:\s*(#.*)?\n)', lambda m: m.group(1) + lines, text, count=1, flags=re.M)
    else:
        text = text.rstrip('\n') + "\n\n# Uploaded by substack_images.py (served copies; masters in assets/).\nimages:\n" + lines
    open(path, 'w', encoding='utf-8').write(text)
    print(f"recorded {len(got)} URL(s) under `images:` in {path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('piece')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--out')
    g.add_argument('--record')
    a = ap.parse_args()
    piece = a.piece.rstrip('/')
    return cmd_out(piece, a.out) if a.out else cmd_record(piece, a.record)


if __name__ == '__main__':
    sys.exit(main())
