#!/usr/bin/env python3
"""check_status.py — does the desk's PROSE still agree with its manifests?

Three tools already guard three other things, and a sentence can be wrong while all
three pass:

  check_links.py   a URL resolves.
  check_refs.py    a cross-reference names the right piece (titles move).
  outlet_audit.py  a piece exists on every outlet it declares (half-published).

None of them reads what the prose CLAIMS. This does.

WHY (2026-09-09, four times in one week)

  * *In Vain* — the founding-writings index and the charter both called it "composed as
    a private draft; unpublished". It had gone live that morning.
  * *The Mask Comes Off Last* — "unpublished", and carrying no link, five days after it
    published. The index was breaking its own stated rule, that live pieces link to
    their reader URL.
  * *Rising After Falls* — published by another session mid-afternoon; the index still
    called it unpublished an hour later. Found by the first run of this tool.
  * The charter still called the Fellowship's domain "open, and Eric's call" after the
    site had shipped. See the limits below: this one is not mechanically visible.

AND THE SHAPE THE PHRASE LIST COULD NOT SEE (2026-10-11), which is why `stage` exists

  * *In Vain* again. `DASHBOARD.d/278-in-vain.md` read "stood up 2026-09-03 … Nothing
    drafted" for TWENTY-FOUR DAYS after publication — while the same file, four lines
    further down, carried **PUBLISHED 2026-09-09** and the reader URL. Nothing was
    contradicted: the file's append-only history was right and only its HEAD was stale.
    "Nothing drafted" is a STRONGER claim than "unpublished" and matched none of the seven
    phrases. Turning `stage` on found five more in the same state — *False Light* (fragment
    and README), *The Towel*, *Love Is Not a Metric Space* (fragment and README), *The
    Kingdom That Isn't* — and no false positives. Two were READMEs, which this desk calls
    truth.

Every case has the same shape. `publish.yaml` is written by the sync tools against the
live post; the prose is written by hand. **The manifest is the witness**, and prose that
contradicts it is what this reports.

WHAT IT CHECKS

  stage        a live piece's `**Stage:**` line does not say it is published — checked only
               where the PATH names the piece (`DASHBOARD.d/NNN-<slug>.md`,
               `pieces/<slug>/README.md`). The only POSITIVE test here: the others look for a
               contradiction, and a Stage line can be wrong without contradicting anything.
  unpublished  prose calls a piece unpublished; its manifest carries a reader URL.
  phantom      prose links a piece as live; its manifest carries no reader URL at all.
  unlinked     a live piece is named with no link, against the house rule — reported
               only in files that STATE that rule, so it never fires on a document that
               never made the promise.
  address      with --prefer OUTLET, a piece linked at another outlet's URL when the
               preferred outlet has one. Use it after moving a publication's home.

WHAT IS DELIBERATELY NOT CHECKED, on check_refs.py's principle that a checker which
cries about correct files gets switched off:

  * `DASHBOARD.md`. It is generated from `DASHBOARD.d`; the fragments are checked instead,
    so a finding names the file you would actually edit.
  * `log/`, `corrections.md`, and everything under a dated heading. They are append-only
    records of what was true when written. An entry saying "unpublished" is accurate
    history, and "fixing" it would be editing the evidence.
  * Any line that marks its own supersession — retired, superseded, (was …), formerly,
    replaced. Naming an old state in order to retire it is the correct use of one.
  * Whether a DECISION has gone stale. The charter case above is real drift and this
    cannot see it: no file records that a decision was made, so there is nothing to
    disagree with. Only a person re-reading catches that, and it is worth saying plainly
    rather than implying the sweep is complete.

CONFIG (instance-side; the framework holds no URLs)

  --outlets publishing/outlets.yaml — the same registry outlet_audit.py reads. A piece
  is PUBLISHED if any outlet's `manifest_url_key` is set in its manifest, or if it still
  opts in the pre-outlets way with `site: true` and the registry names a legacy_outlet.

  A LIMIT OF `address`, worth knowing before trusting a clean run: it can only compare
  what the manifest records. A piece opting in the legacy way carries no outlet URL, so
  there is no preferred address to compare a link against and the check stays silent on
  it — silence there means "not checked", not "correct". At the time of writing 30 of 40
  pieces are in that state. `unpublished`, `phantom` and `unlinked` are unaffected: they
  only need to know whether an address exists, not what it is.

USAGE
  python3 check_status.py [path ...] [--pieces DIR] [--outlets FILE] [--prefer OUTLET]

EXIT
  0  the prose agrees with the manifests
  1  usage / nothing could be checked
  4  at least one disagreement — each named with file, line, and what the manifest says
"""
import argparse
import os
import re
import sys

