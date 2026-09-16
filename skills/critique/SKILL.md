---
name: critique
description: Review a draft against its target style and give concrete, actionable feedback. Use when the user says "critique this", "how's this draft", "does this sound like my voice", "edit this", or wants a read before calling a piece done. Reads the draft and the style, names specific lines that stray, and — when the user accepts a wording change — records the why in the style's corrections.md. Does not rewrite the whole piece unless asked.
---

# Critique

The quality half of the loop. Read a draft against the voice it's meant to have,
and say — concretely — where it lands and where it strays.

## Always do this first

1. Read the draft (`pieces/<name>/draft.md`) and the piece's `README.md` for its
   target style.
2. Load `styles/<style>/style.md`, `config.yaml`, and a sampling of `exemplars/`
   — the same steering `draft` uses. You're checking the draft against *this*
   voice, not against generic "good writing". And the layers above it: `python3 framework/tools/publications.py context <slug>` names the text's publication, its
   **house file** (`publishing/house/<publication>.md`), its **project** (`projects/<name>/`) and its
   style. Load the house file and the project's README/brief with the style: the house file holds
   the conventions every voice of that publication keeps, and the desk's `CLAUDE.md` does not carry
   them. No house file means the publication keeps none beyond the desk's — never borrow another
   publication's. (2026-09-15.)

3. Run `python3 framework/tools/check_pronouns.py pieces/<name> --names <named figures>` and
   read every hit against the constitution's pronoun rules before you read the prose: forced
   sentence-initial capitals, the generic masculine (a hypothetical person is *they*), a
   lowercase *the one / someone* or a *what* for God, a lowercase deity pronoun — and, inside a
   scripture quotation, a capitalized *He / Him / His* (section E: the Son, or else a bracketed
   *[Them]* for the Father) and a lowercase *me / my / mine* where a Gospel footnote says the Son
   is speaking (section F: the house capitalizes His own pronouns in a quotation). Each hit is
   justified by naming its referent or it is a finding. (Added 2026-09-03; the sweep had been
   typed by hand per session and twice was not typed at all. E and F added 2026-09-07 after
   *False Light* carried four misses inside King James quotations — *Him only shalt thou serve*,
   *He maketh His sun*, *mine own self*, *without me* — that no sweep could see.)

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

## Giving feedback

- Be concrete and located: quote the line, name what's off (which principle or
  which `avoid` item), propose a specific fix. "Weak" is not feedback; "this
  opens with a rhetorical question, which the style rules out — try leading with
  the claim" is.
- Separate **style** misses (voice, constitution, config) from **substance**
  issues (logic, structure, gaps). Both matter; label which is which.
- Prioritize. Lead with the few changes that matter most, not an exhaustive
  line-edit, unless a full line-edit is what was asked.
- Don't grade with adjectives-as-verdict. Report what's there and what a fix
  would be; the call to accept is the user's.

## Critique, review, audit — which one this is

- **`critique`** (this one) is the **editor mid-draft**: judgment on a passage, and the
  accepted wording changes go to `corrections.md` so the voice can learn.
- **`style-audit`** is the **linter**: every rule in the constitution, checked, reported.
- **`review`** is the **pre-publish read**: the gates, the voice, *and the primary sources
  re-opened to test the claims that carry weight*, ranked and delivered as an artifact with
  each proposed change marked where it lands. Reach for it when a piece is finished or
  composed and the author is deciding whether to ship it.

If the author says "review this" on a finished piece, that is `review`.

## The deliverable is an artifact — this is not optional

**A critique pass ends with the house review artifact published, every time.** Not a report
pasted into chat, not a page built by hand, not a bulleted list of line numbers. Write the
findings to `pieces/<slug>/review.json`, render, publish:

    python3 framework/tools/review_artifact.py pieces/<slug> --out <file>

then publish that file with the **Artifact** tool — one artifact per piece, republished to the
same URL as versions land. **Chat carries the shape and the link; the page carries the detail.**

*(Eric, 2026-09-14: the artifact "should happen by default in our framework." It already did for
`review`; `critique` had it behind a condition — "when the author needs to read the piece rather
than a report on it" — which is a judgment call the skill was making on the author's behalf every
time, and making wrong. A critique is *always* a set of proposed changes to prose, and a proposed
change is only judgeable where it lands.)*

**The one exception:** a single wording question mid-draft — the author asks about one sentence
and wants one sentence back. That is a conversation, not a pass. Everything larger is a pass.

### What the tool will refuse, and why

`review_artifact.py` **exits 3 and writes no file** rather than render a page that looks complete
and is not. Three refusals worth knowing before you write the JSON, because each one costs a
round trip:

- **An anchor that matches nothing, matches twice, or overlaps another finding's anchor.**
  Lengthen it until it is unique. Build the JSON with a script that asserts
  `draft.count(anchor) == 1` and the failure never reaches the tool.
- **A `was` key.** `was` is *derived from the anchor* — the anchor **is** the text being
  replaced. Give `anchor` and `now`, never `was`.
- **A finding with no `now`.** Every finding proposes a change; a diagnosis with no replacement
  is a question, and questions belong in `calls`. A deletion is a replacement of a wider span:
  anchor what goes **and** what survives, and let `now` be what remains.

Facts that cannot be counted go in the same `review.json` — `state` flags, `gates`, and every
open question listed under `calls`. Full contract: `framework/docs/REVIEW-ARTIFACT.md`.

### Ranking

Findings render in the order given, and that order is what the author reads first. Rank them:
**fidelity** (a claim that is not true, a fact that came from memory) above **argument** (a gap
or an overreach in the reasoning) above **voice** (the constitution). A voice miss that the
style's own `corrections.md` has already caught once outranks a fresh one — a fault that recurs
is evidence for the next `tune-style`, and saying so in the finding is how it gets there.

## When a wording change is accepted

If the user takes a change that reflects the *voice* (not a one-off fix), capture
it so the style can learn:

1. Append to `styles/<style>/corrections.md`, under today's date:
   `- Changed "X" → "Y". <why, in terms of the voice>`. Append-only.
2. Don't touch `style.md` or `config.yaml` here — corrections accumulate; the
   gated `tune-style` pass is what folds them into the constitution.

## After the session

Log the review in the piece's `log/`, update the piece `README.md` stage/next
move if it changed, and refresh the `DASHBOARD.md` block.
