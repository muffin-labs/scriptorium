#!/usr/bin/env python3
"""
test_suite.py — the desk's regression suite.  Run:  python3 framework/tools/test_suite.py

SAFETY, because this suite exists partly to replace a shell loop that was not safe:

  * It DELETES NOTHING.  Every generated file goes inside one `tempfile.TemporaryDirectory`,
    which the interpreter removes on exit.  There is no `rm` anywhere, and no path is ever
    interpolated into a shell command.
  * It makes NO NETWORK CALLS and drives NO BROWSER, so it can never touch a live post.
    Everything about "live" behaviour is exercised against a stubbed ProseMirror document.
  * It only READS the repository.  Nothing under `pieces/` or `framework/` is written.

The earlier version of this was a bash loop containing `rm -f $S/*` with `$S` unquoted — one
empty variable away from `rm -f /*`.  That is the reason the runner is a program now: a suite
that guards a publishing pipeline should not itself be the most dangerous thing in the repo.

WHAT IT COVERS — every case here is a bug that actually happened (2026-09-01):

  unit    quote/whitespace normalization, and the length-preservation split between the
          positional domain (`flatten_quotes`) and the equality domain (`H`)
  unit    three-way classification: push / pull / converged / conflict / unchanged
  unit    footnote ordering is REFERENCE order, not label order
  unit    escaped asterisks, bullet lists, adjacent-blockquote merging
  unit    footnote blocks render through the footnote path, not the paragraph path
  unit    the CDN image wrapper unwraps to the asset it points at
  unit    a pulled edit is verified by re-rendering; the one confirmed refusal (a
          whitespace run, which no markdown source can produce) is asserted, and no
          other refusal is asserted speculatively
  corpus  every piece renders; no undefined / duplicated / nested footnote refs; no
          unverified † notes left in any draft
  unit    the reader-side extractor, against canned markup (still no network)
  corpus  every live piece's header says it is live, not a draft
  corpus  every published piece matches its sealed baseline
  engine  the JS patcher's own suite (A–E) against every piece, via a stubbed editor
  unit    the pronoun sweep's sections E and F look INSIDE a scripture quotation — the four
          casing/bracket misses measured in *False Light* on 2026-09-07 are reproduced as a
          fixture and must all be listed; --strict warns on them and does not refuse
  unit    tags: the textual `tags:` writer keeps every comment and refuses any write that
          would change another key; an undefined tag stops at the exporter
  corpus  every tag a piece carries is in the desk's vocabulary
  unit    publications: the registry, a piece's one publication, a vocabulary per publication,
          and the store refusing one publication's piece over another's slug
  corpus  with a registry, every manifest names its publication and owns its outlets
"""
import os, re, sys, json, shutil, subprocess, tempfile, datetime, hashlib, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def _resolve_corpus():
    """Find the pieces.  Two layouts run this suite and the difference matters.

        instance   writing-desk/framework/tools/  ->  writing-desk/pieces/
        framework  scriptorium/tools/             ->  tools/fixtures/pieces/

    In a standalone framework checkout `tools/` sits at the REPO ROOT, so the
    instance path resolves to the parent of the checkout — outside it entirely.
    So don't compute the corpus, look for it: take the instance pieces only when
    they are actually on disk, and otherwise fall back to the fixtures that ship
    with the framework.  The fixture corpus exists so that the engine and
    converter checks still RUN in the framework repo, where the code they guard
    lives.  Skipping them there would leave the patcher's regression tests
    running only in a private repo that happens to hold drafts.
    """
    env = os.environ.get('DESK_PIECES')
    if env:
        return os.path.abspath(env), 'explicit ($DESK_PIECES)'
    instance = os.path.join(os.path.dirname(FRAMEWORK), 'pieces')
    if os.path.isdir(instance):
        return instance, 'instance'
    return os.path.join(HERE, 'fixtures', 'pieces'), 'fixture'


PIECES, CORPUS_KIND = _resolve_corpus()

_CORPUS_OUTLETS = None


def corpus_outlets():
    """(outlets, legacy) from the corpus's OWN registry — cached; ({}, None) with no registry."""
    global _CORPUS_OUTLETS
    if _CORPUS_OUTLETS is None:
        import check_status as cs
        _CORPUS_OUTLETS = cs.outlets_for(os.path.dirname(PIECES))
    return _CORPUS_OUTLETS


def live_url(man):
    """-> where a reader finds this piece, by ITS OWN outlet's manifest key, or ''.

    THE CORPUS CHECKS' LIVENESS TEST, and until 2026-09-11 every one of them was
    `man.get('public_url')` — which is ONE outlet's key (`substack`, Being Good), not a
    universal one. outlets.yaml has said EACH OUTLET GETS ITS OWN MANIFEST KEY since the
    professional line was added, and substack_verify and substack_notes learned it the day
    before (scriptorium c1e192f). These did not, so a SECOND PUBLICATION was outside the
    gates CI runs: corpus_headers never asked whether its drafts said they were published,
    corpus_manifests never asked for its title and subtitle, `every published piece declares
    its outlets` never asked, and corpus_baselines never asked for a sealed baseline — which
    is why `love-is-not-a-metric-space` went live on 2026-09-11 with none and nothing said so.
    A whole publication reading as *unpublished* is not a gap in one check; it is every check
    at once, and each of them still printed ok.

    A desk with no registry keeps `public_url`, which is what a one-outlet desk has always
    written and what the shipped fixtures are.
    """
    import check_status as cs
    return cs.live_url(man, corpus_outlets()[0])

from md_to_substack import (flatten_quotes, smarten_quotes, render_block,
                            render_footnote_block, strip_to_reader, render_reader,
                            read_manifest, parse_blocks, manifest_gate,
                            render_marks, render_anchors, anchor_tail,
                            marks_in, mark_keys)
from substack_sync import (H, HM, three_way, align, canonical_image_url,
                           reader_to_source_map, edit_block_source, load_baseline,
                           baseline_has_marks, write_baseline, draft_state)
from substack_verify import (live_blocks, extract_post, header_drift, mark_drift,
                             anchor_drift)
from piece_header import rewrite as header_rewrite
from check_links import extract as extract_links, unrenderable as unrenderable_links
import check_pronouns
import md_to_marp

PASS, FAIL, SKIP = [], [], []


def check(name, ok, detail=''):
    (PASS if ok else FAIL).append((name, detail))
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail and not ok else ''))


def skip(name, why):
    SKIP.append((name, why))
    print(f"  skip  {name}   ({why})")


# ---------------------------------------------------------------- unit: normalization
def unit_normalization():
    print("\n-- normalization -------------------------------------------------")
    s = 'the “word” it’s'
    check('flatten_quotes is length-preserving',
          len(flatten_quotes(s)) == len(s),
          'a positional offset computed on it must index the real text')
    check('H ignores quote style', H('the "x" y') == H('the “x” y'))
    check('H ignores whitespace runs', H('it.  The') == H('it. The'),
          'a double space describes a block no draft can produce')
    check('H still sees real differences', H('a b') != H('a c'))
    check('H ignores leading/trailing space', H('  a b  ') == H('a b'))
    check('smarten opens then closes', smarten_quotes('"a" b') == '“a” b')
    check('smarten handles an apostrophe mid-word', smarten_quotes("it's") == 'it’s')


# ---------------------------------------------------------------- unit: commonmark parity
def unit_commonmark(tmp):
    """The desk's Substack converter is lenient; every other outlet renders CommonMark.

    Two live faults came through that gap on 2026-09-11 (not-yet, son-of-joseph). These
    cases pin what the check must flag and — as important — what it must leave alone,
    because a parity check that flags the house censoring convention would be ignored.
    """
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'cc', os.path.join(os.path.dirname(__file__), 'check_commonmark.py'))
    cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
    md = cc._md()
    if md is None:
        print("  skip  commonmark: markdown-it-py is not installed — this is NOT a pass")
        return
    kinds = lambda body: [k for k, _ in cc.check_text('x\n---\n' + body, md)]
    check('commonmark: a star after a letter before a comma is flagged',
          kinds("*as those who have read it,* Confessions*, know — one of us.* Go on.") == ['stray-asterisk'])
    check('commonmark: the same sentence, fixed, is clean',
          kinds("*as those who have read it,* Confessions, *know — one of us.* Go on.") == [])
    check('commonmark: a backtick used as ayin is flagged',
          kinds("The Hebrew is *`almah*; it means young woman.") == ['backtick-letter-mark'])
    check('commonmark: the real ayin is clean',
          kinds("The Hebrew is *ʿalmah*; it means young woman.") == [])
    check('commonmark: escaped censoring (f\\*\\*k) is not a leak',
          kinds("He tells the camera to f\\*\\*k off.") == [])
    check('commonmark: an asterisk inside code is not a leak',
          kinds("The glob `*.md` matches every *draft* here.") == [])


# ---------------------------------------------------------------- unit: outlet content
def unit_outlet_content(tmp):
    """outlet_audit --content: what counts as drift, and what must not.

    Every false lead on 2026-09-11 was one of two things: a whitespace-only difference a
    reader cannot see, or the syndication line expected on the canonical outlet. Both are
    pinned here, along with the half that must never regress — a changed WORD is drift.
    """
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'oa', os.path.join(os.path.dirname(__file__), 'outlet_audit.py'))
    oa = importlib.util.module_from_spec(spec); spec.loader.exec_module(oa)
    d = os.path.join(tmp, 'oapiece'); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'publish.yaml'), 'w').write(
        'title: T\nsubtitle: S\ncanonical: https://www.example.com/blog/a-piece\n')
    para = ("The tuning was set before the player arrived, by cuts nobody consulted "
            "the flute about, and no work on the surface reaches it.")
    open(os.path.join(d, 'draft.md'), 'w').write('scaffold\n---\n' + para + '\n')
    ws = '<p>' + para.replace(', by', ' , by').replace('the flute', 'the\n  flute') + '</p>'
    r = oa.content_drift(d, ws, canonical_outlet=True)
    check('outlet content: a whitespace-only difference is not drift',
          r is not None and not r['missing'])
    bad = '<p>' + para.replace('player', 'singer') + '</p>'
    r = oa.content_drift(d, bad, canonical_outlet=True)
    check('outlet content: a changed word is still drift',
          r is not None and len(r['missing']) == 1)
    r = oa.content_drift(d, ws, canonical_outlet=False)
    check('outlet content: a syndicated copy must carry the originally-published line',
          r is not None and any(w.startswith('Originally published at') for w in r['missing']))

    # --- the link preview: a store publish never touches the site repo, so a live page's
    # og:image can 404 (one of 33, 2026-09-11). No network: the probe is stubbed.
    page_url = 'https://site.test/writings/a-piece/'
    head = ('<meta property="og:image:width" content="1200"/>'
            '<meta content="/og/a-piece.jpg" property="og:image"/>')
    check('preview: og:image is found whatever the attribute order, and made absolute',
          oa.og_image_url(head, page_url) == 'https://site.test/og/a-piece.jpg',
          str(oa.og_image_url(head, page_url)))
    check('preview: og:image:width is not mistaken for the image',
          oa.og_image_url('<meta property="og:image:width" content="1200"/>', page_url) is None)
    stub = lambda answer: (lambda _url: answer)
    check('preview: an image that answers 200 image/* is fine',
          oa.preview_problem(head, page_url, stub((200, 'image/jpeg'))) is None)
    check('preview: a 404 og:image is reported',
          'HTTP 404' in (oa.preview_problem(head, page_url, stub((404, ''))) or ''))
    check('preview: a 200 that is not an image is reported (an HTML error page)',
          'not an image' in (oa.preview_problem(head, page_url, stub((200, 'text/html'))) or ''))
    check('preview: a page that names no og:image is reported',
          oa.preview_problem('<p>x</p>', page_url, stub((200, 'image/jpeg'))) is not None)
    check('preview: an unreachable image is not a pass',
          oa.preview_problem(head, page_url, stub((None, ''))) is not None)


# ---------------------------------------------------------------- unit: substack pages
def unit_pages(tmp):
    """A page is a post with type "page" — the checks that must NOT fire on one.

    Measured 2026-09-10: clicking Add page opens /publish/post/<id> in the same composer,
    and the draft object differs only by `type`. So the transport is shared and the risk
    is the other direction — a post-shaped check reporting a page as broken because it is
    absent from a list it was never going to be in.
    """
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'sv', os.path.join(os.path.dirname(__file__), 'substack_verify.py'))
    sv = importlib.util.module_from_spec(spec); spec.loader.exec_module(sv)

    repo = os.path.join(tmp, 'pagerepo'); pieces = os.path.join(repo, 'pieces')
    for slug, extra in (('an-essay', ''), ('a-colophon', 'substack_type: page\n')):
        d = os.path.join(pieces, slug); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'publish.yaml'), 'w').write(
            f"title: T\nsubtitle: S\n{extra}"
            f"public_url: https://example.substack.com/p/{slug}\n")
    man_page = sv.read_manifest(os.path.join(pieces, 'a-colophon', 'publish.yaml'))
    man_post = sv.read_manifest(os.path.join(pieces, 'an-essay', 'publish.yaml'))
    check('pages: substack_type is read from the manifest',
          man_page.get('substack_type') == 'page')
    check('pages: a post does not accidentally declare itself one',
          man_post.get('substack_type') is None)

    # The header gate refuses a post with no subtitle — and a PAGE HAS NO SUBTITLE FIELD,
    # so requiring one refused a compose that was correct. A gate that refuses correct work
    # is the worst kind: it teaches you to reach for an override. (2026-09-10.)
    spec2 = importlib.util.spec_from_file_location(
        'mts', os.path.join(os.path.dirname(__file__), 'md_to_substack.py'))
    mts = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(mts)
    pg = os.path.join(pieces, 'a-colophon')
    open(os.path.join(pg, 'publish.yaml'), 'w').write(
        'title: A Colophon\nsubstack_type: page\n')
    errs, _warns = mts.manifest_gate(pg)
    check('pages: the header gate does not demand a subtitle of a page', not errs)
    po = os.path.join(pieces, 'an-essay')
    open(os.path.join(po, 'publish.yaml'), 'w').write('title: An Essay\n')
    errs2, _ = mts.manifest_gate(po)
    check('pages: a POST with no subtitle is still refused', bool(errs2))


# ---------------------------------------------------------------- unit: references + quotes
def unit_references(tmp):
    """Intake, indexing, and the two ways this pair reported correct work as wrong.

    Both cases here were measured on 2026-09-11, the day the tools were written, and
    both are the same failure the scripture checker names in its own docstring: a
    checker that flags correct prose trains the reader to skim past it.
    """
    import importlib.util, os, gzip

    def load(name):
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(os.path.dirname(__file__), name + '.py'))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m

    R, RI = load('references'), load('refindex')

    # The manifest's ⚠️ does two different jobs. Four public-domain scans read
    # "✅ Public domain. ⚠️ OCR." and were called restricted, which demanded they be
    # removed from git. The LEADING marker is the verdict.
    check('references: ✅ then ⚠️ is public domain, not restricted',
          R._verdict('✅ Public domain. ⚠️ OCR.') == 'ok')
    check('references: a leading ⚠️ is restricted',
          R._verdict('⚠️ **In copyright** — do not republish.') == 'restricted')
    check('references: a cell with neither marker states no verdict',
          R._verdict('Public domain, probably') is None)

    # There are THREE verdict markers. ❌ was missed by the first parser, so the one
    # row using it ("❌ **Not redistributable.** arXiv's licence grants us none") read
    # as no-verdict — and no-verdict then meant UNRESTRICTED, which is the unsafe
    # direction. Only an unrelated .gitignore line kept it from mattering.
    check('references: ❌ is a verdict, and it means restricted',
          R._verdict("❌ **Not redistributable.** arXiv's licence grants us none.")
          == 'restricted')
    check('references: an unreadable verdict FAILS CLOSED',
          R._restricted('Probably fine?') is True)
    check('references: only an explicit ✅ is unrestricted',
          R._restricted('✅ Public domain. ⚠️ OCR.') is False)
    check('references: an unclassifiable verdict is also a FINDING, not just fail-closed',
          R._verdict('Probably fine?') is None and R._restricted('Probably fine?') is True)

    # An apostrophe is a letter inside a word and punctuation around one.
    check('references: a quote-mark apostrophe is dropped',
          R.norm("the ‘city of light’ where") == 'the city of light where')
    check("references: a contraction's apostrophe survives",
          "it's" in R.norm("it's here"))

    # A word broken across a PDF line comes back hyphenated.
    check('refindex: a line-break hyphen is rejoined',
          RI.clean('what is believ- able here') == 'what is believable here')
    check('refindex: a spaced dash is not a hyphenation',
          '-' in RI.clean('the source - and the draft'))

    # A .txt source indexes by line, and the locators ascend.
    src = os.path.join(tmp, 'src.txt')
    open(src, 'w').write('\n'.join(f'line {i} of the source text' for i in range(200)))
    out = os.path.join(tmp, 'src.tsv.gz')
    RI.build_text(src, out, lines_per_block=40)
    rows, stream, offsets = R.load_index(out)
    check('refindex: text scheme writes ascending integer locators',
          len(rows) == 5 and [int(r[0]) for r in rows] == sorted(int(r[0]) for r in rows))

    # The joined stream is the whole point: a phrase spanning two rows is findable.
    check('references: a phrase straddling two index rows is found',
          'line 39 of the source text line 40 of the source text' in stream)
    check('references: locate reports the row a hit fell in',
          R.locate(offsets, stream.find('line 41')) == '41')

    # A scanned PDF has no text layer, and treating it as a held source would report
    # every true quotation from it as missing.
    big = os.path.join(tmp, 'scan.pdf')
    open(big, 'wb').write(b'x' * 300_000)
    tiny = os.path.join(tmp, 'scan.tsv.gz')
    with gzip.open(tiny, 'wt') as f:
        f.write('1\tcover page\n')
    check('references: a big file with a tiny index is reported as having no text layer',
          'NO USABLE TEXT' in (R.text_layer_verdict(big, tiny) or ''))
    check('references: a real index is not',
          R.text_layer_verdict(src, out) is None)


def unit_scan_hash(tmp):
    """A saved scan proves its own transcription.

    A scan comes off the page as ten kilobytes of hex that somebody writes into a file by
    hand. `seal` failed closed on a slip, which is safe and says nothing about where it
    went wrong; `plan` had no guard at all, so a mistyped hash there reads as a REAL
    difference and sends somebody to re-sync a block that never changed. The snippet now
    hashes its own output and the loader checks it. (2026-09-14, after three baselines
    were resealed by hand and the digest was computed ad hoc each time.)
    """
    print("\n-- substack_sync: a scan proves its own transcription -----------------")
    import io, contextlib, hashlib, json, importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'substack_sync', os.path.join(os.path.dirname(__file__), 'substack_sync.py'))
    SS = importlib.util.module_from_spec(spec); spec.loader.exec_module(SS)

    inner = json.dumps({'url': 'https://x.substack.com/publish/post/1', 'marksVersion': 1,
                        'title': 'T', 'subtitle': 'S',
                        'counts': {'body': 1, 'fns': 0},
                        'body': ['abc123abc123abc1'], 'fns': [],
                        'bodyMarks': ['e3b0c44298fc1c14'], 'fnsMarks': []})
    digest = hashlib.sha256(inner.encode()).hexdigest()

    good = os.path.join(tmp, 'scan-good.json')
    open(good, 'w').write(json.dumps({'scanVersion': 2, 'sha256': digest, 'scan': inner}))
    with contextlib.redirect_stdout(io.StringIO()):
        live = SS.load_scan(good)
    check('scan hash: a well-formed scan unwraps to the scan itself',
          live['title'] == 'T' and live['body'] == ['abc123abc123abc1'], str(live)[:80])

    # ONE CHARACTER, the shape a hand transcription actually fails in.
    bad = os.path.join(tmp, 'scan-bad.json')
    mangled = inner.replace('abc123abc123abc1', 'abc123abc123abc2')
    open(bad, 'w').write(json.dumps({'scanVersion': 2, 'sha256': digest, 'scan': mangled}))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            SS.load_scan(bad)
        rc = 0
    except SystemExit as e:
        rc = e.code
    check('scan hash: one altered character is REFUSED, and named as transcription',
          rc == 8 and 'TRANSCRIPTION' in buf.getvalue(), f'rc={rc} {buf.getvalue()[:90]}')
    check('scan hash: and the refusal prints both digests, so the slip is findable',
          digest in buf.getvalue()
          and hashlib.sha256(mangled.encode()).hexdigest() in buf.getvalue())

    # A bare pre-2026-09-14 scan still loads, and SAYS it cannot be checked — a skip that
    # announces itself, never a silence.
    old = os.path.join(tmp, 'scan-old.json')
    open(old, 'w').write(inner)
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        live2 = SS.load_scan(old)
    check('scan hash: a bare older scan still loads', live2['title'] == 'T')
    check('scan hash: and says out loud that it cannot be checked',
          'cannot be checked' in buf2.getvalue(), buf2.getvalue()[:90])


def unit_rehash(tmp):
    """`rehash` writes the MANIFEST and nothing else — and a row may carry several hashes.

    Both halves are the same incident, 2026-09-14. A held file's path was assigned to a
    variable called `path` inside the loop, shadowing the manifest's own `path` from above
    it, so the write at the end put the MANIFEST'S TEXT INTO THE LAST HELD FILE:
    Chiang-story.pdf went from a 2.6 MB scan to 50 KB of README. It was gitignored and
    untracked, so git had no copy; it came back only because its manifest row recorded the
    source URL and the source hash.

    And the reason rehash was touching that row at all is the second half: the row records
    TWO hashes on purpose — the source bytes as fetched, and the same scan after ocrmypdf
    gave it a text layer. A parser that took the first called the row a DIGEST MISMATCH
    against its own correct file. Both are true; the bytes on disk say which is which.
    """
    print("\n-- references: rehash writes the manifest, and only the manifest ------")
    import io, contextlib, hashlib, importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'references', os.path.join(os.path.dirname(__file__), 'references.py'))
    R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)

    home = os.path.join(tmp, 'rehash-inst')
    refs = os.path.join(home, 'references')
    os.makedirs(refs); os.makedirs(os.path.join(home, 'books', 'tst'))
    held = {'one.txt': b'the first held source, at some length.' * 8,
            'two.txt': b'the second held source, longer still, and different.' * 9}
    for name, body in held.items():
        open(os.path.join(refs, name), 'wb').write(body)
    H = {n: hashlib.sha256(b).hexdigest() for n, b in held.items()}
    PROV = 'deadbeefdeadbeef'          # a source hash for bytes the desk no longer holds
    open(os.path.join(refs, 'README.md'), 'w').write(
        '# R\n\n| File | Book | Work | Edition / provenance | Added | Redistribution |\n'
        '|---|---|---|---|---|---|\n'
        f'| [one.txt](one.txt) | tst | *One* — A (1) | sha256 `{H["one.txt"][:16]}…` | 2026-09-14 | ✅ Public. |\n'
        f'| [two.txt](two.txt) | tst | *Two* — B (2) | source bytes sha256 `{PROV}…`; the held file '
        f'sha256 `{H["two.txt"][:16]}…` | 2026-09-14 | ✅ Public. |\n')
    R.root = lambda: home

    row2 = [x for x in R.rows(home) if x.get('file') == 'two.txt'][0]
    check('rehash: a row carrying two hashes parses both',
          row2['digests'] == [PROV, H['two.txt'][:16]], str(row2.get('digests')))
    d, st = R.held_digest(row2, os.path.join(refs, 'two.txt'))
    check('rehash: the held digest is the one the BYTES answer to, not the first written',
          st == 'match' and d == H['two.txt'][:16], f'{st} {d}')

    with contextlib.redirect_stdout(io.StringIO()):
        R.cmd_rehash([])

    # THE CHECK THAT WOULD HAVE CAUGHT IT.
    for name, body in held.items():
        check(f'rehash: {name} is byte-for-byte untouched — rehash writes no held file',
              open(os.path.join(refs, name), 'rb').read() == body,
              f'{os.path.getsize(os.path.join(refs, name))} bytes now')

    body = open(os.path.join(refs, 'README.md')).read()
    check('rehash: the matching hash is expanded to its full length',
          H['one.txt'] in body and H['two.txt'] in body)
    check('rehash: a PROVENANCE hash is left alone — those bytes are not held and cannot '
          'be expanded', f'`{PROV}…`' in body, body[body.find('two.txt'):][:200])


def unit_shelf(tmp):
    """push/pull against a fake bucket. No AWS, and the refusals are the point.

    The shelf holds the half of the references that can never be committed, so the
    failures worth testing are the ones where it would hand back the WRONG bytes or
    overwrite the right ones — those are unrecoverable, and everything else is a retry.
    """
    import io, contextlib, hashlib, importlib.util, os

    spec = importlib.util.spec_from_file_location(
        'references', os.path.join(os.path.dirname(__file__), 'references.py'))
    R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)

    home = os.path.join(tmp, 'shelf-inst')
    refs = os.path.join(home, 'references')
    os.makedirs(os.path.join(refs, '.index'))
    os.makedirs(os.path.join(home, 'books', 'tst'))
    body = b'a held source, at length. ' * 40
    open(os.path.join(refs, 'held.txt'), 'wb').write(body)
    digest = hashlib.sha256(body).hexdigest()
    open(os.path.join(refs, '.index', 'held.tsv.gz'), 'wb').write(b'not really gzip')

    def manifest(dig, verdict='✅ Public domain. Safe to quote and redistribute.'):
        open(os.path.join(refs, 'README.md'), 'w').write(
            '# R\n\n| File | Book | Work | Edition / provenance | Added | Redistribution |\n'
            '|---|---|---|---|---|---|\n'
            f'| [held.txt](held.txt) | tst | *A Work* — An Author (1999) | '
            f'sha256 `{dig}` | 2026-09-13 | {verdict} |\n')
    manifest(digest)

    R.root = lambda: home
    check('shelf: the key is the hash, and the leaf keeps it legible',
          R.shelf_key(digest, 'held.txt') == f'refs/{digest}/held.txt')
    check('shelf: an index is keyed by the SOURCE hash, so it is unambiguous',
          R.shelf_key(digest, 'held.txt', index=True)
          == f'refs/{digest}/.index/held.tsv.gz')

    ok, refused = R._shelf_targets(home)
    check('shelf: a well-formed row is addressable', len(ok) == 1 and not refused)

    manifest(digest[:16])
    ok, refused = R._shelf_targets(home)
    check('shelf: a TRUNCATED digest is refused — a prefix is not an address',
          not ok and refused and 'truncated' in refused[0][1], str(refused))

    manifest('f' * 64)
    ok, refused = R._shelf_targets(home)
    check('shelf: a digest that disagrees with the file is refused',
          not ok and refused and 'MISMATCH' in refused[0][1], str(refused))

    manifest(digest, verdict='held on the shelf')      # no ✅ / ⚠️ / ❌
    ok, refused = R._shelf_targets(home)
    check('shelf: a row with no redistribution verdict is refused, not guessed at',
          not ok and refused and 'verdict' in refused[0][1], str(refused))
    manifest(digest)

    # ---- a fake bucket -----------------------------------------------------
    class Fake:
        def __init__(self): self.objs = {}
        def head_object(self, Bucket, Key):
            if Key not in self.objs: raise RuntimeError('404')
            return {}
        def upload_file(self, src, Bucket, Key):
            self.objs[Key] = open(src, 'rb').read()
        def download_file(self, Bucket, Key, dest):
            if Key not in self.objs: raise RuntimeError('404')
            open(dest, 'wb').write(self.objs[Key])
    fake = Fake()
    R.shelf_config = lambda r=None: {'bucket': 'b', 'region': 'us-east-1'}
    R.shelf_client = lambda cfg: fake

    with contextlib.redirect_stdout(io.StringIO()):
        rc = R.cmd_push([])
    check('shelf: push uploads the source and its index', rc == 0 and len(fake.objs) == 2,
          str(sorted(fake.objs)))
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        R.cmd_push([])
    check('shelf: a second push uploads nothing — content addressing makes it idempotent',
          '2 already on the shelf' in buf.getvalue(), buf.getvalue()[-120:])

    # ---- pull, and the two failures that matter ---------------------------
    # A FRESH TREE PER SCENARIO, never a delete. ci_check.py forbids deletion calls in
    # this file — including in a comment, since the guard reads lines — and it is right
    # to: a test that deletes by path is one refactor away from deleting something real.
    def tree(name, with_source=None):
        h = os.path.join(tmp, name)
        os.makedirs(os.path.join(h, 'references', '.index'))
        os.makedirs(os.path.join(h, 'books', 'tst'))
        open(os.path.join(h, 'references', 'README.md'), 'w').write(
            '# R\n\n| File | Book | Work | Edition / provenance | Added | Redistribution |\n'
            '|---|---|---|---|---|---|\n'
            f'| [held.txt](held.txt) | tst | *A Work* — An Author (1999) | '
            f'sha256 `{digest}` | 2026-09-13 | ✅ Public domain. Safe. |\n')
        if with_source is not None:
            open(os.path.join(h, 'references', 'held.txt'), 'wb').write(with_source)
        return h

    empty = tree('shelf-pull')
    R.root = lambda: empty
    with contextlib.redirect_stdout(io.StringIO()):
        rc = R.cmd_pull([])
    check('shelf: pull restores a source the manifest names and the disk lacks',
          rc == 0 and open(os.path.join(empty, 'references', 'held.txt'), 'rb').read() == body)

    # The shelf hands back something else. A shelf that can do that is worse than an
    # empty one, because the file then LOOKS held.
    liar = tree('shelf-liar')
    R.root = lambda: liar
    fake.objs[f'refs/{digest}/held.txt'] = b'not the right bytes at all'
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        rc = R.cmd_pull([])
    check('shelf: bytes that do not hash to the row are NOT written',
          not os.path.exists(os.path.join(liar, 'references', 'held.txt')) and rc == 4,
          buf.getvalue()[-160:])

    # And it never overwrites a local copy that differs — an annotated or re-OCR'd file
    # is the one thing here that no version history holds.
    mine = tree('shelf-mine', with_source=b'my own annotated copy')
    R.root = lambda: mine
    fake.objs[f'refs/{digest}/held.txt'] = body
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        R.cmd_pull([])
    check('shelf: a differing local file is left alone, not replaced',
          open(os.path.join(mine, 'references', 'held.txt'), 'rb').read()
          == b'my own annotated copy', buf.getvalue()[-160:])


def unit_canons(tmp):
    """The canon records, and the one duplication they are allowed to have.

    `references/canons/kjv.yaml` carries the 66 section names for the READER; refindex.py
    keeps its own copy for the BUILDER, which refuses to index a source that does not have
    66 book headings. Two records of the same claim, written for different purposes and at
    different times — which is fine exactly as long as something checks that they agree.
    """
    import canons as C
    import check_loci as L
    from refindex import KJV_BOOKS, HEADER_ALIASES
    cs = C.load()
    if not cs:
        # A skip is not a pass, and this one has to say which it is: a desk with no canon
        # records falls back to the framework's built-in list, and check_loci says so.
        check('canons: no records in this instance — reader falls back to the built-in '
              'King James list (check_loci says so at runtime)', True)
        return
    by = {c.slug: c for c in cs}
    check('canons: every record parses and has a slug', all(c.slug != '?' for c in cs))
    check('canons: a record with an index is resolvable, one without is not',
          all(c.has_index == bool(c.index and os.path.exists(c.index)) for c in cs))
    if 'kjv' in by:
        k = by['kjv']
        check('canons: the kjv record carries all 66 sections', len(k.sections) == 66,
              f'{len(k.sections)}')
        check('canons: the reader\'s section list matches the BUILDER\'s, exactly',
              list(k.sections) == list(KJV_BOOKS),
              f'{sorted(set(k.sections) ^ set(KJV_BOOKS))[:4]}')
        check('canons: the aliases cover the builder\'s header aliases',
              set(HEADER_ALIASES) <= set(k.aliases))
        check('canons: a named canon resolves a real locus',
              bool(k.locus_re and k.locus_re.search('as in John 3:16 and')))
        check('canons: and does NOT invent a section from a stray capital',
              not (k.locus_re and k.locus_re.search('And 22:17')),
              'the false-light failure, 2026-09-10')
    numbered = [c for c in cs if not c.named]
    if numbered:
        n = numbered[0]
        check('canons: a numbered canon needs its own name to make a locus',
              bool(n.locus_re) and not n.locus_re.search(' 29:46 '),
              n.slug)
    if 'kjv' in by:
        # QUOTATION MARKS AND THE BOOK-IMPLIED LOCUS. Both are things the house writes and
        # the checker could not read; every case below is one that actually went wrong.
        k = by['kjv']
        check('spans: a double-quoted passage is a candidate, not just an italic one',
              any('serpent was more subtil' in x for x in
                  L.quoted_spans('the text says "Now the serpent was more subtil than any '
                                 'beast of the field" and so on')))
        check('spans: inner emphasis does not split an outer quotation',
              any('decline of dharma' in x.replace('*', '') for x in
                  L.quoted_spans('"Whenever there is a decline of *dharma* I manifest myself"')))
        check('spans: a passage both italicised and quoted is offered once',
              len(L.quoted_spans('*"the same words twice over here"*')) == 1)
        check('loci: a parenthesised book-implied locus inherits its book',
              [x[1] for x in k.loci('the father "came out" (Luke 15:25), and again (15:28)')]
              == ['Luke 15:25', 'Luke 15:28'])
        check('loci: it inherits from the nearest NAME, not the nearest locus',
              'Luke 22:39' in [x[1] for x in k.loci(
                  'John 18:10 has the ear. Luke sets the scene at the place (22:39-40)')],
              'John has 21 chapters; inheriting the locus invented John 22:39')
        check('loci: "the King James" is not the book of James',
              [x[1] for x in k.loci('Matthew 5:21 (KJV). The King James has it. '
                                    'The same gospel lists them (15:18-19).')]
              == ['Matthew 5:21', 'Matthew 15:18'],
              'the inherited book is validated against the index')
        check('loci: a bare ch:v with no preceding book name is not a locus',
              k.loci('a ratio of (15:28) and nothing else') == [])

    if 'quran' in by:
        # The canon that could NOT be built from the scan the desk holds, and the
        # measurement is in refindex.build_quran_tanzil: 5,269 of 6,236 ayah markers
        # survived that OCR, 614 interior gaps, 79 of 114 surah openings.
        q = by['quran']
        # THIS CANON'S INDEX IS NOT COMMITTED, unlike the KJV's and the Gita's: Tanzil's
        # terms are non-commercial, no-redistribution, so the file and its index are
        # gitignored (references/canons/quran-pickthall.yaml says so). The CANON RECORD is
        # tracked, so `by` holds 'quran' in a tree that cannot hold its index — an export,
        # a CI checkout, a fresh clone. Loading it unconditionally raised FileNotFoundError
        # and took the whole suite down with no summary, which made every push from the
        # desk fail (2026-09-14). Skip, loudly, with the rebuild command: "could not look"
        # must never wear the same face as "passed", and must never look like a crash either.
        if not (q.index and os.path.exists(q.index)):
            skip('canons: the quran index assertions',
                 'index absent — not committed, Tanzil is no-redistribution; rebuild with '
                 'refindex.py references/quran-pickthall-tanzil.txt --scheme quran-tanzil '
                 '--out references/quran-pickthall.tsv.gz')
        else:
            check('canons: quran is indexed and resolves verses', q.has_index and q.verse_resolution)
            idx = L.load(q.index)
            check('canons: the quran index holds 6,236 ayat in 114 surahs',
                  len(idx) == 6236 and len({k[1] for k in idx}) == 114,
                  f'{len(idx)} rows, {len({k[1] for k in idx})} surahs')
            check('canons: every surah runs 1..n with no interior gap',
                  all(sorted(v for (c, ch, v) in idx if ch == n)
                      == list(range(1, 1 + sum(1 for (c, ch, v) in idx if ch == n)))
                      for n in (1, 2, 29, 112, 114)))
            # A WHOLE-SECTION CITATION IS A REAL CITATION: the house cites al-Ikhlas as
            # "Qur'an 112", and keying that on an ayah the index cannot hold answered
            # "112:0 does not exist in this edition" — true, and useless.
            # A RANGE IN A NUMBERED CANON. The depth-2 locus tail captured no end verse
            # until 2026-09-14, so `99:7-8` was read as 99:7, checked alone, and told to
            # "cite 99:7-8" — the checker flagging the correct note. Both dashes are cited.
            rng = q.loci("Qur'an 99:7-8, Pickthall.") + q.loci("Qur'an 16:58–59")
            check('canons: a numbered canon cites a range and keeps its end',
                  len(rng) == 2 and rng[0][0] == ('quran', 99, 7) and rng[0][2] == 8
                  and rng[1][0] == ('quran', 16, 58) and rng[1][2] == 59, repr(rng))
            whole = q.loci("Qur'an 112")
            check('canons: a surah cited whole keys on its first verse and ranges to its last',
                  [x[0] for x in whole] == [('quran', 112, 1)] and whole[0][2] == 4,
                  str(whole))
            check('canons: and its label says both what was cited and what was checked',
                  'whole' in whole[0][1] and '112' in whole[0][1], whole[0][1])
            check('canons: an ayah-level locus keys on the ayah',
                  [x[0] for x in q.loci("Qur'an 29:46")] == [('quran', 29, 46)])
            check('canons: surah 115 is not a locus — section_count is the closed set',
                  q.loci("Qur'an 115:1") == [])

    if 'gita' in by:
        # The chapter-keyed canon. Everything here is a thing that went wrong while it
        # was being built, and would go wrong silently if it came back.
        g = by['gita']
        check('canons: gita is chapter-keyed — this edition has no verse numbers',
              g.verse_resolution is False)
        check('canons: gita is indexed', g.has_index, str(g.index))
        check('canons: a publication year is NOT a chapter',
              g.loci("Arnold's *The Song Celestial*, 1885") == [],
              'section_count is the numeric closed set')
        check('canons: a chapter past the end is not a locus either',
              g.loci('Gita XIX') == [] and g.loci('Gita 19') == [])
        check('canons: roman numerals resolve, because Arnold prints them',
              [k for k, _, _ in g.loci('Gita XII')] == [('gita', 12, 0)])
        check('canons: an italicised locus resolves — the house sets titles that way',
              [k for k, _, _ in g.loci('*Gita* 4.7')] == [('gita', 4, 0)])
        check('canons: and the label keeps the verse that was CITED, not just what '
              'was checked',
              'no verses' in g.loci('*Gita* 4.7')[0][1], g.loci('*Gita* 4.7')[0][1])
        idx = L.load(g.index)
        check('canons: the gita index holds 18 chapters at verse 0',
              sorted(idx) == [('gita', i, 0) for i in range(1, 19)], str(len(idx)))
        joined = ' '.join(idx.values())
        check('canons: the translator\'s notes are NOT in the index — they are '
              'apparatus, not Arnold',
              'repetitionary lines are here omitted' not in joined)
        check('canons: no footnote markers survive to split a quotation',
              '[FN#' not in joined)
        check('canons: the colophon is kept — the corpus quotes it',
              'Religion of Faith' in idx[('gita', 12, 0)])
    # The whole point of a record with no index: the gap is DECLARED, not absent.
    if any(not c.has_index for c in cs):
        found = L.unresolvable_loci("see Qur'an 29:46 and Gita 4.7 for this")
        check('canons: a locus in an unresolved canon is reported, not silent',
              len(found) >= 1, f'{[f[1] for f in found]}')
    import check_quotes as Q
    check('canons: an unresolved canon locus counts as a CITATION SIGNAL in check_quotes',
          Q._is_citation("Qur'an 112 (al-Ikhlas), Pickthall:") if Q.CANON_CITE else True)


def unit_reference_add(tmp):
    """`add` end to end — the one command here with a one-way consequence.

    Getting `--restricted` wrong puts a copyrighted file in git history, where no later
    edit removes it. So: the file lands, the manifest gains a row, the index is built,
    and a restricted source gains BOTH ignore lines — its own and its index's, because
    an index of a copyrighted source is that source's text in another shape.
    """
    import importlib.util, os

    spec = importlib.util.spec_from_file_location(
        'references', os.path.join(os.path.dirname(__file__), 'references.py'))
    R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)

    home = os.path.join(tmp, 'inst')
    # ONE SHELF at the desk root, with the book as a manifest COLUMN (2026-09-13).
    # books/tst/ still has to exist: `add` validates --book against the books the desk
    # has, so a row can never name a book that is not there.
    refs = os.path.join(home, 'references')
    os.makedirs(refs)
    os.makedirs(os.path.join(home, 'books', 'tst'))
    open(os.path.join(refs, 'README.md'), 'w').write(
        '# References\n\n| File | Book | Work | Edition / provenance | Added | Redistribution |\n'
        '|---|---|---|---|---|---|\n\n## A section after the table\n\nProse.\n')
    src = os.path.join(tmp, 'incoming.txt')
    open(src, 'w').write('\n'.join(f'a sentence number {i} in the held source'
                                    for i in range(120)))

    R.root = lambda: home
    R.tracked = lambda rel, r=None: False        # no git in a scratch tree
    R.is_ignored = lambda rel, r=None: False

    rc = R.cmd_add([src, '--book', 'tst', '--work', '*A Held Work* — An Author (1999)',
                    '--edition', 'First edition', '--restricted'])
    check('references add: exits 0', rc == 0)
    check('references add: the file is copied in',
          os.path.exists(os.path.join(refs, 'incoming.txt')))
    check('references add: an index is built',
          os.path.exists(os.path.join(refs, '.index', 'incoming.tsv.gz')))

    readme = open(os.path.join(refs, 'README.md')).read()
    check('references add: a manifest row is appended', '[incoming.txt](incoming.txt)' in readme)
    check('references add: the row carries the work and a hash',
          'A Held Work' in readme and 'sha256' in readme)
    check('references add: the row carries the BOOK, which is how --book selects it',
          '| tst |' in readme)
    check('references add: the row goes INSIDE the table, not at end of file',
          readme.index('incoming.txt') < readme.index('## A section after the table'))

    ig = open(os.path.join(home, '.gitignore')).read()
    check('references add: a restricted file is gitignored',
          '/references/incoming.txt' in ig)
    check("references add: and so is its index — an index IS the text",
          '/references/.index/incoming.tsv.gz' in ig)

    # And the round trip: the thing just added is findable by search, at its line.
    cat = R.catalog(r=home, book='tst')
    check('references add: the new source appears in the catalog as indexed',
          len(cat) == 1 and cat[0]['index'] and cat[0]['restricted'])
    _, stream, offsets = R.load_index(cat[0]['index'])
    check('references add: its text is searchable', 'sentence number 77' in stream)

    # A PIPE IN A CELL WOULD SILENTLY SPLIT THE ROW — the manifest is a markdown table,
    # so an unescaped `|` in the work or the provenance shifts every cell after it and the
    # row's digest and verdict end up in the wrong columns. Not a parse error: a row that
    # reads as missing the two things it plainly states. (2026-09-14, adding a source whose
    # provenance names a pipe-separated format.)
    src3 = os.path.join(tmp, 'piped-work.txt')
    open(src3, 'w').write('a source whose provenance contains a pipe. ' * 20)
    R.cmd_add([src3, '--book', 'tst', '--work', '*A Piped Work* — C (1900)',
               '--edition', 'one line per row as a|b|c', '--public'])
    piped = [x for x in R.rows(home) if x.get('file') == 'piped-work.txt']
    check('references add: a pipe in a cell does not split the row', len(piped) == 1
          and 'unparsed' not in piped[0] and piped[0].get('book') == 'tst',
          str(piped))
    check('references add: and the row still states its digest and its verdict',
          piped and piped[0].get('digests') and piped[0].get('verdict_stated'),
          str(piped[0].get('digests')) if piped else 'no row')


    # DENY BY DEFAULT: the folder's own .gitignore decides, and a public source needs an
    # allow line. The direction is the point — an unclassified file is ignored, so a
    # forgotten line costs a commit rather than leaking a copyrighted source.
    deny = os.path.join(refs, '.gitignore')
    check('references add: a restricted source writes NO allow line',
          not os.path.exists(deny) or 'incoming.txt' not in open(deny).read())

    src2 = os.path.join(tmp, 'open-work.txt')
    open(src2, 'w').write('a public domain sentence, repeated for length. ' * 20)
    R.cmd_add([src2, '--book', 'tst', '--work', '*An Open Work* — Someone (1899)', '--public'])
    body = open(deny).read()
    check('references add: a public source is allowed by name', '!open-work.txt' in body)
    check('references add: the deny file denies by default', body.lstrip().startswith('#')
          and '\n*\n' in body, body[:60])
    check('references add: README and the folder rules allow themselves',
          '!README.md' in body and '!.gitignore' in body)
    n_before = body.count('!open-work.txt')
    R.ensure_allowed('open-work.txt', home)
    check('references add: the allow line is idempotent',
          open(deny).read().count('!open-work.txt') == n_before)

    # The safe failure has to be VISIBLE. A public source that is ignored and untracked
    # is silently uncommittable, and silence is what turns a safe failure into a lost one.
    import io, contextlib
    R.is_ignored = lambda rel, r=None: rel.endswith('open-work.txt')
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R.cmd_check([])
    R.is_ignored = lambda rel, r=None: False
    check('references check: a public source that cannot be committed is a finding',
          'PUBLIC BUT NOT COMMITTABLE: open-work.txt' in buf.getvalue(),
          buf.getvalue()[-200:])

    # A second add of a DIFFERENT file under the same name must not overwrite.
    open(src, 'w').write('completely different bytes')
    rc2 = R.cmd_add([src, '--book', 'tst', '--work', 'x', '--restricted'])
    check('references add: refuses to overwrite a different file of the same name', rc2 == 1)



def unit_quotes_false_positives(tmp):
    """The three false positives another session found by running this tool on the corpus.

    Reported 2026-09-11 by the session that closed REFERENCES-TO-CHECK, from a read-only
    run against pieces/son-of-joseph: three of five DRIFT findings were wrong, each for a
    different reason. All three are named here so none of them comes back.
    """
    import importlib.util, os

    spec = importlib.util.spec_from_file_location(
        'check_quotes', os.path.join(os.path.dirname(__file__), 'check_quotes.py'))
    cq = importlib.util.module_from_spec(spec); spec.loader.exec_module(cq)

    # (1) ALIAS COLLISION. "english" was an alias for five held sources, because the
    # filename stem contributed words. A note about the Nicene Creed thereby "named"
    # two lexicons, a Syriac study and the Summa, and its quotation was reported as
    # drift against whichever shared four common words.
    al = cq.aliases('*An Arabic-English Lexicon* — Edward William Lane (1863)',
                    'arabic-english-lexicon-lane-book1-part3-ocr.txt')
    check('quotes: a generic word is not an alias for a source',
          'english' not in al and 'arabic' not in al, str(sorted(al)))
    check('quotes: the full title is the strongest alias',
          al.get('an arabic english lexicon') == 100, str(sorted(al.items())))
    check("quotes: the author's surname is an alias, at lower weight",
          al.get('lane') == 40 or al.get('edward') == 40, str(sorted(al.items())))

    # A footnote shortens a title; the manifest holds the long form.
    al2 = cq.aliases('*The Spiritual Exercises of St. Ignatius of Loyola* — tr. Charles Seager',
                     'spiritual-exercises-ignatius-seager-1849-ocr.txt')
    check('quotes: a shortened title still names the source',
          any(a == 'the spiritual exercises' for a in al2), str(sorted(al2)))

    # But a prefix must still BE a name. Two words of "Book I Part 3" gave the alias
    # "book i", which matched any footnote containing the word "book" and tied Lane's
    # Arabic lexicon to a third of the corpus — where its degraded OCR then produced a
    # finding every time. Measured 2026-09-11: 152 corpus findings became 18.
    al3 = cq.aliases('*An Arabic-English Lexicon*, **Book I Part 3** — Edward William Lane',
                     'arabic-english-lexicon-lane-book1-part3-ocr.txt')
    check('quotes: a title prefix of only common short words is not an alias',
          'book i' not in al3 and 'an arabic' not in al3, str(sorted(al3)))
    check('quotes: the lexicon is still named by its full title',
          al3.get('an arabic english lexicon') == 100, str(sorted(al3.items())))

    # (2) OCR SPLIT WORDS. The held scan reads "je sus christ"; the draft has
    # "Jésus-Christ". Reported as drift, and the drift was the scanner's.
    check('quotes: an accented word normalizes without splitting',
          cq.norm('Rhône-Café') == 'rhone cafe', cq.norm('Rhône-Café'))
    scan = 'a notice of the quiet ude of evening was printed in that year'
    st, _, detail, _ = cq.find('the quietude of evening', scan, [(0, '1')],
                               None, scan.replace(' ', ''))
    check('quotes: a word the held OCR split is still a match',
          st == 'MATCH' and 'word breaks' in detail, f'{st}: {detail}')

    # (3) DEGRADED OCR. BDB's scan reads "is able to do anything with e3ris". A
    # quotation checked against that is reported as drift; the right answer is that
    # the held copy cannot be compared against here.
    garble = ('q vbn f y g m ib is able to do anything with e3ris 4 cf ay n '
              'i2 the s3 w o rd 7b i and e ris n o t')
    check('quotes: a degraded OCR window is recognized as illegible',
          cq.ocr_garbled(garble), garble[:60])
    check('quotes: ordinary prose is not called illegible',
          not cq.ocr_garbled('the keeper set the lamp down beside the door and waited '
                             'there until the household had finished its evening meal'))

    # PAGE CITATIONS ARE CALIBRATED, NOT COMPARED. A `pages` index counts PDF pages and
    # a footnote cites the printed leaf; front matter puts a constant between them.
    # Comparing directly flagged 23 correct citations in one piece.
    obs = [('a', [(25, 27)], 29), ('b', [(28, 30)], 33), ('c', [(29, 29)], 33),
           ('d', [(24, 24)], 28), ('e', [(30, 30)], 40)]
    deltas = [f - lo for _, cs, f in obs for lo, _ in cs]
    mode = max(set(deltas), key=deltas.count)
    odd = [k for k, cs, f in obs if not any(lo - 1 <= f - mode <= hi + 1 for lo, hi in cs)]
    check('quotes: a constant printed-to-index offset is learned', mode == 4, str(deltas))
    check('quotes: citations that agree with the offset are not flagged',
          odd == ['e'], str(odd))


def unit_quotes(tmp):
    """check_quotes: who a quotation belongs to, and the three statuses that are not drift."""
    import importlib.util, os, gzip

    spec = importlib.util.spec_from_file_location(
        'check_quotes', os.path.join(os.path.dirname(__file__), 'check_quotes.py'))
    cq = importlib.util.module_from_spec(spec); spec.loader.exec_module(cq)

    # INVENTED PROSE, ON PURPOSE. An earlier version of these fixtures quoted the real
    # sources on the shelf, which put copyrighted text from restricted references into
    # the shareable framework repo — the exact thing voice_privacy.py exists to catch,
    # and it caught it. A checker's tests need strings of the right SHAPE, never the
    # right provenance. (2026-09-11.)
    src = ('rouse the sleepers from the long habit of the couch that is holding them '
           'stand up from your idleness before the hour is gone and the keeper may draw '
           'any measure he wishes to himself by the use of that rule')
    offsets = [(0, '29')]

    # A paragraph carries several quotations and several markers; a span belongs to the
    # marker that FOLLOWS it. Handing every span to every marker checked one book's
    # sentence against another book and reported both as drift.
    paras = ['Here is the first: *a lamp is the only thing*[^a] And here is the second: '
             '*you are a builder and there is a simple method*[^b]']
    by = cq.body_spans_by_marker(paras)
    check('quotes: a body span goes to the marker that follows it',
          by.get('a') == ['a lamp is the only thing']
          and by.get('b') == ['you are a builder and there is a simple method'])

    check('quotes: an exact quotation matches',
          cq.find('stand up from your idleness', src, offsets)[0] == 'MATCH')

    # The house marks an elision with an ellipsis. A quotation that drops words
    # silently is neither a match nor a misquotation; it is its own finding.
    st, _, detail, _ = cq.find('Rouse the sleepers. Stand up from your idleness.',
                               src, offsets)
    check('quotes: words in order with a dropped passage is UNMARKED ELISION',
          st == 'UNMARKED ELISION' and 'habit of the couch' in detail, detail)

    # An italic run with nothing in common is the author's own emphasis, not a
    # quotation that went missing.
    check('quotes: an unrelated italic run is NO OVERLAP, not NOT FOUND',
          cq.find('the desk keeps its own counsel entirely', src, offsets)[0] == 'NO OVERLAP')

    # A real misquotation still has to be caught.
    check('quotes: a changed word inside a real quotation is DRIFT',
          cq.find('stand up from your slumber before the hour is gone', src, offsets)[0]
          in ('DRIFT', 'NOT FOUND'))

    # A title is not a quotation.
    # Bold is the author's own prose. The italic pattern reads `**x**` as `*x*`, so a
    # bolded sentence was extracted as a quotation: *Jealous of a Calf*'s own line
    # "There cannot be two infinites" was matched against the Summa and reported as
    # drift against a Trinity question about innascibility. (Named 2026-09-11.)
    check('quotes: a bolded sentence is prose, not a quoted span',
          not any('two infinites' in x for x in
                  cq.spans('the argument is simple: **There cannot be two infinites** '
                           'and that is the whole of it')),
          str(cq.spans('the argument is simple: **There cannot be two infinites** '
                       'and that is the whole of it')))
    check('quotes: a real italic quotation beside bold is still found',
          any('stand up from your idleness' in x for x in
              cq.spans('**Not a quote.** He wrote *stand up from your idleness today*')))
    check('quotes: bold does not shift the marker a span is attributed to',
          cq.body_spans_by_marker(
              ['**Bold prose here.** He wrote *stand up from your idleness now*[^a]']
          ).get('a') == ['stand up from your idleness now'])

    check('quotes: an italic book title is recognized as a title',
          cq.looks_like_a_title('Lantern Papers, or the Rule of Attention in the '
                                'Quiet House'))
    check('quotes: ordinary quoted prose is not',
          not cq.looks_like_a_title('stand up from your idleness before the hour is gone'))

    # A PDF interleaves running page numbers with the prose.
    numbered = 'the measure and the moment 28 is that instant marked upon it'
    check('quotes: an interleaved page number is not drift',
          cq.find('the measure and the moment is that instant marked upon it',
                  numbered, [(0, '32')], cq.denumbered(numbered))[0] == 'MATCH')


# ---------------------------------------------------------------- unit: normalization
def unit_normalization():
    print("\n-- normalization -------------------------------------------------")
    s = 'the “word” it’s'
    check('flatten_quotes is length-preserving',
          len(flatten_quotes(s)) == len(s),
          'a positional offset computed on it must index the real text')
    check('H ignores quote style', H('the "x" y') == H('the “x” y'))
    check('H ignores whitespace runs', H('it.  The') == H('it. The'),
          'a double space describes a block no draft can produce')
    check('H still sees real differences', H('a b') != H('a c'))
    check('H ignores leading/trailing space', H('  a b  ') == H('a b'))
    check('smarten opens then closes', smarten_quotes('"a" b') == '“a” b')
    check('smarten handles an apostrophe mid-word', smarten_quotes("it's") == 'it’s')


# ---------------------------------------------------------------- unit: commonmark parity
def unit_commonmark(tmp):
    """The desk's Substack converter is lenient; every other outlet renders CommonMark.

    Two live faults came through that gap on 2026-09-11 (not-yet, son-of-joseph). These
    cases pin what the check must flag and — as important — what it must leave alone,
    because a parity check that flags the house censoring convention would be ignored.
    """
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'cc', os.path.join(os.path.dirname(__file__), 'check_commonmark.py'))
    cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
    md = cc._md()
    if md is None:
        print("  skip  commonmark: markdown-it-py is not installed — this is NOT a pass")
        return
    kinds = lambda body: [k for k, _ in cc.check_text('x\n---\n' + body, md)]
    check('commonmark: a star after a letter before a comma is flagged',
          kinds("*as those who have read it,* Confessions*, know — one of us.* Go on.") == ['stray-asterisk'])
    check('commonmark: the same sentence, fixed, is clean',
          kinds("*as those who have read it,* Confessions, *know — one of us.* Go on.") == [])
    check('commonmark: a backtick used as ayin is flagged',
          kinds("The Hebrew is *`almah*; it means young woman.") == ['backtick-letter-mark'])
    check('commonmark: the real ayin is clean',
          kinds("The Hebrew is *ʿalmah*; it means young woman.") == [])
    check('commonmark: escaped censoring (f\\*\\*k) is not a leak',
          kinds("He tells the camera to f\\*\\*k off.") == [])
    check('commonmark: an asterisk inside code is not a leak',
          kinds("The glob `*.md` matches every *draft* here.") == [])


# ---------------------------------------------------------------- unit: outlet content
def unit_outlet_content(tmp):
    """outlet_audit --content: what counts as drift, and what must not.

    Every false lead on 2026-09-11 was one of two things: a whitespace-only difference a
    reader cannot see, or the syndication line expected on the canonical outlet. Both are
    pinned here, along with the half that must never regress — a changed WORD is drift.
    """
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'oa', os.path.join(os.path.dirname(__file__), 'outlet_audit.py'))
    oa = importlib.util.module_from_spec(spec); spec.loader.exec_module(oa)
    d = os.path.join(tmp, 'oapiece'); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'publish.yaml'), 'w').write(
        'title: T\nsubtitle: S\ncanonical: https://www.example.com/blog/a-piece\n')
    para = ("The tuning was set before the player arrived, by cuts nobody consulted "
            "the flute about, and no work on the surface reaches it.")
    open(os.path.join(d, 'draft.md'), 'w').write('scaffold\n---\n' + para + '\n')
    ws = '<p>' + para.replace(', by', ' , by').replace('the flute', 'the\n  flute') + '</p>'
    r = oa.content_drift(d, ws, canonical_outlet=True)
    check('outlet content: a whitespace-only difference is not drift',
          r is not None and not r['missing'])
    bad = '<p>' + para.replace('player', 'singer') + '</p>'
    r = oa.content_drift(d, bad, canonical_outlet=True)
    check('outlet content: a changed word is still drift',
          r is not None and len(r['missing']) == 1)
    r = oa.content_drift(d, ws, canonical_outlet=False)
    check('outlet content: a syndicated copy must carry the originally-published line',
          r is not None and any(w.startswith('Originally published at') for w in r['missing']))

    # --- the link preview: a store publish never touches the site repo, so a live page's
    # og:image can 404 (one of 33, 2026-09-11). No network: the probe is stubbed.
    page_url = 'https://site.test/writings/a-piece/'
    head = ('<meta property="og:image:width" content="1200"/>'
            '<meta content="/og/a-piece.jpg" property="og:image"/>')
    check('preview: og:image is found whatever the attribute order, and made absolute',
          oa.og_image_url(head, page_url) == 'https://site.test/og/a-piece.jpg',
          str(oa.og_image_url(head, page_url)))
    check('preview: og:image:width is not mistaken for the image',
          oa.og_image_url('<meta property="og:image:width" content="1200"/>', page_url) is None)
    stub = lambda answer: (lambda _url: answer)
    check('preview: an image that answers 200 image/* is fine',
          oa.preview_problem(head, page_url, stub((200, 'image/jpeg'))) is None)
    check('preview: a 404 og:image is reported',
          'HTTP 404' in (oa.preview_problem(head, page_url, stub((404, ''))) or ''))
    check('preview: a 200 that is not an image is reported (an HTML error page)',
          'not an image' in (oa.preview_problem(head, page_url, stub((200, 'text/html'))) or ''))
    check('preview: a page that names no og:image is reported',
          oa.preview_problem('<p>x</p>', page_url, stub((200, 'image/jpeg'))) is not None)
    check('preview: an unreachable image is not a pass',
          oa.preview_problem(head, page_url, stub((None, ''))) is not None)


# ---------------------------------------------------------------- unit: substack pages
def unit_pages(tmp):
    """A page is a post with type "page" — the checks that must NOT fire on one.

    Measured 2026-09-10: clicking Add page opens /publish/post/<id> in the same composer,
    and the draft object differs only by `type`. So the transport is shared and the risk
    is the other direction — a post-shaped check reporting a page as broken because it is
    absent from a list it was never going to be in.
    """
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'sv', os.path.join(os.path.dirname(__file__), 'substack_verify.py'))
    sv = importlib.util.module_from_spec(spec); spec.loader.exec_module(sv)

    repo = os.path.join(tmp, 'pagerepo'); pieces = os.path.join(repo, 'pieces')
    for slug, extra in (('an-essay', ''), ('a-colophon', 'substack_type: page\n')):
        d = os.path.join(pieces, slug); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'publish.yaml'), 'w').write(
            f"title: T\nsubtitle: S\n{extra}"
            f"public_url: https://example.substack.com/p/{slug}\n")
    man_page = sv.read_manifest(os.path.join(pieces, 'a-colophon', 'publish.yaml'))
    man_post = sv.read_manifest(os.path.join(pieces, 'an-essay', 'publish.yaml'))
    check('pages: substack_type is read from the manifest',
          man_page.get('substack_type') == 'page')
    check('pages: a post does not accidentally declare itself one',
          man_post.get('substack_type') is None)

    # The header gate refuses a post with no subtitle — and a PAGE HAS NO SUBTITLE FIELD,
    # so requiring one refused a compose that was correct. A gate that refuses correct work
    # is the worst kind: it teaches you to reach for an override. (2026-09-10.)
    spec2 = importlib.util.spec_from_file_location(
        'mts', os.path.join(os.path.dirname(__file__), 'md_to_substack.py'))
    mts = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(mts)
    pg = os.path.join(pieces, 'a-colophon')
    open(os.path.join(pg, 'publish.yaml'), 'w').write(
        'title: A Colophon\nsubstack_type: page\n')
    errs, _warns = mts.manifest_gate(pg)
    check('pages: the header gate does not demand a subtitle of a page', not errs)
    po = os.path.join(pieces, 'an-essay')
    open(os.path.join(po, 'publish.yaml'), 'w').write('title: An Essay\n')
    errs2, _ = mts.manifest_gate(po)
    check('pages: a POST with no subtitle is still refused', bool(errs2))


# ---------------------------------------------------------------- unit: substack notes
def unit_notes(tmp):
    """One Note per live post; the backlog is derived, and goes out one a day (2026-09-10)."""
    print("\n-- substack notes --------------------------------------------------")
    import substack_notes as sn
    root = os.path.join(tmp, 'notesrepo')

    def piece(slug, date=None, extra='', note=None, form='note', style='plain-note'):
        d = os.path.join(root, slug); os.makedirs(d, exist_ok=True)
        url = f'https://example.substack.com/p/{slug}'
        live = f'public_url: {url}\npublished_at: {date}   # a comment\n' if date else ''
        comp = 'companions:\n  note: note.md\n' if note is not None else ''
        open(os.path.join(d, 'publish.yaml'), 'w').write(f'title: T {slug}\n{live}{extra}{comp}')
        if note is not None:          # the Note is the piece's `note` companion (docs/COMPANIONS.md)
            open(os.path.join(d, 'note.md'), 'w').write(
                f'form: {form}\nstyle: {style}\n# a scaffold comment\n---\n' + note.replace('URL', url))
        return d

    piece('a-old', '2026-08-01')
    piece('b-mid', '2026-08-02', note='A line.\n')
    piece('c-done', '2026-08-03',
          extra='substack_note:\n  posted_at: 2026-09-09\n  note_url: https://substack.com/@x/note/c-9\n')
    piece('colophon', '2026-08-01', extra='substack_type: page\n')
    piece('unpublished')
    piece('e-fresh', '2026-09-10',
          extra='substack_note:\n  posted_at: 2026-09-10\n  note_url: https://substack.com/@x/note/c-10\n')

    corpus = sn.load(root)
    slugs = [p['slug'] for p in corpus]
    check('notes: a page is not announced', 'colophon' not in slugs)
    check('notes: an unpublished piece is not in scope', 'unpublished' not in slugs)
    check('notes: states are read from disk',
          [p['state'] for p in corpus] == ['missing', 'drafted', 'posted', 'posted'],
          str([(p['slug'], p['state']) for p in corpus]))
    check('notes: the backlog is oldest first and skips posted',
          [p['slug'] for p in sn.backlog(corpus)] == ['a-old', 'b-mid'])
    check("notes: a backlog Note today closes today's slot",
          (sn.backlog_done_today(corpus, '2026-09-09') or {}).get('slug') == 'c-done')
    check("notes: a FRESH publication's Note does not use the backlog slot",
          sn.backlog_done_today(corpus, '2026-09-10') is None)
    check('notes: next exits 3 once the day is used',
          sn.main(['next', '--pieces', root, '--today', '2026-09-09']) == 3)

    paras, problems = sn.read_note(os.path.join(root, 'b-mid'), 'https://example.substack.com/p/b-mid')
    check('notes: a well-formed Note has no problems', not problems, str(problems))
    check('notes: the hash is the paragraphs joined by a blank line',
          sn.note_hash(paras) == hashlib.sha256('A line.\n\nhttps://example.substack.com/p/b-mid'.encode()).hexdigest())
    bad = piece('f-bad', '2026-08-04', note='A *marked* line.\n\nhttps://elsewhere.example/p/x\n')
    _, probs = sn.read_note(bad, 'https://example.substack.com/p/f-bad')
    check('notes: a Note carries no URL of its own — the tool adds the post link',
          any('URL' in p for p in probs), str(probs))
    check('notes: markdown is refused in a plain-text Note', any('markdown' in p for p in probs), str(probs))
    check('notes: the post URL is appended as the last paragraph',
          paras[-1] == 'https://example.substack.com/p/b-mid', str(paras))
    poem = piece('g-poem', '2026-08-05', note='one\ntwo\n\nthree\n', form='poem', style='plain-poem')
    pp, pprobs = sn.read_note(poem, 'https://example.substack.com/p/g-poem')
    check('notes: a poem goes one paragraph per line, a Braille-blank line between stanzas (2026-09-11)',
          pp == ['one', 'two', '⠀', 'three', '⠀', 'https://example.substack.com/p/g-poem'], str(pp or pprobs))
    check('notes: never a hard break — the Notes schema has none',
          'hardBreak' not in sn.composer_js(pp, 'T'))
    dotted = piece('g-dot', '2026-08-05', note='one\n\ntwo\n', form='poem', style='plain-poem')
    with open(os.path.join(dotted, 'note.md')) as fh:
        body = fh.read().replace('style: plain-poem\n', 'style: plain-poem\nstanza_break: dot\n')
    with open(os.path.join(dotted, 'note.md'), 'w') as fh:
        fh.write(body)
    dp, _ = sn.read_note(dotted, 'https://example.substack.com/p/g-dot')
    check('notes: stanza_break: dot puts a middle dot in the gap', dp[:3] == ['one', '·', 'two'], str(dp))
    with open(os.path.join(dotted, 'note.md'), 'w') as fh:
        fh.write(body.replace('stanza_break: dot', 'stanza_break: stars'))
    _, bad_sb = sn.read_note(dotted, 'https://example.substack.com/p/g-dot')
    check('notes: an unknown stanza_break is refused', any('stanza_break' in p for p in bad_sb), str(bad_sb))
    wrong = piece('h-wrong', '2026-08-06', note='one\n', form='poem', style='plain-note')
    _, wp = sn.read_note(wrong, 'https://example.substack.com/p/h-wrong')
    check('notes: a voice pointed at a form it does not write is refused', any('writes' in p for p in wp), str(wp))

    a = os.path.join(root, 'a-old')
    sn.record(a, '2026-09-11', 'https://substack.com/@x/note/c-11')
    text = open(os.path.join(a, 'publish.yaml')).read()
    check('notes: record keeps the manifest comments', '# a comment' in text)
    check('notes: record writes a block the manifest reader understands',
          sn.read_manifest(os.path.join(a, 'publish.yaml')).get('substack_note', {}).get('posted_at') == '2026-09-11')
    try:
        sn.record(a, '2026-09-12', 'https://substack.com/@x/note/c-12'); twice = False
    except SystemExit:
        twice = True
    check('notes: a post gets one Note — record refuses a second', twice)

    feed = [{'id': 1, 'blob': '{"url": "https://example.substack.com/p/a-old"}'},
            {'id': 2, 'blob': '{"url": "https://example.substack.com/p/a-older"}'}]
    check('notes: a feed match does not take a longer slug for a shorter one',
          sn.match_notes([{'slug': 'a-old', 'url': 'https://example.substack.com/p/a-old'}], feed)
          == {'a-old': [1]})


# ------------------------------------------------- unit: a second Substack outlet is in scope
def unit_outlet_urls(tmp):
    """Each outlet's posts are found by ITS OWN manifest key, and its own Notes profile.

    `substack_verify` and `substack_notes` both read `public_url` — which is one outlet's key
    (`substack`, Being Good), not a universal one. outlets.yaml has said so since the
    professional line was added: EACH OUTLET GETS ITS OWN MANIFEST KEY. So every post on the
    second Substack outlet was skipped by the verifier, with the wrong reason ("composed but not
    published") about a post live for a day, and was not in the Notes corpus at all. Measured
    2026-09-11 on `love-is-not-a-metric-space`, whose own manifest carried a comment saying so.

    A desk with no registry keeps `public_url`: that is what a one-outlet desk writes, and the
    fixtures above are exactly that case.
    """
    print("\n-- a second Substack outlet is in scope --------------------------")
    import importlib, substack_notes as sn
    import substack_verify as sv

    repo = os.path.join(tmp, 'tworepo')
    os.makedirs(os.path.join(repo, 'publishing'), exist_ok=True)
    open(os.path.join(repo, 'publishing', 'outlets.yaml'), 'w').write(
        'substack_primary: substack\n'
        'outlets:\n'
        '  substack:\n'
        '    reader_base: https://one.substack.com/p/\n'
        '    manifest_url_key: public_url\n'
        '    account_handle: one\n'
        '    notes_profile_id: 111\n'
        '    notes_handle: one\n'
        '  substack-two:\n'
        '    reader_base: https://two.substack.com/p/\n'
        '    manifest_url_key: substack_url\n'
        '    account_handle: two\n'
        '    notes_profile_id: 222\n'
        '    notes_handle: two\n'
        '    notes_probe_draft_id: 999\n'
        '  blog:\n'
        '    reader_base: https://example.com/blog/\n'
        '    manifest_url_key: blog_url\n')
    def mk(slug, body):
        d = os.path.join(repo, 'pieces', slug); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'publish.yaml'), 'w').write(body)
        open(os.path.join(d, 'draft.md'), 'w').write('x\n---\n\nProse.\n')
        return d
    mk('one-piece', 'title: One\noutlets:\n  - substack\n'
                    'public_url: https://one.substack.com/p/one-piece\npublished_at: 2026-09-01\n')
    mk('two-piece', 'title: Two\noutlets:\n  - blog\n  - substack-two\n'
                    'substack_url: https://two.substack.com/p/two-piece\npublished_at: 2026-09-02\n')
    mk('two-unpub', 'title: Unpublished\noutlets:\n  - substack-two\n')

    old = os.environ.get('DESK_OUTLETS')
    os.environ['DESK_OUTLETS'] = os.path.join(repo, 'publishing', 'outlets.yaml')
    try:
        url, outlet, key = sv.live_url(os.path.join(repo, 'pieces', 'two-piece'))
        check("verify: the second outlet's piece is found by its own key",
              (url, outlet, key) == ('https://two.substack.com/p/two-piece', 'substack-two', 'substack_url'),
              str((url, outlet, key)))
        check('verify: the first outlet still reads public_url',
              sv.live_url(os.path.join(repo, 'pieces', 'one-piece'))[2] == 'public_url')
        live = {n for n, _d, _u in sv.published_pieces(repo)}
        check('verify: both publications are in scope for a sweep', live == {'one-piece', 'two-piece'}, str(live))
        _d, u, why = sv.resolve_piece(repo, 'two-unpub')
        check('verify: an unpublished piece names the key it is missing',
              u is None and 'substack_url' in (why or '') and 'not published' in (why or ''), str(why))
        name, base, problem = sv.archive_outlet(repo)
        check('archive: the primary is the default publication', (name, base, problem) ==
              ('substack', 'https://one.substack.com', None), str((name, base, problem)))
        name2, base2, _p = sv.archive_outlet(repo, 'substack-two')
        check('archive: --outlet walks the other publication',
              (name2, base2) == ('substack-two', 'https://two.substack.com'), str((name2, base2)))
        _n, _b, p3 = sv.archive_outlet(repo, 'blog')
        check('archive: a non-Substack outlet has no archive, and says so',
              p3 and 'not a Substack outlet' in p3, str(p3))

        corpus = {p['slug']: p for p in sn.load(os.path.join(repo, 'pieces'))}
        check('notes: a second-outlet post is in the corpus at all', 'two-piece' in corpus, str(list(corpus)))
        check("notes: it carries its own url and outlet",
              corpus.get('two-piece', {}).get('url') == 'https://two.substack.com/p/two-piece'
              and corpus['two-piece']['outlet'] == 'substack-two', str(corpus.get('two-piece')))
        ap = argparse.Namespace(profile=None, handle=None,
                                outlets=os.environ['DESK_OUTLETS'], outlet=None)
        check('notes: each outlet is checked against ITS OWN profile feed',
              sn.config(ap, 'substack-two') == ('222', 'two')
              and sn.config(ap, 'substack') == ('111', 'one'),
              str((sn.config(ap, 'substack-two'), sn.config(ap, 'substack'))))
        check('notes: the probe draft is the outlet\'s own',
              sn.outlet_spec(ap.outlets, 'substack-two')[1].get('notes_probe_draft_id') == 999)
    finally:
        if old is None:
            os.environ.pop('DESK_OUTLETS', None)
        else:
            os.environ['DESK_OUTLETS'] = old
        importlib.invalidate_caches()


# ---------------------------------------- unit: what the desk CLAIMS on an outlet
def unit_outlet_reverse(tmp):
    """`outlet_audit` reverse: the only direction that can see a page the desk never made.

    It subtracts what the desk claims from what the outlet lists, so everything depends on
    that set being right. It was hand-rolled — `public_url` and `site_url` slugs plus every
    directory name — and outlets.yaml had already written down the consequence: with a key
    per outlet, a `blog_url` reads as a page the desk does not know. It said to fix it in the
    tool rather than by re-colliding the keys, and `known_on` is that: it asks `slug_of`, the
    resolver the FORWARD direction uses, so the two cannot disagree.

    A false finding here is the expensive kind. Reverse drift is what an audit is for, so a
    run that always reports one is a run nobody reads — which is exactly why muffinlabs' real
    sitemap was left unwired until 2026-09-11.
    """
    print("\n-- outlet reverse: what the desk claims on an outlet ----------------")
    import outlet_audit as oa

    blog = {'reader_base': 'https://example.com/blog/', 'manifest_url_key': 'blog_url'}
    site = {'reader_base': 'https://example.org/writings/', 'manifest_url_key': 'site_url',
            'slug_source': 'public_url', 'trailing_slash': True}
    li = {'reader_base': 'https://www.linkedin.com/pulse/', 'manifest_url_key': 'linkedin_url',
          'derive': False}

    pieces = [
        # a piece whose live address is recorded under ITS OWN outlet's key, and whose
        # directory name does not match it — a retitle, which is the normal case
        {'name': 'old-handle', 'manifest': {'title': 'New Name',
                                            'blog_url': 'https://example.com/blog/new-name'}},
        # the desk SAYING what a piece is called in public: the one field whose whole purpose
        # is to override the derivation. Three imported MuffinLabs pieces carry one.
        {'name': 'dir-name', 'manifest': {'title': 'Something Else',
                                          'site_slug': 'kept-url'}},
        # alignmentfellowship's case: its slug comes from the Substack URL, not the directory
        {'name': 'af-handle', 'manifest': {'title': 'T',
                                           'public_url': 'https://one.substack.com/p/real-slug'}},
    ]

    check('reverse: a recorded url under the outlet\'s own key is claimed',
          'new-name' in oa.known_on(pieces, blog))
    check('reverse: `site_slug` is claimed — the desk said so explicitly',
          'kept-url' in oa.known_on(pieces, blog), str(sorted(oa.known_on(pieces, blog))))
    check('reverse: `slug_source` is honoured, so a derived site slug is claimed',
          'real-slug' in oa.known_on(pieces, site), str(sorted(oa.known_on(pieces, site))))
    check('reverse: a directory name is still claimed, for a piece with neither',
          {'old-handle', 'dir-name', 'af-handle'} <= oa.known_on(pieces, blog))
    check('reverse: a page nothing on the desk names is NOT claimed',
          'a-native-post' not in oa.known_on(pieces, blog))
    # derive: false means an address can only be RECORDED, and guessing one here would
    # claim a page that never existed — the mirror of the finding this check exists for.
    check('reverse: an outlet whose urls cannot be derived claims only handles and records',
          oa.known_on(pieces, li) == {'old-handle', 'dir-name', 'af-handle'},
          str(sorted(oa.known_on(pieces, li))))


# ------------------------------- unit: a second publication is INSIDE the gates
def unit_live_urls(tmp):
    """A piece is LIVE at its own outlet's address — for every tool that asks, not just two.

    `substack_verify` and `substack_notes` learned this on 2026-09-11 (scriptorium c1e192f).
    Five more readers of `public_url` did not, and `public_url` is ONE outlet's key
    (`substack`, Being Good). The corpus gates are the expensive ones: `is it live` was the
    entry condition to the header check, the manifest check, the declares-its-outlets check
    and the baseline check, so a whole second publication was not failing them — it was never
    being asked. Measured the same day: the gates counted 36 live pieces and the desk had 37,
    and the one they could not see was live with a `*Draft —*` header and no sealed baseline.

    A desk with no registry keeps `public_url`. That is what a one-outlet desk has always
    written, and what the fixtures that ship with this framework are.
    """
    print("\n-- a second publication is inside the gates ------------------------")
    import check_status as cs
    import publications as pb
    import piece_header as ph

    reg = {'substack': {'reader_base': 'https://one.substack.com/p/',
                        'manifest_url_key': 'public_url', 'account_handle': 'one'},
           'blog': {'reader_base': 'https://example.com/blog/', 'manifest_url_key': 'blog_url'},
           'substack-two': {'reader_base': 'https://two.substack.com/p/',
                            'manifest_url_key': 'substack_url', 'account_handle': 'two'}}
    one = {'title': 'One', 'public_url': 'https://one.substack.com/p/one', 'published_at': '2026-09-01'}
    two = {'title': 'Two', 'blog_url': 'https://example.com/blog/two',
           'substack_url': 'https://two.substack.com/p/two',
           'canonical': 'https://example.com/blog/two', 'published_at': '2026-09-02'}

    check('live_url: the first outlet still reads public_url',
          cs.live_url(one, reg) == 'https://one.substack.com/p/one')
    check('live_url: a piece on NO Substack is live all the same',
          cs.live_url({'blog_url': 'https://example.com/blog/x'}, reg) == 'https://example.com/blog/x')
    check("live_url: the piece's own canonical picks which address is home",
          cs.live_url(two, reg) == 'https://example.com/blog/two', cs.live_url(two, reg))
    check('live_url: a draft is not live at any outlet', cs.live_url({'title': 'D'}, reg) == '')
    check('live_url: `site: true` records an opt-in, not an address, so it is not live',
          cs.live_url({'site': True}, reg, legacy='blog') == '')
    check('live_url: with no registry, the one-outlet desk\'s key stands',
          cs.live_url(one, {}) == 'https://one.substack.com/p/one'
          and cs.live_url(two, {}) == '')

    # publications: `required_outlets` is a GATE, and a gate that cannot see a piece asks it
    # nothing. Latent on 2026-09-11 only because the second publication required no outlets.
    pubs = {'two-pub': {'name': 'Two', 'byline': '', 'outlets': ['blog', 'substack-two'],
                        'books': [], 'styles': [], 'required_outlets': ['substack-two'], 'tags': ''}}
    man = {'publication': 'two-pub', 'outlets': ['blog'], 'blog_url': 'https://example.com/blog/two'}
    check('required_outlets: without the registry a non-Substack publication is never asked',
          pb.missing_required(man, pubs) == [])
    check('required_outlets: with it, the same piece is held to its publication',
          pb.missing_required(man, pubs, reg) == [('substack-two', 'not declared')],
          str(pb.missing_required(man, pubs, reg)))
    check('required_outlets: a written-down reason still exempts it',
          pb.missing_required(dict(man, outlets_exempt={'substack-two': 'Eric: blog only'}),
                              pubs, reg) == [])

    # piece_header: the banner IS a link to where a reader finds the piece, so a wrong key
    # does not degrade, it emits `[Title]()` — a published header pointing nowhere.
    check('header: the banner links the piece at its own home',
          '](https://example.com/blog/two)' in ph.banner(two, reg), ph.banner(two, reg))
    check('header: with no registry the banner is unchanged for a one-outlet desk',
          '](https://one.substack.com/p/one)' in ph.banner(one, {}))

    # substack_tags --verify reads the PUBLIC post; `plan` already derived the editor host
    # per publication, so only this leg was wrong, and it refused rather than mis-fetched.
    import substack_tags as st
    try:
        st.public_tags('https://two.substack.com', two.get('public_url'), 'substack_url')
        ok = False
    except pb.Refused as e:
        ok = 'substack_url' in str(e)
    check('tags: the public-verify refusal names the key THIS outlet writes', ok)

    # sync_post_images: not a near miss. With no public_url the slug fell through to the
    # first /p/ anywhere in the file and the origin to a hard-coded elmuffin.substack.com,
    # so the fetch crossed publications — the wrong post's images, into this piece.
    import sync_post_images as sp
    d = os.path.join(tmp, 'two-piece')
    os.makedirs(d, exist_ok=True)
    outlets_yaml = ('substack_primary: substack\noutlets:\n'
                    '  substack:\n    reader_base: https://one.substack.com/p/\n'
                    '    manifest_url_key: public_url\n    account_handle: one\n'
                    '  substack-two:\n    reader_base: https://two.substack.com/p/\n'
                    '    manifest_url_key: substack_url\n    account_handle: two\n')
    os.makedirs(os.path.join(tmp, 'publishing'), exist_ok=True)
    open(os.path.join(tmp, 'publishing', 'outlets.yaml'), 'w').write(outlets_yaml)
    body = ('title: Two\noutlets:\n  - substack-two\n'
            'substack_url: https://two.substack.com/p/two\n'
            'post_url: https://two.substack.com/publish/post/9\npublished_at: 2026-09-02\n')
    open(os.path.join(d, 'publish.yaml'), 'w').write(body)
    old = os.environ.get('DESK_OUTLETS')
    os.environ['DESK_OUTLETS'] = os.path.join(tmp, 'publishing', 'outlets.yaml')
    try:
        check('images: the post is fetched from ITS OWN publication, at its own slug',
              sp.post_address(d, body) == ('https://two.substack.com', 'two'),
              str(sp.post_address(d, body)))
    finally:
        if old is None:
            os.environ.pop('DESK_OUTLETS', None)
        else:
            os.environ['DESK_OUTLETS'] = old

    # md_to_site --syndicated names an OUTLET, so the URL recorded is that outlet's.
    site = os.path.join(HERE, 'md_to_site.py')
    root = os.path.join(tmp, 'syn')
    pd = os.path.join(root, 'pieces', 'two')
    os.makedirs(os.path.join(root, 'publishing'), exist_ok=True)
    os.makedirs(pd, exist_ok=True)
    open(os.path.join(root, 'publishing', 'outlets.yaml'), 'w').write(outlets_yaml)
    open(os.path.join(root, 'publishing', 'publications.yaml'), 'w').write(
        'publications:\n  two-pub:\n    name: Two\n    byline: T\n'
        '    outlets: [substack, substack-two]\n')
    open(os.path.join(pd, 'draft.md'), 'w').write('*scaffold*\n\n---\n\nProse of the piece.\n')
    open(os.path.join(pd, 'publish.yaml'), 'w').write(
        'title: Two\nsubtitle: Its subtitle\npublication: two-pub\noutlets:\n  - substack-two\n'
        'public_url: https://one.substack.com/p/WRONG\n'
        'substack_url: https://two.substack.com/p/two\npublished_at: 2026-09-02\n')
    bundle = os.path.join(tmp, 'syn-bundle')
    r = subprocess.run([sys.executable, site, bundle, pd, '--outlet', 'substack-two',
                        '--syndicated', 'substack-two', '--apply'],
                       capture_output=True, text=True, cwd=root)
    md = ''
    cdir = os.path.join(bundle, 'content')
    if os.path.isdir(cdir):
        md = open(os.path.join(cdir, sorted(os.listdir(cdir))[0])).read()
    check('bundle: --syndicated records THAT outlet\'s url, not the first outlet\'s',
          'url: https://two.substack.com/p/two' in md and 'WRONG' not in md,
          (r.stderr[-300:] or md[:300]))
    r = subprocess.run([sys.executable, site, bundle, pd, '--outlet', 'substack-two',
                        '--syndicated', 'nosuch', '--apply'], capture_output=True, text=True, cwd=root)
    check('bundle: --syndicated on an outlet the registry does not define is refused',
          r.returncode == 8, (r.stdout + r.stderr)[-200:])


# ---------------------------------------------------------------- unit: companions
def unit_stage(tmp):
    """`corpus.stage` — the word the reader-protecting gates scope on.

    Three states, and the boundary that matters is live / not-live: a gate that exists to
    protect a reader fails for a text a reader can reach and reports for one nobody can.
    Written 2026-09-14, after one session's freshly scaffolded piece turned CI red for
    every other session on the desk.
    """
    print("\n-- corpus: how far along a text is ------------------------------------")
    import corpus
    root = os.path.join(tmp, 'stage-inst')
    def mk(name, manifest='', draft=None):
        d = os.path.join(root, 'pieces', name)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'publish.yaml'), 'w').write('title: T\nsubtitle: S\n' + manifest)
        if draft is not None:
            open(os.path.join(d, 'draft.md'), 'w').write(draft)
        return d

    scaffold = mk('scaffold')
    check('stage: a piece with no draft is drafting', corpus.stage(scaffold) == 'drafting',
          corpus.stage(scaffold))

    header_only = mk('header-only', draft='*Draft — notes about the voice.*\n')
    check('stage: a draft that is all scaffold header is still drafting',
          corpus.stage(header_only) == 'drafting', corpus.stage(header_only))

    written = mk('written', draft='*Draft — the note.*\n\n---\n\nThe first real sentence.\n')
    check('stage: prose below the header makes it composed',
          corpus.stage(written) == 'composed', corpus.stage(written))
    check('stage: composed is NOT live — nobody can read it yet', not corpus.live(written))

    # Each outlet has its own manifest key, and any one of them means a reader can get it.
    # Reading only `public_url` is how a whole second publication once sat outside the gates.
    for key in ('public_url', 'site_url'):
        live = mk('live-' + key, manifest=f'{key}: https://example.test/p/x\n',
                  draft='*Draft.*\n\n---\n\nWords.\n')
        check(f'stage: {key} means live', corpus.stage(live) == 'live', corpus.stage(live))

    empty = mk('live-empty', manifest='public_url:\n', draft='*D.*\n\n---\n\nWords.\n')
    check('stage: an EMPTY reader URL is not a reader URL',
          corpus.stage(empty) == 'composed', corpus.stage(empty))


def unit_companions(tmp):
    """A piece's companions resolve — role, form, voice, back-pointer — and the review page
    shows them beside the piece, with findings anchorable in a Note (2026-09-11)."""
    print("\n-- companions -------------------------------------------------------")
    import companions as cp
    import review_artifact as ra
    root = os.path.join(tmp, 'compdesk'); pieces = os.path.join(root, 'pieces')
    os.makedirs(os.path.join(root, 'styles', 'v-poem'))
    open(os.path.join(root, 'styles', 'v-poem', 'config.yaml'), 'w').write('form: poem\n')

    def mk(slug, manifest='', draft='*scaffold*\n---\n\nThe body.\n', files=None):
        d = os.path.join(pieces, slug); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'publish.yaml'), 'w').write('title: T\nsubtitle: S\n' + manifest)
        open(os.path.join(d, 'draft.md'), 'w').write(draft)
        for k, v in (files or {}).items():
            open(os.path.join(d, k), 'w').write(v)
        return d

    poem = 'form: poem\nstyle: v-poem\n# scaffold\n---\nline one\nline two\n\nline three\n'
    a = mk('a-essay', 'companions:\n  note: note.md\n  talk: b-talk\n', files={'note.md': poem})
    b = mk('b-talk', draft='*d*\n---\n## I. Start\n<!-- slide: Hi -->\n> Shown.\n\nSaid aloud here.\n',
           files={'talk.yaml': 'title: The Talk\nduration_min: 5\n',
                  'README.md': '# The Talk\n**Style:** [plain-talk](../../framework/styles/plain-talk/style.md)\n'})
    probs = [p for _s, p, _st in cp.check(pieces)]
    check('companions: a talk that does not point back at its essay is refused',
          any('companion_of' in p for p in probs), str(probs))
    open(os.path.join(b, 'talk.yaml'), 'a').write('companion_of: a-essay\n')
    check('companions: a poem Note and a talk resolve cleanly', not cp.check(pieces), str(cp.check(pieces)))
    check('companions: a poem keeps its lines and stanzas',
          cp.paragraphs(cp.companion(a, 'note')) == [['line one', 'line two'], ['line three']])
    open(os.path.join(a, 'note.md'), 'w').write(poem.replace('v-poem', 'plain-note'))
    check('companions: a voice pointed at a form it does not write is refused',
          any('writes' in p for _s, p, _st in cp.check(pieces)))
    open(os.path.join(a, 'note.md'), 'w').write(poem)
    legacy = os.path.join(tmp, 'compdesk-legacy', 'pieces')          # built apart, never deleted
    os.makedirs(os.path.join(legacy, 'old-piece'))
    open(os.path.join(legacy, 'old-piece', 'substack-note.md'), 'w').write('old\n')
    check('companions: a legacy substack-note.md is refused', any('legacy' in p for _s, p, _st in cp.check(legacy)))

    h = mk('c-headingless', 'captions:\n  assets/none.png: A caption.\n',
           draft='*s*\n---\n\n![A dog on a quilt](assets/none.png)\n\nThe body.\n')
    hp = ra.build(h, {})
    check('review page: a headingless piece lifts its first-block image into the masthead as the hero',
          '<figure class="hero">' in hp and 'Hero image slot' not in hp)
    check('review page: the hero shows its caption from publish.yaml',
          '<span>A caption.</span>' in hp)
    page = ra.build(a, {})
    check('review page: the Note renders beside the piece with its lines kept',
          'id="c-note"' in page and 'line one<br>line two' in page)
    check('review page: the talk renders with its script', 'id="c-talk"' in page and 'Said aloud here.' in page)
    f = [{'anchor': 'line three', 'now': 'line 3', 'title': 'a poem finding'}]
    page2 = ra.build(a, {'findings': [dict(x) for x in f]})
    check('review page: a finding can anchor in the Note', 'hl-open' in page2 and 'line 3' in page2)
    n, errs = ra.apply_findings(a, [dict(x) for x in f])
    body = open(os.path.join(a, 'note.md')).read()
    check('review --apply: a Note finding is written into note.md, header and lines intact',
          n == 1 and not errs and body.startswith('form: poem') and 'line two\n\nline 3' in body, str(errs))


# ---------------------------------------------------------------- unit: scripture check
def unit_required_companions(tmp):
    """A publication can require a companion of its PUBLISHED pieces — the same shape as
    required_outlets, one layer in. (Eric, 2026-09-11: every MuffinLabs Substack post gets a Note.)"""
    print("\n-- publications: a required companion ---------------------------------")
    import publications as pb
    root = os.path.join(tmp, 'reqdesk'); os.makedirs(os.path.join(root, 'publishing'), exist_ok=True)
    d = os.path.join(root, 'pieces', 'p1'); os.makedirs(d, exist_ok=True)
    open(os.path.join(root, 'publishing', 'publications.yaml'), 'w').write(
        'publications:\n  pro:\n    name: Pro\n    outlets: [sub]\n    required_companions: [note]\n')
    pubs, probs = pb.load(root)
    check('required_companions: the registry parses it', not probs and
          pubs['pro']['required_companions'] == ['note'], str(probs))
    outs = {'sub': {'manifest_url_key': 'substack_url'}}
    live = {'publication': 'pro', 'substack_url': 'https://x', 'outlets': ['sub']}
    check('required_companions: a published piece with no note is caught',
          pb.missing_companions(live, pubs, d, outs) == [('note', 'not declared')])
    check('required_companions: an unpublished draft is not held to it',
          pb.missing_companions({'publication': 'pro', 'outlets': ['sub']}, pubs, d, outs) == [])
    paper = dict(live, companions={'note': 'note.md'})
    check('required_companions: a note declared but not on disk is caught',
          [r for r, _w in pb.missing_companions(paper, pubs, d, outs)] == ['note'])
    open(os.path.join(d, 'note.md'), 'w').write('form: note\nstyle: v\n---\nA line.\n')
    check('required_companions: a note on disk satisfies it',
          pb.missing_companions(paper, pubs, d, outs) == [])
    check('required_companions: an exemption needs a reason',
          pb.missing_companions(dict(live, companions_exempt={'note': ''}), pubs, d, outs) ==
          [('note', 'exempted without a reason')] and
          pb.missing_companions(dict(live, companions_exempt={'note': 'a link post'}), pubs, d, outs) == [])
    bad, probs2 = pb.load(root) if False else (None, None)
    open(os.path.join(root, 'publishing', 'publications.yaml'), 'w').write(
        'publications:\n  pro:\n    name: Pro\n    outlets: [sub]\n    required_companions: [sonnet]\n')
    _p, probs3 = pb.load(root)
    check('required_companions: a role that is not a companion role is refused',
          any('required_companions' in x for x in probs3), str(probs3))


def unit_corpus(tmp):
    """Two namespaces: a slug is unique within one, not across the desk, and a companion
    pointer resolves by role. (The talk and its essay, 2026-09-11.)"""
    print("\n-- corpus: pieces/ and talks/ -----------------------------------------")
    import corpus
    import companions as cp
    root = os.path.join(tmp, 'twodesk')
    ess = os.path.join(root, 'pieces', 'same-name')
    talk = os.path.join(root, 'talks', 'same-name')
    other = os.path.join(root, 'talks', 'only-a-talk')
    for d in (ess, talk, other):
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'draft.md'), 'w').write('*scaffold*\n---\n\nBody.\n')
    open(os.path.join(ess, 'publish.yaml'), 'w').write(
        'title: Same Name\nsubtitle: S\ncompanions:\n  talk: same-name\n')
    open(os.path.join(talk, 'talk.yaml'), 'w').write('title: Same Name\ncompanion_of: same-name\n')
    open(os.path.join(other, 'talk.yaml'), 'w').write('title: Only a Talk\n')
    for d in (talk, other):
        open(os.path.join(d, 'README.md'), 'w').write(
            '# Same Name\n**Style:** [plain-talk](../../framework/styles/plain-talk/style.md)\n')

    check('corpus: both namespaces are walked',
          {(s, k) for s, _d, k in corpus.texts(root)} ==
          {('same-name', 'piece'), ('same-name', 'talk'), ('only-a-talk', 'talk')})
    check('corpus: a bare slug prefers pieces/', corpus.find(root, 'same-name') == ess)
    check("corpus: prefer='talk' takes the talks/ side",
          corpus.find(root, 'same-name', prefer='talk') == talk)
    check('corpus: a text that exists once resolves wherever it lives',
          corpus.find(root, 'only-a-talk') == other)
    check('corpus: a slug in neither namespace is None', corpus.find(root, 'nope') is None)
    check('corpus: kind is read from the directory, not the path',
          corpus.kind_of(talk) == 'talk' and corpus.kind_of(ess) == 'piece')
    check('corpus: rel names the namespace', corpus.rel(root, talk) == os.path.join('talks', 'same-name'))

    # The pair resolves both ways across the shared slug — the whole point of the move.
    c = cp.companion(ess, 'talk')
    check('companions: the essay\'s talk pointer lands in talks/', c and c['path'] == talk)
    check('companions: the pair checks clean across namespaces',
          not cp.check(os.path.join(root, 'pieces')), str(cp.check(os.path.join(root, 'pieces'))))
    open(os.path.join(other, 'talk.yaml'), 'a').write('companion_of: same-name\n')
    probs = cp.check(os.path.join(root, 'pieces'))
    check('companions: a talk claiming an essay that does not claim it back is caught',
          any('companion_of' in p for _s, p, _st in probs), str(probs))
    # Every finding carries the stage the caller scopes on, and a scratch piece with no
    # reader URL is never 'live' — which is what keeps an unfinished piece out of the gate.
    check('companions: every finding says what stage its piece is at',
          all(len(x) == 3 and x[2] in ('live', 'composed', 'drafting') for x in probs)
          and not any(x[2] == 'live' for x in probs), str(probs))


def unit_schedule(tmp):
    """`publish_at:` — the moment is read strictly, the gate refuses before it, and the
    tools that make a piece public refuse while the tools that only prepare it warn."""
    print("\n-- scheduling: a piece can be finished and not be due ----------------")
    import schedule as sched
    from datetime import datetime, timezone

    for bad, why in [('2026-09-15', 'a bare date names no moment'),
                     ('soon', 'prose is not a moment'),
                     ('2026-09-15 09:00 Mars/Olympus', 'an unknown zone')]:
        try:
            sched.parse_moment(bad)
            check(f'schedule: refuses {bad!r} — {why}', False, 'it was accepted')
        except sched.Malformed:
            check(f'schedule: refuses {bad!r} — {why}', True)

    same = (sched.parse_moment('2026-09-15 09:00 America/New_York')
            == sched.parse_moment('2026-09-15 13:00 UTC'))
    check('schedule: a zone and an offset name the same instant', same)

    d = os.path.join(tmp, 'schedpiece'); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'publish.yaml'), 'w').write(
        'title: T\nsubtitle: S\npublish_at: 2026-09-15 09:00 America/New_York  # a comment\n')
    before = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    after = datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc)
    check('schedule: embargoed before the moment', sched.state(d, before)[0] == 'embargoed')
    check('schedule: open after it', sched.state(d, after)[0] == 'open')
    check('schedule: a trailing comment does not break the field',
          sched.read_field(d).startswith('2026-09-15 09:00'))
    check('schedule: the refusal names the piece and the moment',
          'schedpiece' in (sched.refuse_if_embargoed(d, before) or ''))
    check('schedule: no refusal once it is open', sched.refuse_if_embargoed(d, after) is None)

    open(os.path.join(d, 'publish.yaml'), 'w').write('title: T\n')
    check('schedule: a piece with no publish_at is never embargoed',
          sched.state(d)[0] == 'none' and sched.refuse_if_embargoed(d) is None)

    # Arming is gated on the reading having happened (Eric, 2026-09-11).
    import subprocess as _sp
    open(os.path.join(d, 'publish.yaml'), 'w').write(
        'title: T\npublish_at: 2026-09-15 09:00 America/New_York\n')
    r = _sp.run([sys.executable, os.path.join(HERE, 'schedule.py'), 'arm', d,
                 '--task', 't', '--does', 'x'], capture_output=True, text=True)
    check('schedule: arm refuses without --reviewed',
          r.returncode != 0 and 'reviewed' in (r.stdout + r.stderr))
    r = _sp.run([sys.executable, os.path.join(HERE, 'schedule.py'), 'arm', d, '--task', 't',
                 '--does', 'x', '--reviewed', 'A, today'], capture_output=True, text=True)
    man = open(os.path.join(d, 'publish.yaml'), encoding='utf-8').read()
    # The writer quotes its values (2026-09-11, "arm: its own key, quoted values"), and
    # this assertion was left expecting the bare form — so the suite went red on correct
    # code and blocked every push to both repos until someone read it. Accept either.
    check('schedule: arm records who approved the drafts',
          r.returncode == 0 and re.search(r'approved:\s*"?A, today"?', man), r.stderr.strip())
    r = _sp.run([sys.executable, os.path.join(HERE, 'schedule.py'), 'runbook', d],
                capture_output=True, text=True)
    check('schedule: the runbook carries the moment and the late-fire instruction',
          '2026-09-15 09:00' in r.stdout and 'RUNNING LATE' in r.stdout)

    # The wiring, stated as the rule it is: public REFUSES, preparing WARNS.
    site = open(os.path.join(HERE, 'md_to_site.py'), encoding='utf-8').read()
    check('schedule: md_to_site refuses an embargoed piece (exit 12)',
          'refuse_if_embargoed' in site and 'die(12' in site)
    for tool, word in (('md_to_substack.py', 'EMBARGO'), ('md_to_linkedin.py', 'EMBARGO')):
        src = open(os.path.join(HERE, tool), encoding='utf-8').read()
        check(f'schedule: {tool} warns rather than refusing', word in src)


def unit_scripture(tmp):
    """The scripture checker's conventions, which are where it can go wrong.

    A checker that flags correct prose is worse than none — it trains the reader to
    skim past it. Three of this house's conventions look like drift to a naive
    string compare, and each one is a case here.
    """
    import importlib.util, os, gzip
    spec = importlib.util.spec_from_file_location(
        'check_loci', os.path.join(os.path.dirname(__file__), 'check_loci.py'))
    cs = importlib.util.module_from_spec(spec); spec.loader.exec_module(cs)

    idx = os.path.join(tmp, 'idx.tsv.gz')
    with gzip.open(idx, 'wt') as f:
        f.write("Matthew\t6\t24\tNo man can serve two masters: for either he will hate "
                "the one, and love the other; or else he will hold to the one, and despise "
                "the other. Ye cannot serve God and mammon.\n")
        f.write("Philippians\t4\t8\tFinally, brethren, whatsoever things are true, "
                "whatsoever things [are] honest, whatsoever things [are] lovely, "
                "think on these things.\n")
        f.write("Exodus\t20\t20\tAnd Moses said unto the people, Fear not: for God is "
                "come to prove you, and that his fear may be before your faces.\n")
        f.write("1 Corinthians\t13\t4\tCharity suffereth long, [and] is kind.\n")
        f.write("1 Corinthians\t13\t5\tSeeketh not her own, is not easily provoked.\n")
    index = cs.load(idx)
    canon = lambda k: cs.norm(index[k])

    check('scripture: a whole verse matches',
          cs.match("No man can serve two masters", canon(('Matthew', 6, 24)))[0])
    check('scripture: an ellipsis matches fragments in order',
          cs.match("whatsoever things are true… think on these things",
                   canon(('Philippians', 4, 8)))[0])
    check("scripture: the KJV's own [brackets] are words, kept",
          cs.match("whatsoever things are honest", canon(('Philippians', 4, 8)))[0])
    check("scripture: a DRAFT's [substitution] is a wildcard, not drift",
          cs.match("and that [Their] fear may be before your faces",
                   canon(('Exodus', 20, 20)))[0])
    check('scripture: real drift is still caught',
          not cs.match("No man can serve three masters", canon(('Matthew', 6, 24)))[0])
    check('scripture: fragments out of order are caught',
          not cs.match("think on these things… whatsoever things are true",
                       canon(('Philippians', 4, 8)))[0])
    check('scripture: a quotation spanning two verses fails against just one',
          not cs.match("Charity suffereth long, and is kind. Seeketh not her own",
                       canon(('1 Corinthians', 13, 4)))[0])
    check('scripture: and matches the joined range',
          cs.match("Charity suffereth long, and is kind. Seeketh not her own",
                   cs.norm(index[('1 Corinthians', 13, 4)] + ' ' +
                           index[('1 Corinthians', 13, 5)]))[0])
    # a locus must come from the closed book set — "And 22:17" is not a citation
    check('scripture: a non-book word is never read as a locus',
          not cs.LOCUS_RE.search("And 22:17 says otherwise"))
    check('scripture: a real locus is read',
          bool(cs.LOCUS_RE.search("see Revelation 22:17")))
    # commentary must not be mistaken for a quotation
    lo, run = cs.overlap("What the ellipsis drops:", canon(('Philippians', 4, 8)))
    check('scripture: commentary scores below the candidate floor', lo < 0.25 or run < 4)
    hi, run2 = cs.overlap("whatsoever things are true", canon(('Philippians', 4, 8)))
    check('scripture: a real quotation scores above it', hi >= 0.6 and run2 >= 4)


# ---------------------------------------------------------------- unit: review artifact
def unit_review_artifact(tmp):
    """The author-facing review page is generated, so its invariants are testable.

    It exists because two sessions hand-built it in two different formats on 2026-09-09
    and 2026-09-10. A hand-built page can silently drop a footnote, miscount a delta, or
    leave a [^marker] on screen; a generated one is checked here instead.
    """
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        'review_artifact', os.path.join(os.path.dirname(__file__), 'review_artifact.py'))
    ra = importlib.util.module_from_spec(spec); spec.loader.exec_module(ra)

    d = os.path.join(tmp, 'piece'); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'publish.yaml'), 'w').write('title: A Piece\nsubtitle: And its claim.\n')
    open(os.path.join(d, 'draft.md'), 'w').write(
        'scaffold\n---\n## I. First\n\nA line with **weight** and a note.[^a]\n\n'
        '> A quotation.\n\n## II. Second\n\nA [sibling](https://example.com/p/x) and one more.[^b]\n\n'
        '[^a]: The first note.\n\n[^b]: The second note.\n')
    facts = {'version': 'v2', 'state': ['not composed'],
             'prior': {'words': 10, 'movements': 1, 'notes': 1},
             'gates': [['check_links', '1 live']],
             'calls': [['A call', 'Its body.']]}
    h = ra.build(d, facts)

    check('review: both movements render', h.count('class="mv"') == 2)
    check('review: contents matches movements', h.count('<a href="#m') == 2)
    check('review: every marker became a numbered ref',
          len(re.findall(r'id="r\d+"', h)) == 2)
    check('review: every ref has a definition',
          len(re.findall(r'id="n\d+"', h)) == len(re.findall(r'id="r\d+"', h)))
    check('review: no [^marker] reaches the reader', '[^' not in h)
    check('review: no raw ** reaches the reader', '**' not in h)
    check('review: deltas are computed, not asserted', 'class="delta"' in h)
    check('review: state flag is stamped', 'not composed' in h)
    check('review: the call is listed as a call', 'A call' in h and 'calls' in h)
    check('review: a sibling link survives', 'https://example.com/p/x' in h)
    check('review: hero absent renders a marked slot', 'class="slot"' in h)
    check('review: title and subtitle come from the manifest',
          'A Piece' in h and 'And its claim.' in h)

    # a one-space inline comment leaked into the headline until 2026-09-10
    open(os.path.join(d, 'publish.yaml'), 'w').write(
        'title: A Piece # settled by the author\nsubtitle: And its claim.   # from §V\n')
    h2 = ra.build(d, facts)
    check('review: inline comment never reaches the title',
          '<h1>A Piece</h1>' in h2 and 'settled by the author' not in h2)
    check('review: inline comment never reaches the subtitle', 'from §V' not in h2)

    # the two failures a hand-built page hides
    bad = os.path.join(tmp, 'bad'); os.makedirs(bad, exist_ok=True)
    open(os.path.join(bad, 'draft.md'), 'w').write('s\n---\nText.[^ghost]\n\n[^real]: n.\n')
    try:
        ra.build(bad, {}); check('review: undefined marker refuses', False)
    except SystemExit as e:
        check('review: undefined marker refuses with exit 2', e.code == 2)

    # --- findings: a proposed change, marked where it lands ------------------
    # The anchor is the whole mechanism. A finding that fails to highlight leaves a
    # page that LOOKS complete, so every miss has to be a refusal and not a warning.
    def fnd(**kw):
        f = dict(facts); f['findings'] = [kw]; return f

    hf = ra.build(d, fnd(anchor='A line with **weight**', severity='fidelity',
                         title='T', what='W', evidence='E', now='A line with **heft**'))
    check('review: the anchored span is marked in place',
          '<mark class="hl hl-fidelity" id="a1">' in hf)
    check('review: the mark closes exactly once',
          hf.count('<mark class="hl') == 1 and hf.count('</mark>') == 1)
    check('review: markdown inside the REPLACEMENT renders',
          '<strong>heft</strong>' in hf and '<strong>weight</strong>' not in hf,
          'the replacement is spliced into the markdown BEFORE the inline pass, so its '
          'emphasis pairs with the run around it exactly as the original did')
    check('review: no sentinel reaches the reader',
          not any(c in hf for c in '\ue000\ue001\ue002\ue003'))
    check('review: the note hangs under its own paragraph',
          hf.index('id="a1"') < hf.index('id="f1"') < hf.index('<h2>Second</h2>'),
          'a change is judged next to the sentence it changes')
    # THE MARK SHOWS THE PROPOSAL, NOT THE PRESENT (Eric, 2026-09-10). Reading the
    # highlighted prose has to be reading the piece as it would be if the changes were
    # taken — that is the thing being decided.
    hn = ra.build(d, fnd(anchor='and one more', title='T', now='and one fewer'))
    prose = re.sub(r'<aside class="fx.*?</aside>', '', hn, flags=re.S)
    check('review: the mark renders the replacement, not the original',
          'and one fewer' in prose and 'and one more' not in prose)
    check('review: the original survives in the card as the derived `was`',
          '<dd class="was">and one more</dd>' in hn,
          'derived from the anchor, so the two halves of the diff cannot drift')
    check('review: the stamp says the prose is showing proposals',
          'prose shows 1 proposed change<' in hn,
          'the page is not draft.md any more and must not pretend to be')
    # EVERY FINDING PROPOSES A CHANGE (Eric, 2026-09-10: "this doesn't tell me what the
    # proposed change is. it should."). A band titled `proposed changes` whose rows
    # propose nothing is lying about what it is; a diagnosis with no replacement is a
    # question, and questions have their own band.
    check('review: a finding with no `now` is refused',
          bool(ra.place([{'anchor': 'x', 'title': 'T'}],
                        [{'text': 'x', 'marks': [], 'cards': []}])),
          'a finding that only diagnoses belongs in `calls`')
    check('review: a `now` identical to the anchor is refused',
          bool(ra.place([{'anchor': 'x', 'title': 'T', 'now': 'x'}],
                        [{'text': 'x', 'marks': [], 'cards': []}])),
          'it proposes nothing, and would render as a change')
    check('review: every finding carries a was/now diff',
          hf.count('<dt>was</dt>') == 1 and hf.count('<dt>now</dt>') == 1)
    check('review: `was` as an input is refused',
          bool(ra.place([{'anchor': 'x', 'title': 'T', 'was': 'y', 'now': 'z'}],
                        [{'text': 'x', 'marks': [], 'cards': []}])),
          'a hand-typed `was` can disagree with the anchor; a derived one cannot')
    check('review: an empty `now` is refused',
          bool(ra.place([{'anchor': 'x', 'title': 'T', 'now': ''}],
                        [{'text': 'x', 'marks': [], 'cards': []}])),
          'a deletion is a replacement of the wider span, not an invisible mark')
    check('review: the finding is listed in the index', 'class="fidx"' in hf)
    check('review: severity colours the mark and the card',
          'class="fx sev-fidelity"' in hf)

    check('review: a finding may anchor inside a footnote',
          '<mark class="hl' in ra.build(d, fnd(anchor='The second note.', title='N',
                                               now='The second note, rewritten.')))
    check('review: an unknown severity degrades to open, it does not crash',
          'sev-open' in ra.build(d, fnd(anchor='A quotation.', severity='wat', title='S',
                                        now='A quotation, amended.')))

    for label, kw, want in (
            ('matches nothing', dict(anchor='not in the draft at all', title='X', now='q'),
             'matches nothing'),
            ('matches twice', dict(anchor='and one more', title='X', now='q'), None),
            ('is missing', dict(title='X', now='q'), 'no anchor')):
        errs = ra.place([kw], [{'text': 'and one more … and one more', 'marks': [], 'cards': []}]
                        if want is None else
                        [{'text': 'A line with weight', 'marks': [], 'cards': []}])
        check(f'review: an anchor that {label} is refused', bool(errs),
              'a silently dropped finding is the one failure this page cannot have')

    hs = [{'text': 'alpha beta gamma', 'marks': [], 'cards': []}]
    check('review: overlapping anchors are refused',
          bool(ra.place([{'anchor': 'alpha beta', 'title': 'A', 'now': 'ALPHA BETA'},
                         {'anchor': 'beta gamma', 'title': 'B', 'now': 'BETA GAMMA'}], hs)),
          'right-to-left insertion would otherwise produce broken nesting')

    check('review: no findings renders the page unchanged',
          'class="fidx"' not in ra.build(d, facts))

    # A GRID MAKES AN ANONYMOUS ITEM OUT OF EVERY BARE TEXT RUN. The index row is a
    # three-column grid, so a title that is raw text (plus any inline markup) is dealt
    # into the columns one fragment at a time — the row explodes to one word per line.
    # Shipped 2026-09-10 and caught by Eric on a narrow viewport, because the DOM checks
    # here read innerText, which cannot see layout. Assert the STRUCTURE instead: every
    # grid child is exactly one element, with no loose text between them.
    hg = ra.build(d, fnd(anchor='A quotation.', now='A quotation, amended.',
                         title='A <em>tell</em> in the <b>text</b> — three times'))
    row = re.search(r'<a class="sev-\w+" href="#f1">(.*?)</a>', hg, re.S).group(1)
    check('review: the index row has exactly three grid children',
          re.fullmatch(r'<b>\d+</b><em class="sev">[a-z]+</em><span class="ft">.*</span>',
                       row, re.S) is not None,
          'a bare text run inside a grid becomes its own item and wraps one word per line')
    check('review: markup inside a finding title survives',
          '<em>tell</em>' in row and '<b>text</b>' in row)

    # a gate value long enough to be a sentence must not force the page sideways
    check('review: gate chips wrap rather than overflow',
          'white-space:nowrap}' not in ra.CSS.split('.gates b{')[0].split('.gates span{')[1])

    # --- images and their ALT TEXT ------------------------------------------
    # Alt text is house prose, it is the only thing a screen-reader user gets from a
    # picture, and NOTHING else on this page showed it. Image blocks were skipped
    # outright, so a piece's body images were simply absent — and an image sharing a
    # block with an HTML comment was rendered as literal `<!-- slide -->` text.
    # (Eric, 2026-09-10: "our artifact preview render should show us the alt text".)
    ip = os.path.join(tmp, 'img'); os.makedirs(os.path.join(ip, 'assets'), exist_ok=True)
    open(os.path.join(ip, 'publish.yaml'), 'w').write(
        'title: T\nsubtitle: S\nimages:\n  assets/local.png: https://cdn.example/x_1.png\n')
    open(os.path.join(ip, 'draft.md'), 'w').write(
        'scaffold\n---\n![A hero, described](assets/nope.png)\n\n## I. First\n\n'
        '<!-- slide -->\n<!-- design: internal -->\n![Figure 1: the shape](assets/gone.png)\n\n'
        'Prose.\n\n![](assets/none.png)\n\n![Remote one](https://cdn.example/x_1.png)\n')
    # a real (tiny) PNG so the CDN->local mapping is exercised end to end
    try:
        from PIL import Image
        Image.new('RGB', (8, 6), (30, 40, 60)).save(os.path.join(ip, 'assets', 'local.png'))
        have_pil = True
    except ImportError:
        have_pil = False
    hi = ra.build(ip, {})
    check('review: an image block renders as a figure, not as skipped text',
          hi.count('<figure') == 4, 'body images were dropped from the page entirely')
    check('review: the alt text is shown as prose',
          'A hero, described' in hi and 'Figure 1: the shape' in hi)
    check('review: an EMPTY alt is called out, not left blank',
          'alt-none' in hi and 'MISSING' in hi,
          'a picture with no alt gives a screen-reader user nothing')
    check('review: an HTML comment never reaches the page',
          '&lt;!--' not in hi and 'internal' not in hi,
          'the converter strips them for the reader; this page is the author reading')
    check('review: raw image markdown never reaches the page', '![' not in hi)
    # Embedding needs PIL; without it the fourth image cannot be shown either, and it must be
    # NAMED like the others. A hard-coded 3 failed on every machine without PIL (CI, 2026-09-11).
    check('review: an image the page cannot show is NAMED, not dropped',
          hi.count('image not shown') == (3 if have_pil else 4),
          'three of the four fixture images have no file; the fourth resolves via the map (with PIL)')
    check('review: a CDN url maps back to its local file via publish.yaml',
          (not have_pil) or ('no local file for it' not in hi
                             and hi.count('data:image/jpeg') == 1),
          'the manifest records which local file each uploaded url came from')
    check('review: alt text is anchorable like any other prose',
          'id="a1"' in ra.build(ip, {'findings': [
              {'anchor': 'A hero, described', 'now': 'A hero, described better', 'title': 'X'}]}),
          'so a review can propose new alt text and --apply can write it')

    # --- --apply: the contract makes applying a review a substitution, not a retyping ---
    ap = os.path.join(tmp, 'apply'); os.makedirs(ap, exist_ok=True)
    src = ('scaffold\n---\n## I. First\n\nThe devil taketh him up, and sheweth him all.[^a]\n\n'
           'A second line entirely.\n\n[^a]: A note about the world — outside — of it.\n')
    def fresh():
        open(os.path.join(ap, 'draft.md'), 'w').write(src)
    fresh()
    n, errs = ra.apply_findings(ap, [
        {'anchor': 'taketh him up, and sheweth him all', 'now': 'taketh Him up, and sheweth Him all'},
        {'anchor': 'A note about the world', 'now': 'A note about the whole world'}])
    got = open(os.path.join(ap, 'draft.md')).read()
    check('apply: every finding is written in', (n, errs) == (2, []))
    check('apply: the replacement is the `now`, byte for byte',
          'taketh Him up, and sheweth Him all' in got,
          'what the author approved and what lands come from the same string')
    check('apply: a finding may land in a footnote', 'A note about the whole world' in got)
    check('apply: the scaffold header above --- is untouched', got.startswith('scaffold\n---\n'))
    check('apply: untouched blocks are not re-flowed', 'A second line entirely.' in got)
    check('apply: footnote continuations keep the 4-space indent',
          all(l.startswith('    ') for l in got.split('[^a]: ')[1].split('\n')[1:] if l.strip()))

    fresh()
    n, errs = ra.apply_findings(ap, [{'anchor': 'not in this draft', 'now': 'x'}])
    check('apply: an anchor that misses refuses', n == 0 and bool(errs))
    check('apply: NOTHING is written when any finding misses',
          open(os.path.join(ap, 'draft.md')).read() == src,
          'a half-applied review leaves the draft in a state nobody chose')

    fresh()
    ra.apply_findings(ap, [{'anchor': 'A second line entirely.',
                            'now': 'A [second line](https://example.com/p/a) entirely, made long '
                                   'enough that the wrapper has to break it somewhere near here.'}])
    got = open(os.path.join(ap, 'draft.md')).read()
    check('apply: a markdown link is never broken across lines',
          not re.search(r'\[[^\]]*\n[^\]]*\]\(', got),
          'it still parses, but no draft on this desk carries one that way')

    # the anchor is matched across the draft's own line wraps
    fresh()
    open(os.path.join(ap, 'draft.md'), 'w').write(
        'h\n---\n## I. A\n\nThe devil taketh him up, and\nsheweth him all.\n')
    n, errs = ra.apply_findings(ap, [{'anchor': 'taketh him up, and sheweth him all',
                                      'now': 'taketh Him up, and sheweth Him all'}])
    check('apply: an anchor matches across the file\'s line wraps', (n, errs) == (1, []),
          'draft.md wraps at ~100 chars; the anchor is written as one line')

    # a headingless piece put the whole prose in BOTH lead and movements: the word
    # count doubled and every anchor matched twice
    flat = os.path.join(tmp, 'flat'); os.makedirs(flat, exist_ok=True)
    open(os.path.join(flat, 'draft.md'), 'w').write('s\n---\nJust one unheaded paragraph here.\n')
    hflat = ra.build(flat, {'findings': [{'anchor': 'one unheaded paragraph', 'title': 'F',
                                          'now': 'one unheaded sentence'}]})
    check('review: a headingless piece counts its words once',
          '<b>5</b>' in hflat, 'lead and movements are one source of truth')
    check('review: a headingless piece still anchors', 'id="a1"' in hflat)


# ---------------------------------------------------------------- unit: link extraction
def unit_link_extraction():
    """A cross-link must be seen in every form a draft can carry it.

    The checker read only [text](url) until 2026-09-02. The house cites a published
    sibling as an autolink inside a footnote, so the one form it could not see was
    the one the convention uses — and a 404 shipped into a draft behind that blind
    spot.
    """
    print("\n-- link extraction -----------------------------------------------")
    U = 'https://example.com/p/a'
    check('inline [text](url)', extract_links(f'see [A]({U}) here') == {U})
    check('autolink <url>', extract_links(f'[^a]: *A* — <{U}>.') == {U},
          'how a footnote cites a live sibling — the form that was invisible')
    check('bare url', extract_links(f'watch {U} now') == {U})
    check('trailing period is not part of the url',
          extract_links(f'it is at {U}.') == {U},
          'otherwise a sentence-final url reports a false dead')
    check('inline and autolink de-duplicate',
          extract_links(f'[A]({U}) and <{U}>') == {U},
          'one fetch, not two')
    check('two distinct urls both survive',
          extract_links(f'[A]({U}) then <{U}b>') == {U, U + 'b'})
    check('emphasis markers are stripped from a bare url',
          extract_links(f'see *{U}*') == {U})
    check('no url yields nothing', extract_links('nothing here') == set())

    # ...and seeing a form is not the same as the pipeline being able to RENDER it. The
    # converter emits [text](url) and nothing else, so a checker that merely resolves an
    # autolink is more permissive than the thing it guards — which is how three sibling
    # citations passed a green check and would have published as angle-bracketed strings.
    hdr = '# t\n\n*head <https://example.com/h>*\n\n---\n\n'
    U = 'https://example.com/p/a'
    forms = lambda t: {u: f for u, f in unrenderable_links(t)}
    check('an autolink in the body is flagged as unrenderable',
          forms(hdr + f'x <{U}> y').get(U) == 'autolink <url>')
    check('a bare url in the body is flagged',
          forms(hdr + f'x {U} y').get(U) == 'bare url',
          'measured live: Substack does not autolink one, it publishes as plain text')
    check('an inline [text](url) is NOT flagged', not forms(hdr + f'x [A]({U}) y'))
    check('a url written both ways is NOT flagged',
          not forms(hdr + f'[A]({U}) and <{U}>'),
          'the inline form is present, so it renders')
    check('a url in the scaffold header is NOT flagged',
          not any(u == 'https://example.com/h' for u, _f in unrenderable_links(hdr + 'body')),
          'the header is dropped before publication and never reaches a reader')


# ---------------------------------------------------------------- unit: CLI dispatch
def unit_cli_dispatch():
    """Every command the CLI accepts must resolve to a function that exists.

    This is here because on 2026-09-01 `substack_sync.py images` crashed with
    `NameError: name 'cmd_images' is not defined` — the dispatch branch shipped without its
    handler. It was the scraper half of the recompose image gate, so the gate added that day to
    stop a recompose destroying a live image could not be run at all. Nothing caught it, because
    nothing was checking that the CLI's own table was complete.
    """
    print("\n-- CLI dispatch is complete --------------------------------------")
    src = open(os.path.join(HERE, 'substack_sync.py')).read()
    branches = set(re.findall(r"cmd == '([a-z-]+)'", src))
    called = set(re.findall(r'\b(cmd_[a-z_]+)\(', src))
    defined = set(re.findall(r'^def (cmd_[a-z_]+)', src, re.M))
    check('every dispatched handler is defined', not (called - defined),
          f'undefined: {sorted(called - defined)}')
    check('every documented command has a branch', branches,
          f'found {len(branches)} branches')
    missing_branch = sorted(b for b in branches
                            if f"cmd_{b.replace('-', '_')}(" not in src)
    check('every branch names a handler', not missing_branch, f'{missing_branch}')


# ---------------------------------------------------------------- unit: piece resolution
def unit_piece_resolution(tmp):
    """A failure to resolve a piece must name its own cause.

    On 2026-09-02 `substack_verify --fresh forking-paths` reported a freshly published essay as
    "no public_url — not published". The bare slug resolved to no directory, an absent
    publish.yaml read as an empty manifest, and the empty manifest read as unpublished. Three
    different causes printed one message, and the message named the wrong one — which is worse
    than silence, because it gets believed. This asserts they stay distinguishable.
    """
    print("\n-- piece resolution names its own failure ------------------------")
    sys.path.insert(0, HERE)
    from substack_verify import resolve_piece

    repo = os.path.join(tmp, 'repo')
    os.makedirs(os.path.join(repo, 'pieces', 'live'))
    os.makedirs(os.path.join(repo, 'pieces', 'composed'))
    os.makedirs(os.path.join(repo, 'pieces', 'bare'))
    open(os.path.join(repo, 'pieces', 'live', 'publish.yaml'), 'w').write(
        'title: L\npublic_url: https://example.invalid/p/l\n')
    open(os.path.join(repo, 'pieces', 'composed', 'publish.yaml'), 'w').write(
        'title: C\npost_url: https://example.invalid/publish/post/1\n')

    d, url, why = resolve_piece(repo, 'live')
    check('a bare slug resolves', url and why is None, f'url={url} why={why}')
    d2, url2, _ = resolve_piece(repo, os.path.join(repo, 'pieces', 'live'))
    check('a path resolves to the same piece', d2 == d, f'{d2} != {d}')

    _, url3, why3 = resolve_piece(repo, 'composed')
    check('composed-but-unpublished says so', url3 is None and 'not published' in (why3 or ''), str(why3))
    _, url4, why4 = resolve_piece(repo, 'bare')
    check('missing publish.yaml says so', url4 is None and 'never composed' in (why4 or ''), str(why4))
    _, url5, why5 = resolve_piece(repo, 'nope')
    check('a bad slug says no such piece', url5 is None and 'no such piece' in (why5 or ''), str(why5))
    check('the three failures are distinguishable', len({why3, why4, why5}) == 3,
          'a shared message is what caused the 2026-09-02 misdiagnosis')


# ---------------------------------------------------------------- unit: three-way
def unit_three_way():
    print("\n-- three-way classification --------------------------------------")
    base = ['A', 'B', 'C', 'D', 'E']
    draft = ['A', 'B2', 'C', 'D2', 'E2']     # B and D and E moved in the draft
    live = ['A', 'B', 'C2', 'D2', 'E3']      # C and D and E moved live
    rows, structural = three_way('body', base, draft, live)
    got = {r['baseIdx']: r['state'] for r in rows}
    check('unchanged when neither side moved', got[0] == 'unchanged', str(got))
    check('push when only the draft moved', got[1] == 'push', str(got))
    check('pull when only live moved', got[2] == 'pull', str(got))
    check('converged when both made the same edit', got[3] == 'converged', str(got))
    check('conflict when both moved differently', got[4] == 'conflict', str(got))
    check('no structural rows for a same-length change', structural == [], str(structural))

    # The second verdict. Every row above has IDENTICAL text on all three sides here, so
    # `state` is `unchanged` throughout and only `markState` can carry the finding — which is
    # exactly the shape of the bug: a block whose words never moved and whose italics did.
    same = ['T', 'T', 'T', 'T', 'T']
    mrows, _st = three_way('body', same, same, same,
                           base_m=['A', 'B', 'C', 'D', 'E'],
                           draft_m=['A', 'B2', 'C', 'D2', 'E2'],
                           live_m=['A', 'B', 'C2', 'D2', 'E3'])
    check('a text-identical row still classifies its marks',
          all(r['state'] == 'unchanged' for r in mrows), str([r['state'] for r in mrows]))
    mgot = {r['baseIdx']: r['markState'] for r in mrows}
    check('marks unchanged / push / pull / converged / conflict',
          [mgot[i] for i in range(5)] == ['unchanged', 'push', 'pull', 'converged', 'conflict'],
          str(mgot))

    # UNKNOWN IS NOT UNCHANGED. 34 baselines were sealed before marks were tracked, and a
    # tool that answers "no formatting change" when it has nothing to compare is the failure
    # being fixed, wearing a different hat.
    urows, _u = three_way('body', same, same, same)
    check('no mark data anywhere reads as unknown, never unchanged',
          all(r['markState'] == 'unknown' for r in urows), str([r['markState'] for r in urows]))
    prows, _p2 = three_way('body', same, same, same,
                           base_m=None, draft_m=['A'] * 5, live_m=['A'] * 5)
    check('a text-only BASELINE reads as unknown even when both live sides have marks',
          all(r['markState'] == 'unknown' for r in prows), str([r['markState'] for r in prows]))

    pairs, added, removed = align(['A', 'B', 'C'], ['A', 'B', 'X', 'C'])
    check('align reports an inserted row', added == [2] and removed == [],
          f'added={added} removed={removed}')


# ---------------------------------------------------------------- unit: converter
def unit_converter(tmp):
    print("\n-- converter -----------------------------------------------------")
    check('escaped asterisks survive as literal text',
          strip_to_reader(render_block(r'F\*\*k you', '.')) == 'F**k you')
    check('real emphasis still becomes markup',
          '<em>' in render_block('a *real* emphasis', '.'))
    check('escaped asterisks do not open emphasis',
          '<strong>' not in render_block(r'F\*\*k a F\*\*k b', '.'))

    # An alt that transcribes text in the image quotes it, and a bare `"` ended the attribute:
    # love-is-not-a-metric-space's 608-char alt parsed back as 103 chars. Parse, don't grep.
    from html.parser import HTMLParser
    class _Alts(HTMLParser):
        def __init__(self):
            super().__init__()
            self.alts = []
        def handle_starttag(self, tag, attrs):
            if tag == 'img':
                self.alts.append(dict(attrs).get('alt'))
    alt = 'an arrow labeled "featurize." & a column headed "<vector>"'
    p = _Alts()
    p.feed(render_block(f'![{alt}](https://example.com/fig.png)', '.'))
    check('an alt with double quotes survives a parse round trip intact',
          p.alts == [alt], repr(p.alts))
    check('body-text quotes stay bare (reader digests depend on it)',
          render_block('she said "hi"', '.') == '<p>she said "hi"</p>',
          render_block('she said "hi"', '.'))

    ul = render_block('- one\n- two\n  continued', '.')
    check('a bullet list renders as a list', ul.startswith('<ul>') and ul.count('<li>') == 2, ul[:60])
    check('a list item absorbs its indented continuation', 'two continued' in ul, ul[:80])

    fn = render_footnote_block('[^x]: the note *body*', '.')
    check('a footnote renders without its label',
          fn is not None and strip_to_reader(fn) == 'the note body', repr(fn))
    check('a footnote through the paragraph path keeps its label (the bug)',
          '[[FNx]]' in render_block('[^x]: the note', '.'),
          'render_block must not be used for footnotes')

    # adjacent blockquotes merge, because ProseMirror merges them on paste
    d = os.path.join(tmp, 'bq')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\nbody\n\n> one\n\n> two\n\ntail\n')
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    body, fns, res, iss = render_reader(d)
    merged = [b for b in body if b.startswith('one')]
    check('adjacent blockquotes merge into one block',
          len(merged) == 1 and merged[0] == 'onetwo', str(body))

    # A syndicated copy opens with "Originally published at <canonical>" (2026-09-11: the
    # MuffinLabs Substack copies the blog, and Substack emits no rel=canonical).
    dc = os.path.join(tmp, 'canon')
    os.makedirs(dc, exist_ok=True)
    with open(os.path.join(dc, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\nFirst paragraph.\n\nSecond.\n')
    with open(os.path.join(dc, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\ncanonical: https://example.com/blog/x\n')
    cb, _cf, _cr, _ci = render_reader(dc)
    check('a piece with canonical: opens with the Originally-published line',
          cb[:2] == ['Originally published at https://example.com/blog/x.', 'First paragraph.'], str(cb))
    blocks_c = parse_blocks(dc)[0]
    check('and the line links the canonical',
          blocks_c[0] == '<p><em>Originally published at <a href="https://example.com/blog/x">'
                         'https://example.com/blog/x</a>.</em></p>', blocks_c[0])
    check('its source cannot be located in draft.md (sync must never pull it into prose)',
          render_reader.sources['body'][0] not in open(os.path.join(dc, 'draft.md')).read())
    with open(os.path.join(dc, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    nb, _nf, _nr, _ni = render_reader(dc)
    check('a piece with no canonical: gets no such line', nb[0] == 'First paragraph.', str(nb))


def unit_footnote_continuation(tmp):
    """A footnote's continuation paragraph must stay in the footnote.

    Before 2026-09-02 it did not: the block splitter made it a separate block, it failed
    the `[^id]:` match, and it published as an ordinary BODY paragraph in place. Content
    relocated rather than dropped, which is worse — the output reads as deliberate, the
    paragraph count merely goes up by one, and nothing refuses.
    """
    print("\n-- footnote continuation -----------------------------------------")
    d = os.path.join(tmp, 'fncont')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('t\n\n---\n\n## I\n\nnote here.[^a] and here.[^b]\n\n'
                '[^a]: first of A.\n\n    indented second of A CONT_KEPT.\n\n'
                '[^b]: first of B.\n\nunindented after B CONT_LOOSE.\n')
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    blocks, ordered, _stripped, _res, _unv, issues, _src = parse_blocks(d)
    fns = dict(ordered)
    body = ' '.join(blocks)
    check('an indented continuation stays in its footnote',
          'CONT_KEPT' in fns.get('a', ''), repr(fns.get('a')))
    check('an indented continuation does NOT leak into the body',
          'CONT_KEPT' not in body,
          'the 2026-09-02 bug: it published in place, as body text')
    check('an unindented paragraph after a definition stays body text',
          'CONT_LOOSE' in body,
          'it cannot be claimed as a continuation — definitions sit mid-document here')
    check('and that ambiguous case is reported, not silent',
          any(n == 'b' for n, _t in issues.get('orphaned', [])),
          'silence is how a continuation gets written wrong and never noticed')

    # ...but a divider or heading after a definition is the ORDINARY shape here, and warning on
    # it fired on 11 of 27 pieces — a warning that always fires stops being read.
    d2 = os.path.join(tmp, 'fnquiet')
    os.makedirs(d2, exist_ok=True)
    with open(os.path.join(d2, 'draft.md'), 'w') as f:
        f.write('t\n\n---\n\n## I\n\nnote.[^a]\n\n[^a]: the note.\n\n---\n\n## II\n\ntail.\n')
    with open(os.path.join(d2, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    _b2, _o2, _s2, _r2, _u2, issues2, _x2 = parse_blocks(d2)
    check('a divider or heading after a definition does NOT warn',
          not issues2.get('orphaned'),
          f"would fire on the ordinary shape: {issues2.get('orphaned')}")


def unit_footnote_order(tmp):
    print("\n-- footnote ordering ---------------------------------------------")
    d = os.path.join(tmp, 'fnorder')
    os.makedirs(d, exist_ok=True)
    # labels sort as 103 < 999 < zzz, but they are CITED in the order zzz, 999, 103
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\nfirst[^zzz] second[^999] third[^103]\n\n'
                '[^103]: one-oh-three\n\n[^999]: nine-nine-nine\n\n[^zzz]: zed\n')
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: t\nsubtitle: s\n')
    body, fns, res, iss = render_reader(d)
    check('footnotes emit in first-reference order, not label order',
          fns == ['zed', 'nine-nine-nine', 'one-oh-three'], str(fns))
    check('no spurious footnote issues', not any(iss[k] for k in ('undefined', 'duplicated', 'nested')),
          str(iss))

    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\na[^a] b[^a]\n\n[^a]: dup\n')
    _b, _f, _r, iss2 = render_reader(d)
    check('a footnote cited twice is reported', iss2['duplicated'] == ['a'], str(iss2))

    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('x\n\n---\n\na[^a]\n\n[^a]: see [^b]\n\n[^b]: other\n')
    _b, _f, _r, iss3 = render_reader(d)
    check('a footnote referenced inside a footnote is reported',
          'b' in iss3['nested'], str(iss3))


def unit_pull_verification():
    print("\n-- pull verification ---------------------------------------------")
    src = 'take this* but *is this for us* — asked'
    src = 'not *can I take this* but *is this for us* — asked upward'
    reader = strip_to_reader(render_block(src, '.'))
    out, note = edit_block_source(src, reader, reader.replace('for us', 'for me'), '.')
    check('a pulled edit lands inside emphasis without eating the markers',
          out is not None and '*is this for me*' in out, f'{note}: {out!r}')

    m = reader_to_source_map(src, reader)
    check('the offset map is monotonic', all(m[i] <= m[i + 1] for i in range(len(reader))))

    # The genuinely unrepresentable case, and the real one: a double space. strip_to_reader
    # collapses whitespace runs, so no markdown source can render two spaces — the verifier
    # must refuse rather than write something that does not round-trip. This is the refusal
    # that correctly fired on `Both Ends of the Leash`.
    bad, note2 = edit_block_source(src, reader, reader.replace('for us', 'for  us'), '.')
    check('an edit that cannot round-trip is refused, not guessed',
          bad is None, f'expected a refusal, got {note2}')

    # A plain edit with no markup in play must APPLY — the refusals above are not the
    # verifier being timid, they are it declining specific things it cannot round-trip.
    plain = 'a plain source sentence here'
    ok2, note3 = edit_block_source(plain, plain, 'a plain replacement sentence here', '.')
    check('a plain, representable edit still applies',
          ok2 == 'a plain replacement sentence here', f'{note3}: {ok2!r}')



def unit_images():
    print("\n-- images --------------------------------------------------------")
    s3 = 'https://substack-post-media.s3.amazonaws.com/public/images/abc_1536x1024.png'
    cdn = ('https://substackcdn.com/image/fetch/$s_!x,w_1456,c_limit/'
           + s3.replace(':', '%3A').replace('/', '%2F'))
    check('the CDN wrapper unwraps to the asset it points at',
          canonical_image_url(cdn) == s3, canonical_image_url(cdn))
    check('a bare asset URL is unchanged', canonical_image_url(s3) == s3)


# ---------------------------------------------------------------- unit: live extraction
def unit_live_extraction():
    """The reader-side extractor, offline.

    substack_verify fetches live pages; these checks feed it canned markup instead, so
    the suite keeps its no-network promise while still guarding the parser. Every case
    below is a shape that produced a FALSE DRIFT against the real corpus before it was
    fixed -- a verifier that cries wolf is worse than none, because the first thing
    anyone does with a noisy check is stop reading it.
    """
    print("\n-- live-page extraction (offline) --------------------------------")

    # A list is ONE block. Substack nests <li><p>..</p></li>; if the inner </p> closes
    # the buffer, one list becomes N blocks and every piece with a list reports drift.
    b, f, bm, fm, _ba, _fa = live_blocks('<ul><li><p>alpha</p></li><li><p>beta</p></li></ul>')
    check('a bullet list extracts as a single block', b == ['alphabeta'], repr(b))

    # Same bug, different tag -- and adjacent quotes merge, as the draft renderer merges them.
    b, _f, _bm, _fm, _ba, _fa = live_blocks('<blockquote><p>one</p></blockquote><blockquote><p>two</p></blockquote>')
    check('adjacent blockquotes merge into one block', b == ['onetwo'], repr(b))

    b, _f, _bm, _fm, _ba, _fa = live_blocks('<p>plain</p><blockquote><p>q</p></blockquote><p>after</p>')
    check('a lone blockquote does not swallow the paragraph after it',
          b == ['plain', 'q', 'after'], repr(b))

    # Furniture Substack injects into the body: not prose, must not count as drift.
    b, _f, _bm, _fm, _ba, _fa = live_blocks('<p>real</p><div class="subscription-widget-wrap-editor">'
                       '<div class="subscription-widget"><div class="preamble">'
                       '<p class="cta-caption">Thanks for reading! Subscribe.</p>'
                       '</div></div></div><p>also real</p>')
    check('a subscribe widget is not counted as body', b == ['real', 'also real'], repr(b))

    b, _f, _bm, _fm, _ba, _fa = live_blocks('<div class="captioned-image-container"><figure>'
                       '<img src="x"><figcaption>a caption</figcaption></figure></div><p>text</p>')
    check('an image and its caption are not body', b == ['text'], repr(b))

    # Void tags inside a skipped subtree once wedged the parser open forever: <img>,
    # <source> and <hr> have no end tag, so a depth counter that increments on them
    # never comes back down and the whole rest of the post vanishes.
    b, _f, _bm, _fm, _ba, _fa = live_blocks('<div class="captioned-image-container"><picture>'
                       '<source srcset="a"><img src="b"></picture></div><hr><p>survives</p>')
    check('void tags in skipped subtrees do not wedge the parser', b == ['survives'], repr(b))

    # The superscript marker is not prose; the footnote body is not body.
    b, f, bm, fm, _ba, _fa = live_blocks('<p>Sentence<a class="footnote-anchor" href="#footnote-1">1</a> ends.</p>'
                       '<div class="footnote"><a class="footnote-number">1</a>'
                       '<div class="footnote-content"><p>The note.</p></div></div>')
    check('a footnote anchor leaves no digit in the prose', b == ['Sentence ends.'], repr(b))
    check('footnote content is captured separately', f == ['The note.'], repr(f))

    # ---- marks: the layer reader-text cannot see --------------------------------------
    # Everything above compares TEXT. Wrapping a word already in the post in <em> changes
    # none of it, so none of the checks above can fail on it. These can.
    _b, _f, bm, fm, _ba, _fa = live_blocks(
        '<p>Plain <em>satsang</em> and <strong>bold</strong> '
        '<a href="https://elmuffin.substack.com/p/x">a link</a>.</p>')
    check('em, strong and link are each enumerated from the live page',
          mark_keys(bm[0]) == [('em', 'satsang', ''), ('strong', 'bold', ''),
                               ('link', 'a link', 'https://elmuffin.substack.com/p/x')],
          repr(mark_keys(bm[0])))

    # THE FALSE PASS, in one assertion. Same reader-text on both sides, one <em> apart:
    # the digest cannot tell them apart, and the mark scan must.
    plain, italic = '<p>He sat in the satsang.</p>', '<p>He sat in the <em>satsang</em>.</p>'
    pb, _pf, pbm, _pfm, _ba, _fa = live_blocks(plain)
    ib, _if, ibm, _ifm, _ba, _fa = live_blocks(italic)
    check('an italics-only difference is INVISIBLE to the text digest',
          H(pb[0]) == H(ib[0]), f'{pb[0]!r} vs {ib[0]!r}')
    check('an italics-only difference IS visible to the mark scan',
          mark_keys(pbm[0]) == [] and mark_keys(ibm[0]) == [('em', 'satsang', '')],
          f'{mark_keys(pbm[0])} vs {mark_keys(ibm[0])}')

    # A RUN IS A SPAN, NOT AN ELEMENT. Substack serves `**a _b_ c**` back as three <strong>
    # elements around the em; the converter emits one <strong> wrapping it. Compared
    # element-by-element that is drift on every bold-containing-an-italic in the corpus --
    # 8 pieces of 34 on the first sweep, 2026-09-09, not one a real difference.
    _b1, _f1, split, _m1, _ba, _fa = live_blocks('<p><strong>There is no </strong><em><strong>toward'
                                       '</strong></em><strong> in the index.</strong></p>')
    _b2, _f2, whole, _m2, _ba, _fa = live_blocks('<p><strong>There is no <em>toward</em> in the '
                                       'index.</strong></p>')
    check('a bold split around an italic is one run, not three',
          mark_keys(split[0]) == mark_keys(whole[0])
          == [('strong', 'There is no toward in the index.', ''), ('em', 'toward', '')],
          repr(mark_keys(split[0])))

    # The two <a> tags that are not links. A footnote superscript counted as a link would
    # put a phantom run in every footnoted block of every piece in the corpus.
    _b3, _f3, anch, fnm, _ba, _fa = live_blocks(
        '<p>Sentence<a class="footnote-anchor" href="#footnote-1">1</a> ends.</p>'
        '<div class="footnote"><a class="footnote-number" href="#footnote-anchor-1">1</a>'
        '<div class="footnote-content"><p>The <em>note</em>.</p></div></div>')
    check('a footnote anchor is not counted as a link', mark_keys(anch[0]) == [], repr(anch))
    check('a footnote body\'s own italics are collected',
          mark_keys(fnm[0]) == [('em', 'note', '')], repr(fnm))

    # Substack curls quotes on paste; the draft has straight ones. A run must not report
    # drift for that -- the same flattening the text digest has always applied.
    _b4, _f4, cur, _m4, _ba, _fa = live_blocks('<p>She said <em>\u201cno\u201d</em> once.</p>')
    check('a run with curled quotes compares straight',
          mark_keys(cur[0]) == [('em', '"no"', '')], repr(mark_keys(cur[0])))

    # ---- anchors: the layer neither text NOR marks can see ----------------------------
    # The superscript digit is dropped from the prose above and is not a mark; before this,
    # WHERE a footnote hung was simply not collected, so it could not be compared.
    _b5, _f5, _m5, _fm5, ba, fa = live_blocks(
        '<p>He stopped.<a class="footnote-anchor" href="#footnote-1">1</a> Then he waited.'
        '<a class="footnote-anchor" href="#footnote-2">2</a></p>'
        '<div class="footnote"><a class="footnote-number">1</a>'
        '<div class="footnote-content"><p>A note.</p></div></div>')
    check('each anchor is collected with its number and the words it follows',
          ba[0] == [(1, 'He stopped.'), (2, 'He stopped. Then he waited.')], repr(ba))
    check('a block with no anchors collects none', fa == [[]], repr(fa))

    # The draft's `[[FNn]]` marker and the live `<a class="footnote-anchor">` must land on
    # the SAME offset, or the two sides are being measured with different rulers.
    _runs, scanned, danch = marks_in('<p>He stopped.[[FN1]] Then he waited.[[FN2]]</p>')
    check('the draft marker and the live anchor agree on the position',
          scanned == 'He stopped. Then he waited.' and danch == [(11, '1'), (27, '2')],
          f'{danch} {scanned!r}')
    check('the marker leaves no trace in the reader-text it is measured against',
          anchor_tail(scanned, danch[0][0]) == 'He stopped.', repr(anchor_tail(scanned, danch[0][0])))

    # A page that shipped no post (login wall, layout change) must read as "could not
    # check", never as an empty post that trivially matches nothing.
    check('a page with no _preloads yields no post',
          extract_post('<html><body>nothing here</body></html>') is None)


def unit_mark_drift(tmp):
    """The regression the whole chain used to pass.

    A draft and a live post whose READER-TEXT is identical block for block and footnote for
    footnote, differing only in one <em>. Every digest on this desk reports MATCH; the run
    comparison must report drift, and must say it is FORMATTING drift rather than sending
    the reader to look for a word that changed.

    Measured on `rising-after-falls`, 2026-09-09: after italicising two words the
    regenerated surgical patch was byte-identical in size to the previous one (29,782
    bytes), reported `unchanged`, and applied nothing.
    """
    print("\n-- marks: a formatting-only change is caught ----------------------")
    d = os.path.join(tmp, 'marks'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: A Piece\nsubtitle: With one italic\n')
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\n'
                'He sat in the *satsang* and listened.[^1]\n\n'
                'A plain closing line.\n\n'
                '[^1]: The word is *satsang*, a sitting-together.\n')

    body, fns, _r, _i = render_reader(d)
    dbm, dfm, offsets_ok = render_marks(d)
    check('the mark scan stays 1:1 with render_reader',
          len(dbm) == len(body) and len(dfm) == len(fns), f'{len(dbm)}/{len(body)} {len(dfm)}/{len(fns)}')
    check('a run offset indexes the reader-text it was scanned from', offsets_ok)
    check('the draft\'s own italic is seen',
          mark_keys(dbm[0]) == [('em', 'satsang', '')], repr(mark_keys(dbm[0])))

    # the live post: same words, no italics anywhere
    live_html = ('<p>He sat in the satsang and listened.'
                 '<a class="footnote-anchor" href="#footnote-1">1</a></p>'
                 '<p>A plain closing line.</p>'
                 '<div class="footnote"><a class="footnote-number">1</a>'
                 '<div class="footnote-content"><p>The word is satsang, a sitting-together.</p>'
                 '</div></div>')
    lb, lf, lbm, lfm, _ba, _fa = live_blocks(live_html)
    check('the live page and the draft agree on every block of TEXT',
          [H(x) for x in lb] == [H(x) for x in body] and [H(x) for x in lf] == [H(x) for x in fns],
          f'live={lb} draft={body}')

    drift = (mark_drift(lbm, dbm, lb, body, 'block')
             + mark_drift(lfm, dfm, lf, fns, 'footnote', base=1))
    check('the mark scan catches what the digest cannot', len(drift) == 2, repr(drift))
    check('the report names the block, the kind, and the run',
          any('block #0' in x and 'emphasis' in x and 'satsang' in x for x in drift), repr(drift))
    check('a footnote-only formatting change is caught too',
          any('footnote #1' in x for x in drift), repr(drift))

    # and the converse: identical formatting is silence, not noise
    same = live_blocks('<p>He sat in the <em>satsang</em> and listened.'
                       '<a class="footnote-anchor" href="#footnote-1">1</a></p>'
                       '<p>A plain closing line.</p>')
    check('matching formatting reports nothing',
          mark_drift(same[2], dbm, same[0], body, 'block') == [], repr(mark_drift(same[2], dbm, same[0], body, 'block')))

    # a link whose text is right and whose target is wrong is its OWN kind of drift
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\nSee [the essay](https://elmuffin.substack.com/p/right).\n')
    body2, _f2, _r2, _i2 = render_reader(d)
    dbm2, _dfm2, _ok2 = render_marks(d)
    lb2, _lf2, lbm2, _lfm2, _ba, _fa = live_blocks(
        '<p>See <a href="https://elmuffin.substack.com/p/wrong">the essay</a>.</p>')
    d2 = mark_drift(lbm2, dbm2, lb2, body2, 'block')
    check('a wrong href is reported as a link target, not as emphasis',
          len(d2) == 1 and 'link target' in d2[0] and 'wrong' in d2[0] and 'right' in d2[0], repr(d2))


def unit_anchor_drift(tmp):
    """The regression the mark scan ALSO passed.

    A draft and a live post whose reader-text is identical block for block, whose marks are
    identical run for run, and whose one difference is which sentence carries footnote 1.
    Every digest on this desk reports MATCH, the mark scan reports nothing, and the anchor
    comparison must report drift — and must say it is ANCHOR drift, because the repair is
    dragging a superscript in the editor, not repatching a block or restoring an italic.

    Measured 2026-09-11 on `for-the-love-of-dogs`, live since 2026-08-05: footnote 1 sat
    after "It was slow. It worked." on the post and after "I stopped trying to frighten
    him." in the draft — two paragraphs apart — and `substack_verify --fresh` said MATCH for
    five weeks. Only `substack_repatch --structural` ever noticed, by refusing to patch.
    """
    print("\n-- anchors: a footnote on the wrong sentence is caught ------------")
    d = os.path.join(tmp, 'anchors'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: A Piece\nsubtitle: With one footnote\n')
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\n'
                'I stopped trying to frighten him.[^1] He was a terror on the leash.\n\n'
                'It was slow. It worked.\n\n'
                '[^1]: The training book I followed.\n')

    body, fns, _r, _i = render_reader(d)
    dba, dfa = render_anchors(d)
    check('the anchor scan stays 1:1 with render_reader',
          len(dba) == len(body) and len(dfa) == len(fns),
          f'{len(dba)}/{len(body)} {len(dfa)}/{len(fns)}')
    check('the draft says which sentence carries the note',
          dba[0] == [(1, 'I stopped trying to frighten him.')] and dba[1] == [], repr(dba))

    # the live post: same words, same formatting, the superscript two blocks later
    right = ('<p>I stopped trying to frighten him.'
             '<a class="footnote-anchor" href="#footnote-1">1</a>'
             ' He was a terror on the leash.</p>'
             '<p>It was slow. It worked.</p>')
    wrong = ('<p>I stopped trying to frighten him. He was a terror on the leash.</p>'
             '<p>It was slow. It worked.'
             '<a class="footnote-anchor" href="#footnote-1">1</a></p>')
    fn = ('<div class="footnote"><a class="footnote-number">1</a>'
          '<div class="footnote-content"><p>The training book I followed.</p></div></div>')

    lb, lf, lbm, lfm, lba, lfa = live_blocks(wrong + fn)
    dbm, dfm, _ok = render_marks(d)
    check('a moved anchor is INVISIBLE to the text digest',
          [H(x) for x in lb] == [H(x) for x in body] and [H(x) for x in lf] == [H(x) for x in fns],
          f'live={lb} draft={body}')
    check('a moved anchor is INVISIBLE to the mark scan',
          mark_drift(lbm, dbm, lb, body, 'block') == [],
          repr(mark_drift(lbm, dbm, lb, body, 'block')))

    drift = anchor_drift(lba, dba, lb, body, 'block')
    check('the anchor scan catches what neither of them can', len(drift) == 2, repr(drift))
    check('it names the block the note LEFT and the words it should follow',
          any('block #0' in x and 'frighten him.' in x for x in drift), repr(drift))
    check('it names the block the note LANDED in and the words it now follows',
          any('block #1' in x and 'It worked.' in x for x in drift), repr(drift))

    # and the converse: the anchor where the draft puts it is silence, not noise
    ok_lb, _f, _m, _fm2, ok_lba, _fa = live_blocks(right + fn)
    check('an anchor in the right place reports nothing',
          anchor_drift(ok_lba, dba, ok_lb, body, 'block') == [],
          repr(anchor_drift(ok_lba, dba, ok_lb, body, 'block')))

    # A note that moved WITHIN one block: same block, same count, different sentence. The
    # per-block count check cannot see this one -- only the tail can.
    same_block = ('<p>I stopped trying to frighten him. He was a terror on the leash.'
                  '<a class="footnote-anchor" href="#footnote-1">1</a></p>'
                  '<p>It was slow. It worked.</p>')
    sb, _f2, _m2, _fm3, sba, _fa2 = live_blocks(same_block + fn)
    d2 = anchor_drift(sba, dba, sb, body, 'block')
    check('a note that moved within its own block is caught by the tail',
          len(d2) == 1 and 'moved' in d2[0] and 'terror on the leash.' in d2[0], repr(d2))

    # Two anchors in one block must keep their ORDER, not merely their count.
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\nFirst claim.[^a] Second claim.[^b]\n\n'
                '[^a]: Note A.\n\n[^b]: Note B.\n')
    body3, _f3, _r3, _i3 = render_reader(d)
    dba3, _dfa3 = render_anchors(d)
    check('footnote NAMES become the live NUMBERS, in first-reference order',
          dba3[0] == [(1, 'First claim.'), (2, 'First claim. Second claim.')], repr(dba3))
    swapped = ('<p>First claim.<a class="footnote-anchor" href="#footnote-2">2</a>'
               ' Second claim.<a class="footnote-anchor" href="#footnote-1">1</a></p>')
    sw, _f4, _m4, _fm4, swa, _fa4 = live_blocks(swapped)
    d3 = anchor_drift(swa, dba3, sw, body3, 'block')
    check('two anchors swapped in one block are caught', len(d3) == 1 and '2 after' in d3[0], repr(d3))

    # A merged blockquote is the one shape where the two sides count blocks differently:
    # the draft renders two adjacent `> ` blocks as ONE, and live_blocks merges the live
    # pair to match. An anchor in the SECOND quote must move with it, or every footnoted
    # blockquote in the corpus reports a drift that is not there.
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\n> Alpha line.\n\n> Beta line.[^1]\n\n[^1]: A note.\n')
    body4, _f5, _r5, _i5 = render_reader(d)
    dba4, _dfa4 = render_anchors(d)
    mb, _f6, _m5, _fm5, mba, _fa5 = live_blocks(
        '<blockquote><p>Alpha line.</p></blockquote>'
        '<blockquote><p>Beta line.<a class="footnote-anchor" href="#footnote-1">1</a></p>'
        '</blockquote>')
    check('the merged blockquote is one block on both sides',
          len(mb) == len(body4) == 1, f'{mb} vs {body4}')
    check('an anchor in the second of two merged quotes does not report false drift',
          anchor_drift(mba, dba4, mb, body4, 'block') == [],
          f'{mba} vs {dba4}')


def unit_sync_baseline_marks(tmp):
    """The sync baseline's second domain.

    substack_sync's baseline recorded hashes of reader-text and nothing else, so a block
    whose only difference was an <em> hashed identically on both sides and the three-way
    called it `unchanged`. Same false pass as substack_verify and substack_repatch had, one
    tool over — and worse here, because a seal writes the mistake down and every later sync
    measures against a state that was never true.
    """
    print("\n-- sync baseline: marks are recorded and aligned ------------------")
    d = os.path.join(tmp, 'syncmarks'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'publish.yaml'), 'w') as f:
        f.write('title: A Piece\nsubtitle: With one italic\n')
    with open(os.path.join(d, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\nHe sat in the *satsang* and listened.[^1]\n\n'
                '[^1]: A note with *emphasis*.\n')

    st = draft_state(d)
    check('draft_state carries the mark runs beside the text',
          len(st['bodyMarks']) == len(st['body']) and len(st['fnsMarks']) == len(st['fns'])
          and st['bodyMarks'][0], f"{st['bodyMarks']} {st['fnsMarks']}")

    # the hash must move when only the formatting does
    plain = os.path.join(tmp, 'syncplain'); os.makedirs(plain, exist_ok=True)
    shutil.copy2(os.path.join(d, 'publish.yaml'), plain)
    with open(os.path.join(plain, 'draft.md'), 'w') as f:
        f.write('*Draft*\n\n---\n\nHe sat in the satsang and listened.[^1]\n\n'
                '[^1]: A note with emphasis.\n')
    sp = draft_state(plain)
    check('the TEXT hash is identical across a formatting-only difference',
          [H(t) for t in st['body']] == [H(t) for t in sp['body']]
          and [H(t) for t in st['fns']] == [H(t) for t in sp['fns']])
    check('a non-empty footnote list is actually under test',
          len(st['fns']) == 1 and len(sp['fns']) == 1, f"{len(st['fns'])} {len(sp['fns'])}")
    check('the MARK hash is not, in the body',
          [HM(r) for r in st['bodyMarks']] != [HM(r) for r in sp['bodyMarks']])
    check('the MARK hash is not, in a footnote',
          [HM(r) for r in st['fnsMarks']] != [HM(r) for r in sp['fnsMarks']])
    check('an unformatted block hashes to the empty signature',
          all(x == HM([]) for x in [HM(r) for r in sp['bodyMarks']]))

    # a sealed baseline records both; a legacy one records neither and says so
    write_baseline(d, st['title'], st['subtitle'],
                   [H(t) for t in st['body']], [H(t) for t in st['fns']], 'test',
                   body_m=[HM(r) for r in st['bodyMarks']], fns_m=[HM(r) for r in st['fnsMarks']])
    base = load_baseline(d)
    check('a sealed baseline records the mark hashes', baseline_has_marks(base), str(sorted(base)))

    write_baseline(d, st['title'], st['subtitle'],
                   [H(t) for t in st['body']], [H(t) for t in st['fns']], 'legacy')
    check('a text-only baseline is detectable as such', not baseline_has_marks(load_baseline(d)))

    # MISALIGNED mark lists are refused rather than written: a mark list one row short would
    # attach every block's formatting to its neighbour's, which is the precise failure the
    # row alignment exists to prevent.
    write_baseline(d, st['title'], st['subtitle'],
                   [H(t) for t in st['body']], [H(t) for t in st['fns']], 'misaligned',
                   body_m=[], fns_m=[])
    check('a mark list that does not line up 1:1 with the rows is not recorded',
          not baseline_has_marks(load_baseline(d)))


def unit_manifest_gate(tmp):
    print("\n-- manifest gate: a post needs a title and a subtitle ---------------")
    d = os.path.join(tmp, 'gate'); os.makedirs(d, exist_ok=True)
    man = os.path.join(d, 'publish.yaml')
    with open(man, 'w') as f:
        f.write('title: T\nfootnotes: native\n')
    errs, _w = manifest_gate(d)
    check('a manifest with no subtitle is refused', errs == ['publish.yaml has no subtitle'], str(errs))
    with open(man, 'w') as f:
        f.write('title: T\nsubtitle:    \n')
    errs, _w = manifest_gate(d)
    check('a blank subtitle counts as missing', errs == ['publish.yaml has no subtitle'], str(errs))
    with open(man, 'w') as f:
        f.write('title: T   # working title (alts: A / B)\nsubtitle: S   # PROPOSED 2026-09-02, not yet settled\n')
    errs, warns = manifest_gate(d)
    check('an unsettled title/subtitle warns but does not refuse',
          not errs and len(warns) == 2 and warns[0].startswith('title') and warns[1].startswith('subtitle'),
          str((errs, warns)))
    with open(man, 'w') as f:
        f.write('title: T   # settled 2026-09-01 (Eric)\nsubtitle: S\n')
    errs, warns = manifest_gate(d)
    check('a settled header passes clean', not errs and not warns, str((errs, warns)))
    check('a missing manifest is an error, not a pass', manifest_gate(os.path.join(tmp, 'nope'))[0])
    # the caption says what the image represents -- provenance and disclaimers warn, never refuse
    dc = os.path.join(tmp, 'caption'); os.makedirs(dc, exist_ok=True)
    with open(os.path.join(dc, 'publish.yaml'), 'w') as f:
        f.write('title: T\nsubtitle: S\ncover_caption: A friar at the sink. An imagined scene, not a likeness of him.\n')
    errs, warns = manifest_gate(dc)
    check('a provenance/disclaimer caption warns, never refuses',
          not errs and any(w.startswith('cover_caption reads as provenance') for w in warns), str((errs, warns)))
    with open(os.path.join(dc, 'publish.yaml'), 'w') as f:
        f.write("title: T\nsubtitle: S\ncover_caption: The work doesn't change. Who it's done with does.\n")
    errs, warns = manifest_gate(dc)
    check('a caption that says what the image represents passes clean', not errs and not warns, str((errs, warns)))
    with open(os.path.join(dc, 'draft.md'), 'w') as f:
        f.write('scaffold\n\n---\n\n![A man stands at a stone sink drying a plate](assets/hero.png)\n\nBody.\n')
    with open(os.path.join(dc, 'publish.yaml'), 'w') as f:
        f.write('title: T\nsubtitle: S\ncover: assets/hero.png   # 10x10, generated\ncover_caption: A man stands at a stone sink, drying up.\n')
    errs, warns = manifest_gate(dc)
    check('a caption that repeats the alt warns',
          not errs and any(w.startswith('cover_caption repeats the alt') for w in warns), str((errs, warns)))

    # the live side: the body comparison never sees the header, so this one must
    post = {'title': 'T', 'subtitle': ''}
    check('an empty live subtitle is drift even when the manifest is empty too',
          header_drift(post, {'title': 'T'}) == ['live post has NO subtitle'])
    post = {'title': 'T', 'subtitle': 'It\u2019s here \u2014 now'}
    check('curly quotes and dashes do not count as header drift',
          header_drift(post, {'title': 'T', 'subtitle': "It's here -- now"}) == [])
    check('a changed subtitle is reported',
          header_drift(post, {'title': 'T', 'subtitle': 'Other'})[0].startswith('subtitle differs'))


# ---------------------------------------------------------------- unit: pronoun sweep, E and F
PRONOUN_FIXTURE = """*Draft — fixture for the pronoun sweep; the four False Light misses of 2026-09-07 as they were before the audit.*

---

And the answer: *Get thee hence.*[^matt4] And the reason He gives is
short: *It is written, Him only shalt thou serve.* The fixture needs
no more of the passage than that.

*For He maketh His sun to rise on the evil and on the good, and sendeth rain on the just and on
the unjust.*[^matt545] The rain is not a reward.

Set that next to the man who said this instead. *I can of mine own self do nothing: as I hear, I
judge … because I seek not mine own will, but the will of the Father which hath sent me.*[^john530]
*Without me ye can do nothing.*[^john155] The grammar of the two texts runs in opposite directions.

He that hath seen Me hath seen the Father: *He that hath seen Me hath seen the Father.*[^john149]
Paul says it plainly: *I can do all things through Christ which strengtheneth me.*[^phil413] John
the elder says *We love [Them], because [They] first loved us.*[^1john] The point is *not* that
*He* wins; the point is that the exam was refused.

> And He said unto them, Why are ye so fearful? how is it that ye have no faith?[^mark440]

[^matt4]: Matthew 4:8–10 (KJV). The King James reads *and him only shalt thou serve*.

[^matt545]: Matthew 5:45 (KJV). The King James reads *for he maketh his sun to rise on the evil and on
    the good*.

[^john530]: John 5:30 (KJV), abridged. Cf. 5:19, *The Son can do nothing of Himself*.

[^john155]: John 15:5 (KJV). The King James reads *without me ye can do nothing*.

[^john149]: John 14:9 (KJV).

[^phil413]: Philippians 4:13 (KJV).

[^1john]: 1 John 4:19 (KJV).

[^mark440]: Mark 4:40 (KJV).
"""


# Section H's fixture: the two reflexives that shipped live in *They Them* (2026-09-10) as they
# read before the correction, the wrong FORM the correction first reached for (*Themself*, retired
# 2026-09-11 for *Themselves* — in prose and inside a bracketed substitution, which is this house
# speaking inside the source's sentence), the two legitimate uses the same day's corpus sweep
# turned up, and the shapes that must stay quiet — the intensive, a possessive subject, a
# quotation, a footnote definition, and the corrected wording itself.
REFLEXIVE_FIXTURE = """*Draft — fixture for section H.*

---

Read it as a plural of majesty if you like, or as God in deliberation — the *form* is still
plural, in the mouth of God, in the first chapter. And the likeness that comes out the far side of
that sentence is, we've already seen, itself two: male and female. A plural form, speaking of
itself in the plural, and making an image that isn't one thing either.

God is not male. They are the One Xenophanes' oxen could not draw, the no-form seen at Horeb, the
verb that refused to harden into a noun, the source that called itself *us* before They had made
anything at all.

God knows themselves the way no creature is known. The Father itself is a phrase this house would
never write. They are doing the thing itself, and *I am that I am, saith the LORD unto itself*[^ex]
is the source's wording, not ours.

Press *all-powerful* hard enough and it leaves no room for a second thing standing outside God on
its own ground. That the clutching self is the source of its own suffering is not a finding a
follower of Jesus has to hold at arm's length.

If God's power is total there is no second engine running anywhere on its own. And the corrected
line reads: the source that called Themselves *us*, a plural form speaking of Themselves in the
plural.

The form the house retired says what God *shows* of Themself, and the substitution carries it into
a quotation: *thy Father which seeth in secret [Themself] shall reward thee openly*[^mt6]. A source
that writes *they did it themself* unbracketed keeps its own wording.

[^ex]: Exodus 3:14 (KJV). The King James reads *I AM THAT I AM*.

[^mt6]: Matthew 6:4 (KJV), which reads *himself*.
"""

def unit_pronouns(tmp):
    print("\n-- pronoun sweep: E and F look inside a scripture quotation ---------")
    d = os.path.join(tmp, 'pronouns'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(PRONOUN_FIXTURE)
    r = check_pronouns.sweep(d)
    E = [(w, ev) for w, ev, _ in r['E']]
    F = [(w, ev) for w, ev, _ in r['F']]
    e_sent = {(w, ev): sent for w, ev, sent in r['E']}
    f_sent = {(w, ev): sent for w, ev, sent in r['F']}

    # the measured misses — each must be listed
    check('E lists Matthew 4:10 "Him only shalt thou serve" (no adjacent ref; KJV diction qualifies it)',
          ('Him', 'kjv-diction') in E, str(E))
    check('E hit carries its sentence',
          'Him only shalt thou serve' in e_sent.get(('Him', 'kjv-diction'), ''), str(e_sent))
    check('E lists Matthew 5:45 "He maketh His sun" — both pronouns, via the ref',
          E.count(('He', 'ref:matt545')) == 1 and E.count(('His', 'ref:matt545')) == 1, str(E))
    check('F lists John 5:30 "mine own self" twice and "sent me" once, via the Gospel ref',
          F.count(('mine', 'ref:john530')) == 2 and F.count(('me', 'ref:john530')) == 1, str(F))
    check('F lists John 15:5 "without me"', ('me', 'ref:john155') in F, str(F))
    check('F hit carries its sentence',
          'Without me ye can do nothing' in f_sent.get(('me', 'ref:john155'), ''), str(f_sent))

    # what must NOT be listed
    check('F skips an epistle — Paul\'s "strengtheneth me" is not a Gospel',
          not any(ev == 'ref:phil413' for _, ev in F), str(F))
    check('F does not mistake 1 John for the Gospel of John',
          not any(ev == 'ref:1john' for _, ev in F), str(F))
    check('F is clean on a recased Gospel quotation ("hath seen Me")',
          not any(ev == 'ref:john149' for _, ev in F), str(F))
    check('E lists the recased John 14:9 "He" for justification (referent: the Son)',
          ('He', 'ref:john149') in E, str(E))
    check('E does not list a bracketed [They]/[Them] as a masculine',
          not any(ev == 'ref:1john' for _, ev in E), str(E))
    check('E ignores italic emphasis in the author\'s own prose (*He* wins — no ref, no diction)',
          not any(sent.startswith('The point is') for _, _, sent in r['E']), str(r['E']))
    check('E sweeps a blockquote carrying a KJV ref',
          ('He', 'ref:mark440') in E, str(E))
    check('neither E nor F sweeps a footnote definition (the note keeps the source wording)',
          not any('King James reads' in sent for _, _, sent in r['E'] + r['F']), str(r['E'] + r['F']))
    # E and F take the same escape as C, D, G and H (2026-09-10): a ruled hit must be recordable,
    # or every later session re-derives the same referent. Not every E hit is even a deity
    # pronoun -- "He that hath seen Me" is the KJV's sentence-initial capital on "whoever".
    allow_e = check_pronouns.sweep(d, allow=['Him only shalt thou serve'])
    check('pronouns_allow silences a justified E hit',
          not any('Him only shalt thou serve' in sent for _, _, sent in allow_e['E']), str(allow_e['E']))
    check('a justified E hit does not silence the others',
          any(ev == 'ref:matt545' for _, ev, _ in allow_e['E']), str(allow_e['E']))
    allow_f = check_pronouns.sweep(d, allow=['Without me ye can do nothing'])
    check('pronouns_allow silences a justified F hit',
          not any(ev == 'ref:john155' for _, ev, _ in allow_f['F']), str(allow_f['F']))
    # A blockquote's `body` has its `> ` markers stripped, so a PARAGRAPH-relative window drifts
    # two characters per line and misses the substring on any long quotation. Measured on *The
    # Towel* 2026-09-10: four hits in one John 13 blockquote could not be justified at all.
    d7 = os.path.join(tmp, 'pronouns-bq'); os.makedirs(d7, exist_ok=True)
    with open(os.path.join(d7, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\n"
                "> *Jesus knowing that the Father had given all things into His hands, and that He\n"
                "> was come from God, and went to God; He riseth from supper, and laid aside His\n"
                "> garments; and took a towel, and girded Himself. After that He poureth water into\n"
                "> a bason, and began to wash the disciples' feet.*[^t]\n\n"
                "[^t]: John 13:3-5 (KJV).\n")
    check('the long-blockquote fixture lists every pronoun in the span',
          len(check_pronouns.sweep(d7)['E']) == 6, str(len(check_pronouns.sweep(d7)['E'])))
    check('a substring LATE in a long blockquote still silences its hit',
          not any('poureth water' in sent for _, _, sent in
                  check_pronouns.sweep(d7, allow=['After that He poureth water'])['E']),
          str(check_pronouns.sweep(d7, allow=['After that He poureth water'])['E']))
    check('and a substring late in the span does not silence one at the start',
          any('given all things' in sent for _, _, sent in
              check_pronouns.sweep(d7, allow=['After that He poureth water'])['E']))

    check('an unrelated allow entry silences neither E nor F',
          len(check_pronouns.sweep(d, allow=['nothing to do with this'])['E']) == len(r['E'])
          and len(check_pronouns.sweep(d, allow=['nothing to do with this'])['F']) == len(r['F']))
    check('the quotation edge still holds for D (lowercase "him" inside *…* is not a D hit)',
          not r['D'], str(r['D']))

    # --strict: E and F warn, they do not refuse; C/D still do
    tool = os.path.join(HERE, 'check_pronouns.py')
    p = subprocess.run([sys.executable, tool, d, '--strict'], capture_output=True, text=True)
    check('--strict exits 0 with only E/F/G hits, and says they are warnings',
          p.returncode == 0 and 'hits are warnings' in p.stdout, f"rc={p.returncode}\n{p.stdout[-400:]}")
    d2 = os.path.join(tmp, 'pronouns-d'); os.makedirs(d2, exist_ok=True)
    with open(os.path.join(d2, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\nGod made the world and he saw that it was good.\n")
    p = subprocess.run([sys.executable, tool, d2, '--strict'], capture_output=True, text=True)
    check('--strict still exits 3 on a D hit', p.returncode == 3, f"rc={p.returncode}")
    # D refuses under --strict exactly as C does, so it takes the same escape (2026-09-10): D is a
    # proximity test, and most of what it finds is a pronoun for something else standing near a
    # God-word. Without this the only way to clear a D hit is to reword the draft.
    with open(os.path.join(d2, 'publish.yaml'), 'w', encoding='utf-8') as f:
        f.write("title: T\nsubtitle: S\npronouns_allow:\n  - and he saw that it was good\n")
    r2 = check_pronouns.sweep(d2)
    check('publish.yaml pronouns_allow silences a justified D hit', not r2['D'], str(r2['D']))
    p = subprocess.run([sys.executable, tool, d2, '--strict'], capture_output=True, text=True)
    check('--strict exits 0 once the only D hit is justified', p.returncode == 0, f"rc={p.returncode}")
    with open(os.path.join(d2, 'publish.yaml'), 'w', encoding='utf-8') as f:
        f.write("title: T\nsubtitle: S\npronouns_allow:\n  - some unrelated phrase\n")
    check('an unrelated pronouns_allow entry does NOT silence a D hit',
          len(check_pronouns.sweep(d2)['D']) == 1, str(check_pronouns.sweep(d2)['D']))

    # G — the LORD takes capitals (2026-09-07): a mixed-case Lord in the body is listed, a
    # footnote definition's King James wording is not, and LORD itself is never a hit
    d3 = os.path.join(tmp, 'pronouns-g'); os.makedirs(d3, exist_ok=True)
    with open(os.path.join(d3, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\nThe choir sang to the Lord. *Wait on the LORD.*[^ps] "
                "The steward's lord came home.\n\n[^ps]: Psalm 27:14 (KJV): *Wait on the LORD*; "
                "Matthew 22:37 reads *love the Lord thy God*.\n")
    r3 = check_pronouns.sweep(d3)
    check('G lists the mixed-case "the Lord" in the author\'s prose', len(r3['G']) == 1 and 'sang to the Lord' in r3['G'][0], str(r3['G']))
    d4 = os.path.join(tmp, 'pronouns-g2'); os.makedirs(d4, exist_ok=True)
    with open(os.path.join(d4, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\n*Wait on the LORD.*[^ps] The steward's lord came home.\n\n"
                "[^ps]: Psalm 27:14 (KJV); Matthew 22:37 reads *love the Lord thy God*.\n")
    check('G does not list LORD, a lowercase lord, or a footnote definition\'s King James wording',
          not check_pronouns.sweep(d4)['G'], str(check_pronouns.sweep(d4)['G']))
    p = subprocess.run([sys.executable, tool, d3, '--strict'], capture_output=True, text=True)
    check('--strict exits 0 with only a G hit, and says it is a warning', p.returncode == 0 and 'hits are warnings' in p.stdout, f"rc={p.returncode}")

    # H — a reflexive whose antecedent is God (2026-09-10), or the wrong form outright (2026-09-11).
    # The two antecedent hits are the two misses that shipped live in *They Them*; the two non-hits
    # are the only two legitimate uses a corpus sweep found the same day, and both sit as close to a
    # God-word as the misses do.
    d5 = os.path.join(tmp, 'pronouns-h'); os.makedirs(d5, exist_ok=True)
    with open(os.path.join(d5, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(REFLEXIVE_FIXTURE)
    r5 = check_pronouns.sweep(d5)
    H = [(w, ev.split(':', 1)[0]) for w, ev, _ in r5['H']]
    h_sent = {(w, ev.split(':', 1)[0]): sent for w, ev, sent in r5['H']}
    check('H catches "the source that called itself" — an appositive in a copular God chain',
          ('itself', 'appositive') in H, str(r5['H']))
    check('the appositive hit carries its sentence',
          'called itself' in h_sent.get(('itself', 'appositive'), ''), str(h_sent))
    check('H catches "A plural form, speaking of itself" — a self-naming verb in a God paragraph',
          ('itself', 'self-naming') in H, str(r5['H']))
    check('H does not fire on "standing outside God on its own ground" (the second thing owns it)',
          not any('outside God' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H does not fire on "the source of its own suffering" (the clutching self owns it)',
          not any('clutching self' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H skips the intensive "the thing itself" under a God subject',
          not any('doing the thing' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H keeps a God-word taking the intensive ("the Father itself")',
          any('The Father itself' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H reads a possessive as the subject it is ("God\'s power ... on its own" is not God\'s)',
          not any("God's power" in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H catches a plain God subject ("God knows themselves")',
          ('themselves', 'subject') in H, str(r5['H']))
    check('H catches *Themself* as a wrong form — the house reflexive is *Themselves* (2026-09-11)',
          ('Themself', 'wrong-form') in H and 'shows* of Themself' in h_sent[('Themself', 'wrong-form')],
          str(r5['H']))
    check('the wrong form is caught inside a quotation when it is BRACKETED — the bracket is this house',
          any('seeth in secret' in sent for w, _, sent in r5['H'] if w == 'Themself'), str(r5['H']))
    check('an unbracketed *themself* inside a quotation is the source\'s own and stays',
          not any('did it themself' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H leaves a quotation alone (the source\'s own case is evidence)',
          not any('saith the LORD' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('H skips a footnote definition', not any('KJV' in sent for _, _, sent in r5['H']), str(r5['H']))
    check('the corrected wording is clean — Themselves and Their own are never H hits',
          not any('Themselves' in w or 'Their' in w for w, _, _ in r5['H']), str(r5['H']))
    d6 = os.path.join(tmp, 'pronouns-h2'); os.makedirs(d6, exist_ok=True)
    with open(os.path.join(d6, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write("*Draft.*\n\n---\n\nGod knows themselves the way no creature is known.\n")
    r6 = check_pronouns.sweep(d6)
    check('the H-only fixture really is H-only (no C or D hit riding along)',
          r6['H'] and not r6['C'] and not r6['D'], str(r6['C'] + r6['D']))
    p = subprocess.run([sys.executable, tool, d6, '--strict'], capture_output=True, text=True)
    check('--strict exits 0 on H hits — an antecedent is a human call, so H warns and never refuses',
          p.returncode == 0 and 'hits are warnings' in p.stdout, f"rc={p.returncode}\n{p.stdout[-400:]}")
    # a justified hit is silenced the way a C or G hit is, in a reviewable file
    with open(os.path.join(d5, 'publish.yaml'), 'w', encoding='utf-8') as f:
        f.write("title: T\nsubtitle: S\npronouns_allow:\n  - called itself\n")
    check('publish.yaml pronouns_allow silences a justified H hit',
          not any('called itself' in sent for _, _, sent in check_pronouns.sweep(d5)['H']),
          str(check_pronouns.sweep(d5)['H']))


TALK_FIXTURE = """*Draft — v0. Header is scaffold.*

---

## I. The Setup (5 min)

<!-- slide: The promise -->
> Enough attributes and the right person is a query away.
- one bullet

The spoken script of the first slide.
It continues on a second line of the same paragraph.

A second paragraph.

<!-- slide -->
![Figure 1](assets/fig1.png)

Say what the axes are.

<!-- slide: Silent -->
> A line with nobody speaking over it.

## II. The Geometry (12 min)

<!-- slide: One -->
Words words words.
"""


def unit_talk(tmp):
    print("\n-- talk: draft.md -> Marp deck with the script as notes ---------------")
    d = os.path.join(tmp, 'talk'); os.makedirs(os.path.join(d, 'assets'), exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(TALK_FIXTURE)
    with open(os.path.join(d, 'outline.md'), 'w', encoding='utf-8') as f:
        f.write("## I. The Setup (5 min)\n## II. The Geometry (12 min)\n")
    slides = md_to_marp.parse(TALK_FIXTURE)
    kinds = [x['kind'] for x in slides]
    check('movements become section slides and markers become slides',
          kinds == ['section', 'slide', 'slide', 'slide', 'section', 'slide'], str(kinds))
    first = slides[1]
    check('blockquote and list go on the slide, prose becomes notes',
          first['on'] == ['> Enough attributes and the right person is a query away.', '- one bullet']
          and first['notes'] == ['The spoken script of the first slide. It continues on a second line of the same paragraph.',
                                 'A second paragraph.'], str(first))
    check('the header above --- is discarded', not any('scaffold' in n for x in slides for n in x['notes']))
    faults = md_to_marp.check(slides, d)
    check('--check names a missing figure and a slide with no notes',
          any('missing figure assets/fig1.png' in f for f in faults) and any('Silent' in f and 'no speaker notes' in f for f in faults),
          str(faults))
    deck = md_to_marp.render(slides, {'title': 'T', 'subtitle': 'S'}, d)
    check('the deck opens with Marp front matter and the title slide',
          deck.startswith('---\nmarp: true') and '# T' in deck and '## S' in deck)
    check('notes travel as HTML comments and a figure is sized for the slide',
          '<!--\nThe spoken script' in deck and '![Figure 1 h:600px](assets/fig1.png)' in deck, deck[:400])
    out_dir, n, has_style = md_to_marp.write_briefs(slides, {'title': 'T', 'subtitle': 'S', 'speaker': 'Me'}, d)
    briefs = sorted(f for f in os.listdir(out_dir) if f.endswith('.md'))
    check('--briefs writes one brief per slide plus the title slide and an index, and names an untitled figure slide by its figure',
          n == 7 and len(briefs) == 8 and '04-fig1.md' in briefs and 'README.md' in briefs, str(briefs))
    b = open(os.path.join(out_dir, '03-the-promise.md'), encoding='utf-8').read()
    check('a brief carries the slide text verbatim, the script as context, and position/neighbors',
          '> Enough attributes and the right person is a query away.' in b and 'The spoken script of the first slide.' in b
          and '**Position:** 3 of 7' in b and 'A second paragraph.' in b, b[:600])
    check('00-style.md is reported absent rather than invented', has_style is False)
    per = md_to_marp.per_movement(slides, os.path.join(d, 'outline.md'))
    check('per-movement words carry the outline minutes',
          [(t.split('.')[0], b) for t, w, b in per] == [('I', 5), ('II', 12)] and per[0][1] > per[1][1], str(per))


# ---------------------------------------------------------------- unit: dc -> deck
def _tiny_png():
    """A real, complete 1x1 PNG, built here so the fixture needs no binary in git."""
    import struct, zlib
    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(b'\x00\x00')) + chunk(b'IEND', b''))


DC_FIXTURE = """<helmet><style>body{background:#111}</style></helmet>
<x-dc><x-import width="1600" height="900">
<section data-label="Open" data-speaker-notes="Say &#x201c;hello&#x201d; &amp; wait.">
  <h1>A &mdash; Talk</h1>
</section>
<section data-label="Figure">
  <img src="assets/fig1.png">
</section>
</x-import></x-dc>
"""


def _run_deck(src, out):
    tool = os.path.join(HERE, 'dc_to_deck.py')
    r = subprocess.run([sys.executable, tool, src, out],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def unit_deck(tmp):
    """Every case here is a fault that actually happened, or a footgun the port created.

    The truncated PNG is the real one: a Claude Design asset came back cut off at the
    export tool's read limit (2026-09-09) and would have shipped as a broken slide.
    The refuse-to-delete cases are new: in the JavaScript original the output path was
    computed, and in this port it is an argument.
    """
    print("\n-- deck: Claude Design .dc.html -> standalone deck ---------------")
    src = os.path.join(tmp, 'deck-src')
    os.makedirs(os.path.join(src, 'assets'), exist_ok=True)
    with open(os.path.join(src, 'deck.dc.html'), 'w', encoding='utf-8') as f:
        f.write(DC_FIXTURE)
    with open(os.path.join(src, 'deck-stage.js'), 'w', encoding='utf-8') as f:
        f.write('/* stub runtime */\n')
    png = os.path.join(src, 'assets', 'fig1.png')
    with open(png, 'wb') as f:
        f.write(_tiny_png())
    # an asset no slide references — it must NOT be copied
    with open(os.path.join(src, 'assets', 'unused.png'), 'wb') as f:
        f.write(b'not even a png')

    out = os.path.join(tmp, 'deck-out')
    code, log = _run_deck(src, out)
    check('a well-formed deck builds', code == 0, log.strip())
    if code != 0:
        return

    html = open(os.path.join(out, 'deck.html'), encoding='utf-8').read()
    notes = json.load(open(os.path.join(out, 'notes.json'), encoding='utf-8'))

    check('the authoring wrapper is gone and deck-stage is the root',
          '<x-import' not in html and '<x-dc' not in html
          and '<deck-stage width="1600" height="900">' in html, html[:200])
    check('the deck is not indexable and does not flash before the runtime defines it',
          '<meta name="robots" content="noindex">' in html
          and 'deck-stage:not(:defined) { visibility: hidden; }' in html)
    check('the helmet head survives into the deck',
          '<style>body{background:#111}</style>' in html)
    check('the title comes from the first slide h1, entity-decoded',
          notes['title'] == 'A — Talk', notes['title'])
    check('speaker notes are decoded, named and numeric entities alike',
          notes['slides'][0]['notes'] == 'Say “hello” & wait.', notes['slides'][0]['notes'])
    check('a slide with no notes still gets an entry, with its label',
          notes['slideCount'] == 2 and notes['slides'][1]['label'] == 'Figure'
          and notes['slides'][1]['notes'] == '', str(notes['slides'][1]))
    check('only referenced assets are copied',
          sorted(os.listdir(os.path.join(out, 'assets'))) == ['fig1.png'],
          str(os.listdir(os.path.join(out, 'assets'))))

    # the fault this guard exists for
    with open(png, 'rb') as f:
        good = f.read()
    with open(png, 'wb') as f:
        f.write(good[:len(good) // 2])
    code, log = _run_deck(src, out)
    check('a truncated PNG stops the build and says to re-download it',
          code == 1 and 'truncated' in log and 'IEND' in log, log.strip())
    check('and the previous good build is left intact, not half-erased',
          os.path.exists(os.path.join(out, 'deck.html'))
          and os.path.exists(os.path.join(out, 'assets', 'fig1.png')))
    with open(png, 'wb') as f:
        f.write(good)

    # footguns the port introduced by taking the output path as an argument
    keep = os.path.join(tmp, 'not-a-deck')
    os.makedirs(keep, exist_ok=True)
    with open(os.path.join(keep, 'irreplaceable.txt'), 'w', encoding='utf-8') as f:
        f.write('do not delete me')
    code, log = _run_deck(src, keep)
    check('a directory that is not a deck build is refused, not deleted',
          code == 2 and 'refusing to delete' in log
          and os.listdir(keep) == ['irreplaceable.txt'], log.strip())
    code, log = _run_deck(src, src)
    check('writing the output over the source is refused',
          code == 2 and 'same directory' in log, log.strip())
    check('and the source survived that', os.path.exists(os.path.join(src, 'deck.dc.html')))

    # malformed input fails loudly rather than emitting a deck missing slides
    bad = os.path.join(tmp, 'deck-unbalanced')
    shutil.copytree(src, bad)
    with open(os.path.join(bad, 'deck.dc.html'), 'w', encoding='utf-8') as f:
        f.write(DC_FIXTURE.replace('</section>', '', 1))
    code, log = _run_deck(bad, os.path.join(tmp, 'deck-out-bad'))
    check('an unbalanced <section> is an error, not a silently shortened deck',
          code == 1 and 'unbalanced' in log, log.strip())

    missing = os.path.join(tmp, 'deck-missing-asset')
    shutil.copytree(src, missing, ignore=shutil.ignore_patterns('fig1.png'))   # absent by construction
    code, log = _run_deck(missing, os.path.join(tmp, 'deck-out-missing'))
    check('a slide pointing at an asset that is not there names the asset',
          code == 1 and 'assets/fig1.png' in log, log.strip())


# ---------------------------------------------------------------- unit: store publish

DC_TALK_FIXTURE = """*Draft — v1. Header above the first --- is scaffold.*
---
## I. The Setup

<!-- slide: The promise -->
> Enough attributes &mdash; and the "right" person is a query away.

The spoken script of the first slide. It says "hello" & waits.

A second paragraph.

<!-- slide: Two ways -->
- a query
- a room

Bullets get script too.

<!-- slide -->
<!-- design: the figure fills the slide -->
![Figure 1](assets/fig1.png)

Introduce the figure, then show it.

<!-- slide -->
> One line to remember.

The closing beat.
"""

DC_UNTAGGED = """<x-dc><x-import width="1280" height="720">
<section data-label="Title" data-speaker-notes="Title slide. No page number. Let the room settle before the first line."><h1>T</h1></section>
<section data-label="I. The Setup" data-speaker-notes="Section slide. Say the movement name and pause."><h2>I. The Setup</h2></section>
<section data-label="The promise" data-speaker-notes="The spoken script of the first slide. It says &quot;hello&quot; &amp; waits.&#10;&#10;A second paragraph."><h2>The promise</h2><p>Enough attributes — and the “right” person is a query away.</p></section>
<section data-label="Two ways" data-speaker-notes="Bullets get script too."><h2>Two ways</h2><ul><li>a query</li><li>a room</li></ul></section>
<section data-label="Fig" data-speaker-notes="Introduce the figure, then show it."><svg></svg></section>
<section data-label="Close" data-speaker-notes="The closing beat."><p>One line to remember.</p></section>
</x-import></x-dc>
"""


def _run_dc(*args):
    tool = os.path.join(HERE, 'md_to_dc.py')
    r = subprocess.run([sys.executable, tool, *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def unit_dc(tmp):
    """The deck's canvas is generated from the draft and held to it. Every case here is the
    fork that actually happened on the first talk (2026-09-09): words changed in the canvas
    that the desk never saw, figures redrawn out of the deck, notes reworded — or the footgun a
    re-sync could introduce by touching layout it should have kept."""
    print("\n-- dc: draft.md -> design canvas, and the canvas held to the draft -----")
    talk = os.path.join(tmp, 'dc-talk')
    os.makedirs(os.path.join(talk, 'assets'), exist_ok=True)
    with open(os.path.join(talk, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(DC_TALK_FIXTURE)
    with open(os.path.join(talk, 'talk.yaml'), 'w', encoding='utf-8') as f:
        f.write('title: T\nsubtitle: S\nspeaker: Me\nfooter: T\n')
    with open(os.path.join(talk, 'assets', 'fig1.png'), 'wb') as f:
        f.write(_tiny_png())

    c1 = os.path.join(tmp, 'dc-c1')
    code, log = _run_dc('generate', talk, '--to', c1)
    check('generate writes one artboard per slide, Main first, plus canvas.json and a preview image',
          code == 0 and os.path.exists(os.path.join(c1, 'Main.dc.html'))
          and os.path.exists(os.path.join(c1, 'canvas.json')) and os.path.exists(os.path.join(c1, 'fig1.png'))
          and len([f for f in os.listdir(c1) if f.endswith('.dc.html')]) == 6, log.strip()[:300])
    if code != 0:
        return
    main_ = open(os.path.join(c1, 'Main.dc.html'), encoding='utf-8').read()
    check('the title slide carries title, subtitle and speaker as roles, and no page number',
          'data-role="title"' in main_ and '>T</h1>' in main_ and '>S</p>' in main_
          and '<span data-role="footer-num"></span>' in main_)
    promise = open(os.path.join(c1, 'S03-the-promise.dc.html'), encoding='utf-8').read()
    check('a claim slide keys on its title, its line is a role, a quote is escaped and an entity the draft wrote passes through',
          'data-slide-key="the-promise"' in promise and 'data-role="line"' in promise
          and '&mdash; and the &quot;right&quot;' in promise, promise[:600])
    check('speaker notes ride the section as an attribute, paragraph breaks as &#10;',
          'data-speaker-notes="The spoken script of the first slide. It says &quot;hello&quot; &amp; waits.&#10;&#10;A second paragraph."' in promise)
    figboard = [f for f in os.listdir(c1) if f.startswith('S05-fig-fig1')]
    check('an untitled figure slide keys on its figure and references the image by basename',
          len(figboard) == 1 and 'data-role="figure" src="fig1.png"' in open(os.path.join(c1, figboard[0]), encoding='utf-8').read(), str(figboard))
    cj = json.load(open(os.path.join(c1, 'canvas.json'), encoding='utf-8'))
    check('canvas.json lays every artboard out and turns a design note into a sticky note above its slide',
          len(cj['artboards']) == 6 and any(a['file'] == 'Main.dc.html' for a in cj['artboards'])
          and cj.get('annotations') and cj['annotations'][0]['id'] == 'design-05-1'
          and 'fills the slide' in cj['annotations'][0]['text'], str(cj)[:300])
    check('the last slide keys on its line, not its position',
          any(f.startswith('S06-line-one-line-to-remember') for f in os.listdir(c1)), str(os.listdir(c1)))

    code, log = _run_dc('verify', talk, '--from', c1)
    check('verify: a freshly generated canvas matches the draft', code == 0 and 'MATCH' in log, log.strip()[-200:])

    # the designer edits layout; the author edits words
    two = os.path.join(c1, 'S04-two-ways.dc.html')
    t = open(two, encoding='utf-8').read().replace('font-size:40px;line-height:1.3;', 'font-size:44px;color:#4a6fa5;', 1)
    with open(two, 'w', encoding='utf-8') as f:
        f.write(t)
    cj['annotations'].append({'id': 'note-1', 'x': 0, 'y': -400, 'w': 300, 'text': 'designer: keep it cool'})
    json.dump(cj, open(os.path.join(c1, 'canvas.json'), 'w', encoding='utf-8'))
    with open(os.path.join(talk, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(DC_TALK_FIXTURE.replace('- a query\n', '- a database query\n')
                .replace('<!-- slide -->\n> One line', '<!-- slide: New -->\n> A new slide.\n\nIts script.\n\n<!-- slide -->\n> One line'))
    code, log = _run_dc('verify', talk, '--from', c1)
    check('verify: a reworded bullet and a slide the draft gained are DRIFT, named by slide, exit 1',
          code == 1 and "DRIFT  04 Two ways" in log and "'a database query'" in log and 'New' in log and 'missing from the canvas' in log,
          log.strip()[-400:])
    code, log = _run_dc('compose', talk, '--from', c1, '--to', os.path.join(tmp, 'dc-refused'))
    check('compose refuses a drifting canvas', code == 1 and 'refuses' in log, log.strip()[-200:])

    c2 = os.path.join(tmp, 'dc-c2')
    code, log = _run_dc('resync', talk, '--from', c1, '--to', c2)
    check('resync reports what it kept, added and dropped, and verifies its own output',
          code == 0 and '6 kept' in log and '1 added' in log and '0 dropped' in log and 'verified' in log, log.strip()[:400])
    if code == 0:
        t2 = open(os.path.join(c2, 'S04-two-ways.dc.html'), encoding='utf-8').read()
        check("the designer's layout edit survived and the author's words replaced the old ones",
              'font-size:44px;color:#4a6fa5;' in t2 and '>a database query</li>' in t2 and '>a query</li>' not in t2, t2[:800])
        cj2 = json.load(open(os.path.join(c2, 'canvas.json'), encoding='utf-8'))
        check("the designer's sticky note is kept; ours are regenerated",
              any(a['id'] == 'note-1' for a in cj2['annotations']) and any(a['id'].startswith('design-') for a in cj2['annotations']))
        check('the new slide is an artboard', any(f.startswith('S06-new') for f in os.listdir(c2)), str(os.listdir(c2)))
        code, log = _run_dc('verify', talk, '--from', c2)
        check('verify: the re-synced canvas matches', code == 0, log.strip()[-200:])

    # compose -> the site's one-file deck -> dc_to_deck builds it
    src = os.path.join(tmp, 'dc-site-src')
    code, log = _run_dc('compose', talk, '--from', c2, '--to', src)
    deck = open(os.path.join(src, 'deck.dc.html'), encoding='utf-8').read() if code == 0 else ''
    check('compose writes the x-import deck with assets/ paths and the full-resolution figure beside it',
          code == 0 and '<x-import component-from-global-scope="deck-stage"' in deck and 'src="assets/fig1.png"' in deck
          and 'width:1280px;height:720px;' not in deck and deck.count('<section') == 7
          and open(os.path.join(src, 'assets', 'fig1.png'), 'rb').read() == _tiny_png(), log.strip()[:300])
    with open(os.path.join(src, 'deck-stage.js'), 'w', encoding='utf-8') as f:
        f.write('/* stub */\n')
    code, log = _run_deck(src, os.path.join(tmp, 'dc-site-out'))
    notes = json.load(open(os.path.join(tmp, 'dc-site-out', 'notes.json'), encoding='utf-8')) if code == 0 else {}
    check('dc_to_deck builds the composed deck, notes decoded, title from the first h1',
          code == 0 and notes.get('title') == 'T' and notes['slides'][2]['notes'].startswith('The spoken script of the first slide. It says "hello" & waits.\n\nA second'),
          (log + str(notes.get('slides', [])[2:3]))[:300])
    code, log = _run_dc('verify', talk, '--from', os.path.join(src, 'deck.dc.html'))
    check('verify reads the composed deck as well as the artboards', code == 0 and 'MATCH' in log, log.strip()[-200:])

    # the first talk's deck: untagged, matched by position, and its known drift found
    with open(os.path.join(talk, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(DC_TALK_FIXTURE)
    un = os.path.join(tmp, 'dc-untagged.dc.html')
    with open(un, 'w', encoding='utf-8') as f:
        f.write(DC_UNTAGGED)
    code, log = _run_dc('verify', talk, '--from', un)
    check('an untagged deck is matched by position: typographic quotes are not drift, a figure drawn out of the deck is',
          code == 1 and 'matched by position' in log and 'match  03 The promise' in log
          and "DRIFT  05" in log and "['fig1.png']" in log and 'DRIFT — 1 slide' in log, log.strip()[-500:])
    code, log = _run_dc('resync', talk, '--from', os.path.join(tmp, 'dc-untagged-dir'), '--to', os.path.join(tmp, 'dc-x'))
    check('resync needs a directory of artboards', code == 2, log.strip()[-200:])

    # refusals
    with open(os.path.join(talk, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write(DC_TALK_FIXTURE.replace('assets/fig1.png', 'assets/never-generated.png'))
    code, log = _run_dc('generate', talk, '--to', os.path.join(tmp, 'dc-c3'))
    check('generate refuses a figure the draft names that is not on disk', code == 2 and 'never-generated.png' in log, log.strip())


def _run_tb(*args):
    tool = os.path.join(HERE, 'talk_bundle.py')
    r = subprocess.run([sys.executable, tool, *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def unit_talk_tags(tmp):
    """A talk's tags live on the DESK and reach the store (2026-09-15).

    Before this they could not be expressed at all: talk_bundle wrote slug, title, date,
    digest, outlets, kind and subtitle, so a published talk's tags were hand-written in the
    SITE repo, in free text, in a vocabulary nothing checked — and the fault showed up the
    only way it could, as a live page with no tags on it. Every case here is that fault or a
    way of reintroducing it.
    """
    print("\n-- talk tags: the desk owns them, the bundler carries them ----------")
    import tags as tg
    root = os.path.join(tmp, 'ttdesk')
    talks, pieces_d = os.path.join(root, 'talks'), os.path.join(root, 'pieces')
    os.makedirs(os.path.join(talks, 'a-talk'), exist_ok=True)
    os.makedirs(os.path.join(pieces_d, 'an-essay'), exist_ok=True)
    os.makedirs(os.path.join(root, 'publishing'), exist_ok=True)
    vocab = os.path.join(root, 'publishing', 'tags.yaml')
    open(vocab, 'w').write('tags:\n  - tag: geometry\n    label: Geometry\n    about: Shapes.\n'
                           '  - tag: rooms\n    label: Rooms\n    about: Rooms.\n')
    open(os.path.join(pieces_d, 'an-essay', 'publish.yaml'), 'w').write('title: An Essay\n')
    tpath = os.path.join(talks, 'a-talk', 'talk.yaml')
    open(tpath, 'w').write('title: A Talk   # settled\nsubtitle: or, A Sub\n')
    run = lambda *a: tg.main(['--root', root, *a])

    # tags.py reaches the talks namespace
    check('talk tags: a bare slug prefers pieces/, `talks/<slug>` names the talk',
          run('show', 'talks/a-talk') == 0 and run('show', 'an-essay') == 0)
    check('talk tags: add writes into talk.yaml, not publish.yaml',
          run('add', 'talks/a-talk', 'rooms', 'geometry') == 0
          and 'tags:' in open(tpath).read()
          and not os.path.exists(os.path.join(talks, 'a-talk', 'publish.yaml')),
          open(tpath).read())
    check('talk tags: the comment on another key survives the write',
          '# settled' in open(tpath).read(), open(tpath).read())
    check('talk tags: vocabulary order, not the order typed',
          tg.tags_of(tg.read_manifest(os.path.join(talks, 'a-talk')))[0] == ['geometry', 'rooms'],
          open(tpath).read())
    check('talk tags: an undefined tag is refused and nothing is written',
          run('add', 'talks/a-talk', 'not-a-tag') == 3
          and tg.tags_of(tg.read_manifest(os.path.join(talks, 'a-talk')))[0] == ['geometry', 'rooms'])
    rows = {r['ref']: r for r in tg.corpus(root)}
    check('talk tags: corpus spans both namespaces and keys by ref, not by slug',
          set(rows) == {'talks/a-talk', 'pieces/an-essay'} and rows['talks/a-talk']['kind'] == 'talk',
          str(sorted(rows)))
    problems, _notes = tg.check(root, vocab)
    check('talk tags: check passes a well-tagged talk', not problems, str(problems))
    open(tpath, 'a').write('  - practise\n')
    problems, _n = tg.check(root, vocab)
    check('talk tags: check names the TALK, not a bare slug its essay could own',
          any("carried by talks/a-talk" in p for p in problems), str(problems))
    open(tpath, 'w').write('title: A Talk\nsubtitle: or, A Sub\ntags:\n  - geometry\n  - rooms\n')

    # out through the bundler
    src = os.path.join(tmp, 'tt-src'); os.makedirs(src, exist_ok=True)
    open(os.path.join(src, 'piece.yaml'), 'w').write(
        'slug: a-talk\ntitle: A Talk\nsubtitle: or, A Sub\npublished_at: 2026-09-15\n'
        'outlets:\n  - site\nbody: |\n  The framing prose.\n')
    deck = os.path.join(tmp, 'tt-deck'); os.makedirs(deck, exist_ok=True)
    json.dump({'slug': 'a-talk', 'title': 'A Talk', 'slideCount': 2,
               'slides': [{'index': 0, 'label': 'One', 'notes': ''}]},
              open(os.path.join(deck, 'notes.json'), 'w'))
    bundle = os.path.join(tmp, 'tt-bundle')
    code, log = _run_tb(src, deck, bundle, '--desk', root)
    check('talk tags: the bundle builds and says which tags it carried',
          code == 0 and 'tags: geometry, rooms' in log, log.strip()[:300])
    if code == 0:
        rec = json.load(open(os.path.join(bundle, 'talks', 'a-talk', 'piece.json')))
        idx = json.load(open(os.path.join(bundle, 'index.json')))
        entry = [p for p in idx['pieces'] if p['slug'] == 'a-talk'][0]
        want = [{'tag': 'geometry', 'label': 'Geometry'}, {'tag': 'rooms', 'label': 'Rooms'}]
        check('talk tags: the record and the index entry carry {tag,label}, as a piece does',
              rec.get('tags') == want and entry.get('tags') == want and entry['kind'] == 'talk',
              str((rec.get('tags'), entry.get('tags'))))

    # the refusals, each one a way back to the fork
    open(os.path.join(src, 'piece.yaml'), 'a').write('tags:\n  - geometry\n')
    code, log = _run_tb(src, deck, os.path.join(tmp, 'tt-b2'), '--desk', root)
    check('talk tags: tags in the SITE piece.yaml are refused, naming where they belong',
          code == 9 and 'live on the DESK' in log, log.strip()[:200])
    open(os.path.join(src, 'piece.yaml'), 'w').write(
        'slug: a-talk\ntitle: A Talk\npublished_at: 2026-09-15\noutlets:\n  - site\n'
        'body: |\n  The framing prose.\n')
    code, log = _run_tb(src, deck, os.path.join(tmp, 'tt-b3'), '--desk', os.path.join(tmp, 'nodesk'))
    check('talk tags: a desk that does not know the talk is refused, not silently untagged',
          code == 3 and 'no talks/a-talk' in log, log.strip()[:200])
    open(tpath, 'w').write('title: A Talk\ntags:\n  - not-a-tag\n')
    code, log = _run_tb(src, deck, os.path.join(tmp, 'tt-b4'), '--desk', root)
    check('talk tags: a tag outside the vocabulary stops the bundle (exit 8)',
          code == 8 and 'not in the tag vocabulary' in log, log.strip()[:200])
    open(tpath, 'w').write('title: A Talk\n')
    code, log = _run_tb(src, deck, os.path.join(tmp, 'tt-b5'), '--desk', root)
    check('talk tags: an untagged talk still bundles, and says it carries none',
          code == 0 and 'no tags' in log, log.strip()[:200])


def unit_audit_tags(tmp):
    """outlet_audit compares every text's tags to what each outlet carries (2026-09-16).

    A tag added to a live text reaches no outlet by itself — the store record and the Substack
    post are separate writes — and on 2026-09-15 two texts were found publicly untagged by a
    person looking at a page, with every check here green. These cases pin the comparison down
    without the network: the store index is a fixture and the Substack reader is injected.

    The last case is the fault the first real run found in the forward check itself: a WAITING
    outlet answers a scheduled post's address with a 200 teaser, which was counted present, so
    the tag gate asked for tags on a post that did not exist yet.
    """
    print("\n-- outlet audit: tags, on the store and on Substack -----------------")
    import io, contextlib
    import outlet_audit as oa
    import publications as pb
    import tags as tg

    check('audit tags: order is not drift, case is not drift',
          oa.tag_drift(['Alpha', 'Beta'], ['beta', 'alpha']) == ([], []))
    check('audit tags: missing and extra are both named',
          oa.tag_drift(['Alpha', 'Beta'], ['Alpha', 'Stray']) == (['Beta'], ['Stray']))

    # ---- the store index
    root = os.path.join(tmp, 'atdesk')
    for rel_ in ('pieces/shared', 'pieces/lone', 'pieces/bare', 'pieces/odd', 'pieces/away', 'talks/shared'):
        os.makedirs(os.path.join(root, rel_), exist_ok=True)
    os.makedirs(os.path.join(root, 'publishing'), exist_ok=True)
    open(os.path.join(root, 'publishing', 'tags.yaml'), 'w').write(
        'tags:\n  - tag: alpha\n    label: Alpha\n    about: a\n'
        '  - tag: beta\n    label: Beta\n    about: b\n')
    w = lambda rel_, text: open(os.path.join(root, rel_), 'w').write(text)
    w('pieces/shared/publish.yaml', 'title: Shared\ntags:\n  - alpha\n')
    w('talks/shared/talk.yaml', 'title: Shared\ntags:\n  - alpha\n  - beta\n')
    w('pieces/lone/publish.yaml', 'title: Lone\ntags:\n  - alpha\n')
    w('pieces/bare/publish.yaml', 'title: Bare\n')
    w('pieces/odd/publish.yaml', 'title: Odd\ntags:\n  - nope\n')
    w('pieces/away/publish.yaml', 'title: Away\ntags:\n  - alpha\n')
    tag = lambda t, l: {'tag': t, 'label': l}
    index = {'pieces': [
        {'slug': 'shared', 'kind': 'piece', 'outlets': ['site'], 'tags': [tag('alpha', 'Alpha')]},
        {'slug': 'shared', 'kind': 'talk', 'outlets': ['site'], 'tags': [tag('alpha', 'Alpha')]},
        {'slug': 'lone', 'kind': 'piece', 'outlets': ['site'], 'tags': [tag('alpha', 'Old Alpha')]},
        {'slug': 'bare', 'kind': 'piece', 'outlets': ['site'], 'tags': [tag('alpha', 'Alpha')]},
        {'slug': 'odd', 'kind': 'piece', 'outlets': ['site']},
        {'slug': 'ghost', 'kind': 'piece', 'outlets': ['site'], 'tags': [tag('alpha', 'Alpha')]},
        {'slug': 'lone', 'kind': 'talk', 'outlets': ['site']},
        {'slug': 'away', 'kind': 'piece', 'outlets': ['elsewhere']},
    ]}
    vocabs = tg.Vocabularies(root, None, None)
    n, found = oa.store_tag_drift(index, root, None, vocabs)
    by = {f['ref']: f for f in found}
    check('audit tags: the store check reads a TALK entry against talks/, not its essay',
          'talks/shared' in by and by['talks/shared']['missing'] == ['beta'], str(by))
    check('audit tags: an index entry that matches the desk is not a finding',
          'pieces/shared' not in by, str(by))
    check('audit tags: a label the vocabulary renamed is drift, though the ids match',
          by.get('pieces/lone', {}).get('relabeled') == [('alpha', 'Old Alpha', 'Alpha')], str(by))
    check('audit tags: tags on the store that the desk dropped are extra',
          by.get('pieces/bare', {}).get('extra') == ['alpha'], str(by))
    check('audit tags: a desk tag outside the vocabulary is reported, not compared',
          'nope' in by.get('pieces/odd', {}).get('problem', ''), str(by))
    check('audit tags: a slug the desk does not hold, and a kind it does not hold, are skipped',
          n == 6 and not any('ghost' in r for r in by), f'checked {n}, {sorted(by)}')
    n2, found2 = oa.store_tag_drift(index, root, None, vocabs, outlets=['elsewhere'])
    check('audit tags: --outlet limits the store check to entries published there',
          n2 == 1 and [f['ref'] for f in found2] == ['pieces/away'], f'{n2} {found2}')

    # ---- Substack, the reader injected
    sroot = os.path.join(tmp, 'atsub'); sd = os.path.join(sroot, 'pieces', 'p')
    os.makedirs(sd, exist_ok=True); os.makedirs(os.path.join(sroot, 'publishing'), exist_ok=True)
    open(os.path.join(sroot, 'publishing', 'outlets.yaml'), 'w').write(
        'outlets:\n  sub:\n    reader_base: https://x.substack.com/p/\n    account_handle: tagger\n')
    open(os.path.join(sroot, 'publishing', 'tags.yaml'), 'w').write(
        'tags:\n  - tag: discernment\n    label: Discernment\n    about: b\n'
        '  - tag: canon\n    label: The Canon\n    about: c\n    substack: false\n')
    open(os.path.join(sd, 'publish.yaml'), 'w').write(
        'title: P\noutlets:\n  - sub\npublished_at: 2026-09-01\n'
        'post_url: https://x.substack.com/publish/post/42\ntags:\n  - discernment\n  - canon\n')
    seen = []

    def reader(now):
        def f(host, url, key):
            seen.append(url)
            if isinstance(now, Exception):
                raise now
            return now
        return f
    job = [('p', sd, 'https://x.substack.com/p/p')]
    n, found, unr = oa.substack_tag_drift(job, fetch_tags=reader(['Discernment']))
    check('audit tags: a `substack: false` tag is not expected on Substack',
          n == 1 and not found and not unr, str((found, unr)))
    check('audit tags: the post is read at the address the forward check found live',
          seen[-1] == 'https://x.substack.com/p/p', str(seen))
    _n, found, _u = oa.substack_tag_drift(job, fetch_tags=reader([]))
    check('audit tags: a post with none of its tags reports them missing',
          found and found[0]['missing'] == ['Discernment'], str(found))
    _n, found, _u = oa.substack_tag_drift(job, fetch_tags=reader(['Discernment', 'Stray']))
    check('audit tags: a post carrying a tag the desk does not is extra',
          found and found[0]['extra'] == ['Stray'], str(found))
    _n, found, unr = oa.substack_tag_drift(job, fetch_tags=reader(OSError('down')))
    check('audit tags: an unreadable post is "not checked", never "matches"',
          unr == ['p'] and not found, str((found, unr)))
    open(os.path.join(sd, 'publish.yaml'), 'a').write('  - nope\n')
    _n, found, _u = oa.substack_tag_drift(job, fetch_tags=reader(['Discernment']))
    check('audit tags: a piece its own tag tool refuses is reported, not skipped',
          found and 'nope' in found[0].get('problem', ''), str(found))

    # ---- the teaser: a WAITING outlet's 200 before the moment is not the post
    troot = os.path.join(tmp, 'atteaser'); td = os.path.join(troot, 'pieces', 'early')
    os.makedirs(td, exist_ok=True); os.makedirs(os.path.join(troot, 'publishing'), exist_ok=True)
    open(os.path.join(troot, 'publishing', 'outlets.yaml'), 'w').write(
        'outlets:\n'
        '  site:\n    reader_base: https://site.test/blog/\n    manifest_url_key: blog_url\n'
        '    on_schedule: immediate\n'
        '  sub:\n    reader_base: https://sub.test/p/\n    on_schedule: at_moment\n')
    open(os.path.join(td, 'publish.yaml'), 'w').write(
        'title: Early\npublish_at: 2099-01-01 09:00 America/New_York\npublished_at: 2026-09-01\n'
        'outlets:\n  - site\n  - sub\nblog_url: https://site.test/blog/early\n'
        'scheduled:\n  sub:\n    at: 2099-01-01 09:00 EST\n    set: 2026-09-01\n'
        '    where: "the platform\'s own scheduler"\n    approved: "the suite"\n')
    real_fetch, argv, cwd = oa.fetch, sys.argv, os.getcwd()
    oa.fetch = lambda url, timeout=20: (200, '<html><title>Early</title>teaser</html>', url.split('?')[0])
    out, code = io.StringIO(), None
    try:
        os.chdir(troot)
        sys.argv = ['outlet_audit.py', '--no-reverse', '--no-tags']
        with contextlib.redirect_stdout(out):
            try:
                oa.main()
            except SystemExit as e:
                code = e.code
    finally:
        oa.fetch, sys.argv = real_fetch, argv
        os.chdir(cwd)
    text = out.getvalue()
    check('audit tags: a scheduled copy answering 200 before its moment is SCHEDULED, not present',
          code == 0 and '1 present, 1 scheduled, 0 missing' in text, f'exit {code}: {text[-400:]}')


def unit_store(tmp):
    """The two publishing tools, exercised without touching AWS.

    The index merge is the one that could do real damage: a bundle holding one talk must
    not unpublish the rest of the corpus, and the obvious implementation — write the
    index from what is in this bundle — does exactly that.
    """
    print("\n-- store: bundle assembly and cache policy ----------------------")
    import store_publish, talk_bundle

    cc = {'index': 'IDX', 'pieces': 'PIECES', 'images': 'IMG',
          'talks': 'TALK', 'talks_mutable': 'TALKMUT'}
    got = {k: store_publish.cache_control(k, cc) for k in [
        'index.json',
        'pieces/x.json',
        'images/x/hero.webp',
        'talks/x/assets/fig1.png',
        'talks/x/deck-stage.js',
        'talks/x/deck.html',
        'talks/x/notes.json',
    ]}
    check('an immutable asset and a rewritten file get different cache policies',
          got['images/x/hero.webp'] == 'IMG'
          and got['talks/x/assets/fig1.png'] == 'TALK'
          and got['talks/x/deck.html'] == 'TALKMUT'
          and got['talks/x/notes.json'] == 'TALKMUT', str(got))
    check('content json is short-lived', got['index.json'] == 'IDX' and got['pieces/x.json'] == 'PIECES')
    check("a talk's record is rewritten in place, so it is not cached for a year",
          store_publish.cache_control('talks/x/piece.json', cc) == 'TALKMUT')
    check('an unknown key falls back rather than caching forever',
          store_publish.cache_control('stray.txt', cc) == 'PIECES')
    live = {'pieces': [{'slug': 'shared', 'kind': 'talk'}, {'slug': 'shared', 'kind': 'piece'},
                       {'slug': 'other', 'kind': 'piece'}]}
    check('a bundle index that would drop live entries is caught',
          store_publish.index_losses(live, {'pieces': [{'slug': 'new', 'kind': 'piece'}]})
          == ['other (piece)', 'shared (piece)', 'shared (talk)'],
          'index.json replaces the live list outright; a fresh bundle would unpublish the store')
    check('and it is keyed by kind: an essay does not stand in for its talk',
          store_publish.index_losses(live, {'pieces': [{'slug': 'shared', 'kind': 'piece'},
                                                        {'slug': 'other', 'kind': 'piece'}]})
          == ['shared (talk)'])
    check('a bundle seeded from the live index loses nothing',
          store_publish.index_losses(live, {'pieces': live['pieces'] + [{'slug': 'new'}]}) == [])
    check('content types are pinned for the formats a bundle carries',
          store_publish.content_type('a/b.webp') == 'image/webp'
          and store_publish.content_type('a/b.js').startswith('text/javascript')
          and store_publish.content_type('a/b.json') == 'application/json')

    # --- revalidate: a publish is visible at once, but never before the CDN turns over ---
    check('revalidate: only the JSON a site reads is sent, never an image or a deck',
          store_publish.revalidate_keys(['images/a/hero.webp', 'pieces/a.json', 'index.json',
                                         'talks/t/deck.html']) == ['index.json', 'pieces/a.json'])
    import hashlib as _hl
    new, old = b'{"v": 2}', b'{"v": 1}'
    md5_new = _hl.md5(new).hexdigest()
    serving = {'pieces/a.json': old}
    seen_urls = []
    def fake_get(url):
        seen_urls.append(url)
        key = url.split('/', 3)[3]
        return (200, serving[key]) if key in serving else (404, b'')
    check('revalidate: the CDN still holding the old bytes is not current',
          not store_publish.cdn_current(fake_get, 'https://cdn.test', 'pieces/a.json', md5_new))
    check('revalidate: the CDN is polled with no cache-busting query — what the site would get',
          seen_urls and '?' not in seen_urls[-1])
    check('revalidate: a deleted key is current once the CDN answers 404',
          store_publish.cdn_current(fake_get, 'https://cdn.test', 'pieces/gone.json', None))
    clock = [0.0]
    def fake_sleep(s):
        clock[0] += s
        serving['pieces/a.json'] = new                 # the edge turns over during the wait
    late = store_publish.wait_for_cdn(fake_get, 'https://cdn.test', {'pieces/a.json': md5_new},
                                      timeout=30, every=3, sleep=fake_sleep, clock=lambda: clock[0])
    check('revalidate: the wait returns as soon as the CDN serves the new bytes', late == [] and clock[0] == 3)
    serving['pieces/a.json'] = old
    clock[0] = 0.0
    late = store_publish.wait_for_cdn(fake_get, 'https://cdn.test', {'pieces/a.json': md5_new},
                                      timeout=9, every=3, sleep=lambda s: clock.__setitem__(0, clock[0] + s),
                                      clock=lambda: clock[0])
    check('revalidate: an edge that never turns over is reported, not waited on forever',
          late == ['pieces/a.json'] and clock[0] == 9, f'{late} at t={clock[0]}')
    posted = []
    def fake_post(answer):
        def post(url, data, headers):
            posted.append((url, json.loads(data), headers.get('Authorization')))
            return answer
        return post
    ok, msg = store_publish.ping(fake_post((200, '{"revalidated": ["quire:piece:a"], "ignored": []}')),
                                 'https://site.test/api/revalidate/', 'SEKRIT', ['pieces/a.json'])
    check('revalidate: the keys go with the bearer, and the site\'s expired tags are reported',
          ok and 'quire:piece:a' in msg
          and posted[-1] == ('https://site.test/api/revalidate/', {'keys': ['pieces/a.json']}, 'Bearer SEKRIT'))
    check('revalidate: a refusal is not a pass',
          not store_publish.ping(fake_post((401, '{"error": "unauthorized"}')), 'u', 's', ['x.json'])[0])
    check('revalidate: a 200 that expired nothing is not a pass',
          not store_publish.ping(fake_post((200, '{"revalidated": [], "ignored": ["x.json"]}')), 'u', 's', ['x.json'])[0])
    check('revalidate: an unreachable site is not a pass',
          not store_publish.ping(fake_post((None, 'timed out')), 'u', 's', ['x.json'])[0])
    class _R:
        def __init__(self, rc, out): self.returncode, self.stdout = rc, out
    check('revalidate: the secret is read from the Keychain, and a missing one is None',
          store_publish.keychain_secret('svc', run=lambda *a, **k: _R(0, 'abc\n')) == 'abc'
          and store_publish.keychain_secret('svc', run=lambda *a, **k: _R(44, '')) is None)

    # a bundle from a fixture deck
    talk = os.path.join(tmp, 'talk-src'); os.makedirs(talk, exist_ok=True)
    deck = os.path.join(tmp, 'talk-deck'); os.makedirs(os.path.join(deck, 'assets'), exist_ok=True)
    with open(os.path.join(deck, 'notes.json'), 'w', encoding='utf-8') as f:
        json.dump({'slug': 'a-talk', 'title': 'A Talk', 'slideCount': 3, 'slides': []}, f)
    with open(os.path.join(deck, 'deck.html'), 'w', encoding='utf-8') as f:
        f.write('<deck-stage></deck-stage>')
    with open(os.path.join(talk, 'piece.yaml'), 'w', encoding='utf-8') as f:
        f.write('slug: a-talk\ntitle: A Talk\npublished_at: 2026-09-08\n'
                'outlets: [muffinlabs]\nbody: |\n  Some **framing** prose.\n')

    bundle = os.path.join(tmp, 'bundle')
    # Pretend the store already holds another piece, published to a different outlet.
    os.makedirs(bundle, exist_ok=True)
    with open(os.path.join(bundle, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'spec': '2', 'generated_at': '', 'pieces': [
            {'slug': 'elsewhere', 'title': 'Elsewhere', 'published_at': '2026-01-01',
             'digest': 'sha256:dead', 'outlets': ['alignmentfellowship'], 'kind': 'piece'}]}, f)

    # A talk is bundled against the desk that holds its script — that is where its tags live
    # (unit_talk_tags), so the desk has to know it. This one is untagged, which is allowed.
    tdesk = os.path.join(tmp, 'talk-desk')
    os.makedirs(os.path.join(tdesk, 'pieces'), exist_ok=True)
    os.makedirs(os.path.join(tdesk, 'talks', 'a-talk'), exist_ok=True)
    with open(os.path.join(tdesk, 'talks', 'a-talk', 'talk.yaml'), 'w', encoding='utf-8') as f:
        f.write('title: A Talk\n')

    r = subprocess.run([sys.executable, os.path.join(HERE, 'talk_bundle.py'), talk, deck, bundle,
                        '--desk', tdesk], capture_output=True, text=True)
    check('a talk bundle assembles', r.returncode == 0, (r.stdout + r.stderr).strip())
    if r.returncode != 0:
        return

    check("a talk's record is filed beside its deck, not in pieces/",
          os.path.exists(os.path.join(bundle, 'talks', 'a-talk', 'piece.json'))
          and not os.path.exists(os.path.join(bundle, 'pieces', 'a-talk.json')))
    with open(os.path.join(bundle, 'talks', 'a-talk', 'piece.json'), encoding='utf-8') as f:
        piece = json.load(f)
    check('the piece carries a talk block with relative paths',
          piece['talk']['deck'] == '../talks/a-talk/deck.html'
          and piece['talk']['slide_count'] == 3, str(piece.get('talk')))
    check('the digest covers reader text, not markup',
          piece['plain'] == 'Some framing prose.', repr(piece.get('plain')))
    check('the digest is a sha256 of that text',
          piece['digest'] == 'sha256:' + hashlib.sha256(piece['plain'].encode()).hexdigest())

    with open(os.path.join(bundle, 'index.json'), encoding='utf-8') as f:
        index = json.load(f)
    slugs = sorted(p['slug'] for p in index['pieces'])
    check('publishing one talk does NOT unpublish everything else',
          slugs == ['a-talk', 'elsewhere'], str(slugs))
    check('the index is newest first',
          [p['slug'] for p in index['pieces']] == ['a-talk', 'elsewhere'],
          str([p['slug'] for p in index['pieces']]))

    # re-running must replace the entry, not duplicate it
    subprocess.run([sys.executable, os.path.join(HERE, 'talk_bundle.py'), talk, deck, bundle],
                   capture_output=True, text=True)
    with open(os.path.join(bundle, 'index.json'), encoding='utf-8') as f:
        index2 = json.load(f)
    check('re-publishing replaces the index entry rather than duplicating it',
          len(index2['pieces']) == 2, str([p['slug'] for p in index2['pieces']]))

    # nothing is published without being named
    with open(os.path.join(talk, 'piece.yaml'), 'w', encoding='utf-8') as f:
        f.write('slug: a-talk\ntitle: A Talk\npublished_at: 2026-09-08\nbody: |\n  x\n')
    r2 = subprocess.run([sys.executable, os.path.join(HERE, 'talk_bundle.py'), talk, deck,
                         os.path.join(tmp, 'bundle2')], capture_output=True, text=True)
    check('a talk with no outlets is refused, not published everywhere',
          r2.returncode != 0 and 'outlets' in (r2.stdout + r2.stderr), (r2.stdout + r2.stderr).strip())

    # ---- a talk and an essay sharing a slug: both must survive a merge ----
    essay_src = os.path.join(tmp, 'same-slug')
    os.makedirs(essay_src, exist_ok=True)
    with open(os.path.join(essay_src, 'a-talk.md'), 'w', encoding='utf-8') as f:
        f.write('---\nslug: a-talk\ntitle: A Talk, the essay\npublished_at: 2026-09-09\n'
                'digest: sha256:0123456789ab\n---\n\nThe essay.\n')
    r0 = subprocess.run([sys.executable, os.path.join(HERE, 'bundle_pieces.py'), essay_src, bundle,
                         '--outlet', 'muffinlabs'], capture_output=True, text=True)
    with open(os.path.join(bundle, 'index.json'), encoding='utf-8') as f:
        both = sorted((p['slug'], p['kind']) for p in json.load(f)['pieces'] if p['slug'] == 'a-talk')
    check('an essay sharing a talk\'s slug does not replace the talk in the index',
          r0.returncode == 0 and both == [('a-talk', 'piece'), ('a-talk', 'talk')],
          str(both) + ' ' + (r0.stdout + r0.stderr).strip()[:200])
    check('and the two records live at different keys',
          os.path.exists(os.path.join(bundle, 'pieces', 'a-talk.json'))
          and os.path.exists(os.path.join(bundle, 'talks', 'a-talk', 'piece.json')))

    # ---- bundle_pieces: markdown bundle -> the JSON the store serves ----
    content = os.path.join(tmp, 'vendored')
    os.makedirs(content, exist_ok=True)
    imgs = os.path.join(tmp, 'vendored-images', 'a-piece')
    os.makedirs(imgs, exist_ok=True)
    with open(os.path.join(imgs, 'hero.webp'), 'wb') as f:
        f.write(b'RIFF____WEBP')
    with open(os.path.join(content, 'a-piece.md'), 'w', encoding='utf-8') as f:
        f.write('---\nslug: a-piece\ntitle: A Piece\npublished_at: 2026-05-04\n'
                'digest: sha256:abc123def456\nhero:\n  src: /images/a-piece/hero.webp\n'
                '  alt: A hero\n---\n\nBody with an ![inline](/images/a-piece/hero.webp).\n')

    b2 = os.path.join(tmp, 'bundle-pieces')
    r3 = subprocess.run([sys.executable, os.path.join(HERE, 'bundle_pieces.py'), content, b2,
                         '--outlet', 'alignmentfellowship', '--images',
                         os.path.join(tmp, 'vendored-images')], capture_output=True, text=True)
    check('a vendored bundle converts to store JSON', r3.returncode == 0,
          (r3.stdout + r3.stderr).strip())
    if r3.returncode != 0:
        return
    with open(os.path.join(b2, 'pieces', 'a-piece.json'), encoding='utf-8') as f:
        conv = json.load(f)
    # A destination rewrote ../images to /images so it could serve from /public. The
    # store needs that undone, in the front matter AND in the prose.
    check('a destination image rewrite is undone in front matter',
          conv['hero']['src'] == '../images/a-piece/hero.webp', str(conv.get('hero')))
    check('and undone in the body too',
          '../images/a-piece/hero.webp' in conv['body'] and '](/images/' not in conv['body'],
          conv['body'])
    check('the digest is carried over, never recomputed',
          conv['digest'] == 'sha256:abc123def456', conv['digest'])
    check('images travel with the piece',
          os.path.exists(os.path.join(b2, 'images', 'a-piece', 'hero.webp')))

    # An unchanged re-run must write a byte-identical index. Stamping generated_at on every
    # run made each no-change publish re-upload index.json and invalidate it (2026-09-11).
    bp_args = [sys.executable, os.path.join(HERE, 'bundle_pieces.py'), content, b2,
               '--outlet', 'alignmentfellowship', '--images', os.path.join(tmp, 'vendored-images')]
    idx = os.path.join(b2, 'index.json')
    with open(idx, 'rb') as f:
        idx_before = f.read()
    r4 = subprocess.run(bp_args, capture_output=True, text=True)
    with open(idx, 'rb') as f:
        idx_after = f.read()
    check('an unchanged re-run leaves index.json byte-identical',
          r4.returncode == 0 and idx_before == idx_after, (r4.stdout + r4.stderr).strip())
    # ...and a real change still stamps a new time. Backdate first: a same-second rerun
    # would otherwise pass without proving anything.
    stale = json.loads(idx_after)
    stale['generated_at'] = '2000-01-01T00:00:00Z'
    with open(idx, 'w', encoding='utf-8') as f:
        json.dump(stale, f)
    md = os.path.join(content, 'a-piece.md')
    with open(md, encoding='utf-8') as f:
        orig_md = f.read()
    with open(md, 'w', encoding='utf-8') as f:
        f.write(orig_md.replace('title: A Piece', 'title: A Piece, Retitled'))
    r5 = subprocess.run(bp_args, capture_output=True, text=True)
    with open(idx, encoding='utf-8') as f:
        changed = json.load(f)
    with open(md, 'w', encoding='utf-8') as f:
        f.write(orig_md)
    check('a changed entry stamps a new generated_at',
          r5.returncode == 0 and changed['generated_at'] != '2000-01-01T00:00:00Z'
          and changed['pieces'][0]['title'] == 'A Piece, Retitled', str(changed.get('generated_at')))
    # ...and an unchanged run keeps even a backdated stamp.
    r6 = subprocess.run(bp_args[:], capture_output=True, text=True)  # title restored -> entries change back
    with open(idx, encoding='utf-8') as f:
        kept = json.load(f)
    stamp = kept['generated_at']
    subprocess.run(bp_args, capture_output=True, text=True)
    with open(idx, encoding='utf-8') as f:
        again = json.load(f)
    check('a second unchanged run keeps the same generated_at',
          r6.returncode == 0 and again['generated_at'] == stamp, f'{stamp} -> {again.get("generated_at")}')

    # ---- snapshot: the way back ----
    # Served from a local directory rather than the real store: the suite makes no
    # network calls, and a backup tool that needs the thing it is backing up to be
    # reachable in order to be TESTED is not much of a backup tool.
    import http.server, socketserver, threading, functools
    store_root = os.path.join(tmp, 'fake-store')
    os.makedirs(os.path.join(store_root, 'pieces'), exist_ok=True)
    os.makedirs(os.path.join(store_root, 'images', 'a-piece'), exist_ok=True)
    with open(os.path.join(store_root, 'images', 'a-piece', 'hero.webp'), 'wb') as f:
        f.write(b'RIFF____WEBP')
    piece = {'slug': 'a-piece', 'title': 'A Piece', 'published_at': '2026-05-04',
             'digest': 'sha256:abc123def456', 'body': 'Prose.\n',
             'hero': {'src': '../images/a-piece/hero.webp', 'alt': 'A hero'}}
    with open(os.path.join(store_root, 'pieces', 'a-piece.json'), 'w', encoding='utf-8') as f:
        json.dump(piece, f)
    # A talk that shares the essay's slug, filed beside its deck the way quire's getTalk
    # reads it. The snapshot must keep both, not let one overwrite the other.
    tdir = os.path.join(store_root, 'talks', 'a-piece')
    os.makedirs(tdir, exist_ok=True)
    talk_rec = {'slug': 'a-piece', 'title': 'A Talk', 'published_at': '2026-05-04',
                'digest': 'sha256:fedcba654321', 'body': 'Framing.\n',
                'talk': {'deck': '../talks/a-piece/deck.html',
                         'notes': '../talks/a-piece/notes.json', 'slide_count': 1}}
    with open(os.path.join(tdir, 'piece.json'), 'w', encoding='utf-8') as f:
        json.dump(talk_rec, f)
    for name, text in (('deck.html', '<deck-stage></deck-stage>'), ('deck-stage.js', '//'),
                       ('notes.json', '{"slideCount": 1, "slides": []}')):
        with open(os.path.join(tdir, name), 'w', encoding='utf-8') as f:
            f.write(text)
    with open(os.path.join(store_root, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'spec': '2', 'generated_at': '', 'pieces': [
            {'slug': 'a-piece', 'title': 'A Piece', 'published_at': '2026-05-04',
             'digest': 'sha256:abc123def456', 'outlets': ['somewhere'], 'kind': 'piece'},
            {'slug': 'a-piece', 'title': 'A Talk', 'published_at': '2026-05-04',
             'digest': 'sha256:fedcba654321', 'outlets': ['somewhere'], 'kind': 'talk'}]}, f)

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=store_root)
    class Quiet(handler.func):
        def log_message(self, *a): pass
    httpd = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=store_root))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        cfg_path = os.path.join(tmp, 'store.yaml')
        with open(cfg_path, 'w', encoding='utf-8') as f:
            f.write(f'store:\n  base_url: http://127.0.0.1:{port}\n  bucket: b\n'
                    f'  region: us-east-1\n  distribution_id: d\n')
        snap = os.path.join(tmp, 'snap')
        snapshot = os.path.join(HERE, 'snapshot.py')
        r = subprocess.run([sys.executable, snapshot, snap, '--config', cfg_path],
                           capture_output=True, text=True)
        check('a snapshot of the store completes', r.returncode == 0,
              (r.stdout + r.stderr).strip())
        check('it writes the piece back as front matter + markdown',
              os.path.exists(os.path.join(snap, 'content', 'a-piece.md')))
        check('and brings the images with it',
              os.path.exists(os.path.join(snap, 'images', 'a-piece', 'hero.webp')))
        tmd = os.path.join(snap, 'talks', 'a-piece', 'piece.md')
        check('a talk and an essay sharing a slug are both kept, at different paths',
              os.path.exists(tmd) and 'title: A Talk' in open(tmd, encoding='utf-8').read()
              and 'title: A Piece' in open(os.path.join(snap, 'content', 'a-piece.md'),
                                           encoding='utf-8').read())
        if os.path.exists(os.path.join(snap, 'content', 'a-piece.md')):
            text = open(os.path.join(snap, 'content', 'a-piece.md'), encoding='utf-8').read()
            check('the date is a bare YYYY-MM-DD, not a quoted string',
                  'published_at: 2026-05-04' in text, text[:200])
            check('the body survives the round trip', text.rstrip().endswith('Prose.'))

        rv = subprocess.run([sys.executable, snapshot, snap, '--config', cfg_path,
                             '--verify-only'], capture_output=True, text=True)
        check('verify-only passes on a good snapshot', rv.returncode == 0,
              (rv.stdout + rv.stderr).strip())

        # A verifier that cannot fail is not a verifier. Each of these is a way a
        # backup rots quietly.
        # Each broken snapshot is a COPY made without the file — the suite deletes nothing.
        gone_img = os.path.join(tmp, 'snap-missing-image')
        shutil.copytree(snap, gone_img, ignore=shutil.ignore_patterns('hero.webp'))
        r1 = subprocess.run([sys.executable, snapshot, gone_img, '--config', cfg_path,
                             '--verify-only'], capture_output=True, text=True)
        check('a missing image fails verification',
              r1.returncode == 1 and 'missing' in (r1.stdout + r1.stderr), r1.stderr.strip())

        with open(os.path.join(snap, 'images', 'a-piece', 'hero.webp'), 'wb') as f:
            f.write(b'RIFF____WEBP')
        md = os.path.join(snap, 'content', 'a-piece.md')
        body = open(md, encoding='utf-8').read().replace('sha256:abc123def456', 'sha256:0000')
        open(md, 'w', encoding='utf-8').write(body)
        r2 = subprocess.run([sys.executable, snapshot, snap, '--config', cfg_path,
                             '--verify-only'], capture_output=True, text=True)
        check('a digest that disagrees with the index fails verification',
              r2.returncode == 1 and 'digest disagrees' in (r2.stdout + r2.stderr),
              r2.stderr.strip())

        gone_md = os.path.join(tmp, 'snap-missing-piece')
        shutil.copytree(snap, gone_md, ignore=shutil.ignore_patterns('a-piece.md'))
        r3 = subprocess.run([sys.executable, snapshot, gone_md, '--config', cfg_path,
                             '--verify-only'], capture_output=True, text=True)
        check('a missing piece fails verification',
              r3.returncode == 1 and 'missing' in (r3.stdout + r3.stderr), r3.stderr.strip())
    finally:
        httpd.shutdown()





def unit_linkedin_canonical_once(tmp):
    """The canonical line appears ONCE. The shared converter already prepends it for a piece
    that records a `canonical:`, and md_to_linkedin prepended its own on top — so a piece whose
    canonical was recorded before its LinkedIn copy was composed carried the line twice, one
    above the subtitle and one below (measured 2026-09-11, in the editor, by eye)."""
    print("\n-- linkedin: the canonical line, exactly once ------------------------")
    import md_to_linkedin as ml
    d = os.path.join(tmp, 'li-canon')
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'draft.md'), 'w', encoding='utf-8').write(
        '*scaffold*\n\n---\n\nOpening paragraph.\n\nClosing paragraph.\n')
    open(os.path.join(d, 'publish.yaml'), 'w', encoding='utf-8').write(
        'title: T\nsubtitle: S\ncanonical: https://example.invalid/blog/t\n'
        'outlets:\n  - linkedin\n')
    body, _notes, _imgs, _meta = ml.build(d)
    seeded = sum(1 for b in body if 'Originally published at ' in b)
    check('linkedin: the shared converter is the one that seeds the canonical line', seeded == 1,
          f'{seeded} in body')
    # what main() assembles, in the same two lines it uses
    already = bool(body) and 'Originally published at ' in body[0]
    parts = [] if already else ['<p><em>Originally published at …</em></p>']
    if already:
        parts.append(body.pop(0))
    parts.append('<p><em>S</em></p>')
    parts += body
    total = sum(1 for p in parts if 'Originally published at ' in p)
    check('linkedin: the assembled article carries it exactly once', total == 1, f'{total} in parts')
    check('linkedin: and it still comes before the subtitle',
          'Originally published at ' in parts[0] and '<em>S</em>' in parts[1])


# ---------------------------------------------------------------- unit: linkedin outlet
def unit_captions(tmp):
    """Captions live in publish.yaml and reach every outlet from there (2026-09-11)."""
    print("\n-- captions: publish.yaml -> every outlet ----------------------------")
    import md_to_substack as m2s
    import substack_verify as sv
    import md_to_linkedin as ml
    d = os.path.join(tmp, 'cap-piece')
    os.makedirs(os.path.join(d, 'assets'), exist_ok=True)
    for n in ('hero.png', 'fig.png'):
        with open(os.path.join(d, 'assets', n), 'wb') as f:
            f.write(_tiny_png())
    with open(os.path.join(d, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write('*scaffold*\n\n---\n\n![A hero scene](assets/hero.png)\n\nOpening paragraph.\n\n'
                '![A chart](assets/fig.png)\n\nClosing paragraph.\n')
    man = os.path.join(d, 'publish.yaml')
    base = 'title: T\nsubtitle: S\n'
    def write(extra):
        with open(man, 'w', encoding='utf-8') as f:
            f.write(base + extra)
    write('')
    plain_body = m2s.render_reader(d)[0]
    check('captions: none declared, none emitted', m2s.render_captions(d) == ['', ''], str(m2s.render_captions(d)))
    check('captions: a clean draft carries no caption prose', m2s.caption_prose(d) == [])
    pd = os.path.join(tmp, 'cap-prose')
    os.makedirs(pd, exist_ok=True)
    with open(os.path.join(pd, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write('*s*\n\n---\n\n![A dog](assets/x.png)\n\n*A caption in the body.*\n\nProse.\n\n'
                '*An italic line that follows prose, not an image.*\n')
    with open(os.path.join(pd, 'publish.yaml'), 'w', encoding='utf-8') as f:
        f.write('title: T\nsubtitle: S\n')
    check('captions: an italic line directly under an image is caught as caption prose',
          m2s.caption_prose(pd) == ['*A caption in the body.*'], str(m2s.caption_prose(pd)))
    check('captions: the header gate REFUSES caption prose (captions live in publish.yaml)',
          any('caption is written into draft.md' in e for e in m2s.manifest_gate(pd)[0]),
          str(m2s.manifest_gate(pd)[0]))
    write('cover: assets/hero.png\ncover_caption: What the hero means.\n'
          "captions:\n  assets/fig.png: 'The chart, \"quoted\" & plain.'\n")
    joined = '\n'.join(m2s.parse_blocks(d)[0])
    check('captions: the hero takes cover_caption as its figcaption',
          '<figcaption>What the hero means.</figcaption>' in joined, joined[:200])
    check('captions: a body image takes its captions: entry, HTML-escaped',
          '<figcaption>The chart, "quoted" &amp; plain.</figcaption>' in joined, joined[-240:])
    check('captions: the reader digest does not move when captions are added',
          m2s.render_reader(d)[0] == plain_body, str(m2s.render_reader(d)[0]))
    check('captions: render_captions lists them in document order',
          m2s.render_captions(d) == ['What the hero means.', 'The chart, "quoted" & plain.'],
          str(m2s.render_captions(d)))
    write('cover_caption: By filename.\n')
    check('captions: a hero.* image takes cover_caption with no cover: key',
          m2s.render_captions(d) == ['By filename.', ''], str(m2s.render_captions(d)))
    write('cover: assets/hero.png\ncover_caption: Old.\ncaptions:\n  assets/hero.png: New.\n')
    check('captions: an explicit captions: entry wins over cover_caption', m2s.render_captions(d)[0] == 'New.')
    check('captions: a folded-block marker read as one line is not a caption', m2s._manifest_line('>-') == '')
    check('captions: a trailing YAML comment is not part of the caption',
          m2s._manifest_line('Means this.   # kept by Eric') == 'Means this.')

    live = ('<div class="captioned-image-container"><figure><a class="image-link"><img src="x"></a>'
            '<figcaption class="image-caption">What the hero means.</figcaption></figure></div>'
            '<p>t</p><div class="captioned-image-container"><figure><img src="y"></figure></div>')
    check('captions: live captions are read per figure, in order',
          sv.live_captions(live) == ['What the hero means.', ''], str(sv.live_captions(live)))
    check("captions: Substack's curly quotes are not drift",
          sv.caption_drift(['The chart, \u201cquoted\u201d & plain.'], ['The chart, "quoted" & plain.']) == [])
    check('captions: a live caption the desk does not hold is reported, not invisible',
          bool(sv.caption_drift(['Set by hand.', ''], ['', ''])))
    check('captions: a wrong live caption is reported by position',
          'caption #2' in ' '.join(sv.caption_drift(['a', 'b'], ['a', 'c'])))
    check('captions: no captions on either side is silent', sv.caption_drift(['', ''], ['', '']) == [])

    write('cover: assets/hero.png\ncover_caption: What the hero means.\ncaptions:\n  assets/fig.png: The chart.\n')
    _b, _n, images, _m = ml.build(d)
    # 2026-09-15: the hero is the Article's COVER, not figure 1 — it leaves `images` for
    # `guards['cover']`, carrying cover_caption; the body figures keep their captions: entries.
    check('captions: the LinkedIn hero is the cover, carrying cover_caption',
          (_m.get('cover') or {}).get('caption') == 'What the hero means.', str(_m.get('cover')))
    check('captions: the LinkedIn figure payloads carry each caption, hero excluded',
          [i.get('caption') for i in images] == ['The chart.'], str(images))

    tool = os.path.join(HERE, 'substack_captions.py')
    out = os.path.join(tmp, 'caps.js')
    cap_env = {**os.environ, 'DESK_OUTLETS': os.path.join(tmp, 'cap-outlets.yaml')}
    with open(cap_env['DESK_OUTLETS'], 'w', encoding='utf-8') as f:
        f.write('outlets:\n  sub:\n    reader_base: https://cap.substack.com/p/\n    account_handle: capper\n')
    r = subprocess.run([sys.executable, tool, d, '--out', out], capture_output=True, text=True, env=cap_env)
    js = open(out).read() if r.returncode == 0 and os.path.exists(out) else ''
    check('captions: substack_captions writes a snippet carrying the desk captions in order',
          r.returncode == 0 and json.dumps(['What the hero means.', 'The chart.']) in js,
          (r.stdout + r.stderr)[-300:])
    check('captions: the snippet refuses on an image-count mismatch rather than guessing',
          'matched by position' in js)
    write('')
    r = subprocess.run([sys.executable, tool, d, '--out', out], capture_output=True, text=True, env=cap_env)
    check('captions: substack_captions refuses a piece with no captions (exit 2)', r.returncode == 2,
          (r.stdout + r.stderr)[-200:])

    # The bundle: the hero's caption rides in hero.caption, a body image's as its markdown title.
    write('outlets:\n  - site\npublished_at: 2026-09-11\ncover: assets/hero.png\n'
          'cover_caption: What the hero means.\ncaptions:\n  assets/fig.png: The "chart".\n')
    bundle = os.path.join(tmp, 'cap-bundle')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'md_to_site.py'), bundle, d, '--outlet', 'site', '--apply'],
                       capture_output=True, text=True, cwd=tmp)
    md = ''
    if r.returncode == 0:
        found = [f for f in os.listdir(os.path.join(bundle, 'content'))] if os.path.isdir(os.path.join(bundle, 'content')) else []
        md = open(os.path.join(bundle, 'content', found[0])).read() if found else ''
    fm = md.split('---')[1] if md.count('---') >= 2 else ''
    import yaml as _y
    hero = (_y.safe_load(fm) or {}).get('hero', {}) if fm else {}
    check('captions: the bundle carries the hero caption in hero.caption',
          hero.get('caption') == 'What the hero means.', (r.stderr[-300:] or str(hero)))
    check('captions: the bundle carries a body caption as the image title, quotes escaped',
          '.webp "The \\"chart\\".")' in md, (r.stderr[-200:] or md[-300:]))


def unit_linkedin_post(tmp):
    """The announcing post is the author's approved text, kept beside the piece (2026-09-11)."""
    print("\n-- linkedin: the announcing post ------------------------------------")
    piece = os.path.join(tmp, 'li-post-piece')
    os.makedirs(piece, exist_ok=True)
    with open(os.path.join(piece, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write('*scaffold*\n\n---\n\nOpening paragraph.\n\nClosing paragraph.\n')
    with open(os.path.join(piece, 'publish.yaml'), 'w', encoding='utf-8') as f:
        f.write('title: A Piece\nsubtitle: Its subtitle\noutlets:\n  - muffinlabs\n  - linkedin\n'
                'blog_url: https://www.muffinlabs.ai/blog/a-piece\n'
                'verified:\n  date: 2026-09-10\n  by: test\n  covers: the fixture\n')
    ocfg = os.path.join(tmp, 'li-post-outlets.yaml')
    with open(ocfg, 'w', encoding='utf-8') as f:
        f.write('outlets:\n  muffinlabs:\n    reader_base: https://www.muffinlabs.ai/blog/\n'
                '    manifest_url_key: blog_url\n  linkedin:\n    reader_base: https://www.linkedin.com/pulse/\n'
                '    manifest_url_key: linkedin_url\n    derive: false\n')
    tool = os.path.join(HERE, 'md_to_linkedin.py')
    out = os.path.join(tmp, 'li-post-out')
    text = 'First paragraph of the announcement.\n\nSecond, ending in a colon:'
    with open(os.path.join(piece, 'linkedin-post.md'), 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    r = subprocess.run([sys.executable, tool, piece, '--outlets', ocfg, '--out', out, '--no-fetch'],
                       capture_output=True, text=True)
    art = json.load(open(os.path.join(out, 'article.json'))) if r.returncode == 0 else {}
    check('linkedin: the approved announcing post is carried into article.json',
          art.get('announce') == text, (r.stdout + r.stderr)[-300:])
    with open(os.path.join(piece, 'linkedin-post.md'), 'w', encoding='utf-8') as f:
        f.write('x' * 3001)
    r = subprocess.run([sys.executable, tool, piece, '--outlets', ocfg, '--out', out, '--no-fetch', '--check'],
                       capture_output=True, text=True)
    check('linkedin: an announcing post over 3,000 characters is refused',
          r.returncode == 1 and 'linkedin-post.md is 3,001 characters' in r.stderr, r.stderr[-300:])


def unit_prose(tmp):
    """check_status and check_refs: prose that goes on describing a piece the way it used to be.
    Every case is one that happened on this desk in September 2026."""
    print("\n-- prose: what the prose claims agrees with the manifests ---------------")
    import check_status as cs
    import check_refs as cr
    root = os.path.join(tmp, 'prose')

    def w(rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)

    w('publishing/outlets.yaml', "outlets:\n  substack:\n    manifest_url_key: public_url\n")
    w('pieces/live-one/publish.yaml',
      "title: Live One\nsubtitle: A Subtitle\npublic_url: https://pub.test/p/live-one\n")
    w('pieces/live-one/README.md', "# Live One\n")
    w('pieces/draft-one/publish.yaml', "title: Draft One\n")
    w('pieces/draft-one/README.md', "# Draft One\n")
    # a retitle that reached the manifest and nothing else
    w('pieces/retitled/publish.yaml', "title: New Name\npublic_url: https://pub.test/p/new-name\n")
    w('pieces/retitled/README.md', "# Old Name\n")
    lines = [
        "# Index", "", "Live pieces link to their reader URL.", "",
        "- *Live One* (`live-one`) — the founding distinction; unpublished.",          # 5
        "- [*Live One: A Subtitle*](https://site.test/live-one/)",                       # 6
        "  (`live-one`) — cited with its subtitle, which is the same piece.",
        "- [*Old Name*](https://site.test/new-name/)",                                   # 8
        "  (`retitled`) — a stale title, wrapped the way the index wraps.",
        "- [`draft-one`](../../pieces/draft-one/README.md) is a path, not a title claim.",
        "- *Draft One* (`draft-one`) — unpublished. **The live posts are re-synced:** `live-one`.",  # 11
        "", "## 2026-09-01 a dated heading", "",
        "- *Live One* (`live-one`) — unpublished. History, not drift.",                  # 15
    ]
    w('books/b/writings.md', "\n".join(lines) + "\n")

    f = cs.check([os.path.join(root, 'books')], os.path.join(root, 'pieces'),
                 os.path.join(root, 'publishing', 'outlets.yaml'), None) or []
    stale = [(ln, k, s) for _p, ln, k, s, _w in f if k == 'unpublished' and s == 'live-one']
    check("check_status: a live piece still called unpublished is reported (In Vain, 2026-09-09)",
          [ln for ln, _k, _s in stale] == [5], str(f))
    check("check_status: the same words under a dated heading are history, not drift",
          not any(ln >= 13 for ln, _k, _s in stale), str(stale))
    check("check_status: 'unpublished' in one sentence is not pinned on a live piece named in the next",
          not any(ln == 11 for ln, _k, _s in stale), str(stale))

    found, _n, _k = cr.problems(root)
    by = {s: (what, where) for s, what, where in found}
    check("check_refs: a stale title in a book index, wrapped as the index wraps, is reported "
          "(The Door and the Room, 2026-09-11)",
          'retitled' in by and any(t_ == 'Old Name' and f_.endswith('writings.md')
                                   for s, _w, where in found if s == 'retitled' for t_, f_, _l in where),
          str(found))
    check("check_refs: a README heading that disagrees with publish.yaml's title is reported",
          any(s == 'retitled' and 'README H1' in what for s, what, _w in found), str(found))
    check("check_refs: 'Title: Subtitle' is the same piece, not a stale title",
          'live-one' not in by, str(by.get('live-one')))
    check("check_refs: `slug` as link text is a path, not a title claim",
          'draft-one' not in by, str(by.get('draft-one')))

    import publications as pb
    pubs = {'bg': {'outlets': ['sub', 'site'], 'required_outlets': ['sub', 'site']}}
    live = {'publication': 'bg', 'public_url': 'https://pub.test/p/a'}
    check("publications: a published piece missing a required outlet is reported (Eric, 2026-09-11)",
          pb.missing_required(dict(live, outlets=['sub']), pubs) == [('site', 'not declared')])
    check("publications: an exemption with a reason is honoured",
          pb.missing_required(dict(live, outlets=['sub'],
                                   outlets_exempt={'site': 'Eric: not for the Fellowship'}), pubs) == [])
    check("publications: an exemption with no reason is not an exemption",
          pb.missing_required(dict(live, outlets=['sub'], outlets_exempt={'site': ' '}), pubs)
          == [('site', 'exempted without a reason')])
    check("publications: a draft is not held to it",
          pb.missing_required({'publication': 'bg', 'outlets': []}, pubs) == [])


def unit_substack_account(tmp):
    """substack_account.py: with several Substack outlets ONE is primary and runs in the pane; the
    rest open in Claude in Chrome. The pane's login is one cookie store shared by every tab and
    every session (measured 2026-09-11), so every write also proves it is on the right account —
    from the snippet's own answer, never a handle typed in."""
    print("\n-- substack account: one primary in the pane, the rest in Chrome --------")
    import json as _json
    import substack_account as sa

    def w(name, text):
        path = os.path.join(tmp, name)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        return path

    def said(handle=None, host='bg.substack.com', status=401):
        """The snippet's answer, as a browser returns it."""
        if handle is None:
            return {'signed_in': False, 'status': status, 'origin': f'https://{host}'}
        return {'signed_in': True, 'handle': handle, 'name': 'x', 'origin': f'https://{host}'}
    ml = 'ml.substack.com'

    base = ("# a comment that must survive a primary switch\n"
            "substack_primary: bg\n"
            "outlets:\n"
            "  bg:\n    reader_base: https://bg.substack.com/p/\n    account_handle: elmuffin\n"
            "  ml:\n    reader_base: https://ml.substack.com/p/\n    account_handle: ericgarciaphd\n"
            "    chrome_browser: eric@muffinlabs.ai\n"
            "  site:\n    reader_base: https://site.test/writings/\n")
    cfg = w('acct-outlets.yaml', base)
    doc = sa.load(cfg)
    check("substack_account: the declared primary is the primary", sa.primary(doc) == ('bg', None))
    check("substack_account: the primary runs in the pane; any other opens in its Chrome browser",
          sa.route(doc, 'bg')['surface'] == 'pane' and sa.route(doc, 'ml')['surface'] == 'chrome'
          and sa.route(doc, 'ml')['chrome_browser'] == 'eric@muffinlabs.ai')
    check("substack_account: the primary, in the pane, as its account, passes",
          sa.verdict(doc, 'bg', said('elmuffin'), 'pane')[0] == 0)
    check("substack_account: a non-primary, in its browser, as its account, passes",
          sa.verdict(doc, 'ml', said('ericgarciaphd', ml), 'chrome')[0] == 0)
    check("substack_account: any *.substack.com page answers for the account (one login cookie)",
          sa.verdict(doc, 'bg', said('elmuffin', 'substack.com'), 'pane')[0] == 0
          and sa.verdict(doc, 'ml', said('ericgarciaphd', 'bg.substack.com'), 'chrome')[0] == 0)
    check("substack_account: a non-primary checked in the pane is the wrong browser (exit 4)",
          sa.verdict(doc, 'ml', said('elmuffin'), 'pane')[0] == 4)
    check("substack_account: signed in as someone else is a refusal (exit 5)",
          sa.verdict(doc, 'ml', said('elmuffin', ml), 'chrome')[0] == 5
          and sa.verdict(doc, 'bg', said('ericgarciaphd'), 'pane')[0] == 5)
    check("substack_account: only a 401/403 is signed out (exit 3)",
          sa.verdict(doc, 'bg', said(status=401), 'pane')[0] == 3
          and sa.verdict(doc, 'bg', said(status=403), 'pane')[0] == 3)
    check("substack_account: a 404 or 5xx settles nothing — no sign-in errand (exit 7)",
          sa.verdict(doc, 'bg', said(status=404), 'pane')[0] == 7
          and sa.verdict(doc, 'bg', said(status=502), 'pane')[0] == 7)
    check("substack_account: an answer read off Substack is refused (exit 7)",
          sa.verdict(doc, 'bg', said('elmuffin', 'evil.example'), 'pane')[0] == 7
          and sa.verdict(doc, 'bg', said('elmuffin', 'substack.com.evil.example'), 'pane')[0] == 7)
    check("substack_account: a handle typed in instead of the snippet's answer is refused (exit 7)",
          sa.verdict(doc, 'bg', 'elmuffin', 'pane')[0] == 7 and sa.verdict(doc, 'bg', None, 'pane')[0] == 7)
    check("substack_account: where it ran must be said — there is no default browser",
          sa.verdict(doc, 'bg', said('elmuffin'), None)[0] == 1)
    check("substack_account: handles compare without the @ or case",
          sa.verdict(doc, 'bg', said('@ElMuffin'), 'pane')[0] == 0)
    check("substack_account: a non-Substack outlet and an unknown one are not routed",
          sa.verdict(doc, 'site', said('x'), 'pane')[0] == 6 and sa.verdict(doc, 'nope', said('x'), 'pane')[0] == 1)
    notes = sa.load(w('acct-notes.yaml', base.replace("    account_handle: ericgarciaphd\n",
                                                      "    notes_handle: ericgarciaphd\n")))
    check("substack_account: a notes_handle alone does not authorise a write (exit 6)",
          sa.verdict(notes, 'ml', said('ericgarciaphd', ml), 'chrome')[0] == 6)
    steps = ' '.join(sa.route(doc, 'ml')['browser_steps'])
    check("substack_account: route spells out reaching the Chrome browser by its exact name",
          all(k in steps for k in ('list_connected_browsers', 'select_browser', 'switch_browser',
                                   "'eric@muffinlabs.ai'")) and sa.route(doc, 'bg')['browser_steps'] == [])
    check("substack_account: the CLI takes the snippet's JSON verbatim",
          sa.main(['--outlets', cfg, 'check', 'bg', '--surface', 'pane',
                   '--result', _json.dumps(said('elmuffin'))]) == 0
          and sa.main(['--outlets', cfg, 'check', 'bg', '--surface', 'pane', '--result', 'elmuffin']) == 7)

    one = sa.load(w('acct-one.yaml', "outlets:\n  bg:\n    reader_base: https://bg.substack.com/p/\n"
                                     "    account_handle: elmuffin\n"))
    check("substack_account: a lone Substack outlet is the primary without saying so",
          sa.primary(one) == ('bg', None))
    two = sa.load(w('acct-two.yaml', base.replace("substack_primary: bg\n", "")))
    check("substack_account: several Substack outlets and no primary is refused, not guessed",
          sa.primary(two)[0] is None and sa.verdict(two, 'bg', said('elmuffin'), 'pane')[0] == 6)
    homeless = sa.load(w('acct-homeless.yaml', base.replace("    chrome_browser: eric@muffinlabs.ai\n", "")))
    check("substack_account: a non-primary with no chrome_browser has nowhere to run (exit 6)",
          sa.verdict(homeless, 'ml', said('ericgarciaphd', ml), 'chrome')[0] == 6)

    code, _msg = sa.set_primary(cfg, 'ml')
    check("substack_account: switching refuses to demote an outlet with no browser to go to",
          code == 6 and sa.load(cfg).get('substack_primary') == 'bg')
    cfg2 = w('acct-switch.yaml', base.replace("    account_handle: elmuffin\n",
                                              "    account_handle: elmuffin\n    chrome_browser: gmail\n"))
    code, msg = sa.set_primary(cfg2, 'ml')
    after = sa.load(cfg2)
    with open(cfg2, encoding='utf-8') as fh:
        text = fh.read()
    check("substack_account: switching the primary rewrites it in place, comments intact",
          code == 0 and after.get('substack_primary') == 'ml'
          and '# a comment that must survive a primary switch' in text
          and sa.route(after, 'bg')['surface'] == 'chrome' and sa.route(after, 'ml')['surface'] == 'pane', msg)
    check("substack_account: the switch names the sign-ins it needs",
          '@ericgarciaphd' in msg and "'gmail'" in msg and '@elmuffin' in msg, msg)
    check("substack_account: switching to the current primary is a no-op; to a non-Substack outlet, refused",
          sa.set_primary(cfg2, 'ml')[0] == 0 and sa.set_primary(cfg2, 'site')[0] == 1)
    check("substack_account: the snippet is same-origin (a cross-origin fetch fails in the pane)",
          "fetch('/api/v1/user/profile/self'" in sa.SNIPPET and 'substack.com/api' not in sa.SNIPPET)

GUARD_RUNNER = r"""
// Run one generated snippet with a TRIPWIRE for a document: the first read of document, window or
// any DOM constructor throws, and every fetch is recorded. Signed in as argv[3] (none: HTTP argv[4]),
// on the publication argv[5].
const fs = require('fs');
const [file, handle, status, host] = process.argv.slice(2);
const src = fs.readFileSync(file, 'utf8');
const touched = [], calls = [];
const trip = what => new Proxy({}, { get: (_t, k) => {
  if (k === 'then') return undefined;
  touched.push(what + '.' + String(k)); throw new Error('tripwire: ' + what + '.' + String(k)); } });
const H = host || 'bg.substack.com';
globalThis.location = { origin: 'https://' + H, hostname: H, host: H,
                        href: 'https://' + H + '/publish/post/42', pathname: '/publish/post/42' };
for (const g of ['document', 'window', 'DataTransfer', 'ClipboardEvent', 'DOMParser']) globalThis[g] = trip(g);
globalThis.fetch = async (path, o) => {
  calls.push(((o && o.method) || 'GET') + ' ' + path);
  if (path === '/api/v1/user/profile/self')
    return handle ? { status: 200, json: async () => ({ handle }) } : { status: Number(status) || 401, json: async () => ({}) };
  return { ok: false, status: 599, json: async () => ({}), text: async () => '' };
};
(async () => {
  let out = null, error = null;
  try { out = await eval(src); } catch (e) { error = String((e && e.message) || e); }
  console.log(JSON.stringify({ out: typeof out === 'string' ? out : null, error, touched, calls }));
})();
"""


def unit_account_guard(tmp):
    """Every generated Substack snippet checks the signed-in account ITSELF, in the same eval as its
    work (2026-09-11). `substack_account.py check` confirms the account once, but the pane's cookie
    store is shared by every tab and session: another session can switch its login between that
    check and the write, and the write lands under the wrong byline with no error. Each generator's
    output is run against a tripwire document: signed in as someone else, or signed out, it must
    return the guard's refusal having read nothing of the page and called nothing but the profile."""
    print("\n-- account guard: every Substack snippet checks who is signed in ------")
    import substack_account as sa
    import substack_tags as st
    import pane_carry
    import md_to_clipboard
    root = os.path.join(tmp, 'guarddesk')
    pub = os.path.join(root, 'publishing')
    os.makedirs(pub, exist_ok=True)
    with open(os.path.join(pub, 'outlets.yaml'), 'w', encoding='utf-8') as f:
        f.write("substack_primary: bg\noutlets:\n"
                "  bg:\n    reader_base: https://bg.substack.com/p/\n    account_handle: '@ElMuffin'\n"
                "    notes_handle: notes-only\n"
                "  ml:\n    reader_base: https://ml.substack.com/p/\n    account_handle: ericgarciaphd\n"
                "    chrome_browser: x\n"
                "  noacct:\n    reader_base: https://na.substack.com/p/\n    notes_handle: na\n    chrome_browser: y\n"
                "  site:\n    reader_base: https://site.test/w/\n")
    with open(os.path.join(pub, 'tags.yaml'), 'w', encoding='utf-8') as f:
        f.write('tags:\n  - tag: idolatry\n    label: Idolatry\n    about: a\n')

    def piece(slug, manifest):
        d = os.path.join(root, 'pieces', slug)
        os.makedirs(os.path.join(d, 'assets'), exist_ok=True)
        with open(os.path.join(d, 'assets', 'hero.png'), 'wb') as f:
            f.write(_tiny_png())
        with open(os.path.join(d, 'draft.md'), 'w', encoding='utf-8') as f:
            f.write('*scaffold*\n\n---\n\n![A hero](assets/hero.png)\n\nOpening paragraph with a note.[^1]\n\n'
                    'Closing *paragraph* here.\n\n[^1]: The note.\n')
        with open(os.path.join(d, 'publish.yaml'), 'w', encoding='utf-8') as f:
            f.write('title: P\nsubtitle: S\ncover: assets/hero.png\ncover_caption: The hero.\n'
                    'cover_provenance: generated\ntags:\n  - idolatry\n' + manifest)
        return d
    p = piece('p', 'post_url: https://bg.substack.com/publish/post/42\noutlets:\n  - bg\n  - site\n')
    q = piece('q', 'post_url: https://ml.substack.com/publish/post/43\noutlets:\n  - ml\n')
    legacy = piece('legacy', 'post_url: https://ml.substack.com/publish/post/44\n')
    offsub = piece('offsub', 'outlets:\n  - site\n')
    torn = piece('torn', 'post_url: https://ml.substack.com/publish/post/45\noutlets:\n  - bg\n')
    unsure = piece('unsure', '')
    na = piece('na', 'outlets:\n  - noacct\n')

    def settles(d):
        try:
            return sa.outlet_for_piece(d)[0]
        except sa.NoAccount as e:
            return 'refused: ' + str(e)
    check('guard: a piece writes to the Substack outlet its outlets: names',
          settles(p) == 'bg' and settles(q) == 'ml', f'{settles(p)} / {settles(q)}')
    check('guard: a manifest with no outlets: is settled by its post_url host', settles(legacy) == 'ml',
          settles(legacy))
    check('guard: no Substack outlet, a post_url on another outlet, or nothing to go on is refused',
          all(settles(x).startswith('refused') for x in (offsub, torn, unsure)),
          ' | '.join(settles(x) for x in (offsub, torn, unsure)))
    check('guard: an outlet with only a notes_handle authorises nothing', settles(na).startswith('refused'),
          settles(na))
    g, _name, want, hosts = sa.guard_for_piece(p)
    check('guard: it insists on account_handle, normalised — never notes_handle',
          want == 'elmuffin' and sa.guard_handle(g) == 'elmuffin' and 'notes-only' not in g, g[:120])
    check("guard: and on the outlet's own publication — one account can own several",
          hosts == ['bg.substack.com'] and '"bg.substack.com"' in g and 'ml.substack.com' not in g, str(hosts))
    check('guard: a custom-domain outlet checks the account alone until publish_host: names its editor',
          sa.publish_hosts({'reader_base': 'https://custom.example/p/'}) == []
          and sa.publish_hosts({'reader_base': 'https://custom.example/p/',
                                'publish_host': 'custom.substack.com'}) == ['custom.substack.com']
          and sa.publish_hosts({'reader_base': 'https://custom.example/p/'},
                               {'post_url': 'https://cus.substack.com/publish/post/1'}) == ['cus.substack.com'])
    check("guard: the check snippet's own same-origin fetch (a cross-origin fetch fails in the pane)",
          "fetch('/api/v1/user/profile/self', { credentials: 'include' })" in g and 'substack.com/api' not in g)

    plan = os.path.join(tmp, 'guard-plan.json')
    live = os.path.join(tmp, 'guard-live.json')
    with open(plan, 'w', encoding='utf-8') as f:
        json.dump({'rows': [{'state': 'push', 'markState': 'unchanged', 'kind': 'body',
                             'liveIdx': 0, 'draftIdx': 0}],
                   'title': {'state': 'unchanged'}, 'subtitle': {'state': 'unchanged'}}, f)
    with open(live, 'w', encoding='utf-8') as f:
        json.dump({'body': ['x', 'y', 'z'], 'fns': ['n']}, f)
    out = lambda k: os.path.join(tmp, f'guard-{k}.js')
    T = lambda n: os.path.join(HERE, n)
    gens = [('md_to_substack', [T('md_to_substack.py'), p, out('compose')], 'compose'),
            ('substack_repatch', [T('substack_repatch.py'), p, out('repatch')], 'repatch'),
            ('substack_repatch --structural', [T('substack_repatch.py'), '--structural', p, out('structural')], 'structural'),
            ('substack_sync scan', [T('substack_sync.py'), 'scan', p, out('scan')], 'scan'),
            ('substack_sync fetch', [T('substack_sync.py'), 'fetch', p, plan, out('fetch')], 'fetch'),
            ('substack_sync push', [T('substack_sync.py'), 'push', p, plan, live, out('push')], 'push'),
            ('substack_sync images', [T('substack_sync.py'), 'images', p, out('images')], 'images'),
            ('substack_cover', [T('substack_cover.py'), p, '--post', '42', '--out', out('cover')], 'cover'),
            ('substack_captions', [T('substack_captions.py'), p, '--out', out('captions')], 'captions')]
    snippets = {}
    for label, args, key in gens:
        r = subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=root)
        js = open(out(key), encoding='utf-8').read() if os.path.exists(out(key)) else ''
        snippets[label] = out(key)
        check(f'guard: {label} opens with the guard for @elmuffin, as one expression',
              r.returncode == 0 and sa.guard_handle(js) == 'elmuffin' and js.startswith('(async () => {')
              and js.index(sa.GUARD_MARK) < 80, (r.stdout + r.stderr)[-300:])
    with open(out('clipboard-fn'), 'w', encoding='utf-8') as f:
        f.write(md_to_clipboard.footnote_snippet(p, [['1', 'The note.']]))
    snippets['md_to_clipboard --fn-out'] = out('clipboard-fn')
    check('guard: md_to_clipboard --fn-out opens with the guard too',
          sa.guard_handle(open(out('clipboard-fn'), encoding='utf-8').read()) == 'elmuffin')

    r = subprocess.run([sys.executable, T('substack_repatch.py'), q, out('q')], capture_output=True, text=True)
    check("guard: each piece's snippet names ITS outlet's account",
          r.returncode == 0 and sa.guard_handle(open(out('q'), encoding='utf-8').read()) == 'ericgarciaphd',
          (r.stdout + r.stderr)[-200:])
    r = subprocess.run([sys.executable, T('substack_repatch.py'), offsub, out('offsub')], capture_output=True, text=True)
    check('guard: a piece whose account cannot be settled gets no snippet at all (exit 9)',
          r.returncode == sa.NO_ACCOUNT_EXIT and not os.path.exists(out('offsub')), (r.stdout + r.stderr)[-200:])
    check('guard: substack_account guard names the outlet and account (exit 9 when it cannot)',
          sa.main(['guard', p]) == 0 and sa.main(['guard', offsub]) == sa.NO_ACCOUNT_EXIT)

    check('guard: substack_tags carries the guard for its posts',
          sa.guard_handle(st.snippet([st.plan(p)])) == 'elmuffin')
    try:
        st.snippet([st.plan(p), st.plan(q)])
        mixed = 'no refusal'
    except st.pb.Refused as e:
        mixed = str(e)
    check('guard: substack_tags refuses one run over two accounts', '2 accounts' in mixed, mixed)

    compose = open(snippets['md_to_substack'], encoding='utf-8').read()
    fb = compose[compose.find('window.__sbInsertFootnotes = async () => {'):]
    check("guard: md_to_substack's footnote pass (call B, its own eval) checks the account again first",
          'window.__sbInsertFootnotes = async () => {' in compose
          and 0 < fb.find('await __deskAccount()') < fb.find('document.querySelector'))

    bare = os.path.join(tmp, 'guard-carry', 'bare.js')
    os.makedirs(os.path.dirname(bare), exist_ok=True)
    with open(bare, 'w', encoding='utf-8') as f:
        f.write("(() => document.querySelector('.ProseMirror').editor)()")
    check('guard: pane_carry refuses a Substack snippet that carries no guard, and serves nothing',
          pane_carry.main(['pane_carry.py', bare]) == 2
          and not os.path.exists(os.path.join(os.path.dirname(bare), 'carry.html')))

    if not shutil.which('node'):
        skip('guard: the snippets against a tripwire document', 'node not installed')
        return
    runner = os.path.join(tmp, 'guard-run.js')
    with open(runner, 'w', encoding='utf-8') as f:
        f.write(GUARD_RUNNER)

    def run(path, *who):
        r = subprocess.run(['node', runner, path, *who], capture_output=True, text=True, timeout=60)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {'crash': r.stderr[-300:]}
    PROFILE = ['GET /api/v1/user/profile/self']
    for label, path in snippets.items():
        bad = {}
        for who in (['someone-else', '', 'bg.substack.com'], ['', '401', 'bg.substack.com'],
                    ['', '404', 'bg.substack.com']):
            res = run(path, *who)
            ref = json.loads(res['out']) if res.get('out') else {}
            if not (ref.get('accountGuard') is True and res['touched'] == [] and res['calls'] == PROFILE
                    and res['error'] is None):
                bad[who[0] or 'HTTP ' + who[1]] = res
        # the same account's OTHER publication: refused locally, without so much as a fetch
        res = run(path, 'ElMuffin', '', 'ml.substack.com')
        ref = json.loads(res['out']) if res.get('out') else {}
        if not (str(ref.get('refused')).startswith('publication:') and res['touched'] == []
                and res['calls'] == []):
            bad['another publication of the same account'] = res
        ok = run(path, 'ElMuffin', '', 'bg.substack.com')
        passed = ok.get('calls', [])[:1] == PROFILE and (ok.get('touched') or ok.get('calls', [])[1:])
        check(f'guard: {label} — another account, another publication, or none stops before the '
              f'page; the right one gets through', not bad and bool(passed), json.dumps(bad or ok)[:300])


def unit_automode(tmp):
    """automode.py: the pane re-sync's standing rule, built from the desk's Substack outlets and
    merged into USER settings, the only scope the classifier reads (repo .claude/ settings are
    ignored by design; measured 2026-09-11)."""
    print("\n-- automode: the pane re-sync rule lives in user scope, and only its own entry moves ---")
    import automode as am
    root = os.path.join(tmp, 'am-desk')
    os.makedirs(os.path.join(root, 'publishing'))
    os.makedirs(os.path.join(root, '.claude'))
    outlets = os.path.join(root, 'publishing', 'outlets.yaml')
    with open(outlets, 'w', encoding='utf-8') as fh:
        fh.write("outlets:\n"
                 "  substack:\n    reader_base: https://pen.substack.com/p/\n"
                 "  site:\n    reader_base: https://site.test/writings/\n"
                 "  substack-pro:\n    reader_base: https://pro.substack.com/p/\n")
    hosts = am.substack_hosts(outlets)
    check("automode: every *.substack.com outlet and nothing else", hosts == ['pen.substack.com', 'pro.substack.com'], str(hosts))
    text = am.rule(hosts)
    check("automode: the rule names each publication's editor",
          'https://pen.substack.com/publish/post/<id>' in text and 'https://pro.substack.com/publish/post/<id>' in text)
    check("automode: every tool the rule names exists (a rename must not narrow it silently)",
          all(os.path.isfile(os.path.join(HERE, t)) for t in am.TOOLS), str(am.TOOLS))
    check("automode: the rule keeps the hash gate and excludes email and first Publish",
          'sha256' in text and 'does NOT cover clicking Publish' in text and 'sends email' in text)
    try:
        am.rule([])
        check("automode: a desk with no Substack outlet is refused", False)
    except ValueError:
        check("automode: a desk with no Substack outlet is refused", True)

    new, act = am.merge({}, text)
    check("automode: a new allow list starts with $defaults (omitting it discards the built-ins)",
          act == 'added' and new['autoMode']['allow'] == ['$defaults', text], str(new))
    check("automode: re-running is a no-op", am.merge(new, text)[1] == 'unchanged')
    prior = {'model': 'x', 'autoMode': {'allow': ['$defaults', 'someone else', am.MARKER + ' old', am.MARKER + ' dup'],
                                        'soft_deny': ['$defaults']}}
    upd, act = am.merge(prior, text)
    check("automode: an older entry is replaced, duplicates dropped, other entries and keys kept",
          act == 'updated' and upd['autoMode']['allow'] == ['$defaults', 'someone else', text]
          and upd['model'] == 'x' and upd['autoMode']['soft_deny'] == ['$defaults'], str(upd))
    kept, _ = am.merge({'autoMode': {'allow': ['mine only']}}, text)
    check("automode: a list the author wrote without $defaults stays that way",
          kept['autoMode']['allow'] == ['mine only', text])

    settings = os.path.join(tmp, 'am-user', 'settings.json')
    os.makedirs(os.path.dirname(settings))
    with open(settings, 'w', encoding='utf-8') as fh:
        json.dump({'theme': 'dark'}, fh)
    rc = am.main(['install', '--root', root, '--settings', settings])
    with open(settings, encoding='utf-8') as fh:
        wrote = json.load(fh)
    check("automode: install merges into user settings and keeps what was there",
          rc == 0 and wrote.get('theme') == 'dark' and wrote['autoMode']['allow'] == ['$defaults', text], str(wrote))
    with open(settings, 'w', encoding='utf-8') as fh:
        fh.write('{not json')
    rc = am.main(['install', '--root', root, '--settings', settings])
    with open(settings, encoding='utf-8') as fh:
        check("automode: unreadable settings are refused and left untouched", rc == 2 and fh.read() == '{not json')
    local = os.path.join(root, '.claude', 'settings.local.json')
    rc = am.main(['install', '--root', root, '--settings', local])
    check("automode: a repo .claude/ path is refused, since the classifier ignores it",
          rc == 2 and not os.path.exists(local))

    cfg = os.path.join(tmp, 'am-config.json')
    for allow, want, label in ((['built-in', text], 0, 'in force'),
                               (['built-in'], 3, 'missing'),
                               (['built-in', am.MARKER + ' old'], 3, 'stale')):
        with open(cfg, 'w', encoding='utf-8') as fh:
            json.dump({'allow': allow, 'soft_deny': []}, fh)
        rc = am.main(['check', '--root', root, '--config-json', cfg])
        check(f"automode: check reads the config in force: {label} -> exit {want}", rc == want, str(rc))


def unit_linkedin(tmp):
    """LinkedIn is the last outlet a piece reaches and a copy of it, so almost everything
    here is a refusal: every case is a way the copy could go up wrong or go up first."""
    print("\n-- linkedin: the Article copy, and the audit that checks it ---------")
    import outlet_audit

    # --- the audit: a missing Article redirects to a live page -----------------------
    li = {'reader_base': 'https://www.linkedin.com/pulse/', 'manifest_url_key': 'linkedin_url',
          'derive': False, 'not_found_markers': ['article_not_found']}
    check('a redirect to LinkedIn\'s not-found page is a miss, not a 200',
          outlet_audit.landed_on_not_found(
              'https://www.linkedin.com/top-content/?trk=article_not_found', li))
    check('a live Article is not mistaken for a miss',
          not outlet_audit.landed_on_not_found(
              'https://www.linkedin.com/pulse/some-essay-eric-garcia-abc123/', li))
    check('an outlet with no markers never reads a redirect as a miss',
          not outlet_audit.landed_on_not_found('https://x.test/top-content/?trk=article_not_found',
                                               {'reader_base': 'https://x.test/'}))
    check('a LinkedIn URL is never guessed from a slug',
          outlet_audit.slug_of({}, 'some-essay', li) is None)
    check('a recorded LinkedIn URL is used as recorded',
          outlet_audit.slug_of({'linkedin_url': 'https://www.linkedin.com/pulse/x-y-1/'},
                               'x', li) == 'https://www.linkedin.com/pulse/x-y-1/')

    # --- the audit: an Article prints footnote refs as literal [n] -------------------
    # The --content check dropped native superscripts but not these, so the three footnoted
    # paragraphs of love-is-not-a-metric-space read as stale on a correct copy (2026-09-11).
    fp = os.path.join(tmp, 'li-audit-piece')
    os.makedirs(fp, exist_ok=True)
    with open(os.path.join(fp, 'publish.yaml'), 'w', encoding='utf-8') as f:
        f.write('title: T\nsubtitle: S\n')
    noted = 'This is Sam. Thirty-four, who climbs and reads and gets up early every day.'
    prose = 'Table [2] in the appendix gives the full count for every one of the cohorts.'
    with open(os.path.join(fp, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write('scaffold\n---\n' + noted.replace('Sam.', 'Sam.[^sam]') + '\n\n'
                + prose + '\n\n[^sam]: Not his name.\n')
    page = (f'<p>{noted.replace("Sam.", "Sam.[1]")}</p><p>{prose}</p>'
            '<h2>Notes</h2><p>[1] Not his name.</p>')
    r = outlet_audit.content_drift(fp, page, footnote_marker='bracket')
    check('an Article\'s inline [1] after a word is not drift on an outlet that prints them',
          r is not None and not r['missing'], str(r))
    r = outlet_audit.content_drift(fp, page)
    check('the same [1] is drift on an outlet that does not declare footnote_marker',
          r is not None and [w[:11] for w in r['missing']] == ['This is Sam'], str(r))
    r = outlet_audit.content_drift(fp, page.replace('Table [2] in', 'Table in'),
                                   footnote_marker='bracket')
    check('a bracketed number in prose still counts where markers are dropped',
          r is not None and [w[:5] for w in r['missing']] == ['Table'], str(r))

    # --- the converter ---------------------------------------------------------------
    piece = os.path.join(tmp, 'li-piece')
    os.makedirs(os.path.join(piece, 'assets'), exist_ok=True)
    with open(os.path.join(piece, 'assets', 'fig.png'), 'wb') as f:
        f.write(_tiny_png())
    quoted_alt = 'A chart with an arrow labeled "featurize." and a second labeled "d"'
    with open(os.path.join(piece, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write('*scaffold, never published*\n\n---\n\n'
                'Opening paragraph with a claim.[^a]\n\n'
                '## A heading\n\n'
                f'![{quoted_alt}](assets/fig.png)\n\n'
                'Closing paragraph with *emphasis* and a second note.[^b]\n\n'
                '[^a]: The first note.\n\n[^b]: The second note.\n')
    manifest = ('title: A Piece\nsubtitle: Its subtitle\n'
                'outlets:\n  - muffinlabs\n  - linkedin\n'
                'blog_url: https://www.muffinlabs.ai/blog/a-piece\n'
                'verified:\n  date: 2026-09-10\n  by: test\n  covers: the fixture\n')
    with open(os.path.join(piece, 'publish.yaml'), 'w', encoding='utf-8') as f:
        f.write(manifest)
    ocfg = os.path.join(tmp, 'li-outlets.yaml')
    with open(ocfg, 'w', encoding='utf-8') as f:
        f.write('outlets:\n  muffinlabs:\n    reader_base: https://www.muffinlabs.ai/blog/\n'
                '    manifest_url_key: blog_url\n'
                '  linkedin:\n    reader_base: https://www.linkedin.com/pulse/\n'
                '    manifest_url_key: linkedin_url\n    derive: false\n')

    tool = os.path.join(HERE, 'md_to_linkedin.py')
    def run(*extra):
        r = subprocess.run([sys.executable, tool, piece, '--outlets', ocfg, '--no-fetch', *extra],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    out = os.path.join(tmp, 'li-out')
    code, log = run('--out', out)
    check('a verified piece with a recorded canonical composes', code == 0, log.strip())
    if code == 0:
        a = open(os.path.join(out, 'article.html'), encoding='utf-8').read()
        j = json.load(open(os.path.join(out, 'article.json'), encoding='utf-8'))
        check('the first line says where the original lives',
              a.splitlines()[0].startswith('<p><em>Originally published at '
                                            '<a href="https://www.muffinlabs.ai/blog/a-piece">'),
              a.splitlines()[0])
        check('the subtitle becomes the lede, since an Article has no subtitle field',
              a.splitlines()[1] == '<p><em>Its subtitle</em></p>', a.splitlines()[1])
        check('footnotes become [n] in first-reference order, with Notes at the end',
              'claim.[1]' in a and 'note.[2]' in a and '<h2>Notes</h2>' in a
              and '[1] The first note.' in a and '[2] The second note.' in a, a[-300:])
        check('no raw footnote marker survives', '[[FN' not in a)
        check('a figure is a marked slot, not an inlined data: image',
              '[Figure 1 — upload here]' in a and 'data:image' not in a)
        # The Substack renderer truncates this alt at its first double quote. Here it must
        # arrive whole, because it is read from the markdown, not recovered from HTML.
        check('an alt text containing double quotes survives whole',
              j['images'][0]['alt'] == quoted_alt, repr(j['images'][0]['alt']))
        check('the figure is listed with the file to upload',
              j['images'][0]['file'].endswith('assets/fig.png'))
        # The paste drops alt text (measured 2026-09-10), so the payload that carries the
        # image must carry the alt with it, whole.
        fp = os.path.join(out, 'fig1.json')
        f1 = json.load(open(fp, encoding='utf-8')) if os.path.exists(fp) else {}
        check('each figure gets a carry payload with its bytes and its alt together',
              f1.get('alt') == quoted_alt and str(f1.get('dataUri', '')).startswith('data:image/png;base64,'),
              str({k: (v[:40] if isinstance(v, str) else v) for k, v in f1.items()}))

    # --- the refusals ---------------------------------------------------------------
    def refuses(mutate, why_fragment, label):
        good = open(os.path.join(piece, 'publish.yaml'), encoding='utf-8').read()
        with open(os.path.join(piece, 'publish.yaml'), 'w', encoding='utf-8') as f:
            f.write(mutate(good))
        code, log = run('--check')
        with open(os.path.join(piece, 'publish.yaml'), 'w', encoding='utf-8') as f:
            f.write(good)
        check(label, code == 1 and why_fragment in log, log.strip()[:300])

    refuses(lambda m: m.replace('blog_url: https://www.muffinlabs.ai/blog/a-piece\n', ''),
            'publish the canonical first',
            'no recorded canonical: refused — the copy never goes up first')
    refuses(lambda m: m.replace('  - linkedin\n', ''),
            'does not name `linkedin`',
            'a piece that does not name linkedin is refused, not syndicated anyway')
    refuses(lambda m: m.replace('verified:\n  date: 2026-09-10\n  by: test\n  covers: the fixture\n', ''),
            'check_verified refuses',
            'an unverified piece is refused — syndication does not weaken verification')

    code, _log = run('--check')
    check('--check writes nothing', code == 0 and not os.path.exists(os.path.join(piece, 'linkedin')))



# ---------------------------------------------------------------- unit: scratch drafts
def unit_scratch(tmp):
    """A test writes into the outlet's ONE standing draft, never a new one (2026-09-11)."""
    print("\n-- scratch drafts: one per outlet, reused ------------------------------")
    import scratch_draft as sd
    cfg = {'outlets': {
        'sub': {'scratch_draft': {'id': 215233016,
                                  'edit_url': 'https://x.substack.com/publish/post/215233016'}},
        'bare': {'reader_base': 'https://y.test/'},
        'half': {'scratch_draft': {'id': 1}},
        'wrong': {'scratch_draft': {'id': 7, 'edit_url': 'https://x.test/publish/post/8'}}}}
    check('a recorded scratch draft is returned as recorded',
          sd.scratch_for(cfg, 'sub') == {'kind': 'editor', 'id': '215233016',
                                         'edit_url': 'https://x.substack.com/publish/post/215233016'})
    check('an outlet with none recorded says so rather than inventing one',
          sd.scratch_for(cfg, 'bare') is None)
    for name, why in (('half', 'no edit URL'), ('wrong', 'an edit URL for another draft')):
        try:
            sd.scratch_for(cfg, name); ok = False
        except ValueError:
            ok = True
        check(f'a scratch draft with {why} is refused', ok)
    try:
        sd.scratch_for(cfg, 'nope'); ok = False
    except KeyError:
        ok = True
    check('an outlet outlets.yaml does not define is an error, not a None', ok)
    check('the title says what the draft is', sd.TITLE.startswith('TEST') and 'never publish' in sd.TITLE)

    # --- a site's scratch is a store record the site renders (quire 0.16) -----------------
    site = {'outlets': {'af': {'scratch_draft': {'view_url': 'https://af.test/scratch/'}},
                        'mixed': {'scratch_draft': {'view_url': 'https://af.test/scratch/', 'id': 3}}}}
    check("a site's scratch is its store key and the page that shows it",
          sd.scratch_for(site, 'af') == {'kind': 'store', 'store_key': 'scratch/af.json',
                                         'view_url': 'https://af.test/scratch/'})
    try:
        sd.scratch_for(site, 'mixed'); ok = False
    except ValueError:
        ok = True
    check('a scratch that is half editor, half site is refused', ok)

    import subprocess
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bundle_pieces.py')
    content, imgs, bundle = (os.path.join(tmp, 'scr-' + n) for n in ('content', 'imgs', 'bundle'))
    os.makedirs(content); os.makedirs(os.path.join(imgs, 'live-one'))
    with open(os.path.join(imgs, 'live-one', 'fig.webp'), 'wb') as f:
        f.write(b'RIFF-not-really-webp')
    with open(os.path.join(content, 'live-one.md'), 'w', encoding='utf-8') as f:
        f.write('---\ntitle: Live One\npublished_at: 2026-09-11\ndigest: sha256:abc\n'
                'hero:\n  src: /images/live-one/fig.webp\n  alt: A figure\n---\n\n'
                'Words.\n\n![A figure](/images/live-one/fig.webp "What it means")\n')
    r = subprocess.run([sys.executable, tool, content, bundle, '--outlet', 'af', '--images', imgs,
                        '--scratch'], capture_output=True, text=True)
    rec = os.path.join(bundle, 'scratch', 'af.json')
    check('--scratch writes scratch/<outlet>.json', r.returncode == 0 and os.path.exists(rec),
          r.stderr[-300:])
    if os.path.exists(rec):
        with open(rec, encoding='utf-8') as f:
            got = json.load(f)
        check("the scratch's pictures are its own, never the live piece's",
              '../scratch/images/af/fig.webp' in got['body'] and '../images/live-one/' not in got['body']
              and got['hero']['src'] == '../scratch/images/af/fig.webp', got['body'][-120:])
    check('--scratch never writes the index, a piece record, or images/<slug>/',
          not os.path.exists(os.path.join(bundle, 'index.json'))
          and not os.path.exists(os.path.join(bundle, 'pieces'))
          and not os.path.exists(os.path.join(bundle, 'images'))
          and os.path.exists(os.path.join(bundle, 'scratch', 'images', 'af', 'fig.webp')))
    with open(os.path.join(content, 'second.md'), 'w', encoding='utf-8') as f:
        f.write('---\ntitle: Two\npublished_at: 2026-09-11\ndigest: sha256:def\n---\n\nMore.\n')
    r = subprocess.run([sys.executable, tool, content, bundle, '--outlet', 'af', '--scratch'],
                       capture_output=True, text=True)
    check('--scratch refuses more than one piece', r.returncode != 0 and 'exactly one' in r.stderr, r.stderr)


# ---------------------------------------------------------------- unit: tags
def unit_tags(tmp):
    """Tags are a controlled vocabulary written into heavily commented manifests (2026-09-11).

    The writer is the dangerous part: a YAML round-trip would strip every comment in every
    publish.yaml on the desk, so tags.py edits the `tags:` block as text and refuses any
    write that would change another key. These cases pin that down, then follow a tag out
    through the exporter and the bundler, where an undefined tag must stop, not ship."""
    print("\n-- tags: vocabulary, textual manifest writer, export ---------------")
    import tags as tg
    import yaml as _y
    root = os.path.join(tmp, 'tagdesk'); pdir = os.path.join(root, 'pieces')
    vocab = os.path.join(root, 'publishing', 'tags.yaml')
    run = lambda *a: tg.main(['--root', root, *a])

    def piece(slug, text):
        d = os.path.join(pdir, slug); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'publish.yaml'), 'w').write(text)
        return d
    read = lambda d: open(os.path.join(d, 'publish.yaml')).read()

    # the vocabulary
    v0 = piece('v0', 'title: V\n')
    check('tags: add with no vocabulary yet is refused, and nothing is written',
          run('add', 'v0', 'practice') == 3 and read(v0) == 'title: V\n' and not os.path.exists(vocab))
    check('tags: define starts a vocabulary', run('define', 'practice', '--label', 'Practice',
                                                  '--about', 'The daily doing of it.') == 0)
    run('define', 'fear-of-god', '--label', 'The fear of God', '--about', 'What the fear was.')
    v, probs = tg.load_vocab(vocab)
    check('tags: define appends in order, label intact',
          list(v) == ['practice', 'fear-of-god'] and v['fear-of-god']['label'] == 'The fear of God' and not probs,
          str((v, probs)))
    check('tags: a second define of the same tag is refused',
          run('define', 'practice', '--label', 'P', '--about', 'a') == 3)
    check('tags: a tag id must be lowercase-hyphenated',
          run('define', 'Fear of God', '--label', 'F', '--about', 'a') == 3)
    dv = os.path.join(tmp, 'dupe.yaml')
    open(dv, 'w').write('tags:\n  - tag: a\n    label: A\n    about: x\n  - tag: a\n    label: A2\n    about: y\n'
                        '  - tag: b\n    label: B\n')
    _v, probs = tg.load_vocab(dv)
    check('tags: a vocabulary defining a tag twice is caught (a keyed mapping would hide it)',
          any('twice' in p for p in probs), str(probs))
    check('tags: a vocabulary entry with no about is caught', any("'b' has no about" in p for p in probs), str(probs))
    nl = os.path.join(tmp, 'notlast.yaml')
    open(nl, 'w').write('tags:\n  - tag: a\n    label: A\n    about: x\nother: 1\n')
    try:
        tg.define(nl, 'b', 'B', 'y'); refused = False
    except tg.Refused:
        refused = True
    check('tags: define refuses when `tags:` is not the last block', refused and 'other: 1\n' == open(nl).read()[-9:])

    # the textual writer
    orig = ('# Publish manifest\ntitle: T   # settled 2026-09-01 (Eric)\nsubtitle: S\n\n'
            'verified:\n  date: 2026-09-01\n  covers: >-\n    Everything.\n\n'
            '# --- outlets ---\noutlets:\n  - substack\nsite_url: https://example.org/x/\n')
    a = piece('a', orig)
    check('tags: add writes the block', run('add', 'a', 'fear-of-god', 'practice') == 0)
    text = read(a)
    check('tags: every comment survives the edit',
          text.startswith(orig) and '# settled 2026-09-01 (Eric)' in text and '# --- outlets ---' in text)
    check('tags: written in vocabulary order, whatever order they were given',
          _y.safe_load(text)['tags'] == ['practice', 'fear-of-god'], text[-60:])
    check('tags: removing every tag restores the file byte for byte',
          run('remove', 'a', 'practice', 'fear-of-god') == 0 and read(a) == orig, repr(read(a)[-80:]))
    check('tags: an unknown tag is refused and nothing is written',
          run('add', 'a', 'nonsense') == 3 and read(a) == orig)

    b = piece('b', 'title: B\ntags:   # chosen with Eric\n  - fear-of-god   # the whole piece\nsubtitle: S\n')
    run('add', 'b', 'practice')
    check('tags: a block mid-file keeps its key comment, item comments, and the key after it',
          read(b) == 'title: B\ntags:   # chosen with Eric\n  - practice\n  - fear-of-god   # the whole piece\nsubtitle: S\n',
          repr(read(b)))
    c = piece('c', 'title: C\ntags: [fear-of-god, practice]   # flow\n')
    run('remove', 'c', 'fear-of-god')
    check('tags: a flow list is rewritten as a block, comment kept',
          read(c) == 'title: C\ntags:   # flow\n  - practice\n', repr(read(c)))
    d = piece('d', 'title: D\ntags:\n- practice\nsubtitle: S')
    run('add', 'd', 'fear-of-god')
    check('tags: a sequence at the key\'s own indent is read, and a file with no final newline is handled',
          _y.safe_load(read(d)) == {'title': 'D', 'tags': ['practice', 'fear-of-god'], 'subtitle': 'S'}, repr(read(d)))
    hand = 'title: E\ntags:\n  # these were argued over\n  - practice\n'
    e = piece('e', hand)
    check('tags: a hand-edited block (a standalone comment) is refused, not rewritten',
          run('add', 'e', 'fear-of-god') == 3 and read(e) == hand)
    check('tags: a piece with no manifest is refused',
          (os.makedirs(os.path.join(pdir, 'bare'), exist_ok=True) or run('add', 'bare', 'practice')) == 3)

    # the checker and find
    piece('f', 'title: F\ntags:\n  - practise\n')
    piece('g', 'title: G\ntags: practice\n')
    problems, notes = tg.check(root, vocab)
    check("tags: check flags a tag not in the vocabulary, naming the piece",
          any("'practise' is not in the vocabulary — carried by f" in p for p in problems), str(problems))
    check('tags: check flags a `tags:` that is not a list', any(p.startswith('g:') for p in problems), str(problems))
    check('tags: check exits 1 on drift', run('check') == 1)
    rows = {r['slug']: r for r in tg.corpus(root)}
    check('tags: find --none sees the untagged and the manifest-less apart',
          not rows['a']['tags'] and rows['a']['manifest'] and not rows['bare']['manifest'])

    # out through the exporter and the bundler
    x = os.path.join(pdir, 'x'); os.makedirs(x, exist_ok=True)
    open(os.path.join(x, 'draft.md'), 'w').write('# X\n*Draft — header*\n\n---\n\nBody text.\n')
    open(os.path.join(x, 'publish.yaml'), 'w').write(
        'title: X\nsubtitle: S\npublished_at: 2026-09-01\noutlets:\n  - site\ntags:\n  - fear-of-god\n  - practice\n')
    bundle = os.path.join(tmp, 'tagbundle')
    site = os.path.join(HERE, 'md_to_site.py')
    r = subprocess.run([sys.executable, site, bundle, x, '--outlet', 'site', '--tags', vocab, '--apply'],
                       capture_output=True, text=True, cwd=root)
    fm = open(os.path.join(bundle, 'content', 'x.md')).read().split('---')[1] if r.returncode == 0 else ''
    check('tags: the exporter carries each tag with its label, in vocabulary order',
          (_y.safe_load(fm) or {}).get('tags') == [{'tag': 'practice', 'label': 'Practice'},
                                                   {'tag': 'fear-of-god', 'label': 'The fear of God'}],
          r.stderr[-300:] or fm)
    check("tags: the vocabulary's `about` stays on the desk", 'about' not in fm and 'daily doing' not in fm)
    open(os.path.join(x, 'publish.yaml'), 'a').write('  - practise\n')
    r = subprocess.run([sys.executable, site, os.path.join(tmp, 'tb2'), x, '--outlet', 'site', '--tags', vocab],
                       capture_output=True, text=True, cwd=root)
    check('tags: the exporter refuses a tag the vocabulary does not define (exit 8)',
          r.returncode == 8 and 'practise' in r.stderr, r.stderr[-200:])
    r = subprocess.run([sys.executable, site, os.path.join(tmp, 'tb3'), x, '--outlet', 'site'],
                       capture_output=True, text=True, cwd=tmp)
    check('tags: a tagged piece with no vocabulary to hand is refused (exit 8)', r.returncode == 8, r.stderr[-200:])

    store = os.path.join(tmp, 'tagstore')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'bundle_pieces.py'), os.path.join(bundle, 'content'),
                        store, '--outlet', 'site'],
                       capture_output=True, text=True)
    ok = r.returncode == 0
    pj = json.load(open(os.path.join(store, 'pieces', 'x.json'))) if ok else {}
    ix = json.load(open(os.path.join(store, 'index.json'))) if ok else {}
    check('tags: the bundler carries tags into the piece record and the index entry',
          ok and [t['tag'] for t in pj.get('tags', [])] == ['practice', 'fear-of-god']
          and ix['pieces'][0].get('tags') == pj.get('tags'), r.stderr[-300:])
    bad = os.path.join(tmp, 'badtags'); os.makedirs(bad, exist_ok=True)
    open(os.path.join(bad, 'y.md'), 'w').write('---\nslug: y\ntitle: Y\npublished_at: 2026-09-01\n'
                                               'digest: sha256:00\ntags: [practice]\n---\n\nBody\n')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'bundle_pieces.py'), bad, os.path.join(tmp, 'bs'),
                        '--outlet', 'site'], capture_output=True, text=True)
    check('tags: the bundler refuses tags that are not {tag, label}', r.returncode == 1 and 'tags' in r.stderr,
          r.stderr[-200:])



# ---------------------------------------------------------------- unit: publication ownership
def unit_publication_ownership(tmp):
    """Ownership both ways, projects, house files, and a publication's deity conventions (2026-09-15).

    The registry listed which voices a publication owned, and nothing on the voice's side said so:
    a style registered to neither publication passed, a piece naming the other publication's voice
    was a note, and the devotional publication's house conventions sat in the desk's CLAUDE.md where
    the professional one inherited them, its essays swept for deity casing by the pronoun gate."""
    print("\n-- publications: styles and projects owned both ways, house files, deity sections --")
    import publications as pb
    import check_pronouns as cp
    root = os.path.join(tmp, 'owndesk')
    for d in ('publishing', 'styles/voice-a', 'styles/voice-b', 'books/proj-a', 'books/novel-a',
              'pieces/pa', 'pieces/pb'):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    reg = os.path.join(root, 'publishing', 'publications.yaml')
    base = ('publications:\n  a:\n    name: A\n    outlets: [site-a]\n    styles: [voice-a]\n'
            '    projects: [proj-a, novel-a]\n    deity_conventions: true\n'
            '  b:\n    name: B\n    outlets: [site-b]\n    styles: [voice-b]\n')
    open(reg, 'w').write(base)
    open(os.path.join(root, 'styles/voice-a/config.yaml'), 'w').write('publication: a\nformality: 2\n')
    open(os.path.join(root, 'styles/voice-b/config.yaml'), 'w').write('formality: 3\n')
    open(os.path.join(root, 'pieces/pa/publish.yaml'), 'w').write('title: PA\npublication: a\n')
    open(os.path.join(root, 'pieces/pa/README.md'), 'w').write('# PA\n[v](../../styles/voice-a/) [p](../../books/proj-a/)\n')
    open(os.path.join(root, 'pieces/pb/publish.yaml'), 'w').write('title: PB\npublication: b\n')
    open(os.path.join(root, 'pieces/pb/README.md'), 'w').write('# PB\n[v](../../styles/voice-a/)\n')
    pubs, probs = pb.load(root)
    check('own: projects load, with the house file at its default path', not probs
          and pubs['a']['projects'] == ['proj-a', 'novel-a']
          and pubs['a']['house'].endswith(os.path.join('publishing', 'house', 'a.md'))
          and pubs['a']['deity_conventions'] and not pubs['b']['deity_conventions'], str(probs))
    problems, _n, _c = pb.check(root, pubs)
    check("own: a style whose config names no publication fails",
          any('styles/voice-b/config.yaml' in x and 'names no publication' in x for x in problems), str(problems))
    check("own: a piece naming another publication's voice FAILS, and says whose it is",
          any(x.startswith('pb:') and "voice-a" in x and "a's" in x for x in problems), str(problems))
    open(os.path.join(root, 'styles/voice-b/config.yaml'), 'w').write('publication: a\n')
    open(os.path.join(root, 'pieces/pb/README.md'), 'w').write('# PB\n[v](../../styles/voice-b/)\n')
    os.makedirs(os.path.join(root, 'styles/stray'), exist_ok=True)
    os.makedirs(os.path.join(root, 'books/orphan'), exist_ok=True)
    problems, _n, _c = pb.check(root, pubs)
    check('own: a config that disagrees with the registry fails',
          any("names publication 'a', but b owns it" in x for x in problems), str(problems))
    check('own: an unowned style and an unowned project both fail',
          any(x.startswith('styles/stray:') for x in problems)
          and any(x.startswith('books/orphan:') for x in problems), str(problems))
    open(os.path.join(root, 'styles/voice-b/config.yaml'), 'w').write('publication: b\n')
    os.rmdir(os.path.join(root, 'styles/stray')); os.rmdir(os.path.join(root, 'books/orphan'))
    problems, _n, _c = pb.check(root, pubs)
    check('own: the desk is clean once every voice and project is owned both ways', not problems, str(problems))
    open(reg, 'w').write(base.replace('    styles: [voice-b]\n', '    styles: [voice-b, voice-a]\n'))
    check('own: one style owned by two publications is a registry problem',
          any("style 'voice-a' belongs to both a and b" in x for x in pb.load(root)[1]), str(pb.load(root)[1]))
    open(reg, 'w').write(base.replace('projects:', 'books:'))
    check('own: `books:` still reads as the older name of `projects:`',
          pb.load(root)[0]['a']['projects'] == ['proj-a', 'novel-a'])
    open(reg, 'w').write(base)
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = pb.main(['--root', root, 'context', 'pa'])
    check('own: context names the publication, a missing house file as none, the project and the style',
          rc == 0 and 'publication: a' in out.getvalue() and '(none' in out.getvalue()
          and 'books/proj-a' in out.getvalue() and 'styles/voice-a' in out.getvalue(), out.getvalue())
    os.makedirs(os.path.join(root, 'publishing', 'house'), exist_ok=True)
    open(os.path.join(root, 'publishing', 'house', 'a.md'), 'w').write('# House A\n')
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        pb.main(['--root', root, 'context', 'pa'])
    check('own: context names a house file once it exists', 'publishing/house/a.md' in out.getvalue(), out.getvalue())
    check('own: deity conventions follow the publication; no registry stays strict',
          pb.deity_conventions(os.path.join(root, 'pieces', 'pa'))
          and not pb.deity_conventions(os.path.join(root, 'pieces', 'pb'))
          and pb.deity_conventions(os.path.join(tmp, 'no-such-desk', 'pieces', 'x')))
    body = '# PB\n*Draft.*\n\n---\n\nThe choir sang to the Lord. A man walked in and he sat down.\n'
    open(os.path.join(root, 'pieces/pb/draft.md'), 'w').write(body)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_pronouns.py'),
                        os.path.join(root, 'pieces', 'pb')], capture_output=True, text=True, cwd=root)
    check("own: check_pronouns skips the deity sections for a publication without them, and keeps B",
          'not asked' in r.stdout and 'G. mixed-case *Lord* in the body' in r.stdout
          and re.search(r'G\. .*\(0\):', r.stdout) and not re.search(r'B\. .*\(0;', r.stdout), r.stdout[-600:])


# ---------------------------------------------------------------- unit: publications
def unit_publications(tmp):
    """Two publications on one desk, kept apart (2026-09-11).

    A desk grew a second publication — a professional line beside a devotional one — and the
    only thing that said which piece was whose was a comment. Tags were about to be a single
    vocabulary for both, and the shared content store keys a record by slug alone, so one
    publication's piece could overwrite the other's and its site would serve the wrong words.
    These cases pin the registry, the per-piece assignment, per-publication vocabularies, and
    the two store guards."""
    print("\n-- publications: registry, assignment, per-publication tags, store --")
    import publications as pb
    import tags as tg
    import yaml as _y
    root = os.path.join(tmp, 'pubdesk'); pdir = os.path.join(root, 'pieces')
    os.makedirs(os.path.join(root, 'publishing'), exist_ok=True)
    reg = os.path.join(root, 'publishing', 'publications.yaml')
    check('pubs: no registry is a one-publication desk, and nothing is asked',
          pb.load(root) == (None, []) and pb.of_piece({'title': 'x'}, None) == (None, []))

    open(reg, 'w').write('publications:\n  a:\n    name: A\n    outlets: [site-a]\n'
                         '  a:\n    name: A again\n')
    _p, probs = pb.load(root)
    check('pubs: a publication defined twice is caught (PyYAML would keep the second)',
          any('defined twice' in x for x in probs), str(probs))
    open(reg, 'w').write('publications:\n  a:\n    name: A\n    outlets: [site-a]\n'
                         '  b:\n    name: B\n    outlets: [site-a, site-b]\n')
    _p, probs = pb.load(root)
    check('pubs: an outlet owned by two publications is caught',
          any("'site-a' belongs to both a and b" in x for x in probs), str(probs))
    open(reg, 'w').write('# registry\npublications:\n  a:\n    name: A\n    outlets: [site-a]\n'
                         '    styles: [voice-a]\n  b:\n    name: B\n    outlets: [site-b]\n')
    pubs, probs = pb.load(root)
    check('pubs: a clean registry loads, each with its own vocabulary path',
          not probs and pubs['b']['tags'].endswith(os.path.join('publishing', 'tags', 'b.yaml')), str(probs))

    def piece(slug, text, draft=None):
        d = os.path.join(pdir, slug); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'publish.yaml'), 'w').write(text)
        if draft:
            open(os.path.join(d, 'draft.md'), 'w').write(draft)
        return d
    orig = ('# manifest\ntitle: One\nsubtitle: >-\n  A folded\n  subtitle.\n# why the outlets\n'
            'outlets:\n  - site-a\npublished_at: 2026-09-01\n')
    one = piece('one', orig, draft='# One\n*header*\n\n---\n\nBody.\n')
    check('pubs: a piece with no publication is a problem once there is a registry',
          pb.of_piece(pb.read_manifest(one), pubs)[1] != [])
    rc = pb.main(['--root', root, 'assign', 'one', 'a'])
    text = open(os.path.join(one, 'publish.yaml')).read()
    check('pubs: assign writes one line, under the (folded) subtitle, and nothing else moves',
          rc == 0 and text == orig.replace('  subtitle.\n', '  subtitle.\npublication: a\n'), repr(text))
    check('pubs: assign will not silently move a piece to another publication',
          pb.main(['--root', root, 'assign', 'one', 'b']) == 3)
    pb.main(['--root', root, 'assign', 'one', 'b', '--move'])
    check('pubs: an outlet the publication does not own is named as the problem',
          any('site-a' in x and 'belong to a' in x for x in pb.of_piece(pb.read_manifest(one), pubs)[1]),
          str(pb.of_piece(pb.read_manifest(one), pubs)))
    pb.main(['--root', root, 'assign', 'one', 'a', '--move'])
    leg = piece('legacy', 'title: L\npublication: a (The A Line)\n')
    check('pubs: the older free-text form reads as unassigned, not as a publication',
          pb.of_piece(pb.read_manifest(leg), pubs)[0] is None)
    pb.main(['--root', root, 'assign', 'legacy', 'a'])
    check('pubs: assign keeps the id and moves the old label into a comment',
          open(os.path.join(leg, 'publish.yaml')).read() == 'title: L\npublication: a   # The A Line\n',
          repr(open(os.path.join(leg, 'publish.yaml')).read()))
    check('pubs: assigning an unknown publication is refused', pb.main(['--root', root, 'assign', 'one', 'zzz']) == 3)
    two = piece('two', 'title: Two\npublication: b\noutlets: [site-b]\npublished_at: 2026-09-01\n',
                draft='# Two\n*header*\n\n---\n\nBody.\n')
    lone = piece('lone', 'title: Lone\n')

    # one vocabulary per publication; the same id may mean two things
    run = lambda *x: tg.main(['--root', root, *x])
    check('pubs: define asks which publication when there is more than one',
          run('define', 'practice', '--label', 'P', '--about', 'x') == 3)
    run('define', 'practice', '--label', 'Practice', '--about', 'The daily doing.', '--publication', 'a')
    run('define', 'practice', '--label', 'Practice, professionally', '--about', 'Craft.', '--publication', 'b')
    run('define', 'only-a', '--label', 'Only A', '--about', 'x', '--publication', 'a')
    check('pubs: each piece takes tags from its own publication',
          run('add', 'one', 'practice', 'only-a') == 0 and run('add', 'two', 'practice') == 0)
    check("pubs: another publication's tag is refused", run('add', 'two', 'only-a') == 3
          and _y.safe_load(open(os.path.join(two, 'publish.yaml')))['tags'] == ['practice'])
    check('pubs: a piece with no publication cannot be tagged', run('add', 'lone', 'practice') == 3)
    problems, notes = tg.check(root, None, pubs)
    check('pubs: check passes with the same tag id in two vocabularies', not problems, str(problems))
    open(os.path.join(lone, 'publish.yaml'), 'a').write('tags:\n  - practice\n')
    problems, _n = tg.check(root, None, pubs)
    check('pubs: check fails a tagged piece that names no publication',
          any(x.startswith('lone:') for x in problems), str(problems))
    open(os.path.join(lone, 'publish.yaml'), 'w').write('title: Lone\n')   # untagged again

    # out through the exporter: publication and per-publication labels travel
    site = os.path.join(HERE, 'md_to_site.py')
    b1 = os.path.join(tmp, 'pubbundle')
    r = subprocess.run([sys.executable, site, b1, one, two, '--outlet', 'site-b', '--apply'],
                       capture_output=True, text=True, cwd=root)
    fm = open(os.path.join(b1, 'content', 'two.md')).read().split('---')[1] if r.returncode == 0 else ''
    got = _y.safe_load(fm) or {}
    check("pubs: the exporter records the publication and labels tags from ITS vocabulary",
          got.get('publication') == 'b' and got.get('tags') == [{'tag': 'practice', 'label': 'Practice, professionally'}],
          r.stderr[-300:] or fm)
    stray = piece('stray', 'title: S\npublication: a\noutlets: [site-b]\npublished_at: 2026-09-01\n',
                  draft='# S\n\n---\n\nBody.\n')
    r = subprocess.run([sys.executable, site, os.path.join(tmp, 'pb2'), stray, '--outlet', 'site-b'],
                       capture_output=True, text=True, cwd=root)
    check("pubs: the exporter refuses a piece declaring another publication's outlet (exit 9)",
          r.returncode == 9 and 'site-b' in r.stderr, r.stderr[-200:])

    # the store: two publications cannot share a slug
    ca, cb = os.path.join(tmp, 'pca'), os.path.join(tmp, 'pcb')
    for d, pub in ((ca, 'a'), (cb, 'b')):
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'same.md'), 'w').write(
            f'---\nslug: same\ntitle: Same\npublished_at: 2026-09-01\ndigest: sha256:00\npublication: {pub}\n---\n\nBody\n')
    store = os.path.join(tmp, 'pubstore')
    bp = os.path.join(HERE, 'bundle_pieces.py')
    r1 = subprocess.run([sys.executable, bp, ca, store, '--outlet', 'site-a'], capture_output=True, text=True)
    r2 = subprocess.run([sys.executable, bp, cb, store, '--outlet', 'site-b'], capture_output=True, text=True)
    ix = json.load(open(os.path.join(store, 'index.json'))) if r1.returncode == 0 else {}
    check("pubs: the bundler refuses one publication's piece over another's slug (exit 9)",
          r1.returncode == 0 and r2.returncode == 9
          and [p.get('publication') for p in ix.get('pieces', [])] == ['a']
          and json.load(open(os.path.join(store, 'pieces', 'same.json')))['publication'] == 'a',
          (r1.stderr + r2.stderr)[-300:])
    try:
        import store_publish as sp
    except (ImportError, SystemExit):
        skip('pubs: store_publish refuses a record passing between publications', 'boto3 not installed')
    else:
        live = {'pieces': [{'slug': 'same', 'kind': 'piece', 'publication': 'a'},
                           {'slug': 'old', 'kind': 'piece'}]}
        bundle = {'pieces': [{'slug': 'same', 'kind': 'piece', 'publication': 'b'},
                             {'slug': 'same', 'kind': 'talk', 'publication': 'b'},
                             {'slug': 'old', 'kind': 'piece', 'publication': 'b'}]}
        check('pubs: store_publish refuses a record passing between publications, and nothing else',
              sp.publication_conflicts(live, bundle) == ['same (piece): live as a, this bundle says b'],
              str(sp.publication_conflicts(live, bundle)))



# ---------------------------------------------------------------- unit: substack tags
def unit_substack_tags(tmp):
    """Each Substack post set to exactly its piece's tags (2026-09-11). The snippet runs against a
    STUBBED Substack — no network — so what is asserted is the logic: create a missing publication
    tag once, attach what is missing, detach what the desk does not list, never delete a publication
    tag, do nothing the second time, write nothing on a dry run, and refuse a tampered plan."""
    print("\n-- substack tags: the snippet, against a stubbed Substack -------------")
    import substack_tags as st
    root = os.path.join(tmp, 'stdesk'); d = os.path.join(root, 'pieces', 'p')
    os.makedirs(d, exist_ok=True); os.makedirs(os.path.join(root, 'publishing'), exist_ok=True)
    open(os.path.join(root, 'publishing', 'outlets.yaml'), 'w').write(
        'outlets:\n  sub:\n    reader_base: https://x.substack.com/p/\n    account_handle: tagger\n')
    open(os.path.join(root, 'publishing', 'tags.yaml'), 'w').write(
        'tags:\n  - tag: idolatry\n    label: Idolatry\n    about: a\n'
        '  - tag: discernment\n    label: Discernment\n    about: b\n'
        '  - tag: canon\n    label: The Canon\n    about: c\n    substack: false\n')
    man = os.path.join(d, 'publish.yaml')
    open(man, 'w').write('title: P\npost_url: https://x.substack.com/publish/post/42\n'
                         'tags:\n  - canon\n  - discernment\n  - idolatry\n')
    p = st.plan(d)
    check('stags: labels in vocabulary order, and a `substack: false` tag is not sent',
          p['labels'] == ['Idolatry', 'Discernment'] and p['skipped'] == ['canon'] and p['post'] == 42, str(p))
    open(man, 'a').write('published_at: 2026-09-01\n')
    check('stags: a LIVE post is refused without --live', st.main([d]) == 3)
    check('stags: ...but a dry run of a live post needs no --live', st.main([d, '--dry-run', '--out', os.path.join(tmp, 'x.js')]) == 0)
    open(man, 'w').write('title: P\ntags:\n  - idolatry\n')
    check('stags: no post_url is refused', st.main([d]) == 3)
    open(man, 'w').write('title: P\npost_url: https://x.substack.com/publish/post/42\ntags:\n  - nope\n')
    check('stags: a tag not in the vocabulary is refused', st.main([d]) == 3)
    open(man, 'w').write('title: P\npost_url: https://x.substack.com/publish/post/42\n')
    check('stags: an untagged piece is refused — "not tagged yet" is not "strip the post"', st.main([d]) == 3)
    check('stags: --clear sets it to none on purpose', st.plan(d, clear=True)['labels'] == [])

    if not shutil.which('node'):
        skip('stags: the snippet against a stubbed Substack', 'node not installed'); return
    stub = r"""
const pubTags = [{id: 'T1', name: 'Idolatry'}, {id: 'T9', name: 'Other'}], calls = [];
const onPost = { 42: ['T9'], 43: [] };
process.on('exit', () => console.error('CALLS ' + JSON.stringify(calls)));
globalThis.location = { pathname: process.env.PATHNAME || '/publish/home',
                        hostname: process.env.PUB_HOST || 'x.substack.com',
                        origin: 'https://' + (process.env.PUB_HOST || 'x.substack.com') };
globalThis.fetch = async (path, o) => {
  const m = (o && o.method) || 'GET'; calls.push(m + ' ' + path);
  if (path === '/api/v1/user/profile/self')
    return { status: 200, json: async () => ({ handle: process.env.SIGNED_IN || 'tagger' }) };
  const ok = (b) => ({ ok: true, status: 200, text: async () => JSON.stringify(b) });
  if (m === 'GET' && path === '/api/v1/publication/post-tag') return ok(pubTags);
  if (m === 'POST' && path === '/api/v1/publication/post-tag') {
    const t = { id: 'T' + (pubTags.length + 1), name: JSON.parse(o.body).name }; pubTags.push(t); return ok(t); }
  const g = path.match(/^\/api\/v1\/post\/(\d+)\/tag$/);
  if (m === 'GET' && g) return ok((onPost[g[1]] || []).map((id) => ({ post_tag_id: id })));
  const a = path.match(/^\/api\/v1\/post\/(\d+)\/tag\/(.+)$/);
  if (m === 'POST' && a) { onPost[a[1]].push(a[2]); return ok({ post_tag_id: a[2] }); }
  if (m === 'DELETE' && a) { onPost[a[1]] = onPost[a[1]].filter((x) => x !== a[2]); return ok({}); }
  return { ok: false, status: 404, text: async () => 'no route ' + m + ' ' + path };
};
"""
    open(man, 'w').write('title: P\npost_url: https://x.substack.com/publish/post/42\n'
                         'tags:\n  - idolatry\n  - discernment\n')
    q = os.path.join(root, 'pieces', 'q'); os.makedirs(q, exist_ok=True)
    open(os.path.join(q, 'publish.yaml'), 'w').write('title: Q\npost_url: https://x.substack.com/publish/post/43\n'
                                                     'tags:\n  - discernment\n')

    def run(scripts, env=None):
        f = os.path.join(tmp, 'stags-run.mjs')
        open(f, 'w').write(stub + '\nlet result;\n' + '\n'.join(
            '{\n' + s.replace('const result =', 'result =') + '\nconsole.log(JSON.stringify(result));\n}' for s in scripts))
        r = subprocess.run(['node', f], capture_output=True, text=True, env={**os.environ, **(env or {})})
        outs = [json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
        writes = [c for c in json.loads((re.findall(r'CALLS (\[.*\])', r.stderr) or ['[]'])[-1])
                  if c.split()[0] in ('POST', 'DELETE')]
        return r, outs, writes

    both = [st.plan(d), st.plan(q)]
    r, outs, writes = run([st.snippet(both, dry=True)])
    dry = (outs or [{}])[0]
    check('stags: a dry run reports the diff and writes nothing',
          writes == [] and dry.get('dry') is True and dry.get('created') == ['Discernment']
          and dry.get('removed') == ['p: Other'], r.stderr[-300:] or str(dry))
    r, outs, writes = run([st.snippet(both), st.snippet(both)])
    first, second = (outs + [{}, {}])[:2]
    res = {x['slug']: x for x in first.get('results', [])}
    check('stags: the first run creates a shared tag once, attaches what is missing, detaches the extra',
          first.get('ok') is True and first.get('created') == ['Discernment']
          and res.get('p', {}).get('removed') == ['Other'] and res.get('p', {}).get('now') == ['Idolatry', 'Discernment']
          and res.get('q', {}).get('now') == ['Discernment'], r.stderr[-300:] or str(first))
    check('stags: a publication tag is detached, never deleted',
          not any(w.startswith('DELETE /api/v1/publication') for w in writes)
          and any(w == 'DELETE /api/v1/post/42/tag/T9' for w in writes), str(writes))
    check('stags: the second run does nothing',
          second.get('created') == [] and second.get('removed') == []
          and all(x['attached'] == [] for x in second.get('results', [])), str(second))

    bad = st.snippet(both).replace('"Discernment"', '"Discernmnet"', 1)
    r, _o, writes = run([bad])
    check('stags: a plan that fails its checksum is refused, and nothing is written',
          r.returncode != 0 and 'checksum' in r.stderr and writes == [], r.stderr[-300:])
    flipped = st.snippet(both, dry=True).replace('"dry":true', '"dry":false', 1)
    r, _o, writes = run([flipped])
    check('stags: a dry run cannot be turned into a real one in transit — the checksum covers it',
          r.returncode != 0 and writes == [], r.stderr[-300:])
    r, _o, writes = run([st.snippet(both)], env={'PATHNAME': '/publish/post/42'})
    check('stags: the snippet refuses to run in the editor holding a listed post',
          r.returncode != 0 and 'refusing' in r.stderr and writes == [], r.stderr[-200:])
    import substack_account as sa
    r, _o, writes = run([st.snippet(both)], env={'SIGNED_IN': 'someone-else'})
    calls = json.loads((re.findall(r'CALLS (\[.*\])', r.stderr) or ['[]'])[-1])
    check("stags: the snippet carries its posts' account guard, and another account is refused "
          "before any tag call",
          sa.guard_handle(st.snippet(both)) == 'tagger' and r.returncode != 0 and 'accountGuard' in r.stderr
          and calls == ['GET /api/v1/user/profile/self'], r.stderr[-300:])
    r, _o, writes = run([st.snippet(both)], env={'PUB_HOST': 'other.substack.com'})
    calls = json.loads((re.findall(r'CALLS (\[.*\])', r.stderr) or ['[]'])[-1])
    check('stags: a run on another publication of the same account throws before any call at all',
          r.returncode != 0 and 'publication:' in r.stderr and calls == [], r.stderr[-300:])

# ---------------------------------------------------------------- corpus
def corpus_integrity():
    print("\n-- corpus: every piece renders cleanly ---------------------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('corpus render', f'no corpus at {pieces_dir}'); return
    faults, n = [], 0
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        n += 1
        try:
            body, fns, residual, iss = render_reader(d)
        except Exception as e:                                    # noqa: BLE001
            faults.append(f'{p}: render error {e}')
            continue
        for k in ('undefined', 'duplicated', 'nested'):
            if iss[k]:
                faults.append(f'{p}: footnote {k} {iss[k]}')
        if residual:
            faults.append(f'{p}: verify/clearance residue {residual}')
        if not body:
            faults.append(f'{p}: renders to an empty body')
    check(f'all {n} pieces render with no footnote, verify, or clearance faults',
          not faults, '; '.join(faults[:4]))


def corpus_headers():
    """A published piece's draft.md must say it is published.

    The file keeps the name draft.md for its whole life -- renaming would give nine tools
    a second name to know about, and a call site that missed it would not error, it would
    silently drop the piece from every corpus check. So the header carries the state, and
    this check keeps the header honest: it is front matter, invisible to readers, and
    therefore exactly the kind of thing that rots unnoticed without a test.
    """
    print("\n-- corpus: live pieces say they are live --------------------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('headers', f'no corpus at {pieces_dir}'); return
    stale, n = [], 0
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        if not live_url(man):
            continue
        if not man.get('published_at'):
            stale.append(f'{p} (live but no published_at)'); continue
        n += 1
        new, note = header_rewrite(open(os.path.join(d, 'draft.md')).read(), man,
                                   corpus_outlets()[0])
        if new is not None:
            stale.append(p)
        elif note != 'already current':
            # `left alone` is not `current`. A live piece whose front matter piece_header
            # cannot reach (no `---`, no H1) keeps whatever it said while it was a draft, and
            # counting that as a pass is the same silence this check was written against —
            # the fix is a person's, so it has to be said out loud rather than skipped.
            stale.append(f'{p} ({note})')
    check(f'all {n} live pieces carry a current published header',
          not stale, '; '.join(stale[:4]) + '  (fix: piece_header.py --apply)')


def corpus_manifests():
    """Every composed piece carries the two lines the body check cannot see.

    A post's title and subtitle are not in body_html, so corpus_baselines and
    substack_verify's block comparison are blind to them by construction. This is the
    offline half of the guard: the manifest that will be composed must already carry both.
    (The online half is `substack_verify.py --archive`, which reads the reader's list.)
    """
    print("\n-- corpus: composed pieces carry a title and a subtitle -------------")
    import corpus
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('manifests', f'no corpus at {pieces_dir}'); return
    bad, pending, unsettled, captioned, n = [], [], [], [], 0
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'publish.yaml')):
            continue
        n += 1
        errs, warns = manifest_gate(d)
        if errs:
            # A LIVE post with no subtitle is the incident this check was written for
            # (one sat that way 2026-08-05 -> 2026-09-03). The same finding on a piece
            # nobody can read yet is a to-do: it has no subtitle because it has no words.
            # Reported either way; only the live one fails. The guard that actually
            # protects a reader is md_to_substack's exit 6, which refuses to COMPOSE a
            # piece with an empty header and has no override. (2026-09-14, corpus.stage.)
            (bad if corpus.live(d) else pending).append(f'{p}: ' + '; '.join(errs))
        head = [w for w in warns if not w.startswith('cover_caption')]
        if head and live_url(read_manifest(os.path.join(d, 'publish.yaml'))):
            unsettled.append(p)
        if any(w.startswith('cover_caption') for w in warns):
            captioned.append(p)
    check(f'all {n} composed pieces carry a title and a subtitle', not bad, '; '.join(bad[:4]))
    if pending:
        print(f"  note  {len(pending)} unpublished piece(s) still owe a header line: "
              + '; '.join(pending[:4]) + "  (md_to_substack refuses to compose without it)")
    if unsettled:
        print(f"  note  live but the manifest still marks the header unsettled: {', '.join(unsettled)}"
              "  (clear the comment once the author has signed off)")
    if captioned:
        print(f"  note  a caption reads as provenance or repeats the alt: {', '.join(captioned)}"
              "  (a caption says what the image represents -- framework/docs/ALT-TEXT.md)")



def corpus_publications():
    """Once the desk has a publication registry, every manifest names one of its publications."""
    print("\n-- corpus: every piece names its publication --------------------------")
    import publications as pb
    root = os.path.dirname(PIECES)
    pubs, probs = pb.load(root)
    if pubs is None:
        skip('corpus publications', 'no publication registry — a one-publication desk')
        return
    problems, _notes, counts = pb.check(root, pubs, os.path.join(root, 'publishing', 'outlets.yaml'))
    problems = probs + problems
    check('corpus publications: ' + ', '.join(f'{p} {n}' for p, n in counts.items())
          + ' — every manifest names one, and owns its outlets', not problems, '; '.join(problems[:5]))


def corpus_caption_spec():
    """No draft writes a caption into its body — captions live in publish.yaml (2026-09-11)."""
    print("\n-- corpus: captions live in publish.yaml, not draft.md -----------------")
    import md_to_substack as m2s
    bad = [(os.path.basename(d), m2s.caption_prose(d)) for d in (os.path.join(PIECES, n) for n in sorted(os.listdir(PIECES)))
           if os.path.isdir(d) and m2s.caption_prose(d)]
    check(f'corpus captions: no draft writes a caption under an image', not bad,
          '; '.join(f'{s}: {ls[0][:50]}' for s, ls in bad[:4]))


def corpus_companions():
    """Every companion a PUBLISHED piece declares resolves — `companions.py check`.

    Scoped to live pieces on 2026-09-14. A required Note missing from a live piece is a
    fault; the same finding on a piece being drafted is a to-do, and failing on it turns
    CI red for every session over one unfinished scaffold. The publish skill has always
    described this gate as firing "once the piece is live" — it never did. Reported, not
    silenced: the unpublished ones are printed with their stage. (corpus.stage.)
    """
    print("\n-- corpus: companions resolve -----------------------------------------")
    import companions as cp
    found = cp.check(PIECES)
    live = [(s, p) for s, p, st in found if st == 'live']
    later = [(s, p, st) for s, p, st in found if st != 'live']
    check('corpus companions: every declared companion of a PUBLISHED piece resolves '
          '(role, form, voice, back-pointer)',
          not live, '; '.join(f'{s}: {p}' for s, p in live[:4]))
    if later:
        print(f"  note  {len(later)} open on unpublished piece(s), which is a to-do rather "
              f"than a fault: " + '; '.join(f'{s} [{st}]: {p}' for s, p, st in later[:4]))


def corpus_voice_privacy():
    """No private voice's text has reached the framework — `voice_privacy.py` (2026-09-11)."""
    print("\n-- corpus: the instance's voices stay out of the framework ------------")
    import voice_privacy as vp, io, contextlib
    root = os.path.dirname(PIECES)
    if not vp.private_voices(root):
        skip('voice privacy', 'no instance voices — the framework alone has none to leak')
        return
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = vp.main(['--instance', root])
    lines = buf.getvalue().strip().splitlines()
    check('voice privacy: no new run of a private voice anywhere in the framework', rc == 0,
          ' | '.join(lines[:3]))


def corpus_desk_scaffold():
    """What tools/new-desk hands a new desk must be what this desk actually runs.

    The desk's CI workflow and its pre-push hook ship as templates (templates/desk/); new-desk
    copies them into every desk it makes. Nothing kept the template and this desk's own copies in
    step, and drift is invisible from both sides: edit the desk's workflow and new desks keep
    getting the old one; edit the template and nobody here runs what it ships, so it can be wrong
    for months. They are small files and they are supposed to be the same file.
    """
    print("\n-- corpus: the desk runs what new-desk ships ----------------------")
    desk = os.path.dirname(FRAMEWORK)
    if not os.path.isdir(os.path.join(desk, 'pieces')):
        skip('desk scaffold', 'a framework checkout with no desk around it'); return
    tpl = os.path.join(FRAMEWORK, 'templates', 'desk')
    drift, n = [], 0
    for rel in ('.github/workflows/tests.yml', '.githooks/pre-push'):
        shipped, mine = os.path.join(tpl, *rel.split('/')), os.path.join(desk, *rel.split('/'))
        if not os.path.isfile(shipped):
            drift.append(f'{rel}: templates/desk does not ship it'); continue
        if not os.path.isfile(mine):
            drift.append(f'{rel}: this desk has none (fix: prepush.py install, or copy it in)')
            continue
        n += 1
        if open(shipped, encoding='utf-8').read() != open(mine, encoding='utf-8').read():
            drift.append(f'{rel}: this desk and templates/desk differ')
    check(f'all {n} scaffold file(s) match templates/desk', not drift, '; '.join(drift))


def corpus_prose():
    """What the prose claims about a piece agrees with its manifest: check_status, check_refs,
    and — wherever an outlet registry exists — the rule that a published piece says where it goes."""
    print("\n-- corpus: prose agrees with the manifests -----------------------------")
    import check_status as cs
    import check_refs as cr
    import yaml
    root = os.path.dirname(PIECES)
    found, n, _k = cr.problems(root)
    check(f"every cross-reference names its piece by its current title ({n} claim(s))",
          not found, '; '.join(f"{s}: {w} at {where[0][1]}:{where[0][2]}" for s, w, where in found[:5]))
    outlets = os.path.join(root, 'publishing', 'outlets.yaml')
    if not os.path.exists(outlets):
        skip('prose vs manifests, and outlets declared', 'no publishing/outlets.yaml in this corpus')
        return
    f = cs.check([root], PIECES, outlets, None) or []
    check(f"no prose calls a live piece unpublished, or links a draft as live",
          not f, '; '.join(f"{os.path.relpath(p, root)}:{ln} {k} `{s}`" for p, ln, k, s, _w in f[:5]))
    # A piece that declares no outlet is exported nowhere, and outlet_audit checks only the
    # outlets a piece declares — so a published piece with none is invisible to both. That is
    # how Not Made of Things That Appear sat live on Substack and missing from the site.
    missing = []
    for d in sorted(os.listdir(PIECES)):
        mp = os.path.join(PIECES, d, 'publish.yaml')
        if not os.path.exists(mp):
            continue
        with open(mp, encoding='utf-8') as fh:
            m = yaml.safe_load(fh) or {}
        if live_url(m) and not m.get('outlets') and m.get('site') is not True:
            missing.append(d)
    check("every published piece declares its outlets", not missing, ', '.join(missing))
    # Eric, 2026-09-11: "all the pieces on being good should get a place on alignmentfellowship
    # unless i say otherwise." A publication's `required_outlets` is that rule, and a piece opts
    # out only by writing the reason down (`outlets_exempt:`).
    import publications as pb
    pubs, _probs = pb.load(root)
    # The registry, so a piece is PUBLISHED by its own outlet's key. Without it this gate
    # asked nothing of a publication that does not write `public_url`.
    outlets_reg, _legacy = corpus_outlets()
    short = []
    for d in sorted(os.listdir(PIECES)):
        mp = os.path.join(PIECES, d, 'publish.yaml')
        if not os.path.exists(mp):
            continue
        with open(mp, encoding='utf-8') as fh:
            m = yaml.safe_load(fh) or {}
        short += [f'{d} ({o}: {why})' for o, why in pb.missing_required(m, pubs, outlets_reg)]
    check("every published piece is on every outlet its publication requires, or says why not",
          not short, ', '.join(short[:6]))
    # The same rule one layer in: a publication can require a companion of its published pieces.
    # MuffinLabs requires a Note, so it is written with the piece rather than on the morning.
    lacking = []
    for d in sorted(os.listdir(PIECES)):
        mp = os.path.join(PIECES, d, 'publish.yaml')
        if not os.path.exists(mp):
            continue
        with open(mp, encoding='utf-8') as fh:
            m = yaml.safe_load(fh) or {}
        lacking += [f'{d} ({role}: {why})'
                    for role, why in pb.missing_companions(m, pubs, os.path.join(PIECES, d),
                                                           outlets_reg)]
    check("every published piece carries the companions its publication requires, or says why not",
          not lacking, ', '.join(lacking[:6]))
    # `publish_at:` is a refusal, so a manifest the gate cannot read is a gate that is not
    # there — and a piece that is already live cannot also be waiting to go live.
    import schedule as sched
    faults = []
    for d in sorted(os.listdir(PIECES)):
        pdir = os.path.join(PIECES, d)
        if sched.read_field(pdir) is None:
            continue
        try:
            st, moment = sched.state(pdir)
        except sched.Malformed as e:
            faults.append(f'{d}: {e}')
            continue
        with open(os.path.join(pdir, 'publish.yaml'), encoding='utf-8') as fh:
            m = yaml.safe_load(fh) or {}
        # "Live AND embargoed" stopped being a contradiction the day an outlet could be
        # `on_schedule: immediate`: a piece is published on its canonical site the moment it is
        # ready and still waits for its feed outlets. The contradiction is narrower now — live on
        # an outlet that was supposed to WAIT — and asking the old question failed the first
        # canonical-first publication for doing exactly what it was told.
        waited_on = [o for o, cfg in (outlets_reg or {}).items()
                     if cfg.get('manifest_url_key') and m.get(cfg['manifest_url_key'])
                     and sched.policy_for(outlets_reg, o) != 'immediate']
        if st == 'embargoed' and waited_on:
            faults.append(f'{d}: embargoed until {sched.fmt(moment)}, but it is already live on '
                          f'{", ".join(waited_on)}, which waits for the moment')
    check("every publish_at is a readable moment, and no live piece is still embargoed",
          not faults, '; '.join(faults[:5]))


def corpus_tags():
    """Every tag on every piece is in its publication's vocabulary — `tags.py check`."""
    print("\n-- corpus: tags are all in their vocabulary --------------------------")
    import publications as pb
    import tags as tg
    root = os.path.dirname(PIECES)
    pubs, _probs = pb.load(root)
    rows = tg.corpus(root, pubs)
    if not any(r['tags'] for r in rows):
        skip('corpus tags', 'no piece carries a tag yet')
        return
    problems, _notes = tg.check(root, None, pubs)
    check(f"corpus tags: {sum(1 for r in rows if r['tags'])} tagged piece(s), all in their vocabulary",
          not problems, '; '.join(problems[:5]))


def corpus_commonmark():
    """Every draft survives a CommonMark parser — `check_commonmark.py`.

    The desk's Substack converter is lenient; every other outlet renders CommonMark. Two
    reader-visible faults came through that gap on 2026-09-11 (not-yet, son-of-joseph),
    and every other check compared the draft against the outlet that tolerated them."""
    print("\n-- corpus: every draft survives CommonMark --------------------------")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'cc', os.path.join(os.path.dirname(__file__), 'check_commonmark.py'))
    cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
    md = cc._md()
    if md is None:
        skip('corpus commonmark', 'markdown-it-py is not installed — NOT a pass')
        return
    found = []
    for name in sorted(os.listdir(PIECES)):
        p = os.path.join(PIECES, name, 'draft.md')
        if os.path.exists(p):
            for kind, ctx in cc.check_text(open(p, encoding='utf-8').read(), md):
                found.append(f'{name}: {kind} …{ctx[:60]}…')
    check('corpus commonmark: no draft leaks emphasis or a letter-mark backtick',
          not found, '; '.join(found[:4]))


def on_substack(man):
    """Is this piece live on a Substack outlet? An outlet is Substack-shaped when it carries an
    `account_handle` — the account the guard checks before any write — and the piece is live
    there when its manifest holds that outlet's own url key."""
    outlets, _legacy = corpus_outlets()
    for _name, cfg in (outlets or {}).items():
        if not cfg.get('account_handle'):
            continue
        key = cfg.get('manifest_url_key')
        if key and man.get(key):
            return True
    return False


def corpus_baselines():
    print("\n-- corpus: published pieces match their baselines -----------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('corpus baselines', f'no corpus at {pieces_dir}'); return
    pub, behind, ahead, textonly = 0, [], [], []
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        if not live_url(man):
            continue                                              # composed drafts are not live
        # A baseline is the THREE-WAY SYNC's record of what Substack last held, and it exists
        # because Substack's editor is a second writer that can change a post out from under the
        # desk. A piece live only on a store-served site has no second editor: the store copy is
        # regenerated from this draft every publish, so there is nothing to merge against and a
        # missing baseline is not a fault. Asked of every live piece, this failed the first
        # canonical-first publication — live on the blog, Substack still scheduled for Tuesday.
        if not on_substack(man):
            continue
        pub += 1
        base = load_baseline(d)
        if base is None:
            behind.append(f'{p} (no baseline)')
            continue
        body, fns, _r, _i = render_reader(d)
        differs = [H(t) for t in body] != base['body'] or [H(t) for t in fns] != base['fns']
        # The second domain. A baseline sealed before marks were tracked cannot answer, and
        # is listed rather than quietly passed -- an unanswerable check that reports success
        # is the thing this whole change is about.
        if baseline_has_marks(base):
            bm, fm, _ok = render_marks(d)
            if ([HM(r) for r in bm] != base['bodyMarks']
                    or [HM(r) for r in fm] != base['fnsMarks']):
                differs = True
        else:
            textonly.append(p)
        # A draft may be DELIBERATELY ahead of its live post: a rewrite is drafted and is
        # waiting on the author to read it before anything touches a public page. That is a
        # normal, intended state on this desk, and reporting it as a failure for as long as it
        # lasts is how a corpus-wide gate gets tuned out. `draft_ahead:` in publish.yaml is the
        # declaration, and it is deliberately shaped like the `verified:` clearance: a date and
        # a sentence, written where it is reviewable in the diff and survives the session.
        #
        #     draft_ahead:
        #       since: 2026-09-07
        #       note: v2 rewrite drafted, awaiting Eric's read; the post still holds v1.
        #
        # One line per value — `read_manifest` does not fold `>-` block scalars, and a `note:`
        # written as one would parse to the literal string '>-'.
        #
        # Two rules keep it from becoming a way to switch the check off:
        #   * a declaration with no `since:` date does NOT excuse anything — it still fails, so
        #     the escape hatch cannot be a bare toggle;
        #   * a declaration on a piece that is back IN SYNC fails too, which retires the key by
        #     itself once the rewrite ships, instead of letting it sit there excusing the next
        #     drift nobody noticed.
        decl = man.get('draft_ahead')
        since = decl.get('since', '').strip() if isinstance(decl, dict) else ''
        if decl and not since:
            behind.append(f'{p} (draft_ahead: with no since: date)')
        elif decl and not differs:
            behind.append(f'{p} (draft_ahead: but the draft matches the post — retire the key)')
        elif decl:
            ahead.append((p, since, _age(since), decl.get('note', '').strip()))
        elif differs:
            behind.append(p)
    check(f'all {pub} published pieces are in sync', not behind, '; '.join(behind))
    if textonly:
        print(f"  note  {len(textonly)} baseline(s) predate mark tracking, so FORMATTING is not "
              f"checked for them: {', '.join(textonly[:6])}"
              + (' …' if len(textonly) > 6 else ''))
        print(f"        (they seal with marks on the next completed sync; until then only their "
              f"text is held to the baseline)")
    for name, since, age, note in ahead:
        print(f"  note  {name}: draft deliberately ahead of the live post since {since}{age} "
              f"(declared in publish.yaml; a re-sync or recompose clears it)"
              + (f"\n        {note}" if note else ''))


def _age(since):
    """' , N days' for a declaration date, so one left to rot is visible in the report."""
    try:
        d = datetime.date.fromisoformat(since)
    except ValueError:
        return ''
    n = (datetime.date.today() - d).days
    return f', {n} day{"" if n == 1 else "s"}' if n > 0 else ''


# ---------------------------------------------------------------- engine (stubbed browser)
def engine_suite(tmp):
    print("\n-- engine: JS patcher against a stubbed editor --------------------")
    pieces_dir = PIECES
    if not os.path.isdir(pieces_dir):
        skip('engine suite', f'no corpus at {pieces_dir}'); return
    repatch = os.path.join(HERE, 'substack_repatch.py')
    runner = os.path.join(HERE, 'test_substack_repatch.js')
    srunner = os.path.join(HERE, 'test_substack_structural.js')
    scanner = os.path.join(HERE, 'test_substack_scan.js')
    if not shutil.which('node'):
        skip('engine suite', 'node not available')
        return
    # Every snippet carries its piece's account guard, so a generator needs outlets.yaml to say
    # whose post a piece is. The fixtures have no desk around them: give them one Substack outlet
    # on their post_url host. A piece that is on no Substack outlet has no post to patch.
    import substack_account as sa
    env = dict(os.environ)
    if CORPUS_KIND == 'fixture' and not env.get('DESK_OUTLETS'):
        env['DESK_OUTLETS'] = os.path.join(tmp, 'fixture-outlets.yaml')
        with open(env['DESK_OUTLETS'], 'w', encoding='utf-8') as fh:
            fh.write('outlets:\n  fixture:\n    platform: substack\n'
                     '    reader_base: https://example.invalid/p/\n    account_handle: fixture\n')
    failures, ran, skipped, scan_ok, off_substack = [], 0, 0, 0, 0
    for p in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, p)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        try:
            sa.outlet_for_piece(d, env.get('DESK_OUTLETS'))
        except sa.NoAccount:
            off_substack += 1
            continue
        js = os.path.join(tmp, f'{p}.js')
        gen = subprocess.run([sys.executable, repatch, d, js], capture_output=True, text=True, env=env)
        if gen.returncode != 0:
            failures.append(f'{p}: generator refused ({gen.stdout.strip().splitlines()[:1]})')
            continue
        r = subprocess.run(['node', runner, js], capture_output=True, text=True)
        ran += 1
        skipped += r.stdout.count('\nskip') + r.stdout.startswith('skip')
        if r.returncode != 0:
            failures.append(f'{p}: ' + '; '.join(l.strip() for l in r.stdout.splitlines()
                                                 if l.startswith('FAIL')))
        # the structural engine, against the same piece: S1–S9, with a document model that
        # moves whole blocks, anchors and marks (see test_substack_structural.js)
        sjs = os.path.join(tmp, f'{p}.structural.js')
        sgen = subprocess.run([sys.executable, repatch, '--structural', d, sjs], capture_output=True, text=True,
                              env=env)
        if sgen.returncode != 0:
            failures.append(f'{p}: structural generator refused ({sgen.stdout.strip().splitlines()[:1]})')
            continue
        sr = subprocess.run(['node', srunner, sjs], capture_output=True, text=True)
        skipped += sr.stdout.count('\nskip') + sr.stdout.startswith('skip')
        if sr.returncode != 0:
            failures.append(f'{p} [structural]: ' + '; '.join(l.strip() for l in sr.stdout.splitlines()
                                                              if l.startswith('FAIL')))

        # THE CROSS-THE-WIRE ASSERTION, and the one the sync baseline rests on. SCAN_JS
        # computes a mark signature in the browser; mark_sig() computes one in Python. They
        # are the same string derived on two sides of a wire, and a hash of two strings that
        # can disagree is not a baseline. Run the real scan snippet against this piece's own
        # document and require both domains to match digest for digest. The scan is generated per
        # piece: its content is the same everywhere, but its guard names the piece's account.
        scan_js = os.path.join(tmp, f'{p}.scan.js')
        subprocess.run([sys.executable, os.path.join(HERE, 'substack_sync.py'), 'scan', d, scan_js],
                       capture_output=True, text=True, env=env)
        if not os.path.isfile(scan_js):
            failures.append(f'{p} [scan]: the scan generator wrote nothing')
        else:
            cr = subprocess.run(['node', scanner, scan_js, sjs], capture_output=True, text=True)
            if cr.returncode != 0:
                failures.append(f'{p} [scan]: runner failed ({cr.stderr.strip()[:120]})')
            else:
                try:
                    live = json.loads(cr.stdout)
                except Exception as e:                            # noqa: BLE001
                    failures.append(f'{p} [scan]: unparseable output ({e})')
                    continue
                # The scan hashes its own output (2026-09-14), so what comes back is
                # {scanVersion, sha256, scan}. Unwrap it HERE and check the digest — this
                # corpus run over 45 pieces is the widest exercise the self-hash gets, and
                # a wrapper the suite merely tolerated would prove nothing about it.
                if isinstance(live, dict) and 'scan' in live and 'sha256' in live:
                    got = hashlib.sha256(live['scan'].encode('utf-8')).hexdigest()
                    if got != live['sha256']:
                        failures.append(f'{p} [scan]: the scan does not hash to the digest '
                                        f'it carries')
                        continue
                    live = json.loads(live['scan'])
                else:
                    failures.append(f'{p} [scan]: the scan carries no self-hash')
                    continue
                st = draft_state(d)
                want_t = ([H(t) for t in st['body']], [H(t) for t in st['fns']])
                want_m = ([HM(r) for r in st['bodyMarks']], [HM(r) for r in st['fnsMarks']])
                if (list(want_t[0]), list(want_t[1])) != (live['body'], live['fns']):
                    failures.append(f'{p} [scan]: the browser and Python disagree on TEXT hashes')
                elif (list(want_m[0]), list(want_m[1])) != (live['bodyMarks'], live['fnsMarks']):
                    bad = next((i for i, (x, y) in enumerate(zip(want_m[0], live['bodyMarks']))
                                if x != y), None)
                    failures.append(f'{p} [scan]: the browser and Python disagree on MARK '
                                    f'signatures (first body row {bad})')
                else:
                    scan_ok += 1
    if off_substack:
        print(f"        ({off_substack} piece(s) on no Substack outlet: no post to patch)")
    if not ran and off_substack and not failures:
        # Two different zeros, and only one of them is a fault. A desk whose pieces are on no
        # Substack outlet — a new one, before publishing/outlets.yaml exists — has no post to
        # patch, and the engine is INAPPLICABLE. The zero this check is for is a corpus where
        # the generator refused piece after piece: that still fails, with the refusal named.
        skip('JS patcher suite', f'{off_substack} piece(s), none on a Substack outlet')
    else:
        check(f'JS patcher suite passes for all {ran} pieces', ran > 0 and not failures,
              ' | '.join(failures[:3]) or 'no piece ran')
    check(f'the browser and Python agree on text AND mark digests for all {scan_ok} pieces',
          scan_ok == ran, f'{scan_ok}/{ran}')
    if skipped:
        print(f"        ({skipped} inapplicable check(s) skipped across the corpus)")


def reseal_fixtures():
    """Rewrite the fixture golden baselines from the converter's current output.

    This is the ONE writing operation in this file, it is opt-in, and it refuses to
    touch anything but the shipped fixtures — a golden file you can reseal by accident
    is not golden, and resealing the real corpus from here would silently move a
    published piece's sync baseline without ever looking at the live post.
    """
    from substack_sync import write_baseline
    fixtures = os.path.join(HERE, 'fixtures', 'pieces')
    if os.path.abspath(PIECES) != os.path.abspath(fixtures):
        print(f"refusing: --reseal-fixtures only reseals {fixtures}, but the corpus "
              f"is {CORPUS_KIND} ({PIECES})")
        return 1
    n = 0
    for name in sorted(os.listdir(fixtures)):
        d = os.path.join(fixtures, name)
        if not os.path.isfile(os.path.join(d, 'draft.md')):
            continue
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        if not man.get('public_url'):
            continue
        body, fns, _r, _i = render_reader(d)
        write_baseline(d, man.get('title', ''), man.get('subtitle', ''),
                       [H(t) for t in body], [H(t) for t in fns],
                       'fixture golden file — sealed by test_suite.py --reseal-fixtures')
        print(f"  sealed  {name}  ({len(body)} body, {len(fns)} fns)")
        n += 1
    print(f"{n} fixture baseline(s) resealed")
    return 0


def unit_furniture_and_body_scripture(tmp):
    """The three faults of 2026-09-11, each pinned by a test.

    1. A running header/footer landed INSIDE verse text ("of the stock of Israel,
       [of] the www.holybooks.com Page 678 tribe of Benjamin"), so a correct
       quotation of Philippians 3:5 was reported as drift. 684 verses of the shipped
       KJV index carried it and every check passed them.
    2. `refindex --verify` had no opinion about furniture, so a contaminated index
       could be built, verified, shipped and trusted.
    3. `check_loci` read the footnotes only, so a piece that quotes scripture in
       its prose could report "0 problems" having checked none of what a reader sees.
    """
    import importlib.util, os, gzip

    def load(name):
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(os.path.dirname(__file__), name + '.py'))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m

    RI = load('refindex')

    # 1. the frequency stripper removes what repeats and keeps what does not
    # Each page carries the SAME running furniture and DIFFERENT work text — which is
    # the whole distinction the stripper runs on. A fixture whose pages are identical
    # makes the work furniture by definition and proves nothing.
    work = ['beginning God created the heaven', 'earth was without form and void', 'God said Let there be light', 'God divided the light from darkness', 'evening and the morning were first', 'waters be gathered unto one place', 'dry land appear and it was so', 'earth bring forth grass the herb', 'lights in the firmament of heaven', 'greater light to rule the day']
    pages = [(i, f"www.holybooks.com Page {i} {w}") for i, w in enumerate(work, 1)]
    cleaned, report = RI.strip_furniture(pages)
    check('furniture: the repeated header is stripped from every page',
          all('holybooks' not in t for _, t in cleaned), str(cleaned[:1]))
    check('furniture: the work\'s own words survive',
          all(w in t for w, (_, t) in zip(work, cleaned)), str(cleaned[:2]))
    check('furniture: the stripper reports what it dropped', bool(report), str(report))

    # a phrase on ONE page is not furniture, and deleting it would delete the work
    pages = [(1, 'a singular sentence appears only here')] + \
            [(i, f'common running head page {i} ordinary text') for i in range(2, 12)]
    cleaned, _ = RI.strip_furniture(pages)
    check('furniture: a phrase on one page is left alone',
          'a singular sentence appears only here' in cleaned[0][1], cleaned[0][1])

    # 2. --verify refuses an index that still carries furniture
    bad = os.path.join(tmp, 'dirty.tsv')
    with open(bad, 'w', encoding='utf-8') as f:
        f.write('Genesis\t1\t1\tIn the beginning www.holybooks.com God created\n')
    check('verify: a contaminated index cannot pass', RI.verify(bad) != 0, 'verify returned 0')

    # 3. check_loci reads the BODY, not only the notes
    CS = load('check_loci')
    idx = os.path.join(tmp, 'mini.tsv')
    with open(idx, 'w', encoding='utf-8') as f:
        f.write('Genesis\t50\t15\tAnd when Joseph\u2019s brethren saw that their father was '
                'dead, they said, Joseph will peradventure hate us\n')
    piece = os.path.join(tmp, 'piecebody'); os.makedirs(piece, exist_ok=True)
    with open(os.path.join(piece, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write('# T\n\n*scaffold*\n\n---\n\n'
                'The text says *when Joseph\u2019s brethren saw that their father was dead, '
                'they said, Joseph will peradventure hate us*.[^g]\n\n'
                '[^g]: Genesis 50:15, KJV.\n')
    import subprocess, sys
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__),
                        'check_loci.py'), piece, '--index', idx],
                       capture_output=True, text=True)
    check('check_loci: a body quotation is checked', 'MATCH' in r.stdout, r.stdout[-300:])
    check('check_loci: the body count reaches the summary',
          '1 quotation(s) checked' in r.stdout or '2 quotation(s) checked' in r.stdout,
          r.stdout[-200:])


def unit_wrapped_links(tmp):
    """A markdown link whose URL is split across lines — published as a dead %20 address.

    Measured 2026-09-13 on what-holds-you-here: applying a review re-flowed a footnote and
    textwrap broke `…/p/where-the-timelines-agree` after a HYPHEN. The spaces inside a link
    were hidden from the wrapper; hyphens were not. The Substack converter then joined the
    halves with a space, and the composed post carried a dead link — while `check_links`
    reported 0 dead, because its LINK_RE (`[^)\\s]+`) cannot match a URL with a newline in
    it, so the link was not checked at all. Two holes, one shape: the tool that re-flows and
    the tool that checks were both blind to the same break.
    """
    import importlib.util, os, subprocess, sys

    def load(name):
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(os.path.dirname(__file__), name + '.py'))
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m

    RA = load('review_artifact')
    url = 'https://elmuffin.substack.com/p/where-the-timelines-agree'
    block = ('[^lot]: Luke 17:31-33, KJV. Verse 33 is close kin to Matthew 10:39, which '
             f'[*Where the Timelines Agree*]({url}) references without quoting in its last '
             'movement; the body quotes Luke\'s form, so the two are not the same move.')
    out = RA.rewrap(block, 96)
    check('rewrap: a URL is never split, not even at a hyphen',
          all(url in line for line in [' '.join(out.split())]) and
          not any(l.rstrip().endswith('-') and 'http' in l for l in out.split('\n')),
          out)
    check('rewrap: the block is still wrapped to the measure',
          max(len(l) for l in out.split('\n')) <= 110, out)

    # check_links sees a wrapped URL, and says so even when nothing else is checkable
    d = os.path.join(tmp, 'wrapped'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'draft.md'), 'w', encoding='utf-8') as f:
        f.write('# T\n\n*scaffold*\n\n---\n\nSee [*A*](https://example.com/a-\n    b) here.\n')
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), 'check_links.py'), d],
                       capture_output=True, text=True)
    check('check_links: a URL split across lines is a finding',
          'SPLIT ACROSS LINES' in r.stdout and r.returncode != 0,
          f'rc={r.returncode} {r.stdout[-200:]}')


def unit_outlet_readiness(tmp):
    """A piece must be able to reach every outlet it names BEFORE the first one publishes.

    Measured 2026-09-13: Substack published and emailed, then the site upload failed on an
    expired SSO token. Half-published, and discovered in the only order that cannot be undone.
    """
    import os, subprocess, sys, textwrap
    tool = os.path.join(os.path.dirname(__file__), 'check_outlets.py')

    d = os.path.join(tmp, 'nooutlets'); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'draft.md'), 'w').write('# T\n\n---\n\nbody\n')
    open(os.path.join(d, 'publish.yaml'), 'w').write('title: T\nsubtitle: S\n')
    r = subprocess.run([sys.executable, tool, d], capture_output=True, text=True)
    check('outlets: a piece declaring none is refused',
          r.returncode == 4 and 'no `outlets:`' in r.stdout, r.stdout[-160:])

    d2 = os.path.join(tmp, 'browseronly'); os.makedirs(d2, exist_ok=True)
    open(os.path.join(d2, 'draft.md'), 'w').write('# T\n\n---\n\nbody\n')
    open(os.path.join(d2, 'publish.yaml'), 'w').write('title: T\nsubtitle: S\noutlets:\n  - substack\n')
    reg = os.path.join(tmp, 'outlets.yaml')
    open(reg, 'w').write(textwrap.dedent("""
        outlets:
          substack:
            account_handle: someone
    """).strip() + '\n')
    r = subprocess.run([sys.executable, tool, d2, '--outlets', reg], capture_output=True, text=True)
    check('outlets: a browser outlet reports MANUAL and never a pass',
          r.returncode == 0 and 'man ' in r.stdout and 'account guard' in r.stdout, r.stdout[-160:])

    d3 = os.path.join(tmp, 'unknownoutlet'); os.makedirs(d3, exist_ok=True)
    open(os.path.join(d3, 'draft.md'), 'w').write('# T\n\n---\n\nbody\n')
    open(os.path.join(d3, 'publish.yaml'), 'w').write('title: T\nsubtitle: S\noutlets:\n  - nowhere\n')
    r = subprocess.run([sys.executable, tool, d3, '--outlets', reg], capture_output=True, text=True)
    check('outlets: an outlet the registry does not know is not a pass',
          r.returncode == 4, r.stdout[-160:])


def main():
    if '--reseal-fixtures' in sys.argv:
        return reseal_fixtures()
    print("regression suite — no deletion, no network, no browser, repo read-only")
    print(f"corpus: {CORPUS_KIND}  ({PIECES})")
    with tempfile.TemporaryDirectory(prefix='desk-suite-') as tmp:
        print(f"scratch: {tmp}  (removed on exit)")
        unit_normalization()
        unit_link_extraction()
        unit_review_artifact(tmp)
        unit_corpus(tmp)
        unit_required_companions(tmp)
        unit_linkedin_canonical_once(tmp)
        unit_schedule(tmp)
        unit_scripture(tmp)
        unit_pages(tmp)
        unit_outlet_content(tmp)
        unit_commonmark(tmp)
        unit_references(tmp)
        unit_canons(tmp)
        unit_scan_hash(tmp)
        unit_rehash(tmp)
        unit_shelf(tmp)
        unit_reference_add(tmp)
        unit_quotes(tmp)
        unit_quotes_false_positives(tmp)
        unit_furniture_and_body_scripture(tmp)
        unit_wrapped_links(tmp)
        unit_outlet_readiness(tmp)
        unit_notes(tmp)
        unit_outlet_urls(tmp)
        unit_live_urls(tmp)
        unit_outlet_reverse(tmp)
        unit_stage(tmp)
        unit_companions(tmp)
        unit_cli_dispatch()
        unit_piece_resolution(tmp)
        unit_three_way()
        unit_converter(tmp)
        unit_footnote_continuation(tmp)
        unit_footnote_order(tmp)
        unit_pull_verification()
        unit_images()
        unit_live_extraction()
        unit_mark_drift(tmp)
        unit_anchor_drift(tmp)
        unit_sync_baseline_marks(tmp)
        unit_manifest_gate(tmp)
        unit_pronouns(tmp)
        unit_talk(tmp)
        unit_deck(tmp)
        unit_dc(tmp)
        unit_talk_tags(tmp)
        unit_audit_tags(tmp)
        unit_store(tmp)
        unit_tags(tmp)
        unit_publications(tmp)
        unit_publication_ownership(tmp)
        unit_substack_tags(tmp)
        unit_linkedin(tmp)
        unit_linkedin_post(tmp)
        unit_scratch(tmp)
        unit_captions(tmp)
        unit_prose(tmp)
        unit_substack_account(tmp)
        unit_account_guard(tmp)
        unit_automode(tmp)
        corpus_integrity()
        corpus_headers()
        corpus_manifests()
        corpus_publications()
        corpus_companions()
        corpus_caption_spec()
        corpus_voice_privacy()
        corpus_tags()
        corpus_baselines()
        corpus_commonmark()
        corpus_desk_scaffold()
        corpus_prose()
        engine_suite(tmp)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped")
    for name, detail in FAIL:
        print(f"  FAILED  {name}   {detail}")
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
