---
name: chapter-draft
description: Draft or continue a chapter of a book, steered by the book's scaffold. Use when the user says "draft chapter X", "write the next chapter of <book>", "keep going on <book>", or hands you a chapter outline to turn into prose. Loads the book's README (truth), the chapter's notes, the character + voice guides, the GMC, and the motif guide, and writes into book/<chapter>.md. The book-scale analog of `draft`. Drafts are cheap and disposable.
---

# Chapter draft

Turn a chapter's scaffold into prose. Book-scale sibling of `draft`: same
draft-freely / tune-deliberately ethic, but a chapter answers to the *whole book's*
continuity, POV scheme, and motif system, not just a style.

## Always do this first

1. Identify the **book**, the **chapter**, and its **POV character** from
   `projects/<name>/README.md` and `outline/structure.md`. If POV or chapter is
   ambiguous, ask — don't guess.
2. Load the scaffold, in this order:
   - `projects/<name>/README.md` — **truth** (locked decisions; where it disagrees with
     an older outline, it governs).
   - `chapter_notes/<n>.md` — the beat-by-beat plan for *this* chapter.
   - `outline/characters.md` — physical + **dialogue-voice** reference (single source
     of truth for how people look and sound). Match the POV's internal voice.
   - `projects/<name>/gmc/<pov>.md` — what this character wants and what collides here.
   - `CLAUDE.md` (the book's craft guide) — POV rules, motif pairs, any conventions.
3. If the book names a target **style** (a tuned voice in `styles/`), load it as
   steering exactly as `draft` does (style.md + config.yaml + exemplars).

## Drafting

- Write into `projects/<name>/book/<chapter>.md`. One current draft per chapter; prior
  versions live in git, not stacked in the file.
- **Honor the chapter's job, not whatever comes to mind.** Draft the notes' spine and
  the POV's GMC — the scene should be someone *wanting and colliding*, not events
  passing by.
- **Don't replay.** If another chapter already covered this event from a different POV,
  this chapter must carry the story forward — render what *this* POV uniquely perceives
  and does; never re-tell a scene the reader already had.
- **Write to the craft bar** the book's `CLAUDE.md` sets (strict POV, show-not-tell,
  sensory grounding, varied metaphor openness, emotion from situation not statement).
  Don't wait for the audit to catch what the guide already forbids.
- Steer, don't parrot exemplars. Offer the draft (or new section) for reaction; say
  it's disposable.

## After a drafting session

1. Append a dated entry to `projects/<name>/log/<current-month>.md` — what you drafted,
   decisions, open threads. Append-only.
2. Update the chapter's status in `outline/structure.md` and the README if the act's
   status moved.
3. Suggest the next gate: `chapter-audit` on what you drafted, and `pov-audit` once
   a second POV of the same event exists.

## Boundaries

- Don't touch a tuned style's `style.md` / `config.yaml`; wording feedback goes to
  `corrections.md` (`critique` / `tune-style` territory).
- **Don't contradict the ledger.** Every concrete fact — a character's look, an age, a
  date, a prior event — must agree with `outline/characters.md`, the continuity
  ledger, and what earlier chapters established. If a needed specific isn't fixed
  anywhere, write a `[bracket]` for the author or add it to the scaffold first; don't
  quietly invent a fact that later chapters must honor.
- Where the book fictionalizes real people/places (legal), use the fictional names and
  details the continuity ledger sets — never the real ones.
- Don't publish. Producing the chapter draft is the whole job.
