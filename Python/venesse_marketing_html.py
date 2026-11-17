"""Offline marketing dashboard; one validated row per eligible campaign."""
from datetime import datetime
from html import escape
from pathlib import Path
import math
import webbrowser
import pandas as pd


def _money(value):
    return 'N/A' if value is None else (f'-${abs(value):,.2f}' if value < 0 else f'${value:,.2f}')


def _ratio(value, suffix):
    return 'N/A' if value is None else f'{value:,.2f}{suffix}'

def _bars(labels, series):
    """Grouped bars with amounts in a separate right-hand column."""
    all_values=[float(v) for _,_,values in series for v in values]
    low, high = min([0]+all_values), max([0]+all_values)
    if high==low: high=low+1
    span=high-low
    low-=span*.05 if low<0 else 0
    high+=span*.12
    height=70+len(labels)*(len(series)*30+24)
    x0=lambda value: 240+(value-low)/(high-low)*380
    zero=x0(0)
    parts=[f'<svg viewBox="0 0 780 {height}" role="img" aria-label="Marketing financial performance">']
    parts.append(f'<line x1="{zero}" x2="{zero}" y1="10" y2="{height-35}" stroke="#cbd5e1"/>')
    for i,label in enumerate(labels):
        y=24+i*(len(series)*30+24)
        parts.append(f'<text x="225" y="{y+17}" text-anchor="end">{escape(str(label))}</text>')
        for j,(name,color,values) in enumerate(series):
            value=float(values[i]); end=x0(value); bar_y=y+j*30
            parts.append(f'<rect x="{min(zero,end)}" y="{bar_y}" width="{max(abs(end-zero),.5)}" height="21" rx="3" fill="{color}"><title>{escape(str(label))} · {escape(name)}: {_money(value)}</title></rect>')
            parts.append(f'<text x="765" y="{bar_y+17}" text-anchor="end">{_money(value)}</text>')
    parts.append('</svg><div class="legend">')
    parts.extend(f'<span><i style="background:{color}"></i>{escape(name)}</span>' for name,color,_ in series)
    return ''.join(parts)+'</div>'

CSS = '*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#172033;font:15px Arial,sans-serif}main{max-width:1360px;margin:auto;padding:36px 28px}header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:28px}h1{font-size:32px;margin:10px 0}h2{font-size:18px;margin:0 0 20px}.eyebrow{color:#2563eb;font-size:12px;letter-spacing:2px;font-weight:bold}.muted,small{color:#64748b}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}.card,.panel{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:22px}.card p{color:#64748b;margin:0 0 12px}.card strong{font-size:27px;display:block}.card small{display:block;margin-top:12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}.panel{margin-bottom:20px}svg{width:100%;height:auto}.comparison-panel svg{display:block;max-width:760px;margin:0 auto}.comparison-panel .legend{flex-wrap:wrap}svg text{font:17px Arial;fill:#334155}.legend{display:flex;justify-content:center;gap:24px;color:#64748b;font-size:13px}.legend i{display:inline-block;width:10px;height:10px;margin-right:7px}table{width:100%;border-collapse:collapse;white-space:nowrap}td,th{text-align:right;padding:12px;border-bottom:1px solid #e2e8f0}td:first-child,th:first-child{text-align:left}th{color:#64748b;font-size:12px}.table-wrap{overflow-x:auto}.notes{font-size:13px;color:#64748b;line-height:1.8}li{line-height:1.9}button{border:0;background:#172033;color:white;padding:12px 18px;border-radius:8px;cursor:pointer}.badge{color:#166534;background:#dcfce7;padding:8px 12px;border-radius:20px;font-size:12px}@media(max-width:850px){.cards{grid-template-columns:1fr 1fr}.grid{display:block}header{display:block}button{margin-top:16px}}@media print{body{background:white}main{padding:0}button{display:none}.panel,.card{break-inside:avoid}.grid{display:block}.panel{padding:14px;margin-bottom:12px}h2{break-after:avoid;page-break-after:avoid}.panel svg{display:block;width:100%;height:auto;max-height:135mm;break-inside:avoid;page-break-inside:avoid}.legend{break-before:avoid;page-break-before:avoid;flex-wrap:wrap}.table-wrap{overflow:visible}thead{display:table-header-group}tr{break-inside:avoid}@page{size:A4 landscape;margin:12mm}}'


