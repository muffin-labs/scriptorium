#!/usr/bin/env python3
"""references.py — bring a source into the desk, index it, and search what is held.

WHY THIS EXISTS (Eric, 2026-09-11: *"make sure that scriptorium is checking references
against resources that we have locally and not from the LLM itself … have a way of
bringing used references into the writing-desk (.gitignoring them if they are
copywritten) and they can be used in the future and are indexed for future reference"*).

  The desk already closed this hole for ONE source. `check_loci.py` verifies every
  scripture quotation against a local KJV index and knows the house conventions. Nothing
  did it for anything else — and the measurement is blunt: on 2026-09-11 this desk held
  **43 reference files and exactly one index**. `refindex.py --scheme pages` had existed
  for a day and had never been run on anything. So a quotation of Lawrence, McGilchrist,
  Novak or the Ballard opinion was checked by a session opening the PDF and reading it,
  which works when it happens and is silent when it does not.

  The other half is intake. Adding a reference was four hand steps — copy the file, hash
  it, write the manifest row, add the .gitignore line — and built no index. A four-step
  hand procedure is one that gets skipped, and the step most likely to be skipped is the
  .gitignore line on a copyrighted PDF, which is the one that cannot be undone once it is
  in git history.

WHAT IT DOES NOT DO, SAID FIRST.  Holding a source locally does not make a claim true. This
  makes a quotation CHECKABLE and tells you loudly when one is not; it cannot tell you a
  page says what the prose claims it says. That is `review`'s re-open-the-sources read, and
  it is a human's. (Same warning `check_verified.py` gives about itself, for the same reason.)

THE MANIFEST IS THE README, AND STAYS THE README.  `references/README.md`
  already carries one row per file — work, edition/provenance, date, redistribution — and
  CLAUDE.md names it as the index of what is on disk. A second machine-readable catalog
  beside it would be two sources of truth for one fact, which this desk has already learned
  is worse than one source in the wrong place. So this tool READS and WRITES that table, and
  everything else it needs is derivable: the index is `.index/<stem>.tsv.gz` or it is absent;
  restricted is the ⚠️ in the last column.

USAGE
  references.py add <file> --book <name> --work "<work> — <author> (<year>)"
                 [--edition "<edition / provenance>"] [--restricted | --public]
                 [--scheme auto|pages|text|kjv] [--note "..."] [--no-index]
  references.py list [--book <name>] [--unindexed]
  references.py index <file-or-path> [--scheme ...]        # (re)build one index
  references.py search "<phrase>" [--book <name>] [--source <substr>] [-n <hits>]
  references.py push [--book <b>] [--dry-run] [--no-indexes]
  references.py pull [<file>…] [--book <b>] [--indexes-only]
  references.py rehash [--dry-run] [--force]               # full sha256 into every row
  references.py check                                      # manifest ↔ disk ↔ gitignore
                                                           #   ↔ index ↔ digest

EXIT
  0  fine
  1  usage / no such thing
  4  `check` found an inconsistency — most seriously a ⚠️ file that is not gitignored
"""
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = ".index"

# A CANON INDEX IS NOT A SOURCE, and the canon records are what say which files those are.
# `.index/<stem>.tsv.gz` is the derived index of one held file, keyed by its name; a CANON
# index is built by a named scheme for a named canon (kjv.tsv.gz, gita-arnold.tsv.gz) and
# sits beside the sources, so `files_on_disk` would otherwise report it as a source with no
# manifest row. This was hard-coded to {"kjv.tsv.gz"} while there was one of them; asking
# the records means the next canon needs no edit here. (2026-09-14, indexing Arnold's Gita.)
LEGACY_INDEXES = {"kjv.tsv.gz"}          # the floor, if the records cannot be read at all


def canon_indexes(r=None):
    try:
        sys.path.insert(0, HERE)
        import canons as C
        named = {os.path.basename(c.index) for c in C.load(r or root()) if c.index}
    except Exception:                                             # noqa: BLE001
        named = set()
    return LEGACY_INDEXES | named
SOURCE_EXT = (".pdf", ".txt", ".md", ".html", ".htm", ".epub")


# ---------------------------------------------------------------- discovery

