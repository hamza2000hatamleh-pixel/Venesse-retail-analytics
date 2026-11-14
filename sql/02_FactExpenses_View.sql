USE [Venesse]
GO

/****** Object:  View [dbo].[FactExpenses]    Script Date: 11/14/2026 6:41:26 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[FactExpenses]
AS
SELECT
    e.expense_id,
    e.expense_name,
    e.expense_category_id,

    CAST(
        CONVERT(CHAR(8), e.expense_date, 112)
        AS INT
    ) AS expense_date_key,

    e.expense_amount

FROM dbo.Expenses AS e;
GO

