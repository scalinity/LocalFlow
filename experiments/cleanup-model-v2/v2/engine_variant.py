"""Isolated parser repair: ignore empty separator tokens around markers.

The production file is loaded into a distinct module. Every protection,
proposal-resolution rule and validator remains unchanged. No live module is
monkey-patched and the installed application never imports this package.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from .baseline import load as load_baseline

NAME = "localflow.v2.cleanup._experiment_baseline._v2_experiment_engine"


def load():
    if NAME in sys.modules:
        return sys.modules[NAME]
    baseline = load_baseline()
    spec = importlib.util.spec_from_file_location(NAME, baseline.__file__)
    module = importlib.util.module_from_spec(spec)
    sys.modules[NAME] = module
    spec.loader.exec_module(module)

    def evidence(window_text, span):
        s, e = span
        if re.search(r"[.!?](\s|$)", window_text[s:e].rstrip(".!? ")):
            return "crosses_sentence"
        ms = module.correction_marker_start(window_text, span)
        if not module._has_content(window_text[s:ms]):
            return "no_outdated_value"
        tail = window_text[e:]
        m = re.search(r"[.!?\n]", tail)
        # The old split keeps the isolated comma after 'sorry' as word zero.
        # Remove only punctuation-only separators, retaining the four-word cap.
        tokens = lambda t: [w for token in t.split() if (w := token.lower().strip(",;:"))]
        after = tokens(tail[:m.start()] if m else tail)[:4]
        marker = window_text[ms:e].lower()
        if marker == "i mean" and after and after[0] in module._EMPHASIS_AFTER_I_MEAN:
            return "emphasis_not_correction"
        if not module._has_content(" ".join(after)):
            return "no_replacement"
        validation = sys.modules[baseline.__package__ + ".validation"]
        FUNCTION_WORDS, FILLERS = validation.FUNCTION_WORDS, validation.FILLERS
        before = tokens(window_text[s:ms])
        replacement = next((w for w in after if w not in FUNCTION_WORDS and w not in FILLERS), "")
        for values in (module._WEEKDAYS, module._MONTHS):
            if before[-1] in values and replacement in values and any(
                    w not in FUNCTION_WORDS and w not in FILLERS for w in before[:-1]):
                return "overbroad_calendar_value"
        if marker in module._SINGLE_WORD_MARKERS and not module._parallel(before, after):
            return "not_parallel"
        return None

    module._evidence_reason = evidence
    return module
