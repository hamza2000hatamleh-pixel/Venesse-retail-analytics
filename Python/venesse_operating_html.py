"""Offline operating profitability dashboard; provisional separate campaign costs."""
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


def _operating_metrics(year, sales, expenses, campaigns):
    for name, data in (('sales', sales), ('expense', expenses), ('operating campaign', campaigns)):
        if data is None or data.empty:
            raise ValueError(f'No {name} data available for {year}.')
    sales = sales.copy()
    expenses = expenses.copy()
    campaigns = campaigns.copy()
    for data, id_column in ((expenses, 'expense_id'), (campaigns, 'campaign_id')):
        if data[id_column].isna().any():
            raise ValueError(f'Missing {id_column} values for {year}.')
        if data[id_column].duplicated().any():
            raise ValueError(f'Duplicate {id_column} values for {year}.')
    for data, columns in ((sales, ('net_revenue', 'cogs')), (expenses, ('expense_amount',)), (campaigns, ('campaign_cost',))):
        for column in columns:
            data[column] = pd.to_numeric(data[column], errors='coerce')
            if not data[column].map(math.isfinite).all():
                raise ValueError(f'Invalid or missing {column} for {year}.')
    date_specs = ((sales, 'order_date_key', '%Y%m%d'), (expenses, 'expense_date_key', '%Y%m%d'), (campaigns, 'campaign_start_date', None))
    for data, column, date_format in date_specs:
        dates = pd.to_datetime(data[column].astype(str), format=date_format, errors='coerce')
        if dates.isna().any():
            raise ValueError(f'Invalid or missing {column} for {year}.')
        if ((dates.dt.year != year) | ~dates.dt.month.between(1, 9)).any():
            raise ValueError(f'Out-of-period {column} values for {year}.')
        data['month'] = dates.dt.month
    expenses['expense_category_name'] = expenses['expense_category_name'].fillna('Uncategorized')
    monthly = pd.DataFrame(index=pd.Index(range(1, 10), name='month'))
    monthly_sales = sales.groupby('month').agg(revenue=('net_revenue', 'sum'), cogs=('cogs', 'sum'))
    monthly = monthly.join(monthly_sales)
    monthly['operating_expenses'] = expenses.groupby('month')['expense_amount'].sum()
    monthly['campaign_costs'] = campaigns.groupby('month')['campaign_cost'].sum()
    monthly = monthly.fillna(0)
    monthly['gross_profit'] = monthly['revenue'] - monthly['cogs']
    monthly['operating_profit'] = monthly['gross_profit'] - monthly['operating_expenses'] - monthly['campaign_costs']
    monthly['operating_margin'] = monthly['operating_profit'] / monthly['revenue'].where(monthly['revenue'] != 0) * 100
    categories = expenses.groupby('expense_category_name')['expense_amount'].sum().sort_values(ascending=False)
    revenue = sales['net_revenue'].sum()
    cogs = sales['cogs'].sum()
    gross_profit = revenue - cogs
    operating_expenses = expenses['expense_amount'].sum()
    campaign_costs = campaigns['campaign_cost'].sum()
    operating_profit = gross_profit - operating_expenses - campaign_costs
    totals=dict(revenue=float(revenue),cogs=float(cogs),gross_profit=float(gross_profit),operating_expenses=float(operating_expenses),campaign_costs=float(campaign_costs),operating_profit=float(operating_profit))
    for key,value in totals.items():
        if not math.isfinite(value) or not monthly[key].map(math.isfinite).all() or not math.isclose(float(monthly[key].sum()),value,abs_tol=.01,rel_tol=0):
            raise ValueError(f'Monthly {key} reconciliation failed for {year}.')
    if not categories.map(math.isfinite).all() or not math.isclose(float(categories.sum()),totals['operating_expenses'],abs_tol=.01,rel_tol=0):
        raise ValueError(f'Expense category reconciliation failed for {year}.')
    totals.update(margin=operating_profit/revenue*100 if revenue!=0 else None,monthly=monthly,categories=categories,top_expenses=expenses.sort_values(["expense_amount","expense_date_key","expense_id"],ascending=[False,True,True]).head(10).copy(),loss_months=int((monthly['operating_profit']<0).sum()))
    return totals



