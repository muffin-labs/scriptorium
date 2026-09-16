---
name: review
description: The pre-publish read of a finished piece, delivered as an artifact with every proposed change marked where it lands in the prose. Use when the user says "review X", "let's review it", "read this before I publish", "what's wrong with this piece", or opens a composed piece for a last look. Runs the mechanical gates, reads the draft against its style, RE-READS THE PRIMARY SOURCES to test the claims that carry weight, then ranks the findings and renders them into the house review artifact — each finding anchored to the exact span it is about. Proposes; never applies without a yes.
---

# Review

The last read before a piece ships. `critique` is the editor mid-draft and writes
to `corrections.md`; `style-audit` is the linter that enumerates rules. **Review is
the whole pre-publish read** — gates, voice, and, the part neither of the others
does, **the sources re-opened and the load-bearing claims tested** — ending in one
artifact the author can act from.

The deliverable is the **artifact, not the chat message.** A review posted into a
conversation scrolls away; a review anchored into the prose can be read line by
line, and each proposed change is judged in the only place it can be judged —
next to the sentence it changes.

## Always do this first

1. **Take the lease.** `python3 framework/tools/lease.py acquire <slug> --what "review pass"`.
   Release it when you are done. Advisory, and the point is that a session about to
   touch the piece finds out in one call that you are on it.
2. **Read the piece's `README.md`** — target style, book, audience, budget, and the
   **guardrails**, which are the piece's own rules and are findings when broken. Then the layers
   above the style, whose rules are findings too: `python3 framework/tools/publications.py context <slug>` names the text's publication, its
   **house file** (`publishing/house/<publication>.md`), its **project** (`projects/<name>/`) and its
   style. Load the house file and the project's README/brief with the style: the house file holds
   the conventions every voice of that publication keeps, and the desk's `CLAUDE.md` does not carry
   them. No house file means the publication keeps none beyond the desk's — never borrow another
   publication's. (2026-09-15.)
3. **Read the whole `draft.md`.** All of it, including every footnote. A review that
   skimmed the notes will miss the class of fault that lives only there.
4. **Name the session after the piece** — `mcp__ccd_session_mgmt__set_session_title`
   with `session_id: "self"` and the title from `publish.yaml`. Best-effort; silent
   when the tool is absent.

## Run the gates before you read for judgment

Mechanical first, so the read is about the things a tool cannot see:

```
python3 framework/tools/gates.py pieces/<slug> --json
```

**One command, and it is the command — not a list to work through.** It runs every gate
(links · verified · scripture · quotes · commonmark · pronouns · stage direction · refs),
prints what each said, and `--json` writes those results into the piece's `review.json`, so
the artifact's gate band **reports what actually ran.** A gate that was skipped cannot appear
there as a pass.

That is a repair, not a convenience. Measured 2026-09-11: a review worked down the list by
hand, ran six of eight, missed `check_loci.py`, and verified the piece's scripture
against a website — while the desk held an indexed KJV and the tool that reads it. The
artifact then said *sources re-opened*, which was true of the network and not of the repo.
(Eric: *"you have KJV in the index why didnt you check that?"*)

Add `--names <named figures>` work by hand where a piece needs it, and run
`md_to_substack.py` when you want the converter's counts; everything else is in the runner.

**`check_quotes.py` is the gate that changes what the source re-read is for.** It matches every
non-scripture quotation against the copy of the source held in `references/` and
reports the page. What it cannot do is tell you the page says what the prose claims — so the
re-read stops being a transcription check and becomes the only thing it was ever good for:
does the source bear the weight the argument puts on it. A **NOT HELD** finding means the
quotations in that footnote were checked by nothing at all; bring the source in with
`references.py add` before the review claims to have tested them.

Every gate result goes in the artifact's `gates`, pass or fail — the author should
see what ran, not be told it was fine.

**Read every pronoun hit against the constitution and justify it by naming its
referent.** And know what the sweep cannot see: it has no section for a
**third-person lowercase deity pronoun inside a quotation**, so a King James
*taketh him up* for the Son passes clean. Casing misses inside quotations are
**referent-blind** and have now escaped this desk twice. Check them by hand.

## Then go back to the sources

This is the step that separates a review from a proofread, and it finds the
findings worth having.

- **Re-open the primary source for every claim the argument leans on** — the PDF in
  `references/`, the scan, the scripture ledger in `notes.md`. Not the
  notes *about* the source: the source.
- **Check each quotation character by character** against it — the dashes, the
  capitals, the ellipses. A piece whose method is verbatim quotation is convicted by
  a dropped em dash, and the same sentence quoted two ways in one essay is the
  house's oldest recurring fault.
- **Test the paraphrases hardest.** Where the draft says *the text tells the reader
  X*, find the sentence that says X. If the quoted line does not carry the claim, the
  footnote is under-citing even when the claim is true — and the fix is usually the
  next sentence in the source, not a retreat.
- **Try the hostile reading.** Take the guardrail that says a reader with both books
  open must not be able to knock this over, and be that reader. Where a source
  sentence admits two readings and the essay asserts one, say so.
- **Count what is claimed as counted.** An absolute (*never appears*, *every verb*,
  *precisely*) is a finding unless you have run the count yourself. Run it — and when
  the count comes back better than the claim, that is a finding too.

## Rank, and say which kind

