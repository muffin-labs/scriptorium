# Writing desk — behavior

A markdown-native writing desk run through Claude Code. This framework lives in
`framework/` (a git submodule). Your writing lives in `pieces/` and your tuned
voices in `styles/`, in your instance repo. Copy this file to your instance root
and adjust it.

## The loop

- `DASHBOARD.md` is the top of the desk — one block per piece in flight. It is
  **generated** from `DASHBOARD.d/`; edit the fragment, not the file (see
  *Working alongside other sessions*).
- Each `pieces/<name>/README.md` holds that piece's stage, target style, and the
  single next move.
- Detail lives in `pieces/<name>/outline.md`, `draft.md`, `notes.md`, and
  `log/`.
- **A talk lives in `talks/<slug>/`, the desk's second namespace**, so it can carry the
  same slug as the essay of the same argument. A slug is unique within a namespace, not
  across the desk; `tools/corpus.py` resolves one, and a companion pointer resolves by
  role. See `docs/NAMESPACES.md`.

When asked "what's on the desk," read the dashboard, drill into the live piece
README, and propose one concrete next move. After a writing session, log it
(dated, append-only), update the piece README, and refresh the dashboard block.
The `whats-on-the-desk` skill has the details.

## Styles steer; they don't get trained into a model

A style is structured context that steers a draft — never model weights.

- **Pick a style before drafting.** Every piece names a target style in its
  README. `draft` loads that style's `style.md`, `config.yaml`, and `exemplars/`
  as steering.
- **A publication can carry more than one voice.** A book/publication may name
  several styles — e.g. a witness voice that testifies and an argued-essay voice
  that reasons. Each text picks exactly one; never blend them in a draft. Name
  siblings by a shared prefix (`being-good`, `being-good-essay`); the book README
  lists the voices and says when to use each. See `docs/STYLES.md`.
- **A piece can carry companions** — the poem posted as its Note, the talk of the same
  argument. Each is its own text, in its own **form** (`essay`, `poem`, `note`, `talk`) and its
  own voice, declared under `companions:` in the piece's `publish.yaml` and previewed on the
  piece's one review page. `tools/companions.py check`; see `docs/COMPANIONS.md`.
- **Your voices stay in your instance.** The framework ships generic starters, one per form;
  `tools/voice_privacy.py` fails on any run of your voices' text that reaches the framework.
- **Corrections are append-only.** When you change Claude's wording, the *why*
  goes in `styles/<name>/corrections.md`. Never edit a past correction.
- **The constitution changes only during a `tune-style` pass.** Don't rewrite
  `style.md` mid-draft. Accumulate corrections, then distill them deliberately —
  one change at a time — the way a rule is amended, not patched.

## Publications

- **A desk can carry more than one publication** — an audience, a byline, its voices, and the
  outlets that reach it. They are registered in `publishing/publications.yaml`, and **every piece
  names its one** in `publish.yaml` (`publication: <id>`; `tools/publications.py assign` writes
  it). A piece never spans two: the same argument for two audiences is two pieces.
- **Kept apart per publication:** outlets, styles, **projects** (`projects/<name>/`) — each has one
  owner — **tags** (each publication has its own vocabulary) and **house rules**
  (`publishing/house/<publication>.md`). The content store is shared, so a slug belongs to one
  publication, and the tools refuse a crossing rather than overwrite.
- **What governs a text, most general first: the desk's `CLAUDE.md` → its publication's house file →
  its project → its style.** Keep a publication's conventions out of the desk's `CLAUDE.md`: every
  text on the desk reads it. `publications.py context <slug>` names the layers for one text.
- `python3 framework/tools/publications.py check` — every manifest names a publication and owns
  its outlets; every style and project has one owner, and a style's `config.yaml` names it back. **A one-publication desk needs no registry**; add it with the second publication.
  See `docs/PUBLICATIONS.md`.

## Reading the shelf — search first, sweep for an address, read the page yourself

Source texts live in `references/`, indexed, and a quotation is checked against a file
rather than recalled (`docs/REFERENCE-SHELF.md`). The shelf is far larger than any context
window — a single lexicon volume can run past 180,000 lines — so reading it is always a
question of what you open, not whether you open it.

- **`references.py search "<phrase>"` first.** Every question that has a phrase in it is
  answered there, exactly, at one line per hit. Reach for it instead of recalling a wording.
