USE Venesse;
GO

WITH MonthlySales AS (
    SELECT
        order_date_key / 100 AS year_month,
        SUM(net_revenue) AS revenue,
        SUM(cogs) AS cogs
    FROM dbo.FactSales
    WHERE order_date_key BETWEEN 20260101 AND 20260930
      AND status_id = 6 -- 6 refers to "delivered" orders only in DimOrderStatus
    GROUP BY order_date_key / 100
)
SELECT
    year_month,
    revenue,
    cogs,
    revenue - cogs AS gross_profit,
    ROUND(
        100.0 * (revenue - cogs) / NULLIF(revenue, 0),
        2
    ) AS gross_margin_pct
FROM MonthlySales
ORDER BY year_month;
WITH YearlySales AS (
    SELECT
        order_date_key / 10000 AS sales_year,
        SUM(net_revenue) AS revenue,
        SUM(cogs) AS cogs,
        SUM(net_revenue - cogs) AS gross_profit
    FROM dbo.FactSales
    WHERE status_id = 6
      AND (
          order_date_key BETWEEN 20250101 AND 20250930
          OR order_date_key BETWEEN 20260101 AND 20260930
      )
    GROUP BY order_date_key / 10000
)
SELECT
    sales_year,
    revenue,
    cogs,
    gross_profit,
    ROUND(
        100.0 * gross_profit / NULLIF(revenue, 0),
        2
    ) AS gross_margin_pct,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY sales_year))
        / NULLIF(LAG(revenue) OVER (ORDER BY sales_year), 0),
        2
    ) AS revenue_yoy_growth_pct
FROM YearlySales
ORDER BY sales_year;