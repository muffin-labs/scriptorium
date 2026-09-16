#!/usr/bin/env python3
"""check_refs.py — do the desk's cross-references still name the right piece?

`check_links.py` proves a URL resolves.  This proves something different and, with several
sessions running, more fragile: that when one file CALLS a piece by name, the name is still the
piece's name.

WHY (2026-09-02).  A sibling was retitled twice in one afternoon by another session —
*Fear Not, Little Flock* to *The Kingdom That Isn't*, then a second piece from *Two Wills* to
*Already Inside the Fence* — while other files went on referring to the old titles.  Nothing was
broken in a way any tool could see: every link still resolved, every file still parsed.  The
references were simply about a piece that no longer had that name, and the only reason it was
caught was that somebody happened to re-read the file.

METHOD, and the choice here is the useful part.  There is no need for history.  A stale title
shows up as a DISAGREEMENT: the same slug labelled with two different titles in two places.  So
this compares the corpus against ITSELF, and uses each piece's publish.yaml title — or its README H1 where
there is none — only to say which side of a disagreement is right.  That needs no record of past titles, which is good, because the
desk does not keep one and should not have to.

WHY IT READS BOOK INDEXES AND THE MANIFEST (2026-09-11).  *The Door and the Room* went on naming
a piece in the founding-writings index for four days after it was retitled *None but He and I*,
and this checker called the corpus consistent throughout. It read no index files, and it did not
know the index's own form, `*Title* (`slug`)`, usually wrapped over two lines — the most common
way the desk names a piece, and invisible to it. Both are read now. And the README H1 stopped
being the only witness: publish.yaml's `title` is kept against the live post, so it is truth
where it exists, and a heading that disagrees with its manifest is reported on its own — the
retitle that reached one file and not the other. A heading of "Title — Subtitle" agrees.

WHAT IS DELIBERATELY NOT CHECKED, because a checker that cries about correct files gets
switched off:

  * `log/` and `corrections.md`.  They are APPEND-ONLY records of what was true when written.
    A log entry naming the old title is not stale, it is accurate history, and "fixing" it would
    be editing the evidence.
  * Any line that marks its own supersession — *Retired:*, *superseded*, *(was …)*, *formerly*,
    *replaced*.  Naming an old title in order to retire it is the correct use of an old title.

Exit: 0 consistent | 1 disagreements found | 2 nothing could be checked.
"""
import os, re, sys
import sys as _sys, os as _os                                        # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import corpus                                                        # noqa: E402


SCAN_NAMES = ('README.md', 'notes.md', 'outline.md', 'draft.md', 'DASHBOARD.md')
SKIP_DIR_PARTS = ('/log/', '/.git/', '/node_modules/', '/__pycache__/')
SKIP_FILES = ('corrections.md',)
SUPERSESSION = re.compile(
    r'retired|supersed|formerly|\bwas\b\s*[:"“]|\(was\b|replaced|previous title|old title|'
    r'working title\s*\*?\*?[:,]', re.I)

# `## slug *(title **X**)*` / `*(working title **X**)*` — the dashboard's own labelling
HEAD_LABEL = re.compile(r'^##\s+([A-Za-z0-9][A-Za-z0-9._-]*)\s*\*\((?:working\s+)?title\s+'
                        r'(?:\*\*(?P<b>[^*]+)\*\*|"(?P<q>[^"]+)")\s*\)\*', re.M)
# The house's index form: an emphasized title immediately followed by the slug in backticks,
# optionally linked, and in writings.md wrapped onto the next line --
#   - [*The Mask Comes Off Last*](https://…/the-mask-comes-off-last/)
#     (`the-mask-comes-off-last`) — …
#   - *None but He and I* (`none-but-he-and-i`) — …
# Matched over the whole file, not line by line, because the wrap is the usual case.
INDEX_LABEL = re.compile(
    r'(?<![\w*])(?P<em>\*{1,3})(?P<t>[^*`\n]{2,120}?)(?P=em)'
    r'(?:\]\([^)\s]*\))?[ \t]*(?:\n[ \t]*)?\(\s*`(?P<slug>[A-Za-z0-9][A-Za-z0-9._-]*)`')
# a markdown link whose target is a piece directory
PIECE_LINK = re.compile(r'\[([^\]]{2,120})\]\(([^)]*?pieces/|\.\./)([A-Za-z0-9][A-Za-z0-9._-]*)/'
                        r'(?:README\.md)?\)')


