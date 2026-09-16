#!/usr/bin/env python3
"""Put a piece's composed body HTML on the system clipboard and paste it with a real ⌘V.

WHY THIS EXISTS
---------------
`md_to_substack.py` emits a self-contained JS snippet that carries the entire essay
baked into a string literal. Driving it means an agent reproducing every byte of that
snippet into a browser `javascript_exec` call — for a 5,700-word essay that is ~37KB of
the author's own prose, retyped. That makes the transcription the weakest link in the
chain: one wrong character diffs as a real edit and can publish a typo in the author's
voice. The guards downstream cannot see it, because to them a typo is just another edit.

The clipboard removes the agent from the transport entirely. The bytes go
disk -> macOS pasteboard -> Chrome -> ProseMirror, and are never retyped.

WHAT WORKS, AND WHAT DOES NOT (measured 2026-09-01)
---------------------------------------------------
  in-app browser pane + navigator.clipboard.read()  -> NotAllowedError: document not focused
  in-app browser pane + synthetic cmd+v             -> no-op, editor stays empty
  REAL Chrome + real click + real cmd+v             -> WORKS; h2/em/strong all survive

So this is used with the `claude-in-chrome` surface, not the in-app pane. Programmatic
`focus()` does not satisfy the Clipboard API; the click has to be a real one.

THE PASTEBOARD IS A SINGLETON, AND THIS TOOL NOW TREATS IT AS ONE (2026-09-08)
-------------------------------------------------------------------------------
Between loading the pasteboard and pressing ⌘V, any other process can take it. With several
desk sessions composing at once that is not a corner case: on 2026-09-07 one session lost the
pasteboard THREE times in one afternoon — a stranger's name and a broken asset landed in an
editor once; a stray quotation once; a re-check seconds before a paste found another session's
whole essay ("I. The Same Street") on the board. `--verify` immediately before the keystroke
was necessary and not sufficient, because the gap it guards is a full tool round-trip.

Two things close it, and this tool does both:

  1. A LEASE on the pasteboard (`lease.py`, slug `pasteboard`), acquired before the write and
     released after the paste. Every session that has ever taken the board mid-compose was
     another Claude session running this same tool, so an advisory lease is sufficient: the
     other session WAITS (`--wait`, default 120s) instead of clobbering. On timeout it reports
     who holds the lease and stops; it never breaks the lease itself.

  2. `--paste` collapses load → read-back → verify → keystroke into ONE process. The board is
     exposed for the milliseconds it takes to send ⌘V through System Events, not for the seconds
     an agent spends between tool calls. The keystroke goes to a Chrome tab this tool has FIRST
     raised and CHECKED (`--expect-url`): it finds the window and tab whose URL contains the
     expected string, makes that tab active and that window frontmost, reads the active tab's
     URL back, and refuses to press anything if it does not match. The editor still needs a
     REAL click for focus before this runs — `.focus()` from a script does not satisfy Chrome.

  Requires: macOS Accessibility permission for the app running this (Terminal, or the Claude
  desktop app) — System Settings → Privacy & Security → Accessibility. The first `--paste`
  fails with `osascript is not allowed to send keystrokes (1002)` until it is granted; the tool says
  so and nothing is pasted.

USAGE
-----
    # the body (HTML flavor), one process, atomic:
    python3 framework/tools/md_to_clipboard.py <piece-dir> --paste --expect-url publish/post/<id> [--fn-out notes.js]

    # any text payload the same way (the base64 footnote carrier):
    python3 framework/tools/md_to_clipboard.py --text-file payload.b64 --paste --expect-url publish/post/<id>

    # an inline HTML fragment over the editor's current selection (a link or italic added to a live run):
    python3 framework/tools/md_to_clipboard.py --html-file run.html --paste --expect-url publish/post/<id>

    # legacy two-step (load now, ⌘V from the browser tool later) — still lease-guarded:
    python3 framework/tools/md_to_clipboard.py <piece-dir> [--fn-out notes.js]   # holds the lease
    python3 framework/tools/md_to_clipboard.py <piece-dir> --verify                # right before ⌘V
    python3 framework/tools/md_to_clipboard.py --release                           # after the paste

Prints the same counts as `md_to_substack.py`, plus the SHA-256 of the HTML **read back off
the pasteboard** — evidence about the clipboard, not a hash of what this script hoped to put
there. Runs the identical preflight refusals (a stray "verify" note, nested footnote refs) —
this is a different transport, never a way around the gates.

Footnotes cannot travel as HTML by clipboard: a paste cannot create native Substack footnotes.
`--fn-out` writes the footnote-insertion snippet (keyed on the [[FNn]] markers the paste leaves
behind); `--fn-b64` writes the footnote DATA as one base64 line, which is what `--text-file
--paste` carries into the page for the insertion snippet to decode (see skills/publish).

PLATFORM
--------
macOS only today, and `set_clipboard_html` / `set_clipboard_text` / `press_paste` below are
the entire platform-specific surface -- everything else in this repo is platform-neutral.
Windows and Linux support is wanted and is a small, well-scoped contribution; see "Platform
support" in the README for sketches and for the one hard requirement: the payload must land
under the HTML clipboard *flavor*. Plain text is the trap -- it pastes, it looks like it
worked, and every heading, blockquote, italic and link is silently gone.
"""

