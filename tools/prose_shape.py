#!/usr/bin/env python3
"""prose_shape.py — measure the SHAPE of prose, not its words.

WHY THIS EXISTS.  A style constitution can forbid a phrase. It cannot forbid a
rhythm, because a rhythm has no spelling. The desk's voices are steered by 560
lines of rules and 3,733 lines of rationale, and the thing that still reads as
generic — clause rhythm, where a sentence puts its weight, how a paragraph
closes, whether paragraphs vary at all — is named nowhere, because nobody had a
way to say it. This says it in numbers.

AND IT SOLVES A LICENSING PROBLEM.  The two texture references for the
being-good voices are in copyright and cannot be committed. A MEASUREMENT of
them is not the text: a sentence-length distribution is a fact about the prose,
carries none of it, and is safe to check in. So the target shape ships even
though the books never can.

WHAT IT DOES NOT DO, SAID FIRST.  A shape match is not a voice match. Prose can
hit every number here and still say nothing worth reading, and two good voices
can share a profile. This narrows what to forbid and gives `style-audit`
something it can actually fail a draft on. It does not judge the writing.

USAGE
  prose_shape.py profile <file|dir> [<file|dir>…] [--name <label>] [--json]
                         [--no-dialogue]   # drop quoted speech: a fiction target
                                           # read through its characters is not a voice
  prose_shape.py compare <profile.json> <profile.json> [<profile.json>…]
  prose_shape.py check <style> <file|dir>…   # against styles/<style>/shape.yaml

Accepts .md / .txt directly and .pdf via pdftotext. A directory is walked for
*.md. In a piece's draft.md everything above the first `---` is scaffold and is
discarded, the same way the converter discards it.
"""
import json
import os
import re
import statistics
import subprocess
import sys

ABBREV = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc", "eg", "ie",
          "cf", "ca", "no", "vol", "pp", "ch", "fig", "al", "ibid"}

# ---------------------------------------------------------------- loading

def read_text(path):
    if path.lower().endswith(".pdf"):
        out = subprocess.run(["pdftotext", path, "-"], capture_output=True)
        return out.stdout.decode("utf-8", "replace")
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def strip_markdown(text, is_draft=False):
    # A piece's scaffold note lives above the first ---; the converter drops it.
    if is_draft and "\n---" in text:
        text = text.split("\n---", 1)[1]
    text = re.sub(r"```.*?```", " ", text, flags=re.S)        # code fences
    text = re.sub(r"^\s{0,3}#{1,6} .*$", " ", text, flags=re.M)  # headings
    text = re.sub(r"^\s{0,3}>.*$", " ", text, flags=re.M)     # block quotes
    # A footnote DEFINITION runs from its label to the next blank line, and on this corpus
    # it is routinely four or five lines of scholarly prose — loci, editions, parenthetical
    # caveats, semicolon chains. Stripping only the label's own line left the continuation
    # lines in the sample and measured a reader-invisible apparatus as if it were the voice:
    # it depressed burstiness, and it inflated the parenthesis and tricolon rates, because
    # that is exactly how a citation is punctuated. Caught 2026-11-02 on a piece with 32
    # footnotes, after the first version of this tool had reported on it twice.
    text = re.sub(r"(?ms)^[ \t]*\[\^[^\]]+\]:.*?(?=\n[ \t]*\n|\Z)", " ", text)
    text = re.sub(r"\[\^[^\]]+\]", "", text)                  # footnote marks
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)         # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)      # links -> label
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)       # html comments
    text = re.sub(r"<[^>]+>", " ", text)                      # tags
    text = re.sub(r"[*_`#]+", "", text)                       # emphasis marks
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)      # bullets
    return text


DIALOGUE = re.compile(r"[\u201c\"][^\u201c\u201d\"]{0,400}?[\u201d\"]")


def strip_dialogue(text):
    """Drop quoted speech. A novel's question rate and paragraph shape are mostly its
    characters talking, which says nothing about a narrating voice. July in particular
    writes unquoted dialogue as its own short lines, so a line that is bare speech with
    no sentence punctuation goes too."""
    text = DIALOGUE.sub(" ", text)
    keep = []
    for line in text.split("\n"):
        t = line.strip()
        if t and len(t.split()) <= 12 and not re.search(r"[.;:]", t) and (
                t.endswith("?") or t.endswith("!") or not re.search(r"[.!?]$", t)):
            continue
        keep.append(line)
    return "\n".join(keep)


def paragraphs(text):
    out = []
    for block in re.split(r"\n\s*\n", text):
        block = " ".join(block.split())
        if len(block) > 40 and re.search(r"[.!?]", block):
            out.append(block)
    return out


