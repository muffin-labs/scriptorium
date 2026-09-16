#!/usr/bin/env python3
"""publications.py — which publication each piece belongs to, and what a publication owns.

A desk can carry more than one publication: two audiences, two bylines, two sets of voices,
two places a reader subscribes. Without a name for that, membership lives in four places at
once — the outlets a piece declares, a "Book:" line in its README, the prefix of its style,
and which notes file about Substack applies — and anything that has to be kept APART per
publication (a tag vocabulary, a slug in a shared content store) has nothing to key on.

So a publication is a thing the desk names, in one registry, and each piece names its one.

    # publishing/publications.yaml (instance; override with --registry or $DESK_PUBLICATIONS)
    publications:
      being-good:                     # the id: lowercase, hyphenated, never shown to a reader
        name: Being Good              # what a reader subscribes to
        byline: E.L. Muffin
        outlets: [substack, alignmentfellowship]   # every outlet belongs to ONE publication
        projects: [being-good, all-my-stories]     # projects/<name>/ — the long projects it holds
        styles: [being-good-essay, being-good-journal]   # the voices it speaks in
        deity_conventions: true       # check_pronouns' deity sections apply to its texts
        # tags:  publishing/tags/being-good.yaml   # its tag vocabulary; this is the default
        # house: publishing/house/being-good.md    # its house rules; this is the default

    # styles/<name>/config.yaml
    publication: being-good           # the voice names its owner back; check holds the two equal

    # pieces/<slug>/publish.yaml
    publication: being-good

A DESK WITH ONE PUBLICATION NEEDS NO REGISTRY. Without the file every tool behaves as it
always did — one tag vocabulary at publishing/tags.yaml, and no piece is asked to name a
publication. The registry is what a desk adds the day a second publication arrives.

WHAT `check` HOLDS, once the registry exists:
  * every outlet belongs to at most one publication. A site reads the store by outlet, so an
    outlet shared by two publications is a site showing both.
  * every manifest names a publication the registry defines.
  * every outlet a piece declares belongs to that publication.
  * OWNERSHIP BOTH WAYS (2026-09-15). Every style directory and every project directory
    (projects/<name>/) belongs to exactly one publication, and a style's config.yaml names that
    same publication back. A text whose README names a style or a project is failed when its
    publication does not own it — one publication's voice cannot draft the other's piece.
  * (a note, not a failure) an outlet in outlets.yaml that no publication owns.

LAYERS. A text is governed, most general first, by the desk (CLAUDE.md), its publication's
HOUSE file (house conventions: casing, links, what a quotation may say), its project
(projects/<name>/ — README, brief, a CLAUDE.md of its own), and its style. `context` prints
the three paths below the desk for one text, so a skill loads them instead of guessing.

USAGE
    publications.py list
    publications.py show <piece>
    publications.py context <piece>                  # publication, house file, project, style
    publications.py assign <piece> <publication>     # writes `publication:` into publish.yaml
    publications.py check [--outlets publishing/outlets.yaml]

EXIT  0 ok | 1 check found problems | 2 nothing to check, or usage | 3 refused

This module is also the base the other tools stand on: where the instance is, how a piece is
resolved, and how a manifest is written without losing its comments.
"""
import os, re, sys, argparse, tempfile

import yaml

DEFAULT_REGISTRY = os.path.join('publishing', 'publications.yaml')
ID = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


class Refused(Exception):
    """A write that was not safe to make, or a request that cannot be answered. Nothing written."""


# ------------------------------------------------------------------ the instance
def instance_root(start=None):
    cur = os.path.abspath(start or os.environ.get('DESK_INSTANCE') or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, 'pieces')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def pieces(root):
    """-> [(slug, dir)] for every directory under pieces/."""
    pdir = os.path.join(root, 'pieces')
    if not os.path.isdir(pdir):
        return []
    return [(s, os.path.join(pdir, s)) for s in sorted(os.listdir(pdir))
            if os.path.isdir(os.path.join(pdir, s)) and not s.startswith('.')]


def piece_dir(root, ref):
    """A slug or a path -> the piece directory. Refuses one that does not exist."""
    import corpus
    cand = corpus.find(root, ref) or (
        ref if os.sep in ref.rstrip(os.sep) else os.path.join(root, 'pieces', ref))
    cand = os.path.normpath(cand)
    if not os.path.isdir(cand):
        raise Refused(f'no such piece: {ref}')
    return cand


