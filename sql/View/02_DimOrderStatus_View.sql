USE [Venesse]
GO

/****** Object:  View [dbo].[DimOrderStatus]    Script Date: 11/14/2026 6:44:19 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[DimOrderStatus]
AS
SELECT
    status_id,
    status_name
FROM dbo.OrderStatus;
GO

