"""Offline customer dashboard using the agent's existing SQL query."""
from datetime import datetime
from html import escape
from pathlib import Path
import math
import webbrowser
import pandas as pd
from venesse_html import _chart, _money, _growth


def _customer_metrics(df, year):
    if df is None or df.empty:
        raise ValueError(f"No customer sales data available for {year}.")
    df = df.copy()
    if df[['customer_id', 'order_id']].isna().any().any():
        raise ValueError(f'Missing customer or order IDs for {year}.')
    df['net_revenue'] = pd.to_numeric(df['net_revenue'], errors='coerce')
    if not df['net_revenue'].map(math.isfinite).all():
        raise ValueError(f'Invalid revenue for {year}.')
    dates = pd.to_datetime(df['order_date_key'].astype(str), format='%Y%m%d', errors='coerce')
    if dates.isna().any() or ((dates.dt.year != year) | ~dates.dt.month.between(1, 9)).any():
        raise ValueError(f'Invalid or out-of-period dates for {year}.')
    df['month'] = dates.dt.month
    if (df.groupby('order_id')['customer_id'].nunique() > 1).any():
        raise ValueError(f'Inconsistent order ownership for {year}.')
    if (df.groupby('order_id')['order_date_key'].nunique() > 1).any():
        raise ValueError(f'Inconsistent order dates for {year}.')
    customers = df.groupby('customer_id').agg(orders=('order_id', 'nunique'), revenue=('net_revenue', 'sum'))
    active = len(customers)
    repeat = int((customers['orders'] >= 2).sum())
    orders = df['order_id'].nunique()
    revenue = df['net_revenue'].sum()
    ranked = customers.reset_index().sort_values(['revenue', 'customer_id'], ascending=[False, True])
    top_count = math.ceil(active * .10)
    top_revenue = ranked.head(top_count)['revenue'].sum()
    segments = [('One-time (1 order)', int((customers['orders'] == 1).sum())), ('Repeat (2–3 orders)', int(customers['orders'].between(2, 3).sum())), ('Loyal (4+ orders)', int((customers['orders'] >= 4).sum()))]
    monthly_active, monthly_repeat = [], []
    for month in range(1, 10):
        counts = df.loc[df['month'] == month].groupby('customer_id')['order_id'].nunique()
        monthly_active.append(len(counts))
        monthly_repeat.append(float((counts >= 2).sum() / len(counts) * 100) if len(counts) else None)
    if not math.isclose(customers['revenue'].sum(), revenue, abs_tol=.01, rel_tol=0):
        raise ValueError('Customer revenue reconciliation failed.')
    if customers['orders'].sum() != orders or sum(n for _, n in segments) != active:
        raise ValueError('Customer/order reconciliation failed.')
    return dict(active=active, repeat=repeat, rate=repeat / active * 100, orders=orders, revenue=revenue, aov=revenue / orders, top_count=top_count, top_revenue=top_revenue, top_share=top_revenue / revenue * 100 if revenue > 0 else None, segments=segments, monthly_active=monthly_active, monthly_repeat=monthly_repeat)