import sys, os, json, hashlib, subprocess, base64, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md_to_substack import read_manifest, convert, manifest_gate  # noqa: E402
import lease as _lease                                           # noqa: E402

PASTEBOARD_SLUG = 'pasteboard'
DEFAULT_WAIT = 120.0
DEFAULT_APP = 'Google Chrome'

FN_TEMPLATE = """(() => {
  window.__sbFN = %FOOTNOTES%;
  const ed = document.querySelector('.ProseMirror').editor;
  const findToken = (doc, t) => { let f = null; doc.descendants((node, pos) => { if (f) return false; if (node.isText) { const i = node.text.indexOf(t); if (i >= 0) { f = { from: pos + i, to: pos + i + t.length }; return false; } } return true; }); return f; };
  let done = 0; const missing = [];
  for (const [n, c] of window.__sbFN) {
    const loc = findToken(ed.state.doc, '[[FN' + n + ']]');
    if (!loc) { missing.push(n); continue; }
    ed.chain().focus().setTextSelection(loc).deleteSelection().insertFootnote().run();
    ed.chain().insertContent(c).run();
    done++;
  }
  return JSON.stringify({ inserted: done, missing });
})()"""


def footnote_snippet(piece_dir, footnotes):
    """The --fn-out snippet behind the piece's account guard (substack_account.py): it writes into
    the editor, so it checks who is signed in first, in the same eval. Exits 9 if it cannot say."""
    import substack_account as sa
    return sa.guarded(piece_dir, FN_TEMPLATE.replace('%FOOTNOTES%', json.dumps(footnotes)),
                      'md_to_clipboard --fn-out')


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:16]


def _darwin_only():
    if sys.platform != 'darwin':
        sys.exit(
            'md_to_clipboard: macOS only -- this is the one platform-specific piece of the\n'
            'framework, and it has only ever been run on macOS.\n\n'
            'Right now, use the JS-snippet fallback documented in skills/publish/SKILL.md.\n'
            'Know that it is a real downgrade: it requires the agent to reproduce the whole\n'
            'essay into a browser eval, which is the transcription risk this tool exists to\n'
            'remove. Verify the composed post against the draft either way.\n\n'
            'Porting is small and welcome -- set_clipboard_html() is the whole surface. The\n'
            'payload must land under the HTML clipboard FLAVOR, not as plain text; plain text\n'
            'pastes cleanly and silently drops every heading, blockquote, italic and link.\n'
            '  Linux/X11:     xclip -selection clipboard -t text/html\n'
            '  Linux/Wayland: wl-copy --type text/html\n'
            '  Windows:       CF_HTML, which needs its own header with byte offsets\n'
            '                 (StartHTML/EndHTML/StartFragment/EndFragment) -- Set-Clipboard\n'
            '                 alone will not do it.\n'
            'See "Platform support" in the framework README.')


# ----------------------------------------------------------------------------- pasteboard I/O

