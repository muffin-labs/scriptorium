#!/usr/bin/env python3
"""substack_account.py — which browser a Substack operation runs in, and is it the right person?

WHY (2026-09-11).  A desk can own several Substack outlets on different accounts — one per
byline, because a Substack profile has one display name across every publication under it. The
built-in pane's cookie store is shared by every tab and every session: a cookie set in one pane
tab was present in a fresh one, and a session that had never signed in found the pane signed in
as the other session's account. So signing the pane out, or into another account, silently turns
every concurrent session's work into the other byline's — and THAT rule stands unchanged.

WHAT WAS WRONG WITH IT (measured 2026-11-03).  This file used to conclude from the shared cookie
store that "the pane can hold one Substack account, never two". It holds both. Two `profile/self`
fetches, nothing signed in or out: `elmuffin.substack.com` answered `elmuffin`,
`muffinlabs.substack.com` answered `ericgarciaphd`. SUBSTACK RESOLVES THE ACCOUNT PER
PUBLICATION. There is no switching between them, and therefore no byline to lose. What believing
otherwise cost: `scaling-computer-vision-workflows-aws` sat one block behind its live post from
2026-09-18 to 2026-11-02, and the work was filed as *blocked on a surface this desk does not
have*. It was not blocked; the pane did it in one pass as soon as the assumption was checked
instead of quoted.

THE RULE (amended 2026-11-03).  THE ACCOUNT IS THE GATE; THE SURFACE IS A PREFERENCE. What makes
a write safe is that the account is settled by a same-origin fetch against THE OUTLET'S OWN
PUBLICATION HOST immediately before the write, and that the snippet re-checks it in the same eval
as the work (`guard_js`). So: a wrong account is a refusal wherever it is found (exit 5). A right
account on a surface the table did not route to is a PASS, with a note (exit 0) — the table is a
static assertion, and it was overruling a measurement.

`substack_primary:` is therefore a PREFERENCE: it says which surface to reach for first — the
pane for the primary, a named Chrome browser for an outlet that wants one of its own — and
nothing is refused for being on the other. It is still worth declaring, because reaching for the
right surface first is cheaper than discovering the wrong one.

This is NOT "any account works anywhere". An outlet is written only from a page on its own
publication, signed in as its own handle, proven per write. That is what made the MuffinLabs
re-sync safe from the pane; the table was not.

CONFIG (instance-side, publishing/outlets.yaml; the framework holds no handles)

    substack_primary: substack            # top level — names exactly one Substack outlet
    outlets:
      substack:
        reader_base: https://elmuffin.substack.com/p/
        account_handle: elmuffin          # the profile handle that must be signed in to write
        chrome_browser: <name>            # optional: a surface of its own, never a permission
      substack-muffinlabs:
        reader_base: https://muffinlabs.substack.com/p/
        account_handle: ericgarciaphd
        chrome_browser: eric@muffinlabs.ai   # where to reach for it first; the pane works too

  A Substack outlet is one whose `reader_base` is on `*.substack.com`, or that says
  `platform: substack` (a custom domain). With only one Substack outlet it is the primary without
  saying so. `account_handle` is REQUIRED to write: `notes_handle` names the same person today,
  but it is a Notes-feed display setting, never a write permission.

USAGE
    substack_account.py route <outlet>          # which surface to reach for FIRST, its account, the snippet
    substack_account.py primary                 # the primary, and where every Substack outlet runs
    substack_account.py primary <outlet>        # make <outlet> the primary (edits outlets.yaml)
    substack_account.py check <outlet> --surface pane|chrome --result '<the snippet's JSON>'
    substack_account.py snippet

  Run the snippet on any `*.substack.com` page of that surface — the publication's own host, where
  the editor lives, is fine. It must be SAME-ORIGIN: a fetch from a publication host to
  substack.com fails in the pane (measured), so the snippet uses a relative path.

  `check` takes the snippet's answer VERBATIM, never a handle typed in: a typed handle can pass
  without the snippet ever running. The answer carries its origin and HTTP status, so `check` also
  refuses one read on a page that is neither the outlet's own nor Substack's, and treats only a
  401/403 as signed out — a 404 or 5xx says nothing about who is signed in.

  THE GUARD IN EVERY SNIPPET.  `check` confirms the account ONCE. But the pane's cookie store is
  shared by every tab and every session, so another session can switch the pane's login between
  that check and the write — and the write lands under the wrong byline, with no error. So every
  generated script that reads or writes a Substack editor or its API opens with `guard_js`: the
  same same-origin profile fetch as the snippet, run IN THE SAME EVAL as the work, which returns
  `{"refused": …, "accountGuard": true, …}` before the document is touched unless the page is the
  outlet's own publication AND is signed in as its `account_handle`. The PUBLICATION half matters
  because one account can own several publications: the handle would match and the post would be
  the wrong one. `guard_for_piece` settles which Substack outlet a piece writes to (its publish.yaml
  `outlets:`, via outlets.yaml); a generator that cannot settle it writes nothing (exit 9). `wrap`
  makes a snippet one promise-valued expression, so the javascript_tool REPL, a `<script>` that
  assigns it to a global, and a test harness's `await eval(...)` all get its return value.

    substack_account.py guard <piece-dir>        # the outlet and account a piece's snippets insist on

  FINDING THE CHROME BROWSER.  `chrome_browser` is the name the browser was given at Claude in
  Chrome's Connect prompt — until someone names it, list_connected_browsers shows "Browser 1/2/3".
  So: list_connected_browsers; select_browser the one named EXACTLY as outlets.yaml says; if it is
  not there, switch_browser and give it exactly that name. Never pick one by guessing from the
  list, and ask the author before driving a browser.

EXIT
  0  ok — signed in as the outlet's account, on the outlet's surface (or: primary changed)
  1  usage, or no such outlet
  3  signed out — the author signs in (automation never enters credentials)
  4  RETIRED 2026-11-03, and never returned. It meant "checked on the wrong surface", and it
     refused a correct account because the routing table pointed elsewhere. The surface is a
     preference; off-preference with the right account is exit 0 with a note
  5  signed in as SOMEONE ELSE — stop; do not write here, and do not switch this surface
  6  misconfigured — no account_handle, several Substack outlets and no primary, a non-primary
     with no chrome_browser, or a demotion that would leave an outlet nowhere to run
  7  the answer settles nothing — not the snippet's JSON, read on a page that is neither the
     outlet's nor Substack's, or an HTTP status other than 401/403. Run the snippet again on the
     right page; do NOT send the author off to sign in
  9  (guard, and every snippet generator) the piece's Substack account cannot be settled — no
     outlets.yaml, no Substack outlet in its `outlets:`, two of them, or no account_handle
"""
import argparse
import json
import os
import re
import sys
import tempfile
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    yaml = None

