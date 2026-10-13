"""Create the complete local offline report exclusively from saved measurements."""
from __future__ import annotations

import collections
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from .common import *
from .score import aggregate,synthetic,real,canon


def pct(value):
    return "Not run" if value is None else f"{100*value:.2f}%"


def build():
    if (ART / "remediation/decision.json").exists():
        from .remediation_report import build as build_fresh
        return build_fresh()
    decision=read_json(ART/"results/decision.json")
    if not decision:
        raise RuntimeError("A measured recommendation is required before publishing the report")
    cases=read_jsonl(ART/"dataset/final_cases.jsonl")
    byid={c["case_id"]:c for c in cases}
    inspected=read_json(ART/'results/engineering-flag-review.json',{}).get('cases',{})
    models=[k for k in ("A","C","D","E","C-engine") if (ART/"eval"/f"final-{k}.jsonl").exists()]
    if not all(k in models for k in ('A','C','D','E')):
        raise RuntimeError('All four requested final models must be evaluated')
    rows={k:read_jsonl(ART/"eval"/f"final-{k}.jsonl") for k in models}
    if any(len(v)!=len(cases) or {r["case_id"] for r in v}!=set(byid) for v in rows.values()):
        raise RuntimeError("Final evaluation is incomplete")
    judges=read_jsonl(ART/"judge/verdicts.jsonl")
    judge_map={(v['case_id'],v['model'],v['stage']):v for v in judges}
    required={(c['case_id'],k,stage) for c in cases for k in models for stage in ('model_only','delivered')}
    if not required.issubset(judge_map) or any(judge_map[key]['status']!='judged' for key in required):
        raise RuntimeError('Final blinded assessment is incomplete; unjudged outputs remain unverified')
    flagged={v['case_id'] for v in judges if v['model'] in ('C','D','E') and v['stage']=='delivered'
             and (any(v['verdict'][f] for f in ('semantic_damage','critical_fact_changed','hallucination','unwanted_edit'))
                  or v['verdict']['cleanup']=='wrong')}
    if not flagged.issubset(inspected):
        raise RuntimeError('Candidate checker flags still require inspection before recommendation')
    aggs={k:aggregate(cases,rows[k]) for k in models}
    audio_cases=[c for c in cases if c['origin']=='real_audio']
    audio_baseline=[]
    for label,field in [('Raw Parakeet','raw_input'),('After upstream normalization','model_input')]:
        measures=[real(c,c[field]) for c in audio_cases]
        errors=sum(m['wer_errors'] for m in measures);words=sum(m['wer_words'] for m in measures)
        chars=sum(m['cer_chars'] for m in measures);char_errors=sum(m['cer_errors'] for m in measures)
        audio_baseline.append([label,len(measures),pct(errors/words),f'{errors}/{words}',pct(char_errors/chars),f'{char_errors}/{chars}'])
    get=lambda k,o,m:aggs.get(k,{}).get(o,{}).get("delivered",{}).get(m,{}).get("value")
    best=decision["best_key"]
    primary=[k for k in ("A","C","D","E") if k in models]
    maps={k:{r["case_id"]:r for r in rows[k]} for k in models}
    correct_proposals_blocked=sum(
        c['origin']=='synthetic' and not c.get('is_noop',False)
        and canon(maps['E'][c['case_id']].get('model_only') or '')==canon(c['target'])
        and canon(maps['E'][c['case_id']]['delivered'])!=canon(c['target'])
        for c in cases)
    examples=[]
    for c in cases:
        outputs={}
        for k in primary:
            r=maps[k][c["case_id"]]
            s=synthetic(c,r["delivered"],True) if c["origin"]=="synthetic" else real(c,r["delivered"])
            outputs[k]={"delivered":r["delivered"],"model_only":r.get("model_only"),
                        "path":r["path"],"ms":r["total_cleanup_ms"],"failures":r.get("validator_failures",[]),
                        "reference_complete":s.get("reference_complete"),"damage":s.get("damage"),
                        "reference_complete_by_stage":{"delivered":s.get('reference_complete'),
                            "model_only":canon(r.get('model_only') or '')==canon(c['target']) if c['origin']=='synthetic' else None},
                        "assessment":{stage:judge_map[(c['case_id'],k,stage)]['verdict'] for stage in ('model_only','delivered')}}
        reference=c.get("target") or c.get("raw_transcription") or c.get("verbatim_reference")
        alternatives=c.get('contract_refs')
        if alternatives:
            reference='\n\n'.join(label.replace('_',' ')+': '+value for label,value in alternatives.items())
        examples.append({"id":c["case_id"],"origin":c["origin"],"category":c["category"],"input":c["model_input"],
                         "raw_input":c['raw_input'] if c['origin']=='real_audio' and c['raw_input']!=c['model_input'] else None,
                         "inspection_note":inspected.get(c['case_id'],{}).get('reason'),
                         "target":reference,"reference_label":"Fixed synthetic target" if c['origin']=='synthetic' else "Fixed public reference alternatives" if alternatives else "Fixed public transcription",
                         "is_noop":c.get("is_noop",False),"outputs":outputs})
    hero=next((c for c in examples if c['id']==decision.get('hero_case_id')),None)
    if hero is None:hero=next((c for c in examples if c["origin"]=="synthetic" and len(c["input"])<420
               and c["outputs"].get(best,{}).get("reference_complete")
               and not c["outputs"].get("C",{}).get("reference_complete")),None)
    if hero is None:
        hero=next((c for c in examples if c["origin"]=="synthetic" and len(c["input"])<350),None)
    hero_view=None if hero is None else {"input":hero["input"],"C":hero["outputs"]["C"]["delivered"],
              "candidate":hero["outputs"][best]["delivered"],"candidate_label":best+" · Evaluated candidate",
              "caption":hero["id"]+" · fixed synthetic evaluation · a measured example, not a typical-effect claim"}
    cats={}
    for origin in ("synthetic","real_audio"):
        cats[origin]={}
        for category in sorted({c["category"] for c in cases if c["origin"]==origin}):
            subset=[c for c in cases if c["origin"]==origin and c["category"]==category]
            ids={c["case_id"] for c in subset};rec={"n":len(subset)}
            for k in models:
                a=aggregate(subset,[r for r in rows[k] if r["case_id"] in ids])[origin]
                metric="reference_complete" if origin=="synthetic" else "wer"
                rec[k]={mode:a[mode].get(metric) for mode in ("model_only","delivered")}
            cats[origin][category]=rec
    data=read_json(ART/"dataset/stats.json",{})
    coverage=read_json(ART/"results/data-coverage.json",{})
    trainstats=data.get("splits",{}).get("train",{})
    old=read_json(ART/"investigation.json",{})
    curves={}
    for name,root in [("Original C",OLD_ART/"train/main")]+[(p.name,p) for p in sorted((ART/"train").glob("*")) if p.is_dir()]:
        ms=read_jsonl(root/"metrics.jsonl")
        if not ms:continue
        curves[name]=[{"name":"Training","color":"#8A5AB5","points":[{"x":m["update"],"y":m["loss"]} for m in ms if m["event"]=="train"]},
                      {"name":"Validation","color":"#195C5D","points":[{"x":m["update"],"y":m["val_loss"]} for m in ms if m["event"]=="val"]}]
    scaling=read_json(ART/"results/scaling.json",{"rows":[],"series":[],"note":"Not run"})
    ledger=read_json(ART/"claude/ledger.json",{"entries":{},"reservations":{}})
    spend=collections.defaultdict(lambda:{"cost":0.,"input":0,"output":0,"cache_read":0,"cache_write":0,"requests":0})
    entry_models={};request_counts={}
    for manifest in (ART/"claude").glob("*/manifest.json"):
        m=read_json(manifest)
        model=read_json(manifest.parent/'pricing.json',{}).get('model','Unrecorded model')
        for attempt in m["attempts"]:
            entry_models[attempt['ledger_key']]=model
            request_counts[attempt['ledger_key']]=len(attempt.get('custom_ids',[]))
    for key,e in ledger["entries"].items():
        p=spend[entry_models.get(key,'Unrecorded model')+' / '+e['purpose']]
        p['cost']+=e.get('actual_usd',0);p['requests']+=request_counts.get(key,0)
        for field in ("input","output","cache_read","cache_write"):p[field]+=e.get("usage",{}).get(field,0)
    total=sum(p["cost"] for p in spend.values())
    budget=CONFIG['claude']['spend_cap_usd']
    outstanding=sum(e["max_usd"] for e in ledger["entries"].values() if e["state"]=="outstanding")
    costrows=[[k,v["requests"],f"{v['input']:,}",f"{v['output']:,}",f"{v['cache_read']:,}",f"{v['cache_write']:,}",f"${v['cost']:.4f}"] for k,v in spend.items()]
    checks=read_json(ART/"checks/summary.json",[])
    identities=read_json(ART/"results/model-identities.json",{})
    runtime=[]
    for k in primary:
        rt=aggs[k].get("synthetic",{}).get("runtime",{})
        rr=aggs[k].get("real_audio",{}).get("runtime",{})
        ident=identities.get(k,{})
        runtime.append([k,f"{rt.get('median_ms',0):.0f}",f"{rt.get('p95_ms',0):.0f}",f"{rr.get('median_ms',0):.0f}",
                        f"{rr.get('p95_ms',0):.0f}",f"{max(rt.get('peak_mlx_bytes',0),rr.get('peak_mlx_bytes',0))/1e9:.2f}",
                        f"{max(rt.get('peak_rss_bytes',0),rr.get('peak_rss_bytes',0))/1e9:.2f}",
                        f"{ident['size_bytes']/1e9:.2f}" if ident.get('size_bytes') else "Not run"])
    ablation=[[k,pct(get(k,'synthetic','reference_repair')),pct(get(k,'synthetic','punctuation_only_repaired')),
               pct(get(k,'synthetic','noop_preserved')),pct(aggs[k]['synthetic']['runtime']['fallback_rate']),
               sum(v['verdict']['semantic_damage'] for v in judges if v['model']==k and v['stage']=='delivered' and byid[v['case_id']]['origin']=='synthetic')] for k in models]
    judge_scopes={};cleanup_scopes={}
    for origin in ('synthetic','real_audio'):
        for stage in ('model_only','delivered'):
            table_rows=[];cleanup_rows=[]
            for k in primary:
                selected=[v['verdict'] for v in judges if v['model']==k and v['stage']==stage
                          and v['status']=='judged' and byid[v['case_id']]['origin']==origin]
                table_rows.append([k,len(selected),sum(v['semantic_damage'] for v in selected),
                                   sum(v['critical_fact_changed'] for v in selected),
                                   sum(v['hallucination'] for v in selected),sum(v['unwanted_edit'] for v in selected),
                                   sum(v['punctuation']=='improved' for v in selected),sum(v['punctuation']=='worse' for v in selected)])
                cleanup_rows.append([k,len(selected),*[sum(v['cleanup']==status for v in selected)
                                     for status in ('complete','partial','none_needed','wrong')],
                                     *[sum(v['self_correction']==status for v in selected)
                                     for status in ('resolved','unresolved','wrong')]])
            judge_scopes[origin+':'+stage]=table_rows
            cleanup_scopes[origin+':'+stage]=cleanup_rows
    inspection_scopes={}
    for origin in ('synthetic','real_audio'):
        selected=[v for cid,v in inspected.items() if byid[cid]['origin']==origin]
        inspection_scopes[origin]=[[k,len(selected),
            sum(v[k].get('introduced_semantic_damage',False) or v[k].get('critical_fact_change',False) for v in selected),
            sum(v[k].get('introduced_hallucination',False) for v in selected)] for k in ('C','D','E')]
    long_cases=[c for c in cases if len(c['model_input'].split())>200]
    long_ids={c['case_id'] for c in long_cases}
    long_rows=[]
    for k in primary:
        measured=aggregate(long_cases,[r for r in rows[k] if r['case_id'] in long_ids])
        if 'synthetic' in measured:
            a=measured['synthetic'];rt=a['runtime']
            assessed=[judge_map[(c['case_id'],k,'delivered')]['verdict'] for c in long_cases if c['origin']=='synthetic']
            long_rows.append([k,a['delivered']['n'],pct(a['model_only'].get('reference_repair',{}).get('value')),
                              pct(a['delivered'].get('reference_repair',{}).get('value')),
                              sum(v['cleanup']=='complete' for v in assessed),
                              sum(v['semantic_damage'] for v in assessed),pct(rt['fallback_rate']),
                              f"{rt['median_ms']:.0f}",f"{rt['p95_ms']:.0f}"])
    rejection_rows=[]
    for k in models:
        counts=collections.Counter(f for r in rows[k] for f in r.get('validator_failures',[]))
        rejection_rows.extend([[k,reason,n] for reason,n in counts.most_common()])
    report={
        "created_label":datetime.now(ZoneInfo('America/New_York')).strftime('%B %d, %Y · %H:%M ET'),
        "intro":"A second product experiment on the quantized Qwen3.5-4B cleanup model, with fresh labels, broader dictation, and an isolated parser repair.",
        "model_order":primary,"best_key":best,"recommendation":decision,"hero":hero_view,
        "headlines":decision.get('headlines',[]),"aggregates":aggs,"categories":cats,"examples":examples,
        "audio_baseline":{"columns":["Stage","Clips","WER","Word errors / words","CER","Character errors / characters"],
                          "rows":audio_baseline,
                          "note":f"Upstream normalization changed {sum(c.get('normalization_changed',False) for c in audio_cases)} of {len(audio_cases)} recordings. Every cleanup model receives the same normalized text. Public references are fixed; DisfluencySpeech permits the same set of transcript variants for every model."},
        "quality_findings":decision.get('quality_findings',[]),
        "judge":{"scopes":judge_scopes,"columns":["Model","Judged outputs","Semantic damage","Critical facts","Hallucinations","Unwanted edits","Punctuation improved","Punctuation worse"],
                 "cleanup_scopes":cleanup_scopes,"cleanup_columns":["Model","Judged outputs","Complete repair","Partial repair","None needed","Wrong cleanup","Correction resolved","Unresolved","Wrong correction"],
                 "note":"Opus 5.5 assessed randomized, anonymous outputs. Identical outputs share one assessment. The tables retain raw checker flags, which can include mistakes; per-example reasons are available in the reading desk. Meaning and fact changes are assessed relative to the common normalized input; recognizer and upstream-normalization errors are separate from damage introduced by cleanup. This is an automated assessment, not human adjudication; all unjudged outputs remain unverified."},
        "inspection":{"scopes":inspection_scopes,"columns":["Model","Flagged cases inspected","Clear meaning / fact changes","Unauthorized added words"],
                      "note":"Engineering inspection compared C, D and E on the same set of checker-flagged cases, including unwanted edits and wrong cleanup. It distinguishes unchanged fallback, unresolved repairs and awkward formatting from clear introduced meaning or fact changes. Raw verdicts above are retained. This is not independent human adjudication, and it cannot count mistakes the checker missed. Per-case inspection notes are shown in the reading desk."},
        "long_form":{"columns":["Model",">200-word cases","Model exact repairs","Delivered exact repairs","Judged complete","Raw semantic flags","Fallback","Median ms","p95 ms"],
                     "rows":long_rows,"note":"Synthetic connected dictation longer than 200 words, evaluated through the production window planner. The complete and semantic counts are raw blinded assessments of delivered outputs. No continuous long-form real-audio result is claimed."},
        "data_findings":[{"title":f"{trainstats.get('accepted',0):,} new accepted families","body":f"{trainstats.get('captured_families',0):,} produced exact engine-prompt supervision. {trainstats.get('long_over_200',0):,} exceed 200 words. Every accepted new label passed a separate Opus check."},
                         {"title":"Punctuation received substantially more supervision","body":f"The new corpus has {coverage.get('punctuation_or_case_only_repairs',0):,} punctuation-or-casing-only repairs and {coverage.get('vocabulary_pairs',0):,} examples with explicit vocabulary aliases. The original corpus had 234 such punctuation repairs out of 5,238 pairs, with a maximum of 171 words. New inputs reach {coverage.get('maximum_words',0)} words. The median remains 42 words in both corpora; this is broader coverage, not uniformly longer text."}],
        "curves":curves,"scaling_series":scaling.get('series',[]),"scaling_table":{"columns":scaling.get('columns',[]),"rows":scaling.get('rows',[])},"scaling_note":scaling.get('note'),
        "data_method":["Scenarios were allocated to train, validation and test before generation. Test and validation labels were fixed before new candidate evaluation. Existing frozen-test examples were exclusion material only and never training targets.",
                       "Sonnet 5.5 generated fictional pairs using several prompting approaches. Opus 5.5 independently checked every accepted label. Structural failures, semantic failures and duplicates were rejected rather than repaired to favor a candidate.",
                       "Supervision uses the existing production prompts and verified prefix-cached Gated DeltaNet training loop. Gold targets blocked by the engine remain visible; the dataset is not silently restricted to outputs the old engine already accepts.",
                       "Long examples are supervised in the engine's actual windows. A target is split only at aligned retained tokens. Cases with uncertain window alignment stay in evaluation and are excluded from training supervision.",
                       "Fresh public audio uses 150 previously unexposed DisfluencySpeech validation clips and 70 FLEURS sentence families for final test. The 70 development clips are disjoint. No new claim of unseen speakers or continuous long-form real speech is made."],
        "engine_findings":[{"title":"A comma could block a real correction","body":"The original parser sees an empty punctuation token before the replacement in '3, sorry, 4'. The isolated variant removes punctuation-only separators before applying the same parallel-value check."},
                           {"title":"Meaning safeguards remain in force","body":"Protected spans, ambiguous occurrences, sentence boundaries, deletion-size limits, final validation, and rollback are retained. The variant also correctly rejects emphasis such as 'I mean, it'."},
                           {"title":f"{correct_proposals_blocked} reference-correct proposals still blocked","body":"Even E can reject a model output that exactly matches the fixed target. Retained technical-token and correction checks can block explicit revisions to versions, decimal values, or times. These final-test findings describe the remaining delivery limit; they were not used to change the evaluated engine."},
                           {"title":"Normalization can mistake a pronoun for a number","body":"Numeric normalization happens before cleanup and can mistake pronouns for numbers. Every cleanup variant receives the same normalized text. The reading desk shows original recognizer text wherever normalization changed it, so upstream errors are distinguishable from cleanup edits."}],
        "rejections":{"columns":["Model / engine","Validator reason","Cases"],"rows":rejection_rows,
                      "note":"A case may have several failed checks. These counts describe rejected or salvaged proposals, not necessarily damage in the delivered text. Fallback includes every final path other than the full llm path."},
        "ablation":{"columns":["Variant","Exact repairs","Punctuation-only repaired","Preserve-as-is unchanged","Fallback","Raw semantic flags"],"rows":ablation},
        "engine_note":"D uses the production engine. E uses the same quantized D artifact with only the isolated parser repair. C + parser fix is an engine-only control. Model-only output means the first cleanup proposals after the preparatory correction pass, before output validation; changing accepted corrections can change that prompt even with identical weights. Semantic counts are raw automated flags on the same 481 synthetic cases; they are not human adjudication. Engine code in the installed application was not changed.",
        "checks":checks,"runtime_table":{"columns":["Model","Synthetic median ms","Synthetic p95 ms","Audio median ms","Audio p95 ms","Peak MLX GB","Peak process RSS GB","Artifact GB"],"rows":runtime},
        "runtime_note":"Latency is warm cleanup latency; it excludes the already-recorded ASR pass. MLX allocator peak and macOS process RSS peak measure different memory views and must not be added together; neither is whole-machine RAM. All final models use the production LocalFlow interpreter and greedy wrappers.",
        "runtime_caveat":"This shared desktop is not an isolated timing laboratory. Final model evaluations run serially without simultaneous experiment training. Background system activity and the installed LocalFlow process can still affect measurements.",
        "cost_headlines":[{"value":f"${total:.4f}","label":"Measured usage priced at batch rates"},{"value":f"${budget:.2f}","label":"Active total budget"},{"value":f"${outstanding:.2f}","label":"Maximum outstanding batch charge"},{"value":f"${budget-total-outstanding:.2f}","label":"Unspent budget after outstanding requests"}],
        "cost_table":{"columns":["Model / purpose","Requests","Input tokens","Output tokens","Cache reads","Cache writes","USD"],"rows":costrows},
        "cost_note":"Costs above use actual API-returned token usage and the verified model-specific batch rates. Billing reconciliation was unavailable: the workspace key cannot access Anthropic's Admin Cost API and the billing browser required sign-in. No credit purchase, auto-reload change, or payment action was performed. The prior experiment's spend is excluded.",
        "configuration":read_json(ART/'results/reproducibility.json',{}),"commands":read_json(ART/'results/reproduction-commands.json',[]),
        "deployment":read_json(ART/'results/deployment.json',{}),"limitations":decision.get('limitations',[]),
        "provenance":"Repository source and experiment revisions, exact model digests, data hashes, API batch receipts, output rows, and training curves are retained in experiments/cleanup-model-v2/artifacts. The HTML contains all displayed measurements and works without a server.",
    }
    destination=ROOT/CONFIG['paths']['report_dir']/"index.html"
    destination.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(report,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=(EXP/'v2/report_template.html').read_text()
    destination.write_text(template.replace('__REPORT_DATA__',payload))
    write_json(ART/'results/report-data.json',report)
    # Shareable counts and metrics contain no transcripts, prompts, paths or ids.
    write_json(ROOT/CONFIG['paths']['report_dir']/'measurements.json',{
        'created':utc_now(),'recommendation':decision['title'],'aggregates':aggs,'spend_usd':total,
        'budget_usd':budget,'new_accepted_families':trainstats.get('accepted',0),'checks':checks,
        'blinded_assessment':report['judge'],'flagged_case_inspection':report['inspection']})
    print(json.dumps({'report':str(destination),'bytes':destination.stat().st_size,'examples':len(examples),'spend_usd':total}))


if __name__=='__main__':build()