def unemphasize(text):
    """Strip markdown emphasis from a link's text.

    `[*The Highest Peak*](../the-optimal-timeline/README.md)` is a reference to a piece named
    *The Highest Peak*; the asterisks are formatting, not part of the name.  The first run of
    this checker reported nine disagreements that were nothing but emphasis markers — a checker
    whose output is mostly noise gets muted, which costs more than the bug it was built for.
    """
    t = text.strip()
    for _ in range(3):
        m = re.fullmatch(r'(\*\*\*|\*\*|\*|__|_)(.+?)\1', t, re.S)
        if not m:
            break
        t = m.group(2).strip()
    return t


def instance_root(start=None):
    cur = os.path.abspath(start or os.environ.get('DESK_INSTANCE') or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, 'pieces')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def h1_title(path):
    """The piece's own name: its H1, minus a trailing italic parenthetical.

    `# Secondhand *(slug \\`hearing-firsthand\\`)*`            -> Secondhand
    `# In the Name (The Ambassador) *(was "The Name")*`        -> In the Name (The Ambassador)
    """
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith('# '):
                    t = line[2:].strip()
                    t = re.sub(r'\s*\*\(.*$', '', t).strip()
                    return t or None
                if line.strip() and not line.startswith(('*', '<', '>')):
                    continue
    except OSError:
        pass
    return None


def norm(s):
    """Compare titles as a reader would: curly and straight quotes alike, whitespace collapsed."""
    s = s.replace('\u2019', "'").replace('\u2018', "'").replace('\u201c', '"').replace('\u201d', '"')
    return re.sub(r'\s+', ' ', s).strip()


def manifest_field(path, key):
    """A top-level scalar from publish.yaml, read without a YAML dependency: a title is one line,
    and this checker runs in bare CI images."""
    try:
        with open(path) as fh:
            src = fh.read()
    except OSError:
        return None
    m = re.search(r'^%s:[ \t]*(.*?)[ \t]*$' % re.escape(key), src, re.M)
    if not m:
        return None
    v = re.sub(r'\s+#.*$', '', m.group(1)).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in '\'"':
        v = v[1:-1]
    return None if v in ('', '>', '>-', '|', '|-') else v


def truth(root):
    """slug -> title. publish.yaml's `title` where there is one — the manifest is the witness,
    kept against the live post by the sync tools — and the README H1 otherwise."""
    out = {}
    # Both namespaces. A talk and its essay share a slug AND a title, so they agree by
    # construction; what matters is that a talk's title is known at all.
    for slug, d, _kind in corpus.texts(root):
        t = manifest_field(os.path.join(d, 'publish.yaml'), 'title')
        if not t:
            t = manifest_field(os.path.join(d, 'talk.yaml'), 'title')
        if not t:
            rd = os.path.join(d, 'README.md')
            t = h1_title(rd) if os.path.isfile(rd) else None
        if t:
            out.setdefault(slug, t)
    return out


def subtitles(root):
    """slug -> subtitle, where publish.yaml has one."""
    out = {}
    pdir = os.path.join(root, 'pieces')
    if os.path.isdir(pdir):
        for slug in os.listdir(pdir):
            s = manifest_field(os.path.join(pdir, slug, 'publish.yaml'), 'subtitle')
            if s:
                out[slug] = s
    return out


def cited_forms(title, sub):
    """Every way a correct citation can print this piece's name: the title alone, or with its
    subtitle after a colon or a dash — *They/Them: The Pronoun as Iconoclasm* is not stale."""
    forms = {norm(title)}
    if sub:
        forms |= {norm(f'{title}: {sub}'), norm(f'{title} \u2014 {sub}'), norm(f'{title} - {sub}')}
    return forms


def heading_disagreements(root):
    """(slug, h1, title) where a README H1 and publish.yaml name two different things — a
    retitle that reached one file and not the other. "Title — Subtitle" agrees."""
    out = []
    pdir = os.path.join(root, 'pieces')
    if not os.path.isdir(pdir):
        return out
    for slug in sorted(os.listdir(pdir)):
        man = os.path.join(pdir, slug, 'publish.yaml')
        rd = os.path.join(pdir, slug, 'README.md')
        title = manifest_field(man, 'title')
        h1 = h1_title(rd) if os.path.isfile(rd) else None
        if not title or not h1:
            continue
        if norm(h1) not in cited_forms(title, manifest_field(man, 'subtitle')):
            out.append((slug, h1, title))
    return out


