#!/usr/bin/env python3
"""
substack_sync.py — two-way sync between a piece's draft.md and its LIVE Substack post,
with real conflict detection.

WHY THIS EXISTS (and why it is not just "repatch, but both ways")

  substack_repatch.py pushes draft -> live and is deliberately stateless: it diffs the
  draft against the live post scraped at run time. That is sound for a one-way push, and
  unsound the moment edits can originate on BOTH sides. A bare two-way difference cannot
  tell you WHICH side moved: draft-changed and live-changed look identical.

  Real case (2026-09-01). `Nothing to Get` read "is this for us" in the draft and "is this
  for me" live — the phrase entered at the compose commit and was never touched since, so
  the edit was made in Substack. `I Believe in You` had its subtitle capitalized in
  Substack, while publish.yaml still held the lowercase form. A stateless push would have
  silently reverted both, and reported success.

  So sync is THREE-way. Baseline B (what was last known synced), draft D, live L:

      D == B, L != B     -> PULL   (only Substack moved; bring it into draft.md)
      D != B, L == B     -> PUSH   (only the draft moved; the ordinary re-sync)
      D != B, L != B, D == L -> CONVERGED (both made the same edit; nothing to do)
      D != B, L != B, D != L -> CONFLICT (stop; a human decides)
      D == B, L == B     -> unchanged

  Conflicts should be exceedingly rare — they need the same block edited on both sides
  between syncs. Rare is not never, and the whole point of the baseline is that when one
  does happen it is reported instead of silently resolved in whichever direction the tool
  happened to run.

THE BASELINE

  `<piece>/sync-baseline.json` — HASHES ONLY (sha256/16 of the flattened reader-text),
  never the text itself.

  TWO hashes per row, not one. The reader-text hash answers "did the words change"; the
  MARK hash answers "did the formatting change", and until 2026-09-09 nothing asked. A
  block whose only difference is an `<em>` hashes identically as text, so the three-way
  classified it `unchanged` and both directions of sync ran straight past it — the same
  false pass measured on `rising-after-falls` in substack_verify and substack_repatch,
  one tool over. `bodyMarks` / `fnsMarks` close it.

  A baseline written before that has NO mark hashes, and 34 of them exist. Their rows
  classify as `unknown`, never as `unchanged`: a tool that reports "no formatting change"
  when it has nothing to compare against is worse than one that says it cannot tell. Seal
  after the next sync and the row starts being checked. Two reasons: the file stays a couple of KB next to a 40 KB draft,
  and the text is already in draft.md, which is the point. Hashes are enough to CLASSIFY
  every block; the text needed to RESOLVE a pull is fetched from the live post, and only
  for the handful of blocks that actually need it.

  It is a committed file. It records what was last synced, so it belongs in history beside
  the draft it describes.

PHASES (each browser step is one JS eval in the live post's editor)

  1. scan   <piece> <out.js>                   -> JS returning title/subtitle + hashes
  2. plan   <piece> <live.json>                -> classify every block; write plan.json
  3. fetch  <piece> <plan.json> <out.js>       -> JS returning live TEXT for pull rows only
  4. pull   <piece> <plan.json> <live-text.json>  -> write those edits into draft.md
  5. (push) python3 substack_repatch.py <piece> push.js  -> the ordinary hardened push
  6. seal   <piece> <live.json>                -> record the new baseline once both agree

  seed <piece> --from-git REV | --from-draft | --from-live <live.json>
       establishes a first baseline for a piece published before sync existed.
       --from-git is the honest one: render draft.md as it stood at the commit the piece
       was composed from, which IS what was pushed.

SCOPE LIMIT (deliberate)

  A MARK PULL is described, never applied. Bringing an italic back from Substack means
  writing `*` into the markdown at a mapped offset, and the run can straddle syntax that is
  already there; the report names the block and the exact runs so a human edits draft.md.
  The PUSH direction is fully handled — substack_repatch applies em/strong as real marks.

  Structural divergence — a block or footnote added, removed or reordered on either side —
  is DESCRIBED precisely and never auto-merged. Same guardrail as substack_repatch.py: a
  live public essay is not the place for a machine to guess at a paragraph it invented or
  dropped. `plan` names the block and the side; a human resolves it.

Never publishes, never clicks. Every phase leaves the decision with a person.
"""
import sys, os, re, json, hashlib, subprocess, tempfile, shutil, difflib
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md_to_substack import (CANONICAL_SRC, render_reader, read_manifest, flatten_quotes,
                            render_block, render_footnote_block, strip_to_reader,
                            render_marks, mark_sig, mark_keys)
from substack_repatch import JS_HELPERS
import substack_account as sa

BASELINE = 'sync-baseline.json'


def H(s):
    """Hash of the COMPARISON domain: straight-quoted, whitespace-collapsed reader-text.

    Whitespace runs are collapsed here and nowhere else. HTML collapses them, so `it.  The`
    and `it. The` render identically — and `strip_to_reader` already collapses them on the
    draft side, which means a live post holding a double space describes a block NO DRAFT CAN
    EVER PRODUCE. Left comparable, that row reports a difference that can never converge, on
    every sync, forever.

    It is not a hypothetical tidiness argument. Chasing exactly that phantom on `Both Ends of
    the Leash` (2026-09-01) put a one-character edit between two adjacent footnote anchors and
    deleted one of them off a live post — an edit no reader could even have seen, made only to
    quiet a report. Comparing whitespace-insensitively makes the report quiet by itself.

    This function is only ever used for EQUALITY. Nothing positional may use it: collapsing is
    not length-preserving, so an offset computed on it would not index the real text. The
    length-preserving `flatten_quotes` is what the diff and offset machinery use.
    """
    return hashlib.sha256(re.sub(r'\s+', ' ', flatten_quotes(s)).strip().encode('utf-8')).hexdigest()[:16]


def HM(runs):
    """Hash of one block's MARKS. Same digest function as H, over the mark signature, so the
    two domains are stored and compared the same way and neither can be mistaken for the
    other."""
    return H(mark_sig(runs))


def draft_state(piece_dir):
    body, fns, residual, fn_issues = render_reader(piece_dir)
    body_m, fns_m, _offsets_ok = render_marks(piece_dir)
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    return {
        'title': man.get('title', ''), 'subtitle': man.get('subtitle', ''),
        'body': body, 'fns': fns, 'residual': residual, 'fn_issues': fn_issues,
        'bodyMarks': body_m, 'fnsMarks': fns_m,
        'post_url': man.get('post_url', ''),
    }


def load_baseline(piece_dir):
    p = os.path.join(piece_dir, BASELINE)
    return json.load(open(p)) if os.path.exists(p) else None


def write_baseline(piece_dir, title, subtitle, body_h, fns_h, note,
                   body_m=None, fns_m=None):
    """Seal a baseline. `body_m`/`fns_m` are the per-row MARK hashes; omitting them writes a
    text-only baseline, which every reader must then treat as `unknown` formatting rather
    than as unchanged. They are written only when they line up 1:1 with the text rows,
    because a mark list that has drifted out of alignment would attach one block's
    formatting to another's — the exact failure the row alignment exists to prevent."""
    p = os.path.join(piece_dir, BASELINE)
    out = {
        'note': note,
        'title': H(title), 'subtitle': H(subtitle),
        'body': body_h, 'fns': fns_h,
    }
    if body_m is not None and fns_m is not None \
            and len(body_m) == len(body_h) and len(fns_m) == len(fns_h):
        out['bodyMarks'], out['fnsMarks'] = body_m, fns_m
    json.dump(out, open(p, 'w'), indent=1)
    return p


def baseline_has_marks(base):
    """Does this baseline record formatting at all? 34 predate the question."""
    return bool(base) and 'bodyMarks' in base and 'fnsMarks' in base


# ---------------------------------------------------------------- alignment

def align(base, side):
    """LCS-align a side's hash list against the baseline's.
    Returns (pairs, added, removed): pairs are (base_idx, side_idx) for matched rows,
    added are side indices with no baseline counterpart, removed are the converse."""
    sm = difflib.SequenceMatcher(a=base, b=side, autojunk=False)
    pairs, added, removed = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            pairs += [(i1 + k, j1 + k) for k in range(i2 - i1)]
        elif tag == 'replace':
            # a same-length replace is an EDIT of those rows, not a structural change:
            # pair them up so the three-way can classify each one.
            if (i2 - i1) == (j2 - j1):
                pairs += [(i1 + k, j1 + k) for k in range(i2 - i1)]
            else:
                removed += list(range(i1, i2))
                added += list(range(j1, j2))
        elif tag == 'delete':
            removed += list(range(i1, i2))
        elif tag == 'insert':
            added += list(range(j1, j2))
    return pairs, added, removed


