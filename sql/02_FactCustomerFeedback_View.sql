USE [Venesse]
GO

/****** Object:  View [dbo].[FactCustomerFeedback]    Script Date: 11/14/2026 6:42:07 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[FactCustomerFeedback]
AS
SELECT
    f.feedback_id,
    f.order_id,
    f.out_of_5_star,
    f.comments
FROM dbo.CustomerFeedback AS f;
GO