def manifest_path(pdir):
    """The manifest a text keeps its front matter in — `talk.yaml` for a talk, `publish.yaml`
    for a piece. Read from the directory rather than from its path, as corpus.kind_of does:
    the two namespaces are told apart by what is in them, never by where they sit."""
    talk = os.path.join(pdir, 'talk.yaml')
    return talk if os.path.exists(talk) else os.path.join(pdir, 'publish.yaml')


def read_manifest(pdir):
    p = manifest_path(pdir)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {}


def write_atomic(path, text):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.desk-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
        if os.path.exists(path):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def verified_write(path, old, new, expect):
    """Write `new` over `old` only if every key reads back as `expect(before)` says it should.

    The one discipline every manifest writer on the desk shares: publish.yaml is heavily
    commented, so it is edited as text, and a textual edit is proven by parsing both sides."""
    try:
        before, after = yaml.safe_load(old) or {}, yaml.safe_load(new) or {}
    except yaml.YAMLError as e:
        raise Refused(f'{path}: the edit would not parse ({e}); nothing written')
    if after != expect(dict(before)):
        raise Refused(f'{path}: the edit would change more than it should; nothing written. '
                      f'Edit it by hand.')
    write_atomic(path, new)


# ------------------------------------------------------------------ the registry
class _UniqueKeys(yaml.SafeLoader):
    """PyYAML lets a repeated mapping key silently replace the first. In a registry keyed by
    publication id that would make a duplicate invisible, so here it is an error."""