def _classify(b, d, l):
    if d == b and l == b:
        return 'unchanged'
    if d != b and l == b:
        return 'push'
    if d == b and l != b:
        return 'pull'
    if d == l:
        return 'converged'
    return 'conflict'


def three_way(kind, base_h, draft_h, live_h, draft_texts=None,
              base_m=None, draft_m=None, live_m=None):
    """Classify every row of one list (body or footnotes) against the baseline.
    Takes HASH lists for all three sides — at plan time the live side is hashes only,
    which is the whole point: classification never needs the live text, and the text
    for the few rows that do need it is fetched afterwards.

    Each row carries TWO verdicts. `state` is the text one and means what it always meant.
    `markState` is the same classification over the row's formatting, and it is `unknown`
    whenever any of the three sides has no mark data — a baseline sealed before marks were
    tracked, or a scan JSON captured by an older snippet. UNKNOWN IS NOT UNCHANGED: the
    whole failure being fixed here is a tool reporting no difference when it never looked.

    Returns (rows, structural)."""
    d_pairs, d_added, d_removed = align(base_h, draft_h)
    l_pairs, l_added, l_removed = align(base_h, live_h)
    d_of = dict(d_pairs)
    l_of = dict(l_pairs)

    rows, structural = [], []
    for bi in range(len(base_h)):
        di, li = d_of.get(bi), l_of.get(bi)
        if di is None or li is None:
            structural.append({'kind': kind, 'baseIdx': bi,
                               'side': 'draft' if di is None else 'live',
                               'what': 'block present at last sync is gone'})
            continue
        state = _classify(base_h[bi], draft_h[di], live_h[li])
        if base_m is not None and draft_m is not None and live_m is not None \
                and bi < len(base_m) and di < len(draft_m) and li < len(live_m):
            mark_state = _classify(base_m[bi], draft_m[di], live_m[li])
        else:
            mark_state = 'unknown'
        rows.append({'kind': kind, 'baseIdx': bi, 'draftIdx': di, 'liveIdx': li,
                     'state': state, 'markState': mark_state})

    for j in d_added:
        structural.append({'kind': kind, 'side': 'draft', 'draftIdx': j,
                           'what': 'block added since last sync',
                           'text': (draft_texts[j][:110] if draft_texts else '')})
    for j in l_added:
        # live text is not in hand at plan time; the index is enough to go look
        structural.append({'kind': kind, 'side': 'live', 'liveIdx': j,
                           'what': 'block added since last sync', 'text': ''})
    return rows, structural


# ---------------------------------------------------------------- pull into draft.md

def reader_to_source_map(block_src, reader_text):
    """reader-offset -> source-offset, for one block.

    The reader-text is the block with markdown deleted and whitespace collapsed, so it is
    very nearly a subsequence of the source. difflib's matching blocks give the alignment
    directly, which beats trying to re-derive it by parsing: it needs no knowledge of which
    syntax produced which character, and it degrades into "unmapped" rather than into a
    wrong offset."""
    # Newlines are the one systematic difference: strip_to_reader turns each into a space.
    # Swapping them 1:1 (same length, so offsets stay valid against the real source) lets
    # whitespace align exactly instead of showing up as a gap in every wrapped line.
    flat_src = block_src.replace('\n', ' ')
    m = [None] * (len(reader_text) + 1)
    for i, j, n in difflib.SequenceMatcher(a=flat_src, b=reader_text,
                                           autojunk=False).get_matching_blocks():
        for k in range(n):
            m[j + k] = i + k
    m[len(reader_text)] = len(block_src)
    # fill gaps (reader chars with no source counterpart) by taking the next known anchor
    nxt = len(block_src)
    for j in range(len(reader_text), -1, -1):
        if m[j] is None:
            m[j] = nxt
        else:
            nxt = m[j]
    return m


def edit_block_source(block_src, old_reader, new_reader, piece_dir, kind='body'):
    """Rewrite one block's markdown so its reader-text becomes `new_reader`, changing only
    the runs that differ and leaving emphasis, links and footnote markers alone.

    Verified end-to-end rather than trusted: the edited source is re-rendered and its
    reader-text compared to what was asked for. An offset map that slipped — the run
    straddled a `*`, a link, a footnote marker — fails this check and the caller is told to
    do it by hand. Returns (new_src, note) with new_src None on refusal."""
    hunks = [(j1, j2, new_reader[k1:k2])
             for tag, j1, j2, k1, k2 in _opcodes(old_reader, new_reader) if tag != 'equal']
    if not hunks:
        return block_src, 'no change'
    m = reader_to_source_map(block_src, old_reader)
    out = block_src
    for j1, j2, repl in sorted(hunks, key=lambda h: -h[0]):        # latest-first keeps offsets valid
        # End of the span is one past the LAST reader char being replaced — not the source
        # position of the next one, which would swallow any markdown sitting between them
        # (`for us*` instead of `for us`, eating the closing emphasis marker).
        a = m[j1]
        b = (m[j2 - 1] + 1) if j2 > j1 else a
        if a is None or b is None or a > b:
            return None, 'offsets could not be mapped into the markdown'
        out = out[:a] + repl + out[b:]
    rendered = (render_footnote_block(out, piece_dir) if kind == 'footnote'
                else render_block(out, piece_dir))
    if rendered is None:
        return None, 'block no longer parses as a footnote definition'
    got = flatten_quotes(strip_to_reader(rendered))
    want = flatten_quotes(new_reader)
    if got != want:
        return None, 'edited block did not re-render to the expected text'
    return out, 'verified'


def _opcodes(a, b):
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()


# ---------------------------------------------------------------- browser JS

SCAN_JS = """await (async () => {
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor — open the live post at /publish/post/<id>' });
%HELPERS%
  const sha = async s => {
    const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 16);
  };
  // TWO domains per node. The text hash is what this tool has always compared; the mark
  // signature is the formatting, which no hash of reader-text can ever carry. `markSig`
  // must produce exactly what mark_sig() produces in Python — the same string computed on
  // the two sides of the wire.
  const body = [], fns = [], bodyM = [], fnsM = [];
  const markSig = n => marksOf(n).map(markKey).join('\u0001');
  root.editor.state.doc.forEach(n => {
    if (n.type.name === 'footnote') { fns.push(n.textContent); fnsM.push(markSig(n)); }
    else if (isBodyNode(n)) { body.push(n.textContent); bodyM.push(markSig(n)); }
  });
  const hash = async a => Promise.all(a.map(t => sha(sameText(t))));   // comparison domain
  const T = document.querySelector('textarea[placeholder="Title"]');
  const S = document.querySelector('textarea[placeholder="Add a subtitle\\u2026"]');
  const scan = JSON.stringify({
    url: location.href, marksVersion: 1,
    title: T ? T.value : '', subtitle: S ? S.value : '',
    counts: { body: body.length, fns: fns.length },
    body: await hash(body), fns: await hash(fns),
    bodyMarks: await hash(bodyM), fnsMarks: await hash(fnsM)
  });
  // THE SCAN HASHES ITSELF, so the transcription off the page can be PROVED rather than
  // trusted. A scan comes back as ten kilobytes of hex that an agent then writes into a
  // file by hand — the exact transcription risk `pane_carry` removes on the way IN, with
  // nothing guarding the way out. `seal` failing closed made a slip a refusal rather than
  // a wrong baseline, which is safe but tells you nothing about WHERE it went wrong; and
  // `plan` had no such guard at all, so a mistyped hash there reads as a real difference
  // and sends somebody to re-sync a block that never changed.
  //
  // Same rule as the carrier: identify the bytes at the point of use. (2026-09-14, after
  // three baselines were resealed by hand and the hash was computed ad hoc each time.)
  const digest = [...new Uint8Array(await crypto.subtle.digest(
      'SHA-256', new TextEncoder().encode(scan)))]
    .map(b => b.toString(16).padStart(2, '0')).join('');
  return JSON.stringify({ scanVersion: 2, sha256: digest, scan });
})()"""

