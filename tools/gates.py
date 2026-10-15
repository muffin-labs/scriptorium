#!/usr/bin/env python3
"""gates.py — run every mechanical check a piece has, in one command.

WHY THIS EXISTS
  The gates were a LIST IN PROSE, in `skills/review/SKILL.md`, and a list in prose is
  a list a reader can skim. Measured 2026-09-11: a review ran six of the eight gates,
  skipped `check_loci.py`, and verified the piece's scripture against a website
  instead — while the desk held an indexed KJV and a tool that reads it. The review
  then reported "sources re-opened" in its artifact, which was true of the network and
  not of the repo. Nothing in the pipeline could tell the difference.

  So the fix is not another sentence in a skill file. It is one command that runs
  them all and one record of what it found. (Eric, 2026-09-11: *"anything we can fix
  in our repo to prevent *not* checking a local source?"*)

  `--json` writes the results into the piece's `review.json` under `gates`, so the
  review artifact's gate band REPORTS WHAT RAN rather than what the reviewer typed.
  A gate that was skipped cannot appear there as a pass.

USAGE
  python3 gates.py <piece_dir> [--json] [-v]

EXIT
  0  every gate passed
  1  usage
  4  at least one gate failed — the summary names which
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))

# name, argv-after-tool, and whether a non-zero exit is a FAILURE or merely a WARNING.
# check_stage_direction and check_pronouns report shapes a human must judge, so they
# warn; the rest are facts.
GATES = [
    ("check_links",           ["check_links.py", "{piece}"],           True),
    ("check_verified",        ["check_verified.py", "{piece}"],        True),
    ("check_loci",       ["check_loci.py", "{piece}"],       True),
    ("check_quotes",          ["check_quotes.py", "{piece}"],          True),
    ("check_commonmark",      ["check_commonmark.py", "{piece}"],      True),
    ("check_pronouns",        ["check_pronouns.py", "{piece}"],        False),
    ("check_stage_direction", ["check_stage_direction.py", "{piece}"], False),
    ("check_refs",            ["check_refs.py"],                       True),
    # A `publish_at` that names no zone is refused on the day it is due; catch it at review.
    ("schedule_lint",         ["schedule.py", "lint", "{piece}"],      True),
    # A warning here, a stop at publish (check_captions' own docstring): an uncaptioned
    # figure should be news at review, not on the last step of publishing (2026-10-15).
    ("check_captions",        ["check_captions.py", "{piece}"],        False),
    # Non-fatal HERE and fatal at publish: a draft may not have settled its outlets, but a
    # piece about to go live must be able to reach every one it names. The publish skill runs
    # it as a hard gate at step 0, because the first outlet is the irreversible one.
    ("check_outlets",         ["check_outlets.py", "{piece}"],         False),
]


# Several tools end on a paragraph of caveat rather than on their result — the last
# line of check_quotes is a warning about what a MATCH does not mean, which says
# nothing about this run. So prefer a line that carries a count.
SUMMARY_RE = re.compile(r"(?i)\b\d+\s+(quotation|link|hit|finding|problem|draft|title|"
                        r"gate|piece|sentence|outlet|figure)s?\b|\b0 dead\b|all consistent|verified:")


def summary_of(text):
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    hits = [l.strip() for l in lines if SUMMARY_RE.search(l)]
    return (hits[-1] if hits else (lines[0].strip() if lines else ""))


def run(piece, verbose=False):
    out = []
    for name, argv, fatal in GATES:
        tool = os.path.join(HERE, argv[0])
        if not os.path.exists(tool):
            out.append((name, None, "tool not present in this framework", False))
            continue
        cmd = [sys.executable, tool] + [a.format(piece=piece) for a in argv[1:]]
        p = subprocess.run(cmd, capture_output=True, text=True)
        summary = summary_of(p.stdout) or summary_of(p.stderr) or f"exit {p.returncode}"
        ok = (p.returncode == 0) or not fatal
        out.append((name, p.returncode, summary, ok))
        if verbose and p.returncode:
            print(p.stdout.rstrip() or p.stderr.rstrip())
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__.strip()); sys.exit(1)
    piece = args[0].rstrip("/")
    if not os.path.exists(os.path.join(piece, "draft.md")):
        print(f"no draft.md in {piece}"); sys.exit(1)

    results = run(piece, verbose="-v" in sys.argv)
    width = max(len(n) for n, *_ in results)
    failed = []
    for name, code, summary, ok in results:
        mark = "ok  " if ok and code == 0 else ("warn" if ok else "FAIL")
        if not ok:
            failed.append(name)
        print(f"  {mark}  {name.ljust(width)}  {summary[:120]}")

    if "--json" in sys.argv:
        path = os.path.join(piece, "review.json")
        facts = {}
        if os.path.exists(path):
            facts = json.load(open(path, encoding="utf-8"))
        facts["gates"] = [[n, s] for n, _c, s, _ok in results]
        json.dump(facts, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n  wrote {len(results)} gate result(s) to {path}")

    print(f"\n{len(results)} gate(s) run, {len(failed)} failing"
          + (f": {', '.join(failed)}" if failed else ""))
    sys.exit(4 if failed else 0)


if __name__ == "__main__":
    main()
