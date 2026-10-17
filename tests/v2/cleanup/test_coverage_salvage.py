"""A cleanup candidate whose ONLY failure is a few deleted source words is
repaired by putting those exact words back, then validated again in full.

One unapproved deletion ("you know") used to send the whole window back to
the raw transcript, discarding every legitimate edit with it. Candidates
that also add words, change numbers, drop negations or lose more than a few
words are still rejected whole.

Run: .venv/bin/python tests/v2/cleanup/test_coverage_salvage.py
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import CleanupEngine  # noqa: E402
from localflow.v2.cleanup.validation import (  # noqa: E402
    restore_missing_words, validate)

SOURCE = ("okay so we will ship it you know on friday after the review "
          "and then we will write the notes for the team")
DROPS_FILLER = ("Okay, so we will ship it on Friday after the review, and "
                "then we will write the notes for the team.")


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def engine_for(proposal):
    def gen(prompt, max_tokens):
        text = "NONE" if "Find the self-corrections" in prompt else proposal
        return {"text": text, "output_tokens": 8, "limit_hit": False,
                "prompt": prompt}
    return CleanupEngine(gen, model_id="fake")


def decision_of(res):
    return [o for o in res.observations
            if o.get("kind") == "cleanup_decision"][-1]


def test_restore_puts_the_dropped_words_back_in_place():
    assert validate(SOURCE, DROPS_FILLER).accepted is False
    restored, count = restore_missing_words(SOURCE, DROPS_FILLER)
    assert count == 2
    assert "ship it you know on Friday" in restored, restored
    assert validate(SOURCE, restored).accepted
    # nothing new: every word of the repaired text is a source word
    assert not (set(words(restored)) - set(words(SOURCE)))


def test_nothing_to_restore_returns_none():
    assert restore_missing_words(SOURCE, SOURCE) is None


def test_engine_keeps_the_good_edits_when_only_coverage_failed():
    res = engine_for(DROPS_FILLER).clean(SOURCE)
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert "you know" in res.text and "Friday" in res.text, res.text
    d = decision_of(res)
    assert d["accepted"] is True and d["salvaged_words"] == 2, d


def test_added_word_is_still_rejected_whole():
    proposal = DROPS_FILLER.replace("will ship", "will really ship")
    res = engine_for(proposal).clean(SOURCE)
    assert res.path == "llm_fallback_normalized", res.path
    assert res.text == SOURCE


def test_losing_many_words_is_still_rejected_whole():
    proposal = "Okay, so we will ship it on Friday."
    res = engine_for(proposal).clean(SOURCE)
    assert res.path == "llm_fallback_normalized", res.path
    assert res.text == SOURCE


def test_dropped_connectives_start_the_following_numbered_or_bulleted_item():
    first = "sit on the chair with both feet flat on the floor"
    second = "stand beside the table while keeping the doorway clear"
    for markers in (("1. ", "2. "), ("- ", "- ")):
        proposal = (f"Do 2 actions in order:\n\n{markers[0]}{first.capitalize()}."
                    f"\n{markers[1]}{second.capitalize()}.")
        for connective in ("then", "and", "and then"):
            source = f"Do 2 actions in order: {first}, {connective} {second}."
            expected = (f"Do 2 actions in order:\n\n{markers[0]}{first.capitalize()}."
                        f"\n{markers[1]}{connective.capitalize()} {second}.")
            restored, count = restore_missing_words(source, proposal)
            assert restored == expected, restored
            assert count == len(connective.split())
            assert words(re.sub(r"(?m)^\d+[.)]\s+", "", restored)) == words(source)
            result = engine_for(proposal).clean(source)
            assert result.path == "llm", (result.path, result.fallback_reason)
            assert result.text == expected, result.text


def test_prior_completed_clause_keeps_its_omitted_tail_in_the_prior_item():
    source = "Bring paper forms to the office. Return keys."
    proposal = "1. Bring paper.\n2. Return keys."
    restored, count = restore_missing_words(source, proposal)
    assert restored == "1. Bring paper forms to the office.\n2. Return keys.", restored
    assert count == 4
    assert validate(source, restored).accepted
    # Four restored words still exceed this short input's existing salvage cap.
    assert engine_for(proposal).clean(source).text == source


def test_source_boundary_keeps_then_in_the_completed_clause():
    source = ("Do 2 actions: sit on the chair until then. "
              "Stand beside the table while keeping the doorway clear.")
    proposal = ("Do 2 actions:\n\n1. Sit on the chair until.\n"
                "2. Stand beside the table while keeping the doorway clear.")
    expected = proposal.replace("until.", "until then.")
    assert restore_missing_words(source, proposal) == (expected, 1)
    assert engine_for(proposal).clean(source).text == expected


def test_existing_source_list_boundary_does_not_get_guessed_placement():
    source = ("1. Sit on the chair with both feet on the floor.\n"
              "2. Then stand beside the table while keeping the doorway clear.")
    proposal = source.replace("Then stand", "Stand")
    assert restore_missing_words(source, proposal) is None
    assert engine_for(proposal).clean(source).text == source


def test_within_item_conjunction_stays_inside_that_item():
    source = ("Do 2 actions: place the red and blue pens in the box, "
              "then close the lid.")
    proposal = ("Do 2 actions:\n\n1. Place the red blue pens in the box.\n"
                "2. Then close the lid.")
    expected = proposal.replace("red blue", "red and blue")
    assert restore_missing_words(source, proposal) == (expected, 1)
    assert engine_for(proposal).clean(source).text == expected


def test_list_placement_does_not_rewrite_quoted_or_protected_content():
    for opening, closing in (("\"", "\""), ("“", "”"), ("‘", "’"),
                             ("'", "'"), ("`", "`")):
        quoted = f"Do 2 actions: repeat {opening}sit, then stand{closing} in the room."
        proposal = (f"Do 2 actions:\n1. Repeat {opening}sit.\n"
                    f"2. Stand{closing} in the room.")
        assert restore_missing_words(quoted, proposal) is None
        assert engine_for(proposal).clean(quoted).text == quoted

    for quoted_clause in ("'don't sit on the chair, then stand by the table'",
                          "'sit\non the chair, then stand by the table'",
                          "\"sit on the chair, then stand by the table"):
        source = f"Do 2 actions: repeat {quoted_clause} in the room."
        proposal = source.replace("Do 2 actions: repeat", "Do 2 actions:\n1. Repeat")
        proposal = proposal.replace(", then stand", ".\n2. Stand")
        assert restore_missing_words(source, proposal) is None
        assert engine_for(proposal).clean(source).text == source

    source = ("Do 2 actions: sit on the chair with both feet on the floor, "
              "then stand beside the table while keeping the doorway clear.")
    proposal = ("Do 2 actions:\n1. Sit on the chair with both feet on the floor.\n"
                "2. Stand beside the table while keeping the doorway clear.")
    start = source.index("then stand")
    protected = [(start, start + len("then stand"))]
    assert restore_missing_words(source, proposal, protected_positions=protected) is None
    assert engine_for(proposal).clean(source, protected_spans=protected).text == source


def test_contractions_do_not_stop_list_placement_in_a_long_window():
    # Only quoted or code text at the connective blocks the placement; the
    # contraction inside the item and elsewhere in the window does not.
    filler = ("It's a short visit, so don't rush. We can't skip the log "
              "and it isn't optional. ") * 12
    source = (f"{filler}\n\nDo 2 actions: don't sit on the chair, "
              "then stand by the table in the room.")
    proposal = (f"{filler}\n\nDo 2 actions:\n1. Don't sit on the chair.\n"
                "2. Stand by the table in the room.")
    expected = proposal.replace("2. Stand", "2. Then stand")
    assert len(source.split()) > 200
    assert restore_missing_words(source, proposal) == (expected, 1)


def test_connective_never_opens_a_fragment_item():
    source = "We need 3 things from the shop: milk, eggs, and butter for the cake."
    proposal = "We need 3 things from the shop:\n\n- Milk\n- Eggs\n- Butter for the cake"
    assert restore_missing_words(source, proposal) is None
    assert engine_for(proposal).clean(source).text == source


def test_unresolved_cross_item_attachment_preserves_source():
    source = ("Do 2 actions: sit on the chair with both feet on the floor, "
              "slowly stand beside the table while keeping the doorway clear.")
    proposal = ("Do 2 actions:\n1. Sit on the chair with both feet on the floor.\n"
                "2. Stand beside the table while keeping the doorway clear.")
    assert restore_missing_words(source, proposal) is None
    assert engine_for(proposal).clean(source).text == source


def test_unpunctuated_connective_or_temporal_tail_preserves_source():
    for preceding, following in (("sit quietly until", "stand"),
                                 ("sit quietly since", "stand"),
                                 ("sit quietly from", "on stand"),
                                 ("sit on the chair", "stand")):
        source = (f"Do 2 actions: {preceding} then {following} beside the table "
                  "while keeping the doorway clear.")
        proposal = (f"Do 2 actions:\n1. {preceding.capitalize()}.\n"
                    f"2. {following.capitalize()} beside the table "
                    "while keeping the doorway clear.")
        assert restore_missing_words(source, proposal) is None
        assert engine_for(proposal).clean(source).text == source


def test_item_start_case_preserves_source_names_and_capital_i():
    for source_word, proposal_word, expected_word in (
        ("Jane", "Jane", "Jane"), ("i", "I", "I"),
    ):
        source = ("Do 2 actions: sit on the chair with both feet on the floor, "
                  f"then {source_word} will stand beside the table and wait.")
        proposal = ("Do 2 actions:\n1. Sit on the chair with both feet on the floor.\n"
                    f"2. {proposal_word} will stand beside the table and wait.")
        expected = proposal.replace(f"2. {proposal_word}", f"2. Then {expected_word}")
        assert restore_missing_words(source, proposal) == (expected, 1)
        assert engine_for(proposal).clean(source).text == expected


def test_authorized_list_and_spoken_step_formatting_remain_available():
    for source, proposal in (
        ("Here is a list of things: apples, pears, and bananas.",
         "Here is a list of things:\n\n- Apples\n- Pears\n- Bananas"),
        ("Do these steps: first sit on the chair, second stand beside the table.",
         "Do these steps:\n\n1. Sit on the chair.\n2. Stand beside the table."),
    ):
        assert restore_missing_words(source, proposal) is None
        result = engine_for(proposal).clean(source)
        assert result.path == "llm", (result.path, result.fallback_reason)
        assert result.text == proposal


def test_item_start_keeps_authorized_article_polish():
    for source_article, output_article, noun in (("an", "A", "user"), ("a", "An", "adult")):
        source = (f"Do 2 actions: read the printed receipt, and {source_article} {noun} "
                  "should prepare the table with clean paper.")
        proposal = ("Do 2 actions:\n1. Read the printed receipt.\n"
                    f"2. {output_article} {noun} should prepare the table with clean paper.")
        expected = proposal.replace(f"2. {output_article}", f"2. And {output_article.lower()}")
        assert restore_missing_words(source, proposal) == (expected, 1)
        assert engine_for(proposal).clean(source).text == expected


if __name__ == "__main__":
    tests = (test_restore_puts_the_dropped_words_back_in_place,
             test_nothing_to_restore_returns_none,
             test_engine_keeps_the_good_edits_when_only_coverage_failed,
             test_added_word_is_still_rejected_whole,
             test_losing_many_words_is_still_rejected_whole,
             test_dropped_connectives_start_the_following_numbered_or_bulleted_item,
             test_prior_completed_clause_keeps_its_omitted_tail_in_the_prior_item,
             test_source_boundary_keeps_then_in_the_completed_clause,
             test_existing_source_list_boundary_does_not_get_guessed_placement,
             test_within_item_conjunction_stays_inside_that_item,
             test_list_placement_does_not_rewrite_quoted_or_protected_content,
             test_contractions_do_not_stop_list_placement_in_a_long_window,
             test_connective_never_opens_a_fragment_item,
             test_unresolved_cross_item_attachment_preserves_source,
             test_unpunctuated_connective_or_temporal_tail_preserves_source,
             test_item_start_case_preserves_source_names_and_capital_i,
             test_authorized_list_and_spoken_step_formatting_remain_available,
             test_item_start_keeps_authorized_article_polish)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} coverage salvage tests passed")
