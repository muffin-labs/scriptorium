#!/usr/bin/env python3
"""substack_verify.py — does the repo match what readers actually see?

The regression suite proves a draft matches its SEALED BASELINE. That is a claim about
this repository and nothing else: a baseline is a local file, and a piece can match its
baseline perfectly while the live post says something different — because someone edited
on Substack, because an "Update" was never clicked, or because a push half-landed.

This tool closes that gap from the reader's side. It fetches the PUBLIC page over plain
HTTP — no browser, no credentials, the same bytes a reader gets — pulls the post out of
the `window._preloads` blob the page ships, renders the local draft, and compares them
block for block and footnote for footnote.

It compares TWO domains, and the second one exists because the first was blind. Reader-text
(tags stripped) is what every digest on this desk has ever compared -- and wrapping a word
that is already in the post in <em> changes none of it. Measured on `rising-after-falls`
2026-09-09: after italicising two words, the regenerated surgical patch was byte-identical in
size to the previous one, the patcher reported `unchanged`, and a digest check would have
said MATCH with the italic absent from the live post. So the marked RUNS -- em, strong, and
link with its href -- are enumerated from both sides and compared for count, string and
order, and formatting drift is reported as DRIFT-MARKS, distinct from text drift, because
the fix for it is different.

The THIRD domain is where each footnote is CITED, and it exists because the first two were
blind to it too. Reader-text drops the superscript digit; the mark scan does not count it as
a mark. So a footnote attached to the wrong sentence produced no diff at all — measured
2026-09-11 on `for-the-love-of-dogs`, live since 2026-08-05 with footnote 1 anchored two
paragraphs away from where the draft cites it, reported MATCH on every run. The ordered
(number, preceding-words) of each block's anchors is therefore compared on both sides, and
that drift is reported as DRIFT-ANCHORS — a third name, because a moved superscript is
fixed in the editor rather than by repatching text or restoring an italic.

It is deliberately NOT part of test_suite.py. That suite promises no network calls, and
that promise is worth more than the convenience of one runner.

    python3 substack_verify.py                # every published piece
    python3 substack_verify.py pieces/lord-lord
    python3 substack_verify.py --fresh        # bypass the CDN cache (use after an Update)
    python3 substack_verify.py --archive      # the reader's list: every live post has a
                                              # title + subtitle and the desk knows it
    python3 substack_verify.py --archive --outlet substack-muffinlabs   # the other publication

A PIECE IS FOUND BY ITS OWN OUTLET'S KEY. Each outlet declares the manifest field its reader
URL is written under (`manifest_url_key`, outlets.yaml), because each outlet has its own. This
tool read `public_url` — one outlet's key — at every site, so a desk's second Substack
publication was invisible to it: skipped, and skipped with the wrong reason, "composed but not
published", about a post that had been live for a day (2026-09-11, `love-is-not-a-metric-space`).
An --archive walk belongs to ONE publication and now says which rather than deriving it from
whichever manifest came first.

WITHOUT --fresh THIS TOOL CAN REPORT DRIFT THAT DOES NOT EXIST, and it did on 2026-09-03: a
sweep of 26 pieces returned three DRIFTED, and all three came back MATCH the moment the same
pieces were re-checked cache-busted. The CDN was serving pages older than the posts. A false
DRIFT is worse than a false MATCH here, because the obvious response to drift is to push the
draft over the live post — repairing something that was never broken, and overwriting whatever
the cached copy was too old to show. PREFER --fresh, and never act on a cached DRIFT.

Exit: 0 all checked pieces match | 1 drift | 2 nothing could be checked.

Reaching zero pieces is a FAILURE, not a pass. A run that checked nothing must never be
able to report success — that is the whole failure mode this tool exists to catch.
"""
import sys, os, re, json, time, argparse, subprocess, urllib.request, urllib.error
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from md_to_substack import (render_captions, read_manifest, render_reader, render_marks,   # noqa: E402
                            render_anchors, anchor_tail, MarkRuns, mark_keys)
from substack_sync import H                                      # noqa: E402
import substack_account as sa                                    # noqa: E402

UA = 'writing-desk-verify/1.0 (+repo consistency check)'
TIMEOUT = 15          # per request; a page that takes longer is not going to arrive
ATTEMPTS = 2
BUDGET = 300          # whole-run ceiling, seconds

VOID  = {'img','br','hr','input','source','meta','link','col','area','base','wbr','embed','track'}
BLOCK = {'p','h1','h2','h3','h4','h5','h6','blockquote','ul','ol','pre'}
SKIP_TAG   = {'figure','svg','button','style','script','picture','video','audio','noscript'}
SKIP_CLASS = {'captioned-image-container','subscribe-widget','button-wrapper','poll',
              'embedded-post-wrap','embedded-post','paywall','digest-post-embed',
              'tweet','native-video-embed','footnote-number','pullquote','image-link',
              'subscription-widget-wrap','subscription-widget-wrap-editor',
              'subscription-widget','share-dialog','comments-section'}