FETCH_JS = """(() => {
  const WANT_BODY = %BODY_IDX%, WANT_FNS = %FN_IDX%;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor found' });
%HELPERS%
  const body = [], fns = [], bodyM = [], fnsM = [];
  // the RUNS, not a hash: a mark pull is resolved by a human editing draft.md, and
  // "footnote 9 wants em 'My voice'" is the only form of that report anyone can act on.
  const runs = n => marksOf(n).map(r => ({ kind: r.kind, text: r.text, href: r.href || '' }));
  root.editor.state.doc.forEach(n => {
    if (n.type.name === 'footnote') { fns.push(n.textContent); fnsM.push(runs(n)); }
    else if (isBodyNode(n)) { body.push(n.textContent); bodyM.push(runs(n)); }
  });
  const pick = (a, idx) => Object.fromEntries(idx.map(i => [i, a[i]]));
  return JSON.stringify({ body: pick(body, WANT_BODY), fns: pick(fns, WANT_FNS),
                          bodyMarks: pick(bodyM, WANT_BODY), fnsMarks: pick(fnsM, WANT_FNS) });
})()"""


# ---------------------------------------------------------------- commands

def cmd_scan(piece_dir, out_js):
    js = sa.guarded(piece_dir, SCAN_JS.replace('%HELPERS%', JS_HELPERS), 'substack_sync scan')
    open(out_js, 'w').write(js)
    d = draft_state(piece_dir)
    print(f"wrote {out_js}")
    print(f"draft: body={len(d['body'])} fns={len(d['fns'])}  post_url~{d['post_url'] or '(none)'}")
    print("Run it in the live post's editor. SAVE ITS WHOLE RETURN VALUE — the wrapper as")
    print("well as the scan inside it: the snippet hashes its own output, and `plan` and")
    print("`seal` check that hash, so a slip in writing ten kilobytes of hex out by hand is")
    print("refused as a TRANSCRIPTION error instead of read as a difference in the post.")
    print("Then: plan <piece> <live.json>")


def load_scan(path):
    """Read a saved scan, and PROVE the transcription rather than trusting it.

    A scan comes off the page as ten kilobytes of hex that somebody then writes into a
    file by hand. Since 2026-09-14 the snippet hashes its own output, so the file it is
    saved into carries {scanVersion, sha256, scan} and this can check one against the
    other. A mismatch is a REFUSAL naming the two digests: the failure is transcription,
    not content, and the two must never wear the same face — a mistyped hash inside a scan
    reads downstream as a real difference and sends somebody to re-sync a block that never
    changed.

    An older bare scan (no wrapper) is still accepted, and says so once. It cannot be
    checked — that is the whole reason for the wrapper — so it is a note, not a silence.
    """
    raw = json.load(open(path))
    if not (isinstance(raw, dict) and 'scan' in raw and 'sha256' in raw):
        print(f"note: {os.path.basename(path)} is a bare scan with no self-hash — it "
              f"cannot be checked for transcription. Re-run `scan` for a snippet that "
              f"carries one.")
        return raw
    got = hashlib.sha256(raw['scan'].encode('utf-8')).hexdigest()
    if got != raw['sha256']:
        print("REFUSING: the scan does not hash to the digest it carries — this is a "
              "TRANSCRIPTION error, not a difference in the post.")
        print(f"  the page computed  {raw['sha256']}")
        print(f"  this file hashes   {got}")
        print("  Copy the snippet's whole return value again; do not edit it by hand.")
        sys.exit(8)
    return json.loads(raw['scan'])


def cmd_plan(piece_dir, live_json, out_plan):
    live = load_scan(live_json)
    if live.get('error'):
        print(f"scan failed: {live['error']}")
        sys.exit(1)
    d = draft_state(piece_dir)

    if d['residual']:
        print(f"Refusing: {len(d['residual'])} footnote(s) still contain 'verify': {d['residual']}")
        sys.exit(2)
    iss = {k: v for k, v in d['fn_issues'].items() if v}
    if d['fn_issues']['undefined'] or d['fn_issues']['duplicated'] or d['fn_issues']['nested']:
        print(f"Refusing: footnote refs/definitions do not pair up ({iss}).")
        sys.exit(4)

    base = load_baseline(piece_dir)
    if base is None:
        print("NO BASELINE for this piece — a two-way diff cannot tell which side moved.")
        print("Establish one first:")
        print("  seed <piece> --from-git <rev>   (render draft.md as at the commit it was composed from)")
        print("  seed <piece> --from-draft       (assert the draft is what is live)")
        print("  seed <piece> --from-live <live.json>")
        print("\nFor reference, the current raw divergence:")
        print(f"  body  draft={len(d['body'])}  live={live['counts']['body']}")
        print(f"  fns   draft={len(d['fns'])}   live={live['counts']['fns']}")
        sys.exit(3)

    # Marks are classified only when ALL THREE sides can speak: a baseline sealed before
    # marks were tracked, or a scan JSON from an older snippet, yields `unknown` rows rather
    # than a comfortable `unchanged`.
    have_marks = baseline_has_marks(base) and 'bodyMarks' in live and 'fnsMarks' in live
    bm = (base.get('bodyMarks'), [HM(r) for r in d['bodyMarks']], live.get('bodyMarks')) \
        if have_marks else (None, None, None)
    fm = (base.get('fnsMarks'), [HM(r) for r in d['fnsMarks']], live.get('fnsMarks')) \
        if have_marks else (None, None, None)

    b_rows, b_struct = three_way('body', base['body'],
                                 [H(t) for t in d['body']], live['body'], d['body'],
                                 base_m=bm[0], draft_m=bm[1], live_m=bm[2])
    f_rows, f_struct = three_way('footnote', base['fns'],
                                 [H(t) for t in d['fns']], live['fns'], d['fns'],
                                 base_m=fm[0], draft_m=fm[1], live_m=fm[2])
    rows = b_rows + f_rows
    structural = b_struct + f_struct

    title_state = ('unchanged' if H(d['title']) == base['title'] == H(live['title']) else
                   'push' if H(live['title']) == base['title'] else
                   'pull' if H(d['title']) == base['title'] else
                   'converged' if H(d['title']) == H(live['title']) else 'conflict')
    sub_state = ('unchanged' if H(d['subtitle']) == base['subtitle'] == H(live['subtitle']) else
                 'push' if H(live['subtitle']) == base['subtitle'] else
                 'pull' if H(d['subtitle']) == base['subtitle'] else
                 'converged' if H(d['subtitle']) == H(live['subtitle']) else 'conflict')

    plan = {
        'piece': os.path.basename(piece_dir), 'post_url': d['post_url'],
        'marksTracked': have_marks,
        'draftMarks': {'body': [mark_keys(r) for r in d['bodyMarks']],
                       'fns': [mark_keys(r) for r in d['fnsMarks']]},
        'title': {'state': title_state, 'draft': d['title'], 'live': live['title']},
        'subtitle': {'state': sub_state, 'draft': d['subtitle'], 'live': live['subtitle']},
        'rows': rows, 'structural': structural,
    }
    json.dump(plan, open(out_plan, 'w'), indent=1)

    tally = {}
    for r in rows:
        tally[r['state']] = tally.get(r['state'], 0) + 1
    print(f"=== {plan['piece']} ===")
    print(f"  title    {title_state}" + ('' if title_state in ('unchanged', 'converged')
                                          else f"   draft={d['title']!r} live={live['title']!r}"))
    print(f"  subtitle {sub_state}" + ('' if sub_state in ('unchanged', 'converged')
                                        else f"   draft={d['subtitle']!r} live={live['subtitle']!r}"))
    print(f"  blocks   " + '  '.join(f"{k}={v}" for k, v in sorted(tally.items())))
    mtally = {}
    for r in rows:
        mtally[r['markState']] = mtally.get(r['markState'], 0) + 1
    print(f"  marks    " + '  '.join(f"{k}={v}" for k, v in sorted(mtally.items()))
          + ('' if have_marks else
             "   (this baseline predates mark tracking — formatting is NOT being checked; "
             "seal after this sync to start)"))
    for r in rows:
        if r['state'] in ('pull', 'conflict', 'push') or r['markState'] in ('pull', 'conflict', 'push'):
            mk = '' if r['markState'] in ('unchanged', 'unknown') else f"  marks:{r['markState']}"
            print(f"    {r['state']:9} {r['kind']:8} draft#{r['draftIdx']} live#{r['liveIdx']}{mk}")
    if structural:
        print(f"  STRUCTURAL ({len(structural)}) — not auto-merged, resolve by hand:")
        for s in structural:
            print(f"    {s['side']:5} {s['kind']:8} {s.get('what')}"
                  + (f"  {s['text']!r}" if s.get('text') else ''))
    need = [r for r in rows if r['state'] in ('pull', 'conflict')
            or r['markState'] in ('pull', 'conflict')]
    mark_push = [r for r in rows if r['markState'] == 'push']
    print(f"\nwrote {out_plan}")
    if need:
        print(f"{len(need)} row(s) need live text: fetch <piece> {out_plan} <out.js>")
        if any(r['markState'] in ('pull', 'conflict') for r in rows):
            print("  NOTE: a formatting PULL is reported, never applied — bringing an italic back "
                  "means writing `*` into the markdown at a mapped offset, and the run can "
                  "straddle syntax already there. `pull` will name the block and the runs; you "
                  "edit draft.md.")
    elif (any(r['state'] == 'push' for r in rows) or mark_push
          or title_state == 'push' or sub_state == 'push'):
        print("push-only: run substack_repatch.py to stage the edits."
              + (f"  ({len(mark_push)} of them {'is' if len(mark_push) == 1 else 'are'} "
                 f"FORMATTING-only — invisible to reader-text, applied as real marks by the "
                 f"repatch engines)" if mark_push else ''))
    else:
        print("nothing to do." + ('' if have_marks else
              "  (…as far as TEXT goes; this baseline records no marks, so formatting was "
              "not compared. Seal to start checking it.)"))


