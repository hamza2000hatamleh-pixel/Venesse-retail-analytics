"""Venesse reporting agent — organized reading order.

1. Connection and fetch functions: retrieve source data from SQL Server.
2. Shared helpers: calculate validated metrics and write TXT files.
3–5. Reports and comparisons: calculate and format business results.
6–7. Exports: save TXT reports or call existing HTML dashboard modules.
8. Command pipeline: parse text, validate the request, then dispatch.
9. Entry point: start the interactive prompt when run directly.

Period: January–September. Sales use delivered status 6; feedback uses order dates
without that filter. Marketing and operating campaign eligibility differ.
Operating campaign costs remain provisionally separate from operating expenses.
AI request interpretation and commentary use the explicitly configured provider.
"""

import os
import pyodbc
import pandas as pd
import math
import re
from pathlib import Path
from datetime import datetime
from venesse_html import export_sales_html
from venesse_customer_html import export_customer_html
from venesse_product_html import export_product_html
from venesse_retention_html import export_retention_html
from venesse_marketing_html import export_marketing_html
from venesse_feedback_html import export_feedback_html
from venesse_operating_html import export_operating_html
from venesse_full_html import export_full_html
from venesse_ai_client import track_request_usage
from venesse_ai_interpreter import interpret_business_request
from venesse_ai_summary import add_ai_summary_to_result

# ============================================================================
# 1. DATABASE CONNECTION AND FETCH FUNCTIONS
# ============================================================================

