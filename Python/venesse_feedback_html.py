"""Offline customer-feedback dashboard, based on order-date Jan–Sep reviews."""
from datetime import datetime
from html import escape
from pathlib import Path
import webbrowser
import pandas as pd


def _classify(comment):
    text = '' if pd.isna(comment) else str(comment).strip().casefold()
    if text == 'slow delivery':
        return 'Delivery'
    if text in ('product arrived damaged', 'quality below expectation'):
        return 'Product Quality / Handling'
    return 'General Dissatisfaction'


def _feedback_metrics(df, year):
    if df is None or df.empty:
        raise ValueError(f'No customer feedback available for {year}.')
    df = df.copy()
    if df['feedback_id'].isna().any() or df['feedback_id'].duplicated().any():
        raise ValueError(f'Missing or duplicate feedback IDs for {year}.')
    df['out_of_5_star'] = pd.to_numeric(df['out_of_5_star'], errors='coerce')
    if not df['out_of_5_star'].isin([1,2,3,4,5]).all():
        raise ValueError(f'Invalid or missing ratings for {year}.')
    df['region'] = df['region'].fillna('Unknown region').astype(str)
    df['negative'] = df['out_of_5_star'] <= 2
    total = len(df)
    positive = int((df['out_of_5_star'] >= 4).sum())
    neutral = int((df['out_of_5_star'] == 3).sum())
    negative = int(df['negative'].sum())
    ratings = df['out_of_5_star'].value_counts().reindex([1,2,3,4,5], fill_value=0)
    regions = df.groupby('region').agg(reviews=('feedback_id','size'), negative=('negative','sum'), average=('out_of_5_star','mean'))
    regions['negative_pct'] = regions['negative']/regions['reviews']*100
    regions = regions.sort_values(['negative_pct','reviews'], ascending=[False,False])
    complaints = df.loc[df['negative'],'comments'].map(_classify).value_counts().reindex(['Delivery','Product Quality / Handling','General Dissatisfaction'],fill_value=0)
    checks = [int(ratings.sum())==total, positive+neutral+negative==total, int(regions['reviews'].sum())==total, int(regions['negative'].sum())==negative, int(complaints.sum())==negative]
    if not all(checks):
        raise ValueError(f'Feedback reconciliation failed for {year}.')
    return dict(total=total,average=float(df['out_of_5_star'].mean()),positive=positive,neutral=neutral,negative=negative,positive_pct=positive/total*100,negative_pct=negative/total*100,ratings=ratings,regions=regions,complaints=complaints)


def _chart(labels, series, percentage=False):
    # Fixed value column avoids collisions with category labels.
    maximum=max([float(v) for _,_,values in series for v in values]+[1])
    height=70+len(labels)*(len(series)*30+24)
    parts=[f'<svg viewBox="0 0 800 {height}" role="img" aria-label="Customer feedback distribution">']
    for i,label in enumerate(labels):
        y=24+i*(len(series)*30+24)
        parts.append(f'<text x="265" y="{y+17}" text-anchor="end">{escape(str(label))}</text>')
        for j,(name,color,values) in enumerate(series):
            value=float(values[i]); by=y+j*30
            display=f'{value:.2f}%' if percentage else f'{value:,.0f}'
            parts.append(f'<rect x="280" y="{by}" width="{value/maximum*370}" height="21" rx="3" fill="{color}"><title>{escape(str(label))} · {escape(name)}: {display}</title></rect><text x="780" y="{by+17}" text-anchor="end">{display}</text>')
    parts.append('</svg><div class="legend">')
    parts.extend(f'<span><i style="background:{color}"></i>{escape(name)}</span>' for name,color,_ in series)
    return ''.join(parts)+'</div>'