def cmd_fetch(piece_dir, plan_json, out_js):
    plan = json.load(open(plan_json))
    need = [r for r in plan['rows'] if r['state'] in ('pull', 'conflict')
            or r.get('markState') in ('pull', 'conflict')]
    bidx = sorted({r['liveIdx'] for r in need if r['kind'] == 'body'})
    fidx = sorted({r['liveIdx'] for r in need if r['kind'] == 'footnote'})
    js = (FETCH_JS.replace('%HELPERS%', JS_HELPERS)
                  .replace('%BODY_IDX%', json.dumps(bidx)).replace('%FN_IDX%', json.dumps(fidx)))
    js = sa.guarded(piece_dir, js, 'substack_sync fetch')
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} — fetches {len(bidx)} body + {len(fidx)} footnote block(s) of live text")


def _summarize(old, new):
    d = [(old[j1:j2], new[k1:k2]) for tag, j1, j2, k1, k2 in _opcodes(old, new) if tag != 'equal']
    return '; '.join(f'{o[:40]!r} -> {n[:40]!r}' for o, n in d[:3]) + (' …' if len(d) > 3 else '')


def _fmt_marks(plan, lt, row):
    """One row's formatting, both sides, in the only form a human can act on: the words."""
    kind = 'fns' if row['kind'] == 'footnote' else 'body'
    live_runs = (lt.get('fnsMarks' if kind == 'fns' else 'bodyMarks') or {}).get(str(row['liveIdx']))
    draft_runs = (plan.get('draftMarks', {}).get(kind) or [None] * (row['draftIdx'] + 1))[row['draftIdx']]
    fmt = lambda rs: ('  '.join(
        f"{(r['kind'] if isinstance(r, dict) else r[0])}"
        f"{(r['text'] if isinstance(r, dict) else r[1])!r}"
        for r in rs) or '(none)') if rs is not None else '(not fetched)'
    return f"live {fmt(live_runs)}  |  draft {fmt(draft_runs)}"


def cmd_pull(piece_dir, plan_json, livetext_json):
    plan = json.load(open(plan_json))
    lt = json.load(open(livetext_json))
    d = draft_state(piece_dir)
    conflicts = [r for r in plan['rows'] if r['state'] == 'conflict'
                 or r.get('markState') == 'conflict']
    if conflicts:
        print(f"REFUSING: {len(conflicts)} conflict(s) — the same block moved on both sides.")
        for r in conflicts:
            src = lt['fns' if r['kind'] == 'footnote' else 'body'].get(str(r['liveIdx']), '')
            mine = (d['fns'] if r['kind'] == 'footnote' else d['body'])[r['draftIdx']]
            print(f"\n  {r['kind']} draft#{r['draftIdx']} / live#{r['liveIdx']}")
            print(f"    draft: {mine[:200]}")
            print(f"    live : {src[:200]}")
            if r.get('markState') == 'conflict':
                print(f"    FORMATTING also conflicts: {_fmt_marks(plan, lt, r)}")
        print("\nResolve each by hand in draft.md (or in Substack), then re-run scan/plan.")
        sys.exit(5)

    pulls = [r for r in plan['rows'] if r['state'] == 'pull']
    # A FORMATTING pull is never applied, and that is a decision, not a gap. Bringing an
    # italic back from Substack means writing `*` into the markdown at a mapped offset, and
    # the run can straddle a link, a footnote marker or emphasis that is already there --
    # the same class of edit `edit_block_source` refuses when it cannot map cleanly. So the
    # report names the block and the exact runs, and a human writes the asterisks. The PUSH
    # direction needs none of this: substack_repatch applies em/strong as real marks.
    mark_pulls = [r for r in plan['rows'] if r.get('markState') == 'pull']
    if mark_pulls:
        print(f"{len(mark_pulls)} FORMATTING pull(s) — reported, NOT applied. Substack holds "
              f"formatting draft.md does not:")
        for r in mark_pulls:
            print(f"  {r['kind']:8} draft#{r['draftIdx']} live#{r['liveIdx']}   {_fmt_marks(plan, lt, r)}")
        print("  Add the emphasis to draft.md by hand (`*word*` / `**word**`), then re-run "
              "scan/plan. Nothing above was changed for you.")

    if not pulls and plan['title']['state'] != 'pull' and plan['subtitle']['state'] != 'pull':
        if not mark_pulls:
            print("no pulls to apply.")
            return
        # draft.md still does NOT match the live post. Returning 0 here would tell a caller
        # that reads only the status that the pull is finished, which is the whole family of
        # bug this work exists to remove.
        sys.exit(6)

    path = os.path.join(piece_dir, 'draft.md')
    src = open(path).read()
    sources = render_reader.sources
    applied, manual = [], []
    for r in pulls:
        kind = 'fns' if r['kind'] == 'footnote' else 'body'
        texts = d['fns'] if kind == 'fns' else d['body']
        new = lt[kind].get(str(r['liveIdx']))
        if new is None:
            manual.append((r, 'live text not in the fetch result'))
            continue
        old_reader = texts[r['draftIdx']]
        block_src = sources[kind][r['draftIdx']]
        if block_src == CANONICAL_SRC:
            manual.append((r, 'the canonical line is generated from publish.yaml -> canonical:, '
                              'not draft.md; change it there'))
            continue
        if src.count(block_src) != 1:
            manual.append((r, 'block source is not uniquely locatable in draft.md'))
            continue
        # keep draft.md straight-quoted: the curly quotes are Substack's rendering, not content
        new_src, note = edit_block_source(block_src, old_reader, flatten_quotes(new),
                                          piece_dir, r['kind'])
        if new_src is None:
            manual.append((r, note))
            continue
        src = src.replace(block_src, new_src, 1)
        applied.append((r, f'{note}: {_summarize(old_reader, flatten_quotes(new))}'))

    if applied:
        open(path, 'w').write(src)
    print(f"applied {len(applied)} pull edit(s) to {path}")
    for r, msg in applied:
        print(f"  {r['kind']:8} draft#{r['draftIdx']}  {msg}")
    if plan['title']['state'] == 'pull' or plan['subtitle']['state'] == 'pull':
        print("\npublish.yaml needs the live value (edit by hand — it is the manifest, not prose):")
        if plan['title']['state'] == 'pull':
            print(f"  title:    {plan['title']['live']}")
        if plan['subtitle']['state'] == 'pull':
            print(f"  subtitle: {plan['subtitle']['live']}")
    if manual:
        print(f"\n{len(manual)} edit(s) could NOT be placed safely — apply by hand:")
        for r, msg in manual:
            print(f"  {r['kind']:8} draft#{r['draftIdx']}  {msg}")
        sys.exit(6)
    if mark_pulls:
        # Exit non-zero: draft.md does NOT yet match the live post, and a caller that reads
        # only the status must not be told the pull is finished.
        sys.exit(6)



