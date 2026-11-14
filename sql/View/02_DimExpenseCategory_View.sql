USE [Venesse]
GO

/****** Object:  View [dbo].[DimExpenseCategory]    Script Date: 11/14/2026 6:45:47 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[DimExpenseCategory]
AS
SELECT
    expense_category_id,
    expense_category_name
FROM dbo.ExpenseCategories;
GO