# One expression, so a browser tool can evaluate it and return the result. Relative path on
# purpose: see USAGE.
SNIPPET = (
    "await (async () => { const r = await fetch('/api/v1/user/profile/self', "
    "{credentials: 'include'}); if (r.status !== 200) return {signed_in: false, "
    "status: r.status, origin: location.origin}; const j = await r.json(); "
    "return {signed_in: true, handle: j.handle, name: j.name, origin: location.origin}; })()"
)
PRIMARY_KEY = 'substack_primary'
# The only HTTP answers that mean nobody is signed in. Anything else — a 404, a 5xx — says nothing
# about who is, and must not send the author off to sign in for nothing.
SIGNED_OUT = (401, 403)


def load(path):
    """The whole registry: {'outlets': {...}, 'substack_primary': ...}."""
    if yaml is None:
        raise SystemExit("substack_account: pyyaml is required")
    with open(path, encoding='utf-8') as fh:
        doc = yaml.safe_load(fh) or {}
    doc.setdefault('outlets', {})
    doc['outlets'] = doc['outlets'] or {}
    return doc


def norm(handle):
    return str(handle or '').strip().lstrip('@').lower()


def expected(spec):
    """The handle allowed to WRITE to this outlet: `account_handle`, and only that. `notes_handle`
    names the same person today, but it is a display setting and does not authorise a write."""
    return norm((spec or {}).get('account_handle')) or None