try:
    import yaml
except ImportError:
    yaml = None

SKIP_DIR_PARTS = ('/log/', '/.git/', '/node_modules/', '/__pycache__/', '/.next/', '/out/')
# DASHBOARD.md is GENERATED from DASHBOARD.d by dashboard.py, so a claim in it is a copy
# of a claim in a fragment. Checking both reports every finding twice and points the
# second one at a file that will be overwritten. The fragments are checked; the build
# output is not, for the same reason nothing lints a build output.
SKIP_FILES = ('corrections.md', 'DASHBOARD.md')
FRAGDIR_NAME = 'DASHBOARD.d'      # the fragments ARE checked; only the build output is not

SUPERSESSION = re.compile(
    r'retired|supersed|formerly|\bwas\b\s*[:"“]|\(was\b|replaced|previously|no longer|'
    r'what this replaced|until \d{4}-\d{2}-\d{2}', re.I)

LOG_HEADING = re.compile(r'^#{1,6}\s+\d{4}-\d{2}-\d{2}\b')

UNPUBLISHED = re.compile(
    r'\bunpublished\b|\bnot yet published\b|\bprivate draft\b|\bnot published\b|'
    r'\bunreleased\b|\bdraft only\b|\bawaiting publication\b|'
    r"\bawaiting (?:a human |Eric's )?publish\b", re.I)

# THE STAGE LINE, which is a different question from the prose check below and needs a
# different kind of answer.  `UNPUBLISHED` is a list of seven phrases, and it only ever sees a
# CONTRADICTION: prose that says one of those words about a piece the manifest calls live.  A
# `**Stage:**` line can be wrong without using any of them.  Measured 2026-10-11 on
# `DASHBOARD.d/278-in-vain.md`: for twenty-four days its Stage line read *stood up 2026-09-03 …
# Nothing drafted* while the same file, four lines further down, carried **PUBLISHED 2026-09-09**
# and the reader URL.  Nothing was contradicted and nothing was missing — the file's own
# append-only history was right and its HEAD was stale, which is the one shape a phrase list
# cannot see.  "Nothing drafted" is a stronger claim than "unpublished" and matched none of them.
#
# So this check is POSITIVE rather than negative: where the path says which piece a Stage line is
# about, a live piece's Stage line has to ASSERT the publication rather than merely avoid denying
# it.  The path is what makes it safe — `DASHBOARD.d/NNN-<slug>.md` and `pieces/<slug>/README.md`
# are the two places where a `**Stage:**` line belongs to exactly one piece, so there is no
# guessing about the subject and no block-proximity heuristic to get wrong.
STAGE = re.compile(r'^\*\*Stage:\*\*\s*(.*)$', re.M)
FRAGMENT_NAME = re.compile(r'^(\d{3})-(.+)\.md$')
# Deliberately NOT a verb: "Eric clicks Publish" is a Stage line AWAITING publication, and must
# not read as asserting one.  `\bpublished\b` does not match it; neither does `\blive\b` match
# "lives".  A Stage line that says "not published" asserts by this test and is then caught by
# UNPUBLISHED, which is the check built for a contradiction — the two cover different faults.
PUBLICATION_ASSERTED = re.compile(r'\bpublished\b|\blive\b|\bshipped\b|\bre-?synced\b', re.I)

SLUG_REF = re.compile(r'`([a-z0-9][a-z0-9-]{2,})`')
MD_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')
RULE_STATED = re.compile(r'live pieces link to their reader url', re.I)


