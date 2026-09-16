---
name: rewrite
description: Rewrite a finished or already-published piece in a voice that has moved since it was written — after a tune-style pass, or when the author says "rewrite X in the new voice", "re-voice this", "bring this up to the current constitution". Asks the depth questions first (how deep; are the footnotes kept; which figure is run literally; what the close does; which facts and consent lines are touched; whether the title still fits; and it asks the author for a hero image rather than choosing one), then drafts a full new version into draft.md, gates it with critique, RENDERS A REVIEW ARTIFACT the author can actually read, and STOPS for their read. Renames the piece's slug when the title changes. Never re-syncs a live post itself; that is publish, invoked separately on the author's word.
---

# Rewrite

A voice moves. A `tune-style` pass folds a stretch of corrections into the constitution, and
every piece written under the old constitution is now slightly in the wrong voice. This skill
brings one of them forward: the same piece, said the way the voice says things now.

It is not `draft` (which starts from notes and an outline) and not `critique` (which edits
what is there). It is a full re-say of a piece whose facts, arc and footnotes already exist,
under a constitution that has changed. Most of the work is deciding what stays fixed.

## Before writing anything

1. **Read the piece's scaffold, not just its prose.** `README.md` (stage, voice, decisions,
   guardrails, consent), `publish.yaml` (is it live? which footnotes are verified?), the `log/`
   (what has been corrected on the page since it published — those corrections are load-bearing
   and must survive), and the ledger entries it rests on (`projects/<name>/facts.md` for a
   witness-anchored piece). And the layers above the voice: `python3 framework/tools/publications.py context <slug>` names the text's publication, its
   **house file** (`publishing/house/<publication>.md`), its **project** (`projects/<name>/`) and its
   style. Load the house file and the project's README/brief with the style: the house file holds
   the conventions every voice of that publication keeps, and the desk's `CLAUDE.md` does not carry
   them. No house file means the publication keeps none beyond the desk's — never borrow another
   publication's. (2026-09-15.)