def _marketing_metrics(df, year):
    if df is None or df.empty:
        raise ValueError(f'No eligible marketing campaign data available for {year}.')
    df = df.copy()
    if df['campaign_id'].isna().any() or df['campaign_id'].duplicated().any():
        raise ValueError(f'Missing or duplicate campaign IDs for {year}.')
    numeric = ['campaign_cost','num_of_clicks','delivered_orders','attributed_revenue','attributed_cogs']
    for column in numeric:
        df[column] = pd.to_numeric(df[column], errors='coerce')
        if not df[column].map(math.isfinite).all():
            raise ValueError(f'Invalid or missing {column} for {year}.')
    if (df[['campaign_cost','num_of_clicks','delivered_orders']] < 0).any().any():
        raise ValueError('Campaign costs, clicks and order counts cannot be negative.')
    for column, fallback in [('campaign_name','Unknown campaign'),('channel_name','Unknown channel')]:
        df[column] = df[column].fillna(fallback).astype(str)
    df['profit_after_marketing'] = df['attributed_revenue']-df['attributed_cogs']-df['campaign_cost']
    amounts = ['attributed_revenue','attributed_cogs','campaign_cost','profit_after_marketing']
    channels = df.groupby('channel_name',as_index=False)[amounts].sum()
    totals = {column:float(df[column].sum()) for column in amounts}
    if not all(math.isfinite(v) for v in totals.values()) or not channels[amounts].map(math.isfinite).all().all():
        raise ValueError('Non-finite aggregated marketing amounts.')
    for column in amounts:
        if not math.isclose(float(channels[column].sum()),totals[column],abs_tol=.01,rel_tol=0):
            raise ValueError(f'Channel {column} reconciliation failed.')
    cost = totals['campaign_cost']
    totals.update(roas=totals['attributed_revenue']/cost if cost>0 else None,
                  roi=totals['profit_after_marketing']/cost*100 if cost>0 else None,
                  campaigns=len(df),losses=int((df['profit_after_marketing']<0).sum()),
                  channels=channels.sort_values('profit_after_marketing',ascending=False),
                  detail=df.sort_values(['profit_after_marketing','campaign_id'],ascending=[False,True]))
    return totals


def _performance_table(df, name):
    rows=[]
    for _,r in df.iterrows():
        cost=float(r['campaign_cost'])
        roas=float(r['attributed_revenue'])/cost if cost>0 else None
        roi=float(r['profit_after_marketing'])/cost*100 if cost>0 else None
        label=escape(str(r[name]))
        if name=='campaign_name':
            label += f' <small>(ID {escape(str(r["campaign_id"]))})</small>'
        rows.append(f'<tr><td>{label}</td><td>{_money(r["attributed_revenue"])}</td><td>{_money(cost)}</td><td>{_money(r["profit_after_marketing"])}</td><td>{_ratio(roas,"x")}</td><td>{_ratio(roi,"%")}</td></tr>')
    return '<div class="table-wrap"><table><thead><tr><th>'+('Campaign' if name=='campaign_name' else 'Channel')+'</th><th>Attributed revenue</th><th>Spend</th><th>Profit after marketing</th><th>ROAS</th><th>Marketing ROI</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'