def export_feedback_html(year, fetch_feedback_data, output_folder='reports', open_browser=True):
    base_year=year-1
    try:
        current=_feedback_metrics(fetch_feedback_data(year),year)
        baseline_df=fetch_feedback_data(base_year)
        if baseline_df is None:
            raise ValueError(f'Unable to retrieve baseline feedback for {base_year}.')
        base=None if baseline_df.empty else _feedback_metrics(baseline_df,base_year)
    except (ValueError,TypeError,KeyError,OverflowError) as error:
        return f'Feedback HTML report was not saved.\n{error}'
    specs=[('Total reviews','total','count'),('Average rating','average','rating'),('Positive reviews · 4–5','positive','count'),('Neutral reviews · 3','neutral','count'),('Negative reviews · 1–2','negative','count'),('Negative-review rate','negative_pct','percent')]
    cards=[]
    for title,key,kind in specs:
        v=current[key]
        display=f'{v:,.0f}' if kind=='count' else f'{v:.2f} / 5' if kind=='rating' else f'{v:.2f}%'
        change='N/A'
        if base:
            delta=v-base[key]
            change=f'{delta:+,.0f} reviews' if kind=='count' else f'{delta:+.2f} rating points' if kind=='rating' else f'{delta:+.2f} pp'
        cards.append(f'<article class="card"><p>{title}</p><strong>{display}</strong><small>{change} vs {base_year}</small></article>')
    def series(values,old_values=None):
        result=[(str(year),'#2563eb',list(values))]
        if old_values is not None:
            result.insert(0,(str(base_year),'#94a3b8',list(old_values)))
        return result
    rating_chart=_chart([f'{i} star' if i==1 else f'{i} stars' for i in range(1,6)],series(current['ratings'],base['ratings'] if base else None))
    sentiments=['Positive · 4–5','Neutral · 3','Negative · 1–2']
    rates=lambda m:[m[k]/m['total']*100 for k in ('positive','neutral','negative')]
    sentiment_chart=_chart(sentiments,series(rates(current),rates(base) if base else None),True)
    complaint_chart=_chart(list(current['complaints'].index),series(current['complaints'],base['complaints'] if base else None))
    regional_rows=[]
    for region,r in current['regions'].iterrows():
        old=None
        if base is not None and region in base['regions'].index:
            old=float(base['regions'].loc[region,'negative_pct'])
        old_text='N/A' if old is None else f'{old:.2f}%'
        delta='N/A' if old is None else f'{r["negative_pct"]-old:+.2f} pp'
        regional_rows.append(f'<tr><td>{escape(str(region))}</td><td>{int(r["reviews"]):,}</td><td>{r["average"]:.2f}</td><td>{int(r["negative"]):,}</td><td>{old_text}</td><td>{r["negative_pct"]:.2f}%</td><td>{delta}</td></tr>')
    highest=current['regions'].iloc[0]; highest_name=escape(str(current['regions'].index[0]))
    summary=f'<li>{current["positive_pct"]:.2f}% of reviews were positive, {current["neutral"]/current["total"]*100:.2f}% neutral, and {current["negative_pct"]:.2f}% negative.</li><li>{highest_name} had the highest observed negative-review rate ({highest["negative_pct"]:.2f}%; {int(highest["negative"])} of {int(highest["reviews"])} reviews). Consider review counts when comparing regions.</li>'
    if current['negative']:
        top=current['complaints'].idxmax()
        summary+=f'<li>Largest complaint category: {escape(top)} ({int(current["complaints"].max())} negative reviews).</li>'
    else:
        summary+='<li>No negative reviews were recorded for the selected period.</li>'
    comparison_label=f'Compared with {base_year}' if base else f'No data for {base_year}; year-over-year comparisons unavailable'
    html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Venesse feedback · {year}</title><style>{CSS}</style></head><body><main><header><div><div class="eyebrow">VENESSE / CUSTOMER FEEDBACK</div><h1>Customer feedback & satisfaction</h1><p class="muted">January–September {year}, based on order date · {comparison_label}</p><span class="badge">Ratings, sentiment, regions & complaints reconciled · {'Both years' if base else str(year)+' only'}</span></div><button onclick="window.print()">Print / Save as PDF</button></header><div class="cards">{''.join(cards)}</div><div class="grid"><section class="panel"><h2>Rating distribution</h2>{rating_chart}</section><section class="panel"><h2>Sentiment · share of reviews</h2>{sentiment_chart}</section></div><section class="panel compact-chart"><h2>Negative reviews by complaint category</h2>{complaint_chart}</section><section class="panel"><h2>Regional feedback · {year}</h2><div class="table-wrap"><table><thead><tr><th>Region</th><th>Reviews {year}</th><th>Average / 5</th><th>Negative {year}</th><th>Negative rate {base_year}</th><th>Negative rate {year}</th><th>Rate change</th></tr></thead><tbody>{''.join(regional_rows)}</tbody></table></div><p class="notes">Regions shown are those with reviews in {year}. N/A indicates no available baseline reviews for that region.</p></section><section class="panel"><h2>Business summary</h2><ul>{summary}</ul><p class="notes">These results describe submitted reviews and may not represent all customers. Sentiment is assigned from star ratings. Complaint categories use exact comment matching for negative reviews only: “slow delivery” → Delivery; “product arrived damaged” or “quality below expectation” → Product Quality / Handling; all other comments → General Dissatisfaction. The fallback category does not establish an underlying cause.</p></section><footer class="notes">Generated {datetime.now():%Y-%m-%d %H:%M:%S}. Feedback uses January–September order dates without a delivered-status restriction. Positive = 4–5 stars; neutral = 3; negative = 1–2. Yearly distributions use each year's own review population. pp = percentage points. Internal reconciliation does not independently audit source completeness or representativeness.</footer></main></body></html>'''
    try:
        folder=Path(output_folder); folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'venesse_feedback_dashboard_{year}_{datetime.now():%Y%m%d_%H%M%S_%f}.html'
        path.write_text(html,encoding='utf-8')
    except OSError as error:
        return f'Unable to save feedback HTML report: {error}'
    if open_browser:
        try: webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error: pass
    return f'Feedback HTML report saved successfully:\n{path.resolve()}'