def sentences(para):
    # Split on terminal punctuation followed by space + capital/quote, holding
    # back the common abbreviations so "Mr. Novak" is not two sentences.
    parts, buf = [], ""
    tokens = re.split(r"([.!?]+[\"')”]*\s+)", para)
    for i in range(0, len(tokens), 2):
        chunk = tokens[i]
        delim = tokens[i + 1] if i + 1 < len(tokens) else ""
        buf += chunk + delim
        last = re.findall(r"([A-Za-z]+)[.!?]*[\"')”]*\s*$", chunk)
        if last and last[-1].lower() in ABBREV:
            continue
        if delim or i + 1 >= len(tokens):
            s = buf.strip()
            if s:
                parts.append(s)
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    return [s for s in parts if len(s.split()) >= 2]


def words(s):
    return re.findall(r"[A-Za-z'’-]+", s)

# ---------------------------------------------------------------- shapes

CONJ_OPEN = {"and", "but", "so", "yet", "or", "because", "nor", "for", "still", "then"}
TRICOLON = re.compile(r"\b[\w'’-]+(?:\s+[\w'’-]+){0,3},\s+[\w'’-]+(?:\s+[\w'’-]+){0,3},\s+and\s+", re.I)
ANTITHESIS = re.compile(r"\b(?:not|isn't|is not|aren't|wasn't|never)\b[^.;!?]{3,60}?(?:[,—-]\s*|\s+but\s+)(?:it'?s\s+|it is\s+|they'?re\s+|but\s+)", re.I)


def pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


