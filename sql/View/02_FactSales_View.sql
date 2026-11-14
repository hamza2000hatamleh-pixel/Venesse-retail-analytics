USE [Venesse]
GO

/****** Object:  View [dbo].[FactSales]    Script Date: 11/14/2026 6:40:07 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[FactSales]
AS
WITH BaseSales AS (
    SELECT
        o.order_id,
        o.customer_id,
        oi.product_id,
        o.campaign_id,

        CAST(CONVERT(CHAR(8), o.order_date, 112) AS INT)
            AS order_date_key,

        CAST(CONVERT(CHAR(8), o.ship_date, 112) AS INT)
            AS ship_date_key,

        o.status_id,

        CASE
            WHEN o.payment_method = 'cash' THEN 1
            WHEN o.payment_method = 'credit card' THEN 2
            WHEN o.payment_method = 'PayPal' THEN 3
        END AS payment_method_key,

        oi.quantity,
        oi.unit_price,
        oi.unit_cost,
        oi.item_discount,
        o.order_discount,

        CAST(
            oi.quantity * oi.unit_price
            AS DECIMAL(18,2)
        ) AS gross_revenue,

        CAST(
            oi.quantity * oi.unit_cost
            AS DECIMAL(18,2)
        ) AS cogs,

        CAST(
            oi.quantity * oi.unit_price
            * (1 - oi.item_discount)
            * (1 - o.order_discount)
            AS DECIMAL(18,2)
        ) AS net_revenue

    FROM dbo.Orders AS o
    INNER JOIN dbo.OrderItems AS oi
        ON o.order_id = oi.order_id
),

ItemDiscounts AS (
    SELECT
        *,
        CAST(
            gross_revenue * item_discount
            AS DECIMAL(18,2)
        ) AS item_discount_amount
    FROM BaseSales
),

OrderDiscounts AS (
    SELECT
        *,
        CAST(
            gross_revenue
            - item_discount_amount
            - net_revenue
            AS DECIMAL(18,2)
        ) AS order_discount_amount
    FROM ItemDiscounts
)

SELECT
    order_id,
    customer_id,
    product_id,
    campaign_id,
    order_date_key,
    ship_date_key,
    status_id,
    payment_method_key,
    quantity,
    gross_revenue,
    item_discount_amount,
    order_discount_amount,
    net_revenue,
    cogs

FROM OrderDiscounts;
GO