def _construct_mapping(loader, node, deep=False):
    seen = set()
    for k, _v in node.value:
        key = loader.construct_object(k, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(None, None, f'{key!r} is defined twice', k.start_mark)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeys.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def registry_path(root, explicit=None):
    return explicit or os.environ.get('DESK_PUBLICATIONS') or os.path.join(root, DEFAULT_REGISTRY)


def load(root, explicit=None):
    """-> (publications, problems). publications is None when the desk has no registry — a
    one-publication desk — and otherwise id -> {name, byline, outlets, required_outlets, projects,
    styles, deity_conventions, tags, house}. `books:` is read as the older name of `projects:`."""
    path = registry_path(root, explicit)
    if not os.path.exists(path):
        if explicit:
            return {}, [f'{path}: no such registry']
        return None, []
    try:
        with open(path, encoding='utf-8') as fh:
            doc = yaml.load(fh, Loader=_UniqueKeys) or {}
    except yaml.YAMLError as e:
        return {}, [f'{path}: {e}'.replace('\n', ' ')]
    raw = doc.get('publications') if isinstance(doc, dict) else None
    if not isinstance(raw, dict) or not raw:
        return {}, [f'{path}: needs a top-level `publications:` mapping']
    pubs, problems, owner = {}, [], {}
    for pid, e in raw.items():
        if not isinstance(pid, str) or not ID.match(pid):
            problems.append(f'publication id {pid!r} must be lowercase words joined by hyphens'); continue
        if not isinstance(e, dict) or not str(e.get('name') or '').strip():
            problems.append(f'{pid}: needs a name'); continue
        entry = {'name': str(e['name']).strip(), 'byline': str(e.get('byline') or '').strip()}
        if 'books' in e and 'projects' in e:
            problems.append(f'{pid}: names both books and projects — projects is the one field')
        for field in ('outlets', 'projects', 'styles'):
            v = e.get(field) if field != 'projects' or 'projects' in e else e.get('books')
            v = v or []
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                problems.append(f'{pid}: {field} must be a list of names'); v = []
            entry[field] = list(v)
        for o in entry['outlets']:
            if o in owner:
                problems.append(f'outlet {o!r} belongs to both {owner[o]} and {pid} — a site reads '
                                f'by outlet, so it would show both publications')
            owner.setdefault(o, pid)
        for field, what in (('styles', 'style'), ('projects', 'project')):
            for x in entry[field]:
                k = (field, x)
                if k in owner:
                    problems.append(f'{what} {x!r} belongs to both {owner[k]} and {pid}')
                owner.setdefault(k, pid)
        dc = e.get('deity_conventions', False)
        if not isinstance(dc, bool):
            problems.append(f'{pid}: deity_conventions must be true or false'); dc = False
        entry['deity_conventions'] = dc
        # Outlets EVERY published piece of this publication must be on, unless the piece records
        # why not. Optional; a publication without it asks nothing.
        req = e.get('required_outlets') or []
        if not isinstance(req, list) or not all(isinstance(x, str) for x in req):
            problems.append(f'{pid}: required_outlets must be a list of names'); req = []
        stray = [o for o in req if o not in entry['outlets']]
        if stray:
            problems.append(f'{pid}: required_outlets {stray} are not among its own outlets')
        entry['required_outlets'] = [o for o in req if o in entry['outlets']]
        # Companions EVERY published piece of this publication must carry, unless the piece
        # records why not. The same shape as required_outlets, one layer in: a Note is written
        # with the piece rather than remembered on the morning it goes live.
        rc = e.get('required_companions') or []
        if not isinstance(rc, list) or not all(isinstance(x, str) for x in rc):
            problems.append(f'{pid}: required_companions must be a list of roles'); rc = []
        stray = [c for c in rc if c not in ('note', 'talk')]
        if stray:
            problems.append(f'{pid}: required_companions {stray} are not companion roles')
        entry['required_companions'] = [c for c in rc if c not in stray]
        t = e.get('tags')
        entry['tags'] = os.path.join(root, t) if isinstance(t, str) and t.strip() else \
            os.path.join(root, 'publishing', 'tags', f'{pid}.yaml')
        h = e.get('house')
        entry['house'] = os.path.join(root, h) if isinstance(h, str) and h.strip() else \
            os.path.join(root, 'publishing', 'house', f'{pid}.md')
        pubs[pid] = entry
    return pubs, problems


def missing_required(man, pubs, outlets=None):
    """-> [(outlet, why)] for a PUBLISHED piece: each outlet its publication requires that the
    piece neither declares nor exempts. An exemption is `outlets_exempt: {outlet: "reason"}` —
    with a reason, because the rule this serves is "every piece, unless Eric says otherwise",
    and the saying has to be written down. A draft is not held to it.

    PUBLISHED is asked of the piece's OWN outlet, which is what `outlets` is for: pass the
    registry (outlets.yaml's `outlets:` mapping) and liveness is read by each outlet's
    `manifest_url_key`. Without it this read `public_url` — the `substack` outlet's key — so
    a piece of a publication that does not use Substack was never published as far as this
    gate was concerned, and its `required_outlets` silently asked nothing of it. Latent on
    2026-09-11, when the second publication happened to require no outlets; a gate that does
    not apply is worth fixing before the day it should have.
    """
    if not pubs or not man:
        return []
    if outlets is None:                     # no registry offered: the one-outlet desk's key
        live = man.get('public_url')
    else:
        # Imported here, not at module scope: this file is the base the other tools stand on,
        # and check_status is one of them.
        import check_status as cs
        live = cs.live_url(man, outlets)
    if not live:
        return []
    e = pubs.get(man.get('publication') or '')
    if not e:
        return []
    declared = set(man.get('outlets') or [])
    exempt = man.get('outlets_exempt') if isinstance(man.get('outlets_exempt'), dict) else {}
    out = []
    for o in e.get('required_outlets') or []:
        if o in declared:
            continue
        why = exempt.get(o)
        if isinstance(why, str) and why.strip():
            continue
        out.append((o, 'exempted without a reason' if o in exempt else 'not declared'))
    return out


def missing_companions(man, pubs, piece_dir, outlets=None, require_live=True):
    """-> [(role, why)] for a PUBLISHED piece: each companion its publication requires that the
    piece neither declares nor exempts. `companions_exempt: {note: "reason"}` opts out, with a
    reason, for the same cause as outlets_exempt: the rule is "every piece, unless the author
    says otherwise", and the saying has to be written down. A draft is not held to it.

    Published is read the same way `missing_required` reads it — by the piece's OWN outlet's
    manifest key — so this asks nothing of a piece that has not gone live.

    `require_live=False` asks it of a piece that is not live yet. That is for the one moment
    before publication where the answer still costs nothing: arming the schedule, which on this
    desk IS the approval (`schedule.py set`, docs/SCHEDULING.md). Checked only at publication, a
    missing Note is found on the morning the post goes out. (Eric, 2026-09-11: the Note "should
    happen by default after approval, please make sure the tooling would do this".)"""
    if not pubs or not man:
        return []
    if outlets is None:
        live = man.get('public_url')
    else:
        import check_status as cs
        live = cs.live_url(man, outlets)
    if not live and require_live:
        return []
    e = pubs.get(man.get('publication') or '')
    if not e:
        return []
    declared = man.get('companions') if isinstance(man.get('companions'), dict) else {}
    exempt = man.get('companions_exempt') if isinstance(man.get('companions_exempt'), dict) else {}
    out = []
    for role in e.get('required_companions') or []:
        target = declared.get(role)
        if isinstance(target, str) and target.strip():
            if role == 'note' and not os.path.exists(os.path.join(piece_dir, target.strip())):
                out.append((role, f'declares {target.strip()}, which is not on disk'))
            continue
        why = exempt.get(role)
        if isinstance(why, str) and why.strip():
            continue
        out.append((role, 'exempted without a reason' if role in exempt else 'not declared'))
    return out


def outlet_owner(pubs, outlet):
    return next((p for p, e in (pubs or {}).items() if outlet in e['outlets']), None)


def owner_of(pubs, field, name):
    """The publication whose `field` ('styles' or 'projects') lists `name`, or None."""
    return next((p for p, e in (pubs or {}).items() if name in e[field]), None)


def style_publication(root, style):
    """-> the `publication:` a style's config.yaml names back, '' when it names none, or None
    when the style has no config.yaml."""
    path = os.path.join(root, 'styles', style, 'config.yaml')
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as fh:
            doc = yaml.safe_load(fh) or {}
    except yaml.YAMLError:
        return ''
    return str(doc.get('publication') or '') if isinstance(doc, dict) else ''


def _dirs(root, name):
    d = os.path.join(root, name)
    return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))
                  and not x.startswith('.')) if os.path.isdir(d) else []


