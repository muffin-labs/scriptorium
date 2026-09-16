#!/usr/bin/env python3
"""
md_to_substack.py — turn a piece's draft.md + publish.yaml into a self-contained
JS snippet that composes the whole post in an OPEN Substack composer:

  1. sets Title + Subtitle,
  2. pastes the whole formatted body in one synthetic ProseMirror paste
     (paragraphs, headings, blockquote, dividers, lists, bold/italic/links, and
     images inlined as data: URIs — Substack uploads them to its CDN), and
  3. defines window.__sbInsertFootnotes() which converts the body's [[FNn]]
     markers into NATIVE Substack footnotes via the editor's own Tiptap
     `insertFootnote` command, filling each note's (rich) content.

Usage:  python3 md_to_substack.py <piece-dir> [out.js]

The caller runs the emitted JS in two steps against a fresh, logged-in composer:
  A) run the whole snippet         -> title/subtitle set, body pasted
  B) run await window.__sbInsertFootnotes()  -> markers become native footnotes
Both steps first check the page is signed in as the piece's Substack account
(substack_account.py, the guard) and return {"refused": "account: …"} untouched if not.
(The two-step split is required: ProseMirror applies the paste asynchronously,
so the markers aren't in the doc model until the next tick / next call.)

Never publishes. Leaves a DRAFT for a human to review and publish.

draft.md conventions:
  - Front-matter/scaffolding = everything up to & including the FIRST `---`; dropped.
  - HTML comments stripped anywhere.
  - Blank-line blocks -> <p>; `## ` -> <h2>, `### ` -> <h3>; lone `---` -> <hr>.
  - Inline: **bold**, *italic*, [t](u); ![alt](path) -> inlined <img>.
  - Footnotes: `text[^n]` ref -> [[FNn]] marker; a block starting `[^n]: ...`
    is a footnote definition (collected, removed from the body).

INTERNAL EDITORIAL NOTES (never publish):
  - Anything inside an HTML comment `<!-- ... -->` is stripped (anywhere).
  - Inside a footnote, anything after a dagger `†` is an internal note (verify:/
    todo:/attribute:) and is dropped. Put "Verify X before print" style notes
    after a `†` so they auto-strip at publish.
  - Safety net: a trailing `Verify ….` sentence in a footnote is also dropped.
  - GUARD 1 (malformed note): if a footnote still contains "verify" AFTER
    cleaning, exit non-zero unless --allow-verify. Catches a note someone forgot
    to put behind a dagger.
  - GUARD 2 (the real one): a `†` note whose text looks like an unverified-claim
    marker (verify/todo/tk/check/confirm/pin/source/cite) exits non-zero unless
    --allow-unverified. This is checked against the text that was REMOVED.
    Guard 1 alone was structurally inert: the documented convention is to put
    verify notes behind a `†`, which strips them before Guard 1 ever looks — so a
    well-formed note always passed. A draft carrying 17 of them converted clean
    (2026-08-29). A `†` marker means the claim is UNVERIFIED; publishing it
    silently is exactly the failure these guards exist to prevent.
  - GUARD 3 (header): an empty `title` or `subtitle` in publish.yaml exits 6, no
    override. The subtitle is the second line of every archive card and the
    social preview; the composer accepts an empty one silently, and a post went
    live without one on 2026-08-05 and sat that way for a month before anyone
    looked (found 2026-09-03). A title/subtitle whose comment says PROPOSED /
    working / not settled is printed as a warning, since a private draft is
    where the author reviews it.
"""
import sys, os, re, json, base64, mimetypes
from html.parser import HTMLParser

def read_manifest(path):
    """Flat key: value, plus ONE level of nesting so `images:` can carry a map of
    local-path -> already-uploaded Substack URL. Anything deeper is ignored."""
    m, block = {}, None
    if os.path.exists(path):
        for line in open(path):
            line = line.split('#', 1)[0].rstrip()
            if not line.strip():
                continue
            if line.startswith((' ', '\t')):                          # nested entry
                if block is not None and ':' in line:
                    k, v = line.strip().split(':', 1)
                    m[block][k.strip()] = v.strip()
                continue
            if ':' in line:
                k, v = line.split(':', 1)
                k, v = k.strip(), v.strip()
                if v == '':                                          # opens a nested block
                    block = k
                    m[k] = {}
                else:
                    block = None
                    m[k] = v
    return m

UNSETTLED = re.compile(r'\b(?:proposed|proposal|not (?:yet )?settled|unsettled|placeholder|tbd|tk|working title)\b', re.I)
SETTLED = re.compile(r'(?<!not )(?<!not yet )(?<!un)settled\b', re.I)

# A caption says what the image REPRESENTS in the piece. Provenance ("generated", "not a
# photograph") is recorded in publish.yaml beside `cover:`, and a disclaimer ("not a likeness
# of") is a warning label, not a caption. Measured 2026-09-10: a hero was captioned "... An
# imagined scene, not a likeness of ...", because the rule said only that a caption "must not
# imply a photograph". Rule: framework/docs/ALT-TEXT.md, Captions.
CAPTION_PROVENANCE = re.compile(
    r"\b(?:ai[- ]generated|generated (?:image|by|with)|not a (?:photo(?:graph)?|likeness|portrait)|"
    r"imagined scene|artist'?s (?:impression|rendering)|illustration of|stock (?:photo|image)|"
    r"(?:photo(?:graph)?|image) (?:by|credit)|courtesy of)\b", re.I)

def _strip_comment(v):
    return re.split(r'\s+#', v, maxsplit=1)[0].strip() if isinstance(v, str) else ''

def _hero_alt(piece_dir, cover):
    """The alt text the draft gives its hero image, or ''."""
    fp = os.path.join(piece_dir, 'draft.md')
    if not cover or not os.path.exists(fp):
        return ''
    m = re.search(r'!\[([^\]]*)\]\(' + re.escape(cover) + r'\)', open(fp, encoding='utf-8').read())
    return m.group(1) if m else ''

def _shared_run(a, b):
    """The longest run of consecutive words two strings share, normalized."""
    norm = lambda t: re.sub(r"[^a-z0-9 ]", '', re.sub(r'\s+', ' ', t.lower().replace('\u2019', "'").replace("'", ''))).split()
    wa, hay, best = norm(a), ' ' + ' '.join(norm(b)) + ' ', ''
    for i in range(len(wa)):
        for j in range(len(wa), i, -1):
            run = ' '.join(wa[i:j])
            if len(run) > len(best) and (' ' + run + ' ') in hay:
                best = run
                break
    return best