def export_customer_html(year, fetch_customer_sales_data, output_folder='reports', open_browser=True):
    base_year = year - 1
    try:
        current = _customer_metrics(fetch_customer_sales_data(year), year)
        baseline_df = fetch_customer_sales_data(base_year)
        if baseline_df is None:
            raise ValueError(f"Unable to retrieve baseline customer sales for {base_year}.")
        has_baseline = not baseline_df.empty
        if has_baseline:
            base = _customer_metrics(baseline_df, base_year)
        else:
            base = dict(active=None, repeat=None, rate=None, aov=None, orders=None,
                        monthly_active=[None] * 9, monthly_repeat=[None] * 9)
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return f'Customer HTML report was not saved.\n{error}'
    share = 'N/A' if current['top_share'] is None else f"{current['top_share']:.2f}%"
    comparison_label = f"Compared with {base_year}" if has_baseline else f"No data for {base_year}; year-over-year comparisons unavailable"
    validation_label = "Both years" if has_baseline else f"{year} only"
    cards = []
    for title, value, change in [
        ('Active customers', f"{current['active']:,}", _growth(current['active'], base['active'])),
        ('Repeat customers', f"{current['repeat']:,}", _growth(current['repeat'], base['repeat'])),
        ('Repeat customer rate', f"{current['rate']:.2f}%", (f"{current['rate']-base['rate']:+.2f} pp" if has_baseline else "N/A")),
        ('Average order value', _money(current['aov']), _growth(current['aov'], base['aov'])),
        ('Delivered orders', f"{current['orders']:,}", _growth(current['orders'], base['orders'])),
        ('Top 10% revenue share', share, f"{current['top_count']} customers · rounded up")]:
        cards.append(f'<article class="card"><p>{title}</p><strong>{value}</strong><small>{change}'+(f' vs {base_year}' if title != 'Top 10% revenue share' else '')+'</small></article>')
    def count_chart():
        max_value = max([v for v in base['monthly_active'] + current['monthly_active'] if v is not None] + [1]) * 1.15
        parts = ['<svg viewBox="0 0 760 300" role="img" aria-label="Monthly active customers">']
        for tick in range(5):
            value = max_value * tick / 4
            y = 256 - value / max_value * 230
            parts.append(f'<line x1="60" y1="{y}" x2="740" y2="{y}" stroke="#e2e8f0"/><text x="48" y="{y+4}" text-anchor="end">{value:.0f}</text>')
        for values, color, label in [(base['monthly_active'], '#94a3b8', base_year), (current['monthly_active'], '#2563eb', year)]:
            if all(v is None for v in values):
                continue
            points = []
            for i, value in enumerate(values):
                x, y = 60+i*85, 256-value/max_value*230
                points.append(f'{x},{y}')
                parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"><title>{label}, month {i+1}: {value} customers</title></circle>')
            parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3"/>')
        for i in range(9):
            parts.append(f'<text x="{60+i*85}" y="285" text-anchor="middle">{datetime(2000,i+1,1):%b}</text>')
        parts.append(f'</svg><p class="muted">' + (f'Gray: {base_year} · Blue: {year}' if has_baseline else f'Blue: {year} · Baseline unavailable') + '</p>')
        return ''.join(parts)
    repeat_series = [(str(year), '#2563eb', current['monthly_repeat'])]
    if has_baseline:
        repeat_series.insert(0, (str(base_year), '#94a3b8', base['monthly_repeat']))
    repeat_chart = _chart(repeat_series, percentage=True)
    segment_rows = ''.join(f'<tr><td>{escape(label)}</td><td>{count:,}</td><td>{count/current["active"]*100:.2f}%</td></tr>' for label,count in current['segments'])
    bars = ''.join(f'<div class="bar-row"><span>{escape(label)}</span><div class="track"><div class="bar" style="width:{count/current["active"]*100:.3f}%"></div></div><strong>{count}</strong></div>' for label,count in current['segments'])
    monthly_rows = ''.join(f'<tr><td>{datetime(2000,i+1,1):%B}</td><td>{base["monthly_active"][i] if has_baseline else "N/A"}</td><td>{current["monthly_active"][i]}</td><td>{"N/A" if current["monthly_repeat"][i] is None else format(current["monthly_repeat"][i],".2f")+"%"}</td></tr>' for i in range(9))
    css = '''*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#172033;font:15px Arial,sans-serif}main{max-width:1240px;margin:auto;padding:36px 28px}header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:28px}h1{font-size:32px;margin:10px 0}h2{font-size:18px;margin:0 0 20px}.eyebrow{color:#2563eb;font-size:12px;letter-spacing:2px;font-weight:bold}.muted,small{color:#64748b}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}.card,.panel{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:22px}.card p{color:#64748b;margin:0 0 12px}.card strong{font-size:27px;display:block}.card small{display:block;margin-top:12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.panel{margin-bottom:20px}svg{width:100%;height:auto}svg text{font:12px Arial;fill:#64748b}.legend{display:flex;justify-content:center;gap:24px;color:#64748b;font-size:13px}.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px}table{width:100%;border-collapse:collapse}td,th{text-align:right;padding:12px;border-bottom:1px solid #e2e8f0}td:first-child,th:first-child{text-align:left}th{color:#64748b;font-size:12px}.table-wrap{overflow-x:auto}.bar-row{display:grid;grid-template-columns:150px 1fr 35px;gap:12px;align-items:center;margin:24px 0;font-size:13px}.track{background:#f1f5f9;height:20px;border-radius:4px}.bar{background:#2563eb;height:20px;border-radius:4px}.notes{font-size:13px;color:#64748b;line-height:1.8}button{border:0;background:#172033;color:white;padding:12px 18px;border-radius:8px;cursor:pointer}.badge{color:#166534;background:#dcfce7;padding:8px 12px;border-radius:20px;font-size:12px}@media(max-width:800px){.cards{grid-template-columns:1fr 1fr}.grid{display:block}header{display:block}button{margin-top:16px}}@media print{body{background:white}main{padding:0}button{display:none}.panel,.card{break-inside:avoid}.grid{display:block}@page{size:A4 landscape;margin:12mm}}'''
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Venesse customers · {year}</title><style>{css}</style></head><body><main><header><div><div class="eyebrow">VENESSE / CUSTOMER PERFORMANCE</div><h1>Customer analytics & purchase behavior</h1><p class="muted">January–September {year} · {comparison_label} · Delivered sales</p><span class="badge">Customer revenue, orders & segments reconciled · {validation_label}</span></div><button onclick="window.print()">Print / Save as PDF</button></header><div class="cards">{''.join(cards)}</div><div class="grid"><section class="panel"><h2>Monthly active customers</h2>{count_chart()}</section><section class="panel"><h2>Monthly repeat customer rate</h2>{repeat_chart}</section><section class="panel"><h2>Purchase frequency · {year}</h2>{bars}<table><thead><tr><th>Segment</th><th>Customers</th><th>Share</th></tr></thead><tbody>{segment_rows}</tbody></table></section><section class="panel"><h2>Revenue concentration</h2><p>Top {current['top_count']} customers generated <strong>{_money(current['top_revenue'])}</strong>, or <strong>{share}</strong> of revenue.</p><p>Total delivered revenue: {_money(current['revenue'])}.</p><p class="notes">The top 10% group is ranked by revenue separately each year. Group size is rounded up. The group can contain different customers between years.</p></section></div><section class="panel"><h2>Monthly customer detail</h2><div class="table-wrap"><table><thead><tr><th>Month</th><th>Active {base_year}</th><th>Active {year}</th><th>Repeat rate {year}</th></tr></thead><tbody>{monthly_rows}</tbody></table></div></section><footer class="notes">Generated {datetime.now():%Y-%m-%d %H:%M:%S}. Repeat customer = at least two distinct delivered orders within the stated period. Monthly repeat rate uses customers with two or more orders in that month divided by active customers in that month. Annual figures use the entire January–September period; monthly active counts must not be summed to obtain annual unique customers. This is purchase behavior, not cross-year cohort retention. Internal reconciliation does not independently audit source completeness.</footer></main></body></html>'''
    try:
        folder = Path(output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'venesse_customers_dashboard_{year}_{datetime.now():%Y%m%d_%H%M%S_%f}.html'
        path.write_text(html, encoding='utf-8')
    except OSError as error:
        return f'Unable to save customer HTML report: {error}'
    if open_browser:
        try:
            webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error:
            pass
    return f'Customer HTML report saved successfully:\n{path.resolve()}'

