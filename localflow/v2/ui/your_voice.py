"""The Your Voice pane — the Insights view's communication-profile
section (V2 M14, Spec S22, contract profile.md).

Deliberately simple AppKit over the state/service layers (the M09
discipline): a status line, the measured block, the interpretive cards
with their supporting examples, and the actions — Generate (on demand;
the idle scheduler lives in the coordinator), exclude one supporting
example (durable; the snapshot invalidates and regenerates without
it). Below the eligible-words floor the pane shows measured totals and
the honest explanation — never a fabricated profile (the M14 stop
condition). No control here touches the dictation pipeline.
"""

from __future__ import annotations

from AppKit import (NSButton, NSMakeRect, NSTextField, NSTextView,
                    NSView)

from .hub import _button, _label, _scroll, _textview


class YourVoicePane:
    """Builds and refreshes the Your Voice section. Owned by
    ``HubController``; all actions dispatch back through it."""

    def __init__(self, controller, cw: float, ch: float):
        self.controller = controller
        self.view = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, cw, ch))
        self.status = _label(NSMakeRect(8, ch - 26, cw - 220, 18), "")
        self.view.addSubview_(self.status)
        self.view.addSubview_(_button(
            "Generate", self.controller, "voiceGenerate:",
            NSMakeRect(cw - 100, ch - 28, 92, 22)))
        self.text = _textview(NSMakeRect(0, 0, cw, 100))
        sc = _scroll(NSMakeRect(8, 30, cw - 16, ch - 62), self.text)
        sc.setAutoresizingMask_(18 | 16)
        self.view.addSubview_(sc)
        self.view.addSubview_(_label(
            NSMakeRect(8, 4, 210, 18), "Exclude evidence example id:"))
        self.exclude_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(220, 2, 220, 22))
        self.view.addSubview_(self.exclude_field)
        self.view.addSubview_(_button(
            "Exclude", self.controller, "voiceExcludeEvidence:",
            NSMakeRect(448, 1, 90, 22)))

    def refresh(self, data: dict | None):
        """Render the profile snapshot state honestly: absent,
        invalidated (with reason — deleted/expired/excluded evidence)
        or current (measured + cards + coverage)."""
        if not data or data.get("subview", "usage") != "voice":
            return
        if data.get("profile_reason"):
            self.status.setStringValue_("Your Voice unavailable")
            self.text.setString_(
                f"No profile service is wired ({data['profile_reason']}).")
            return
        profile = data.get("profile")
        if profile is None:
            self.status.setStringValue_("No profile snapshot yet")
            self.text.setString_(
                "Nothing has been generated. Choose Generate to"
                " compute measured views from eligible evidence — or"
                " leave it: insufficient history is a valid"
                " measured-only state, never an error.")
            return
        measured = profile.get("measured") or {}
        self.status.setStringValue_(
            f"Snapshot {profile.get('snapshot_id', '')[:16]}… ·"
            f" algorithm v{profile.get('algorithm_version')} ·"
            f" state {profile.get('state')}")
        if profile.get("state") != "current":
            # Nothing from an invalidated snapshot is shown: its
            # evidence changed (deleted, expired or excluded), so its
            # numbers and cards no longer describe the history.
            self.text.setString_(
                f"This snapshot was invalidated"
                f" ({profile.get('invalidated_reason')}) — its evidence"
                " changed. Choose Generate to recompute from the"
                " current eligible history; deleted evidence cannot"
                " reappear.")
            return
        lines = [f"Eligible examples: "
                 f"{measured.get('eligible_examples', 0)}",
                 f"Eligible words: {measured.get('eligible_words', 0)}"
                 f" (interpretation floor "
                 f"{measured.get('min_words_threshold')})",
                 f"Median/mean words per utterance: "
                 f"{(measured.get('utterance_words') or {}).get('median')}"
                 f" / {(measured.get('utterance_words') or {}).get('mean')}",
                 "Not counted as your speech: "
                 + json_dumps(measured.get("excluded")),
                 "Dictations by local hour: "
                 + json_dumps(measured.get("hour_histogram"))
                 + f" (no offset recorded: "
                   f"{measured.get('hours_unknown', 0)})",
                 "", "Frequent phrases:"]
        for p in measured.get("frequent_phrases") or []:
            lines.append(f"  {p['phrase']}  ×{p['count']}")
        lines += ["", "Corrections by kind: "
                  + json_dumps(measured.get("corrections_by_kind")),
                  "Dictionary-hit examples: "
                  f"{measured.get('dictionary_hit_examples', 0)}",
                  "Technical terms: "
                  + ", ".join(measured.get("technical_terms") or []),
                  "Modes: " + json_dumps(measured.get("modes")),
                  "", "Interpretive cards:"]
        cards = profile.get("cards") or []
        if not cards:
            note = measured.get("interpretive_note") \
                or "no cards supported by the measured evidence"
            lines.append(f"  (none — {note})")
        for card in cards:
            lines.append(f"  [{card['kind']}] {card['title']}")
            lines.append(f"    {card['statement']}")
            lines.append(f"    evidence: "
                         f"{', '.join(card['evidence_example_ids'])}")
        self.text.setString_("\n".join(lines))


def json_dumps(value) -> str:
    import json
    if not value:
        return "—"
    return json.dumps(value, sort_keys=True)