def load_outlets(path):
    if not path or not os.path.exists(path):
        return {}, None
    cfg = yaml.safe_load(open(path).read()) or {}
    return cfg.get('outlets') or {}, cfg.get('legacy_outlet')


def reader_urls(man, outlets, legacy):
    """{outlet: url} for every outlet this piece actually has an address on."""
    out = {}
    for name, spec in outlets.items():
        key = (spec or {}).get('manifest_url_key')
        val = man.get(key) if key else None
        if val:
            out[name] = str(val).rstrip('/')
    if not out and man.get('site') is True and legacy:
        # Pre-outlets opt-in: it says the piece goes to the legacy outlet, but records no
        # URL, so there is no address to compare a link against — only the fact of it.
        out[legacy] = None
    return out


DEFAULT_URL_KEY = 'public_url'


def live_url(man, outlets, legacy=None):
    """-> the ONE reader URL that names this piece, by ITS OWN outlet's manifest key, or ''.

    `reader_urls` answers "every address this piece has"; this answers the narrower question
    a dozen call sites actually ask — *is it live, and where does a human go* — and it is
    here rather than in each of them because each of them answered it by reading
    `public_url`, which is ONE outlet's key (`substack`, Being Good) and not a universal one.
    outlets.yaml has said EACH OUTLET GETS ITS OWN MANIFEST KEY since the professional line
    was added; substack_verify and substack_notes learned it on 2026-09-11 (scriptorium
    c1e192f) and these did not, so a whole second publication read as *not published* to the
    corpus gates, the required-outlets rule, the header check and the baseline check alike.

    A `site: true` opt-in is deliberately NOT live here: it records that a piece goes
    somewhere, not an address, and every caller of this wants the address. Hence legacy=None
    by default — pass one only if a bare opt-in should count.

    The piece's own `canonical:` wins when it records one, because that is the piece SAYING
    which of its addresses is home; otherwise the first outlet in registry order that it has
    an address on. A desk with no registry keeps `public_url`, which is what a one-outlet
    desk has always written and what the fixtures are.
    """
    if not outlets:
        return str(man.get(DEFAULT_URL_KEY) or '').rstrip('/')
    urls = reader_urls(man, outlets, legacy)
    urls = {k: v for k, v in urls.items() if v}
    if not urls:
        return ''
    canon = str(man.get('canonical') or '').rstrip('/')
    if canon in set(urls.values()):
        return canon
    return next(iter(urls.values()))


def outlets_for(root, path=None):
    """(outlets, legacy) for a desk root — its `publishing/outlets.yaml` unless one is named.
    ({}, None) when the desk has none, which is the one-outlet case `live_url` falls back for."""
    return load_outlets(path or os.path.join(root, 'publishing', 'outlets.yaml'))


def load_manifests(pieces_dir, outlets, legacy):
    got = {}
    if not os.path.isdir(pieces_dir):
        return got
    for name in sorted(os.listdir(pieces_dir)):
        p = os.path.join(pieces_dir, name, 'publish.yaml')
        if not os.path.exists(p):
            continue
        try:
            man = yaml.safe_load(open(p).read()) or {}
        except Exception:
            continue
        got[name] = {'urls': reader_urls(man, outlets, legacy), 'title': man.get('title')}
    return got


def markdown_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'node_modules']
            for f in files:
                if not f.endswith('.md') or f in SKIP_FILES:
                    continue
                full = os.path.join(root, f)
                if any(s in full.replace(os.sep, '/') for s in SKIP_DIR_PARTS):
                    continue
                yield full


def stage_subject(path, manifests):
    """-> the slug a `**Stage:**` line in this file is about, from the PATH, or None.

    Only two shapes qualify, because only in those does the path name one piece with no
    inference: a dashboard fragment `DASHBOARD.d/NNN-<slug>.md`, and a piece's own
    `pieces/<slug>/README.md`.  Anywhere else a Stage line could be about anything, and a
    checker that guesses its subject is the checker that cries about correct files.
    """
    norm = path.replace(os.sep, '/')
    base = os.path.basename(norm)
    parts = norm.split('/')
    slug = None
    if '/%s/' % FRAGDIR_NAME in '/' + norm:
        m = FRAGMENT_NAME.match(base)
        if m:
            slug = m.group(2)
    elif base == 'README.md' and len(parts) >= 3 and parts[-3] == 'pieces':
        slug = parts[-2]
    return slug if slug in manifests else None


