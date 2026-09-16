# Scheduling a publication

A piece can be finished and not be due. Between sealing it and publishing it there was
nothing in the desk that knew the difference — every tool that publishes would publish,
and the only thing standing between a sealed piece and a live one was somebody
remembering. This is the thing that knows.

**One field, one moment, one refusal.**

```yaml
publish_at: 2026-09-15 09:00 America/New_York
```

`tools/schedule.py` holds the field and the rule. (Eric, 2026-09-11, on the first
scheduled piece: *"lets seal it but delay publishing it until next week."*)

## The commands

```
python3 framework/tools/schedule.py check <piece>...     exit 4 while it is embargoed
python3 framework/tools/schedule.py list                 every piece carrying the field
python3 framework/tools/schedule.py due --within 48h     what opens inside a window
python3 framework/tools/schedule.py set <piece> "2026-09-15 09:00 America/New_York"
python3 framework/tools/schedule.py clear <piece>
```

`set` refuses the moment before it writes it, so a manifest never carries a `publish_at`
the tools cannot read.

## What it refuses, and what it only warns about

The line is **public, or not public** — not *finished, or not finished*.

| | | |
|---|---|---|
| **`md_to_site.py`** | **REFUSES**, exit 12 | The store bundle is what a site reads. An embargoed piece in it is a published piece. It **refuses** rather than skipping, because a piece named on the command line and silently dropped is how an embargo is discovered a week later. |
| **`md_to_substack.py`** | warns | A Substack draft is private. Composing early is *how* a scheduled publication is prepared, so it composes and prints the moment where the composer will read it. |
| **`md_to_linkedin.py`** | warns | It writes a file on this Mac. The warning is there because the next thing anyone does with that file is paste it. |
| **the `publish` skill** | **stops** | It runs `schedule.py check` in preflight and will not click Publish before the moment. |

## The order: compose, review, THEN arm

**The schedule is not set until the drafts are reviewed and approved.** (Eric, 2026-09-11:
*"in general, we dont set the schedule until the drafts are reviewed and approved."*)

A scheduled publication is the one kind that fires with nobody watching, so the reading has to
have happened before it is armed — and the thing to read is produced by composing, which puts
composing *first* and arming last:

1. **Compose the drafts** under the embargo. A Substack draft is private and a LinkedIn Article
   is a draft until published; `md_to_substack.py` prints the embargo and carries on, which is
   what makes this step possible at all.
2. **The author reads them** — the drafts themselves, and the review artifact beside them.
3. **Then arm.** Each platform's own scheduler is set to the moment, and any desk-side wake-up
   is recorded with `schedule.py arm --reviewed "<who, when>"`. **`arm` refuses without
   `--reviewed`**, and writes who approved it into the manifest, so the order is auditable
   afterwards rather than merely intended.

Ordering note for a syndicated piece: the LinkedIn copy carries *Originally published at
&lt;canonical&gt;*, so it is composed **after** the canonical is live, not before. That is a
publication-day step, not a preparation step.

## Not every outlet waits — `on_schedule:`

