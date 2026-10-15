#!/usr/bin/env python3
"""
voice_privacy.py — an instance's voices never reach the framework.

A voice (`styles/<name>/` in the instance) is the most personal thing a desk holds: the author's
rules, their corrections, the texts they tune against. The framework is public. The split has
always been the promise (README: "your personal trained voices live only in your instance"); this
is the check that keeps it, because a framework edited daily by sessions that have just read a
private constitution will, eventually, paste a line of one into a doc.

Names are not what leaks — a framework doc may say `being-good-essay` as an example of a family
name. CONTENT leaks. So the check is textual:

  1. No `framework/styles/<name>` shares a name with an instance voice. A private voice copied
     into the framework is the whole leak at once.
  2. No run of RUN consecutive words (default 12) from an instance voice's files — style.md,
     config.yaml, corrections.md, exemplars/ — appears in any framework text file.

  What is NOT the author's, and so does not count:
    - runs from `framework/templates/style/`, with `<name>` read as the voice's own name (the
      scaffold every voice is seeded from);
    - runs from the starter a voice declares it was seeded from — `seeded_from: plain-english`
      in its config.yaml. Declared, never inferred: the same run in a starter and a private
      voice is either inheritance or a leak, and only the author knows which.

THE BASELINE — a ratchet, so the check is useful the day it lands

  The first run on this desk (2026-09-11) found framework text that already overlapped private
  voices: house rules generalized into tools, scripture both quote. Those are a cleanup, not a
  reason to ship a check that is red forever. `--accept` records every current hit in
  `<instance>/styles/.privacy-baseline.json` — as SHA-1s of the runs, never the runs, so the
  baseline leaks nothing even if it were published — and later runs fail only on hits not in it.
  The file lives with the voices, which is to say in the private repo. `--accept` is the one
  writing operation here and is never run by the suite.

Usage:  voice_privacy.py [--instance <root>] [--run 12] [--accept] [--all]
          --all   report baselined hits too
Exit:   0 clean, 1 a new leak found, 2 no instance to compare (framework alone: nothing to do)
"""
import sys, os, re, json, hashlib, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK = os.path.dirname(HERE)
TEXT = ('.md', '.py', '.yaml', '.yml', '.js', '.txt', '.html', '.json', '.sh')
# What a VOICE contributes runs FROM. The framework side is scanned whole — a leak can land in
# any file there — but on the voice side only the author's own writing is private: the
# constitution, the knobs, the corrections, the exemplar notes. A style may also ship MECHANISM
# beside those (`styles/<name>/check.py`, the mechanical half of a critique), and mechanism is
# not voice: it is usually PORTED FROM THE FRAMEWORK, so it shares whole lines with the tools by
# construction. Scanning it reported 97 runs of `recess-talk` "leaking" into img_deck.py,
# md_to_marp.py and md_to_substack.py on 2026-10-15 — every one of them code the instance had
# copied OUT of the framework, read backwards as the author's prose going in. A check that
# cries leak at its own source code gets switched off, which is how a privacy gate actually
# fails. The docstring above always said these four; now the code agrees with it.
VOICE_TEXT = ('.md', '.yaml', '.yml', '.txt')
WORD = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?")
BASELINE = '.privacy-baseline.json'


def words(text):
    return WORD.findall(text.lower())


def runs(ws, n):
    return {' '.join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def sha(run):
    return hashlib.sha1(run.encode('utf-8')).hexdigest()


def files_under(d, exts=TEXT):
    for root, dirs, names in os.walk(d):
        dirs[:] = [x for x in dirs if x not in ('.git', 'node_modules', '__pycache__')]
        for nm in names:
            if nm.endswith(exts) and not nm.startswith('.'):
                yield os.path.join(root, nm)


def read(p):
    try:
        return open(p, encoding='utf-8').read()
    except (UnicodeDecodeError, OSError):
        return ''


def private_voices(instance):
    base = os.path.join(instance, 'styles')
    return sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))) \
        if os.path.isdir(base) else []