2. **Read what changed in the voice.** `git log` on `styles/<voice>/style.md` and `config.yaml`
   since the piece's last version, and the `corrections.md` entries in that window. The rewrite is
   *for* those changes; name them to yourself before you touch a sentence. A rule that postdates the
   live text (the Son's capital pronoun, the bracketed house pronoun, the American-English fold) is
   applied now, and the log says which ones were.
3. **Ask the depth questions, with a lean on each**, so "go with your leans" is a complete answer:
   - **How deep?** The witness voice's tune (2026-09-07) argued for shorter — no length floor, stop
     when it lands — and *Flow* came out a third shorter with the same beats. The essay voice's tune
     was deliberately lighter, and a texture pass keeps the sections and the footnotes. **Say which
     you intend.** When the author answers "I don't mind if it's extra work," that is the deep one:
     sections and footnotes may go.
   - **Are the footnotes kept?** A verified footnote is an asset: keep it byte-for-byte (splice the
     old text in programmatically, then prove it identical) and the `verified:` block still stands.
     Cut one only with the prose it supports, renumber, and update every `[^n]` reference in
     `publish.yaml`'s `verified:` text. Never write a new footnote in a rewrite without verifying it;
     a rewrite is not an anchor pass.
   - **Which figure is run literally?** The essay voice now takes its governing figure to its
     accounting and never glosses it. Pick one (the one the piece already has — the confluence, the
     tuned instrument), run it in its own section, and add no new figure. The witness voice's
     equivalent is the household comparison and the one odd detail.
   - **What does the close do?** An inversion of the opening is permitted and a bow is not, in
     both voices. The witness close is the smallest true sentence; the essay close opens a space.
   - **Which lines are consent-bound or fact-bound?** A paragraph about a real person written under
     a recorded consent boundary is re-voiced in sentence length only, with no new facts, and
     flagged for the author's read above everything else. A fact the rewrite would restate (a
     chronology, a place, who was in the room) is checked against the ledger first; when the
     author supplies a better fact mid-rewrite, it goes to `facts.md` *before* it goes to the prose.
   - **Does the title still fit — and if it moves, the slug moves with it.** A re-voiced piece
     often outgrows the title it was drafted under. Ask. **When the title changes, rename the piece
     to match** (see *Renaming* below); the slug is the piece's address, and an address that
     describes the piece it used to be is how a corpus starts lying about itself. Lean: keep a
     settled title, propose a rename when the title was working or when the rewrite moved the
     thesis.
   - **Is there a hero image?** **Ask the author for one, and say the rewrite is holding a slot for
     it.** Do not choose, generate, or describe an image on their behalf. If they have not got one
     yet, leave the slot marked in the review artifact and in the draft header — a slot the author
     can see is a decision waiting; an image you picked is a decision taken from them. Where the
     piece is already live and has a hero, snapshot it (URL and caption) before anything else, since
     a recompose drops it.

     **When they supply one, it is checked in — the image is part of the piece, not a thing that
     lives only in Substack.** Four steps, and none is optional:
     1. **`pieces/<slug>/assets/hero.png`** (the house name; 34 pieces use it). The repo holds the
        bytes, so a recompose can never orphan it.
     2. **`publish.yaml` records `cover:` and `cover_caption:`**, with the dimensions and a
        `sha256` so a later file can be told from this one.
     3. **Disclose the provenance, and treat it as load-bearing rather than housekeeping.** Say
        whether it is a photograph or **generated**. This matters most where a photorealistic image
        could be read as a picture of the author or someone they know: it can silently re-attach a
        biographical reading the prose deliberately dropped. *Not Made of Things That Appear* is the
        case — its §I is universal on purpose (*take a dog out on a leash*, not the author's own
        dog), the corpus holds a real photograph of the author with his dog in another piece, and a
        generated man-and-dog cover would have undone that scoping without a word being changed.
        Neither the caption nor the alt may *claim* a photograph or a likeness it is not — and
        **the caption says what the image represents** in this piece: never its provenance, which is
        this step's record, and never a disclaimer. **Write the alt to
        [`framework/docs/ALT-TEXT.md`](../../docs/ALT-TEXT.md)** — describe it, and transcribe
        any text that is *in* it, in quotation marks — and the caption to that file's *Captions*
        section.
     4. **Put it in the review artifact**, downscaled to about 1400px and embedded, so the surface
        the author reviews shows the actual cover rather than a description of one.

     **The cover is set from the repo by `substack_cover.py`** (see `publish`), not by hand — the
     older note here said the featured image could only be attached in the composer, and that was
     untested rather than true. The **caption** is set with it, from `cover_caption:`.
   - **Which version seams go?** A published piece accumulates sentences about its own earlier
     versions (*the correction I owe*, *for a while I told it as…*). They are process showing
     through; the reader never saw the earlier version. Cut them, or turn them into direct address
     (*You'd like it to be two roads. I'd like that too.*).
4. **Take the lease** (`lease.py acquire <slug> --what "v<N> rewrite …"`) and **back up the prior
   version** to the scratchpad. Git has it too, but the diff you want later is against the file.

## Name the session after the piece

Once you know which piece you are working on, rename the session to that piece's title, by
calling `mcp__ccd_session_mgmt__set_session_title` with `session_id: "self"` and the title. The
app's session list then reads as a shelf of pieces instead of a row of identical entries.

- **Take the title from `pieces/<slug>/publish.yaml` (`title:`), falling back to the README's
  H1.** Titles on this desk move late and often — one was retitled on Substack at publication and
  pulled back into the manifest — and `publish.yaml` is what actually ships to a reader.
- **Re-title whenever the piece changes.** A session that opens on one piece and moves to another
  should carry the name of the one it is on *now*. That is where the value is; naming it once at
  the start is the part that goes stale.