def head_text(text):
    """Everything above the first dated heading — below it is history, as everywhere else here."""
    out = []
    for ln in text.split('\n'):
        if LOG_HEADING.match(ln):
            break
        out.append(ln)
    return '\n'.join(out)


def stage_findings(path, text, slug, man):
    """A live piece's Stage line must SAY SO.  -> [(line_no, kind, slug, what)]"""
    head = head_text(text)
    m = STAGE.search(head)
    if not m:
        return []                      # no Stage line is not a claim; nothing to check
    line_no = head[:m.start()].count('\n') + 1
    stage = m.group(1)
    if SUPERSESSION.search(stage):
        return []
    urls = [u for u in man['urls'].values() if u]
    if PUBLICATION_ASSERTED.search(stage) or any(u in stage for u in urls):
        return []
    where = ', '.join(f"{o}={u}" for o, u in man['urls'].items() if u) or \
            ', '.join(man['urls'])
    return [(line_no, 'stage', slug,
             f"the Stage line does not say this piece is published; manifest has {where}")]


def blocks(text):
    """(line_no, block) per bullet or paragraph.

    A claim and the slug it is about share a bullet, not a line — the index wraps its
    entries over three or four — so the bullet is the unit that has to be read. A dated
    heading switches off the rest of the file: below it is history."""
    out, cur, start = [], [], 1

    def flush():
        nonlocal cur
        if cur:
            out.append((start, '\n'.join(cur)))
            cur = []

    for i, ln in enumerate(text.split('\n'), 1):
        if LOG_HEADING.match(ln):
            break
        # A TABLE ROW IS ITS OWN BLOCK. These READMEs carry "seams" tables listing several
        # siblings, one per row. Treated as one paragraph, a single "unpublished" in any
        # row was attributed to every slug in the table — 60-odd false positives on the
        # first full sweep, which is exactly how a checker gets switched off.
        if ln.lstrip().startswith('|'):
            flush()
            out.append((i, ln))
            continue
        if (ln.startswith(('- ', '* ', '+ ')) or not ln.strip()) and cur:
            flush()
        if not ln.strip():
            continue
        if not cur:
            start = i
        cur.append(ln)
    flush()
    return out


def check(paths, pieces_dir, outlets_file, prefer):
    outlets, legacy = load_outlets(outlets_file)
    manifests = load_manifests(pieces_dir, outlets, legacy)
    if not manifests:
        print(f"error: no piece manifests under {pieces_dir}", file=sys.stderr)
        return None
    if prefer and prefer not in outlets:
        print(f"error: --prefer {prefer} is not an outlet in {outlets_file}", file=sys.stderr)
        return None

    findings = []
    for path in markdown_files(paths):
        try:
            text = open(path).read()
        except (OSError, UnicodeDecodeError):
            continue
        rule_here = bool(RULE_STATED.search(text))

        subject = stage_subject(path, manifests)
        if subject and manifests[subject]['urls']:
            for found in stage_findings(path, text, subject, manifests[subject]):
                findings.append((path, *found))

        for line_no, block in blocks(text):
            if SUPERSESSION.search(block):
                continue
            refs = [s for s in SLUG_REF.findall(block) if s in manifests]
            if not refs:
                continue
            links = MD_LINK.findall(block)

            for slug in refs:
                man = manifests[slug]
                urls = man['urls']
                live = bool(urls)

                if live and _claims_near(block, slug, UNPUBLISHED):
                    where = ', '.join(f"{o}={u}" for o, u in urls.items() if u) or \
                            ', '.join(urls)
                    findings.append((path, line_no, 'unpublished', slug,
                                     f"prose says unpublished; manifest has {where}"))
                    continue

                if not live and links:
                    title = man['title'] or ''
                    names_it = any(
                        _slugify(t.strip('*_ ')) in (slug, _slugify(title))
                        for t, _ in links)
                    if names_it:
                        findings.append((path, line_no, 'phantom', slug,
                                         "prose links it as live; manifest has no reader URL"))
                    continue

                if live and rule_here and not links:
                    findings.append((path, line_no, 'unlinked', slug,
                                     "live, and this file states that live pieces link "
                                     "to their reader URL"))
                    continue

                if prefer and live and links:
                    want = urls.get(prefer)
                    if not want:
                        continue
                    hrefs = [u.rstrip('/') for _t, u in links]
                    if want in hrefs:
                        continue
                    other = [(o, u) for o, u in urls.items()
                             if o != prefer and u and u in hrefs]
                    if other:
                        findings.append((path, line_no, 'address', slug,
                                         f"links {other[0][0]} ({other[0][1]}); "
                                         f"{prefer} is {want}"))
    return findings