def deity_conventions(text_dir):
    """Do the deity-pronoun conventions apply to this text? True on a desk with no registry and
    for a text whose publication cannot be read — the strict answer when the question has none."""
    root = instance_root(text_dir)
    try:
        pubs, _p = load(root)
        man = read_manifest(text_dir)
    except Exception:                                   # noqa: BLE001 — unreadable: stay strict
        return True
    if not pubs or not man:
        return True
    e = pubs.get(man.get('publication') or '')
    return True if e is None else e['deity_conventions']


def of_piece(man, pubs):
    """-> (publication id or None, problems). No registry: (None, []) — nothing is asked."""
    if pubs is None or man is None:
        return None, []
    pid = man.get('publication')
    if not pid:
        return None, ['names no publication (publication: in publish.yaml)']
    if pid not in pubs:
        return None, [f'names publication {pid!r}, which the registry does not define']
    outlets = man.get('outlets') if isinstance(man.get('outlets'), list) else []
    stray = [o for o in outlets if o not in pubs[pid]['outlets']]
    if stray:
        return pid, [f"declares outlet(s) {', '.join(stray)}, which belong to "
                     f"{', '.join(sorted({outlet_owner(pubs, o) or 'no publication' for o in stray}))}, "
                     f"not {pid}"]
    return pid, []


def projects_dir(root):
    """The directory a desk keeps its projects in: `projects/`, or `books/` on a desk from before
    2026-09-16, when the directory was renamed to match what the registry calls them."""
    new, old = os.path.join(root, 'projects'), os.path.join(root, 'books')
    return old if os.path.isdir(old) and not os.path.isdir(new) else new


def readme_refs(pdir):
    """(style, project) named by the piece README's first styles/… and projects/… links, if any
    (books/… on an older desk)."""
    try:
        text = open(os.path.join(pdir, 'README.md'), encoding='utf-8').read()
    except OSError:
        return None, None
    s = re.search(r'styles/([a-z0-9][a-z0-9-]*)/', text)
    b = re.search(r'(?<![A-Za-z0-9])(?:projects|books)/([a-z0-9][a-z0-9-]*)/', text)
    return (s.group(1) if s else None), (b.group(1) if b else None)