# The minimal push. Where substack_repatch ships the WHOLE document and rediscovers what
# differs, sync already knows — the plan says exactly which blocks moved and in which
# direction — so this carries only those blocks. A 6,000-word essay with a one-word fix
# becomes a few hundred bytes instead of ~24 KB.
#
# It also buys a real guarantee the full-document patcher cannot give: each row carries the
# hash the block had AT SCAN TIME, and every row is checked BEFORE anything is applied. If
# the post changed in between — someone editing in Substack while this ran — the whole push
# aborts having staged nothing, instead of writing over an edit it never saw.
PUSH_JS = """await (async () => {
  const PATCH = %PATCH%, TITLE = %TITLE%, SUBTITLE = %SUBTITLE%;
  const SET_TITLE = %SET_TITLE%, SET_SUB = %SET_SUB%;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor — open the live post at /publish/post/<id>' });
  const ed = root.editor;
%HELPERS%
  const sha = async s => {
    const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 16);
  };
  const body = [], fns = [];
  ed.state.doc.forEach((node, pos) => {
    const raw = node.textContent;
    const rec = { pos, node, raw, text: flat(raw) };
    if (node.type.name === 'footnote') fns.push(rec);
    else if (isBodyNode(node)) body.push(rec);
  });
  const list = k => (k === 'footnote' ? fns : body);
  const report = { stale: [], applied: [], failed: [], reviewMarks: [],
                   titleChanged: false, subtitleChanged: false, aborted: false };

  // pre-image check across EVERY row before a single edit is applied
  for (const r of PATCH) {
    const L = list(r.kind)[r.liveIdx];
    if (!L) { report.stale.push({ kind: r.kind, liveIdx: r.liveIdx, why: 'no block at that index' }); continue; }
    if (await sha(sameText(L.raw)) !== r.expect)                       // same domain as the scan
      report.stale.push({ kind: r.kind, liveIdx: r.liveIdx,
                          why: 'live text changed since the scan', live: L.text.slice(0, 90) });
  }
  if (report.stale.length) {
    report.aborted = true;
    report.note = 'live post moved since the scan — nothing was staged. Re-run scan/plan.';
    return JSON.stringify(report);
  }

  const tasks = [];
  for (const r of PATCH) {
    const L = list(r.kind)[r.liveIdx];
    for (const h of diffHunks(L.text, flat(r.text))) tasks.push({ r, L, hunk: h });
  }
  tasks.sort((a, b) => (b.L.pos - a.L.pos) || (b.hunk.aStart - a.hunk.aStart));
  for (const t of tasks) {
    try {
      const from = offsetToPos(t.L.node, t.L.pos, t.hunk.aStart);
      const to = offsetToPos(t.L.node, t.L.pos, t.hunk.aEnd);
      const st = ed.state;
      const marks = st.doc.resolve(from).marks();
      const endMarks = st.doc.resolve(Math.max(from, to)).marks();
      const uniform = marks.length === endMarks.length && marks.every(m => endMarks.some(e => e.eq(m)));
      const prevCh = t.hunk.aStart > 0 ? t.L.raw[t.hunk.aStart - 1] : ' ';
      const ins = smarten(t.hunk.text, prevCh);
      let tr = st.tr;
      if (ins.length) tr = tr.replaceWith(from, to, st.schema.text(ins, marks));
      else tr = tr.delete(from, to);
      ed.view.dispatch(tr);
      const e = { kind: t.r.kind, liveIdx: t.r.liveIdx, insert: ins || '(deleted)' };
      report.applied.push(e);
      if (!uniform || t.hunk.big) report.reviewMarks.push(e);
    } catch (err) {
      report.failed.push({ kind: t.r.kind, liveIdx: t.r.liveIdx, error: String(err) });
    }
  }
  const setField = (sel, v) => {
    const el = document.querySelector(sel);
    if (!el || el.value === v) return false;
    const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  };
  if (SET_TITLE) report.titleChanged = setField('textarea[placeholder="Title"]', TITLE);
  if (SET_SUB) report.subtitleChanged = setField('textarea[placeholder="Add a subtitle\\u2026"]', SUBTITLE);
  report.stagedEdits = report.applied.length;
  return JSON.stringify(report);
})()"""


def cmd_push(piece_dir, plan_json, live_json, out_js):
    plan = json.load(open(plan_json))
    live = load_scan(live_json)
    d = draft_state(piece_dir)
    if any(r['state'] == 'conflict' for r in plan['rows']):
        print("REFUSING: the plan has conflicts. Resolve them first (see `pull`).")
        sys.exit(5)
    patch = []
    for r in plan['rows']:
        if r['state'] != 'push':
            continue
        kind = r['kind']
        texts = d['fns'] if kind == 'footnote' else d['body']
        expect = (live['fns'] if kind == 'footnote' else live['body'])[r['liveIdx']]
        patch.append({'kind': kind, 'liveIdx': r['liveIdx'],
                      'expect': expect, 'text': texts[r['draftIdx']]})
    set_title = plan['title']['state'] == 'push'
    set_sub = plan['subtitle']['state'] == 'push'
    if not patch and not set_title and not set_sub:
        print("nothing to push.")
        return
    js = (PUSH_JS.replace('%HELPERS%', JS_HELPERS)
                 .replace('%PATCH%', json.dumps(patch))
                 .replace('%TITLE%', json.dumps(d['title']))
                 .replace('%SUBTITLE%', json.dumps(d['subtitle']))
                 .replace('%SET_TITLE%', 'true' if set_title else 'false')
                 .replace('%SET_SUB%', 'true' if set_sub else 'false'))
    js = sa.guarded(piece_dir, js, 'substack_sync push')
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} ({len(js)} bytes) — {len(patch)} block(s)"
          + (", title" if set_title else "") + (", subtitle" if set_sub else ""))
    for p_ in patch:
        print(f"  {p_['kind']:8} live#{p_['liveIdx']}")


def _render_at(piece_dir, rev, top):
    """Render draft.md as it stood at `rev`, in a temp copy of the piece."""
    rel = os.path.relpath(os.path.abspath(os.path.join(piece_dir, 'draft.md')), top)
    blob = subprocess.run(['git', '-C', top, 'show', f'{rev}:{rel}'],
                          capture_output=True, text=True, check=True).stdout
    tmp = tempfile.mkdtemp()
    try:
        for f in os.listdir(piece_dir):
            src = os.path.join(piece_dir, f)
            if os.path.isfile(src):
                shutil.copy2(src, tmp)
        open(os.path.join(tmp, 'draft.md'), 'w').write(blob)
        body, fns, _res, _iss = render_reader(tmp)
        bm, fm, _ok = render_marks(tmp)
        return ([H(t) for t in body], [H(t) for t in fns],
                [HM(r) for r in bm], [HM(r) for r in fm])
    finally:
        shutil.rmtree(tmp)


