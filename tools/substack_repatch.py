#!/usr/bin/env python3
"""
substack_repatch.py — surgically re-sync an ALREADY-PUBLISHED Substack post to the
current draft.md, changing only what actually changed and touching nothing else.

Where md_to_substack.py composes a fresh post from scratch, this emits a self-contained
JS snippet that, run once in the OPEN editor of the *live* post, will:

  1. read the current draft's reader-text (body blocks + native footnotes) — baked in
     here by this tool, after the SAME verify-and-strip preflight as a fresh publish;
  2. scrape the live post's reader-text straight out of its ProseMirror doc;
  3. align them (non-empty body top-nodes 1:1, footnote nodes 1:1) and REFUSE if the
     structure differs — a block or footnote added / removed / reordered — because that
     is a rewrite, not a touch-up, and wants a full recompose or a human, not a blind
     nuke-and-repave of a live public essay;
  4. otherwise replace only the changed run inside each changed node — preserving the
     surrounding text, the node, and the marks (bold/italic/links) across the edit —
     plus the title/subtitle if they changed;
  5. reconcile the MARKS themselves, which no text comparison can see: the em/strong runs
     the draft has and the live post lacks are added, the ones it no longer has are
     removed, and link drift is reported rather than guessed at;
  6. return a JSON report (applied / unchanged / marks / footnoteChanges / structural / failed).

Step 5 exists because steps 1-4 were measurably blind. Everything they compare is
READER-TEXT, and wrapping a word that is already in the post in <em> changes none of it:
on `rising-after-falls`, 2026-09-09, italicising two words produced a regenerated patch
byte-identical in size to the previous one (29,782 bytes), which reported `unchanged` and
applied nothing — a FALSE PASS, the one result a re-sync tool must never be able to give.
Applying a mark is not a text replacement, so it does not go through the hunk machinery:
the block is located by text, its text nodes walked to map string offsets to absolute
ProseMirror positions (a block is split into several runs by its footnote anchors), the
range read back and asserted to equal the exact string the draft marks, and only then is
`addMark` dispatched.

It never clicks anything. After it stages the edits, the "Continue" button lights up and
a HUMAN reviews and clicks Continue -> Publish (choosing not to resend email). Same
draft-only guarantee as md_to_substack.py.

Usage:  python3 substack_repatch.py <piece-dir> [out.js]
        python3 substack_repatch.py --structural <piece-dir> [out.js]

--structural is the second engine, for the case the first one REFUSES: a block added,
removed, merged or split, or a footnote retired — a rewrite of a live post whose embeds
and images a full recompose would destroy. It aligns draft blocks against the live doc by
text (LCS), and then:

  * pairs every ANCHOR-BEARING block 1:1 by order inside each changed range and edits
    those by text hunk only, so the native footnote anchors are never touched by HTML;
  * replaces everything else whole, from the converter's own HTML (italics, links), with
    quotes smartened OUTSIDE tags only — an href with curled quotes is a dead link;
  * drops the anchor of a footnote the draft has retired, and the orphaned footnote node
    if the editor does not remove it itself;
  * REFUSES, before touching anything, when: a block's HTML does not hash to its own text
    (a transcription error, if the snippet was retyped into an eval); anchor-bearing blocks
    do not pair 1:1; the draft ADDS a footnote (insertFootnote is not automated here);
    footnote order differs; or a hunk would span an inline node or a mark boundary.

Every op is checked against the draft's own sha256/16 after it lands, and the whole
document is re-read at the end: block count, every block's text, footnote count, anchor
count, and a link mark on every block whose HTML carried one. It grew out of three
hand-built syncs of `The Hollow Flute` (2026-09-04 → 07), each of which needed one more
guard than the last; the guards are the point.

The caller (the `publish` skill in republish mode) runs the emitted JS once against the
live post's editor at  https://<pub>.substack.com/publish/post/<id> .

Baseline: this diffs the current draft against the LIVE POST ITSELF (scraped at run time),
not a stored snapshot — so it is stateless and self-correcting: whatever is deployed is
the baseline, and only the delta to the current draft is applied.
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md_to_substack import render_reader, read_manifest, flatten_quotes, render_marks
import substack_account as sa


def main():
    structural = '--structural' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print("usage: substack_repatch.py <piece-dir> [out.js]")
        sys.exit(1)
    piece_dir = args[0].rstrip('/')
    out_js = args[1] if len(args) > 1 else 'repatch.js'
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    post_url = man.get('post_url', '')
    body, fns, residual, fn_issues = render_reader(piece_dir)
    body_marks, fn_marks, offsets_ok = render_marks(piece_dir)
    if not (len(body_marks) == len(body) and len(fn_marks) == len(fns)):
        print("Refusing: the mark scanner and render_reader disagree on how many blocks this "
              "draft has. They walk the same list and must not diverge; fix that before "
              "trusting either.")
        sys.exit(5)
        print(f"WARNING: {len(residual)} footnote(s) still carry verify or clearance language (an ISO date, 'consulted …') after cleaning: "
              f"{residual}. Resolve the note (verify -> move behind a †, or delete; a desk path such as "
              f"projects/…/facts.md -> a public URL or plain words) before republishing.")
        print("Refusing to write output.")
        sys.exit(2)

    if fn_issues['undefined'] or fn_issues['duplicated'] or fn_issues['nested']:
        print(f"Refusing: footnote refs and definitions do not pair up "
              f"({ {k: v for k, v in fn_issues.items() if v} }). Each of these shifts the "
              f"footnote indexing the surgical diff aligns on.")
        sys.exit(4)

    n_marks = sum(len(r) for r in body_marks) + sum(len(r) for r in fn_marks)
    print(f"target body-blocks~{len(body)}  footnotes~{len(fns)}  marked-runs~{n_marks}  "
          f"post_url~{post_url or '(none — set it in publish.yaml before republishing)'}")
    if not offsets_ok:
        print("NOTE: a block's scanned text did not reproduce its reader-text, so mark offsets "
              "are advisory here; runs are still located in the live doc by their text.")
    if not post_url:
        print("NOTE: publish.yaml has no post_url. Republish mode targets the editor of an existing "
              "post; open https://<pub>.substack.com/publish/post/<id> for the live post, and record "
              "that post_url in publish.yaml so future runs are unambiguous.")

    if structural:
        js = sa.guarded(piece_dir, build_structural(piece_dir, man, body, fns, body_marks, fn_marks),
                        'substack_repatch --structural')
        open(out_js, 'w').write(js)
        print(f"wrote {out_js} ({len(js)} bytes) — STRUCTURAL engine: run once in the live editor; "
              f"read `refused` and `ok` in the report; nothing is applied on a refusal")
        return

    js = (REPATCH_JS
          .replace('%HELPERS%', JS_HELPERS)
          .replace('%TITLE%', json.dumps(man.get('title', '')))
          .replace('%SUBTITLE%', json.dumps(man.get('subtitle', '')))
          .replace('%BODY%', json.dumps(body))
          .replace('%FNS%', json.dumps(fns))
          .replace('%BODYMARKS%', json.dumps(jsonable(body_marks)))
          .replace('%FNMARKS%', json.dumps(jsonable(fn_marks))))
    js = sa.guarded(piece_dir, js, 'substack_repatch')
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} ({len(js)} bytes)")


def jsonable(marks):
    """render_marks' tuples as the shape the engines read: {start,end,kind,text,href}.

    The offsets travel even though nothing compares them: they are the tiebreak that lets
    the engine place a mark when the run's text occurs more than once in its block."""
    return [[{'start': s_, 'end': e_, 'kind': k, 'text': t, 'href': h}
             for s_, e_, k, t, h in runs] for runs in marks]


