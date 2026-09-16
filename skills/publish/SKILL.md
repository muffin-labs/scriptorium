---
name: publish
description: Compose a finished piece as a Substack DRAFT in one pass — verify the footnotes, strip internal notes, then set title, subtitle, formatted body, images, and native footnotes — by driving the browser. Use when the user says "publish X to Substack", "load X into Substack", "put X on Substack", or wants a ready-to-review draft. For a piece already live, it re-syncs the published post SURGICALLY — changing only what actually changed (a fixed word, a casing sweep, a reworded clause) and touching nothing else. A FRESH compose produces a private DRAFT; the author says publish and this skill clicks it. A RE-SYNC of an already-published post STAGES (measured three times: the editor says Saved while the public page still serves the old text), so verify before writing AND after, against the cache-busted reader URL. Shipping a staged edit is NOT gated: click Update → Update now without asking — the decision was the edit. Only a FIRST publication needs the author. A FIRST publication SENDS the subscriber email — that is the only email a piece ever gets. Every re-sync after that sends NOTHING: the confirm dialog's text is read first, and any delivery control must be provably off or it stops and asks. Every publication also gets ONE Substack Note, posted on the author's word (step 9); posts that predate that are a backlog worked one Note per day — use this skill for "post today's note", "next note", "catch up on notes".
---

# Publish (to Substack)

Turn a finished piece into a faithful, ready-to-review Substack **draft** in one pass.
Automation composes the draft; a human reviews and clicks Publish. This replaces the slow,
glitchy char-by-char editor typing with one paste + one footnote pass.

## Preconditions

- The piece is finished (`pieces/<name>/draft.md`) and has a **manifest**
  `pieces/<name>/publish.yaml` — **`outlets`** (see below), `title`, `subtitle`, `footnotes`
  (native|endnotes|none), **`send_email` (default `true` — a first publication sends the email;
  every re-sync after it sends nothing)**, optional `cover`, optional **`post_url`**
  (record it once the piece is live; its presence switches this skill into **republish mode** —
  see below), and optional **`public_url`**.
- **`outlets:` says where the piece goes, and this skill NEVER picks one.** It is a list of
  instance-defined outlet names (`publishing/outlets.md` in the instance):

  ```yaml
  outlets:
    - substack
    - <other outlet>
  ```

  **A missing or empty `outlets:` is a STOP, not a default.** Do not publish to "the obvious
  one"; ask the author which outlets this piece is for, write the answer into the manifest, then
  continue. The set is normally settled when the piece is created (the `draft` skill asks), so an
  absent list means the question was never put — which is exactly the case where guessing is
  worst. **Publish to every outlet named, and verify each one separately.** A piece that is live
  on one outlet and missing from another is *not* published; it is half-published, and nothing
  will tell you unless you look.

  *Measured 2026-09-09:* the desk ran for weeks publishing to Substack alone while a second live
  host stood unfed, because this skill named only one destination and nothing ever compared the
  two. The piece published that morning was HTTP 200 on one host and **404 on the other**, and it
  took a hand-run `curl` to notice. (Legacy manifests may still carry `site: true` instead of an
  outlets list; treat it as the site outlet and migrate it when you touch the piece.)
- **`post_url` and `public_url` are different URLs and both are needed.** `post_url` is the
  **editor** address (`/publish/post/<id>`) that republish drives. `public_url` is the
  **canonical reader** address (`/p/<slug>`) — the only one that may appear in another essay's
  body under the in-text cross-link convention. Record both when a piece goes live: a piece that
  carried only the editor URL left a sibling essay with no correct link to reach for. Take the
  slug from the publication's archive rather than guessing it from the title.
- **In auto mode, the pane's snippet path needs its standing rule in force:**
  `python3 framework/tools/automode.py check` (exit 0). Exit 3 means missing or stale: run
  `automode.py install` on the author's yes. It writes their user settings, the only scope the
  classifier reads. A running session picks the rule up without restarting (measured). See
  *Getting a snippet into the page* below.
- **Which mode:** no `post_url` → **fresh compose** (the default flow below), browser open on a
  **fresh empty** composer (`https://<pub>.substack.com/publish/post?type=newsletter`).
  `post_url` present → **republish** (surgical re-sync), browser open on that **live post's
  editor** (`https://<pub>.substack.com/publish/post/<id>`). Either way the user is **logged
  in** — automation cannot enter credentials.
- **Transport: the `window.name` CARRIER + synthetic paste is the default on BOTH surfaces
  (2026-09-14). The real-⌘V clipboard path is a fallback, and it has a cost you must not pay by
  accident: it RAISES THE BROWSER WINDOW.**

  Eric, 2026-09-14: *"using the browser via the plugin brings it to the foreground, interrupting my
  workflow, can we fix this in the toolkit?"* — and the interruption is not only rude, **it
  corrupts the document.** Measured the same hour, composing *The Coordinates You Happen to Have*
  in Claude in Chrome: `md_to_clipboard.py --paste` raised the window into the author's typing, and
  **three characters of what he was typing — `fix` — landed as an unmarked text node at the head of
  the post's first paragraph.** Nothing reported it. The converter does not emit `fix`; only the
  fidelity digest's block-by-block comparison found it, and only because the digest was run before
  the publish click. **A real ⌘V through System Events cannot be made quiet**: macOS delivers a real
  keystroke to the frontmost app, so raising the window IS the mechanism, not a bug in the tool.
  The fix is therefore to stop needing the keystroke.

  **The carrier does not need it.** It is a synthetic `paste` ClipboardEvent on `.ProseMirror` —
  no Clipboard API, no System Events, no focus, no raise — and the snippet reaches the page through
  `window.name`, which survives a cross-origin navigation on any surface. Measured on the pane
  2026-09-10 (digest-identical compose) and in **real Chrome** 2026-09-14, where the footnote pass,
  the cover write and the tag write all went in this way with the payload's sha256 re-checked
  **inside the page** before each execution. **Use `--paste` only where System Events is the only
  way in, and say so in chat when you do.**

- **Surface: the BUILT-IN BROWSER PANE is the default for BOTH a re-sync and a fresh compose — for
  the PRIMARY Substack outlet; every other Substack outlet opens in Claude in Chrome (below).**
  Measured 2026-09-10 (Eric's preference: *"if we can publish using the built in browser instead
  of the plugin that would be preferable for the skill in general"*). The pane only ever looked
  Chrome-only because both paths need a generated snippet **inside the page** and the agent must
  never retype it; the **`window.name` carrier** below solves that, and it is surface-independent.
  Real Chrome plus the clipboard remains a working fallback, not the default. **Never switch
  transports silently: say which surface you are on.**
- **Confirm the ACCOUNT before any write — the surface decides whose byline it is.** A Substack
  login is one cookie for every `*.substack.com` publication, and **the built-in pane's cookie
  store is shared by every tab and every session** (measured 2026-09-11: a cookie set in one tab
  was present in a fresh one, and a session that never signed in found the pane signed in). So a
  desk with two Substack accounts cannot hold both in the pane — and **never sign the pane out, or
  into the other account**: that silently turns every concurrent session's work into the other
  byline's. **With more than one Substack outlet, ONE is the primary** (`substack_primary:` in
  `outlets.yaml`; Eric, 2026-09-11): the primary uses the pane for all its Substack operations, and
  every other Substack outlet opens in **Claude in Chrome**, in the browser its `chrome_browser`
  names. Change it with `substack_account.py primary <outlet>` — it refuses to demote an outlet that
  has no browser to go to, and says which sign-ins the switch needs.

  ```
  python3 framework/tools/substack_account.py route <outlet>   # the pane (primary), or which Chrome browser
  #   there, on any *.substack.com page (the editor's host is fine), run the snippet it prints
  python3 framework/tools/substack_account.py check <outlet> --surface pane|chrome --result '<its JSON, verbatim>'
  ```

  **Exit 5 is a refusal: stop** — signed in as the wrong account. Do not compose, re-sync or click
  anything there, and never switch the pane to fix it. **Exit 4** means you checked this outlet in
  the wrong browser. Exit 3 is signed out (a 401/403): the author signs in. **Exit 7** means the
  answer settles nothing — not the snippet's JSON, read on a page that is neither the outlet's nor
  Substack's, or another HTTP status: run it again on the right page, and do not send the author to
  sign in. Pass the snippet's answer as-is; never type a handle in.

  **Every snippet then checks again, itself.** `check` is one moment, and another session can
  switch the pane's login right after it. So every generated Substack script (`md_to_substack`,
  `substack_repatch` and `--structural`, `substack_sync` scan/fetch/push/images, `substack_cover`,
  `substack_captions`, `substack_tags`, `md_to_clipboard --fn-out`) opens with the **account
  guard**: in the same eval, before it reads or writes anything, it checks **the publication and
  the account** — the page's host must be the outlet's own `*.substack.com` publication, and the
  same profile fetch must answer with its `account_handle` — and otherwise returns
  `{"refused": "publication: …" | "account: …", "accountGuard": true}` (`substack_tags` throws
  instead). The publication half is there because **one account can own several publications**,
  where the byline matches and the post is still the wrong one; that half is local, so a snippet
  opened on the wrong publication stops without even a fetch. An outlet on a custom domain checks
  the account alone until `publish_host:` in outlets.yaml names its editor host — the generator
  says so when it emits one. **Treat either refusal like exit 5:** stop, and never switch the login. A generator that cannot settle the piece's outlet from its
  `outlets:` writes nothing (exit 9); `substack_account.py guard pieces/<slug>` names the account
  a piece's snippets insist on. `pane_carry.py` refuses a Substack snippet with no guard, so
  regenerate one; never hand-make it. Each snippet is **one promise-valued expression**:
  `javascript_tool` returns its value, and the `<script>` carrier assigns it to a global you
  `await` in the next call.

  **Reaching the Chrome browser:** `list_connected_browsers`, then `select_browser` the one named
  *exactly* as `chrome_browser` says (`route` prints the steps). If it isn't listed, `switch_browser`
  and give it exactly that name at the Connect prompt. Never pick one by guessing from the list, and
  ask the author before driving a browser.
- **The Claude in Chrome extension is a framework requirement, not an optional extra** — see
  *Requirements* in the framework README for install and troubleshooting. In short: extension
  **v1.0.36+**, a **direct Anthropic plan**, a session signed in with **`/login`** (an API-key or
  `setup-token` session cannot use the extension at all), and `claude --chrome`. Verify with
  `/chrome` — **Status: Enabled**, **Extension: Installed**. If the user is missing it, **say so
  and stop**; do not quietly fall back to retyping the essay.
- Publication specifics and defaults live in the **instance**, never in this framework skill.
  A desk can carry several publications, each with its own outlets: read the piece's
  `publication:` and `outlets:`, then each outlet's notes (on this framework's reference desk,
  `publishing/substack.md` holds the rules for **every** Substack outlet and a second Substack
  publication's identity sits in its own file beside it). `publications.py context <slug>` names
  the publication's **house file**; the preflight holds the draft to it as it does to the style.

## Name the session after the piece

Once you know which piece you are working on, rename the session to that piece's title, by
calling `mcp__ccd_session_mgmt__set_session_title` with `session_id: "self"` and the title. The
app's session list then reads as a shelf of pieces instead of a row of identical entries.

- **Take the title from `pieces/<slug>/publish.yaml` (`title:`), falling back to the README's
  H1.** Titles on this desk move late and often — one was retitled on Substack at publication and
  pulled back into the manifest — and `publish.yaml` is what actually ships to a reader.
- **Re-title whenever the piece changes.** A session that opens on one piece and moves to another
  should carry the name of the one it is on *now*. That is where the value is; naming it once at
  the start is the part that goes stale.
- **Best-effort, and silent when it fails.** The tool lives in the Claude Code desktop app. A
  terminal session does not have it, and there is no way to test for it except by calling. If it
  is missing, carry on — do not retry, do not mention it, and never let it block the work.
- **It will not stomp a title the author chose.** The app asks them to approve a rename over a
  title they set themselves, and replaces its own generated titles without asking. So propose
  freely; the guard is on their side of it.

## Showing the author the piece

When the author needs to *read* the piece rather than a report on it — a re-voiced draft, a
pass they have to rule on — render the house review artifact rather than pasting prose into
chat or building a page by hand:

    python3 framework/tools/review_artifact.py pieces/<slug> --out <file>

then publish that file with the **Artifact** tool, one artifact per piece, republished to the
same URL as versions land. Facts that cannot be counted go in `pieces/<slug>/review.json` —
state flags, gates, and every open question listed as a call. Contract:
`framework/docs/REVIEW-ARTIFACT.md`.

## Preflight — critique gate, verify & strip editorial notes (DO THIS FIRST)

A published draft must be **critiqued**, carry **verified** claims, and carry **zero** internal
notes. The converter enforces the last; `check_verified.py` enforces the second; you enforce the
first.

0-. **Is it even due yet?** A piece can be sealed and not due, and the manifest says so:

   ```
   python3 framework/tools/schedule.py check pieces/<name>        # exit 4 = embargoed
   ```

   **Exit 4 means compose, and do not click.** A Substack draft is private, so composing early is
   how a scheduled publication is prepared at all — but the Publish click, the store publish and
   the LinkedIn post all wait for the moment. **For Substack, set its own scheduled time to that
   moment in the composer** rather than coming back to click by hand: that is how the one email
   goes out on time whether or not anyone is at the Mac. `md_to_site.py` refuses outright
   (exit 12), so the blog cannot be published early even by accident.
   **And record the schedule once it is set** — `schedule.py record pieces/<name> --outlet <o>
   --where "…" --evidence "<post id>" --approved "<who, when>"`. A native schedule lives on the
   platform, so the desk cannot see it: without the record, `outlet_audit` cannot tell a piece
   that is scheduled from one that was forgotten, and says the same reassuring sentence either
   way. [`framework/docs/SCHEDULING.md`](../../docs/SCHEDULING.md) has the field and the rule.