def export_marketing_html(year, fetch_marketing_data, output_folder='reports', open_browser=True):
    base_year=year-1
    try:
        current=_marketing_metrics(fetch_marketing_data(year),year)
        baseline_df=fetch_marketing_data(base_year)
        if baseline_df is None:
            raise ValueError(f'Unable to retrieve baseline marketing data for {base_year}.')
        base=None if baseline_df.empty else _marketing_metrics(baseline_df,base_year)
    except (ValueError,TypeError,KeyError,OverflowError) as error:
        return f'Marketing HTML report was not saved.\n{error}'
    specs=[('Attributed revenue','attributed_revenue','money'),('Attributed COGS','attributed_cogs','money'),('Campaign spend','campaign_cost','money'),('Profit after marketing','profit_after_marketing','money'),('ROAS','roas','x'),('Marketing ROI','roi','%')]
    cards=[]
    for title,key,kind in specs:
        value=current[key]
        display=_money(value) if kind=='money' else _ratio(value,kind)
        old=base[key] if base else None
        if value is None or old is None:
            change='N/A'
        elif kind=='money':
            change=_money(value-old)+' change'
        elif kind=='%':
            change=f'{value-old:+.2f} pp'
        else:
            change=f'{value-old:+.2f}x'
        cards.append(f'<article class="card"><p>{title}</p><strong>{display}</strong><small>{change} vs {base_year}</small></article>')
    channels=current['channels']
    channel_chart=_bars(channels['channel_name'].tolist(),[('Attributed revenue','#2563eb',channels['attributed_revenue'].tolist()),('Spend','#94a3b8',channels['campaign_cost'].tolist()),('Profit after marketing','#14b8a6',channels['profit_after_marketing'].tolist())])
    top=current['detail'].head(10)
    labels=[f'{r["campaign_name"]} (ID {r["campaign_id"]})' for _,r in top.iterrows()]
    campaign_chart=_bars(labels,[('Profit after marketing','#2563eb',top['profit_after_marketing'].tolist())])
    comparison=''
    if base:
        a=base['channels'].set_index('channel_name'); b=channels.set_index('channel_name')
        labels=sorted(set(a.index)|set(b.index))
        comparison='<section class="panel comparison-panel"><h2>Channel profit after marketing · year comparison</h2>'+_bars(labels,[(str(base_year),'#94a3b8',[float(a.loc[n,'profit_after_marketing']) if n in a.index else 0 for n in labels]),(str(year),'#2563eb',[float(b.loc[n,'profit_after_marketing']) if n in b.index else 0 for n in labels])])+'<p class="notes">A channel absent from one available year is plotted with zero amounts.</p></section>'
    comparison_label=f'Compared with {base_year}' if base else f'No data for {base_year}; year-over-year comparisons unavailable'
    best=current['detail'].iloc[0]
    summary=f'<li>{current["campaigns"]:,} eligible campaigns; {current["losses"]:,} generated negative profit after marketing.</li><li>Highest campaign profit after marketing: {escape(str(best["campaign_name"]))} ({_money(best["profit_after_marketing"])}).</li><li>Total attributed revenue of {_money(current["attributed_revenue"])} less attributed COGS of {_money(current["attributed_cogs"])} and campaign spend of {_money(current["campaign_cost"])} gives {_money(current["profit_after_marketing"])} profit after marketing.</li>'
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Venesse marketing · {year}</title><style>{CSS}</style></head><body><main><header><div><div class="eyebrow">VENESSE / MARKETING PERFORMANCE</div><h1>Marketing performance & profitability</h1><p class="muted">January–September {year} · {comparison_label}</p><span class="badge">Campaign & channel totals reconciled · {'Both years' if base else str(year)+' only'}</span></div><button onclick="window.print()">Print / Save as PDF</button></header><div class="cards">{''.join(cards)}</div><div class="grid"><section class="panel"><h2>Channel financial performance · {year}</h2>{channel_chart}</section><section class="panel"><h2>Top 10 campaigns by profit after marketing · {year}</h2>{campaign_chart}</section></div>{comparison}<section class="panel"><h2>Business summary</h2><ul>{summary}</ul><p class="notes">Attributed sales do not establish incremental sales caused by advertising. Profit after marketing excludes other operating expenses.</p></section><section class="panel"><h2>Channel performance · {year}</h2>{_performance_table(channels,'channel_name')}</section><section class="panel"><h2>All campaign performance · {year}</h2>{_performance_table(current['detail'],'campaign_name')}</section><footer class="notes">Generated {datetime.now():%Y-%m-%d %H:%M:%S}. Eligible campaigns both start and end within January–September; campaign costs and clicks come from campaign performance records. Attributed revenue and historical COGS use delivered orders in the same period. ROAS = attributed revenue / campaign spend. Marketing ROI = (attributed revenue − attributed COGS − campaign spend) / campaign spend × 100. Ratios use aggregate amounts, not averages of campaign ratios. N/A indicates missing baseline or zero campaign spend. pp = percentage points. Reconciliation checks internal totals; it does not independently audit source completeness or attribution.</footer></main></body></html>'''
    try:
        folder=Path(output_folder); folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'venesse_marketing_dashboard_{year}_{datetime.now():%Y%m%d_%H%M%S_%f}.html'
        path.write_text(html,encoding='utf-8')
    except OSError as error:
        return f'Unable to save marketing HTML report: {error}'
    if open_browser:
        try: webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error: pass
    return f'Marketing HTML report saved successfully:\n{path.resolve()}'
