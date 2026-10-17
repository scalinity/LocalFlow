"""Small matched comparison of Claude generators and anonymous label checks."""
from __future__ import annotations

import argparse
import collections
import copy
import json
import random
import re
import statistics
import time
from .common import *
from .data import CATEGORIES, GEN_SYSTEM, VERIFY_SYSTEM, plan, wave
from lfx import synth, batches

STUDY=ART/'generator-study'
MODELS={'Haiku':'claude-haiku-5-5','Sonnet':'claude-sonnet-5-5','Opus':'claude-opus-5-5'}


def prepare():
    path=STUDY/'specs.json'
    if path.exists():return read_json(path)
    pools=collections.defaultdict(list)
    for spec in plan('train',1500,200000):pools[spec['category']].append(spec)
    specs=[]
    for category,_,_ in CATEGORIES:
        selected=pools[category][:8]
        assert len(selected)==8
        for i,s in enumerate(selected):
            s['length']=('220-300 words' if i%2==0 else '350-500 words') if category=='long_instructions' else ['8-28 words','29-70 words','71-130 words','131-185 words'][i%4]
            specs.append(s)
    random.Random(731).shuffle(specs)
    write_json(path,specs)
    write_json(STUDY/'plan.json',{'created':utc_now(),'briefs_per_model':96,'categories':12,
               'same_serialized_specs':True,'generation_effort':'medium','verification_effort':'low',
               'generation_prompt_sha256':sha256_text(GEN_SYSTEM),'verification_prompt_sha256':sha256_text(VERIFY_SYSTEM),
               'purpose':'Generator and checker screening; no downstream training equivalence claim.',
               'labels_used_for_training':False,'pricing_source':'https://platform.claude.com/docs/en/about-claude/pricing'})
    return specs


def generate(label):
    specs=prepare();requests={};chunks=[];pending=[]
    for s in specs:
        if s['category']=='long_instructions':
            if pending:chunks.append(pending);pending=[]
            chunks.append([s])
        else:
            pending.append(s)
            if len(pending)==8:chunks.append(pending);pending=[]
    if pending:chunks.append(pending)
    name='generator-study-gen-'+label.lower()
    for i,chunk in enumerate(chunks):
        requests[f'{name}-{i:03d}']={'model':MODELS[label],'max_tokens':10000 if len(chunk)>1 else 6500,
            'thinking':{'type':'adaptive'},
            'system':[{'type':'text','text':GEN_SYSTEM,'cache_control':{'type':'ephemeral'}}],
            'messages':[{'role':'user','content':'Create these families:\n'+json.dumps(chunk)}],
            'output_config':{'effort':'medium','format':{'type':'json_schema','schema':synth.GEN_SCHEMA}}}
    w=wave(name,requests,synth.parse_generation,MODELS[label],'generator_comparison_generation')
    w.run(chunk=100)
    lookup={s['family_id']:s for s in specs};seen=set();rows=[];failures=[]
    for rid,result in w.outcomes.items():
        if result['status']!='succeeded':
            failures.append({'request':rid,'status':result['status']});continue
        for family in result['value']:
            fid=family['family_id']
            if fid not in lookup or fid in seen:
                failures.append({'family_id':fid,'status':'unknown_or_duplicate_id'});continue
            seen.add(fid);spec=lookup[fid]
            try:p=synth.prepare_family(family,spec)
            except Exception as exc:
                failures.append({'family_id':fid,'status':'prepare_error','detail':str(exc)[:150]});continue
            if p['is_noop']!=spec['is_noop']:p['reject'].append('requested_noop_mismatch')
            if not p['is_noop'] and p['model_input']==p['target']:p['reject'].append('empty_repair')
            p['reject']=sorted(set(p['reject']))
            p.update(generator=label,study_id=sha256_text(fid+'|'+label)[:16],raw_generated=family)
            rows.append(p)
    write_jsonl(STUDY/f'{label.lower()}-pairs.jsonl',rows)
    write_json(STUDY/f'{label.lower()}-generation.json',{'completed':utc_now(),'requested':len(specs),'returned':len(rows),
               'structurally_valid':sum(not p['reject'] for p in rows),'failures':failures,
               'missing_ids':sorted(set(lookup)-seen)})
    print(json.dumps({'model':label,'returned':len(rows),'valid':sum(not p['reject'] for p in rows)}),flush=True)