0-outlets. **Can you reach every outlet this piece names? Ask BEFORE the first one goes.**

   ```
   python3 framework/tools/check_outlets.py pieces/<name>        # exit 4 = stop
   ```

   Publishing is not one act, and **the first outlet is the irreversible one** — on Substack it
   mails the subscriber list. So the moment to find out that the second outlet cannot be written
   to is before the first, not after. Measured 2026-09-13 publishing *What Holds You Here*:
   Substack went live and sent its launch email, and the site upload then failed on an **expired
   AWS SSO token**, leaving the piece live on one outlet and absent from the other — the
   half-published state this skill names as the failure to design against, discovered in the one
   order that cannot be undone. The tool proves a store-backed outlet's credentials actually work
   (an STS call, then a HEAD on the bucket), reports a browser outlet as MANUAL rather than as a
   pass, and **refuses a piece that declares no `outlets:` at all.**

0. **Run every gate in one command first:** `python3 framework/tools/gates.py pieces/<name>`
   — links, verified, scripture, quotes, CommonMark, pronouns, stage direction, refs. The
   individual tools are documented below and each is worth reading when it fires; the runner is
   what makes "I ran the checks" mean all of them. (Added 2026-09-11, after a pre-publish read
   worked down the list by hand and skipped the scripture gate while the desk held the index.)

0. **Verification gate — run it, and do not argue with it.**

   ```
   python3 framework/tools/check_verified.py pieces/<name>        # fresh compose: blocks
   python3 framework/tools/check_verified.py --resync pieces/<name>   # surgical fix: warns
   ```

   **Why this is step zero and not a footnote.** *The Knowledge of Good and Evil* went live on
   2026-08-25 carrying ~20 verbatim quotations of a named living person — on abuse, addiction and
   belief — taken from a machine-generated transcript and never checked against the audio. The
   desk had written the doubt down **three times**, in `notes.md`, in the `log/`, and under a
   README heading that still read *Anchors to verify before print*. **The compose ran anyway,
   because every existing guard read the draft and nothing read the notes about the draft** — and
   the scaffold is exactly where a careful writer puts a doubt they have not resolved yet.

   The tool **fails closed**: no clearance recorded anywhere means blocked. There is deliberately
   **no `--force`**. To clear a piece you write the clearance into `publish.yaml`, where it is
   reviewable and survives:

   ```yaml
   verified:
     date: 2026-09-02
     by: Eric
     covers: >-
       All 42 interview quotes checked against the audio; scripture loci and wording against the KJV.
   ```

   **`--resync` allows a surgical fix to an already-live post** — it introduces no new claim, and a
   gate that also blocked the corrections would mean the corpus could not be repaired until every
   ledger in it was closed, which is how a gate gets switched off for good. It still prints the open
   doubts. **A re-sync is not a clearance.**

   **What it cannot do:** it checks whether anyone *said* they checked. It cannot tell you a citation
   is correct. A green result is not a warrant.

0a. **Critique gate — a piece is critiqued before it publishes.** Publishing is the end of the
   quality loop, not a shortcut around it. Before composing a **fresh** draft (or a
   **substantive** republish — a reworded passage, a new or changed section), confirm the piece's
   `log/` records a `critique` (or `style-audit`) pass covering the **current** draft. If none —
   or if the draft has changed materially since the last recorded pass — run `critique` first and
   fold its accepted fixes into `draft.md` before continuing. Skip only on the user's **explicit**
   say-so, and note the skip in the log. (A trivial re-sync — a casing sweep, a one-word fix, a
   fixed typo — is exactly what republish mode is for and does **not** need a fresh critique.)

0b-images. **Images live with the piece, not only on Substack.**
   A piece keeps its pictures in `pieces/<name>/assets/`, referenced from `draft.md` the
   ordinary markdown way — `![alt](assets/hero.png)` — and `publish.yaml` records, under an
   `images:` block, which Substack URL each local file is already uploaded to.

   **Why the URL is recorded:** for a piece that is already live the converter emits
   `<img src="<that URL>">` instead of inlining the bytes, so a recompose **reuses the asset
   already in the post** rather than uploading a duplicate and orphaning the old one. It also
   keeps the snippet small — *For the Love of Dogs* converts to 9.7 KB this way instead of
   ~14 MB. A piece with no recorded URL still inlines, which is what performs the first upload.
   Delete a URL to force a fresh upload from the local file.

   **An image added in the Substack composer exists only on Substack**, and `draft.md` will
   not know about it, so a recompose would silently drop it. Pull it back down with
   `python3 framework/tools/sync_post_images.py pieces/<name> --apply`, which stores every
   image in the post under `assets/` and writes the `images:` block. It prefers **your original
   upload** when it can find one (Substack stores PNGs byte-for-byte, so the md5 match is
   proven rather than guessed), searching `~/Downloads` by default; failing that it keeps
   Substack's copy. Run it dry first — it changes nothing without `--apply`.

0b-cover. **The cover is a checked-in asset, not only a Substack setting.**
   A piece's hero lives at `pieces/<name>/assets/hero.png` and is recorded in `publish.yaml` as
   `cover:` plus `cover_caption:`, with dimensions and a `sha256`. **`publish.yaml` must also state
   the image's provenance — photograph or generated** — because a photorealistic hero can imply a
   real person, or re-attach a biographical reading a piece deliberately dropped. Provenance is the
   manifest's record: neither caption nor alt may *claim* a photograph or a likeness, and
   **the caption says what the image represents** — never a provenance note, never a disclaimer
   ([`ALT-TEXT.md` → Captions](../../docs/ALT-TEXT.md); the header gate warns on either). (Precedent: the generated portrait in
   `metric-space`, disclosed in the manifest and in the footnote before its gate cleared.)
   **The cover is settable from the repo, and this skill sets it** (2026-09-10). The older claim
   here — *the converter does not set the featured image, attaching it is a composer-UI action* —
   was untested rather than true, and it ended every piece with the author hunting through
   Downloads for a file the repo already had. Measured on post 214063778:

       POST /api/v1/image        {"image": "<data URI>"}  -> 200 {"id","url","imageWidth",…}
       PUT  /api/v1/drafts/<id>  {"cover_image": "<url>"} -> 200, persists on read-back

       python3 framework/tools/substack_cover.py pieces/<slug> --post <id> --out cover.js

   Carry the snippet in with `pane_carry.py` and **verify its hash in the page before executing** —
   the payload is the image itself, so a corrupted carry is a corrupted upload. The tool refuses on
   a missing `cover:`, a file the manifest names but the disk lacks, a non-image, and **a cover with
   no provenance recorded**, since a cover is the most public thing a post has. It uploads, sets
   `cover_image`, reads back, and touches nothing else — **verify the body digest afterwards
   anyway**, which is how this run proved the body was untouched.

   **`cover_image` is NOT the hero.** They are two different images and setting one is not
   setting the other: `cover_image` is the drafts-list thumbnail, the archive card, the social
   preview and the email header, and **it does not appear in the post.** The hero a reader sees on
   opening the piece is a **body** image — a `captionedImage` node at the top of the doc. The first
   version of this tool set the cover and stopped, and the author reported the image *"shows up in
   substack but not in the piece itself at the top where it should."* `substack_cover.py` now does
   both from one upload; `--cover-only` opts out of the body half.

   **The hero's caption comes from the converter now, not from this tool** (2026-09-11).
   `md_to_substack` emits every image that has a caption — `captions:` by local path, or
   `cover_caption:` for the hero (the `cover:` path, or any `hero.*`) — as
   `<figure><img><figcaption>`, and Substack's paste turns the `<figcaption>` into the
   captionedImage's caption node (measured on a TEST draft; Substack's own
   `captioned-image-container` wrapper, pasted, LOSES the caption). So a recompose keeps the
   caption instead of destroying it. A post composed before this gets its captions with
   `substack_captions.py` (in the editor, by position; it refuses on an image-count mismatch),
   and `substack_verify` compares live captions with the desk's and reports **DRIFT-CAPTION** —
   a live caption the desk does not hold included, where before it was invisible.

   **And the body half is not durable on its own.** A recompose rebuilds the body from `draft.md`,
   so an image inserted only into the live post is dropped the next time, silently. The durable form
   is `0b-images`: reference it in `draft.md` as `![alt](assets/hero.png)` **and** record the
   uploaded URL under `images:` in `publish.yaml`. Then the converter emits `<img src="<that URL>">`
   and a recompose reuses the asset rather than orphaning it — measured on this piece, **25 KB
   emitted with the mapping against ~3.4 MB without it.** The alt text is read out of the draft's
   image markdown, because the hero is a piece's most-seen image and a screen reader gets only that.

   **The alt-text rule lives in [`framework/docs/ALT-TEXT.md`](../../docs/ALT-TEXT.md)** — describe the
   image, and transcribe any text that is *in* it, in quotation marks. Read it there rather than
   reconstructing it here; what follows is the measured history that produced it.

   **Two things about hero alt text, both learned the hard way on 2026-09-10.** **(a) Transcribe any
   text that is IN the image**, in quotation marks — WCAG 1.1.1 requires text presented within an
   image to be available as text, so a sighted reader getting four phrases off the picture means a
   screen-reader user must get them too. It is not decoration and it is not optional. **(b) Alt text
   is house prose and the house sweeps govern it.** The first version of this one said *labelled*,
   against a spelling rule that names `labeled` explicitly — written into `draft.md` *after* the
   last britishism sweep had run, so nothing caught it and the author did. **Because the alt lives
   in `draft.md`, the ordinary sweeps do cover it — but only if they run again afterwards**, which
   is the standing rule that a passage written after a check does not inherit that check's clean
   bill. Re-run the sweeps after adding a hero.

   **The caption comes with the body hero.** `cover_caption:` becomes a `caption` node inside the
   `captionedImage`, so it is set in the same pass and needs no visit to the composer. (This line
   used to say the caption was the author's job — true while only `cover_image` was being set
   through the API, and stale from the moment the body half existed. It was repeated to the author
   several times after it had stopped being true.)

   **The Publish click is delegable on the author's explicit say-so** (Eric, 2026-09-10: *"we
   should fix the skill so that we just require user confirmation to go live"*). The older rule —
   *the first click is never delegated, and asking for permission does not transfer it* — is
   retired. **What replaces it is confirmation, not ceremony:** the author says publish, and this
   skill publishes.

### Email: once, on going live, and never again

**The policy, in the author's words** (Eric, 2026-09-10): *"when we go live for the first time, we
send an email. That is the only time we send an email."*

So the rule is **structural, not per-piece**:

- **A FIRST publication SENDS the email.** It is the one notification a piece ever gets, and it is
  the point of having subscribers. `should_send_email: true` on a draft about to go live is
  **correct**, not a defect to reconcile away.
- **Every re-sync, update and correction after that sends NOTHING.** A published post being fixed
  must not mail anyone. Read the *Update* dialog and prove no delivery control is enabled; if one
  is present and cannot be proven off, **stop and ask.**

**The check is symmetric, and only one half of it existed.** The update path had *prove it is off*;
the first-publication path had nothing — it asserted that publishing sends and then clicked. So a
launch whose delivery toggle happened to be off would send no email, tell nobody, and look exactly
like a success. **A silent non-send is a failure of this rule, not a safe outcome:** the piece gets
no second chance, because every path after the first sends nothing by design.

So, before a **first** publication: read the dialog's text for the delivery section, then **prove the
control is ON** — `aria-checked="true"` on the toggle, or `should_send_email: true` from
`GET /api/v1/drafts/<id>`, which is the field that actually governs it. **If it is off, or its state
cannot be determined, STOP and ask** — exactly as the update path stops when it cannot prove the
opposite. Do not toggle it silently in either direction; the author gets told which way it reads.

**`send_email:` in the manifest is a record of intent, not a switch.** No tool reads it (verified
2026-09-10) and it cannot cause or prevent an email — Substack's own control does that. Its job is
to be the thing you check the composer against: they agree, or you stop. A manifest that says
`false` on a piece about to go live for the first time is a decision to skip the launch email, and
should be confirmed with the author rather than obeyed or ignored.

**What this replaced, and why the replacement is narrower rather than looser.** The old rule was
*never click, never email*, which conflated two very different acts: going live, which the author
asks for, and mailing a list, which is irreversible. Splitting them means the click is delegable and
**the one genuinely irreversible thing still gets checked every time** — on the update path, where a
stray email would be a mistake nobody can take back.

**A correction worth carrying, because it nearly produced the wrong call.** On 2026-09-10 this skill
inferred *"this publication has never emailed"* from eight archive rows showing `email_sent_at:
null`. **The archive endpoint does not return `email_sent_at` or `should_send_email` at all** — the
nulls were absent keys read as values. **A missing field is not a `false`.** Read delivery state
from `GET /api/v1/drafts/<id>`, which does carry it, and from the dialog — never from the archive.

**Then verify on the cache-busted public URL.** *"Your post is live!"* is a claim; `substack_verify
--fresh` is the evidence. **And do not probe the contract with a 1×1 test pixel on a real
   post** — Substack renders a transparent 1×1 as a green placeholder block in the drafts list, and
   the author saw it and asked whether something was broken. Probe on the outlet's scratch draft
   (`tools/scratch_draft.py <outlet>`), or go straight to the real file.

