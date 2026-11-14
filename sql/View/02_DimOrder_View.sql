USE [Venesse]
GO

/****** Object:  View [dbo].[DimOrder]    Script Date: 11/14/2026 6:44:43 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE   VIEW [dbo].[DimOrder]
AS
SELECT
    order_id,
    customer_id,
    order_date,
    ship_date
FROM dbo.Orders;
GO