IMAGES_JS = """(() => {
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor — open the live post at /publish/post/<id>' });
  // Collect every image the post holds, wherever it sits in the node tree. Attribute names
  // vary by node type (captionedImage/image/nativeVideo thumbnails), so take any attr that
  // looks like a URL rather than guessing one key.
  const out = [];
  const visit = (n) => {
    const a = n.attrs || {};
    for (const k of ['src', 'url', 'imageSrc', 'thumbnail']) {
      if (typeof a[k] === 'string' && /^https?:\/\//.test(a[k])) {
        out.push({ type: n.type.name, attr: k, src: a[k],
                   alt: a.alt || '', caption: (a.caption && String(a.caption)) || '' });
        break;
      }
    }
    n.forEach ? n.forEach(visit) : null;
  };
  root.editor.state.doc.forEach(visit);
  // DOM fallback: anything rendered as an <img> that the node walk missed.
  for (const el of root.querySelectorAll('img')) {
    if (el.src && /^https?:\/\//.test(el.src) && !out.some(o => o.src === el.src))
      out.push({ type: 'dom-img', attr: 'src', src: el.src, alt: el.alt || '', caption: '' });
  }
  // EMBEDS: media the draft cannot express at all. An image at least has a URL that can sit
  // in draft.md; a YouTube embed is a `youtube2` node carrying `videoId` and NOTHING that
  // looks like a URL, so the loop above cannot see it and every image check ran blind past
  // it. Collect any non-text node that produced no image entry, so a new embed kind Substack
  // adds later is caught by default rather than needing this list extended.
  const TEXTY = new Set(['doc','paragraph','heading','text','hardBreak','horizontalRule','hr',
    'blockquote','bulletList','orderedList','listItem','footnote','codeBlock',
    'footnoteAnchor']);   // footnoteAnchor is structural, not media — the footnote machinery owns it
  const emb = [];
  // An image WRAPPER is not an embed. `captionedImage` carries the caption and the image sits
  // in its child `image2`, so a node's OWN attrs cannot settle it -- and since captions began
  // being emitted (2026-09-11) every captioned hero read as an unrecorded embed and refused
  // its own recompose. Ask the SUBTREE instead: a node containing an image the scrape already
  // collected is that image's wrapper. A youtube2 still carries no image anywhere under it, so
  // catching a new embed kind by default is unchanged -- which is the property to keep.
  const hasImageInSubtree = (n) => {
    let found = false;
    const walk = (m) => {
      if (found) return;
      const a = m.attrs || {};
      if (['src','url','imageSrc','thumbnail'].some(k => typeof a[k] === 'string' && out.some(o => o.src === a[k]))) {
        found = true; return;
      }
      m.forEach ? m.forEach(walk) : null;
    };
    walk(n);
    return found;
  };
  const visitEmbed = (n) => {
    if (!TEXTY.has(n.type.name) && !hasImageInSubtree(n)) {
      const id = Object.values(a).find(v => typeof v === 'string' && v.length);
      emb.push({ type: n.type.name, key: id || n.type.name, attrs: a });
    }
    n.forEach ? n.forEach(visitEmbed) : null;
  };
  root.editor.state.doc.forEach(visitEmbed);
  return JSON.stringify({ images: out, embeds: emb });
})()"""


def canonical_image_url(u):
    """Reduce a Substack image URL to the asset it actually points at.

    The same picture surfaces twice in a scrape: once as the node's own `src` (the S3
    object) and once as the rendered <img>, which Substack wraps in a CDN transform —
    `substackcdn.com/image/fetch/$s_!x,w_1456,.../https%3A%2F%2F...s3...png`. They are one
    image in two dresses. Comparing the dressed form against draft.md would report a live
    image as unreferenced and fail a recompose that was perfectly safe, so unwrap the
    embedded original and compare that.
    """
    m = re.search(r'/(https?%3A%2F%2F[^/]+)$', u, re.I) or re.search(r'/(https?://.+)$', u[8:], re.I)
    if 'substackcdn.com/image/fetch/' in u and m:
        return urllib.parse.unquote(m.group(1))
    return u


def cmd_images(piece_dir, out_js):
    """Emit the scraper half of the recompose image gate.

    `check-images` compares what the LIVE post holds against what draft.md references, and it
    needs a scrape to compare against. This writes that snippet. It shipped without this half
    (2026-09-01): the dispatch named `cmd_images`, nothing defined it, and `images` crashed with
    a NameError — which meant the gate could not be run at all, on the very day the gate was
    added to stop a recompose destroying a live image.
    """
    open(out_js, 'w').write(sa.guarded(piece_dir, IMAGES_JS, 'substack_sync images'))
    draft = open(os.path.join(piece_dir, 'draft.md')).read()
    refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', draft)
    print(f"wrote {out_js}")
    print(f"draft.md references {len(refs)} image(s)")
    print("Run it in the post's editor, save the JSON it returns, then:")
    print(f"  python3 framework/tools/substack_sync.py check-images {piece_dir} <images.json>")


def cmd_check_images(piece_dir, images_json):
    """Refuse a recompose that would destroy an image.

    A recompose re-pastes the whole body from draft.md. Any image the LIVE post holds that
    the draft does not reference is simply gone the moment that paste lands, and the desk
    stores no bytes to rebuild it from — images are URL-only by policy (2026-09-01), which
    keeps binaries out of git history at the cost of the repo being unable to reconstruct a
    post on its own.

    That policy is safe only while every live image is actually referenced in draft.md, and
    nothing was checking. `The Highest Peak` was one paste away from proving it (2026-09-01):
    a captionedImage in the body and no image markdown in the draft at all.

    So this is the recompose preflight. It compares what the post HAS against what the draft
    KNOWS ABOUT, and refuses on any gap. Fix a gap by pasting the image's URL into draft.md
    where it belongs — never by deleting it from the post.
    """
    data = json.load(open(images_json))
    if data.get('error'):
        print(f"scrape failed: {data['error']}")
        sys.exit(1)
    draft = open(os.path.join(piece_dir, 'draft.md')).read()
    seen, live = set(), []
    for im in data.get('images', []):                                # dedupe on the real asset
        c = canonical_image_url(im['src'])
        if c in seen:
            continue
        seen.add(c)
        live.append({**im, 'canonical': c})
    # A piece may reference an uploaded asset the SANCTIONED way — `![alt](assets/hero.png)`
    # in draft.md, plus an `images:` entry in publish.yaml mapping that file to the URL it is
    # already at (the publish skill's 0b-images). The converter reads that map and emits
    # <img src="<that url>">, so a recompose REUSES the asset rather than orphaning it: this
    # is the safe case, and comparing live URLs against the draft's TEXT alone reported it as
    # the dangerous one — then advised pasting the URL into draft.md, which contradicts the
    # convention it is meant to protect. Both halves are required: a map entry whose local
    # file nothing in the draft references would still be lost by a re-paste.
    mapped = set()
    man_path = os.path.join(piece_dir, 'publish.yaml')
    if os.path.exists(man_path):
        try:
            import yaml as _yaml
            man = _yaml.safe_load(open(man_path, encoding='utf-8')) or {}
        except Exception:
            man = {}
        for local, url in (man.get('images') or {}).items():
            if local and isinstance(url, str) and str(local) in draft:
                mapped.add(canonical_image_url(url))
    missing = [im for im in live
               if im['canonical'] not in draft and im['canonical'] not in mapped]
    print(f"live images: {len(live)} (deduped)   referenced in draft.md: {len(live) - len(missing)}")
    for im in live:
        via = ' (via publish.yaml images:)' if (im not in missing
                                                and im['canonical'] not in draft) else ''
        mark = 'MISSING' if im in missing else 'ok     '
        print(f"  {mark} {im['type']:12} {im['canonical'][:76]}{via}")
    if missing:
        print(f"\nREFUSING: {len(missing)} live image(s) are not referenced in draft.md.")
        print("A recompose re-pastes the body and would destroy them, and the desk keeps no")
        print("local copy to restore from. Paste each URL into draft.md where the image belongs")
        print("(![alt](<url>)) and re-run. Do not resolve this by removing the image from the post.")
        sys.exit(8)
    print("\nOK — every live image is referenced in the draft. A recompose cannot lose one.")

    # ---- embeds -------------------------------------------------------------------------
    # An embed is NOT like an image. An image can be made recompose-safe by pasting its URL
    # into draft.md, because the converter emits <img>. There is no markdown that emits a
    # `youtube2` node, so an embed CANNOT be made reproducible — recording it only makes the
    # loss visible and re-addable by hand. Say that plainly rather than implying the manifest
    # protects it. (hollow-flute, 2026-09-03: a YouTube embed sat on a live post completely
    # invisible to every check here, because it carries a videoId and no URL.)
    embeds = data.get('embeds', [])
    if embeds:
        man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
        recorded = set(man.get('embeds', {}) or {})
        unrecorded = [e for e in embeds if e['key'] not in recorded]
        print(f"\nlive embeds: {len(embeds)}   recorded in publish.yaml: {len(embeds) - len(unrecorded)}")
        for e in embeds:
            mark = 'UNRECORDED' if e in unrecorded else 'ok        '
            print(f"  {mark} {e['type']:12} {e['key']}")
        if unrecorded:
            print(f"\nREFUSING: {len(unrecorded)} live embed(s) are not recorded in publish.yaml.")
            print("A recompose WILL drop them — no markdown reproduces an embed — and nothing in")
            print("the repo can rebuild one. Add each under an `embeds:` block (key = the id below,")
            print("value = what it is and where it sits), then re-add it by hand in the composer")
            print("after any recompose. Do not resolve this by deleting the embed from the post.")
            sys.exit(9)
        print("Every live embed is recorded. NOTE: recording is not protection — a recompose")
        print("still drops them, and they must be re-added by hand in the composer afterwards.")



