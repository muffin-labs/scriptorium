---
name: substack-sync
description: Two-way sync between a piece's draft.md and its already-live Substack post, with conflict detection. Use when the user says "sync X", "re-sync X", "pull my Substack edits back", "the live post is behind", "update the published post", or wants a live post and its draft brought back into agreement. Classifies every block three ways against a stored baseline — push (draft moved), pull (Substack moved), conflict (both moved) — pulls Substack-side edits into draft.md, then pushes. On an already-published post the push is LIVE the moment it lands — there is no staging gate; only email stays behind a human click.
---

# Substack sync (two-way, with conflicts)

Bring a **live** post and its `draft.md` back into agreement, in whichever direction each
change actually travelled. Use this — not a bare push — for any piece that is already
published.

## Why this is not just "republish"

`publish`'s republish mode pushes draft → live and is stateless: it diffs the draft against
the live post. That is right for a one-way push and wrong the moment edits can start on
**both** sides, because a bare difference cannot tell you which side moved.

That is not hypothetical. On 2026-09-01, `Nothing to Get` read *"is this for us"* in the
draft and *"is this for me"* live — the phrase entered at the compose commit and was never
touched again, so the edit had been made in Substack. `I Believe in You` had its subtitle
capitalized in Substack while `publish.yaml` still held the lowercase form. A stateless push
would have reverted both and reported success.

So sync is **three-way**, against a baseline of what was last known synced:

| draft vs baseline | live vs baseline | | |
|---|---|---|---|
| same | same | **unchanged** | nothing to do |
| changed | same | **push** | the ordinary re-sync |
| same | changed | **pull** | bring Substack's edit into `draft.md` |
| changed | changed, same text | **converged** | nothing to do |
| changed | changed, different | **conflict** | **stop** — a human decides |

Conflicts need the same block edited on both sides between syncs, so they should be
exceedingly rare. Rare is not never, and the baseline exists so that when one happens it is
**reported** rather than silently resolved in whichever direction the tool ran.

### Every row is classified TWICE: text, and marks

The table above ran on reader-text alone until 2026-09-09, and reader-text cannot see
formatting. A block whose only difference is an `<em>` hashes identically on both sides, so
it classified as **unchanged** and sync ran straight past it — the same false pass that
`substack_verify` and `substack_repatch` had, one tool over, and worse here because a
**seal writes the mistake down** and every later sync then measures against a state that was
never true.

So a row now carries `state` (the words) and `markState` (the `em`/`strong`/link runs),
classified by the same five rules. Read them together:

- `plan` prints a **`marks`** tally beside `blocks`, and flags any row whose formatting
  moved even when its text did not.
- A **formatting push** needs nothing special — `substack_repatch` applies `em`/`strong` as
  real ProseMirror marks.
- A **formatting pull is reported, never applied.** Bringing an italic back from Substack
  means writing `*` into the markdown at a mapped offset, and the run can straddle a link, a
  footnote marker, or emphasis already there. `pull` names the block and the exact runs
  (`live em'satsang' em'kirtan' | draft (none)`) and **exits non-zero**; you edit `draft.md`.
- `seal` **refuses** while the words agree and the formatting does not.

**`unknown` is not `unchanged`.** A baseline sealed before this existed has no mark hashes —
34 of them did — and its rows report `unknown`, with `plan` saying in as many words that
formatting was not compared. A tool that answers "no change" when it never looked is the
failure being fixed, wearing a different hat. Those baselines start carrying marks at their
next completed `seal`; nothing needs re-sealing on purpose.

## Preconditions

- The piece is live and `publish.yaml` carries **`post_url`** (the *editor* address,
  `/publish/post/<id>`) and **`public_url`** (the reader address, `/p/<slug>`). These are
  different URLs and both are needed.
- **Signed in as the outlet's account, ON THE OUTLET'S OWN PUBLICATION.** The account is the gate;
  the surface is a preference (`substack_account.py route <outlet>` says which to reach for first —
  the pane for the primary, a named `chrome_browser` for an outlet that has one). Run its snippet
  **on that outlet's publication host**, then `check --surface pane|chrome --result '<its JSON>'`
  (see the `publish` skill, *Confirm the ACCOUNT*). A push on the wrong account edits a post its
  session does not own, or fails halfway. **Exit 5 is a stop**, not a prompt to sign in again; exit
  7 means run the snippet again on the right page — which now includes an answer read on another
  Substack publication, because Substack resolves the account per publication. **Exit 4 is retired:**
  a correct account on an off-preference surface passes with a note.
