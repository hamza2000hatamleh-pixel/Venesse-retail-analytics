# Venesse | Retail Sales & Customer Analytics

### End-to-End Business Intelligence, Data Analytics & AI Reporting Portfolio Project

**Technologies:** SQL Server | T-SQL | Power BI | DAX | Python | Pandas | Tkinter | AI Agent

## Project Overview

Venesse is an end-to-end retail analytics portfolio project that transforms transactional business data into validated reports and business insights.

The project combines data cleaning, relational database modeling, SQL analysis, Power BI dashboards, and a Python business reporting agent. It covers sales performance, customer purchasing and retention, marketing performance, product profitability, customer feedback, and financial performance.

The Python agent adds a desktop interface for requesting reports in natural language, generating HTML dashboards, and reviewing optional AI commentary alongside calculated KPIs and supporting evidence.

## Project Workflow

1. **Data Preparation:** Clean and validate transactional data using SQL Server.
2. **Data Modeling:** Build relational tables and analytical views.
3. **Business Analysis:** Develop SQL queries to investigate business performance.
4. **Power BI:** Create analytical dashboards using DAX measures and interactive visualizations.
5. **Python Reporting:** Retrieve SQL Server data, calculate business metrics with Pandas, validate results, and export TXT and HTML reports.
6. **AI Agent:** Interpret natural-language requests, route them to supported report functions, and generate commentary from selected report evidence.
7. **Desktop Interface:** Provide dashboard shortcuts, custom request entry, progress messages, token usage, and access to saved reports.
8. **Validation:** Reconcile financial metrics and business KPIs and run offline regression checks.

## Key Business Questions

- How is revenue performing compared with the previous year?
- Which customers contribute the most revenue?
- How effectively are customers being retained?
- Which marketing campaigns have the highest attributed profitability and ROAS?
- Which products and categories contribute most to profitability?
- What do submitted customer reviews indicate about customer experience?
- How do operating expenses affect business profitability?

## Dashboard Analysis

### Sales Performance

Revenue trends, historical COGS, gross profit, profit margins, year-over-year comparisons, and leading products.

### Customer Analytics

Customer segmentation, repeat purchasing, top customer contributions, and revenue concentration.

### Customer Retention

Previous-year customer cohort retention, non-returning customers, and historical baseline revenue at risk. Retention is distinct from repeat purchasing within a single reporting period.

### Marketing Campaign Performance

Campaign-attributed revenue, marketing spending, ROAS, conversion rates, and profitability. Attributed results do not establish incremental marketing impact.

### Product Performance & Profitability

Product and category profitability, regional comparisons, and changes in selling prices and costs.

### Customer Feedback & Satisfaction

Customer ratings, rating-based sentiment, regional satisfaction, and complaint classification. Submitted reviews may not represent all customers.

### Operating Expenses & Profitability

Operating expenses, campaign costs, provisional operating profit and margin, and year-over-year financial performance.

## Python Business Agent

The agent extends the SQL and Power BI analysis with an automated reporting workflow and a local Windows desktop interface.

### Reporting and Desktop Features

- Seven individual HTML dashboards and one combined business report.
- TXT reports and supported year-over-year comparisons.
- Eight dashboard shortcuts: Full Dashboard, Sales, Customers, Retention, Products, Marketing, Feedback, and Operating.
- A year selector and a custom business-request field.
- Background report generation, progress messages, and an **Open last report** button.
- HTML exports with browser **Print / Save as PDF** support.

### AI Features

- Natural-language interpretation using NanoGPT with the configured `qwen3-30b-a3b-instruct-2507` model.
- Local validation of supported actions, year counts, and export preferences before dispatch.
- Deterministic report functions calculate financial and business metrics; model output does not execute arbitrary SQL or Python.
- Optional AI observations for TXT and HTML reports, with expandable source evidence in HTML.
- Calculated KPI highlights displayed separately from generated observations.
- Local checks for evidence references, numeric consistency, unsupported wording, and repeated highlights. Standalone table rows are rejected as narrative evidence.
- Keyword fallback when AI interpretation is unavailable. Calculated reports and highlights can still run without an API key.

AI observations require review. These checks reduce errors but do not prove that every narrative claim is supported.

### Token Usage and Commentary Cache