# JS helpers shared by the full-document patcher below and by substack_sync's
# minimal push, so the two can never drift on typography, diffing or offsets.
JS_HELPERS = r"""  // Substack owns some blocks in its own document: a subscribe prompt it injects into
  // published posts, and its relatives. They carry text, they are NOT authored content, and
  // they exist in no draft.md — so counting them as body blocks makes a piece look
  // structurally divergent forever and shifts every index after the first one. `They/Them`
  // carried two subscribeWidgets (one after the opening beat, one at the tail) and so read as
  // live=85 vs draft=83, which the count guard could only report as "refusing to patch."
  // Anything unrecognized is deliberately NOT excluded: an unknown block changes the count and
  // surfaces as a structural refusal, which is the safe direction to be wrong in.
  const SUBSTACK_FURNITURE = new Set(['subscribeWidget', 'subscribeWithCaption', 'button',
    'paywall', 'latestPosts', 'embeddedPublication', 'share', 'poll', 'digestPostEmbed']);
  // Media nodes carry TEXT (a caption) but can never come from draft.md: a markdown image
  // renders to <figure><img alt=...> whose alt lives in an attribute, so render_reader's body
  // never contains it. Counting a captioned image as a body block therefore makes the live doc
  // permanently one block longer than its own draft — `Flow` read 34 against 33 and looked
  // structurally divergent when it was in sync, and every index after the image was shifted by
  // one, which is the condition under which a "surgical" patch writes into the wrong paragraph.
  const MEDIA = new Set(['captionedImage', 'image', 'video', 'nativeVideo', 'audio',
    'embeddedPost', 'tweet', 'youtube2']);
  const isBodyNode = n => n.type.name !== 'footnote'
    && !SUBSTACK_FURNITURE.has(n.type.name)
    && !MEDIA.has(n.type.name)
    && n.textContent.trim() !== '';

  const flat = s => s.replace(/[\u2018\u2019]/g, "'").replace(/[\u201c\u201d]/g, '"');

  // TWO normalizations, and keeping them apart is the point.
  //
  //   flat()     — quotes only. LENGTH-PRESERVING, so a char offset computed on it is a valid
  //                offset into the real text. Everything positional uses this.
  //   sameText() — flat() plus collapsed whitespace. NOT length-preserving, so it must never
  //                touch an offset. Used only to answer "is this block different?"
  //
  // A run of whitespace is not content: HTML collapses it, so `it.  The` and `it. The` render
  // identically and no reader can tell them apart. But `strip_to_reader` collapses runs on the
  // draft side, so a live post holding a double space describes a block NO DRAFT CAN EVER
  // PRODUCE — a difference that can never converge, reported on every future sync.
  //
  // `Both Ends of the Leash` (2026-09-01) is why this exists. Chasing exactly that phantom, a
  // one-space push was aimed between two adjacent footnote anchors and deleted one of them off
  // a live post. The edit was cosmetically invisible to readers; it was made only to quiet a
  // report. Comparing whitespace-insensitively means the report is quiet on its own and the
  // post never has to be touched.
  const sameText = s => flat(s).replace(/\s+/g, ' ').trim();
  const OPENS = new Set([...' \t\n(\u3010[{\u2014\u2013-\u201c\u2018']);
  const smarten = (s, prevCh) => {
    let out = '';
    for (let i = 0; i < s.length; i++) {
      const ch = s[i], prev = i ? s[i-1] : (prevCh || ' ');
      if (ch === '"') out += OPENS.has(prev) ? '\u201c' : '\u201d';
      else if (ch === "'") out += OPENS.has(prev) ? '\u2018' : '\u2019';
      else out += ch;
    }
    return out;
  };

  // minimal char-level diff of one block into hunks [{aStart,aEnd,text}], grouping each
  // contiguous run of edits between matched text into ONE hunk. Two separate edits in a
  // paragraph stay two hunks, so each is applied with its own marks — a casing flip inside
  // an italic run keeps the italic, a plain-text fix stays plain.
  const diffHunks = (a, b) => {
    if (a === b) return [];
    const n = a.length, m = b.length;
    let p = 0; while (p < n && p < m && a[p] === b[p]) p++;
    let s = 0; while (s < n - p && s < m - p && a[n-1-s] === b[m-1-s]) s++;
    const ac = a.slice(p, n - s), bc = b.slice(p, m - s);
    const A = ac.length, B = bc.length;
    // guard the DP: fall back to one span for pathologically large cores
    if (A * B > 4000000 || A > 60000 || B > 60000) return [{ aStart: p, aEnd: n - s, text: bc, big: true }];
    const dp = Array.from({ length: A + 1 }, () => new Uint16Array(B + 1));
    for (let i = A - 1; i >= 0; i--) for (let j = B - 1; j >= 0; j--)
      dp[i][j] = ac[i] === bc[j] ? dp[i+1][j+1] + 1 : Math.max(dp[i+1][j], dp[i][j+1]);
    const hunks = []; let i = 0, j = 0, ds = null, de = null, ins = '';
    const flush = () => { if (ds !== null || ins.length) hunks.push({ aStart: p + (ds !== null ? ds : i), aEnd: p + (de !== null ? de : i), text: ins }); ds = de = null; ins = ''; };
    while (i < A && j < B) {
      if (ac[i] === bc[j]) { flush(); i++; j++; }
      else if (dp[i+1][j] >= dp[i][j+1]) { if (ds === null) ds = i; de = i + 1; i++; }
      else { if (ds === null) { ds = i; de = i; } ins += bc[j]; j++; }
    }
    if (i < A) { if (ds === null) ds = i; de = A; }
    if (j < B) ins += bc.slice(j);
    flush();
    return hunks;
  };

  // map a character offset within a top node's textContent to an absolute doc position,
  // walking real text descendants so it is correct whether the node is a bare textblock
  // (paragraph/heading) or wraps a paragraph (footnote).
  const offsetToPos = (node, nodeStartPos, charOffset) => {
    // Map a char offset in the node's reader-text to a document position.
    //
    // The comparison is STRICT (`<`, not `<=`) and that is the whole point. An offset landing
    // exactly on a text-node boundary must resolve to the START OF THE NEXT TEXT RUN, not to
    // the end of the current one — because between two text runs there can be an inline node,
    // and the "end of the current run" is that node's position. With `<=`, a delete whose
    // boundary fell there removed the inline node instead of the character.
    //
    // Found the hard way on `Both Ends of the Leash` (2026-09-01): the paragraph reads
    // "...delivering it.[anchor 10] [anchor 11] The behavior...", and deleting one space
    // deleted footnote 11 off a LIVE post. Undo restored it; the public page never lost it.
    // Any inline node is exposed to this — a footnote anchor is simply the one this desk has.
    let acc = 0, out = null;
    node.descendants((child, relPos) => {
      if (out !== null) return false;
      if (child.isText) {
        const len = child.text.length;
        if (charOffset < acc + len) { out = nodeStartPos + 1 + relPos + (charOffset - acc); return false; }
        acc += len;
      }
      return true;
    });
    if (out === null) out = nodeStartPos + node.nodeSize - 1;   // offset at the very end
    return out;
  };

  // ---------------------------------------------------------------- marks
  // The layer reader-text cannot see. Everything above this line compares TEXT, and a
  // formatting-only edit -- wrapping a word already in the post in <em> -- changes none of
  // it. Measured on `rising-after-falls` 2026-09-09: after italicising two words the
  // regenerated patch was byte-identical in size to the previous one, the engine reported
  // `unchanged`, and it applied nothing. A no-op reported as success is the one failure
  // mode a re-sync tool must not have, so marks are scraped, planned and applied as their
  // own pass, after the text pass has finished.
  const MARKKIND = { em: 'em', italic: 'em', strong: 'strong', bold: 'strong', link: 'link' };
  const canonHref = h => { h = (h || '').trim(); return (h.endsWith('/') && (h.split('/').length - 1) > 3) ? h.slice(0, -1) : h; };

  // A RUN IS A SPAN OF FORMATTING, NOT AN ELEMENT. ProseMirror stores `**a _b_ c**` as
  // three text nodes each carrying the strong mark; the converter emits it as one <strong>
  // wrapping an <em>, and Substack serves it back as three <strong> elements. Compared
  // span-by-span those disagree on every bold-containing-an-italic in the corpus -- 8
  // pieces of 34 on the first sweep, 2026-09-09, not one of them a real difference. So
  // contiguous spans of the same kind (and, for a link, the same href) are merged before
  // anything is compared. Merge first, trim after: a span is contiguous with its neighbour
  // only while it still owns the space between them.
  // Shared by the PLAN (which asks whether a node's formatting changed) and by the final
  // report. They used to live only in the report; the plan referencing them from up here
  // crashed with "Cannot access 'runKeys' before initialization", because a const is not
  // hoisted for use. (2026-09-14, adding fnReplace.)
  const runKeys = runs => runs.map(r => r.kind + ' ' + sameText(r.text) + ' ' + (r.href || ''));
  const wantKeys = t => runKeys((t.marks || []).map(r => ({ kind: r.kind, text: r.text, href: r.href })));
  const marksOf = node => {
    const raw = []; let acc = 0;
    node.descendants(c => {
      if (!c.isText) return true;
      const len = c.text.length;
      for (const m of (c.marks || [])) {
        const kind = MARKKIND[m.type && m.type.name];
        if (!kind) continue;
        raw.push({ start: acc, end: acc + len, kind,
                   href: kind === 'link' ? canonHref(m.attrs && m.attrs.href) : '' });
      }
      acc += len;
      return true;
    });
    const text = flat(node.textContent);
    raw.sort((a, b) => (a.kind < b.kind ? -1 : a.kind > b.kind ? 1
                        : a.href < b.href ? -1 : a.href > b.href ? 1 : a.start - b.start));
    const merged = [];
    for (const r of raw) {
      const last = merged[merged.length - 1];
      if (last && last.kind === r.kind && last.href === r.href && r.start <= last.end) last.end = Math.max(last.end, r.end);
      else merged.push({ start: r.start, end: r.end, kind: r.kind, href: r.href });
    }
    const out = [];
    for (const r of merged) {
      let start = r.start, end = r.end;
      while (start < end && /\s/.test(text[start])) start++;
      while (end > start && /\s/.test(text[end - 1])) end--;
      // Two spans, and the difference matters. The TRIMMED one is the run's identity --
      // `<em>word </em>` and `<em>word</em>` are the same italic and must compare equal.
      // The RAW one is what the mark actually occupies, and it is what a removal has to
      // clear: strip only the trimmed range and the mark survives on the trailing space,
      // invisible to a reader and invisible to the next scan, but still in the document.
      if (end > start) out.push({ start, end, rawStart: r.start, rawEnd: r.end,
                                  kind: r.kind, href: r.href, text: text.slice(start, end) });
    }
    out.sort((a, b) => a.start - b.start || b.end - a.end || (a.kind < b.kind ? -1 : 1));
    return out;
  };

  // the EQUALITY domain for marks: kind, whitespace-collapsed text, href. Never offsets --
  // an offset says where a run is, not what it is, and a block whose text merely moved
  // would otherwise report drift that is not there.
  const markKey = r => r.kind + ' ' + sameText(r.text) + ' ' + (r.href || '');

  const lcsPairs = (A, B) => {
    const n = A.length, m = B.length;
    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
      dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const pairs = []; let i = 0, j = 0;
    while (i < n && j < m) { if (A[i] === B[j]) { pairs.push([i, j]); i++; j++; } else if (dp[i + 1][j] >= dp[i][j + 1]) i++; else j++; }
    return pairs;
  };

  // Plan one node's mark reconciliation. LINKS ARE NEVER PLANNED FOR APPLICATION: a link
  // mark carries Substack's own attributes, and guessing them onto a live public essay is
  // the class of blind write this engine refuses everywhere else. Link drift is REPORTED
  // so a human can see it; the structural engine restores a link the safe way, by
  // re-inserting the block from the converter's own HTML.
  const planMarks = (liveRuns, targetRuns) => {
    const add = [], remove = [], links = [];
    const paired = lcsPairs(liveRuns.map(markKey), targetRuns.map(markKey));
    const liveMatched = new Set(paired.map(p => p[0])), targetMatched = new Set(paired.map(p => p[1]));
    liveRuns.forEach((r, i) => { if (!liveMatched.has(i)) (r.kind === 'link' ? links : remove).push(r); });
    targetRuns.forEach((r, j) => { if (!targetMatched.has(j)) (r.kind === 'link' ? links : add).push(r); });
    return { add, remove, links };
  };

  // Where does a run the live doc lacks belong? By its TEXT, in the live doc's own
  // coordinates -- the draft's offsets are into COLLAPSED reader-text and cannot index a
  // live node that may hold a double space. The draft offset is used only to break a tie
  // between repeated occurrences, and an unbroken tie REFUSES rather than guessing which
  // "faith" in the paragraph was the one meant to go italic.
  const locateRun = (liveFlat, runText, hint, taken) => {
    const idxs = []; for (let i = liveFlat.indexOf(runText); i >= 0; i = liveFlat.indexOf(runText, i + 1)) idxs.push(i);
    const free = idxs.filter(x => !taken.some(t => x < t.end && x + runText.length > t.start));
    if (free.length === 1) return free[0];
    if (!free.length) return -1;
    const scored = free.map(x => ({ x, d: Math.abs(x - hint) })).sort((a, b) => a.d - b.d);
    return (scored.length > 1 && scored[0].d === scored[1].d) ? -1 : scored[0].x;
  };

  const markTypeFor = (schema, kind) =>
    (schema.marks && (schema.marks[kind] || schema.marks[{ em: 'italic', strong: 'bold', link: 'link' }[kind]])) || null;

  // Apply one node's plan. Every range is READ BACK AND ASSERTED to equal the exact string
  // the draft marks before a transaction is dispatched -- the same discipline the hand-made
  // edit used on 2026-09-09, and the only thing standing between "italicise satsang" and
  // "italicise whatever happens to sit at that offset".
  const applyMarksTo = (ed, rec, targetRuns, label, out) => {
    const liveRuns = marksOf(rec.node);
    const plan = planMarks(liveRuns, targetRuns);
    for (const r of plan.links)
      out.review.push({ where: label, kind: 'link', text: r.text.slice(0, 60), href: r.href || null,
                        why: 'link marks are not applied automatically -- recompose the block or fix it by hand' });
    if (!plan.add.length && !plan.remove.length) { out.unchanged++; return; }
    const liveFlat = flat(rec.node.textContent);
    const ops = [];
    for (const r of plan.remove)
      ops.push({ op: 'remove', kind: r.kind, start: r.rawStart, end: r.rawEnd,
                 text: liveFlat.slice(r.rawStart, r.rawEnd), label: r.text });
    for (const r of plan.add) {
      // occurrences already covered by a live run of the SAME kind are spoken for: that
      // italic is already there, and it is not the one the draft is asking for.
      const taken = liveRuns.filter(l => l.kind === r.kind).map(l => ({ start: l.start, end: l.end }));
      const at = locateRun(liveFlat, r.text, r.start, taken);
      if (at < 0) {
        out.review.push({ where: label, kind: r.kind, text: r.text.slice(0, 60),
                          why: 'the run text is absent from the live block, or repeated in it with no way to tell which occurrence is meant' });
        continue;
      }
      ops.push({ op: 'add', kind: r.kind, start: at, end: at + r.text.length, text: r.text });
    }
    ops.sort((a, b) => b.start - a.start);
    for (const o of ops) {
      try {
        const st = ed.state;
        const type = markTypeFor(st.schema, o.kind);
        if (!type) { out.review.push({ where: label, kind: o.kind, text: o.text.slice(0, 60), why: 'the editor schema has no mark of this kind' }); continue; }
        const from = offsetToPos(rec.node, rec.pos, o.start), to = offsetToPos(rec.node, rec.pos, o.end);
        const got = flat(st.doc.textBetween(from, to));
        if (got !== o.text) throw new Error(label + ': the range holds ' + JSON.stringify(got.slice(0, 40)) + ', not ' + JSON.stringify(o.text.slice(0, 40)));
        ed.view.dispatch(o.op === 'add' ? st.tr.addMark(from, to, type.create())
                                        : st.tr.removeMark(from, to, type));
        out.applied.push({ where: label, op: o.op, kind: o.kind, text: (o.label || o.text).slice(0, 60) });
      } catch (e) {
        out.failed.push(String(e));
      }
    }
  };"""

