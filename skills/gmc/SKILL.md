---
name: gmc
description: Build and maintain Goal / Motivation / Conflict sheets for a book's characters and chapters (Debra Dixon's GMC). Use when the user says "GMC", "why does this character want anything", "the characters feel passive", "what's driving this chapter", or before drafting a chapter whose engine is unclear. Gives every main character a reason to exist and to push the plot; sets characters' GMCs against each other so scenes have tension. Produces/updates scaffold, not prose.
---

# GMC

Goal / Motivation / Conflict — the spine that keeps characters from being passive.
The most common failure of a literary draft is that things *happen to* the cast;
GMC is the fix. This builds the scaffold; `chapter-draft` writes from it.

## The model (Dixon)

For each character, and framed both **externally** (plot) and **internally** (arc):

- **Goal** — what they are actively trying to get or do. External ("win the ring",
  "get to the festival", "keep the triangle intact"); the external goal drives the
  internal journey of change (or the tragic failure to change).
- **Motivation** — *why* they want it. Without motivation a goal is a vacuum and the
  reader can't care. This is where you pit values against each other: power vs.
  justice, fame vs. authenticity, safety vs. truth, being-known vs. being-held.
- **Conflict** — what stands in the way (the *why not?*). External obstacles *and*
  an internal contradiction. Conflict sets the story's start (the first collision
  that trips the whole GMC web) and end.

**The engine is collision.** Each main character's GMC should be in conflict with
another's. "Persefoni needs Démion at the hospital; Démion needs to play Sunday" is
two GMCs at war — that is what makes a scene move. When planning, ask *whose wants
collide here, and who is thwarted.*

## Always do this first

1. Read `projects/<name>/README.md` (truth) and `outline/characters.md` (who they are).
2. Read any existing GMC sheets in `projects/<name>/gmc/` and the feedback the README
   points to. Don't restate what's there; extend it.

## Doing the work

**Character sheets** — one file per main character, `projects/<name>/gmc/<character>.md`:

```
# <Character> — GMC

## Goal        external: … | internal: …
## Motivation  external: … | internal: …  (the values in tension)
## Conflict    external: … | internal: …  (the why-not, both layers)

## Whose GMC this collides with
- <other character>: … (where their wants cross)

## Arc: does this character change, or tragically fail to?
```

**Chapter GMC** — a short block added to the chapter's `chapter_notes/<n>.md` (don't
make a separate file): *whose GMCs are in this scene, what each wants right now, who
is thwarted, what action is taken (or refused), how the collision raises tension.*
If the answer is "nobody wants anything and nothing collides", the chapter is a
candidate to cut, compress, or re-aim — say so.

## Boundaries

- Scaffold only. Never write prose here; `chapter-draft` does that from these sheets.
- Don't invent biography that contradicts `outline/characters.md` or the continuity
  ledger — GMC interprets the established character, it doesn't overwrite them.
- Passivity can be a deliberate theme (a character to whom life happens). If so, name
  it as a *choice* with its own GMC underneath (what the passivity protects), so it
  reads as character and not as a hole.