def shown(spec):
    """For display only: `account_handle`, else `notes_handle`."""
    spec = spec or {}
    return norm(spec.get('account_handle') or spec.get('notes_handle')) or None


def origin_ok(spec, origin):
    """Is an answer read on `origin` about this outlet's account?

    ONLY ON THE OUTLET'S OWN PUBLICATION (tightened 2026-11-03). This used to accept any
    *.substack.com page, on the premise that one login cookie covers them all. The cookie does;
    THE ANSWER DOES NOT. `profile/self` is resolved PER PUBLICATION — measured the same day,
    nothing signed in or out: `elmuffin.substack.com` answered `elmuffin` and
    `muffinlabs.substack.com` answered `ericgarciaphd`. So a handle read on one publication says
    nothing about who you are on another, and `check` now insists on the host the write will run
    against — which is what `guard_js` already insisted on in the same eval as the work."""
    host = urlparse(str(origin or '')).hostname or ''
    hosts = publish_hosts(spec)
    if not hosts:
        # A custom-domain publication whose `*.substack.com` host nobody has recorded: the account
        # alone, exactly as `guard_js` falls back. Name `publish_host:` to get the stricter check.
        return bool(host) and (host == 'substack.com' or host.endswith('.substack.com'))
    return host in hosts


def browser_steps(chrome_browser):
    """How to reach a named Claude in Chrome browser without guessing (see FINDING THE CHROME BROWSER)."""
    n = repr(chrome_browser)
    return [f"list_connected_browsers — find the browser named exactly {n}",
            f"select_browser {n} (ask the author before driving it) — never pick one by guessing from the list",
            f"not listed? switch_browser, and at the Connect prompt name it exactly {n}, as outlets.yaml does",
            # Measured 2026-10-15: the extension listed "Browser 1" and "Browser 2" — names nothing
            # on the desk sets — and the outlet's browser was found only by its sign-in. The name is
            # a convenience; the ACCOUNT is the proof, and `check` already refuses the wrong one.
            "no browser carries that name (the extension may number them)? then the account decides, "
            "not the label: on each connected browser in turn, open the outlet's /publish/home and run "
            "the snippet below; the one `check` passes (exit 0) is the one. Never write to a browser "
            "`check` has not passed, and if none passes, the author signs in — never you"]


def is_substack(spec):
    spec = spec or {}
    if spec.get('platform') == 'substack':
        return True
    host = urlparse(str(spec.get('reader_base') or '')).hostname or ''
    return host == 'substack.com' or host.endswith('.substack.com')


def substack_outlets(doc):
    return [n for n, s in doc['outlets'].items() if is_substack(s)]


def primary(doc):
    """-> (name or None, problem or None)."""
    subs = substack_outlets(doc)
    declared = doc.get(PRIMARY_KEY)
    if declared:
        if declared not in doc['outlets']:
            return None, f"{PRIMARY_KEY}: {declared!r} is not an outlet"
        if declared not in subs:
            return None, f"{PRIMARY_KEY}: {declared!r} is not a Substack outlet"
        return declared, None
    if len(subs) == 1:
        return subs[0], None
    if not subs:
        return None, "no Substack outlets"
    return None, (f"{len(subs)} Substack outlets ({', '.join(subs)}) and no {PRIMARY_KEY} — "
                  f"name one: substack_account.py primary <outlet>")


def route(doc, name):
    """-> dict, or None for an unknown outlet. `problem` is set when it cannot be run anywhere."""
    spec = doc['outlets'].get(name)
    if spec is None:
        return None
    prim, problem = primary(doc)
    is_primary = (name == prim)
    r = {'outlet': name, 'account': expected(spec), 'primary': is_primary,
         # Where to REACH FIRST — never what permits the write, which is the account (2026-11-03).
         'surface': 'pane' if is_primary else 'chrome',
         'surface_is_preference': True,
         'chrome_browser': (spec or {}).get('chrome_browser'),
         'problem': None, 'note': None, 'snippet': SNIPPET, 'browser_steps': []}
    if not is_substack(spec):
        r['problem'] = f"{name} is not a Substack outlet"
    elif problem and prim is None:
        r['problem'] = problem
    elif not is_primary and not r['chrome_browser']:
        # Was exit 6, "nowhere to run". The pane resolves every publication's account at once, so
        # it HAS somewhere to run: there.
        r['note'] = (f"{name} is not the primary and names no chrome_browser, so reach for the "
                     f"built-in pane — it resolves @{r['account']} on {name}'s own publication. "
                     f"Name a chrome_browser in outlets.yaml to give it a surface of its own.")
        r['surface'] = 'pane'
    if not is_primary and r['chrome_browser']:
        r['browser_steps'] = browser_steps(r['chrome_browser'])
    return r


