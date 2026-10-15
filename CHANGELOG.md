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

- **`voice_privacy` stops reading a style's own checker as the author's prose.** A voice may ship
  MECHANISM beside its constitution — `styles/<name>/check.py`, the mechanical half of a critique
  — and mechanism is not voice: it is usually ported FROM the framework, so it shares whole lines
  with the tools by construction. The scan walked every text file in a voice directory, `.py`
  included, and so reported 97 runs of one voice "leaking" into `img_deck.py`, `md_to_marp.py`
  and `md_to_substack.py` — every one of them code the instance had copied OUT of the framework,
  read backwards as prose going in. The framework side is still scanned whole; the voice side now
  contributes runs from `.md`, `.yaml`, `.yml` and `.txt` only, which is what the docstring always
  said it scanned. A check that cries leak at its own source code gets switched off, and that is
  how a privacy gate actually fails. PATCH.

- **A second path to a published deck, for a talk whose every slide is a picture.**
  `tools/img_deck.py`. The existing path — draft → `md_to_dc.py` → a Claude Design canvas →
  `dc_to_deck.py` → `talk_bundle.py` — exists because a typographic deck needs a design pass.
  A deck built the other way round has none to make: when every slide is an image generated to
  a written specification, with its words carved or lettered inside the frame, the canvas has
  no layout work in it and `md_to_dc.py verify` has nothing to read, because the words are
  pixels. This builds the same output directory `talk_bundle.py` already consumes — `deck.html`
  (`<deck-stage>` + one `<section>` per slide, the same embedder relay `dc_to_deck.py` emits),
  `notes.json`, `deck-stage.js`, `assets/` — straight from `draft.md`.
  **It refuses any slide it cannot render as one picture**, rather than rendering half of it: no
  image, two images, or an image plus text still set as type are each a fault that stops the run
  and names the slide. A deck of pictures has no fallback rendering, so a missing image is a
  blank slide, not a plainer one. **Each image's alt text becomes the slide's accessible text**,
  which in this deck is the only route its words have to a screen reader — so an empty alt is a
  fault too. Speaker notes stay the draft's prose, so the draft is still the one source of the
  script whichever path a talk takes.
  **The desk keeps the masters; the deck ships what a phone can load.** Served copies are resized
  (`--width`, default 1600) and re-encoded as JPEG (`--quality`, default 82), never cropped —
  a crop would silently cut a carved word off a slide edge. The first deck through it went from
  56 MB of PNG masters to 6.2 MB served. `--keep-png` copies the masters through instead, and
  over 20 MB it warns that the result is a download rather than a page.
  Choosing between the two: type on a slide goes through the canvas, because something has to
  decide how that type looks; finished pictures come through here; a deck that mixes them goes
  through the canvas. MINOR.

- **`prepush.py` fetches before it judges the framework pointer, and says what it actually
  checked.** The guard read `refs/remotes/origin/main` as it stood — this clone's MEMORY of the
  remote, not the remote — so once a sibling session pushed the framework, an instance push whose
  pointer was on origin/main all along was refused with *"push the framework first"*. On a desk
  running six sessions at once that is the ordinary case. It now fetches the default branch first,
  and when the fetch cannot run it says the verdict may rest on a stale ref instead of asserting
  a refusal it cannot stand behind. **The default branch is asked of the remote** (`ls-remote
  --symref`) rather than assumed to be `main`, and the name is taken by stripping `refs/heads/`
  rather than splitting on the last slash — `claude/nice-feynman-oxrv57` is one branch name, and
  the obvious `rsplit('/', 1)` turns it into a branch that does not exist. **The stated reason is
  corrected too:** the rule is not that CI cannot fetch the commit (github.com serves any commit
  reachable from a ref) but that `actions/checkout` fetches submodules SHALLOW, so the runner has
  the default branch's history and not a side branch's — the rule stands, its old explanation did
  not. A genuine refusal now names the branch the commit IS on, so the remedy reads *merge it
  into main* instead of *push the framework first*. Nine cases in `test_concurrency.py`, against a
  local repository as `origin` — no network.
- **`gitenv.py`: one named place for the `GIT_*` variables that silently redirect a repository.**
  A git hook always runs with `GIT_DIR` and `GIT_WORK_TREE` set, and they override `-C <dir>` and
  `cwd=` — so a tool asking about one repository, under a hook or under anything a hook started,
  gets the answer for another one, silently and with a zero exit status. It caught `dashboard.py`
  on 2026-10-03 and `prepush.py` on 2026-10-11, the latter being a tool that is *only* ever run
  from a hook, so every repository question it asked was answerable about the wrong repository.
  All seven of `prepush.py`'s git calls now pass `git_env()`; `dashboard.py` imports the filter
  instead of carrying its own copy and still exports `git_env` for its callers. Both were found
  by the pre-push hook refusing a push, which is the gate catching, in its own tooling, exactly
  the class of fault it exists for.

