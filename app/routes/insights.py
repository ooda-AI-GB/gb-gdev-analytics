from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import AIInsight, DataSource, DataRecord
from app.routes import get_current_user, get_active_subscription
from typing import Any
import json
import os
from datetime import datetime, timedelta

try:
    from google import genai
except ImportError:
    genai = None

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/insights", response_class=HTMLResponse)
async def list_insights(
    request: Request,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    # Fetch user's insights (linked to sources owned by user)
    # Join Source to filter by user
    insights = db.query(AIInsight).join(DataSource).filter(DataSource.user_id == user.id).order_by(desc(AIInsight.created_at)).all()
    
    return templates.TemplateResponse("insights/list.html", {"request": request, "user": user, "insights": insights})

@router.post("/api/insights/generate")
async def generate_insights(
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not genai:
        return JSONResponse({"error": "AI not available"}, status_code=503)

    # Gather data
    sources = db.query(DataSource).filter(DataSource.user_id == user.id, DataSource.status == "active").all()
    if not sources:
        return JSONResponse({"message": "No active data sources"}, status_code=400)
    
    context = ""
    for s in sources:
        records = db.query(DataRecord).filter(DataRecord.source_id == s.id).order_by(desc(DataRecord.record_date)).limit(20).all()
        data_sample = [json.loads(r.data) for r in records]
        context += f"Source: {s.name} ({s.source_type})\nData: {json.dumps(data_sample)}\n\n"
        
    prompt = f"""Analyze this business data. Identify: anomalies (unusual values), trends (increasing/decreasing patterns), correlations (fields that move together), forecasts (next period predictions), and recommendations (actionable advice).
    
    Return ONLY a JSON array of objects with this schema:
    [
        {{
            "type": "anomaly" | "trend" | "correlation" | "forecast" | "recommendation",
            "title": "Short title",
            "description": "Detailed explanation",
            "severity": "info" | "warning" | "critical"
        }}
    ]
    
    Data:
    {context}
    """
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        # Parse JSON
        insights_data = json.loads(response.text)
        
        count = 0
        for item in insights_data:
            insight = AIInsight(
                # Link to first source for simplicity or leave null if global
                source_id=sources[0].id if sources else None,
                insight_type=item.get("type", "trend"),
                title=item.get("title", "Insight"),
                description=item.get("description", ""),
                severity=item.get("severity", "info"),
                model_used="gemini-2.5-flash"
            )
            db.add(insight)
            count += 1
            
        db.commit()
        return JSONResponse({"count": count})
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