def verdict(doc, name, result, surface):
    """-> (exit code, message). `result` is the snippet's own answer (a dict), exactly as the
    browser returned it — never a handle typed in; `surface` is where it ran, 'pane' or 'chrome'."""
    r = route(doc, name)
    if r is None:
        return 1, f"no outlet {name!r} in the registry"
    if surface not in ('pane', 'chrome'):
        return 1, "say where the snippet ran: --surface pane|chrome"
    if r['problem']:
        return 6, r['problem']
    spec = doc['outlets'][name]
    want = r['account']
    if not want:
        why = (f" (its notes_handle @{shown(spec)} is a display setting, not a write permission)"
               if shown(spec) else "")
        return 6, (f"{name} names no account_handle{why} — refusing rather than assuming who may "
                   f"write there. Add one to outlets.yaml.")
    # The account is read FIRST and the surface only noted (2026-11-03). This used to return 4
    # right here, before looking at the answer at all — refusing a correct account because a
    # static table said the outlet lived on the other surface.
    prefers = ("the built-in pane (it is the primary)" if r['surface'] == 'pane'
               else f"Claude in Chrome, browser {r['chrome_browser']!r}")
    where = "the built-in pane" if surface == 'pane' else "Claude in Chrome"
    if not isinstance(result, dict) or 'signed_in' not in result or 'origin' not in result:
        return 7, ("that is not the snippet's answer. Run `route`'s snippet in that browser and pass "
                   "its JSON verbatim — a handle typed in proves nothing.")
    own = ' / '.join(publish_hosts(spec)) or '(no *.substack.com host recorded — add publish_host:)'
    if not origin_ok(spec, result.get('origin')):
        return 7, (f"the snippet ran on {result.get('origin')!r}, which is not {name}'s own "
                   f"publication. Substack resolves the account PER PUBLICATION, so an answer "
                   f"read anywhere else settles nothing about who you are here. Run it on {own}.")
    if not result.get('signed_in'):
        status = result.get('status')
        if status in SIGNED_OUT:
            return 3, (f"signed out in {where} (HTTP {status}). {name} needs @{want}; the author "
                       f"signs in — automation never enters credentials.")
        return 7, (f"the profile check answered HTTP {status}, which says nothing about who is "
                   f"signed in. Reload {own} and run the snippet again — do not ask the author to "
                   f"sign in.")
    got = norm(result.get('handle'))
    if not got:
        return 7, "the answer says signed in but carries no handle — run the snippet again"
    if got != want:
        return 5, (f"STOP: {where} is signed in as @{got}, and {name} needs @{want}. Do not write, "
                   f"and do not sign this surface into another account — "
                   + ("every session shares the pane's login." if surface == 'pane'
                      else "fix the browser's login, or the outlet's chrome_browser."))
    ok = f"ok: {where} is signed in as @{got}, the account {name} publishes as"
    if surface != r['surface']:
        ok += (f". Note: {name} prefers {prefers}, which is a PREFERENCE and not a permission — "
               f"the account is what permits the write, and it checks out. Proceed here, and "
               f"write from the surface you just checked, not the other one")
    return 0, ok


# ------------------------------------------------------------------ the guard in every snippet
GUARD_MARK = '/* desk-account-guard v1 */'
NO_ACCOUNT_EXIT = 9


class NoAccount(Exception):
    """A piece's Substack account cannot be settled, so no snippet may be generated for it."""


