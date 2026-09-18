# Changelog

Scriptorium uses [semantic versioning](https://semver.org). The version is in `VERSION`, every
release is a git tag `vX.Y.Z` on `main`, and this file says what each one changed. The rule for
which number moves, written for the person deciding at release time:

- **MAJOR** — a desk has to change to keep working: a `publish.yaml` key renamed or removed, a
  tool's command line or exit codes changed, a skill's contract with the instance changed, a
  template's layout moved.
- **MINOR** — something a desk can adopt or ignore: a new skill, tool, manifest key, gate, or
  outlet kind; a doc that changes what the desk should do next.
- **PATCH** — a fix that changes no interface: a guard that now fires where it should, a
  converter that renders what it always meant to.

A desk pins the framework by submodule commit, so a tag is a name for a commit a desk can move
to on purpose, not something that moves a desk by itself.

Every change that a desk would notice gets a line under **Unreleased** in the same commit; a
release moves those lines under a version heading, bumps `VERSION`, tags, and publishes the
GitHub release with the same text.

## Unreleased

- **The reference sweep — a convention for reading a shelf larger than the context window.**
  `docs/REFERENCE-SWEEP.md`, and a section in `CLAUDE.md`. `references.py search` answers any
  question with a phrase in it; a question with none goes to a cheap-model subagent that returns
  **addresses, never words** (`<file> @ <line>` plus a gloss), and the session opens those lines
  itself. Nothing a sweep says may reach a draft, a footnote, or a characterization of a source.
  The shelf on this desk is 41 text sources and 1,383,253 lines, the largest single volume 188,974
  — unreadable whole — and it is OCR: a model asked what a passage *says* repairs the damage
  silently, which a summary hides and a line number cannot. It is aimed at the fault class the
  quote gates pass green, since this corpus's footnote faults are mostly characterizations of a
  source rather than misquotations. It replaces no check and does not stand in for `review`'s
  re-open of the primary sources, which is a human's. MINOR.

- **`outlet_audit.py` compares tags.** Every text on the store index — pieces and talks, tag ids
  and labels, from one fetch — and every Substack post the forward check just found live, through
  `substack_tags`' own plan, against the desk. A finding is `TAGS … missing / extra / relabeled`
  and exits 3; an unreadable tag source exits 2 ("not checked" is not "matches"). `--no-tags`
  skips it; `--store` names the store config (default: `store.yaml` beside `--config`). A tag
  added to a live text reaches no outlet by itself, and two texts had been found publicly
  untagged by a person looking at a page. MINOR.
- **`outlet_audit.py` no longer counts a scheduled copy as present.** A waiting outlet
  (`on_schedule: at_moment`) whose moment is still ahead is judged by its schedule even when its
  address answers 200 — Substack serves a scheduled post's URL with a teaser. It reads
  *scheduled* (or *NOT SCHEDULED*) as a missing copy always did. PATCH.

- **`prepush.py` builds its CI venv on Windows.** `venv_python` looked for the interpreter at
  `bin/python`, which only exists on POSIX; native Windows Python's `venv` module writes
  `Scripts/python.exe`, so every push failed with a `FileNotFoundError` before CI ever ran. PATCH.

- **`engine_suite`'s node-availability check no longer crashes when node isn't installed at
  all.** It probed with `subprocess.run(['node', '--version'])` and only checked the return
  code; with no `node` on PATH that raises `FileNotFoundError` before a return code exists,
  so a machine without node failed CI instead of skipping the suite, same as every other
  node-gated check here already does with `shutil.which('node')`. PATCH.

- **`prepush.py` decodes the CI subprocess's output as UTF-8, not the console code page.**
  The child now runs in `PYTHONUTF8` mode and emits UTF-8, but the parent's
  `subprocess.run(..., text=True)` decoded with Windows' `cp1252` by default, so any non-ASCII
  byte in CI's output crashed the reader thread before the hook could even report a verdict.
  PATCH.

- **`requirements-ci.txt` gains `tzdata`.** Windows ships no IANA timezone database, so
  `zoneinfo.ZoneInfo('America/New_York')` in `schedule.py` raised on every Windows run; the
  `tzdata` package supplies it and is a no-op on macOS/Linux, which already have system tz
  data. PATCH.

- **`prepush.py` runs the CI subprocess in Python's UTF-8 mode.** `open()`'s default encoding
  on Windows is the console's ANSI code page, not UTF-8; `test_suite.py`'s own fixtures write
  non-ASCII text (`from §V`) with no encoding named, which then failed to decode as UTF-8 on
  read and turned every push red on Windows regardless of the commit's actual content. Setting
  `PYTHONUTF8=1` on the subprocess env fixes the default without touching the 223 unguarded
  `open()` calls in the vendored test suite. PATCH.

- **`schedule.py record` writes its free text as quoted YAML scalars and refuses a result that
  would not parse** — the fix `arm` already had. An `--evidence` naming an API path with a colon
  had made a manifest unreadable to every tool on the desk; and the block is placed through a
  callable, so an ellipsis in the evidence is not read as a regex escape. PATCH.

- **A talk's tags live on the desk and reach the store.** `talks/<slug>/talk.yaml` takes `tags:`
  and `publication:` like a piece's `publish.yaml`; `tags.py` spans both namespaces (name a talk
  `talks/<slug>` — a bare slug still prefers `pieces/`); `talk_bundle.py` resolves them against
  the publication's vocabulary and writes `[{tag, label}]` into the talk's record and its index
  entry, the same shape `bundle_pieces.py` writes for a piece, so a site reads a talk's tags where
  it reads an essay's. It refuses a bundle built against a desk that does not know the talk
  (exit 3), a tag the vocabulary does not define (exit 8), tags with no publication (exit 9), and
  `tags:` in the site-side `piece.yaml`. **A desk adopts this by adding `publication:` and `tags:`
  to its talks**; a talk without them bundles as before and carries none.

