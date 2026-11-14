
USE Venesse;
GO

/*
VENESSE RETAIL ANALYTICS
04 - PRODUCT PERFORMANCE & PROFITABILITY

Period: January - September 2026
Comparison: January - September 2025
Delivered orders: status_id = 6

Note: Verify dimension column names before execution.
*/

------------------------------------------------------------
-- 1. PRODUCT PROFITABILITY
------------------------------------------------------------

WITH ProductSales AS (
    SELECT
        fs.product_id,
        SUM(fs.quantity) AS units_sold,
        SUM(fs.net_revenue) AS revenue,
        SUM(fs.cogs) AS cogs,
        SUM(fs.net_revenue - fs.cogs) AS gross_profit
    FROM dbo.FactSales fs
    WHERE fs.status_id = 6
      AND fs.order_date_key BETWEEN 20260101 AND 20260930
    GROUP BY fs.product_id
)
SELECT
    p.product_name,
    ps.units_sold,
    ROUND(ps.revenue, 2) AS revenue,
    ROUND(ps.cogs, 2) AS cogs,
    ROUND(ps.gross_profit, 2) AS gross_profit,
    ROUND(
        100.0 * ps.gross_profit /
        NULLIF(ps.revenue, 0), 2
    ) AS gross_margin_pct,
    ROUND(
        100.0 * ps.gross_profit /
        NULLIF(SUM(ps.gross_profit) OVER (), 0), 2
    ) AS gross_profit_contribution_pct
FROM ProductSales ps
JOIN dbo.DimProduct p
    ON ps.product_id = p.product_id
ORDER BY ps.gross_profit DESC;

------------------------------------------------------------
-- 2. CATEGORY PROFITABILITY
------------------------------------------------------------

WITH CategorySales AS (
    SELECT
        p.category_name,
        SUM(fs.net_revenue) AS revenue,
        SUM(fs.cogs) AS cogs,
        SUM(fs.net_revenue - fs.cogs) AS gross_profit
    FROM dbo.FactSales fs
    JOIN dbo.DimProduct p
        ON fs.product_id = p.product_id
    WHERE fs.status_id = 6
      AND fs.order_date_key BETWEEN 20260101 AND 20260930
    GROUP BY p.category_name
)
SELECT
    category_name,
    ROUND(revenue, 2) AS revenue,
    ROUND(cogs, 2) AS cogs,
    ROUND(gross_profit, 2) AS gross_profit,
    ROUND(
        100.0 * gross_profit /
        NULLIF(revenue, 0), 2
    ) AS gross_margin_pct,
    DENSE_RANK() OVER (
        ORDER BY gross_profit DESC
    ) AS profitability_rank
FROM CategorySales
ORDER BY profitability_rank;

------------------------------------------------------------
-- 3. REGIONAL CATEGORY PERFORMANCE
------------------------------------------------------------

WITH RegionalSales AS (
    SELECT
        c.region,
        p.category_name,
        SUM(fs.net_revenue) AS revenue,
        SUM(fs.cogs) AS cogs,
        SUM(fs.net_revenue - fs.cogs) AS gross_profit
    FROM dbo.FactSales fs
    JOIN dbo.DimCustomer c
        ON fs.customer_id = c.customer_id
    JOIN dbo.DimProduct p
        ON fs.product_id = p.product_id
    WHERE fs.status_id = 6
      AND fs.order_date_key BETWEEN 20260101 AND 20260930
    GROUP BY
        c.region,
        p.category_name
)
SELECT
    region,
    category_name,
    ROUND(revenue, 2) AS revenue,
    ROUND(gross_profit, 2) AS gross_profit,
    ROUND(
        100.0 * gross_profit /
        NULLIF(revenue, 0), 2
    ) AS gross_margin_pct,
    DENSE_RANK() OVER (
        PARTITION BY region
        ORDER BY gross_profit DESC
    ) AS regional_profit_rank
FROM RegionalSales
ORDER BY region, regional_profit_rank;

------------------------------------------------------------
-- 4. YEAR-OVER-YEAR PRODUCT GROSS PROFIT
------------------------------------------------------------

WITH ProductYearlyProfit AS (
    SELECT
        fs.product_id,
        fs.order_date_key / 10000 AS sales_year,
        SUM(fs.net_revenue - fs.cogs) AS gross_profit
    FROM dbo.FactSales fs
    WHERE fs.status_id = 6
      AND (
          fs.order_date_key BETWEEN 20250101 AND 20250930
          OR fs.order_date_key BETWEEN 20260101 AND 20260930
      )
    GROUP BY
        fs.product_id,
        fs.order_date_key / 10000
),
ProductComparison AS (
    SELECT
        product_id,
        SUM(CASE WHEN sales_year = 2025
            THEN gross_profit ELSE 0 END) AS py_profit,
        SUM(CASE WHEN sales_year = 2026
            THEN gross_profit ELSE 0 END) AS cy_profit
    FROM ProductYearlyProfit
    GROUP BY product_id
)
SELECT
    p.product_name,
    ROUND(pc.py_profit, 2) AS py_gross_profit,
    ROUND(pc.cy_profit, 2) AS cy_gross_profit,
    ROUND(pc.cy_profit - pc.py_profit, 2)
        AS gross_profit_change,
    ROUND(
        100.0 * (pc.cy_profit - pc.py_profit) /
        NULLIF(pc.py_profit, 0), 2
    ) AS gross_profit_yoy_pct
FROM ProductComparison pc
JOIN dbo.DimProduct p
    ON pc.product_id = p.product_id
ORDER BY gross_profit_change DESC;

------------------------------------------------------------
-- 5. TOP 10 PRODUCTS BY GROSS PROFIT
------------------------------------------------------------

WITH ProductProfit AS (
    SELECT
        fs.product_id,
        SUM(fs.net_revenue) AS revenue,
        SUM(fs.net_revenue - fs.cogs) AS gross_profit
    FROM dbo.FactSales fs
    WHERE fs.status_id = 6
      AND fs.order_date_key BETWEEN 20260101 AND 20260930
    GROUP BY fs.product_id
),
RankedProducts AS (
    SELECT
        p.product_name,
        pp.revenue,
        pp.gross_profit,
        ROW_NUMBER() OVER (
            ORDER BY pp.gross_profit DESC, pp.product_id
        ) AS product_rank
    FROM ProductProfit pp
    JOIN dbo.DimProduct p
        ON pp.product_id = p.product_id
)
SELECT
    product_rank,
    product_name,
    ROUND(revenue, 2) AS revenue,
    ROUND(gross_profit, 2) AS gross_profit
FROM RankedProducts
WHERE product_rank <= 10
ORDER BY product_rank;
