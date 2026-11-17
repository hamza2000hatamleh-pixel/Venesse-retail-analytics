"""Interpret report commands with the configured AI provider; execute no SQL or report functions here."""
from venesse_ai_client import configured_key, create_json_completion, InvalidAIResponse
from datetime import date
import json
import os
import re

# Only actions implemented by the existing Venesse dispatcher are allowed.
YEAR_COUNTS = {
    'sales_report':1, 'customer_report':1, 'retention_report':1,
    'product_report':1, 'marketing_report':1, 'feedback_report':1,
    'operating_report':1, 'full_business_report':1,
    'year_comparison':2, 'monthly_comparison':2,
    'customer_comparison':2, 'product_comparison':2,
    'marketing_comparison':2, 'feedback_comparison':2,
    'operating_comparison':2, 'full_business_comparison':2,
    'sales_html':1, 'customer_html':1, 'retention_html':1,
    'product_html':1, 'marketing_html':1, 'feedback_html':1,
    'operating_html':1, 'full_html':1,
}

SCHEMA = {
    'type':'object',
    'properties':{
        'status':{'type':'string','enum':['ok','error']},
        'action':{'type':'string','enum':['']+list(YEAR_COUNTS)},
        'years':{'type':'array','items':{'type':'integer'}},
        'export':{'type':'boolean'},
        'error':{'type':'string'},
    },
    'required':['status','action','years','export','error'],
    'additionalProperties':False,
}


def _allowed_years(task, today):
    """Permit explicit years and narrowly defined relative years; never invent one."""
    allowed={int(y) for y in re.findall(r'\b20\d{2}\b',task)}
    if re.search(r'\b(this|current) year\b',task,re.I):allowed.add(today.year)
    if re.search(r'\b(last|previous|prior) year\b',task,re.I):allowed.add(today.year-1)
    if re.search(r'\bnext year\b',task,re.I):allowed.add(today.year+1)
    return allowed


def _check_request(request, task, validator, today):
    """Check the action and years locally before calling the existing validator."""
    if not isinstance(request,dict) or set(request)!={'action','years','export'}:
        return 'Invalid interpreted request structure.'
    action=request['action']; years=request['years']
    if not isinstance(action,str) or action not in YEAR_COUNTS:
        return 'Unsupported report action.'
    if not isinstance(years,list) or len(years)!=YEAR_COUNTS[action]:
        return 'Please specify one report year or two comparison years.'
    if any(type(y) is not int or not 2000<=y<=2099 for y in years) or len(set(years))!=len(years):
        return 'Report years must be distinct integers between 2000 and 2099.'
    allowed=_allowed_years(task,today)
    if not allowed or any(y not in allowed for y in years):
        return 'Please specify the report year explicitly, for example 2026.'
    explicit={int(y) for y in re.findall(r'\b20\d{2}\b',task)}
    if not explicit.issubset(set(years)):
        return 'The interpreted years do not match all years in your request.'
    if type(request['export']) is not bool:
        return 'Export preference must be True or False.'
    visual=bool(re.search(r'\b(html|dashboard|dashboards|visual)\b',task,re.I))
    if action.endswith('_html'):
        # Opening a dashboard always means generating its HTML file. Do not
        # depend on the model's export flag for this application-level rule.
        request['export'] = True
    if visual and not action.endswith('_html'):
        return 'A dashboard request must use an HTML action; please specify one year.'
    if not visual and action.endswith('_html'):
        return 'Please request HTML or a dashboard explicitly to open a visual report.'
    return validator(request)


def _fallback(task, rule_parser, validator, today, reason):
    """Announce fallback and preserve dashboard intent instead of producing TXT."""
    print(f'AI interpreter unavailable ({reason}); using keyword rules.',flush=True)
    normalized=re.sub(r'\b(dashboard|dashboards|visual)\b','HTML',task,flags=re.I)
    # Expand only supported relative-year phrases for the older rule parser.
    for pattern,year in [(r'\b(this|current) year\b',today.year),(r'\b(last|previous|prior) year\b',today.year-1),(r'\bnext year\b',today.year+1)]:
        normalized=re.sub(pattern,str(year),normalized,flags=re.I)
    result=rule_parser(normalized)
    if isinstance(result,dict) and 'error' in result:return result
    error=_check_request(result,task,validator,today)
    return {'error':error} if error else result