CSS = '*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#172033;font:15px Arial,sans-serif}main{max-width:1360px;margin:auto;padding:36px 28px}header{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:28px}h1{font-size:32px;margin:10px 0}h2{font-size:18px;margin:0 0 20px}.eyebrow{color:#2563eb;font-size:12px;letter-spacing:2px;font-weight:bold}.muted,small{color:#64748b}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}.card,.panel{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:22px}.card p{color:#64748b;margin:0 0 12px}.card strong{font-size:27px;display:block}.card small{display:block;margin-top:12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}.panel{margin-bottom:20px}svg{width:100%;height:auto}.comparison-panel svg{display:block;max-width:760px;margin:0 auto}.comparison-panel .legend{flex-wrap:wrap}svg text{font:17px Arial;fill:#334155}.legend{display:flex;justify-content:center;gap:24px;color:#64748b;font-size:13px}.legend i{display:inline-block;width:10px;height:10px;margin-right:7px}table{width:100%;border-collapse:collapse;white-space:nowrap}td,th{text-align:right;padding:12px;border-bottom:1px solid #e2e8f0}td:first-child,th:first-child{text-align:left}th{color:#64748b;font-size:12px}.table-wrap{overflow-x:auto}.notes{font-size:13px;color:#64748b;line-height:1.8}li{line-height:1.9}button{border:0;background:#172033;color:white;padding:12px 18px;border-radius:8px;cursor:pointer}.badge{color:#166534;background:#dcfce7;padding:8px 12px;border-radius:20px;font-size:12px}@media(max-width:850px){.cards{grid-template-columns:1fr 1fr}.grid{display:block}header{display:block}button{margin-top:16px}}@media print{body{background:white}main{padding:0}button{display:none}.panel,.card{break-inside:avoid}.grid{display:block}@page{size:A4 landscape;margin:12mm}}.compact-chart svg{display:block;max-width:760px;margin:0 auto}.legend{flex-wrap:wrap}'