def manifest_gate(piece_dir):
    """Is the reader-facing header of this post complete?  Returns (errors, warnings).

    An empty `title` or `subtitle` is an ERROR and the compose refuses.  The subtitle is
    not decoration on Substack: it is the second line of every archive card, the homepage
    listing, the social preview and the email header, and the composer accepts an empty
    one without a murmur.  Measured 2026-09-03: a post had been live since 2026-08-05 with
    no subtitle at all, and nothing in the pipeline had ever looked -- the converter read
    `man.get('subtitle', '')` and passed the empty string straight into the editor.

    A `title`/`subtitle` whose trailing comment says it is still PROPOSED / a working title /
    not yet settled is a WARNING, not a refusal: a private draft is exactly where the author
    reviews it, and the note is the desk's own record that they have not.  It is printed so
    the person composing sees it, because the field the comment is about is the one line of
    the post the author is least likely to re-read in the editor."""
    path = os.path.join(piece_dir, 'publish.yaml')
    if not os.path.exists(path):
        return ([f'no publish.yaml in {piece_dir}'], [])
    man = read_manifest(path)
    errors, warnings = [], []
    # A PAGE HAS NO SUBTITLE FIELD. Measured 2026-09-10: a custom page opens in the same
    # composer as a post with Title only — no `Add a subtitle…` textarea exists — so a page
    # cannot have the thing this gate refuses without. Requiring one here refused a compose
    # that was correct, which is the worst kind of gate: it teaches you to reach for an
    # override. The subtitle rule stands for posts, where it is second line of every archive
    # card and social preview; a page is in none of those.
    required = ('title',) if man.get('substack_type') == 'page' else ('title', 'subtitle')
    for k in required:
        v = man.get(k, '')
        if not isinstance(v, str) or not v.strip():
            errors.append(f'publish.yaml has no {k}')
    for line in open(path):
        key = line.split(':', 1)[0].strip()
        if key in ('title', 'subtitle') and '#' in line:
            note = line.split('#', 1)[1].strip()
            # "settled 2026-09-02 (replaced the working title X)" is a settled line whose
            # history mentions the old state; the settlement wins over the mention.
            if UNSETTLED.search(note) and not (SETTLED.search(note)
                                                and not re.search(r'not (?:yet )?settled|unsettled', note, re.I)):
                warnings.append(f'{key} is marked unsettled: {note[:70]}')
    for line in caption_prose(piece_dir):
        errors.append(f'a caption is written into draft.md under an image ("{line[:60]}"), where it '
                      'publishes as a paragraph -- move it to publish.yaml `captions:` (keyed by the '
                      "image's local path) or `cover_caption:`, and delete the line "
                      '(framework/docs/ALT-TEXT.md, Captions)')
    # The caption: a WARNING, never a refusal -- the wording is the author's, and a warning is
    # how this gate already treats a header line the author has not signed off.
    cap = _strip_comment(man.get('cover_caption', ''))
    if cap and cap not in ('>', '>-', '|', '|-'):
        if CAPTION_PROVENANCE.search(cap):
            warnings.append(f'cover_caption reads as provenance or a disclaimer, not meaning: "{cap[:70]}" '
                            '-- a caption says what the image represents (framework/docs/ALT-TEXT.md, Captions)')
        run = _shared_run(cap, _hero_alt(piece_dir, _strip_comment(man.get('cover', ''))))
        if len(run.split()) >= 4:
            warnings.append(f'cover_caption repeats the alt ("{run}") -- the alt describes the image, '
                            'the caption says what it means (framework/docs/ALT-TEXT.md, Captions)')
    return errors, warnings

def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def data_uri(piece_dir, rel):
    fp = os.path.join(piece_dir, rel)
    mime = mimetypes.guess_type(fp)[0] or 'image/png'
    b64 = base64.b64encode(open(fp, 'rb').read()).decode()
    return f'data:{mime};base64,{b64}'

_IMGMAP = {}          # local image path -> already-uploaded Substack URL, per piece

# --- captions -----------------------------------------------------------------
# A caption says what an image MEANS in the piece; the alt says what it shows (ALT-TEXT.md,
# Captions). Captions live in publish.yaml, never in draft.md: `captions:` maps an image's local
# path, as draft.md writes it, to its caption, and the hero may use `cover_caption:` instead.
# Every outlet reads them through caption_for() -- this converter (<figcaption>, which Substack's
# paste turns into the captionedImage's caption node), md_to_site (the bundle's image title and
# hero.caption) and md_to_linkedin (the figure payload) -- so one line in the manifest reaches all
# three. Before this no converter carried a caption at all: a hero's cover_caption never reached a
# recomposed post, and a caption set by hand on a live post was destroyed by the next rebuild
# (found 2026-09-10 on none-but-he-and-i; 2026-09-11 on love-is-not-a-metric-space).
_CAPTIONS, _COVER, _COVER_CAPTION = {}, '', ''
HERO_FILE = re.compile(r'(?:^|/)hero\.[A-Za-z0-9]+$')


def _manifest_line(v):
    """A scalar manifest value, trimmed, without a trailing ` # comment`; '' for a YAML block
    marker (a folded `>-` read as one line is the two characters `>-`, not a caption)."""
    if not isinstance(v, str):
        return ''
    v = re.sub(r'\s+#\s.*$', '', v).strip()
    return '' if v in ('>', '>-', '|', '|-') else v


def _yaml_manifest(piece_dir, fallback):
    """publish.yaml through a real YAML parser when one is installed, else `fallback`.
    read_manifest() keeps a quoted value's quotes, and a caption is exactly the kind of value
    that gets quoted: `'The chart, "quoted".'` arrived with its outer quotes on (2026-09-11)."""
    try:
        import yaml
        with open(os.path.join(piece_dir, 'publish.yaml'), encoding='utf-8') as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else fallback
    except Exception:                                              # noqa: BLE001
        return fallback


def load_captions(man):
    """(captions-by-local-path, cover path, cover_caption) from a publish.yaml mapping."""
    raw = man.get('captions') if isinstance(man.get('captions'), dict) else {}
    caps = {str(k): _manifest_line(v) for k, v in raw.items() if _manifest_line(v)}
    return caps, _manifest_line(man.get('cover', '')), _manifest_line(man.get('cover_caption', ''))


IMAGE_LINE = re.compile(r'!\[[^\]]*\]\([^)\s]+\)')
ITALIC_LINE = re.compile(r'(\*|_)(?!\1)\S.*\S?\1', re.S)


def caption_prose(piece_dir):
    """Every italic-only line sitting directly under an image in draft.md -- a caption written
    into the body. The spec puts captions in publish.yaml; a line under the image publishes as
    an ordinary PARAGRAPH, not a caption, and nothing downstream can tell. For the Love of Dogs
    carried two, live as paragraphs, from 2026-08-05 until 2026-09-11. -> [line, ...]"""
    path = os.path.join(piece_dir, 'draft.md')
    if not os.path.exists(path):
        return []
    raw = open(path, encoding='utf-8').read()
    body = raw.split('\n---\n', 1)[1] if '\n---\n' in raw else raw
    blocks = [' '.join(b.split()) for b in re.split(r'\n\s*\n', body) if b.strip()]
    return [nxt for b, nxt in zip(blocks, blocks[1:])
            if IMAGE_LINE.fullmatch(b) and ITALIC_LINE.fullmatch(nxt)]