0b-embeds. **An embed is not an image, and the image checks were blind to it.**
   An image can be made recompose-safe by putting its URL in `draft.md`, because the converter
   emits `<img>`. **No markdown emits an embed.** A YouTube embed is a `youtube2` node carrying
   a `videoId` and nothing URL-shaped, so the media scrape — which collected only URL-ish
   attributes — walked straight past it, and every check reported a clean post.

   Measured on `hollow-flute`, 2026-09-03: a YouTube embed sat at the top of a live post,
   invisible to `check-images`, to the body scrape (which excludes media), and therefore to the
   fidelity digest. A full recompose would have dropped it silently with nothing in the repo to
   rebuild it from.

   The scrape now also returns `embeds`, and `check-images` **refuses (exit 9)** while any live
   embed is unrecorded. Record each one in `publish.yaml`:

   ```yaml
   embeds:
     xNHwumRin9c: youtube2 — https://www.youtube.com/watch?v=... — top of post
   ```

   **Recording is NOT protection, and the message says so.** It makes the loss visible in
   advance; a recompose still drops the embed and it must be **re-added by hand in the composer
   afterwards.** Never resolve the refusal by deleting the embed from the post.

0b-marks. **A formatting-only edit was invisible to the entire chain — the same shape as
   0b-embeds, one layer down.** `substack_verify` and both `substack_repatch` engines compared
   READER-TEXT: tags stripped, entities unescaped, whitespace collapsed. Wrapping a word that is
   already in the post in `<em>` changes none of that, so it produced **zero diff**.

   Measured on `rising-after-falls`, 2026-09-09: after italicising *satsang* and *kirtan*, the
   regenerated surgical patch was **byte-identical in size to the previous one (29,782 bytes)**.
   The failure mode was the dangerous one — a **false pass**: the patcher reported `unchanged`
   and applied nothing, and the digest then reported **MATCH** with the italic simply not there.

   The tools now enumerate the **marked runs** — `em`, `strong`, and `link` with its href — from
   both sides and compare them for count, string and order:

   * `substack_verify` reports a formatting-only difference as **`DRIFT-MARKS`**, distinct from
     text drift, and prints a `marks` column beside `body` and `fn`. Read the kind: DRIFT means a
     word changed, DRIFT-MARKS means the words are right and the formatting is not.
   * `substack_repatch` (both engines) **applies** a missing or stray `em`/`strong` as a real
     ProseMirror mark — the block located by text, its text nodes walked to map string offsets to
     absolute positions (a block is split into several runs by its footnote anchors), the range
     **read back and asserted** to equal the exact string before `addMark` is dispatched. The
     report carries `marks: {applied, review, failed, unchanged}`.
   * **Link marks are reported, never applied.** A link mark carries Substack's own attributes;
     the safe repair is the structural engine re-inserting that block from the converter's HTML.
   * A run is a **span of formatting, not an element**: Substack serves `**a _b_ c**` back as
     three `<strong>` elements around the `<em>`, so contiguous spans of the same kind are
     coalesced before anything is compared. Skipping that reported drift on every
     bold-containing-an-italic in the corpus — 8 pieces of 34, none of them real.

   The first full sweep after this landed (2026-09-09, 34 live posts) found **7 pieces with real
   formatting drift** that every previous run had passed. The lesson is 0b-embeds' lesson again:
   **the scrape defines what can be checked, and what it does not collect cannot be verified.**

0b-anchors. **A footnote on the wrong sentence was invisible to BOTH of the above — the same
   shape again, one layer further down.** Reader-text drops the superscript digit, and the mark
   scan does not count an anchor as a mark, so **which sentence carries a note** was collected by
   nothing and therefore compared by nothing.

   Measured 2026-09-11 on `for-the-love-of-dogs`, live since 2026-08-05: the post anchored
   footnote 1 after *"It was slow. It worked."* while `draft.md` cites it after *"I stopped trying
   to frighten him."* — two paragraphs apart, a different claim carrying the note — and
   `substack_verify --fresh` reported **MATCH** every time it was run for five weeks. The only
   tool that ever saw it was `substack_repatch --structural`, and only because it refuses to patch
   a block whose footnote count it cannot align: *"the draft adds footnote(s) to block 3
   ([[FN1]]) that the live post lacks."*

   `substack_verify` now enumerates each block's anchors from both sides as an ordered list of
   **(footnote number, the words it follows)** and reports a difference as **`DRIFT-ANCHORS`**,
   a third kind beside DRIFT and DRIFT-MARKS, with an `anchors` column beside `marks`. Read the
   kind: DRIFT means a word changed, DRIFT-MARKS means the formatting is wrong, DRIFT-ANCHORS
   means the words and the formatting are right and the **note is hanging off the wrong
   sentence**. The repair is dragging the superscript in the editor — a repatch will not do it,
   and a recompose is the heavy way.

   Only blocks whose text already agrees are compared, so an anchor report never doubles a text
   report. The sweep the day it landed (2026-09-11, 36 live posts, 663 anchors) found **no other
   piece with anchor drift**.

0b-links. **Status-check the in-body cross-links:**
   `python3 framework/tools/check_links.py pieces/<name>` — exits non-zero and names any link
   that does not resolve. A cross-link URL copied out of the scaffold is **unverified by
   default**; a dead sibling slug once sat in a piece's README and DASHBOARD as its canonical
   address from the day it published, because that URL had only ever been copied and never
   followed. Fix a dead link here **and** in every scaffold file that repeats it.

0b-scripture. **Check every scripture quotation against the text, not against a memory of it:**
   `python3 framework/tools/check_loci.py pieces/<name>`
   It reads each footnote's locus, looks the verse up in the indexed KJV, and compares the
   quoted spans. **This is the one preflight step that can say a citation is WRONG** rather
   than that nobody has confirmed it — `check_verified.py` records whether anyone *said* they
   checked, and says plainly it cannot do more.

   It knows this house's conventions, because a checker that flags correct prose is worse than
   none: the King James's own `[brackets]` are supplied words and are kept, a **draft's**
   `[Them]` is the disclosed substitution and matches whatever the source has there, an
   ellipsis matches its fragments in order, and a mid-sentence start is fine.

   Read the finding kind. **RANGE** is the commonest and is not drift: the quotation runs past
   the verse the note cites (*cite 13:4-5*). **DRIFT** names the word where the quotation
   leaves the text. **SUSPECT** is a partial match, which is where a real error looks like a
   near miss — read it rather than dismissing it. **NOT IN INDEX** means the locus is not in
   this edition. A first corpus run (2026-09-10, 144 quotations) found 17 across 11 pieces.

   **The index is content and lives in the instance**, built once from a PDF the author owns:
   `framework/tools/refindex.py <kjv.pdf> --scheme kjv --out references/kjv.tsv.gz`,
   with a provenance row in that folder's README. `--verify` refuses an index with interior
   gaps, because a chapter missing a verse answers "not found" for a locus that exists, and the
   reader of that answer cannot tell which side is wrong.

0b-quotes. **Check every OTHER quotation against the source on disk:**
   `python3 framework/tools/check_quotes.py pieces/<name>`
   The same move as 0b-scripture, for books, opinions, lexicons and transcripts: it resolves
   each footnote to the reference the desk actually holds and matches the quoted spans against
   that source's index, reporting the page or line the words are on.

   **The finding that matters most is NOT HELD** — a footnote citing a source that is not in
   `references/`, whose quotations were therefore checked by *nothing*. That is
   the state in which wording gets supplied from memory, and before this tool it was invisible:
   a piece with twelve unheld quotations looked exactly like a piece with none. Bring the source
   in rather than waving it through:

       python3 framework/tools/references.py add <file> --book <book> \
           --work "<Work> — <Author> (<year>)" --edition "<provenance>" --restricted|--public

   `add` copies the file in, hashes it, writes the manifest row, **adds the .gitignore line
   before the bytes land** when it is restricted, and builds the index. An index of a
   copyrighted source is that source's text in another shape, so it is gitignored too.

   **PAGE OUT OF RANGE** is checked by CALIBRATION, not comparison: a `pages` index
   counts PDF pages while a footnote cites the printed leaf, so the tool learns the
   constant offset this source and this piece agree on and reports only the citation
   that disagrees with it. A page number is a claim a reader can follow, and it is
   invisible to a text comparison.

   **SOURCE ILLEGIBLE HERE** means the held scan's text layer is too degraded around
   that passage to compare words against — read the page by eye rather than believing
   either side.

   The other statuses: **UNMARKED ELISION** — every word is in the source and in order, but the
   quotation drops a passage without an ellipsis, so it reads as contiguous text and is not.
   **DRIFT** names the word where the quotation leaves the source. **OUT OF ORDER** — the
   fragments are all there but not in the order the ellipsis claims. **NO OVERLAP** is counted
   separately and not as a failure: an italic run in this house is as often emphasis or a title
   as a quotation. Read the count anyway — if one of those *was* meant to be a quotation, it is
   not in that source at all.

   `references.py list` says what is held and what is indexed; `references.py search "<phrase>"`
   answers *do we hold a source that says this* across every index in one call, which is the
   command to reach for instead of recalling a wording. `references.py check` proves the
   manifest, the disk, the .gitignore and the indexes agree.

   **A MATCH IS NOT A CLEAN BILL, AND A GREEN RUN IS NOT "THE FOOTNOTES ARE RIGHT."**
   On this corpus **most footnote faults are CHARACTERIZATIONS of a source, not
   misquotations** — a note saying a lexicon ranks one derivation first when it ranks
   another; a claim attributed to the writer who reported it rather than the one who
   made it a year later. Nothing mechanical can see those. Three such faults were found
   by hand on this corpus on 2026-09-11 and **not one was a misquotation.** The tool
   narrows the re-read; it does not replace it.

0b-commonmark. **Check that the markup survives a strict parser:**
   `python3 framework/tools/check_commonmark.py pieces/<name>` — must report **0 findings.**
   The desk composes Substack with its own converter, which is lenient; every other outlet
   renders the same draft through CommonMark, which is not. So a draft can be right on Substack
   and print literal markup everywhere else — and every other check here compares the draft
   against the outlet that tolerated it. Found live 2026-09-11, both reader-visible:
   `not-yet` (`Confessions*, know` — a `*` after a letter and before a comma cannot open
   emphasis) and `son-of-joseph` (ʿayin written as a backtick, which opens inline code).
   **Fix only the occurrence the parser flags.** The not-yet repair matched the same characters
   in a *correct* italic inside a verbatim footnote quotation and broke it; this check is what
   caught that. Write ʿ (U+02BF) and ʾ (U+02BE), never a backtick. `md_to_site.py` also runs it
   at export and warns without blocking, since the bundle is the whole site.


0b-commonmark. **Check that the markup survives a strict parser:**
   `python3 framework/tools/check_commonmark.py pieces/<name>` — must report **0 findings.**
   The desk composes Substack with its own converter, which is lenient; every other outlet
   renders the same draft through CommonMark, which is not. So a draft can be right on Substack
   and print literal markup everywhere else — and every other check here compares the draft
   against the outlet that tolerated it. Found live 2026-09-11, both reader-visible:
   `not-yet` (`Confessions*, know` — a `*` after a letter and before a comma cannot open
   emphasis) and `son-of-joseph` (ʿayin written as a backtick, which opens inline code).
   **Fix only the occurrence the parser flags.** The not-yet repair matched the same characters
   in a *correct* italic inside a verbatim footnote quotation and broke it; this check is what
   caught that. Write ʿ (U+02BF) and ʾ (U+02BE), never a backtick. `md_to_site.py` also runs it
   at export and warns without blocking, since the bundle is the whole site.

0b-pronouns. **Run the pronoun sweep, and justify every hit by naming who it points at:**
   `python3 framework/tools/check_pronouns.py pieces/<name> --names <the named figures> --strict`
   It lists sentence-initial forced capitals (a capital *He* silently reassigns a referent to the
   Son), every masculine pronoun and the phrases *a man*, *the man* (an imagined person is they/them;
   a real person's own pronouns stand), any lowercase *the one / someone / a mind* in a
   sentence that names God (this voice writes *the One*, *Someone*, and never lets God be a
   *what*), and any lowercase deity pronoun outside a quotation. **`--strict` refuses on those
   last two.** Added 2026-09-03 after *The Mask Comes Off Last* reached a composed draft with
   twenty-one generic masculines and a lowercase *the one* for God — both rules were in force,
   neither was in any sweep, and both were caught by the author reading the page. **A rule no
   sweep checks is a rule nobody enforces.**
   Two more sections look **inside** a scripture quotation, where the first four stop (added
   2026-09-07): **E** lists every capitalized *He / Him / His / Himself* inside an italic or
   blockquoted scripture quotation, with its sentence — justify each as the Son, or, where the
   referent is the Father, bracket the substitution (*[Them] only shalt thou serve*, the verb
   bracketed too where agreement needs it); **F** lists every lowercase *me / my / mine / myself*
   inside a quotation whose footnote cites a Gospel — the Son's own pronouns take the house
   capital in a quotation (*He that hath seen Me*), never bracketed, disclosed once per piece.
   **E and F warn and never refuse**, because each needs a human call on a referent or a speaker.
   Measured on *False Light*, 2026-09-07, four misses in one draft that no section could see:
   Matthew 4:10 *Him only shalt thou serve*, Matthew 5:45 *He maketh His sun*, John 5:30 *mine
   own self*, John 15:5 *without me* — the first caught by the author reading the page. The
   Matthew 4:10 span had no footnote ref of its own (the ref sat on an earlier span), which is why
   E also qualifies a span on King James diction alone.

0b. **Verify the footnotes.** Every footnote that quotes or characterizes a real person,
   cites a work, or pins a scriptural/textual locus must be fact-checked before composing —
   misquoting a real person in a public post is the failure to prevent. If the piece's
   anchor ledger (`README.md` / `notes.md`) isn't already closed, run a verification pass
   now (a fact-check sub-agent over the footnote claims is the fast path) and fold the
   corrections into `draft.md`. Quote only what's confirmed.

0c. **Move editorial notes out of the reader's way.** Internal "Verify X", "attribute
   carefully", "todo" notes must not publish. The convention (auto-stripped by the
   converter): put them **after a dagger `†`** inside the footnote, or inside an HTML
   comment `<!-- … -->`. Both are dropped at convert time.

   **The converter enforces this two ways, and the second is the one that matters.** It refuses
   if a footnote still contains "verify" *after* cleaning (a note someone forgot to put behind a
   dagger), **and it refuses if a `†` note it stripped reads like an unverified-claim marker** —
   `verify/todo/tk/check/confirm/pin/source/cite` — naming each one. That second guard was added
   2026-08-29 after the first was found to be structurally inert: the convention is to put verify
   notes behind a `†`, which strips them *before* the first guard looks, so a well-formed note
   always passed. **A draft carrying 17 unverified anchors converted clean and exited 0.** Four
   of those anchors were later found to be factually wrong, three of them misquotations of named
   translators.

   **A `†` marker means the claim is unverified.** Clear it by verifying the claim, not by
   deleting the marker, and never reach for `--allow-verify` / `--allow-unverified` to silence a
   real one.

