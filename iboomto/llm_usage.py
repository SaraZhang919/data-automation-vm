"""Local token estimates, actual provider usage and explicit pricing assumptions."""
import os
from functools import lru_cache
from datetime import date
from .core import digest, stamp

PRICE_SOURCE='https://developers.openai.com/api/docs/models/gpt-5.6-sol'


@lru_cache(maxsize=1)
def encoder():
    import tiktoken
    return tiktoken.get_encoding('o200k_base')


def token_estimates(system,payload,question=''):
    from .llm_evidence import dumps
    try:
        count=lambda v:len(encoder().encode(v if isinstance(v,str) else dumps(v),disallowed_special=()))
        modules={k:count(v) for k,v in payload.items() if k!='details'}
        modules.update({'details/'+k:count(v) for k,v in payload.get('details',{}).items()})
        modules['system_prompt']=count(system)
        return {'estimated_input_tokens':count(system)+count({'question':question,'evidence':payload}),
                'module_token_estimates':modules,'token_estimator':'o200k_base message content; module counts exclude outer JSON framing; not billed counts'}
    except Exception as exc:
        return {'estimated_input_tokens':'','module_token_estimates':{},'token_estimator':'unavailable: '+type(exc).__name__}


def cost(usage,model,today=None):
    today=today or date.today()
    common={'price_source':PRICE_SOURCE,'price_checked_on':'2026-09-10'}
    if model!='gpt-5.6-sol' or today>date(2026,11,21):
        return {**common,'estimated_cost_usd':'','cost_status':'pricing_review_required'}
    if 'prompt_tokens' not in usage or 'completion_tokens' not in usage:
        return {**common,'estimated_cost_usd':'','cost_status':'usage_unavailable'}
    inp=usage['prompt_tokens'];out=usage['completion_tokens'];details=usage.get('prompt_tokens_details') or {}
    cached=min(inp,details.get('cached_tokens',0));write=min(inp-cached,details.get('cache_write_tokens',0))
    normal=inp-cached-write;im=2 if inp>272000 else 1;om=1.5 if inp>272000 else 1
    value=((normal*4+cached*.4+write*5)*im+out*20*om)/1e6
    return {**common,'estimated_cost_usd':round(value,8),'cost_status':'estimated_from_provider_usage',
            'pricing_basis':'USD/1M: input4, cached0.4, cache_write5, output20; reasoning included in output; long-context multipliers if applicable'}


def save_run(report,analysis_id,kind,attempts,cache_hits,status):
    unknown=sum(r.get('estimated_cost_usd','')=='' for r in attempts)
    report.upsert('AI Run Usage',[{'id':analysis_id,'at':stamp(),'run_id':os.environ.get('GITHUB_RUN_ID','local'),
        'kind':kind,'status':status,'api_calls':len(attempts),'cache_hits':cache_hits,
        'successful_calls':sum(r.get('status')=='success' for r in attempts),
        'input_tokens_known':sum(r.get('input_tokens') or 0 for r in attempts),
        'output_tokens_known':sum(r.get('output_tokens') or 0 for r in attempts),
        'estimated_cost_usd':round(sum(r['estimated_cost_usd'] for r in attempts),8) if not unknown else '',
        'unknown_cost_calls':unknown,'cost_status':'unknown_calls_present' if unknown else 'estimated' if attempts else 'no_api_call'}])


def cached_run(report,kind):
    from uuid import uuid4
    save_run(report,uuid4().hex,kind,[],1,'cached')
