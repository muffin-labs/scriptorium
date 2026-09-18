#!/usr/bin/env python3
"""
substack_notes.py — one Substack Note per publication, and a backlog worked one a day.

A Note is Substack's short-form feed post. Every live post gets exactly one, announcing it:
the piece's `note` companion, then the post's public URL alone as the last paragraph. The Notes
composer turns a bare post URL into that post's card by itself (measured 2026-09-10:
`setContent` with the URL as plain text rendered the publication name, the title and the hero
within three seconds), so the text is all the desk has to carry.

WHERE THE STATE LIVES — per piece, never in a shared queue

  pieces/<slug>/publish.yaml       declares the Note as the piece's `note` companion
                                   (docs/COMPANIONS.md):

                                       companions:
                                         note: note.md

  pieces/<slug>/note.md            the Note's text, under a `form:` / `style:` header closed by
                                   `---`. Form `note` (short prose paragraphs) or `poem` (lines
                                   and stanzas). Plain text; NO URL — the post's own link is
                                   appended here, from publish.yaml, when the Note is built.

  pieces/<slug>/publish.yaml       a `substack_note:` block, written by `record`:

                                       substack_note:
                                         posted_at: 2026-09-11
                                         note_url: https://substack.com/@<handle>/note/c-<id>

                                   or `substack_note:` / `  skip: <reason>` for a post that
                                   should never get one.

  The backlog is DERIVED — every live post with no Note, oldest `published_at` first — so
  there is no queue file for two sessions to read, edit and write back over each other.

A POEM IN A NOTE (measured 2026-09-11)

  The Notes editor's schema has no hard-break node (paragraph, text, lists, blockquote,
  codeBlock, mention — nothing else), so a line break inside a paragraph cannot be sent. A poem
  goes ONE PARAGRAPH PER LINE, which is how multi-line Notes already render in the feed: tight
  lines, no gap (a posted five-line Note is five <p>, no <br>). An EMPTY paragraph between stanzas
  is kept by the editor and DROPPED by the server: measured 2026-09-11 on the first poem Note
  (c-334978586), 64 paragraphs sent with 11 empty, 53 live with 0 empty. The same day, a private
  Notes draft (POST /api/v1/comment/draft) showed the rule: any whitespace-only paragraph is
  stripped (empty, U+00A0, U+200B, U+3000) and a non-whitespace one is kept (U+2800, "·").
  So a stanza gap is a MARKER line — `stanza_break:` in note.md's header: `braille` (U+2800,
  reads as an empty line; the default), `dot` ("·", visible), or `none`. Screen readers may
  announce U+2800; `dot` is the accessible choice. PROVEN on a posted Note the same day:
  Earmuffs reposted as c-335012885 reads back 64 paragraphs, all 11 U+2800 gaps kept. Private
  probes go in the standing Notes draft (`notes_probe_draft_id`, outlets.yaml), never a live Note.

CADENCE

  A FRESH publication's Note (posted_at == published_at) goes out with the post, always.
  A BACKLOG Note (any other day) goes out at most one per calendar day: `next` exits 3 once
  today's is recorded. That is the whole of "catch up one day at a time", and it is a guard
  rather than a reminder because a backlog posted in one sitting is the thing it prevents.

Commands

  status                  every live post: posted / drafted / missing / skip, and what's next
  next                    the next backlog post (exit 3 when today's backlog Note is done)
  text <slug>             the Note as JSON: paragraphs, sha256, and the composer snippet
  record <slug> --url U   write the substack_note block after the Post click; refuses twice
  verify [<slug> ...]     read the PUBLIC notes feed (no login) and confirm each recorded Note
                          exists and names its post — and list Notes the desk has no record of

Posting is not this tool's job. It prepares the text and checks the result; the `publish`
skill drives the composer, and a Note is posted only on the author's word.

Exit: 0 ok, 1 problem found, 2 could not read, 3 today's backlog Note is already out.
"""
import sys, os, re, json, argparse, datetime, hashlib, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from md_to_substack import read_manifest                                  # noqa: E402
import companions                                                         # noqa: E402
import substack_account as sa                                             # noqa: E402

BLOCK = 'substack_note'

# The standing probe draft's first line — what the tooling calls it, and how a person scrolling
# their drafts knows to leave it alone. The instance records the draft's id as
# `notes_probe_draft_id` (outlets.yaml); `probe` prints both. Never posted, never deleted.
PROBE_LABEL = 'PROBE — private Notes test draft. Never post, never delete.'
FEED = 'https://substack.com/api/v1/reader/feed/profile/{id}?types%5B%5D=note'
UA = 'Mozilla/5.0 (writing-desk substack_notes)'