# The engine. Runs in the live post's editor. Stages edits only; never publishes.
REPATCH_JS = r"""(() => {
  const TITLE = %TITLE%, SUBTITLE = %SUBTITLE%, BODY = %BODY%, FNS = %FNS%;
  const BODYMARKS = %BODYMARKS%, FNMARKS = %FNMARKS%;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor found — open the live post at /publish/post/<id>' });
  const ed = root.editor;
%HELPERS%

  // --- title / subtitle: set only if changed (a no-op set would still dirty the doc) ---
  const setField = (sel, v) => {
    const el = document.querySelector(sel);
    if (!el || el.value === v) return false;
    const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  };
  const titleChanged = setField('textarea[placeholder="Title"]', TITLE);
  const subtitleChanged = setField('textarea[placeholder="Add a subtitle…"]', SUBTITLE);

  // --- scrape live: ordered top nodes, split body vs footnote, keep positions + node refs ---
  // Typography: Substack curls straight quotes as the body is pasted, so the live doc
  // and the draft's reader-text disagree on every quote mark. Compare FLATTENED text
  // (curly -> straight, a 1:1 substitution that preserves length, so offsets computed
  // on it are valid against the real doc), and SMARTEN anything actually inserted so
  // it matches the typography of the document it lands in.
  // (typography helpers come from JS_HELPERS)

  const liveBody = [], liveFns = [];
  ed.state.doc.forEach((node, pos) => {
    const raw = node.textContent;
    const rec = { pos, node, raw, text: flat(raw) };
    if (node.type.name === 'footnote') liveFns.push(rec);
    else if (isBodyNode(node)) liveBody.push(rec);
  });

  const report = {
    titleChanged, subtitleChanged, structural: false,
    bodyBlocks: { live: liveBody.length, target: BODY.length },
    footnotes: { live: liveFns.length, target: FNS.length },
    applied: [], unchanged: 0, footnoteChanges: [], failed: [], reviewMarks: [],
    marks: { applied: [], review: [], failed: [], unchanged: 0 }
  };

  // structural guard: counts must match 1:1, else this is a rewrite — refuse.
  if (liveBody.length !== BODY.length || liveFns.length !== FNS.length) {
    report.structural = true;
    report.note = 'block/footnote count differs — structural change, not a touch-up. Refusing to patch; use a full recompose or edit by hand.';
    return JSON.stringify(report);
  }

  // GUARD: a permutation preserves the count, so the count check above cannot see one.
  // Before 2026-09-01 that was the only structural check, and a piece whose footnotes
  // were emitted in label order against a live doc in reference order passed it 30 == 30
  // with all thirty mismatched — the re-sync would have overwritten every note of a live
  // essay with another note's text. If a target block's exact text lives at a DIFFERENT
  // live index, the two lists are misaligned, not edited: refuse and say so.
  const findReorder = (targets, live, kind) => {
    const at = new Map();
    live.forEach((l, i) => { if (!at.has(sameText(l.text))) at.set(sameText(l.text), i); });
    const out = [];
    for (let i = 0; i < targets.length; i++) {
      if (sameText(targets[i]) === sameText(live[i].text)) continue;
      const j = at.get(sameText(targets[i]));
      if (j !== undefined && j !== i) out.push({ kind, targetIdx: i, livesAtIdx: j });
    }
    return out;
  };
  // GUARD: and a pair that is neither equal nor plausibly the same node (a one-word fix
  // leaves a long block ~99% intact) means the lists are misaligned some other way.
  //
  // "Intact" is measured as the share of WORDS kept in order — an LCS over word tokens.
  // Common prefix + common suffix alone counted everything between the first and last edit
  // as changed, so two one-character fixes far apart scored like a rewrite: son-of-joseph's
  // [^almah], 2026-09-11, `almah -> ʿalmah near the start and again deep in a 573-char note,
  // scored 0.309 and a correct patch was refused. Words, not characters, because two
  // unrelated English passages share a long CHARACTER subsequence (spaces, "the", "of") and
  // a char-level ratio would wave a real misalignment through. The prefix+suffix ratio stays
  // as a floor so a one-word node with one character fixed still reads as the same node.
  const affixRatio = (a, b) => {
    let p = 0; while (p < a.length && p < b.length && a[p] === b[p]) p++;
    let q = 0; while (q < a.length - p && q < b.length - p && a[a.length-1-q] === b[b.length-1-q]) q++;
    return (p + q) / Math.max(a.length, b.length);
  };
  const wordLcs = (A, B) => {
    if (A.length * B.length > 4000000) return 0;          // too big to score: the floor decides
    let prev = new Int32Array(B.length + 1), cur = new Int32Array(B.length + 1);
    for (let i = 1; i <= A.length; i++) {
      for (let j = 1; j <= B.length; j++)
        cur[j] = A[i-1] === B[j-1] ? prev[j-1] + 1 : Math.max(prev[j], cur[j-1]);
      [prev, cur] = [cur, prev];
    }
    return prev[B.length];
  };
  const similarity = (a, b) => {
    a = sameText(a); b = sameText(b);
    if (!a.length && !b.length) return 1;
    const A = a ? a.split(' ') : [], B = b ? b.split(' ') : [];
    return Math.max(affixRatio(a, b), wordLcs(A, B) / Math.max(A.length, B.length));
  };
  const findSuspect = (targets, live, kind) => {
    const out = [];
    for (let i = 0; i < targets.length; i++) {
      if (sameText(targets[i]) === sameText(live[i].text)) continue;
      const sim = similarity(live[i].text, targets[i]);
      if (sim < 0.5) out.push({ kind, idx: i, similarity: +sim.toFixed(3),
                                live: live[i].text.slice(0, 90), target: targets[i].slice(0, 90) });
    }
    return out;
  };

  report.reordered = [...findReorder(BODY, liveBody, 'body'), ...findReorder(FNS, liveFns, 'footnote')];
  report.suspect   = [...findSuspect(BODY, liveBody, 'body'), ...findSuspect(FNS, liveFns, 'footnote')];
  if (report.reordered.length || report.suspect.length) {
    report.structural = true;
    report.note = report.reordered.length
      ? 'target text found at a DIFFERENT live index — the two lists are misaligned, not edited. Refusing to patch; nothing was changed.'
      : 'a changed pair is too dissimilar to be the same node — likely misalignment. Refusing to patch; nothing was changed.';
    return JSON.stringify(report);
  }

  // (diff + offset helpers come from JS_HELPERS)

  // one task per hunk, across body then footnotes
  const tasks = [];
  const plan = (targets, live, kind) => {
    for (let idx = 0; idx < targets.length; idx++) {
      if (sameText(targets[idx]) === sameText(live[idx].text)) { report.unchanged++; continue; }
      const hunks = diffHunks(live[idx].text, targets[idx]);
      if (!hunks.length) { report.unchanged++; continue; }
      for (const h of hunks) tasks.push({ kind, idx, node: live[idx].node, raw: live[idx].raw,
                                          nodePos: live[idx].pos, hunk: h });
    }
  };
  plan(BODY, liveBody, 'body');
  plan(FNS, liveFns, 'footnote');

  // apply latest-position-first (node then offset, both descending) so every not-yet-applied
  // position stays valid across edits.
  tasks.sort((a, b) => (b.nodePos - a.nodePos) || (b.hunk.aStart - a.hunk.aStart));
  for (const t of tasks) {
    try {
      const from = offsetToPos(t.node, t.nodePos, t.hunk.aStart);
      const to = offsetToPos(t.node, t.nodePos, t.hunk.aEnd);
      const state = ed.state;
      const marks = state.doc.resolve(from).marks();
      const endMarks = state.doc.resolve(Math.max(from, to)).marks();
      const uniform = marks.length === endMarks.length && marks.every(m => endMarks.some(e => e.eq(m)));
      let tr = state.tr;
      const prevCh = t.hunk.aStart > 0 ? t.raw[t.hunk.aStart - 1] : ' ';
      const insert = smarten(t.hunk.text, prevCh);
      if (insert.length) tr = tr.replaceWith(from, to, state.schema.text(insert, marks));
      else tr = tr.delete(from, to);
      ed.view.dispatch(tr);
      const entry = { kind: t.kind, block: t.idx, insert: insert || '(deleted)' };
      report.applied.push(entry);
      if (t.kind === 'footnote') report.footnoteChanges.push(entry);
      if (!uniform || t.hunk.big) report.reviewMarks.push(entry);
    } catch (e) {
      report.failed.push({ kind: t.kind, block: t.idx, error: String(e) });
    }
  }
  // --- marks, after the text is settled -----------------------------------------------
  // Runs last on purpose: a text hunk carries the marks of the run it replaces, so the
  // document has to have stopped moving before "which words are italic" can be answered.
  // `unchanged` above counts blocks whose TEXT did not change -- which is exactly the
  // number that used to be reported as a clean no-op while an italic was missing.
  const reMark = (targets, kind) => {
    const recs = []; ed.state.doc.forEach((node, pos) => {
      if (node.type.name === 'footnote') { if (kind === 'footnote') recs.push({ node, pos }); }
      else if (isBodyNode(node) && kind === 'body') recs.push({ node, pos });
    });
    if (recs.length !== targets.length) {
      report.marks.review.push({ where: kind, why: 'block count moved during the text pass -- marks not reconciled' });
      return;
    }
    recs.forEach((rec, i) => applyMarksTo(ed, rec, targets[i] || [], kind + ' ' + i, report.marks));
  };
  reMark(BODYMARKS, 'body');
  reMark(FNMARKS, 'footnote');

  report.stagedEdits = report.applied.length + report.marks.applied.length;
  return JSON.stringify(report);
})()
"""