class Extract(HTMLParser):
    """body_html -> the (body, footnotes) shape render_reader produces for a draft."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body, self.fns = [], []
        self.body_marks, self.fn_marks = [], []
        self.body_anchors, self.fn_anchors = [], []
        self.body_norm, self.fn_norm = [], []     # reader-text the anchor offsets index
        self.depth = 0
        self.skip_to = self.fn_to = self.cap_to = self.anchor_to = None
        self.anchor_buf = None
        self.buf = self.buf_depth = self.buf_tag = None
        self.marks = MarkRuns()          # the second domain: which words are marked

    def _enter(self, tag, attrs):
        cls = set(dict(attrs).get('class', '').split())
        if self.skip_to is not None:
            return
        if 'footnote-anchor' in cls:                 # superscript marker: drop its text
            # ...but not its POSITION. The digit is not reader-text; which sentence it
            # follows is the third comparison domain (see MarkRuns.anchor).
            self.anchor_to = self.depth; self.anchor_buf = []; return
        if 'footnote-content' in cls:
            self.cap_to = self.depth; self.buf = []; self.buf_depth = None
            self.marks = MarkRuns(); return
        if 'footnote' in cls:
            self.fn_to = self.depth; return
        if tag in SKIP_TAG or (cls & SKIP_CLASS):
            self.skip_to = self.depth; return
        # Marks are collected only inside an OPEN block, and only after every skip above
        # has had its say -- which is what keeps the two <a> tags that are not links out of
        # the link list: `footnote-anchor` returned above, `footnote-number` and
        # `image-link` are SKIP_CLASS. A footnote superscript counted as a link would put a
        # phantom run in every footnoted block of every piece.
        if self.buf is not None:
            self.marks.enter(tag, attrs)
        if self.cap_to is not None or self.fn_to is not None:
            return
        if tag in BLOCK and self.buf is None:
            # Only the OUTERMOST block opens a buffer. Substack nests prose as
            # <li><p>..</p></li> and <blockquote><p>..</p></blockquote>; letting an
            # inner </p> close the buffer splits one block into several and reports
            # drift that is not there.
            self.buf, self.buf_depth, self.buf_tag = [], self.depth, tag

    def _leave(self, tag):
        if self.skip_to is not None:
            if self.depth == self.skip_to: self.skip_to = None
            return
        if self.anchor_to is not None and self.depth == self.anchor_to:
            self.anchor_to = None
            if self.buf is not None:
                self.marks.anchor(''.join(self.anchor_buf or []))
            self.anchor_buf = None
            return
        if self.cap_to is not None:
            if self.depth == self.cap_to:
                self.cap_to = None
                runs, txt, anchors = self.marks.take()
                self.fns.append(''.join(self.buf or [])); self.fn_marks.append(runs)
                self.fn_anchors.append(anchors); self.fn_norm.append(txt)
                self.buf = None
            elif self.buf is not None:
                self.marks.leave(tag)
            return
        if self.fn_to is not None:
            if self.depth == self.fn_to: self.fn_to = None
            return
        if self.buf is not None:
            self.marks.leave(tag)
        if tag in BLOCK and self.buf is not None and self.depth == self.buf_depth:
            t = ''.join(self.buf)
            runs, txt, anchors = self.marks.take()
            if t.strip():
                self.body.append((self.buf_tag, t)); self.body_marks.append(runs)
                self.body_anchors.append(anchors); self.body_norm.append(txt)
            self.buf = self.buf_depth = self.buf_tag = None

    def handle_starttag(self, tag, attrs):
        if tag in VOID: return
        self._enter(tag, attrs); self.depth += 1

    def handle_startendtag(self, tag, attrs):
        pass                                          # self-closing: no subtree, no text

    def handle_endtag(self, tag):
        if tag in VOID: return
        self.depth -= 1; self._leave(tag)

    def handle_data(self, d):
        if self.skip_to is not None: return
        if self.anchor_to is not None:
            # The superscript's own digit: kept only long enough to say WHICH footnote
            # this anchor is, then dropped before it can reach the prose.
            if self.anchor_buf is not None: self.anchor_buf.append(d)
            return
        if self.buf is not None: self.buf.append(d); self.marks.data(d)


def live_blocks(body_html):
    """(body_texts, footnotes, body_marks, fn_marks, body_anchors, fn_anchors) as the
    reader gets them.

    Three domains, one parse. The texts are what every digest on this desk compares; the
    marks are the layer those digests cannot see (see MarkRuns in md_to_substack); the
    anchors are the layer neither of them sees — WHICH sentence carries each footnote.
    Anchors come back in `render_anchors`' shape, (number, tail), so the two sides are
    directly comparable."""
    p = Extract(); p.feed(body_html); p.close()
    # The draft renderer merges adjacent blockquotes; Substack keeps them separate.
    # The marks merge with them: order is preserved by concatenation, which is all the
    # equality domain uses (offsets are never compared).
    out, marks, anchors, norms = [], [], [], []
    for (tag, text), runs, anch, norm in zip(p.body, p.body_marks, p.body_anchors, p.body_norm):
        if tag == 'blockquote' and out and out[-1][0] == 'blockquote':
            out[-1] = (tag, out[-1][1] + text)
            marks[-1] = marks[-1] + runs
            # ANCHOR OFFSETS *ARE* COMPARED, unlike the marks', so a merged block's anchors
            # have to move with the text that is now in front of them. The shift is the
            # reader-text length of the block they were merged into, which is exactly the
            # normalization the draft's own merged block produces.
            anchors[-1] = anchors[-1] + [(pos + len(norms[-1]), lab) for pos, lab in anch]
            norms[-1] = norms[-1] + norm
        else:
            out.append((tag, text)); marks.append(runs)
            anchors.append(list(anch)); norms.append(norm)
    return ([t for _, t in out], p.fns, marks, p.fn_marks,
            [_anchor_entries(a, n) for a, n in zip(anchors, norms)],
            [_anchor_entries(a, n) for a, n in zip(p.fn_anchors, p.fn_norm)])


def _anchor_entries(anchors, norm_text):
    """Raw (pos, label) anchors as the (number, tail) pairs render_anchors produces."""
    return [(int(lab) if lab.isdigit() else 0, anchor_tail(norm_text, pos))
            for pos, lab in anchors]


class _Captions(HTMLParser):
    """Each <figure>'s <figcaption> text, in order; '' for a figure with none."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.caps, self.fig, self.incap = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag == 'figure':
            self.fig += 1
            self.caps.append('')
        elif tag == 'figcaption' and self.fig:
            self.incap += 1

    def handle_endtag(self, tag):
        if tag == 'figcaption' and self.incap:
            self.incap -= 1
        elif tag == 'figure' and self.fig:
            self.fig -= 1

    def handle_data(self, d):
        if self.incap and self.caps:
            self.caps[-1] += d


