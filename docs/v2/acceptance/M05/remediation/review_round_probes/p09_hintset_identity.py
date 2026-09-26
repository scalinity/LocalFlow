"""AUDIT-05 identity: (a) the checked HintSet constructor freezes containers
only one level deep -- a nested mutable score/omission/scope value can be
changed after the id was bound, so one hint_set_id denotes two contents;
(b) the 'sealed' VocabularySnapshot exposes a mutable _select_memo that
select() trusts and returns through HintSet._frozen WITHOUT re-deriving the
id, so a poisoned memo yields a HintSet whose id does not match its content."""
from _common import *
import json
snap = V.VocabularySnapshot([ent("E-1", "One"), ent("E-2", "Two")])
sel = V.RelevantVocabularySelector(1)
hs = sel.select(snap, now_utc="t")
score = [1]
t0 = hs.terms[0]
forged_term = V.HintTerm(canonical=t0.canonical, entry_id=t0.entry_id, scope_kind=t0.scope_kind,
                         scope_value=t0.scope_value, source=t0.source, score=(score,))
om = [{"canonical": "Two", "entry_id": "E-2", "reason": ["budget_limit"]}]
h2 = V.HintSet(hint_set_id=None, selector_revision=hs.selector_revision,
               vocabulary_revision=hs.vocabulary_revision, scope=dict(hs.scope),
               terms=[forged_term], omitted=om, created_utc="t", term_limit=1)
before = (h2.hint_set_id, json.dumps(h2.to_json(), sort_keys=True))
score.append(99)                     # caller keeps a reference
om[0]["reason"].append("evil")
after = (h2.hint_set_id, json.dumps(h2.to_json(), sort_keys=True))
expect("same hint_set_id never describes two contents (nested values)",
       before[0] != after[0] or before[1] == after[1],
       {"id": after[0], "content_changed": before[1] != after[1]})
recomputed = V._hint_set_id(h2.selector_revision, h2.vocabulary_revision, h2.scope,
                            h2.terms, h2.omitted, h2.term_limit)
expect("stored id equals the id of the current content", recomputed == h2.hint_set_id,
       (h2.hint_set_id, recomputed))
# (b) memo poisoning through the sealed snapshot
snap2 = V.VocabularySnapshot([ent("E-1", "One"), ent("E-2", "Two")])
try:
    snap2._select_memo[(sel.SELECTOR_REVISION, sel.max_terms)] = (
        "m05hs:000000000000", hs.scope, (), ())
    poisoned = sel.select(snap2, now_utc="t")
    real_id = V._hint_set_id(poisoned.selector_revision, poisoned.vocabulary_revision,
                             poisoned.scope, poisoned.terms, poisoned.omitted, poisoned.term_limit)
    expect("select() never returns a HintSet whose id mismatches its content",
           poisoned.hint_set_id == real_id,
           {"id": poisoned.hint_set_id, "terms": len(poisoned.terms), "content_id": real_id})
except (AttributeError, TypeError) as e:
    expect("memo is not caller-mutable", True, type(e).__name__)
done()