def blind():
    destination=STUDY/'blind-pairs.jsonl'
    if destination.exists():return read_jsonl(destination)
    assert all((STUDY/f'{k.lower()}-pairs.jsonl').exists() for k in MODELS)
    rows=[];mapping={}
    for label in MODELS:
        for p in read_jsonl(STUDY/f'{label.lower()}-pairs.jsonl'):
            q=copy.deepcopy(p);oid='pair-'+p['study_id'];q['pair_id']=oid
            mapping[oid]={'generator':label,'family_id':p['family_id'],'study_id':p['study_id']}
            rows.append(q)
    random.Random(913).shuffle(rows)
    # verify_user emits only the content, category, correction/vocabulary labels,
    # and opaque pair id. Generator and author notes never enter the request.
    write_jsonl(destination,rows);write_json(STUDY/'blind-map.json',mapping)
    return rows


def recover(label):
    """Retry missing briefs once, individually; preserve first-attempt evidence."""
    specs=prepare();path=STUDY/f'{label.lower()}-pairs.jsonl';rows=read_jsonl(path)
    completed={p['family_id'] for p in rows};missing=[s for s in specs if s['family_id'] not in completed]
    original=STUDY/f'{label.lower()}-initial-generation.json'
    if not original.exists():write_json(original,read_json(STUDY/f'{label.lower()}-generation.json'))
    if not missing:return
    if (STUDY/'blind-pairs.jsonl').exists():raise RuntimeError('Checks already fixed; do not replace their labels')
    name='generator-study-gen-'+label.lower()+'-retry';requests={}
    for s in missing:
        requests[s['family_id']]={'model':MODELS[label],'max_tokens':10000,'thinking':{'type':'adaptive'},
            'system':[{'type':'text','text':GEN_SYSTEM,'cache_control':{'type':'ephemeral'}}],
            'messages':[{'role':'user','content':'Create these families:\n'+json.dumps([s])}],
            'output_config':{'effort':'medium','format':{'type':'json_schema','schema':synth.GEN_SCHEMA}}}
    w=wave(name,requests,synth.parse_generation,MODELS[label],'generator_comparison_generation');w.run(chunk=100)
    lookup={s['family_id']:s for s in missing}
    for rid,result in w.outcomes.items():
        if result['status']!='succeeded':continue
        for family in result['value']:
            fid=family['family_id']
            if fid!=rid or fid in completed:continue
            p=synth.prepare_family(family,lookup[fid])
            if p['is_noop']!=lookup[fid]['is_noop']:p['reject'].append('requested_noop_mismatch')
            if not p['is_noop'] and p['model_input']==p['target']:p['reject'].append('empty_repair')
            p['reject']=sorted(set(p['reject']))
            p.update(generator=label,study_id=sha256_text(fid+'|'+label)[:16],raw_generated=family,
                     recovered_from_individual_request=True)
            rows.append(p);completed.add(fid)
    write_jsonl(path,rows)
    write_json(STUDY/f'{label.lower()}-recovery.json',{'completed':utc_now(),'requested':len(missing),
               'recovered':sum(p.get('recovered_from_individual_request',False) for p in rows),
               'total_returned':len(rows),'remaining_missing':sorted(set(lookup)-completed)})
    print(json.dumps({'model':label,'retry_requested':len(missing),'total_returned':len(rows)}),flush=True)