def scan_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('.git', '__pycache__', 'node_modules')]
        p = dirpath.replace(os.sep, '/') + '/'
        if any(s in p for s in SKIP_DIR_PARTS):
            continue
        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            if fn in SCAN_NAMES or (fn.endswith('.md') and ('/DASHBOARD.d/' in p or '/projects/' in p or '/books/' in p)):
                yield os.path.join(dirpath, fn)


def collect(root):
    """-> claims[slug] = set of (title, relpath, lineno), and unknown-slug references."""
    claims, unknown = {}, []
    known = {slug for slug, _d, _k in corpus.texts(root)}
    for path in scan_files(root):
        rel = os.path.relpath(path, root)
        try:
            with open(path) as fh:
                lines = fh.read().split('\n')
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if SUPERSESSION.search(line):
                continue
            for m in HEAD_LABEL.finditer(line):
                slug, title = m.group(1), (m.group('b') or m.group('q')).strip()
                claims.setdefault(slug, set()).add((title, rel, i))
            for m in PIECE_LINK.finditer(line):
                text, slug = m.group(1).strip(), m.group(3)
                if slug not in known:
                    # `../<name>/` is only a PIECE reference from inside pieces/. From
                    # projects/all-my-stories it means the sibling project, and calling that a
                    # missing piece is the checker inventing a problem.
                    if (rel.startswith(('pieces' + os.sep, 'talks' + os.sep))
                            and slug not in ('..', '.') and not slug.endswith('.md')):
                        unknown.append((slug, rel, i))
                    continue
                text = unemphasize(text)
                if text.startswith('`') and text.endswith('`'):
                    continue          # [`false-light`](…) — the slug as link text is a path
                if re.fullmatch(r'[\w./-]+', text) or text.lower() in ('readme', 'piece', 'here'):
                    continue          # a path or a generic word, not a title claim
                if text[:1].islower():
                    continue          # 'the companion essay' — a descriptor, not a name
                claims.setdefault(slug, set()).add((text, rel, i))
        whole = '\n'.join(lines)
        for m in INDEX_LABEL.finditer(whole):
            slug, title = m.group('slug'), m.group('t').strip()
            if slug not in known or not title[:1].isupper():
                continue          # emphasis on a phrase that happens to precede a slug, not a name
            first = whole.count('\n', 0, m.start()) + 1
            last = whole.count('\n', 0, m.end()) + 1
            if any(SUPERSESSION.search(lines[k - 1]) for k in range(first, last + 1)):
                continue
            claims.setdefault(slug, set()).add((title, rel, first))
    return claims, unknown


def problems(root):
    """([(slug, what, [(title, file, line), ...]), ...], claims_checked, pieces_with_claims).
    An empty list means consistent. Split out of main() so the suite and rename_piece can ask."""
    real, subs = truth(root), subtitles(root)
    claims, unknown = collect(root)
    out = []
    for slug in sorted(claims):
        current = real.get(slug)
        if not current:
            continue
        ok = cited_forms(current, subs.get(slug))
        wrong = [(t_, f, ln) for t_, f, ln in sorted(claims[slug]) if norm(t_) not in ok]
        if wrong:
            out.append((slug, 'titled %r' % current, wrong))
    for slug, h1, title in heading_disagreements(root):
        out.append((slug, 'README H1 %r but publish.yaml title %r' % (h1, title),
                    [(h1, os.path.join('pieces', slug, 'README.md'), 1)]))
    for slug, f, ln in unknown:
        out.append((slug, 'referenced but no such piece', [('', f, ln)]))
    return out, sum(len(v) for v in claims.values()), len(claims)


def main(argv):
    root = instance_root(argv[1] if len(argv) > 1 else None)
    if not truth(root):
        sys.stderr.write('check_refs: no pieces/ found under %s\n' % root)
        return 2
    found, checked, pieces = problems(root)
    for slug, what, where in found:
        print('%s — %s' % (slug, what))
        for title, f, ln in where:
            print(('    %-14r %s:%d' % (title, f, ln)) if title else ('    %s:%d' % (f, ln)))
    if found:
        print('\nchecked %d title claim(s) across %d piece(s): %d disagreement(s)'
              % (checked, pieces, len(found)))
        print("publish.yaml's title is truth where it exists, the README H1 otherwise. Fix the "
              "reference — and if the manifest or the heading is the stale one, fix that and re-run.")
        return 1
    print('checked %d title claim(s) across %d piece(s): all consistent' % (checked, pieces))
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv))
