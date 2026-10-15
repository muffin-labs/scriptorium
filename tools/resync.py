#!/usr/bin/env python3
"""resync.py — a correction is not shipped until EVERY outlet the piece declares has it.

WHY THIS EXISTS (Eric, 2026-09-14: *"our toolset should republish to all outlets. why was
this missed?"*).

  The answer was that the fan-out was PROSE. `substack_repatch.py` and `substack_sync.py`
  contain no occurrence of `outlets`, `md_to_site` or `store_publish` — they know one
  destination and cannot raise the existence of a second. The rule to carry a correction to
  the other outlets lived in one sentence of the `substack-sync` skill, which even cited the
  measured precedent: *For the Love of Dogs*, 2026-09-11, corrected on Substack while
  alignmentfellowship.org went on serving the old sentence "until an audit happened to look."

  So it had already happened once, been measured, and been written up — and it recurred on
  2026-09-14 anyway, on *In the Name (The Ambassador)*. That is the evidence that another
  paragraph of documentation was not the fix.

  THE ASYMMETRY IS THE HOLE. Publishing got a real preflight gate after a measured
  half-publish — `check_outlets.py` refuses a piece whose outlets cannot all be reached,
  precisely so the irreversible outlet is not the one you discover the problem after. The
  RE-SYNC path referenced it zero times, even though a correction is the one case where the
  outlets are GUARANTEED to disagree at the start.

WHAT IT DOES. Reads the piece's `outlets:`, resolves each outlet's reader URL, fetches it
  cache-busted, and asks whether the live page carries the paragraphs the desk now holds.
  Then it reports per outlet and REFUSES TO LOOK LIKE COMPLETION: the summary always reads
  "N of M outlets current", and the exit code is non-zero while any outlet is behind.

  That last part is the point. `substack_verify --fresh` printed "the repo matches the
  publication" and exited 0 on a piece declaring two outlets — a true sentence about one
  publication that reads as a finished job. A partial must be loud, not silent.

WHAT IT DOES NOT DO. It does not write to any outlet. Carrying the change is still the
  outlet's own path — the browser for Substack, a bundle + store publish for a site, a person
  for LinkedIn — and this tool is what tells you which of those you still owe.

  The comparison is `outlet_audit.content_drift`: a PRESENCE check, borrowed rather than
  reimplemented. It can prove every paragraph the desk holds is on the page a reader gets.
  It cannot prove ordering, or that the page carries nothing extra. Said here because a
  checker that implies more than it proves is worse than none.

DEFERRAL IS BOUND TO THE DRAFT, or it is just a silent skip.

    resync.py <piece> --defer <outlet> --reason "a person posts this one"

  writes `resync_defer: {<outlet>: {reason, draft_sha, at}}` into publish.yaml. The deferral
  holds only while `draft.md` still hashes to `draft_sha`. Edit the draft and the deferral
  lapses back to BEHIND on its own — because a reason given for one version of a piece is not
  a reason for the next one, and a permanent exemption is how a gate gets switched off for good.

EXIT
  0  every declared outlet is current, or validly deferred
  2  an outlet could not be read — never wears the same face as a pass
  3  an outlet is behind, missing, or has no reader address recorded
"""
import argparse, hashlib, importlib.util, os, sys, time, datetime

try:
    import yaml
except ImportError:
    print("resync: PyYAML required", file=sys.stderr); sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))