def check_rows(label, rows, name, group_size=8, max_tokens=3000):
    requests={};ids={}
    for i in range(0,len(rows),group_size):
        chunk=rows[i:i+group_size];rid=f'{name}-{i//group_size:03d}';ids[rid]=[p['pair_id'] for p in chunk]
        requests[rid]={'model':MODELS[label],'max_tokens':max_tokens,'thinking':{'type':'adaptive'},
            'system':[{'type':'text','text':VERIFY_SYSTEM,'cache_control':{'type':'ephemeral'}}],
            'messages':[{'role':'user','content':synth.verify_user(chunk)}],
            'output_config':{'effort':'low','format':{'type':'json_schema','schema':synth.VERIFY_SCHEMA}}}
    w=wave(name,requests,synth.parse_verify,MODELS[label],'verification')
    w.run(chunk=100)
    verdicts={}
    for rid,pids in ids.items():
        result=w.outcomes.get(rid,{})
        values=result.get('value',[]) if result.get('status')=='succeeded' else []
        counts=collections.Counter(v.get('pair_id') for v in values)
        for pid in pids:
            match=next((v for v in values if v.get('pair_id')==pid),None)
            verdicts[pid]=match if match and counts[pid]==1 else {'verdict':'UNVERIFIED','reasons':['missing_or_duplicate_verdict']}
    return verdicts


def retry_unverified(label, rows, verdicts, name):
    missing=[p for p in rows if verdicts[p['pair_id']]['verdict']=='UNVERIFIED']
    if missing:
        write_json(STUDY/(name+'-initial.json'),verdicts)
        verdicts.update(check_rows(label,missing,name+'-retry',group_size=4,max_tokens=6000))
    return verdicts


def early_check(label):
    """Check finished generators while the remaining generation is pending."""
    rows=[]
    for generator in ('Haiku','Opus'):
        for p in read_jsonl(STUDY/f'{generator.lower()}-pairs.jsonl'):
            q=copy.deepcopy(p);q['pair_id']='pair-'+p['study_id'];rows.append(q)
    random.Random(913).shuffle(rows)
    write_json(STUDY/f'{label.lower()}-early-started.json',{'created':utc_now(),'pair_ids':[p['pair_id'] for p in rows]})
    verdicts=check_rows(label,rows,'generator-study-check-early-'+label.lower())
    verdicts=retry_unverified(label,rows,verdicts,'generator-study-check-early-'+label.lower())
    write_json(STUDY/f'{label.lower()}-early-checks.json',{'completed':utc_now(),'judge':label,'verdicts':verdicts,'retry_complete':True})
    print(json.dumps({'judge':label,'early_verdicts':len(verdicts)}),flush=True)


def check(label):
    rows=blind();verdicts={}
    if (STUDY/f'{label.lower()}-early-started.json').exists():
        while not (STUDY/f'{label.lower()}-early-checks.json').exists():time.sleep(10)
        early=read_json(STUDY/f'{label.lower()}-early-checks.json')
        while (STUDY/f'generator-study-check-early-{label.lower()}-initial.json').exists() and not (early.get('retry_complete') or early.get('retried_at')):
            time.sleep(10);early=read_json(STUDY/f'{label.lower()}-early-checks.json')
        verdicts.update(early['verdicts'])
    remaining=[p for p in rows if p['pair_id'] not in verdicts]
    final=check_rows(label,remaining,'generator-study-check-'+label.lower())
    final=retry_unverified(label,remaining,final,'generator-study-check-'+label.lower())
    verdicts.update(final)
    write_json(STUDY/f'{label.lower()}-checks.json',{'completed':utc_now(),'judge':label,'verdicts':verdicts})
    print(json.dumps({'judge':label,'verdicts':dict(collections.Counter(v['verdict'] for v in verdicts.values()))}),flush=True)


def cost(name):
    ledger=batches.ledger();manifest=read_json(ART/'claude'/name/'manifest.json')
    entries=[ledger['entries'][a['ledger_key']] for a in manifest['attempts']]
    usage=collections.Counter()
    for e in entries:usage.update(e.get('usage',{}))
    return {'usd':sum(e.get('actual_usd',0) for e in entries),'usage':dict(usage),
            'requests':sum(len(a['custom_ids']) for a in manifest['attempts']),
            'batches':[a['batch_id'] for a in manifest['attempts']]}