Order the findings by what it would cost to ship them, and give each a severity:

| severity | what belongs in it |
|---|---|
| `fidelity` | the piece misquotes, miscases or misattributes its own sources. Cheapest to fix, most expensive to ship. |
| `argument` | a claim the text will not carry, a concession that takes back a conviction, a note that under-cites. |
| `voice` | the constitution, the config `avoid` list, the piece's own guardrails. |
| `open` | a decision that is the author's, not yours. |

Lead with the few that matter. An exhaustive line-edit is a different job and is
only run when asked.

## Render it — the artifact is the deliverable

Write the findings to `pieces/<slug>/review.json` and render:

```
python3 framework/tools/review_artifact.py pieces/<slug> --out <file>
```

then publish with the **Artifact** tool — one artifact per piece, republished to the
same URL as versions land, so the author's link never moves under them.

Each finding is **anchored to the exact span of `draft.md` it is about**, and the
page marks that span in place and hangs the note under the paragraph:

```json
{ "severity": "fidelity",
  "anchor": "It asks nothing for Itself",
  "now":    "It asks — nothing — for Itself",
  "title": "§II drops the source's dashes from a sentence §I quotes with them",
  "what": "The book reads <em>It asks—nothing—for Itself</em>. (HTML ok.)",
  "evidence": "<em>Unveiled Mysteries</em>, p. 25, read in the PDF today." }
```

- **The anchor is verbatim `draft.md`**, markdown and all, matched against the
  whitespace-normalised block — line wraps do not matter, `*asterisks*` do.
- **Read the alt text while you are there, against
  [`framework/docs/ALT-TEXT.md`](../../docs/ALT-TEXT.md).** The page shows every image with
  its alt text as prose, because that string is house writing that no other surface
  displays — and it is anchorable, so a finding can propose better alt text like any other
  change. **The half that gets forgotten is transcription:** a chart's title, both axis
  labels, its legend and its annotations are text *in* the image and have to be quoted. An
  alt that is a figure number, a caption or a citation is a finding. An empty one is
  flagged: a picture with no alt gives a screen-reader user nothing.
- **The mark shows the PROPOSAL.** Where a finding carries `now`, the marked span
  renders the replacement, so the highlighted prose reads as the piece would read if
  every change were taken. **`now` must be an exact replacement for `anchor`** — the
  same span, rewritten. Write it as real markdown; it goes through the same inline
  pass as the prose around it.
- **`was` is not an input** — it is the anchored text, derived, so the two halves of
  the diff cannot disagree. **A deletion is a replacement of a wider span** — anchor
  what goes *and* what survives, and let `now` be what remains.
- **Every finding proposes a change.** `now` is required and a no-op `now` is refused.
  Naming the fault is the easy half; **if you cannot write the replacement, you have not
  finished the finding.** Write the rewrite even when it is one clause, and say in `what`
  what it costs. A fault you genuinely cannot resolve is a **question** — put it in
  `calls`, which is the band for the author's decisions, and do not dress it as a change.
- **`evidence` says what you checked it against.** A finding the author has to take
  on trust is a finding they have to re-derive.
- **Anchors are not allowed to miss.** An anchor matching nothing, matching twice, or
  overlapping another **exits 3 and names it, and writes no file** — because a page
  that silently dropped a finding still looks complete, and the author would read it
  believing they had seen everything. Lengthen the anchor until it is unique.
- Contract and every other key: `framework/docs/REVIEW-ARTIFACT.md`.

Put the author's decisions in `calls`, not in `findings` — a question is not a
proposed change, the two bands are read differently, and the tool now enforces the line:
a finding without a replacement is refused.

## Then say it in chat, briefly

The artifact carries the detail; the message carries the shape. What the gates said,
what the piece does well, how many findings and of what kind, and the one question
that most needs an answer. Link the artifact. Do not re-list the findings — that is
the thing the page exists to stop.

## Proposing is not applying

**Review proposes. It does not edit `draft.md` without a yes.** When the author takes the
changes, **apply them with the tool, never by hand**:

```
python3 framework/tools/review_artifact.py pieces/<slug> --apply
```

That is what the strict contract buys: `now` is an exact replacement for `anchor`, so what
the author approved on the page and what lands in the file are the same string. Nothing is
written unless every finding lands. **If the author takes only some**, drop the rest from
`findings` first — keep them under another key so they are not lost.

**Then re-run every gate, and read your own new prose against the same sweeps you just
used on theirs.** A pass that rewrites a piece can introduce exactly the faults it was
hunting: on *False Light* the stage-direction grep caught *"Here I want to be careful…"* in
a section written minutes after finding 9 flagged that identical shape in the opening line.

After applying, re-render, republish the same artifact URL, and then:

- a change that reflects the **voice** goes in `styles/<style>/corrections.md`,
  append-only, with the why — the same rule `critique` follows;
- a piece already **composed to Substack** is now behind the desk, so say so and
  re-sync with `publish`; a piece already **live** needs `substack_verify --fresh`
  after, because *Saved* is not *shipped*;
- log the pass in `pieces/<slug>/log/`, update the piece `README.md`, edit
  `DASHBOARD.d/<NNN>-<slug>.md` and run `python3 framework/tools/dashboard.py sync`.
  Never edit `DASHBOARD.md` by hand.