def publish_hosts(spec, man=None):
    """The `*.substack.com` host(s) this outlet's editor and API live on: its `reader_base`, an
    explicit `publish_host:`, and the piece's own `post_url`.

    ONE ACCOUNT CAN OWN SEVERAL PUBLICATIONS, and the handle check cannot see the difference: the
    same byline, the wrong publication. The host can, because a write is relative to the page it
    runs on. A custom-domain publication whose editor host nobody has recorded yields NONE, and the
    guard then checks the account alone — name `publish_host:` in outlets.yaml to get the check."""
    out = []
    for u in ((spec or {}).get('reader_base'), (spec or {}).get('publish_host'),
              (man or {}).get('post_url')):
        u = str(u or '')
        h = _host(u if u.startswith('http') else 'https://' + u)
        if h.endswith('.substack.com'):
            out.append(h)
    return sorted(set(out))


def guard_js(spec, outlet=None, hosts=None):
    """A JS async function (an expression) resolving to null when this page is the outlet's own
    publication AND is signed in as its `account_handle`, else to an abort object. The fetch is
    SNIPPET's, relative on purpose: a cross-origin fetch fails in the pane. Anything but a 200
    carrying that handle — signed out, someone else, a 404, a throw — aborts: a guard that is
    unsure does not let the write through. The host is checked FIRST, and locally: a snippet opened
    on another publication stops without so much as a fetch."""
    want = expected(spec)
    if not want:
        raise NoAccount(f"{outlet or 'this outlet'} names no account_handle — refusing rather than "
                        f"assuming who may write there. Add one to outlets.yaml.")
    return (GUARD_MARK + " (async () => {\n"
            f"  const WANT = {json.dumps(want)}, OUTLET = {json.dumps(outlet or '')}, "
            f"HOSTS = {json.dumps(sorted(set(hosts or [])))};\n"
            "  const here = typeof location !== 'undefined' ? location : {};\n"
            "  const origin = here.origin || '';\n"
            "  const stop = (why, extra) => Object.assign({ refused: why + ' - nothing was read or "
            "written', accountGuard: true, outlet: OUTLET, want: WANT, origin }, extra || {});\n"
            "  if (HOSTS.length && HOSTS.indexOf(here.hostname) < 0)\n"
            "    return stop('publication: this page is ' + (here.hostname || '?') + ', and ' + OUTLET"
            " + ' publishes at ' + HOSTS.join(' / ') + ' - open the post there', "
            "{ host: here.hostname || '' });\n"
            "  let r;\n"
            "  try { r = await fetch('/api/v1/user/profile/self', { credentials: 'include' }); }\n"
            "  catch (e) { return stop('account: the profile check could not run (' + e + ')'); }\n"
            "  if (r.status !== 200) return stop('account: this page is not signed in as @' + WANT + "
            "' (HTTP ' + r.status + ')', { status: r.status });\n"
            "  let j = null;\n"
            "  try { j = await r.json(); } catch (e) { return stop('account: the profile answer is not JSON'); }\n"
            "  const got = String((j && j.handle) || '').trim().replace(/^@/, '').toLowerCase();\n"
            "  if (got !== WANT) return stop('account: signed in as @' + (got || '?') + ', and ' + OUTLET + "
            "' publishes as @' + WANT + ' - do not switch this browser to another login', { got });\n"
            "  return null;\n"
            "})")


def wrap(js, guard):
    """`js` (one expression: a sync IIFE, an async one, or `await (async …)()`) behind `guard`, as
    ONE promise-valued expression with no top-level await. The guard runs first, in the same eval;
    on a refusal it returns the abort as a JSON string, the shape every snippet here returns, and
    `js` is never evaluated. Inside `js`, `__deskAccount` is the guard, for a function the snippet
    leaves behind to call later (md_to_substack's footnote pass)."""
    body = js.strip().rstrip(';').rstrip()
    return ("(async () => {\n"
            f"  const __deskAccount = {guard};\n"
            "  const __deskStop = await __deskAccount();\n"
            "  if (__deskStop) return JSON.stringify(__deskStop);\n"
            f"  return (\n{body}\n  );\n"
            "})()\n")


