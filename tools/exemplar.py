#!/usr/bin/env python3
"""exemplar.py — read a style's exemplar passages out of the local reference shelf.

WHY THIS EXISTS.  `draft` is told to "match the texture of these passages" and, until
2026-11-02, every style's exemplars/ folder held a bibliography. The texture references
are in copyright, so they cannot be committed and the prose could not live in the repo.
The fix is not to commit them: it is to hold them on the shelf, commit only the
ADDRESSES, and read the spans at draft time. This does the reading.

So nothing copyrighted enters git, and a drafting session gets actual prose instead of a
description of prose — which is what it had, and which steers nothing.

WHAT IT DOES NOT DO.  It does not decide whether a passage is worth imitating, and it
will happily print a span whose page map has drifted. The map carries a `move` per entry
for that reason: a passage loaded without its job is just someone else's writing.

USAGE
  exemplar.py show <style> [--move <substr>] [--chars <n>]
  exemplar.py list <style>

Reads styles/<style>/exemplars/map.yaml and the PDFs named there from references/.
Requires the shelf to hold them — `references.py pull` if a clean checkout does not.
"""
import os
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("exemplar.py: PyYAML missing; pip install pyyaml")

REFS = "references"


def load_map(style):
    p = os.path.join("styles", style, "exemplars", "map.yaml")
    if not os.path.exists(p):
        sys.exit(f"no exemplar map: {p}\n"
                 f"This style steers on rules alone. Write a map.yaml to give it texture.")
    with open(p) as fh:
        return yaml.safe_load(fh) or {}


def page_text(pdf, first, last):
    path = os.path.join(REFS, pdf)
    if not os.path.exists(path):
        return None, (f"NOT ON THE SHELF: {path}\n"
                      f"  The map addresses it and the file is absent, so this exemplar "
                      f"steers nothing.\n"
                      f"  Fix: python3 framework/tools/references.py pull {pdf}")
    out = subprocess.run(["pdftotext", "-f", str(first), "-l", str(last), path, "-"],
                         capture_output=True)
    if out.returncode != 0:
        return None, f"pdftotext failed on {path}: {out.stderr.decode()[:200]}"
    text = out.stdout.decode("utf-8", "replace")
    if len(text.strip()) < 200:
        return None, (f"NO TEXT LAYER AT pp. {first}-{last} of {pdf} — "
                      f"the span cannot be read; open the page by eye.")
    return text, None


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    cmd, style = argv[1], argv[2]
    args = argv[3:]
    want, limit = None, 2400
    i = 0
    while i < len(args):
        if args[i] == "--move":
            want = args[i + 1].lower(); i += 2
        elif args[i] == "--chars":
            limit = int(args[i + 1]); i += 2
        else:
            i += 1

    m = load_map(style)
    default = m.get("source_default")
    items = m.get("exemplars") or []
    if want:
        items = [e for e in items if want in (e.get("move", "") + e.get("story", "")).lower()]
    if not items:
        sys.exit(f"no exemplars matched in styles/{style}/exemplars/map.yaml")

    if cmd == "list":
        print(f"\n{style} — {len(items)} exemplar(s)")
        for e in items:
            src = e.get("source", default)
            lo, hi = e["pages"]
            print(f"  {e['move']}\n      {e.get('story','?')} · {src} pp. {lo}-{hi}")
        print()
        return 0

    if cmd != "show":
        sys.exit(f"unknown command: {cmd}")

    problems = 0
    for e in items:
        src = e.get("source", default)
        lo, hi = e["pages"]
        print("\n" + "=" * 78)
        print(f"MOVE: {e['move']}")
        print(f"FROM: {e.get('story','?')} — {src}, pp. {lo}-{hi}")
        if e.get("note"):
            print(f"WHY:  {' '.join(e['note'].split())}")
        print("=" * 78)
        text, err = page_text(src, lo, hi)
        if err:
            problems += 1
            print(f"\n  ⚠️  {err}\n")
            continue
        body = " ".join(text.split())
        print("\n" + body[:limit] + ("…" if len(body) > limit else "") + "\n")

    if problems:
        print(f"\n{problems} exemplar(s) could not be read — the style is steering on "
              f"rules alone for those moves.\n")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
