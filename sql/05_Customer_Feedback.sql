
USE Venesse;
GO

/*
VENESSE RETAIL ANALYTICS
05 - CUSTOMER FEEDBACK & SATISFACTION

Period: January - September 2026

Business rule:
Include all order statuses because negative experiences
may involve delayed, returned, or damaged orders.

Rating classification:
Positive = 4-5 stars
Neutral  = 3 stars
Negative = 1-2 stars

Note:
Confirm column names against exported table definitions.
*/

------------------------------------------------------------
-- 1. OVERALL CUSTOMER SATISFACTION
------------------------------------------------------------

WITH FeedbackData AS (
    SELECT
        cf.feedback_id,
        cf.out_of_5_star AS rating
    FROM dbo.CustomerFeedback cf
    JOIN dbo.Orders o
        ON cf.order_id = o.order_id
    WHERE o.order_date >= '2026-01-01'
      AND o.order_date < '2026-10-01'
      AND o.ship_date < '2026-10-01'
)
SELECT
    COUNT(*) AS total_reviews,
    ROUND(AVG(CAST(rating AS FLOAT)), 2)
        AS average_rating,

    SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END)
        AS positive_reviews,

    SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END)
        AS neutral_reviews,

    SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END)
        AS negative_reviews,

    ROUND(
        100.0 * SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 2
    ) AS positive_rate_pct,

    ROUND(
        100.0 * SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 2
    ) AS negative_rate_pct
FROM FeedbackData;

------------------------------------------------------------
-- 2. RATING DISTRIBUTION
------------------------------------------------------------

WITH RatingDistribution AS (
    SELECT
        cf.out_of_5_star AS rating,
        COUNT(*) AS review_count
    FROM dbo.CustomerFeedback cf
    JOIN dbo.Orders o
        ON cf.order_id = o.order_id
    WHERE o.order_date >= '2026-01-01'
      AND o.order_date < '2026-10-01'
      AND o.ship_date < '2026-10-01'
    GROUP BY cf.out_of_5_star
)
SELECT
    rating,
    review_count,
    ROUND(
        100.0 * review_count /
        NULLIF(SUM(review_count) OVER (), 0),
        2
    ) AS review_percentage
FROM RatingDistribution
ORDER BY rating DESC;

------------------------------------------------------------
-- 3. CUSTOMER SATISFACTION BY REGION
------------------------------------------------------------

WITH RegionalFeedback AS (
    SELECT
        r.region,
        cf.out_of_5_star AS rating
    FROM dbo.CustomerFeedback cf
    JOIN dbo.Orders o
        ON cf.order_id = o.order_id
    JOIN dbo.Customers c
        ON o.customer_id = c.customer_id
    JOIN dbo.Regions r
        ON c.region_id = r.region_id
    WHERE o.order_date >= '2026-01-01'
      AND o.order_date < '2026-10-01'
      AND o.ship_date < '2026-10-01'
)
SELECT
    region,
    COUNT(*) AS total_reviews,
    ROUND(AVG(CAST(rating AS FLOAT)), 2)
        AS average_rating,

    SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END)
        AS negative_reviews,

    ROUND(
        100.0 * SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 2
    ) AS positive_rate_pct,

    ROUND(
        100.0 * SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 2
    ) AS negative_rate_pct
FROM RegionalFeedback
GROUP BY region
ORDER BY average_rating DESC;

------------------------------------------------------------
-- 4. CUSTOMER FEEDBACK BY ORDER STATUS
------------------------------------------------------------

WITH StatusFeedback AS (
    SELECT
        os.status_name,
        cf.out_of_5_star AS rating
    FROM dbo.CustomerFeedback cf
    JOIN dbo.Orders o
        ON cf.order_id = o.order_id
    JOIN dbo.OrderStatus os
        ON o.status_id = os.status_id
    WHERE o.order_date >= '2026-01-01'
      AND o.order_date < '2026-10-01'
      AND o.ship_date < '2026-10-01'
)
SELECT
    status_name,
    COUNT(*) AS total_reviews,
    ROUND(AVG(CAST(rating AS FLOAT)), 2)
        AS average_rating,

    SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END)
        AS negative_reviews,

    ROUND(
        100.0 * SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 2
    ) AS negative_rate_pct
FROM StatusFeedback
GROUP BY status_name
ORDER BY negative_rate_pct DESC;

------------------------------------------------------------
-- 5. NEGATIVE REVIEW COMMENTS
------------------------------------------------------------

SELECT
    cf.feedback_id,
    cf.order_id,
    cf.out_of_5_star AS rating,
    cf.comments,
    o.order_date
FROM dbo.CustomerFeedback cf
JOIN dbo.Orders o
    ON cf.order_id = o.order_id
WHERE o.order_date >= '2026-01-01'
  AND o.order_date < '2026-10-01'
  AND o.ship_date < '2026-10-01'
  AND cf.out_of_5_star <= 2
ORDER BY
    cf.out_of_5_star ASC,
    o.order_date DESC;

------------------------------------------------------------
-- 6. MOST FREQUENT NEGATIVE COMMENTS
------------------------------------------------------------

SELECT
    cf.comments,
    COUNT(*) AS occurrence_count
FROM dbo.CustomerFeedback cf
JOIN dbo.Orders o
    ON cf.order_id = o.order_id
WHERE o.order_date >= '2026-01-01'
  AND o.order_date < '2026-10-01'
  AND o.ship_date < '2026-10-01'
  AND cf.out_of_5_star <= 2
  AND NULLIF(LTRIM(RTRIM(cf.comments)), '') IS NOT NULL
GROUP BY cf.comments
ORDER BY occurrence_count DESC, cf.comments;