def build_structural(piece_dir, man, body, fns, body_marks, fn_marks):
    """Bake the draft as a TARGET the structural engine can align against a live doc:
    per body block its reader-text, its HTML (quotes smartened outside tags), the names of
    the footnote anchors it carries, whether a divider precedes it, and a sha256/16 of the
    reader-text — the hash is computed HERE so that a snippet retyped into a browser eval
    fails closed on any transcription slip. Footnotes carry name, text and hash in
    first-reference order, which is the order the live doc holds them."""
    import re, hashlib
    from md_to_substack import parse_blocks, strip_to_reader, smarten_quotes
    blocks, ordered, *_rest = parse_blocks(piece_dir)
    H = lambda t: hashlib.sha256(flatten_quotes(re.sub(r'\s+', ' ', t).strip()).encode()).hexdigest()[:16]
    def smart(h):   # smarten the text, never the tags: a curled quote inside href="…" is a dead link
        return ''.join(x if x.startswith('<') else smarten_quotes(x) for x in re.split(r'(<[^>]+>)', h))
    tbody, hr_before = [], False
    for b in blocks:
        if b.strip() == '<hr>':
            hr_before = True
            continue
        txt = strip_to_reader(b)
        if not txt:
            continue
        tbody.append({'text': txt, 'html': smart(b), 'anchors': re.findall(r'\[\[FN(\w+)\]\]', b),
                      'hrBefore': hr_before, 'hash': H(txt),
                      'marks': jsonable([body_marks[len(tbody)]])[0]})
        hr_before = False
    if [t['text'] for t in tbody] != list(body):
        print("Refusing: the structural builder's block list does not match render_reader's — "
              "the two walk the draft differently; fix that before trusting either.")
        sys.exit(5)
    tfns = [{'name': str(n), 'text': t, 'hash': H(t), 'marks': jsonable([m])[0]}
            for (n, _c), t, m in zip(ordered, fns, fn_marks)]
    target = {'title': man.get('title', ''), 'subtitle': man.get('subtitle', ''),
              'body': tbody, 'fns': tfns}
    print(f"structural target: {len(tbody)} body block(s), {len(tfns)} footnote(s), "
          f"{sum(len(t['marks']) for t in tbody) + sum(len(t['marks']) for t in tfns)} marked run(s), "
          f"{sum(len(t['anchors']) for t in tbody)} anchor(s), "
          f"{sum(1 for t in tbody if '<a ' in t['html'])} block(s) with links")
    return (STRUCTURAL_JS.replace('%HELPERS%', JS_HELPERS)
                         .replace('%TARGET%', json.dumps(target, ensure_ascii=False)))