def profile(paths, label, no_dialogue=False):
    paras, src = [], []
    for p in paths:
        files = []
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                files += [os.path.join(root, n) for n in sorted(names)
                          if n.endswith(".md") and n != "README.md"]
        else:
            files = [p]
        for f in files:
            if not os.path.isfile(f):
                print(f"skip (no such file): {f}", file=sys.stderr)
                continue
            is_draft = os.path.basename(f) == "draft.md"
            raw = strip_markdown(read_text(f), is_draft)
            if no_dialogue:
                raw = strip_dialogue(raw)
            got = paragraphs(raw)
            if got:
                paras += got
                src.append(os.path.basename(f))

    sents, per_para, finals = [], [], []
    for para in paras:
        ss = sentences(para)
        if not ss:
            continue
        lens = [len(words(s)) for s in ss]
        sents += list(zip(ss, lens))
        per_para.append(len(ss))
        if len(ss) >= 2:
            finals.append((lens[-1], statistics.mean(lens[:-1])))

    if len(sents) < 20:
        sys.exit(f"{label}: only {len(sents)} sentences found — not enough to profile")

    lens = [n for _, n in sents]
    allw = sum(lens)
    k = allw / 1000.0
    text_all = " ".join(s for s, _ in sents)
    openers = sum(1 for s, _ in sents if (words(s) or [""])[0].lower() in CONJ_OPEN)
    commas = sum(s.count(",") for s, _ in sents)

    return {
        "name": label,
        "files": len(src),
        "paragraphs": len(paras),
        "sentences": len(sents),
        "words": allw,
        # --- the headline: does the line length move?
        "sent_mean": round(statistics.mean(lens), 1),
        "sent_median": statistics.median(lens),
        "sent_stdev": round(statistics.pstdev(lens), 1),
        "burstiness": round(statistics.pstdev(lens) / statistics.mean(lens), 3),
        "pct_short_le5": pct(sum(1 for n in lens if n <= 5), len(lens)),
        "pct_long_ge35": pct(sum(1 for n in lens if n >= 35), len(lens)),
        "sent_p10": sorted(lens)[len(lens) // 10],
        "sent_p90": sorted(lens)[len(lens) * 9 // 10],
        # --- paragraph architecture
        "para_sent_mean": round(statistics.mean(per_para), 2),
        "pct_one_sentence_para": pct(sum(1 for n in per_para if n == 1), len(per_para)),
        # negative = the paragraph snaps shut shorter than it ran
        "para_final_delta": round(statistics.mean([f - m for f, m in finals]), 1) if finals else None,
        # --- clause weight
        "commas_per_sent": round(commas / len(sents), 2),
        "emdash_per_1k": round(text_all.count("—") / k, 1),
        "semicolon_per_1k": round(text_all.count(";") / k, 1),
        "colon_per_1k": round(text_all.count(":") / k, 1),
        "paren_per_1k": round(text_all.count("(") / k, 1),
        "question_per_1k": round(text_all.count("?") / k, 1),
        # --- the two default-register tells
        "tricolon_per_1k": round(len(TRICOLON.findall(text_all)) / k, 2),
        "antithesis_per_1k": round(len(ANTITHESIS.findall(text_all)) / k, 2),
        # --- openers
        "pct_opener_conj": pct(openers, len(sents)),
    }

KEYS = ["sent_mean", "sent_median", "sent_stdev", "burstiness", "pct_short_le5",
        "pct_long_ge35", "sent_p10", "sent_p90", "para_sent_mean",
        "pct_one_sentence_para", "para_final_delta", "commas_per_sent",
        "emdash_per_1k", "semicolon_per_1k", "colon_per_1k", "paren_per_1k",
        "question_per_1k", "tricolon_per_1k", "antithesis_per_1k",
        "pct_opener_conj"]


def show(p):
    print(f"\n{p['name']}  — {p['files']} file(s), {p['paragraphs']} paras, "
          f"{p['sentences']} sentences, {p['words']:,} words")
    for key in KEYS:
        print(f"  {key:<24} {p[key]}")


def compare(profs):
    width = max(len(p["name"]) for p in profs)
    head = "  ".join(f"{p['name'][:14]:>14}" for p in profs)
    print(f"\n{'':<24}  {head}")
    print(f"{'':<24}  " + "  ".join(f"{'-'*14}" for _ in profs))
    for key in KEYS:
        row = "  ".join(f"{str(p.get(key)):>14}" for p in profs)
        print(f"{key:<24}  {row}")
    print()



# ---------------------------------------------------------------- the gate

def check(style, paths):
    """Measure prose against its style's shape target. Exit 3 if a band is missed, so a
    preflight can refuse. Only the `targets` block is enforced — `excluded` metrics are
    measured and printed without a verdict, because the file says why they are not
    transferable and a gate that quietly enforced them would be chasing genre."""
    try:
        import yaml
    except ImportError:
        sys.exit("check: PyYAML missing; pip install pyyaml")
    cfg_path = os.path.join("styles", style, "shape.yaml")
    if not os.path.exists(cfg_path):
        sys.exit(f"no shape target: {cfg_path}\n"
                 f"  This style is steered by rules alone. `prose_shape.py profile` on the "
                 f"target texts, then write one.")
    with open(cfg_path) as fh:
        cfg = yaml.safe_load(fh) or {}
    targets = cfg.get("targets") or {}
    p = profile(paths, style)

    print(f"\n{p['name']} — {p['sentences']} sentences, {p['words']:,} words")
    print(f"  against {cfg_path}\n")
    miss = []
    for key, spec in targets.items():
        band = spec.get("target")
        got = p.get(key)
        if band is None or got is None:
            continue
        lo, hi = band
        # A ceiling-only metric. On a low-count figure — a tricolon or an antithesis is a
        # handful of instances in six thousand words — per-piece noise swamps the signal,
        # and a floor would order a draft to ADD the construction we are trying to thin.
        # Measured on they-them: tricolon 0.97 against a corpus mean of 2.23. Only the
        # ceiling is evidence.
        if spec.get("direction") == "max":
            lo = float("-inf")
        ok = lo <= got <= hi
        mark = "ok  " if ok else "MISS"
        arrow = ""
        if not ok:
            arrow = "  (too low)" if got < lo else "  (too high)"
            miss.append((key, got, band[0] if spec.get("direction") != "max" else None,
                         hi, spec.get("governs"), spec.get("from")))
        shown = f"[<= {hi}]" if spec.get("direction") == "max" else f"[{band[0]}, {hi}]"
        print(f"  {mark} {key:<24} {got:>8}   band {shown}{arrow}")

    ex = cfg.get("excluded") or {}
    if ex:
        print("\n  measured, not enforced (genre rather than register):")
        for key in ex:
            print(f"       {key:<24} {str(p.get(key)):>8}")

    if not miss:
        print("\n  Every enforced band met. That is a floor, not a verdict: this says the "
              "lines stop\n  being uniform, never that the writing is good.\n")
        return 0
    print(f"\n  {len(miss)} band(s) missed:\n")
    for key, got, lo, hi, governs, frm in miss:
        d = "cut" if lo is None or got > hi else "lift"
        rng = f"<= {hi}" if lo is None else f"[{lo}, {hi}]"
        print(f"    {key}: {got} -> {d} to {rng}"
              + (f"; corpus baseline was {frm}" if frm is not None else "")
              + (f"; model is {governs}" if governs else ""))
    print()
    return 3


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd = argv[1]
    if cmd == "profile":
        args = argv[2:]
        label, as_json, paths, nodlg = None, False, [], False
        i = 0
        while i < len(args):
            if args[i] == "--name":
                label = args[i + 1]; i += 2
            elif args[i] == "--json":
                as_json = True; i += 1
            elif args[i] == "--no-dialogue":
                nodlg = True; i += 1
            else:
                paths.append(args[i]); i += 1
        if not paths:
            sys.exit("profile: no input paths")
        p = profile(paths, label or os.path.basename(paths[0].rstrip("/")), nodlg)
        print(json.dumps(p, indent=2)) if as_json else show(p)
    elif cmd == "check":
        if len(argv) < 4:
            sys.exit("check: need a style and at least one path")
        return check(argv[2], argv[4:] and argv[3:] or argv[3:])
    elif cmd == "compare":
        profs = []
        for f in argv[2:]:
            with open(f) as fh:
                profs.append(json.load(fh))
        if not profs:
            sys.exit("compare: no profiles")
        compare(profs)
    else:
        sys.exit(f"unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    sys.exit(main(sys.argv) or 0)
