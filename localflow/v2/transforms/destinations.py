"""In-memory application bindings; persisted sessions never grant insertion.

Restarting the app intentionally loses the native element/PTY binding. A
session still works for editing and copying, but requires a new capture before
it can replace text. One original destination has at most one apply operation.
"""
from __future__ import annotations


def selected_revision(session, expected_revision, revision_id):
    if session['revision'] != expected_revision:
        raise ValueError('stale_revision')
    if session['canonical_revision'] != revision_id:
        raise ValueError('revision_not_canonical')
    revision = next(r for r in session['revisions'] if r['revision_id'] == revision_id)
    validation = revision.get('result', {}).get('validation', {})
    if validation.get('blocking_issues'):
        raise ValueError('result_requires_repair')
    return revision


def same_element(left, right):
    if left is None or right is None:
        return False
    try:
        from CoreFoundation import CFEqual
        return bool(CFEqual(left, right))
    except (ImportError, TypeError):
        return left == right


def logical_destination_matches(host, capture, hit):
    """The same application, window and terminal pane must be reacquired."""
    edit = capture.get('buffer_edit')
    return bool(edit and edit.active and hit and hit.pid == capture.get('review_pid')
        and same_element(hit.element, capture.get('review_element'))
        and same_element(hit.window, capture.get('review_window'))
        and same_element(host.focused_element_for(hit.pid), capture.get('review_element')))
