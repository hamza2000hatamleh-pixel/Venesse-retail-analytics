USE [Venesse]
GO

/****** Object:  View [dbo].[DimPaymentMethod]    Script Date: 11/14/2026 6:43:45 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[DimPaymentMethod]
AS
SELECT
    CASE
        WHEN payment_method = 'cash' THEN 1
        WHEN payment_method = 'credit card' THEN 2
        WHEN payment_method = 'PayPal' THEN 3
    END AS payment_method_key,
    payment_method
FROM (
    SELECT DISTINCT payment_method
    FROM dbo.Orders
) AS pm;
GO