def cmd_detect(piece_dir, live_json):
    """Find which revision the LIVE POST still matches — that one IS the baseline.

    Do not reach for "the newest commit." A commit can carry an editorial pass that was
    never published, and seeding from it inverts every row that pass touched: the tool
    reports a PULL and dutifully reverts the change in draft.md, reporting success.

    That is not hypothetical. `e37d5f3` bundled a corpus-wide deity-pronoun capitalization
    sweep into an unrelated compose commit, and the sweep never reached Substack. Seeding
    `The Way Home Is Down` from it wanted to revert ten capitals — caught, because this
    comparison was run by hand. Seeding `They/Them` and `I Believe in You` from it was NOT
    checked, and ten more capitals were quietly pulled out of two live essays before the
    author noticed. Hence this command: the check is the tool's job, not the operator's
    memory.
    """
    live = load_scan(live_json)
    top = subprocess.run(['git', '-C', piece_dir, 'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True, check=True).stdout.strip()
    rel = os.path.relpath(os.path.abspath(os.path.join(piece_dir, 'draft.md')), top)
    revs = subprocess.run(['git', '-C', top, 'log', '--format=%h', '--', rel],
                          capture_output=True, text=True, check=True).stdout.split()
    if not revs:
        print("no commits touch this draft — nothing to detect.")
        sys.exit(1)
    live_bm, live_fm = live.get('bodyMarks'), live.get('fnsMarks')
    print(f"{'rev':10} {'body':>14} {'footnotes':>14} {'marks':>14}   subject")
    best, best_score = None, -1
    for rev in revs:
        try:
            bh, fh, bmh, fmh = _render_at(piece_dir, rev, top)
        except Exception as e:
            print(f"{rev:10} (render failed: {e})")
            continue
        bm = sum(1 for x, y in zip(bh, live['body']) if x == y)
        fm = sum(1 for x, y in zip(fh, live['fns']) if x == y)
        exact = (len(bh) == len(live['body']) and len(fh) == len(live['fns']))
        # Marks break the tie, and only the tie. Two revisions can match the live post on
        # every word while only one of them matches its italics -- and the one that does is
        # the state that was actually pushed. Weighted below a single text row so a scan with
        # no mark data (an older snippet) changes nothing about which rev is chosen.
        if live_bm is not None and live_fm is not None:
            mm = (sum(1 for x, y in zip(bmh, live_bm) if x == y)
                  + sum(1 for x, y in zip(fmh, live_fm) if x == y))
            mtot = len(bmh) + len(fmh)
            mcol = f'{mm:>6}/{mtot:<7}'
            mbonus = (mm / mtot) if mtot else 0
        else:
            mm, mcol, mbonus = 0, f'{"-":>14}', 0
        score = bm + fm + (10000 if exact and bm == len(bh) else 0) + mbonus
        subj = subprocess.run(['git', '-C', top, 'log', '-1', '--format=%s', rev],
                              capture_output=True, text=True).stdout.strip()[:54]
        print(f"{rev:10} {bm:>6}/{len(bh):<7} {fm:>6}/{len(fh):<7} {mcol}   {subj}")
        if score > best_score:
            best, best_score = rev, score
    print(f"\nbest match: {best}")
    print(f"  seed {piece_dir} --from-git {best}")
    print("A revision matching the live post on EVERY body block is the state that was last\n"
          "pushed. If the newest commit is not that revision, it carries work that never\n"
          "shipped — seeding from it would revert that work instead of publishing it.")


def cmd_resolve(piece_dir, live_json, args):
    """Record a HUMAN's decision on a conflicted row, by moving the baseline for that row.

    A conflict means both sides moved and disagree, and no rule can settle it — which is why
    `pull` and `push` both refuse to touch one. Resolving is therefore not a flag that forces
    past a guard; it is the decision the guard exists to ask for, written down.

    --take-draft <kind>:<idx>  the draft is right: baseline := live, so the row becomes a PUSH
    --take-live  <kind>:<idx>  live is right:      baseline := draft, so the row becomes a PULL

    Take-draft after editing the draft by hand is the normal shape: incorporate whatever live
    had that you want, put the finished text in draft.md, then say so here.
    """
    live = load_scan(live_json)
    base = load_baseline(piece_dir)
    if base is None:
        print("no baseline to resolve against.")
        sys.exit(3)
    d = draft_state(piece_dir)
    draft_h = {'body': [H(t) for t in d['body']], 'footnote': [H(t) for t in d['fns']]}
    live_h = {'body': live['body'], 'footnote': live['fns']}
    draft_m = {'body': [HM(r) for r in d['bodyMarks']], 'footnote': [HM(r) for r in d['fnsMarks']]}
    live_m = {'body': live.get('bodyMarks'), 'footnote': live.get('fnsMarks')}
    key = {'body': 'body', 'footnote': 'fns'}
    mkey = {'body': 'bodyMarks', 'footnote': 'fnsMarks'}
    done = []
    i = 0
    while i < len(args):
        mode = args[i]
        if mode not in ('--take-draft', '--take-live'):
            print(f"unknown option {mode!r}")
            sys.exit(1)
        kind, _, idx = args[i + 1].partition(':')
        idx = int(idx)
        if kind not in ('body', 'footnote'):
            print(f"kind must be body or footnote, got {kind!r}")
            sys.exit(1)
        base[key[kind]][idx] = (live_h[kind][idx] if mode == '--take-draft'
                                else draft_h[kind][idx])
        # A row is one row in both domains. Moving its text hash and leaving its mark hash
        # behind would resolve the words and quietly re-open the formatting as a fresh
        # conflict on the next plan.
        if baseline_has_marks(base) and live_m[kind] is not None:
            base[mkey[kind]][idx] = (live_m[kind][idx] if mode == '--take-draft'
                                     else draft_m[kind][idx])
        done.append(f"{mode[7:]:5} {kind}#{idx}")
        i += 2
    base['note'] = base.get('note', '') + f" | resolved by hand: {', '.join(done)}"
    json.dump(base, open(os.path.join(piece_dir, BASELINE), 'w'), indent=1)
    print(f"resolved {len(done)} row(s) in {os.path.join(piece_dir, BASELINE)}:")
    for x in done:
        print(f"  {x}")



def cmd_seed(piece_dir, mode, arg):
    body_m = fns_m = None
    if mode == '--from-draft':
        d = draft_state(piece_dir)
        title, subtitle = d['title'], d['subtitle']
        body_h, fns_h = [H(t) for t in d['body']], [H(t) for t in d['fns']]
        body_m, fns_m = [HM(r) for r in d['bodyMarks']], [HM(r) for r in d['fnsMarks']]
        note = 'seeded from draft.md as it stands'
    elif mode == '--from-live':
        live = load_scan(arg)
        title, subtitle = live['title'], live['subtitle']
        body_h, fns_h = live['body'], live['fns']
        body_m, fns_m = live.get('bodyMarks'), live.get('fnsMarks')
        note = 'seeded from the live post'
    elif mode == '--from-git':
        # git must run in the PIECE's repo, not the framework submodule this file lives in
        top = subprocess.run(['git', '-C', piece_dir, 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, check=True).stdout.strip()
        rel = os.path.relpath(os.path.abspath(os.path.join(piece_dir, 'draft.md')), top)
        blob = subprocess.run(['git', '-C', top, 'show', f'{arg}:{rel}'],
                              capture_output=True, text=True, check=True).stdout
        # publish.yaml AS AT THAT REV too, and it must reach the RENDER, not just the header.
        # The body is rendered from draft.md AND the manifest — the converter prepends
        # "Originally published at <canonical>" for any piece whose manifest records one — so
        # copying today's publish.yaml beside an old draft.md renders a body that was never
        # pushed anywhere. Measured 2026-09-18 on scaling-computer-vision-workflows-aws:
        # `canonical:` was recorded at the cutover, AFTER the Substack compose, and the seed
        # produced a 35-block baseline for a 34-block post. A baseline that never matched the
        # live post is the exact lie this file's seal guard exists to refuse.
        relman = os.path.relpath(os.path.abspath(os.path.join(piece_dir, 'publish.yaml')), top)
        old_man = subprocess.run(['git', '-C', top, 'show', f'{arg}:{relman}'],
                                 capture_output=True, text=True)
        tmp = tempfile.mkdtemp()
        try:
            for f in os.listdir(piece_dir):
                s = os.path.join(piece_dir, f)
                if os.path.isfile(s):
                    shutil.copy2(s, tmp)
            open(os.path.join(tmp, 'draft.md'), 'w').write(blob)
            if old_man.returncode == 0:
                open(os.path.join(tmp, 'publish.yaml'), 'w').write(old_man.stdout)
            body, fns, _res, _iss = render_reader(tmp)
            bmarks, fmarks, _ok = render_marks(tmp)
            man = read_manifest(os.path.join(tmp, 'publish.yaml'))
        finally:
            shutil.rmtree(tmp)
        title, subtitle = man.get('title', ''), man.get('subtitle', '')
        body_h, fns_h = [H(t) for t in body], [H(t) for t in fns]
        body_m, fns_m = [HM(r) for r in bmarks], [HM(r) for r in fmarks]
        note = f'seeded from draft.md + publish.yaml at {arg}'
    else:
        print("seed needs --from-git <rev> | --from-draft | --from-live <live.json>")
        sys.exit(1)
    p = write_baseline(piece_dir, title, subtitle, body_h, fns_h, note,
                       body_m=body_m, fns_m=fns_m)
    print(f"wrote {p} — {note} (body={len(body_h)} fns={len(fns_h)}"
          + (")" if body_m is not None else
             ", NO MARKS — the source carried none, so formatting will read `unknown`)"))


def _warn_if_draft_uncommitted(piece_dir):
    """A baseline sealed against an UNCOMMITTED draft describes a state the repo does not contain.

    Measured 2026-09-03. Six baselines were sealed from working-tree drafts; three of those drafts
    carried a house edit that had been pushed to Substack but never committed. Locally everything
    agreed — draft, live post and baseline. In CI, which checks out the committed tree, the draft
    was the old text and the baseline described the new one, so the build went red on every push
    and the local suite stayed green, which is the most confusing shape a failure can take.

    The baseline is not wrong in that situation; git is behind. So this WARNS rather than refuses —
    sealing mid-edit is legitimate — but it names the consequence and the fix, because nothing
    warned at all the first time and the inconsistency was invisible until CI found it.
    """
    # ABSOLUTE path: with `git -C <piece_dir>` a relative pathspec resolves inside that
    # directory, so passing 'pieces/<slug>/draft.md' looks for it twice-nested and matches
    # nothing. The first version of this guard silently never fired for that reason.
    draft = os.path.abspath(os.path.join(piece_dir, 'draft.md'))
    try:
        top = subprocess.run(['git', '-C', piece_dir, 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, timeout=10)
        if top.returncode != 0:
            return
        st = subprocess.run(['git', '-C', piece_dir, 'status', '--porcelain', '--', draft],
                            capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return
    if not st:
        return
    print('WARNING: %s has uncommitted changes.' % draft)
    print('  This baseline describes the draft AS IT IS ON DISK, which is not what the repo holds.')
    print('  Commit the draft in the SAME commit as the baseline, or CI will compare the committed')
    print('  draft against a baseline of the uncommitted one and fail while your local suite passes.')


def cmd_seal(piece_dir, live_json):
    live = load_scan(live_json)
    d = draft_state(piece_dir)
    db, df = [H(t) for t in d['body']], [H(t) for t in d['fns']]
    dbm, dfm = [HM(r) for r in d['bodyMarks']], [HM(r) for r in d['fnsMarks']]

    # A seal says "these two are the same now". Before marks were compared it could say that
    # while an italic was missing, and then the baseline made the lie permanent: every future
    # plan measured against a state that was never true. So formatting is a sealing condition,
    # not a footnote to one.
    if 'bodyMarks' in live and 'fnsMarks' in live:
        if dbm != live['bodyMarks'] or dfm != live['fnsMarks']:
            print("REFUSING to seal: the words agree but the FORMATTING does not.")
            for kind, a, b, runs in (('body', dbm, live['bodyMarks'], d['bodyMarks']),
                                     ('footnote', dfm, live['fnsMarks'], d['fnsMarks'])):
                for i, (x, y) in enumerate(zip(a, b)):
                    if x != y:
                        print(f"    {kind} #{i}  draft marks: "
                              + (', '.join(f'{k}{t!r}' for k, t, _h in mark_keys(runs[i])) or '(none)'))
            print("  Push it (substack_repatch applies em/strong), or bring the live formatting")
            print("  into draft.md by hand, then seal. Sealing now would record a state that is")
            print("  not true and hide the difference from every later sync.")
            sys.exit(7)
    else:
        print("NOTE: this scan carries no mark data (an older scan snippet). Sealing the text")
        print("      only; formatting will read as `unknown` until a fresh scan is sealed.")

    if db != live['body'] or df != live['fns']:
        print("REFUSING to seal: draft and live still differ — sync is not complete.")
        print(f"  body  draft={len(db)} live={len(live['body'])}  "
              f"matched={sum(1 for a, b in zip(db, live['body']) if a == b)}")
        print(f"  fns   draft={len(df)} live={len(live['fns'])}  "
              f"matched={sum(1 for a, b in zip(df, live['fns']) if a == b)}")
        sys.exit(7)
    if H(d['title']) != H(live['title']) or H(d['subtitle']) != H(live['subtitle']):
        print("REFUSING to seal: title/subtitle still differ between publish.yaml and live.")
        sys.exit(7)
    _warn_if_draft_uncommitted(piece_dir)
    marks_ok = 'bodyMarks' in live and 'fnsMarks' in live
    p = write_baseline(piece_dir, d['title'], d['subtitle'], db, df,
                       'sealed: draft and live agree' + (' (text and marks)' if marks_ok else
                                                         ' (text only — scan carried no marks)'),
                       body_m=dbm if marks_ok else None, fns_m=dfm if marks_ok else None)
    print(f"sealed {p} (body={len(db)} fns={len(df)}"
          + (f" marks={sum(len(r) for r in d['bodyMarks']) + sum(len(r) for r in d['fnsMarks'])})"
             if marks_ok else ", no marks recorded)"))


def main():
    if len(sys.argv) < 3:
        print("usage: substack_sync.py <scan|plan|fetch|pull|push|resolve|detect|images|check-images|seed|seal> <piece-dir> [args]")
        sys.exit(1)
    cmd, piece_dir = sys.argv[1], sys.argv[2].rstrip('/')
    rest = sys.argv[3:]
    if cmd == 'scan':
        cmd_scan(piece_dir, rest[0] if rest else 'scan.js')
    elif cmd == 'plan':
        cmd_plan(piece_dir, rest[0], rest[1] if len(rest) > 1 else 'sync-plan.json')
    elif cmd == 'fetch':
        cmd_fetch(piece_dir, rest[0], rest[1] if len(rest) > 1 else 'fetch.js')
    elif cmd == 'pull':
        cmd_pull(piece_dir, rest[0], rest[1])
    elif cmd == 'resolve':
        cmd_resolve(piece_dir, rest[0], rest[1:])
    elif cmd == 'push':
        cmd_push(piece_dir, rest[0], rest[1], rest[2] if len(rest) > 2 else 'push.js')
    elif cmd == 'images':
        cmd_images(piece_dir, rest[0] if rest else 'images.js')
    elif cmd == 'check-images':
        cmd_check_images(piece_dir, rest[0])
    elif cmd == 'detect':
        cmd_detect(piece_dir, rest[0])
    elif cmd == 'seed':
        cmd_seed(piece_dir, rest[0], rest[1] if len(rest) > 1 else None)
    elif cmd == 'seal':
        cmd_seal(piece_dir, rest[0])
    else:
        print(f"unknown command {cmd!r}")
        sys.exit(1)


if __name__ == '__main__':
    main()
