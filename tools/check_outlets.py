#!/usr/bin/env python3
"""check_outlets.py — can this piece actually reach every outlet it declares?

WHY THIS EXISTS
  Publishing is not one act. A piece names several outlets and they go out one at a
  time, and the FIRST one is irreversible — on Substack it mails the subscriber list.
  So the moment to discover that the second outlet cannot be written to is BEFORE the
  first one goes, not after.

  Measured 2026-09-13, publishing *What Holds You Here*: Substack went live and sent
  its launch email, and the alignmentfellowship upload then failed on an EXPIRED AWS
  SSO TOKEN. The piece was left live on one outlet and absent from the other — the
  "half-published" state this desk's own publish skill names as the failure to design
  against — and nothing could have said so earlier, because nothing looked until the
  step that needed the credential. (Eric: *"if there is an issue in the framework that
  caused this error we should fix it."*)

WHAT IT CHECKS, per outlet the piece declares
  store-backed (a `store:` in the outlet, e.g. a quire site)  the credential really works:
      an STS identity call on the profile the store names, then a HEAD on the bucket.
      An expired SSO token fails both, which is the whole point.
  substack-backed (an `account_handle`)                       reported MANUAL: the account
      guard runs in the browser and cannot be answered from here. Named so it is not
      mistaken for a pass.
  anything else                                               reported UNKNOWN, never OK.

  A piece with NO `outlets:` is a REFUSAL, matching the publish skill: publishing to
  "the obvious one" is how a piece ends up on one host and nowhere else.

USAGE
  python3 check_outlets.py <piece_dir> [--outlets publishing/outlets.yaml] [--store publishing/store.yaml]

EXIT
  0  every declared outlet is reachable (or is a MANUAL browser check)
  1  usage / no draft
  4  a declared outlet cannot be written to, or the piece declares none
"""
import os, sys, subprocess


def _yaml(path):
    try:
        import yaml
    except ImportError:
        print("error: pyyaml not installed", file=sys.stderr); sys.exit(1)
    with open(path, encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {}


def manifest_path(text_dir):
    """A text's manifest by namespace: a piece's publish.yaml, or a talk's talk.yaml. None if
    neither — and the caller must exit NON-ZERO then: a gate that cannot look must not wear a
    pass's face (backlog: the-outlet-gates-cannot-see-a-talk, 2026-10-15)."""
    for name in ('publish.yaml', 'talk.yaml'):
        p = os.path.join(text_dir, name)
        if os.path.exists(p):
            return p
    return None


def declared(piece_dir):
    mp = manifest_path(piece_dir)
    if mp is None:
        print(f"REFUSING: {piece_dir} has no publish.yaml or talk.yaml — nothing says where it goes.")
        sys.exit(4)
    man = _yaml(mp)
    out = man.get('outlets')
    if not out and man.get('site') is True:
        return ['<legacy site: true>']
    return out or []


def check_store(outlet, name, store_cfg):
    """An SSO token that has expired answers every call with a 401-shaped error, so ask."""
    store = (store_cfg or {}).get('store') or store_cfg or {}
    profile = store.get('aws_profile')
    bucket = store.get('bucket')
    env = dict(os.environ)
    args = ['aws', 'sts', 'get-caller-identity', '--output', 'text']
    if profile:
        args += ['--profile', profile]
    p = subprocess.run(args, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        why = (p.stderr or p.stdout).strip().splitlines()[-1:] or ['']
        hint = ('  the SSO token has expired — run:  aws sso login --profile %s' % profile
                if profile and 'sso' in why[0].lower() or 'ExpiredToken' in why[0] or 'InvalidClientTokenId' in why[0]
                else '')
        return False, f"credentials do NOT work for profile {profile!r}: {why[0][:90]}", hint
    if bucket:
        h = subprocess.run(['aws', 's3api', 'head-bucket', '--bucket', bucket] +
                           (['--profile', profile] if profile else []),
                           capture_output=True, text=True, env=env)
        if h.returncode != 0:
            return False, f"bucket {bucket} not reachable: {(h.stderr or '').strip()[-80:]}", ''
    return True, f"profile {profile!r} authenticated, bucket reachable", ''


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__.strip()); sys.exit(1)
    piece = args[0].rstrip('/')
    if not os.path.exists(os.path.join(piece, 'draft.md')):
        print(f"no draft.md in {piece}"); sys.exit(1)

    def opt(flag, default):
        return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default

    reg_path = opt('--outlets', 'publishing/outlets.yaml')
    store_path = opt('--store', 'publishing/store.yaml')
    registry = _yaml(reg_path).get('outlets', {}) if os.path.exists(reg_path) else {}
    store_cfg = _yaml(store_path) if os.path.exists(store_path) else {}

    names = declared(piece)
    if not names:
        print("REFUSING: this piece declares no `outlets:`.")
        print("  Publishing to the obvious one is how a piece ends up live on one host and")
        print("  missing from another. Ask which outlets it is for, write them into")
        print(f"  {os.path.basename(manifest_path(piece) or 'publish.yaml')} in {piece}, then publish.")
        sys.exit(4)

    bad = 0
    for name in names:
        cfg = registry.get(name, {})
        if cfg.get('store') or (name != 'substack' and store_cfg and cfg.get('reader_base')
                                and not cfg.get('account_handle')):
            ok, note, hint = check_store(name, cfg, store_cfg)
            print(f"  {'ok  ' if ok else 'FAIL'}  {name:22s}  {note}")
            if hint:
                print(hint)
            bad += 0 if ok else 1
        elif cfg.get('account_handle'):
            print(f"  man   {name:22s}  browser outlet — the account guard answers this "
                  f"(@{cfg['account_handle']}), not this tool")
        else:
            print(f"  ??    {name:22s}  no entry in {reg_path} — nothing here can say it is reachable")
            bad += 1

    print(f"\n{len(names)} declared outlet(s), {bad} that cannot be written to")
    if bad:
        print("Publishing now would leave the piece HALF-PUBLISHED. Fix the outlet first.")
    sys.exit(4 if bad else 0)


if __name__ == '__main__':
    main()
