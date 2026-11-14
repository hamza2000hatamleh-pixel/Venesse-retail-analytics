USE [Venesse]
GO

/****** Object:  View [dbo].[DimMarketingCampaign]    Script Date: 11/14/2026 6:45:19 PM ******/
SET ANSI_NULLS ON
GO

SET QUOTED_IDENTIFIER ON
GO

CREATE VIEW [dbo].[DimMarketingCampaign]
AS
SELECT
    mc.campaign_id,
    mc.campaign_name,
    mch.channel_name,
    mc.campaign_start_date,
    mc.campaign_end_date
FROM dbo.MarketingCampaigns AS mc
LEFT JOIN dbo.MarketingChannels AS mch
    ON mc.channel_id = mch.channel_id;
GO

