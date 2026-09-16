---
name: draft
description: Start or continue a piece in a chosen style. Use when the user says "draft this", "write the next section", "keep going on <piece>", "put this in my voice", or hands you notes/an outline to turn into prose. Loads the piece's target style as steering (style.md + config.yaml + exemplars) and writes into the piece's draft.md. Drafts are cheap and disposable; it never edits the style constitution.
---

# Draft

Turn intent into prose, steered by a style. Drafting is the fast, cheap half of
the loop — write freely, revise later, let git remember old versions.

## Always do this first

1. Identify the **piece** and its **target style** from `pieces/<name>/README.md`
   (the `Style:` line). If the piece or style is ambiguous, ask — don't guess a
   voice. Then the layers above the style: `python3 framework/tools/publications.py context <slug>` names the text's publication, its
   **house file** (`publishing/house/<publication>.md`), its **project** (`projects/<name>/`) and its
   style. Load the house file and the project's README/brief with the style: the house file holds
   the conventions every voice of that publication keeps, and the desk's `CLAUDE.md` does not carry
   them. No house file means the publication keeps none beyond the desk's — never borrow another
   publication's. (2026-09-15.)
1a. **When the piece is NEW, settle its outlets before drafting, and confirm them with
   the author.** A piece declares where it will be published in `publish.yaml`:

   ```yaml
   outlets:
     - substack
     - <other outlet>
   ```

   **Never select an outlet silently, and never leave the list empty.** Read the
   instance's outlet registry (`publishing/outlets.md`), **propose** a set with a
   one-line reason, and get an explicit yes — the same way a target style is settled.
   Where a piece goes is an editorial decision about audience, not a deployment
   detail, and the author is the one who makes it.

   *Why this is here rather than in `publish`:* a piece that reaches the publish step
   without a declared destination has already been written for nobody in particular,
   and the pressure at that point is to pick the obvious one and move on. The desk did
   exactly that — it published to a single outlet for weeks while a second live host
   sat unfed, because nothing had ever asked. `publish` now **refuses** a manifest with
   no `outlets:` rather than defaulting, so the question cannot be skipped; this step
   is where it gets answered while it is still cheap. (Eric, 2026-09-09: *"the skill for
   creating a piece should define which outlets it will go to and confirm with the user.
   **A publication's `required_outlets` are the proposal, not an option** (`publications.yaml`).
   Propose every one of them; if the user drops one, write the reason into the manifest as
   `outlets_exempt: {<outlet>: "<their reason>"}`. The suite refuses a published piece that is
   missing a required outlet without a written reason — the rule is "every piece, unless the
   author says otherwise", and the saying has to be recorded where the next session will see it.
   we should not silently select one."*)
1c. **When the piece is NEW, settle its publication and its tags with the outlets, in the same
   exchange.** On a desk with a publication registry (`publishing/publications.yaml`), every
   manifest names its one publication — the outlets just proposed belong to exactly one, and the
   book and style usually agree; propose it and, on the yes,
   `python3 framework/tools/publications.py assign <slug> <publication>`. Then propose **one to
   four tags** from that publication's vocabulary (`tags.py list --publication <it>`), each with a
   line from the piece's premise, exactly as the `tags` skill's Mode 2 does — and apply only what
   is approved. A piece can be tagged again once it is written; what this prevents is a piece
   reaching `publish` never having been asked, which is how the desk grew a forty-piece untagged
   backlog before tags existed. (Eric, 2026-09-11.)
1b. **A companion is drafted like a piece, in its own voice.** When the ask is the Note, the
   poem, or the talk that goes out *with* a piece ([`COMPANIONS.md`](../../docs/COMPANIONS.md)),
   the target style is the one the companion names (`style:` in a `note.md` header; the talk's
   README), not the piece's — and that voice must write the companion's form. Read the piece's
   `draft.md` first: a companion is made *from* the piece, and its facts are the piece's. Write
   into the companion's file, never into `draft.md`.
2. Load the style as steering, in this order:
   - `styles/<style>/style.md` — the constitution (voice, do/don't).
   - `styles/<style>/config.yaml` — mechanical knobs. Honor them literally
     (formality, sentence length, person, contractions, the `avoid` list).
   - `styles/<style>/exemplars/` — match the *texture* of these passages.
3. Read the piece's `outline.md` and `notes.md`, and the book's `facts.md` (the
   witness/anchor ledger), if they exist. Draft the outline's spine, not whatever
   comes to mind.

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

## Drafting

- Write into `pieces/<name>/draft.md`. Keep **one** current draft there; prior
  versions live in git history, not stacked in the file.
- Steer, don't parrot: the exemplars set texture and the constitution sets rules;
  the content is the piece's own.
- If the style and the piece's needs genuinely conflict, surface it and ask —
  don't silently override the style or the user's intent.
- Offer the draft (or the new section) for reaction. Drafts are disposable; say so.

## After a drafting session

0. Run `python3 framework/tools/check_pronouns.py pieces/<name> --names <named figures>` on what
   you just wrote and repair before logging: restructure any sentence-initial forced capital, make
   every invented person *they/them*, capitalize every oblique reference to God (*the One*,
   *Someone*) and keep God a *who*. Inside a scripture quotation, read sections E and F: a
   capitalized *He / Him / His* there says *the Son* — for the Father it is a bracketed *[Them]*
   (verb bracketed too where agreement needs it) — and the Son's own *me / my / mine* take the
   capital. Read section H the same way: a lowercase *itself / its own / themselves* whose antecedent
   is God is God made a *what* — the word is *Themselves*, *Their own* — and a *themself* in any case
   is simply the wrong form, bracketed substitutions included. Justify each remaining hit by
   naming its referent. (Added 2026-09-03 — see the constitution's pronoun section and
   `corrections.md`; E and F added 2026-09-07 after *False Light* carried four such misses; H added
   2026-09-10 after *They Them* shipped two reflexives live; the form settled on *Themselves*
   2026-09-11, Eric's call, five uses swept.) **The deity sections (A, C–H) are a house convention,
   not the desk's:** the tool asks them only of a publication with `deity_conventions: true` and
   says so when it skips them; B and I hold for every text.
1. Append a dated entry to `pieces/<name>/log/<current-month>.md` — what you
   drafted, decisions, open threads. Append-only, newest at the bottom.
2. Update `pieces/<name>/README.md` — the `Stage:` and `Next move:` lines.
3. Refresh the piece's block in `DASHBOARD.md`.

## Boundaries

- Don't touch `styles/<style>/style.md` or `config.yaml`. Wording feedback goes
  to `corrections.md` (that's `critique`/`tune-style` territory), never a live
  edit of the constitution.
- Don't publish or send anything. Producing a draft is the whole job here.
- **Captions live in `publish.yaml`, never in `draft.md`.** An image's caption goes under
  `captions:` (keyed by the path the draft gives the image) or `cover_caption:` for the hero —
  not as an italic line under the image, which publishes as an ordinary paragraph. The
  converter refuses that line and the suite checks the corpus for it
  ([`ALT-TEXT.md`](../../docs/ALT-TEXT.md), Captions).
- **Render only the witness that's in the ledger.** Every concrete detail about a
  real person or animal — a behavior, a feeling, an event, a timespan — must trace
  to a fact in the book's `facts.md`. If a vivid specific would help but isn't in
  the ledger, write a `[bracket]` for the author to fill; never invent it. The
  machine renders; it does not live.
  - **The rule reaches anything checkable, not only people and animals.** A product
    and its interface, a place, an institution, a date, a price — if a reader could
    verify it in five seconds, it is witness and not scenery. Treat it like a
    quotation: get it from the ledger or from the author, or leave a `[bracket]`.
    Inventing plausible detail about a real thing is the same fault as inventing it
    about a real person, and it is easier to commit because the thing has no
    feelings to bruise.
  - **Invention hides best in the strongest prose.** A made-up
    detail looks no different on the page from a true one, and the temptation to
    supply one is greatest in an opening, a close, and any passage being rewritten to
    repair an earlier invention. The most satisfying lines are the first ones to hold
    against the ledger.

## Images carry alt text, and it is prose you are writing

When a draft references an image, its alt text is **house prose in `draft.md`** — the
sweeps govern it, and it is the whole of what a reader who cannot see the picture gets.
**Write it to [`framework/docs/ALT-TEXT.md`](../../docs/ALT-TEXT.md)**: describe the image,
and transcribe any text that is *in* it, in quotation marks. A chart is mostly text, so a
chart's alt is several sentences — its title, both axis labels, its legend and its
annotations. A figure number is not alt text and neither is a citation.
