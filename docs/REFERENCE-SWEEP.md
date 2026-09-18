# The reference sweep — a cheap model reads the shelf and returns addresses

A **sweep** is a question put to a held source that is too large to read, answered by a
cheap model in a subagent, which returns **where to look** and nothing else. The session
then opens those lines and reads them itself.

**The rule, before anything else: a sweep returns addresses, never words.** Nothing a
sweep says reaches a draft, a footnote, or a characterization of a source. Its output is a
list of `<file> @ <line>` with a one-line gloss each — a map, not a finding.

That is stated first because the shelf exists for exactly one reason: so a quotation comes
from the page rather than from a model's memory. A sweep that returned prose would put a
model's memory back in the path, and in the worst possible shape — the wording would arrive
already wearing a citation, which is the one form no checker catches.

## Why a sweep exists at all

Measured on this shelf: **41 text sources, 1,383,253 lines. 31 of them run over 5,000
lines, and the largest — Lane's *Arabic-English Lexicon*, Book I Part 3 — is 188,974 lines
by itself**, more than any context window holds. The shelf cannot be read. It can only be
addressed.

Two tools already address it, and between them they cover most of the work:

- **`references.py search "<phrase>"`** answers every question that has a phrase in it, at
  a cost of one line per hit. **Reach for it first.** If you know the words, you do not
  need a model.
- **`check_loci.py` and `check_quotes.py`** verify a quotation that has already been
  written. They are checks, not reading.

The gap is the question with no phrase in it. *Does Lane rank this derivation first or
third? Where does Waddell actually treat the wheel, as against where he mentions it? Does
this volume claim what the footnote says it claims?* `search` cannot find it — there is
nothing to search for. The checkers cannot find it either, and this is the important part:
**this desk's own finding is that most footnote faults here are CHARACTERIZATIONS of a
source, not misquotations** — a note saying a lexicon ranks one derivation first when it
ranks another; a claim credited to the writer who reported it rather than the one who made
it. Three such faults were found by hand on 2026-09-11 and none was a misquotation. Every
one of them would pass `check_quotes.py` green, because the words were the source's words.

That fault class is found by reading the source. The sweep is how a 189,000-line source
gets narrowed to the forty lines worth reading.

## The OCR argument, which is the strongest one

The shelf is largely OCR, and it is visibly damaged. A real `search` run on it returns
*"the kingdom of heavens is children's"*, *"one catholie church of seov god"*, and
*"ekkanolayv"*.

A model asked to summarize that text will repair it. That is not a failure of the cheap
model in particular — it is what models do with damaged input, and the better the model the
more fluently it does it. **The repair is invisible in a summary and obvious at the line.**
So the sweep is never asked what a passage says; it is asked where the passage is, and the
damage stays on screen where a human can see it.

## Running one

Narrow first, with the tools, and only then spend a model:

```bash
# 1. Is there a phrase? Then there is no sweep.
python3 framework/tools/references.py search "wheel of life" --source waddell -n 20

# 2. No phrase. Find the span cheaply.
grep -n -i -E 'wheel|bhavacakra' references/buddhism-of-tibet-waddell-1895-ocr.txt | head -40

# 3. Extract the candidate span to a scratch file — never into this session's context.
sed -n '18400,19600p' references/buddhism-of-tibet-waddell-1895-ocr.txt > "$SCRATCH/waddell-span.txt"
```

Then hand the span to a subagent with `model: haiku`, and give it the output contract
explicitly:

> Read `<path>`. The text is OCR and is damaged; do not correct it and do not quote it.
> Answer only with lines of the form `@ <line number> — <eight words on what is there>`.
> Give me at most fifteen. If the question is not addressed in this span, say
> `NOT IN SPAN` and nothing else. Do not summarize. Do not draw a conclusion.
> Question: <the question>

The corpus goes into the subagent and never into this session. What comes back is a list of
line numbers. Open them with `sed -n` and read them yourself — that read is the one that
counts, and it is the only one whose output may reach prose.

## When not to sweep

- **You have the phrase.** `references.py search`. Cheaper, exact, and it cannot invent.
- **You are verifying a quotation already written.** `check_loci.py` for a canon locus,
  `check_quotes.py` for everything else. Those are gates; a sweep is not.
- **It is the pre-publish re-open of the primary sources.** That read belongs to `review`,
  and it is a human's. A sweep may narrow where the human looks. It may not stand in for
  the looking.
- **The source is small.** Under a few hundred lines, reading it costs less than the round
  trip.
- **The answer will be quoted.** Then you must open the page regardless, so sweep only to
  find the page.

## Delegation stays inside the session

The sweep is a subagent of the session, not a transport to another service. The text goes
where the session's own reads already go, under the same credentials, with no second
account to hold the shelf and no hook standing between the session and `Read`. That matters
here more than it would elsewhere: **17 of this shelf's files are held under a
deny-by-default `.gitignore` precisely because they cannot be redistributed**, and a
delegation path that copied them to a third party would defeat the rule the shelf is built
on while appearing to be a performance optimization.

## What this does not do

A sweep does not check anything. It cannot tell you that a page says what the prose claims
it says — it can only tell you which page to argue with. That is `review`'s
re-open-the-sources read, and it is a human's; the same warning `references.py`,
`check_quotes.py` and `check_verified.py` each give about themselves, for the same reason.

And a sweep that returns the wrong address is cheap: it costs one `sed`. That asymmetry is
the whole design. A wrong address wastes a minute. A wrong summary that reached a footnote
is a correction to a live post.
