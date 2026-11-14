USE [Venesse]
GO

/****** Object:  View [dbo].[DimProduct]    Script Date: 11/14/2026 6:43:12 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO


CREATE VIEW [dbo].[DimProduct] AS 
SELECT 
    p.product_id ,
    p.product_name ,
    pc.category_name ,
    p.unit_cost ,
    p.unit_price ,
    p.color ,
    p.[size] 
from Products p
LEFT JOIN ProductCategories pc on p.category_id = pc.category_id;
GO

