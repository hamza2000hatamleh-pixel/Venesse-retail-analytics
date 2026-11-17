"""Standalone offline product profitability dashboard."""
from datetime import datetime
from html import escape
from pathlib import Path
import math
import webbrowser
import pandas as pd
from venesse_html import _money, _growth, _pct


def _product_metrics(df, year):
    if df is None or df.empty:
        raise ValueError(f'No product sales data available for {year}.')
    df = df.copy()
    if df['product_id'].isna().any():
        raise ValueError(f'Missing product IDs for {year}.')
    for column in ('quantity', 'net_revenue', 'cogs'):
        df[column] = pd.to_numeric(df[column], errors='coerce')
        if not df[column].map(math.isfinite).all():
            raise ValueError(f'Invalid or missing {column} for {year}.')
    df['product_name'] = df['product_name'].fillna('Unknown product')
    df['category_name'] = df['category_name'].fillna('Uncategorized')
    # A single product ID must not split across contradictory labels.
    labels = df.groupby('product_id')[['product_name', 'category_name']].nunique()
    if (labels > 1).any().any():
        raise ValueError(f'Inconsistent product labels for {year}.')
    def aggregate(keys):
        grouped = df.groupby(keys, as_index=False).agg(units=('quantity','sum'), revenue=('net_revenue','sum'), cogs=('cogs','sum'))
        grouped['profit'] = grouped['revenue'] - grouped['cogs']
        grouped['margin'] = grouped['profit'] / grouped['revenue'].where(grouped['revenue'] != 0) * 100
        return grouped
    products = aggregate(['product_id','product_name','category_name'])
    categories = aggregate(['category_name']).sort_values('revenue', ascending=False)
    revenue, cogs, units = df['net_revenue'].sum(), df['cogs'].sum(), df['quantity'].sum()
    profit = revenue - cogs
    top = products.sort_values(['profit','product_id'], ascending=[False,True]).head(10)
    for grouped in (products,categories):
        for column, expected in [('revenue',revenue),('cogs',cogs),('profit',profit),('units',units)]:
            if not math.isclose(grouped[column].sum(), expected, abs_tol=.01, rel_tol=0):
                raise ValueError(f'Product/category {column} reconciliation failed for {year}.')
    return dict(products=products,categories=categories,top=top,revenue=revenue,profit=profit,units=units,active=products['product_id'].nunique(),margin=profit/revenue*100 if revenue else None,top_profit=top['profit'].sum(),top_share=top['profit'].sum()/profit*100 if profit>0 else None)


def _bars(labels, series):
    """Grouped horizontal bars with a shared scale, supporting losses."""
    all_values=[float(v) for _,_,values in series for v in values]
    low, high = min([0]+all_values), max([0]+all_values)
    if high==low: high=low+1
    span=high-low
    low-=span*.05 if low<0 else 0
    high+=span*.12
    height=60+len(labels)*(len(series)*22+16)
    x0=lambda value: 190+(value-low)/(high-low)*460
    zero=x0(0)
    parts=[f'<svg viewBox="0 0 780 {height}" role="img" aria-label="Product or category financial performance">']
    parts.append(f'<line x1="{zero}" x2="{zero}" y1="10" y2="{height-35}" stroke="#cbd5e1"/>')
    for i,label in enumerate(labels):
        y=20+i*(len(series)*22+16)
        parts.append(f'<text x="180" y="{y+14}" text-anchor="end">{escape(str(label))}</text>')
        for j,(name,color,values) in enumerate(series):
            value=float(values[i]); end=x0(value); bar_y=y+j*22
            parts.append(f'<rect x="{min(zero,end)}" y="{bar_y}" width="{max(abs(end-zero),.5)}" height="15" rx="2" fill="{color}"><title>{escape(str(label))} · {escape(name)}: {_money(value)}</title></rect>')
            parts.append(f'<text x="{end+5 if value>=0 else end-5}" y="{bar_y+12}" text-anchor="{"start" if value>=0 else "end"}">{_money(value)}</text>')
    parts.append('</svg><div class="legend">')
    parts.extend(f'<span><i style="background:{color}"></i>{escape(name)}</span>' for name,color,_ in series)
    return ''.join(parts)+'</div>'


