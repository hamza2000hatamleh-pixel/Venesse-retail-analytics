USE [Venesse]
GO

/****** Object:  View [dbo].[FactCampaignPerformance]    Script Date: 11/14/2026 6:42:44 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[FactCampaignPerformance]
AS
SELECT
    campaign_id,
    campaign_cost,
    num_of_clicks
    
FROM dbo.MarketingCampaigns;
GO

