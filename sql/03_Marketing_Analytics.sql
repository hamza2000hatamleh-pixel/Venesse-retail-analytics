
USE Venesse;
GO

/*
VENESSE RETAIL ANALYTICS
03 - MARKETING CAMPAIGN ANALYSIS

Analysis period: January - September 2026
Revenue recognition: Delivered orders (status_id = 6)
Campaign attribution: Orders linked by campaign_id

Note:
Campaign costs are attributed to the campaign start period.
ROAS = Revenue / Marketing Cost
Marketing ROI = (Gross Profit - Marketing Cost) / Marketing Cost
*/

------------------------------------------------------------
-- 1. CAMPAIGN PERFORMANCE
------------------------------------------------------------

WITH CampaignSales AS (
    SELECT
        campaign_id,
        COUNT(DISTINCT order_id) AS delivered_orders,
        SUM(net_revenue) AS revenue,
        SUM(cogs) AS cogs,
        SUM(net_revenue - cogs) AS gross_profit
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260101 AND 20260930
      AND campaign_id IS NOT NULL
    GROUP BY campaign_id
),
CampaignPerformance AS (
    SELECT
        mc.campaign_id,
        mc.campaign_name,
        mc.campaign_cost AS marketing_cost,
        mc.num_of_clicks,
        COALESCE(cs.delivered_orders, 0) AS delivered_orders,
        COALESCE(cs.revenue, 0) AS revenue,
        COALESCE(cs.cogs, 0) AS cogs,
        COALESCE(cs.gross_profit, 0) AS gross_profit
    FROM dbo.MarketingCampaigns mc
    LEFT JOIN CampaignSales cs
        ON mc.campaign_id = cs.campaign_id
    WHERE mc.campaign_start_date >= '2026-01-01'
      AND mc.campaign_start_date < '2026-10-01'
)
SELECT
    campaign_id,
    campaign_name,
    marketing_cost,
    num_of_clicks,
    delivered_orders,
    ROUND(revenue, 2) AS revenue,
    ROUND(cogs, 2) AS cogs,
    ROUND(gross_profit, 2) AS gross_profit,

    ROUND(
        100.0 * delivered_orders / NULLIF(num_of_clicks, 0),
        2
    ) AS conversion_rate_pct,

    ROUND(
        revenue / NULLIF(marketing_cost, 0),
        2
    ) AS roas,

    ROUND(
        gross_profit - marketing_cost,
        2
    ) AS profit_after_marketing,

    ROUND(
        100.0 * (gross_profit - marketing_cost)
        / NULLIF(marketing_cost, 0),
        2
    ) AS marketing_roi_pct

FROM CampaignPerformance
ORDER BY profit_after_marketing DESC;

------------------------------------------------------------
-- 2. CAMPAIGN PERFORMANCE SUMMARY
------------------------------------------------------------

WITH CampaignSales AS (
    SELECT
        campaign_id,
        COUNT(DISTINCT order_id) AS delivered_orders,
        SUM(net_revenue) AS revenue,
        SUM(cogs) AS cogs
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260101 AND 20260930
      AND campaign_id IS NOT NULL
    GROUP BY campaign_id
),
EligibleCampaigns AS (
    SELECT
        mc.campaign_id,
        mc.campaign_cost,
        mc.num_of_clicks,
        COALESCE(cs.delivered_orders, 0) AS delivered_orders,
        COALESCE(cs.revenue, 0) AS revenue,
        COALESCE(cs.cogs, 0) AS cogs
    FROM dbo.MarketingCampaigns mc
    LEFT JOIN CampaignSales cs
        ON mc.campaign_id = cs.campaign_id
    WHERE mc.campaign_start_date >= '2026-01-01'
      AND mc.campaign_start_date < '2026-10-01'
)
SELECT
    COUNT(*) AS total_campaigns,
    SUM(num_of_clicks) AS total_clicks,
    SUM(delivered_orders) AS delivered_orders,
    ROUND(SUM(campaign_cost), 2) AS marketing_spending,
    ROUND(SUM(revenue), 2) AS revenue,
    ROUND(SUM(revenue - cogs), 2) AS gross_profit,

    ROUND(
        100.0 * SUM(delivered_orders)
        / NULLIF(SUM(num_of_clicks), 0), 2
    ) AS conversion_rate_pct,

    ROUND(
        SUM(revenue) / NULLIF(SUM(campaign_cost), 0), 2
    ) AS roas,

    ROUND(
        SUM(revenue - cogs - campaign_cost), 2
    ) AS profit_after_marketing,

    ROUND(
        100.0 * SUM(revenue - cogs - campaign_cost)
        / NULLIF(SUM(campaign_cost), 0), 2
    ) AS marketing_roi_pct

