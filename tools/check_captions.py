#!/usr/bin/env python3
"""check_captions.py — every figure a draft shows must carry a caption.

WHY THIS EXISTS
  An instance can rule that a caption is a DEFAULT rather than a per-figure choice.
  This desk did, in 2026-09-11, and wrote it into a style's corrections file and
  into ALT-TEXT.md — where it lived, as prose. No tool read it.

  Measured 2026-09-14: *The Coordinates You Happen to Have* was drafted, critiqued,
  gated nine ways, cleared, composed and PUBLISHED TO ALL THREE OUTLETS with three
  of its four figures carrying no caption at all. Every gate was green the whole
  way, because none of them was looking. The author caught it, which is the same
  way the pronoun and britishism rules were caught before they had sweeps — and the
  lesson each time is the one this file exists to stop repeating: **a rule no sweep
  checks is a rule nobody enforces.**

  Alt text and a caption are two different jobs and neither substitutes for the
  other. The alt is what a reader who cannot see the picture gets; the caption is
  what the sighted skimmer gets, and it says what the figure MEANS rather than what
  it shows. A drafting pass that writes the alt and stops leaves the skimmer nothing.

WHAT IT CHECKS
  For every image referenced in draft.md as `![alt](path)`:
    - the hero (the manifest's `cover:`, or any `assets/hero.*`) must have
      `cover_caption:`
    - every other figure must have an entry under `captions:` keyed by the exact
      path the draft gives it
  It also reports a `captions:` key that no image in the draft uses, because that is
  a caption the reader will never see and usually means a path was renamed.

USAGE
  python3 check_captions.py <piece_dir> [<piece_dir> ...]
  python3 check_captions.py --all [--root .]

EXIT
  0  every figure has a caption
  1  usage
  3  at least one figure has none
"""
import os, re, sys, glob

IMG = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)\)')


def _manifest(piece_dir):
    """The caption-bearing fields, read the way md_to_substack reads them.

    `images:` matters as much as `captions:`. A PUBLISHED piece references its hero by
    the uploaded CDN url rather than by `assets/hero.png`, so a checker that only knows
    local paths calls a captioned hero uncaptioned. The converter maps the url back
    through `images:` before looking up a caption, and so must this: a check that cries
    wolf on two thirds of the corpus is a check the next session switches off.

    Deliberately a small hand parser rather than a yaml import: this runs in CI,
    where the point is that the check cannot be the thing that breaks.
    """
    path = os.path.join(piece_dir, 'publish.yaml')
    cover, cover_caption, captions, url_to_local = '', '', {}, {}
    if not os.path.exists(path):
        return cover, cover_caption, captions, url_to_local
    inblock = imgblock = False
    for line in open(path, encoding='utf-8'):
        # A trailing comment on the key line is still the key (`captions:   # settled …`).
        # Matching `^captions:\s*$` alone read such a block as absent and reported every
        # figure uncaptioned — measured 2026-10-15 on the-top-step, 19 false misses.
        if re.match(r'^captions:\s*(#.*)?$', line):
            inblock, imgblock = True, False
            continue
        if re.match(r'^images:\s*(#.*)?$', line):
            imgblock, inblock = True, False
            continue
        if imgblock:
            m = re.match(r'\s+(\S+?)\s*:\s*(https?://\S+)', line)
            if m:
                url_to_local[m.group(2).strip()] = m.group(1).strip()
                continue
            if line.strip() and not line.startswith((' ', '\t')):
                imgblock = False
        if inblock:
            m = re.match(r'\s+(\S+?)\s*:\s*(.+?)\s*$', line)
            if m:
                captions[m.group(1)] = m.group(2).strip().strip('"\'')
                continue
            if line.strip() and not line.startswith((' ', '\t')):
                inblock = False
        m = re.match(r'^cover:\s*(\S+)', line)
        if m:
            cover = m.group(1)
        m = re.match(r'^cover_caption:\s*(.+?)\s*$', line)
        if m:
            cover_caption = m.group(1).strip().strip('"\'')
    return cover, cover_caption, captions, url_to_local


def check(piece_dir):
    draft = os.path.join(piece_dir, 'draft.md')
    if not os.path.exists(draft):
        return [], []
    body = open(draft, encoding='utf-8').read()
    # the scaffold above the first `---` never reaches a reader, so its images are not figures
    body = body.split('\n---\n', 1)[1] if '\n---\n' in body else body
    srcs = [m.group('src') for m in IMG.finditer(body)]
    cover, cover_caption, captions, url_to_local = _manifest(piece_dir)
    missing, orphans = [], []
    for raw in srcs:
        src = url_to_local.get(raw, raw)      # a live piece cites the CDN url, not the file
        is_hero = (cover and src == cover) or re.search(r'/hero\.[A-Za-z0-9]+$', src)
        if is_hero:
            if not cover_caption:
                missing.append((raw, 'hero, and `cover_caption:` is empty or absent'))
        elif not captions.get(src):
            missing.append((raw, 'no entry under `captions:` for ' +
                            (src if src == raw else src + ' (via `images:`)')))
    local = {url_to_local.get(x, x) for x in srcs}
    for key in captions:
        if key not in local:
            orphans.append(key)
    return missing, orphans


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--all' in sys.argv:
        root = args[0] if args else '.'
        dirs = sorted(d for d in glob.glob(os.path.join(root, 'pieces', '*'))
                      if os.path.exists(os.path.join(d, 'draft.md')))
    elif args:
        dirs = args
    else:
        sys.exit(__doc__.strip())

    bad = figures = 0
    for d in dirs:
        missing, orphans = check(d)
        name = os.path.basename(os.path.normpath(d))
        body = open(os.path.join(d, 'draft.md'), encoding='utf-8').read()
        body = body.split('\n---\n', 1)[1] if '\n---\n' in body else body
        figures += len(IMG.findall(body))
        if missing:
            bad += 1
            print(f"{name} — {len(missing)} figure(s) with NO CAPTION")
            for src, why in missing:
                print(f"    {src}\n        {why}")
        for key in orphans:
            print(f"{name} — caption for {key}, which the draft never shows "
                  f"(renamed path?) — no reader will see it")
    print(f"\n{figures} figure(s) across {len(dirs)} piece(s); "
          f"{bad} piece(s) with a figure carrying no caption")
    if bad:
        print("A caption is a DEFAULT on this desk, not a preference. Alt text is what a reader\n"
              "who cannot see the picture gets; the caption is what the skimmer gets, and it says\n"
              "what the figure MEANS. Write it in publish.yaml — never as an italic line in the\n"
              "draft, which publishes as an ordinary paragraph.")
        sys.exit(3)


if __name__ == '__main__':
    main()