def live_captions(body_html):
    """The live post's image captions, in order. Figures are SKIP_TAG to the body parse, so
    before this a caption on the live post -- right, wrong, or hand-set -- was invisible to
    every check on this desk (2026-09-11)."""
    p = _Captions(); p.feed(body_html); p.close()
    return [re.sub(r'\s+', ' ', c).strip() for c in p.caps]


def caption_drift(live, want):
    """Differences between the live captions and the desk's, by position. A live caption the
    desk does not hold is reported too: invisible is exactly what it used to be."""
    if not any(want) and not any(live):
        return []
    if len(live) != len(want):
        return [f'figures {len(live)} live vs {len(want)} draft; captions not aligned']
    return [f'caption #{i + 1}: live {a[:60]!r} vs desk {b[:60]!r}'
            for i, (a, b) in enumerate(zip(live, want)) if H(a) != H(b)]


def fetch_public(url, fresh=False, attempts=ATTEMPTS):
    if fresh:
        url += ('&' if '?' in url else '?') + f'_cb={int(time.time())}'
    headers = {'User-Agent': UA}
    if fresh:
        headers['Cache-Control'] = 'no-cache'
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            # An HTTP status is a definitive answer from the server. Retrying a 403 or
            # a 404 just spends time to be told the same thing again.
            raise
        except Exception as e:                                    # noqa: BLE001
            last = e
            if i + 1 < attempts:
                time.sleep(2 * (i + 1))
    raise last


def extract_post(page_html):
    m = re.search(r'window\._preloads\s*=\s*JSON\.parse\((".*?")\)\s*;?\s*</script>',
                  page_html, re.S)
    if not m:
        return None
    return json.loads(json.loads(m.group(1))).get('post')