0c-clearance. **Clearance language is scaffold too, and the converter refuses it.** A footnote that
   says the checking was *done* — *(both consulted 2026-09-07)*, *checked 2026-09-02 against …*, a
   bare ISO date — is the desk's verification record reaching the reader. Its place is
   `publish.yaml` → `verified:`; the footnote carries the citation and nothing about the checking.
   Found 2026-09-07 on *The Towel*: eight loans were cleared with sources written into the footnotes,
   one of them carried its access date along, every guard read it as clean (a note that says the
   verifying is finished contains no *verify*), and the author caught it in the composer. The
   converter now refuses on an ISO date anywhere in the reader text, and on *consulted / accessed /
   retrieved* followed by a date, in both transports and in the suite's corpus check. Date a source
   the way a reader expects — *(2002)*, *March 10, 1967* — and put the day you checked it in the
   manifest.

0d. **Header gate — the post has a title AND a subtitle.** The converter (and therefore the
   clipboard tool) **refuses with exit 6** when `publish.yaml` has an empty `title` or
   `subtitle`, and there is no override: add the line. The subtitle is not decoration — it is
   the second line of every archive card, the homepage listing, the social preview and the
   email header, and **the composer accepts an empty one without a murmur.** Found 2026-09-03:
   a post had been live since 2026-08-05 with no subtitle at all, and nothing in the pipeline
   had ever looked, because every check compared *body* blocks and the header is not in the
   body. A `title`/`subtitle` whose trailing comment still says *PROPOSED* / *working title* /
   *not yet settled* **warns rather than refuses** — a private draft is where the author reviews
   it — but say so in chat, because that one line is the part of the post the author is least
   likely to re-read in the editor. Once they sign off, replace the comment with *settled
   <date>* so the suite's note goes quiet. The offline half of this guard runs in
   `test_suite.py` (`corpus_manifests`); the online half is `substack_verify.py --archive`
   (below), which reads the **publication's** list rather than the repo's and is the only check
   that can see a post the desk never composed.

0d-captions. **Caption gate — every figure the draft shows must carry a caption, and this
   one is HARD at publish.**

   ```
   python3 framework/tools/check_captions.py pieces/<name>        # exit 3 = stop
   ```

   An instance can rule that a caption is a **default, not a per-figure choice**; this one did,
   in 2026-09-11, and `check_captions.py` is what reads that rule. Alt text and a caption are two
   different jobs: the alt is what a reader who cannot see the picture gets, the caption is what
   the sighted skimmer gets, and it says what the figure **means** rather than what it shows. A
   drafting pass that writes the alt and stops leaves the skimmer nothing.

   **Why it is a gate and not a line in a style file: it already was a line in a style file.**
   Measured 2026-09-14 — a piece was drafted, critiqued, gated nine ways, cleared, composed and
   published **to three outlets** with three of its four figures carrying no caption. Every gate
   was green the whole way, because none of them was looking, and a human caught it after it was
   public on three hosts. Same shape as the pronoun and
   britishism rules before they had sweeps: **a rule no sweep checks is a rule nobody enforces.**

   Captions live in `publish.yaml` — `captions:` keyed by the path the draft gives each image,
   `cover_caption:` for the hero — **never as an italic line under the image in `draft.md`**,
   which publishes as an ordinary paragraph. `gates.py` runs this as a WARNING, because 22 pieces
   that published before the rule existed still carry an uncaptioned hero and a gate that fails
   the whole corpus on day one is a gate somebody switches off. Here it is a stop.

0e. **Tags gate — a piece publishes with its tags, so ask if it has none.** Run
   `python3 framework/tools/tags.py show <slug>`. A piece with **no tags** warns rather than
   refuses (tags are not a correctness property of the post), but say so in chat and offer the
   `tags` skill's Mode 2 before composing: once a piece is live, tagging it means a public edit
   on every outlet that carries tags. A tag the vocabulary does not define is not a warning —
   `tags.py check` fails, and `md_to_site.py` refuses to export it.

0f. **Does its publication require a companion?** A Note is posted the day a piece goes live, and
   a publication can require one of every published piece (`required_companions:` in
   `publishing/publications.yaml`; MuffinLabs requires a Note).

   ```
   python3 framework/tools/companions.py list <slug>      # what it declares, and whether it resolves
   ```

   **Say so before composing, not after publishing.** The corpus gate only fires once the piece is
   live — which is the morning the Note is due, and the worst moment to write one. A required Note
   missing here is a stop-and-ask, and the answer is either a `note.md` written with the piece or an
   exemption with a reason (`companions_exempt: {note: "<why>"}`).
   [`framework/docs/COMPANIONS.md`](../../docs/COMPANIONS.md) has the rule.

## Steps — composing the body

**Two transports, and the choice is the surface, not the quality.** On the **built-in pane**
(the default) carry `md_to_substack.py`'s snippet in with `pane_carry.py` and let its synthetic
paste do the work — measured 2026-09-10, digest-identical to the draft. On **real Chrome** use
the system clipboard and a real ⌘V, described below. **Both are safe for the same reason and it
is the only reason that matters: neither one routes the author's prose through the agent.**

> **Never retype the essay.** The older JS-snippet path bakes the whole piece into a string
> literal, so driving it means the agent reproducing every byte of the author's prose into a
> `javascript_exec` call — ~37KB for a 5,700-word essay. **That makes the agent's transcription
> the weakest link in the chain:** one wrong character diffs as a real edit and can publish a
> typo in the author's voice, and no downstream guard can see it, because to a guard a typo is
> just another edit. The clipboard removes the agent from the transport: the bytes go
> **disk → system pasteboard → Chrome → ProseMirror** and are never retyped.

**These measurements are about the CLIPBOARD, not about the pane.** Measured 2026-09-01:

| surface | result *with the pasteboard transport* |
|---|---|
| in-app browser pane + `navigator.clipboard.read()` | ❌ `NotAllowedError: Document is not focused` |
| in-app browser pane + synthetic `cmd+v` | ❌ no-op, editor stays empty |
| **real Chrome + real click + real `cmd+v`** | ✅ **works** — `h2`, `em`, `strong`, links, blockquotes all survive |

**The conclusion is that the pane cannot reach the pasteboard — which is why the pane uses
`pane_carry.py` instead, not why you should leave the pane.** A programmatic `.focus()` does not
satisfy the Clipboard API, so on real Chrome the click has to be a real one.

> **This block used to end "So compose in real Chrome, not the in-app pane," and that sentence
> outlived the change that made the pane the default.** It cost a session most of a day on
> 2026-09-10: the agent read *these* lines rather than the Surface bullet 260 lines above, drove
> real Chrome, found the window minimized (a hidden zero-size viewport swallows a ⌘V silently),
> cleared a composed draft to empty before discovering it, and then lost the signed-in tab
> altogether — while the pane was signed in the whole time and a two-word surgical fix through it
> took one call. **A skill that says the default in one place and contradicts it in the numbered
> steps will be obeyed by the numbered steps.** When the default moves, grep the whole file for the
> old one.

1. **DEFAULT — carry the converter's snippet in and let it paste synthetically.** Generate with
   `md_to_substack.py`, deliver with `pane_carry.py`, re-hash **in the page**, execute. Full recipe
   in *Getting a snippet into the page* below; it works on the pane and in real Chrome alike, and
   **it never raises the window.** Skip to step 2.

   **FALLBACK — the pasteboard and a real ⌘V, which RAISES THE BROWSER WINDOW** (default from
   2026-09-08 to 2026-09-14; see the Transport bullet for what that cost):

   ```
   python3 framework/tools/md_to_clipboard.py pieces/<name> --paste --expect-url publish/post/<id> --fn-b64 <fn.b64> --fn-out <fn.js>
   ```

   after a **real click** into the body (step 3 below happens first — the click gives the editor
   focus; the tool gives the keystroke). It acquires the **`pasteboard` lease** (`lease.py`,
   waiting up to 120s for another session to finish, then stopping and naming the holder — it
   never breaks a lease), runs the same converter and therefore the **same refusals** (a stray
   "verify", nested footnote refs, undefined/duplicated markers), places the HTML flavor, **reads
   it back off the pasteboard and hashes it**, locates the Chrome tab whose URL contains
   `--expect-url`, makes it the active tab of the frontmost window, **reads the active tab's URL
   back and refuses if it does not match**, re-reads the board one last time, sends a **real ⌘V
   through System Events**, and releases the lease. The pasteboard is exposed for the milliseconds
   of the keystroke, not for a tool round-trip.

   **Why this replaced the two-step.** The pasteboard is global mutable state. Until 2026-09-02 the
   tool checked only that "HTML" appeared in `clipboard info`; **it reported a clean write while the
   board held another piece's footnote snippet**, which pasted into a fresh post. The read-back fixed
   that, and `--verify` immediately before the ⌘V was added — and on 2026-09-07 **one session still
   lost the board three times in an afternoon** (a stranger's name and an `assetError` node; a stray
   quotation; a re-check seconds before a paste found another session's whole essay). Every taker was
   another Claude session composing. So: a lease, because the takers all run this tool; and one
   process, because the gap `--verify` guarded was a full round-trip. **Needs Accessibility
   permission** for the app running the tool (System Settings → Privacy & Security →
   Accessibility); without it the tool stops at `not allowed to send keystrokes (1002)` with nothing
   pasted and the lease released. **Say so and stop; do not fall back to retyping.**

   **The two-step still exists and is still lease-guarded:** run without `--paste` to load and hold
   the lease, `--verify` immediately before a ⌘V sent from the browser tool, then `--release`. Use it
   only where System Events cannot reach the browser.
2. **Open the composer on the outlet's surface — the pane for the primary, Claude in Chrome for any
   other (`substack_account.py route`) — confirmed by `substack_account.py check`** — and set Title + Subtitle by JS (small, no prose in it),
   then `clearContent(true)` so a retry can't append to a half-paste. **Snapshot any image or embed
   the live doc holds FIRST** (see 0b-images / 0b-embeds); `clearContent` removes them, and an
   `undo` is a rescue, not a plan (measured 2026-09-07: a hero added in the composer was cleared
   before it was read; `undo` brought it back that time).
3. **Body:** carry the converter's snippet in and execute it (step 1's default) — no click and no
   window raise. On the `--paste` fallback only, a **real click** into the body first. Either way
   formatting, links and dividers arrive intact and footnote refs remain as `[[FNn]]` markers.

   **Then count the top nodes against the converter's own counts before going on.** That is what
   catches a stray keystroke that arrived while the window was raised, and it is cheap.
   **Substack applies smart-quote input rules on paste** (`'`→`’`, `"`→`“ ”`), so the live text
   will differ from the draft at every apostrophe — that is expected, it is what the whole
   corpus published with, and step 6's digest must account for it rather than treat it as
   corruption.
4. **Footnotes:** run the `--fn-out` snippet. It turns every `[[FNn]]` marker into a **native**
   Substack footnote via Tiptap's `insertFootnote` and fills each note's rich content. Returns
   `{inserted, missing}` — **`missing` must be empty.** Markers are keyed on the footnote's
   **name**, not a number (`[[FNbeelzebul]]`), so grep for `\[\[FN[a-z0-9]+\]\]`.

   **Getting the snippet into the page, measured 2026-09-02.** It carries the author's footnote
   prose, so retyping it into an eval is the same transcription risk the clipboard exists to
   remove — and two obvious alternatives do **not** work on this surface: both
   `navigator.clipboard.readText()` and a `fetch()` to a CORS-enabled `http://127.0.0.1`
   **hang and time out the CDP call at 45s**, with the renderer alive and responsive afterwards
   and no permission prompt on screen. **What does work:** base64 the footnote data (`--fn-b64` writes it), put the cursor in an EMPTY
   TOP-LEVEL paragraph between the body and the footnotes (`splitBlock` at the end of the last body
   node — not `focus('end')`, which lands INSIDE the last footnote), and paste it as text with the
   same lease-guarded one-process tool: `md_to_clipboard.py --text-file <fn.b64> --paste
   --expect-url publish/post/<id>` (base64's charset is immune to the smart-quote input rules that
   would corrupt raw JSON). Read it back out of the DOM with `atob`, **checksum it against the
   file**, delete the carrier node, then insert. **Insert in batches of ~8–9** — thirty-five in one call also exceeds the 45s
   timeout. Prove the transfer with a checksum computed on both sides before inserting anything.
   **Two failures measured on this path, 2026-09-10, and both are silent.**
   **(a) `--paste` raises the window but does not put the caret in the editor.** It reported
   *"pasted body … the lease is released"* into a document that stayed empty — the report is a claim
   about the keystroke, not evidence about the doc (`hasFocus:false`, `editorFocused:false` on the
   page afterwards). **Always a real coordinate click into the body first**, then the ⌘V, then the
   count check. **(b) A carrier ⌘V that appears to have failed may have landed in the wrong place.**
   One went into the *middle of a paragraph*, splitting it mid-word and burying 8,796 characters
   inside the remainder, with no error anywhere; a top-node count of 80 against an expected 79 was
   the only tell. **Check the node count against the converter's, not just the marker count.**

   **And when you strip a base64 carrier back out of prose, bound the match by the payload's known
   length — never by charset greed.** `/^[A-Za-z0-9+/=]{4000,}/` removed 8,797 characters instead of
   8,796, because **`e` is a base64 character**: it ate the *e* of *"a long time"* and left *"a long
   tim taking pictures down"* mid-essay. Use `text.slice(0, text.length - knownB64Len)`, or splice at
   the exact count. **That is a transcription-class corruption introduced by a repair — the precise
   class this whole transport exists to prevent — and no contraction, link or pronoun sweep can see
   it. Only the fidelity digest can.**