def check(root, pubs, outlets_file=None):
    """-> (problems, notes, counts). A problem fails the check; a note is worth knowing."""
    import corpus
    problems, notes, counts = [], [], {p: 0 for p in pubs}
    # Ownership both ways: what is on disk is owned, what is owned is on disk, and a style
    # names its owner back. Only a desk that HAS styles/ or projects/ is asked.
    ptop = os.path.basename(projects_dir(root))
    for field, top, what in (('styles', 'styles', 'style'), ('projects', ptop, 'project')):
        if not os.path.isdir(os.path.join(root, top)):
            continue
        present = _dirs(root, top)
        for x in present:
            if not owner_of(pubs, field, x):
                problems.append(f'{top}/{x}: no publication owns this {what} '
                                f'(add it to {field} in publications.yaml)')
        for p, e in pubs.items():
            for x in e[field]:
                if x not in present:
                    problems.append(f'{p}: {what} {x!r} is not a directory under {top}/')
    for x in _dirs(root, 'styles'):
        owner, named = owner_of(pubs, 'styles', x), style_publication(root, x)
        if owner and named is not None and named != owner:
            problems.append(f'styles/{x}/config.yaml: ' + (
                f'names publication {named!r}, but {owner} owns it' if named else
                f'names no publication (publication: {owner})'))
    for slug, d, kind in corpus.texts(root):
        slug = slug if kind == 'piece' else f'talks/{slug}'
        try:
            man = read_manifest(d)
        except yaml.YAMLError:
            problems.append(f'{slug}: publish.yaml does not parse'); continue
        if man is None:
            continue
        pid, probs = of_piece(man, pubs)
        problems += [f'{slug}: {p}' for p in probs]
        if not pid:
            continue
        counts[pid] += 1
        style, book = readme_refs(d)
        if style and style not in pubs[pid]['styles']:
            problems.append(f"{slug}: README's style {style!r} is not one {pid} owns"
                            + (f' — it is {owner_of(pubs, "styles", style)}\'s'
                               if owner_of(pubs, 'styles', style) else ''))
        if book and book not in pubs[pid]['projects']:
            problems.append(f"{slug}: README's project {os.path.basename(projects_dir(root))}/{book} is not one {pid} owns"
                            + (f' — it is {owner_of(pubs, "projects", book)}\'s'
                               if owner_of(pubs, 'projects', book) else ''))
    if outlets_file and os.path.exists(outlets_file):
        with open(outlets_file, encoding='utf-8') as fh:
            defined = set(((yaml.safe_load(fh) or {}).get('outlets') or {}).keys())
        for o in sorted(defined):
            if not outlet_owner(pubs, o):
                notes.append(f'outlet {o!r} is defined in outlets.yaml but no publication owns it')
        for p, e in pubs.items():
            for o in e['outlets']:
                if o not in defined:
                    problems.append(f'{p}: outlet {o!r} is not defined in {os.path.basename(outlets_file)}')
    return problems, notes, counts


# ------------------------------------------------------------------ writing `publication:`
def set_scalar(pdir, key, value, comment=None):
    """Set a top-level `key: value` in publish.yaml as text. A new key goes right under the
    title and subtitle, where a reader of the manifest looks first. An existing line keeps its
    comment; `comment` is used when it has none. Returns True if changed."""
    path = manifest_path(pdir)
    if not os.path.exists(path):
        raise Refused(f'{os.path.basename(pdir)} has no publish.yaml; create it first '
                      f'(templates/piece/publish.yaml)')
    old = open(path, encoding='utf-8').read()
    lines = old.splitlines(keepends=True)
    keyre = re.compile(rf'^{re.escape(key)}[ \t]*:(?P<rest>.*)$')
    at = next((i for i, l in enumerate(lines) if keyre.match(l.rstrip('\n'))), None)
    if at is not None:
        rest = keyre.match(lines[at].rstrip('\n')).group('rest')
        _v, sep, existing = rest.partition('#')
        if at + 1 < len(lines) and lines[at + 1][:1] in (' ', '\t') and lines[at + 1].strip():
            raise Refused(f'{path}: `{key}:` spans lines; edit it by hand')
        note = f'#{existing.rstrip()}' if sep else (f'# {comment}' if comment else '')
        lines[at] = f'{key}: {value}' + (f'   {note}' if note else '') + '\n'
    else:
        anchor = None
        for want in ('subtitle', 'title'):
            anchor = next((i for i, l in enumerate(lines) if re.match(rf'^{want}[ \t]*:', l)), None)
            if anchor is not None:
                break
        if anchor is None:
            anchor = next((i - 1 for i, l in enumerate(lines) if l.strip() and not l.startswith('#')), -1)
        else:
            while anchor + 1 < len(lines) and lines[anchor + 1][:1] in (' ', '\t') and lines[anchor + 1].strip():
                anchor += 1                                  # a folded title/subtitle's continuation
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines.insert(anchor + 1, f'{key}: {value}\n')
    new = ''.join(lines)
    if new == old:
        return False
    verified_write(path, old, new, lambda b: {**b, key: value})
    return True


