#!/usr/bin/env python3
"""dashboard.py — stop DASHBOARD.md being a shared singleton that the last writer wins.

THE PROBLEM (measured 2026-09-02).  `DASHBOARD.md` is one file holding ~27 independent blocks,
each owned by exactly one piece.  Six sessions were running against the desk at once; every one
of them read the whole file, edited its own block, and wrote the whole file back.  The last
write won and the others vanished without an error, a conflict, or a trace.  It happened three
times to one block in a single afternoon, and it was noticed only because somebody re-grepped.

THE FIX is not locking and not merging.  It is REMOVING THE SHARED FILE FROM THE WRITE PATH.
Each block becomes its own file under `DASHBOARD.d/`, owned by one piece.  `DASHBOARD.md` is
then GENERATED — it stays committed, because it is what a human reads and what the instructions
point at, but nothing edits it directly any more.  Two sessions writing two different pieces now
touch two different files and cannot collide at all.  This is the desk's own principle applied
one level down: the README is truth and the dashboard is a summary, so the summary should be
derived rather than authored.

THE PART THAT IS EASY TO GET WRONG, and the reason `ingest` exists.  During the changeover —
and any time a session that has not learned the new layout edits `DASHBOARD.md` by hand — a
blind `render` would overwrite that hand edit and reintroduce exactly the silent data loss this
tool exists to end.  So the default is not `render`, it is `sync`: INGEST FIRST (pull any
hand-edit in `DASHBOARD.md` back down into its fragment), THEN render.  A generator that can
destroy hand-written work is not an improvement on the problem it replaces.

AND THE INVERSE, WHICH INTEGRATION TESTING CAUGHT AFTER THE UNIT TESTS PASSED.  A first version
of `ingest` assumed `DASHBOARD.md` was always the newer side, so running the DOCUMENTED workflow
— edit your fragment, then `sync` — silently reverted the fragment from the older generated
file.  The tool destroyed exactly the work it had just told you to do.  So ingest is decided
PER BLOCK BY MTIME: `DASHBOARD.md` newer than the fragment means a hand edit worth pulling down;
a fragment newer than `DASHBOARD.md` means the normal workflow, and it is left alone.  Whichever
side was written last is the side that wins, which is the only rule that is right in both
directions.

    dashboard.py split    one-time: explode DASHBOARD.md into DASHBOARD.d/
    dashboard.py ingest   pull hand-edits in DASHBOARD.md back into fragments
    dashboard.py render   fragments -> DASHBOARD.md   (atomic)
    dashboard.py sync     ingest, then render   [default]
    dashboard.py check    exit 1 if DASHBOARD.md differs from the fragments

`ingest` and `sync` take `--dry-run`: every decision is printed and no file is written.

ORDERING carries no shared state on purpose.  It lives in the filename (`NNN-slug.md`, gaps of
ten), so adding a piece creates one new file and edits nothing.  An explicit order file would
just be the singleton again, one indirection away.

TWO WAYS THE ABOVE STILL LOST DATA, both measured on the real desk 2026-09-30, both now closed.

(1) A FRAGMENT WITH NO HEADING MAKES INGEST APPEND FOREVER.  `render` is a concatenation, so a
fragment that does not open with its own `## ` heading has its text absorbed into the PREVIOUS
fragment's block in `DASHBOARD.md`.  `ingest` then reads that block, sees it differ from the
previous fragment, and writes the merged text down — so the headless fragment's content is now
in two fragments, and the next `render` emits it twice, and the next `ingest` banks the two.
`290-none-but-he-and-i.md` reached 86 committed copies of a block belonging to
`not-made-of-things-that-appear` this way, growing by one on every sync, across many sessions.
The tell was in the output all along: `ingest: 1 fragment(s) absent from DASHBOARD.md and KEPT`
— a fragment cannot be absent from a file that is generated from it unless its text arrived
under somebody else's heading.  The same shape applies to a slug held by TWO fragments (the desk
has two `in-vain.md`), where `ingest` cannot tell which block belongs to which file and would
write both blocks into whichever fragment the dict kept.

So ingest is now ADDRESS-CHECKED: a block is written down only when the mapping between blocks
and fragments is one-to-one for that slug.  Anything else — a block rendered from more than one
fragment, a slug held by more than one fragment, a slug appearing in more than one block — is
UNADDRESSABLE and left strictly alone, named in the output with the remedy.  Merging is the one
operation that cannot be undone by hand here, so the tool declines to guess.

(2) MTIME IS NOT PROVENANCE IN A GIT CHECKOUT.  Deciding per block by mtime is right in a live
working tree and meaningless the moment the files are checked out: `git` stamps every file with
the checkout time, in whatever order it wrote them.  On a clean clone of the desk that made
`DASHBOARD.md` look newer than fragments committed six hours after it, and ingest duly reverted
them — `400-two-ways-to-lose-yourself.md` from v2.4 back to v2.3, and
`380-scaling-computer-vision-workflows-aws.md` from live-on-three-outlets back to unpublished.
That is the original bug exactly: a stale whole-file read overwriting somebody's newer work.

So each side's age now comes from the repository's own record when the file is CLEAN (the commit
time of the last commit that touched it) and from mtime only when it is DIRTY or untracked — the
one state in which mtime is the newer fact.  A tie is not evidence, so a tie keeps the fragment.
And every overwrite ingest is about to make is PRINTED, with the lines it drops, so a session
watching a sync can stop it; `--dry-run` decides and writes nothing.
"""
import os, re, subprocess, sys

