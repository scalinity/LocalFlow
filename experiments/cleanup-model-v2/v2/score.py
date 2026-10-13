"""Transparent reference metrics, with punctuation and long-form coverage."""
from __future__ import annotations

import collections
import difflib
import json
import re
import statistics
from .common import *
from lfx.score import score_synthetic, score_real, edit_distance
from lfx.audio import lexical


def punctuation_slots(text):
    matches=list(re.finditer(r"\w+(?:['’]\w+)*",text))
    words=[m.group().casefold() for m in matches]
    slots=collections.Counter()
    ends=[0]+[m.end() for m in matches]
    starts=[m.start() for m in matches]+[len(text)]
    for i,(a,b) in enumerate(zip(ends,starts)):
        for mark in re.findall(r"[^\w\s]",text[a:b]):
            slots[(i,mark)]+=1
    return words,slots


def punctuation(hyp,reference):
    hw,hs=punctuation_slots(hyp);rw,rs=punctuation_slots(reference)
    mapping={0:0}
    for block in difflib.SequenceMatcher(None,hw,rw,autojunk=False).get_matching_blocks():
        for k in range(block.size):
            mapping[block.a+k+1]=block.b+k+1
    mapped=collections.Counter()
    for (i,p),n in hs.items():
        mapped[(mapping.get(i, -(i+1)),p)]+=n
    tp=sum((mapped&rs).values());fp=sum((mapped-rs).values());fn=sum((rs-mapped).values())
    f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 1.0
    return {"tp":tp,"fp":fp,"fn":fn,"f1":f1,"exact":hw==rw and mapped==rs}


def canon(text):
    return re.sub(r"[ \t]+"," ",text.strip()).replace("\r\n","\n")


def synthetic(case,text,delivered):
    base=score_synthetic(case,text,delivered=delivered)
    target=case["target"]
    initial=punctuation(case["model_input"],target)
    # Isolate boundary-mark repairs from cases that also require a word change.
    # The broader legacy field below intentionally retains its original meaning.
    punctuation_only_needed=(punctuation_slots(case['model_input'])[0]==punctuation_slots(target)[0]
                             and not initial['exact'])
    if text is None:
        return {**base,"reference_complete":False,"reference_repair":False if not case['is_noop'] else None,
                "punctuation_f1":0,"punctuation_exact":False,
                "punctuation_repaired":False if not initial['exact'] else None,
                "punctuation_only_repaired":False if punctuation_only_needed else None}
    punct=punctuation(text,target)
    base.update(reference_complete=canon(text)==canon(target),
                reference_repair=(canon(text)==canon(target)) if not case["is_noop"] else None,
                punctuation_f1=punct["f1"],punctuation_exact=punct["exact"],
                punctuation_tp=punct["tp"],punctuation_fp=punct["fp"],punctuation_fn=punct["fn"],
                punctuation_needed=not initial["exact"],
                punctuation_repaired=punct["exact"] if not initial["exact"] else None,
                punctuation_only_needed=punctuation_only_needed,
                punctuation_only_repaired=punct['exact'] if punctuation_only_needed else None,
                punctuation_gain=punct["f1"]-initial["f1"],
                unchanged=text==case["model_input"])
    return base


def real(case,text):
    metrics=score_real(case,{"normalized":case["model_input"]},text)
    if text is not None:
        refs=[case["lexical_reference"]] if case["source"]=="fleurs" else list(case["contract_refs"].values())
        hyp=" ".join(lexical(text))
        best=min([(edit_distance(list(hyp),list(" ".join(lexical(ref)))),len(" ".join(lexical(ref)))) for ref in refs],key=lambda p:p[0]/max(1,p[1]))
        metrics.update(cer_errors=best[0],cer_chars=best[1])
    return metrics


def aggregate(cases,rows):
    case_map={c["case_id"]:c for c in cases}
    out={}
    for origin in ("synthetic","real_audio"):
        selected=[(case_map[r["case_id"]],r) for r in rows if r["case_id"] in case_map and case_map[r["case_id"]]["origin"]==origin]
        if not selected:continue
        bymode={}
        for mode in ("model_only","delivered"):
            measured=[synthetic(c,r.get(mode),mode=="delivered") if origin=="synthetic" else real(c,r.get(mode)) for c,r in selected]
            a={"n":len(measured)}
            for field in ("damage","facts_changed","hallucination","omission","negation_changed","noop_preserved",
                          "reference_complete","reference_repair","repair_success","correction_success","punctuation_repaired","punctuation_only_repaired",
                          "punctuation_exact","punctuation_f1","punctuation_gain","unnecessary_edit","unauthorized_edit","list_ok"):
                vals=[m[field] for m in measured if m.get(field) is not None]
                if vals:a[field]={"value":sum(vals)/len(vals),"n":len(vals),"sum":sum(vals)}
            for prefix,den in (("wer","words"),("cer","chars")):
                errs=sum(m.get(prefix+"_errors",0) for m in measured)
                size=sum(m.get(prefix+"_"+den,0) for m in measured)
                if size:a[prefix]={"value":errs/size,"errors":errs,"denominator":size}
            bymode[mode]=a
        latency=sorted(r["total_cleanup_ms"] for _,r in selected)
        bymode["runtime"]={"median_ms":statistics.median(latency),"p95_ms":latency[min(len(latency)-1,int((len(latency)-1)*.95))],
                          "peak_mlx_bytes":max(r.get("peak_mem_bytes",0) for _,r in selected),
                          "peak_rss_bytes":max(r.get("rss_peak_bytes",0) for _,r in selected),
                          "fallback_count":sum(r["path"]!="llm" for _,r in selected),
                          "fallback_rate":sum(r["path"]!="llm" for _,r in selected)/len(selected),
                          "validator_failures":dict(collections.Counter(f for _,r in selected for f in r.get("validator_failures",[])))}
        out[origin]=bymode
    return out


def summarize(cases_file,output_name):
    cases=read_jsonl(Path(cases_file))
    rows=read_jsonl(ART/"eval"/f"{output_name}.jsonl")
    out=aggregate(cases,rows)
    write_json(ART/"scores"/f"{output_name}.json",out)
    print(json.dumps(out,indent=2))


if __name__=="__main__":
    import sys
    summarize(sys.argv[1],sys.argv[2])