- **Every snippet re-checks the publication and the account itself.** The pane's login is shared
  and can change after `check`, so each `scan`/`fetch`/`push`/`images` and `substack_repatch`
  snippet opens with the account guard. Before reading or writing the post it requires the page to
  be the outlet's own publication host *and* signed in as its `account_handle`, and otherwise
  returns `{"refused": …, "accountGuard": true}`. That is a stop, the same as exit 5. A piece whose outlet cannot be settled from `outlets:` gets no snippet
  (exit 9); see `substack_account.py guard pieces/<name>`.
- The browser is open and **logged in** on that post's editor. Automation cannot enter
  credentials.
- The piece has a **baseline** (`<piece>/sync-baseline.json`). If it does not, seed one
  first — see *First run* below.

## The loop

Each browser step is one JS eval in the live post's editor.

1. **Scan.** `python3 framework/tools/substack_sync.py scan pieces/<name> scan.js`
   Run it in the editor; **save its whole return value**, wrapper and all. It returns
   title, subtitle and one hash per block — not the text, so a 6,000-word essay costs a
   few hundred bytes to compare.

   **The scan hashes itself, so save it verbatim and never tidy it.** The return is
   `{scanVersion, sha256, scan}`, and `plan`, `seal`, `push`, `detect` and `resolve` all
   check the digest before reading a word of it. That is there because a scan is
   kilobytes of hex an agent writes into a file by hand — the transcription risk
   `pane_carry` removes on the way *in*, with nothing on the way out. `seal` failed closed
   on a slip, which is safe and tells you nothing about where it went wrong; **`plan` had
   no guard at all, so a mistyped hash read as a REAL difference and would send you to
   re-sync a block that never changed.** A mismatch now refuses (exit 8) and prints both
   digests. An older bare scan still loads and says out loud that it cannot be checked.
2. **Plan.** `python3 framework/tools/substack_sync.py plan pieces/<name> live.json plan.json`
   Classifies every block and prints the tally. **Read it before doing anything else.**
   Structural rows (a block added or removed on one side) are described and never
   auto-merged.
3. **Fetch** — only if there are pulls or conflicts:
   `python3 framework/tools/substack_sync.py fetch pieces/<name> plan.json fetch.js`
   Run it; it returns the live text for *just those* blocks.
4. **Pull.** `python3 framework/tools/substack_sync.py pull pieces/<name> plan.json livetext.json`
   Writes the Substack-side edits into `draft.md`, changing only the runs that differ and
   leaving emphasis, links and footnote markers intact. Every edit is **verified by
   re-rendering** the block and comparing; anything that does not land exactly is reported
   for a human instead of being written. It **refuses outright** if there are conflicts.