FRAGDIR = 'DASHBOARD.d'
DASHBOARD = 'DASHBOARD.md'
BLOCK_RE = re.compile(r'^## ', re.M)


def instance_root(start=None):
    cur = os.path.abspath(start or os.environ.get('DESK_INSTANCE') or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(cur, DASHBOARD)) or os.path.isdir(os.path.join(cur, FRAGDIR)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def slug_of(heading):
    """`## hearing-firsthand *(title **Secondhand**)*` -> `hearing-firsthand`.

    The slug is the stable identity and the title is not — a piece was retitled twice in one
    afternoon while another session held stale references to it.  Fragments are named by slug
    for that reason, so a retitle rewrites a file's CONTENT and never its name.
    """
    text = heading[3:].strip()
    m = re.match(r'([a-z0-9][a-z0-9._-]*)', text)
    # A real slug is lowercase-and-hyphens; a prose heading ("Books") is not, and must be
    # slugified rather than passed through — otherwise the fragment for `## Books` is named
    # `Books` and sorts and compares differently from every other fragment on the shelf.
    if m and (len(text) == len(m.group(1)) or text[len(m.group(1))] in ' *('):
        return m.group(1)
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') or 'section'


def parse(text):
    """-> (preamble, [(slug, block_text), ...]).  Block text keeps its heading and trailing \n."""
    starts = [m.start() for m in BLOCK_RE.finditer(text)]
    if not starts:
        return text, []
    preamble = text[:starts[0]]
    blocks = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[s:e]
        blocks.append((slug_of(chunk.split('\n', 1)[0]), chunk))
    return preamble, blocks


def frag_path(root, num, slug):
    return os.path.join(root, FRAGDIR, '%03d-%s.md' % (num, slug))


def fragments(root):
    """-> [(num, slug, path)] in render order."""
    d = os.path.join(root, FRAGDIR)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        m = re.match(r'^(\d{3})-(.+)\.md$', fn)
        if m:
            out.append((int(m.group(1)), m.group(2), os.path.join(d, fn)))
    return sorted(out, key=lambda t: (t[0], t[1]))


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = '%s.tmp%d' % (path, os.getpid())
    with open(tmp, 'w') as fh:
        fh.write(text)
    os.replace(tmp, path)


def _norm(s):
    """Fragments are stored VERBATIM — this only guarantees a trailing newline.

    An earlier version normalized to exactly one trailing newline and re-joined blocks with a
    blank line.  On the fixture that round-tripped perfectly; on the real dashboard it did not,
    because the live file separates some blocks by a blank line and others by none, and the
    normalizer flattened all of them.  The result would have been a first render that reflowed
    the entire document — not data loss, but a diff nobody asked for, in the one file this
    change exists to stop churning.  So: keep the bytes, and only ensure a block cannot run
    into the next one's heading.
    """
    return s if s.endswith('\n') else s + '\n'


# ----------------------------------------------------------------- addressing
# `render` is a concatenation, so the map from fragments to the blocks of DASHBOARD.md is only
# one-to-one while every non-preamble fragment opens with its own `## ` heading and no slug is
# held twice.  Where it is not, `ingest` has no way to tell whose text a block is, and writing
# it down merges two pieces' work into one file.  These two functions are what lets ingest say
# "I cannot address this" instead of guessing.

PREAMBLE = 'preamble'


def render_spans(root):
    """-> (rendered_text, [(start, end, fragment_path), ...]) — render, plus who wrote what.

    Exactly `render_text`'s bytes, with the provenance kept, so a block's owners are read off
    the offsets rather than inferred from the fragments' shape.
    """
    parts, spans, off = [], [], 0
    for _num, _slug, path in fragments(root):
        with open(path) as fh:
            chunk = _norm(fh.read())
        parts.append(chunk)
        spans.append((off, off + len(chunk), path))
        off += len(chunk)
    return ''.join(parts), spans


def unaddressable(root, live_text=None):
    """-> {slug: reason} for every slug ingest must not write, and why.

    Three shapes, all of them the same fault — the address is not unique:

      * a rendered block drawing on more than one fragment (a fragment with no `## ` heading of
        its own, whose text lands inside its neighbour's block),
      * a slug held by more than one fragment,
      * a slug appearing in more than one block of the live DASHBOARD.md.
    """
    bad = {}

    frags = fragments(root)
    seen = {}
    for _num, slug, path in frags:
        seen.setdefault(slug, []).append(path)
    for slug, paths in seen.items():
        if len(paths) > 1:
            bad[slug] = ('held by %d fragments (%s) — ingest cannot tell which block is which'
                         % (len(paths), ', '.join(os.path.basename(x) for x in paths)))

    text, spans = render_spans(root)
    starts = [m.start() for m in BLOCK_RE.finditer(text)]
    regions = [(PREAMBLE, 0, starts[0] if starts else len(text))]
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        regions.append((slug_of(text[s:e].split('\n', 1)[0]), s, e))
    for slug, s, e in regions:
        owners = [path for a, b, path in spans if a < e and b > s and b > a]
        if len(owners) > 1:
            names = [os.path.basename(x) for x in owners]
            headless = [n for n in names[1:]]
            bad[slug] = ('rendered from %d fragments (%s) — %s open%s no `## ` heading, so their '
                         'text lands inside this block' %
                         (len(owners), ', '.join(names), ', '.join(headless),
                          's' if len(headless) == 1 else ''))

    if live_text is not None:
        _pre, live_blocks = parse(live_text)
        counts = {}
        for slug, _chunk in live_blocks:
            counts[slug] = counts.get(slug, 0) + 1
        for slug, n in counts.items():
            if n > 1:
                bad[slug] = '%d blocks with this slug in %s — the address is not unique' % (n, DASHBOARD)
    return bad


def headless_fragments(root):
    """-> [path] for non-preamble fragments that do not open with a `## ` heading."""
    out = []
    for _num, slug, path in fragments(root):
        if slug == PREAMBLE:
            continue
        with open(path) as fh:
            if not fh.read().lstrip('\n').startswith('## '):
                out.append(path)
    return out


# ------------------------------------------------------------------ provenance
# Which side of a block is the NEWER one?  In a live working tree that is mtime.  In a fresh
# checkout it is not: git stamps every file with the checkout time, so mtime says only in which
# order git happened to write them.  Reading it there reverted fragments committed hours after
# DASHBOARD.md.  So: a CLEAN file's age is the commit time of the last commit that touched it —
# the repository's own record, which survives a clone — and mtime is used only for a file that
# is dirty or untracked, the one state in which mtime is the newer fact.

# Every git HOOK runs with GIT_DIR and GIT_WORK_TREE already set, and those OVERRIDE `-C <dir>`
# — so a `dashboard.py sync` invoked from a hook (or from anything a hook started, the pre-push
# CI run included) would read the ambient repository's history instead of the desk's, and decide
# which side of a block is newer from the wrong record.  Caught 2026-09-30 by the framework's own
# pre-push hook, whose exported CI run had GIT_DIR pointing at the submodule.  So the environment
# is cleared of everything that can redirect a repository, and `-C root` is left as the only
# thing saying which repository this is.
_GIT_REDIRECTS = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
                  'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_NAMESPACE',
                  'GIT_CEILING_DIRECTORIES', 'GIT_PREFIX')