def default_pieces():
    env = os.environ.get('DESK_PIECES')
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.dirname(os.path.dirname(HERE)), 'pieces')


# ------------------------------------------------------------------------ the corpus
def live_url(piece_dir, man):
    """-> (url, outlet): the piece's reader address on ITS OWN Substack outlet.

    Each outlet declares the manifest key its URL is written under (`manifest_url_key` in
    outlets.yaml). This read `public_url` — the `substack` outlet's key — so a post on the
    second Substack outlet was not merely unannounced, it was not in the corpus at all: no
    backlog slot, no status row, and `verify` could not have caught a Note posted for it by
    hand. `love-is-not-a-metric-space` said so in its own manifest, in a comment, on the day
    it went live (2026-09-11). A desk with no registry keeps `public_url`, which is what a
    one-outlet desk has always written."""
    try:
        outlet, spec = sa.substack_outlet_for_piece(piece_dir)
    except Exception:                                             # noqa: BLE001 — unplaceable
        outlet, spec = None, {}
    key = (spec or {}).get('manifest_url_key') or 'public_url'
    return man.get(key, ''), outlet


def load(pieces_dir):
    """Every piece that is a live POST (not a page), with its Note state."""
    out = []
    for slug in sorted(os.listdir(pieces_dir)):
        d = os.path.join(pieces_dir, slug)
        man = read_manifest(os.path.join(d, 'publish.yaml'))
        url, outlet = live_url(d, man)
        date = man.get('published_at', '')
        if not url or not re.match(r'\d{4}-\d{2}-\d{2}$', date):
            continue                                        # not live
        if man.get('substack_type') == 'page':
            continue                                        # a page is not announced
        block = man.get(BLOCK) if isinstance(man.get(BLOCK), dict) else {}
        if block.get('skip'):
            state = 'skip'
        elif block.get('posted_at'):
            state = 'posted'
        elif companions.companion(d, 'note'):
            state = 'drafted'
        else:
            state = 'missing'
        # A YAML title is often quoted, and the quotes are the file's rather than the piece's.
        # They reached the composer snippet's card check as literal characters, so `card` could
        # never be true for a quoted title — and this session's own prompt says card MUST be true
        # before the Note is posted. A correct Note would have stopped on a false negative.
        out.append({'slug': slug, 'dir': d,
                    'title': str(man.get('title') or slug).strip().strip('"\''),
                    'url': url, 'outlet': outlet, 'published_at': date, 'state': state,
                    'posted_at': block.get('posted_at', ''),
                    'note_url': block.get('note_url', ''), 'skip': block.get('skip', '')})
    out.sort(key=lambda p: (p['published_at'], p['slug']))
    return out


def backlog(corpus):
    return [p for p in corpus if p['state'] in ('drafted', 'missing')]


def backlog_done_today(corpus, today):
    """The backlog Note that already went out today, if any. A fresh publication's own
    Note (posted the day the post went live) does not count against the cadence."""
    for p in corpus:
        if p['posted_at'] == today and p['posted_at'] != p['published_at']:
            return p
    return None


# ------------------------------------------------------------------------ the text
def note_paragraphs(comp):
    """The companion as composer paragraphs. A poem: one per line, a MARKER line between
    stanzas. Prose: one per paragraph. See A POEM IN A NOTE above for why."""
    blocks = companions.paragraphs(comp)
    if companions.FORMS[comp['form']]['lines'] != 'keep':
        return [b[0] for b in blocks]
    gap = companions.stanza_marker(comp)
    out = []
    for i, stanza in enumerate(blocks):
        if i:
            out.append(gap)
        out += stanza
    return out + [gap]                       # the last stanza's gap, before the card


def read_note(piece_dir, post_url):
    """-> (paragraphs, problems). The last paragraph is the post URL, added here."""
    comp = companions.companion(piece_dir, 'note')
    if not comp:
        return [], ['no `note` companion declared in publish.yaml']
    problems = companions.problems_of(comp, piece_dir)
    if problems:
        return [], problems
    return note_paragraphs(comp) + [post_url], []


