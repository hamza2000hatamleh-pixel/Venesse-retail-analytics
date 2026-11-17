"""Combine the seven existing offline dashboards into one self-contained HTML file."""
from datetime import datetime
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
import re
import webbrowser

from venesse_html import export_sales_html
from venesse_customer_html import export_customer_html
from venesse_retention_html import export_retention_html
from venesse_product_html import export_product_html
from venesse_marketing_html import export_marketing_html
from venesse_feedback_html import export_feedback_html
from venesse_operating_html import export_operating_html


class _Cards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards=[]
        self.inside=False
        self.field=None
        self.title=''
        self.value=''

    def handle_starttag(self, tag, attrs):
        if tag=='article':
            self.inside=True
            self.title=self.value=''
        if self.inside and tag in ('p','strong'):
            self.field=tag

    def handle_data(self, data):
        if self.inside and self.field=='p': self.title+=data
        if self.inside and self.field=='strong': self.value+=data

    def handle_endtag(self, tag):
        if tag in ('p','strong'): self.field=None
        if tag=='article' and self.inside:
            if self.title and self.value: self.cards.append((self.title,self.value))
            self.inside=False


def _embed_dashboard(document):
    styles='\n'.join(re.findall(r'<style[^>]*>(.*?)</style>',document,re.S|re.I))
    match=re.search(r'<main[^>]*>(.*?)</main>',document,re.S|re.I)
    if not match or not styles:
        raise ValueError('Dashboard HTML is missing its main content or styles.')
    content=re.sub(r'<button\b[^>]*>.*?</button>','',match.group(1),flags=re.S|re.I)
    # Declarative shadow DOM isolates each module's styles, while keeping all
    # sections in normal document flow for a single browser print operation.
    overrides=':host{display:block;color:#172033;font:15px Arial,sans-serif}main{padding:24px 0;max-width:none}header{margin-top:0}@media print{main{padding:0}header{break-after:avoid}}'
    return '<template shadowrootmode="open"><style>'+styles+overrides+'</style><main>'+content+'</main></template>'