def git_env(base=None):
    """A copy of the environment with every repository-redirecting GIT_* variable removed."""
    env = dict(os.environ if base is None else base)
    for var in _GIT_REDIRECTS:
        env.pop(var, None)
    return env


def _git(root, args):
    try:
        r = subprocess.run(['git', '-C', root] + args, capture_output=True, text=True,
                           timeout=30, env=git_env())
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def provenance(root, paths=(DASHBOARD, FRAGDIR)):
    """-> (commit_times, dirty) keyed by repo-relative path; ({}, set()) outside a checkout."""
    out = _git(root, ['log', '--format=@%ct', '--name-only', '--'] + list(paths))
    if out is None:
        return {}, set()
    times, when = {}, None
    for line in out.splitlines():
        if line.startswith('@'):
            when = int(line[1:])
        elif line.strip() and when is not None:
            times.setdefault(line.strip(), when)      # --name-only is newest-first
    dirty = set()
    st = _git(root, ['status', '--porcelain', '--'] + list(paths))
    for line in (st or '').splitlines():
        if len(line) > 3:
            dirty.add(line[3:].split(' -> ')[-1].strip().strip('"'))
    return times, dirty


def age_of(root, path, times, dirty):
    """The time to compare this side on, or None if the file is not there."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace(os.sep, '/')
    if rel in dirty or rel not in times:
        return mtime                                  # uncommitted: mtime is the newer fact
    return float(times[rel])                          # committed and clean: the repo's record


def _dropped_lines(old, new):
    keep = set(new.splitlines())
    return [l for l in old.splitlines() if l.strip() and l not in keep]


def do_split(root, force=False):
    path = os.path.join(root, DASHBOARD)
    with open(path) as fh:
        text = fh.read()
    preamble, blocks = parse(text)
    existing = fragments(root)
    if existing and not force:
        sys.stderr.write('dashboard: %s already has %d fragments; --force to re-split\n'
                         % (FRAGDIR, len(existing)))
        return 1
    _atomic_write(frag_path(root, 0, 'preamble'), _norm(preamble))
    n = 0
    for slug, chunk in blocks:
        n += 10
        _atomic_write(frag_path(root, n, slug), _norm(chunk))
    print('split %s -> %d fragments in %s/' % (DASHBOARD, len(blocks) + 1, FRAGDIR))
    return 0


def render_text(root):
    parts = []
    for _num, _slug, path in fragments(root):
        with open(path) as fh:
            parts.append(_norm(fh.read()))
    return ''.join(parts)      # exact concatenation: the separators live IN the fragments


def do_render(root, quiet=False):
    frags = fragments(root)
    if not frags:
        sys.stderr.write('dashboard: no fragments in %s/ — run `dashboard.py split` first\n' % FRAGDIR)
        return 2
    out = render_text(root)
    path = os.path.join(root, DASHBOARD)
    old = open(path).read() if os.path.isfile(path) else None
    if old == out:
        if not quiet:
            print('render: %s already current (%d fragments)' % (DASHBOARD, len(frags)))
        return 0
    _atomic_write(path, out)
    if not quiet:
        print('render: wrote %s from %d fragments' % (DASHBOARD, len(frags)))
    return 0


def do_ingest(root, quiet=False, dry_run=False):
    """Pull hand-edits made directly in DASHBOARD.md back down into the fragments.

    This is what makes the changeover safe, and it stays useful afterwards: any session or
    editor that has not learned the new layout will keep editing the generated file, and their
    work has to survive that.  A block with no fragment is a NEW piece and gets one.  A fragment
    with no block is reported and NEVER deleted — the absence may just mean the other side is
    stale, and deleting somebody's block on that guess is the original bug wearing a new hat.

    Two refusals stand in front of every write, and both exist because the write happened:

      * UNADDRESSABLE — the block-to-fragment map is not one-to-one for this slug, so the block
        is some other piece's text as well.  Writing it down merges them, and the merge feeds
        itself on every later sync.  Never written; always named.
      * the fragment is the NEWER side, judged on the repository's record for a clean file and
        on mtime only for a dirty one.  mtime alone said DASHBOARD.md was newer in a fresh
        checkout, where it is only the file git wrote last.

    Whatever survives both is printed before it is written, with the lines it drops.
    """
    path = os.path.join(root, DASHBOARD)
    if not os.path.isfile(path):
        return 0

    with open(path) as fh:
        live = fh.read()
    preamble, blocks = parse(live)
    frags = fragments(root)
    by_slug = {slug: (num, p) for num, slug, p in frags}

    blocked = unaddressable(root, live)
    times, dirty = provenance(root)
    dash_age = age_of(root, path, times, dirty)

    def dashboard_is_newer(frag):
        """Is DASHBOARD.md the newer side for this block?  A tie is not evidence: keep the
        fragment, because a merge is the loss that cannot be undone by hand."""
        frag_age = age_of(root, frag, times, dirty)
        if frag_age is None:
            return True                      # no fragment yet: the dashboard is all there is
        if dash_age is None:
            return False
        return dash_age > frag_age + 1e-6

    changed, added, kept, refused, overwrites = [], [], [], [], []

    pre_num, pre_path = by_slug.get(PREAMBLE, (0, frag_path(root, 0, PREAMBLE)))
    have_pre = os.path.isfile(pre_path)
    if PREAMBLE in blocked:
        if have_pre and _norm(open(pre_path).read()) != _norm(preamble):
            refused.append(PREAMBLE)
    elif dashboard_is_newer(pre_path) and (not have_pre
                                           or _norm(open(pre_path).read()) != _norm(preamble)):
        if have_pre:
            overwrites.append((PREAMBLE, pre_path, _dropped_lines(open(pre_path).read(), preamble)))
        if not dry_run:
            _atomic_write(pre_path, _norm(preamble))
        changed.append(PREAMBLE)

    nxt = (max([n for n, _, _ in frags], default=0) // 10 + 1) * 10
    for slug, chunk in blocks:
        if slug in by_slug:
            _num, p = by_slug[slug]
            current = open(p).read()
            if _norm(current) == _norm(chunk):
                continue
            if slug in blocked:
                refused.append(slug)           # the address is not unique — never merge on a guess
            elif dashboard_is_newer(p):
                overwrites.append((slug, p, _dropped_lines(current, chunk)))
                if not dry_run:
                    _atomic_write(p, _norm(chunk))
                changed.append(slug)
            else:
                kept.append(slug)              # the fragment is the newer side: the normal workflow
        elif slug in blocked:
            refused.append(slug)
        else:
            if not dry_run:
                _atomic_write(frag_path(root, nxt, slug), _norm(chunk))
            added.append(slug)
            nxt += 10

    seen = {s for s, _ in blocks} | {PREAMBLE}
    orphans = [s for _n, s, _p in frags if s not in seen]
    headless = headless_fragments(root)
    if not quiet:
        tag = 'ingest (dry run): would update' if dry_run else 'ingest: updated'
        if changed or added:
            print('%s %d, add%s %d  (%s)' %
                  (tag, len(changed), 'ed' if not dry_run else '', len(added),
                   ', '.join(changed + ['+' + a for a in added])))
        else:
            print('ingest: nothing to pull down from %s' % DASHBOARD)
        for slug, p, dropped in overwrites:
            print('ingest: %s %s from %s  (%d line(s) dropped)'
                  % ('WOULD OVERWRITE' if dry_run else 'OVERWROTE',
                     os.path.relpath(p, root), DASHBOARD, len(dropped)))
            for line in dropped[:3]:
                print('           - %s' % (line[:140] + ('…' if len(line) > 140 else '')))
            if len(dropped) > 3:
                print('           - … %d more' % (len(dropped) - 3))
        if kept:
            print('ingest: %d fragment(s) newer than %s, kept: %s'
                  % (len(kept), DASHBOARD, ', '.join(kept)))
        if refused:
            print('ingest: %d block(s) REFUSED — the address is not unique, so nothing was written:'
                  % len(refused))
            for slug in refused:
                print('  %s: %s' % (slug, blocked[slug]))
        if headless:
            print('ingest: %d fragment(s) with NO `## ` HEADING — give each one its own heading '
                  'so it renders as its own block:' % len(headless))
            for p in headless:
                print('  %s' % os.path.relpath(p, root))
        if orphans:
            print('ingest: %d fragment(s) absent from %s and KEPT: %s'
                  % (len(orphans), DASHBOARD, ', '.join(orphans)))
    return 0


def do_check(root):
    frags = fragments(root)
    if not frags:
        sys.stderr.write('dashboard: no fragments to check\n')
        return 2
    path = os.path.join(root, DASHBOARD)
    live = open(path).read() if os.path.isfile(path) else ''
    if live == render_text(root):
        print('check: %s matches its %d fragments' % (DASHBOARD, len(frags)))
        return 0
    _, live_blocks = parse(live)
    live_by = dict(live_blocks)
    drift = []
    for _n, slug, p in frags:
        if slug == 'preamble':
            continue
        want = _norm(open(p).read())
        got = _norm(live_by.get(slug, ''))
        if slug not in live_by:
            drift.append('%s: MISSING from %s' % (slug, DASHBOARD))
        elif want != got:
            drift.append('%s: differs' % slug)
    for slug in live_by:
        if slug not in {s for _n, s, _p in frags}:
            drift.append('%s: in %s with no fragment' % (slug, DASHBOARD))
    print('check: %s DIFFERS from its fragments' % DASHBOARD)
    for d in drift or ['(whitespace/ordering only)']:
        print('  ' + d)
    for pth in headless_fragments(root):
        print('  %s: NO `## ` HEADING — its text renders inside the previous block, so it reads '
              'to `ingest` as that block\'s and cannot round-trip' % os.path.relpath(pth, root))
    for slug, why in sorted(unaddressable(root, live).items()):
        print('  %s: UNADDRESSABLE — %s' % (slug, why))
    print('run `dashboard.py sync` — it ingests hand-edits before rendering, so nothing is lost')
    return 1


def main(argv):
    if len(argv) > 1 and argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    cmd = argv[1] if len(argv) > 1 else 'sync'
    root = instance_root()
    dry = '--dry-run' in argv
    if cmd == 'split':
        return do_split(root, force='--force' in argv)
    if cmd == 'render':
        return do_render(root)
    if cmd == 'ingest':
        return do_ingest(root, dry_run=dry)
    if cmd == 'check':
        return do_check(root)
    if cmd == 'sync':
        rc = do_ingest(root, dry_run=dry)
        if dry:
            return rc                      # --dry-run decides and writes nothing, either side
        return rc or do_render(root)
    sys.stderr.write('dashboard: unknown command %r (split|ingest|render|sync|check)\n' % cmd)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