def prelude(guard):
    """The guard as STATEMENTS, for a snippet that is a top-level-await script rather than one
    expression (substack_tags): it throws, the way that script refuses everything else."""
    return (f"const __deskAccount = {guard};\n"
            "{ const __deskStop = await __deskAccount(); "
            "if (__deskStop) throw new Error(JSON.stringify(__deskStop)); }\n")


def guard_handle(text):
    """The handle a generated snippet's guard insists on, or None if it carries no guard."""
    m = re.search(re.escape(GUARD_MARK) + r' \(async \(\) => \{\s*const WANT = ("[^"\\]*")', text or '')
    return json.loads(m.group(1)) if m else None


def drives_substack(text):
    """Does this snippet read or write a Substack editor or its API? (pane_carry's test.)"""
    return bool(re.search(r"\.ProseMirror|['\"]/api/v1/", text or ''))


def outlets_path_for(piece_dir, outlets_path=None):
    """Explicit path, else $DESK_OUTLETS, else <the instance holding the piece>/publishing/outlets.yaml
    (the nearest ancestor with a pieces/ directory, as publications.instance_root finds it)."""
    if outlets_path:
        return outlets_path
    if os.environ.get('DESK_OUTLETS'):
        return os.environ['DESK_OUTLETS']
    cur = os.path.abspath(piece_dir)
    while True:
        if os.path.isdir(os.path.join(cur, 'pieces')):
            return os.path.join(cur, 'publishing', 'outlets.yaml')
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _host(url):
    return urlparse(str(url or '')).hostname or ''


def _manifest(piece_dir):
    path = os.path.join(piece_dir, 'publish.yaml')
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {}


def substack_outlet_for_piece(piece_dir, outlets_path=None):
    """-> (outlet name, spec) of the ONE Substack outlet a piece BELONGS to. Raises NoAccount.

    WHOSE POST THIS IS, asked without asking permission to write it. `outlet_for_piece` is this
    plus the account check, and every WRITE goes through that one. A read-only tool
    (`substack_verify` fetching a public page, `substack_notes` reading a public feed) needs the
    first question answered and must not be refused by the second: an outlet with no
    `account_handle` recorded yet is one nothing may write, not one nothing may look at.

    Its publish.yaml `outlets:` list names it. A manifest with no list (it predates outlets) is
    settled by the host of its `post_url`, or by the desk having a single Substack outlet. A
    `post_url` on ANOTHER Substack outlet's host than the one declared is refused: the manifest
    disagrees with itself about whose post this is."""
    slug = os.path.basename(os.path.normpath(piece_dir))
    path = outlets_path_for(piece_dir, outlets_path)
    if not path or not os.path.isfile(path):
        raise NoAccount(f"{slug}: no publishing/outlets.yaml found (looked for {path or 'an instance root'}), "
                        f"so nothing says which Substack account may write this post")
    doc = load(path)
    man = _manifest(piece_dir)
    subs = substack_outlets(doc)
    post_host = _host(man.get('post_url'))
    by_host = [n for n in subs if post_host and _host(doc['outlets'][n].get('reader_base')) == post_host]
    declared = man.get('outlets')
    if isinstance(declared, list):
        mine = [o for o in declared if o in subs]
        if len(mine) > 1:
            mine = [o for o in mine if o in by_host] or mine
        if not mine:
            raise NoAccount(f"{slug}: its outlets: ({', '.join(map(str, declared)) or 'none'}) name no "
                            f"Substack outlet")
        if len(mine) > 1:
            raise NoAccount(f"{slug}: its outlets: name {len(mine)} Substack outlets ({', '.join(mine)}) "
                            f"and its post_url does not say which this post is")
        name = mine[0]
        if by_host and name not in by_host:
            raise NoAccount(f"{slug}: outlets: says {name}, but its post_url is on {post_host}, "
                            f"which is {by_host[0]}'s — the manifest disagrees with itself")
    elif len(by_host) == 1:
        name = by_host[0]
    elif len(subs) == 1:
        name = subs[0]
    else:
        raise NoAccount(f"{slug}: no outlets: list, and neither its post_url nor the desk settles "
                        f"which of {len(subs)} Substack outlets it is")
    return name, doc['outlets'][name] or {}


