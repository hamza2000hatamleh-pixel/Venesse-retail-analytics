"""Offline retention dashboard using delivered Jan–Sep customer sales."""
from datetime import datetime
from html import escape
from pathlib import Path
import math
import webbrowser
import pandas as pd


def _retention_metrics(baseline, current):
    if baseline is None or current is None:
        raise ValueError('Unable to retrieve customer sales data.')
    if baseline.empty:
        raise ValueError('No previous-year cohort is available; retention cannot be calculated.')
    for frame in (baseline, current):
        if frame['customer_id'].isna().any():
            raise ValueError('Missing customer IDs.')
    baseline = baseline.copy()
    for frame in (baseline, current.copy()):
        values = pd.to_numeric(frame['net_revenue'], errors='coerce')
        if not values.map(math.isfinite).all():
            raise ValueError('Invalid or missing revenue values.')
        frame['net_revenue'] = values
    revenue = baseline.groupby('customer_id')['net_revenue'].sum()
    if not revenue.map(math.isfinite).all() or not math.isfinite(float(revenue.sum())):
        raise ValueError('Non-finite aggregated revenue.')
    cohort, active = set(revenue.index), set(current['customer_id'])
    retained, absent = cohort & active, cohort - active
    segments = revenue.rename('revenue').to_frame()
    ranks = revenue.rank(method='dense', ascending=False)
    segments['segment'] = ranks.map(lambda r: 'High Value' if r <= math.ceil(len(cohort)*.2) else 'Medium Value' if r <= math.ceil(len(cohort)*.5) else 'Low Value')
    lost = segments.loc[segments.index.isin(absent)]
    grouped = lost.groupby('segment').agg(customers=('revenue','size'), risk=('revenue','sum')).reindex(['High Value','Medium Value','Low Value'],fill_value=0)
    risk = float(revenue.loc[revenue.index.isin(absent)].sum())
    kept = float(revenue.loc[revenue.index.isin(retained)].sum())
    total = float(revenue.sum())
    checks = [len(retained)+len(absent)==len(cohort), len(retained)+len(active-cohort)==len(active), int(grouped['customers'].sum())==len(absent), math.isclose(kept+risk,total,abs_tol=.01,rel_tol=0), math.isclose(float(grouped['risk'].sum()),risk,abs_tol=.01,rel_tol=0)]
    if not all(checks):
        raise ValueError('Retention reconciliation failed.')
    return dict(cohort=len(cohort),retained=len(retained),absent=len(absent),current_only=len(active-cohort),rate=len(retained)/len(cohort)*100,risk=risk,total=total,segments=grouped)


def _bars(labels, values, money=False):
    low, high = min([0]+values), max([0]+values)
    span = high-low or 1
    zero = 210 + (0-low)/span*430
    parts = [f'<svg viewBox="0 0 800 {len(labels)*55+20}" role="img" aria-label="Retention performance">']
    for i,(label,value) in enumerate(zip(labels,values)):
        y=15+i*55; end=210+(value-low)/span*430
        display=f'${value:,.2f}' if money else f'{value:,.0f}'
        parts.append(f'<text x="195" y="{y+16}" text-anchor="end">{escape(label)}</text><rect x="{min(zero,end)}" y="{y}" width="{abs(end-zero)}" height="25" rx="4" fill="{["#2563eb","#e57d32","#64748b"][i%3]}"><title>{escape(label)}: {display}</title></rect><text x="660" y="{y+17}">{display}</text>')
    return ''.join(parts)+'</svg>'