def caption_for(path, caps=None, cover=None, cover_caption=None, imgmap=None):
    """The caption for one image, by the path draft.md gives it; '' if it has none.

    `captions:` wins. Otherwise the hero -- the image at `cover:`, or any `hero.*` -- takes
    `cover_caption:`. A remote URL is mapped back to its local path through `images:` first,
    so a live piece whose draft points at the CDN is captioned by the same key."""
    caps = _CAPTIONS if caps is None else caps
    cover = _COVER if cover is None else cover
    cover_caption = _COVER_CAPTION if cover_caption is None else cover_caption
    local = path
    if re.match(r'https?://', path):
        local = {v: k for k, v in ((_IMGMAP if imgmap is None else imgmap) or {}).items()}.get(path, path)
    if caps.get(local):
        return caps[local]
    is_hero = bool(cover) and local == cover or bool(HERO_FILE.search(local))
    return cover_caption if (is_hero and cover_caption) else ''


def img_src(piece_dir, rel):
    # An absolute URL passes straight through. That covers an image hosted anywhere —
    # including one you uploaded in the composer by hand and never stored locally — so a
    # piece is free to keep no local copy at all. The trade is durability: a URL is a
    # pointer at somebody else's server, and nothing in this repo can rebuild the post
    # if it stops resolving.
    if re.match(r'https?://', rel):
        return rel
    """A piece keeps its images on disk under `images/`. Once a piece is live, its
    publish.yaml records the Substack URL each one was uploaded to; we then point at
    THAT rather than re-inlining the bytes, so a recompose reuses the asset already in
    the post instead of uploading a duplicate and orphaning the old one. A piece with
    no recorded URL (a fresh compose) still inlines, which is what uploads it."""
    url = _IMGMAP.get(rel)
    if url:
        return url
    return data_uri(piece_dir, rel)

# House convention censors a quoted swear as f\*\*k — backslash-escaped asterisks, so the
# markdown shows the asterisks rather than opening emphasis. Nothing honoured the escape: the
# backslashes travelled straight into the post (`F\*\*k you, dude.` reached readers of
# `The Knowledge of Good and Evil`), and worse, the bare `**` inside them is a valid bold
# delimiter, so the emphasis regex could pair one censored word with the next and bold the
# sentence between them. Escaped punctuation is therefore parked behind a sentinel BEFORE the
# emphasis passes run and restored after, which is the only ordering that is safe.
_ESCAPES = {'*': '\x00A\x00', '_': '\x00U\x00', '[': '\x00L\x00', ']': '\x00R\x00'}