def _audit():
    """Borrow outlet_audit's fetch/slug/drift rather than writing a second set of bugs."""
    spec = importlib.util.spec_from_file_location('_oa', os.path.join(HERE, 'outlet_audit.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def die(code, msg):
    print(f"resync: {msg}", file=sys.stderr); sys.exit(code)


def draft_sha(piece_dir):
    p = os.path.join(piece_dir, 'draft.md')
    if not os.path.exists(p):
        return None
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def declared_outlets(manifest, legacy_outlet):
    out = manifest.get('outlets')
    if isinstance(out, list) and out:
        return [str(o) for o in out]
    if manifest.get('site') is True and legacy_outlet:       # pre-outlets manifest
        return [legacy_outlet]
    return []


def is_canonical(outlet_cfg):
    """Explicit `canonical: true` wins; otherwise the quire sites, which publish at once
    because they drive no traffic (outlets.yaml). Matters only because render_reader
    prepends 'Originally published at …' for a syndicated copy and the canonical correctly
    lacks it — expecting it there once reported the original site as stale."""
    if 'canonical' in outlet_cfg:
        return bool(outlet_cfg['canonical'])
    return outlet_cfg.get('on_schedule') == 'immediate'


def substack_state(piece_dir):
    """A Substack outlet is checked by substack_verify, not by content_drift.

    content_drift is a BODY-PARAGRAPH presence check and says so: footnote text is out of
    scope, and marks and anchors are invisible to it. This tool's first run reported
    *The Sheep in the Basement* as 2-of-2 CURRENT when its only pending change was a
    FOOTNOTE — a false green of exactly the kind the rest of this desk keeps finding.
    substack_verify compares body, footnotes, marks AND anchors, so for Substack it is the
    better answer and is called rather than reimplemented.
    """
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(HERE, 'substack_verify.py'),
                        '--fresh', piece_dir], capture_output=True, text=True, timeout=180)
    out = (r.stdout or '') + (r.stderr or '')
    for line in out.splitlines():
        if 'MATCH' in line:
            return ('CURRENT', line.strip().split('MATCH', 1)[1].strip()[:80] or 'body, footnotes, marks, anchors')
        if 'DRIFT' in line:
            kind = 'DRIFT-MARKS' if 'DRIFT-MARKS' in line else ('DRIFT-ANCHORS' if 'DRIFT-ANCHORS' in line else 'DRIFT')
            return ('BEHIND', f"{kind}: {line.strip()[:110]}")
    return ('UNREADABLE', 'substack_verify said nothing readable')


def check_outlet(oa, piece_dir, manifest, piece_name, oname, ocfg, deferrals, sha):
    d = deferrals.get(oname)
    if d and isinstance(d, dict) and d.get('draft_sha') == sha:
        return ('DEFERRED', d.get('reason', '(no reason recorded)'), None)
    if d and isinstance(d, dict) and d.get('draft_sha') != sha:
        stale = ' (deferral lapsed — the draft changed since it was given)'
    else:
        stale = ''

    url = oa.slug_of(manifest, piece_name, ocfg)
    if not url:
        return ('NO ADDRESS', f"no {ocfg.get('manifest_url_key','reader url')} recorded{stale}", None)

    if ocfg.get('account_handle') or 'substack.com' in str(ocfg.get('reader_base', '')):
        st, note = substack_state(piece_dir)
        return (st, note + stale, url)

    status, page, final = oa.fetch(url)
    if status is None:
        return ('UNREACHABLE', f"request failed{stale}", url)
    if status != 200 or oa.landed_on_not_found(final, ocfg):
        return ('MISSING', f"HTTP {status}{stale}", url)

    drift = oa.content_drift(piece_dir, page, canonical_outlet=is_canonical(ocfg),
                             footnote_marker=ocfg.get('footnote_marker'))
    if drift is None:
        return ('UNREADABLE', f"nothing to compare{stale}", url)
    # content_drift returns {'paragraphs': n, 'missing': [...]} — a non-empty `missing` is
    # the finding. Reading the truthy DICT as drift reports every outlet behind forever,
    # which this tool did on its first run and which is exactly the cry-wolf failure
    # content_drift's own docstring warns about.
    missing = drift.get('missing') or []
    if missing:
        return ('BEHIND', f"{len(missing)} of {drift.get('paragraphs','?')} paragraph(s) missing "
                          f"from the live page{stale}; first: {missing[0][:80]}", url)
    return ('CURRENT', f"{drift.get('paragraphs','?')} body paragraph(s) present "
                       f"(body only — footnotes/marks not compared here)", url)


def check_talk_outlet(oa, manifest, oname, ocfg):
    """A talk's page is a deck of pictures, so there is no paragraph text to compare against the
    draft. What CAN be said is that the recorded page answers; the word is PRESENT, never CURRENT,
    so nobody reads it as a content check. The deck is verified where it is built (img_deck.py
    --check, and the served deck.html against the local build)."""
    url = manifest.get('public_url') or manifest.get(ocfg.get('manifest_url_key', '')) or ''
    if not url:
        return ('NO ADDRESS', 'talk.yaml records no public_url', None)
    status, _page, final = oa.fetch(url)
    if status is None:
        return ('UNREACHABLE', 'request failed', url)
    if status != 200 or oa.landed_on_not_found(final, ocfg):
        return ('MISSING', f'HTTP {status}', url)
    return ('PRESENT', 'HTTP 200 — a talk: the deck is not compared here (img_deck --check, and the '
                       'served deck.html against the local build)', url)