- **A question with no phrase in it gets a sweep**, and a sweep returns **addresses, never
  words**: a cheap-model subagent reads the span and hands back `<file> @ <line>` with a
  one-line gloss, then you open those lines and read them. Nothing a sweep says may reach a
  draft, a footnote, or a characterization of a source — the shelf exists so that wording
  comes from the page, and a summary wearing a citation is the one form no checker catches.
  The shelf is OCR and visibly damaged; a model asked what a passage *says* will silently
  repair it, which is invisible in a summary and obvious at the line. `docs/REFERENCE-SWEEP.md`.
- **A sweep is not a check and never a substitute for `review`'s re-open of the primary
  sources**, which is a human's. It narrows where the human looks. Most footnote faults on a
  corpus like this are characterizations rather than misquotations, and those pass the quote
  gates green — a sweep is how you find the forty lines worth arguing with.

## Working alongside other sessions

Several Claude sessions run against this desk at once — **six on 2026-09-02**. Most of the desk
is already safe under that, and safe by design: `pieces/<slug>/` has exactly one owner, and logs
and `corrections.md` are append-only. Nothing of that kind was ever damaged. **All the damage
landed on shared singletons**, so those are the things with rules.

- **Never edit `DASHBOARD.md` by hand.** It is **generated** from `DASHBOARD.d/<NNN>-<slug>.md`,
  one fragment per piece. Edit *your piece's fragment*, then run
  `python3 framework/tools/dashboard.py sync`. Two sessions updating two pieces now write two
  different files and cannot collide. *(Before this, the same block was silently overwritten
  three times in one afternoon: every session read the whole file, changed its own block, and
  wrote the whole file back.)* `sync` **ingests hand-edits before it renders**, so if you or
  another session edits the generated file anyway, the work is pulled back into the fragment
  rather than lost — but the fragment is the place to write.
- **Take the lease before a long edit to a piece**, and say what you are doing:
  `python3 framework/tools/lease.py acquire <slug> --what "drafting §V"`, and `release` when
  done. It is **advisory** — it stops nobody, and it is not pretending to. What it buys is that a
  session about to touch a piece finds out in one call that another one already is, and who.
  `lease.py list` shows everything held. A lease whose process is gone reads as stale and can be
  broken; **breaking is recorded in the new lease**, never silent.
- **Cross-reference by slug; check the titles.** Titles move late and often — two pieces were
  retitled mid-session on 2026-09-02 while other files went on naming them the old way, and every
  link still resolved, so nothing could see it. `python3 framework/tools/check_refs.py` compares
  the corpus against itself and reports any slug labelled with two different titles, using each
  README's H1 to say which side is right. **`log/` and `corrections.md` are exempt** — they are
  append-only records of what was true when written, and an old title there is history, not rot.
- **The manifest is the witness; the prose is written by hand.** `publish.yaml` is kept
  current by the sync tools against the live post, so a doc calling a piece unpublished is a
  claim about the past — and five pieces in three days went on being described as drafts after
  they were live (*In Vain*, *The Mask Comes Off Last*, *Rising After Falls*, *What Was Already
  There*, *Not Made of Things That Appear*). `check_status.py --outlets publishing/outlets.yaml`
  reports prose that contradicts a manifest. `check_refs.py` reports a piece named by a title it
  no longer has — in book indexes too, in their `*Title* (`slug`)` form — and a README H1 that
  disagrees with its manifest's title; a retitle that reached one file and not the other is how
  *The Door and the Room* outlived its piece by four days. **Both are gated: the suite runs them
  (`corpus_prose`), so CI and the pre-push hook refuse a push that leaves the corpus disagreeing
  with itself** — which puts the correction in the publishing or retitling commit, the only one
  that knows. The same check refuses a published piece with no `outlets:`: that hole is how *Not
  Made of Things That Appear* sat live on Substack, exported nowhere, invisible to
  `outlet_audit`. `rename_piece.py` runs both after a move and exits 3 if they disagree about
  the piece. **Exempt:** `log/`, `corrections.md`, anything under a dated heading, any line
  marking its own supersession; `check_status` also skips the generated `DASHBOARD.md`.
  **Neither can see a stale DECISION** — the charter went on calling the Fellowship's domain
  "open, and Eric's call" after the site shipped, and no file records that a decision was
  made, so nothing disagrees. That one still needs a human re-reading.
- **Never hard-code a localhost port.** Use `framework/tools/session_port.py`, which derives one
  from the session and **fails loudly** when it is taken. A fixed port plus a swallowed bind error
  once served one session's code to another session's browser. And **identify fetched bytes at the
  point of use** — hash what came back over the wire, not the file you meant to serve.