# ------------------------------------------------------------------ the CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog='publications.py', description=__doc__.split('\n')[0])
    ap.add_argument('--root')
    ap.add_argument('--registry')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    p = sub.add_parser('show'); p.add_argument('piece')
    p = sub.add_parser('context'); p.add_argument('piece')
    p = sub.add_parser('assign'); p.add_argument('piece'); p.add_argument('publication')
    p.add_argument('--move', action='store_true',
                   help='re-assign a piece that already names a different publication')
    p = sub.add_parser('check'); p.add_argument('--outlets')
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    root = instance_root(a.root)
    pubs, problems = load(root, a.registry)
    try:
        if pubs is None:
            if a.cmd == 'check':
                print('no publication registry: a one-publication desk, nothing to check')
                return 2
            raise Refused(f'no registry at {os.path.relpath(registry_path(root), root)} — this desk '
                          f'has one publication, and pieces need not name it')
        if problems:
            if a.cmd != 'check':
                raise Refused('fix the registry first:\n  ' + '\n  '.join(problems))
        return _dispatch(a, root, pubs, problems)
    except Refused as e:
        print(f'refused: {e}', file=sys.stderr)
        return 3


def _dispatch(a, root, pubs, reg_problems):
    if a.cmd == 'check':
        outlets = a.outlets or os.path.join(root, 'publishing', 'outlets.yaml')
        problems, notes, counts = check(root, pubs, outlets)
        problems = reg_problems + problems
        for n in notes:
            print(f'  note  {n}')
        for p in problems:
            print(f'  FAIL  {p}')
        print(', '.join(f'{p}: {n} piece(s)' for p, n in counts.items()) + ' — '
              + (f'{len(problems)} problem(s)' if problems else 'every manifest names its publication'))
        return 1 if problems else 0

    if a.cmd == 'list':
        _p, _n, counts = check(root, pubs)
        for pid, e in pubs.items():
            print(f"{pid:18} {e['name']}" + (f" — {e['byline']}" if e['byline'] else ''))
            print(f"{'':18} outlets: {', '.join(e['outlets']) or '-'}   projects: {', '.join(e['projects']) or '-'}")
            print(f"{'':18} styles: {', '.join(e['styles']) or '-'}   tags: {os.path.relpath(e['tags'], root)}"
                  f"   pieces: {counts[pid]}")
            print(f"{'':18} house: {os.path.relpath(e['house'], root)}"
                  + ('' if os.path.exists(e['house']) else ' (none written)')
                  + f"   deity conventions: {'yes' if e['deity_conventions'] else 'no'}")
        return 0

    d = piece_dir(root, a.piece)
    slug = os.path.basename(d)
    if a.cmd == 'show':
        pid, probs = of_piece(read_manifest(d), pubs)
        print(f"{slug}: {pid or '(none)'}" + ''.join(f'\n  {p}' for p in probs))
        return 0
    if a.cmd == 'context':
        # What governs this text below the desk — the files a drafting or reviewing skill loads.
        pid, probs = of_piece(read_manifest(d), pubs)
        style, book = readme_refs(d)
        rel = lambda x: os.path.relpath(x, root)
        e = pubs.get(pid) or {}
        house = e.get('house')
        print(f"publication: {pid or '(none)'}" + (f"   ({e['name']})" if e else ''))
        print(f"house:       " + (rel(house) if house and os.path.exists(house) else
                                  '(none — this publication keeps no house rules beyond the desk)'))
        print(f"project:     " + (rel(os.path.join(projects_dir(root), book)) if book else '(none)'))
        print(f"style:       " + (rel(os.path.join(root, 'styles', style)) if style else '(none named in README)'))
        print(f"deity conventions: {'yes' if (e.get('deity_conventions') if e else True) else 'no'}")
        for p in probs:
            print(f'  note  {p}')
        return 0

    if a.publication not in pubs:
        raise Refused(f"{a.publication!r} is not a publication: {', '.join(pubs)}")
    current = (read_manifest(d) or {}).get('publication')
    note = None
    if current and current != a.publication:
        # An older free-text form — `publication: elmuffin (E. L. Muffin)` — names the same
        # publication with a label beside it. The id is kept; the label moves to a comment.
        legacy = re.fullmatch(rf'{re.escape(a.publication)}\s*\((.+)\)\s*', str(current))
        if legacy:
            note = legacy.group(1).strip()
        elif not a.move:
            raise Refused(f'{slug} already names {current!r}. Moving a piece to another publication '
                          f'moves its outlets and its slug in the store — pass --move if that is meant.')
    changed = set_scalar(d, 'publication', a.publication, comment=note)
    _pid, probs = of_piece(read_manifest(d), pubs)
    print(f'{slug}: {a.publication}' + ('' if changed else '   (unchanged)'))
    for p in probs:
        print(f'  note  {p}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