def _connect_to_database():
    """Open the Windows-authenticated Venesse SQL Server connection.
    Fetch functions own the connection and close it in their finally blocks.
    """
    def odbc_value(value):
        return '{'+value.replace('}', '}}')+'}'
    server=os.getenv('VENESSE_DB_SERVER','localhost')
    database=os.getenv('VENESSE_DB_DATABASE','Venesse')
    driver=os.getenv('VENESSE_DB_DRIVER','ODBC Driver 17 for SQL Server')
    return pyodbc.connect(
        f"DRIVER={odbc_value(driver)};"
        f"SERVER={odbc_value(server)};"
        f"DATABASE={odbc_value(database)};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )



def fetch_sales_data(year):

    """Read January–September delivered-sales dates, revenue and historical COGS.
    Return a DataFrame and propagate database errors to the calling report.
    """
    start_date = f"{year}0101"
    end_date = f"{year}1001"

    # Use parameterized SQL so the selected year is passed separately from query text.
    query = """
        SELECT
            order_date_key,
            net_revenue,
            cogs
        FROM dbo.FactSales
        WHERE order_date_key >= ?
        AND order_date_key < ?
        AND status_id = 6
    """
    # Create the database connection used by this retrieval.
    connection = None

    try:
        connection = _connect_to_database()
        cursor = connection.cursor()
        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()
        columns = [
        column[0]
        for column in cursor.description
        ]
        df = pd.DataFrame.from_records(
            [tuple(row) for row in rows],
            columns=columns
        )
        return df

    finally:
        if connection is not None:
            connection.close()


def fetch_customer_sales_data(year):
    """Read delivered January–September sales items with customer and order IDs.
    Return rows for distinct-order customer analytics and prior-year retention.
    """
    # Use parameterized SQL so the selected year is passed separately from query text.
    query = """
        SELECT
            order_id,
            customer_id,
            order_date_key,
            net_revenue
        FROM dbo.FactSales
        WHERE order_date_key >= ?
          AND order_date_key < ?
          AND status_id = 6
    """

    # Create the database connection used by this retrieval.
    connection = _connect_to_database()

    try:
        cursor = connection.cursor()
        cursor.execute(
            query,
            (int(f"{year}0101"), int(f"{year}1001"))
        )

        columns = [
            column[0] for column in cursor.description
        ]

        return pd.DataFrame.from_records(
            [tuple(row) for row in cursor.fetchall()],
            columns=columns
        )

    finally:
        connection.close()


def fetch_product_sales_data(year):
    """Read delivered January–September product sales with category labels.
    Return quantities, net revenue and historical COGS for profitability analysis.
    """
    # Use parameterized SQL so the selected year is passed separately from query text.
    query = """
        SELECT
            s.product_id,
            p.product_name,
            p.category_name,
            s.quantity,
            s.net_revenue,
            s.cogs
        FROM dbo.FactSales AS s
        LEFT JOIN dbo.DimProduct AS p
            ON s.product_id = p.product_id
        WHERE s.order_date_key >= ?
          AND s.order_date_key < ?
          AND s.status_id = 6
    """

    # Create the database connection used by this retrieval.
    connection = _connect_to_database()

    try:
        cursor = connection.cursor()
        cursor.execute(
            query,
            (int(f"{year}0101"), int(f"{year}1001"))
        )

        columns = [column[0] for column in cursor.description]

        return pd.DataFrame.from_records(
            [tuple(row) for row in cursor.fetchall()],
            columns=columns
        )

    finally:
        connection.close()


def fetch_marketing_data(year):
    """Read campaigns that both start and end within January–September.
    Join campaign performance with delivered-sales revenue, COGS and distinct orders.
    Return one query-result row per join match; report functions check campaign IDs.
    """
    # Use parameterized SQL so the selected year is passed separately from query text.
    query = """
        WITH CampaignSales AS (
            SELECT
                campaign_id,
                COUNT(DISTINCT order_id) AS delivered_orders,
                SUM(net_revenue) AS attributed_revenue,
                SUM(cogs) AS attributed_cogs
            FROM dbo.FactSales
            WHERE order_date_key >= ?
              AND order_date_key < ?
              AND status_id = 6
            GROUP BY campaign_id
        )
        SELECT
            c.campaign_id,
            c.campaign_name,
            c.channel_name,
            c.campaign_start_date,
            c.campaign_end_date,
            p.campaign_cost,
            p.num_of_clicks,
            COALESCE(s.delivered_orders, 0) AS delivered_orders,
            COALESCE(s.attributed_revenue, 0) AS attributed_revenue,
            COALESCE(s.attributed_cogs, 0) AS attributed_cogs
        FROM dbo.DimMarketingCampaign AS c
        LEFT JOIN dbo.FactCampaignPerformance AS p
            ON c.campaign_id = p.campaign_id
        LEFT JOIN CampaignSales AS s
            ON c.campaign_id = s.campaign_id
        WHERE c.campaign_start_date >= ?
          AND c.campaign_start_date < ?
          AND c.campaign_end_date >= ?
          AND c.campaign_end_date < ?
    """

    start_date = f"{year}-01-01"
    end_date = f"{year}-10-01"

    # Create the database connection used by this retrieval.
    connection = _connect_to_database()

    try:
        cursor = connection.cursor()
        cursor.execute(
            query,
            (
                int(f"{year}0101"),
                int(f"{year}1001"),
                start_date,
                end_date,
                start_date,
                end_date
            )
        )

        columns = [
            column[0] for column in cursor.description
        ]

        return pd.DataFrame.from_records(
            [tuple(row) for row in cursor.fetchall()],
            columns=columns
        )

    finally:
        connection.close()


def fetch_feedback_data(year):
    """Read January–September feedback by order date, without a delivered-status filter.
    Return a DataFrame; close the SQL connection even when retrieval fails.
    """
    # Use parameterized SQL so the selected year is passed separately from query text.
    query = """
        SELECT
            f.feedback_id,
            f.order_id,
            o.customer_id,
            o.order_date,
            c.region,
            f.out_of_5_star,
            f.comments
        FROM dbo.FactCustomerFeedback AS f
        INNER JOIN dbo.DimOrder AS o
            ON f.order_id = o.order_id
        LEFT JOIN dbo.DimCustomer AS c
            ON o.customer_id = c.customer_id
        WHERE o.order_date >= ?
          AND o.order_date < ?
    """

    # Create the database connection used by this retrieval.
    connection = _connect_to_database()

    try:
        cursor = connection.cursor()
        cursor.execute(
            query,
            (f"{year}-01-01", f"{year}-10-01")
        )

        columns = [
            column[0] for column in cursor.description
        ]

        return pd.DataFrame.from_records(
            [tuple(row) for row in cursor.fetchall()],
            columns=columns
        )

    finally:
        connection.close()


def fetch_operating_expenses(year):
    """Read individual January–September expense records and category names.
    Return expense IDs, names, date keys and amounts for operating reports.
    """
    # Use parameterized SQL so the selected year is passed separately from query text.
    query = """
        SELECT
            e.expense_id,
            e.expense_name,
            e.expense_date_key,
            e.expense_category_id,
            c.expense_category_name,
            e.expense_amount
        FROM dbo.FactExpenses AS e
        LEFT JOIN dbo.DimExpenseCategory AS c
            ON e.expense_category_id = c.expense_category_id
        WHERE e.expense_date_key >= ?
          AND e.expense_date_key < ?
    """

    # Create the database connection used by this retrieval.
    connection = _connect_to_database()

    try:
        cursor = connection.cursor()
        cursor.execute(
            query,
            (int(f"{year}0101"), int(f"{year}1001"))
        )

        columns = [
            column[0] for column in cursor.description
        ]

        return pd.DataFrame.from_records(
            [tuple(row) for row in cursor.fetchall()],
            columns=columns
        )

    finally:
        connection.close()


def fetch_operating_campaign_costs(year):
    """Read full campaign costs for campaigns starting in January–September.
    Campaigns may end later; operating reports assign cost to the start month.
    """
    # Use parameterized SQL so the selected year is passed separately from query text.
    query = """
        SELECT
            c.campaign_id,
            c.campaign_name,
            c.campaign_start_date,
            c.campaign_end_date,
            p.campaign_cost
        FROM dbo.DimMarketingCampaign AS c
        LEFT JOIN dbo.FactCampaignPerformance AS p
            ON c.campaign_id = p.campaign_id
        WHERE c.campaign_start_date >= ?
          AND c.campaign_start_date < ?
    """

    # Create the database connection used by this retrieval.
    connection = _connect_to_database()

    try:
        cursor = connection.cursor()
        cursor.execute(
            query,
            (f"{year}-01-01", f"{year}-10-01")
        )

        columns = [
            column[0] for column in cursor.description
        ]

        return pd.DataFrame.from_records(
            [tuple(row) for row in cursor.fetchall()],
            columns=columns
        )

    finally:
        connection.close()


# ============================================================================
# 2. SHARED CALCULATION AND FILE HELPERS
# ============================================================================

def summarize_monthly_sales(df):
    """Convert a sales DataFrame into month-indexed revenue, COGS and gross profit.
    Raise for invalid values/dates; retain months represented in the retrieved data.
    """
    monthly = df.copy()

    monthly["order_date"] = pd.to_datetime(
        monthly["order_date_key"].astype(str),
        format="%Y%m%d",
        errors="raise"
    )

    for column in ("net_revenue", "cogs"):
        monthly[column] = pd.to_numeric(
            monthly[column],
            errors="raise"
        )

        if not monthly[column].map(math.isfinite).all():
            raise ValueError(f"Invalid values in {column}.")

    monthly["month"] = monthly["order_date"].dt.month

    if monthly["order_date"].isna().any():
        raise ValueError("Missing sales dates.")

    if not monthly["order_date"].dt.month.between(1, 9).all():
        raise ValueError("Sales dates must be within January–September.")

    summary = monthly.groupby("month").agg(
        revenue=("net_revenue", "sum"),
        cogs=("cogs", "sum")
    )

    summary["gross_profit"] = (
        summary["revenue"] - summary["cogs"]
    )
    return summary.sort_index()


def _load_operating_metrics(year):
    """Fetch each operating dataset once and validate the values actually used.
    Return reconciled monthly/category metrics; raise ValueError for invalid data
    and propagate pyodbc errors. Campaign costs remain provisionally separate.
    """
    sales = fetch_sales_data(year)
    expenses = fetch_operating_expenses(year)
    campaigns = fetch_operating_campaign_costs(year)
    for name, data in (('sales', sales), ('expense', expenses), ('operating campaign', campaigns)):
        if data is None or data.empty:
            raise ValueError(f'No {name} data available for {year}.')
    sales = sales.copy()
    expenses = expenses.copy()
    campaigns = campaigns.copy()
    for data, id_column in ((expenses, 'expense_id'), (campaigns, 'campaign_id')):
        if data[id_column].isna().any():
            raise ValueError(f'Missing {id_column} values for {year}.')
        if data[id_column].duplicated().any():
            raise ValueError(f'Duplicate {id_column} values for {year}.')
    for data, columns in ((sales, ('net_revenue', 'cogs')), (expenses, ('expense_amount',)), (campaigns, ('campaign_cost',))):
        for column in columns:
            data[column] = pd.to_numeric(data[column], errors='coerce')
            if not data[column].map(math.isfinite).all():
                raise ValueError(f'Invalid or missing {column} for {year}.')
    date_specs = ((sales, 'order_date_key', '%Y%m%d'), (expenses, 'expense_date_key', '%Y%m%d'), (campaigns, 'campaign_start_date', None))
    for data, column, date_format in date_specs:
        dates = pd.to_datetime(data[column].astype(str), format=date_format, errors='coerce')
        if dates.isna().any():
            raise ValueError(f'Invalid or missing {column} for {year}.')
        if ((dates.dt.year != year) | ~dates.dt.month.between(1, 9)).any():
            raise ValueError(f'Out-of-period {column} values for {year}.')
        data['month'] = dates.dt.month
    expenses['expense_category_name'] = expenses['expense_category_name'].fillna('Uncategorized')
    monthly = pd.DataFrame(index=pd.Index(range(1, 10), name='month'))
    monthly_sales = sales.groupby('month').agg(revenue=('net_revenue', 'sum'), cogs=('cogs', 'sum'))
    monthly = monthly.join(monthly_sales)
    monthly['operating_expenses'] = expenses.groupby('month')['expense_amount'].sum()
    monthly['campaign_costs'] = campaigns.groupby('month')['campaign_cost'].sum()
    monthly = monthly.fillna(0)
    monthly['gross_profit'] = monthly['revenue'] - monthly['cogs']
    monthly['operating_profit'] = monthly['gross_profit'] - monthly['operating_expenses'] - monthly['campaign_costs']
    monthly['operating_margin'] = monthly['operating_profit'] / monthly['revenue'].where(monthly['revenue'] != 0) * 100
    categories = expenses.groupby('expense_category_name')['expense_amount'].sum().sort_values(ascending=False)
    revenue = sales['net_revenue'].sum()
    cogs = sales['cogs'].sum()
    gross_profit = revenue - cogs
    operating_expenses = expenses['expense_amount'].sum()
    campaign_costs = campaigns['campaign_cost'].sum()
    operating_profit = gross_profit - operating_expenses - campaign_costs
    totals = dict(revenue=revenue, cogs=cogs, gross_profit=gross_profit,
                  operating_expenses=operating_expenses, campaign_costs=campaign_costs,
                  operating_profit=operating_profit)
    for name, total in totals.items():
        if not math.isfinite(total) or not monthly[name].map(math.isfinite).all():
            raise ValueError(f'Non-finite operating {name} for {year}.')
        if not math.isclose(monthly[name].sum(), total, rel_tol=0, abs_tol=0.01):
            raise ValueError(f'Monthly {name} reconciliation failed for {year}.')
    if not categories.map(math.isfinite).all() or not math.isclose(categories.sum(), operating_expenses, rel_tol=0, abs_tol=0.01):
        raise ValueError(f'Expense category reconciliation failed for {year}.')
    totals.update(monthly=monthly, categories=categories)
    return totals


def save_text_report(report, filename_prefix, output_folder="reports"):
    """Create the output folder and write report text as timestamped UTF-8 TXT.
    Return the absolute saved path; let the caller handle filesystem errors.
    """
    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    # Write the validated report through the shared timestamped TXT helper.
    file_path = folder / f"{filename_prefix}_{timestamp}.txt"

    file_path.write_text(report, encoding="utf-8")

    return file_path.resolve()


# ============================================================================
# 3. SINGLE-YEAR TXT REPORTS
# ============================================================================

def generate_sales_report(year):
    """Build a single-year sales TXT report with totals, margin and monthly results.
    Validate numeric values and reconcile monthly totals; return report or error text.
    """

    # Retrieve sales data.
    try:
        df = fetch_sales_data(year)
    except pyodbc.Error:
        return (
            "Unable to retrieve sales data. "
            "Check the database connection."
        )

    # Support the earlier fetch function, which returns None on failure.
    if df is None:
        return "Unable to retrieve sales data."

    if df is None or df.empty:
        return f"No matching sales data found for {year}."

    df = df.copy()

    # Prepare numeric values and dates.
    for column in ["net_revenue", "cogs"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["order_date"] = pd.to_datetime(
        df["order_date_key"].astype(str),
        format="%Y%m%d",
        errors="coerce"
    )

    required_columns = ["net_revenue", "cogs", "order_date"]

    if df[required_columns].isna().any().any():
        return (
            "Cannot generate the report: "
            "some sales records contain missing or invalid values."
        )
    for column in ("net_revenue", "cogs"):
        if not df[column].map(math.isfinite).all():
            return (
                "Cannot generate the report: "
                f"{column} contains non-finite values."
            )
    if ((df["order_date"].dt.year != year) | ~df["order_date"].dt.month.between(1, 9)).any():
        return f"Cannot generate the report: out-of-period sales dates for {year}."

    # Calculate overall KPIs.
    total_revenue = df["net_revenue"].sum()
    total_cogs = df["cogs"].sum()
    gross_profit = total_revenue - total_cogs

    gross_margin = (
        f"{gross_profit / total_revenue * 100:.2f}%"
        if total_revenue != 0
        else "N/A (zero revenue)"
    )

    # Calculate monthly performance.
    df["month"] = df["order_date"].dt.month

    monthly = (
        df.groupby("month", as_index=False)
        .agg(
            total_revenue=("net_revenue", "sum"),
            total_cogs=("cogs", "sum")
        )
        .sort_values("month")
    )

    monthly["gross_profit"] = (
        monthly["total_revenue"] - monthly["total_cogs"]
    )

    # Reconcile monthly totals with overall totals.
    def totals_match(monthly_total, overall_total):
        """Compare financial totals with a one-cent absolute tolerance and no relative tolerance.
        """
        return math.isclose(
            monthly_total,
            overall_total,
            rel_tol=0,
            abs_tol=0.01
        )

    # Reconcile grouped results against source totals or expected partitions.
    checks = {
        "Revenue": totals_match(
            monthly["total_revenue"].sum(),
            total_revenue
        ),
        "COGS": totals_match(
            monthly["total_cogs"].sum(),
            total_cogs
        ),
        "Gross Profit": totals_match(
            monthly["gross_profit"].sum(),
            gross_profit
        )
    }

    validation_text = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    overall_status = "PASS" if all(checks.values()) else "FAIL"

    monthly_text = monthly.to_string(
        index=False,
        float_format=lambda value: f"{value:.2f}"
    )

    report = (
        f"VENESSE SALES REPORT — {year} (January–September)\n"
        "------------------------------\n"
        f"Total Revenue: ${total_revenue:,.2f}\n"
        f"Total COGS: ${total_cogs:,.2f}\n"
        f"Gross Profit: ${gross_profit:,.2f}\n"
        f"Gross Margin: {gross_margin}\n"
        "------------------------------\n\n"
        "MONTHLY PERFORMANCE\n"
        "------------------------------\n"
        f"{monthly_text}\n\n"
        "FINANCIAL VALIDATION\n"
        "------------------------------\n"
        f"{validation_text}\n"
        f"Overall: {overall_status}"
    )

    return report


def generate_customer_report(year):
    """Build customer purchasing analytics from delivered sales-item rows.
    Count distinct orders, repeat customers and independently ranked top-10% revenue.
    Return formatted report text with internal validation results or an error.
    """
    try:
        df = fetch_customer_sales_data(year)
    except pyodbc.Error:
        return f"Unable to retrieve customer sales for {year}."

    if df is None or df.empty:
        return f"No customer sales data available for {year}."

    df = df.copy()

    if df[["customer_id", "order_id"]].isna().any().any():
        return "Cannot generate customer report: missing customer or order IDs."

    df["net_revenue"] = pd.to_numeric(
        df["net_revenue"],
        errors="coerce"
    )

    if not df["net_revenue"].map(math.isfinite).all():
        return "Cannot generate customer report: invalid revenue."

    # Each order should belong to exactly one customer.
    customers_per_order = df.groupby("order_id")["customer_id"].nunique()

    if (customers_per_order > 1).any():
        return "Cannot generate customer report: inconsistent order ownership."

    customers = df.groupby("customer_id").agg(
        order_count=("order_id", "nunique"),
        revenue=("net_revenue", "sum")
    )

    active_customers = len(customers)
    delivered_orders = df["order_id"].nunique()
    total_revenue = df["net_revenue"].sum()

    repeat_customers = int((customers["order_count"] >= 2).sum())
    one_time_customers = int((customers["order_count"] == 1).sum())
    repeat_two_three = int(
        customers["order_count"].between(2, 3).sum()
    )
    loyal_customers = int((customers["order_count"] >= 4).sum())

    repeat_rate = repeat_customers / active_customers * 100
    average_order_value = total_revenue / delivered_orders
    revenue_per_customer = total_revenue / active_customers

    # Round up so the group contains at least 10% of customers.
    top_count = math.ceil(active_customers * 0.10)

    ranked_customers = (
        customers.reset_index()
        .sort_values(
            ["revenue", "customer_id"],
            ascending=[False, True]
        )
    )

    top_revenue = ranked_customers.head(top_count)["revenue"].sum()

    top_contribution = (
        f"{top_revenue / total_revenue * 100:.2f}%"
        if total_revenue > 0
        else "N/A"
    )

    # Reconcile grouped results against source totals or expected partitions.
    checks = {
        "Customer revenue": math.isclose(
            customers["revenue"].sum(),
            total_revenue,
            rel_tol=0,
            abs_tol=0.01
        ),
        "Order count": (
            customers["order_count"].sum() == delivered_orders
        ),
        "Customer segments": (
            one_time_customers
            + repeat_two_three
            + loyal_customers
            == active_customers
        )
    }

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    return (
        f"VENESSE CUSTOMER ANALYTICS — {year}\n"
        "Period: January–September | Delivered sales\n"
        "------------------------------------------\n"
        f"Active customers: {active_customers:,}\n"
        f"Delivered orders: {delivered_orders:,}\n"
        f"Revenue: ${total_revenue:,.2f}\n"
        f"Repeat customers (2+ orders): {repeat_customers:,}\n"
        f"Repeat customer rate: {repeat_rate:.2f}%\n"
        f"Average order value: ${average_order_value:,.2f}\n"
        f"Revenue per active customer: ${revenue_per_customer:,.2f}\n\n"
        "PURCHASE FREQUENCY\n"
        f"One-time (1 order): {one_time_customers:,}\n"
        f"Repeat (2–3 orders): {repeat_two_three:,}\n"
        f"Loyal (4+ orders): {loyal_customers:,}\n\n"
        "CUSTOMER REVENUE CONCENTRATION\n"
        f"Top 10% group size (rounded up): {top_count:,}\n"
        f"Top group revenue: ${top_revenue:,.2f}\n"
        f"Top group share of revenue: {top_contribution}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def generate_retention_report(year):
    """Measure returns from the previous-year January–September customer cohort.
    Historical revenue at risk belongs to non-returning baseline customers.
    Segment baseline value using dense revenue rank; return validated report/error text.
    """
    base_year = year - 1
    datasets = {}

    for selected_year in (base_year, year):
        try:
            df = fetch_customer_sales_data(selected_year)
        except pyodbc.Error:
            return (
                "Unable to retrieve customer sales "
                f"for {selected_year}."
            )

        if df is None or df.empty:
            return (
                "No customer sales data available "
                f"for {selected_year}."
            )

        df = df.copy()

        if df["customer_id"].isna().any():
            return f"Missing customer IDs for {selected_year}."

        df["net_revenue"] = pd.to_numeric(
            df["net_revenue"], errors="coerce"
        )

        if not df["net_revenue"].map(math.isfinite).all():
            return f"Invalid revenue values for {selected_year}."

        datasets[selected_year] = df

    baseline = datasets[base_year]
    current = datasets[year]

    # Build prior-year and current-year customer sets for cohort membership.
    baseline_customers = set(baseline["customer_id"])
    current_customers = set(current["customer_id"])

    retained = baseline_customers & current_customers
    non_returning = baseline_customers - current_customers
    current_only = current_customers - baseline_customers

    cohort_count = len(baseline_customers)
    retention_rate = len(retained) / cohort_count * 100

    baseline_revenue = baseline.groupby(
        "customer_id"
    )["net_revenue"].sum()

    retained_revenue = baseline_revenue.loc[
        baseline_revenue.index.isin(retained)
    ].sum()

    revenue_at_risk = baseline_revenue.loc[
        baseline_revenue.index.isin(non_returning)
    ].sum()

    total_baseline_revenue = baseline["net_revenue"].sum()

    risk_share = (
        f"{revenue_at_risk / total_baseline_revenue * 100:.2f}%"
        if total_baseline_revenue > 0
        else "N/A"
    )

    # Rank baseline customer value before selecting non-returning customers.
    customer_segments = baseline_revenue.rename(
        "baseline_revenue"
    ).to_frame()

    customer_segments["revenue_rank"] = (
        customer_segments["baseline_revenue"]
        .rank(method="dense", ascending=False)
    )

    high_limit = math.ceil(cohort_count * 0.20)
    medium_limit = math.ceil(cohort_count * 0.50)

    def assign_segment(rank):
        """Map a dense baseline-revenue rank to High, Medium or Low Value cohort segments.
        """
        if rank <= high_limit:
            return "High Value"
        if rank <= medium_limit:
            return "Medium Value"
        return "Low Value"

    customer_segments["segment"] = (
        customer_segments["revenue_rank"].map(assign_segment)
    )

    non_returning_segments = customer_segments.loc[
        customer_segments.index.isin(non_returning)
    ]

    segment_summary = (
        non_returning_segments.groupby("segment")
        .agg(
            non_returning_customers=("baseline_revenue", "size"),
            revenue_at_risk=("baseline_revenue", "sum")
        )
        .reindex(
            ["High Value", "Medium Value", "Low Value"],
            fill_value=0
        )
    )

    segment_display = segment_summary.reset_index()

    segment_display["Share of revenue at risk"] = (
        segment_display["revenue_at_risk"].map(
            lambda amount: (
                f"{amount / revenue_at_risk * 100:.2f}%"
                if revenue_at_risk > 0
                else "N/A"
            )
        )
    )

    segment_display["revenue_at_risk"] = (
        segment_display["revenue_at_risk"].map(
            lambda amount: f"${amount:,.2f}"
        )
    )

    segment_display = segment_display.rename(columns={
        "segment": "Segment",
        "non_returning_customers": "Non-returning customers",
        "revenue_at_risk": "Revenue at risk"
    })

    segment_text = segment_display.to_string(index=False)

    # Reconcile grouped results against source totals or expected partitions.
    checks = {
        "Baseline cohort partition": (
            len(retained) + len(non_returning) == cohort_count
        ),
        "Current customer partition": (
            len(retained) + len(current_only)
            == len(current_customers)
        ),
        "Baseline revenue partition": math.isclose(
            retained_revenue + revenue_at_risk,
            total_baseline_revenue,
            rel_tol=0,
            abs_tol=0.01
        ),
        "Segment customer count": (
                segment_summary["non_returning_customers"].sum()
                == len(non_returning)
        ),
        "Segment revenue at risk": math.isclose(
            segment_summary["revenue_at_risk"].sum(),
            revenue_at_risk,
            rel_tol=0,
            abs_tol=0.01
        )
    }

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    non_returning_rate = (
        len(non_returning) / cohort_count * 100
    )

    summary_text = (
        f"- {len(retained):,} of {cohort_count:,} baseline customers "
        f"returned ({retention_rate:.2f}%).\n"
        f"- {len(non_returning):,} baseline customers did not return "
        f"during the comparison period ({non_returning_rate:.2f}%).\n"
        f"- These non-returning customers generated "
        f"${revenue_at_risk:,.2f} in baseline-period revenue "
        f"({risk_share} of baseline revenue).\n"
        "- Investigate non-returning customers by historical value "
        "and profitability before choosing re-engagement offers."
    )

    return (
        f"VENESSE CUSTOMER RETENTION — {year}\n"
        "Period: January–September | Delivered sales\n"
        f"Baseline cohort: {base_year}\n"
        "------------------------------------------\n"
        f"Baseline customers: {cohort_count:,}\n"
        f"Retained customers: {len(retained):,}\n"
        f"Non-returning customers: {len(non_returning):,}\n"
        f"Retention rate: {retention_rate:.2f}%\n"
        f"Current active customers: {len(current_customers):,}\n"
        f"Current-only customers: {len(current_only):,}\n\n"
        "BASELINE REVENUE EXPOSURE\n"
        f"Baseline revenue: ${total_baseline_revenue:,.2f}\n"
        f"Baseline revenue from retained customers: "
        f"${retained_revenue:,.2f}\n"
        f"Revenue at risk: ${revenue_at_risk:,.2f}\n"
        f"Share of baseline revenue at risk: {risk_share}\n\n"
        "Revenue at risk represents historical baseline-period "
        "revenue from non-returning customers, not a forecast "
        "of lost revenue.\n"
        "Current-only customers were absent from the baseline "
        "period; they are not necessarily first-time customers.\n\n"
        "NON-RETURNING CUSTOMERS BY BASELINE VALUE\n"
        "------------------------------------------\n"
        "Segments use dense baseline-revenue ranks: "
        "High <= ceil(20% of cohort), "
        "Medium <= ceil(50%), otherwise Low.\n"
        f"{segment_text}\n\n"
        "BUSINESS SUMMARY\n"
        "------------------------------\n"
        f"{summary_text}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def generate_product_report(year):
    """Build product and category revenue, units, gross-profit and margin results.
    Reconcile grouped amounts to retrieved sales totals and return report/error text.
    """
    try:
        df = fetch_product_sales_data(year)
    except pyodbc.Error:
        return f"Unable to retrieve product sales for {year}."

    if df is None or df.empty:
        return f"No product sales data available for {year}."

    df = df.copy()

    for column in ("quantity", "net_revenue", "cogs"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

        if not df[column].map(math.isfinite).all():
            return f"Invalid or missing values in {column}."

    if df["product_id"].isna().any():
        return "Cannot generate product report: missing product IDs."

    df["product_name"] = df["product_name"].fillna("Unknown product")
    df["category_name"] = df["category_name"].fillna("Uncategorized")

    labels = df.groupby("product_id")[["product_name", "category_name"]].nunique()
    if (labels > 1).any().any():
        return f"Cannot generate product report: inconsistent product labels for {year}."

    products = df.groupby(
        ["product_id", "product_name", "category_name"],
        as_index=False
    ).agg(
        units_sold=("quantity", "sum"),
        revenue=("net_revenue", "sum"),
        cogs=("cogs", "sum")
    )

    products["gross_profit"] = products["revenue"] - products["cogs"]
    products["margin_pct"] = (
        products["gross_profit"]
        / products["revenue"].where(products["revenue"] != 0)
        * 100
    )

    categories = df.groupby(
        "category_name",
        as_index=False
    ).agg(
        units_sold=("quantity", "sum"),
        revenue=("net_revenue", "sum"),
        cogs=("cogs", "sum")
    )

    categories["gross_profit"] = (
        categories["revenue"] - categories["cogs"]
    )
    categories["margin_pct"] = (
        categories["gross_profit"]
        / categories["revenue"].where(categories["revenue"] != 0)
        * 100
    )

    top_products = products.sort_values(
        ["gross_profit", "product_id"],
        ascending=[False, True]
    ).head(10)

    total_revenue = df["net_revenue"].sum()
    total_profit = total_revenue - df["cogs"].sum()
    top_profit = top_products["gross_profit"].sum()

    contribution = (
        f"{top_profit / total_profit * 100:.2f}%"
        if total_profit > 0
        else "N/A (total gross profit <= 0)"
    )

    # Reconcile grouped figures with the source data.
    checks = {
        "Product revenue": math.isclose(
            products["revenue"].sum(),
            total_revenue,
            rel_tol=0,
            abs_tol=0.01
        ),
        "Product gross profit": math.isclose(
            products["gross_profit"].sum(),
            total_profit,
            rel_tol=0,
            abs_tol=0.01
        ),
        "Category revenue": math.isclose(
            categories["revenue"].sum(),
            total_revenue,
            rel_tol=0,
            abs_tol=0.01
        ),
        "Category gross profit": math.isclose(
            categories["gross_profit"].sum(),
            total_profit,
            rel_tol=0,
            abs_tol=0.01
        )
    }

    top_display = top_products[
        [
            "product_name", "category_name", "units_sold",
            "revenue", "gross_profit", "margin_pct"
        ]
    ].copy()

    category_display = categories.sort_values(
        "revenue", ascending=False
    )[
        [
            "category_name", "units_sold",
            "revenue", "gross_profit", "margin_pct"
        ]
    ].copy()

    for table in (top_display, category_display):
        for column in ("revenue", "gross_profit"):
            table[column] = table[column].map(
                lambda value: f"${value:,.2f}"
            )

        table["margin_pct"] = table["margin_pct"].map(
            lambda value: f"{value:.2f}%"
            if pd.notna(value) else "N/A"
        )

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    return (
        f"VENESSE PRODUCT PROFITABILITY — {year}\n"
        "Period: January–September | Delivered sales\n"
        "------------------------------------------\n"
        f"Units sold: {df['quantity'].sum():,.0f}\n"
        f"Products with sales: {products['product_id'].nunique()}\n"
        f"Revenue: ${total_revenue:,.2f}\n"
        f"Gross profit: ${total_profit:,.2f}\n"
        f"Top 10 products gross profit: ${top_profit:,.2f}\n"
        f"Top 10 share of gross profit: {contribution}\n\n"
        "TOP 10 PRODUCTS BY GROSS PROFIT\n"
        f"{top_display.to_string(index=False)}\n\n"
        "CATEGORY PERFORMANCE\n"
        f"{category_display.to_string(index=False)}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def generate_marketing_report(year):
    """Build campaign/channel performance, ROAS and marketing ROI.
    Profit after marketing subtracts attributed historical COGS and campaign spend.
    Return report text with reconciliation checks, or an explanatory error.
    """
    try:
        df = fetch_marketing_data(year)
    except pyodbc.Error:
        return f"Unable to retrieve marketing data for {year}."

    if df is None or df.empty:
        return f"No eligible marketing campaigns available for {year}."

    df = df.copy()

    if df["campaign_id"].isna().any():
        return "Cannot generate marketing report: missing campaign IDs."

    if df["campaign_id"].duplicated().any():
        return "Cannot generate marketing report: duplicate campaign IDs."

    # Define the numeric source fields that must be usable before calculations.
    numeric_columns = (
        "campaign_cost",
        "num_of_clicks",
        "delivered_orders",
        "attributed_revenue",
        "attributed_cogs"
    )

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

        if not df[column].map(math.isfinite).all():
            return f"Invalid or missing values in {column}."

    if (
        df[["campaign_cost", "num_of_clicks", "delivered_orders"]]
        < 0
    ).any().any():
        return "Campaign costs, clicks, and order counts cannot be negative."

    df["channel_name"] = df["channel_name"].fillna("Unknown channel")
    df["campaign_name"] = df["campaign_name"].fillna("Unknown campaign")

    df["gross_profit"] = (
        df["attributed_revenue"] - df["attributed_cogs"]
    )
    df["profit_after_marketing"] = (
        df["gross_profit"] - df["campaign_cost"]
    )

    channels = df.groupby("channel_name", as_index=False).agg(
        campaign_cost=("campaign_cost", "sum"),
        attributed_revenue=("attributed_revenue", "sum"),
        attributed_cogs=("attributed_cogs", "sum"),
        profit_after_marketing=("profit_after_marketing", "sum")
    )

    def format_performance(data, name_column):
        """Format campaign/channel financial amounts and cost-based ROAS/ROI as a table.
        """
        display = data[
            [
                name_column,
                "attributed_revenue",
                "campaign_cost",
                "profit_after_marketing"
            ]
        ].copy()

        positive_cost = data["campaign_cost"].where(
            data["campaign_cost"] > 0
        )

        display["ROAS"] = (
            data["attributed_revenue"] / positive_cost
        ).map(
            lambda value: f"{value:.2f}x"
            if pd.notna(value) else "N/A"
        )

        display["Marketing ROI"] = (
            data["profit_after_marketing"] / positive_cost * 100
        ).map(
            lambda value: f"{value:.2f}%"
            if pd.notna(value) else "N/A"
        )

        for column in (
            "attributed_revenue",
            "campaign_cost",
            "profit_after_marketing"
        ):
            display[column] = display[column].map(
                lambda value: f"${value:,.2f}"
            )

        return display.to_string(index=False)

    revenue = df["attributed_revenue"].sum()
    cogs = df["attributed_cogs"].sum()
    spending = df["campaign_cost"].sum()
    gross_profit = revenue - cogs
    profit_after_marketing = gross_profit - spending

    roas = (
        f"{revenue / spending:.2f}x"
        if spending > 0 else "N/A"
    )
    roi = (
        f"{profit_after_marketing / spending * 100:.2f}%"
        if spending > 0 else "N/A"
    )

    # Reconcile grouped results against source totals or expected partitions.
    checks = {
        "Channel revenue": math.isclose(
            channels["attributed_revenue"].sum(),
            revenue,
            rel_tol=0,
            abs_tol=0.01
        ),
        "Channel COGS": math.isclose(
            channels["attributed_cogs"].sum(),
            cogs,
            rel_tol=0,
            abs_tol=0.01
        ),
        "Channel spending": math.isclose(
            channels["campaign_cost"].sum(),
            spending,
            rel_tol=0,
            abs_tol=0.01
        ),
        "Channel profit after marketing": math.isclose(
            channels["profit_after_marketing"].sum(),
            profit_after_marketing,
            rel_tol=0,
            abs_tol=0.01
        )
    }

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    campaigns = df.sort_values(
        ["profit_after_marketing", "campaign_id"],
        ascending=[False, True]
    )
    channels = channels.sort_values(
        "profit_after_marketing", ascending=False
    )

    # Build deterministic observations from the calculated metrics.
    insights = []

    best_profit = df.sort_values(
        ["profit_after_marketing", "campaign_id"],
        ascending=[False, True]
    ).iloc[0]

    insights.append(
        "Highest profit after marketing: "
        f"{best_profit['campaign_name']} "
        f"(${best_profit['profit_after_marketing']:,.2f})."
    )

    paid_campaigns = df.loc[df["campaign_cost"] > 0].copy()

    if not paid_campaigns.empty:
        paid_campaigns["roi_pct"] = (
            paid_campaigns["profit_after_marketing"]
            / paid_campaigns["campaign_cost"]
            * 100
        )

        best_roi = paid_campaigns.sort_values(
            ["roi_pct", "campaign_id"],
            ascending=[False, True]
        ).iloc[0]

        insights.append(
            f"Highest marketing ROI: {best_roi['campaign_name']} "
            f"({best_roi['roi_pct']:,.2f}%)."
        )

    loss_campaigns = df.loc[
        df["profit_after_marketing"] < 0
    ].sort_values("profit_after_marketing")

    if loss_campaigns.empty:
        insights.append(
            "No eligible campaign recorded negative profit "
            "after marketing."
        )
    else:
        for _, campaign in loss_campaigns.iterrows():
            insights.append(
                f"Negative profit after marketing: "
                f"{campaign['campaign_name']} "
                f"(${campaign['profit_after_marketing']:,.2f})."
            )

    if spending > 0:
        insights.append("Share of total marketing spending:")

        for _, campaign in df.sort_values(
            ["campaign_cost", "campaign_id"],
            ascending=[False, True]
        ).iterrows():
            share = campaign["campaign_cost"] / spending * 100

            insights.append(
                f"{campaign['campaign_name']}: {share:.2f}%."
            )

    insights.append(
        "Use these attributed results to guide investigation; "
        "they do not establish the incremental return from "
        "increasing campaign budgets."
    )

    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )

    return (
        f"VENESSE MARKETING PERFORMANCE — {year}\n"
        "Period: January–September | Delivered sales\n"
        "Includes campaigns starting and ending within the period.\n"
        "------------------------------------------\n"
        f"Eligible campaigns: {len(df):,}\n"
        f"Campaign-attributed revenue: ${revenue:,.2f}\n"
        f"Campaign-attributed COGS: ${cogs:,.2f}\n"
        f"Attributed gross profit: ${gross_profit:,.2f}\n"
        f"Marketing spending: ${spending:,.2f}\n"
        f"Profit after marketing: ${profit_after_marketing:,.2f}\n"
        f"ROAS: {roas}\n"
        f"Marketing ROI: {roi}\n\n"
        "CAMPAIGN PERFORMANCE\n"
        f"{format_performance(campaigns, 'campaign_name')}\n\n"
        "CHANNEL PERFORMANCE\n"
        f"{format_performance(channels, 'channel_name')}\n\n"
        "ROAS and ROI use total amounts, not averages of ratios.\n"
        "N/A = zero campaign cost.\n"
        "Attributed results do not establish incremental sales "
        "caused by marketing. Profit after marketing excludes "
        "other operating expenses.\n\n"
        "BUSINESS SUMMARY\n"
        "------------------------------\n"
        f"{summary_text}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def generate_feedback_report(year):
    """Build star-rating, rating-based sentiment, region and complaint summaries.
    Classify exact comment text for negative reviews only; reconcile review counts.
    Return report text ending with validation status, or an error message.
    """
    try:
        df = fetch_feedback_data(year)
    except pyodbc.Error:
        return f"Unable to retrieve feedback data for {year}."

    if df is None or df.empty:
        return f"No customer feedback available for {year}."

    df = df.copy()

    if df["feedback_id"].isna().any():
        return "Cannot generate feedback report: missing feedback IDs."

    if df["feedback_id"].duplicated().any():
        return "Cannot generate feedback report: duplicate feedback IDs."

    df["out_of_5_star"] = pd.to_numeric(
        df["out_of_5_star"], errors="coerce"
    )

    if not df["out_of_5_star"].isin([1, 2, 3, 4, 5]).all():
        return "Cannot generate feedback report: invalid or missing ratings."

    df["region"] = df["region"].fillna("Unknown region")
    df["negative"] = df["out_of_5_star"] <= 2

    total = len(df)
    positive = int((df["out_of_5_star"] >= 4).sum())
    neutral = int((df["out_of_5_star"] == 3).sum())
    negative = int(df["negative"].sum())
    average = df["out_of_5_star"].mean()

    rating_distribution = (
        df["out_of_5_star"]
        .value_counts()
        .reindex([1, 2, 3, 4, 5], fill_value=0)
        .rename_axis("Rating")
        .reset_index(name="Reviews")
    )

    regions = df.groupby("region").agg(
        reviews=("feedback_id", "size"),
        negative_reviews=("negative", "sum")
    )

    regions["negative_pct"] = (
        regions["negative_reviews"] / regions["reviews"] * 100
    )

    regions = regions.sort_values(
        ["negative_pct", "reviews"],
        ascending=[False, False]
    )

    region_display = regions.reset_index().rename(columns={
        "region": "Region",
        "reviews": "Reviews",
        "negative_reviews": "Negative reviews",
        "negative_pct": "Negative review %"
    })

    region_display["Negative review %"] = (
        region_display["Negative review %"].map(
            lambda value: f"{value:.2f}%"
        )
    )

    # Only negative reviews are classified as complaints.
    complaints = df.loc[df["negative"]].copy()

    def classify_complaint(comment):
        # Match the supplied DAX categories without inferring causes.
        """Map exact normalized negative-review comments to the established complaint categories.
        Use General Dissatisfaction as a fallback rather than inferring a root cause.
        """
        text = "" if pd.isna(comment) else str(comment).strip().casefold()

        if text == "slow delivery":
            return "Delivery"

        if text in (
            "product arrived damaged",
            "quality below expectation"
        ):
            return "Product Quality / Handling"

        return "General Dissatisfaction"

    complaints["category"] = complaints["comments"].map(
        classify_complaint
    )

    complaint_counts = (
        complaints["category"]
        .value_counts()
        .rename_axis("Complaint category")
        .reset_index(name="Negative reviews")
    )

    # Build deterministic observations from the calculated metrics.
    insights = [
        f"{positive / total * 100:.2f}% of reviews were positive, "
        f"{neutral / total * 100:.2f}% neutral, and "
        f"{negative / total * 100:.2f}% negative."
    ]

    if not complaint_counts.empty:
        top = complaint_counts.iloc[0]

        insights.append(
            f"The largest complaint category was "
            f"{top['Complaint category']} "
            f"({int(top['Negative reviews'])} negative reviews)."
        )

        if top["Complaint category"] == "General Dissatisfaction":
            insights.append(
                "General Dissatisfaction is a fallback category; "
                "it does not establish the underlying cause. "
                "Collect more specific complaint reasons."
            )

    highest_region = regions.index[0]
    highest = regions.iloc[0]

    insights.append(
        f"{highest_region} had the highest negative-review rate "
        f"({highest['negative_pct']:.2f}%; "
        f"{int(highest['negative_reviews'])} of "
        f"{int(highest['reviews'])} reviews). "
        "Consider review counts when comparing regions."
    )

    insights.append(
        "These results describe customers who submitted reviews; "
        "they may not represent all customers."
    )

    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )

    # Reconcile grouped results against source totals or expected partitions.
    checks = {
        "Rating distribution": (
            rating_distribution["Reviews"].sum() == total
        ),
        "Sentiment partition": (
            positive + neutral + negative == total
        ),
        "Regional review count": (
            regions["reviews"].sum() == total
        ),
        "Regional negative count": (
            regions["negative_reviews"].sum() == negative
        ),
        "Complaint count": (
            complaint_counts["Negative reviews"].sum() == negative
        )
    }

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    return (
        f"VENESSE CUSTOMER FEEDBACK — {year}\n"
        "Period: January–September, based on order date\n"
        "No delivered-status filter is applied.\n"
        "------------------------------------------\n"
        f"Total reviews: {total:,}\n"
        f"Average rating: {average:.2f} / 5\n"
        f"Positive reviews (4–5): {positive:,} "
        f"({positive / total * 100:.2f}%)\n"
        f"Neutral reviews (3): {neutral:,} "
        f"({neutral / total * 100:.2f}%)\n"
        f"Negative reviews (1–2): {negative:,} "
        f"({negative / total * 100:.2f}%)\n\n"
        "RATING DISTRIBUTION\n"
        f"{rating_distribution.to_string(index=False)}\n\n"
        "REGIONAL COMPARISON\n"
        f"{region_display.to_string(index=False)}\n\n"
        "NEGATIVE REVIEWS BY COMPLAINT CATEGORY\n"
        f"{complaint_counts.to_string(index=False) if negative else 'No negative reviews.'}\n\n"
        "BUSINESS SUMMARY\n"
        f"{summary_text}\n\n"
        "VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def generate_operating_report(year):
    """Build monthly operating profit and expense-category results for January–September.
    Subtract campaign costs separately as a provisional assumption; require cost data.
    Return report text with monthly/category reconciliation, or an error message.
    """
    try:
        data = _load_operating_metrics(year)
    except pyodbc.Error:
        return f"Unable to retrieve operating data for {year}."
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return f"Cannot generate operating report: {error}"

    revenue = data["revenue"]
    cogs = data["cogs"]
    gross_profit = data["gross_profit"]
    operating_expenses = data["operating_expenses"]
    campaign_costs = data["campaign_costs"]
    operating_profit = data["operating_profit"]
    monthly = data["monthly"]
    categories = data["categories"]

    operating_margin = (
        f"{operating_profit / revenue * 100:.2f}%"
        if revenue != 0 else "N/A"
    )

    monthly_display = monthly[
        [
            "revenue",
            "gross_profit",
            "operating_expenses",
            "campaign_costs",
            "operating_profit",
            "operating_margin"
        ]
    ].copy()

    for column in monthly_display.columns:
        if column == "operating_margin":
            monthly_display[column] = monthly_display[column].map(
                lambda value: (
                    f"{value:.2f}%"
                    if pd.notna(value) else "N/A"
                )
            )
        else:
            monthly_display[column] = monthly_display[column].map(
                lambda value: f"${value:,.2f}"
            )

    monthly_display = monthly_display.reset_index()
    monthly_display["month"] = monthly_display["month"].map(
        lambda month: datetime(2000, month, 1).strftime("%b")
    )

    category_display = categories.rename(
        "Operating expenses"
    ).reset_index()

    category_display["Operating expenses"] = (
        category_display["Operating expenses"].map(
            lambda value: f"${value:,.2f}"
        )
    )

    loss_months = int((monthly["operating_profit"] < 0).sum())

    # Build deterministic observations from the calculated metrics.
    insights = [
        f"{loss_months} of 9 months recorded an operating loss.",
        f"Gross profit was ${gross_profit:,.2f}, compared with "
        f"${operating_expenses + campaign_costs:,.2f} in "
        "operating expenses and separate campaign costs."
    ]

    if operating_profit < 0:
        insights.append(
            "The period recorded an operating loss under "
            "the provisional separate-campaign-cost assumption."
        )

    largest_category = categories.index[0]

    insights.append(
        f"The largest operating-expense category was "
        f"{largest_category} (${categories.iloc[0]:,.2f})."
    )

    insights.append(
        "Confirm that campaign costs are not already included "
        "in operating expenses before using this operating "
        "profit figure for decisions."
    )

    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )

    # Keep independent period totals for checking the monthly aggregation.
    expected_totals = {
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "operating_expenses": operating_expenses,
        "campaign_costs": campaign_costs,
        "operating_profit": operating_profit
    }

    # Reconcile grouped results against source totals or expected partitions.
    checks = {
        f"Monthly {name}": math.isclose(
            monthly[name].sum(),
            total,
            rel_tol=0,
            abs_tol=0.01
        )
        for name, total in expected_totals.items()
    }

    checks["Expense category total"] = math.isclose(
        categories.sum(),
        operating_expenses,
        rel_tol=0,
        abs_tol=0.01
    )

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    return (
        f"VENESSE OPERATING PROFITABILITY — {year}\n"
        "Period: January–September | Delivered sales\n"
        "Campaign costs treated as separate (provisional).\n"
        "Full campaign cost is assigned to its start month.\n"
        "------------------------------------------\n"
        f"Revenue: ${revenue:,.2f}\n"
        f"COGS: ${cogs:,.2f}\n"
        f"Gross profit: ${gross_profit:,.2f}\n"
        f"Operating expenses: ${operating_expenses:,.2f}\n"
        f"Campaign costs: ${campaign_costs:,.2f}\n"
        f"Operating profit: ${operating_profit:,.2f}\n"
        f"Operating margin: {operating_margin}\n\n"
        "MONTHLY OPERATING PERFORMANCE\n"
        f"{monthly_display.to_string(index=False)}\n\n"
        "OPERATING EXPENSES BY CATEGORY\n"
        f"{category_display.to_string(index=False)}\n\n"
        "BUSINESS SUMMARY\n"
        f"{summary_text}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


# ============================================================================
# 4. YEAR-OVER-YEAR TXT COMPARISONS
# ============================================================================

def compare_sales_years(base_year, comparison_year):
    """Compare January–September revenue, COGS, gross profit and margin for two years.
    Use percentage growth only for positive baselines and percentage points for margin.
    Return a formatted comparison or an error; no Overall status is appended.
    """
    if base_year == comparison_year:
        return "Please specify two different years."

    results = {}

    for year in (base_year, comparison_year):
        try:
            df = fetch_sales_data(year)
        except pyodbc.Error:
            return f"Unable to retrieve sales data for {year}."

        if df is None:
            return f"Unable to retrieve sales data for {year}."

        if df is None or df.empty:
            return f"No sales data available for {year}."

        amounts = df[["net_revenue", "cogs"]].apply(
            pd.to_numeric,
            errors="coerce"
        )

        if amounts.isna().any().any():
            return f"Invalid or missing financial values for {year}."

        if not amounts.apply(
            lambda column: column.map(math.isfinite)
        ).all().all():
            return f"Non-finite financial values for {year}."

        revenue = amounts["net_revenue"].sum()
        cogs = amounts["cogs"].sum()
        profit = revenue - cogs

        results[year] = {
            "Revenue": revenue,
            "COGS": cogs,
            "Gross Profit": profit,
            "Gross Margin": (
                profit / revenue * 100
                if revenue != 0
                else None
            )
        }

    base = results[base_year]
    comparison = results[comparison_year]
    rows = []

    for metric in ("Revenue", "COGS", "Gross Profit"):
        old_value = base[metric]
        new_value = comparison[metric]

        change = (
            f"{(new_value - old_value) / old_value * 100:+.2f}%"
            if old_value > 0
            else "N/A (baseline <= 0)"
        )

        rows.append({
            "Metric": metric,
            str(base_year): f"${old_value:,.2f}",
            str(comparison_year): f"${new_value:,.2f}",
            "Change": change
        })

    old_margin = base["Gross Margin"]
    new_margin = comparison["Gross Margin"]

    rows.append({
        "Metric": "Gross Margin",
        str(base_year): (
            f"{old_margin:.2f}%"
            if old_margin is not None else "N/A"
        ),
        str(comparison_year): (
            f"{new_margin:.2f}%"
            if new_margin is not None else "N/A"
        ),
        "Change": (
            f"{new_margin - old_margin:+.2f} pp"
            if old_margin is not None and new_margin is not None
            else "N/A"
        )
    })

    table = pd.DataFrame(rows).to_string(index=False)

    return (
        "VENESSE YEAR-OVER-YEAR COMPARISON\n"
        "Period: January–September, both years\n"
        f"Baseline: {base_year} | Comparison: {comparison_year}\n"
        "------------------------------------------------------------\n"
        f"{table}\n\n"
        "pp = percentage points"
    )


def compare_monthly_sales(base_year, comparison_year):
    """Compare two years of monthly sales with an outer join on month.
    Format absent months as unavailable and add rule-based performance insights.
    """
    if base_year == comparison_year:
        return "Please specify two different years."

    summaries = {}

    for year in (base_year, comparison_year):
        try:
            df = fetch_sales_data(year)

            if df is None:
                return f"Unable to retrieve sales data for {year}."

            if df is None or df.empty:
                return f"No sales data available for {year}."

            dates = pd.to_datetime(df["order_date_key"].astype(str), format="%Y%m%d", errors="coerce")
            if dates.isna().any() or (dates.dt.year != year).any():
                return f"Invalid or out-of-period sales dates for {year}."
            summaries[year] = summarize_monthly_sales(df)

        except pyodbc.Error:
            return f"Unable to retrieve sales data for {year}."

        except (ValueError, TypeError):
            return f"Invalid sales values or dates for {year}."

    comparison = summaries[base_year].join(
        summaries[comparison_year],
        how="outer",
        lsuffix=f"_{base_year}",
        rsuffix=f"_{comparison_year}"
    )

    rows = []

    for month, values in comparison.iterrows():
        row: dict[str, int | str] = {"Month": int(month)}

        for metric in ("revenue", "gross_profit"):
            old_value = values[f"{metric}_{base_year}"]
            new_value = values[f"{metric}_{comparison_year}"]

            label = "Revenue" if metric == "revenue" else "Profit"

            row[f"{label} {base_year}"] = (
                f"${old_value:,.2f}"
                if pd.notna(old_value) else "N/A"
            )
            row[f"{label} {comparison_year}"] = (
                f"${new_value:,.2f}"
                if pd.notna(new_value) else "N/A"
            )
            row[f"{label} change"] = (
                f"{(new_value - old_value) / old_value * 100:+.2f}%"
                if pd.notna(old_value)
                and pd.notna(new_value)
                and old_value > 0
                else "N/A"
            )
        margins = {}

        for year in (base_year, comparison_year):
            revenue = values[f"revenue_{year}"]
            profit = values[f"gross_profit_{year}"]

            margin = (
                profit / revenue * 100
                if pd.notna(revenue)
                and pd.notna(profit)
                and revenue != 0
                else None
            )

            margins[year] = margin

            row[f"Margin {year}"] = (
                f"{margin:.2f}%"
                if margin is not None
                else "N/A"
            )

        old_margin = margins[base_year]
        new_margin = margins[comparison_year]

        row["Margin change"] = (
            f"{new_margin - old_margin:+.2f} pp"
            if old_margin is not None and new_margin is not None
            else "N/A"
        )
        rows.append(row)

    table = pd.DataFrame(rows).to_string(index=False)
    # Build deterministic observations from the calculated metrics.
    insights = []

    for metric, label in (
        ("revenue", "Revenue"),
        ("gross_profit", "Gross profit")
    ):
        old = comparison[f"{metric}_{base_year}"]
        new = comparison[f"{metric}_{comparison_year}"]

        # Percentage growth requires both values and a positive baseline.
        valid = old.notna() & new.notna() & (old > 0)

        growth = (
            (new[valid] - old[valid]) / old[valid] * 100
        )

        if not growth.empty:
            best_month = growth.idxmax()
            month_name = datetime(2000, int(best_month), 1).strftime("%B")

            insights.append(
                f"{label}: highest percentage change was in "
                f"{month_name} ({growth.loc[best_month]:+.2f}%)."
            )
        comparable = old.notna() & new.notna()
        dollar_change = new[comparable] - old[comparable]

        if not dollar_change.empty:
            top_month = dollar_change.idxmax()
            top_increase = dollar_change.loc[top_month]

            if top_increase > 0:
                month_name = datetime(
                    2000, int(top_month), 1
                ).strftime("%B")

                insights.append(
                    f"{label}: largest dollar increase was in "
                    f"{month_name} (${top_increase:,.2f})."
                )

        declines = old.notna() & new.notna() & (new < old)

        if declines.any():
            month_names = [
                datetime(2000, int(month), 1).strftime("%B")
                for month in comparison.index[declines]
            ]

            insights.append(
                f"{label} declined in: {', '.join(month_names)}."
            )

    revenue_up_profit_down = (
        (
            comparison[f"revenue_{comparison_year}"]
            > comparison[f"revenue_{base_year}"]
        )
        & (
            comparison[f"gross_profit_{comparison_year}"]
            < comparison[f"gross_profit_{base_year}"]
        )
    )

    if revenue_up_profit_down.any():
        month_names = [
            datetime(2000, int(month), 1).strftime("%B")
            for month in comparison.index[revenue_up_profit_down]
        ]

        insights.append(
            "Revenue increased while gross profit declined in: "
            f"{', '.join(month_names)}. "
            "Review costs and sales mix to investigate."
        )
    margin_series = {}

    for year in (base_year, comparison_year):
        revenue = comparison[f"revenue_{year}"]
        profit = comparison[f"gross_profit_{year}"]

        # A zero-revenue month has no defined gross margin.
        margin_series[year] = (
            profit / revenue.where(revenue != 0) * 100
        )

    margin_changes = (
        margin_series[comparison_year] - margin_series[base_year]
    ).dropna()

    if not margin_changes.empty:
        best_month = margin_changes.idxmax()
        best_change = margin_changes.loc[best_month]

        if best_change > 0:
            month_name = datetime(
                2000, int(best_month), 1
            ).strftime("%B")

            insights.append(
                "Gross margin: largest improvement was in "
                f"{month_name} ({best_change:+.2f} pp)."
            )

        worst_month = margin_changes.idxmin()
        worst_change = margin_changes.loc[worst_month]

        if worst_change < 0:
            month_name = datetime(
                2000, int(worst_month), 1
            ).strftime("%B")

            insights.append(
                "Gross margin: largest decline was in "
                f"{month_name} ({worst_change:+.2f} pp)."
            )
    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )
    return (
        "VENESSE MONTHLY YEAR-OVER-YEAR COMPARISON\n"
        "Period: January–September\n"
        f"Baseline: {base_year} | Comparison: {comparison_year}\n"
        "Profit = gross profit | pp = percentage points\n"
        "N/A = missing data, zero revenue, or a non-positive "
        "growth baseline\n\n"
        f"{table}\n\n"
        "BUSINESS SUMMARY\n"
        "------------------------------\n"
        f"{summary_text or 'Insufficient comparable data.'}"
    )


def compare_customer_years(base_year, comparison_year):
    """Compare customer purchasing metrics using distinct orders and customer IDs.
    Rank each year independently for top-10% revenue; this is not cohort retention.
    """
    if base_year == comparison_year:
        return "Please specify two different years."

    results = {}

    for year in (base_year, comparison_year):
        try:
            df = fetch_customer_sales_data(year)
        except pyodbc.Error:
            return f"Unable to retrieve customer sales for {year}."

        if df is None or df.empty:
            return f"No customer sales data available for {year}."

        df = df.copy()

        if df[["customer_id", "order_id"]].isna().any().any():
            return f"Missing customer or order IDs for {year}."

        df["net_revenue"] = pd.to_numeric(
            df["net_revenue"], errors="coerce"
        )

        if not df["net_revenue"].map(math.isfinite).all():
            return f"Invalid revenue values for {year}."

        ownership = df.groupby("order_id")["customer_id"].nunique()

        if (ownership > 1).any():
            return f"Inconsistent order ownership for {year}."

        customers = df.groupby("customer_id").agg(
            orders=("order_id", "nunique"),
            revenue=("net_revenue", "sum")
        )

        active = len(customers)
        orders = df["order_id"].nunique()
        revenue = df["net_revenue"].sum()
        repeat = int((customers["orders"] >= 2).sum())

        top_count = math.ceil(active * 0.10)

        ranked = (
            customers.reset_index()
            .sort_values(
                ["revenue", "customer_id"],
                ascending=[False, True]
            )
        )

        top_revenue = ranked.head(top_count)["revenue"].sum()

        results[year] = {
            "Active customers": active,
            "Repeat customers": repeat,
            "Repeat customer rate": repeat / active * 100,
            "Delivered orders": orders,
            "Revenue": revenue,
            "Average order value": revenue / orders,
            "Revenue per customer": revenue / active,
            "Top 10% group size": top_count,
            "Top 10% revenue": top_revenue,
            "Top 10% revenue share": (
                top_revenue / revenue * 100
                if revenue > 0 else None
            ),
            "revenue_check": math.isclose(
                customers["revenue"].sum(),
                revenue,
                rel_tol=0,
                abs_tol=0.01
            ),
            "orders_check": (
                customers["orders"].sum() == orders
            )
        }

    base = results[base_year]
    current = results[comparison_year]

    count_metrics = {
        "Active customers",
        "Repeat customers",
        "Delivered orders",
        "Top 10% group size"
    }

    rate_metrics = {
        "Repeat customer rate",
        "Top 10% revenue share"
    }

    metrics = [
        "Active customers",
        "Repeat customers",
        "Repeat customer rate",
        "Delivered orders",
        "Revenue",
        "Average order value",
        "Revenue per customer",
        "Top 10% group size",
        "Top 10% revenue",
        "Top 10% revenue share"
    ]

    rows = []

    for metric in metrics:
        old = base[metric]
        new = current[metric]

        def format_value(value):
            """Format an operating comparison amount; show unavailable values as N/A.
            """
            if value is None:
                return "N/A"
            if metric in count_metrics:
                return f"{value:,}"
            if metric in rate_metrics:
                return f"{value:.2f}%"
            return f"${value:,.2f}"

        if old is None or new is None:
            change = "N/A"
        elif metric in rate_metrics:
            change = f"{new - old:+.2f} pp"
        elif old > 0:
            change = f"{(new - old) / old * 100:+.2f}%"
        else:
            change = "N/A"

        rows.append({
            "Metric": metric,
            str(base_year): format_value(old),
            str(comparison_year): format_value(new),
            "Change": change
        })

    # Reconcile grouped results against source totals or expected partitions.
    checks = {
        f"{year} {label}": results[year][key]
        for year in (base_year, comparison_year)
        for label, key in (
            ("customer revenue", "revenue_check"),
            ("order count", "orders_check")
        )
    }

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    # Build deterministic observations from the calculated metrics.
    insights = []

    def percentage_change(metric):
        """Format a yearly percentage change, returning N/A when the baseline is non-positive.
        """
        old = base[metric]
        new = current[metric]

        return (
            (new - old) / old * 100
            if old > 0 else None
        )

    active_change = percentage_change("Active customers")
    repeat_change = percentage_change("Repeat customers")

    if active_change is not None and repeat_change is not None:
        insights.append(
            f"Active customers changed by {active_change:+.2f}%, "
            f"while repeat customers changed by {repeat_change:+.2f}%."
        )

    repeat_rate_change = (
        current["Repeat customer rate"]
        - base["Repeat customer rate"]
    )

    insights.append(
        "Repeat customer rate changed by "
        f"{repeat_rate_change:+.2f} percentage points."
    )

    if repeat_rate_change < 0:
        insights.append(
            "A smaller share of active customers placed two or more "
            "delivered orders within the period. Investigate purchase "
            "frequency and post-purchase experience."
        )

    revenue_change = percentage_change("Revenue")
    order_change = percentage_change("Delivered orders")
    aov_change = percentage_change("Average order value")

    if all(
        value is not None
        for value in (revenue_change, order_change, aov_change)
    ):
        insights.append(
            f"Revenue changed by {revenue_change:+.2f}%, "
            f"delivered orders by {order_change:+.2f}%, "
            f"and average order value by {aov_change:+.2f}%."
        )

        if revenue_change > 0 and order_change < 0:
            insights.append(
                "Revenue increased despite fewer delivered orders, "
                "with a higher average order value. This alone does "
                "not establish whether prices, basket sizes, or "
                "product mix caused the increase."
            )

    old_share = base["Top 10% revenue share"]
    new_share = current["Top 10% revenue share"]

    if old_share is not None and new_share is not None:
        insights.append(
            f"The current year's top 10% customer group generated "
            f"{new_share:.2f}% of revenue; its share changed by "
            f"{new_share - old_share:+.2f} percentage points. "
            "The customers in this group can differ between years."
        )

    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )

    table = pd.DataFrame(rows).to_string(index=False)

    return (
        "VENESSE CUSTOMER YEAR-OVER-YEAR COMPARISON\n"
        "Period: January–September | Delivered sales\n"
        f"Baseline: {base_year} | Comparison: {comparison_year}\n"
        "Repeat customer = 2+ distinct orders within the period\n"
        "Top 10% group is selected independently for each year, "
        "with group size rounded up.\n"
        "pp = percentage points\n\n"
        f"{table}\n\n"
        "BUSINESS SUMMARY\n"
        "------------------------------\n"
        f"{summary_text}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def compare_product_years(base_year, comparison_year):
    """Compare two years of product/category performance and independently ranked leaders.
    Match products by ID, calculate changes and reconcile the comparison totals.
    """
    if base_year == comparison_year:
        return "Please specify two different years."

    datasets = {}

    for year in (base_year, comparison_year):
        try:
            df = fetch_product_sales_data(year)
        except pyodbc.Error:
            return f"Unable to retrieve product sales for {year}."

        if df is None or df.empty:
            return f"No product sales data available for {year}."

        df = df.copy()

        if df["product_id"].isna().any():
            return f"Missing product IDs for {year}."

        for column in ("quantity", "net_revenue", "cogs"):
            df[column] = pd.to_numeric(
                df[column], errors="coerce"
            )

            if not df[column].map(math.isfinite).all():
                return f"Invalid {column} values for {year}."

        df["product_name"] = df["product_name"].fillna(
            "Unknown product"
        )
        df["category_name"] = df["category_name"].fillna(
            "Uncategorized"
        )

        labels = df.groupby("product_id")[["product_name", "category_name"]].nunique()
        if (labels > 1).any().any():
            return f"Inconsistent product labels for {year}."

        datasets[year] = df

    def summarize(df, group_column):
        """Aggregate product/category sales quantities, revenue, COGS and gross profit.
        """
        summary = df.groupby(group_column).agg(
            units=("quantity", "sum"),
            revenue=("net_revenue", "sum"),
            cogs=("cogs", "sum")
        )

        summary["profit"] = (
            summary["revenue"] - summary["cogs"]
        )

        return summary

    def build_comparison(group_column):
        """Join the two yearly product/category summaries and calculate comparable changes.
        """
        base = summarize(datasets[base_year], group_column)
        current = summarize(
            datasets[comparison_year], group_column
        )

        joined = base.join(
            current,
            how="outer",
            lsuffix=f"_{base_year}",
            rsuffix=f"_{comparison_year}"
        )

        # Record presence before replacing absent sales with zero.
        in_base = joined.index.isin(base.index)
        in_current = joined.index.isin(current.index)

        joined["Sales presence"] = [
            "Both periods" if old and new
            else "Comparison only" if new
            else "Baseline only"
            for old, new in zip(in_base, in_current)
        ]

        amount_columns = [
            f"{metric}_{year}"
            for year in (base_year, comparison_year)
            for metric in ("units", "revenue", "cogs", "profit")
        ]

        joined[amount_columns] = (
            joined[amount_columns].fillna(0)
        )

        joined["profit_difference"] = (
            joined[f"profit_{comparison_year}"]
            - joined[f"profit_{base_year}"]
        )

        return joined.sort_values(
            "profit_difference", ascending=False
        )

    product_comparison = build_comparison("product_id")
    category_comparison = build_comparison("category_name")

    # Match products by ID, not by names that could be shared.
    # Prefer the comparison year's labels where available.
    labels = pd.concat(
        [datasets[base_year], datasets[comparison_year]],
        ignore_index=True
    ).drop_duplicates("product_id", keep="last")

    labels = labels.set_index("product_id")

    def format_comparison(comparison, product_level=False):
        """Format product/category comparison rows, including amounts, margins and changes.
        """
        rows = []

        for key, values in comparison.iterrows():
            row = {}

            if product_level:
                row["Product ID"] = key
                row["Product"] = labels.loc[key, "product_name"]
                row["Category"] = labels.loc[key, "category_name"]
            else:
                row["Category"] = key

            row["Sales presence"] = values["Sales presence"]

            for metric, label in (
                ("units", "Units"),
                ("revenue", "Revenue"),
                ("profit", "GP")
            ):
                old = values[f"{metric}_{base_year}"]
                new = values[f"{metric}_{comparison_year}"]

                for year, amount in (
                    (base_year, old),
                    (comparison_year, new)
                ):
                    row[f"{label} {year}"] = (
                        f"{amount:,.0f}"
                        if metric == "units"
                        else f"${amount:,.2f}"
                    )

                row[f"{label} change %"] = (
                    f"{(new - old) / old * 100:+.2f}%"
                    if old > 0
                    else "N/A"
                )

            row["GP change $"] = (
                f"${values['profit_difference']:+,.2f}"
            )

            margins = {}

            for year in (base_year, comparison_year):
                revenue = values[f"revenue_{year}"]
                profit = values[f"profit_{year}"]

                margins[year] = (
                    profit / revenue * 100
                    if revenue != 0
                    else None
                )

                row[f"Margin {year}"] = (
                    f"{margins[year]:.2f}%"
                    if margins[year] is not None
                    else "N/A"
                )

            old_margin = margins[base_year]
            new_margin = margins[comparison_year]

            row["Margin change"] = (
                f"{new_margin - old_margin:+.2f} pp"
                if old_margin is not None
                and new_margin is not None
                else "N/A"
            )

            rows.append(row)

        return pd.DataFrame(rows).to_string(index=False)

    # Reconcile grouped results against source totals or expected partitions.
    checks = {}

    for year in (base_year, comparison_year):
        source = datasets[year]

        expected = {
            "units": source["quantity"].sum(),
            "revenue": source["net_revenue"].sum(),
            "profit": (
                source["net_revenue"].sum()
                - source["cogs"].sum()
            )
        }

        for level, comparison in (
            ("Product", product_comparison),
            ("Category", category_comparison)
        ):
            for metric, total in expected.items():
                checks[f"{year} {level} {metric}"] = math.isclose(
                    comparison[f"{metric}_{year}"].sum(),
                    total,
                    rel_tol=0,
                    abs_tol=0.01
                )

    # Build deterministic observations from the calculated metrics.
    insights = []

    for level, comparison in (
        ("Product", product_comparison),
        ("Category", category_comparison)
    ):
        changes = comparison["profit_difference"]

        def get_name(key):
            """Choose the available descriptive label for a joined operating comparison row.
            """
            if level == "Product":
                return labels.loc[key, "product_name"]
            return str(key)

        biggest_gain = changes.idxmax()
        gain = changes.loc[biggest_gain]

        if gain > 0:
            insights.append(
                f"{level}: largest gross profit increase was "
                f"{get_name(biggest_gain)} (${gain:+,.2f})."
            )

        biggest_decline = changes.idxmin()
        decline = changes.loc[biggest_decline]

        if decline < 0:
            insights.append(
                f"{level}: largest gross profit decline was "
                f"{get_name(biggest_decline)} (${decline:+,.2f})."
            )

        old_revenue = comparison[f"revenue_{base_year}"]
        new_revenue = comparison[f"revenue_{comparison_year}"]
        old_profit = comparison[f"profit_{base_year}"]
        new_profit = comparison[f"profit_{comparison_year}"]

        # Compare margins only where both periods have positive revenue.
        comparable = (old_revenue > 0) & (new_revenue > 0)

        margin_changes = (
            new_profit[comparable] / new_revenue[comparable] * 100
            - old_profit[comparable] / old_revenue[comparable] * 100
        )

        if not margin_changes.empty:
            worst_margin = margin_changes.idxmin()
            margin_change = margin_changes.loc[worst_margin]

            if margin_change < 0:
                insights.append(
                    f"{level}: largest gross margin decline was "
                    f"{get_name(worst_margin)} "
                    f"({margin_change:+.2f} pp)."
                )

        revenue_up_profit_down = (
            (new_revenue > old_revenue)
            & (new_profit < old_profit)
        )

        flagged = comparison.loc[
            revenue_up_profit_down
        ].sort_values("profit_difference")

        if not flagged.empty:
            # Limit the list to keep the summary readable.
            names = [
                get_name(key)
                for key in flagged.head(5).index
            ]

            extra = (
                f" and {len(flagged) - 5} more"
                if len(flagged) > 5
                else ""
            )

            insights.append(
                f"{level}: revenue increased while gross profit "
                f"declined for {', '.join(names)}{extra}. "
                "Review costs, discounts, and sales mix."
            )

    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    return (
        "VENESSE PRODUCT AND CATEGORY COMPARISON\n"
        "Period: January–September | Delivered sales\n"
        f"Baseline: {base_year} | Comparison: {comparison_year}\n"
        "GP = gross profit | pp = percentage points\n"
        "Sorted by dollar change in gross profit, highest first.\n"
        "Absent sales are shown as zero; this does not establish "
        "a product launch or discontinuation.\n"
        "N/A = non-positive growth baseline or zero-revenue margin\n\n"
        "PRODUCT-LEVEL COMPARISON\n"
        f"{format_comparison(product_comparison, product_level=True)}\n\n"
        "CATEGORY-LEVEL COMPARISON\n"
        f"{format_comparison(category_comparison)}\n\n"
        "BUSINESS SUMMARY\n"
        "------------------------------\n"
        f"{summary_text or 'No changes to highlight.'}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def compare_marketing_years(base_year, comparison_year):
    """Compare campaign totals and channel performance between two years.
    Use aggregate ROAS/ROI, show absent-channel amounts as zero and reconcile totals.
    """
    if base_year == comparison_year:
        return "Please specify two different years."

    datasets = {}
    totals = {}
    channel_summaries = {}

    # Define the numeric source fields that must be usable before calculations.
    numeric_columns = (
        "campaign_cost",
        "num_of_clicks",
        "delivered_orders",
        "attributed_revenue",
        "attributed_cogs"
    )

    for year in (base_year, comparison_year):
        try:
            df = fetch_marketing_data(year)
        except pyodbc.Error:
            return f"Unable to retrieve marketing data for {year}."

        if df is None or df.empty:
            return f"No eligible marketing campaigns available for {year}."

        df = df.copy()

        if df["campaign_id"].isna().any():
            return f"Missing campaign IDs for {year}."

        if df["campaign_id"].duplicated().any():
            return f"Duplicate campaign IDs for {year}."

        for column in numeric_columns:
            df[column] = pd.to_numeric(
                df[column], errors="coerce"
            )

            if not df[column].map(math.isfinite).all():
                return f"Invalid or missing {column} for {year}."

        if (
            df[["campaign_cost", "num_of_clicks", "delivered_orders"]]
            < 0
        ).any().any():
            return f"Negative costs, clicks, or order counts for {year}."

        df["channel_name"] = df["channel_name"].fillna(
            "Unknown channel"
        )

        df["profit_after_marketing"] = (
            df["attributed_revenue"]
            - df["attributed_cogs"]
            - df["campaign_cost"]
        )

        datasets[year] = df

        revenue = df["attributed_revenue"].sum()
        cogs = df["attributed_cogs"].sum()
        spending = df["campaign_cost"].sum()
        profit = revenue - cogs - spending

        totals[year] = {
            "Eligible campaigns": len(df),
            "Attributed revenue": revenue,
            "Attributed COGS": cogs,
            "Marketing spending": spending,
            "Profit after marketing": profit,
            "ROAS": revenue / spending if spending > 0 else None,
            "Marketing ROI": (
                profit / spending * 100
                if spending > 0 else None
            )
        }

        channel_summaries[year] = df.groupby("channel_name").agg(
            revenue=("attributed_revenue", "sum"),
            cogs=("attributed_cogs", "sum"),
            spending=("campaign_cost", "sum"),
            profit=("profit_after_marketing", "sum")
        )

    # Overall comparison
    rows = []

    for metric in totals[base_year]:
        old = totals[base_year][metric]
        new = totals[comparison_year][metric]

        def format_value(value):
            """Format an operating comparison amount; show unavailable values as N/A.
            """
            if value is None:
                return "N/A"
            if metric == "Eligible campaigns":
                return f"{value:,}"
            if metric == "ROAS":
                return f"{value:.2f}x"
            if metric == "Marketing ROI":
                return f"{value:.2f}%"
            return f"${value:,.2f}"

        if old is None or new is None:
            change = "N/A"
        elif metric == "Marketing ROI":
            change = f"{new - old:+.2f} pp"
        elif metric == "ROAS":
            change = f"{new - old:+.2f}x"
        elif old > 0:
            change = f"{(new - old) / old * 100:+.2f}%"
        else:
            change = "N/A"

        rows.append({
            "Metric": metric,
            str(base_year): format_value(old),
            str(comparison_year): format_value(new),
            "Change": change
        })

    overall_text = pd.DataFrame(rows).to_string(index=False)

    # Channel comparison
    channels = channel_summaries[base_year].join(
        channel_summaries[comparison_year],
        how="outer",
        lsuffix=f"_{base_year}",
        rsuffix=f"_{comparison_year}"
    )

    channels["Presence"] = [
        "Both periods"
        if channel in channel_summaries[base_year].index
        and channel in channel_summaries[comparison_year].index
        else "Baseline only"
        if channel in channel_summaries[base_year].index
        else "Comparison only"
        for channel in channels.index
    ]

    amount_columns = [
        f"{metric}_{year}"
        for year in (base_year, comparison_year)
        for metric in ("revenue", "cogs", "spending", "profit")
    ]

    channels[amount_columns] = (
        channels[amount_columns].fillna(0)
    )

    channels["profit_change"] = (
        channels[f"profit_{comparison_year}"]
        - channels[f"profit_{base_year}"]
    )

    channels = channels.sort_values(
        "profit_change", ascending=False
    )

    channel_rows = []

    for channel, values in channels.iterrows():
        row = {
            "Channel": channel,
            "Presence": values["Presence"]
        }

        for metric, label in (
            ("revenue", "Revenue"),
            ("spending", "Spend"),
            ("profit", "Profit")
        ):
            old = values[f"{metric}_{base_year}"]
            new = values[f"{metric}_{comparison_year}"]

            row[f"{label} {base_year}"] = f"${old:,.2f}"
            row[f"{label} {comparison_year}"] = f"${new:,.2f}"
            row[f"{label} change %"] = (
                f"{(new - old) / old * 100:+.2f}%"
                if old > 0 else "N/A"
            )

        row["Profit change $"] = (
            f"${values['profit_change']:+,.2f}"
        )

        roi_values = {}

        for year in (base_year, comparison_year):
            spending = values[f"spending_{year}"]
            revenue = values[f"revenue_{year}"]
            profit = values[f"profit_{year}"]

            row[f"ROAS {year}"] = (
                f"{revenue / spending:.2f}x"
                if spending > 0 else "N/A"
            )

            roi_values[year] = (
                profit / spending * 100
                if spending > 0 else None
            )

            row[f"ROI {year}"] = (
                f"{roi_values[year]:.2f}%"
                if roi_values[year] is not None else "N/A"
            )

        old_roi = roi_values[base_year]
        new_roi = roi_values[comparison_year]

        row["ROI change"] = (
            f"{new_roi - old_roi:+.2f} pp"
            if old_roi is not None and new_roi is not None
            else "N/A"
        )

        channel_rows.append(row)

    channel_text = pd.DataFrame(channel_rows).to_string(
        index=False
    )

    # Business summary
    insights = []

    for metric in (
        "Attributed revenue",
        "Marketing spending",
        "Profit after marketing"
    ):
        old = totals[base_year][metric]
        new = totals[comparison_year][metric]

        insights.append(
            f"{metric} changed by ${new - old:+,.2f}."
        )

    best_channel = channels["profit_change"].idxmax()
    best_change = channels.loc[best_channel, "profit_change"]

    if best_change > 0:
        insights.append(
            "Largest channel increase in profit after marketing: "
            f"{best_channel} (${best_change:+,.2f})."
        )

    worst_channel = channels["profit_change"].idxmin()
    worst_change = channels.loc[worst_channel, "profit_change"]

    if worst_change < 0:
        insights.append(
            "Largest channel decline in profit after marketing: "
            f"{worst_channel} (${worst_change:+,.2f})."
        )

    insights.append(
        "Channel comparisons can reflect different campaigns "
        "and budgets; attributed results do not establish "
        "incremental marketing effectiveness."
    )

    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )

    # Reconcile channel totals with campaign totals.
    checks = {}

    metric_mapping = {
        "revenue": "Attributed revenue",
        "cogs": "Attributed COGS",
        "spending": "Marketing spending",
        "profit": "Profit after marketing"
    }

    for year in (base_year, comparison_year):
        for column, metric in metric_mapping.items():
            checks[f"{year} channel {column}"] = math.isclose(
                channels[f"{column}_{year}"].sum(),
                totals[year][metric],
                rel_tol=0,
                abs_tol=0.01
            )

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    return (
        "VENESSE MARKETING YEAR-OVER-YEAR COMPARISON\n"
        "Period: January–September | Delivered sales\n"
        "Campaigns must start and end within each year's period.\n"
        f"Baseline: {base_year} | Comparison: {comparison_year}\n"
        "Profit = attributed revenue - COGS - campaign spending\n"
        "pp = percentage points | x = revenue/spending multiple\n"
        "Absent channels show zero amounts; zero-cost ratios "
        "and growth from non-positive baselines show N/A.\n\n"
        "OVERALL PERFORMANCE\n"
        f"{overall_text}\n\n"
        "CHANNEL COMPARISON\n"
        f"{channel_text}\n\n"
        "BUSINESS SUMMARY\n"
        f"{summary_text}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def compare_feedback_years(base_year, comparison_year):
    """Compare rating, sentiment, complaint and regional feedback across two years.
    Use each year’s review population and distinguish unavailable regional rates.
    """
    if base_year == comparison_year:
        return "Please specify two different years."

    results = {}

    def classify_complaint(comment):
        """Map exact normalized negative-review comments to the established complaint categories.
        Use General Dissatisfaction as a fallback rather than inferring a root cause.
        """
        text = (
            ""
            if pd.isna(comment)
            else str(comment).strip().casefold()
        )

        if text == "slow delivery":
            return "Delivery"

        if text in (
            "product arrived damaged",
            "quality below expectation"
        ):
            return "Product Quality / Handling"

        return "General Dissatisfaction"

    for year in (base_year, comparison_year):
        try:
            df = fetch_feedback_data(year)
        except pyodbc.Error:
            return f"Unable to retrieve feedback data for {year}."

        if df is None or df.empty:
            return f"No customer feedback available for {year}."

        df = df.copy()

        if df["feedback_id"].isna().any():
            return f"Missing feedback IDs for {year}."

        if df["feedback_id"].duplicated().any():
            return f"Duplicate feedback IDs for {year}."

        df["out_of_5_star"] = pd.to_numeric(
            df["out_of_5_star"], errors="coerce"
        )

        if not df["out_of_5_star"].isin([1, 2, 3, 4, 5]).all():
            return f"Invalid or missing ratings for {year}."

        df["region"] = df["region"].fillna("Unknown region")
        df["negative"] = df["out_of_5_star"] <= 2

        total = len(df)
        positive = int((df["out_of_5_star"] >= 4).sum())
        neutral = int((df["out_of_5_star"] == 3).sum())
        negative = int(df["negative"].sum())

        ratings = (
            df["out_of_5_star"]
            .value_counts()
            .reindex([1, 2, 3, 4, 5], fill_value=0)
        )

        regions = df.groupby("region").agg(
            reviews=("feedback_id", "size"),
            negative=("negative", "sum")
        )

        complaints = (
            df.loc[df["negative"], "comments"]
            .map(classify_complaint)
            .value_counts()
            .reindex(
                [
                    "General Dissatisfaction",
                    "Product Quality / Handling",
                    "Delivery"
                ],
                fill_value=0
            )
        )

        results[year] = {
            "metrics": {
                "Total reviews": total,
                "Average rating": df["out_of_5_star"].mean(),
                "Positive reviews": positive,
                "Neutral reviews": neutral,
                "Negative reviews": negative,
                "Positive review rate": positive / total * 100,
                "Neutral review rate": neutral / total * 100,
                "Negative review rate": negative / total * 100
            },
            "ratings": ratings,
            "regions": regions,
            "complaints": complaints
        }

    base = results[base_year]["metrics"]
    current = results[comparison_year]["metrics"]

    # Overall KPIs
    overall_rows = []

    for metric, old in base.items():
        new = current[metric]

        if metric == "Average rating":
            old_text = f"{old:.2f} / 5"
            new_text = f"{new:.2f} / 5"
            change = f"{new - old:+.2f} rating points"

        elif metric.endswith("rate"):
            old_text = f"{old:.2f}%"
            new_text = f"{new:.2f}%"
            change = f"{new - old:+.2f} pp"

        else:
            old_text = f"{old:,}"
            new_text = f"{new:,}"
            change = (
                f"{(new - old) / old * 100:+.2f}%"
                if old > 0 else "N/A"
            )

        overall_rows.append({
            "Metric": metric,
            str(base_year): old_text,
            str(comparison_year): new_text,
            "Change": change
        })

    # Rating and complaint counts
    def compare_counts(key, label):
        """Build a two-year count comparison for a feedback distribution.
        """
        table = pd.concat(
            [
                results[base_year][key].rename(str(base_year)),
                results[comparison_year][key].rename(
                    str(comparison_year)
                )
            ],
            axis=1
        ).fillna(0).astype(int)

        table["Count change"] = (
            table[str(comparison_year)] - table[str(base_year)]
        )

        return table.rename_axis(label).reset_index()

    rating_table = compare_counts("ratings", "Rating")
    complaint_table = compare_counts(
        "complaints", "Complaint category"
    )

    # Regional comparison
    regions = results[base_year]["regions"].join(
        results[comparison_year]["regions"],
        how="outer",
        lsuffix=f"_{base_year}",
        rsuffix=f"_{comparison_year}"
    ).fillna(0)

    region_rows = []

    for region, values in regions.iterrows():
        row = {"Region": region}
        rates = {}

        for year in (base_year, comparison_year):
            reviews = int(values[f"reviews_{year}"])
            negative = int(values[f"negative_{year}"])

            rates[year] = (
                negative / reviews * 100
                if reviews > 0 else None
            )

            row[f"Reviews {year}"] = reviews
            row[f"Negative {year}"] = negative
            row[f"Negative % {year}"] = (
                f"{rates[year]:.2f}%"
                if rates[year] is not None else "N/A"
            )

        old_rate = rates[base_year]
        new_rate = rates[comparison_year]

        row["Negative rate change"] = (
            f"{new_rate - old_rate:+.2f} pp"
            if old_rate is not None and new_rate is not None
            else "N/A"
        )

        region_rows.append(row)

    # Business summary
    insights = [
        f"Average rating changed from "
        f"{base['Average rating']:.2f} to "
        f"{current['Average rating']:.2f} "
        f"({current['Average rating'] - base['Average rating']:+.2f} "
        "rating points).",
        "Positive-review rate changed by "
        f"{current['Positive review rate'] - base['Positive review rate']:+.2f} pp.",
        "Negative-review rate changed by "
        f"{current['Negative review rate'] - base['Negative review rate']:+.2f} pp."
    ]

    if current["Negative reviews"] > 0:
        counts = results[comparison_year]["complaints"]
        largest = counts.max()
        leaders = counts[counts == largest].index.tolist()

        insights.append(
            f"Largest complaint category or categories in "
            f"{comparison_year}: {', '.join(leaders)} "
            f"({int(largest)} negative reviews each)."
        )

    insights.append(
        "Review volumes and the customers submitting feedback "
        "can differ between years; these results do not track "
        "the same customer cohort."
    )

    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )

    # Reconcile grouped results against source totals or expected partitions.
    checks = {}

    for year in (base_year, comparison_year):
        result = results[year]
        metrics = result["metrics"]

        checks[f"{year} rating count"] = (
            result["ratings"].sum() == metrics["Total reviews"]
        )
        checks[f"{year} sentiment partition"] = (
            metrics["Positive reviews"]
            + metrics["Neutral reviews"]
            + metrics["Negative reviews"]
            == metrics["Total reviews"]
        )
        checks[f"{year} regional reviews"] = (
            result["regions"]["reviews"].sum()
            == metrics["Total reviews"]
        )
        checks[f"{year} regional negatives"] = (
            result["regions"]["negative"].sum()
            == metrics["Negative reviews"]
        )
        checks[f"{year} complaint count"] = (
            result["complaints"].sum()
            == metrics["Negative reviews"]
        )

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    return (
        "VENESSE CUSTOMER FEEDBACK COMPARISON\n"
        "Period: January–September, based on order date\n"
        "No delivered-status filter is applied.\n"
        f"Baseline: {base_year} | Comparison: {comparison_year}\n"
        "pp = percentage points\n"
        "N/A = zero baseline count or no regional reviews.\n\n"
        "OVERALL PERFORMANCE\n"
        f"{pd.DataFrame(overall_rows).to_string(index=False)}\n\n"
        "RATING DISTRIBUTION\n"
        f"{rating_table.to_string(index=False)}\n\n"
        "REGIONAL COMPARISON\n"
        f"{pd.DataFrame(region_rows).to_string(index=False)}\n\n"
        "NEGATIVE REVIEWS BY COMPLAINT CATEGORY\n"
        f"{complaint_table.to_string(index=False)}\n\n"
        "BUSINESS SUMMARY\n"
        f"{summary_text}\n\n"
        "VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


def compare_operating_years(base_year, comparison_year):
    """Validate and compare operating revenue, costs, profit and margin for two years.
    Reuse one validated dataset per year and explain the movement in profit.
    Separate campaign-cost treatment remains provisional.
    """
    if base_year == comparison_year:
        return "Please specify two different years."

    results = {}

    for year in (base_year, comparison_year):
        try:
            data = _load_operating_metrics(year)
        except pyodbc.Error:
            return f"Unable to retrieve operating data for {year}."
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            return f"Cannot compare operating performance: {error}"
        revenue = data['revenue']
        results[year] = {
            "metrics": {
                "Revenue": revenue,
                "COGS": data['cogs'],
                "Gross profit": data['gross_profit'],
                "Operating expenses": data['operating_expenses'],
                "Campaign costs": data['campaign_costs'],
                "Operating profit": data['operating_profit'],
                "Operating margin": data['operating_profit'] / revenue * 100 if revenue != 0 else None
            },
            "categories": data['categories']
        }

    base = results[base_year]["metrics"]
    current = results[comparison_year]["metrics"]

    rows = []

    for metric, old in base.items():
        new = current[metric]

        if metric == "Operating margin":
            old_text = f"{old:.2f}%" if old is not None else "N/A"
            new_text = f"{new:.2f}%" if new is not None else "N/A"
            amount_change = (
                f"{new - old:+.2f} pp"
                if old is not None and new is not None else "N/A"
            )
            percentage_change = "—"

        else:
            old_text = f"${old:,.2f}"
            new_text = f"${new:,.2f}"
            amount_change = f"${new - old:+,.2f}"
            percentage_change = (
                f"{(new - old) / old * 100:+.2f}%"
                if old > 0 else "N/A"
            )

        rows.append({
            "Metric": metric,
            str(base_year): old_text,
            str(comparison_year): new_text,
            "Amount / pp change": amount_change,
            "Change %": percentage_change
        })

    category_comparison = pd.concat(
        [
            results[base_year]["categories"].rename(
                str(base_year)
            ),
            results[comparison_year]["categories"].rename(
                str(comparison_year)
            )
        ],
        axis=1
    ).fillna(0)

    category_comparison["difference"] = (
        category_comparison[str(comparison_year)]
        - category_comparison[str(base_year)]
    )

    category_rows = []

    for category, values in category_comparison.sort_values(
        "difference", ascending=False
    ).iterrows():
        old = values[str(base_year)]
        new = values[str(comparison_year)]

        category_rows.append({
            "Category": category,
            str(base_year): f"${old:,.2f}",
            str(comparison_year): f"${new:,.2f}",
            "Expense change $": f"${new - old:+,.2f}",
            "Expense change %": (
                f"{(new - old) / old * 100:+.2f}%"
                if old > 0 else "N/A"
            )
        })

    profit_change = (
        current["Operating profit"] - base["Operating profit"]
    )

    direction = (
        "improved" if profit_change > 0
        else "declined" if profit_change < 0
        else "was unchanged"
    )

    # Build deterministic observations from the calculated metrics.
    insights = [
        f"Operating profit {direction}; the dollar change was "
        f"${profit_change:+,.2f}."
    ]

    if (
        base["Operating profit"] < 0
        and current["Operating profit"] < 0
        and profit_change > 0
    ):
        loss_reduction = (
            profit_change / abs(base["Operating profit"]) * 100
        )

        insights.append(
            f"The operating loss narrowed by {loss_reduction:.2f}%, "
            "but the comparison period remained loss-making."
        )

    old_margin = base["Operating margin"]
    new_margin = current["Operating margin"]

    if old_margin is not None and new_margin is not None:
        insights.append(
            "Operating margin changed by "
            f"{new_margin - old_margin:+.2f} percentage points."
        )

    insights.append(
        "Both years treat campaign costs as separate from operating "
        "expenses, provisionally, and assign full campaign costs "
        "to campaigns starting within January–September."
    )

    # Reconcile grouped results against source totals or expected partitions.
    checks = {}

    for year in (base_year, comparison_year):
        metrics = results[year]["metrics"]

        checks[f"{year} expense categories"] = math.isclose(
            results[year]["categories"].sum(),
            metrics["Operating expenses"],
            rel_tol=0,
            abs_tol=0.01
        )

    # Explain the profit movement through its three components.
    profit_bridge = (
        current["Gross profit"] - base["Gross profit"]
        - (
            current["Operating expenses"]
            - base["Operating expenses"]
        )
        - (
            current["Campaign costs"] - base["Campaign costs"]
        )
    )

    checks["Operating profit change bridge"] = math.isclose(
        profit_bridge,
        profit_change,
        rel_tol=0,
        abs_tol=0.01
    )

    # Format internal validation outcomes for the report footer.
    validation = "\n".join(
        f"{name}: {'PASS' if passed else 'FAIL'}"
        for name, passed in checks.items()
    )

    summary_text = "\n".join(
        f"- {insight}" for insight in insights
    )

    return (
        "VENESSE OPERATING YEAR-OVER-YEAR COMPARISON\n"
        "Period: January–September | Delivered sales\n"
        f"Baseline: {base_year} | Comparison: {comparison_year}\n"
        "Campaign costs treated as separate (provisional).\n"
        "N/A growth = non-positive baseline; "
        "margin changes use percentage points.\n"
        "Absent expense categories show zero recorded expenses.\n\n"
        "OVERALL PERFORMANCE\n"
        f"{pd.DataFrame(rows).to_string(index=False)}\n\n"
        "OPERATING EXPENSES BY CATEGORY\n"
        f"{pd.DataFrame(category_rows).to_string(index=False)}\n\n"
        "BUSINESS SUMMARY\n"
        f"{summary_text}\n\n"
        "FINANCIAL VALIDATION\n"
        f"{validation}\n"
        f"Overall: {'PASS' if all(checks.values()) else 'FAIL'}"
    )


# ============================================================================
# 5. COMBINED TXT REPORTS
# ============================================================================

def generate_full_business_report(year):
    """Assemble seven single-year TXT sections, including customer retention.
    Stop on the first section without Overall: PASS; return the combined report/error.
    """
    # List the component reports and the order used in the combined document.
    sections = [
        ("1. SALES OVERVIEW", generate_sales_report),
        ("2. CUSTOMER ANALYTICS", generate_customer_report),
        ("3. CUSTOMER RETENTION", generate_retention_report),
        ("4. MARKETING PERFORMANCE", generate_marketing_report),
        ("5. PRODUCT PROFITABILITY", generate_product_report),
        ("6. CUSTOMER FEEDBACK", generate_feedback_report),
        ("7. OPERATING PROFITABILITY", generate_operating_report)
    ]

    completed_sections = []

    for title, report_function in sections:
        report = report_function(year)

        # Stop if a section has missing data or fails validation.
        if report.splitlines()[-1:] != ["Overall: PASS"]:
            return (
                "Full business report could not be completed.\n"
                f"Section: {title}\n\n"
                f"{report}"
            )

        completed_sections.append(
            f"{'=' * 80}\n"
            f"{title}\n"
            f"{'=' * 80}\n\n"
            f"{report}"
        )

    body = "\n\n".join(completed_sections)

    return (
        f"VENESSE FULL BUSINESS REPORT — {year}\n"
        "Period: January–September\n"
        f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        "Seven business sections with internal validation.\n"
        "Sales-based sections use delivered sales; feedback "
        "uses order dates without a delivered-status filter.\n"
        "Marketing and operating sections use their respective "
        "campaign eligibility rules.\n"
        "Operating results treat campaign costs as separate "
        "from operating expenses (provisional).\n\n"
        f"{body}\n\n"
        f"{'=' * 80}\n"
        "FULL REPORT VALIDATION\n"
        "Completed sections: 7 / 7\n"
        "All section validation checks passed.\n"
        "Overall: PASS"
    )


def compare_full_business_report(base_year, comparison_year):
    """Assemble seven TXT comparisons after validating both years of sales.
    Include annual/monthly sales plus five other comparisons; retention stays separate.
    Stop on the first unsuccessful comparison.
    """
    if base_year == comparison_year:
        return "Please specify two different years."

    # Validate sales for both years before using the sales
    # comparison functions, which do not expose Overall statuses.
    for year in (base_year, comparison_year):
        report = generate_sales_report(year)

        if report.splitlines()[-1:] != ["Overall: PASS"]:
            return (
                "Full business comparison could not be completed.\n"
                f"Sales validation failed for {year}.\n\n"
                f"{report}"
            )

    # List the component reports and the order used in the combined document.
    sections = [
        (
            "1. ANNUAL SALES COMPARISON",
            compare_sales_years,
            "VENESSE YEAR-OVER-YEAR COMPARISON\n"
        ),
        (
            "2. MONTHLY SALES COMPARISON",
            compare_monthly_sales,
            "VENESSE MONTHLY YEAR-OVER-YEAR COMPARISON\n"
        ),
        (
            "3. CUSTOMER COMPARISON",
            compare_customer_years,
            None
        ),
        (
            "4. PRODUCT AND CATEGORY COMPARISON",
            compare_product_years,
            None
        ),
        (
            "5. MARKETING COMPARISON",
            compare_marketing_years,
            None
        ),
        (
            "6. CUSTOMER FEEDBACK COMPARISON",
            compare_feedback_years,
            None
        ),
        (
            "7. OPERATING COMPARISON",
            compare_operating_years,
            None
        )
    ]

    completed_sections = []

    for title, comparison_function, expected_header in sections:
        report = comparison_function(base_year, comparison_year)

        if expected_header is not None:
            successful = report.startswith(expected_header)
        else:
            successful = (
                report.splitlines()[-1:] == ["Overall: PASS"]
            )

        if not successful:
            return (
                "Full business comparison could not be completed.\n"
                f"Section: {title}\n\n"
                f"{report}"
            )

        completed_sections.append(
            f"{'=' * 80}\n"
            f"{title}\n"
            f"{'=' * 80}\n\n"
            f"{report}"
        )

    body = "\n\n".join(completed_sections)

    return (
        "VENESSE FULL BUSINESS COMPARISON\n"
        "Period: January–September, both years\n"
        f"Baseline: {base_year} | Comparison: {comparison_year}\n"
        f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        "Operating campaign costs remain separate (provisional).\n"
        "Cross-year customer retention is a separate report; "
        "customer comparison measures purchasing behavior.\n\n"
        f"{body}\n\n"
        "FULL COMPARISON VALIDATION\n"
        "Completed comparisons: 7 / 7\n"
        "Both years' sales reports passed validation.\n"
        "Sales comparisons generated successfully; "
        "they do not expose separate reconciliation statuses.\n"
        "All other comparison validation checks passed.\n"
        "Overall: PASS"
    )


# ============================================================================
# 6. TXT EXPORT FUNCTIONS
# ============================================================================

def export_sales_report(year, output_folder="reports"):
    """Generate and save the sales report as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = generate_sales_report(year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Report was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_sales_{year}_Jan-Sep",
            output_folder
        )
        return f"Report saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the report: {error}"


def export_customer_report(year, output_folder="reports"):
    """Generate and save the customer report as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = generate_customer_report(year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Customer report was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_customers_{year}_Jan-Sep",
            output_folder
        )

        return f"Customer report saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the customer report: {error}"


def export_retention_report(year, output_folder="reports"):
    """Generate and save the retention report as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = generate_retention_report(year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Retention report was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_retention_{year}_vs_{year - 1}_Jan-Sep",
            output_folder
        )

        return f"Retention report saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the retention report: {error}"


def export_product_report(year, output_folder="reports"):
    """Generate and save the product report as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = generate_product_report(year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Product report was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_products_{year}_Jan-Sep",
            output_folder
        )

        return f"Product report saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the product report: {error}"


def export_marketing_report(year, output_folder="reports"):
    """Generate and save the marketing report as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = generate_marketing_report(year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Marketing report was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_marketing_{year}_Jan-Sep",
            output_folder
        )

        return f"Marketing report saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the marketing report: {error}"


def export_feedback_report(year, output_folder="reports"):
    """Generate and save the feedback report as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = generate_feedback_report(year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Feedback report was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_feedback_{year}_Jan-Sep",
            output_folder
        )

        return f"Feedback report saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the feedback report: {error}"


def export_operating_report(year, output_folder="reports"):
    """Generate and save the operating report as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = generate_operating_report(year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Operating report was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_operating_{year}_Jan-Sep",
            output_folder
        )

        return f"Operating report saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the operating report: {error}"


def export_sales_comparison(
    base_year,
    comparison_year,
    output_folder="reports"
):
    """Generate and save the sales comparison as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = compare_sales_years(base_year, comparison_year)

    if not report.startswith("VENESSE YEAR-OVER-YEAR COMPARISON\n"):
        return f"Comparison was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_comparison_{base_year}_vs_{comparison_year}_Jan-Sep",
            output_folder
        )
        return f"Comparison saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the comparison: {error}"


def export_monthly_comparison(
    base_year,
    comparison_year,
    output_folder="reports"
):
    """Generate and save the monthly comparison as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = compare_monthly_sales(base_year, comparison_year)

    if not report.startswith(
        "VENESSE MONTHLY YEAR-OVER-YEAR COMPARISON\n"
    ):
        return f"Monthly comparison was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_monthly_comparison_"
            f"{base_year}_vs_{comparison_year}_Jan-Sep",
            output_folder
        )
        return f"Monthly comparison saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the monthly comparison: {error}"


def export_customer_comparison(
    base_year,
    comparison_year,
    output_folder="reports"
):
    """Generate and save the customer comparison as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = compare_customer_years(base_year, comparison_year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Customer comparison was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_customer_comparison_"
            f"{base_year}_vs_{comparison_year}_Jan-Sep",
            output_folder
        )

        return f"Customer comparison saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the customer comparison: {error}"


def export_product_comparison(
    base_year,
    comparison_year,
    output_folder="reports"
):
    """Generate and save the product comparison as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = compare_product_years(base_year, comparison_year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Product comparison was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_product_comparison_"
            f"{base_year}_vs_{comparison_year}_Jan-Sep",
            output_folder
        )

        return f"Product comparison saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the product comparison: {error}"


def export_marketing_comparison(
    base_year,
    comparison_year,
    output_folder="reports"
):
    """Generate and save the marketing comparison as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = compare_marketing_years(base_year, comparison_year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Marketing comparison was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_marketing_comparison_"
            f"{base_year}_vs_{comparison_year}_Jan-Sep",
            output_folder
        )

        return f"Marketing comparison saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the marketing comparison: {error}"


def export_feedback_comparison(
    base_year,
    comparison_year,
    output_folder="reports"
):
    """Generate and save the feedback comparison as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = compare_feedback_years(base_year, comparison_year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Feedback comparison was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_feedback_comparison_"
            f"{base_year}_vs_{comparison_year}_Jan-Sep",
            output_folder
        )

        return f"Feedback comparison saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the feedback comparison: {error}"


def export_operating_comparison(
    base_year,
    comparison_year,
    output_folder="reports"
):
    """Generate and save the operating comparison as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = compare_operating_years(base_year, comparison_year)

    if report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Operating comparison was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_operating_comparison_"
            f"{base_year}_vs_{comparison_year}_Jan-Sep",
            output_folder
        )

        return f"Operating comparison saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the operating comparison: {error}"


def export_full_business_report(year, output_folder="reports"):
    """Generate and save the full business report as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = generate_full_business_report(year)

    if not report.startswith(
        f"VENESSE FULL BUSINESS REPORT — {year}\n"
    ) or report.splitlines()[-1:] != ["Overall: PASS"]:
        return f"Full business report was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_full_business_{year}_Jan-Sep",
            output_folder
        )

        return f"Full business report saved successfully:\n{file_path}"

    except OSError as error:
        return f"Unable to save the full business report: {error}"


def export_full_business_comparison(
    base_year,
    comparison_year,
    output_folder="reports"
):
    """Generate and save the full business comparison as a timestamped TXT file.
    Check the existing report success marker before writing; return status/error text.
    """
    report = compare_full_business_report(
        base_year, comparison_year
    )

    if (
        not report.startswith("VENESSE FULL BUSINESS COMPARISON\n")
        or report.splitlines()[-1:] != ["Overall: PASS"]
    ):
        return f"Full business comparison was not saved.\n{report}"

    try:
        file_path = save_text_report(
            report,
            f"venesse_full_comparison_"
            f"{base_year}_vs_{comparison_year}_Jan-Sep",
            output_folder
        )

        return (
            "Full business comparison saved successfully:\n"
            f"{file_path}"
        )

    except OSError as error:
        return f"Unable to save the full business comparison: {error}"


# ============================================================================
# 7. HTML EXPORT ADAPTERS
# ============================================================================

def export_sales_html_report(year):
    """Save HTML; the commentary adapter opens the completed report."""
    try:
        return export_sales_html(
            year,
            fetch_sales_data,
            open_browser=False
        )
    except pyodbc.Error:
        return 'Unable to retrieve sales data for the HTML report.'


def export_customer_html_report(year):
    """Save HTML; the commentary adapter opens the completed report."""
    try:
        return export_customer_html(
            year,
            fetch_customer_sales_data,
            open_browser=False
        )
    except pyodbc.Error:
        return 'Unable to retrieve data for the customer HTML report.'


def export_product_html_report(year):
    """Save HTML; the commentary adapter opens the completed report."""
    try:
        return export_product_html(
            year,
            fetch_product_sales_data,
            open_browser=False
        )
    except pyodbc.Error:
        return 'Unable to retrieve data for the product HTML report.'


def export_retention_html_report(year):
    """Save HTML; the commentary adapter opens the completed report."""
    try:
        return export_retention_html(
            year,
            fetch_customer_sales_data,
            open_browser=False
        )
    except pyodbc.Error:
        return 'Unable to retrieve data for the retention HTML report.'


def export_marketing_html_report(year):
    """Save HTML; the commentary adapter opens the completed report."""
    try:
        return export_marketing_html(
            year,
            fetch_marketing_data,
            open_browser=False
        )
    except pyodbc.Error:
        return 'Unable to retrieve data for the marketing HTML report.'


def export_feedback_html_report(year):
    """Save HTML; the commentary adapter opens the completed report."""
    try:
        return export_feedback_html(
            year,
            fetch_feedback_data,
            open_browser=False
        )
    except pyodbc.Error:
        return 'Unable to retrieve data for the feedback HTML report.'


def export_operating_html_report(year):
    """Save HTML; the commentary adapter opens the completed report."""
    try:
        return export_operating_html(
            year,
            fetch_sales_data,
            fetch_operating_expenses,
            fetch_operating_campaign_costs,
            open_browser=False
        )
    except pyodbc.Error:
        return 'Unable to retrieve data for the operating HTML report.'


def export_full_html_report(year):
    """Save HTML; the commentary adapter opens the completed report."""
    try:
        return export_full_html(
            year,
            fetch_sales_data,
            fetch_customer_sales_data,
            fetch_product_sales_data,
            fetch_marketing_data,
            fetch_feedback_data,
            fetch_operating_expenses,
            fetch_operating_campaign_costs,
            open_browser=False
        )
    except pyodbc.Error:
        return 'Unable to retrieve data for the full HTML report.'


# ============================================================================
# 8. COMMAND PARSING, VALIDATION AND DISPATCH
# ============================================================================

def parse_business_request(task):
    """Translate supported keywords and explicit 20xx years into a request dictionary.
    Return action, years and export preference, or an error dictionary.
    This parser is rule-based and does not call an AI model or execute reports.
    """
    if not isinstance(task, str) or not task.strip():
        return {"error": "Please enter a business request."}

    task = task.lower().strip()

    if not re.search(
        r"\b(sales|revenue|report|product|products|profitability|"
        r"customer|customers|retention|retained|non-returning|"
        r"marketing|campaign|campaigns|feedback|review|reviews|satisfaction|operating|expenses|expense|business|full)\b",
        task
    ):
        return {"error": "Unsupported business request."}

    years = list(dict.fromkeys(
        int(year)
        for year in re.findall(r"\b20\d{2}\b", task)
    ))

    is_comparison = bool(
        re.search(r"\b(compare|comparison|versus|vs)\b", task)
    )

    is_export = bool(
        re.search(r"\b(export|save|download)\b", task)
    )

    # HTML report routing
    if re.search(r"\bhtml\b", task):
        if is_comparison:
            return {
                "error": (
                    "Specify one year for the HTML report. "
                    "The report uses the previous year where required."
                )
            }

        if len(years) != 1:
            return {
                "error": "Please specify one year for the HTML report."
            }

        if re.search(r"\bfull\b", task):
            action = "full_html"
        elif re.search(r"\b(operating|expenses|expense)\b", task):
            action = "operating_html"
        elif re.search(r"\b(feedback|review|reviews|satisfaction)\b", task):
            action = "feedback_html"
        elif re.search(r"\b(retention|retained|non-returning)\b", task):
            action = "retention_html"
        elif re.search(r"\b(marketing|campaign|campaigns)\b", task):
            action = "marketing_html"
        elif re.search(r"\b(product|products)\b", task):
            action = "product_html"
        elif re.search(r"\b(customer|customers)\b", task):
            action = "customer_html"
        else:
            action = "sales_html"

        return {
            "action": action,
            "years": years,
            "export": True
        }

    is_full_report = bool(
        re.search(r"\bfull\b", task)
        and re.search(r"\b(business|report)\b", task)
    )

    if is_full_report:
        if is_comparison:
            if len(years) != 2:
                return {
                    "error": "Please specify two different years to compare."
                }

            return {
                "action": "full_business_comparison",
                "years": years,
                "export": is_export
            }

        if len(years) != 1:
            return {
                "error": "Please specify one year for the full business report."
            }

        return {
            "action": "full_business_report",
            "years": years,
            "export": is_export
        }

    is_monthly = bool(
        re.search(r"\b(monthly|month|months)\b", task)
    )

    # Specific topics must be checked before general customer requests.
    if re.search(r"\b(feedback|review|reviews|satisfaction)\b", task):
        topic = "feedback"
    elif re.search(r"\b(retention|retained|non-returning)\b", task):
        topic = "retention"
    elif re.search(r"\b(operating|expenses|expense)\b", task):
        topic = "operating"
    elif re.search(r"\b(marketing|campaign|campaigns)\b", task):
        topic = "marketing"
    elif re.search(r"\b(product|products)\b", task):
        topic = "product"
    elif re.search(r"\b(customer|customers)\b", task):
        topic = "customer"
    else:
        topic = "sales"

    if topic == "retention":
        if is_comparison:
            return {"error": (
                "Retention uses one selected year and its previous-year cohort. "
                "Use: Generate retention report for 2026."
            )}
        if len(years) != 1:
            return {
                "error": (
                    "Please specify one year for retention. "
                    "The previous year is used as the baseline."
                )
            }

        return {
            "action": "retention_report",
            "years": years,
            "export": is_export
        }

    if topic == "operating" and is_comparison:
        if len(years) != 2:
            return {
                "error": "Please specify two different years to compare."
            }

        return {
            "action": "operating_comparison",
            "years": years,
            "export": is_export
        }


    if is_comparison:
        if len(years) != 2:
            return {
                "error": "Please specify two different years to compare."
            }

        comparison_actions = {
            "feedback": "feedback_comparison",
            "marketing": "marketing_comparison",
            "product": "product_comparison",
            "customer": "customer_comparison",
            "sales": (
                "monthly_comparison"
                if is_monthly else "year_comparison"
            )
        }

        action = comparison_actions[topic]

    else:
        if len(years) != 1:
            if topic == "sales":
                message = (
                    "Please specify a year."
                    if not years
                    else "For two years, use: Compare sales for 2025 and 2026."
                )
            else:
                message = (
                    f"Please specify one year for the {topic} report."
                )

            return {"error": message}

        action = f"{topic}_report"

    return {
        "action": action,
        "years": years,
        "export": is_export
    }


def validate_business_request(request):
    """Check the action allowlist, year count/range/uniqueness and Boolean export flag.
    Return None for an accepted request, otherwise a readable validation message.
    This checks request structure; dataset availability is checked by report functions.
    """
    if not isinstance(request, dict):
        return "Invalid request format."

    # Allow only known actions and their required number of year arguments.
    expected_year_counts = {
        "full_html": 1,
        "operating_html": 1,
        "feedback_html": 1,
        "marketing_html": 1,
        "retention_html": 1,
        "product_html": 1,
        "customer_html": 1,
        "sales_html": 1,
        "full_business_comparison": 2,
        "full_business_report": 1,
        "operating_comparison": 2,
        "operating_report": 1,
        "feedback_comparison": 2,
        "feedback_report": 1,
        "marketing_comparison": 2,
        "marketing_report": 1,
        "retention_report": 1,
        "customer_comparison": 2,
        "product_comparison": 2,
        "customer_report": 1,
        "product_report": 1,
        "sales_report": 1,
        "year_comparison": 2,
        "monthly_comparison": 2
    }

    action = request.get("action")

    if not isinstance(action, str) or action not in expected_year_counts:
        return "Unsupported business action."

    years = request.get("years")

    if not isinstance(years, list):
        return "Years must be provided as a list."

    if len(years) != expected_year_counts[action]:
        return (
            f"{action} requires "
            f"{expected_year_counts[action]} year(s)."
        )

    if any(type(year) is not int for year in years):
        return "Each year must be an integer."

    if any(not 2000 <= year <= 2099 for year in years):
        return "Supported years are 2000–2099."

    if len(set(years)) != len(years):
        return "Please specify two different years to compare."

    if type(request.get("export")) is not bool:
        return "Export preference must be True or False."

    if action.endswith("_html") and not request["export"]:
        return "HTML reports require export=True."

    return None


@track_request_usage
def business_agent(task):
    """Parse a text command, validate its structure and dispatch to a report handler.
    Pass the parsed years to the selected function and return its result string.
    """
    request = interpret_business_request(
        task,
        parse_business_request,
        validate_business_request
    )

    if "error" in request:
        return request["error"]

    validation_error = validate_business_request(request)

    if validation_error is not None:
        return validation_error

    # Map each action/export pair to the existing report or export function.
    handlers = {
        ("full_html", True): export_full_html_report,
        ("operating_html", True): export_operating_html_report,
        ("feedback_html", True): export_feedback_html_report,
        ("marketing_html", True): export_marketing_html_report,
        ("retention_html", True): export_retention_html_report,
        ("product_html", True): export_product_html_report,
        ("customer_html", True): export_customer_html_report,
        ("sales_html", True): export_sales_html_report,
        ("full_business_comparison", False): compare_full_business_report,
        ("full_business_comparison", True): export_full_business_comparison,
        ("full_business_report", False): generate_full_business_report,
        ("full_business_report", True): export_full_business_report,
        ("operating_comparison", True): export_operating_comparison,
        ("operating_comparison", False): compare_operating_years,
        ("operating_report", True): export_operating_report,
        ("operating_report", False): generate_operating_report,
        ("feedback_comparison", True): export_feedback_comparison,
        ("feedback_comparison", False): compare_feedback_years,
        ("feedback_report", True): export_feedback_report,
        ("feedback_report", False): generate_feedback_report,
        ("marketing_comparison", True): export_marketing_comparison,
        ("marketing_comparison", False): compare_marketing_years,
        ("marketing_report", True): export_marketing_report,
        ("marketing_report", False): generate_marketing_report,
        ("retention_report", True): export_retention_report,
        ("retention_report", False): generate_retention_report,
        ("customer_comparison", True): export_customer_comparison,
        ("customer_comparison", False): compare_customer_years,
        ("product_comparison", True): export_product_comparison,
        ("product_comparison", False): compare_product_years,
        ("customer_report", True): export_customer_report,
        ("customer_report", False): generate_customer_report,
        ("product_report", True): export_product_report,
        ("product_report", False): generate_product_report,
        ("sales_report", False): generate_sales_report,
        ("sales_report", True): export_sales_report,
        ("year_comparison", False): compare_sales_years,
        ("year_comparison", True): export_sales_comparison,
        ("monthly_comparison", False): compare_monthly_sales,
        ("monthly_comparison", True): export_monthly_comparison
    }

    handler = handlers.get((request["action"], request["export"]))
    if handler is None:
        return "Unsupported business action/export combination."

    result = handler(*request["years"])

    return add_ai_summary_to_result(
        result,
        request
    )


# ============================================================================
# 9. INTERACTIVE ENTRY POINT
# ============================================================================

def main():
    """Run the interactive command prompt until the user enters exit or quit.
    Send each request through business_agent and print its returned report/status.
    """

    print("Venesse Business Agent")
    print("Example: Analyze sales for 2026")
    print("Example: Export sales report for 2026")
    print("Type 'exit' to quit.")

    while True:
        task = input("\nEnter your request: ").strip()

        if task.lower() in {"exit", "quit"}:
            print("Session ended.")
            break

        print()
        print(business_agent(task))


if __name__ == "__main__":
    main()