- **The system pasteboard is global — so it is leased, and pasted in one process.**
  `md_to_clipboard.py --paste` takes the `pasteboard` lease (waits up to 120s, names the holder on
  timeout, never breaks it), loads the board, reads it back, raises the Chrome tab by URL, and sends
  the real ⌘V itself, so the board is exposed for milliseconds rather than a tool round-trip. Never
  `pbcopy` around it. (Three pasteboard races in one afternoon, 2026-09-07, all to sibling sessions.
  Needs Accessibility permission for the app running the tool.)
- **`git commit -- <paths>`, never `git add` then `git commit`. The INDEX is shared too.**
  Another session's `git add` stages files in the same `.git/index`, and a bare `git commit` then
  sweeps them in — measured 2026-09-03, when a two-file commit carried four files of another
  session's `hollow-flute` work that were never added by this one. **Pathspec-limited commit
  ignores whatever else is staged**, which is the only form that is actually scoped.
- **Scope your commits by path — but a shared ledger is the exception, and it is not worth
  agonizing over.** Commit the piece you worked on and its style edits; do not sweep in another
  session's in-flight work. **The rule is about `pieces/<slug>/` — somebody else's `draft.md`,
  or a whole piece directory that is theirs.** It does **not** govern the book-level append-only
  ledgers (`facts.md`, `pieces.md`, `sources.md`), where four sessions may be appending at once
  and there is no clean seam to cut along: **commit those whole, and say in the message what rode
  along.** (Eric, 2026-09-02: *"I'm fine with changes from other sessions in facts.md being
  committed in different sessions."*) The reason the disclosure still matters is that the commit
  message becomes the only record of what was reviewed and what merely travelled.
- **Every push runs CI first — never `git push --no-verify`.** `.githooks/pre-push` exports the
  exact commit being pushed (from the instance, the framework too, at its recorded pointer) and
  runs `tools/ci_check.py` on it — the command GitHub runs — in a venv holding only
  `requirements-ci.txt`. A red run refuses the push and names the failed checks: fix them, or wait
  for the session whose piece is red; don't skip the gate. (Every push on 2026-09-11, both repos,
  went red on GitHub for things a local suite run could not see: packages this Mac has and the
  runner doesn't, a guard that lived only in the workflow, and other sessions' uncommitted files
  making the committed tree look whole.) **Once per clone:** `python3 framework/tools/prepush.py
  install` sets `core.hooksPath=.githooks` in the instance and the framework and builds the venv.
  An instance push whose framework pointer is not on the framework's origin/main is refused — push
  the framework first. A new third-party import goes into `framework/requirements-ci.txt` in the
  same commit, or CI and the hook both go red.

## The framework is a fork, and it is versioned

- `framework/` is normally the author's **fork** of scriptorium, on `main`, with `upstream`
  as a second remote. Framework changes made while working on a piece are committed **in
  `framework/`, by path**, pushed to the fork, and the pointer bumped in the desk; pull
  `upstream main` when the author wants what changed there. Never leave a framework change
  as an uncommitted diff in the submodule.
- **Semantic versioning, kept in the same commit.** Any change a desk would notice — a new or
  changed skill, tool, manifest key, gate, template, or doc that changes what a desk should
  do — adds a line under *Unreleased* in `framework/CHANGELOG.md`. A release bumps `VERSION`,
  moves the lines under a version heading, tags `vX.Y.Z`, and publishes the GitHub release
  with the same text. MAJOR: a desk must change to keep working. MINOR: a desk can adopt or
  ignore it. PATCH: a fix that changes no interface.

## Principles

- **Logs are append-only.** Never edit a past writing-log entry — a log you can
  revise isn't evidence of what you actually wrote.
- **The README is truth; the dashboard is a summary.** If they disagree,
  reconcile rather than guess.
- **Draft freely; tune deliberately.** Drafts are cheap and disposable. The
  style constitution is load-bearing and changes slowly.
- **Add structure only when it's used.** A new skill, style, or template earns
  its place by being used, not by being anticipated.
- **The scaffold holds the reasoning; the prose carries only the result.** A correction
  replaces the wrong text with the corrected text and adds nothing: no sentence in
  the draft explains or justifies the change. Readers only ever meet the current
  version, so a line that disputes an earlier one ("but that was never really about
  X") exposes the editing instead of advancing the argument. The why belongs in the
  scaffold — corrections, facts, notes — and the draft stays clean of it.
