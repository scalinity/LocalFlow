"""Deterministic paired analyses. Computation uses only the standard library."""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import math
import random
import statistics
from pathlib import Path


def finite(values):
    values = list(values)
    if not values or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("Expected nonempty finite numeric observations")
    return values


def aligned(a, b):
    if not a or set(a) != set(b):
        raise ValueError("Systems must have exactly the same nonempty case IDs")
    keys = sorted(a)
    return [a[k] for k in keys], [b[k] for k in keys]


def quantile(values, probability):
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    low = math.floor(index); high = math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def paired_bootstrap(a, b, *, resamples=10000, seed=20261015, confidence=.95):
    """Percentile CI for mean(a-b), resampling whole paired cases with replacement."""
    a, b = aligned(a, b)
    finite(a); finite(b)
    if type(resamples) is not int or resamples < 1 or not 0 < confidence < 1:
        raise ValueError("Invalid bootstrap settings")
    differences = [x - y for x, y in zip(a, b)]
    n = len(differences); rng = random.Random(seed)
    samples = [sum(differences[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)]
    tail = (1 - confidence) / 2
    return {"n": n, "difference_a_minus_b": statistics.mean(differences),
            "ci": [quantile(samples, tail), quantile(samples, 1-tail)],
            "confidence": confidence, "resamples": resamples, "seed": seed,
            "method": "paired_percentile_linear_quantile"}


def exact_mcnemar(a, b):
    """Two-sided exact binomial test on discordant binary failure indicators."""
    a, b = aligned(a, b)
    if any(type(v) not in (bool, int) or v not in (0, 1) for v in a+b):
        raise ValueError("McNemar requires binary per-case failures")
    table = [[0, 0], [0, 0]]
    for x, y in zip(a, b):
        table[int(x)][int(y)] += 1
    only_b, only_a = table[0][1], table[1][0]
    n = only_a + only_b
    # Integer arithmetic until the final division avoids binomial rounding error.
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(only_a, only_b)+1)) / (2**n)) if n else 1.0
    return {"n": len(a), "table_a_rows_b_columns": table, "a_only_failures": only_a,
            "b_only_failures": only_b, "discordant": n, "p_two_sided": p}


def cohen_kappa(a, b):
    """Unweighted nominal kappa. None ratings are pairwise omitted and counted."""
    a, b = list(a), list(b)
    if len(a) != len(b):
        raise ValueError("Rating vectors have different lengths")
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    n = len(pairs)
    if not n:
        return {"n": 0, "omitted": len(a), "kappa": None, "reason": "no_paired_ratings"}
    ca, cb = collections.Counter(x for x, _ in pairs), collections.Counter(y for _, y in pairs)
    observed = sum(x == y for x, y in pairs) / n
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / n**2
    return {"n": n, "omitted": len(a)-n, "observed_agreement": observed,
            "expected_agreement": expected, "kappa": (observed-expected)/(1-expected) if expected < 1 else None,
            "reason": "constant_category" if expected == 1 else None}


def krippendorff_alpha(units):
    """Nominal alpha, with missing ratings and >=2 raters per usable unit.

    Each unit contributes m*(m-1) ordered coincidences weighted by 1/(m-1).
    Marginals and expected disagreement use only these pairable units.
    """
    all_units = [list(u) for u in units]
    usable = [[v for v in u if v is not None] for u in all_units]
    usable = [u for u in usable if len(u) >= 2]
    counts = collections.Counter(v for unit in usable for v in unit)
    n = sum(counts.values())
    if n < 2:
        return {"units": len(usable), "omitted_units": len(all_units)-len(usable),
                "ratings": n, "alpha": None, "reason": "no_pairable_ratings"}
    observed = sum(sum(x != y for x, y in itertools.permutations(u, 2)) / (len(u)-1)
                   for u in usable) / n
    expected = (n*n - sum(v*v for v in counts.values())) / (n*(n-1))
    return {"units": len(usable), "omitted_units": len(all_units)-len(usable), "ratings": n,
            "observed_disagreement": observed, "expected_disagreement": expected,
            "alpha": 1-observed/expected if expected else None,
            "reason": "constant_category" if not expected else None}


def position_bias(forward, swapped):
    """Average first-minus-second preference across two genuinely swapped runs.

    a=+1, b=-1, tie/both_wrong=0. Stable system preference cancels on reversal.
    This is a descriptive paired contrast, not a claim of causal bias.
    """
    first, second = aligned(forward, swapped)
    signs = {"a": 1, "b": -1, "tie": 0, "both_wrong": 0}
    differences = []
    for x, y in zip(first, second):
        if x["a_system"] == x["b_system"] or (x["a_system"], x["b_system"]) != (y["b_system"], y["a_system"]):
            raise ValueError("Position runs must swap the same two systems")
        if x["choice"] not in signs or y["choice"] not in signs:
            raise ValueError("Position choices must be a, b, tie or both_wrong")
        differences.append((signs[x["choice"]] + signs[y["choice"]])/2)
    return {"n_pairs": len(differences), "first_minus_second": statistics.mean(differences),
            "ties_and_both_wrong": "zero", "range": [-1, 1]}


