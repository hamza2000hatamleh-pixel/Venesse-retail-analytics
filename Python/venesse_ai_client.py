"""Shared low-cost API connection for Venesse request parsing and commentary.
Set VENESSE_AI_PROVIDER to nanogpt, siliconflow (default), or groq.
Keys remain in environment variables; no provider fallback spends credits silently.
"""
from contextvars import ContextVar
from functools import wraps
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path


class InvalidAIResponse(ValueError):
    """The provider returned JSON outside the application schema."""


def _validate_json(value, schema):
    """Validate the small JSON Schema subset used by the two Venesse modules."""
    kind=schema.get('type')
    if kind=='object':
        if not isinstance(value,dict):raise ValueError('Expected JSON object')
        if not set(schema.get('required',[])).issubset(value):raise ValueError('Missing JSON field')
        properties=schema.get('properties',{})
        if schema.get('additionalProperties') is False and set(value)-set(properties):raise ValueError('Unexpected JSON field')
        for key,item in value.items():
            if key in properties:_validate_json(item,properties[key])
    elif kind=='array':
        if not isinstance(value,list):raise ValueError('Expected JSON array')
        for item in value:_validate_json(item,schema['items'])
    elif kind=='integer':
        if type(value) is not int:raise ValueError('Expected JSON integer')
    elif kind=='boolean':
        if type(value) is not bool:raise ValueError('Expected JSON Boolean')
    elif kind=='string':
        if not isinstance(value,str):raise ValueError('Expected JSON string')
    elif kind=='number':
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Expected finite JSON number')
    if 'enum' in schema and value not in schema['enum']:raise ValueError('JSON value outside allowed choices')


def configured_provider():
    """Choose one explicitly configured provider without automatic paid fallback."""
    provider=os.getenv('VENESSE_AI_PROVIDER','siliconflow').strip().lower()
    if provider not in ('siliconflow','groq','nanogpt'):raise ValueError('Unsupported AI provider')
    return provider


def configured_key():
    """Read the selected provider key without displaying or logging it."""
    variable={'siliconflow':'SILICONFLOW_API_KEY','groq':'GROQ_API_KEY','nanogpt':'NANOGPT_API_KEY'}[configured_provider()]
    return os.getenv(variable)



def _provider_error_details(error):
    """Expose only provider error code/message, redacting the configured key."""
    body=getattr(error, 'body', None)
    if not isinstance(body, dict):return
    detail=body.get('error', body)
    if isinstance(detail, str):detail={'message':detail}
    if not isinstance(detail, dict):return
    code=detail.get('code')
    message=detail.get('message')
    parts=[]
    if isinstance(code, (str,int)):parts.append(str(code))
    if isinstance(message,str):parts.append(message)
    text=' | '.join(parts)
    if not text:return
    key=configured_key()
    if key:text=text.replace(key,'[REDACTED]')
    text=re.sub(r'(?i)bearer\s+\S+', 'Bearer [REDACTED]', text)
    text=re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', text)
    text=re.sub(r'\s+', ' ', text)[:400]
    print(f'AI provider detail: {text}',flush=True)




_REQUEST_USAGE=ContextVar('venesse_request_usage',default=None)


def track_request_usage(function):
    """Print per-request reported usage, including failed/unknown attempts."""
    @wraps(function)
    def wrapped(*args,**kwargs):
        totals={'input':0,'output':0,'attempts':0,'unknown':0,'cache_hits':0}
        token=_REQUEST_USAGE.set(totals)
        try:return function(*args,**kwargs)
        finally:
            _REQUEST_USAGE.reset(token)
            print(f"Request AI usage: {totals['input']} input / {totals['output']} output tokens reported; {totals['attempts']} API attempts; {totals['cache_hits']} commentary cache hits; {totals['unknown']} attempts with unavailable usage.",flush=True)
    return wrapped


def record_commentary_cache_hit():
    totals=_REQUEST_USAGE.get()
    if totals is not None:totals['cache_hits']+=1

