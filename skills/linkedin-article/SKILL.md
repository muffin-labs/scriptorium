---
name: linkedin-article
description: Compose a finished, already-published piece as a LinkedIn Article DRAFT for the author to publish — the syndication copy, with an "Originally published at" line in place of rel=canonical and endnotes in place of footnotes. Use when the user says "put X on LinkedIn", "syndicate X to LinkedIn", "LinkedIn article for X", or a piece whose publish.yaml names `linkedin` has gone live on its canonical outlet. Composes the Article, drafts the announcing post, and — on the author's approval of that exact text — types it and clicks Publish (Eric, 2026-09-11). Never engages: no reactions, comments, messages, connections or reposts, and no post but an Article's own announcement.
---

# LinkedIn Article

LinkedIn is the last outlet a piece reaches, and it is a copy. The canonical — the site
the piece calls home — goes first and gets indexed; Substack follows; LinkedIn comes
last and says where the original lives. This skill composes that copy and stops.

## Before anything else

**There is no API.** Articles have no write endpoint at all, and even a short share needs
an approved app and OAuth. So the Article is composed the way a person composes one, in
the author's own logged-in Chrome through `mcp__claude-in-chrome__*`.

**That is automated access to LinkedIn, which its user agreement prohibits.** The instance
records the author's decision about it; read that before doing anything (on this desk:
`.claude/skills/linkedin/SKILL.md` in the command center, which decided profile fields
on 2026-09-08 and, in its first version, said *never posts*). If the instance has not
extended that decision to Articles, **stop and ask** — composing an Article draft is a
wider scope than editing a headline, and it is the author's call, not the tool's.

Where it is allowed, keep what makes it defensible:

- **One Article, at human pace, and the author decides.** No loops, no batches. The Article goes
  out only on the author's approval of the announcing post's exact text, per Article.
- **Nothing social.** Never a reaction, comment, connection, message or repost, and no post but
  the Article's own announcement.
- **Draft first.** The Article is composed and left as a draft (LinkedIn autosaves) until the
  announcement is approved.

## Preflight — the converter refuses, and that is the point

```bash
python3 framework/tools/md_to_linkedin.py pieces/<name> --outlets publishing/outlets.yaml --check
```

It refuses, with no `--force`, when:

- `publish.yaml` does not name `linkedin`. Nothing goes where it was not sent.
- `check_verified.py` refuses. Syndication does not weaken verification.
- the body carries a verify marker, an unpaired footnote, or a clearance date.
- **the canonical is not recorded and live.** PUBLISHING.md: publish the canonical first
  and let it be indexed. An Article whose first line says *originally published at* a URL
  that 404s is a broken promise in the opening sentence — and if LinkedIn goes up first,
  LinkedIn is the copy search engines find.