**One piece has one moment; the outlets it names do not all want it.** (Eric, 2026-09-11: *"we
should be able to configure an outlet for immediate publishing when scheduling … this is because
the other sites (substack and linkedin) benefit from regular publishing and the websites (using
quire) are the canonical publications and do not drive traffic".*)

So the policy belongs to the **outlet**, in the instance's `publishing/outlets.yaml`:

```yaml
outlets:
  alignmentfellowship:
    on_schedule: immediate     # canonical quire site: publishes as soon as the piece is ready
  substack:
    on_schedule: at_moment     # the default; a feed outlet waits for publish_at
```

| class | outlets | why |
|---|---|---|
| **immediate** | the quire websites | They are the **canonical** publication and drive no traffic. A finished piece belongs there at once, and its URL is what every other outlet points at. |
| **at_moment** | Substack, LinkedIn | Regular publishing is the point of a feed. The moment is for them. |

**It fails closed, in every direction.** A missing registry, an unknown outlet, an absent
`on_schedule`, a typo (`imediate`), or no PyYAML all answer `at_moment` — the answer that refuses
to publish. Only the exact string `immediate`, on that one outlet, turns the moment off.

**An exemption is said out loud.** `md_to_site.py` prints *"… is embargoed until <moment>, and
<outlet> is configured `on_schedule: immediate` — publishing it there now, on purpose"*, because a
piece published before its moment with nothing on the terminal reads exactly like a piece that
never had an embargo.

### What dates a canonical-first piece

`md_to_site.py` exports a piece once it has `published_at`, and `bundle_pieces.py` **requires**
it — the page a reader gets has to be dated. So the date is the mechanism, and it is written at
the canonical publication rather than derived from `publish_at`:

- **A piece published canonically first** records `published_at` on the day the site goes live.
  The feed outlets are then *scheduled, not missing* — `outlet_audit` reads that state through the
  outlet's `on_schedule` and counts it as `sched` while the moment is ahead.
- **A redraft of an already-live piece keeps its original date** (Eric, 2026-09-11:
  *"the redrafts KEEP THEIR ORIGINAL DATES"*), held in `original_published_at:` and copied to
  `published_at` at the cutover, so setting it early cannot put the piece into the store before
  the switch.

An earlier version of this page said the unpublished guard in `md_to_site.py` had to move for an
immediate outlet. It did not: that guard only decides what enters the bundle *content*, and
`bundle_pieces` refuses an undated piece immediately afterwards — so relaxing it moved a refusal
one step later and changed nothing that could publish. The date is what makes a canonical-first
publication possible, and `publish_at` still governs every outlet that waits.

## The wake-up, and what it is for

`schedule.py runbook <piece>` prints a self-contained prompt for a scheduled session: the piece,
the moment, the gates, the order, and what to do if it fires late. It is generated from the
manifest rather than typed, so moving `publish_at` cannot leave a stale moment buried in a prompt
nobody re-reads. `arm` records the task; `armed` lists what is armed across the desk.

What a wake-up is *for* is the step no platform can do for itself — the canonical store publish
and the redirect removal. The subscriber email and the syndicated copies belong to Substack's and
LinkedIn's own schedulers, which need nothing from this Mac and do not care whether the app is
open.

## Record the act, not only the intent

`publish_at` says when a piece is **due**. A native schedule — Substack's, LinkedIn's — lives on
the platform, where nothing in this desk can see it. So a tool reading `publish_at` alone reports
*"its own scheduler has it for Tuesday"* **whether the schedule was set or forgotten**, which is
the one failure a scheduled publication actually has.

So the act is written down where the intent is:

```yaml
scheduled:
  substack-muffinlabs:
    at: 2026-09-15 09:00 EDT
    set: 2026-09-11
    where: Substack's own scheduler, on draft 215307337
    evidence: https://muffinlabs.substack.com/publish/post/215307337
    approved: Eric, 2026-09-11
```

written by `schedule.py record`, which **refuses without `--approved`** for the same reason `arm`
does. `outlet_audit` then reads three states rather than two:

| | |
|---|---|
| **scheduled** | due later, and a record says a scheduler was told — printed with where and when |
| **NOT SCHEDULED** | due later, and nothing records one. **A finding, on the day it can still be fixed.** |
| **MISS** | the moment has passed and the copy is not there |

**A 200 before the moment is a teaser, not the post** (2026-09-16). A waiting outlet whose moment
is still ahead cannot be carrying the piece, so `outlet_audit` judges its copy by the schedule
even when the address answers — Substack serves a scheduled post's own URL with a teaser (see
below), and the forward check used to count that as present. The tag gate then asked for tags on
a post whose API answered 404. It reads *scheduled* now, which is what it is.

## Two things measured on the first scheduled publication (2026-09-11)

**A scheduled Substack post has its slug from the moment it is scheduled.** `GET
/api/v1/drafts/<id>` reads `slug: null` on a plain draft and the real slug once `postSchedules`
exists — so the post's public URL is knowable days ahead, and anything that needs it (a Note, a
cross-link, a LinkedIn copy) can be prepared before the post is live. The URL serves a teaser
page in the meantime: title and `og:` tags, **no body**, `robots: noindex`. The piece is not
readable early.