def outlet_for_piece(piece_dir, outlets_path=None):
    """-> (outlet name, spec) of the ONE Substack outlet a piece WRITES to. Raises NoAccount.

    `substack_outlet_for_piece` settles which outlet; this adds the account requirement, and
    every write path goes through it."""
    name, spec = substack_outlet_for_piece(piece_dir, outlets_path)
    if not expected(spec):
        slug = os.path.basename(os.path.normpath(piece_dir))
        raise NoAccount(f"{slug} goes to {name}, which names no account_handle — add one to outlets.yaml")
    return name, spec


def guard_for_piece(piece_dir, outlets_path=None):
    """-> (guard JS, outlet name, handle, hosts) for a piece. Raises NoAccount."""
    name, spec = outlet_for_piece(piece_dir, outlets_path)
    hosts = publish_hosts(spec, _manifest(piece_dir))
    return guard_js(spec, name, hosts), name, expected(spec), hosts


def guarded(piece_dir, js, tool='snippet'):
    """For a generator: `js` wrapped behind the piece's guard, or exit 9 having written nothing."""
    try:
        guard, name, want, hosts = guard_for_piece(piece_dir)
    except NoAccount as e:
        print(f"{tool}: refusing to write a snippet: {e}", file=sys.stderr)
        sys.exit(NO_ACCOUNT_EXIT)
    if os.environ.get('DESK_OUTLETS'):
        # An ambient override of WHOSE account is expected is worth saying out loud every time.
        print(f"account guard: outlets read from $DESK_OUTLETS ({os.environ['DESK_OUTLETS']}), "
              f"not the desk's own publishing/outlets.yaml")
    print(f"account guard: the snippet stops unless the page is signed in as @{want} ({name})"
          + (f", on {' / '.join(hosts)}" if hosts else
             f" — {name} records no *.substack.com host, so the PUBLICATION is not checked; "
             f"name publish_host: in outlets.yaml to check it"))
    return wrap(js, guard)


def _atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.outlets-', suffix='.yaml')
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(text)
    os.replace(tmp, path)


def set_primary(path, name):
    """Make `name` the primary by editing outlets.yaml in place, comments intact.
    -> (exit code, message)."""
    doc = load(path)
    spec = doc['outlets'].get(name)
    if spec is None:
        return 1, f"no outlet {name!r} in {path}"
    if not is_substack(spec):
        return 1, f"{name} is not a Substack outlet"
    if not expected(spec):
        return 6, f"{name} names no account_handle — declare the account before making it primary"
    old, _ = primary(doc)
    if old == name and doc.get(PRIMARY_KEY) == name:
        return 0, f"{name} is already the primary"
    # Demoting an outlet that names no chrome_browser was exit 6, "nowhere to run". It has
    # somewhere: the pane, which resolves its account on its own publication (2026-11-03). The
    # switch says so rather than refusing.
    others = [n for n in substack_outlets(doc) if n != name]

    src = open(path, encoding='utf-8').read()
    line = f"{PRIMARY_KEY}: {name}"
    if re.search(rf'^{PRIMARY_KEY}:', src, re.M):
        new = re.sub(rf'^{PRIMARY_KEY}:[^\n#]*', line + ' ', src, count=1, flags=re.M)
        new = re.sub(rf'^({PRIMARY_KEY}: \S+) +(#|\n)', r'\1 \2', new, count=1, flags=re.M)
        new = new.replace(line + ' \n', line + '\n')
    else:
        m = re.search(r'^outlets:', src, re.M)
        if not m:
            return 6, f"{path} has no top-level outlets: mapping"
        new = src[:m.start()] + line + "\n\n" + src[m.start():]
    if load_text_primary(new) != name:
        return 6, "refusing to write: the edit did not land where it was meant to"
    _atomic_write(path, new)

    want = expected(spec)
    msg = [f"{name} is now the primary: it uses the built-in pane for every Substack operation."]
    msg.append(f"  Sign the PANE in as @{want} — until then every write to {name} is refused (check exit 5).")
    for n in others:
        s = doc['outlets'][n] or {}
        who = expected(s) or shown(s)
        if s.get('chrome_browser'):
            msg.append(f"  {n} opens in Claude in Chrome, browser {s.get('chrome_browser')!r} — "
                       f"it must be signed in as @{who}.")
        else:
            msg.append(f"  {n} names no chrome_browser, so reach for the pane for it too — it "
                       f"resolves @{who} on {n}'s own publication. Name one only if {n} wants a "
                       f"surface of its own.")
    msg.append("  The pane's login is shared by every session: tell anyone mid-write before you switch it.")
    return 0, "\n".join(msg)