def summarize():
    specs=prepare();judges={k:read_json(STUDY/f'{k.lower()}-checks.json')['verdicts'] for k in MODELS}
    # The second checking wave may have started before a first-wave retry
    # finished. Reconcile that completed retry before computing any totals.
    for label in MODELS:
        early_path=STUDY/f'{label.lower()}-early-checks.json'
        if not early_path.exists():continue
        early=read_json(early_path)
        while (STUDY/f'generator-study-check-early-{label.lower()}-initial.json').exists() and not (early.get('retry_complete') or early.get('retried_at')):
            time.sleep(10);early=read_json(early_path)
        if any(judges[label].get(pid)!=v for pid,v in early['verdicts'].items()):
            path=STUDY/f'{label.lower()}-checks.json';original=read_json(path)
            write_json(STUDY/f'{label.lower()}-checks-before-reconciliation.json',original)
            judges[label].update(early['verdicts'])
            original.update(verdicts=judges[label],early_recovery_reconciled_at=utc_now())
            write_json(path,original)
    specmap={s['family_id']:s for s in specs}
    models={};examples=[]
    for label in MODELS:
        rows=read_jsonl(STUDY/f'{label.lower()}-pairs.jsonl');category={}
        for p in rows:
            verdicts={k:judges[k]['pair-'+p['study_id']] for k in MODELS}
            p['judges']=verdicts
            p['text_dual_pass']=all(verdicts[k]['verdict']=='PASS' for k in ('Sonnet','Opus'))
            p['dual_pass']=not p['reject'] and p['text_dual_pass']
            p['cross_model_pass']=not p['reject'] and all(verdicts[k]['verdict']=='PASS' for k in MODELS if k!=label)
            lo,hi=map(int,re.match(r'(\d+)-(\d+)',specmap[p['family_id']]['length']).groups())
            p['source_words']=len(p['model_input'].split());p['target_words']=len(p['target'].split())
            p['source_in_band']=lo<=p['source_words']<=hi
            p['target_in_band']=lo<=p['target_words']<=hi
            examples.append(p)
        for cat,_,_ in CATEGORIES:
            subset=[p for p in rows if p['category']==cat]
            category[cat]={'returned':len(subset),'valid':sum(not p['reject'] for p in subset),
                           'dual_pass':sum(p['dual_pass'] for p in subset)}
        tokenlists=[synth.words(p['model_input']) for p in rows]
        trigrams=[tuple(w[i:i+3]) for w in tokenlists for i in range(max(0,len(w)-2))]
        sets=[synth.shingles(p['model_input']) for p in rows]
        near=sum(any(synth.jaccard(sets[i],sets[j])>=.6 for j in range(i)) for i in range(len(sets)))
        gen=cost('generator-study-gen-'+label.lower());checking=cost('generator-study-check-'+label.lower())
        if (STUDY/f'{label.lower()}-early-checks.json').exists():
            extra=cost('generator-study-check-early-'+label.lower())
            checking['usd']+=extra['usd'];checking['requests']+=extra['requests'];checking['batches']+=extra['batches']
            for key,value in extra['usage'].items():checking['usage'][key]=checking['usage'].get(key,0)+value
        for suffix in ('-early-'+label.lower()+'-retry','-'+label.lower()+'-retry'):
            name='generator-study-check'+suffix
            if (ART/'claude'/name/'manifest.json').exists():
                extra=cost(name)
                checking['usd']+=extra['usd'];checking['requests']+=extra['requests'];checking['batches']+=extra['batches']
                for key,value in extra['usage'].items():checking['usage'][key]=checking['usage'].get(key,0)+value
        recovery=read_json(STUDY/f'{label.lower()}-recovery.json',{})
        if recovery:
            extra=cost('generator-study-gen-'+label.lower()+'-retry')
            gen['usd']+=extra['usd'];gen['requests']+=extra['requests'];gen['batches']+=extra['batches']
            for key,value in extra['usage'].items():gen['usage'][key]=gen['usage'].get(key,0)+value
        accepted=sum(p['dual_pass'] for p in rows)
        models[label]={'requested':len(specs),'returned':len(rows),'structurally_valid':sum(not p['reject'] for p in rows),
              'initial_returned':read_json(STUDY/f'{label.lower()}-initial-generation.json')['returned'],
              'individual_retries':recovery.get('requested',0),
              'dual_pass':accepted,'cross_model_pass':sum(p['cross_model_pass'] for p in rows),
              'text_dual_pass':sum(p['text_dual_pass'] for p in rows),
              'judge_text_pass':{k:sum(p['judges'][k]['verdict']=='PASS' for p in rows) for k in MODELS},
              'judge_pass':{k:sum(not p['reject'] and p['judges'][k]['verdict']=='PASS' for p in rows) for k in MODELS},
              'rejection_reasons':dict(collections.Counter(r for p in rows for r in p['reject'])),
              'categories':category,'median_words':statistics.median(p['source_words'] for p in rows),
              'requested_source_length_met':sum(p['source_in_band'] for p in rows),
              'requested_target_length_met':sum(p['target_in_band'] for p in rows),
              'over200':sum(p['source_words']>200 for p in rows),'near_duplicates':near,
              'distinct_trigram_ratio':len(set(trigrams))/max(len(trigrams),1),
              'generation_cost':gen,'checker_cost':checking,
              'generation_usd_per_1000_accepted':gen['usd']/accepted*1000 if accepted else None}
    disagreements=[]
    for p in examples:
        if len({v['verdict'] for v in p['judges'].values()})>1:disagreements.append(p['study_id'])
    checker_agreement={}
    for checker in MODELS:
        others=[k for k in MODELS if k!=checker]
        comparable=[p for p in examples if p['judges'][others[0]]['verdict']==p['judges'][others[1]]['verdict']
                    and p['judges'][others[0]]['verdict'] in ('PASS','FAIL')]
        checker_agreement[checker]={'comparable':len(comparable),
           'returned_verdicts':sum(p['judges'][checker]['verdict'] in ('PASS','FAIL') for p in examples),
           'unverified':sum(p['judges'][checker]['verdict']=='UNVERIFIED' for p in examples),
           'agreement':sum(p['judges'][checker]['verdict']==p['judges'][others[0]]['verdict'] for p in comparable),
           'pass_when_others_fail':sum(p['judges'][checker]['verdict']=='PASS' and p['judges'][others[0]]['verdict']=='FAIL' for p in comparable),
           'fail_when_others_pass':sum(p['judges'][checker]['verdict']=='FAIL' and p['judges'][others[0]]['verdict']=='PASS' for p in comparable)}
    total=sum(m['generation_cost']['usd']+m['checker_cost']['usd'] for m in models.values())
    result={'created':utc_now(),'plan':read_json(STUDY/'plan.json'),'models':models,'examples':examples,
            'execution':read_json(STUDY/'execution.json',{}),
            'specs':specs,'disagreement_ids':disagreements,'total_usd':total,
            'checker_agreement':checker_agreement,
            'overall_spend_usd':batches.ledger_totals()['actual_usd'],'active_budget_usd':CONFIG['claude']['spend_cap_usd']}
    write_json(STUDY/'results.json',result)
    print(json.dumps({'models':{k:{f:m[f] for f in ('requested','returned','structurally_valid','dual_pass','cross_model_pass','median_words','near_duplicates','generation_usd_per_1000_accepted')} for k,m in models.items()},'total_usd':total},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','generate','recover','blind','check','early-check','summarize']);p.add_argument('model',nargs='?',choices=list(MODELS));a=p.parse_args()
    if a.stage=='generate':generate(a.model)
    elif a.stage=='recover':recover(a.model)
    elif a.stage=='check':check(a.model)
    elif a.stage=='early-check':early_check(a.model)
    elif a.stage=='summarize':summarize()
    elif a.stage=='blind':blind()
    else:prepare()
