# Publications

A **publication** is what a reader subscribes to: one audience, one byline, a set of voices,
and the outlets it reaches them through. A desk can carry several. The framework names the
concept so that everything which must be kept *apart* per publication has something to key on.

## The shape of a desk

```
desk
├── publications          publishing/publications.yaml — the registry
│   ├── outlets           where it is read (outlets.yaml defines them; each has ONE owner)
│   ├── projects          the long projects it holds — projects/<name>/ (each has ONE owner)
│   ├── styles            the voices it speaks in — styles/<name>/ (each has ONE owner)
│   ├── house rules       publishing/house/<publication>.md — conventions every voice keeps
│   └── tags              its own vocabulary — publishing/tags/<publication>.yaml
└── pieces                each names exactly one publication in publish.yaml
```

```yaml
# publishing/publications.yaml
publications:
  being-good:
    name: Being Good
    byline: E.L. Muffin
    outlets: [substack, alignmentfellowship]
    projects: [being-good, all-my-stories]
    styles: [being-good-essay, being-good-journal]
    deity_conventions: true       # check_pronouns' deity sections apply to this publication only
  muffinlabs:
    name: MuffinLabs
    byline: Eric Garcia, PhD
    outlets: [muffinlabs, substack-muffinlabs, linkedin]
    styles: [essay, talk]
```

```yaml
# pieces/<slug>/publish.yaml
publication: being-good

# styles/being-good-essay/config.yaml
publication: being-good       # the voice names its owner back
```

## Layers: what governs a text

Most general first — and a rule lives at the narrowest layer that holds it for every text below:

| layer | where | holds |
|---|---|---|
| desk | `CLAUDE.md` | concurrency, commits, CI, the reference shelf, publishing mechanics — what every text keeps |
| publication | `publishing/house/<publication>.md` | house conventions every voice of that publication keeps (a casing rule, a link convention, what may be quoted and how) |
| project | `projects/<name>/` — README, brief, its own `CLAUDE.md` | one project's world: a novel's POV rules, a book's arc and ledgers |
| style | `styles/<name>/` | one voice |

**A publication's conventions do not belong in the desk's `CLAUDE.md`.** Every text on the desk
reads that file, so a rule written there for one publication is silently kept by the other — on the
reference desk, a professional essay inherited a devotional publication's deity casing for five
days. `publications.py context <slug>` prints the publication, house file, project and style of one
text; `draft`, `critique`, `review`, `rewrite`, `style-audit` and `publish` load what it names. A
publication with no house file keeps nothing beyond the desk's, and no skill borrows another's.

A **project** is a directory under `projects/` — a book, a fellowship's founding documents, a novel.
The directory was `books/` until 2026-09-16, and a desk that still has only `books/` is read
the same way. A piece names its project by linking into it from its README; a project need not publish pieces at
all (a novel drafts chapters in its own directory). `books:` is read as the older name of
`projects:`.

## What is per publication, and what is per desk

| per publication | per desk, shared |
|---|---|
| its outlets, and so its sites and its Substack | `pieces/`, one directory per piece |
| its tag vocabulary | the desk's concurrency rules, leases, the dashboard |
| its books and styles | the framework, the tools, the regression suite |
| its byline and its notes about its platforms | the content store (see below) |

A piece belongs to one publication. If the same argument should reach two audiences, that is
two pieces — the way a talk and its essay are two — each in its own publication's voice.

## The rules the tools hold

