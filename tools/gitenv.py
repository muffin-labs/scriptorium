#!/usr/bin/env python3
"""gitenv.py — one place for the GIT_* variables that silently redirect a repository.

Every git HOOK runs with `GIT_DIR` and `GIT_WORK_TREE` already set, and those OVERRIDE `-C <dir>`
and `cwd=`. So a tool that asks a question about one repository, while running under a hook or
under anything a hook started, gets the answer for ANOTHER repository — and gets it silently,
with a zero exit status.

It has bitten two tools eight days apart, which is why it is a module rather than a habit:

  * `dashboard.py` (2026-10-03) reads the repository's own record to decide which side of a
    block is newer. Under the framework's pre-push hook, `GIT_DIR` pointed at the submodule, so
    `sync` would have judged the desk's fragments against the submodule's history.
  * `prepush.py` (2026-10-11) asks the FRAMEWORK whether a pointer is on its default branch,
    with `cwd=fw`.
    It is invoked from `.githooks/pre-push` — the one environment where `GIT_DIR` is guaranteed
    to be set — so every one of those questions was answerable about the wrong repository.

Both were found by the hook refusing a push — the gate that exists to catch what a local run
cannot see catching exactly that, in its own tooling, twice.

Pass `git_env()` as `env=` on every git subprocess whose repository is chosen by `-C` or `cwd`,
and let that argument be the only thing that says which repository is meant.
"""
import os

# Only the variables that can REDIRECT a repository. Deliberately not GIT_AUTHOR_* / GIT_CONFIG_*:
# identity and config are not a repository, and a caller setting a commit date means it.
REDIRECTS = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
             'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_COMMON_DIR', 'GIT_NAMESPACE',
             'GIT_CEILING_DIRECTORIES', 'GIT_PREFIX')


def git_env(base=None):
    """A copy of the environment with every repository-redirecting GIT_* variable removed."""
    env = dict(os.environ if base is None else base)
    for var in REDIRECTS:
        env.pop(var, None)
    return env