def export_product_html(year, fetch_product_sales_data, output_folder='reports', open_browser=True):
    base_year=year-1
    try:
        current=_product_metrics(fetch_product_sales_data(year),year)
        baseline_df=fetch_product_sales_data(base_year)
        if baseline_df is None:
            raise ValueError(f'Unable to retrieve baseline product sales for {base_year}.')
        base=None if baseline_df.empty else _product_metrics(baseline_df,base_year)
    except (ValueError,TypeError,KeyError,OverflowError) as error:
        return f'Product HTML report was not saved.\n{error}'
    comparison_label=f'Compared with {base_year}' if base is not None else f'No data for {base_year}; year-over-year comparisons unavailable'
    validation_label='Both years' if base is not None else f'{year} only'
    cards=[]
    for title,value,detail in [
        ('Units sold',f"{current['units']:,.0f}",_growth(current['units'],base['units'] if base else None)),
        ('Products with sales',f"{current['active']:,}",_growth(current['active'],base['active'] if base else None)),
        ('Revenue',_money(current['revenue']),_growth(current['revenue'],base['revenue'] if base else None)),
        ('Gross profit',_money(current['profit']),_growth(current['profit'],base['profit'] if base else None)),
        ('Gross margin',_pct(current['margin']),f"{current['margin']-base['margin']:+.2f} pp" if base and current['margin'] is not None and base['margin'] is not None else 'N/A'),
        ('Top 10 gross-profit share',_pct(current['top_share']),_money(current['top_profit'])+' gross profit')]:
        cards.append(f'<article class="card"><p>{title}</p><strong>{value}</strong><small>{detail}'+(f' vs {base_year}' if title!='Top 10 gross-profit share' else '')+'</small></article>')
    top=current['top']; cats=current['categories']
    top_chart=_bars(top['product_name'].tolist(),[(str(year)+' gross profit','#2563eb',top['profit'].tolist())])
    category_chart=_bars(cats['category_name'].tolist(),[('Revenue','#2563eb',cats['revenue'].tolist()),('Gross profit','#14b8a6',cats['profit'].tolist())])
    previous_panel=''
    if base:
        old_top=base['top']
        previous_panel=f'<section class="panel"><h2>Top 10 by gross profit · {base_year}</h2>{_bars(old_top["product_name"].tolist(),[(str(base_year)+" gross profit","#94a3b8",old_top["profit"].tolist())])}<p class="notes">Top products are ranked independently for each year.</p></section>'
    category_rows=[]
    for _,row in cats.iterrows():
        old_margin=None
        if base:
            matches=base['categories'].loc[base['categories']['category_name']==row['category_name']]
            if not matches.empty and pd.notna(matches.iloc[0]['margin']): old_margin=float(matches.iloc[0]['margin'])
        margin=None if pd.isna(row['margin']) else float(row['margin'])
        change=f'{margin-old_margin:+.2f} pp' if margin is not None and old_margin is not None else 'N/A'
        category_rows.append(f'<tr><td>{escape(str(row["category_name"]))}</td><td>{row["units"]:,.0f}</td><td>{_money(row["revenue"])}</td><td>{_money(row["profit"])}</td><td>{_pct(old_margin)}</td><td>{_pct(margin)}</td><td>{change}</td></tr>')
    top_rows=''.join(f'<tr><td>{escape(str(row["product_name"]))}</td><td>{escape(str(row["category_name"]))}</td><td>{row["units"]:,.0f}</td><td>{_money(row["revenue"])}</td><td>{_money(row["profit"])}</td><td>{_pct(None if pd.isna(row["margin"]) else row["margin"])}</td></tr>' for _,row in top.iterrows())
    best=top.iloc[0]
    best_category=cats.sort_values('profit',ascending=False).iloc[0]
    summary=f'<li>Highest product gross profit: {escape(str(best["product_name"]))} ({_money(best["profit"])}).</li><li>Highest category gross profit: {escape(str(best_category["category_name"]))} ({_money(best_category["profit"])}).</li>'
    if current['top_share'] is not None: summary+=f'<li>The top 10 products generated {current["top_share"]:.2f}% of total gross profit.</li>'
    css='''*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#172033;font:15px Arial,sans-serif}main{max-width:1360px;margin:auto;padding:36px 28px}header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:28px}h1{font-size:32px;margin:10px 0}h2{font-size:18px;margin:0 0 20px}.eyebrow{color:#2563eb;font-size:12px;letter-spacing:2px;font-weight:bold}.muted,small{color:#64748b}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}.card,.panel{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:22px}.card p{color:#64748b;margin:0 0 12px}.card strong{font-size:27px;display:block}.card small{display:block;margin-top:12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}.panel{margin-bottom:20px}svg{width:100%;height:auto}svg text{font:12px Arial;fill:#475569}.legend{display:flex;justify-content:center;gap:24px;color:#64748b;font-size:13px}.legend i{display:inline-block;width:10px;height:10px;margin-right:7px}table{width:100%;border-collapse:collapse;white-space:nowrap}td,th{text-align:right;padding:12px;border-bottom:1px solid #e2e8f0}td:first-child,th:first-child{text-align:left}th{color:#64748b;font-size:12px}.table-wrap{overflow-x:auto}.notes{font-size:13px;color:#64748b;line-height:1.8}li{line-height:1.9}button{border:0;background:#172033;color:white;padding:12px 18px;border-radius:8px;cursor:pointer}.badge{color:#166534;background:#dcfce7;padding:8px 12px;border-radius:20px;font-size:12px}@media(max-width:850px){.cards{grid-template-columns:1fr 1fr}.grid{display:block}header{display:block}button{margin-top:16px}}@media print{body{background:white}main{padding:0}button{display:none}.panel,.card{break-inside:avoid}.grid{display:block}@page{size:A4 landscape;margin:12mm}}'''
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Venesse products · {year}</title><style>{css}</style></head><body><main><header><div><div class="eyebrow">VENESSE / PRODUCT PERFORMANCE</div><h1>Product performance & profitability</h1><p class="muted">January–September {year} · {comparison_label} · Delivered sales</p><span class="badge">Product & category totals reconciled · {validation_label}</span></div><button onclick="window.print()">Print / Save as PDF</button></header><div class="cards">{''.join(cards)}</div><div class="grid"><section class="panel"><h2>Top 10 by gross profit · {year}</h2>{top_chart}</section><section class="panel"><h2>Category revenue & gross profit · {year}</h2>{category_chart}</section>{previous_panel}<section class="panel"><h2>Business summary</h2><ul>{summary}</ul><p class="notes">Rankings reflect observed delivered sales; they do not establish future demand or justify an inventory or pricing change by themselves.</p></section></div><section class="panel"><h2>Category margins & performance</h2><div class="table-wrap"><table><thead><tr><th>Category</th><th>Units {year}</th><th>Revenue {year}</th><th>Gross profit {year}</th><th>Margin {base_year}</th><th>Margin {year}</th><th>Margin change</th></tr></thead><tbody>{''.join(category_rows)}</tbody></table></div></section><section class="panel"><h2>Top-product detail · {year}</h2><div class="table-wrap"><table><thead><tr><th>Product</th><th>Category</th><th>Units</th><th>Revenue</th><th>Gross profit</th><th>Margin</th></tr></thead><tbody>{top_rows}</tbody></table></div></section><footer class="notes">Generated {datetime.now():%Y-%m-%d %H:%M:%S}. Historical sales COGS are used. Gross margin = gross profit / revenue; total margin is weighted by revenue. pp = percentage points. N/A = missing baseline/category, zero revenue, or non-positive growth baseline. Product and category units, revenue, COGS and gross profit reconcile to the retrieved source totals for each available year. These internal checks do not independently audit the source data or join uniqueness.</footer></main></body></html>'''
    try:
        folder=Path(output_folder); folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'venesse_products_dashboard_{year}_{datetime.now():%Y%m%d_%H%M%S_%f}.html'
        path.write_text(html,encoding='utf-8')
    except OSError as error:
        return f'Unable to save product HTML report: {error}'
    if open_browser:
        try: webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error: pass
    return f'Product HTML report saved successfully:\n{path.resolve()}'