def load_text_primary(text):
    return (yaml.safe_load(text) or {}).get(PRIMARY_KEY)


def _describe(r):
    if r['problem']:
        return f"UNRUNNABLE — {r['problem']}"
    pref = ("built-in pane (primary)" if r['surface'] == 'pane'
            else f"Claude in Chrome, browser {r['chrome_browser']!r}")
    return f"reach for {pref} first — a preference; the ACCOUNT is the gate"


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--outlets', default='publishing/outlets.yaml')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('route'); p.add_argument('outlet')
    p = sub.add_parser('primary'); p.add_argument('outlet', nargs='?')
    sub.add_parser('snippet')
    p = sub.add_parser('guard'); p.add_argument('piece')
    p = sub.add_parser('check'); p.add_argument('outlet')
    p.add_argument('--surface', choices=('pane', 'chrome'), required=True,
                   help='where the snippet ran — and where you will write; a surface the outlet '
                        'does not prefer still passes if the account checks out')
    p.add_argument('--result', required=True,
                   help="the snippet's JSON answer, verbatim ('-' reads it from stdin)")
    p.add_argument('--json', action='store_true', help='print the verdict as JSON')
    o = ap.parse_args(argv)

    if o.cmd == 'snippet':
        print(SNIPPET)
        return 0
    if o.cmd == 'guard':
        explicit = o.outlets if o.outlets != ap.get_default('outlets') else None
        try:
            name, spec = outlet_for_piece(o.piece, explicit)
        except NoAccount as e:
            print(str(e), file=sys.stderr)
            return NO_ACCOUNT_EXIT
        print(f"{os.path.basename(os.path.normpath(o.piece))}: {name}, @{expected(spec)} — every "
              f"snippet generated for it stops unless the page is signed in as that account")
        return 0
    if o.cmd == 'primary' and o.outlet:
        code, msg = set_primary(o.outlets, o.outlet)
        print(msg, file=sys.stdout if code == 0 else sys.stderr)
        return code
    doc = load(o.outlets)
    if o.cmd == 'primary':
        prim, problem = primary(doc)
        print(f"primary  {prim or '— none: ' + str(problem)}")
        for n in substack_outlets(doc):
            print(f"  {n:24} @{expected(doc['outlets'][n]) or '? (no account_handle)':16} "
                  f"{_describe(route(doc, n))}")
        return 0 if prim and not any(route(doc, n)['problem'] for n in substack_outlets(doc)) else 6
    if o.cmd == 'route':
        r = route(doc, o.outlet)
        if r is None:
            print(f"no outlet {o.outlet!r} in {o.outlets}", file=sys.stderr)
            return 1
        print(f"outlet   {r['outlet']}\naccount  @{r['account'] or '?  (no account_handle — check will refuse)'}\n"
              f"surface  {_describe(r)}")
        if r['note']:
            print(f"note     {r['note']}")
        for i, step in enumerate(r['browser_steps'], 1):
            print(f"  {i}. {step}")
        print(f"snippet  {r['snippet']}")
        return 6 if r['problem'] else 0
    raw = sys.stdin.read() if o.result == '-' else o.result
    try:
        result = json.loads(raw)
    except ValueError:
        result = None
    code, msg = verdict(doc, o.outlet, result, o.surface)
    print(json.dumps({'code': code, 'message': msg}) if o.json else msg,
          file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == '__main__':
    sys.exit(main())