**But a Note cannot attach a post that has not published.** Composing the Note ahead of time —
with the correct URL, from the correct slug — puts *"This attachment is not available"* in the
composer instead of the post's card. The teaser page carries every `og:` tag a card needs, so
this is Substack refusing to attach an unpublished post, not missing metadata. The consequence
is the rule:

> **A Note scheduled ahead of its post carries a plain link, not a card.** To get the card, the
> Note is composed *after* the post is live. `substack_notes.py text <slug> --post-url <url>`
> builds the scheduled version for the case where a plain link is acceptable.

## The Note goes by a scheduled task, and that is the house default

(Eric, 2026-09-11: *"ok lets formalize using the claude-app task for notes."*)

A Note is the one piece of a scheduled publication that **cannot** use its platform's scheduler
properly, for the reason measured above: Substack will not attach an unpublished post, so a Note
scheduled ahead carries a plain link where the card belongs. So the Note is posted **after** the
post is live, by a one-shot scheduled task in the Claude app:

```
python3 framework/tools/substack_notes.py task <slug> --post-url <the post's URL> --at "<moment>"
```

prints a **self-contained prompt** — a scheduled session has no memory of the conversation that
armed it — and the task is created for a few minutes after the post's own moment. Record it like
any other schedule: `schedule.py record <piece> --outlet note --where "Claude app task <id>"
--approved "<who, when>"`.

**What the prompt refuses to do, and why each one is in it:**

| the guard | what it prevents |
|---|---|
| Fetch the post cache-busted and require the **body**, not the teaser | announcing a post nobody can read, if Substack runs late |
| `substack_notes.py status` first; stop if a Note is recorded | a second Note — there is one per post, ever |
| The composer snippet's **sha256 must equal the tool's** | a Note that is not the text the author read |
| **`card` must be true** | the exact failure this whole arrangement exists to avoid |
| Name the browser and confirm the account before composing | posting under the other publication's byline |
| Stop and report on any refusal | a half-finished public act with nobody watching |

**The authorization is specific and the prompt says so**: the author approved *this* Note, whose
text he had already read. It does not extend to rewriting it or posting a different one.

**Two caveats worth saying out loud.** The task runs while the app is open — if it is closed at
the moment, it runs at next launch, which for a Note is late but harmless. And a task's first run
may pause on tool permissions; *Run now* on a task that has nothing to do is the cheap way to
pre-approve them.

## Nothing here fires by itself

Deliberately. `schedule.py` compares a moment to now; it owns no clock and starts no
job. An unattended publication is a decision made explicitly, in the one place built for
it: **Substack's own scheduler**, set in the composer once the draft is ready, which
sends the subscriber email at the appointed time whether or not anyone is at the Mac.
The blog and LinkedIn are done in the session that opens the piece on the day.

The reason to keep it this way is that the desk's publishing steps are not idempotent in
the way a cron job needs — a store publish, a Substack click that sends the one email, a
LinkedIn post — and a failure at 9 a.m. with nobody watching is a worse failure than a
publication that happens at 9:20 with somebody reading the confirm dialog.

## Why the timezone is required

`2026-09-15` is not a moment. It is a date in whatever zone the reader is in, and an
embargo that opens at a different instant depending on who asks is not an embargo. A
moment with no zone is **refused** (exit 2), never assumed.

Write the zone rather than an offset: `America/New_York` stays correct across a DST
boundary where a fixed `-04:00` quietly does not.

## After it opens

The field does not expire and does not need to. Once the moment has passed, `state()`
reads *open*, every tool proceeds, and the line can stay in the manifest as the record of
when the piece was due. Clear it only if the piece is genuinely unscheduled again.

## Per-outlet publication dates

**One piece, one date could not describe the desk it ran on.** A canonical quire site carries
`on_schedule: immediate` and is meant to lead; the feed outlets wait for the moment. Those are
genuinely different days, and a single `published_at:` had to mean both — so in practice it meant
*live on the feed outlet*.

```yaml
published_at: 2026-09-12          # the piece's date; what a one-outlet piece uses
published:
  alignmentfellowship: 2026-09-12 # the canonical led
  substack: 2026-09-12            # the feed outlet's own post_date
```

