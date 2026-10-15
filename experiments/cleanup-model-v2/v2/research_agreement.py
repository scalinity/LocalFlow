"""Compare four-way human choices with saved judge outputs; no API access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .stats import cohen_kappa, emit, index_rows, read_rows

CHOICES = ("a", "b", "tie", "both_wrong")


def latest_annotations(rows, allowed):
    latest = {}
    for row in rows:
        pid, choice = row["pair_id"], row["choice"]
        if pid not in allowed or choice not in (*CHOICES, None):
            raise ValueError("Unknown pair ID or annotation choice")
        # File order is authoritative, regardless of annotated_at clock skew.
        latest[pid] = choice
    return {pid: choice for pid, choice in latest.items() if choice is not None}


def validate_packet(pairs, key):
    indexed = index_rows(pairs, "pair_id")
    if not indexed or set(indexed) != set(key):
        raise ValueError("Pairs and private key must have the same nonempty IDs")
    for pid, entry in key.items():
        parent = entry["duplicate_of"]
        if parent is not None:
            if parent not in indexed or key[parent]["duplicate_of"] is not None:
                raise ValueError("Invalid duplicate reference")
            if (indexed[pid] | {"pair_id":parent}) != indexed[parent] or (entry | {"duplicate_of":None}) != key[parent]:
                raise ValueError("Test-retest pairs must be exact duplicates, including A/B order")
    return indexed


def validate_rule(rule):
    from .judge import SCHEMA
    fields = SCHEMA["properties"]["verdicts"]["items"]["properties"]
    failure = rule["failure_fields"]
    if not failure or len(set(failure)) != len(failure) or any(fields.get(f, {}).get("type") != "boolean" for f in failure):
        raise ValueError("Declare distinct boolean failure_fields")
    seen = set()
    for quality in rule["quality"]:
        field, tiers = quality["field"], quality["tiers"]
        flattened = [v for tier in tiers for v in tier]
        if field in seen or "enum" not in fields.get(field, {}) or not tiers or any(not tier for tier in tiers) or len(flattened) != len(set(flattened)) or set(flattened) != set(fields[field]["enum"]):
            raise ValueError("Quality tiers must partition one verdict enum from worst to best")
        seen.add(field)
    return rule


def verdict_choice(a, b, rule):
    """Apply the supplied, pre-declared rule; never invent a score or ordering."""
    bad_a, bad_b = (any(v[field] for field in rule["failure_fields"]) for v in (a, b))
    if bad_a and bad_b: return "both_wrong"
    if bad_a: return "b"
    if bad_b: return "a"
    def quality(verdict):
        return tuple(next(i for i,tier in enumerate(q["tiers"]) if verdict[q["field"]] in tier) for q in rule["quality"])
    qa, qb = quality(a), quality(b)
    return "a" if qa > qb else "b" if qb > qa else "tie"


def judge_choices(rows, pairs, key, *, stage="delivered", rule=None):
    if not rows: return {}
    if all("pair_id" in r for r in rows):
        indexed = index_rows(rows, "pair_id")
        if set(indexed) - set(pairs): raise ValueError("Judge choices refer to a different packet")
        if any(r["choice"] not in (*CHOICES, None) for r in rows): raise ValueError("Invalid judge choice")
        return {pid:r["choice"] for pid,r in indexed.items() if r["choice"] is not None}
    if rule is None:
        raise ValueError("Expanded judge verdicts require an explicit pre-declared --rule")
    validate_rule(rule)
    from .judge import parse_verdicts
    lookup = {}
    for row in rows:
        rid = (row["case_id"], row["model"], row["stage"])
        if rid in lookup: raise ValueError("Duplicate expanded judge row")
        verdict = row.get("verdict") if row.get("status") == "judged" else None
        if verdict is not None: parse_verdicts(json.dumps({"verdicts":[verdict]}))
        lookup[rid] = verdict
    result = {}
    for pid,pair in pairs.items():
        a = lookup.get((pair["case_id"],key[pid]["a_system"],stage))
        b = lookup.get((pair["case_id"],key[pid]["b_system"],stage))
        if a is not None and b is not None: result[pid] = verdict_choice(a,b,rule)
    return result


def comparison(human, predicted, population):
    eligible = [pid for pid in population if pid in human]
    common = [pid for pid in eligible if pid in predicted]
    table = {h:{j:0 for j in CHOICES} for h in CHOICES}
    for pid in common: table[human[pid]][predicted[pid]] += 1
    return {"n":len(common), "human_completed":len(eligible), "judge_missing":len(eligible)-len(common),
            "accuracy":sum(human[pid] == predicted[pid] for pid in common)/len(common) if common else None,
            "kappa":cohen_kappa([human[pid] for pid in common], [predicted[pid] for pid in common]),
            "confusion_human_rows_judge_columns":table}


def agreement(pairs, key, annotations, judges, *, stage="delivered", rule=None):
    indexed = validate_packet(pairs, key)
    human = latest_annotations(annotations, indexed)
    primary = [pid for pid in indexed if key[pid]["duplicate_of"] is None]
    duplicates = [pid for pid in indexed if key[pid]["duplicate_of"] is not None]
    completed = [pid for pid in duplicates if pid in human and key[pid]["duplicate_of"] in human]
    stable = sum(human[pid] == human[key[pid]["duplicate_of"]] for pid in completed)
    retest_table = {h:{j:0 for j in CHOICES} for h in CHOICES}
    for pid in completed: retest_table[human[key[pid]["duplicate_of"]]][human[pid]] += 1
    result = {"primary_population":"nonduplicate_pairs", "pairs":len(indexed),
              "human_completed":len(human), "human_pending_or_undone":len(indexed)-len(human),
              "rule":rule, "stage":stage, "judges":{},
              "human_test_retest":{"duplicate_pairs":len(duplicates), "completed":len(completed),
                  "consistent":stable, "consistency":stable/len(completed) if completed else None,
                  "confusion_original_rows_duplicate_columns":retest_table}}
    for name,rows in judges.items():
        predicted = judge_choices(rows,indexed,key,stage=stage,rule=rule)
        result["judges"][name] = {**comparison(human,predicted,primary),
                                  "including_duplicates":comparison(human,predicted,indexed)}
    return result


def presented_choices(rows, pairs, key, choices, identity, stage):
    """Orient pair preferences to their actual relative order in judge requests.

    Equal-text outputs share one output_id and have no two distinct positions.
    Missing judgments and deduplicated pairs are omitted from this export only.
    """
    lookup = {(r["case_id"],r["model"],r["stage"]):r.get("verdict") for r in rows}
    positions = {}
    for request in identity["request_parameters"]["initial"].values():
        user = next(m for m in request["messages"] if m["role"] == "user")
        outputs = json.loads(user["content"])["outputs"]
        for i,output in enumerate(outputs): positions[output["output_id"]] = i
    result = []
    reverse = {"a":"b","b":"a","tie":"tie","both_wrong":"both_wrong"}
    for pid,pair in pairs.items():
        if key[pid]["duplicate_of"] is not None or pid not in choices: continue
        a,b = key[pid]["a_system"],key[pid]["b_system"]
        va,vb = lookup.get((pair["case_id"],a,stage)),lookup.get((pair["case_id"],b,stage))
        if not va or not vb: continue
        oa,ob = va["output_id"],vb["output_id"]
        if oa == ob: continue
        if oa not in positions or ob not in positions: raise ValueError("Position identity does not cover the judged outputs")
        choice = choices[pid]
        if positions[oa] > positions[ob]: a,b,choice = b,a,reverse[choice]
        result.append({"pair_id":pid,"a_system":a,"b_system":b,"choice":choice})
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pairs"); p.add_argument("key"); p.add_argument("annotations")
    p.add_argument("--judge", action="append", required=True, metavar="NAME=FILE")
    p.add_argument("--rule"); p.add_argument("--stage", choices=("delivered","model_only"), default="delivered")
    p.add_argument("--output"); p.add_argument("--choices-dir")
    args = p.parse_args(argv)
    pairs = read_rows(args.pairs); key = json.loads(Path(args.key).read_text())
    annotations = read_rows(args.annotations); judges = {}; files = {}
    for argument in args.judge:
        name,sep,path = argument.partition("=")
        if not sep or name in judges or not name or not all(c.isalnum() or c in "-_" for c in name):
            raise ValueError("Use distinct simple judge names and NAME=FILE arguments")
        judges[name]=read_rows(path); files[name]=Path(path)
    rule = json.loads(Path(args.rule).read_text()) if args.rule else None
    result = agreement(pairs,key,annotations,judges,stage=args.stage,rule=rule)
    if args.choices_dir:
        dest=Path(args.choices_dir); dest.mkdir(parents=True,exist_ok=True)
        indexed=index_rows(pairs,"pair_id"); primary=[pid for pid in indexed if key[pid]["duplicate_of"] is None]
        human=latest_annotations(annotations,indexed)
        def save(path,rows):
            path.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows))
        save(dest/"human.jsonl",[{"pair_id":pid,"choice":human.get(pid)} for pid in primary])
        for name,rows in judges.items():
            choices=judge_choices(rows,indexed,key,stage=args.stage,rule=rule)
            save(dest/f"{name}.jsonl",[{"pair_id":pid,"choice":choices.get(pid)} for pid in primary])
            identity_path=files[name].with_name("identity.json")
            if identity_path.exists() and rows and "pair_id" not in rows[0]:
                positioned=presented_choices(rows,indexed,key,choices,json.loads(identity_path.read_text()),args.stage)
                save(dest/f"{name}-positions.jsonl",positioned)
    emit(result,args.output)


if __name__ == "__main__":
    main()