def inline(text, piece_dir):
    text = esc(text)
    for ch, token in _ESCAPES.items():                               # \* -> sentinel
        text = text.replace('\\' + ch, token)
    text = re.sub(r'\[\^(\w+)\]', r'[[FN\1]]', text)                 # footnote refs -> markers
    # The alt is an ATTRIBUTE, so it also needs `"` escaped: the house rule quotes any text in
    # the image (ALT-TEXT.md), and a bare quote ended the attribute there — a 608-char alt parsed
    # back as 103 chars stopping at *labeled*. m.group(1) is already esc()'d by the first line of
    # this function, so only the quote is added here; esc()ing it again made `&` read `&amp;`.
    # Body text keeps its bare quotes, which is what the reader digests are built on.
    def img(m):
        alt = m.group(1).replace('"', '&quot;')
        cap = caption_for(m.group(2))
        fig = f'<img src="{img_src(piece_dir, m.group(2))}" alt="{alt}">'
        if cap:
            fig += f'<figcaption>{esc(cap)}</figcaption>'
        return f'<figure>{fig}</figure>'
    text = re.sub(r'!\[(.*?)\]\((.*?)\)', img, text)
    # link text may not contain brackets, so a nearby footnote marker ([[FNx]]) can't be
    # swallowed into the link when a link and a marker share a paragraph
    text = re.sub(r'\[([^\[\]]+?)\]\(([^)]+?)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    for ch, token in _ESCAPES.items():                               # sentinel -> literal char
        text = text.replace(token, ch)
    return text

# An editorial note that matches this is an UNVERIFIED-CLAIM marker, not a
# harmless aside. Stripping one silently is the failure this guard exists to
# stop, so it is checked against the text that was REMOVED, not what survived.
# Imperative/bare forms only. PAST TENSE MEANS THE WORK IS DONE: a note reading
# "Checked against the luma page 2026-08-26" is a record of verification, not a request
# for it, and blocking on it would refuse a piece that is already correct (flow, 2026-09-01).
CLEARANCE_RE = re.compile(
    r'\b20\d\d-\d\d-\d\d\b'                                   # an ISO date is scaffold, always
    r'|\b(?:consulted|accessed|retrieved)\s+(?:on\s+)?(?:\d|20\d\d|[A-Z][a-z]+ \d)',   # consulted 7 Sept / on 2026
    re.I)

# A reference to a file INSIDE THE DESK is scaffold that reached the reader, the same class as a
# clearance date: a reader cannot open `projects/being-good/facts.md`, and the path rots when the
# desk moves (Eric, 2026-09-16: "the footnotes should never reference files internal to the
# writing desk"). Found that day on a live post of Both Ends of the Leash, whose Pickle footnote
# cited the desk's facts ledger, and in two MuffinLabs footnotes (`docs/STYLES.md`,
# `assets/figures.py`). Two shapes: a relative path whose first segment is one of the desk's own
# directories, and a desk ledger named by its filename. Matched against text with href/src/alt
# attribute values removed, so a public URL to the same document (a reader CAN follow that) and an
# alt that transcribes a filename shown in a picture both pass.
DESK_PATH_RE = re.compile(
    r'(?<![\w/.:-])(?:projects|books|pieces|talks|styles|references|publishing|framework|assets'
    r'|docs|tools|skills|templates|log|DASHBOARD\.d)/[\w.<>*-]'
    r'|(?<![\w/.-])(?:facts|notes|outline|sources|corrections|brief|pieces|writings|README)\.md\b')


def desk_path_in(html):
    """The first desk-internal reference in reader HTML, or None. Attribute values are not reader
    text (a link's target is a URL; an alt transcribes the picture), so they are removed first."""
    m = DESK_PATH_RE.search(re.sub(r'\s(?:href|src|alt)="[^"]*"', '', html))
    return m.group(0) if m else None


UNVERIFIED_RE = re.compile(
    r'\b(verify|verifying|todo|to-do|tk|fixme|xxx)\b'
    r'|\bcheck\b(?!ed|ing)|\bconfirm\b(?!ed|ing)|\bpin\b(?!ned)'
    r'|\bneeds?\s+(?:a\s+)?(?:check|source|cite|citation|verification)\b', re.I)

def clean_footnote(raw):
    """Drop internal editorial notes from a footnote's text.
    Returns (cleaned_text, removed_note_text)."""
    cleaned = re.sub(r'\s*[†‡].*$', '', raw, flags=re.S)             # dagger-delimited tail
    cleaned = re.sub(r'\s*\bVerify\b[^.]*\.\s*$', '', cleaned, flags=re.S)  # trailing "Verify …."
    cleaned = cleaned.strip()
    removed = ''
    if cleaned != raw.strip():
        m = re.search(r'[†‡](.*)$', raw, flags=re.S)
        removed = (m.group(1) if m else raw.strip()[len(cleaned):]).strip()
    return cleaned, removed

def render_block(b, piece_dir):
    """Render ONE stripped markdown block to its body HTML. Factored out of parse_blocks
    so a caller that has edited a block's source can re-render just that block and check
    what it actually produces — which is how substack_sync verifies a pulled edit landed
    as the text it meant, instead of trusting an offset map."""
    if b == '---':
        return '<hr>'
    if b.startswith('### '):
        return '<h3>' + inline(b[4:], piece_dir) + '</h3>'
    if b.startswith('## '):
        return '<h2>' + inline(b[3:], piece_dir) + '</h2>'
    if b.startswith('!['):
        return inline(b, piece_dir)
    if re.match(r'^[-*]\s', b):
        # Bullet list. Nothing parsed these: the block fell through to <p> and the literal
        # "- " markers travelled into the post, while the live doc (where the list is a real
        # bulletList node whose textContent concatenates its items) could never match the
        # draft's rendering. Continuation lines are indented and belong to the open item.
        items, cur = [], None
        for ln in b.split('\n'):
            m2 = re.match(r'^[-*]\s+(.*)$', ln.strip())
            if m2:
                if cur is not None:
                    items.append(cur)
                cur = m2.group(1)
            elif ln.strip() and cur is not None:
                cur += ' ' + ln.strip()
        if cur is not None:
            items.append(cur)
        return '<ul>' + ''.join('<li>' + inline(it, piece_dir) + '</li>' for it in items) + '</ul>'
    if b.startswith('> '):
        # blockquote: strip the '> ' from every line, join, emit one <blockquote>.
        # Without this the marker survives into the paragraph and is escaped to '&gt;'.
        # A merged source (see parse_blocks) holds several quoted paragraphs separated by a
        # blank line; each becomes its own <p> INSIDE the one blockquote.
        paras = [q for q in re.split(r'\n\s*\n', b) if q.strip()]
        inner = ''.join(
            '<p>' + inline(' '.join(re.sub(r'^>\s?', '', ln) for ln in q.split('\n')),
                           piece_dir) + '</p>'
            for q in paras)
        return '<blockquote>' + inner + '</blockquote>'
    return '<p>' + inline(' '.join(b.split('\n')), piece_dir) + '</p>'

def render_footnote_block(b, piece_dir):
    """Render ONE `[^n]: ...` definition block the way parse_blocks does — label stripped,
    lines joined, internal notes cleaned. A footnote is NOT a paragraph, and rendering one
    through render_block leaves its `[^n]:` label in the text, which silently fails any
    round-trip check made against it."""
    m = re.match(r'^\[\^(\w+)\]:\s?(.*)$', b.strip(), re.S)
    if not m:
        return None
    # .split() and not .split('\n'): markdown continues a footnote with an INDENTED line,
    # so splitting on newlines alone re-joins the indentation into the text as a run of
    # spaces. Collapse every whitespace run, exactly as the continuation-paragraph path in
    # parse_blocks() already does.
    text, _removed = clean_footnote(' '.join(m.group(2).split()))
    return inline(text, piece_dir)

# The source recorded for the generated canonical line: never text that draft.md can hold.
CANONICAL_SRC = '\x00canonical-line (generated from publish.yaml -> canonical:)'


def parse_blocks(piece_dir):
    """Parse draft.md into (blocks, footnotes_ordered, stripped, residual).
    `blocks` is the ordered list of body-block HTML strings (<p>/<h2>/<h3>/<hr>/
    <blockquote>/<figure>), each carrying [[FNn]] markers where a ref appeared.
    `footnotes_ordered` is [[n, contentHTML], ...] in FIRST-REFERENCE order, with
    internal notes stripped; `fn_issues` reports refs/definitions that don't pair up.
    This is the shared parser behind both convert() (fresh publish) and
    render_reader() (surgical republish)."""
    global _IMGMAP
    _man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    _IMGMAP = _man.get('images') if isinstance(_man.get('images'), dict) else {}
    global _CAPTIONS, _COVER, _COVER_CAPTION
    _CAPTIONS, _COVER, _COVER_CAPTION = load_captions(_yaml_manifest(piece_dir, _man))
    src = open(os.path.join(piece_dir, 'draft.md')).read()
    src = re.sub(r'<!--.*?-->', '', src, flags=re.S)                 # strip HTML comments
    lines = src.split('\n')
    for i, ln in enumerate(lines):                                  # drop front-matter
        if ln.strip() == '---':
            lines = lines[i + 1:]
            break
    body = '\n'.join(lines).strip()

    footnotes = {}                                                   # n -> content HTML
    fn_src = {}                                                      # n -> raw markdown source
    stripped = 0                                                     # editorial notes removed
    fn_orphans = []                                                  # (id, text) paragraph after a footnote def, unindented
    unverified = []                                                  # (id, note) for verify-markers
    out, out_src = [], []                                            # HTML block + its raw source
    # SPLIT ON BLANK LINES ONLY. The old separator was `\n\s*\n`, whose `\s*` could eat the
    # NEXT block's leading indentation — which is the one signal that marks a footnote's
    # continuation paragraph.
    last_fn = None                                                   # id of the immediately preceding footnote definition
    for block in re.split(r'\n[ \t]*\n', body):
        b = block.strip()
        if not b:
            continue
        # A FOOTNOTE'S CONTINUATION PARAGRAPH. Markdown continues a footnote with an indented
        # block. Before 2026-09-02 this fell through to the body path and published as an
        # ordinary paragraph, in place — content silently RELOCATED, not dropped, so the output
        # looked deliberate and nothing refused. Joined with a space, exactly as a multi-LINE
        # footnote already is.
        if last_fn and re.match(r'^(?: {4,}|\t)\S', block):
            text, removed = clean_footnote(' '.join(b.split()))
            if removed:
                stripped += 1
                if UNVERIFIED_RE.search(removed):
                    unverified.append((last_fn, ' '.join(removed.split())[:90]))
            if text:
                footnotes[last_fn] = (footnotes[last_fn] + ' ' + inline(text, piece_dir)).strip()
                fn_src[last_fn] += '\n\n' + block
            continue
        m = re.match(r'^\[\^(\w+)\]:\s?(.*)$', b, re.S)              # footnote definition
        if m:
            # .split(), not .split('\n') — see render_footnote_block(). A multi-LINE footnote
            # definition indents its continuation lines, and splitting on newlines alone carries
            # that indentation into the rendered text ("iconography.     The reading"). Invisible
            # to the fidelity digest, which normalizes whitespace on BOTH sides, so it reached a
            # rendered page before anyone saw it (hollow-flute, 2026-09-02).
            raw = ' '.join(m.group(2).split())
            text, removed = clean_footnote(raw)
            if removed:
                stripped += 1
                if UNVERIFIED_RE.search(removed):
                    unverified.append((m.group(1), ' '.join(removed.split())[:90]))
            footnotes[m.group(1)] = inline(text, piece_dir)
            fn_src[m.group(1)] = b
            last_fn = m.group(1)
            continue
        # An UNindented paragraph straight after a footnote definition is ambiguous: this house
        # puts definitions mid-document with body prose after them, so it cannot be claimed as a
        # continuation. It is also exactly how a continuation gets written by mistake, so say so.
        # ...but only a PARAGRAPH is a plausible mistaken continuation. A divider, a heading, a
        # quote, a list or an image can never be one, and they are the ordinary thing to find
        # after a block of definitions in this house — warning on those fires on nearly every
        # piece, and a warning that always fires is read as noise and then not read at all.
        if last_fn and not re.match(r'^(---|#|>|[-*+]\s|!\[|\|)', b):
            fn_orphans.append((last_fn, ' '.join(b.split())[:70]))
        last_fn = None
        # ADJACENT BLOCKQUOTES MERGE. ProseMirror joins two neighbouring blockquotes into one
        # node on paste, so a draft with two consecutive `> ` blocks composes to ONE live
        # blockquote holding two paragraphs. Emitting them as two blocks here made the draft
        # permanently one block longer than its own post — `In the Name` read 111 against a
        # live 110 and could never be re-synced, because the surgical patcher aligns top nodes
        # 1:1 and rightly refuses a count mismatch. The converter now models what Substack
        # actually produces rather than what the markdown looks like.
        if b.startswith('> ') and out_src and out_src[-1].startswith('> '):
            out_src[-1] = out_src[-1] + '\n\n' + b
            out[-1] = render_block(out_src[-1], piece_dir)
            continue
        out_src.append(b)
        out.append(render_block(b, piece_dir))

    # Footnotes in FIRST-REFERENCE order — the order the composer actually inserts them
    # (it walks the body's markers in document order), and therefore the order the live
    # doc holds them in.
    #
    # This was previously sorted by LABEL — numerics first, then alphabetically — on the
    # reasoning that "Substack renumbers by position anyway." That is true for composing
    # and false for the surgical re-sync, which aligns footnote nodes 1:1 BY INDEX. Any
    # draft whose labels are named (`[^kjv]`) or no longer in citation order then paired
    # every footnote against the wrong live node — and the count-only structural guard
    # could not see it, because a permutation preserves the count. Real case: `In the
    # Name` (2026-09-01) rendered footnote #0 as `John 10:3` against a live #0 that was
    # the shelucho-shel-adam maxim; 30 == 30, zero aligned, and a re-sync would have
    # overwritten all thirty notes of a live essay with mismatched text.
    # A SYNDICATED copy says where the original lives. Substack cannot emit rel=canonical
    # (no publisher field for it, 2026-09-10), so the only instrument is a visible first line
    # -- the same one md_to_linkedin writes. It is driven by `canonical:` in publish.yaml, the
    # field md_to_linkedin already reads first; a piece whose home IS this Substack sets none
    # and gets none. Generated here, in the parser both convert() and render_reader() share, so
    # the composed post and substack_verify's expectation carry it together. Its source is a
    # sentinel that cannot occur in draft.md, so substack_sync can never "pull" it into prose.
    canonical = str(_man.get('canonical') or '').strip()
    if canonical:
        out.insert(0, '<p><em>Originally published at <a href="%s">%s</a>.</em></p>'
                   % (esc(canonical), esc(canonical)))
        out_src.insert(0, CANONICAL_SRC)
    seen, ref_order, duplicated = set(), [], []
    for blk in out:
        for ref in re.finditer(r'\[\[FN(\w+)\]\]', blk):
            n = ref.group(1)
            if n in seen:
                duplicated.append(n)                                 # 2nd ref => 2nd live node
                continue
            seen.add(n)
            ref_order.append(n)
    # A footnote referenced from INSIDE another footnote cannot work: the composer's
    # insertFootnote pass walks the BODY's markers only, so the marker in the note is never
    # converted — it publishes as a literal `[^25]` — while this converter's reader-text strips
    # it, leaving a dangling `cf. )` on the draft side. Both wrong, differently, and neither
    # visible to any existing guard. `The Way Home Is Down` carried exactly that to readers from
    # the day it published (found 2026-09-01).
    nested = sorted({m.group(1) for n, c in footnotes.items()
                     for m in re.finditer(r'\[\[FN(\w+)\]\]', c)})
    fn_issues = {
        'undefined':    [n for n in ref_order if n not in footnotes],   # ref with no definition
        'unreferenced': [n for n in footnotes if n not in seen],        # definition never cited
        'duplicated':   sorted(set(duplicated)),                        # cited more than once
        'nested':       nested,                                         # ref inside a footnote
        'orphaned':     fn_orphans,                                     # unindented para after a footnote def
    }
    ordered = [[n, footnotes[n]] for n in ref_order if n in footnotes]
    # A footnote (or a body block) that carries CLEARANCE language — "consulted 2026-09-07",
    # "checked 2026-09-02", a bare ISO date — is scaffold that reached the reader. The desk's
    # place for a verification record is publish.yaml -> `verified:`; the footnote carries the
    # citation and nothing about the checking. Found 2026-09-07 when "(both consulted
    # 2026-09-07)" was composed into a live footnote of The Towel and the author caught it in
    # the editor: the guards above look for verify/todo language, and a note that says the
    # checking is DONE reads as clean to every one of them. An ISO date is the tell — reader
    # prose dates a source "(2002)" or "March 10, 1967", never 2026-09-07 — so it refuses on
    # the date shape and on consulted/accessed/retrieved + a date, wherever it is.
    residual = [n for n, c in ordered
                if re.search(r'verify', c, re.I) or CLEARANCE_RE.search(c) or desk_path_in(c)]
    # An image's alt text is exempt: it TRANSCRIBES what is in the picture, verbatim and in
    # quotation marks (docs/ALT-TEXT.md), and a picture of a ledger or a receipt carries ISO
    # dates. A transcription is not scaffold — the date is the image's, not the desk's. Found
    # 2026-09-14 when A Writing Desk That Keeps Its Receipts' hero (a receipt tape of
    # timestamped commits) refused to compose on the dates its alt had to carry.
    _no_alt = lambda b: re.sub(r'\salt="[^"]*"', ' alt=""', b)
    residual += ['body#%d' % i for i, b in enumerate(out)
                 if CLEARANCE_RE.search(_no_alt(b)) or desk_path_in(b)]
    sources = {'body': out_src, 'fns': [fn_src[n] for n, _c in ordered]}
    return out, ordered, stripped, residual, unverified, fn_issues, sources

def render_captions(piece_dir):
    """Every body image's caption, in document order, '' for an uncaptioned one. The
    position is the key: it is how substack_verify lines them up with the live figures
    and how substack_captions writes them into an existing post."""
    out = []
    for b in parse_blocks(piece_dir)[0]:
        for fig in re.finditer(r'<figure>(.*?)</figure>', b, re.S):
            c = re.search(r'<figcaption>(.*?)</figcaption>', fig.group(1), re.S)
            out.append(c.group(1).replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
                       if c else '')
    return out


def convert(piece_dir):
    blocks, ordered, stripped, residual, unverified, fn_issues, _src = parse_blocks(piece_dir)
    return '\n'.join(blocks), ordered, stripped, residual, unverified, fn_issues

# --- typography -------------------------------------------------------------
# Substack's editor (ProseMirror smart-quote input rules) converts straight quotes
# to curly ones as the body is pasted. draft.md is written with straight quotes, so
# the composed live post and the draft's reader-text disagree on every apostrophe
# and quotation mark forever after. Nothing normalized them, so a surgical re-sync
# saw a diff in every quote-bearing block and would have rewritten each one — mass
# typographic damage disguised as a one-word touch-up (found 2026-09-01).
#
# The diff domain therefore compares FLATTENED text (curly -> straight), while any
# run actually inserted into the live doc is SMARTENED (straight -> curly) so it
# matches the typography of the document it lands in.

def flatten_quotes(s):
    """Curly quotes -> straight. The comparison domain; never inserted."""
    return (s.replace('\u2018', "'").replace('\u2019', "'")
             .replace('\u201c', '"').replace('\u201d', '"'))

def smarten_quotes(s):
    """Straight quotes -> curly, by the usual boundary rule: a quote that follows
    whitespace, an opening bracket or a dash opens; anything else closes."""
    out, opening = [], set(' \t\n(【[{\u2014\u2013-\u201c\u2018')
    for i, ch in enumerate(s):
        if ch in '"\'':
            prev = s[i - 1] if i else ' '
            opens = prev in opening
            if ch == '"':
                out.append('\u201c' if opens else '\u201d')
            else:
                out.append('\u2018' if opens else '\u2019')
        else:
            out.append(ch)
    return ''.join(out)

def strip_to_reader(html_fragment):
    """Reduce a block/footnote HTML fragment to the plain reader-text that the
    live Substack editor actually holds: drop [[FNn]] markers (they became native
    footnotes), drop tags, unescape the three entities esc() introduces, collapse
    whitespace. This is the domain the surgical diff and the live doc share."""
    s = re.sub(r'\[\[FN\w+\]\]', '', html_fragment)
    # A caption is MEDIA text: the live post keeps it inside the captionedImage, which
    # substack_verify and substack_repatch skip as a block. Keeping it out here holds the
    # reader digest where it was before captions existed; captions are compared separately.
    s = re.sub(r'<figcaption[^>]*>.*?</figcaption>', '', s, flags=re.S)
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return re.sub(r'\s+', ' ', s).strip()

# --- marks: the layer reader-text cannot see ---------------------------------
# Every comparison on this desk — the surgical diff, the structural aligner, the
# per-block digest in substack_verify — runs on READER-TEXT: tags stripped, entities
# unescaped, whitespace collapsed. That domain is deliberate and it is right for text.
# It is also, by construction, BLIND TO FORMATTING. Wrapping a word that is already in
# the post in <em> changes zero reader-text, so it produces zero diff.
#
# Measured on `rising-after-falls`, 2026-09-09: after italicising *satsang* and *kirtan*
# in a composed draft, the regenerated surgical patch was byte-identical in size to the
# previous one (29,782 bytes). The failure mode is the dangerous one — a FALSE PASS: the
# patcher reports `unchanged` and applies nothing, and the digest check then reports MATCH
# while the italic is simply not there. Same shape as the youtube2 embed blindness in the
# publish skill's 0b-embeds: THE SCRAPE DEFINES WHAT CAN BE CHECKED, and what it does not
# collect cannot be verified.
#
# `MarkRuns` is the second domain, collected alongside the first: the marked RUNS of a
# block — em / strong / link — as (kind, text, href), in document order, with their
# character offsets into that block's reader-text. One scanner, fed by both sides, so the
# draft and the live post can never be compared by two different definitions of a mark.
MARK_TAGS = {'em': 'em', 'i': 'em', 'strong': 'strong', 'b': 'strong', 'a': 'link'}

def canon_href(h):
    """The comparison domain for a link target.

    Measured against the live publication 2026-09-09 (`the-kingdom-that-isnt`): Substack
    serves authored hrefs back VERBATIM — no utm parameters, no redirect wrapper — so this
    stays deliberately minimal. It exists to absorb the one difference that is not content
    (a trailing slash), and nothing else: a normalizer that rewrites more than it must is
    how a real broken link gets normalized into looking fine."""
    h = (h or '').strip()
    return h[:-1] if h.endswith('/') and h.count('/') > 3 else h


class MarkRuns:
    """Collect marked runs from a stream of HTML events, with offsets into reader-text.

    Fed by md_to_substack (the draft's own converter output) and by substack_verify's
    live-page extractor, so both sides answer "which words are italic" the same way.

    Two properties are load-bearing:

      * `text` is built with the SAME normalization `strip_to_reader` applies — markers
        dropped, whitespace runs collapsed, ends stripped — so a run's (start, end) are
        real offsets into the reader-text everything else compares. `assert_text` is the
        check that this stayed true; nothing should trust an offset without it.
      * runs are emitted in OPEN order (sorted by start, longest-first on a tie), not
        close order. `<strong><em>x</em></strong>` and `<em><strong>x</strong></em>` are
        the same formatting, and the draft's own regexes can emit either nesting; close
        order would report that as drift forever.
    """
    _MARKER = re.compile(r'\[\[FN(\w+)\]\]')

    def __init__(self):
        self.stack = []          # [kind, href, start]
        self.out = []
        self.text = ''
        self.anchors = []        # [(pos, label)] — where each footnote is CITED

    def _feed(self, s):
        s = re.sub(r'\s+', ' ', s)
        if s.startswith(' ') and (not self.text or self.text.endswith(' ')):
            s = s.lstrip()
        self.text += s

    def data(self, s):
        # The footnote markers are not reader-text, but WHERE they sat is: the text is fed
        # around them so the recorded position indexes the same reader-text every offset
        # here indexes. Splitting rather than deleting is the whole point -- `_MARKER.sub`
        # erased the one fact that says which sentence carries the note.
        parts = self._MARKER.split(s)
        self._feed(parts[0])
        for i in range(1, len(parts), 2):
            self.anchor(parts[i])
            self._feed(parts[i + 1])

    def anchor(self, label):
        """Record a footnote citation at the current position.

        Called by the draft side from `data` (the `[[FNn]]` marker) and by the live side
        from substack_verify's extractor (the `<a class="footnote-anchor">` element, whose
        digit is likewise not reader-text). One recorder, both sides, as with the runs."""
        self.anchors.append((len(self.text), str(label).strip()))

    def enter(self, tag, attrs):
        kind = MARK_TAGS.get(tag)
        if kind is None:
            return False
        href = canon_href(dict(attrs).get('href', '')) if kind == 'link' else ''
        self.stack.append([kind, href, len(self.text)])
        return True

    def leave(self, tag):
        kind = MARK_TAGS.get(tag)
        if kind is None:
            return False
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == kind:
                k, href, start = self.stack.pop(i)
                self.out.append([start, len(self.text), k, href])   # UNTRIMMED; take() finishes
                break
        return True

    def take(self):
        """The block's coalesced runs, in reader order; resets for the next block.

        A RUN IS A SPAN OF FORMATTING, NOT AN ELEMENT, and the difference is not academic.
        The converter emits `**a _b_ c**` as one `<strong>` wrapping an `<em>`; Substack
        stores the same formatting as THREE strong elements around the em and serves it
        back that way. Compared element-by-element, every bold-containing-an-italic in the
        corpus reported drift -- 8 pieces of 34 on the first sweep, 2026-09-09, none of
        them a real difference. Contiguous spans of the same kind (and, for a link, the
        same href) are therefore merged before anything is compared.

        Merging happens on the UNTRIMMED spans and the trim comes after, in that order:
        `<strong>There is no </strong><em><strong>toward</strong></em>` is contiguous only
        while the first span still owns its trailing space. Trim first and the two spans
        no longer touch, which is the artifact this method exists to remove.

        A gap of real text is never bridged: `_a_ plain _b_` stays two italics on both
        sides, so a draft that merged them into one would still be reported.
        """
        merged = []
        for start, end, k, h in sorted(self.out, key=lambda r: (r[2], r[3], r[0])):
            if merged and merged[-1][2] == k and merged[-1][3] == h and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end, k, h])
        runs = []
        for start, end, k, h in merged:
            # trim inward past whitespace: `<em>word </em>` and `<em>word</em> ` are the
            # same italic, and a run ending on a space cannot be addressed as a mark range
            # without also claiming the space.
            while start < end and self.text[start] == ' ':
                start += 1
            while end > start and self.text[end - 1] == ' ':
                end -= 1
            if end > start:
                runs.append((start, end, k, self.text[start:end], h))
        runs.sort(key=lambda r: (r[0], -r[1], r[2]))
        text = self.text.rstrip()
        # An anchor on the last word sits at a position the rstrip just removed; clamp it
        # rather than hand back an offset that does not index the text it came with.
        anchors = [(min(pos, len(text)), lab) for pos, lab in self.anchors]
        self.stack, self.out, self.text, self.anchors = [], [], '', []
        return runs, text, anchors