def set_clipboard_html(html: str) -> None:
    """Put `html` on the macOS pasteboard under the HTML flavor.

    pbcopy only sets public.utf8-plain-text, which ProseMirror pastes as flat text --
    every heading, blockquote, link and italic would be lost. AppleScript's
    «data HTML<hex>» sets the real HTML flavor, which is what the paste handler reads.
    """
    _darwin_only()
    hexed = html.encode('utf-8').hex()
    # Passed via stdin, not argv: a 32KB essay overruns the command-line length limit.
    proc = subprocess.run(['osascript', '-'], input='set the clipboard to «data HTML%s»' % hexed,
                          text=True, capture_output=True)
    if proc.returncode != 0:
        sys.exit('md_to_clipboard: osascript failed: %s' % proc.stderr.strip())
    got = read_clipboard_html()
    if got is None:
        sys.exit('md_to_clipboard: the pasteboard has no HTML flavor after the write.\n'
                 'Nothing was placed. Do not paste — you would paste whatever was there before.')
    if got != html:
        sys.exit('md_to_clipboard: WROTE %d chars, PASTEBOARD HOLDS %d — the write did not take.\n'
                 '  intended sha256=%s\n  actual   sha256=%s\n'
                 'Another process almost certainly owns the pasteboard (a concurrent session, a\n'
                 'clipboard manager). Do NOT paste. Re-run once the pasteboard is yours.'
                 % (len(html), len(got), _sha(html), _sha(got)))


def read_clipboard_html():
    """Return the HTML flavor currently on the pasteboard, or None if there isn't one.

    This is the half that was missing until 2026-09-02. The old check asked whether the
    string "HTML" appeared in `clipboard info` and then reported the SHA-256 of the string
    it had *intended* to place. Neither is evidence about the pasteboard, and the gap is not
    theoretical: on 2026-09-02 the tool reported a clean write while the pasteboard actually
    held a footnote snippet from a DIFFERENT piece, left by a concurrent session. It pasted
    into a fresh Substack post and was caught only by a post-check. A hash of your own
    intent proves nothing; read the bytes back.
    """
    proc = subprocess.run(['osascript', '-e', 'the clipboard as «class HTML»'],
                          text=True, capture_output=True)
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    if not out.startswith('«data HTML') or not out.endswith('»'):
        return None
    try:
        return bytes.fromhex(out[len('«data HTML'):-1]).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        return None


def set_clipboard_text(text: str) -> None:
    """Put a plain-text payload on the pasteboard (the base64 footnote carrier) and read it back."""
    _darwin_only()
    proc = subprocess.run(['pbcopy'], input=text.encode('utf-8'), capture_output=True)
    if proc.returncode != 0:
        sys.exit('md_to_clipboard: pbcopy failed: %s' % proc.stderr.decode(errors='replace').strip())
    got = read_clipboard_text()
    if got != text:
        sys.exit('md_to_clipboard: text write did not take (wrote %d chars, board holds %d, '
                 'sha %s vs %s). Another process owns the pasteboard. Do NOT paste.'
                 % (len(text), len(got or ''), _sha(text), _sha(got or '')))