TASK_PROMPT = """\
Post the Substack Note for {slug} — "{title}".

You are a scheduled session with no memory of how this was arranged. Everything you need is
here and in the piece. The desk is {root}. Do not improvise past this list.

WHY A TASK AND NOT A SCHEDULED NOTE: Substack will not attach a post that has not published, so
a Note composed ahead of time carries a plain link where the post's card belongs. Posting it
after the post is live is the only way to get the card. (Eric, 2026-09-11, formalizing it.)

1. The post must be LIVE first. Fetch {post_url} cache-busted and confirm it serves the piece —
   the BODY, not the scheduled-post teaser (the teaser carries the title and og: tags and no
   body). If it is not live, STOP and say so; do not post a Note announcing a post nobody can
   read. It was scheduled for {moment}; if it is late, that is Substack's business, not yours to
   work around.
2. Check the Note has not already gone out:
   `python3 framework/tools/substack_notes.py status` — if this piece already records a
   `substack_note:`, STOP. One Note per post, ever.
3. Build it, and never retype it:
   `python3 framework/tools/substack_notes.py text {slug}`
   That prints the paragraphs, a sha256, and a composer snippet. The Note's text is note.md plus
   the post's URL as the last paragraph.
4. Open the Notes composer at https://substack.com/home (the "What's on your mind?" box), signed
   in as the piece's own Substack account, and run the printed snippet. It refuses unless exactly
   one composer is open and empty. It returns {{sha256, card, postEnabled}}:
   - the sha256 MUST equal the tool's, or stop;
   - `card` MUST be true — that is the post's card, and getting it is the whole reason this runs
     after the post is live rather than before;
   - Post must be enabled.
5. Click Post. Then record and verify:
   `python3 framework/tools/substack_notes.py record {slug}` (it takes the id from the public
   feed — exactly one Note must name the post, or it writes nothing), then
   `python3 framework/tools/substack_notes.py verify {slug}`.
6. Commit the manifest by path, and tell Eric what went out with the Note's URL.

IF ANYTHING REFUSES, STOP AND REPORT. A Note is public the moment Post is clicked and there is no
second one. Eric authorized this posting in advance, on 2026-09-11, for a Note whose text he had
already read; that authorization does not extend to rewriting the Note or posting a different one.
"""


def cmd_task(slug, piece_dir, post_url, moment, root):
    """The self-contained prompt for a scheduled session that posts this Note after the post
    goes live. Generated rather than typed, so a moved moment or a renamed piece cannot leave a
    stale instruction inside a prompt nobody re-reads."""
    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    title = str(man.get('title') or '').strip().strip('"\'')
    return TASK_PROMPT.format(slug=slug, title=title, post_url=post_url, moment=moment, root=root)


def note_hash(paras):
    """What the composer must echo back: paragraph texts joined by a blank line. Computed
    from the editor's JSON on the page side, so it cannot depend on getText()'s separator."""
    return hashlib.sha256('\n\n'.join(paras).encode('utf-8')).hexdigest()


def composer_js(paras, title):
    doc = {'type': 'doc', 'content': [
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': t}]} if t
        else {'type': 'paragraph'} for t in paras]}
    return (
        "await (async () => {\n"
        # Substack keeps a hidden [role=dialog] in the DOM after the composer closes, so
        # the FIRST dialog is not the composer. Take the editor that is actually on screen.
        "  const eds = [...document.querySelectorAll('[role=dialog] .tiptap')]\n"
        "    .filter(e => e.getBoundingClientRect().height > 0);\n"
        "  if (eds.length !== 1) return {refused: `need exactly one open Notes composer, found ${eds.length}`};\n"
        "  const el = eds[0], d = el.closest('[role=dialog]');\n"
        "  if (!el.editor) return {refused: 'composer has no editor handle'};\n"
        "  const ed = el.editor;\n"
        "  if (ed.getText().trim()) return {refused: 'composer is not empty', has: ed.getText().slice(0, 200)};\n"
        f"  ed.commands.setContent({json.dumps(doc, ensure_ascii=False)});\n"
        "  await new Promise(r => setTimeout(r, 3000));\n"
        "  const paras = ed.getJSON().content.map(p => (p.content || []).map(n => n.text || '').join(''));\n"
        "  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(paras.join('\\n\\n')));\n"
        "  const sha256 = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');\n"
        f"  const card = d.innerText.includes({json.dumps(title, ensure_ascii=False)});\n"
        "  const post = [...d.querySelectorAll('button')].find(b => b.innerText.trim() === 'Post');\n"
        "  return {sha256, card, postEnabled: !!post && !post.disabled};\n"
        "})()\n")