- **`check_status.py` gains `stage`: a live piece's `**Stage:**` line must SAY it is published.**
  The existing `unpublished` finding is a list of seven phrases and only ever sees a
  *contradiction*, so a Stage line can be wrong without using one. Measured 2026-10-11:
  `DASHBOARD.d/278-in-vain.md` read *"stood up 2026-09-03 … Nothing drafted"* for twenty-four days
  after publication while the SAME FILE, four lines down, carried **PUBLISHED 2026-09-09** and the
  reader URL — the append-only history was right and only the head was stale, which is the one
  shape neither a phrase list nor a whole-file search can catch. *"Nothing drafted"* is a stronger
  claim than *"unpublished"* and matched nothing. The new check is **positive** rather than
  negative, and it is checked only where the PATH names the piece — `DASHBOARD.d/NNN-<slug>.md`
  and `pieces/<slug>/README.md` — so there is no guessing at the subject; a Stage line satisfies
  it by carrying *published · live · shipped · re-synced* or one of the piece's own reader URLs.
  *"Eric clicks Publish"* deliberately does not satisfy it, and a line marking its own
  supersession is exempt as everywhere else here. A second weakness fell out of the same change:
  `unpublished` identifies its subject by a backticked `` `slug` `` near the words, so it had also
  missed a fragment reading *"COMPOSED … as a PRIVATE DRAFT … awaiting Eric's Publish"* — a phrase
  that IS on the list — because the fragment never backticks its own slug. The path-based subject
  has no such hole. **Turning it on found five more pieces in the same state and no false
  positives**, two of them READMEs, which this desk calls truth. Eight cases in `test_suite.py`,
  gated by `corpus_prose`.

- **`dashboard.py sync` no longer merges two pieces' fragments, and no longer reverts a fragment
  out of a stale `DASHBOARD.md`.** Two corruptions, both measured on a real desk 2026-09-30, both
  running for weeks in the committed tree. **(1) A fragment with no `## ` heading of its own has
  its text rendered inside the PREVIOUS fragment's block**, so `ingest` read that block as the
  neighbour's and wrote the merged text down — and the next render emitted it twice, and the next
  ingest banked the two. One fragment reached **86 committed copies** of another piece's update
  block and the generated file **125**, growing by one on every sync, across many sessions. The
  same shape applies to a slug held by two fragments, where `ingest` cannot tell which block
  belongs to which file. `ingest` is now **address-checked**: a block is written down only where
  the block-to-fragment map is one-to-one for that slug; a block rendered from more than one
  fragment, a slug held by more than one fragment, and a slug appearing in more than one block
  are each **UNADDRESSABLE**, left strictly alone, and named with the remedy. `check` reports a
  headless fragment by name. **(2) mtime is not provenance in a git checkout** — git stamps every
  file at checkout time, in whatever order it wrote them, which made a `DASHBOARD.md` committed at
  12:48 look newer than fragments committed six hours later, and ingest duly reverted them (a
  published piece back to unpublished, a draft back one version). A **clean** file's age is now the
  commit time of the last commit that touched it, and mtime is read only for a file that is dirty
  or untracked; a tie keeps the fragment. Every overwrite ingest is about to make is **printed**
  with the lines it drops, and `ingest`/`sync` take `--dry-run`.
  Both reads go through a git environment stripped of `GIT_DIR`, `GIT_WORK_TREE` and the other
  repository-redirecting `GIT_*` variables: a git **hook** sets those for everything it runs, and
  they override `-C <dir>`, so a `sync` invoked from a hook would have read the ambient
  repository's history instead of the desk's. The framework's own pre-push run found this by
  going red — `GIT_DIR` pointed at the submodule — and a test case now sets those variables to a
  third repository and proves every read and write still lands in the one under test.
- **`ci_check.py` now runs `test_concurrency.py` as well as `test_suite.py`.** The multi-session
  guards were written as a separate runner while another session held `test_suite.py` and stayed
  out of CI on a note saying to fold them in later — so the dashboard guards were never a gate,
  and the two faults above sat in the tree. Running the second file is cheaper than folding it in.
  (`test_concurrency.py` invokes `git` with an explicit argv and no shell, inside a repository of
  its own under `tempfile.TemporaryDirectory()`, because the provenance it tests *is* the
  repository's record; the tree-untouched hash check is what holds that honest.)
- **`read_manifest()` strips a scalar's surrounding quotes, the way a YAML parser would** —
  PATCH, and it was reaching readers. `title: "X"` is the ordinary way to write a title, and this
  parser handed back the quotes as part of the value, so a Substack post composed as `"X"` with
  literal quote marks **in the two fields a reader sees first**. Caught live mid-publish twice in
  one session: once from `md_to_substack` composing a fresh post, then again from
  `substack_repatch` re-staging the same quotes onto an already-published one. The defect was
  known and had been patched three times locally rather than at the source — `_yaml_manifest` was
  added 2026-09-11 for exactly this (a quoted caption arriving with its quotes on), and
  `piece_header.py` and `substack_notes.py` each carry their own `.strip('"\'')`. Those stay and
  are now redundant rather than load-bearing. A YAML block-scalar opener (`>`, `>-`, `|`, `|-`) is
  left alone. Every importer of `read_manifest` is fixed by this, including `substack_repatch`,
  `substack_sync`, `md_to_clipboard`, `md_to_dc` and `md_to_marp`.
- **`md_to_substack` reads the post header through a real YAML parser** (`_yaml_manifest`) rather
  than `read_manifest`, belt-and-braces alongside the fix above: the header is the most visible
  text a post has, and the YAML path also handles escapes and multi-line scalars the line parser
  cannot.

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