- **Adoption is fork-first** (README, SETUP.md, `new-desk --framework <your fork>` with
  `upstream` as a second remote), and **CONTRIBUTING.md** plus a pull-request template say what
  belongs upstream, what never does, and what a PR carries. Docs only; nothing a desk must change.

## 0.1.0 — 2026-09-15

The first tagged release, cut the day the framework moved to the `muffin-labs` organization.
It is `0.x` on purpose: the writing loop, the publishing transport and the shared-desk rules are
in daily use, and their interfaces still move.

- **The writing loop:** `draft`, `critique`, `style-audit`, `tune-style`, `rewrite`, `review`
  (the review artifact, with every proposed change anchored in the prose), `tags`, `talk`,
  `whats-on-the-desk`, and the book-scale set (`book-status`, `gmc`, `chapter-draft`,
  `chapter-audit`, `pov-audit`, `continuity-audit`).
- **Styles as steering:** a style is a folder — constitution, config, exemplars, an append-only
  corrections file — and `tune-style` is the gated pass that folds corrections in.
- **Publishing:** Substack (compose, surgical republish, two-way sync with a sealed baseline,
  verify against the live page block by block, cover, tags, Notes), LinkedIn Articles (the copy
  with *Originally published at*, the hero as the cover, figures with their alt and captions),
  and quire content-store sites (`md_to_site` → `bundle_pieces` → `store_publish`).
- **Scheduling:** `publish_at` with per-outlet `on_schedule`, native-scheduler records, a
  publication-day runbook, and the Note by scheduled task after the post is live.
- **Gates:** links, verified clearance, scripture loci, held-source quotations, CommonMark,
  pronouns, stage direction, cross-references, captions, outlets — `gates.py` runs them all.
- **The shared desk:** advisory leases, a generated dashboard from per-piece fragments,
  path-scoped commits, a session-derived port, a pre-push hook that runs CI on the exact commit.
- **Adoption:** `tools/new-desk` scaffolds a private instance from a fork of this repo, with CI.