def read_clipboard_text():
    proc = subprocess.run(['pbpaste'], capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode('utf-8', errors='replace')


# ----------------------------------------------------------------------------- the keystroke

def raise_tab(expect_url: str, app: str = DEFAULT_APP) -> str:
    """Find the Chrome tab whose URL contains `expect_url`, make it the active tab of a
    frontmost window, and return the URL Chrome reports for the active tab afterwards.

    The keystroke goes to whatever is frontmost. Chrome routinely has several windows open
    (seven, measured 2026-09-08), and the automation tab group is not necessarily the front
    one; a ⌘V sent blind would land in the wrong page. So the tab is located BY URL and raised,
    and the caller compares what comes back against what it expected before pressing anything.
    """
    script = '''
tell application "%(app)s"
  set found to false
  set hit to ""
  repeat with w in windows
    set i to 0
    repeat with t in tabs of w
      set i to i + 1
      if (URL of t) contains "%(needle)s" then
        set active tab index of w to i
        set index of w to 1
        set found to true
        set hit to URL of t
        exit repeat
      end if
    end repeat
    if found then exit repeat
  end repeat
  if not found then return "NOTFOUND"
  activate
  delay 0.4
  return URL of active tab of front window
end tell''' % {'app': app.replace('"', ''), 'needle': expect_url.replace('"', '')}
    proc = subprocess.run(['osascript', '-'], input=script, text=True, capture_output=True)
    if proc.returncode != 0 and '-600' in proc.stderr:
        # "Application isn't running (-600)" was seen ONCE, transiently, seconds after Accessibility
        # was granted, with Chrome demonstrably running and answering the same script a moment later.
        # One retry after a beat; a second failure is real and is reported.
        time.sleep(1.0)
        proc = subprocess.run(['osascript', '-'], input=script, text=True, capture_output=True)
    if proc.returncode != 0:
        sys.exit('md_to_clipboard: could not address %s via AppleScript: %s' % (app, proc.stderr.strip()))
    return proc.stdout.strip()


def frontmost_app() -> str:
    proc = subprocess.run(['osascript', '-e',
                           'tell application "System Events" to get name of first application '
                           'process whose frontmost is true'], text=True, capture_output=True)
    return proc.stdout.strip() if proc.returncode == 0 else ''


def press_paste(app: str = DEFAULT_APP) -> None:
    """Send a REAL ⌘V to the frontmost app through System Events.

    This is the step that needs Accessibility permission. The error when it is missing is
    unmistakable (`not allowed to send keystrokes`, error 1002); surface it and stop — nothing
    has been pasted, and the pasteboard still holds the payload for a manual ⌘V.
    """
    front = frontmost_app()
    if front and app.split()[0].lower() not in front.lower():
        sys.exit('md_to_clipboard: refusing to press ⌘V — frontmost app is %r, not %r.' % (front, app))
    proc = subprocess.run(['osascript', '-e',
                           'tell application "System Events" to keystroke "v" using command down'],
                          text=True, capture_output=True)
    if proc.returncode != 0:
        sys.exit('md_to_clipboard: the keystroke was NOT sent: %s\n'
                 'If this says "not allowed to send keystrokes" (1002), grant Accessibility to the\n'
                 'app running this tool — the Claude desktop app or Terminal, whichever launched it\n'
                 '(System Settings → Privacy & Security → Accessibility) — then\n'
                 're-run. The pasteboard still holds the payload; the lease is released.'
                 % proc.stderr.strip())


# ----------------------------------------------------------------------------- lease helpers

def take_pasteboard(what: str, wait: float):
    ok, rec, waited = _lease.acquire_wait(PASTEBOARD_SLUG, what, timeout=wait)
    if not ok:
        sys.exit('md_to_clipboard: the pasteboard lease is HELD by %s (pid %s, %s) since %s and did '
                 'not free up in %.0fs. Waited; did not break it. Re-run, or `lease.py list`.'
                 % (rec.get('session'), rec.get('pid'), rec.get('what') or 'no note',
                    rec.get('acquired'), waited))
    if waited >= 1:
        print('pasteboard lease: acquired after waiting %.0fs' % waited)
    return rec


def drop_pasteboard():
    _lease.release(PASTEBOARD_SLUG)


def assert_pasteboard_mine():
    rec = _lease.read(PASTEBOARD_SLUG)
    if rec and not rec['mine']:
        sys.exit('md_to_clipboard: the pasteboard lease is held by %s (%s). Do NOT paste; wait or '
                 'coordinate.' % (rec.get('session'), rec.get('what') or 'no note'))


# ----------------------------------------------------------------------------- modes

def do_paste(read_back, expected: str, expect_url: str, app: str, label: str) -> None:
    """Raise the target tab, re-read the board, press ⌘V — the atomic tail of a --paste."""
    if not expect_url:
        sys.exit('md_to_clipboard: --paste needs --expect-url <substring of the editor URL> so the '
                 'keystroke can be aimed at a checked tab rather than whatever is frontmost.')
    url = raise_tab(expect_url, app)
    if url == 'NOTFOUND' or expect_url not in url:
        sys.exit('md_to_clipboard: no %s tab whose URL contains %r is frontmost (got %r). Nothing '
                 'pasted.' % (app, expect_url, url))
    got = read_back()                       # the last look before the keystroke
    if got != expected:
        sys.exit('md_to_clipboard: the pasteboard changed under the lease (%s → %s). Something is '
                 'writing it without taking the lease. Nothing pasted.'
                 % (_sha(expected), _sha(got or '')))
    # A REAL keystroke goes to the FRONTMOST app, so raising the window is the mechanism and not a
    # bug we can fix here. Say so before it happens, because the author is usually mid-sentence in
    # something else: on 2026-09-14 this raise took three characters of Eric's typing ("fix") into a
    # live Substack compose, where only the fidelity digest found them. The carrier + synthetic
    # paste needs no keystroke and no raise -- prefer it (publish SKILL.md, Transport).
    print('md_to_clipboard: RAISING %s to send a real Cmd-V — this steals focus, and anything you '
          'type in the next moment lands in the document. Prefer the window.name carrier + '
          'synthetic paste, which needs neither.' % app, file=sys.stderr)
    press_paste(app)
    time.sleep(0.3)
    print('pasted %s into %s (%s) — %d chars sha256=%s; the lease is released. NOW COUNT THE TOP '
          'NODES against the converter\'s own counts — a raised window can have taken a stray '
          'keystroke into the doc, and only the digest sees it.'
          % (label, app, url, len(expected), _sha(expected)))


def verify_only(piece_dir):
    """Re-check that the pasteboard still holds THIS piece's body, immediately before pasting."""
    _html, _fns, _st, residual, _unv, fn_issues = convert(piece_dir)
    if residual or fn_issues['nested'] or fn_issues['undefined'] or fn_issues['duplicated']:
        sys.exit('md_to_clipboard --verify: the piece no longer converts cleanly; re-run without '
                 '--verify to see the refusal.')
    assert_pasteboard_mine()
    got = read_clipboard_html()
    if got is None:
        sys.exit('STALE: the pasteboard has no HTML flavor. Do NOT paste — re-run to reload it.')
    if got != _html:
        sys.exit('STALE: the pasteboard does not hold this piece.\n'
                 '  expected %d chars sha256=%s\n  found    %d chars sha256=%s\n'
                 'Something took the pasteboard since it was loaded. Do NOT paste; re-run to reload.'
                 % (len(_html), _sha(_html), len(got), _sha(got)))
    print('OK: pasteboard holds %s — %d chars sha256=%s. Safe to paste.'
          % (piece_dir, len(got), _sha(got)))


def _opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith('--'):
            return sys.argv[i + 1]
        return True
    return default


def text_mode(path: str, paste: bool, expect_url: str, app: str, wait: float) -> None:
    text = open(path, encoding='utf-8').read().replace('\n', '')
    take_pasteboard('text payload %s (%s)' % (os.path.basename(path), _sha(text)), wait)
    try:
        set_clipboard_text(text)
        print('clipboard: %d chars of text  sha256=%s  (read back off the pasteboard)' % (len(text), _sha(text)))
        if paste:
            do_paste(read_clipboard_text, text, expect_url, app, 'text payload')
        else:
            print('holding the pasteboard lease; press ⌘V in the editor, then --release.')
            return                      # keep the lease for the legacy two-step
    finally:
        if paste:
            drop_pasteboard()


def html_mode(path: str, paste: bool, expect_url: str, app: str, wait: float) -> None:
    """Paste an inline HTML fragment over the editor's current selection, lease-guarded, one
    process. Select the old run in the editor first; the paste replaces it.

    MEASURED 2026-09-09 (In Vain, a live post): Substack's paste handler, given an inline-only
    fragment over a text selection, keeps the TEXT and DROPS EVERY MARK — `<a><em>…</em></a>`
    landed as plain text with `marks: []`. So this mode carries the words; the marks are then
    applied through the editor's own transaction API (`tr.addMark(from, to,
    schema.marks.link.create({href}))`, likewise `italic`), which is a URL and a range, not
    prose. A whole-body paste (block-level HTML) keeps its marks; only the inline-over-selection
    case strips them. There is no `setLink` command in Substack's Tiptap build."""
    html = open(path, encoding='utf-8').read().strip()
    take_pasteboard('html fragment %s (%s)' % (os.path.basename(path), _sha(html)), wait)
    try:
        set_clipboard_html(html)
        print('clipboard: %d chars of text/html  sha256=%s  (read back off the pasteboard)' % (len(html), _sha(html)))
        if paste:
            do_paste(read_clipboard_html, html, expect_url, app, 'html fragment')
        else:
            print('holding the pasteboard lease; press ⌘V in the editor, then --release.')
            return
    finally:
        if paste:
            drop_pasteboard()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    paste = '--paste' in sys.argv
    expect_url = _opt('--expect-url', '')
    app = _opt('--app', DEFAULT_APP)
    wait = float(_opt('--wait', DEFAULT_WAIT))

    if '--release' in sys.argv:
        ok, rec = _lease.release(PASTEBOARD_SLUG)
        print('released the pasteboard lease' if ok and rec else
              ('no pasteboard lease held' if ok else 'pasteboard lease is %s\'s, not this session\'s' % rec.get('session')))
        return

    html_file = _opt('--html-file')
    if html_file:
        return html_mode(html_file, paste, expect_url, app, wait)

    text_file = _opt('--text-file')
    if text_file:
        # --text-file consumes the positional slot in `args` if given as its argument; ignore args
        return text_mode(text_file, paste, expect_url, app, wait)

    if not args:
        sys.exit(__doc__)
    piece_dir = args[0].rstrip('/')
    if '--verify' in sys.argv:
        return verify_only(piece_dir)
    fn_out = _opt('--fn-out')
    fn_b64 = _opt('--fn-b64')

    man = read_manifest(os.path.join(piece_dir, 'publish.yaml'))
    # Same gates as a normal compose. A different transport is not a lower bar.
    gate_errors, gate_warnings = manifest_gate(piece_dir)
    for w in gate_warnings:
        print('WARNING: %s -- the author has not signed off on this line; make sure they '
              'read it in the editor before Publish.' % w)
    if gate_errors:
        sys.exit('REFUSING: %s. A post needs a title and a subtitle before it is composed; '
                 'add them to publish.yaml. There is no override.' % '; '.join(gate_errors))
    html, footnotes, stripped, residual, unverified, fn_issues = convert(piece_dir)

    if residual:
        sys.exit('REFUSING: %d block(s) still carry verify or clearance language after cleaning: %s\n'
                 '  A verify note: verify the claim, then put the note behind a dagger. Clearance '
                 'language (an ISO date, "consulted 2026-09-07"): move it to publish.yaml -> verified:. A desk '
                 'path (projects/..., facts.md): a reader cannot open it; cite a public URL or say it in words.'
                 % (len(residual), residual))
    if fn_issues['nested']:
        sys.exit('REFUSING: footnote reference(s) inside a footnote: %s. These publish as a '
                 'literal marker. Reword the note.' % fn_issues['nested'])
    if fn_issues['undefined'] or fn_issues['duplicated']:
        sys.exit('REFUSING: undefined=%s duplicated=%s — either desynchronizes footnote '
                 'indices for a later surgical re-sync.'
                 % (fn_issues['undefined'], fn_issues['duplicated']))

    if fn_out:
        js = footnote_snippet(piece_dir, footnotes)   # exits 9, before the pasteboard is touched
        with open(fn_out, 'w') as f:
            f.write(js)
        print('footnote snippet: %s (%d notes)' % (fn_out, len(footnotes)))
    if fn_b64:
        b = base64.b64encode(json.dumps(footnotes, ensure_ascii=False).encode('utf-8')).decode()
        with open(fn_b64, 'w') as f:
            f.write(b)
        print('footnote data (base64): %s (%d notes, %d chars, sha256=%s)' % (fn_b64, len(footnotes), len(b), _sha(b)))

    take_pasteboard('body of %s (%s)' % (piece_dir, _sha(html)), wait)
    try:
        set_clipboard_html(html)
        print('paragraphs~%d  headings~%d  dividers~%d  images~%d  footnotes~%d  '
              'editorial-notes-stripped~%d'
              % (html.count('<p>'), html.count('<h2>') + html.count('<h3>'),
                 html.count('<hr>'), html.count('<img'), len(footnotes), stripped))
        on_board = read_clipboard_html()   # re-read; this is evidence, the variable above is intent
        print('clipboard: %d chars of text/html  sha256=%s  (read back off the pasteboard)'
              % (len(on_board), _sha(on_board)))
        print('title:    %s' % json.dumps(man.get('title', '')))
        print('subtitle: %s' % json.dumps(man.get('subtitle', '')))
        if unverified:
            print('note: %d anchor(s) still carry a † marker' % len(unverified))
        if paste:
            do_paste(read_clipboard_html, html, expect_url, app, 'body of %s' % piece_dir)
        else:
            print()
            print('Holding the pasteboard lease. Next, in REAL Chrome (not the in-app pane):')
            print('  1. open the composer and set title/subtitle; REAL click into the body')
            print('  2. re-check, then a REAL cmd+v:  python3 framework/tools/md_to_clipboard.py %s --verify' % piece_dir)
            print('  3. release:                      python3 framework/tools/md_to_clipboard.py --release')
            print('  (or do all of it in one process next time: --paste --expect-url publish/post/<id>)')
    finally:
        if paste:
            drop_pasteboard()


if __name__ == '__main__':
    main()