FROM EligibleCampaigns;

------------------------------------------------------------
-- 3. TOP 3 PRODUCTS BY CAMPAIGN REVENUE
------------------------------------------------------------

WITH ProductCampaignSales AS (
    SELECT
        fs.campaign_id,
        fs.product_id,
        SUM(fs.net_revenue) AS revenue,
        SUM(fs.net_revenue - fs.cogs) AS gross_profit
    FROM dbo.FactSales fs
    WHERE fs.status_id = 6
      AND fs.order_date_key BETWEEN 20260101 AND 20260930
      AND fs.campaign_id IS NOT NULL
    GROUP BY
        fs.campaign_id,
        fs.product_id
),
RankedProducts AS (
    SELECT
        pcs.campaign_id,
        mc.campaign_name,
        pcs.product_id,
        p.product_name,
        pcs.revenue,
        pcs.gross_profit,
        ROW_NUMBER() OVER (
            PARTITION BY pcs.campaign_id
            ORDER BY pcs.revenue DESC, pcs.product_id
        ) AS product_rank
    FROM ProductCampaignSales pcs
    INNER JOIN dbo.MarketingCampaigns mc
        ON pcs.campaign_id = mc.campaign_id
    INNER JOIN dbo.Products p
        ON pcs.product_id = p.product_id
    WHERE mc.campaign_start_date >= '2026-01-01'
      AND mc.campaign_start_date < '2026-10-01'
)
SELECT
    campaign_id,
    campaign_name,
    product_rank,
    product_name,
    ROUND(revenue, 2) AS revenue,
    ROUND(gross_profit, 2) AS gross_profit
FROM RankedProducts
WHERE product_rank <= 3
ORDER BY campaign_id, product_rank;

------------------------------------------------------------
-- 4. CAMPAIGN PROFITABILITY RANKING
------------------------------------------------------------

WITH CampaignProfit AS (
    SELECT
        mc.campaign_id,
        mc.campaign_name,
        mc.campaign_cost AS marketing_cost,
        COALESCE(SUM(
            CASE
                WHEN fs.status_id = 6
                 AND fs.order_date_key BETWEEN 20260101 AND 20260930
                THEN fs.net_revenue - fs.cogs
                ELSE 0
            END
        ), 0) AS gross_profit
    FROM dbo.MarketingCampaigns mc
    LEFT JOIN dbo.FactSales fs
        ON mc.campaign_id = fs.campaign_id
    WHERE mc.campaign_start_date >= '2026-01-01'
      AND mc.campaign_start_date < '2026-10-01'
    GROUP BY
        mc.campaign_id,
        mc.campaign_name,
        mc.campaign_cost
)
SELECT
    campaign_id,
    campaign_name,
    ROUND(marketing_cost, 2) AS marketing_cost,
    ROUND(gross_profit, 2) AS gross_profit,
    ROUND(gross_profit - marketing_cost, 2)
        AS profit_after_marketing,
    DENSE_RANK() OVER (
        ORDER BY gross_profit - marketing_cost DESC
    ) AS profitability_rank
FROM CampaignProfit
ORDER BY profitability_rank;
