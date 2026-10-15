---
name: picture-deck
description: Build a talk whose every slide is a PICTURE, one slide at a time, working from a reading copy (`talks/<slug>/preview.md`). The desk writes a spec per slide; the author generates each image and drops it in with an instruction by position — "make this slide 4", "replace slide 6 with this", "new slide 12", "this should come after slide 5", "cut slide 16". Each turn places the picture in draft.md with its alt text and the words spoken over it, checks the picture against its spec, regenerates the preview and the slide map, and commits that one slide. Use whenever an image arrives for a talk with a slide number, or the author asks to preview the deck. Publishing the deck is `img_deck.py` → `talk_bundle.py` → `store_publish.py`, on the author's word.
---

# Picture deck

A picture deck is a talk where **every slide is one generated image with its words inside the
frame**: carved, lettered, painted, never set as type over the picture. The first was *The Top
Step* (2026-10-14/15, 27 slides). There is no layout pass, so there is no canvas. The draft holds
the script and the order, a spec file holds what each picture must show, and the author makes
the pictures.

**Choosing the path.** A deck with type on its slides goes through the canvas (`talk` skill,
`md_to_dc.py`). A deck of finished pictures comes through here. A deck that mixes the two goes
through the canvas. `img_deck.py` refuses a slide it cannot render as exactly one image.

## The files

```
talks/<slug>/
  draft.md          the source: the order, each slide's image and alt text, the spoken script
  talk.yaml         title, size, pace_wpm, duration_min, publication, figures: …
  preview.md        the READING COPY: generated, never edited — img_deck.py --md
  assets/SPECS.md   one spec per picture, addressed by FILE; the slide map is generated into it
  assets/*.png      the masters, as the author generated them
```

In `draft.md` a picture slide is a slide marker, one image line whose alt text is the slide's
words or a description of the picture, then the paragraphs said while it is up:

```
<!-- slide -->
![A tall standing stone … carved "THAT JOB IS GONE, AND NOBODY MISSES IT."](assets/s05-the-job.png)

The spoken script, in ordinary paragraphs.
```

A movement heading (`## I. …`) opens a slide too, and carries the section picture.

**Set `pace_wpm` in `talk.yaml`** to the voice's pace. The preview's clock and `md_to_marp`'s
both read it, and both default to 130.

## Before the first picture

1. Run `talk`'s *Always do this first*: the spoken-register style, the outline's minutes,
   `talk.yaml`, the publication and the tags.
2. **Write `assets/SPECS.md` before asking for any image.** It starts with what the deck reads as
   one object: the world (sky, ground, light, camera), the materials and what each one means,
   **the letterform** (*how* text is set, not only what it says), the tone of every recurring
   surface, and the closed constraints. Then one section per picture, headed by its filename.
   Each spec **restates the world in full** so it can be pasted alone, because consistency
   across separate generations is the whole risk. Each spec whose picture carries words ends
   with a `Read back before accepting:` line giving the exact string.
3. Put `<!-- slide-map -->` and `<!-- /slide-map -->` where the map belongs, then run
   `img_deck.py talks/<slug> --map talks/<slug>/assets/SPECS.md`. Until the deck is finished,
   the map's `on disk` column is the list of pictures still to make.

**The desk writes specs and never generates or invents an image.** The author generates.
(Eric, 2026-10-14: *"we should describe them and I will generate them."*)

## The loop: one picture per turn

The author reads `preview.md` and sends one image with one instruction. For each one:

1. **Resolve the position against the preview the author was reading, then confirm it from the
   picture.** Every insertion renumbers the deck under them, so "slide 6" means slide 6 *as of
   the last regeneration*. If the picture plainly is a remake of a slide that now sits elsewhere,
   follow the picture and say so. **Ask** when the instruction does not say *insert* or
   *replace* ("this should be slide 7" next to an existing slide 7). Those are different talks,
   and guessing costs a whole regeneration.