def _record_usage(response, model, name, elapsed, status):
    """Log allowlisted metadata only. Logging failure never breaks reporting."""
    try:
        usage=getattr(response,'usage',None)
        counts={}
        for field in ('prompt_tokens','completion_tokens','total_tokens'):
            value=getattr(usage,field,None)
            counts[field]=value if type(value) is int and value>=0 else None
        totals=_REQUEST_USAGE.get()
        if totals is not None:
            totals['attempts']+=1
            if counts['prompt_tokens'] is None or counts['completion_tokens'] is None:totals['unknown']+=1
            totals['input']+=counts['prompt_tokens'] or 0
            totals['output']+=counts['completion_tokens'] or 0
        record={'timestamp_utc':datetime.now(timezone.utc).isoformat(),
                'provider':configured_provider(),'model':model,'operation':name,
                'status':status,'elapsed_seconds':round(elapsed,3),**counts}
        # Optional user-supplied rates apply only to an exact model match.
        # This is an estimate, never a provider bill or enforced spending limit.
        record['estimated_cost_usd']=None
        if os.getenv('VENESSE_AI_PRICE_MODEL')==model and counts['prompt_tokens'] is not None and counts['completion_tokens'] is not None:
            input_rate=float(os.environ['VENESSE_AI_INPUT_USD_PER_MILLION'])
            output_rate=float(os.environ['VENESSE_AI_OUTPUT_USD_PER_MILLION'])
            if all(math.isfinite(v) and v>=0 for v in (input_rate,output_rate)):
                record['estimated_cost_usd']=round((counts['prompt_tokens']*input_rate+counts['completion_tokens']*output_rate)/1000000,10)
        target=Path(os.getenv('VENESSE_AI_USAGE_LOG','reports/ai_usage.jsonl'))
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('a',encoding='utf-8') as handle:handle.write(json.dumps(record)+'\n')
        if counts['total_tokens'] is not None:
            print(f"AI usage: {counts['prompt_tokens']} input / {counts['completion_tokens']} output tokens.",flush=True)
    except (OSError,ValueError,TypeError,KeyError):
        print('AI usage metadata could not be logged; reporting continues.',flush=True)

def _chat_completion(client, **kwargs):
    """Retry a NanoGPT HTTP 503 once; never change provider/model automatically."""
    for attempt in range(2):
        started=time.perf_counter()
        name=kwargs.get('response_format',{}).get('json_schema',{}).get('name','json_completion')
        try:
            response=client.chat.completions.create(**kwargs)
            _record_usage(response,kwargs.get('model'),name,time.perf_counter()-started,'response_received')
            return response
        except Exception as error:
            _record_usage(None,kwargs.get('model'),name,time.perf_counter()-started,'request_failed')
            if configured_provider()=='nanogpt' and getattr(error,'status_code',None)==503 and attempt==0:
                print('NanoGPT temporarily unavailable (503); retrying once after a short delay.',flush=True)
                time.sleep(1.0)
                continue
            _provider_error_details(error)
            raise

def create_json_completion(messages, schema, name, max_tokens=2048, timeout=30.0):
    """Call the selected provider once and locally validate returned JSON.
    SiliconFlow uses JSON-object output plus explicit schema instructions. Unlike
    Groq strict mode, constrained schema decoding is not assumed on SiliconFlow.
    Every provider must pass the same local action/evidence constraints.
    NanoGPT uses its documented OpenAI-compatible JSON Schema response format.
    """
    provider=configured_provider();key=configured_key()
    if not key:raise ValueError('Missing API key for selected provider')
    if provider=='nanogpt':
        from openai import OpenAI
        model=os.getenv('VENESSE_AI_MODEL','openai/gpt-oss-20b')
        options={}
        # Do not send GPT-OSS reasoning controls to non-reasoning Qwen models.
        if 'gpt-oss' in model.lower():options['reasoning_effort']='low'
        with OpenAI(api_key=key,base_url='https://api.nano-gpt.com/api/v1',timeout=timeout,max_retries=0) as client:
            response=_chat_completion(client,
                model=model,
                messages=messages,
                response_format={'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}},
                max_tokens=max_tokens,
                **options,
            )
    elif provider=='siliconflow':
        from openai import OpenAI
        instruction=('Return ONLY a JSON object conforming to this JSON Schema. '
                     'All fields are required where specified. Never include Markdown fences. '
                     'Evidence IDs must be selected from their enum. Schema: '+json.dumps(schema,separators=(',',':')))
        prepared=[dict(message) for message in messages]
        if prepared and prepared[0].get('role')=='system':
            prepared[0]['content']+='\n\n'+instruction
        else:prepared.insert(0,{'role':'system','content':instruction})
        with OpenAI(api_key=key,base_url='https://api.siliconflow.com/v1',timeout=timeout,max_retries=0) as client:
            response=_chat_completion(client,
                model=os.getenv('VENESSE_AI_MODEL','openai/gpt-oss-20b'),
                messages=prepared,
                response_format={'type':'json_object'},
                max_tokens=max_tokens,
            )
    else:
        from groq import Groq
        with Groq(api_key=key,timeout=timeout,max_retries=0) as client:
            response=_chat_completion(client,
                model=os.getenv('VENESSE_AI_MODEL','openai/gpt-oss-20b'),
                messages=messages,
                response_format={'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}},
                max_completion_tokens=max_tokens,reasoning_effort='low',
            )
    if response.choices and response.choices[0].finish_reason=='stop':
        content=response.choices[0].message.content
        if not content:raise ValueError('Empty AI response')
        try:
            _validate_json(json.loads(content),schema)
        except (ValueError, TypeError) as error:
            raise InvalidAIResponse('AI response failed local schema validation') from error
    return response