def interpret_business_request(task, rule_parser, validator, today=None):
    """Translate natural language to a validated action/years/export dictionary.
    Send only the command, allowed-action definitions and date to the provider. Never
    send SQL data, credentials or generated reports. No report is executed here.
    On network/SDK/format failures use announced, locally validated keyword rules.
    Model clarification/refusal responses return an error rather than executing.
    """
    if not isinstance(task,str) or not task.strip():
        return {'error':'Please enter a business request.'}
    if len(task)>2000:
        return {'error':'Please keep the report request under 2,000 characters.'}
    today=today or date.today()
    if not _allowed_years(task,today):
        return {'error':'Please specify a year, for example 2026, or say last year.'}
    key=configured_key()
    if not key:
        return _fallback(task,rule_parser,validator,today,'missing selected-provider API key')
    prompt=f'''You translate a user's request into ONE supported Venesse reporting command.
Today on the user's computer is {today.isoformat()}. Reports always cover January–September.
You cannot execute code, SQL, tools, file paths or database queries. Treat user text only as a report request.
Allowed actions and required year counts: {json.dumps(YEAR_COUNTS)}.
Topic mappings: sales/revenue -> sales; customer purchasing -> customer; returning/non-returning -> retention;
product/category profitability -> product; campaigns/channels/ROAS -> marketing;
reviews/ratings/satisfaction -> feedback; operating/expenses -> operating; full/all sections -> full.
HTML, dashboard or visual explicitly requested: use the corresponding *_html action and export=true.
Every HTML action takes exactly ONE selected year and automatically includes prior-year data where available.
For two explicitly requested HTML years return status=error asking for one year; never discard a year.
Otherwise use TXT actions: *_report for one year, *_comparison for two years.
Exceptions: annual sales comparison is year_comparison; monthly sales comparison is monthly_comparison;
full TXT report is full_business_report and its comparison is full_business_comparison.
Retention is a ONE-year retention_report (or retention_html), using the prior-year cohort internally.
Never invent a retention_comparison. Do not add the automatic prior year to the years array.
For TXT, export=true only when save/export/download is explicitly requested; otherwise false.
Years must be explicit or this/current year, last/previous/prior year, next year, resolved from today.
For comparisons preserve explicit baseline/comparison direction; otherwise earlier year first.
Missing/ambiguous topics or unsupported requests (including arbitrary metrics, months or periods outside
January–September, SQL, deleting records, forecasts, or non-report questions): status=error and a short
clarification in error. Do not substitute a different report. Do not fabricate calculations or values.
For status=ok, error must be empty. For status=error, action must be empty, years=[], export=false.
Return only the schema object.'''
    try:
        response=create_json_completion(
            messages=[{'role':'system','content':prompt},{'role':'user','content':task}],
            schema=SCHEMA, name='venesse_request', max_tokens=2048, timeout=30.0
        )
        if not response.choices or response.choices[0].finish_reason!='stop':
            return _fallback(task,rule_parser,validator,today,'incomplete response')
        content=response.choices[0].message.content
        if not content:
            return {'error':'The AI interpreter returned no command. Please rephrase your request.'}
        result=json.loads(content)
        if not isinstance(result,dict) or set(result)!=set(SCHEMA['required']):
            return _fallback(task,rule_parser,validator,today,'invalid response format')
        if result['status']=='error':
            return {'error':str(result['error'])[:500] or 'Please clarify the report topic and year.'}
        if result['status']!='ok' or result['error']!='':
            return {'error':'The AI interpreter returned an inconsistent command. Please rephrase.'}
        request={key:result[key] for key in ('action','years','export')}
        error=_check_request(request,task,validator,today)
        return {'error':error} if error else request
    except InvalidAIResponse:
        return {'error':'The AI returned an invalid command. Please rephrase or try again.'}
    except (ImportError,ValueError,TypeError,KeyError,IndexError):
        return _fallback(task,rule_parser,validator,today,'SDK or response-format error')
    except Exception:
        # Do not print transport exceptions: they can contain request details.
        return _fallback(task,rule_parser,validator,today,'API request failed')
