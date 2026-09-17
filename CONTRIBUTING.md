# How we work together

Read this before your first commit. It exists so that committing to one repo
doesn't constantly break `main`, and so the syllabus's "every member contributes to GitHub"
requirement is satisfied cleanly and visibly.

## The golden rule
**`main` always runs.** Every merge into `main` must pass CI. If a merge breaks the skeleton,
it gets reverted, not debugged on `main`.

## Branch → PR → merge
1. Never push to `main` directly.
2. Branch per issue: `git checkout -b <area>/<short-desc>` (e.g. `optimizer/greedy-hours`).
3. Small, focused commits. Push your branch, open a Pull Request into `main`.
4. CI runs automatically (lint + tests, Python and web). **A red PR cannot merge.**
5. At least one teammate reviews and approves.
6. Delete the branch after merge.

## Before you push
```bash
make lint     # ruff + web typecheck
make test     # python + web tests
```
If both are green locally, CI will (almost always) be green too.

## Contracts are sacred
The three shapes in `/contracts` are how we stay unblocked. Editing them changes everyone's
work silently, so **contract changes go through a PR that the whole team agrees to**, never a quiet unilateral edit.

## Lockfiles are committed
`uv.lock` and `web/package-lock.json` are checked in. Commit them when deps change so everyone
installs identical versions.

## Every folder owns its tests
Put tests next to the code they cover. That way a Data change can't fail the Optimizer's merge
and vice-versa.
