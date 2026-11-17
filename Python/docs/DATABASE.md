# Database requirements

This source package does not create or seed a database. Live reporting requires the existing Venesse schema and data. SQL queries in venesse_ai_agent_edit.py are the exact reference for required columns and join keys.

Referenced tables:
- dbo.FactSales
- dbo.DimCustomer
- dbo.DimOrder
- dbo.DimProduct
- dbo.DimMarketingCampaign
- dbo.FactCampaignPerformance
- dbo.FactCustomerFeedback
- dbo.FactExpenses
- dbo.DimExpenseCategory

Set VENESSE_DB_SERVER for the SQL Server instance. VENESSE_DB_DATABASE defaults to Venesse. VENESSE_DB_DRIVER defaults to ODBC Driver 17 for SQL Server. Connection uses Windows authentication; the current Windows identity must have access. This local development configuration retains TrustServerCertificate=yes; review certificate configuration before adapting it to another environment.

This GitHub-preparation copy uses environment configuration in place of the developer-specific server name. The working project has not been modified.