def export_retention_html(year, fetch_customer_sales_data, output_folder='reports', open_browser=True):
    try:
        baseline=fetch_customer_sales_data(year-1)
        current=fetch_customer_sales_data(year)
        m=_retention_metrics(baseline,current)
    except (ValueError,TypeError,KeyError,OverflowError) as error:
        return f'Retention HTML report was not saved.\n{error}'
    pct=lambda value: 'N/A' if value is None else f'{value:.2f}%'
    share=m['risk']/m['total']*100 if m['total']>0 else None
    cards=[('Previous-year cohort',f"{m['cohort']:,}"),('Retained customers',f"{m['retained']:,}"),('Retention rate',pct(m['rate'])),('Non-returning customers',f"{m['absent']:,}"),('Historical revenue at risk',f"${m['risk']:,.2f}"),('Share of baseline revenue',pct(share))]
    card_html=''.join(f'<article><p>{title}</p><strong>{value}</strong></article>' for title,value in cards)
    g=m['segments']
    rows=''.join(f'<tr><td>{escape(label)}</td><td>{int(row["customers"]):,}</td><td>${row["risk"]:,.2f}</td><td>{pct(row["risk"]/m["risk"]*100 if m["risk"]>0 else None)}</td></tr>' for label,row in g.iterrows())
    count_chart=_bars(['Retained','Non-returning'],[m['retained'],m['absent']])
    risk_chart=_bars(list(g.index),g['risk'].astype(float).tolist(),True)
    css='''*{box-sizing:border-box}body{background:#f1f5f9;color:#172033;font:15px Arial;margin:0}main{max-width:1350px;margin:auto;padding:36px 28px}header{display:flex;justify-content:space-between;align-items:center}h1{font-size:32px}h2{font-size:19px}.eyebrow{color:#2563eb;letter-spacing:2px;font-weight:bold;font-size:12px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:26px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}article,section{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:22px}section{margin-bottom:20px}strong{font-size:29px}p,footer{color:#64748b;line-height:1.7}svg{width:100%}svg text{font:13px Arial;fill:#475569}table{width:100%;border-collapse:collapse}td,th{text-align:right;padding:14px;border-bottom:1px solid #e2e8f0}td:first-child,th:first-child{text-align:left}.table-wrap{overflow:auto}button{background:#172033;color:white;border:0;padding:12px 18px;border-radius:8px}.badge{color:#166534}li{line-height:1.9}@media(max-width:850px){.cards{grid-template-columns:1fr 1fr}.grid{display:block}header{display:block}}@media print{body{background:white}button{display:none}main{padding:0}.grid{display:block}section,article{break-inside:avoid}@page{size:A4 landscape;margin:12mm}}'''
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Venesse retention · {year}</title><style>{css}</style></head><body><main><header><div><div class="eyebrow">VENESSE / CUSTOMER RETENTION</div><h1>Customer retention & historical revenue at risk</h1><p>January–September {year-1} cohort → January–September {year} · Delivered sales</p><span class="badge">Cohort, revenue and segment reconciliation passed</span></div><button onclick="window.print()">Print / Save as PDF</button></header><div class="cards">{card_html}</div><div class="grid"><section><h2>Previous-year cohort outcomes</h2>{count_chart}</section><section><h2>Historical revenue at risk by value segment</h2>{risk_chart}</section></div><section><h2>Non-returning customer segments</h2><div class="table-wrap"><table><thead><tr><th>Baseline value segment</th><th>Customers</th><th>Historical revenue at risk</th><th>Share of risk</th></tr></thead><tbody>{rows}</tbody></table></div></section><section><h2>Business summary</h2><ul><li>{m['retained']:,} of {m['cohort']:,} baseline customers returned: {m['rate']:.2f}% retention.</li><li>{m['absent']:,} baseline customers did not return within the selected period; their baseline revenue was ${m['risk']:,.2f}.</li><li>{m['current_only']:,} current-period customers were absent from the baseline period. This does not establish that they are first-time customers.</li></ul><p>Revenue at risk is historical baseline revenue, not forecast lost sales. Retention is customer-based, irrespective of the number of sales-item rows.</p></section><footer>Generated {datetime.now():%Y-%m-%d %H:%M:%S}. Value segments use dense descending baseline-revenue rank: High ≤ ceil(cohort × 20%); Medium ≤ ceil(cohort × 50%); Low otherwise. Ties can change group proportions. A previous-year cohort is required. Empty current-period results are treated as zero observed returns; confirm source completeness before interpreting them. Internal reconciliation does not independently audit source completeness or join uniqueness. N/A indicates a non-positive revenue denominator.</footer></main></body></html>'''
    try:
        folder=Path(output_folder); folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'venesse_retention_dashboard_{year}_{datetime.now():%Y%m%d_%H%M%S_%f}.html'
        path.write_text(html,encoding='utf-8')
    except OSError as error:
        return f'Unable to save retention HTML report: {error}'
    if open_browser:
        try: webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error: pass
    return f'Retention HTML report saved successfully:\n{path.resolve()}'
