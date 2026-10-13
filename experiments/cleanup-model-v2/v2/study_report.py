"""Publish the measured generator comparison as a private offline HTML file."""
from __future__ import annotations
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from .common import *
from .generator_study import STUDY


def build():
    results=read_json(STUDY/'results.json');decision=read_json(STUDY/'decision.json')
    if not results or not decision:raise RuntimeError('Measured results and an assessed conclusion are required')
    payload={**results,'decision':decision,'created_label':datetime.now(ZoneInfo('America/New_York')).strftime('%B %d, %Y · %H:%M ET')}
    encoded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    destination=ROOT/'reports/localflow-generator-comparison/index.html'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text((EXP/'v2/generator_report_template.html').read_text().replace('__STUDY_DATA__',encoded))
    safe={}
    for k,m in results['models'].items():
        safe[k]={f:m[f] for f in ('requested','returned','initial_returned','individual_retries','structurally_valid','dual_pass','cross_model_pass',
                 'judge_pass','judge_text_pass','text_dual_pass','rejection_reasons','categories','median_words','over200','near_duplicates',
                 'distinct_trigram_ratio','requested_source_length_met','requested_target_length_met',
                 'generation_usd_per_1000_accepted')}
        safe[k]['generation_usd']=m['generation_cost']['usd'];safe[k]['checking_usd']=m['checker_cost']['usd']
    write_json(destination.parent/'measurements.json',{'created':utc_now(),'models':safe,
               'checker_agreement':results['checker_agreement'],'comparison_usd':results['total_usd'],
               'conclusion':decision['title']})
    print(json.dumps({'path':str(destination),'bytes':destination.stat().st_size}))


if __name__=='__main__':build()