class _FragmentMarks(HTMLParser):
    """MarkRuns over a standalone HTML fragment — one body block, or one footnote."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.runs = MarkRuns()

    def handle_starttag(self, tag, attrs):
        self.runs.enter(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        self.runs.leave(tag)

    def handle_data(self, d):
        self.runs.data(d)


def marks_in(html_fragment):
    """(runs, reader_text, anchors) for one block or footnote of the converter's own HTML.

    `runs` are (start, end, kind, text, href) with kind in {em, strong, link};
    `anchors` are (pos, footnote-name) for each `[[FNn]]` citation. The caller is
    expected to check `reader_text == strip_to_reader(html_fragment)` before using an
    offset — see `render_marks` and `render_anchors`."""
    p = _FragmentMarks()
    p.feed(html_fragment)
    p.close()
    return p.runs.take()


def mark_keys(runs):
    """The EQUALITY domain for a list of runs: kind, flattened text, href — no offsets.

    Offsets are for locating a run in a document; they are not part of what a mark IS.
    Comparing them would report drift on a block whose text merely moved, which is the
    false-drift direction this desk has already paid for once."""
    return [(k, re.sub(r'\s+', ' ', flatten_quotes(t)).strip(), h) for _s, _e, k, t, h in runs]


def mark_sig(runs):
    """One block's marks as a single canonical string, for hashing.

    Must agree BYTE FOR BYTE with the JS `marksOf(node).map(markKey).join('\u0001')` in
    substack_repatch's JS_HELPERS — the two are the same signature computed on the two sides
    of the wire, and a baseline hash is worthless if they can disagree. `\u0001` separates
    runs because it is not whitespace, so the normalization H() applies to the whole string
    cannot merge two runs into one.
    """
    return '\u0001'.join(f'{k} {t} {h}' for k, t, h in mark_keys(runs))


def render_marks(piece_dir):
    """(body_marks, fn_marks, offsets_ok) — the mark layer of render_reader.

    Parallel to `render_reader`, filtered identically, so index i means the same block in
    both. `offsets_ok` is False for any block whose scanned text did not reproduce
    `strip_to_reader`'s: the run STRINGS are still comparable there, but the offsets are
    not to be trusted, and the patcher falls back to locating a run by its text."""
    blocks, ordered, _stripped, _residual, _unverified, _fn_issues, _sources = parse_blocks(piece_dir)
    body, offsets_ok = [], True
    for b in blocks:
        if b.strip() == '<hr>':
            continue
        txt = strip_to_reader(b)
        if not txt:
            continue
        runs, scanned, _anchors = marks_in(b)
        offsets_ok = offsets_ok and scanned == txt
        body.append(runs)
    fns = []
    for _n, c in ordered:
        runs, scanned, _anchors = marks_in(c)
        offsets_ok = offsets_ok and scanned == strip_to_reader(c)
        fns.append(runs)
    return body, fns, offsets_ok


# --- anchors: WHERE a footnote is cited --------------------------------------
# Third domain, same lesson as the second. Reader-text drops the superscript digit, and
# the mark scan never looked at it: a footnote attached to the wrong sentence is invisible
# to both. Measured 2026-09-11 on `for-the-love-of-dogs` -- live since 2026-08-05, its
# footnote 1 anchored after "It was slow. It worked." while the draft cites it after
# "I stopped trying to frighten him." -- and `substack_verify --fresh` reported MATCH every
# time it was run. Only `substack_repatch --structural` noticed, and only because it refuses
# to patch a block whose footnote count it cannot align.
#
# The comparison domain is (footnote number, TAIL): the few words of reader-text the anchor
# follows. A tail rather than a bare offset because a bare offset is unreadable in a report
# and says nothing about which sentence moved -- and the tail is exact, not fuzzy, since only
# blocks whose text ALREADY agrees are ever compared.

def anchor_tail(text, pos, n=40):
    """The reader-text an anchor follows: where it sits, in a form a person can check."""
    return re.sub(r'\s+', ' ', flatten_quotes(text[:pos]))[-n:]


def render_anchors(piece_dir):
    """(body_anchors, fn_anchors) — the anchor layer of render_reader.

    Parallel to `render_reader` and `render_marks`, filtered identically, so index i means
    the same block in all three. Each entry is a list of (number, tail) in document order,
    where `number` is the footnote's live number (first-reference order, 1-based; 0 for a
    ref with no definition) and `tail` is the text it follows — or None where the scanned
    text did not reproduce `strip_to_reader`'s, in which case the offsets are not to be
    trusted and only the NUMBERS are comparable.
    """
    blocks, ordered, _stripped, _residual, _unverified, _fn_issues, _sources = parse_blocks(piece_dir)
    number = {n: i + 1 for i, (n, _c) in enumerate(ordered)}

    def entries(fragment, want):
        _runs, scanned, anchors = marks_in(fragment)
        ok = scanned == want
        return [(number.get(lab, 0), anchor_tail(scanned, pos) if ok else None)
                for pos, lab in anchors]

    body = []
    for b in blocks:
        if b.strip() == '<hr>':
            continue
        txt = strip_to_reader(b)
        if not txt:
            continue
        body.append(entries(b, txt))
    fns = [entries(c, strip_to_reader(c)) for _n, c in ordered]
    return body, fns


def render_reader(piece_dir):
    """(title-independent) reader-text view of the piece, for surgical republish:
    (body_texts, footnote_texts, residual). body_texts drops <hr>/empty blocks so
    it aligns 1:1 with the live doc's non-empty, non-footnote top nodes; footnote_texts
    is in first-reference order — the order the composer inserts them, which is the
    order the live doc holds. `fn_issues` surfaces refs/definitions that don't pair
    up, any of which would shift that alignment."""
    blocks, ordered, stripped, residual, _unverified, fn_issues, sources = parse_blocks(piece_dir)
    body, body_src = [], []
    for b, bsrc in zip(blocks, sources['body']):
        if b.strip() == '<hr>':
            continue
        txt = strip_to_reader(b)
        if txt:
            body.append(txt)
            body_src.append(bsrc)                                    # stays 1:1 with `body`
    fns = [strip_to_reader(c) for _n, c in ordered]
    render_reader.sources = {'body': body_src, 'fns': sources['fns']}
    return body, fns, residual, fn_issues

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    allow_verify = '--allow-verify' in sys.argv
    allow_unverified = '--allow-unverified' in sys.argv
    piece_dir = args[0].rstrip('/')
    out_js = args[1] if len(args) > 1 else 'paste.js'
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    # An embargo does NOT stop a compose: a Substack draft is private, and composing
    # early is how a scheduled publication is prepared at all. It stops the click,
    # which is the skill's job, so this says the moment out loud where the composer
    # will read it. schedule.py holds the field.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import schedule as _sched
    _state, _moment = _sched.state(piece_dir)
    if _state == 'embargoed':
        print(f"EMBARGO: this piece is not due until {_sched.fmt(_moment)} "
              f"({_sched.human_delta(_moment)}). Composing is fine — the draft is private. "
              f"DO NOT CLICK PUBLISH: set Substack's own scheduled time to that moment "
              f"instead, or come back when it opens.")
    gate_errors, gate_warnings = manifest_gate(piece_dir)
    for w in gate_warnings:
        print(f"WARNING: {w} -- the author has not signed off on this line; make sure they "
              f"read it in the editor before Publish.")
    if gate_errors:
        for e in gate_errors:
            print(f"WARNING: {e}")
        print("Refusing to write output: fix what is named above (a post needs a title and a "
              "subtitle; a caption belongs in publish.yaml, not draft.md). There is no override.")
        sys.exit(6)
    html, footnotes, stripped, residual, unverified, fn_issues = convert(piece_dir)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import substack_account as sa
    js = sa.guarded(piece_dir, JS_TEMPLATE
                    .replace('%TITLE%', json.dumps(man.get('title', '')))
                    .replace('%SUBTITLE%', json.dumps(man.get('subtitle', '')))
                    .replace('%BODY%', json.dumps(html))
                    .replace('%FOOTNOTES%', json.dumps(footnotes)), 'md_to_substack')
    print(f"paragraphs~{html.count('<p>')}  headings~{html.count('<h2>')+html.count('<h3>')}  "
          f"dividers~{html.count('<hr>')}  images~{html.count('<img')}  footnotes~{len(footnotes)}  "
          f"editorial-notes-stripped~{stripped}")
    if residual:
        print(f"WARNING: {len(residual)} block(s) still carry verify or clearance language after "
              f"cleaning: {residual}. A 'verify' note: verify the claim, then move the note behind "
              f"a † (or delete it). Clearance language (an ISO date, 'consulted 2026-09-07'): the "
              f"record belongs in publish.yaml -> verified:, not in the reader's footnote. A desk "
              f"path (projects/…, facts.md, assets/figures.py): a reader cannot open it — cite a "
              f"public URL or say it in words, and keep provenance in publish.yaml.")
        if not allow_verify:
            print("Refusing to write output. Re-run with --allow-verify to override.")
            sys.exit(2)
    if fn_issues.get('orphaned'):
        print("WARNING: a paragraph follows a footnote definition without being indented, so it "
              "publishes as BODY TEXT, in place — not as part of the note:")
        for n, txt in fn_issues['orphaned']:
            print(f"           after [^{n}]: {txt}…")
        print("           If it was meant to continue the footnote, indent it four spaces. If it "
              "is body prose, this is fine and nothing needs changing.")
    if fn_issues['nested']:
        print(f"WARNING: footnote reference(s) inside a footnote: {fn_issues['nested']}. These "
              f"cannot become footnotes — they publish as a literal marker. Reword the note.")
        sys.exit(5)
    if fn_issues['undefined'] or fn_issues['duplicated']:
        # Either one changes how many footnote nodes the composer creates, which
        # desynchronizes every later index for a subsequent surgical re-sync.
        if fn_issues['undefined']:
            print(f"WARNING: footnote ref(s) with no definition, which publish as raw "
                  f"markers: {fn_issues['undefined']}")
        if fn_issues['duplicated']:
            print(f"WARNING: footnote(s) cited more than once: {fn_issues['duplicated']}. "
                  f"Each extra citation becomes its own live footnote node.")
        sys.exit(4)
    if fn_issues['unreferenced']:
        print(f"NOTE: {len(fn_issues['unreferenced'])} footnote definition(s) are never cited "
              f"and will not appear in the post: {fn_issues['unreferenced']}")
    if unverified:
        print(f"WARNING: {len(unverified)} footnote(s) carry an UNVERIFIED-CLAIM marker that "
              f"would be stripped and published as fact:")
        for n, note in unverified:
            print(f"  [^{n}]  † {note}")
        if not allow_unverified:
            print("Refusing to write output. Verify the claims and clear the notes, or re-run "
                  "with --allow-unverified if these are genuinely not verify-markers.")
            sys.exit(3)
    open(out_js, 'w').write(js)
    print(f"wrote {out_js} ({len(js)} bytes)")

JS_TEMPLATE = """(() => {
  const setField = (el, v) => { if (!el) return; const d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value'); d.set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); };
  setField(document.querySelector('textarea[placeholder="Title"]'), %TITLE%);
  setField(document.querySelector('textarea[placeholder="Add a subtitle\\u2026"]'), %SUBTITLE%);
  const pm = document.querySelector('.ProseMirror'); pm.focus();
  const dt = new DataTransfer(); dt.setData('text/html', %BODY%);
  pm.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
  window.__sbFN = %FOOTNOTES%;
  window.__sbInsertFootnotes = async () => {
    // Call B is its own eval, and the pane's login can change between A and B: the account
    // guard (substack_account.wrap) runs again here, before the document is touched.
    const stop = await __deskAccount();
    if (stop) return JSON.stringify(stop);
    const ed = document.querySelector('.ProseMirror').editor;
    const findToken = (doc, t) => { let f = null; doc.descendants((node, pos) => { if (f) return false; if (node.isText) { const i = node.text.indexOf(t); if (i >= 0) { f = { from: pos + i, to: pos + i + t.length }; return false; } } return true; }); return f; };
    let done = 0; const missing = [];
    for (const [n, c] of window.__sbFN) {
      const loc = findToken(ed.state.doc, '[[FN' + n + ']]');
      if (!loc) { missing.push(n); continue; }
      ed.chain().focus().setTextSelection(loc).deleteSelection().insertFootnote().run();
      ed.chain().insertContent(c).run();
      done++;
    }
    return JSON.stringify({ inserted: done, missing });
  };
  return 'body pasted (' + document.querySelectorAll('.ProseMirror > *').length + ' blocks pre-async); next: await window.__sbInsertFootnotes()';
})()
"""

if __name__ == '__main__':
    main()
