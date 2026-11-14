
USE Venesse;
GO

/*
VENESSE RETAIL ANALYTICS
06 - OPERATING EXPENSES & PROFITABILITY

Reporting periods:
January - September 2025
January - September 2026

Revenue: Delivered orders only (status_id = 6)

Accounting assumptions:
- Campaign costs are attributed to their start month.
- Campaign costs are treated as additional to operating expenses.
- Potential overlap with marketing operating expenses
  has not been independently ruled out.
- "Operating profit" is a project-defined management metric,
  not audited accounting net income.

Verify Expenses and MarketingCampaigns column names.
*/

------------------------------------------------------------
-- 1. OPERATING EXPENSES BY CATEGORY
------------------------------------------------------------

WITH ExpenseSummary AS (
    SELECT
        YEAR(e.expense_date) AS expense_year,
        ec.expense_category_name,
        SUM(e.expense_amount) AS total_expenses
    FROM dbo.Expenses e
    INNER JOIN dbo.ExpenseCategories ec
        ON e.expense_category_id = ec.expense_category_id
    WHERE (
        e.expense_date >= '2025-01-01'
        AND e.expense_date < '2025-10-01'
    )
    OR (
        e.expense_date >= '2026-01-01'
        AND e.expense_date < '2026-10-01'
    )
    GROUP BY
        YEAR(e.expense_date),
        ec.expense_category_name
)
SELECT
    expense_year,
    expense_category_name,
    ROUND(total_expenses, 2) AS total_expenses,
    ROUND(
        100.0 * total_expenses
        / NULLIF(
            SUM(total_expenses) OVER (
                PARTITION BY expense_year
            ), 0
        ),
        2
    ) AS expense_contribution_pct
FROM ExpenseSummary
ORDER BY expense_year, total_expenses DESC;

------------------------------------------------------------
-- 2. MONTHLY OPERATING EXPENSES
------------------------------------------------------------

SELECT
    YEAR(expense_date) AS expense_year,
    MONTH(expense_date) AS expense_month,
    ROUND(SUM(expense_amount), 2) AS operating_expenses
FROM dbo.Expenses
WHERE (
    expense_date >= '2025-01-01'
    AND expense_date < '2025-10-01'
)
OR (
    expense_date >= '2026-01-01'
    AND expense_date < '2026-10-01'
)
GROUP BY
    YEAR(expense_date),
    MONTH(expense_date)
ORDER BY expense_year, expense_month;

------------------------------------------------------------
-- 3. YEARLY FINANCIAL PERFORMANCE
------------------------------------------------------------

WITH Sales AS (
    SELECT
        order_date_key / 10000 AS sales_year,
        SUM(net_revenue) AS revenue,
        SUM(cogs) AS cogs
    FROM dbo.FactSales
    WHERE status_id = 6
      AND (
          order_date_key BETWEEN 20250101 AND 20250930
          OR order_date_key BETWEEN 20260101 AND 20260930
      )
    GROUP BY order_date_key / 10000
),
OperatingExpenses AS (
    SELECT
        YEAR(expense_date) AS expense_year,
        SUM(expense_amount) AS operating_expenses
    FROM dbo.Expenses
    WHERE (
        expense_date >= '2025-01-01'
        AND expense_date < '2025-10-01'
    )
    OR (
        expense_date >= '2026-01-01'
        AND expense_date < '2026-10-01'
    )
    GROUP BY YEAR(expense_date)
),
CampaignCosts AS (
    SELECT
        YEAR(campaign_start_date) AS campaign_year,
        SUM(campaign_cost) AS campaign_costs
    FROM dbo.MarketingCampaigns
    WHERE (
        campaign_start_date >= '2025-01-01'
        AND campaign_start_date < '2025-10-01'
    )
    OR (
        campaign_start_date >= '2026-01-01'
        AND campaign_start_date < '2026-10-01'
    )
    GROUP BY YEAR(campaign_start_date)
),
Financials AS (
    SELECT
        s.sales_year,
        s.revenue,
        s.cogs,
        s.revenue - s.cogs AS gross_profit,
        COALESCE(e.operating_expenses, 0)
            AS operating_expenses,
        COALESCE(c.campaign_costs, 0)
            AS campaign_costs
    FROM Sales s
    LEFT JOIN OperatingExpenses e
        ON s.sales_year = e.expense_year
    LEFT JOIN CampaignCosts c
        ON s.sales_year = c.campaign_year
)
SELECT
    sales_year,
    ROUND(revenue, 2) AS revenue,
    ROUND(cogs, 2) AS cogs,
    ROUND(gross_profit, 2) AS gross_profit,
    ROUND(operating_expenses, 2)
        AS operating_expenses,
    ROUND(campaign_costs, 2) AS campaign_costs,
    ROUND(
        gross_profit - operating_expenses - campaign_costs,
        2
    ) AS operating_profit,
    ROUND(
        100.0 * (
            gross_profit - operating_expenses - campaign_costs
        ) / NULLIF(revenue, 0),
        2
    ) AS operating_margin_pct
FROM Financials
ORDER BY sales_year;