def seeded_from(instance, voice):
    cfg = os.path.join(instance, 'styles', voice, 'config.yaml')
    m = re.search(r'^seeded_from\s*:\s*([\w-]+)', read(cfg), re.M)
    return m.group(1) if m else ''


def hits(instance, n=12):
    """-> (name_clashes, {(voice, framework_rel_path): set(runs)})"""
    voices = private_voices(instance)
    fw_styles = os.path.join(FRAMEWORK, 'styles')
    shipped = set(os.listdir(fw_styles)) if os.path.isdir(fw_styles) else set()
    clashes = [v for v in voices if v in shipped]

    templates = [read(p) for p in files_under(os.path.join(FRAMEWORK, 'templates', 'style'))]
    fw = {os.path.relpath(p, os.path.dirname(FRAMEWORK)): runs(words(read(p)), n)
          for p in files_under(FRAMEWORK)}
    found = {}
    for v in voices:
        inherited = set()
        for t in templates:
            inherited |= runs(words(t.replace('<name>', v)), n)
        seed = seeded_from(instance, v)
        if seed and os.path.isdir(os.path.join(fw_styles, seed)):
            for p in files_under(os.path.join(fw_styles, seed), VOICE_TEXT):
                inherited |= runs(words(read(p)), n)
        mine = set()
        for p in files_under(os.path.join(instance, 'styles', v), VOICE_TEXT):
            mine |= runs(words(read(p)), n)
        mine -= inherited
        for rel, rs in fw.items():
            h = mine & rs
            if h:
                found[(v, rel)] = h
    return clashes, found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--instance', default=os.path.dirname(FRAMEWORK))
    ap.add_argument('--run', type=int, default=12)
    ap.add_argument('--accept', action='store_true')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args(argv)
    voices = private_voices(args.instance)
    if not voices:
        print('no instance voices to compare against — nothing to check')
        return 2
    clashes, found = hits(args.instance, args.run)
    bpath = os.path.join(args.instance, 'styles', BASELINE)

    if args.accept:
        data = {f'{v} -> {rel}': sorted(sha(r) for r in rs) for (v, rel), rs in sorted(found.items())}
        json.dump({'note': 'voice_privacy.py --accept: SHA-1s of 12-word runs of private voice text '
                           'already present in the framework. Hashes only; the runs are not stored.',
                   'hits': data}, open(bpath, 'w', encoding='utf-8'), indent=1)
        print(f'accepted {sum(len(x) for x in data.values())} run(s) in {len(data)} file pair(s) '
              f'into {os.path.relpath(bpath, args.instance)}')
        return 0

    base = {}
    if os.path.exists(bpath):
        base = {k: set(v) for k, v in json.load(open(bpath, encoding='utf-8')).get('hits', {}).items()}
    new = 0
    for v in clashes:
        new += 1
        print(f'  LEAK  framework/styles/{v} has the name of a private voice')
    for (v, rel), rs in sorted(found.items()):
        known = base.get(f'{v} -> {rel}', set())
        fresh = [r for r in rs if sha(r) not in known]
        if fresh:
            new += 1
            print(f'  LEAK  {rel}: {len(fresh)} new run(s) from private voice {v!r} — e.g. "{sorted(fresh)[0]}"')
        elif args.all:
            print(f'  known {rel}: {len(rs)} baselined run(s) from {v!r}')
    known_n = sum(1 for (v, rel), rs in found.items()
                  if all(sha(r) in base.get(f'{v} -> {rel}', set()) for r in rs))
    print(f"{len(voices)} private voice(s) checked; {new} new leak(s)"
          + (f"; {known_n} baselined file pair(s) still to clean up" if known_n else ''))
    return 1 if new else 0


if __name__ == '__main__':
    sys.exit(main())
