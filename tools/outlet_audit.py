#!/usr/bin/env python3
"""outlet_audit.py — does every piece actually exist on every outlet it declares?

WHY THIS EXISTS (2026-09-09, and it is not hypothetical)

  A piece was published, went live on one outlet, and was HTTP 404 on a second live
  outlet that had been standing unfed for weeks. Every step reported success, because
  each outlet's own checks only ever looked at that outlet. `substack_verify --archive`
  audits one publication against the desk; nothing compared the desk's outlets to each
  other. It was found by a person running `curl` by hand.

  HALF-PUBLISHED IS THE STATE NOTHING REPORTS, because both halves look complete from
  inside themselves. This is the check that looks across.

WHAT IT CHECKS

  forward   every piece that is PUBLISHED and DECLARES an outlet resolves there (200,
            and the page actually mentions the piece). A 404 is drift, not an error.
  declared  a piece that is live on an outlet it does not declare — the manifest is
            lying about where the piece went, which is how an outlet quietly acquires
            content nobody tracks.
  reverse   every URL the outlet itself lists (sitemap or index) is a piece the desk
            knows about. This is the only direction that can see a page the desk never
            produced.
  preview   on an outlet with `og_image: true`, every live page names an og:image and it
            answers 200 with an image. A store publish is an upload that never touches the
            site repo, so a piece can go live with its link preview 404 — on 2026-09-11 one
            of 33 did, and a shared link showed no image. Nothing else looks.

  tags      every text's tags on the STORE INDEX (what every store-backed site reads —
            pieces and talks, tag ids AND labels, one fetch) and on each live SUBSTACK post
            (through substack_tags' own plan and reader) match the desk. A tag added to a
            live text reaches no outlet by itself; on 2026-09-15 two texts were found publicly
            untagged by a person looking at a page. `--no-tags` skips it.

WHAT IT REFUSES TO CONCLUDE

  That a piece is fine because it was not checked. "Could not reach" is its own exit
  code and never wears the same face as "matches" — the same rule substack_verify sets.

CONFIG (instance-side; the framework holds no URLs)

  publishing/outlets.yaml:

    legacy_outlet: alignmentfellowship   # what a pre-outlets `site: true` means
    outlets:
      substack:
        reader_base: https://elmuffin.substack.com/p/
        manifest_url_key: public_url
      alignmentfellowship:
        reader_base: https://alignmentfellowship.org/writings/
        trailing_slash: true
        manifest_url_key: site_url
        sitemap: https://alignmentfellowship.org/sitemap.xml

  An outlet without native footnotes names how it prints a reference inline —
  `footnote_marker: bracket` for "word.[1]" — so --content does not read the marker as
  changed text (FOOTNOTE_MARKERS).

USAGE
  python3 outlet_audit.py [--config publishing/outlets.yaml] [--pieces pieces]
                          [--outlet NAME] [--no-reverse] [--no-tags] [--store FILE] [--quiet]

EXIT
  0 every declared outlet has its piece      3 drift (something missing or undeclared)
  1 usage / config                           2 nothing could be reached
"""
import sys, os, re, json, time, argparse, urllib.request, urllib.error, urllib.parse
import html as html_mod
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import yaml

UA = 'scriptorium-outlet-audit/1.0'


def die(code, msg):
    print(f"outlet_audit: {msg}", file=sys.stderr)
    sys.exit(code)


class _Redirect308(urllib.request.HTTPRedirectHandler):
    """urllib does not follow 308 on its own, and a site that renames slugs answers
    almost entirely in 308s. Reading those as misses is how an audit invents 19
    failures that are all the same fact: the desk's directory name is not the
    published slug."""
    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_301(req, fp, 301, msg, headers)


_OPENER = urllib.request.build_opener(_Redirect308)


