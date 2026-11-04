---
name: humor-pass
description: Give a draft the humor its style asks for — by letting the self the piece is about TALK, whole paragraphs of its own logic run straight, not by adding jokes. Use when the user says "this isn't funny enough", "do a humor pass", "make it funnier", "in the style of <a texture reference>", "let the self talk", or when a style's config.yaml declares `humor:` and a draft or rewrite has just been written under it. Proposes every change as a review finding marked where it lands, trial-applies them on a scratch copy against the gates, and applies nothing without the author's yes.
---

# Humor pass

A style that carries humor (`humor:` in its `config.yaml`) is rarely served by a joke per section.
The pass that worked, and that the author asked to be able to run again, gives the **subject the
floor**: a whole paragraph in which the self under examination reasons in its own vocabulary, with
complete confidence, and the reader sees the gap. The humor is the argument seen from inside. It is
not garnish, and it is never bolted on.

It is not `critique` (which checks the draft against every rule) and not `draft` (which writes from
the outline). It is one question asked of a finished or nearly finished draft — **where does the self
get to talk?** — and answered with proposals the author judges where they land.

## Always do this first

1. **Load the style the way `draft` does** — `style.md`, `config.yaml`, `exemplars/` — and the layers
   above it (`python3 framework/tools/publications.py context <slug>`). Read the style's own humor
   rules before writing a line: who the target is, what is never the target, where the comedy stops.
   **The style's rules govern; this skill only says how to run the pass.** A style with no `humor:`
   key gets no pass — say so, and suggest a `tune-style` if the author wants one.
2. **Read the texture references by address, never by quotation.** If the style keeps an exemplar
   map (`exemplars/map.yaml`: a move, a story, a page), use it to choose the mechanic. If the book is
   on the shelf, open those pages and read them yourself. Copyrighted texture references are
   measured and mapped, not reproduced: no sentence of theirs goes into a draft, a finding, or a log.
3. **Read the piece's no-go zones before its prose.** The ledger (`facts.md`) may mark a scene as
   tender rather than comic; the style names its gravest things (a death, the sacred, someone
   else's suffering); a piece may carry a consent boundary. List them, and write nothing funny in
   or beside them.
4. **Back up the draft** to the scratchpad. The pass proposes, but `--apply` writes.

## Choose the depth, and say which

- **Line** — one laugh in a paragraph that already exists, mid-paragraph, the sentence walking on
  past it. Cheap, and it is what a first pass tends to produce. It satisfies "funny somewhere" and
  usually misses "funny throughout".
- **Floor** — a **whole paragraph** given to the self: its plan, its ledger, its form, its case,
  run straight to the end. This is the depth the author chose when offered both (2026-11-04), and
  the default when the style says its humor is carried rather than occasional. A good pass mixes
  them: two or three floors, and lines where a floor would crowd the argument.

If the style's config names a depth (`humor_depth: line | floor`), use it. Otherwise propose the
floor and say the line pass is the lighter option.

## Writing a floor

- **Find where the self is already talking.** A paragraph that describes what the self does (it
  takes up a remedy, it keeps score, it negotiates) is a floor waiting to be given. Rewrite it so the
  self does it, in its own words and logic, and the essay stops narrating.
- **Mine first, and openly hypothetical** — the author's own self, imagined running the thing. The
  hypothetical frame is what lets the self keep exact accounts without inventing a fact about the
  author's life: a figure in the self's ledger is one the author supplied, one belonging to a
  conceded *you*, or one the sentence openly imagines. Nothing else.
- **Procedure, stated as ordinary practice.** The list ranked for the easy wins, the column added
  later, the thing given up in principle and kept in practice. The precision is
  where the laugh is. Nothing in the paragraph says it is funny.
- **The self's vocabulary beside the serious thing, and the collision makes the self small.** An
  office, a form, a review, a schedule. The thing it is talking about keeps its full weight.
- **Turn to the ache in the same diction, and end plain.** The last sentences put the cost down in
  the words the joke used, without *but seriously*, and the paragraph closes on a plain line, never
  on its laugh.
- **One floor per paragraph, and it needn't be every movement.** Where the style asks that every
  movement be funny somewhere, the question is a flag, never a quota: a movement with nowhere for
  the self to talk gets a line, or is named as exempt.

## Proposing it — the review artifact, never a silent edit

Every change is a finding in `pieces/<slug>/review.json` (`severity: voice`), anchored on the
**whole paragraph** it replaces for a floor, with `now` as finished prose and `evidence` naming the
mechanic and the rule. Build the JSON with a script that asserts each anchor occurs once and no two
overlap (`review_artifact.py` exits 3 otherwise). Then add a `calls` entry saying what the pass did
and what it left alone, render, and publish with the Artifact tool to the piece's one review URL.
Contract: [`REVIEW-ARTIFACT.md`](../../docs/REVIEW-ARTIFACT.md).

**Trial-apply before you publish the page.** Copy the piece directory to the scratchpad, run
`review_artifact.py <copy> --apply`, and on the copy run `check_pronouns.py --strict`,
`prose_shape.py check <style>` and the quote and locus checkers. Report any check the proposals would
newly break, and repair the proposals rather than the gate. **Expect the shape bands to move:** a
self's paragraph runs long and even, which lowers burstiness and raises commas per sentence; trim
the commas, and leave the burstiness to the author as a call rather than chopping the floor to fit.

## When the author says yes

`review_artifact.py pieces/<slug> --apply` writes every accepted `now` (a subset: delete the rest from
`findings` first). Then, on the real draft: the gates, `check_pronouns --strict`, the positional
sweep by hand, `prose_shape check`. Move the applied findings under `applied` in `review.json`,
republish the page, log it (append-only), and append a `corrections.md` entry saying why, in terms of
the voice, the author took what they took. That entry is evidence for the next `tune-style`.

## Two faults this pass makes, and the check for each

- **A cut made for a band orphans its referent.** Splitting a sentence to shorten a paragraph's last
  line, or to lift the share of short sentences, leaves an *it* with nothing to point at, or a
  retreat line that leans on a pair the reader met six sentences back. Re-read every split as a reader who has not seen the earlier version: does each pronoun and
  each *the first / the second* name its thing in the sentence?
- **Short sentences put pronouns at the head.** A rhythm pass multiplies sentence-initial *He* and
  *They*, and in a house that reserves those capitals for God, each one silently reassigns the
  referent. `check_pronouns` section A misses one whose antecedent is a named human. Sweep
  sentence heads by hand after any pass that shortens, and name the subject where it was a pronoun.