def export_full_html(year, fetch_sales_data, fetch_customer_sales_data,
                     fetch_product_sales_data, fetch_marketing_data,
                     fetch_feedback_data, fetch_operating_expenses,
                     fetch_operating_campaign_costs, output_folder='reports',
                     open_browser=True):
    """Reuse validated exporters. Unavailable sections are explicitly marked."""
    def cached(fetch):
        results={}
        def read(selected_year):
            if selected_year not in results:
                results[selected_year]=fetch(selected_year)
            frame=results[selected_year]
            return None if frame is None else frame.copy(deep=True)
        return read
    sales,customers,products,marketing,feedback,expenses,campaigns=[cached(f) for f in (fetch_sales_data,fetch_customer_sales_data,fetch_product_sales_data,fetch_marketing_data,fetch_feedback_data,fetch_operating_expenses,fetch_operating_campaign_costs)]
    jobs=[('sales','Sales',export_sales_html,(sales,)),
          ('customers','Customer analytics',export_customer_html,(customers,)),
          ('retention','Customer retention',export_retention_html,(customers,)),
          ('products','Product profitability',export_product_html,(products,)),
          ('marketing','Marketing',export_marketing_html,(marketing,)),
          ('feedback','Customer feedback',export_feedback_html,(feedback,)),
          ('operating','Operating profitability',export_operating_html,(sales,expenses,campaigns))]
    sections=[]; overview=[]; available=0; problems=[]
    try:
        with TemporaryDirectory(prefix='venesse_full_') as temporary:
            for section_id,title,exporter,args in jobs:
                result=exporter(year,*args,output_folder=temporary,open_browser=False)
                if 'saved successfully:\n' not in result:
                    problems.append(title)
                    sections.append(f'<section id="{section_id}" class="report-section"><h2>{escape(title)} · unavailable</h2><p class="warning">{escape(result)}</p></section>')
                    overview.append(f'<tr><th><a href="#{section_id}">{escape(title)}</a></th><td>Unavailable — see section for details.</td></tr>')
                    continue
                path=Path(result.splitlines()[-1])
                document=path.read_text(encoding='utf-8-sig')
                embedded=_embed_dashboard(document)
                sections.append(f'<section id="{section_id}" class="report-section"><div>{embedded}</div></section>')
                cards=_Cards(); cards.feed(document)
                selected=cards.cards[:3]
                if section_id=='operating':
                    selected=[card for card in cards.cards if 'Operating profit' in card[0] or 'Operating margin' in card[0] or card[0]=='Operating expenses']
                metrics=' · '.join(f'{escape(label)}: <strong>{escape(value)}</strong>' for label,value in selected)
                overview.append(f'<tr><th><a href="#{section_id}">{escape(title)}</a></th><td>{metrics}</td></tr>')
                available+=1
        if available==0:
            return 'Full HTML report was not saved. No dashboard sections could be generated.'
        status=f'{available} of 7 sections generated'
        if problems: status+=' · Unavailable: '+', '.join(problems)
        nav=''.join(f'<a href="#{key}">{escape(title)}</a>' for key,title,_,_ in jobs)
        css='''*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:85px}body{margin:0;background:#f1f5f9;color:#172033;font:15px Arial,sans-serif}.shell{max-width:1360px;padding:30px 28px;margin:auto}.cover,.overview{background:white;border:1px solid #e2e8f0;padding:28px;border-radius:14px;margin-bottom:20px}.eyebrow{font-weight:bold;letter-spacing:2px;color:#2563eb;font-size:12px}h1{font-size:36px;margin:14px 0}.muted{color:#64748b;line-height:1.7}.status{line-height:1.7;color:#334155}nav{position:sticky;top:0;z-index:10;background:#172033;padding:14px 20px;display:flex;flex-wrap:wrap;gap:14px;border-radius:10px}nav a{color:white;text-decoration:none;font-size:13px}button{background:#172033;border:0;color:white;padding:12px 18px;border-radius:8px;cursor:pointer}table{border-collapse:collapse;width:100%}th,td{padding:15px;text-align:left;border-bottom:1px solid #e2e8f0;line-height:1.7}th{width:210px}a{color:#2563eb}.report-section{margin-top:24px}.warning{white-space:pre-wrap;background:#fff7ed;border:1px solid #fed7aa;padding:20px;border-radius:10px;color:#9a3412}@media(max-width:700px){.shell{padding:16px}nav{position:static}th,td{display:block;width:auto}h1{font-size:28px}}@media print{html{scroll-padding-top:0}body{background:white}.shell{max-width:none;padding:0}nav,button{display:none}.cover{break-after:page}.report-section{break-before:page;margin:0}.overview{border:0;padding:0}a{color:inherit;text-decoration:none}@page{size:A4 landscape;margin:12mm}}'''
        html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Venesse full business report · {year}</title><style>{css}</style></head><body><main class="shell"><header class="cover"><div class="eyebrow">VENESSE / BUSINESS PERFORMANCE</div><h1>Full business report · {year}</h1><p class="muted">January–September · Previous-year comparisons where available<br>Generated {datetime.now():%Y-%m-%d %H:%M:%S}</p><p class="status">{escape(status)}</p><button onclick="window.print()">Print full report / Save as PDF</button><p class="muted">Open in a current Chrome or Edge browser for section rendering and printing.</p></header><nav aria-label="Report sections"><a href="#overview">Executive overview</a>{nav}</nav><section id="overview" class="overview"><h2>Executive overview</h2><table><tbody>{''.join(overview)}</tbody></table><p class="muted">These indicators come from the individual dashboards; populations and filters differ by section. Feedback is based on order date without a delivered-status filter. Retention requires a previous-year customer cohort. Marketing and operating campaign costs use different eligibility rules. Operating profitability remains provisional until campaign-cost overlap with expenses is resolved. Internal checks reconcile retrieved data and do not independently audit completeness. Sources are fetched once per source and year during this export; this is not a database transaction snapshot.</p></section>{''.join(sections)}<noscript><p>Section rendering uses declarative shadow DOM; use a current Chrome or Edge browser.</p></noscript></main></body></html>'''
        folder=Path(output_folder); folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'venesse_full_dashboard_{year}_{datetime.now():%Y%m%d_%H%M%S_%f}.html'
        path.write_text(html,encoding='utf-8')
    except (OSError,ValueError,TypeError,KeyError,OverflowError) as error:
        return f'Full HTML report was not saved.\n{error}'
    if open_browser:
        try: webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error: pass
    note='\nPartial report: '+', '.join(problems)+' unavailable.' if problems else ''
    return f'Full HTML report saved successfully:{note}\n{path.resolve()}'