5. **Push.** `python3 framework/tools/substack_repatch.py pieces/<name> push.js`, run once
   in the editor, then check the report (see *Reading the push report*).

   > **Do not retype a large push script into the browser.** `substack_repatch.py` bakes the
   > **entire rendered essay** into its snippet — 73KB for a 5,700-word piece — so driving it by
   > hand means the agent reproducing every byte of the author's prose. On a **live, public**
   > post that is the worst place to accept a transcription risk: one wrong character diffs as a
   > real edit, the tool applies it faithfully, and the guards cannot object because to them a
   > typo is just another edit.
   >
   > **When the script is small enough to read in full, run it as-is.** When it is not, and
   > `plan` has already told you exactly which blocks moved, prefer a **minimal guarded edit**:
   > pull the target text **programmatically** out of the generated script (never retype it),
   > and apply only the changed span with every guard the tool uses, plus one it lacks —
   >
   > - refuse unless body and footnote counts match the draft exactly (structural guard);
   > - refuse if the old text is absent, or occurs more than once (alignment guard);
   > - refuse if the span's start and end marks differ (formatting guard — this one fires in
   >   practice: a span crossing `<em>` would otherwise flatten the emphasis);
   > - **re-read `doc.textBetween(from, to)` and refuse unless it equals the expected text**
   >   (position guard — `substack_repatch.py` does not do this);
   > - apply multiple edits **latest-position-first** so unapplied positions stay valid;
   > - normalize curly/straight apostrophes for the *lookup*, and **re-smarten the replacement
   >   to match the live document's own typography** so nothing downgrades a `’` to a `'`.
   >
   > Six live posts were re-synced this way on 2026-09-01; every one reported `marks: 0`, and a
   > re-scan and re-plan read `converged / nothing to do` before sealing.
6. **Hand off — confirm on the public page, do not infer.** **Measured 2026-09-01:** a guarded
   body edit on a live post left the editor showing *Saved* while the **public page still served
   the old text**, until **Update → Update now** was clicked (cache-busted check;
   `cf-cache-status: DYNAMIC`, so not a caching artifact). Earlier notes here asserted the
   opposite. **So check the cache-busted reader URL and report what you actually saw** — either
   *live and confirmed*, or *staged, awaiting Update*. **"Saved" is not "shipped."** The old
   wording follows and is kept for the part that is still true — that you must verify before
   writing, and that the write itself is not undoable.

   **Original note — the push is already public.** **There is no staging gate on a live post.** The
   edit reaches readers on autosave; **Continue** is usually **disabled** afterwards, because
   nothing is left unpublished. Do not report the sync as "staged, awaiting your click" — report
   it as **done**, and hand over the list of what changed so a human can read it on the public
   page. Never click **Continue / Publish / Send** yourself: that control is what **sends email**.
7. **Seal.** Re-run *scan*, then
   `python3 framework/tools/substack_sync.py seal pieces/<name> live-after.json`
   It refuses unless draft and live now agree, and records the new baseline. **Do not skip
   this** — an unsealed sync leaves the next one unable to tell which side moved.
8. **Carry it to every other outlet the piece declares — and START by asking how many there
   are.** This loop moves Substack and nothing else, and a correction is not live until every
   outlet in `publish.yaml`'s `outlets:` has it.

   ```
   python3 framework/tools/resync.py pieces/<name>        # exit 3 = an outlet is behind
   ```

   **Run it before you touch the first outlet and again after the last.** It reads `outlets:`,
   checks each against the live page, and **refuses to look like completion** — the summary
   always reads *N of M outlets current*, and the exit is 3 while any outlet is behind. That is
   the whole point: the failure this step exists to prevent is not forgetting the rule, it is
   *reporting done* after moving one outlet, which is what a green `substack_verify` invites,
   since it exits 0 on a true statement about one publication. A Substack outlet is checked
   through `substack_verify` (body, footnotes, marks, anchors); other outlets are compared on
   body paragraphs only, and the tool prints that limit on every run rather than implying more.
   An outlet a person has to publish is deferred with a reason —
   `--defer <outlet> --reason "…"` — and the deferral **binds to the draft's sha256 and lapses
   the moment the draft changes**, because a reason given for one version is not a reason for
   the next. **Measured 2026-09-11:** *For the Love of Dogs* had its storm sentence
   corrected, re-synced, `substack_verify --fresh` MATCH, and was logged *live and verified* —
   while alignmentfellowship.org went on serving the old sentence until an audit happened to
   look, because the content store was never re-uploaded. Not a cache: the store object was five
   hours older than the correction.
   For each outlet other than `substack`:
   - **a store outlet** (the site reads the content store) — the one-piece export and upload in
     the instance's `publishing/outlets.md`: seed the index from the live store, export **only
     this piece** from a committed, clean draft, `store_publish.py --dry-run`, read the counts,
     upload.
   - **an outlet a person publishes** (LinkedIn) — regenerate the copy with its skill and hand it
     over. It is **pending** until they update it; say so rather than reporting it done.

   Then, after about a minute, from the instance root:

   ```
   python3 framework/tools/resync.py pieces/<name>        # must exit 0
   ```

   **Exit 0 is the report.** Until it is, the correction is not live, whatever any single
   outlet's check said. `outlet_audit.py --content --outlet <outlet>` is still the wider sweep
   — it also runs the reverse direction from each outlet's sitemap, which resync does not — so
   reach for it when auditing the corpus rather than finishing one piece. **Report per outlet
   until they all agree** — *Substack confirmed; alignmentfellowship pending* — never one word
   for all of them.

## First run (a piece published before sync existed)

`plan` refuses without a baseline, because it would have to guess. **Do not guess either.**

1. Scan the live post first.
2. `python3 framework/tools/substack_sync.py detect pieces/<name> live.json`
   Renders `draft.md` at every commit that touched it and reports how many blocks each
   revision still matches. **The revision matching the live post on every body block is the
   state that was last pushed** — that is the baseline, whatever its date.
3. `seed pieces/<name> --from-git <the rev detect names>`

`--from-draft` and `--from-live` also exist, but they are *assertions*, and a wrong
assertion makes the first sync push or pull something nobody asked for.

**Never seed from "the newest commit" because it is newest.** A commit can carry an
editorial pass that was never published, and seeding from it **inverts every row that pass
touched**: the plan reports a PULL, and the sync dutifully reverts the author's own work in
`draft.md` and reports success.

This is the mistake that motivated `detect`. `e37d5f3` bundled a corpus-wide deity-pronoun
capitalization sweep into an unrelated compose commit, and the sweep never reached Substack.
On `The Way Home Is Down` the comparison was run by hand and caught it — ten capitals that
would have been reverted. On `They/Them` and `I Believe in You` it was **not** run, and ten
more capitals were quietly pulled out of two live essays before the author caught it. Against
the live scan, `detect` scores the right revision 83/83 and the tempting newest one 80/83.

The check is the tool's job, not the operator's memory. Run it.

## Before a recompose: check the images

A surgical push never touches an image. A **recompose** re-pastes the whole body, and any
image the live post holds that `draft.md` does not reference is destroyed by that paste.

Images are **URL-only** on this desk (2026-09-01): the repo stores no bytes, and a draft
points at the asset already hosted on Substack. That keeps binaries out of git history, and
it is safe **only** while every live image is actually referenced in the draft — so check,
every time, before anything rebuilds a post:

```
python3 framework/tools/substack_sync.py images pieces/<name> images.js     # run it in the editor
python3 framework/tools/substack_sync.py check-images pieces/<name> images.json
```

It exits non-zero and names any live image the draft does not know about. **Fix a gap by
pasting that URL into `draft.md` where the image belongs — never by deleting the image from
the post.**

Two details it handles so you don't have to: the same picture appears twice in a scrape (the
node's S3 `src` and the rendered `<img>`, which Substack wraps in a `substackcdn.com/image/
fetch/…` transform), and the wrapper embeds the original URL-encoded — so it unwraps and
dedupes before comparing. Without that it would report a perfectly safe post as unsafe.

`The Highest Peak` is why this exists: a `captionedImage` in the body, no image markdown in
the draft, and a recompose requested. It was one paste from losing the image with nothing on
disk to rebuild it from.

## Reading the push report

`{stagedEdits, unchanged, applied[], footnoteChanges[], reviewMarks[], failed[],
structural, reordered[], suspect[]}`.

- **`failed` must be empty.**
- `structural: true` — nothing was applied. Check `reordered` and `suspect`:
  - **`reordered`** — a target block's exact text sits at a *different* live index. The two
    lists are misaligned, not edited. Do not patch; find out why.
  - **`suspect`** — a changed pair too dissimilar to be the same node.
- `reviewMarks` — a hunk that crossed a formatting boundary. Eyeball those in the editor.

## Confirm it reached readers (`substack_verify`)

"Saved" is not "shipped," and a baseline is a local file — a piece can match its
baseline perfectly while the live post says something else. After any write to a live
post, check the page a reader actually gets:

```
python3 framework/tools/substack_verify.py --fresh pieces/<name>
```

It fetches the public URL over plain HTTP (no browser, no credentials, no writes),
pulls the post out of the page's `window._preloads`, renders the local draft, and
compares block for block and footnote for footnote. `--fresh` cache-busts — measured to
turn `cf-cache-status: HIT` into `MISS` — so a stale CDN copy cannot fake either a pass
or a failure.

Exit 0 match, 1 drift, 2 nothing could be read. **2 is not a pass**: a run that verified
no pages reports failure, because "I could not look" and "it matches" must never wear
the same face.

Run with no arguments to sweep every published piece.

> Do not put this in CI on a GitHub-hosted runner. Measured 2026-09-02: Substack returns
> **403 to Azure IP ranges** on every path — page, API, and RSS, with any user agent. It
> is an IP block, so there is no header that fixes it. Run it locally, or from a
> self-hosted runner.

## Before you change any of this

```
python3 framework/tools/test_suite.py
```

35 checks: normalization, three-way classification, the converter, footnote ordering, pull
verification, images, plus a corpus sweep (every piece renders; every published piece matches
its baseline) and the JS patcher's own A–E suite against all 27 pieces via a stubbed editor.

CI runs it on every push and PR in both repos — against the shipped fixtures in the
framework repo, against the real corpus here. Neither can check a draft against the LIVE
post: that needs an authenticated browser and stays a human-run `scan`.

It deletes nothing, makes no network calls, drives no browser, and writes only inside a
temporary directory — so it can never touch a live post. It replaced a bash loop that contained
`rm -f $S/*` with `$S` unquoted, which was one empty variable away from `rm -f /*`.

## Guardrails

- **Never click Publish / Continue / Update / Send** — that control **sends email**. But the old
  claim here, *"the skill stages; a human ships — this holds doubly here,"* was **backwards, and
  it was most wrong exactly where it sounded most careful.** The target being a live post is what
  **removes** the gate, not what strengthens it: **on an already-published post the push is the
  publication.** Readers see it on autosave.
  **Therefore the checks that matter all run _before_ the write:** the pre-image hash per block,
  the conflict refusal, the structural refusal. There is no after. Anything wrong that lands is
  **already public**, and the fix is another public edit — so re-read *Reading the push report*
  and mean it.
- **Conflicts stop the run.** Do not pick a side. Show the user both versions and let them
  choose.
- **Structural divergence is not auto-merged by `plan`/`push`.** A block added, removed or
  reordered on either side is described and left alone by the three-way tooling. **When the
  draft side is the one that moved** — a rewrite of a live post — use the structural engine,
  `substack_repatch.py --structural` (see the `publish` skill, *Structural republish*): it
  aligns by block text, keeps footnote anchors by editing those blocks by hunk only, drops a
  retired footnote's anchor, refuses an added footnote, and hash-checks every block it writes.
  Seal afterwards as usual. It still never guesses: every refusal names the block.
- **Never pass a flag to force past a refusal.** The refusals here exist because each one
  has already been the failure mode once.
- **Seal every completed sync.** The baseline is the whole mechanism. A seal now records
  **both** domains, and refuses while either disagrees — including the case where every word
  matches and an italic does not.
- **A draft that is deliberately ahead of its post gets declared, not sealed.** A rewrite
  drafted and waiting on the author's read is a normal state on this desk, and the corpus
  baseline check would otherwise report it as a failure for as long as it lasts — which is how
  a corpus-wide gate gets tuned out and stops being read at all. Say so in `publish.yaml`:

      draft_ahead:
        since: 2026-09-07
        note: v2 rewrite drafted, awaiting Eric's read; the post still holds v1.

  It is shaped like the `verified:` clearance on purpose — a date and a sentence, in the diff,
  surviving the session. **One line per value**; the manifest reader does not fold `>-` block
  scalars, and a folded `note:` parses to the literal string `>-`. Two rules stop it becoming a
  way to switch the check off: a declaration with **no `since:` date excuses nothing** and still
  fails, and a declaration on a piece that is **back in sync** fails too, so the key retires
  itself once the rewrite ships instead of sitting there excusing the next drift nobody noticed.
  **It is never a substitute for sealing a sync that actually completed.**
- **A pull that reverses an editorial pass is a red flag, not a result.** If a plan wants to
  undo something the author clearly meant (capitalization, a house convention, a considered
  rewrite), stop and re-run `detect` — the baseline is probably wrong, and the "Substack-side
  edit" is really the live post being *behind*.
- **The same preflight as `publish` applies**: footnote claims fact-checked, internal notes
  behind a `†`, and the critique gate for a substantive re-sync.

## Two bugs this replaced (do not reintroduce them)

Both were found on 2026-09-01, in a batch of six live posts that were one click from being
damaged.

- **Footnote order.** `md_to_substack.render_reader` emitted footnotes sorted by *label*
  (numerics, then alphabetically) while the live post holds them in *reference* order — and
  the surgical patcher aligns footnote nodes **1:1 by index**. `In the Name` rendered
  footnote #0 as `John 10:3` against a live #0 that was the *shelucho shel adam* maxim.
  Thirty footnotes, thirty mismatched, and the only structural check was a count: 30 == 30,
  so it passed. Footnotes are now emitted in first-reference order, and `substack_repatch`
  carries a guard that detects a permutation.
- **Smart quotes.** `draft.md` is written with straight quotes; Substack curls them as the
  body is pasted. Nothing normalized this, so every quote-bearing block looked changed and a
  "one-word" re-sync would have rewritten the typography of an entire essay. The diff domain
  is now flattened (curly → straight, a length-preserving substitution so offsets stay
  valid), and any run actually inserted is smartened to match the document it lands in.

A third, found 2026-09-09 and the same shape:

- **Formatting was invisible to every domain this desk compares.** Reader-text is tags
  stripped, so wrapping an existing word in `<em>` produced **zero diff** everywhere:
  `substack_repatch` reported `unchanged` and applied nothing, `substack_verify` reported
  MATCH, and the sync baseline recorded a text hash that could not tell the two apart.
  Measured on `rising-after-falls`: the regenerated patch was **byte-identical in size to
  the previous one (29,782 bytes)**. Marks are now a second domain everywhere — enumerated
  from both sides by one scanner, hashed into the baseline, applied by the repatch engines.
  The corresponding guardrail is above; the detail is in the `publish` skill's **0b-marks**.

The lesson all three share: **a guard that cannot see the failure it is named for is worse
than no guard**, because it reads as coverage. A count cannot see a permutation, and a hash
of the words cannot see the italics.
