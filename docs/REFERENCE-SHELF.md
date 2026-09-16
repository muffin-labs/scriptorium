# The reference shelf — one shelf per desk, with a private copy off the machine

> **Status** (2026-09-13). **Part one — one shelf at the desk root — is BUILT**, and so is
> everything in part two that runs on this machine: `rehash`, `push`, `pull`, the shelf
> domain in `check`, and the CDK stack (`infra/lib/reference-shelf-stack.ts`, synthesizes
> clean). **The stack is NOT DEPLOYED and nothing has been uploaded** — that creates real
> resources in a real account and is the author's call, not a session's. `check` reports
> the shelf as NOT CONFIGURED and names what the desk is one disk away from losing.
>
> **To turn it on:** `cd infra && npx cdk deploy DeskReferenceShelf`, take the
> `ShelfBucketName` output into `references/shelf.yaml` (shape below, and
> `references.py push` prints it), then `references.py push --dry-run`.

The desk holds source texts so that a quotation is checked against a file rather than
recalled, and the folder that holds them **denies by default**: `*`, plus one `!` line per
public source. A copyrighted file is therefore held on disk and **never committed**,
because git history is one-way and no later edit removes a PDF from it.

That rule is right and is not up for revision. This document is about the two bills it
leaves unpaid: the shelf is divided by a unit that does no work, and the half of it that
cannot be committed exists in exactly one place.

## Part one — one shelf, at the desk root  ✅ built 2026-09-13

### How it worked, and why the division was theatre

Storage was **per book**: `books/<book>/references/`, each with its own `.index/`, its own
manifest `README.md`, its own deny-by-default `.gitignore`. The book was in every path —
`refdir(book)`, `index_for(book, file)`, `rows(book)`.

Behavior was **per desk**. `catalog()` walks every book unless `--book` is passed, and
nothing passes it: `search`, `check` and `check_quotes` all default to `None`, and
[`gates.py`](../tools/gates.py) runs `check_quotes.py {piece}` with no `--book` at all.
Nothing infers a piece's book from the piece. **In the gate that runs before every review
and every publish, the desk already has one flat shelf** — wearing a per-book directory.

And the division was never exercised: three books existed and **one** had a
`references/` folder. `alignment-fellowship` and `all-my-stories` had none.

The framework itself already suspected this. `check_loci.py` resolves its KJV index
in this order:

```python
INDEX_CANDIDATES = [
    os.environ.get("KJV_INDEX", ""),
    "references/kjv.tsv.gz",                    # ← desk root, tried FIRST
    "books/being-good/references/kjv.tsv.gz",   # ← the book path, as fallback
]
```

A desk-root `references/` is already preferred, with the book path behind it and a
`books/*/references/` glob behind that. Somebody had already written the conclusion down.

### The move

```
references/                     one shelf for the desk
  README.md                     the manifest — one row per file, with a Book column
  .gitignore                    one deny-by-default file
  .index/<stem>.tsv.gz          derived, uncommitted
  <source files>
```

The book stops being a directory and becomes **a column in the manifest**.

The house rule is *add structure only when it's used*, and that alone would settle it. But
the substantive argument is better: **a source serves pieces, not books.** Lawrence grounds
both the Alignment Fellowship foundation and *Being Good*. The KJV serves everything.
Under a per-book directory a shared source is either duplicated — with a second copy, a
second index and a second row — or assigned a home arbitrarily, at which point the
directory asserts something false about a file that the manifest would have recorded
correctly.

And the association the directory stands in for **already has a home**:
`projects/<book>/sources.md`, the annotated *why it matters*. The references folder was only
ever the manifest of files on disk. A file can serve two books; a directory can hold it
once.

`--book` survives as a filter over the manifest's Book column, which is what every call
site meant anyway.

### What the move cost — measured, not estimated

52 files and 49 indexes moved; 52 rows gained a Book column;
rewrite one `.gitignore` and the root's defense-in-depth lines; collapse `refdir(book)` →
`refdir()` and `books()` out of `references.py`, `refindex.py`, `check_quotes.py` and
`check_loci.py` (whose fallbacks then become dead and should go with it).

One commit. The new `references/.gitignore` was written and **probed with
`git check-ignore` BEFORE a single byte moved** — the same order `references.py add` uses,
and for the same one-way reason. Tracked files moved with `git mv`, ignored ones with
`mv`; afterwards **17 ignored, 37 committable, 0 problems**, which is exactly the split
that existed before. `references.py check` green (52 files, 52 rows, 49/49 indexed); suite
742 passed, 0 failed.

`check` gained one finding with the column: **`UNKNOWN BOOK`** / **`NO BOOK`**. The Book
column is all that is left of the directories, so a row naming a book the desk does not
have is a filter that silently matches nothing.

## Part two — the shelf goes to S3

### Why