- **Best-effort, and silent when it fails.** The tool lives in the Claude Code desktop app. A
  terminal session does not have it, and there is no way to test for it except by calling. If it
  is missing, carry on — do not retry, do not mention it, and never let it block the work.
- **It will not stomp a title the author chose.** The app asks them to approve a rename over a
  title they set themselves, and replaces its own generated titles without asking. So propose
  freely; the guard is on their side of it.

## Writing it

- **Same beats, same order, unless the depth answer said otherwise.** The arc was already argued
  out and critiqued; the rewrite is about the voice, and the author can hear a structural change
  only if the voice change is not also arguing with them.
- **Apply the accumulated corrections as you go, not after.** The shapes that recur across the
  ledger — the autobiography of reading (*this is the part that stopped me cold*), announcing a
  move (*I want to name…*, *this is worth slowing down on*, *let me be exact*), the uncounted
  absolute (*one of the most … the human race has ever produced*), the number the source never
  supplied, the wink and the run-up before the big sentence — are cheaper to not write than to
  cut. Grep for them before critique; the list lives in `corrections.md` and in the voice's
  `avoid:` block.
- **Direct address goes at the hinges.** Where the reader is forming an objection, name it and
  concede it (*You are about to say the two traditions could not have touched. I'd like to say it
  too. It's false.*). Never to instruct, never to corner.
- **The huge sentence is delivered flat and nothing follows it.** If a line after it explains or
  dwells (*A year ago I would not have believed that*), cut the line.
- **Upgrade the cross-links.** A sibling that has gone live since the piece was written gets named
  and hyperlinked in the body where the old text said *another essay*. Canonical `public_url` only.
- **Leave slots, never inventions.** Where the new voice wants a real detail the ledger does not
  hold (what was on the desk at 4 a.m.; what the officer in the basement was doing), put a slot in
  an HTML comment for the author and let the piece stand without it.
- **The header says what version this is and that it is not live.** The published-line stays; the
  voice note names the version, the date, what was rewritten under which rules, what was cut, and
  *not yet re-synced*.

## Renaming: the slug follows the title

**When the author changes the title, change the slug to match.** The desk had drifted the other
way — *The Fountain and the Cistern* still answers to `made-with-hands`, *I Am a Prophet Also as
Thou Art* to `hearing-firsthand` — and each of those READMEs had to add a line explaining that the
address is not the piece. Two such lines is a convention; ten is a corpus that needs a decoder.
(Eric, 2026-09-10, reversing the older keep-the-slug practice.)

**Derive the slug from the settled title**, not from the thesis: lowercase, hyphens, articles
dropped where they add nothing (*Not Made of Things That Appear* → `not-made-of-things-that-appear`,
or a shorter distinctive stem the author approves). **Only rename on a settled title.** A working
title that is still one of four candidates is not a title, and renaming twice is worse than renaming
late — say so and hold.

**A rename is one atomic move across six places.** Do all of them, in this order, then prove it:

1. `git mv pieces/<old> pieces/<new>` — the directory. `draft.md` keeps its own filename for life;
   it is the *directory* that carries the address.
2. `git mv DASHBOARD.d/<NNN>-<old>.md DASHBOARD.d/<NNN>-<new>.md`, keeping the number. Then
   `dashboard.py sync`. **Check for a stale duplicate afterwards** — two fragments for one slug
   render the block twice and neither is wrong on its face.
3. **Sweep every cross-reference**, which is the part that gets missed: sibling READMEs, `outline.md`
   and `notes.md` seam notes, the book's `pieces.md` pointer, and any `projects/<name>/*.md` that names
   the piece. `grep -rn '<old>' --include='*.md' .` and read every hit.
4. **Leave `log/` and `corrections.md` alone.** They are append-only records of what was true when
   written; an old slug there is history, not rot — the same exemption `check_refs.py` already makes.
5. Release the lease under the **old** slug and re-acquire under the new one, or the advisory lock
   points at a directory that no longer exists.
6. Note the rename in the log and in the README, with the old slug named once so a search for it
   still lands.

**Prove it:** `check_refs.py` and `dashboard.py check` both clean, and `grep -rn '<old>'` returns
only `log/`, `corrections.md`, and the one README line that records the rename.

**The one thing that does not follow, and it is not an exception you get to make.** A **published**
piece's Substack URL is fixed by Substack at publication. `public_url` keeps the slug it was born
with, every sibling essay's in-text link points at that URL, and renaming the desk directory does not
and must not touch it. So for a live piece the desk slug and the URL slug **will** diverge — that is
correct, not drift. Record both in `publish.yaml` and move on. If the author wants the *public* URL
changed, that is a Substack-side decision with its own consequences for every link already pointing
at it, and it is theirs to make deliberately, not a side effect of a rewrite.

## Gate, then stop

1. `check_pronouns.py --strict` with every named figure; justify each hit by naming its referent
   (a crowd, a doctrine, the non-dualists' term for the Absolute) or fix it.
2. Run `critique` against the **current** constitution and apply what is rule-driven. Judgment
   calls — the close, a paragraph whose last line could read as the old thesis in miniature, a
   chronology rendered from one sentence of the author's — are **flagged for the author, not
   decided**.
3. **Render the review artifact with the tool and give the author the link.** A rewrite asks
   the author to judge prose, and a `draft.md` full of `[^slug]` markers, scaffold headers and raw
   markdown is not the thing they are being asked to judge. **The format is not yours to design:**
   write `pieces/<slug>/review.json` and run

       python3 framework/tools/review_artifact.py pieces/<slug> --out <file>

   then publish that file with the **Artifact** tool. The generator parses the prose out of
   `draft.md` and never retypes it, counts the deltas rather than asserting them, refuses on a
   footnote marker with no definition, and renders a marked **slot** where a hero is still owed.
   `review.json` carries only what the generator cannot count — the version label, the state flags
   (*not composed*, *Substack holds v1*), the gates that ran, the cover caption and provenance, and
   **every open question, listed as a call**. `framework/docs/REVIEW-ARTIFACT.md` has the contract.
   **Keep one artifact per piece and republish to the same URL** as versions land; the author's
   link should not change under them. Send the link, and send the file too for anyone who would
   rather read the markdown. (Two sessions hand-built this page in two different formats on
   2026-09-09 and 2026-09-10, which is why it is a tool.)
4. Log it (append-only): what the rewrite did, what it held constant, what critique changed, what
   is flagged, and that it is **not re-synced**. Update the README stage and next move; update the
   dashboard fragment; `dashboard.py sync`; release the lease.
5. **Stop.** The author reads. On their word, `publish` handles the re-sync — and a rewrite is
   structural, so it will be a **recompose** of the live post, not a surgical patch: hero and
   caption snapshotted first, the pasteboard verified immediately before the paste, the old range
   deleted after the new body lands, footnotes inserted and checksummed, fidelity digest identical
   to the draft before *Update*, the confirm dialog read for an email control, and
   `substack_verify --fresh` on the public page before the word *done*.

## What this skill has decided so far

- *Flow* v4 (witness, 2026-09-07): same beats, a third shorter; the Superviber episode moved
  inside the nine days on the author's word; version seams cut; wife paragraph re-voiced in
  sentence length only under the standing consent; two-line close on the truck; four detail slots.
- *Krishna Is Not Christ* v2 (essay, 2026-09-07): sections kept, one companion beat (Cappo) and its
  footnote cut, the other fifteen footnotes spliced in verbatim and renumbered; the harmonium and
  the confluence run literally; §VII corrected to the author's account of the chapel (a Thursday, the
  public safety officer in the basement, back on Sunday) after that account was written to the
  ledger first; the close an inversion of the opening; the live *Flow* named and linked in the body.