def across_seeds(values):
    values = finite(values)
    return {"n": len(values), "mean": statistics.mean(values),
            "sd": statistics.stdev(values) if len(values) > 1 else None, "sd_ddof": 1}


def holm(contrasts, *, alpha=.05):
    """Holm step-down adjusted p-values; retain every pre-declared contrast."""
    if not contrasts or not 0 < alpha < 1:
        raise ValueError("Expected contrasts and a valid alpha")
    names = [r["name"] for r in contrasts]
    if len(set(names)) != len(names):
        raise ValueError("Contrast names must be unique")
    if any(type(r["p"]) not in (float, int) or not math.isfinite(r["p"]) or not 0 <= r["p"] <= 1 for r in contrasts):
        raise ValueError("Every pre-declared contrast needs a finite p-value in [0,1]")
    adjusted = {}; running = 0.0
    for rank, index in enumerate(sorted(range(len(contrasts)), key=lambda i: (contrasts[i]["p"], i))):
        running = max(running, min(1.0, (len(contrasts)-rank)*contrasts[index]["p"]))
        adjusted[index] = running
    return [{**r, "p_holm": adjusted[i], "reject": adjusted[i] <= alpha} for i, r in enumerate(contrasts)]


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def index_rows(rows, key="case_id"):
    result = {}
    for row in rows:
        if row[key] in result:
            raise ValueError("Duplicate analysis ID: " + row[key])
        result[row[key]] = row
    return result


def emit(value, path=None):
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)
    else:
        print(text, end="")


def export_scores(cases_file, output_file, *, prefix, system, stage):
    """Expose existing per-case score functions; aggregate JSON cannot be resampled."""
    from .common import ART
    from . import score
    from .research_inputs import development_cases
    cases = development_cases(cases_file, prefix)
    outputs = index_rows(read_rows(ART / "eval" / f"{prefix}-{system}.jsonl"))
    case_map = index_rows(cases)
    aligned(case_map, outputs)
    rows = []
    for cid in sorted(case_map):
        c = case_map[cid]; output = outputs[cid].get(stage)
        metrics = score.synthetic(c, output, stage == "delivered") if c["origin"] == "synthetic" else score.real(c, output)
        rows.append({**metrics, "case_id": cid, "system": system, "stage": stage})
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False)+"\n" for r in rows))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    paired = sub.add_parser("paired")
    paired.add_argument("a"); paired.add_argument("b"); paired.add_argument("--score", required=True)
    paired.add_argument("--failure"); paired.add_argument("--resamples", type=int, default=10000)
    paired.add_argument("--seed", type=int, default=20261015); paired.add_argument("--output")
    ratings = sub.add_parser("ratings")
    ratings.add_argument("files", nargs="+"); ratings.add_argument("--field", required=True)
    ratings.add_argument("--id", default="case_id"); ratings.add_argument("--output")
    position = sub.add_parser("position")
    position.add_argument("forward"); position.add_argument("swapped")
    position.add_argument("--id", default="pair_id"); position.add_argument("--output")
    seeds = sub.add_parser("seeds")
    seeds.add_argument("values", nargs="+", type=float); seeds.add_argument("--output")
    correction = sub.add_parser("holm")
    correction.add_argument("contrasts"); correction.add_argument("--alpha", type=float, default=.05)
    correction.add_argument("--output")
    export = sub.add_parser("export")
    export.add_argument("cases"); export.add_argument("--system", required=True)
    export.add_argument("--prefix", default="development"); export.add_argument("--stage", choices=("delivered", "model_only"), default="delivered")
    export.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        export_scores(args.cases, args.output, prefix=args.prefix, system=args.system, stage=args.stage)
        return
    if args.command == "paired":
        a, b = index_rows(read_rows(args.a)), index_rows(read_rows(args.b))
        result = {"bootstrap": paired_bootstrap({k: r[args.score] for k, r in a.items()},
            {k: r[args.score] for k, r in b.items()}, resamples=args.resamples, seed=args.seed)}
        if args.failure:
            result["mcnemar"] = exact_mcnemar({k:r[args.failure] for k,r in a.items()}, {k:r[args.failure] for k,r in b.items()})
    elif args.command == "ratings":
        judges = [index_rows(read_rows(f), args.id) for f in args.files]
        if len(judges) < 2: raise ValueError("At least two judges required")
        if any(set(j) != set(judges[0]) for j in judges[1:]): raise ValueError("Rating files must cover the same IDs; use explicit nulls for missing ratings")
        keys = sorted(judges[0])
        result = {"alpha_nominal": krippendorff_alpha([[j[k][args.field] for j in judges] for k in keys]),
                  "kappa": {f"{i}:{j}": cohen_kappa([judges[i][k][args.field] for k in keys], [judges[j][k][args.field] for k in keys])
                            for i,j in itertools.combinations(range(len(judges)),2)}, "judge_files": args.files}
    elif args.command == "position":
        result = position_bias(index_rows(read_rows(args.forward), args.id), index_rows(read_rows(args.swapped), args.id))
    elif args.command == "seeds":
        result = across_seeds(args.values)
    else:
        result = holm(json.loads(Path(args.contrasts).read_text()), alpha=args.alpha)
    emit(result, args.output)


if __name__ == "__main__":
    main()
