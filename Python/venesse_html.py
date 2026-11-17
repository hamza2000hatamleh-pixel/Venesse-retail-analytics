"""Offline sales dashboard. Uses the agent's existing fetch_sales_data function."""
from datetime import datetime
from html import escape
from pathlib import Path
import math
import webbrowser


def _prepare(df, year):
    if df is None or df.empty:
        raise ValueError(f"No sales data available for {year}.")
    totals = {"revenue": 0.0, "cogs": 0.0}
    monthly = {month: {"revenue": 0.0, "cogs": 0.0} for month in range(1, 10)}
    for record in df.to_dict("records"):
        date = datetime.strptime(str(record["order_date_key"]), "%Y%m%d")
        if date.year != year or not 1 <= date.month <= 9:
            raise ValueError(f"Out-of-period sales date for {year}.")
        for source, target in (("net_revenue", "revenue"), ("cogs", "cogs")):
            amount = float(record[source])
            if not math.isfinite(amount):
                raise ValueError(f"Invalid {source} for {year}.")
            totals[target] += amount
            monthly[date.month][target] += amount
    totals["profit"] = totals["revenue"] - totals["cogs"]
    totals["margin"] = totals["profit"] / totals["revenue"] * 100 if totals["revenue"] else None
    for values in monthly.values():
        values["profit"] = values["revenue"] - values["cogs"]
        values["margin"] = values["profit"] / values["revenue"] * 100 if values["revenue"] else None
    for metric in ("revenue", "cogs", "profit"):
        if not math.isclose(sum(v[metric] for v in monthly.values()), totals[metric], rel_tol=0, abs_tol=0.01):
            raise ValueError(f"Monthly {metric} reconciliation failed for {year}.")
    return totals, monthly


def _money(value):
    return f"{'−' if value < 0 else ''}${abs(value):,.2f}"


def _pct(value):
    return "N/A" if value is None else f"{value:.2f}%"


def _growth(new, old):
    return "N/A" if old is None or new is None or old <= 0 else f"{(new - old) / old * 100:+.2f}%"


def _chart(series, percentage=False):
    width, height, left, right, top, bottom = 760, 300, 68, 18, 24, 44
    values = [v for _, _, data in series for v in data if v is not None]
    low, high = min([0] + values), max([0] + values)
    if high == low:
        high = low + 1
    span = high - low
    high += span * 0.10
    low -= span * 0.04 if low < 0 else 0
    plot_w, plot_h = width - left - right, height - top - bottom
    def point(index, value):
        return left + index * plot_w / 8, top + (high - value) / (high - low) * plot_h
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Monthly comparison chart">']
    for tick in range(5):
        value = low + (high - low) * tick / 4
        _, y = point(0, value)
        label = f"{value:.1f}%" if percentage else f"${value / 1000:,.0f}K"
        parts.append(f'<line x1="{left}" y1="{y}" x2="{width-right}" y2="{y}" stroke="#e5eaf1"/><text x="{left-10}" y="{y+4}" text-anchor="end">{label}</text>')
    for index in range(9):
        x, _ = point(index, 0)
        month = datetime(2000, index + 1, 1).strftime("%b")
        parts.append(f'<text x="{x}" y="{height-16}" text-anchor="middle">{month}</text>')
    for label, color, data in series:
        # Draw separate segments around undefined zero-revenue margins.
        segment = []
        for index, value in enumerate(list(data) + [None]):
            if value is None:
                if segment:
                    parts.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" stroke-width="3"/>')
                    segment = []
                continue
            x, y = point(index, value)
            segment.append(f"{x},{y}")
            formatted = _pct(value) if percentage else _money(value)
            parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"><title>{escape(label)} · {index+1}: {formatted}</title></circle>')
    parts.append('</svg><div class="legend">')
    parts.extend(f'<span><i style="background:{color}"></i>{escape(label)}</span>' for label, color, _ in series)
    parts.append('</div>')
    return "".join(parts)