`schedule.published_on(piece, outlet)` answers it: the outlet's own entry wins, and
`published_at:` is the fallback, so **every manifest written before this keeps working** and a
one-outlet piece never needs the block. `md_to_site.py` gates and dates the export per outlet.

**The contradiction this resolved, because it is the interesting part.** `md_to_site.py` held back
any piece with no `published_at`, for a good reason recorded in its own comment: *an outlet
declaration is INTENT; publication is FACT*, after a composed-but-unpublished piece once entered a
bundle bound for a live site. But `published_at` is written **after the feed outlet goes live** —
so **the canonical could only ever publish after the outlet it is supposed to precede.** The
registry said *canonical first* and the tooling made it unreachable. Measured 2026-09-12, by
following the registry exactly and getting a live Substack post whose canonical URL 404'd.

So the gate now reads: a piece with **neither** `published_at` **nor** `publish_at` is a draft and
is held back everywhere — the original guard, untouched. A **sealed, scheduled** piece is not a
draft, and on an `immediate` outlet it leads, dated with the moment it is due.

## The canonical leads, and `record` enforces it

`schedule.py record` **refuses** to write a feed outlet's native schedule while the piece declares
an outlet configured `on_schedule: immediate` that is not live yet:

    refusing to record: the canonical has not been published.

A native schedule fires unattended, so arming one over an unpublished canonical *schedules* the
half-published state `outlet_audit` exists to find. **It is conditional by design** (Eric,
2026-09-11: *"refuse, but only if there is a canonical outlet and it is configured to publish
immediately"*) — a piece with no immediate outlet has no canonical to lead, and nothing invents one.

## The runbook is generated from the piece

`schedule.py runbook <piece>` was **one hard-coded template** written for a single MuffinLabs
piece, with `{slug}`/`{title}`/`{moment}` substituted into it and handed unchanged to every other
piece on the desk. For an *elmuffin* piece it named a LinkedIn article the piece does not have and
told the session to edit `muffinlabs-web/next.config.ts` — another publication's repo — and it
never mentioned the canonical site, `piece_header.py`, `substack_verify` or the Note.

It is now built from the manifest: the piece's own outlets, split by policy into the canonical that
leads and the feeds that wait; its `companions:` Note if it has one; and **the whole
reconciliation**, which was the standing gap. The platforms publish themselves; the per-outlet
date, the header, the four verifications, the **link preview** and the Note's record are all the
desk's, and every one of them used to depend on somebody remembering. (Eric, 2026-09-12: *"the
Still to do after it fires should be baked into the tooling so it runs at the same time as the
note."*)

**The link preview is in there because it is the step a store publish structurally cannot do:**
`og:image` is a file in the site repo and an upload never touches that repo. It was forgotten again
on 2026-09-12 and `outlet_audit` caught it — a live page whose shared link showed no image.

## The Note's card is spent by scheduling it

A Note announces a post, so it is tempting to put it on the composer's own scheduler for the same
moment. **That spends the post's card permanently.**

The card is not resolved from the URL when someone reads the Note. It is a **stored attachment**,
written at compose time, and Substack will not attach a post that is not yet public. Measured
2026-09-14, on a Note two days old whose post had been live the entire time:
`/api/v1/reader/comment/<id>` returns **`attachments: []`**. It never backfills, a posted Note
cannot be edited, and the only way to get the card is to post a different Note.

So the default is **not** the composer's Schedule. It is `substack_notes.py task <slug>
--post-url <url> --at "<moment>"`, which schedules a session to post the Note a few minutes
**after** the post goes live and guards on **`card` must be true**. The composer's Schedule is the
fallback for an author who would rather not have a session wake up — and it is only offered with
the cost said out loud, because a plain truncated link is what every reader of that Note gets,
for as long as the post exists.

*(Written after doing it the wrong way round on 2026-09-12: the Note was scheduled for the same
moment as the post, fired 85 seconds before it, and carries a bare `elmuffin.substack.com/p…`
where the card should be. The mechanism to do it properly already existed and was not reached
for.)*