Deny-by-default bought safety by trading a copyright leak for a **single point of
failure**. Measured 2026-09-13:

| | files | on disk |
|---|---|---|
| held sources | 52 | 119 MB |
| **of those, committed to no repo** | **17** | **69 MB** |
| derived indexes (`.index/`, uncommitted) | 49 | 19 MB |
| **indexes of the uncommitted 17** | 17 | **3 MB** |

Seventeen files exist on one Mac and nowhere else. They are not incidental: McGilchrist,
Campbell, Sanders, Feynman, Born & Wolf, and the Hicks and Byrne volumes that are the
*False Light* exhibits. Several are held **specifically because the edition is the thing a
page number depends on** — the manifest says so in its own rows, at length, for *Hero with
a Thousand Faces* and *The Master and His Emissary*. Losing that disk does not lose a
convenience; it loses the ability to check a citation the corpus has already printed.

**The shelf does not loosen the gitignore rule. It removes the cost of the safe default.**
That is the whole argument, and every decision below follows from it.

A second benefit falls out and is the one Eric asked for: a desk cloned onto another
machine can pick its shelf back up. But a sync feature that happened to be a backup would
be designed differently from a backup that happens to sync, and this is the second.

### Where it lives

A **third bucket**, `desk-references-<account>`, defined in `infra/` beside the content
store — for exactly the reason `infra/lib/content-store-stack.ts` already gives for
splitting snapshots off the store: `store_publish.py --prune` deletes every object a
bundle does not name. A shelf inside either existing bucket is one ordinary publish away
from being deleted, and a backup that shares a bucket with its source is not a backup.

The properties are the snapshots bucket's, and **the absences are the design**:

- `BlockPublicAccess.BLOCK_ALL`, `publicReadAccess: false`, `enforceSSL`, SSE-S3.
- `versioned: true`, `removalPolicy: RETAIN`, **no expiry lifecycle**. Deleting backups on
  a timer is how people find out they had none.
- **No CloudFront. No distribution. No CORS.** Nothing reads this over the web, and a CDN
  in front of a shelf of copyrighted PDFs is the one addition that would turn an exposure
  into a public URL. The content store has a distribution because sites read it; this has
  no reader but the desk.
- SSE-S3, not KMS. The threat is accidental public exposure, not AWS reading Feynman.
  Key management here would be cost without a corresponding failure it prevents.

Cost is a rounding error — 119 MB in S3 Standard is about three-tenths of a cent a month.
It is not a factor in either direction and should not be argued as one.

### The key is the hash, and the manifest is already the pointer

```
refs/<sha256>/<filename>
refs/<sha256>/.index/<stem>.tsv.gz      keyed by the SOURCE's hash
```

The hash prefix carries integrity and makes upload idempotent; the filename leaf keeps a
console listing legible. **There is no book in the key**, and there would not have been
one even without Part One — which is the same conclusion arriving from a third direction.

**No new catalog is created, and that is deliberate.** `references.py` already refuses a
second machine-readable catalog beside the README, on the grounds that two sources of
truth for one fact is worse than one source in the wrong place. The same rule binds here:
the manifest row in `references/README.md` already records the sha256, so **the row is the
S3 key.** A fresh clone knows what should be held, what it hashes to, and whether it is
restricted, before fetching a byte.

Three consequences worth stating, because each is load-bearing:

- **Immutable objects cannot collide.** Two machines pushing the same file write the same
  bytes to the same key. Every wound this desk has taken has been a shared singleton — the
  dashboard, the root `.gitignore`, the git index — and content addressing buys the
  absence of that failure by construction rather than by lease.
- **A rename is free.** The same bytes under a new name are one new key, not a duplicate
  upload, and the old key is still exactly what the old manifest row points at.
- **The shelf can be verified against the manifest without being listed.** Same discipline
  as `snapshot.py`: discover from the manifest, never from a bucket listing.

### The one blocker, named

`references.py` writes `digest[:16]…` into the manifest row. **Every hash in the manifest
today is truncated**, so no existing row can address an object. A one-time
`references.py rehash` must fill full digests into existing rows before any of this works.

It rewrites every row of a hand-maintained table, exactly as the Part One migration does —
so the two are **separate commits, in order**: consolidate, prove with `check`, then
rehash, prove with `check` again. One of them is reversible; the other is the thing every
S3 address depends on, and a table rewritten twice in one commit is a table nobody can
review.

### What goes on the shelf

**Sources.** Indexes stay derived and local: `index --all` rebuilds the shelf in twenty
seconds, and a pushed index is a second copy of a fact that can drift from the first.

**With one exception, and it is the most useful thing here.** `check_quotes.py` searches
the *index*, not the PDF. The indexes of the seventeen uncommitted sources come to **3 MB
against their 69 MB of originals** — twenty-three to one. So:

> `references.py pull --indexes-only` gives a second machine a **working quote gate over
> the copyrighted corpus while it holds not one copyrighted book.**

That is a different capability from *sync my shelf*, and a better one. It is also the only
form in which the gate could run somewhere that should not hold the sources at all. An
index is still that source's text in another shape, so it lives in the same private bucket.

### The commands

```
references.py push [--book B] [--dry-run]        # held files missing from the shelf
references.py pull [--book B] [<file>] [--indexes-only]
```

`--book` filters the manifest's Book column; it is no longer a path.

Neither command asks for a redistribution verdict, because the shelf is private and holds
public and restricted files alike. **The classification governs git, not S3.**

`push` refuses a file whose row states no verdict. `check` already reports that case
(`REDISTRIBUTION NOT STATED`) and treats it as restricted; `push` should not be the tool
that quietly settles a question the manifest has left open.

`pull` writes a file only when the bytes hash to what the row names, and **never
overwrites a differing local file** — it reports the divergence and stops. A pull that
silently replaced an annotated or re-OCR'd local copy would be the one unrecoverable move
in an otherwise recoverable tool.

### What `check` gains

`references.py check` proves manifest ↔ disk ↔ gitignore ↔ index. The shelf is a fifth
domain, and it brings three findings:

- **`ON DISK, NOT ON THE SHELF`** — held here and backed up nowhere. This is the
  single-point-of-failure finding, and it would name all seventeen files today.
- **`NOT HELD, BUT ON THE SHELF`** — the manifest names it, this machine lacks it, and it
  is one command away.
- **`HASH MISMATCH`** — the bytes on disk are not the bytes the row names. New, and only
  checkable once the hashes are full. It catches a re-download that changed edition
  without the row changing, which today is invisible.

**And the message that matters most is in another tool.** `check_quotes.py`'s `NOT HELD`
finding currently ends *"→ bring it in: `references.py add <file> …`"* — go find a PDF.
Once there is a shelf it must first say:

```
→ on the shelf:  python3 framework/tools/references.py pull <file>
```

That is where a session actually meets the problem, and it is the whole
multiple-locations story delivered at the point of use rather than in a document.

### Configuration

`references/shelf.yaml`, beside the shelf it configures. The framework holds no bucket
names — same rule as `outlets.yaml` and `store.yaml`, whose tools take the path as an
argument.

It is kept out of `publishing/store.yaml` on purpose: that file describes the **public
read path**, and reading a config should make obvious which bucket the world can see. One
file holding both a CloudFront base URL and a shelf of copyrighted PDFs is a file somebody
will misread once.

```yaml
shelf:
  bucket: desk-references-<account>
  region: us-east-1
  aws_profile: muffinlabs      # SSO, as the store does. No long-lived keys on disk.
```

### CI

`references.py check` is **not** in [`gates.py`](../tools/gates.py) or `ci_check.py`
today, so the pre-push hook will not go red on a runner with no AWS credentials. If it is
ever added, the shelf domain must **skip loudly** and say it skipped — this house already
knows that a skip is not a pass, and a shelf check that silently passes when it could not
reach the bucket is worse than no shelf check.

## What this does not do

Holding a source privately does not make a claim true, and neither does holding it in two
places. This makes a quotation **checkable from more than one machine** and says loudly
when a source is backed up nowhere. It cannot tell you a page says what the prose claims
it says. That is `review`'s re-open-the-sources read, and it is a human's — the same
warning `references.py`, `check_quotes.py` and `check_verified.py` each give about
themselves, for the same reason.

## Order of work

1. **Consolidate** to `references/`, book → manifest column. `check` green either side.
2. **`rehash`** — full digests into every row. Its own commit. `check` green again.
3. **The bucket**, in `infra/`, and `references/shelf.yaml`.
4. **`push` / `pull`**, then `check`'s fifth domain, then `check_quotes`'s new message.

Steps 1 and 2 have value on their own and are worth doing whether or not 3 and 4 follow.

**Not alongside the citation-check work.** [CITATION-CHECKS.md](CITATION-CHECKS.md) has its
own rename sweep and its own migration, and both tracks prove themselves with a green
`references.py check`. Run one track to completion before starting the other; three
migrations converging on one green run is how a green run stops meaning anything.
`references/canons/` — the canon records that doc defines — lands inside the consolidated
shelf, which is the only place the two designs touch.

## Open, and deliberately left so

- **The manifest is still a shared singleton.** Content addressing makes the *bytes* safe
  under two machines; `README.md` is still a table both of them append to, and that is
  git's problem rather than this tool's. Consolidating to one shelf makes it slightly more
  contended, not less — worth watching once a second machine is real.
- **A shared bucket across desks was considered and dropped.** Prefixing keys by project
  would let several scriptorium instances share one bucket, at the cost of the
  cross-project dedup content addressing gives for free. One desk, one bucket, until there
  is a second desk to argue with.