- Compact evidence selection reduces the source text sent for HTML commentary.
- Console and desktop output show reported input/output tokens, API attempts, and commentary cache hits per request.
- Usage metadata is saved to `reports/ai_usage.jsonl` without prompts or API keys.
- Successful commentary can be reused within the current application session when evidence and AI settings match.
- Changed displayed evidence invalidates reuse; generation timestamps alone do not. Restarting clears the cache.
- Reports still retrieve data on a commentary cache hit, and request interpretation may still use API tokens.

Dollar estimates are optional and require model-specific prices supplied by the user. They are not provider billing records or an enforced spending limit.

### Example Requests

```text
Generate full HTML report for 2026
Generate sales HTML report for 2026
Generate feedback HTML report for 2023
Generate operating HTML report for 2026
Compare customer purchasing between 2025 and 2026
Export customer comparison for 2025 and 2026
```

### Python Setup

See [Python setup, screenshots, and documentation](Python/README.md).

The agent requires a compatible Venesse SQL Server database, Windows authentication, an ODBC driver, and the Python dependencies in `Python/requirements.txt`. The Python folder does not create or seed the database. AI features also require private provider credentials in the local environment or PyCharm run configuration.

Launch `Python/venesse_desktop.py` using the configured Python environment. Keep API keys, generated reports, usage logs, and private run configurations out of version control.

### Regression Testing

The Python component passed **22 offline regression tests** in the development environment. Coverage includes core sales calculations, invalid values and dates, command validation and dispatch, TXT/HTML exports, AI failure behavior, cache invalidation, feedback evidence handling, KPI highlights, and token tracking.

The tests use sample data and block database/network access. They do not independently validate every business calculation or replace live database/API testing and visual report review.

## Selected Business Findings

**January–September 2026**

| KPI | Result |
|---|---:|
| Revenue | $938,352.11 |
| Gross Profit | $229,097.40 |
| Operating Expenses | $272,445.27 |
| Campaign Costs | $16,076.30 |
| Operating Profit — provisional | -$59,424.17 |
| Operating Margin — provisional | -6.33% |

Compared with January–September 2025, revenue increased, and the provisional operating loss decreased by approximately 49%.

Despite improving financial performance, the business remained unprofitable under the current operating-cost model during the analyzed period.

*Financial note: Campaign costs are treated as additional to operating expenses in the current model. Potential overlap with marketing expense categories has not been independently ruled out, so operating profit and margin remain provisional.*

## Business Recommendations

These are areas for further investigation rather than established causal conclusions:

- Investigate opportunities to improve gross margins on high-performing products.
- Evaluate marketing campaigns using attributed profitability alongside revenue and spending.
- Investigate retention strategies using purchasing behavior and historical revenue-at-risk analysis.
- Introduce structured customer feedback collection to investigate causes of dissatisfaction.
- Review major operating expense categories and resolve campaign-cost overlap before relying on final operating-profit conclusions.

## Reporting Scope and Limitations

- Python reports cover **January–September** for each selected year.
- Sales-based reporting uses delivered orders with `status_id = 6`. Feedback uses order dates without that delivered-status filter.
- Missing baseline data is not treated as zero. Commentary omits unavailable prior-year comparisons; source dashboard cells can still display N/A.
- Revenue at risk represents historical baseline revenue, not forecast lost sales.
- AI commentary uses selected displayed evidence rather than a complete database review. Expand source evidence and check the original figures.
- Combined HTML reports can mark unavailable sections explicitly. Within-export data reuse is not a database transaction snapshot.
- Internal reconciliation checks consistency within retrieved data; it does not independently audit source completeness or representativeness.

## Repository Contents

- **Power BI project:** Report definitions, semantic model, and DAX measures.
- **SQL scripts:** Data preparation, modeling, validation, and business analysis.
- **[Python agent](Python/README.md):** Desktop launcher, SQL-connected reporting, HTML dashboards, AI interpretation and commentary, usage tracking, and regression tests.
- **Dashboard screenshots:** Visual portfolio previews, including commentary and source-evidence examples in the Python documentation.

## About the Author

**Hamza Menawer Moh'd Hatamleh**

Mechanical Engineering graduate transitioning into Data Analytics and Business Intelligence, with practical experience in SQL Server, Power BI, DAX, Excel, and Python. This project demonstrates an integrated workflow from database analysis and BI visualization to Python reporting and evidence-linked AI commentary.

[LinkedIn](https://www.linkedin.com/in/hamza-hatamleh-37219244a/)