# ------------------------------------------------------------------------ recording
def record(piece_dir, date, note_url):
    """Write the substack_note block into publish.yaml. Text edit, so every comment in the
    manifest survives. Refuses when a Note is already recorded: a post gets one."""
    path = os.path.join(piece_dir, 'publish.yaml')
    lines = open(path, encoding='utf-8').read().splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if re.match(rf'{BLOCK}:\s*(#.*)?$', l)), None)
    block = [f'{BLOCK}:\n', f'  posted_at: {date}\n', f'  note_url: {note_url}\n']
    if start is None:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines += ['\n', '# --- Substack Note (substack_notes.py record) ---\n'] + block
    else:
        end = start + 1
        while end < len(lines) and (lines[end].startswith((' ', '\t')) or not lines[end].strip()):
            end += 1
        existing = ''.join(lines[start:end])
        if 'posted_at:' in existing:
            raise SystemExit(f'refused: {path} already records a Note\n{existing}')
        if 'skip:' in existing:
            raise SystemExit(f'refused: {path} marks this post skip\n{existing}')
        lines[start:end] = block
    open(path, 'w', encoding='utf-8').writelines(lines)


def normalize_note_url(u, handle):
    """Accept a full URL, `c-<id>`, or a bare id."""
    m = re.search(r'c-(\d+)', u) or re.fullmatch(r'(\d+)', u.strip())
    if not m:
        raise SystemExit(f'not a Note URL or id: {u!r}')
    return f'https://substack.com/@{handle}/note/c-{m.group(1)}'


# ------------------------------------------------------------------------ the feed
def fetch_notes(profile_id, max_pages=40):
    """Every Note on the profile, from the PUBLIC feed. -> list of {id, date, blob}."""
    notes, cursor = [], None
    for _ in range(max_pages):
        url = FEED.format(id=profile_id) + (f'&cursor={cursor}' if cursor else '')
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.load(r)
        for it in j.get('items', []):
            c = it.get('comment') or {}
            if c.get('id'):
                notes.append({'id': c['id'], 'date': c.get('date', ''),
                              'blob': json.dumps(c, ensure_ascii=False)})
        cursor = j.get('nextCursor')
        if not cursor:
            break
    return notes


def slug_of(post_url):
    return post_url.rstrip('/').rsplit('/p/', 1)[-1]


def match_notes(corpus, notes):
    """-> {piece slug: [note ids that name its post]}"""
    hits = {}
    for p in corpus:
        needle = f'/p/{slug_of(p["url"])}'
        ids = [n['id'] for n in notes
               if re.search(re.escape(needle) + r'(?![\w-])', n['blob'])]
        if ids:
            hits[p['slug']] = ids
    return hits


# ------------------------------------------------------------------------ config
def outlet_spec(path, outlet=None):
    """-> (outlet name, spec) from the registry. `outlet` names one; otherwise the desk's
    substack_primary, or its one Substack outlet.

    NOTES BELONG TO A PROFILE, and each outlet records its own (`notes_profile_id`,
    `notes_handle`, `notes_probe_draft_id`). This indexed `outlets['substack']` by literal name,
    so a second publication's Notes would have been checked against the FIRST publication's feed
    — which does not merely fail, it reports a real Note as MISSING and an absent one as fine."""
    if not path or not os.path.exists(path):
        return None, {}
    doc = sa.load(path)
    if outlet:
        return outlet, (doc['outlets'].get(outlet) or {})
    name, _problem = sa.primary(doc)
    if not name:
        name = 'substack' if 'substack' in doc['outlets'] else None
    return name, (doc['outlets'].get(name) or {} if name else {})


def config(args, outlet=None):
    """Profile id and handle for ONE outlet: flags, else the instance's outlets.yaml."""
    pid, handle = args.profile, args.handle
    if not pid or not handle:
        _name, spec = outlet_spec(args.outlets, outlet or getattr(args, 'outlet', None))
        pid = pid or str(spec.get('notes_profile_id') or '')
        handle = handle or spec.get('notes_handle')
    return pid, handle


