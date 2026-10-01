"""Narrow separator authorization; no model, clipboard or desktop effects."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.cleanup.validation import validate


def main():
    source = "here is a list of grocery items tomatoes potatoes and lemons"
    good = "Here is a list of grocery items:\n- tomatoes\n- potatoes\n- lemons"
    assert validate(source, good).accepted
    corrupt = (
        "Here is a list of grocery items:\n- tomatoes\n- lemons",
        "Here is a list of grocery items:\n- potatoes\n- tomatoes\n- lemons",
        good + "\n- lemons",
        good + "\n- onions",
        "- tomatoes\n- potatoes\n- lemons",
    )
    for output in corrupt:
        assert not validate(source, output).accepted, output
    assert not validate(source, good, protected=[(source, "literal")]).accepted
    assert not validate("I bought tomatoes and lemons.",
                        "I bought tomatoes, lemons.").accepted
    pair_source = "here is a list of ingredients salt and pepper and olive oil"
    pair_good = "Here is a list of ingredients:\n- salt and pepper\n- olive oil"
    assert validate(pair_source, pair_good).accepted
    assert not validate(pair_source, pair_good.replace("salt and pepper", "salt pepper")).accepted
    condition_source = source + ". Do not buy onions."
    assert validate(condition_source, good + "\n\nDo not buy onions.").accepted
    assert not validate(condition_source, good + "\n\nBuy onions.").accepted
    print("12/12 list separator fidelity checks passed")


if __name__ == "__main__":
    main()
