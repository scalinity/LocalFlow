"""AUDIT-19: biasing_qualified compares qualified_identity with the SAME
manifest's own fields and accepts any non-empty evidence string, so the
production manifest with supported flipped to True plus a copy of its own
identity qualifies -- even when its evidence text says no qualified
implementation exists, and even for a whitespace-only checkpoint. No
external record of 'the qualified identity' exists to compare against.
Also: a qualified manifest yields hint_disposition ignored=False with
ignored_reason='unsupported_by_adapter' (contradictory)."""
from _common import *
import copy
from localflow.v2 import capabilities as cap
from localflow.v2 import ids
base = cap.asr_capability_manifest("mlx-community/parakeet", model_revision="rev-A",
                                   runtime={"mlx": "0.1"})
def selfqualify(m, evidence=None, rev=None):
    m = copy.deepcopy(m)
    if rev is not None:
        m["model_revision"] = rev
    c = m["capabilities"]["contextual_biasing"]
    c["supported"] = True
    c["qualified_identity"] = {"adapter": m["adapter"], "model_id": m["model_id"],
                               "model_revision": m["model_revision"], "runtime": m["runtime"]}
    if evidence is not None:
        c["evidence"] = evidence
    return m
m1 = selfqualify(base)   # evidence left as 'no qualified biasing implementation exists ...'
print("evidence text:", m1["capabilities"]["contextual_biasing"]["evidence"])
expect("disqualifying evidence text does not qualify", not cap.biasing_qualified(m1), cap.biasing_qualified(m1))
m2 = selfqualify(base, evidence=".", rev=" ")
expect("whitespace checkpoint + '.' evidence does not qualify", not cap.biasing_qualified(m2), cap.biasing_qualified(m2))
snap = V.VocabularySnapshot([ent("E-1", "One")])
hs = V.RelevantVocabularySelector(5).select(snap)
disp = cap.hint_disposition(m1, hs)
print("disposition under qualified manifest:", {k: disp[k] for k in ("accepted_terms", "ignored", "ignored_reason")})
expect("qualified disposition is not labelled unsupported_by_adapter",
       disp["ignored_reason"] != "unsupported_by_adapter", disp["ignored_reason"])
done()