def main():
    ap = argparse.ArgumentParser(description="every outlet a piece declares, or it is not shipped")
    ap.add_argument('piece')
    ap.add_argument('--config', default='publishing/outlets.yaml')
    ap.add_argument('--defer', metavar='OUTLET')
    ap.add_argument('--reason')
    a = ap.parse_args()

    piece_dir = a.piece.rstrip('/')
    if not os.path.isdir(piece_dir):
        die(1, f"no such piece: {piece_dir}")
    piece_name = os.path.basename(piece_dir)
    # A talk's manifest is talk.yaml (talks/<slug>/). Reading publish.yaml only, this tool could
    # not see a talk at all (backlog: the-outlet-gates-cannot-see-a-talk, 2026-10-15).
    mpath = next((os.path.join(piece_dir, n) for n in ('publish.yaml', 'talk.yaml')
                  if os.path.exists(os.path.join(piece_dir, n))), None)
    if mpath is None:
        die(2, f"{piece_name} has no publish.yaml or talk.yaml — nothing to compare, and that is "
               f"not a pass")
    is_talk = os.path.basename(mpath) == 'talk.yaml'
    manifest = yaml.safe_load(open(mpath)) or {}
    cfg = yaml.safe_load(open(a.config)) or {}
    outlets, legacy = cfg.get('outlets', {}), cfg.get('legacy_outlet')
    sha = draft_sha(piece_dir)

    names = declared_outlets(manifest, legacy)
    if not names:
        die(3, f"{piece_name} declares no outlets — that is a stop, not a default "
               f"(which outlets is this piece for?)")

    if a.defer:
        if not a.reason:
            die(1, "--defer needs --reason: a deferral with no reason is a silent skip")
        if a.defer not in names:
            die(1, f"{piece_name} does not declare outlet '{a.defer}'")
        rec = manifest.setdefault('resync_defer', {})
        rec[a.defer] = {'reason': a.reason, 'draft_sha': sha,
                        'at': datetime.date.today().isoformat()}
        yaml.safe_dump(manifest, open(mpath, 'w'), sort_keys=False, allow_unicode=True, width=100)
        print(f"deferred {a.defer} for {piece_name}: {a.reason}")
        print(f"  bound to draft sha {str(sha)[:16]}… — it lapses the moment the draft changes")
        return

    deferrals = manifest.get('resync_defer') or {}
    oa = _audit()
    print(f"{piece_name} declares {len(names)} outlet(s)  [cache-busted]")
    rows, worst = [], 0
    for oname in names:
        ocfg = outlets.get(oname)
        if ocfg is None:
            rows.append((oname, 'UNKNOWN', f"not in {a.config}", None)); worst = max(worst, 3); continue
        if is_talk:
            state, note, url = check_talk_outlet(oa, manifest, oname, ocfg)
        else:
            state, note, url = check_outlet(oa, piece_dir, manifest, piece_name, oname, ocfg, deferrals, sha)
        rows.append((oname, state, note, url))
        if state in ('BEHIND', 'MISSING', 'NO ADDRESS', 'UNKNOWN'):
            worst = max(worst, 3)
        elif state in ('UNREACHABLE', 'UNREADABLE'):
            worst = max(worst, 2)

    width = max(len(r[0]) for r in rows)
    for oname, state, note, url in rows:
        print(f"  {oname:<{width}}  {state:<11} {note}")
        if url:
            print(f"  {'':<{width}}  {url}")

    current = sum(1 for r in rows if r[1] in ('CURRENT', 'DEFERRED', 'PRESENT'))
    print()
    print(f"{current} of {len(rows)} outlet(s) current"
          + ("" if current == len(rows) else " — THIS PIECE IS NOT SHIPPED"))
    if worst == 0:
        if any(r[1] == 'PRESENT' for r in rows):
            print("every outlet answers 200; a talk's deck content is not compared by this tool.")
        else:
            print("every outlet this piece declares carries the current draft.")
    sys.exit(worst)


if __name__ == '__main__':
    main()