def fetch(url, timeout=20):
    """(status, text, final_url). status None means the request itself failed."""
    bust = url + (('&' if '?' in url else '?') + f'_cb={int(time.time())}')
    req = urllib.request.Request(bust, headers={
        'User-Agent': UA, 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace'), r.geturl().split('?')[0]
    except urllib.error.HTTPError as e:
        return e.code, '', url
    except Exception:
        return None, '', url


def fetch_type(url, timeout=20):
    """(status, content-type) for an asset, reading one byte of it. Not cache-busted: an
    image URL can be a signed or transform URL, and a query string is not ours to add."""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            r.read(1)
            return r.status, (r.headers.get('Content-Type') or '').split(';')[0].strip()
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return None, ''


def og_image_url(page_html, page_url):
    """The page's link-preview image as an absolute URL, or None if it names none.
    `og:image:width` and friends are not the image."""
    for tag in re.findall(r'<meta\b[^>]*>', page_html, flags=re.I):
        if re.search(r'''(?:property|name)\s*=\s*["']og:image["']''', tag, flags=re.I):
            m = re.search(r'''content\s*=\s*["']([^"']+)["']''', tag, flags=re.I)
            if m:
                return urllib.parse.urljoin(page_url, html_mod.unescape(m.group(1).strip()))
    return None


def preview_problem(page_html, page_url, probe=fetch_type):
    """None if the page's link preview resolves to an image, else what is wrong with it."""
    img = og_image_url(page_html, page_url)
    if not img:
        return 'the page names no og:image'
    status, ctype = probe(img)
    if status is None:
        return f'og:image could not be reached: {img}'
    if status != 200:
        return f'og:image answers HTTP {status}: {img}'
    if not ctype.startswith('image/'):
        return f'og:image is {ctype or "untyped"}, not an image: {img}'
    return None


def landed_on_not_found(final_url, outlet_cfg):
    """A missing page that REDIRECTS to a page that exists answers 200.

    Measured 2026-09-10: a LinkedIn article that does not exist answers 301 to
    /top-content/?trk=article_not_found, which is a real page and returns 200. The
    forward check followed the redirect and read that 200 as the article being live —
    the audit would have reported every missing LinkedIn copy as present. An outlet
    names the markers that mean "this is where you land when it is not there"."""
    markers = outlet_cfg.get('not_found_markers') or []
    return any(m in (final_url or '') for m in markers)


def schedule_state(piece_dir, outlet, outlet_cfg):
    """-> ('scheduled', moment, how) | ('unscheduled', moment, None) | (None, None, None).

    Three states, because the middle one was invisible: an outlet that WAITS, whose moment is
    still ahead, either has a native schedule recorded against it or does not — and "does not"
    is the silent miss this whole check exists for. Reading `publish_at` alone said the same
    reassuring sentence either way."""
    when = pending_until(piece_dir, outlet_cfg)
    if not when:
        return None, None, None
    try:
        import schedule
        rec = schedule.scheduled_record(piece_dir, outlet)
    except Exception:
        rec = None
    if rec:
        how = f"{rec.get('where', 'recorded')} — set {rec.get('set', '?')}"
        return 'scheduled', when, how
    return 'unscheduled', when, None


def pending_until(piece_dir, outlet_cfg):
    """-> the moment this piece is due on THIS outlet, if that moment is still ahead; else None.

    One field, read two ways, which is the point: `publish_at` is the piece's moment, and an
    outlet's `on_schedule` decides whether it waits for it. A canonical site is `immediate` and
    is live now; a feed outlet is `at_moment` and is absent on purpose until then. Anything
    else — no moment, an unreadable one, an immediate outlet — answers None, so the absence is
    audited rather than excused."""
    if str((outlet_cfg or {}).get('on_schedule') or '').strip().lower() == 'immediate':
        return None
    try:
        import schedule
        st, moment = schedule.state(piece_dir)
    except Exception:
        return None                                   # unreadable: audit it rather than excuse it
    return schedule.fmt(moment) if st == 'embargoed' else None


def slug_of(manifest, piece_name, outlet_cfg):
    """The piece's address on this outlet: the manifest's own URL if it records one,
    else reader_base + the slug. A recorded URL always wins — a piece whose live slug
    was renamed is exactly the case a guessed URL gets wrong."""
    key = outlet_cfg.get('manifest_url_key')
    if key and manifest.get(key):
        return str(manifest[key])
    # An outlet whose addresses cannot be derived — LinkedIn's /pulse/<slug>-<author>-<id>
    # carries an id nothing on the desk knows — is checked only at a RECORDED url. Guessing
    # one would audit a page that never existed and call the miss a finding.
    if outlet_cfg.get('derive') is False:
        return None
    base = outlet_cfg.get('reader_base', '')
    if not base:
        return None
    # The desk's DIRECTORY name is not the published slug: pieces get retitled and the
    # directory keeps its original name (`thousand-faces` publishes as
    # `the-mask-comes-off-last`). Prefer the slug the piece already has on another
    # outlet, which is derived from the title the same way.
    #
    # `site_slug` OUTRANKS BOTH, because it is the desk saying the address outright — it is
    # the one field whose whole purpose is to override the derivation, and `md_to_site`
    # already publishes under it (`site_slug_of`), so a web outlet serves that slug and not
    # this piece's directory name. This tool did not read it, so it would have checked the
    # wrong page in the forward direction and called the right one unknown in reverse. Three
    # imported MuffinLabs pieces carry one to keep a URL across a redraft; all three happen
    # to match their directory today, so nothing on the corpus moves (measured 2026-09-11) —
    # it is the next retitle that would have found this, as a false finding.
    slug = piece_name
    src = outlet_cfg.get('slug_source')
    if src and manifest.get(src):
        slug = str(manifest[src]).rstrip('/').split('/')[-1]
    if manifest.get('site_slug'):
        slug = str(manifest['site_slug']).rstrip('/').split('/')[-1]
    url = base.rstrip('/') + '/' + slug
    return url + '/' if outlet_cfg.get('trailing_slash') else url


def known_on(pieces, outlet_cfg):
    """Every slug the desk CLAIMS on this outlet — the set the reverse check subtracts from.

    It asks `slug_of`, the same resolver the forward direction uses, so the two cannot
    disagree about a piece's address. That is the whole fix: this was a hand-rolled set of
    `public_url` and `site_url` slugs plus every piece's directory name, which is neither of
    the two things that actually decide a public address. It missed

      * EVERY OTHER OUTLET'S KEY. outlets.yaml has said since the professional line was added
        that each outlet gets its own `manifest_url_key`, and it named this as the cost of
        that: a `blog_url` read as a page the desk does not know. The comment said to fix it
        in the tool rather than by re-colliding the keys, and this is that fix.
      * `site_slug`, which is the desk SAYING what a piece is called in public — the one
        field whose entire purpose is to override the derivation. Three imported MuffinLabs
        pieces carry one.
      * `slug_source`, which is why alignmentfellowship resolves at all: its published slug
        is derived from the Substack URL, not from the directory name.

    A directory name is still included, because a piece with no recorded URL and no
    `site_slug` on an outlet that cannot derive one is claimed under its handle and nothing
    else. Measured 2026-09-11: alignmentfellowship's 36 live URLs stay known, and muffinlabs'
    sitemap can be wired without a single false finding.
    """
    known = {pc['name'] for pc in pieces}
    for pc in pieces:
        u = slug_of(pc['manifest'], pc['name'], outlet_cfg)
        if u:
            known.add(str(u).rstrip('/').split('/')[-1])
    return known


def load_pieces(pieces_dir, legacy_outlet):
    out = []
    for name in sorted(os.listdir(pieces_dir)):
        p = os.path.join(pieces_dir, name, 'publish.yaml')
        if not os.path.isfile(p):
            continue
        with open(p) as f:
            m = yaml.safe_load(f) or {}
        declared = m.get('outlets')
        legacy = False
        if not isinstance(declared, list):
            declared = [legacy_outlet] if (m.get('site') is True and legacy_outlet) else []
            legacy = bool(declared)
        out.append({'name': name, 'manifest': m, 'declared': declared,
                    'legacy': legacy, 'published': bool(m.get('published_at'))})
    return out



# ---------------------------------------------------------------- content check
def _render_reader(piece_dir):
    """The desk's own reader-text renderer, borrowed rather than reimplemented."""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location('_mts', os.path.join(here, 'md_to_substack.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.render_reader(piece_dir)


def _text_of(md):
    """Markdown body -> the paragraphs a reader sees, normalised for comparison."""
    md = re.sub(r'```.*?```', ' ', md, flags=re.S)          # fenced code
    md = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', md)          # images
    # Footnote definitions, WHOLE — they run to the next blank line. Anchoring to `$`
    # removes only the first line and leaves the tail behind as a phantom paragraph, raw
    # markdown link and all, which then matches nothing (2026-09-10).
    # Footnote TEXT is deliberately out of scope here: substack_verify compares notes on
    # Substack footnote-for-footnote, and this check is about the body a reader scrolls.
    md = re.sub(r'^\[\^[\w-]+\]:.*?(?=\n\s*\n|\Z)', '', md, flags=re.M | re.S)
    md = re.sub(r'\[\^[\w-]+\]', '', md)                    # footnote refs
    md = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', md)        # links -> their text
    md = re.sub(r'[*_`>#]+', '', md)                        # emphasis, quotes, headings
    out = []
    for block in re.split(r'\n\s*\n', md):
        t = _norm_text(block)
        if len(t) >= 40:                                    # skip headings/short lines
            out.append(t)
    return out


def _strip_page_furniture(page):
    """Remove what the TEMPLATE adds, so only the author's words are compared.

    Three things, each of which produced false drift before it was handled (2026-09-10):

    - `<script>` / `<style>`. Substack ships the whole post again inside a JSON preload;
      leaving it in means the comparison can pass against data rather than against the
      page a reader sees, which is a pass for the wrong reason.
    - Footnote ANCHORS. A native footnote renders its number inline — "…to steer. 1 It's
      also the old error…" — and the draft has no such digit, so every paragraph carrying
      a footnote read as missing.
    - `<sup>` generally, which is how both outlets mark those numbers.
    """
    page = re.sub(r'<script\b.*?</script>', ' ', page, flags=re.S | re.I)
    page = re.sub(r'<style\b.*?</style>', ' ', page, flags=re.S | re.I)
    page = re.sub(r'<a\b[^>]*href="#footnote[^"]*"[^>]*>.*?</a>', ' ', page, flags=re.S | re.I)
    page = re.sub(r'<sup\b.*?</sup>', ' ', page, flags=re.S | re.I)
    return page


# How an outlet with NO native footnotes prints a reference in the body, so --content can
# drop it. LinkedIn has none: md_to_linkedin writes "\u2026Sam.[1] Thirty-four\u2026" and appends a
# Notes section, and the check read every footnoted paragraph as missing from a correct
# copy (love-is-not-a-metric-space, 3 of 39, 2026-09-11). Per outlet, from outlets.yaml's
# `footnote_marker`, never global: a bracketed number in prose on any other outlet is
# words. Only a marker glued to the text before it counts \u2014 "see [2] below" survives, and
# so does each "[1] \u2026" that opens a line of the Notes.
FOOTNOTE_MARKERS = {
    'bracket': re.compile(r'(?<=\S)\[\d+\]'),
}


def _norm_text(t):
    t = t.replace('\u2019', "'").replace('\u2018', "'")
    t = t.replace('\u201c', '"').replace('\u201d', '"')
    t = t.replace('\u2014', '-').replace('\u2013', '-').replace('\u2026', '...')
    t = re.sub(r'<[^>]+>', ' ', t)
    t = html_mod.unescape(t)
    t = re.sub(r'\s+', ' ', t)
    # Stripping every tag to a space leaves a space wherever inline formatting ended
    # mid-sentence: `<strong>…arrived</strong>, by cuts` becomes "arrived , by cuts",
    # and the paragraph then matches nothing. That is the checker manufacturing its own
    # drift — it reported 19 false stale paragraphs on a piece substack_verify had just
    # confirmed identical block for block (2026-09-10). Close the gap the tags opened.
    t = re.sub(r'\s+([,.;:!?%)\]}])', r'\1', t)
    t = re.sub(r'([(\[{])\s+', r'\1', t)
    t = re.sub(r"\s+('s|'t|'re|'ve|'ll|'d|'m)\b", r'\1', t)
    # A hyphen joining two words loses to the same tag-stripping: `belief-<em>in</em>`
    # renders as "belief- in". An em-dash is distinguishable because it carries a space on
    # BOTH sides, so only close the word-hyphen-word case.
    t = re.sub(r'(\w)-\s+(\w)', r'\1-\2', t)
    return t.strip()


def publishable_body(piece_dir):
    """The part of draft.md a reader gets: below the first `---`, internal notes stripped."""
    path = os.path.join(piece_dir, 'draft.md')
    if not os.path.exists(path):
        return None
    src = open(path, encoding='utf-8').read()
    parts = src.split('\n---\n', 1)
    body = parts[1] if len(parts) > 1 else src
    body = re.sub(r'<!--.*?-->', ' ', body, flags=re.S)     # HTML comments
    body = re.sub(r'\u2020[^\n]*', '', body)                # dagger notes
    return body


def content_drift(piece_dir, page_html, canonical_outlet=False, footnote_marker=None):
    """Does the live page carry the desk's paragraphs?

    Deliberately a PRESENCE check, not an equality one, and the report says so. The
    outlets render the same source through different templates — wrappers, class names
    and whitespace differ by design — so comparing whole documents would report drift
    on every piece forever, which is the fastest way to make a check ignored.

    What it can prove: every paragraph the desk holds is on the page a reader gets. That
    catches the failure that matters — a stale build serving an old version, or a piece
    silently truncated — because a changed sentence is a paragraph that is no longer there.

    What it cannot prove: ordering, or that the page carries nothing EXTRA. Say so rather
    than implying more.
    """
    # Use the SAME renderer the converter and substack_verify use, rather than a second
    # markdown-to-text written for this check (a second implementation is a second set
    # of bugs; the hand-rolled one had several, 2026-09-10).
    try:
        want = [n for n in (_norm_text(t) for t in _render_reader(piece_dir)[0]) if len(n) >= 40]
    except Exception:                                          # noqa: BLE001
        return None
    # render_reader prepends "Originally published at <canonical>" whenever a piece has
    # a canonical URL (md_to_substack.py) — correct for a SYNDICATED copy, and correctly
    # absent from the canonical outlet itself. Expecting it there reported the original
    # site as stale for not calling itself a copy (2026-09-11).
    if canonical_outlet:
        want = [w for w in want if not w.startswith('Originally published at ')]
    if not want:
        return None
    have = _norm_text(_strip_page_furniture(page_html))
    # Dropped on BOTH sides, so the desk writing "x[1]" in prose cannot read as stale here.
    # Before whitespace removal, which would glue every marker to the text before it.
    if footnote_marker:
        rx = FOOTNOTE_MARKERS[footnote_marker]
        have = rx.sub('', have)
        want = [rx.sub('', w) for w in want]
    # Compare with ALL whitespace removed. Every remaining false lead on 2026-09-11 was a
    # whitespace artifact of one kind or another — a line break inside a block joined with
    # no space ("sent Me.I came"), an italic word before a suffix split by tag-stripping
    # (*that*s -> "that s") — the same class as the space-before-comma and word-hyphen
    # patches above, which this subsumes. A reader cannot see a whitespace-only difference,
    # and any change to WORDS still changes the non-space characters, so nothing that
    # matters is lost.
    have_ns = re.sub(r'\s+', '', have)
    missing = [w for w in want if re.sub(r'\s+', '', w) not in have_ns]
    return {'paragraphs': len(want), 'missing': missing}


# ------------------------------------------------------------------ tags
#
# WHY (2026-09-15, twice in one day). A tag added to a live text reaches no outlet by itself:
# the store record and the Substack post are separate writes, and nothing went back. So
# *Love Is Not a Metric Space* carried `modeling-limits` on the desk for four days while its
# blog card showed no tags and its Substack post carried none at all — and a talk went live
# with no tags anywhere, because the desk could not yet express them. Both were found by a
# person looking at a page. Every other check here passed, because none of them looked at
# tags. This is the comparison that does, on every run, without being remembered.

def tag_drift(want, now):
    """-> (missing, extra), case-insensitive. ORDER IS NOT DRIFT: every writer emits a
    publication's vocabulary order, so a live list in another order means a reordered
    vocabulary, not a stale post."""
    lw, wl = {x.lower() for x in now}, {x.lower() for x in want}
    return [x for x in want if x.lower() not in lw], [x for x in now if x.lower() not in wl]


def desk_tag_labels(text_dir, pubs, vocabs):
    """-> ({tag: label} in vocabulary order, problem) for one desk text, piece or talk."""
    import publications as pb
    import tags as tagvocab
    man = pb.read_manifest(text_dir) or {}
    names, problem = tagvocab.tags_of(man)
    if problem:
        return None, problem
    if not names:
        return {}, None
    pid, pprobs = pb.of_piece(man, pubs)
    if vocabs.per_publication and not pid:
        return None, '; '.join(pprobs) or 'names no publication'
    vocab, vprobs = vocabs.get(pid)
    if vprobs or vocab is None:
        return None, 'its tag vocabulary is missing or malformed'
    unknown = [t for t in names if t not in vocab]
    if unknown:
        return None, f"not in its vocabulary: {', '.join(unknown)}"
    return {t: vocab[t]['label'] for t in tagvocab.ordered(names, vocab)}, None


def store_tag_drift(index, root, pubs, vocabs, outlets=None):
    """Every store index entry the desk holds, compared tag for tag and label for label.

    The index is what every store-backed site reads a text's tags from, so this one
    comparison covers all of them, pieces and talks alike, from one fetch. A label renamed in
    the vocabulary is drift too: the ids still match and the reader still sees the old word.
    Pure — the index is passed in. `outlets` limits it to entries published to those.
    -> (checked, findings); a finding is {ref, missing, extra, relabeled} or {ref, problem}."""
    import corpus
    checked, findings = 0, []
    for e in (index or {}).get('pieces') or []:
        if outlets and not set(e.get('outlets') or []) & set(outlets):
            continue
        kind = e.get('kind', 'piece')
        d = corpus.find(root, str(e.get('slug') or ''), prefer=kind)
        if not d or corpus.kind_of(d) != kind:
            continue                       # a slug the desk does not hold is the reverse check's
        ref = corpus.rel(root, d)
        want, problem = desk_tag_labels(d, pubs, vocabs)
        checked += 1
        if problem:
            findings.append({'ref': ref, 'problem': problem})
            continue
        have = {t['tag']: t.get('label') for t in (e.get('tags') or [])
                if isinstance(t, dict) and t.get('tag')}
        missing = [t for t in want if t not in have]
        extra = [t for t in have if t not in want]
        relabeled = [(t, have[t], want[t]) for t in want if t in have and have[t] != want[t]]
        if missing or extra or relabeled:
            findings.append({'ref': ref, 'missing': missing, 'extra': extra, 'relabeled': relabeled})
    return checked, findings


def substack_tag_drift(pieces, fetch_tags=None):
    """Every LIVE piece on a Substack outlet: its post's tags against the desk's.

    Through the same `plan` and reader `substack_tags --verify` uses, so the audit and the tool
    cannot disagree about what a post should carry — including a tag the vocabulary keeps off
    Substack (`substack: false`), which is not missing there. `fetch_tags(host, reader_url,
    url_key) -> [names]` is injectable.

    `pieces` is [(ref, dir, reader_url)] — posts the forward check has JUST FOUND LIVE, at the
    address it found them. Being published is not being on Substack: a piece goes canonical
    first, and its Substack copy can be scheduled or missing, each already its own finding.
    Reading `published_at` as "live here" reported two posts as uncomparable that were simply
    not this check's to read (2026-09-16, the first run).
    -> (checked, findings, unreachable)."""
    import publications as pb
    import substack_tags as st
    fetch_tags = fetch_tags or st.public_tags
    jobs, findings = [], []
    for ref, d, reader_url in pieces:
        try:
            p = st.plan(d, clear=True)            # clear: an untagged post is compared, not refused
        except pb.Refused as ex:
            findings.append({'ref': ref, 'problem': str(ex)})
            continue
        jobs.append((ref, {**p, 'reader_url': reader_url or p['reader_url']}))

    def one(job):
        ref, p = job
        try:
            return ref, p, fetch_tags(p['host'], p['reader_url'], p['url_key']), None
        except pb.Refused as ex:
            return ref, p, None, str(ex)
        except Exception as ex:                    # noqa: BLE001 — not checked is not fine
            return ref, p, None, ex

    unreachable = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for ref, p, now, err in ex.map(one, jobs):
            if isinstance(err, str):
                findings.append({'ref': ref, 'problem': err})
            elif err is not None:
                unreachable.append(ref)
            else:
                missing, extra = tag_drift(p['labels'], now)
                if missing or extra:
                    findings.append({'ref': ref, 'missing': missing, 'extra': extra})
    return len(jobs), findings, unreachable


def _tag_line(where, f):
    if f.get('problem'):
        return f"  TAGS  {f['ref']} on {where}: could not be compared — {f['problem']}"
    bits = []
    if f.get('missing'):
        bits.append('missing ' + ', '.join(f['missing']))
    if f.get('extra'):
        bits.append('extra ' + ', '.join(f['extra']))
    for t, old, new in f.get('relabeled') or []:
        bits.append(f'{t} reads {old!r}, the vocabulary says {new!r}')
    return f"  TAGS  {f['ref']} on {where}: " + '; '.join(bits)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--config', default='publishing/outlets.yaml')
    ap.add_argument('--pieces', default='pieces')
    ap.add_argument('--outlet', default=None, help='audit only this outlet')
    ap.add_argument('--no-reverse', action='store_true')
    ap.add_argument('--content', action='store_true',
                    help='also compare the WORDS on each outlet against the desk, not just '
                         'that the URL resolves (a 200 proves a page exists, not that it is '
                         'the right one)')
    ap.add_argument('--quiet', action='store_true', help='only print problems')
    ap.add_argument('--no-tags', action='store_true',
                    help='skip comparing each text\'s tags on the store and on Substack to the desk')
    ap.add_argument('--store', default=None,
                    help='the content store config (default: store.yaml beside --config); '
                         'a desk with none has no store tags to compare')
    a = ap.parse_args()

    if not os.path.exists(a.config):
        die(1, f"no outlet config at {a.config} — the instance defines its outlets, not the framework")
    with open(a.config) as f:
        cfg = yaml.safe_load(f) or {}
    outlets = cfg.get('outlets') or {}
    if not outlets:
        die(1, f"{a.config} defines no outlets")
    legacy_outlet = cfg.get('legacy_outlet')
    if a.outlet:
        if a.outlet not in outlets:
            die(1, f"unknown outlet {a.outlet!r}; config has {', '.join(outlets)}")
        outlets = {a.outlet: outlets[a.outlet]}
    for oname, oc in outlets.items():
        fm = oc.get('footnote_marker')
        if fm is not None and fm not in FOOTNOTE_MARKERS:
            die(1, f"outlet {oname!r}: unknown footnote_marker {fm!r}; "
                   f"known: {', '.join(FOOTNOTE_MARKERS)}")

    pieces = load_pieces(a.pieces, legacy_outlet)
    if not pieces:
        die(1, f"no publish.yaml under {a.pieces}")

    # ---- forward: declared + published -> must resolve -----------------------
    jobs, unrecorded, scheduled_later, unscheduled = [], [], [], []
    for pc in pieces:
        for oname in pc['declared']:
            if oname not in outlets:
                continue
            if not pc['published']:
                continue
            url = slug_of(pc['manifest'], pc['name'], outlets[oname])
            if url:
                jobs.append((pc, oname, url))
            elif outlets[oname].get('derive') is False:
                # A piece can be live on its canonical and not yet on its syndicated outlets:
                # the canonical publishes immediately (a store publish has no scheduler) while
                # Substack and LinkedIn are scheduled on their own platforms for a later moment.
                # That is the ordinary shape of a scheduled publication, not a hole in the record
                # — so `syndication_at` in the future reads as PENDING, and the day it passes the
                # same piece reads as UNRECORDED again. (The pattern, 2026-09-11: canonical first,
                # the rest on each platform's own scheduler.)
                st, when, how = schedule_state(os.path.join(a.pieces, pc['name']), oname,
                                               outlets[oname])
                if st == 'scheduled':
                    scheduled_later.append((pc['name'], oname, when, how))
                elif st == 'unscheduled':
                    unscheduled.append((pc['name'], oname, when))
                else:
                    unrecorded.append((pc['name'], oname, outlets[oname].get('manifest_url_key')))

    results, unreachable, previews = [], 0, []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for (pc, oname, url), (status, body, final) in zip(
                jobs, ex.map(lambda j: fetch(j[2]), jobs)):
            ok = status == 200 and not landed_on_not_found(final, outlets[oname])
            if ok and pending_until(os.path.join(a.pieces, pc['name']), outlets[oname]):
                # A WAITING outlet whose moment is still ahead cannot be carrying the piece yet,
                # so a 200 there is not the post. Substack answers a scheduled post's own
                # address with a teaser — full og: tags, no body — and this check counted it as
                # present; the tag gate then asked for tags on a post the API says does not
                # exist (2026-09-16, a post scheduled for 09-18). Judged by its schedule instead,
                # through the branch below, which reports it scheduled or NOT SCHEDULED.
                ok = False
            # Not there YET is not the same as missing. A piece goes canonical-first — the
            # canonical has no scheduler, the syndicated outlets have their own — so between
            # the two moments the syndicated copy is absent BY DESIGN. Excused only for an
            # outlet that is not this piece's canonical, and only while `syndication_at` is
            # still ahead: the day it passes, the same absence is a finding again.
            later = None
            if not ok:
                canon = str(pc['manifest'].get('canonical') or '')
                obase = str(outlets[oname].get('reader_base') or '').rstrip('/')
                is_canonical_outlet = bool(canon and obase and canon.startswith(obase))
                if not is_canonical_outlet:
                    st2, later, how2 = schedule_state(os.path.join(a.pieces, pc['name']), oname,
                                                      outlets[oname])
                    if st2 == 'scheduled':
                        scheduled_later.append((pc['name'], oname, later, how2))
                    elif st2 == 'unscheduled':
                        # Absent because the moment has not come — so not 'missing' — but with
                        # nothing recording that a scheduler was told, which is its own finding
                        # below rather than a copy counted as gone.
                        unscheduled.append((pc['name'], oname, later))
            row = {'piece': pc['name'], 'outlet': oname, 'url': url, 'scheduled_for': later,
                   'status': status, 'ok': ok,
                   'redirected': final.rstrip('/') != url.split('?')[0].rstrip('/'),
                   'final': final}
            if a.content and ok and body:
                canon = str(pc['manifest'].get('canonical') or '')
                base = str(outlets[oname].get('reader_base') or '').rstrip('/')
                row['content'] = content_drift(os.path.join(a.pieces, pc['name']), body,
                                               canonical_outlet=bool(canon and base and canon.startswith(base)),
                                               footnote_marker=outlets[oname].get('footnote_marker'))
            results.append(row)
            if status is None:
                unreachable += 1
            if ok and body and outlets[oname].get('og_image'):
                previews.append((row, body))
        # The preview images, fetched in parallel after the pages: one per checked page.
        for (row, _b), problem in zip(previews, ex.map(
                lambda rb: preview_problem(rb[1], rb[0]['final'] or rb[0]['url']), previews)):
            row['preview'] = problem

    # ---- unlisted: live, and nothing links to it -----------------------------
    # A piece can answer 200 at its own URL, sit in the sitemap, and still be unreachable by
    # a reader, because the page that lists the pieces is built from something else. On
    # alignmentfellowship that is `content/library.json` in the site repo, a curated reading
    # order a store publish never touches: five pieces were live and unlisted for days, and
    # every check here passed them, because presence was only ever asked of the piece's own
    # URL. The forward check says the door exists; this asks whether anything points at it.
    unlisted = []
    if not a.no_reverse:
        for oname, oc in outlets.items():
            page = oc.get('index_page')
            if not page:
                continue
            status, body, _f = fetch(page + ('&' if '?' in page else '?') + 'cb=audit', timeout=25)
            if status != 200 or not body:
                unlisted.append((None, oname, f'index page {page} answered {status}'))
                continue
            hrefs = ' '.join(re.findall(r'href="([^"]+)"', body))
            for r in results:
                if r['outlet'] != oname or not r.get('ok'):
                    continue
                slug = (r['url'] or '').split('?')[0].rstrip('/').split('/')[-1]
                if slug and f'/{slug}' not in hrefs:
                    unlisted.append((r['piece'], oname, slug))

    # ---- reverse: what each outlet lists that the desk does not claim --------
    reverse = {}
    if not a.no_reverse:
        for oname, oc in outlets.items():
            sm = oc.get('sitemap')
            if not sm:
                continue
            status, body, _f = fetch(sm, timeout=25)
            if status != 200:
                reverse[oname] = {'error': f'sitemap unreachable (HTTP {status})'}
                continue
            base = oc.get('reader_base', '').rstrip('/')
            live = set()
            for loc in re.findall(r'<loc>([^<]+)</loc>', body):
                u = loc.rstrip('/')
                if not base or not u.startswith(base) or u == base:
                    continue
                rest = u[len(base):].strip('/')
                # A piece lives at <reader_base>/<slug>, one segment deep. Anything deeper is
                # the site's own index — /blog/tag/<tag>, and whatever it adds next — and calling
                # those unknown pieces is the audit inventing a problem. Found the day the first
                # MuffinLabs tags shipped, when three tag pages read as three missing pieces.
                if '/' in rest:
                    continue
                live.add(rest)
            reverse[oname] = {'live': live, 'unknown': sorted(live - known_on(pieces, oc))}

    # ---- tags: the desk's, against what each outlet actually carries ---------
    tag_store, tag_sub = None, None            # (checked, findings, unreachable) or None
    if not a.no_tags:
        import publications as pb
        import tags as tagvocab
        import substack_account as sa
        root = pb.instance_root(os.path.dirname(os.path.abspath(a.pieces)))
        pubs, reg_problems = pb.load(root)
        if reg_problems:
            die(1, 'the publication registry is malformed: ' + '; '.join(reg_problems))
        vocabs = tagvocab.Vocabularies(root, None, pubs)
        store_cfg = a.store or os.path.join(os.path.dirname(a.config) or '.', 'store.yaml')
        if os.path.exists(store_cfg):
            with open(store_cfg) as f:
                base = ((yaml.safe_load(f) or {}).get('store') or {}).get('base_url')
            if base:
                status, body, _f = fetch(base.rstrip('/') + '/index.json', timeout=25)
                if status == 200 and body:
                    try:
                        n, found = store_tag_drift(json.loads(body), root, pubs, vocabs,
                                                   outlets=list(outlets) if a.outlet else None)
                        tag_store = (n, found, False)
                    except ValueError:
                        tag_store = (0, [], f'index.json did not parse')
                else:
                    tag_store = (0, [], f'index.json answered HTTP {status}')
        subs = {n for n, oc in outlets.items() if sa.is_substack(oc)}
        # Only posts the forward check just found LIVE, at the address it found them.
        on_sub = [(r['piece'], os.path.join(a.pieces, r['piece']), r['final'] or r['url'])
                  for r in results if r['outlet'] in subs and r['ok']]
        if on_sub:
            n, found, unr = substack_tag_drift(on_sub)
            tag_sub = (n, found, unr)

    # ---- report --------------------------------------------------------------
    stale = [r for r in results
             if r.get('content') and r['content']['missing']]
    no_preview = [r for r in results if r.get('preview')]
    # A copy whose own platform has it scheduled is absent but not missing — reported on its
    # own line above, and counted apart so the summary stays literally true.
    not_yet = [r for r in results if not r['ok'] and r.get('scheduled_for')]
    missing = [r for r in results
               if not r['ok'] and r['status'] is not None and not r.get('scheduled_for')]
    unreach = [r for r in results if r['status'] is None]
    pending = [pc for pc in pieces if pc['declared'] and not pc['published']]
    undeclared = []
    for oname, info in reverse.items():
        for slug in info.get('unknown', []):
            undeclared.append((oname, slug))
    # a piece live on an outlet its manifest does not name
    lying = []
    for pc in pieces:
        # A pre-outlets manifest is not lying, it predates the convention. Only a
        # piece that HAS declared a list can be wrong about what is in it.
        if not isinstance(pc['manifest'].get('outlets'), list):
            continue
        for oname, oc in outlets.items():
            if oname in pc['declared']:
                continue
            key = oc.get('manifest_url_key')
            if key and pc['manifest'].get(key):
                lying.append((pc['name'], oname))

    W = max([len(r['piece']) for r in results] + [12])
    if not a.quiet:
        print(f"auditing {len(pieces)} piece(s) across {len(outlets)} outlet(s)  [cache-busted]")
        for r in sorted(results, key=lambda x: (x['piece'], x['outlet'])):
            # 'MISS' on a copy its own platform has scheduled would read as a fault; it is
            # an absence with a date on it.
            mark = 'ok  ' if r['ok'] else ('sched' if r.get('scheduled_for') else 'MISS')
            c = r.get('content')
            extra = ''
            if c is not None:
                n = c['paragraphs']
                extra = (f"  {n}/{n} paragraphs" if not c['missing']
                         else f"  STALE {n - len(c['missing'])}/{n} paragraphs")
            if not a.quiet or not r['ok']:
                print(f"  {mark}  {r['piece']:<{W}}  {r['outlet']:<20} HTTP {r['status']}{extra}")
    else:
        for r in missing + unreach:
            print(f"  MISS  {r['piece']:<{W}}  {r['outlet']:<20} HTTP {r['status']}  {r['url']}")

    legacy_n = sum(1 for pc in pieces if pc['legacy'])
    print()
    print(f"{len(results) - len(missing) - len(unreach) - len(not_yet)} present, "
          f"{len(not_yet)} scheduled, {len(missing)} missing, "
          f"{len(unreach)} unreachable across {len(outlets)} outlet(s)")
    if pending:
        print(f"  {len(pending)} piece(s) declare an outlet but are not published yet "
              f"(not checked): {', '.join(p['name'] for p in pending)}")
    if legacy_n:
        print(f"  {legacy_n} piece(s) still opt in with legacy `site: true` rather than `outlets:` "
              f"— counted as {legacy_outlet!r}")
    for oname, info in reverse.items():
        if 'error' in info:
            print(f"  reverse {oname}: {info['error']}")
        elif info['unknown']:
            print(f"  reverse {oname}: {len(info['unknown'])} live URL(s) the desk does not know: "
                  f"{', '.join(info['unknown'][:8])}")
        else:
            print(f"  reverse {oname}: all {len(info['live'])} live URL(s) are known to the desk")
    for name, oname in lying:
        print(f"  UNDECLARED  {name} records a {oname} URL but does not list {oname} in `outlets:`")
    for name, oname, when, how in scheduled_later:
        print(f"  scheduled   {name} is not on {oname} yet — {oname}'s own scheduler has it for "
              f"{when} ({how})")
    for name, oname, when in unscheduled:
        print(f"  NOT SCHEDULED  {name} is due on {oname} at {when}, and nothing records a "
              f"schedule set there — intent is not a scheduler")
    for name, oname, key in unrecorded:
        print(f"  UNRECORDED  {name} is published and declares {oname}, whose URLs cannot be "
              f"derived — record it under `{key}` or the copy is unaudited")

    if unlisted:
        for piece, oname, detail in unlisted:
            if piece is None:
                print(f"  UNLISTED  {oname}: {detail}")
            else:
                print(f"  UNLISTED  {piece} is live on {oname} and nothing on its index page "
                      f"links to it — a reader browsing the site cannot reach it")

    if previews:
        print(f"  preview: {len(previews) - len(no_preview)}/{len(previews)} page(s) have a link "
              f"preview that resolves to an image")
        for r in no_preview:
            print(f"  PREVIEW  {r['piece']} on {r['outlet']}: {r['preview']}")

    tag_drifted = []
    if tag_store is not None:
        n, found, err = tag_store
        if err:
            print(f"  tags: the store could not be read — {err}; not checked is not fine")
        else:
            print(f"  tags: {n - len(found)}/{n} text(s) carry the desk's tags on the store index")
        for f in found:
            print(_tag_line('the store', f))
        tag_drifted += found
    if tag_sub is not None:
        n, found, unr = tag_sub
        print(f"  tags: {n - len([f for f in found if not f.get('problem')]) - len(unr)}/{n} "
              f"Substack post(s) carry the desk's tags")
        for f in found:
            print(_tag_line('Substack', f))
        for ref in unr:
            print(f"  TAGS  {ref} on Substack: its post could not be read")
        tag_drifted += found

    if a.content:
        checked = [r for r in results if r.get('content') is not None]
        print(f"  content: {len(checked) - len(stale)}/{len(checked)} page(s) carry every "
              f"paragraph the desk holds"
              + (" — presence, not ordering; a page may still carry extra" if checked else ""))
        for r in stale:
            c = r['content']
            print(f"  STALE  {r['piece']} on {r['outlet']}: {len(c['missing'])} of "
                  f"{c['paragraphs']} paragraph(s) are not on the page")
            print(f"         first: {c['missing'][0][:100]}")
            print(f"         {r['url']}")

    if stale:
        print("\nFAILED: an outlet resolves but serves text the desk does not hold. "
              "A 200 proves a page exists, not that it is the right one.")
        print("  On SUBSTACK, `substack_verify --fresh` is the authority and this is the "
              "coarser instrument: it compares rendered page text across two templates, so "
              "where the two disagree, believe substack_verify and treat the finding here as "
              "a lead. On every other outlet this is the only check there is.")
        sys.exit(3)
    if missing:
        print("\nFAILED: a piece declares an outlet it is not on.")
        sys.exit(3)
    if no_preview:
        print("\nFAILED: a page is live but its link preview is broken — a shared link shows "
              "no image. A store publish never touches the site repo, where previews are made.")
        sys.exit(3)
    if tag_drifted:
        print("\nFAILED: an outlet carries tags the desk does not. A tag added to a live text "
              "reaches no outlet by itself —\n  the store record and the Substack post are separate "
              "writes. Re-publish the record (md_to_site → bundle_pieces → store_publish, or "
              "talk_bundle for a talk)\n  and the post (substack_tags --live).")
        sys.exit(3)
    if undeclared or lying:
        print("\nFAILED: an outlet carries something the manifests do not declare.")
        sys.exit(3)
    if unscheduled:
        print("\nFAILED: a piece is due on an outlet and nothing records a schedule set there.\n"
              "  A native schedule lives on the platform, so the desk cannot see it — only the\n"
              "  record can tell 'scheduled' from 'forgotten' before the moment passes.\n"
              "  Set it, then `schedule.py record <piece> --outlet <o> --where … --approved …`.")
        sys.exit(3)
    if unrecorded:
        # Not 'missing' — the copy may well be up. But nothing can check it, and a check
        # that silently skips is the blind spot this audit was written to close.
        print("\nFAILED: a published piece declares an outlet whose address was never recorded.")
        sys.exit(3)
    if results and len(unreach) == len(results):
        print("\nFAILED: nothing could be reached — that is not a pass.")
        sys.exit(2)
    if unreach:
        print("\nFAILED: some outlets could not be reached; 'not checked' is not 'fine'.")
        sys.exit(2)
    if (tag_store and tag_store[2]) or (tag_sub and tag_sub[2]):
        print("\nFAILED: tags could not be compared everywhere; 'not checked' is not 'fine'.")
        sys.exit(2)
    print("\nevery published piece is on every outlet it declares.")
    sys.exit(0)


if __name__ == '__main__':
    main()
