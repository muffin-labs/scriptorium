#!/usr/bin/env python3
"""ci_check.py — what GitHub CI runs, as one command, shared with the pre-push hook.

    python3 tools/ci_check.py              # a framework checkout: the fixture corpus
    python3 framework/tools/ci_check.py    # an instance root: the real corpus

Both repos' tests.yml call this and nothing else, and tools/prepush.py calls it on an export
of the commit being pushed. One definition of "CI passes", so the hook cannot pass what CI then
fails. Before this, the no-deletion grep lived only in the workflow YAML — and every push on
2026-09-11, both repos, all day, went red on GitHub for reasons a local suite run could not see.

Steps, in order:
  1. The suites must not delete, fetch, or run a shell. Their predecessor was a bash loop
     holding `rm -f $S/*` with $S unquoted. A grep, deliberately dumb: a deletion has to be
     argued into a suite by changing THIS file, not slipped in beside a test. A test that needs
     a file to be absent builds the directory without it. `test_concurrency.py` does invoke one
     program — `git`, with an explicit argv and no shell, inside a `git init` repository of its
     own under `tempfile.TemporaryDirectory()` — because the provenance it tests IS the
     repository's record and there is nothing else to read it from. Step 3 is what holds that
     honest: the real tree is hashed before and after.
  2. The regression suites: `test_suite.py` (the corpus) and `test_concurrency.py` (the
     multi-session guards). The second was written as a separate runner while another session
     held `test_suite.py`, and stayed out of CI on a note saying to fold it in "when the desk is
     quiet" — which meant the dashboard guards it covers were never gated. Two of them then
     broke in the tree for weeks (a fragment with no heading appended a block to its neighbour
     on every sync; a stale DASHBOARD.md reverted newer fragments in a fresh checkout). Running
     the file is cheaper than folding it in, and it is what makes those tests a gate.
  3. The run left the tree untouched. The suite is read-only; every file present before the run
     is hashed before and after. Hashes rather than `git diff`, so it works on a `git archive`
     export with no .git; new files are ignored, as `git diff` ignores untracked ones.

Exit 0 green, 1 red.
"""
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK = os.path.dirname(HERE)
SUITES = [os.path.join(HERE, n) for n in ('test_suite.py', 'test_concurrency.py')]
FORBIDDEN = re.compile(r'rm -rf|shutil\.rmtree|os\.unlink|os\.remove|shell=True'
                       r'|urllib\.request\.urlopen|requests\.')
SKIP_DIRS = {'.git', '__pycache__', 'node_modules'}


def tree_root():
    """The same rule test_suite.py uses to find its corpus: an instance is a framework whose
    parent holds pieces/. The suite runs from there, as the desk workflow runs it."""
    parent = os.path.dirname(FRAMEWORK)
    return parent if os.path.isdir(os.path.join(parent, 'pieces')) else FRAMEWORK


def digest(root):
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            p = os.path.join(d, f)
            if os.path.islink(p):
                continue
            h = hashlib.sha256()
            with open(p, 'rb') as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b''):
                    h.update(chunk)
            out[os.path.relpath(p, root)] = h.hexdigest()
    return out


def main():
    root = tree_root()
    print(f'ci_check: {root}  (python {sys.version.split()[0]})', flush=True)
    red = False

    for suite in SUITES:
        with open(suite, encoding='utf-8') as f:
            hits = [f'{n}: {line.rstrip()}' for n, line in enumerate(f, 1) if FORBIDDEN.search(line)]
        if hits:
            print(f'FAIL  {os.path.basename(suite)} gained a deletion, network, or shell call:\n  '
                  + '\n  '.join(hits), flush=True)
            return 1
    print('ok    the suites do not delete, fetch, or run a shell', flush=True)

    before = digest(root)
    for suite in SUITES:
        if subprocess.run([sys.executable, suite], cwd=root).returncode != 0:
            print(f'FAIL  the regression suite {os.path.basename(suite)}', flush=True)
            red = True
    after = digest(root)
    changed = sorted(p for p, h in before.items() if after.get(p) != h)
    if changed:
        print('FAIL  the suite modified files it is supposed to only read:\n  '
              + '\n  '.join(changed[:20]), flush=True)
        red = True
    else:
        print('ok    the run left the tree untouched', flush=True)
    return 1 if red else 0


if __name__ == '__main__':
    sys.exit(main())