# How far a claim can sit from the slug it is about and still be about it. An index entry
# puts them in the same sentence; the dashboard puts twenty slugs and one stray
# "unpublished" in a single 3,000-character block, and attributing that word to all twenty
# produced 57 false positives on the first full sweep. Proximity is what separates the two,
# and it is a better rule than excluding the file — the dashboard's claims are worth
# checking, just not at block scale.
NEAR = 320


SENT_SPLIT = re.compile(r'(?<=[.!?:])\s+(?=[A-Z*`\[(])')


def _sentences(block):
    """(offset, text) per sentence. Proximity alone attributes a claim to whatever slug
    happens to sit within NEAR characters, and in real prose the neighbour is often the
    OPPOSITE claim: `> All 13 substitutions are applied; four are unpublished drafts. **The
    six live posts are re-synced:** `nothing-to-get`, `the-dreamer`, ...` — six pieces named
    as LIVE, every one reported unpublished because the word sat 40 characters away. Same
    shape in a piece README: `three live posts with the same leak (`distinction`, ...) —
    re-syncs awaiting Eric's yes. Still a private draft awaiting Eric's Publish.` where the
    private draft is the piece doing the reporting, not the three it names.

    A claim and its subject share a SENTENCE. Splitting first keeps every true positive the
    block-and-proximity rule found and drops both of those."""
    out, pos = [], 0
    for part in SENT_SPLIT.split(block):
        out.append((pos, part))
        pos += len(part) + 1
    return out


def _claims_near(block, slug, pattern):
    """Does `pattern` match the same SENTENCE as a `slug` reference, and within NEAR
    characters of it? Sentence first, proximity second — a long sentence listing many
    slugs still needs the distance check."""
    ref_re = re.compile(r'`%s`' % re.escape(slug))
    for _off, sent in _sentences(block):
        refs = [m.start() for m in ref_re.finditer(sent)]
        if not refs:
            continue
        if any(abs(m.start() - r) <= NEAR
               for m in pattern.finditer(sent) for r in refs):
            return True
    return False


def _slugify(t):
    s = str(t).lower().replace('’', "'").replace("'", '')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--pieces', default='pieces')
    ap.add_argument('--outlets', default='publishing/outlets.yaml')
    ap.add_argument('--prefer', default=None)
    ap.add_argument('--quiet', action='store_true')
    o = ap.parse_args()
    if yaml is None:
        print("error: pyyaml is required", file=sys.stderr)
        return 1

    findings = check(o.paths or ['.'], o.pieces, o.outlets, o.prefer)
    if findings is None:
        return 1
    if not findings:
        if not o.quiet:
            print("ok  prose agrees with the manifests")
        return 0

    by_kind = {}
    for f in findings:
        by_kind.setdefault(f[2], []).append(f)
    for kind in sorted(by_kind):
        print(f"\n{kind}  ({len(by_kind[kind])})")
        for path, line, _k, slug, why in sorted(by_kind[kind]):
            print(f"  {path}:{line}  `{slug}`")
            print(f"      {why}")
    print(f"\n{len(findings)} disagreement(s). The manifest is the witness: it is written "
          f"by the sync\ntools against the live post; the prose is written by hand.")
    return 4


if __name__ == '__main__':
    sys.exit(main())