def _top_expenses_table(metrics, selected_year):
    if metrics is None:
        return f'<section class="panel"><h2>Top 10 individual expenses · {selected_year}</h2><p class="notes">Previous-year data unavailable.</p></section>'
    rows=[]
    top=metrics['top_expenses']
    for rank,(_,r) in enumerate(top.iterrows(),1):
        name=r.get('expense_name')
        name='Unnamed expense' if pd.isna(name) else str(name)
        date=pd.to_datetime(str(r['expense_date_key']),format='%Y%m%d').strftime('%d %b %Y')
        rows.append(f'<tr><td>{rank}</td><td>{escape(name)}<br><small>ID {escape(str(r["expense_id"]))}</small></td><td>{escape(str(r["expense_category_name"]))}</td><td>{date}</td><td>{_money(r["expense_amount"])}</td></tr>')
    return f'<section class="panel"><h2>Top 10 individual expenses · {selected_year}</h2><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Expense</th><th>Category</th><th>Date</th><th>Amount</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div><p class="notes">Showing {len(top)} individual records. Top-record total: {_money(top["expense_amount"].sum())}.</p></section>'

def export_operating_html(year, fetch_sales_data, fetch_operating_expenses, fetch_operating_campaign_costs, output_folder='reports', open_browser=True):
    def retrieve(selected):
        datasets=(fetch_sales_data(selected),fetch_operating_expenses(selected),fetch_operating_campaign_costs(selected))
        if any(df is None for df in datasets):
            raise ValueError(f'Unable to retrieve all operating datasets for {selected}.')
        return datasets
    try:
        current=_operating_metrics(year,*retrieve(year))
        baseline_data=retrieve(year-1)
        # An entirely empty baseline is unavailable. Partial baseline data is
        # validated and rejected if a required cost dataset is missing.
        base=None if all(df.empty for df in baseline_data) else _operating_metrics(year-1,*baseline_data)
    except (ValueError,TypeError,KeyError,OverflowError) as error:
        return f'Operating HTML report was not saved.\n{error}'
    specs=[('Revenue','revenue'),('Gross profit','gross_profit'),('Operating expenses','operating_expenses'),('Separate campaign costs','campaign_costs'),('Operating profit · provisional','operating_profit'),('Operating margin · provisional','margin')]
    cards=[]
    for title,key in specs:
        value=current[key]
        display=_ratio(value,'%') if key=='margin' else _money(value)
        old=base[key] if base else None
        change='N/A' if value is None or old is None else f'{value-old:+.2f} pp' if key=='margin' else _money(value-old)+' change'
        cards.append(f'<article class="card"><p>{title}</p><strong>{display}</strong><small>{change} vs {year-1}</small></article>')
    month_labels=[datetime(2000,m,1).strftime('%b') for m in range(1,10)]
    monthly=current['monthly']
    series=[(str(year),'#2563eb',monthly['operating_profit'].tolist())]
    if base:
        series.insert(0,(str(year-1),'#94a3b8',base['monthly']['operating_profit'].tolist()))
    profit_chart=_bars(month_labels,series)
    categories=current['categories']
    cost_chart=_bars([str(v) for v in categories.index],[('Operating expenses','#14b8a6',categories.tolist())])
    rows=[]
    for month,r in monthly.iterrows():
        amount_cells=''.join(f'<td>{_money(r[k])}</td>' for k in ('revenue','gross_profit','operating_expenses','campaign_costs','operating_profit'))
        margin=None if pd.isna(r['operating_margin']) else float(r['operating_margin'])
        old=base['monthly'].loc[month,'operating_profit'] if base else None
        change='N/A' if old is None else _money(r['operating_profit']-old)
        rows.append(f'<tr><td>{month_labels[month-1]}</td>{amount_cells}<td>{_ratio(margin,"%")}</td><td>{change}</td></tr>')
    comparison=f'Compared with {year-1}' if base else f'No data for {year-1}; year-over-year comparisons unavailable'
    summary=f'<li>{current["loss_months"]} of 9 months recorded an operating loss.</li><li>Gross profit of {_money(current["gross_profit"])} less operating expenses of {_money(current["operating_expenses"])} and separate campaign costs of {_money(current["campaign_costs"])} gives provisional operating profit of {_money(current["operating_profit"])}.</li><li>Largest expense category: {escape(str(categories.index[0]))} ({_money(categories.iloc[0])}).</li>'
    top_comparison='<section class="panel"><h2>Largest individual expenses · year comparison</h2><p class="notes">Each year is ranked independently by individual expense amount; records at the same rank are not matched expenses. Categories identify each record and are not aggregated here.</p>'
    if base:
        difference=float(current['top_expenses']['expense_amount'].sum()-base['top_expenses']['expense_amount'].sum())
        top_comparison+=f'<p>Change in the total of each year’s top 10 records: {_money(difference)}.</p>'
    top_comparison+='</section><div class="grid">'+_top_expenses_table(base,year-1)+_top_expenses_table(current,year)+'</div>'
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Venesse operating profitability · {year}</title><style>{CSS}</style></head><body><main><header><div><div class="eyebrow">VENESSE / OPERATING PROFITABILITY</div><h1>Operating expenses & profitability</h1><p class="muted">January–September {year} · Delivered sales · {comparison}</p><span class="badge">Monthly & category totals reconciled · {'Both years' if base else str(year)+' only'}</span></div><button onclick="window.print()">Print / Save as PDF</button></header><section class="panel"><h2>Provisional cost treatment</h2><p class="notes">Campaign costs are treated as separate from operating expenses. Confirm that they are not already included in expenses before using the operating-profit figure for decisions. Full campaign cost is assigned to its start month.</p></section><div class="cards">{''.join(cards)}</div><div class="grid"><section class="panel"><h2>Monthly operating profit · provisional</h2>{profit_chart}</section><section class="panel"><h2>Operating expenses by category · {year}</h2>{cost_chart}</section></div><section class="panel"><h2>Monthly operating performance · {year}</h2><div class="table-wrap"><table><thead><tr><th>Month</th><th>Revenue</th><th>Gross profit</th><th>Expenses</th><th>Campaign costs</th><th>Operating profit</th><th>Operating margin</th><th>Profit change vs {year-1}</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>{top_comparison}<section class="panel"><h2>Business summary</h2><ul>{summary}</ul></section><footer class="notes">Generated {datetime.now():%Y-%m-%d %H:%M:%S}. Operating profit = revenue − historical COGS − operating expenses − separate campaign costs. Operating margin = operating profit / revenue × 100. Campaign eligibility uses start dates within January–September, including campaigns ending later. This differs from the marketing dashboard's requirement that both campaign start and end fall within that period. Months without records within retrieved datasets show zero; entirely missing expense or campaign datasets block generation. Internal reconciliation does not independently audit source completeness or expense overlap. N/A indicates unavailable comparisons or zero revenue. pp = percentage points.</footer></main></body></html>'''
    try:
        folder=Path(output_folder); folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'venesse_operating_dashboard_{year}_{datetime.now():%Y%m%d_%H%M%S_%f}.html'
        path.write_text(html,encoding='utf-8')
    except OSError as error:
        return f'Unable to save operating HTML report: {error}'
    if open_browser:
        try: webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error: pass
    return f'Operating HTML report saved successfully:\n{path.resolve()}'