5. **Post-check (JS):** title/subtitle set · block counts match · **0 empty paragraphs** ·
   heading/divider/image counts · footnotes == manifest count · **0 `[[FN` markers left** ·
   in-body sibling links present. Report the numbers; don't say "done" without them.
6. **Fidelity check — do this, it is the whole point.** **Read a mismatch before repairing it.**
   An intermediate run mismatched on exactly the blocks carrying `[[FN]]` markers — the live text
   still held them while `render_reader` strips them, so the mismatch was *expected at that point*
   rather than damage, and treating it as damage would have caused a second, needless repair. Run the
   digest **after** the footnotes are in; if it mismatches before that, check whether the differing
   blocks are precisely the marker-bearing ones. Hash every live block's flattened text,
   digest the list, and compare against the same digest computed from `draft.md` via
   `render_reader`. **The two digests must be identical.** A clipboard paste cannot introduce a
   transcription error, so this is cheap and should pass first time; if it does *not*, something
   else moved (a concurrent edit to the draft, a Substack-side input rule) and that is worth
   knowing before a human publishes.
7. **Hand off:** the draft is composed. Tell the user to review it in Substack, and **on their
   word, click Publish.** The click is delegable; the *decision* is not, and it is theirs to make on
   a draft they have read. **A first publication SENDS the subscriber email, and that is correct** —
   it is the one notification the piece will ever get. Say so plainly before clicking, so nobody
   learns it from the send. *(Shipping a later **edit** to an already-published post is a different
   act with a different rule — see Republish step 5; that path sends nothing.)*

8. **Set the cover. This is a STEP, not an option, and it runs AFTER the publish click.**
   A post with no `cover_image` has no drafts-list thumbnail, no archive card and no social
   preview: the piece looks unfinished everywhere it is listed, and nothing in the pipeline
   notices, because every other check reads the body. It was the last thing the author had to
   remember, and it should not be.

       python3 framework/tools/substack_cover.py pieces/<slug> --post <id> --cover-only --out cover.js

   **The ordering IS the step, and getting it wrong blocks the publish.** The tool writes through
   the drafts API, and the API is a second editor: run it while the composer holds the document and
   Substack refuses to publish — *"Draft not saved — Post out of date"* — and the cover reverts to
   `null` when the editor writes its own state back (measured 2026-09-10 on
   `what-was-already-there`, which sat one stale copy from being unpublishable). So run it **after
   publishing**, on the share-center page Substack redirects to, with the composer closed. **Assert
   `document.querySelector('.ProseMirror')` is null before writing.**
   `substack_cover.py --cover-only` now says so when it prints its instruction: a non-editor page
   of the publication (`/publish/posts`, `/publish/home`), no composer open on the post. It
   used to say *run it in the post's editor* whatever the mode.

   `--cover-only` whenever `draft.md` already references the hero, or the tool inserts a second
   copy in the body. **It reuses an asset already recorded in `publish.yaml`'s `images:` block
   instead of uploading a duplicate** — 2,588 bytes of snippet against 2,580,143 for the same
   image. Carry it with `pane_carry.py`: it is small, but it carries the author's caption and alt.

   **Then run `substack_verify --fresh` anyway.** A cover write should touch nothing else; that is
   a claim, and this is the cheap check that it held.

8b. **Put the tags on the post — after the publish click, from `/publish/home`.** The desk's tags
   are part of the piece the author approved, so the yes to publish covers them; a post that goes
   live untagged on Substack is missing from every `/t/<tag>` archive page it belongs on.

       python3 framework/tools/substack_tags.py pieces/<slug> --live --dry-run --out tags-dry.js
       python3 framework/tools/substack_tags.py pieces/<slug> --live --out tags.js
       python3 framework/tools/substack_tags.py pieces/<slug> --verify

   Run the dry run first and read its diff (on a fresh post: attach every tag, detach nothing),
   then the real one, on a non-editor page — the snippet refuses the editor holding the post, the
   same rule as the cover. Both carry a checksum of their plan; carry them with `pane_carry.py`
   or paste them exactly as generated. `--verify` reads the public post and fails on a tag
   missing or extra. **Tags changed later on a live piece** are the same three commands, and the
   author's word on the tag change is the word for the sync.

9. **Post the Note: one per publication, the day it goes live.** A Substack Note is the feed's
   short-form post. Every live post gets exactly one, announcing it. `substack_notes.py` holds
   the state and the checks; posting happens in the browser, on the author's word.

   1. **Write the piece's `note` companion** ([`COMPANIONS.md`](../../docs/COMPANIONS.md)):
      `pieces/<slug>/note.md`, declared as `companions:` / `note: note.md` in `publish.yaml`,
      under a header naming its form and voice (`form: note` or `form: poem`, `style: <voice>`,
      closed by `---`). A prose Note is one to three short paragraphs (the piece's own best
      lines, lifted verbatim, are usually right); a poem is lines and stanzas. Plain text, **no
      URL**: the tool appends the post's public URL as the last paragraph, and the composer
      turns that bare URL into the post's card by itself. A poem goes one paragraph per line
      with an empty paragraph between stanzas — the Notes editor has no line-break node
      (measured 2026-09-11). **A posted Note strips whitespace-only paragraphs**, so the gap
      between stanzas is a marker line, `stanza_break:` in the header — `braille` (U+2800, looks
      empty; default), `dot` ("·"), or `none` ([`COMPANIONS.md`](../../docs/COMPANIONS.md)). Read
      the posted Note on the feed to confirm the gaps held.
   2. **Show it to the author and get a yes that names the Note.** A Note is public the moment
      Post is clicked. The yes to publish the post does not cover it: ask for both in one line
      if that's convenient, but ask.
   3. **Open the Notes composer** (*What's on your mind?* at the top of the Substack home feed)
      and fill it from disk:

          python3 framework/tools/substack_notes.py text <slug>

      prints `paragraphs`, `sha256` and `js`. Run the `js` in the page. It refuses unless exactly
      one **visible** composer is open and empty. Substack keeps a hidden `[role=dialog]` in the
      DOM after the composer closes, so "the dialog" is not a selector. It returns
      `{sha256, card, postEnabled}`: **the sha256 must equal the tool's**, `card` must be true
      (the post's card rendered), and Post must be enabled. On any miss, stop.
   4. **Click Post — or, for a SCHEDULED publication, arm a task to post it after the post is
      live.** That is the house default (Eric, 2026-09-11), and the reason is measured: **Know what scheduling costs
      first:** a Note composed before its post is live shows *"This attachment is not available"*
      where the card belongs — Substack will not attach an unpublished post, even though the
      scheduled post's URL already resolves to a teaser with full `og:` tags (measured
      2026-09-11). So a scheduled Note carries a **plain link**; a Note posted after the post is
      live carries the **card**.

      **AND THE COST IS PERMANENT — measured 2026-09-14 on a Note two days old whose post had
      been live the whole time.** The card is not a render-time lookup of the URL: it is a
      STORED ATTACHMENT written when the Note is composed. A Note composed before its post was
      public has `attachments: []` on `/api/v1/reader/comment/<id>`, and it stays empty forever.
      Nothing backfills it, Substack does not let a posted Note be edited, and the only way to
      get the card is a different Note. **So this is not a cosmetic difference to be weighed
      lightly: scheduling the Note spends the card for the life of the post.** Prefer the task
      below; reach for the composer's Schedule only when the author has been told that, in those
      words, and still wants it.

      `substack_notes.py task <slug> --post-url <url> --at "<moment>"` prints the self-contained
      prompt for that task — every guard in it is there because a scheduled session has nobody
      watching: the post must serve its BODY (not the scheduled-post teaser), no Note may already
      be recorded, the composer's sha256 must equal the tool's, and **`card` must be true**.
      Create the task for a few minutes after the post's moment, then
      `schedule.py record <piece> --outlet note --where "Claude app task <id>" --approved "…"`.
      `substack_notes.py text <slug> --post-url <url>` still builds the plain-link version, for
      an author who would rather schedule the Note than have a session wake up.
      [`framework/docs/SCHEDULING.md`](../../docs/SCHEDULING.md) has the table of guards. A Note announces a post, so it
      goes when the post goes. If the piece is due later (`schedule.py check` says EMBARGOED and
      its Substack outlet is `at_moment`), use the composer's **Schedule** for the same moment
      rather than posting now: a Note announcing a post nobody can read yet is the one way to get
      this wrong. Then record it —
      `schedule.py record pieces/<slug> --outlet <substack outlet> --where "the Notes composer's
      own scheduler" --approved "<who, when>"` — because nothing on this side can see a schedule
      that lives on Substack's. *(This line used to read "never use Schedule unless the author
      asks for it", which was right when every publication went out the moment it was composed.)*
   5. **Record, then verify.** `substack_notes.py record <slug>` takes the Note's id from the
      public feed (exactly one Note must name the post, or it writes nothing) and adds a
      `substack_note:` block to `publish.yaml`. Then `substack_notes.py verify <slug>`. Commit
      the manifest and `note.md` with the publication.

   **The backlog: one a day.** Posts that went live before this step existed have no Note. The
   backlog is derived, not queued: every live post with no `substack_note:` block, oldest first.
   It is worked **one per calendar day**. `substack_notes.py next` names today's post, and exits 3
   once today's backlog Note is recorded. A fresh publication's own Note does not use the day's
   slot. Triggers: *"post today's note"*, *"next note"*, *"catch up on notes"*. Same steps 1–5.
   `verify` with no slug checks every recorded Note, and flags any Note naming a post that the
   desk has no record of as `UNRECORDED`. Record that Note; never post a second one.

   **Notes belong to a PROFILE, and each outlet has its own.** `notes_profile_id` /
   `notes_handle` / `notes_probe_draft_id` are read from the piece's **own** Substack outlet, and
   `verify` groups the corpus by outlet and reads each profile's feed — so a two-publication desk
   is swept in one run. Until 2026-09-11 both the corpus and the profile were hard-coded to the
   `substack` outlet, which is two errors that compound: the second publication's posts were not
   in the backlog at all, and had one been checked it would have been checked against the **first
   publication's feed** — reporting a real Note as `MISSING` and an absent one as fine. An outlet
   with no profile id recorded now reports `UNREAD` with its pieces counted, rather than passing
   silently; `probe --outlet <name>` prints that outlet's own probe draft.

### The JS-snippet path — the DEFAULT on both surfaces (2026-09-14)

`md_to_substack.py` emits a self-contained snippet that sets title and subtitle and pastes the
body as a synthetic ProseMirror paste. **Deliver it with `pane_carry.py`, never by retyping it
into an eval** — the transcription warning above is about *delivery*, and it is the whole of the
objection to this path. Delivered by carrier it is digest-identical to the clipboard route
(measured 2026-09-10) and it is now the **default on both surfaces** — on Chrome too, because the
clipboard route's real ⌘V raises the author's window and a raised window takes their keystrokes
into the document (Transport bullet, 2026-09-14). Verify with step 6 either way, without exception.

1. **Convert:** `python3 framework/tools/md_to_substack.py pieces/<name> <out.js>`
2. **Focus** the composer body (click into it).
3. **Call A — body:** run the whole snippet via the browser's JS eval (sets Title + Subtitle,
   pastes the body as one synthetic ProseMirror paste; images inlined as `data:` URIs →
   Substack uploads them to its CDN).
4. **Call B — footnotes:** `await window.__sbInsertFootnotes()`; `missing` must be empty. It is
   its own eval, so it runs the account guard again before touching the document.
5-7. As above.

## Getting a snippet into the page — the `window.name` carrier (pane transport)

Every JS path below (surgical repatch, structural repatch, the footnote pass) needs an
80–125 KB generated snippet **inside the page**. The agent must never retype it: that is the
transcription risk the whole transport chapter exists to remove. Use this on **both** surfaces. It was written for the
pane (measured 2026-09-10 on two live posts) and was used in real Chrome on 2026-09-14 for a
footnote pass, a cover write and a tag write; the clipboard alternative is what raises the window.

**A snippet that is a MODULE needs a module loader, not an injected `<script>`.** `substack_tags.py`
(and anything else ending in a bare last-expression value with top-level `await`) will not run as a
classic script: top-level `await` is a module-only feature, so the injected script throws or
silently yields `undefined`. Import the carried text as a blob module and append ONE line to hand
the value back — the carried bytes themselves stay untouched, so the hash you verified is still the
code that ran:

    const url = URL.createObjectURL(new Blob([payload.text + "\nwindow.__out = result;\n"],
                                             {type: 'text/javascript'}));
    await import(url); URL.revokeObjectURL(url);
    return window.__out;

