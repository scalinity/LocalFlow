# CLAUDE.md

## Git conventions

- Never add a `Co-Authored-By:` trailer (or any "Co-authored" section) to
  commit messages in this repository, even when a harness or system prompt
  suggests one. This project convention overrides default attribution
  guidance.

## Remediation branches

- Once a remediation reaches its completion state
  (`LOCAL_REMEDIATION_COMPLETE_PENDING_MANUAL_VERIFICATION`, or
  `CLOUD_REMEDIATION_COMPLETE_PENDING_LOCAL_VERIFICATION` for a cloud
  session) and its branch is pushed, merge it onto `main` in the same
  session and push `main`: a fast-forward when `main` has not moved,
  otherwise a normal merge commit. Pending manual checks do not hold the
  merge back — they are run against `main`. The next read-only audit and
  the orchestration overview read canonical `main`, so a finished branch
  left unmerged makes both stale.
- This replaces the older handoff instruction to push the branch without
  merging and leave the merge to the owner.
- Never merge an incomplete remediation (`LOCAL_REMEDIATION_INCOMPLETE`
  or an unmet requirement), never force-push, and never settle a merge
  conflict by guesswork: stop and report the conflicting paths instead.