------------------------------------------------------------
-- 4. MONTHLY OPERATING PROFIT
------------------------------------------------------------

WITH MonthlySales AS (
    SELECT
        order_date_key / 10000 AS sales_year,
        (order_date_key / 100) % 100 AS sales_month,
        SUM(net_revenue) AS revenue,
        SUM(net_revenue - cogs) AS gross_profit
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260101 AND 20260930
    GROUP BY
        order_date_key / 10000,
        (order_date_key / 100) % 100
),
MonthlyExpenses AS (
    SELECT
        YEAR(expense_date) AS expense_year,
        MONTH(expense_date) AS expense_month,
        SUM(expense_amount) AS operating_expenses
    FROM dbo.Expenses
    WHERE expense_date >= '2026-01-01'
      AND expense_date < '2026-10-01'
    GROUP BY YEAR(expense_date), MONTH(expense_date)
),
MonthlyCampaignCosts AS (
    SELECT
        YEAR(campaign_start_date) AS campaign_year,
        MONTH(campaign_start_date) AS campaign_month,
        SUM(campaign_cost) AS campaign_costs
    FROM dbo.MarketingCampaigns
    WHERE campaign_start_date >= '2026-01-01'
      AND campaign_start_date < '2026-10-01'
    GROUP BY YEAR(campaign_start_date), MONTH(campaign_start_date)
)
SELECT
    s.sales_year,
    s.sales_month,
    ROUND(s.revenue, 2) AS revenue,
    ROUND(s.gross_profit, 2) AS gross_profit,
    ROUND(COALESCE(e.operating_expenses, 0), 2)
        AS operating_expenses,
    ROUND(COALESCE(c.campaign_costs, 0), 2)
        AS campaign_costs,
    ROUND(
        s.gross_profit
        - COALESCE(e.operating_expenses, 0)
        - COALESCE(c.campaign_costs, 0),
        2
    ) AS operating_profit
FROM MonthlySales s
LEFT JOIN MonthlyExpenses e
    ON s.sales_year = e.expense_year
   AND s.sales_month = e.expense_month
LEFT JOIN MonthlyCampaignCosts c
    ON s.sales_year = c.campaign_year
   AND s.sales_month = c.campaign_month
ORDER BY s.sales_year, s.sales_month;

------------------------------------------------------------
-- 5. YEAR-OVER-YEAR FINANCIAL IMPROVEMENT
------------------------------------------------------------

WITH Sales AS (
    SELECT
        order_date_key / 10000 AS sales_year,
        SUM(net_revenue) AS revenue,
        SUM(net_revenue - cogs) AS gross_profit
    FROM dbo.FactSales
    WHERE status_id = 6
      AND (
          order_date_key BETWEEN 20250101 AND 20250930
          OR order_date_key BETWEEN 20260101 AND 20260930
      )
    GROUP BY order_date_key / 10000
),
Expenses AS (
    SELECT
        YEAR(expense_date) AS expense_year,
        SUM(expense_amount) AS total_expenses
    FROM dbo.Expenses
    WHERE (
        expense_date >= '2025-01-01'
        AND expense_date < '2025-10-01'
    )
    OR (
        expense_date >= '2026-01-01'
        AND expense_date < '2026-10-01'
    )
    GROUP BY YEAR(expense_date)
),
Campaigns AS (
    SELECT
        YEAR(campaign_start_date) AS campaign_year,
        SUM(campaign_cost) AS campaign_costs
    FROM dbo.MarketingCampaigns
    WHERE (
        campaign_start_date >= '2025-01-01'
        AND campaign_start_date < '2025-10-01'
    )
    OR (
        campaign_start_date >= '2026-01-01'
        AND campaign_start_date < '2026-10-01'
    )
    GROUP BY YEAR(campaign_start_date)
),
YearlyProfit AS (
    SELECT
        s.sales_year,
        s.revenue,
        s.gross_profit
          - COALESCE(e.total_expenses, 0)
          - COALESCE(c.campaign_costs, 0)
          AS operating_profit
    FROM Sales s
    LEFT JOIN Expenses e
        ON s.sales_year = e.expense_year
    LEFT JOIN Campaigns c
        ON s.sales_year = c.campaign_year
),
ProfitComparison AS (
    SELECT
        sales_year,
        revenue,
        operating_profit,
        100.0 * operating_profit
            / NULLIF(revenue, 0) AS operating_margin_pct,
        LAG(operating_profit) OVER (
            ORDER BY sales_year
        ) AS previous_year_profit,
        LAG(
            100.0 * operating_profit
            / NULLIF(revenue, 0)
        ) OVER (
            ORDER BY sales_year
        ) AS previous_year_margin_pct
    FROM YearlyProfit
)
SELECT
    sales_year,
    ROUND(operating_profit, 2) AS operating_profit,
    ROUND(operating_margin_pct, 2)
        AS operating_margin_pct,
    ROUND(
        operating_profit - previous_year_profit, 2
    ) AS operating_profit_yoy_change,
    ROUND(
        operating_margin_pct - previous_year_margin_pct,
        2
    ) AS operating_margin_yoy_change_pp
FROM ProfitComparison
ORDER BY sales_year;