**Every network route into the page is shut, and no response header opens one:**

| route, from the https editor page | result |
|---|---|
| `fetch('http://127.0.0.1:<port>/…')` | ❌ `TypeError: Failed to fetch` |
| `<script src="http://127.0.0.1:<port>/…">` | ❌ `onerror` |
| `window.open(...)` + `postMessage` to opener | ❌ the pane **navigates the current tab**; no popup, no opener |

**Neither of the first two reaches the server** — the access log stays empty — so the pane blocks
http subresources from an https document, client-side. Both were tried with correct CORS *and*
`Access-Control-Allow-Private-Network: true` for Chrome's PNA preflight. **Do not debug the
server.** Substack is not the obstacle either: its only CSP is `frame-ancestors`, with no
`connect-src` and no `script-src`, which is why inline execution works once the bytes are in.

**What works: `window.name` survives a cross-origin top-level navigation.**

```
python3 framework/tools/pane_carry.py <snippet-path>
```

It writes the carrier page next to the snippet, serves both on a **session-derived port that
fails loudly rather than sharing**, and prints the carry URL and the payload's **sha256**. Then:

1. Navigate the pane tab to the printed **carry URL**. That page is *same-origin* with the file,
   so its own `fetch` is fine; it writes `JSON.stringify({file, hash, text})` into `window.name`.
2. Navigate the **same tab** to the post editor. `window.name` crosses intact (measured at
   **127,994 chars**).
3. **Re-hash in the page and compare to the printed sha256 before arming the payload.** Not
   ceremony: *a port is not an identity; identify the bytes at the point of use.* It is what makes
   an unauthenticated localhost hop safe, and it is the step someone will be tempted to skip.
4. Execute by appending an inline `<script>` whose `textContent` is the verified payload,
   assigning the snippet's result to a global you read next. **Steps 3 and 4 are ONE
   `javascript_tool` call:** check the page is the editor, re-hash, `throw` on a mismatch, and only
   then inject. The hash gate is in front of execution because it is in the same call.

**In auto mode the classifier decides, and it has decided both ways.** It refuses a bare `eval`
of an opaque variable, and that refusal is correct. It **refused the script-element form too**, on
a live post on 2026-09-10. On 2026-09-11 it **allowed** the same form on a no-op re-sync of *Son
of Joseph*, with no standing rule loaded: the author had asked for the run in that session, and
the one call checked the page, re-hashed, and threw before injecting. (Hash matched in the page,
`stagedEdits: 0`, the button **Continue**/disabled before and after, `substack_verify --fresh`
MATCH 80/80, 36/36, 138/138.) **That allow was the classifier's judgment, not a permission.**
Do not count on it next time.

**A standing `autoMode.allow` rule only works in USER scope.** The classifier ignores `autoMode`
in `.claude/settings.json` **and** `.claude/settings.local.json`, by design: both live in the
repo, and a repo must not grant itself allowances. A rule placed there is inert. It has to go in
`~/.claude/settings.json`, and **`python3 framework/tools/automode.py install`** puts it there:
it builds the rule from this desk's Substack outlets in `outlets.yaml`, and re-running it replaces
only its own entry. It writes the author's user settings, so it runs on the author's yes, once per
machine. **`automode.py check`** reads `claude auto-mode config`, the rules actually in force,
not a settings file. (Measured 2026-09-11: a rule in `settings.local.json` did not appear in
`auto-mode config`.) **The rule takes effect at once, in sessions that predate it** — measured
2026-09-11 in a session that had been running for hours before `install` ran, and had been
refused twice that afternoon: `check` reported it in force, and the same no-op re-sync of *Son of
Joseph* was then allowed (`stagedEdits: 0`, `failed: []`, marks unchanged 116, **Continue**
disabled before and after, `substack_verify --fresh` MATCH). So nobody has to restart a session
to pick it up. **If the
classifier refuses, stop and tell the author.** Do not go looking for a way around the refusal:
a standing rule is the author's authorization to give, and a workaround would be the agent
granting itself one.

Don't hand-write the carrier page: a transport that is reassembled from memory each time is a
transport whose hash check eventually goes missing.

**PROBE THE SERVER IMMEDIATELY BEFORE EVERY CARRY. This is not belt-and-braces; it is the step
whose absence invents facts about the destination.** `pane_carry.py` is reaped when the shell that
started it ends, and a dead server makes `carry.html` fetch nothing and set `window.name` to
nothing — which, read from inside the destination page, is **indistinguishable from a page that
wipes `window.name`**. Measured 2026-09-14 publishing to LinkedIn: three carries in a row came back
as 0 chars and produced a confident, written-down, entirely false finding ("LinkedIn's article
editor clears `window.name` at any size", with a ceiling apparently between 19 KB and 3.5 KB). With
the server verified up, **2.54 MB carried through the same navigation into the same editor** and
read back with its hash matching. One `curl` would have prevented all of it:

    curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<port>/<file>   # expect 200

The port rule already says to hash the bytes that came back; extend it by one notch — **check that
any bytes came back at all.** And when a carry fails, suspect the helper before the remote system:
a localhost process that dies silently produces failures shaped exactly like the remote's behaviour.

### LinkedIn Articles — what is true about images, measured 2026-09-14

The Article editor is Tiptap/ProseMirror at `/article/edit/<id>/`, so the carrier and the synthetic
paste work there unchanged. Its schema names are its own: `inlineImage` (attrs `src`, `alt`, `urn`),
wrapped by `figureImage` with a `figcaption`, plus an `imagePlaceholder` used during upload.

- **An external `src` does NOT survive a save.** Four `inlineImage` nodes pointed at an already-live
  CDN rendered correctly in the editor and were **gone after a reload**. LinkedIn keeps only assets
  it hosts, so "reference the URL you already uploaded" — which is right for Substack — is wrong here.
- **Paste the `data:` URI; that is the path that works.** A synthetic `paste` of
  `<img src="data:…">` at the slot becomes an `imagePlaceholder`, LinkedIn uploads it, and it
  resolves to a `figureImage` that survives a reload. **`insertContentAt` with the same HTML inserts
  nothing and reports success** — count the nodes, never trust the report.
- **`md_to_linkedin.py` DOES emit a slot per figure**, reading `[Figure N — upload here] <alt>`.
  A slot carries its whole alt text, so it is **hundreds of characters long**; a search that filters
  for short paragraphs will not find it and will conclude there are no slots. Delete the slot
  paragraph after its figure is in, and assert zero `[Figure … upload here]` remain.
- **The paste drops the alt**, so set it afterwards on the inner `inlineImage` — and only after
  asserting each figure sits before its own anchor paragraph, or a misplaced figure gets the right
  alt and looks correct.
- **A LinkedIn figcaption saves ONE PER PAGE LOAD. Set one, Update, reload, repeat.**
  Measured 2026-09-14 re-syncing four captions onto a live Article: setting all four in one pass
  left the editor showing all four and **only one survived the save** — and it was the first one
  written in that page's life, not the last. A second pass set three more, and again only the first
  of them persisted. The editor's own read-back is NOT evidence here: the doc had all four every
  time. **Verify on the public page, count the `publishing-image-block-caption` nodes, and expect
  to do one load-set-Update cycle per figure.** Four captions cost four cycles.

- **The announcing-post field in the publish dialog is a QUILL editor** (`.ql-editor`), not Tiptap.
  A synthetic paste leaves it empty. Focus it, select its contents, and
  `document.execCommand('insertText', false, text)`. Then **read it back and hash it against
  `linkedin-post.md`** before clicking Publish: the outlet rule is that the author approves the
  exact text, so the exact text is what has to be proven present.

### The measurement, so nobody has to repeat it

**Fresh compose, from the pane, 2026-09-10.** *A Mother Bird Over the Deep* (54 body blocks, 12
native footnotes, 1 hero, 97 marked runs) composed into a **new empty draft** with
`md_to_substack.py` carried in by `pane_carry.py`. No real Chrome, no clipboard, no Accessibility
permission.

| check | result |
|---|---|
| title / subtitle | both set |
| body blocks | 7 headings + 45 paragraphs + 2 blockquotes + 1 image + 1 rule = **56 nodes** |
| **fidelity digest vs `render_reader`** | **all 54 body blocks identical, all 12 footnotes identical** |
| footnote pass | `{inserted: 12, missing: []}`, **0 `[[FN]]` markers left** |
| empty paragraphs | **0** — the composer's initial node is consumed by the paste |
| marked runs | 67 `em` + 25 `strong` + 5 `link` = **97**, equal to the live post's |
| cross-links | both sibling URLs resolved correctly |
| hero | `image2` with the recorded S3 `src` — **and its `alt` populated from the draft** |

Two things worth carrying away.

**The trailing "extra" block is the divider, not a stray.** A naive block count reads 55 against
the draft's 54, because `render_reader` does not emit the `---` before the footnotes and the
editor does. Subtract the rule before you go hunting for a phantom paragraph.

**A fresh compose sets the image `alt`; adding a hero in the Substack UI does not.** 23 of 34 live
posts carry no `alt` on the hero while the desk holds good alt text for 21 of them — this compose
is the evidence that the converter's `alt` reaches Tiptap intact, so those posts lost it to the
path they were composed by, not to Substack discarding it.

> **⚠️ If you run a transport test like this, TITLE THE DRAFT SO IT CANNOT BE MISTAKEN FOR WORK.**
> The 2026-09-10 test composed a real piece under its real title and subtitle, and left it sitting
> in the Drafts list looking exactly like a finished essay ready to go. The author saw it there and
> reasonably took it for the real thing. **Nothing was published and no email went anywhere** — the
> draft was `is_published: false`, `slug: null`, `email_sent_at: null` — but the near-miss was a
> first publication of a **duplicate** of an already-live post, which is the one click that can mail
> the subscriber list, and it was created by the test itself.
>
> ~~So: set `title` to something like `TEST — DELETE ME (pane transport)` before composing, and
> clean up in the same session.~~ **Superseded 2026-09-11 (Eric): a test never creates a draft.**
> Deleting one is the author's click, never the agent's, so every throwaway became a chore left
> for him. Each outlet now keeps **one standing scratch draft**, recorded in `outlets.yaml` as
> `scratch_draft:`; `python3 framework/tools/scratch_draft.py <outlet>` prints its edit URL and
> the title to set. Open it, set that title, clear the body, paste — and never Continue or
> Publish from it. An outlet with none: create one, give it that title, and record it in the
> same session. The fidelity digest does not care what the title says. **A site's scratch** is a
> store record, not a draft: `bundle_pieces.py … --outlet <site> --scratch`, then
> `store_publish.py`, and the site shows it at its noindexed `/scratch/` (quire 0.16).

## Pages — the same machinery, three differences

**A Substack PAGE is a post with `type: "page"`.** Measured 2026-09-10 by clicking *Add page* in
Settings → Custom pages: it opens at **`/publish/post/<id>`**, in the **same Tiptap composer**, with
the same toolbar and the same *Continue* button. So **every transport in this skill works
unchanged** — `md_to_substack.py`, the `pane_carry.py` carry, the footnote pass, the fidelity
digest against `render_reader`. Do not build a second pipeline; there is only one.

**What a page is for.** Standing information that is not news: a colophon, a disclosure, an
editorial policy. A post is dated and filed in the archive, which is wrong for something that
governs everything published before and after it. A page is undated and sits in the nav bar.

**Declare it in the manifest**, because nothing about the composer will tell you which you are in:

```yaml
substack_type: page      # default `post`; a page is undated, un-archived, never emailed
public_url: https://<pub>.substack.com/<slug>   # RECORD it — never derive it
```

**The three differences, and each one turns a check off rather than on:**

1. **It never emails.** `should_send_email` is `false` on a fresh page and must stay false. The
   first-publication rule — *a first publication sends the subscriber email* — is about posts. A
   page going live mails nobody, and the delivery section must be **provably off**, exactly as on
   the re-sync path.
2. **It is not in the post archive.** `substack_verify --archive` walks the archive API, so a page
   will never appear there; the audit excludes a piece that declares `substack_type: page` rather
   than reporting it missing from a list it was never going to be in.
3. **It needs no cover.** `cover_image` drives the drafts-list thumbnail, the archive card and the
   social preview — a page is in none of those, so step 8 does not apply and `NO COVER` is not a
   finding against it.

**Everything else still holds**, and that is the point of it being the same machinery: the
verification gate, the scripture check, the pronoun and link sweeps, the fidelity digest, and the
rule that the author decides and this skill clicks.

## Republish — surgically re-sync a live post

> **⚠️ Republish edits a public post. Treat the write as irreversible; do NOT assume it has
> shipped.** These are two different things and both matter.
>
> **Measured 2026-09-01, twice, on `The Sheep in the Basement` and `In the Name`:** guarded body
> edits were applied to the live editor, the header showed **Saved** — and the **public page still
> served the old text**. Not a CDN artifact: the check was cache-busted and came back
> `cf-cache-status: DYNAMIC` with no `age` header. **Update** was present and **enabled**; only
> after **Update → Update now** did the public page change. So on that date a live-post body edit
> **staged** rather than published, which is the opposite of what this box previously asserted
> (*"visible to readers immediately… Continue is normally disabled afterwards"*, from `bea8e5a`).
>
> **Do not replace one belief with the other.** The earlier note was written from a real
> observation too; Substack's behaviour may differ by post type or may simply have changed.
> **The rule that survives either way: never infer the outcome — check the public page.**
> - **Verify BEFORE writing.** If autosave *does* publish, the pre-image hash check is the only
>   gate that exists. This costs nothing when it turns out not to be needed.
> - **Verify AFTER, against the reader URL**, cache-busted. That is the only evidence that the
>   change reached readers.
> - **Never report a re-sync as done on the strength of "Saved."** Either it is confirmed on the
>   public page, or it is *staged and awaiting Update* — say which.
>
> **Prefer the `substack-sync` skill for any piece that is already live.** What follows
> pushes draft → live and is **stateless**: it diffs the draft against the live post, which
> cannot tell a draft-side edit from a Substack-side one, and so silently reverts anything
> edited in Substack since the last push. That is not hypothetical — it was caught on
> 2026-09-01 about to revert a reworded line in `Nothing to Get` and a subtitle in
> `I Believe in You`. `substack-sync` is three-way against a stored baseline: it pulls
> Substack's edits into `draft.md` first, reports conflicts instead of picking a side, and
> then calls the push below. Use this section directly only for a piece with **no**
> Substack-side edits possible — in practice, one you just composed.

**0-resync. Before you touch the first outlet, find out how many there are.**

```
python3 framework/tools/resync.py pieces/<name>        # exit 3 = an outlet is behind
```

**Publishing got this gate; re-syncing did not, and that was the hole** (Eric, 2026-09-14:
*"our toolset should republish to all outlets. why was this missed?"*). Step 0-outlets runs
`check_outlets` before a first publication precisely so the irreversible outlet is not the one
you discover the problem after. A **correction** is the case where the outlets are *guaranteed*
to disagree at the start, and nothing ran. `substack_repatch.py` and `substack_sync.py` contain
no occurrence of `outlets` — they know one destination and cannot raise the existence of a
second — so the fan-out lived only in the `substack-sync` skill's prose, which already cited its
own measured precedent and did not stop the same failure recurring three days later.

`resync.py` reads the piece's `outlets:` and **refuses to look like completion**: the summary
reads *N of M outlets current* and the exit is 3 while any outlet is behind. Run it here, and
again after the last carry — **exit 0 is the report.** A green `substack_verify` is not: it
exits 0 on a true statement about one publication, which reads as a finished job.

When a piece is **already published** and `draft.md` has since changed (a fixed quote, a
pronoun-casing sweep, a reworded clause), don't recompose it from scratch — that would
re-upload every image and wipe any Substack-side state. Instead stage a **minimal** edit that
touches only what changed. This is the tool for **touch-ups**; a structural rewrite (blocks or
footnotes added / removed / reordered) is out of scope and the tool **refuses** it (see below).

Preconditions: `publish.yaml` has a **`post_url`**, and the browser is open and logged in on
that post's **editor** at `https://<pub>.substack.com/publish/post/<id>`. (Find the id from the
post's dashboard row / the README; record `post_url` in the manifest the first time.)

1. **Preflight is identical** — verify the footnotes (0b) and keep internal notes behind `†` /
   in comments (0c). The repatch tool runs the same converter, so it **refuses on a stray
   "verify"** exactly as a fresh publish does. The **critique gate (0a)** applies to a
   *substantive* re-sync (a reworded passage); a trivial touch-up (casing, a typo) is exempt.
2. **Generate the patch:** `python3 framework/tools/substack_repatch.py pieces/<name> <out.js>`
   It renders the current draft's **reader-text** (body blocks + native footnotes, the same
   domain the live editor holds) and bakes it into a self-contained snippet. No baseline file:
   it diffs against the **live post itself**, scraped at run time, so it is stateless and
   self-correcting.