`tools/publications.py check` (and the suite's corpus check) enforce, once a registry exists:

- **Every outlet belongs to at most one publication.** A site reads the store by outlet, so an
  outlet shared by two publications is a site showing both.
- **Every manifest names a publication the registry defines.** `publications.py assign <piece>
  <publication>` writes the line — as text, under the title and subtitle, leaving every comment
  in the manifest where it was.
- **Every outlet a piece declares belongs to its publication.** The exporter refuses (exit 9) a
  piece that declares another publication's outlet.
- **Every style and every project belongs to exactly one publication**, and nothing under
  `styles/` or `projects/` is unowned. A style's `config.yaml` names its `publication:`, and a
  disagreement with the registry fails. **A text whose README names a style or a project its
  publication does not own fails** — one publication's voice cannot draft the other's piece.
  (Until 2026-09-15 this was a note; ownership ran one way, and a voice registered to neither
  publication passed.)
- **`deity_conventions: true`** marks a publication whose house capitalizes deity pronouns;
  `check_pronouns.py` asks its deity sections of that publication's texts only.
- A note, not a failure: an outlet `outlets.yaml` defines that no publication owns.

**A piece is LIVE at its own outlet's address, and every gate asks it that way.** Each outlet
declares the manifest field its reader URL is written under (`manifest_url_key`, `outlets.yaml`),
because each outlet has its own: `public_url` is the `substack` outlet's key, `blog_url` is
`muffinlabs`'s, `site_url` is `alignmentfellowship`'s. `check_status.live_url(man, outlets)` is the
one answer to *is it live, and where does a reader go* — the piece's own `canonical:` when it
records one, otherwise the first outlet in registry order that it has an address on, and
`public_url` on a desk with no registry.

Nothing about a second publication makes this optional, and nothing about it makes the failure
loud. Every reader of `public_url` on a desk with two publications does not mis-report the second
one — it reports it as **not published**, which is a state with no findings in it. On 2026-09-11
that was seven tools at once: the suite's header, manifest, declares-its-outlets and baseline
gates, `publications.missing_required`, `piece_header`, `md_to_site --syndicated`,
`sync_post_images`, `substack_tags --verify`, and (until scriptorium c1e192f, the day before)
`substack_verify` and `substack_notes`. The corpus counted 36 live pieces and the desk had 37;
the one nothing could see was live with a `*Draft —*` header and no sealed baseline, and every
check printed ok. **When you add a publication, grep for `public_url` before you trust a green
run.**

**Tags** are checked against the piece's own publication's vocabulary. The same tag id can
mean different things in two publications; neither vocabulary knows the other exists.

**The content store is shared** by every publication's sites, and it keys a record by slug
(and kind). So a slug belongs to one publication: the exporter records `publication` in the
bundle, `bundle_pieces.py` refuses (exit 9) to write one publication's piece over another's,
and `store_publish.py` refuses (exit 7) a bundle that would move a live record from one
publication to another. When two publications want the same slug, one of them sets
`site_slug:` in its manifest.

## One publication needs none of this

With no `publishing/publications.yaml`, every tool behaves as it always did: one tag
vocabulary at `publishing/tags.yaml`, and no piece is asked to name a publication. Add the
registry the day a second publication arrives, then `assign` every piece to one of them —
`publications.py check` lists the ones still to do.

## Adding a project

Make `projects/<name>/` (a README saying what it is, and a `CLAUDE.md` if it has rules of its own),
add `<name>` to its publication's `projects:`, and run `publications.py check`. A project moves
between publications only by moving it in the registry — and every piece linking into it moves
with it, which the check will list.

## Adding a publication

1. Define its outlets in `publishing/outlets.yaml`, and its platform notes beside them.
2. Add it to `publishing/publications.yaml` with the outlets it owns — moving an outlet from
   one publication to another is a decision about a live site, not a tidy-up.
3. Give it styles (`styles/<prefix>-…`, per `STYLES.md`, each `config.yaml` naming
   `publication: <id>`), its projects under `projects/`, a house file when it has a convention every
   voice keeps, and, when its pieces start carrying tags, a vocabulary:
   `tags.py define <tag> --label … --about … --publication <id>`.
4. `publications.py check` — every piece named, every outlet owned.
5. Publish one piece, then run the suite. A gate that has never seen this publication's pieces
   has never been proved to *apply* to them; the section above is what that costs.
