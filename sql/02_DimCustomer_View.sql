USE [Venesse]
GO

/****** Object:  View [dbo].[DimCustomer]    Script Date: 11/14/2026 6:46:22 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[DimCustomer] AS
SELECT
    c.customer_id ,
    c.customer_name, 
    c.date_of_birth ,
    r.region ,
    r.city
FROM Customers c
LEFT JOIN Regions r ON r.region_id = c.region_id;
GO

