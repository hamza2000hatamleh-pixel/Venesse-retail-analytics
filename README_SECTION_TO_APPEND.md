## Python Business Agent

The Python component extends this SQL, DAX, and Power BI project with a desktop interface for automated reporting and optional AI commentary.

- Seven business dashboards and one combined HTML report.
- Sales, customer purchasing, retention, product profitability, marketing, feedback, and provisional operating analysis.
- Natural-language request interpretation constrained to supported reports.
- Deterministic KPI calculations, local validation, and expandable AI source evidence.
- Token usage tracking and session commentary caching.
- 22 passing offline regression tests in the development environment.

The Python reports cover January–September. Feedback and delivered-sales filters differ; operating results remain provisional because campaign-cost overlap with expenses is unresolved. AI observations require source review.

[Python setup, screenshots, and limitations](Python/README.md)

```text
Generate full HTML report for 2026
Compare customer purchasing between 2025 and 2026
```

Launch `Python/venesse_desktop.py` using the configured Python environment and compatible Venesse SQL Server database. Database setup depends on the existing project’s schema; the Python folder does not create or seed it.