2. **Save the image under a filename, not a number.** A filename is the slide's identity; its
   number is only a position. Keep `assets/` sorting in slide order where you can (`s03a-`,
   `s03b-` …), and rename files with `git mv` when a swap would break the order.
3. **Read the picture against its spec, character by character, before writing anything.**
   Check every carved or lettered string against `Read back before accepting`. Check every
   closed constraint, every fact a picture asserts (a bit pattern, a register order, a line of
   code, a curve), and whether the letterform and tone match the rest of the deck. Report what
   is right as well as what is wrong. **A defect goes to the author as one batched list per
   round**: a generated frame cannot be patched, only remade, and batching is what keeps the
   cost of remakes linear. The desk never ships a picture with a factual error on its own
   initiative.
4. **Write the slide into `draft.md`.**
   - **Alt text describes what the picture SHOWS, not what the spec asked for.** For a slide
     whose words are the content, it transcribes them exactly. An alt that describes the
     intended image tells a screen-reader user something the room is not seeing.
     ([`ALT-TEXT.md`](../../docs/ALT-TEXT.md))
   - **Script the beat in the talk's voice**, under the voice's own checker. Introduce, then
     show: say what the room is looking at before saying what it means.
   - **Never refer to a slide by position in the script** ("the last picture", "two slides
     ago"). An insertion turns that into a true sentence about the wrong slide, and only reading
     the deck in order can find it. Name the thing instead.
   - **Re-read the neighbours' beats.** A beat written for the slide that used to sit here, or
     a line that set up a slide now cut, moves or goes with it.
5. **Regenerate, then check.**
   ```bash
   python3 framework/tools/img_deck.py talks/<slug> --check
   python3 framework/tools/img_deck.py talks/<slug> --md talks/<slug>/preview.md
   python3 framework/tools/img_deck.py talks/<slug> --map talks/<slug>/assets/SPECS.md
   ```
   Also run the voice's checker on the draft. Report the slide count, spoken words and minutes
   against `duration_min`. If the talk runs over, cut something; the budget moves only on the
   author's word, with the reason recorded in `talk.yaml`. Note which part of the talk grew,
   because a change of shape is a decision rather than a drift.
6. **Commit that slide on its own**, by path: the image, `draft.md`, `preview.md`, `SPECS.md`
   and the log. The message quotes the author's instruction and gives the new count and clock.
   One slide per commit is what lets a bad remake be undone without unpicking its neighbours.
7. **Append the log** (`log/<date>-….md`): the instruction verbatim, what was checked, what was
   decided and why, and anything left open.

**A spec fault goes into the spec, not into a re-roll.** When a picture comes back wrong
because the spec left something open (the letterform the first time), amend `SPECS.md` for
every affected picture at once, add the rule to the closed constraints, and record the lesson
in the style's `corrections.md`.

**A ruling covers the whole set.** When the author calls an inconsistency fine ("the serif font
is fine"), that holds while every frame it covered is still in the deck. Once half the set is
remade, raise it again. When the author's remakes keep overruling a closed constraint, strike
it through in `SPECS.md` and mark it overruled, keeping the reasoning, instead of deleting it.

## Publishing and republishing

On the author's word, and through the `publish` skill's gates:
`img_deck.py <talk> <out> --runtime <deck-stage.js>` (the desk keeps the PNG masters, and the
deck serves resized JPEGs) → `talk_bundle.py` → `store_publish.py --dry-run`, then the real
publish. Verify against the cache-busted reader URL. A live deck with a slide changed is
republished by the same three commands. Until then, the live page keeps serving the old deck,
so say so.

## Boundaries

- Never edit `preview.md`, the slide map, or `deck.html` by hand. All three are regenerated
  from `draft.md`.
- Never generate, alter, crop or retouch an image. Cropping can cut a carved word off the edge,
  and a fix is a remake by the author.
- Never number a spec. The number is a position and belongs only in the generated map.
