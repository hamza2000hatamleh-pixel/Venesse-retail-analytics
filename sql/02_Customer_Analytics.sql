USE Venesse;
GO

WITH CustomerOrders AS (
    SELECT
        customer_id,
        COUNT(DISTINCT order_id) AS total_orders
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260101 AND 20260930
    GROUP BY customer_id
),
CustomerSegments AS (
    SELECT
        customer_id,
        total_orders,
        CASE
            WHEN total_orders = 1 THEN 'One-Time'
            WHEN total_orders BETWEEN 2 AND 3 THEN 'Repeat'
            ELSE 'Loyal'
        END AS customer_segment
    FROM CustomerOrders
)
SELECT
    customer_segment,
    COUNT(*) AS customer_count,
    SUM(total_orders) AS total_orders,
    ROUND(
        100.0 * COUNT(*) / SUM(COUNT(*)) OVER (),
        2
    ) AS customer_percentage
FROM CustomerSegments
GROUP BY customer_segment
ORDER BY customer_count DESC;
WITH Q1Customers AS (
    SELECT DISTINCT customer_id
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260101 AND 20260331
),
Q2Customers AS (
    SELECT DISTINCT customer_id
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260401 AND 20260630
)
SELECT
    COUNT(*) AS q1_customers,
    COUNT(q2.customer_id) AS retained_customers,
    ROUND(
        100.0 * COUNT(q2.customer_id) / NULLIF(COUNT(*), 0),
        2
    ) AS retention_rate_pct
FROM Q1Customers q1
LEFT JOIN Q2Customers q2
    ON q1.customer_id = q2.customer_id;
WITH Q2Customers AS (
    SELECT DISTINCT customer_id
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260401 AND 20260630
),
Q3Customers AS (
    SELECT DISTINCT customer_id
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260701 AND 20260930
)
SELECT
    COUNT(*) AS q2_customers,
    COUNT(q3.customer_id) AS retained_customers,
    ROUND(
        100.0 * COUNT(q3.customer_id) / NULLIF(COUNT(*), 0),
        2
    ) AS retention_rate_pct
FROM Q2Customers q2
LEFT JOIN Q3Customers q3
    ON q2.customer_id = q3.customer_id;
WITH CustomerRevenue AS (
    SELECT
        customer_id,
        SUM(net_revenue) AS total_revenue
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260101 AND 20260930
    GROUP BY customer_id
),
RankedCustomers AS (
    SELECT
        customer_id,
        total_revenue,
        ROW_NUMBER() OVER (
            ORDER BY total_revenue DESC, customer_id
        ) AS revenue_rank,
        COUNT(*) OVER () AS total_customers
    FROM CustomerRevenue
),
TopCustomers AS (
    SELECT
        *,
        CEILING(total_customers * 0.10) AS top_10_count
    FROM RankedCustomers
)
SELECT
    MAX(total_customers) AS active_customers,
    MAX(top_10_count) AS top_10_customer_count,
    ROUND(
        SUM(CASE
            WHEN revenue_rank <= top_10_count
            THEN total_revenue ELSE 0
        END), 2
    ) AS top_10_revenue,
    ROUND(SUM(total_revenue), 2) AS total_revenue,
    ROUND(
        100.0 * SUM(CASE
            WHEN revenue_rank <= top_10_count
            THEN total_revenue ELSE 0
        END) / NULLIF(SUM(total_revenue), 0),
        2
    ) AS top_10_contribution_pct
FROM TopCustomers;
WITH PYCustomerRevenue AS (
    SELECT
        customer_id,
        SUM(net_revenue) AS py_revenue
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20250101 AND 20250930
    GROUP BY customer_id
),
CYCustomers AS (
    SELECT DISTINCT customer_id
    FROM dbo.FactSales
    WHERE status_id = 6
      AND order_date_key BETWEEN 20260101 AND 20260930
),
CustomerStatus AS (
    SELECT
        py.customer_id,
        py.py_revenue,
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM CYCustomers cy
                WHERE cy.customer_id = py.customer_id
            ) THEN 'Retained'
            ELSE 'Non-Returning'
        END AS customer_status
    FROM PYCustomerRevenue py
)
SELECT
    customer_status,
    COUNT(*) AS customer_count,
    ROUND(SUM(py_revenue), 2) AS py_revenue,
    ROUND(
        100.0 * SUM(py_revenue) /
        NULLIF(SUM(SUM(py_revenue)) OVER (), 0),
        2
    ) AS py_revenue_contribution_pct
FROM CustomerStatus
GROUP BY customer_status;