def export_sales_html(year, fetch_sales_data, output_folder="reports", open_browser=True):
    """Fetch both years, validate dates/amounts, then save one self-contained HTML."""
    base_year = year - 1
    try:
        current, months = _prepare(fetch_sales_data(year), year)
        baseline_df = fetch_sales_data(base_year)
        if baseline_df is None:
            raise ValueError(f"Unable to retrieve baseline sales for {base_year}.")
        has_baseline = not baseline_df.empty
        if has_baseline:
            base, base_months = _prepare(baseline_df, base_year)
        else:
            base = dict(revenue=None, cogs=None, profit=None, margin=None)
            base_months = {m: dict(revenue=None, cogs=None, profit=None, margin=None) for m in range(1, 10)}
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return f"HTML report was not saved.\n{error}"

    comparison_label = f"Compared with {base_year}" if has_baseline else f"No data for {base_year}; year-over-year comparisons unavailable"
    validation_label = "Both years" if has_baseline else f"{year} only"
    cards = []
    for title, value, detail in (
        ("Revenue", _money(current["revenue"]), f'{_growth(current["revenue"], base["revenue"])} vs {base_year}'),
        ("Gross profit", _money(current["profit"]), f'{_growth(current["profit"], base["profit"])} vs {base_year}'),
        ("Gross margin", _pct(current["margin"]), "N/A" if current["margin"] is None or base["margin"] is None else f'{current["margin"]-base["margin"]:+.2f} pp vs {base_year}'),
        ("Cost of goods sold", _money(current["cogs"]), f'{_growth(current["cogs"], base["cogs"])} vs {base_year}')
    ):
        cards.append(f'<article class="card"><p>{title}</p><strong>{value}</strong><small>{detail}</small></article>')

    charts = []
    for metric, title in (("revenue", "Monthly revenue"), ("profit", "Monthly gross profit"), ("margin", "Monthly gross margin")):
        series = [(str(base_year), "#94a3b8", [v[metric] for v in base_months.values()]), (str(year), "#2563eb", [v[metric] for v in months.values()])]
        series = [item for item in series if any(v is not None for v in item[2])]
        charts.append(f'<section class="panel"><h2>{title}</h2>{_chart(series, metric == "margin")}</section>')

    rows = []
    for month, values in months.items():
        rows.append(f'<tr><td>{datetime(2000,month,1):%B}</td><td>{_money(values["revenue"])}</td><td>{_growth(values["revenue"],base_months[month]["revenue"])}</td><td>{_money(values["profit"])}</td><td>{_pct(values["margin"])}</td></tr>')
    rows.append(f'<tr class="total"><td>Total / weighted margin</td><td>{_money(current["revenue"])}</td><td>{_growth(current["revenue"],base["revenue"])}</td><td>{_money(current["profit"])}</td><td>{_pct(current["margin"])}</td></tr>')
    css = '''*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#172033;font:15px Arial,sans-serif}main{max-width:1240px;margin:auto;padding:36px 28px}header{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:28px}.eyebrow{color:#2563eb;font-size:12px;letter-spacing:2px;font-weight:bold}h1{font-size:32px;margin:10px 0}h2{font-size:18px;margin:0 0 20px}.muted,small{color:#64748b}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px}.card,.panel{background:white;border:1px solid #e2e8f0;border-radius:14px;padding:22px}.card p{margin:0 0 12px;color:#64748b}.card strong{font-size:27px;display:block}.card small{display:block;margin-top:12px}.charts{display:grid;grid-template-columns:1fr 1fr;gap:20px}.panel{margin-bottom:20px}.charts .panel:last-child{grid-column:1/-1}svg{width:100%;height:auto}svg text{font:12px Arial;fill:#64748b}.legend{display:flex;justify-content:center;gap:24px;color:#64748b;font-size:13px}.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{text-align:right;padding:13px;border-bottom:1px solid #e2e8f0}th:first-child,td:first-child{text-align:left}th{color:#64748b;font-size:12px}.total{font-weight:bold;background:#f8fafc}.badge{color:#166534;background:#dcfce7;padding:8px 12px;border-radius:20px;font-size:12px}button{border:0;background:#172033;color:white;padding:12px 18px;border-radius:8px;cursor:pointer}.notes{line-height:1.7;font-size:13px;color:#64748b}@media(max-width:800px){.cards{grid-template-columns:1fr 1fr}.charts{display:block}header{display:block}button{margin-top:16px}}@media print{body{background:white}main{padding:0}button{display:none}.panel,.card{break-inside:avoid}.cards{grid-template-columns:repeat(2,1fr)}.charts{display:block}.panel{border-radius:0}header{break-after:avoid}@page{size:A4 landscape;margin:12mm}}'''
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Venesse sales · {year}</title><style>{css}</style></head><body><main><header><div><div class="eyebrow">VENESSE / BUSINESS PERFORMANCE</div><h1>Sales performance overview</h1><p class="muted">January–September {year} · {comparison_label} · Delivered sales</p><span class="badge">Monthly reconciliation passed · {validation_label}</span></div><button onclick="window.print()">Print / Save as PDF</button></header><div class="cards">{"".join(cards)}</div><div class="charts">{"".join(charts)}</div><section class="panel"><h2>Monthly performance · {year}</h2><div class="table-wrap"><table><thead><tr><th>Month</th><th>Revenue</th><th>Revenue YoY</th><th>Gross profit</th><th>Gross margin</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section><footer class="notes">Generated {datetime.now():%Y-%m-%d %H:%M:%S}. Source: the agent's SQL sales query.<br>Gross margin = gross profit / revenue. Total margin is weighted by revenue. pp = percentage points. N/A indicates unavailable baseline data, zero revenue, or a non-positive growth baseline. Months without sales rows show zero recorded amounts; source completeness is not established by reconciliation.<br>Internal checks reconcile monthly revenue, COGS, and gross profit to each available year's totals. They do not independently audit the source data.</footer></main></body></html>'''
    try:
        folder = Path(output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"venesse_sales_dashboard_{year}_{datetime.now():%Y%m%d_%H%M%S_%f}.html"
        path.write_text(html, encoding="utf-8")
    except OSError as error:
        return f"Unable to save HTML report: {error}"
    if open_browser:
        try:
            webbrowser.open(path.resolve().as_uri())
        except webbrowser.Error:
            pass
    return f"Sales HTML report saved successfully:\n{path.resolve()}"