def root():
    """The instance root: the directory holding projects/ (books/ on an older desk). Run from
    anywhere inside it."""
    d = os.getcwd()
    while True:
        if os.path.isdir(os.path.join(d, "projects")) or os.path.isdir(os.path.join(d, "books")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return os.getcwd()
        d = up


def books(r=None):
    """The projects the desk has (projects/<name>/, books/ on an older desk), for validating and
    filtering the manifest's Book column — the column keeps its name; its values are projects.

    ONE SHELF, SINCE 2026-09-13. Sources used to live at books/<book>/references/, and
    the division did no work: three books existed and one had a shelf, `catalog()`
    walked every book unless `--book` was passed, nothing passed it, and `gates.py`
    still does not. It also could not hold a source serving two books — Lawrence
    grounds the Alignment Fellowship foundation and *Being Good* both — without
    duplicating the file or filing it under a lie. The book is now a COLUMN in the
    manifest: metadata about why a source is held, not a claim about where it lives.
    (framework/docs/REFERENCE-SHELF.md.)
    """
    r = r or root()
    base = os.path.join(r, "projects")
    if not os.path.isdir(base):
        base = os.path.join(r, "books")
    if not os.path.isdir(base):
        return []
    return sorted(b for b in os.listdir(base) if os.path.isdir(os.path.join(base, b)))


def refdir(r=None):
    return os.path.join(r or root(), "references")


def readme(r=None):
    return os.path.join(refdir(r), "README.md")


# ---------------------------------------------------------------- the manifest

ROW_RE = re.compile(r"^\|\s*(?:\[(?P<label>[^\]]+)\]\((?P<href>[^)]+)\)|(?P<bare>[^|]+?))\s*\|")

# The digest lives in the provenance cell, where a human wrote it, rather than in a
# column of its own — one place per fact, and the cell already reads as provenance.
# It is matched loosely because fifty rows were hand-written before there was a tool:
# with or without backticks, with an ellipsis or without.
#
# A ROW MAY CARRY MORE THAN ONE, AND BOTH CAN BE TRUE. Chiang-story.pdf records the
# SOURCE bytes it was fetched as, and then the hash of that same scan after ocrmypdf gave
# it a text layer — provenance and held file, neither redundant. A parser that took the
# FIRST match called that row a DIGEST MISMATCH against its own correct file, and the
# finding stood for a day while the data was right the whole time. So: collect them all,
# and let the bytes on disk say which one is the record of them.
DIGEST_RE = re.compile(r"sha256\s*`?([0-9a-f]{6,64})(?:…|\.\.\.)?`?", re.I)


# The manifest's verdict markers, and there are THREE. ❌ was missed by the first
# version of this parser, which knew only ✅ and ⚠️ — so the one row that used it
# ("❌ **Not redistributable.** arXiv's licence grants us none") parsed as NO VERDICT,
# and a row with no verdict was then treated as unrestricted. That is the unsafe
# direction, and only an unrelated .gitignore line kept it from mattering. Caught
# 2026-09-11 by the session that maintains the manifest, reading its own row back.
VERDICT_MARKS = {"✅": "ok", "⚠️": "restricted", "❌": "restricted"}


def _verdict(cell):
    """The FIRST verdict marker decides, not the presence of one.

    The hand-written manifest uses ⚠️ for two different jobs: the redistribution
    verdict, and a quality caveat about the file. Four rows read
    *"✅ Public domain. ⚠️ OCR."* — public-domain scans with a warning about their
    text layer — and a detector that keys on "⚠️ anywhere" called all four
    restricted and demanded they be gitignored and removed from git. That is a
    checker flagging correct work, which trains a reader to ignore it; the row's
    verdict is its LEADING marker. (Measured 2026-09-11, first run of `check`.)
    """
    hits = sorted((cell.find(m), v) for m, v in VERDICT_MARKS.items() if m in cell)
    return hits[0][1] if hits else None


def _restricted(cell):
    """No verdict means RESTRICTED. Fail closed.

    The first version returned False here, so a row whose verdict this parser could
    not read became a file it would happily let anyone commit. Silence is not
    permission — the same rule `check_verified.py` applies to its own clearances,
    and for the same reason: the cost of being wrong runs one way only.
    """
    return _verdict(cell) != "ok"


def rows(r=None):
    """Parse the README's manifest table. A row this cannot read is RETURNED as
    unparsed rather than skipped — a manifest checker that silently drops the rows
    it does not understand reports a clean bill it has not earned."""
    path = readme(r)
    if not os.path.exists(path):
        return []
    out, in_table = [], False
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        if line.startswith("| File |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue
            # SPLIT ON UNESCAPED PIPES ONLY. `add` escapes a `|` inside a cell as the
            # markdown table escape `\|`; a parser that split on it anyway would undo the
            # escaping and shift every cell after it — the same failure the escape exists
            # to prevent, moved one step later.
            cells = [c.strip().replace("\\|", "|")
                     for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
            m = ROW_RE.match(line)
            name = None
            if m:
                name = m.group("href") or m.group("label") or (m.group("bare") or "").strip()
            if not name or len(cells) < 6:
                out.append({"line": n, "file": name, "unparsed": line.rstrip()})
                continue
            digs = [m.group(1).lower() for m in DIGEST_RE.finditer(cells[3])]
            out.append({"line": n, "file": os.path.basename(name),
                        "book": cells[1], "work": cells[2], "edition": cells[3],
                        "digests": digs, "digest": (digs[0] if digs else None),
                        "added": cells[4], "redistribution": cells[5],
                        "restricted": _restricted(cells[5]),
                        "verdict_stated": _verdict(cells[5]) is not None})
    return out


def files_on_disk(r=None):
    d = refdir(r)
    if not os.path.isdir(d):
        return []
    skip = canon_indexes(r)
    return sorted(f for f in os.listdir(d)
                  if os.path.isfile(os.path.join(d, f))
                  and f != "README.md" and f not in skip
                  and not f.startswith("."))


def index_for(filename, r=None):
    stem = re.sub(r"\.(pdf|txt|md|html?|epub)$", "", filename, flags=re.I)
    return os.path.join(refdir(r), INDEX_DIR, stem + ".tsv.gz")


def held_digest(row, path):
    """(digest, status) — the row's record OF THE BYTES ON DISK, out of however many it
    carries. status is 'match', 'mismatch' (it carries hashes and the file answers to
    none of them) or 'none' (it carries no hash at all).

    `digest` alone cannot answer this, because a row legitimately holds more than one hash
    and only one of them is the held file. Asking the file which is which is the only rule
    that does not depend on the order a human wrote them in.
    """
    digs = row.get("digests") or ([row["digest"]] if row.get("digest") else [])
    if not digs:
        return None, "none"
    actual = sha256(path)
    for d in digs:
        if actual.startswith(d):
            return d, "match"
    return None, "mismatch"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- gitignore

def gitignore_path(r=None):
    return os.path.join(r or root(), ".gitignore")


def gitignore_lines(r=None):
    p = gitignore_path(r)
    return open(p, encoding="utf-8").read().splitlines() if os.path.exists(p) else []


def ignore_entry(name):
    return f"/references/{name}"


def is_ignored(rel, r=None):
    """Ask git, do not read .gitignore.

    String-matching the file for an exact line was right while every index had its own
    entry and wrong the moment a directory rule covered them all: the covered files
    then read as NOT ignored, which would have reported every restricted index as
    exposed and appended a redundant line for each one, forever. The question is "would
    git commit this", and only git answers it. (2026-09-11, adding the blanket
    `/references/.index/` rule.)
    """
    try:
        return subprocess.run(["git", "check-ignore", "-q", rel], cwd=r or root(),
                              capture_output=True).returncode == 0
    except Exception:
        return False


def ensure_ignored(entries, r=None):
    """Append any missing entry. Never rewrites or reorders — another session may be
    editing this file, and the whole point of the line is that it is never lost."""
    have = set(l.strip() for l in gitignore_lines(r))
    add = [e for e in entries
           if e not in have and not is_ignored(e.lstrip("/"), r)]
    if add:
        p = gitignore_path(r)
        with open(p, "a", encoding="utf-8") as f:
            if os.path.exists(p) and open(p, encoding="utf-8").read()[-1:] != "\n":
                f.write("\n")
            for e in add:
                f.write(e + "\n")
    return add


DENY_HEADER = """# Deny by default. NOTHING in this folder is committed unless a line below allows it.
#
# A file nobody has classified is IGNORED. Forgetting a line means a PUBLIC file does not
# get committed — visible in `git status`, harmless, fixed in a second. The old
# arrangement was one ignore line per RESTRICTED file in the root .gitignore, where a
# forgotten line leaked a copyrighted source into history, which no later edit removes.
#
# Written by `framework/tools/references.py add --public`. `--restricted` writes nothing,
# because the default already covers it. `references.py check` reports any held public
# source that is not committable, so the safe failure is never silent.

*
!.gitignore
!README.md
"""


def deny_file(r=None):
    return os.path.join(refdir(r), ".gitignore")


def ensure_allowed(name, r=None):
    """Add a `!name` line to the folder's deny-by-default .gitignore, creating it if
    absent. Append-only and idempotent: another session may be adding a source in the
    same second, and no allow line is ever worth losing."""
    path = deny_file(r)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(DENY_HEADER)
    body = open(path, encoding="utf-8").read()
    if f"\n!{name}\n" in body or body.endswith(f"!{name}"):
        return False
    with open(path, "a", encoding="utf-8") as f:
        if not body.endswith("\n"):
            f.write("\n")
        f.write(f"!{name}\n")
    return True


def tracked(rel, r=None):
    """Is this path already in git's index/history? A ⚠️ file that is TRACKED is not
    fixed by a .gitignore line, and saying otherwise is the dangerous half of this
    tool. Reported separately, loudly."""
    try:
        out = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                             cwd=r or root(), capture_output=True, text=True)
        return out.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------- indexing

def build_index(src, out, scheme="auto"):
    sys.path.insert(0, HERE)
    import refindex
    if scheme in ("auto", ""):
        scheme = "text" if src.lower().endswith((".txt", ".md")) else "pages"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if scheme == "text":
        return scheme, refindex.build_text(src, out)
    if scheme == "kjv":
        return scheme, refindex.build_kjv(src, out)
    return scheme, refindex.build_pages(src, out)


def index_chars(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return sum(len(l) for l in f)


def text_layer_verdict(src, idx):
    """Catch the scanned PDF, without needing PyMuPDF to do it.

    A 163-page PDF that indexes to 185 characters is not a short book; it is an
    image scan with no text layer, and a checker that treats it as a held source
    will report every true quotation from it as missing. Measured 2026-09-11 on
    `qed-feynman-princeton-1988.pdf` — the one bad index out of forty-one.

    The signal is deliberately crude and dependency-free: bytes on disk against
    characters in the index. A real text layer yields characters within an order
    of magnitude of the file's size; a scan yields three or four orders less.
    """
    if not (src and idx and os.path.exists(src) and os.path.exists(idx)):
        return None
    size, chars = os.path.getsize(src), index_chars(idx)
    if size > 200_000 and chars < 2_000:
        return (f"NO USABLE TEXT — {chars:,} chars indexed from a {size:,}-byte file. "
                f"Almost certainly a scanned PDF with no text layer; it needs OCR before "
                f"anything can be checked against it.")
    return None


def load_index(path):
    """Rows as (locator, text), plus the joined normalized stream and its offsets.

    Joining is the point. A page index searched row by row cannot find a sentence
    that straddles a page break — it belongs to neither page — and would report a
    correct quotation missing, which is the failure mode this desk names as worse
    than no checker at all.
    """
    op = gzip.open if path.endswith(".gz") else open
    rws = []
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 2:
                rws.append((parts[0], parts[1]))
            elif len(parts) == 4:                      # a kjv index, read generically
                rws.append((f"{parts[0]} {parts[1]}:{parts[2]}", parts[3]))
    stream, offsets, pos = [], [], 0
    for loc, text in rws:
        t = norm(text)
        offsets.append((pos, loc))
        stream.append(t)
        pos += len(t) + 1
    return rws, " ".join(stream), offsets


def locate(offsets, at):
    """Which row an offset in the joined stream fell in."""
    lo = offsets[0][1] if offsets else "?"
    for start, loc in offsets:
        if start > at:
            break
        lo = loc
    return lo


def norm(t):
    """The comparison form. Kept deliberately close to check_loci.norm so the two
    checkers do not disagree about what 'the same words' means — but WITHOUT its
    bracket-stripping, which is a King James convention and not a general one."""
    # Drop combining marks rather than letting the punctuation strip turn them into
    # spaces. NFKD splits an accented letter into its base plus a combining mark, and
    # the character class below then turned the mark into a space — so any accented
    # word silently became two, and matched neither the source nor itself. (2026-09-11.)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("’", "'").replace("‘", "'")
    t = t.replace("“", '"').replace("”", '"')
    t = t.replace("—", " ").replace("–", " ").replace("‐", "-")
    t = re.sub(r"[^a-z0-9' ]+", " ", t.lower())
    # An apostrophe is a letter inside a word (it's, the keeper's) and punctuation
    # everywhere else. Keeping it everywhere made a phrase in single quotation marks in
    # a source fail to match the same phrase unquoted in a draft — reported as DRIFT,
    # and the difference was a quotation mark. (Measured 2026-09-11, first corpus run.)
    t = re.sub(r"(?<![a-z0-9])'|'(?![a-z0-9])", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def catalog(r=None, book=None):
    """Everything held, whether it is indexed, and whether it is restricted."""
    r = r or root()
    out = []
    by_name = {row.get("file"): row for row in rows(r) if row.get("file")}
    for f in files_on_disk(r):
        idx = index_for(f, r)
        row = by_name.get(f, {})
        # `book` FILTERS, it does not locate. An unmanifested file has no book and is
        # therefore in no filtered view — which is right: `check` reports it as having
        # no manifest row, and that is the finding, not a missing shelf.
        if book and row.get("book") != book:
            continue
        out.append({"book": row.get("book", ""), "file": f,
                    "path": os.path.join(refdir(r), f),
                    "index": idx if os.path.exists(idx) else None,
                    "indexable": f.lower().endswith(SOURCE_EXT),
                    "work": row.get("work", ""), "restricted": row.get("restricted"),
                    "manifested": f in by_name})
    return out


# ---------------------------------------------------------------- commands

def cmd_add(argv):
    def opt(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default
    src = next((a for a in argv if not a.startswith("--")
                and argv[argv.index(a) - 1] not in
                ("--book", "--work", "--edition", "--scheme", "--note")), None)
    book, work = opt("--book"), opt("--work")
    if not src or not book or not work:
        print("usage: references.py add <file> --book <name> --work \"<work> — <author> (<year>)\" "
              "[--edition ...] [--restricted|--public] [--scheme ...] [--note ...]")
        return 1
    if not os.path.exists(src):
        print(f"no such file: {src}")
        return 1
    if book not in books():
        print(f"no book '{book}'. Have: {', '.join(books()) or '(none)'}")
        return 1
    if "--restricted" not in argv and "--public" not in argv:
        print("say which: --restricted (in copyright / edition not redistributable) or --public.\n"
              "There is deliberately no default. The whole cost of getting this wrong is one-way:\n"
              "a copyrighted file committed once is in the history whatever you do next.")
        return 1
    restricted = "--restricted" in argv

    r = root()
    name = os.path.basename(src)
    dest = os.path.join(refdir(r), name)
    rel = f"references/{name}"

    # The .gitignore line goes in BEFORE the bytes land, when the file is restricted.
    # Copying first and ignoring second leaves a window in which another session's
    # `git add -A` can stage it, and that window is the only irreversible thing here.
    added_ignores = []
    if restricted:
        if os.path.exists(deny_file(r)):
            print("gitignore: nothing to write — this folder denies by default, so an "
                  "unlisted file is already ignored")
        else:
            # No deny-by-default file here: fall back to the old per-file root lines
            # rather than leave a restricted source unprotected.
            added_ignores = ensure_ignored(
                [ignore_entry(name),
                 ignore_entry(f"{INDEX_DIR}/{re.sub(r'[.][^.]+$', '', name)}.tsv.gz")], r)
            print(f"gitignore: +{len(added_ignores)} root entr"
                  f"{'y' if len(added_ignores)==1 else 'ies'} (no deny-by-default file here)")
    else:
        if ensure_allowed(name, r):
            print("gitignore: allowed in references/.gitignore "
                  "(the folder denies by default)")

    if os.path.abspath(src) != os.path.abspath(dest):
        if os.path.exists(dest) and sha256(dest) != sha256(src):
            print(f"refusing to overwrite a DIFFERENT file already at {rel}")
            return 1
        shutil.copy2(src, dest)
    digest = sha256(dest)
    print(f"held:  {rel}  sha256 {digest[:16]}…  {os.path.getsize(dest):,} bytes")

    if restricted and tracked(rel, r):
        print(f"  ⚠️  ALREADY TRACKED BY GIT — the ignore line does not remove it from history.\n"
              f"      `git rm --cached {rel}` and decide about the existing commits.")

    scheme_out = ""
    if "--no-index" not in argv:
        idx = index_for(name, r)
        try:
            scheme, got = build_index(dest, idx, opt("--scheme", "auto"))
            scheme_out = f" indexed ({scheme}: {got})"
            print(f"index: {os.path.relpath(idx, r)}  {scheme}: {got}")
        except ImportError as e:
            print(f"index: NOT BUILT — {e}. PDFs need PyMuPDF (`pip install pymupdf`); "
                  f"a .txt needs nothing. Re-run `references.py index {name}`.")
        except Exception as e:
            print(f"index: NOT BUILT — {type(e).__name__}: {e}")

    # The manifest row, in the table's own style.
    edition = opt("--edition", "").strip()
    note = opt("--note", "").strip()
    # THE FULL DIGEST, not a prefix. A truncated hash proves the bytes to a human
    # reading the row and addresses nothing; the S3 shelf keys an object on it
    # (framework/docs/REFERENCE-SHELF.md), and `check` can only detect a file that has
    # been swapped under its own name if the row carries the whole thing.
    prov = "; ".join(x for x in [edition, f"sha256 `{digest}`",
                                 f"added {date.today():%Y-%m-%d}"] if x)
    if note:
        prov += f". {note}"
    if scheme_out:
        prov += f".{scheme_out}"
    redis = ("⚠️ **In copyright** — quote short passages with attribution; do **not** "
             "republish this file. Gitignored."
             if restricted else
             "✅ Public domain / redistributable. Safe to quote and redistribute.")
    # A PIPE IN A CELL SILENTLY DESTROYS THE ROW. The manifest is a markdown table, so a
    # `|` anywhere in the work, the provenance or the note shifts every cell after it —
    # and the failure is not a parse error, it is a row whose Book column now holds half a
    # sentence. Measured 2026-09-14 adding the Tanzil Pickthall, whose provenance names its
    # `surah|ayah|text` format: `check` reported the row as having NO DIGEST and NO
    # REDISTRIBUTION VERDICT, both of which were present and in the wrong cells. Escaped,
    # because the alternative is refusing text a writer legitimately wants to write.
    esc = lambda t: t.replace("|", "\\|")
    row = (f"| [{name}]({name}) | {esc(book)} | {esc(work)} | {esc(prov)} | "
           f"{date.today():%Y-%m-%d} | {esc(redis)} |\n")
    _append_row(readme(r), row)
    print("manifest: row appended to references/README.md")
    if restricted:
        print("\nRestricted. Prove it cannot be staged before you commit anything:\n"
              f"  git check-ignore -v {rel}")
    return 0


def _append_row(path, row):
    """Append after the LAST table row, not at end of file — the README has prose and a
    whole documented section after the table."""
    lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
    last = None
    in_table = False
    for i, l in enumerate(lines):
        if l.startswith("| File |"):
            in_table = True
        elif in_table and l.startswith("|"):
            last = i
        elif in_table and not l.startswith("|"):
            in_table = False
    if last is None:
        lines.append(row)
    else:
        lines.insert(last + 1, row)
    open(path, "w", encoding="utf-8").write("".join(lines))


def cmd_list(argv):
    book = argv[argv.index("--book") + 1] if "--book" in argv else None
    only_unindexed = "--unindexed" in argv
    items = catalog(book=book)
    if only_unindexed:
        items = [i for i in items if not i["index"] and i["indexable"]]
    if not items:
        print("nothing held" + (" unindexed" if only_unindexed else ""))
        return 0
    w = max(len(i["file"]) for i in items)
    cur = None
    n_idx = 0
    for i in items:
        if i["book"] != cur:
            cur = i["book"]
            print(f"\n{cur}/references/")
        flag = "⚠️ " if i["restricted"] else ("   " if i["manifested"] else "?? ")
        if i["index"] and text_layer_verdict(i["path"], i["index"]):
            idx = "NO TEXT"
        elif i["index"]:
            idx = "indexed"
        else:
            idx = "image" if not i["indexable"] else "—"
        n_idx += bool(i["index"])
        print(f"  {flag}{i['file']:<{w}}  {idx:<8} {i['work'][:60]}")
    miss = [i for i in items if not i["index"] and i["indexable"]]
    dead = [i for i in items if i["index"] and text_layer_verdict(i["path"], i["index"])]
    print(f"\n{len(items)} file(s), {n_idx - len(dead)} indexed, {len(miss)} indexable but "
          f"not, {len(dead)} held but UNCHECKABLE (no text layer — needs OCR), "
          f"{len(items)-n_idx-len(miss)} not indexable (page images)")
    for i in dead:
        print(f"  NO TEXT LAYER: {i['file']} — held and citable by eye, but nothing can be "
              f"checked against it. That is a third state, not 'indexed' and not 'not held'.")
    if miss:
        print("An unindexed source cannot be checked against — only remembered.\n"
              "  python3 framework/tools/references.py index <file>")
    return 0


def cmd_index(argv):
    scheme = argv[argv.index("--scheme") + 1] if "--scheme" in argv else "auto"
    book = argv[argv.index("--book") + 1] if "--book" in argv else None
    if "--all" in argv:
        hits = [i for i in catalog(book=book)
                if i["file"].lower().endswith(SOURCE_EXT)
                and ("--force" in argv or not i["index"])]
        if not hits:
            print("nothing to index" + ("" if "--force" in argv else " (all indexed; --force to rebuild)"))
            return 0
    else:
        target = next((a for a in argv if not a.startswith("--")
                       and argv[argv.index(a) - 1] not in ("--scheme", "--book")), None)
        if not target:
            print("usage: references.py index <file> | --all [--book <b>] [--force] "
                  "[--scheme pages|text|kjv]")
            return 1
        hits = [i for i in catalog() if i["file"] == os.path.basename(target)]
        if not hits:
            print(f"not held: {target}. `references.py add` brings a file in.")
            return 1
    r = root()
    failed = 0
    for i in hits:
        out = index_for(i["file"], r)
        # The ignore line lands BEFORE the index exists, for the same one-way reason
        # `add` does it in that order.
        if i["restricted"]:
            added = ensure_ignored(
                [ignore_entry(f"{INDEX_DIR}/{os.path.basename(out)}")], r)
            if added:
                print(f"  gitignore: +{added[0]}  (an index of a copyrighted source "
                      f"IS the copyrighted text)")
        try:
            sch, got = build_index(i["path"], out, scheme)
        except Exception as e:
            print(f"{i['book']}/{i['file']}  NOT INDEXED — {type(e).__name__}: {e}")
            failed += 1
            continue
        print(f"{i['book']}/{i['file']}  {sch}: {got} -> {os.path.relpath(out, r)}")
        v = text_layer_verdict(i["path"], out)
        if v:
            print(f"  ⚠️  {v}")
            failed += 1
    if failed:
        print(f"\n{failed} source(s) NOT indexed — they cannot be checked against, "
              f"and `check_quotes.py` will say so rather than pass them.")
    return 4 if failed else 0


def cmd_search(argv):
    terms = [a for a in argv if not a.startswith("-")]
    if not terms:
        print('usage: references.py search "<phrase>" [--book <b>] [--source <substr>] [-n 5]')
        return 1
    phrase = norm(terms[0])
    book = argv[argv.index("--book") + 1] if "--book" in argv else None
    srcf = argv[argv.index("--source") + 1].lower() if "--source" in argv else None
    limit = int(argv[argv.index("-n") + 1]) if "-n" in argv else 5
    if not phrase:
        print("nothing to search for")
        return 1

    items = [i for i in catalog(book=book) if i["index"]]
    if srcf:
        items = [i for i in items if srcf in i["file"].lower() or srcf in i["work"].lower()]
    if not items:
        print("no indexed source matches that filter. `references.py list --unindexed`")
        return 1

    total = 0
    for i in items:
        _, stream, offsets = load_index(i["index"])
        at, hits = 0, 0
        while hits < limit:
            j = stream.find(phrase, at)
            if j < 0:
                break
            loc = locate(offsets, j)
            ctx = stream[max(0, j - 60):j + len(phrase) + 60]
            print(f"{i['book']}/{i['file']} @ {loc}\n    …{ctx}…")
            at, hits, total = j + len(phrase), hits + 1, total + 1
    print(f"\n{total} hit(s) across {len(items)} indexed source(s)")
    if not total:
        print("Not found LOCALLY. That is the answer to report — not a reason to supply the\n"
              "quotation from memory. Either the wording is off, or the desk does not hold\n"
              "the source and needs to (`references.py add`).")
    return 0


# ---------------------------------------------------------------- the shelf (S3)

SHELF_CONFIG = os.path.join("references", "shelf.yaml")

SHELF_HELP = """no shelf configured. The bucket is defined in infra/lib/reference-shelf-stack.ts
and deployed as the DeskReferenceShelf stack; its output names the bucket. Then write
references/shelf.yaml:

  shelf:
    bucket: desk-references-<account>
    region: us-east-1
    aws_profile: muffinlabs      # SSO, as the store does. No long-lived keys on disk.

Deliberately NOT folded into publishing/store.yaml: that file describes the public read
path, and reading a config should make obvious which bucket the world can see."""


def shelf_config(r=None):
    """The shelf's bucket, or None. Never invents a default — an unconfigured shelf is a
    state to report, not one to guess at."""
    r = r or root()
    p = os.path.join(r, SHELF_CONFIG)
    if not os.path.exists(p):
        return None
    try:
        import yaml
    except ImportError:
        print("shelf: PyYAML missing; pip install pyyaml")
        return None
    with open(p, encoding="utf-8") as f:
        cfg = (yaml.safe_load(f) or {}).get("shelf") or {}
    return cfg if cfg.get("bucket") else None


def shelf_client(cfg):
    try:
        import boto3
    except ImportError:
        print("shelf: boto3 missing; pip install boto3")
        return None
    sess = boto3.Session(profile_name=cfg.get("aws_profile") or None,
                         region_name=cfg.get("region") or None)
    return sess.client("s3")


def shelf_key(digest, name, index=False):
    """refs/<sha256>/<filename>, and the index under the SOURCE's hash.

    The hash prefix carries integrity and makes upload idempotent; the filename leaf keeps
    a console listing legible. There is no book in the key and there would not have been
    one even before the shelf was consolidated — content addressing dedupes across books
    whether or not the disk does.
    """
    if index:
        stem = re.sub(r"\.(pdf|txt|md|html?|epub)$", "", name, flags=re.I)
        return f"refs/{digest}/{INDEX_DIR}/{stem}.tsv.gz"
    return f"refs/{digest}/{name}"


def _shelf_targets(r):
    """(row, path, digest) for every manifest row this tool can address.

    A row is REFUSED, not guessed at, when it has no redistribution verdict — `check`
    already treats that as restricted, and `push` must not be the tool that quietly
    settles a question the manifest has left open — or when its digest is absent,
    truncated, or disagrees with the file. An address that is not the file's own hash is
    not an address.
    """
    ok, refused = [], []
    by_name = {x["file"]: x for x in rows(r) if x.get("file") and "unparsed" not in x}
    for f in files_on_disk(r):
        row = by_name.get(f)
        if not row:
            refused.append((f, "no manifest row")); continue
        if not row.get("verdict_stated"):
            refused.append((f, "no redistribution verdict in its row")); continue
        path = os.path.join(refdir(r), f)
        d, st = held_digest(row, path)
        if st == "none":
            refused.append((f, "no digest in its row — `references.py rehash`")); continue
        if st == "mismatch":
            refused.append((f, "DIGEST MISMATCH — the row describes other bytes")); continue
        if len(d) < 64:
            refused.append((f, "truncated digest — `references.py rehash`")); continue
        ok.append((row, path, d))
    return ok, refused


def cmd_push(argv):
    """Upload every held source the shelf does not already have."""
    r = root()
    cfg = shelf_config(r)
    if not cfg:
        print(SHELF_HELP); return 1
    s3 = shelf_client(cfg)
    if not s3:
        return 1
    dry = "--dry-run" in argv
    book = argv[argv.index("--book") + 1] if "--book" in argv else None
    with_idx = "--no-indexes" not in argv
    bucket = cfg["bucket"]
    ok, refused = _shelf_targets(r)
    if book:
        ok = [t for t in ok if t[0].get("book") == book]
    sent = skipped = 0
    for row, path, d in ok:
        name = row["file"]
        items = [(shelf_key(d, name), path)]
        idx = index_for(name, r)
        if with_idx and os.path.exists(idx):
            items.append((shelf_key(d, name, index=True), idx))
        for key, src in items:
            try:
                s3.head_object(Bucket=bucket, Key=key)
                skipped += 1
                continue
            except Exception:
                pass
            if dry:
                print(f"  would push  {key}  ({os.path.getsize(src):,} bytes)")
            else:
                s3.upload_file(src, bucket, key)
                print(f"  pushed  {key}  ({os.path.getsize(src):,} bytes)")
            sent += 1
    for f, why in refused:
        print(f"  REFUSED {f}: {why}")
    print(f"\n{'(dry run) ' if dry else ''}{sent} object(s) "
          f"{'to push' if dry else 'pushed'}, {skipped} already on the shelf, "
          f"{len(refused)} refused")
    return 4 if refused else 0


def cmd_pull(argv):
    """Fetch what the manifest names and this machine does not have."""
    r = root()
    cfg = shelf_config(r)
    if not cfg:
        print(SHELF_HELP); return 1
    s3 = shelf_client(cfg)
    if not s3:
        return 1
    bucket = cfg["bucket"]
    only_idx = "--indexes-only" in argv
    book = argv[argv.index("--book") + 1] if "--book" in argv else None
    want = [a for a in argv if not a.startswith("--")
            and argv[argv.index(a) - 1] != "--book"]
    disk = set(files_on_disk(r))
    got = missed = 0
    for row in rows(r):
        f = row.get("file")
        if not f or "unparsed" in row:
            continue
        if book and row.get("book") != book:
            continue
        if want and f not in want:
            continue
        d = row.get("digest")
        if not d or len(d) < 64:
            print(f"  {f}: no full digest in its row, so nothing can address it "
                  f"— `references.py rehash`")
            missed += 1
            continue
        jobs = []
        if not only_idx and f not in disk:
            jobs.append((shelf_key(d, f), os.path.join(refdir(r), f), d))
        idx = index_for(f, r)
        if not os.path.exists(idx):
            jobs.append((shelf_key(d, f, index=True), idx, None))
        for key, dest, expect in jobs:
            tmp = dest + ".pulling"
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                s3.download_file(bucket, key, tmp)
            except Exception as e:                                # noqa: BLE001
                os.path.exists(tmp) and os.remove(tmp)
                print(f"  {f}: not on the shelf ({type(e).__name__})")
                missed += 1
                continue
            # THE BYTES MUST BE THE BYTES THE ROW NAMES. A shelf that can hand back
            # something else is worse than an empty one, because the file then looks held.
            if expect and sha256(tmp) != expect:
                os.remove(tmp)
                print(f"  ⚠️  {f}: the shelf returned bytes that are not {expect[:16]}… "
                      f"— NOT written")
                missed += 1
                continue
            if os.path.exists(dest):
                # Never overwrite. An annotated or re-OCR'd local copy is the one thing
                # here that no version history holds.
                os.remove(tmp)
                print(f"  {f}: already on disk and differs — left alone")
                continue
            os.replace(tmp, dest)
            print(f"  pulled  {os.path.relpath(dest, r)}")
            got += 1
    print(f"\n{got} pulled, {missed} not available")
    return 4 if missed else 0


def cmd_rehash(argv):
    """Fill the FULL sha256 into every manifest row, once.

    Fifty rows were hand-written with a 16-character prefix and an ellipsis, and two
    with no digest at all. A prefix proves the bytes to a human reading the row and
    addresses nothing: the S3 shelf keys an object on the hash
    (framework/docs/REFERENCE-SHELF.md), and nothing can notice a file swapped under its
    own name unless the row carries the whole digest to compare against.

    A row whose existing prefix does NOT match the file is left alone and reported. That
    is the one case where rewriting would destroy evidence — the row describes bytes
    that are not the bytes on disk, and which of the two is wrong is not this tool's
    call. `--force` rewrites them anyway, and says which.
    """
    r = root()
    force = "--force" in argv
    dry = "--dry-run" in argv
    # NAMED `manifest`, NOT `path`, AND THE NAME IS THE FIX. A loop below walks the held
    # files and wants a path of its own; when both were called `path` the loop's value
    # survived it, and the write at the end put the MANIFEST'S TEXT INTO THE LAST HELD
    # FILE. Measured 2026-09-14: Chiang-story.pdf, the last row in the table, went from a
    # 2.6 MB scan to 50 KB of README — a copyrighted, gitignored, untracked file that git
    # had no copy of. A shadowed name in a function that writes files is not a style
    # matter.
    manifest = readme(r)
    lines = open(manifest, encoding="utf-8").read().splitlines(keepends=True)
    disk = set(files_on_disk(r))
    filled = updated = kept = 0
    conflicts = []
    for row in rows(r):
        f = row.get("file")
        if not f or "unparsed" in row or f not in disk:
            continue
        path = os.path.join(refdir(r), f)
        actual = sha256(path)
        have, st = held_digest(row, path)
        if have == actual:
            kept += 1
            continue
        i = row["line"] - 1
        line = lines[i]
        if st == "mismatch":
            conflicts.append((f, ", ".join(row.get("digests") or []), actual, i))
            if not force:
                continue
            have = (row.get("digests") or [None])[0]
        if have:
            # ONLY the hash that IS the file grows to full length. A row may also record
            # the SOURCE bytes it was fetched as — provenance for an artifact the desk no
            # longer holds, which cannot be expanded and must not be overwritten.
            line = line.replace(have, actual, 1)
            updated += 1
        else:
            # No digest anywhere in the row: add one to the end of the provenance cell,
            # which is where every other row keeps it.
            cells = line.rstrip("\n").split("|")
            cells[4] = cells[4].rstrip() + f", sha256 `{actual}` "
            line = "|".join(cells) + "\n"
            filled += 1
        lines[i] = line
    if not dry:
        # Belt and braces: the only file this function may write is the manifest.
        assert os.path.basename(manifest) == "README.md", manifest
        open(manifest, "w", encoding="utf-8").write("".join(lines))
    for f, have, actual, _ in conflicts:
        print(f"  ⚠️  DIGEST MISMATCH: {f}\n"
              f"      row says  {have}…\n"
              f"      file is   {actual}\n"
              f"      The row describes bytes that are not on disk. Decide which is "
              f"wrong before rewriting; `--force` rewrites the row to the file.")
    print(f"{'(dry run) ' if dry else ''}"
          f"{updated} row(s) completed, {filled} filled in, {kept} already full, "
          f"{len(conflicts)} mismatch(es)")
    return 4 if conflicts and not force else 0


def cmd_check(argv):
    r = root()
    bad = 0
    rws = rows(r)
    unparsed = [x for x in rws if "unparsed" in x]
    by_name = {x["file"]: x for x in rws if x.get("file") and "unparsed" not in x}
    disk = set(files_on_disk(r))
    known = set(books(r))
    print(f"references/  {len(disk)} file(s), {len(by_name)} manifest row(s)")
    for u in unparsed:
        print(f"  UNREADABLE ROW line {u['line']}: {u['unparsed'][:80]}")
        bad += 1
    for f in sorted(disk - set(by_name)):
        print(f"  NO MANIFEST ROW: {f}")
        bad += 1
    for f in sorted(set(by_name) - disk):
        print(f"  ROW WITH NO FILE: {f}  (line {by_name[f]['line']})")
        bad += 1
    if not os.path.exists(deny_file(r)):
        print("  NO DENY-BY-DEFAULT .gitignore in this folder — a new file here is "
              "committable until somebody remembers a line. "
              "`references.py add --public` creates it.")
        bad += 1
    for f in sorted(disk & set(by_name)):
        row = by_name[f]
        rel = f"references/{f}"
        # The Book column is the only thing left of the old per-book directories, so it
        # has to be real: a row naming a book the desk does not have is a filter that
        # silently matches nothing.
        b = (row.get("book") or "").strip()
        if not b:
            print(f"  NO BOOK: {f}  (line {row['line']}) — the Book column is empty, so "
                  f"`--book` can never select this row")
            bad += 1
        elif b not in known:
            print(f"  UNKNOWN BOOK {b!r}: {f}  (line {row['line']}) — no projects/{b}/. "
                  f"Have: {', '.join(sorted(known)) or '(none)'}")
            bad += 1
        if not row["restricted"] and is_ignored(rel, r) and not tracked(rel, r):
            # The safe failure, made visible. Deny-by-default means an unlisted public
            # source is silently uncommittable; silence is what turns a safe failure
            # into a lost one.
            print(f"  PUBLIC BUT NOT COMMITTABLE: {f} — held, redistributable, and "
                  f"ignored. Add `!{f}` to references/.gitignore.")
            bad += 1
        # THE DIGEST IS A SECOND RECORD OF THE SAME FACT, written at a different time,
        # and the only thing that can notice a file swapped under its own name — a
        # re-download that changed edition while the row went on describing the old one.
        path = os.path.join(refdir(r), f)
        d, st = held_digest(row, path)
        if st == "none":
            print(f"  NO DIGEST: {f}  (line {row['line']}) — nothing can tell whether "
                  f"these are the bytes the row describes. `references.py rehash`")
            bad += 1
        elif st == "mismatch":
            # A MISMATCH IS NOT A TRUNCATION, and the two must not share a message.
            # `rehash` deliberately refuses this row, so telling the reader to run it
            # would send them to a tool that does nothing and looks broken. Every hash
            # the row carries is printed, because a row with several is exactly where a
            # reader needs to see which ones were considered.
            print(f"  ⚠️  DIGEST MISMATCH: {f}  (line {row['line']}) — the row describes "
                  f"bytes that are not on disk\n"
                  f"      row says  {', '.join(x + '…' for x in row.get('digests') or [])}\n"
                  f"      file is   {sha256(path)}")
            bad += 1
        elif len(d) < 64:
            print(f"  TRUNCATED DIGEST: {f}  (line {row['line']}) — the prefix "
                  f"matches, but a prefix addresses nothing. `references.py rehash`")
            bad += 1
        if not row.get("verdict_stated"):
            # Fail-closed protects the bytes; this gets the ROW fixed. A cell this
            # parser cannot classify is treated as restricted AND reported, because one
            # such row sat unreadable through two weeks of shelf growth and nothing
            # would ever have told anyone.
            print(f"  REDISTRIBUTION NOT STATED — no {' / '.join(VERDICT_MARKS)} in "
                  f"the last column, so this file is treated as RESTRICTED until the "
                  f"row says otherwise: {f}  (line {row['line']})")
            bad += 1
        # If the FILE is already gitignored, its index must be too — whatever the
        # manifest row says, and especially when the row says nothing. The stricter of
        # the two signals wins, because only one direction is recoverable.
        file_ignored = is_ignored(rel, r)
        if row["restricted"] or file_ignored:
            if row["restricted"] and not file_ignored:
                print(f"  ⚠️  RESTRICTED AND NOT GITIGNORED: {rel}")
                bad += 1
            if row["restricted"] and tracked(rel, r):
                print(f"  ⚠️  RESTRICTED AND TRACKED BY GIT: {rel}")
                bad += 1
            idx = index_for(f, r)
            if os.path.exists(idx) and not is_ignored(os.path.relpath(idx, r), r):
                print(f"  ⚠️  INDEX OF A RESTRICTED SOURCE NOT GITIGNORED: "
                      f"{os.path.relpath(idx, r)}  (an index IS the text)")
                bad += 1
    n_idx = n_indexable = 0
    for f in sorted(disk):
        n_indexable += f.lower().endswith(SOURCE_EXT)
        idx = index_for(f, r)
        if not os.path.exists(idx):
            continue
        n_idx += 1
        v = text_layer_verdict(os.path.join(refdir(r), f), idx)
        if v:
            print(f"  ⚠️  {f}: {v}")
            bad += 1
    print(f"  indexed: {n_idx}/{n_indexable} indexable "
          f"({len(disk)-n_indexable} page image(s))")

    # ---- the shelf -------------------------------------------------------------
    # Deny-by-default bought safety by trading a copyright leak for a SINGLE POINT OF
    # FAILURE: the sources held precisely because they are copyrighted are the ones no
    # repo has a copy of. That is worth saying on every run, configured or not — the
    # number is the whole argument for the shelf, and it was invisible until it was
    # counted. (framework/docs/REFERENCE-SHELF.md.)
    only_here = sorted(f for f in disk
                       if is_ignored(f"references/{f}", r)
                       and not tracked(f"references/{f}", r))
    cfg = shelf_config(r)
    if not cfg:
        if only_here:
            mb = sum(os.path.getsize(os.path.join(refdir(r), f))
                     for f in only_here) / (1 << 20)
            print(f"  shelf: NOT CONFIGURED — {len(only_here)} source(s), {mb:.0f} MB, "
                  f"exist on this machine and in no repo.")
            print(f"         Held because they are copyrighted, which is exactly why "
                  f"nothing else has them. `references.py push`")
    elif "--shelf" in argv:
        s3 = shelf_client(cfg)
        if not s3:
            # A skip is not a pass, and this one says which it is.
            print("  shelf: SKIPPED — configured but unreachable (no boto3/credentials)")
        else:
            ok_t, _ = _shelf_targets(r)
            on_shelf = missing = 0
            for row, path, d in ok_t:
                try:
                    s3.head_object(Bucket=cfg["bucket"],
                                   Key=shelf_key(d, row["file"]))
                    on_shelf += 1
                except Exception:                                  # noqa: BLE001
                    print(f"  ON DISK, NOT ON THE SHELF: {row['file']}")
                    missing += 1
                    bad += 1
            for row in rows(r):
                f = row.get("file")
                if not f or "unparsed" in row or f in disk:
                    continue
                d = row.get("digest")
                if not d or len(d) < 64:
                    continue
                try:
                    s3.head_object(Bucket=cfg["bucket"], Key=shelf_key(d, f))
                    print(f"  NOT HELD, BUT ON THE SHELF: {f} "
                          f"— `references.py pull {f}`")
                    bad += 1
                except Exception:                                  # noqa: BLE001
                    pass
            print(f"  shelf: {on_shelf} on the shelf, {missing} not")
    else:
        print("  shelf: configured — `check --shelf` compares against it")

    print("\nOK" if not bad else f"\n{bad} problem(s)")
    return 0 if not bad else 4


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__.strip())
        return 1
    cmd, rest = argv[0], argv[1:]
    fn = {"add": cmd_add, "list": cmd_list, "index": cmd_index,
          "search": cmd_search, "check": cmd_check, "rehash": cmd_rehash,
          "push": cmd_push, "pull": cmd_pull}.get(cmd)
    if not fn:
        print(f"unknown command: {cmd}\n")
        print(__doc__.strip())
        return 1
    return fn(rest)


if __name__ == "__main__":
    sys.exit(main())