# ------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('cmd', choices=['status', 'next', 'text', 'record', 'verify', 'probe', 'task'])
    ap.add_argument('slugs', nargs='*')
    ap.add_argument('--pieces', default=default_pieces())
    ap.add_argument('--url', help='record: the Note URL (or c-<id>)')
    ap.add_argument('--at', help='task: the moment the post was scheduled for')
    ap.add_argument('--post-url', help="text: the post's public URL, for a Note SCHEDULED "
                                       "beside a post that is not live yet (a scheduled post "
                                       "already has its slug)")
    ap.add_argument('--date', help='record: YYYY-MM-DD (default today, local)')
    ap.add_argument('--today', help=argparse.SUPPRESS)           # for tests
    ap.add_argument('--outlets', default='publishing/outlets.yaml')
    ap.add_argument('--outlet', help='which Substack outlet (probe, and a --profile-less verify '
                                     'of one feed); a piece names its own')
    ap.add_argument('--profile'); ap.add_argument('--handle')
    args = ap.parse_args(argv)

    today = args.today or datetime.date.today().isoformat()
    corpus = load(args.pieces)
    by = {p['slug']: p for p in corpus}

    def piece(slug):
        slug = os.path.basename(slug.rstrip('/'))
        if slug not in by:
            raise SystemExit(f'{slug}: not a live post (needs its outlet\'s reader url + '
                             f'published_at in publish.yaml, and not a page)')
        return by[slug]

    if args.cmd == 'probe':
        name, spec = outlet_spec(args.outlets, args.outlet)
        pid = str(spec.get('notes_probe_draft_id') or '')
        print(json.dumps({'outlet': name, 'draft_id': pid or None, 'first_line': PROBE_LABEL,
                          'rule': 'private; reuse for probes; never post, never delete'},
                         indent=2, ensure_ascii=False))
        return 0 if pid else 1

    if args.cmd == 'status':
        for p in corpus:
            extra = p['posted_at'] or p['skip']
            print(f"  {p['published_at']}  {p['state']:8}  {p['slug']:36} {extra}")
        bl = backlog(corpus)
        counts = {s: sum(p['state'] == s for p in corpus) for s in ('posted', 'drafted', 'missing', 'skip')}
        print(f"\n{len(corpus)} live posts: " + ', '.join(f'{v} {k}' for k, v in counts.items()))
        done = backlog_done_today(corpus, today)
        if done:
            print(f"today's backlog Note is out ({done['slug']}); next one tomorrow")
        elif bl:
            print(f"next backlog Note: {bl[0]['slug']} ({bl[0]['state']})")
        if bl:
            print(f"backlog clears {(datetime.date.fromisoformat(today) + datetime.timedelta(days=len(bl) - (0 if done else 1))).isoformat()} at one a day")
        return 0

    if args.cmd == 'next':
        done = backlog_done_today(corpus, today)
        if done:
            print(f"today's backlog Note is already out: {done['slug']} ({done['note_url']})")
            return 3
        bl = backlog(corpus)
        if not bl:
            print('backlog clear')
            return 0
        p = bl[0]
        print(json.dumps({'slug': p['slug'], 'title': p['title'], 'url': p['url'],
                          'outlet': p['outlet'],
                          'published_at': p['published_at'], 'state': p['state'],
                          'remaining': len(bl)}, indent=2))
        return 0

    if args.cmd == 'text':
        if len(args.slugs) != 1:
            ap.error('text takes one slug')
        if args.post_url:
            # A SCHEDULED Note. The corpus only holds pieces that are already live, because a
            # Note has always followed a publication — but a scheduled post HAS ITS SLUG from
            # the moment it is scheduled (measured 2026-09-11: `slug` is null on a draft and
            # populated once `postSchedules` exists), so its public URL is knowable and the
            # Note can be scheduled beside it rather than posted by hand afterwards.
            d = os.path.join(args.pieces, os.path.basename(args.slugs[0].rstrip('/')))
            if not os.path.isdir(d):
                ap.error(f'no such piece: {args.slugs[0]}')
            man = read_manifest(os.path.join(d, 'publish.yaml'))
            p = {'slug': os.path.basename(d), 'dir': d,
                 'title': str(man.get('title') or '').strip().strip('"\''), 'url': args.post_url}
        else:
            p = piece(args.slugs[0])
        paras, problems = read_note(p['dir'], p['url'])
        if problems:
            print(f"{p['slug']}: " + '; '.join(problems), file=sys.stderr)
            return 1
        print(json.dumps({'slug': p['slug'], 'title': p['title'], 'paragraphs': paras,
                          'sha256': note_hash(paras), 'js': composer_js(paras, p['title'])},
                         indent=2, ensure_ascii=False))
        return 0

    if args.cmd == 'task':
        if len(args.slugs) != 1:
            ap.error('task takes one slug')
        if not args.post_url:
            ap.error('task needs --post-url (a scheduled post has its slug already)')
        d = os.path.join(args.pieces, os.path.basename(args.slugs[0].rstrip('/')))
        if not os.path.isdir(d):
            ap.error(f'no such piece: {args.slugs[0]}')
        print(cmd_task(os.path.basename(d), d, args.post_url,
                       args.at or 'the moment in publish.yaml',
                       os.path.dirname(os.path.abspath(args.pieces))))
        return 0

    if args.cmd == 'record':
        if len(args.slugs) != 1:
            ap.error('record takes one slug')
        p = piece(args.slugs[0])
        pid, handle = config(args, p['outlet'])         # the PIECE's profile, not the desk's first
        if args.url:
            url = normalize_note_url(args.url, handle or 'unknown')
        else:
            # No URL given: take it from the PUBLIC feed, which is the evidence the Note
            # exists at all. Exactly one Note must name the post, or nothing is written.
            if not pid:
                ap.error('no --url and no profile id to read the feed with')
            try:
                found = match_notes([p], fetch_notes(pid)).get(p['slug'], [])
            except (urllib.error.URLError, OSError, ValueError) as e:
                print(f'could not read the notes feed: {e}', file=sys.stderr)
                return 2
            if len(found) != 1:
                print(f"{p['slug']}: the feed has {len(found)} Notes naming this post {found}; "
                      "pass --url to say which", file=sys.stderr)
                return 1
            url = normalize_note_url(str(found[0]), handle or 'unknown')
        date = args.date or today
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
            ap.error('--date is YYYY-MM-DD')
        record(p['dir'], date, url)
        kind = 'fresh' if date == p['published_at'] else 'backlog'
        print(f"recorded {p['slug']}: {url} ({date}, {kind})")
        return 0

    if args.cmd == 'verify':
        scope = [piece(s) for s in args.slugs] if args.slugs else corpus
        # ONE FEED PER PROFILE, and a desk can have two. Grouping by the piece's own outlet is
        # what makes a cross-publication sweep possible at all: checking every piece against one
        # profile's feed would report the other publication's recorded Notes as MISSING and its
        # unrecorded ones as fine — both answers wrong, and both confidently.
        groups = {}
        for p in scope:
            groups.setdefault(p['outlet'], []).append(p)
        hits, notes, unread = {}, [], []
        for outlet, members in groups.items():
            pid, _handle = config(args, outlet)
            if not pid:
                unread.append((outlet, 'no notes_profile_id in outlets.yaml (or --profile)', members))
                continue
            try:
                feed = fetch_notes(pid)
            except (urllib.error.URLError, OSError, ValueError) as e:
                unread.append((outlet, f'could not read the feed: {e}', members))
                continue
            notes += feed
            hits.update(match_notes(members, feed))
        if unread and len(unread) == len(groups):
            for outlet, why, _m in unread:
                print(f'{outlet or "(no outlet)"}: {why}', file=sys.stderr)
            return 2
        bad = 0
        for outlet, why, members in unread:
            bad += 1
            print(f"  UNREAD      {outlet or '(no outlet)'}  {why} "
                  f"({len(members)} piece(s) unchecked)")
        scope = [p for p in scope if p['outlet'] not in {o for o, _w, _m in unread}]
        for p in scope:
            found = hits.get(p['slug'], [])
            rec = re.search(r'c-(\d+)', p['note_url'] or '')
            if p['state'] == 'posted':
                if rec and int(rec.group(1)) in found:
                    print(f"  ok          {p['slug']}  c-{rec.group(1)}")
                else:
                    bad += 1
                    print(f"  MISSING     {p['slug']}  recorded {p['note_url']}, feed has {found or 'none'}")
                if len(found) > 1:
                    print(f"  DUPLICATE   {p['slug']}  {len(found)} Notes name this post: {found}")
            elif found:
                bad += 1
                print(f"  UNRECORDED  {p['slug']}  feed has {found}; run `record` with that id")
        feeds = ', '.join(o or '(no outlet)' for o in groups if o not in {u[0] for u in unread})
        print(f"\n{len(notes)} Notes across {len(groups) - len(unread)} profile(s) [{feeds}]; "
              f"{sum(p['state'] == 'posted' for p in scope)} recorded in scope")
        return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
