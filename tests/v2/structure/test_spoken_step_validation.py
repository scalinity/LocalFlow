"""Step formatting guards, independent of model and desktop state."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.cleanup.validation import validate
from localflow.v2.cleanup.engine import parse_correction_output


def main():
    source = ("This is a test. I need you to follow step 1, check if this still "
              "works, step 2 confirm that it does, and step 3 write a report "
              "showing your validations.")
    good = ("This is a test. I need you to follow:\n"
            "1. Check if this still works.\n2. Confirm that it does.\n"
            "3. Write a report showing your validations.")
    checks = [(source, good, True)]
    for before, after in (("step 1", "step one"), ("step 2", "step two"),
                          ("step 3", "step three")):
        source = source.replace(before, after)
    checks.append((source, good, True))
    for bad in (
        good.replace("2. Confirm that it does.\n", ""),
        good.replace("1. Check if this still works.\n2. Confirm that it does.",
                     "1. Confirm that it does.\n2. Check if this still works."),
        good.replace("2. Confirm that it does.", "1. Confirm that it does."),
        good.replace("2. Confirm that it does.", "4. Confirm that it does."),
        good.replace("showing your validations", "showing your validations and publish it"),
        good.replace("This is a test. I need you to follow:\n", ""),
        good + "\n4. Write a report showing your validations.",
    ):
        checks.append((source, bad, False))
    pair = "step 1 save and close the file and step 2 check the backup"
    pair_good = "1. Save and close the file.\n2. Check the backup."
    checks.extend([
        (pair, pair_good, True),
        (pair, pair_good.replace("save and", "save").replace("Save and", "Save"), False),
        ("step 7 inspect the archive and step 8 record the result",
         "7. Inspect the archive.\n8. Record the result.", True),
        ("step 7 inspect the archive and step 8 record the result",
         "1. Inspect the archive.\n2. Record the result.", False),
        ("step 1 inspect the archive and step 3 record the result",
         "1. Inspect the archive.\n2. Record the result.", False),
        ("step 1 inspect the archive and step 1 record the result",
         "1. Inspect the archive.\n2. Record the result.", False),
        ("step 2 inspect the archive and step 1 record the result",
         "2. Inspect the archive.\n3. Record the result.", False),
        ("Repeat step 1 before step 2.", "Repeat:\n1. Before.\n2. Continue.", False),
        ('The labels "step one" and "step two" appear in the manual.',
         "The labels:\n1. Appear in the manual.\n2. Continue.", False),
        ("step 1 do not restart step 2 wait 30 seconds",
         "1. Do not restart.\n2. Wait 30 seconds.", True),
        ("step 1 do not restart step 2 wait 30 seconds",
         "1. Restart.\n2. Wait 30 seconds.", False),
        ("step 1 do not restart step 2 wait 30 seconds",
         "1. Do not restart.\n2. Wait 300 seconds.", False),
        ("step 1 open the folder. Keep the backup. step 2 inspect the file.",
         "1. Open the folder. Keep the backup.\n2. Inspect the file.", True),
        ("step 1 inspect the file step 2 return to step 1 if it fails",
         "1. Inspect the file.\n2. Return to step 1 if it fails.", True),
        ("step number one open the folder step number two inspect the file",
         "1. Open the folder.\n2. Inspect the file.", True),
        ("Step Eleven open the folder Step Twelve inspect the file",
         "11. Open the folder.\n12. Inspect the file.", True),
    ])
    for index, (raw, output, accepted) in enumerate(checks):
        report = validate(raw, output)
        assert report.accepted == accepted, (index, raw, output, report)
    assert not validate(source, good, protected=[(source, "literal")]).accepted
    corrected = "step one um check monday no wait tuesday and step two write the report"
    accepted, rejected = parse_correction_output("um check monday no wait", corrected, [])
    assert not accepted and rejected[0].reason == "overbroad_calendar_value"
    accepted, rejected = parse_correction_output("monday no wait", corrected, [])
    assert len(accepted) == 1 and not rejected
    accepted, rejected = parse_correction_output("to monday no wait",
                                                "move it to monday no wait to tuesday", [])
    assert len(accepted) == 1 and not rejected
    accepted, rejected = parse_correction_output("check march no wait",
                                                "check march no wait april", [])
    assert not accepted and rejected[0].reason == "overbroad_calendar_value"
    accepted, rejected = parse_correction_output("march no wait",
                                                "check march no wait april", [])
    assert len(accepted) == 1 and not rejected
    print(f"{len(checks) + 6}/{len(checks) + 6} spoken-step fidelity checks passed")


if __name__ == "__main__":
    main()
