"""EV-06/E18.4 / M04: ITN-independent short-command scoring.

Text counterparts of the E18.4 short-command corpus, scored locally by
localflow.v2.normalize.scoring — no model call, no cloud dependency
(M15 owns the optional comparator). Exact intended-token accuracy on
command cases and the false-command rate on non-command controls carry
separate denominators (E06 slash-command accuracy row).

Run: .venv/bin/python tests/v2/normalization/test_short_command_scoring.py
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.normalize import (  # noqa: E402
    NormalizationPolicy,
    normalize,
    score_command_corpus,
    separate_scores,
)

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "short_command_corpus.json").read_text())


def test_corpus_shape():
    cases = CORPUS["cases"]
    commands = [c for c in cases if c["kind"] == "command"]
    non = [c for c in cases if c["kind"] == "non_command"]
    assert len(cases) == 24
    assert len(commands) == 16 and len(non) == 8
    print(f"ok  corpus: {len(cases)} cases "
          f"({len(commands)} command / {len(non)} non-command)")


def test_exact_token_accuracy_and_false_command_rate():
    summary = score_command_corpus(CORPUS["cases"])
    assert summary["command_exact_accuracy"] == 1.0, [
        r for r in summary["results"] if not r["ok"]]
    assert summary["false_command_rate"] == 0.0, [
        r for r in summary["results"] if not r["ok"]]
    assert summary["command_cases"] == 16
    assert summary["non_command_cases"] == 8
    print(f"ok  exact-token accuracy {summary['command_exact_hits']}/"
          f"{summary['command_cases']}; false commands "
          f"{summary['false_commands']}/{summary['non_command_cases']}")


def test_number_word_digit_separate_scoring():
    """AC05: representation edits are counted from the ledger, apart
    from lexical ASR scoring."""
    pol = NormalizationPolicy()
    res = normalize("the timeout is thirty seconds", pol)
    s = separate_scores(res)
    assert s["number_word_to_digit_edits"] == 1
    assert "unit_number" in s["number_word_to_digit_ops"]
    res = normalize("slash brainstorm the budget",
                    NormalizationPolicy(
                        registered_skills={"brainstorm": "brainstorm"}))
    s = separate_scores(res)
    assert s["number_word_to_digit_edits"] == 0
    assert s["other_edits"] == 1 and "skill" in s["other_ops"]
    print("ok  separate scoring: number-word→digit apart from other edits")


def main():
    test_corpus_shape()
    test_exact_token_accuracy_and_false_command_rate()
    test_number_word_digit_separate_scoring()
    print("all short-command scoring tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