# The structural engine. Runs once in the live post's editor. Applies nothing on a refusal;
# stages edits only; never publishes. Returns a JSON report with `refused`, `applied`,
# `failed`, `final` and `ok`.
STRUCTURAL_JS = r"""(async () => {
  const TARGET = /*T*/%TARGET%/*T*/;
  const root = document.querySelector('.ProseMirror');
  if (!root || !root.editor) return JSON.stringify({ error: 'no editor found — open the live post at /publish/post/<id>' });
  const ed = root.editor;
%HELPERS%
  const sha = async s => {
    const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 16);
  };
  const T = TARGET;
  const report = { mode: 'structural', refused: null, ok: false, applied: [], failed: [],
                   titleChanged: false, subtitleChanged: false,
                   marks: { applied: [], review: [], failed: [], unchanged: 0 },
                   plan: { replace: 0, insert: 0, delete: 0, hunk: 0, fnHunk: 0, fnReplace: 0, dropAnchor: 0 } };
  const refuse = (why, extra) => { report.refused = why; Object.assign(report, extra || {}); return JSON.stringify(report); };

  // --- scrape the live doc: body nodes with their anchors (numbered in document order, which
  //     is the order the footnote nodes hold), footnote nodes, and whether a divider precedes
  //     each body node ---
  const scrape = () => {
    const body = [], fns = []; let seq = 0, hrBefore = false;
    ed.state.doc.forEach((node, pos) => {
      if (node.type.name === 'footnote') { fns.push({ node, pos, text: node.textContent }); return; }
      if (node.type.name === 'horizontalRule' || node.type.name === 'hr') { hrBefore = true; return; }
      if (!isBodyNode(node)) return;
      const anchors = [];
      node.descendants((c, rel) => { if (c.type.name === 'footnoteAnchor') anchors.push({ pos: pos + 1 + rel, size: c.nodeSize, seq: seq++ }); });
      body.push({ node, pos, text: node.textContent, anchors, hrBefore });
      hrBefore = false;
    });
    return { body, fns };
  };

  // --- 0. transcription guard: every block that will travel as HTML must hash to its own text ---
  for (let j = 0; j < T.body.length; j++) {
    const b = T.body[j];
    if (b.anchors.length) continue;                       // anchor blocks never travel as HTML
    if (b.html.includes('[[FN')) return refuse('html block ' + j + ' carries a footnote marker but declares no anchor', { block: j });
    const kids = [...new DOMParser().parseFromString(b.html, 'text/html').body.children];
    if (kids.length !== 1) return refuse('html block ' + j + ' parses to ' + kids.length + ' elements, not 1', { block: j });
    if (await sha(sameText(kids[0].textContent)) !== b.hash)
      return refuse('transcription: html block ' + j + ' does not hash to its own reader-text — the snippet was altered between the generator and this eval', { block: j });
  }

  // --- 1. align live body against target body by text (LCS on normalized block text) ---
  const live = scrape();
  const eqL = live.body.map(b => sameText(b.text)), eqT = T.body.map(b => sameText(b.text));
  const pairs = lcsPairs(eqL, eqT);                    // lcsPairs comes from JS_HELPERS
  const ranges = []; let pi = 0, pj = 0;
  for (const [i, j] of [...pairs, [live.body.length, T.body.length]]) {
    if (i > pi || j > pj) ranges.push({ i1: pi, i2: i, j1: pj, j2: j });
    pi = i + 1; pj = j + 1;
  }

  // --- 2. plan. Nothing is dispatched until every check below has passed. ---
  const ops = [], anchorPairs = [], dropAnchors = [];
  // equal blocks: the anchors must agree in count, or the draft has retired every one of them
  for (const [i, j] of pairs) {
    const la = live.body[i].anchors, ta = T.body[j].anchors;
    if (la.length === ta.length) la.forEach((a, k) => anchorPairs.push({ seq: a.seq, name: ta[k] }));
    else if (ta.length === 0) la.forEach(a => dropAnchors.push({ liveIdx: i, anchor: a }));
    else if (la.length === 0) return refuse('the draft adds footnote(s) to block ' + i + ' (' + ta.map(n => '[[FN' + n + ']]').join(' ') + ') that the live post lacks — insertFootnote is not automated here; add them by hand in the composer, or recompose', { liveIdx: i, targetIdx: j, added: ta });
    else return refuse('block ' + i + ' has ' + la.length + ' anchor(s) live and ' + ta.length + ' in the draft with identical text — cannot tell which to keep', { liveIdx: i, targetIdx: j });
  }
  // changed ranges: split at anchor-bearing blocks, which pair 1:1 by order and go by text hunk
  const emitReplace = (i1, i2, j1, j2) => {
    if (i1 === i2 && j1 === j2) return;
    ops.push({ kind: 'replace', i1, i2, j1, j2 });
    report.plan[i1 === i2 ? 'insert' : j1 === j2 ? 'delete' : 'replace']++;
  };
  for (const r of ranges) {
    const la = [], ta = [];
    for (let i = r.i1; i < r.i2; i++) if (live.body[i].anchors.length) la.push(i);
    for (let j = r.j1; j < r.j2; j++) if (T.body[j].anchors.length) ta.push(j);
    if (la.length !== ta.length)
      return refuse('anchor-bearing blocks do not pair 1:1 inside a changed range — un-merge or re-split the draft so each footnote-bearing paragraph has a live counterpart', { range: r, liveAnchorBlocks: la, targetAnchorBlocks: ta });
    let ci = r.i1, cj = r.j1;
    for (let k = 0; k < la.length; k++) {
      const i = la[k], j = ta[k];
      if (live.body[i].anchors.length !== T.body[j].anchors.length)
        return refuse('anchor count differs between paired blocks', { liveIdx: i, targetIdx: j });
      emitReplace(ci, i, cj, j);
      live.body[i].anchors.forEach((a, q) => anchorPairs.push({ seq: a.seq, name: T.body[j].anchors[q] }));
      if (eqL[i] !== eqT[j]) { ops.push({ kind: 'hunk', liveIdx: i, targetIdx: j }); report.plan.hunk++; }
      ci = i + 1; cj = j + 1;
    }
    emitReplace(ci, r.i2, cj, r.j2);
  }
  // footnotes follow their anchors
  const seqToName = new Map(anchorPairs.map(p => [p.seq, p.name]));
  const nameToTarget = new Map(T.fns.map((f, j) => [f.name, j]));
  const droppedSeqs = new Set(dropAnchors.map(d => d.anchor.seq));
  const totalLiveAnchors = anchorPairs.length + dropAnchors.length;
  if (live.fns.length !== totalLiveAnchors)
    return refuse('the live document has ' + live.fns.length + ' footnote node(s) but ' + totalLiveAnchors + ' anchor(s)', { footnotes: live.fns.length, anchors: totalLiveAnchors });
  const fnPairs = [];
  for (let k = 0; k < live.fns.length; k++) {
    if (droppedSeqs.has(k)) continue;
    const name = seqToName.get(k);
    const j = nameToTarget.get(name);
    if (j === undefined) return refuse('live footnote ' + k + ' pairs with anchor [[FN' + name + ']], which names no footnote in the draft', { fn: k, name });
    fnPairs.push({ k, j });
  }
  const covered = new Set(fnPairs.map(p => p.j));
  const added = T.fns.map((f, j) => j).filter(j => !covered.has(j)).map(j => T.fns[j].name);
  if (added.length) return refuse('the draft adds footnote(s) the live post lacks — insertFootnote is not automated here; add them by hand in the composer, or recompose', { added });
  for (let a = 1; a < fnPairs.length; a++) if (fnPairs[a].j <= fnPairs[a - 1].j)
    return refuse('footnote order differs between the draft and the live post', { fnPairs });
  // A FOOTNOTE WHOSE FORMATTING CHANGED IS REPLACED WHOLE, not hunked.
  //
  // A text hunk can only rewrite a run of uniform marks, so a footnote re-quoted from a
  // different source — new italics in new places — fails with "a hunk crosses a formatting
  // boundary" and the whole run aborts with nothing applied. Measured 2026-09-14 on
  // krishna-is-not-christ [^11], whose Gita quotation was replaced with Arnold's: the
  // surgical engine refused it as too dissimilar (0.143) and this one could not express it.
  //
  // Replacing a footnote's CONTENT whole is as safe as replacing a body block — safer, in
  // fact: the anchors live in the BODY, so a footnote node contains no inline node that a
  // replacement could destroy, which is the hazard the anchor-bearing rule exists for. The
  // content comes from the converter's own HTML, so it arrives with its marks already on it.
  for (const p of fnPairs) {
    const textDiffers = sameText(live.fns[p.k].text) !== sameText(T.fns[p.j].text);
    if (!textDiffers) continue;
    const liveRuns = JSON.stringify(runKeys(marksOf(live.fns[p.k].node)));
    const wantRuns = JSON.stringify(wantKeys(T.fns[p.j]));
    if (liveRuns !== wantRuns) {
      // A LINK IS THE ONE MARK THIS CANNOT PUT BACK. fnReplace lands plain text and lets
      // the marks pass dress it, and that pass reports link marks rather than applying
      // them — a link carries Substack's own attributes. So a footnote whose formatting
      // changed AND which carries a link would come out with its link silently gone from
      // a live post. Refuse instead, and say what to do. (Measured 2026-09-14 on flow
      // [^cohort] and the-distance-that-love-needs [^2], whose only mark is a link.)
      if ((T.fns[p.j].marks || []).some(m => m.kind === 'link'))
        return refuse('footnote ' + p.k + ' changed its formatting and carries a link — '
                    + 'replacing it would drop the link, and a link mark cannot be reapplied '
                    + 'automatically. Edit this footnote by hand in the composer, or make the '
                    + 'change small enough that its marked runs are unchanged.',
                      { footnote: p.k, name: T.fns[p.j].name });
      ops.push({ kind: 'fnReplace', k: p.k, j: p.j }); report.plan.fnReplace++;
    }
    else { ops.push({ kind: 'fnHunk', k: p.k, j: p.j }); report.plan.fnHunk++; }
  }
  for (const d of dropAnchors) { ops.push({ kind: 'dropAnchor', liveIdx: d.liveIdx, seq: d.anchor.seq }); report.plan.dropAnchor++; }

  // --- 3. apply, latest document position first, re-reading the doc before every op ---
  const keyOf = o => (o.kind === 'fnHunk' || o.kind === 'fnReplace') ? 1e6 + o.k
                   : o.kind === 'replace' ? (o.i1 === o.i2 ? o.i1 - 0.5 : o.i1) : o.liveIdx;
  ops.sort((a, b) => keyOf(b) - keyOf(a));
  const hunkNode = (rec, targetText, label) => {
    const hunks = diffHunks(flat(rec.text), targetText).sort((a, b) => b.aStart - a.aStart);
    for (const h of hunks) {
      const from = offsetToPos(rec.node, rec.pos, h.aStart), to = offsetToPos(rec.node, rec.pos, h.aEnd);
      const st = ed.state;
      let inl = 0; st.doc.nodesBetween(from, to, n => { if (!n.isText && n.isInline) inl++; });
      if (inl) throw new Error(label + ': a hunk spans an inline node (a footnote anchor) — refusing to edit across it');
      if (flat(st.doc.textBetween(from, to)) !== flat(rec.text).slice(h.aStart, h.aEnd)) throw new Error(label + ': position guard failed');
      const marks = st.doc.resolve(from).marks(), endMarks = st.doc.resolve(Math.max(from, to)).marks();
      const uniform = marks.length === endMarks.length && marks.every(m => endMarks.some(e => e.eq(m)));
      if (!uniform) throw new Error(label + ': a hunk crosses a formatting boundary — split the change so each run is uniform');
      const ins = smarten(h.text, h.aStart > 0 ? rec.text[h.aStart - 1] : ' ');
      ed.view.dispatch(ins.length ? st.tr.replaceWith(from, to, st.schema.text(ins, marks)) : st.tr.delete(from, to));
    }
  };
  const endOf = r => r.pos + r.node.nodeSize;
  try {
    for (const o of ops) {
      const L = scrape();
      if (o.kind === 'fnHunk') {
        hunkNode(L.fns[o.k], T.fns[o.j].text, 'footnote ' + o.k);
        if (await sha(sameText(scrape().fns[o.k].text)) !== T.fns[o.j].hash) throw new Error('footnote ' + o.k + ' did not land as the draft has it');
        report.applied.push({ kind: 'fnHunk', footnote: o.k });
      } else if (o.kind === 'fnReplace') {
        // Replace the footnote's CONTENT as ONE UNMARKED RUN, never the footnote node:
        // deleting the node would orphan its anchor in the body and renumber every note
        // after it. Plain text, because the formatting is then put on by step 3b — the
        // same marks pass that already dresses every hunk-edited node, which is where a
        // footnote's marks have always come from. Nothing new has to understand HTML, and
        // the insert is one uniform run, so it cannot cross a formatting boundary.
        const rec = L.fns[o.k];
        const inner = rec.pos + 1, innerEnd = rec.pos + rec.node.nodeSize - 1;
        let inl = 0; ed.state.doc.nodesBetween(inner, innerEnd, n => { if (!n.isText && n.isInline) inl++; });
        if (inl) throw new Error('footnote ' + o.k + ': carries an inline node — refusing to replace it whole');
        const txt = smarten(T.fns[o.j].text, ' ');
        ed.view.dispatch(ed.state.tr.replaceWith(inner, innerEnd, ed.state.schema.text(txt, [])));
        const after = scrape();
        if (after.fns.length !== L.fns.length) throw new Error('footnote count changed while replacing footnote ' + o.k);
        if (await sha(sameText(after.fns[o.k].text)) !== T.fns[o.j].hash) throw new Error('footnote ' + o.k + ' did not land as the draft has it');
        report.applied.push({ kind: 'fnReplace', footnote: o.k });
      } else if (o.kind === 'hunk') {
        hunkNode(L.body[o.liveIdx], T.body[o.targetIdx].text, 'block ' + o.liveIdx);
        if (await sha(sameText(scrape().body[o.liveIdx].text)) !== T.body[o.targetIdx].hash) throw new Error('block ' + o.liveIdx + ' did not land as the draft has it');
        report.applied.push({ kind: 'hunk', block: o.liveIdx });
      } else if (o.kind === 'dropAnchor') {
        const rec = L.body[o.liveIdx]; const a = rec.anchors.find(x => x.seq === o.seq);
        if (!a) throw new Error('anchor ' + o.seq + ' not found in block ' + o.liveIdx);
        ed.view.dispatch(ed.state.tr.delete(a.pos, a.pos + a.size));
        const after = scrape();
        if (sameText(after.body[o.liveIdx].text) !== sameText(rec.text)) throw new Error('block ' + o.liveIdx + ' changed text when its anchor was dropped');
        if (after.fns.length === L.fns.length) {          // the editor did not remove the orphan itself
          const F = after.fns[o.seq];
          if (sameText(F.text) !== sameText(L.fns[o.seq].text)) throw new Error('orphaned footnote ' + o.seq + ' is not where it was');
          ed.view.dispatch(ed.state.tr.delete(F.pos, F.pos + F.node.nodeSize));
        }
        report.applied.push({ kind: 'dropAnchor', block: o.liveIdx, footnote: o.seq });
      } else {
        const html = T.body.slice(o.j1, o.j2).map(b => b.html).join('');
        let from, to;
        if (o.i1 < o.i2) { from = L.body[o.i1].pos; to = endOf(L.body[o.i2 - 1]); }
        else if (o.i1 >= L.body.length) { from = to = L.body.length ? endOf(L.body[L.body.length - 1]) : 0; }
        // an insert lands on the draft's side of any divider: after the divider if the draft
        // puts one before the new block, otherwise right after the preceding block
        else if (T.body[o.j1].hrBefore || o.i1 === 0) { from = to = L.body[o.i1].pos; }
        else { from = to = endOf(L.body[o.i1 - 1]); }
        if (o.j1 === o.j2) ed.view.dispatch(ed.state.tr.delete(from, to));
        else ed.commands.insertContentAt({ from, to }, html);
        const after = scrape();
        for (let q = 0; q < o.j2 - o.j1; q++)
          if (await sha(sameText(after.body[o.i1 + q].text)) !== T.body[o.j1 + q].hash) throw new Error('replaced block ' + (o.i1 + q) + ' did not land as the draft has it');
        report.applied.push({ kind: o.i1 === o.i2 ? 'insert' : o.j1 === o.j2 ? 'delete' : 'replace', at: o.i1, blocks: o.j2 - o.j1 });
      }
    }
  } catch (e) {
    report.failed.push(String(e));
    // A FAILURE IS NOT A REFUSAL, and `applied: []` does not mean the document is clean.
    // hunkNode dispatches its hunks one at a time, so a throw on the last of them leaves the
    // earlier ones in the document — and the op that threw never reaches report.applied, so
    // the report looked untouched while the live post had been half-edited. Measured
    // 2026-09-14 on krishna-is-not-christ, whose footnote 10 was partly rewritten by a run
    // that reported applying nothing. `refused` still means nothing was touched; `partial`
    // says the opposite out loud, and `final` says exactly what stands.
    report.partial = true;
  }

  // --- 3b. marks, once the blocks have stopped moving ---
  // A block replaced whole came in as the converter's own HTML and already carries its
  // marks; running the reconciliation over it anyway is free and turns into a second,
  // independent check that the HTML landed with its formatting intact. A block edited by
  // text hunk did NOT get its marks from anywhere, and this is the only pass that gives
  // them to it.
  if (!report.failed.length) {
    const M = scrape();
    if (M.body.length === T.body.length && M.fns.length === T.fns.length) {
      M.body.forEach((rec, i) => applyMarksTo(ed, rec, T.body[i].marks || [], 'block ' + i, report.marks));
      M.fns.forEach((rec, k) => applyMarksTo(ed, rec, T.fns[k].marks || [], 'footnote ' + k, report.marks));
    } else {
      report.marks.review.push({ where: 'document', why: 'block or footnote count still differs after the text pass -- marks not reconciled' });
    }
  }

  // --- 4. title / subtitle, only if changed ---
  const setField = (sel, v) => {
    const el = document.querySelector(sel);
    if (!el || el.value === v) return false;
    const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  };
  report.titleChanged = setField('textarea[placeholder="Title"]', T.title);
  report.subtitleChanged = setField('textarea[placeholder="Add a subtitle…"]', T.subtitle);

  // --- 5. read the whole document back; the report is evidence, not a claim ---
  const F = scrape();
  const bodyMismatch = []; for (let i = 0; i < Math.max(F.body.length, T.body.length); i++) if (!F.body[i] || !T.body[i] || sameText(F.body[i].text) !== eqT[i]) bodyMismatch.push(i);
  const fnMismatch = []; for (let k = 0; k < Math.max(F.fns.length, T.fns.length); k++) if (!F.fns[k] || !T.fns[k] || sameText(F.fns[k].text) !== sameText(T.fns[k].text)) fnMismatch.push(k);
  const anchors = F.body.reduce((n, b) => n + b.anchors.length, 0), wantAnchors = T.body.reduce((n, b) => n + b.anchors.length, 0);
  // Read the marks back too. The block digest cannot see them, so without this the final
  // report would certify a document it had only half looked at.
  const markMismatch = [];
  F.body.forEach((b, i) => { if (T.body[i] && JSON.stringify(runKeys(marksOf(b.node))) !== JSON.stringify(wantKeys(T.body[i]))) markMismatch.push('block ' + i); });
  F.fns.forEach((f, k) => { if (T.fns[k] && JSON.stringify(runKeys(marksOf(f.node))) !== JSON.stringify(wantKeys(T.fns[k]))) markMismatch.push('footnote ' + k); });
  const linksMissing = [], dividersOff = [];
  F.body.forEach((b, i) => {
    const t = T.body[i]; if (!t) return;
    if ((t.html.match(/<a /g) || []).length) { let n = 0; b.node.descendants(c => { if (c.isText && c.marks && c.marks.some(m => m.type.name === 'link')) n++; }); if (!n) linksMissing.push(i); }
    if (!!b.hrBefore !== !!t.hrBefore) dividersOff.push(i);
  });
  report.final = { body: F.body.length + '/' + T.body.length, footnotes: F.fns.length + '/' + T.fns.length,
                   anchors: anchors + '/' + wantAnchors, bodyMismatch, fnMismatch, markMismatch, linksMissing, dividersOff,
                   firstNode: ed.state.doc.firstChild ? ed.state.doc.firstChild.type.name : null };
  report.ok = !report.failed.length && !report.marks.failed.length && !bodyMismatch.length
              && !fnMismatch.length && !markMismatch.length && anchors === wantAnchors && !linksMissing.length;
  return JSON.stringify(report);
})()
"""


if __name__ == '__main__':
    main()
