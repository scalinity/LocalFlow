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

## Orchestration overview

- `ORCHESTRATION.html` in the project root is the page used to decide what
  to run next and on which model. Keep it current: a session that finishes
  a unit of work, changes what can run next, takes decision numbers or
  moves a file-ownership boundary realigns the page before it closes out,
  without being asked.
- Check the page against the project's own record (`docs/v2/STATUS.json`,
  the milestone list, the decision log, each unit's expected-files list),
  never against memory of the session. Realign the judgement as well as the
  figures: what is eligible, what may run beside what, and which units a
  session in flight holds.
- Edit in place. A realignment changes a figure, a strip's state or an
  eligibility line and leaves the layout alone.
- Commit the realignment with the work it describes. Say in the handover
  that the page was realigned and what changed, or that nothing it asserts
  changed.
- Leave the page alone when it has uncommitted changes, is checked out in
  another worktree, or another session owns it; say in the handover what
  would have changed.

## Pushing finished work

- A session may push its own finished, verified work to `origin` without
  asking again: stage files by name, commit, push the branch, and push
  `main` where the remediation rule above applies.
- Finished means the checks the work claims were run and reported as they
  came out. An unrun check is never reported as passed, and incomplete
  work stays local.
- Never force-push or rewrite pushed history, and stop and report on any
  conflict instead of guessing.
- The repository is public. Before pushing, scan what is being added for
  credentials and personal identifiers, and keep third-party material and
  private evidence out of the commit.
