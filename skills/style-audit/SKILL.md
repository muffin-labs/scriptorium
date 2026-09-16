---
name: style-audit
description: Audit a draft against its target style AND its audience (brief) rule by rule — a mechanical, read-only sweep that names every line breaking a stated rule, with the rule it broke. Use when the user says "audit this", "run a style pass", "check this against the style", "where does this stray", or wants a disciplined check before a piece is called done. The linter to critique's editor: it finds and reports, it does not rewrite or re-voice.
---

# Style audit

A mechanical sweep of a draft against its target style. `critique` gives the
editor's judgment read and can re-voice a passage; **`style-audit` is the linter**
— it enumerates the constitution, checks the prose against every rule, and reports
each place a rule is broken, with the line and the rule. It finds; it does not fix.

Run it to make a pass disciplined instead of impressionistic: coverage of every
rule, not just whatever jumps out.

**Not the pre-publish read.** That is `review` — the gates, the voice, and the primary
sources re-opened to test the claims that carry weight, delivered as an artifact with each
proposed change marked where it lands. This audit is one input to it.

## Always do this first

1. Identify the **piece** and its **target style** from `pieces/<name>/README.md`
   (the `Style:` line). If ambiguous, ask.
2. Load the **full constitution as a checklist** — every one of these is a check:
   - `styles/<style>/style.md` — each **Do** and each **Don't** is a rule.
   - `styles/<style>/config.yaml` — each mechanical knob (person, formality,
     sentence length, contractions, oxford comma) and every `avoid` item is a rule.
   - `styles/<style>/corrections.md` — **every accumulated correction and flagged
     principle is a binding rule**, even though it isn't in `style.md` yet. These
     are the freshest signal; weight them.
   - `styles/<style>/exemplars/` — the texture to compare against.
   - **The publication's house file** — every rule in it is a check. `python3 framework/tools/publications.py context <slug>` names the text's publication, its
   **house file** (`publishing/house/<publication>.md`), its **project** (`projects/<name>/`) and its
   style. Load the house file and the project's README/brief with the style: the house file holds
   the conventions every voice of that publication keeps, and the desk's `CLAUDE.md` does not carry
   them. No house file means the publication keeps none beyond the desk's — never borrow another
   publication's. (2026-09-15.)
   - `projects/<book>/brief.md` (or the piece's own audience declaration) — **the
     audience and approach are rules too.** Who it's for, the God-entry stance, the
     register, the apparatus. A draft that strays from its reader fails the audit as
     surely as one that strays from its voice.
   - `projects/<book>/facts.md` — the witness/anchor ledger. **Ground truth:** every
     lived detail in the prose must trace to a fact here; `anchor?` items are
     unverified.
3. Read the draft (or the passage named).

## The audit

- **Go rule by rule, not line by line.** For each check, scan the whole draft for
  every violation. Coverage over impressions — that's the whole reason to use this
  over an editor's read.
- Check the config knobs **literally**: person doesn't drift out of first;
  contractions match; sentence-length target holds; formality is in band.
- **Flag patterns once, with all their line refs.** If a stray recurs (e.g.
  thinking-out-loud openers), name the pattern one time and list every instance,
  rather than repeating the finding.
- **Audit against the audience, not only the voice.** Check the brief's approach:
  does the draft gatekeep or condescend to the intended reader? Does it presume
  belief or knowledge the reader lacks, where the approach says *earn* it? Does the
  register match the brief (e.g. lighthearted where called for)? Do `anchor` claims
  render as footnotes per the apparatus, not preachy body text?
- **Catch development-process leakage.** Flag any line that defends against an
  objection the reader was never given, or that only makes sense in light of the
  edit history — a "but that was never really about X" rebuttal to a point no one
  raised. The reasoning that produced a fix belongs in the scaffold, not the prose;
  the draft should read as if it had always been right.
- **Catch invented witness.** Flag any concrete detail about a real person or animal
  — a behavior, feeling, event, or timespan — that doesn't trace to a fact in
  `facts.md`. Lived specifics come from the ledger; if the prose needs one it lacks,
  that's a `[bracket]` for the author, not license to invent.
- Separate **breaks-a-stated-rule** from **unruled-but-off**. If a line reads badly
  but no rule in the style covers it, log it under "Unruled" — it's a candidate for
  a new correction (feed it to `critique`/`tune-style`), not an audit failure.

## Output — a report, not a rewrite

- Produce a **structured report**, worst offenders first. A grouped list or table:
  `rule (quoted from the style) → clean | N strays → line refs (quote each stray)`.
- For each stray, one line on *why* it breaks the rule; a terser/compliant
  alternative may be offered inline as a **suggestion**, never applied.
- End with a one-line **verdict**: is the draft close to the constitution or far,
  and which one or two fixes would move it most.

## Boundaries

- **Read-only.** Never edit `draft.md`, `style.md`, or `config.yaml`. Applying an
  accepted fix is `draft`/`critique` work; amending the constitution is
  `tune-style` work. The audit's whole job is the report.
- **Don't invent rules.** Audit only against what the style actually states. A
  problem the style doesn't name goes under "Unruled," not "Violation."
- The audit is a checklist, not a substitute for the human read — say so.