def pieces_touched_by(repo, rev_range):
    """Piece slugs whose directory a commit range touched.

    Scoping the check to what changed is the difference between a verifier you run and
    one you mean to run: the full sweep is 23 network round-trips, and most commits
    touch one piece.

    An empty range is NOT an error and NOT a silent pass -- the caller reports that
    nothing published was touched, so "no pieces to check" can never be mistaken for
    "everything matches".
    """
    try:
        out = subprocess.run(['git', '-C', repo, 'diff', '--name-only', rev_range],
                             capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None, out.stderr.strip().splitlines()[-1] if out.stderr else 'git failed'
    except Exception as e:                                        # noqa: BLE001
        return None, f'{type(e).__name__}: {e}'
    slugs = []
    for path in out.stdout.splitlines():
        parts = path.split('/')
        if len(parts) >= 2 and parts[0] == 'pieces' and parts[1] not in slugs:
            slugs.append(parts[1])
    return slugs, None


DEFAULT_URL_KEY = 'public_url'


def outlet_of(piece_dir):
    """-> (outlet name, spec) for the piece's Substack outlet, or (None, {}) when nothing settles
    it. Never raises: this tool reads public pages, and a piece it cannot place is one it reports
    rather than one it crashes on."""
    try:
        return sa.substack_outlet_for_piece(piece_dir)
    except Exception:                                             # noqa: BLE001 — see docstring
        return None, {}


def live_url(piece_dir, man=None):
    """-> (url, outlet, key): where a reader finds this piece, by ITS OWN outlet's manifest key.

    EVERY OUTLET GETS ITS OWN MANIFEST KEY — outlets.yaml says so, and `manifest_url_key` is where
    it says it. This tool did not know that. It read `public_url` at four sites, which is one
    publication's key (`substack`, Being Good), so every post on the second Substack outlet
    (`substack-muffinlabs`, whose key is `substack_url`) was skipped — and skipped with the wrong
    reason, "composed but not published", about a post that had been live for a day. Measured
    2026-09-11 on `love-is-not-a-metric-space`, whose manifest had written the problem down in a
    comment: *substack_notes.py cannot see a MuffinLabs post yet (it reads public_url)*. Three more
    MuffinLabs pieces already declare the outlet and would have landed in the same hole.

    A desk with no registry — a fresh instance, a test fixture — keeps the old key as the default,
    because `public_url` is what a one-outlet desk has always written."""
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml')) if man is None else man
    outlet, spec = outlet_of(piece_dir)
    key = (spec or {}).get('manifest_url_key') or DEFAULT_URL_KEY
    return man.get(key, ''), outlet, key


def resolve_piece(repo, arg):
    """Resolve a piece argument to a directory, and say WHY when it cannot.

    Accepts either a path (`pieces/not-yet`) or a bare slug (`not-yet`), because the rest of the
    desk's tooling is addressed by slug and there is no reason this one should differ.

    Returns `(dir, url, reason)`. Exactly one of `url` / `reason` is set.

    The reason strings matter more than the convenience. Before this existed, every failure
    printed "no public_url — not published": a typo'd slug, a piece that was never composed, and
    a genuinely unpublished piece were indistinguishable. On 2026-09-02 that cost a real
    diagnosis — `substack_verify --fresh forking-paths` reported a freshly published essay as not
    published, because the bare slug resolved to a directory that does not exist and an absent
    file reads as an empty manifest. A message that names the wrong cause is worse than no
    message, because it is believed.
    """
    arg = arg.rstrip('/')
    d = arg if os.path.isdir(arg) else None
    if d is None:
        cand = os.path.join(repo, 'pieces', os.path.basename(arg))
        d = cand if os.path.isdir(cand) else None
    if d is None:
        return (arg, None, f"no such piece — tried ./{arg}/ and pieces/{os.path.basename(arg)}/")
    man = os.path.join(d, 'publish.yaml')
    if not os.path.isfile(man):
        return (d, None, "no publish.yaml — never composed to Substack")
    url, _outlet, key = live_url(d)
    if not url:
        return (d, None, f"no {key} in publish.yaml — composed but not published")
    return (d, url, None)


def published_pieces(repo, only=None):
    out = []
    pieces = os.path.join(repo, 'pieces')
    if not os.path.isdir(pieces):
        return out
    for name in sorted(os.listdir(pieces)):
        if only is not None and name not in only:
            continue
        d = os.path.join(pieces, name)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        url, _outlet, _key = live_url(d)
        if not url or '.invalid' in url:          # fixtures are not reachable by design
            continue
        out.append((name, d, url))
    return out


def _norm_header(s):
    s = (s or '')
    # A YAML title is often written quoted, and the quotes belong to the file rather than to
    # the post. Compared raw they read as drift on a post that is perfectly correct — the
    # third place on this desk that this bug appeared (piece_header's banner and the Notes
    # composer's card check were the other two), which is why it is stripped here rather than
    # unquoted in one manifest.
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
        s = s[1:-1]
    for a, b in (('\u2018', "'"), ('\u2019', "'"), ('\u201c', '"'), ('\u201d', '"'),
                 ('\u2014', '--'), ('\u2013', '-'), ('\u2026', '...'), ('\u00a0', ' ')):
        s = s.replace(a, b)
    return re.sub(r'\s+', ' ', s).strip()


def header_drift(post, man):
    """Title and subtitle: the two lines of a post the body comparison never sees.

    The body check was blind to them by construction -- it compares blocks of body_html,
    and the header is not in body_html. So a post could match block-for-block while its
    subtitle was empty, and one did: live from 2026-08-05, found 2026-09-03, never once
    reported by a verify run. An EMPTY live subtitle is drift even if the manifest is empty
    too, because the reader sees the archive card, not the manifest."""
    out = []
    # A PAGE has no subtitle FIELD (measured 2026-09-10: the composer offers Title only), so
    # "live post has NO subtitle" is not drift on one — it is the only state a page can be in.
    # The rule it replaces still stands for posts, where the subtitle is the second line of
    # every archive card and social preview and an empty one went unseen for a month.
    fields = ('title',) if man.get('substack_type') == 'page' else ('title', 'subtitle')
    for k in fields:
        live, want = _norm_header(post.get(k)), _norm_header(man.get(k))
        if not live:
            out.append(f'live post has NO {k}')
        elif want and live != want:
            out.append(f'{k} differs: live {live[:60]!r} vs manifest {want[:60]!r}')
    return out


def _fmt_runs(runs, limit=4):
    """Runs as a reader can check them: em'satsang'  strong'seventeen'  link'text'->url"""
    out = []
    for k, t, h in runs[:limit]:
        t = t if len(t) <= 34 else t[:31] + '...'
        out.append(f"{k}{t!r}" + (f'->{h}' if k == 'link' and h else ''))
    if len(runs) > limit:
        out.append(f'+{len(runs) - limit} more')
    return '[' + ' '.join(out) + ']' if out else '[none]'


def mark_drift(live, draft, live_text, draft_text, label, base=0):
    """Formatting drift, reported apart from text drift, because the fix is different.

    Only blocks whose TEXT already agrees are compared. A block whose words changed will
    of course have different marks, and saying so twice buries the finding that matters.

    Emphasis and links are separated for the same reason: an absent italic is a house-style
    slip, a wrong href is a dead link, and one message covering both tells the reader which
    to go fix. Link TARGETS are compared last and named as their own kind of drift."""
    out = []
    for i, (lr, dr) in enumerate(zip(live, draft)):
        if i >= len(live_text) or i >= len(draft_text):
            break
        if H(live_text[i]) != H(draft_text[i]):
            continue                                   # text drift already explains this one
        lk, dk = mark_keys(lr), mark_keys(dr)
        if lk == dk:
            continue
        le = [r for r in lk if r[0] != 'link']
        de = [r for r in dk if r[0] != 'link']
        ll = [r for r in lk if r[0] == 'link']
        dl = [r for r in dk if r[0] == 'link']
        n = i + base                     # blocks are 0-based, footnotes 1-based, as above
        if le != de:
            out.append(f'{label} #{n} emphasis: live {_fmt_runs(le)} vs draft {_fmt_runs(de)}')
        if [(k, t) for k, t, _h in ll] != [(k, t) for k, t, _h in dl]:
            out.append(f'{label} #{n} linked text: live {_fmt_runs(ll)} vs draft {_fmt_runs(dl)}')
        elif ll != dl:
            bad = [f'{t!r}: live {a or "(none)"} vs draft {b or "(none)"}'
                   for (_k, t, a), (_k2, _t2, b) in zip(ll, dl) if a != b]
            out.append(f'{label} #{n} link target: ' + '; '.join(bad[:2]))
    return out


def _fmt_anchors(entries, limit=4):
    """Anchors as a reader can check them: 1 after 'frighten him.'  2 after 'cower.'"""
    out = [f"{n or '?'} after {t!r}" if t is not None else f"{n or '?'} after ?"
           for n, t in entries[:limit]]
    if len(entries) > limit:
        out.append(f'+{len(entries) - limit} more')
    return '[' + '; '.join(out) + ']' if out else '[none]'


def anchor_drift(live, draft, live_text, draft_text, label, base=0):
    """WHERE each footnote is cited — the domain text and marks are both blind to.

    Measured 2026-09-11 on `for-the-love-of-dogs`, live since 2026-08-05: the post anchored
    footnote 1 after "It was slow. It worked." while the draft cites it after "I stopped
    trying to frighten him." — two paragraphs apart, a different claim carrying the note —
    and `--fresh` reported MATCH every time it was run. Reader-text drops the superscript
    digit and the mark scan never looked at it, so nothing on this desk could see it except
    `substack_repatch --structural`, which refused to patch and said why.

    Only blocks whose TEXT already agrees are compared, for the same reason mark_drift does
    it: when the words changed, so did every position in the block, and saying so a second
    time buries the finding that matters. A tail of None means the block's offsets were not
    trustworthy (its scanned text did not reproduce the reader-text), so only the numbers
    are compared there — a degraded check, never a silent pass."""
    out = []
    for i, (la, da) in enumerate(zip(live, draft)):
        if i >= len(live_text) or i >= len(draft_text):
            break
        if H(live_text[i]) != H(draft_text[i]):
            continue                                   # text drift already explains this one
        n = i + base                     # blocks are 0-based, footnotes 1-based, as above
        if [x for x, _t in la] != [x for x, _t in da]:
            out.append(f'{label} #{n} footnote anchors: live {_fmt_anchors(la)} '
                       f'vs draft {_fmt_anchors(da)}')
            continue
        moved = [(x, lt, dt) for (x, lt), (_x, dt) in zip(la, da)
                 if lt is not None and dt is not None and lt != dt]
        if moved:
            out.append(f'{label} #{n} footnote anchor moved: '
                       + '; '.join(f'[^{x}] live after {lt!r} vs draft after {dt!r}'
                                   for x, lt, dt in moved[:2]))
    return out


def walk_archive(base, fresh=False, page=50):
    """Every post the publication serves publicly, via its archive API, newest first.

    This is the check that does not start from the repo. `published_pieces()` can only
    verify what the desk knows about; a post composed straight in Substack, or one that
    predates the desk, is invisible to it. The archive is the reader's list, and the
    reader's list is the one that has to be right."""
    posts, offset, seen = [], 0, set()
    while True:
        url = f'{base}/api/v1/archive?sort=new&limit={page}&offset={offset}'
        batch = [p for p in json.loads(fetch_public(url, fresh)) if p.get('id') not in seen]
        # A SHORT PAGE IS NOT THE LAST PAGE. Substack caps a page below the limit asked for
        # (measured 2026-09-03: limit=50 returned 23, and offset=23 returned 6 more), so the
        # only end-of-list signal that can be trusted is an empty one. Stopping on a short
        # page silently dropped the six oldest posts -- including the one with no subtitle.
        if not batch:
            return posts
        posts += batch
        seen.update(p.get('id') for p in batch)
        offset += len(batch)


def archive_outlet(repo, want=None):
    """-> (outlet name or None, reader base or None, problem or None) for an --archive run.

    AN ARCHIVE IS ONE PUBLICATION'S, so this walk has to name which. It used to derive the base
    URL from whichever manifest came first in the dict — `re.match(host, next(iter(known))…)` —
    which is only ever right on a desk with one Substack outlet, and silently picks a side on a
    desk with two. The primary is the default because it is the desk's own declared answer to
    "which one, when nobody said"; `--outlet` names the other."""
    path = sa.outlets_path_for(os.path.join(repo, 'pieces')) if os.path.isdir(repo) else None
    if not path or not os.path.isfile(path):
        return (None, None, None)                     # no registry: the old single-outlet path
    doc = sa.load(path)
    if want:
        if want not in doc['outlets']:
            return (None, None, f'{want!r} is not an outlet in {os.path.basename(path)}')
        if want not in sa.substack_outlets(doc):
            return (None, None, f'{want!r} is not a Substack outlet, so it has no post archive')
        name = want
    else:
        name, problem = sa.primary(doc)
        if problem:
            return (None, None, f'{problem} — name one with --outlet')
    base = re.match(r'https?://[^/]+', str(doc['outlets'][name].get('reader_base') or '') or '')
    if not base:
        return (None, None, f'{name} records no reader_base, so its archive cannot be located')
    return (name, base.group(0), None)


def audit_archive(repo, fresh, outlet=None):
    """Cross the live archive with the desk. Returns (rows, problems)."""
    name_outlet, base, problem = archive_outlet(repo, outlet)
    if problem:
        return [], [problem]
    known = {}
    pieces = os.path.join(repo, 'pieces')
    for name in sorted(os.listdir(pieces)) if os.path.isdir(pieces) else []:
        d = os.path.join(pieces, name)
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        u, piece_outlet, _key = live_url(d, man)
        # ONE publication's archive, so one publication's pieces. A post of the other outlet
        # counted here would be reported as missing from a list it was never going to be in —
        # the same false finding `--archive` exists to make impossible in the other direction.
        if name_outlet and piece_outlet and piece_outlet != name_outlet:
            continue
        if u:
            known[u.rstrip('/').rsplit('/', 1)[-1]] = (name, man)
    # A Substack PAGE is a post with `type: "page"` (measured 2026-09-10): same editor
    # route, same composer, same transport — but it is NOT in the post archive, has no
    # post_date, never emails and needs no cover. So a piece that declares itself a page
    # is excluded from this audit rather than reported missing from a list it was never
    # going to be in.
    pages = {k: v for k, v in known.items() if v[1].get('substack_type') == 'page'}
    known = {k: v for k, v in known.items() if v[1].get('substack_type') != 'page'}
    if base is None:                                  # no registry: the desk's own first URL
        if not known:
            return [], ['no piece records a public_url, so the publication cannot be located']
        base = re.match(r'https?://[^/]+', next(iter(known.values()))[1]['public_url']).group(0)
    posts = walk_archive(base, fresh)
    rows, problems = [], []
    for p in posts:
        slug = p.get('slug', '')
        name, man = known.get(slug, (None, None))
        flags = []
        if not _norm_header(p.get('subtitle')):
            flags.append('NO SUBTITLE')
        if not _norm_header(p.get('title')):
            flags.append('NO TITLE')
        # A post with no cover has no drafts-list thumbnail, no archive card and no social
        # preview — it looks unfinished everywhere it is listed, and every other check here
        # reads the BODY, where the hero is a different image that is present. So the one
        # thing that can see this is the archive walk. (2026-09-10: publishing set the cover
        # as a step for the first time, and this is what stops it being skipped silently.)
        if not (p.get('cover_image') or '').strip():
            flags.append('NO COVER')
        if name is None:
            flags.append('not in the desk')
        elif man is not None:
            flags += [f for f in header_drift(p, man) if 'differs' in f]
        rows.append((slug, name or '-', (p.get('post_date') or '')[:10], flags))
        problems += [f'{slug}: {f}' for f in flags]
    for slug, (name, _man) in sorted(pages.items()):
        rows.append((slug, name, 'page', ['(page — not in the post archive)']))
    return rows, problems


def verify(name, piece_dir, url, fresh):
    try:
        post = extract_post(fetch_public(url, fresh))
    except urllib.error.HTTPError as e:
        return ('UNREACHABLE', f'HTTP {e.code} {e.reason}', {})
    except Exception as e:                                        # noqa: BLE001
        return ('UNREACHABLE', f'{type(e).__name__}: {str(e)[:60]}', {})
    if not post:
        return ('UNREACHABLE', 'no _preloads in page (login wall or layout change?)', {})

    lb, lf, lbm, lfm, lba, lfa = live_blocks(post.get('body_html') or '')
    body, fns, _residual, _iss = render_reader(piece_dir)
    dbm, dfm, _offsets_ok = render_marks(piece_dir)
    dba, dfa = render_anchors(piece_dir)
    n_marks = sum(len(r) for r in lbm) + sum(len(r) for r in lfm)
    n_want = sum(len(r) for r in dbm) + sum(len(r) for r in dfm)
    facts = {'audience': post.get('audience'),
             'emailed': post.get('email_sent_at'),
             'blocks': f'{len(lb)}/{len(body)}', 'fns': f'{len(lf)}/{len(fns)}',
             'marks': f'{n_marks}/{n_want}'}
    header = header_drift(post, read_manifest(os.path.join(piece_dir, 'publish.yaml')))
    want_caps = render_captions(piece_dir)
    live_caps = live_captions(post.get('body_html') or '')
    caps = caption_drift(live_caps, want_caps)
    if any(want_caps) or any(live_caps):
        facts['captions'] = f'{sum(1 for c in live_caps if c)}/{sum(1 for c in want_caps if c)}'
    text_ok = ([H(x) for x in lb] == [H(x) for x in body]
               and [H(x) for x in lf] == [H(x) for x in fns])
    # Marks are compared only when the two sides are structurally alignable at all. If the
    # block counts differ, index i is not the same block on both sides and every mark
    # comparison after the first insertion is noise.
    marks, anchors = [], []
    if len(lb) == len(body) and len(lf) == len(fns):
        marks = (mark_drift(lbm, dbm, lb, body, 'block')
                 + mark_drift(lfm, dfm, lf, fns, 'footnote', base=1))
        anchors = (anchor_drift(lba, dba, lb, body, 'block')
                   + anchor_drift(lfa, dfa, lf, fns, 'footnote', base=1))
    n_anch = sum(len(a) for a in lba) + sum(len(a) for a in lfa)
    n_anch_want = sum(len(a) for a in dba) + sum(len(a) for a in dfa)
    if n_anch or n_anch_want:
        facts['anchors'] = f'{n_anch}/{n_anch_want}'
    if not header and text_ok and not marks and not caps and not anchors:
        return ('MATCH', '', facts)

    detail = list(header)
    if len(lb) != len(body): detail.append(f'body {len(lb)} live vs {len(body)} draft')
    if len(lf) != len(fns):  detail.append(f'footnotes {len(lf)} live vs {len(fns)} draft')
    for i, (a, b) in enumerate(zip([H(x) for x in body], [H(x) for x in lb])):
        if a != b:
            detail.append(f'first differing block #{i}: live {lb[i][:70]!r}')
            break
    for i, (a, b) in enumerate(zip([H(x) for x in fns], [H(x) for x in lf])):
        if a != b:
            detail.append(f'first differing footnote #{i + 1}: live {lf[i][:70]!r}')
            break
    detail += marks[:3] + caps[:3] + anchors[:3]
    if len(marks) > 3:
        detail.append(f'(+{len(marks) - 3} more formatting difference(s))')
    if len(anchors) > 3:
        detail.append(f'(+{len(anchors) - 3} more anchor difference(s))')
    # A formatting-only drift gets its OWN status. It is invisible to every text digest on
    # this desk, so a run that reported it as plain DRIFT would send the reader looking for
    # a word that changed and find none -- and the surgical patcher, asked to fix it, would
    # report `unchanged` and apply nothing. Naming the kind is what makes it actionable.
    # Captions likewise: media text no reader digest covers, so they get their own name.
    # An ANCHOR-only drift is its own kind for the same reason a formatting-only one is:
    # nothing in the reader-text changed, so a plain DRIFT sends the reader hunting for a
    # word that is not there — and the fix is different again. A moved anchor is repaired
    # by moving the superscript in the editor, not by repatching a block.
    only = lambda mine, *others: bool(mine) and text_ok and not header and not any(others)
    status = ('DRIFT-MARKS'   if only(marks, caps, anchors) else
              'DRIFT-CAPTION' if only(caps, marks, anchors) else
              'DRIFT-ANCHORS' if only(anchors, marks, caps) else 'DRIFT')
    return (status, '; '.join(detail), facts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('pieces', nargs='*', help='piece dirs (default: every published piece)')
    ap.add_argument('--fresh', action='store_true', help='bypass the CDN cache')
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(HERE)))
    ap.add_argument('--list', action='store_true',
                    help='list what is live (and therefore in scope) without fetching')
    ap.add_argument('--changed', nargs='?', const='HEAD~1..HEAD', metavar='RANGE',
                    help='only pieces this commit range touched (default HEAD~1..HEAD; '
                         'for a pre-push hook, origin/main..HEAD)')
    ap.add_argument('--budget', type=int, default=BUDGET,
                    help='stop after this many seconds rather than grinding (0 = no limit)')
    ap.add_argument('--archive', action='store_true',
                    help='walk the PUBLICATION\'s public archive instead of the repo: every '
                         'live post must have a title and a subtitle and be known to the desk')
    ap.add_argument('--outlet',
                    help='--archive: which Substack outlet\'s archive to walk (default: the '
                         'desk\'s substack_primary). An archive belongs to one publication.')
    a = ap.parse_args()

    if a.archive:
        rows, problems = audit_archive(a.repo, a.fresh, a.outlet)
        if not rows:
            print('FAILED: the archive returned no posts' + (f' ({problems[0]})' if problems else ''))
            return 2
        w = max(len(r[0]) for r in rows)
        print(f"{len(rows)} live post(s) in the publication archive"
              + ("  [cache-busted]" if a.fresh else ""))
        for slug, name, date, flags in rows:
            print(f"  {slug:<{w}}  {date}  {name:<28} {'; '.join(flags)}")
        if problems:
            print(f"\nFAILED: {len(problems)} problem(s) a reader can see:")
            for pr in problems: print(f"  {pr}")
            return 1
        print("\nevery live post has a title and a subtitle, and the desk knows all of them.")
        return 0

    if a.list:
        # "Which pieces must match Substack?" should be one command, not an inference
        # from a filename. The piece's own outlet's URL key is the authoritative answer —
        # and naming the outlet is half of it on a desk with more than one.
        pieces = os.path.join(a.repo, 'pieces')
        rows = []
        for name in sorted(os.listdir(pieces)):
            d = os.path.join(pieces, name)
            if not os.path.isfile(os.path.join(d, 'draft.md')):
                continue
            man = read_manifest(os.path.join(d, 'publish.yaml'))
            url, outlet, _key = live_url(d, man)
            if url:
                state = 'LIVE'
            elif man.get('post_url'):
                state = 'composed'
            else:
                state = 'draft'
            rows.append((name, state, url, outlet or '-'))
        w = max(len(r[0]) for r in rows) if rows else 0
        ow = max((len(r[3]) for r in rows), default=0)
        for name, state, url, outlet in rows:
            print(f"  {name:<{w}}  {state:<9} {outlet:<{ow}}  {url}")
        live = sum(1 for r in rows if r[1] == 'LIVE')
        print(f"\n{live} live (in scope for verification), "
              f"{sum(1 for r in rows if r[1]=='composed')} composed, "
              f"{sum(1 for r in rows if r[1]=='draft')} draft")
        return 0

    if a.changed:
        slugs, err = pieces_touched_by(a.repo, a.changed)
        if err:
            print(f"could not resolve {a.changed}: {err}")
            return 2
        if not slugs:
            print(f"{a.changed} touched no piece — nothing to verify")
            return 0
        targets = published_pieces(a.repo, only=set(slugs))
        unpublished = [s_ for s_ in slugs if s_ not in {t[0] for t in targets}]
        print(f"{a.changed} touched {len(slugs)} piece(s): {', '.join(slugs)}")
        for u in unpublished:
            print(f"  skip  {u}  (not published — nothing live to compare against)")
        if not targets:
            print("none of them are published — nothing to verify")
            return 0
    elif a.pieces:
        targets = []
        for arg in a.pieces:
            d, url, reason = resolve_piece(a.repo, arg)
            if reason:
                print(f"  skip  {os.path.basename(d)}  ({reason})")
                continue
            targets.append((os.path.basename(d), d, url))
    else:
        targets = published_pieces(a.repo)

    if not targets:
        print('no published pieces to verify'); return 2

    print(f"verifying {len(targets)} published piece(s) against the live publication"
          + ("  [cache-busted]" if a.fresh else ""))
    w = max(len(t[0]) for t in targets)
    drift, unreachable, ok, emailed = [], [], 0, []
    started, gave_up = time.time(), None
    for n, (name, d, url) in enumerate(targets):
        # Two ways to stop early, both so a blocked run reports quickly instead of
        # spending half an hour proving the same thing 23 times.
        if a.budget and time.time() - started > a.budget:
            gave_up = f'time budget of {a.budget}s exhausted'; break
        if n >= 3 and ok == 0 and len(drift) == 0 and len(unreachable) == n:
            gave_up = 'the first 3 pages were all unreachable — treating this as blocked'
            break
        status, detail, facts = verify(name, d, url, a.fresh)
        line = f"  {name:<{w}}  {status:<12}"
        if facts.get('blocks'):
            line += (f" {facts['blocks']:>10} body {facts['fns']:>8} fn"
                     f" {facts.get('marks', '-'):>9} marks")
            if facts.get('anchors'):
                line += f" {facts['anchors']:>7} anchors"
        print(line + (f"   {detail}" if detail else ''))
        if status == 'MATCH':
            ok += 1
            if facts.get('emailed'): emailed.append(f"{name} ({facts['emailed']})")
        elif status.startswith('DRIFT'):
            drift.append(name + ('  (formatting only)' if status == 'DRIFT-MARKS' else
                                 '  (captions only)' if status == 'DRIFT-CAPTION' else
                                 '  (footnote anchor positions only)'
                                 if status == 'DRIFT-ANCHORS' else ''))
        else:
            unreachable.append(f'{name}: {detail}')
        time.sleep(0.3)                                # be a polite client

    if gave_up:
        print(f"\nstopped early: {gave_up}")
        print(f"  {len(targets) - len(unreachable) - ok - len(drift)} piece(s) not attempted")
    print(f"\n{ok} match, {len(drift)} drifted, {len(unreachable)} unreachable")
    for u in unreachable: print(f"  unreachable  {u}")
    for d in drift:       print(f"  DRIFTED      {d}")
    if emailed:
        print("  note: these posts record an email send: " + ', '.join(emailed))

    # "Nothing checked" means nothing was FETCHED AND COMPARED. A piece that drifted
    # was checked -- that is a finding, not a failure to look.
    if ok + len(drift) == 0:
        print("\nFAILED: nothing could be checked. A run that verified no pages is not a pass.")
        return 2
    if drift:
        print(f"\nFAILED: {len(drift)} piece(s) differ from the live publication.")
        return 1
    print("\nthe repo matches the publication.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