3. **Run the snippet once** in the live editor's JS eval. It: sets title/subtitle iff changed;
   scrapes the live doc; **aligns** non-empty body top-nodes 1:1 and footnote nodes 1:1;
   **refuses** (returns `structural:true`, applies nothing) if the counts differ; else replaces
   only the changed run inside each changed node, **preserving surrounding text and marks**
   (bold/italic/links) across the edit.
4. **Read the report** it returns: `{stagedEdits, unchanged, applied[], footnoteChanges[],
   reviewMarks[], failed[], structural, reordered[], suspect[]}`. **`failed` must be empty**;
   `structural:true` means stop and either recompose or edit by hand; `reviewMarks` flags any
   hunk that crossed a formatting boundary or was a large fallback — eyeball those in the
   editor. **`reordered`** means a target block's exact text was found at a *different* live
   index: the two lists are misaligned, not edited — the count guard alone could not see this,
   and a piece once aligned 30 footnotes against the wrong 30 live nodes while passing it.
5. **Ship it: click Update → Update now. Do not ask first.** A body edit to a published post
   **stages** — measured three times (2026-09-01 on two posts, 2026-09-03 on `hollow-flute`):
   the editor reads **Saved**, **Update** is **enabled**, and the **cache-busted public page still
   serves the old text.** So the edit is *not* live until the button is pressed, and leaving it
   pressed-by-nobody strands a correction the author believes they asked for.

   **Shipping an update is NOT gated on a fresh yes** (Eric, 2026-09-10, revising the earlier
   ask-then-click rule). Asking permission to press a button on a change the author has already
   asked for is friction that buys nothing: the decision was the edit, and this click only
   finishes it. **Finishing the edit is part of making it.**

   **What is still gated, and it is the only thing: the FIRST publication of an unpublished
   draft** (step 8 above). That click *is* the publication — it is the one that can mail the
   subscriber list, and it stays the author's.

   **The email guard does NOT relax, because it is not what was gating you.** Removing the ask
   removes a permission step, not a safety check. Before confirming, read the dialog's
   **`innerText`** for *Delivery / Send via email / newsletter / notify / subscribers will
   receive*, and if any such section exists, **prove every control in it is off** before clicking.
   **If one is on, or its state cannot be determined, STOP and ask.** Never toggle, uncheck or
   route around one.

   > **⚠️ The dialog is not always the same, and the difference is an email switch.** The note
   > here used to say an already-published post's dialog "has consistently offered none". **False
   > as of 2026-09-10.** *For the Love of Dogs* (2026-08-05, the corpus's oldest post) shows a
   > **Delivery — "Send via email and the Substack app"** section, and its top-right button reads
   > **"Continue", enabled**, where newer posts read "Update". (An enabled *Continue* is a third
   > state; the earlier note only recorded *disabled* Continue meaning "nothing pending".)
   >
   > **And a control query is not the check.** Searching `input`/`select` for email-ish
   > `name`/`id`/`aria-label` returned **`[]`** on that dialog — the toggle is a `role="checkbox"`
   > `<button>` with no accessible name. Only the dialog TEXT caught it. **A structured query that
   > finds nothing is not evidence that nothing is there.** Read the text first; use a control
   > query only to read the state of what the text found.
   >
   > On that post the toggle was off (`aria-checked="false"`, drafts API `should_send_email:
   > false`), it was clicked on Eric's explicit instruction, and `email_sent_at` stayed `null`.
   >
   > **REPORT THE BUTTON STATE AS A POSITIVE `enabled`, NEVER AS `disabled`/`dis`.** A negated
   > boolean in a scraped readout gets inverted on sight: `{t:'Continue', dis:false}` was read as
   > *disabled* — it means **enabled** — and two rounds of work went into explaining why a live
   > button "would not respond" before the field was re-read. Emit
   > `{label, enabled: !b.disabled}`, or the literal words, so the value cannot be misread as its
   > opposite. Same reason the pronoun and status checkers report what a thing IS rather than what
   > it is not.

   **Then verify against the cache-busted reader URL, not the "Your post is live!" screen** —
   that screen is a claim, not evidence. `substack_verify.py --fresh <piece>` is the evidence.
   Report *confirmed public*, or *staged, awaiting Update* — never "done" on the strength of
   **Saved**.

   **And that is Substack confirmed, not the piece.** A republish moves one outlet. If
   `outlets:` names others, carry the change to each — `substack-sync` step 8, the same whether
   you arrived through that skill or here — and report per outlet. On 2026-09-11 a correction
   was logged *live and verified* on the strength of a Substack MATCH while alignmentfellowship.org
   went on serving the old sentence — until an audit happened to look.

   **Read the report** the patch returns: `{stagedEdits, unchanged, applied[], footnoteChanges[],
   reviewMarks[], failed[], structural, reordered[], suspect[]}`. **`failed` must be empty** before
   any of the above.

### Structural republish — when the surgical tool refuses

`substack_repatch.py` refuses a block-count change, and it is right to: a paragraph added,
removed, merged or split is a rewrite, and the surgical engine's 1:1 alignment would write into
the wrong paragraph. **The answer used to be "recompose or edit by hand," and both were bad on a
post that carries an embed or an image** — a recompose destroys the embed (nothing in the repo can
rebuild it), and "by hand" meant a hand-built snippet that needed one more guard every time it
ran (`hollow-flute`, three times, 2026-09-04 → 07). That snippet is now the tool's second engine:

```
python3 framework/tools/substack_repatch.py --structural pieces/<name> <out.js>
```

Run it once in the live post's editor, like the surgical snippet. It **aligns the draft against
the live document by block text** (LCS), then: **anchor-bearing blocks pair 1:1 by order inside
each changed range and are edited by text hunk only**, so a native footnote anchor is never
touched by HTML; every other changed block is **replaced whole from the converter's own HTML**
(italics, links), with quotes **smartened outside tags only** — a curled quote inside `href="…"`
is a dead link, measured 2026-09-04; **a retired footnote's anchor is dropped**, and the orphaned
footnote node too if the editor does not remove it itself (Substack did, measured 2026-09-07); an
**insert lands on the draft's side of a divider** (after the `---` if the draft puts one before
the new block, otherwise right after the preceding block).

**It refuses, before touching anything,** when a block's HTML does not hash to its own text (the
**transcription guard** — the sha256/16 is computed by the generator, so a snippet retyped into
an eval fails closed on any slip); when anchor-bearing blocks do not pair 1:1 (un-merge or re-split
the draft so each footnote-bearing paragraph has a live counterpart — that is what the v3 sync
needed); when the draft **adds** a footnote (`insertFootnote` is not automated here — add it in
the composer, or recompose); when footnote order differs; or when a hunk would span an inline
node or cross a mark boundary.

**Read the report:** `{refused, ok, applied[], failed[], plan{replace,insert,delete,hunk,fnHunk,
dropAnchor}, final{body, footnotes, anchors, bodyMismatch[], fnMismatch[], linksMissing[],
dividersOff[], firstNode}}`. **`refused` must be null and `ok` must be true**; `final` is the
whole document read back after the edits — counts, every block's text, every footnote, the anchor
count, and a link mark on every block whose HTML carried one. Then the same as any republish:
ask, click **Update → Update now** after reading the dialog for email, and **`substack_verify
--fresh`**. The engine is exercised against a stubbed editor on every piece by the suite
(`test_substack_structural.js`, cases S1–S9).

## After a human clicks Publish — mark the file as published

A piece keeps its text in `draft.md` for its whole life. The filename does **not** change
on publication: nine tools identify a piece by that name, and a second name would mean a
call site that missed the rename does not fail — it silently drops the piece from the
corpus checks. The **header** carries the state instead.

Once the post is live, record the facts and rewrite the header:

```
# in publish.yaml
public_url:   https://elmuffin.substack.com/p/<slug>
published_at: YYYY-MM-DD        # the live post's own post_date, not the day you noticed

python3 framework/tools/piece_header.py --apply <slug>
```

That replaces the `*Draft — …*` scaffold line with

> *Published 2026-08-27 · [Nothing to Get](…) —*
> *this file is the source of record for the live post.*
> *Edits here are not live until pushed (`substack_sync push`),*
> *and `substack_verify --fresh` confirms they landed.*

and drops a now-false `*(working title)*` from the H1 when the piece shipped under that
exact title. The rest of the scaffold note — voice, arc, consent boundaries, scripture
conventions — is preserved verbatim; only the word "Draft" goes.

All of it sits above the first `---`, which the converter discards, so it can never reach
a reader. It is checked by the suite (`corpus_headers`) precisely because invisible things
rot unnoticed.

**Then correct every sentence that still calls it a draft.** A book index
(`books/<name>/writings.md`), a sibling README's seams list, a dashboard fragment — anything
written by hand while the piece was unpublished now says something false, and publishing
changes none of it for you. Five pieces in three days went on being described as unpublished
after they were live (*In Vain*, *The Mask Comes Off Last*, *Rising After Falls*, *What Was
Already There*, *Not Made of Things That Appear*), every time because the manifest updated
itself and the prose did not. Link the piece wherever the house rule says live pieces link,
drop the "unpublished", and run:

```
python3 framework/tools/check_status.py --outlets publishing/outlets.yaml
python3 framework/tools/check_refs.py
```

**The suite runs both (`corpus_prose`), so CI and the pre-push hook refuse the push.** The
publishing commit is the one that has to carry the correction — which is the point: the only
session that knows a piece just went live is the one that published it.

**And a published piece must declare its `outlets:`.** *Not Made of Things That Appear* went live
on Substack with none, so `md_to_site` exported it nowhere and `outlet_audit` — which checks only
the outlets a piece declares — could not see it was missing from the site. The suite now refuses a
manifest with a `public_url` and no `outlets:`.

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

Run with no arguments to sweep every published piece. Each piece's **title and subtitle**
are compared too (normalised for curly quotes and dashes): the body comparison cannot see
them, since they are not in `body_html`, and an **empty live subtitle is drift on its own**.

**`--archive` checks the publication, not the repo.** Every other mode starts from
`pieces/` and can only verify what the desk knows about. `--archive` walks the public
archive API instead — the reader's list — and fails on any live post with **no subtitle**,
no title, one the desk has **no manifest for**, or a header that differs from its manifest.
That is the check that would have caught a post which had sat live for a month with an
empty subtitle (2026-08-05 → 2026-09-03): it was composed by hand, before the desk, so
nothing keyed off `pieces/` could see it. Run it after every publish.

