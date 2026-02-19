from sqlalchemy.orm import Session
from app.models import DataSource, DataRecord, Dashboard, Widget, SavedQuery, AIInsight, ScheduledReport
from datetime import datetime, date, timedelta
import json
import random

def seed_analytics(db: Session, user_id: int):
    # Check if data exists for this user
    if db.query(DataSource).filter(DataSource.user_id == user_id).first():
        return

    # --- SOURCE 1: Monthly Revenue ---
    revenue_source = DataSource(
        user_id=user_id,
        name="Monthly Revenue",
        source_type="csv_upload",
        description="Revenue, expenses, and customer metrics",
        status="active",
        config=json.dumps({"fields": ["revenue", "expenses", "profit", "customers", "churn_rate", "mrr", "arr"], "date_col": "date"})
    )
    db.add(revenue_source)
    db.flush()

    start_date = date(2025, 3, 1)
    
    # Generate 12 months
    for i in range(12):
        curr_date = (start_date.replace(day=1) + timedelta(days=32*i)).replace(day=1)
        
        # Linear growth approx
        progress = i / 11.0
        
        revenue = 45000 + (37000 * progress) + random.randint(-1000, 1000)
        expenses = 30000 + (8000 * random.random())
        profit = revenue - expenses
        customers = int(120 + (190 * progress) + random.randint(-5, 5))
        churn_rate = 8.2 - (4.1 * progress) + (random.random() * 0.5)
        mrr = revenue # Approx
        arr = mrr * 12
        
        data = {
            "revenue": round(revenue, 2),
            "expenses": round(expenses, 2),
            "profit": round(profit, 2),
            "customers": customers,
            "churn_rate": round(churn_rate, 2),
            "mrr": round(mrr, 2),
            "arr": round(arr, 2)
        }
        
        record = DataRecord(
            source_id=revenue_source.id,
            record_date=curr_date,
            data=json.dumps(data)
        )
        db.add(record)
    
    revenue_source.row_count = 12
    revenue_source.last_synced_at = datetime.now()

    # --- SOURCE 2: Sales Pipeline ---
    pipeline_source = DataSource(
        user_id=user_id,
        name="Sales Pipeline",
        source_type="csv_upload",
        description="Pipeline health and conversion metrics",
        status="active",
        config=json.dumps({"fields": ["deals_created", "deals_won", "deals_lost", "pipeline_value", "avg_deal_size", "conversion_rate", "sales_cycle_days"], "date_col": "date"})
    )
    db.add(pipeline_source)
    db.flush()

    for i in range(12):
        curr_date = (start_date.replace(day=1) + timedelta(days=32*i)).replace(day=1)
        progress = i / 11.0
        
        deals_created = int(25 + (30 * progress) + random.randint(-2, 2))
        win_rate = 0.22 + (0.12 * progress)
        deals_won = int(deals_created * win_rate)
        deals_lost = deals_created - deals_won
        avg_deal_size = 8000 + (6000 * progress)
        pipeline_value = deals_created * avg_deal_size
        sales_cycle = 45 - (13 * progress)
        
        data = {
            "deals_created": deals_created,
            "deals_won": deals_won,
            "deals_lost": deals_lost,
            "pipeline_value": round(pipeline_value, 2),
            "avg_deal_size": round(avg_deal_size, 2),
            "conversion_rate": round(win_rate * 100, 1),
            "sales_cycle_days": round(sales_cycle, 1)
        }
        
        record = DataRecord(
            source_id=pipeline_source.id,
            record_date=curr_date,
            data=json.dumps(data)
        )
        db.add(record)

    pipeline_source.row_count = 12
    pipeline_source.last_synced_at = datetime.now()

    # --- DASHBOARD ---
    dashboard = Dashboard(
        user_id=user_id,
        name="Business Overview",
        description="Key performance indicators for executive review",
        is_default=True,
        layout=json.dumps({}) # Placeholder
    )
    db.add(dashboard)
    db.flush()

    # --- WIDGETS ---
    widgets_data = [
        {
            "title": "Monthly Revenue",
            "widget_type": "metric_card",
            "source_id": revenue_source.id,
            "config": json.dumps({"field": "revenue", "aggregation": "sum", "format": "currency", "trend": "up"}),
            "x": 0, "y": 0, "w": 4, "h": 2
        },
        {
            "title": "Total Customers",
            "widget_type": "metric_card",
            "source_id": revenue_source.id,
            "config": json.dumps({"field": "customers", "aggregation": "max", "format": "number", "trend": "up"}),
            "x": 4, "y": 0, "w": 4, "h": 2
        },
        {
            "title": "Churn Rate",
            "widget_type": "metric_card",
            "source_id": revenue_source.id,
            "config": json.dumps({"field": "churn_rate", "aggregation": "avg", "format": "percent", "trend": "down"}),
            "x": 8, "y": 0, "w": 4, "h": 2
        },
        {
            "title": "Revenue Trend",
            "widget_type": "line_chart",
            "source_id": revenue_source.id,
            "config": json.dumps({"y_field": "revenue", "x_field": "date", "aggregation": "sum"}),
            "x": 0, "y": 2, "w": 8, "h": 4
        },
        {
            "title": "Deals Won vs Lost",
            "widget_type": "bar_chart",
            "source_id": pipeline_source.id,
            "config": json.dumps({"fields": ["deals_won", "deals_lost"], "x_field": "date", "aggregation": "sum"}),
            "x": 8, "y": 2, "w": 4, "h": 4
        },
        {
            "title": "MRR Growth",
            "widget_type": "trend_indicator",
            "source_id": revenue_source.id,
            "config": json.dumps({"field": "mrr", "compare_period": "month"}),
            "x": 0, "y": 6, "w": 4, "h": 2
        }
    ]

    for w in widgets_data:
        widget = Widget(
            dashboard_id=dashboard.id,
            title=w["title"],
            widget_type=w["widget_type"],
            source_id=w["source_id"],
            config=w["config"],
            position_x=w["x"],
            position_y=w["y"],
            width=w["w"],
            height=w["h"]
        )
        db.add(widget)

    # --- INSIGHTS ---
    insights = [
        {
            "source_id": revenue_source.id,
            "type": "trend",
            "severity": "info",
            "title": "Revenue Accelerating",
            "description": "Revenue growth rate increased from 5% to 12% month-over-month in the last quarter. This acceleration correlates with the improved sales conversion rate."
        },
        {
            "source_id": revenue_source.id,
            "type": "anomaly",
            "severity": "warning",
            "title": "Churn Spike in October",
            "description": "October churn rate of 6.8% was 65% higher than the 3-month average. This coincided with a pricing change. Monitor closely."
        },
        {
            "source_id": pipeline_source.id,
            "type": "recommendation",
            "severity": "info",
            "title": "Optimize Sales Cycle",
            "description": "Deals that include a technical demo close 40% faster. Consider making demos a standard pipeline stage."
        }
    ]

    for i in insights:
        insight = AIInsight(
            source_id=i["source_id"],
            dashboard_id=dashboard.id,
            insight_type=i["type"],
            severity=i["severity"],
            title=i["title"],
            description=i["description"],
            model_used="gemini-2.5-flash"
        )
        db.add(insight)

    # --- SAVED QUERIES ---
    queries = [
        {
            "name": "Quarterly Revenue Summary",
            "nl": "What was total revenue by quarter?",
            "sql": "SELECT strftime('%Y-Q%m', record_date) as quarter, SUM(json_extract(data, '$.revenue')) as total_revenue FROM data_records GROUP BY quarter"
        },
        {
            "name": "Best Month for Deals",
            "nl": "Which month had the highest number of deals won?",
            "sql": "SELECT record_date, json_extract(data, '$.deals_won') as won FROM data_records ORDER BY won DESC LIMIT 1"
        }
    ]

    for q in queries:
        query = SavedQuery(
            user_id=user_id,
            name=q["name"],
            natural_language=q["nl"],
            generated_sql=q["sql"]
        )
        db.add(query)

    db.commit()