Then, without `--check`, it writes `pieces/<name>/linkedin/article.html`, `article.json`
(title, canonical, the cover, figures in upload order with their alt text) and `cover.json`
(the hero's local path and caption — see 4b).

## What the copy looks like, and why

| On the canonical | On LinkedIn | Because |
|---|---|---|
| `rel=canonical` | *Originally published at <url>* as the first line | LinkedIn emits no canonical tag |
| subtitle | italic lede under that line | an Article has a title and nothing else |
| native footnotes | `[1]` in the text, **Notes** at the end | LinkedIn has no footnotes; numbered in first-reference order, as Substack numbers them |
| the hero | the Article's **cover**, uploaded into LinkedIn's own cover control, with `cover_caption` typed under it | the cover is the card thumbnail everywhere the Article is listed; a body figure is not (4b) |
| figures | a marked slot, replaced by pasting that figure over it | a pasted image uploads on save but loses its alt, so figures go one at a time and each alt is restored from its payload |

## Composing — measured 2026-09-10, end to end, in the built-in pane

Driven once, against a draft titled `[TEST — do not publish]`, and every step below is what
actually happened. **The pane is the default surface** (Eric, 2026-09-10); it holds none of the
author's sessions, so they sign in there themselves.

**Testing a step? Use the scratch draft, never `article/new/`** (Eric, 2026-09-11). The agent
cannot delete a draft, so a new one per test is a chore left for the author.
`python3 framework/tools/scratch_draft.py linkedin` prints `/article/edit/<id>/`: the draft
already exists, so setting the title does not remount the editor (step 3's trap), and the body is
cleared with `el.editor.commands.clearContent()` in place of step 4's refuse-if-not-empty — the
scratch is the one editor allowed to be overwritten. Never Publish from it.

1. **Sign-in is the author's.** LinkedIn answers a new device with an *app challenge* ("Check
   your LinkedIn app… tap Yes"). Never touch Resend, SMS, or "Recognize this device". Then
   **confirm it took before navigating** — read `document.title`/`location.pathname` and stop on
   `sign in|login|challenge|checkpoint`. On 2026-09-10 "done, I'm signed in" arrived while the
   pane was still on the challenge; navigating then started a second challenge.
2. **Carry the body.** `python3 framework/tools/pane_carry.py <out>/article.html`, navigate the
   pane to the carry URL, then to `https://www.linkedin.com/article/new/`. `window.name` crosses
   intact — and survives a sign-in round trip and a reload. Verify the sha256 in the page.
3. **Title first, and wait for the draft to exist.** `textarea#article-editor-headline__textarea`,
   set by its native value setter plus an `input` event (it is short and not prose). **Setting
   it creates the draft: the URL becomes `/article/edit/<id>/` and the body editor REMOUNTS.** A
   paste sent straight after the title went into the discarded editor and vanished — the first
   attempt landed zero of 3,271 words. Wait for the `/edit/` URL, re-query the editor, then paste.
4. **Body.** `div.ProseMirror[aria-label="Article editor content"]` is **Tiptap** (`el.editor`).
   Refuse if it is not empty, then dispatch a synthetic `ClipboardEvent('paste')` carrying the
   `text/html` — the same transport as the Substack pane path. Measured against the sent HTML:
   **59/59 blocks byte-identical**. Unlike Substack, **no smart-quote rewriting**. Two changes to
   expect, neither a fault: **every `h2` becomes `h3`** (LinkedIn demotes headings a level), and
   an `em` wrapping a link **splits around it** (the canonical line: 23 `em` sent, 25 counted).
4b. **The cover — the hero goes HERE, not into the body (2026-09-15).** An Article's thumbnail on
   every card — the feed, the author's Articles list, a share — is its **cover image**, a slot
   above the headline that LinkedIn keeps apart from the body. Until today the hero was pasted in
   as figure 1 and the cards showed no image at all (Eric: *"it looks like we don't have a
   preview image for linkedin posts"*). `md_to_linkedin` now writes the manifest's `cover:` to
   `cover.json` and gives it **no body slot**; figures are numbered without it. Measured on three
   Articles, one draft and two already published:
   - **Open the control.** The empty cover area reads *Add a cover image or video to your
     article* with an **Upload from computer** button. The button creates its file input on
     click. A click by accessibility ref **did not fire reliably** (one of three times); a
     synthetic `button.click()` from the page did, every time, and opens an *Add cover image or
     video* dialog holding a real `input[type=file]`.
   - **Upload from the local file, never a carried data URI.** Find that input and use the
     browser tool's file upload on `assets/hero.png` (the path in `cover.json`). Do not click the
     input — that opens a native picker nobody can drive. Then **Next** in the dialog.
     **In the built-in pane there is no file-upload tool**, and this is how it went in there
     (2026-10-15, the-top-step): carry the cover's served copy, decode it in the page into a
     `File`, and set it on that same input — `const dt = new DataTransfer(); dt.items.add(file);
     input.files = dt.files; input.dispatchEvent(new Event('change', {bubbles: true}))`. The
     dialog takes it as an upload; reload and read back the `article-cover` image as below.
   - **Caption, then WAIT.** The cover lands with an *Add credit and caption* textbox under it;
     type `cover.json`'s `caption` there. The cover's `src` is a `data:` URI until the autosave —
     **navigating away inside ~15 s lost the cover once** (the caption survived, the image did
     not). Wait for *Draft - saved*, reload, and read back an `<img>` outside the editor whose
     `src` is `media.licdn.com/dms/image/…/article-cover…` plus the caption textarea. Only then
     move on.
   - **A cover has no alt field.** The hero's alt stays on the blog and Substack; on LinkedIn
     the caption is what a reader gets. Do not paste the hero into the body to keep the alt —
     the same image twice, stacked, is what an Article looked like on 2026-09-15 before the
     body copy came out.
   - **Retrofitting a published Article** is the same steps in its editor (`/pulse/…` → *Edit
     article*, or `/article/edit/<id>/`), then delete the body's figure-1 copy of the hero by
     ProseMirror (`tr.delete` on the first `figureImage`, after checking its alt is the hero's),
     wait for the save, reload, and click **Update** — no dialog follows; the page lands on
     `/pulse/…` with the cover above the headline. **Update by ref also did not always fire;
     `button.click()` did.** Read the public page back: one `article-cover` image, the diagrams
     `article-inline`, the hero not repeated.

5. **Figures, a batch at a time.** `md_to_linkedin` writes `figures<k>.json` — as many figures as
   fit one carry (~3.5 MB), each the served copy (1600 px JPEG), not the master. Carry a batch,
   insert every figure in it as below, then wait for *Draft - saved* with no `imagePlaceholder`
   left and reload to confirm the `src`s are `media.licdn.com` **before** carrying the next batch
   (a navigation before the save loses the unsaved uploads). The-top-step's nineteen figures
   (2026-10-15) went in as five hand-built batches; the converter now builds them, three.
   `fig<N>.json` still exists for a single figure.
   For figure *N*: take it from the batch (or carry `<out>/fig<N>.json`), find the paragraph
   whose text starts `[Figure N — upload here]`, `E.commands.setNodeSelection(pos)`, and paste an
   `<img>` **built with `document.createElement`** so its alt is escaped properly (the shared
   renderer's `esc()` does not escape quotes). It lands as `figureImage` → `inlineImage` +
   `figcaption`. Then:
   - **It is uploaded ON SAVE, not on paste.** For the first 25 seconds the `src` is still a
     `data:` URI and `urn` is empty; after the autosave and a reload it is
     `media.licdn.com/dms/image/…` with `urn:li:digitalmediaAsset:…`. Verify after a reload —
     reading it straight after the paste says "not uploaded", which was wrong.
   - **The paste drops the alt text** (740 characters in, 0 kept). Restore it from the payload:
     `tr.setNodeMarkup(pos, undefined, {...attrs, alt})` on the `inlineImage`. Measured: 740/740,
     exact, still there after a reload.
   - **Then its caption — as an ATTRIBUTE, not just text.** Every `figureImage` LinkedIn creates
     holds an empty `figcaption` (schema: `inlineImage figcaption`), and **LinkedIn saves the
     `figcaption`'s `text` attribute, not its content.** Measured 2026-09-11 on
     love-is-not-a-metric-space: six captions written as content alone showed in the editor, said
     *Draft - saved*, and were all empty after a reload. Set both, in one transaction, last figure
     first: `tr.setNodeMarkup(pos, undefined, {...attrs, text: caption})` for the attribute and
     `tr.replaceWith(pos + 1, pos + 1 + node.content.size, schema.text(caption))` for what the
     reader sees. The payload's `caption` comes from `publish.yaml`'s `captions:` or
     `cover_caption:`, via `md_to_linkedin`; an empty one is left empty.
     **Wait for a real save before navigating**: a *Draft - saved* already on screen is the old
     save, so watch for *Saving* then *saved*, and keep the wait short — the pane kills a script
     after 45 s. Then reload and read back both the attribute and the visible text.
6. **The onboarding modal** ("Say hello to a smoother editing and publishing experience") opens
   on first use and closes on its own. Nothing needs clicking.
7. **Draft the announcing post.** Two or three options, each built only from claims the piece
   makes — the dialog's box reads *Tell your network what your article is about* — and put them to
   the author. The approved text goes in `pieces/<slug>/linkedin-post.md`; `md_to_linkedin` carries it
   into `article.json` as `announce` and refuses one over 3,000 characters.
8. **Publish, on that approval — one guarded script.** Click **Next** in the editor; the dialog holds
   the author line with the audience (*Post to Anyone*), a contenteditable box
   (`[aria-label="Text editor for creating content"]`), a schedule button and **Publish**. Then:
   refuse unless the box is empty; `execCommand('insertText')` each paragraph with two
   `insertParagraph`s between (a blank line survives only that way, as with typing); read the box
   back and **refuse unless it equals the approved text**; refuse unless the audience is what the
   author saw; click **Publish**. Success lands on `/pulse/<slug>-<author>-<id>/?published=t` —
   strip the query and record it (below). Measured 2026-09-11 on love-is-not-a-metric-space.

### 8b. **Scheduling instead of publishing — the default when the piece has a moment.**

   A piece can be live on its canonical and due on its feed outlets later: the canonical is
   `on_schedule: immediate` and LinkedIn is `at_moment` (`publishing/outlets.yaml`). When
   `python3 framework/tools/schedule.py check pieces/<slug>` says EMBARGOED and `linkedin` waits,
   **use LinkedIn's own scheduler rather than coming back to click** — the dialog that holds
   Publish also holds a schedule control, beside it.

   Everything in step 8 still applies and none of it relaxes: the announcing post is typed the
   same way, read back, and **refused unless it equals the text the author approved**; the
   audience is checked; the approval is still per Article and still the author's. The only
   difference is which control finishes it.

   **Then record it, because nothing here can see it afterwards.** The schedule lives on
   LinkedIn's side; the desk's only evidence is what it writes down:

   ```
   python3 framework/tools/schedule.py record pieces/<slug> --outlet linkedin \
       --where "LinkedIn's own scheduler, in the Article publish dialog" \
       --evidence "<article edit url>" --approved "<who, when>"
   ```

   `outlet_audit` reads that record. Without it, a piece due on LinkedIn reports **NOT
   SCHEDULED** — which is the state you want to be told about on the day you could still fix it,
   rather than the morning after.

## After it publishes

- Record the Article's URL in `publish.yaml` under the outlet's `manifest_url_key`
  (`linkedin_url` on this desk). **It cannot be derived** — LinkedIn appends an id — so an
  unrecorded URL is an unaudited copy.
- Run `python3 framework/tools/outlet_audit.py --outlet linkedin`. It checks the recorded
  URL, and a missing Article is reported missing: LinkedIn redirects a dead Article to a
  live 200 page, and the audit knows that page when it sees it.