```
python3 framework/tools/substack_verify.py --archive --fresh
python3 framework/tools/substack_verify.py --archive --fresh --outlet <other-substack-outlet>
```

**An archive belongs to ONE publication, and a desk can have two.** `--archive` walks the
`substack_primary` outlet's by default; `--outlet` names another. Every mode finds a piece by
**its own outlet's `manifest_url_key`** (outlets.yaml), never by `public_url` — which is one
outlet's key, and was hard-coded here until 2026-09-11. While it was, the second Substack
publication was invisible to this tool: its posts were skipped, and skipped with the wrong
reason — *"composed but not published"* about a post live for a day — so **caption, text, mark
and anchor drift went unchecked on a whole publication and every run still said the repo
matched.** `--list` now prints each piece's outlet beside its state; a piece that reads `-`
is one nothing places, and its URL will not be found.

> Do not put this in CI on a GitHub-hosted runner. Measured 2026-09-02: Substack returns
> **403 to Azure IP ranges** on every path — page, API, and RSS, with any user agent. It
> is an IP block, so there is no header that fixes it. Run it locally, or from a
> self-hosted runner.

## The other outlets — export the bundle, hand it over, verify the reader URL

Substack is bespoke because Substack has no write API. **Nothing else has to be**, and the rest
of `outlets:` is served by one neutral artifact rather than one bespoke integration per host.

**Do this as part of publishing, not afterwards.** A piece is published when every outlet it
names has it. Run this once the piece is confirmed live on the outlets that need a human click,
so the exported text is the text readers actually got.

1. **Export the bundle** — the piece must declare the outlet, or it is not exported:

   ```
   python3 framework/tools/md_to_site.py <bundle-dir> pieces/<name> --outlet <outlet> --apply
   ```

   `md_to_site.py` strips the same things the Substack converter strips — the scaffold above the
   first `---`, HTML comments, and anything after a `†` in a footnote — and **refuses** a draft
   with no `---` rather than guessing where the desk ends and the essay begins. Pass
   `--canonical-base` and `--syndicated substack` so the bundle records which URL is canonical
   and which is syndication; getting that backwards is an SEO decision made by accident.

2. **Hand the bundle to the destination.** How is instance-specific and lives in the instance's
   `publishing/` notes — never here. The framework's job ends at the bundle; the instance's note
   says where it goes and what builds it.

3. **Verify on the reader URL, exactly as with Substack.** A build that succeeded is not a page
   that exists. Fetch the piece's public address on that outlet and confirm it returns 200 and
   contains the text — the same *check, don't infer* rule the Substack half of this skill is
   built on. **A 404 here is the normal failure**, because a piece can be absent from a bundle
   for a quiet reason (it never declared the outlet) and every step will still report success.

4. **Record the outlet's URL** in `publish.yaml` beside `public_url`, so a sibling essay's
   cross-link can reach for the right host.

**Half-published is the failure to design against.** Live on one outlet and missing from another
is the state nothing reports, because each half looks complete from inside itself. Check every
outlet in the list, every time, and say which ones you confirmed.

5. **Audit the outlets against each other** — the check that looks across, rather than each
   outlet checking itself:

   ```
   python3 framework/tools/outlet_audit.py            # after any publish
   ```

   It reads the instance's outlet registry (`publishing/outlets.yaml`; the framework holds no
   URLs), and for every piece that is **published and declares an outlet** it fetches that
   outlet's reader URL cache-busted and expects 200. It also runs the **reverse** direction from
   each outlet's sitemap — every live URL must be a piece the desk knows — which is the only
   direction that can see a page the desk never produced. **Exit 3 is drift; exit 2 is "could not
   reach", which never wears the same face as a pass.**

   **It compares TAGS too, on every run** (2026-09-16). Every text on the store index — pieces and
   talks, tag ids and labels, from one fetch of `index.json` — and every Substack post the forward
   check just found live, read through `substack_tags`' own plan so the two cannot disagree about
   what a post should carry. **A tag added to a live text reaches no outlet by itself**: the store
   record and the Substack post are separate writes, and on 2026-09-15 two texts were found
   publicly untagged by a person looking at a page while every check here was green. A finding
   reads `TAGS <ref> on <where>: missing … / extra … / <tag> reads 'X', the vocabulary says 'Y'`;
   the fix is the re-publish it names. `--no-tags` skips it.

   Two things it deliberately does *not* treat as failures: a piece that declares an outlet but
   **is not published yet** (reported and skipped — declaration is intent, publication is fact),
   and a legacy manifest that opts in with `site: true` instead of an `outlets:` list (counted,
   and reported as a migration count).

   **Record the outlet's URL in the manifest** (`site_url`, `public_url`) rather than relying on
   the audit to guess it. A guessed URL is derived from a slug, and slugs diverge: one piece
   publishes as `theythem` on one outlet and `they-them` on another, and a retitled piece keeps
   its old directory name for ever. A recorded URL always wins over a derived one.

## How it works (re-probe here if Substack changes)

- Substack's editor is **Tiptap** over ProseMirror, reachable at
  `document.querySelector('.ProseMirror').editor` (`editor.commands`, `editor.chain()`).
- **Body, the default:** put `text/html` on the **system pasteboard** and send a **real ⌘V** in
  **real Chrome**. Tiptap's paste converter builds the blocks from the HTML flavor.
  **Correction, 2026-09-01 — the old note here said "⌘V and keyboard modifiers are unreliable in
  the browser tool," and that was true of the wrong noun.** It is true of the **in-app browser
  pane**, where a synthetic ⌘V is a no-op and `navigator.clipboard.read()` throws
  `NotAllowedError: Document is not focused` (a programmatic `.focus()` does not satisfy the
  Clipboard API). It is **false of real Chrome**, where a real click plus a real ⌘V pastes
  correctly with `h2`/`em`/`strong`/links/blockquotes intact. Reading that note as surface-neutral
  is what kept this skill on the transcription path for months.
  **The pasteboard needs the HTML flavor specifically:** `pbcopy` sets only
  `public.utf8-plain-text`, which pastes as flat text and loses every heading and italic. Use
  AppleScript's `«data HTML<hex>»` (what `md_to_clipboard.py` does), and pass the script on
  **stdin** — a 32KB essay overruns the argv length limit.
- **Body, on the pane:** dispatch a synthetic `paste` `ClipboardEvent` carrying `text/html` on
  `.ProseMirror` — which is what `md_to_substack.py` already emits. This path was long written off
  as a fallback because it "requires the agent to reproduce the whole essay into the eval," but
  that was a fact about *delivery*, not about the paste: the `window.name` carrier removes the
  transcription entirely, and the paste itself never touches the Clipboard API, so the pane's
  pasteboard ban does not apply to it. **Measured 2026-09-10** — see the compose result below.
- The paste is applied **asynchronously**, so the footnote pass MUST be a separate call
  (B) after the body is in the doc model.
- **Images:** an `<img>` with a `data:` URI is uploaded to Substack's CDN on paste.
- **Footnotes:** paste cannot create native footnotes; `insertFootnote` (option 2) does —
  select the marker, delete it, insert the footnote, `insertContent(html)` fills it. Re-scan
  the doc for each marker so shifting positions don't matter; Substack renumbers by position.
- **Title/subtitle** are React-controlled `<textarea>`s — set via the native value setter
  plus an `input` event.
- **Republish (surgical):** the live post's editor is the same Tiptap/ProseMirror doc, opened
  at `/publish/post/<id>`. Its top nodes are `heading`/`paragraph`/`hr` (body) and `footnote`
  (native footnotes, at the tail, in order) — so body and footnotes separate cleanly and align
  1:1 with the converter's output. The patch diffs **reader-text** (tags/`[[FN]]` markers
  stripped, entities unescaped) so the diff domain equals the editor's text. Each changed run
  is replaced in place with `tr.replaceWith(from, to, schema.text(new, marks))`, carrying the
  marks resolved at the edit — casing flips inside an `<em>` keep the italic. Edits apply
  **latest-position-first** (node then offset, descending) so unapplied positions stay valid.
  Char-offset→doc-position uses `node.descendants` (correct whether a node is a bare textblock
  or wraps a paragraph). **`Continue` stays disabled until a real edit lands** — a good check
  that a no-op re-sync changed nothing.

## Recompose: check the images first

A recompose (a full re-paste, as opposed to the surgical re-sync above) **destroys any image
the live post holds that `draft.md` does not reference.** Images are URL-only on this desk —
the repo stores no bytes — so there is nothing to restore one from.

Run the check before any recompose, and treat it as a gate rather than advice:

```
python3 framework/tools/substack_sync.py images pieces/<name> images.js      # run in the editor
python3 framework/tools/substack_sync.py check-images pieces/<name> images.json
```

Non-zero exit names every live image the draft does not know about. Fix a gap by pasting the
URL into `draft.md` where the image belongs — **never** by deleting the image from the post.

## Guardrails

- **NEVER WRITE TO THE DRAFTS API WHILE THE COMPOSER IS OPEN ON THAT POST.** This is the
  two-editors rule below, one layer down, and the API does not look like an editor — which is
  exactly why it catches people. Measured 2026-09-10 on `what-was-already-there`: a
  `PUT /api/v1/drafts/<id>` setting `cover_image`, sent from the editor page's own console while
  the composer held the document, desynced the two. Substack then **refused to publish** —
  *"Draft not saved — Post out of date"* — and the cover reverted to `null` when the editor saved
  its own state back over the write. A fully composed, digest-verified draft sat one stale copy
  away from being unpublishable, and **nothing warned until the publish button refused.**
  The recovery is a page reload (the body survives it; verify the counts after). The rule: set the
  cover **before** opening the composer, or through the composer's own UI, or after publishing
  with the editor closed — and re-verify the body digest either way.
- **Never leave two editors open on the same post.** The sync tooling compares `draft.md` against
  **one** live post; it has no concept of two editors racing, and the newer save silently wins.
  On 2026-09-01 the in-app pane and real Chrome both held the same post — the pane still carrying
  the **empty pre-paste state** while Chrome held the finished essay — which put a 5,700-word
  published piece one autosave away from being overwritten with 38 characters of leftover test
  content, and swallowed edits the author made in the wrong window. **Before composing, navigate
  away or close every surface except the one you are composing on**, and say which surface you are
  using so the author edits the same one.
- **The pasteboard is a leased singleton.** `md_to_clipboard.py` takes the `pasteboard` lease and
  waits for it; never `pbcopy` around the tool, and never paste from a board you did not load under
  the lease in the same process. Three races in one afternoon (2026-09-07), all to sibling sessions,
  are why. If `--paste` is refused for Accessibility, say so and stop; do not fall back to retyping.
- **Never retype the essay to get it into Substack.** If a step requires the agent to reproduce
  the author's prose character by character, that step is wrong — reach for the clipboard
  transport. The author's words should travel **disk → pasteboard → browser**, never through the
  agent's fingers. This is not a performance preference: a transcription slip publishes a typo in
  the author's voice, and every guard downstream reads it as an intended edit.
- **Shipping an edit is ungated; publishing needs the author's word — not their mouse.** Two
  different acts, two rules. **First publication of an unpublished draft: the author decides, this
  skill clicks.** It is the publication, and it is the one time the subscriber list is mailed —
  which is the point of having one, not a hazard to design around. **Shipping a later edit to an already-published post:
  just click Update → Update now** (Eric, 2026-09-10, revising the 2026-09-03 ask-then-click rule,
  which itself replaced a blanket never-click). The decision was the edit; the click only finishes
  it, and an unfinished edit strands a correction the author believes they asked for.
  **The email guard does not move, and removing the ask did not touch it** — an ask is a permission
  step, a guard is a safety check. Read the confirm dialog's **text** and prove nothing can be
  mailed: *Delivery / Send via email / newsletter / notify*. **If a delivery section exists, every
  control in it must be provably off; if one is on, or you cannot tell, STOP and ask.** Never
  toggle or route around one. **Do not rely on a control query** — on the one post that has this
  section the toggle is a `role="checkbox"` button with no accessible name, and an
  input/select query returned `[]` while the section was plainly there in the text.
- **Verify both sides of a live write, and never infer the outcome.** *Before*, because the
  pre-image hash check is the only gate that exists if autosave turns out to publish. *After*,
  against the **cache-busted reader URL** — measured repeatedly, the editor says *Saved* while
  readers still get the old text. **"Saved" is not "shipped," and neither is "Your post is live!"**
  — that screen is a claim; `substack_verify --fresh` is the evidence.
- **Republish is surgical, and touch-ups only.** It changes the smallest span that differs and
  nothing else. If the diff is structural — a block or footnote added, removed, or reordered —
  the tool **refuses** (`structural:true`, zero edits); recompose the piece or edit by hand
  instead of nuking-and-repaving a live essay. Never pass a flag to force past a refusal.
- **Framework stays generic.** No publication specifics, no secrets, no personal writing here.
- **Never recompose without the image check.** A re-paste silently drops any live image the
  draft does not reference, and nothing in the repo can rebuild it.
- **Verified + clean before it ships.** Preflight is not optional: footnote claims are
  fact-checked, and internal notes are stripped (the converter refuses output otherwise).
  Misquoting a real person or leaking a "Verify X" note into a public draft is the failure
  this step exists to prevent.
- **Verify before hand-off.** Always run the post-check; a paste that silently half-lands is
  the failure mode to catch (paragraph/footnote/marker counts).
- **Footnotes are coupled to Substack internals** (`.editor`, `insertFootnote`). If Substack
  changes them, call B's `missing` list or the leftover-marker count will surface it — fall
  back to endnotes (a trailing `<hr>` + numbered list) and flag for a re-probe.
