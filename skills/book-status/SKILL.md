---
name: book-status
description: Orientation for a long-form book on the desk (novel, memoir). Use when the user asks "where's the book", "what's next on <book>", "where does the manuscript stand", or opens a book session without naming a chapter. Reads the book README (truth) and structure, gives the live act/chapter picture, and proposes one concrete next move. The whats-on-the-desk of book scale.
---

# Book status

The view across one book's acts and chapters. Proposes the next move; it doesn't
draft (that's `chapter-draft`) or audit (that's `chapter-audit` / `pov-audit`).

A book is a project — a `projects/<name>/` folder (`books/<name>/` on a desk from before 2026-09-16). Unlike a piece, it holds many chapters, a
scaffold layer (outline / characters / GMC / continuity), and its own craft guide.
The README is truth; every other file can lag.

## Always do this first

1. Read `projects/<name>/README.md` — status, locked decisions, the current direction.
   Where the README and an older outline disagree, **the README governs.**
2. Read `projects/<name>/outline/structure.md` (or equivalent) — the chapter list and
   per-chapter status (drafted / outlined / TBD).
3. Open only what you need for the move at hand: a chapter's `chapter_notes/<n>.md`,
   its `book/<n>.md` prose, the `gmc/` sheets, the `log/`. Note the date.

Don't propose from the structure table alone — a chapter marked "drafted" may be
pre-feedback, pre-rewrite, or pre-continuity-fix. Cross-check the README's status.

## Proposing the next move

- Give the live picture briefly: which act is in play, what's drafted vs. awaiting
  regeneration, what's blocked on a decision.
- Propose **one** concrete next move — "redesign the Act 4 outline", "draft ch 1.05",
  "run `chapter-audit` on 2.11", "GMC sheet for Démion before his hinge chapter" — not
  a plan. If several compete, name them and let the user pick; priority is theirs.
- A chapter blocked on an open question is not a candidate; surface the question.
- Respect the rewrite order the README sets (usually: scaffold → outline → prose →
  audit), and don't propose prose for an act whose outline/GMC isn't settled.

## After a work session

Keep the book honest:

1. Append a dated entry to `projects/<name>/log/<current-month>.md` (create `log/` if the
   book doesn't have one) — append-only, newest at the bottom.
2. Update `projects/<name>/README.md` status and any per-chapter status in `structure.md`.
3. If the desk's top-level `DASHBOARD.md` tracks the book, refresh its block.
