from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Widget, Dashboard, DataRecord, DataSource
from app.routes import get_current_user, get_active_subscription
from typing import Any, Optional
import json
from datetime import datetime, timedelta

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/api/widgets/{id}/data")
async def get_widget_data(
    id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    widget = db.query(Widget).filter(Widget.id == id).first()
    if not widget:
        return JSONResponse({"error": "Widget not found"}, status_code=404)
        
    # Check access (via dashboard)
    dashboard = db.query(Dashboard).filter(Dashboard.id == widget.dashboard_id, Dashboard.user_id == user.id).first()
    if not dashboard:
        # Check if shared? (Simplification: only owner for now or shared logic)
        if not widget.dashboard.shared:
             return JSONResponse({"error": "Access denied"}, status_code=403)

    if not widget.source_id:
        return JSONResponse({"labels": [], "datasets": []})

    records = db.query(DataRecord).filter(DataRecord.source_id == widget.source_id).all()
    
    # Simple processing
    try:
        config = json.loads(widget.config or "{}")
        field = config.get("field") or config.get("y_field")
        agg = config.get("aggregation", "sum")
        
        data_points = []
        for r in records:
            d = json.loads(r.data)
            val = d.get(field, 0)
            try:
                val = float(val)
            except:
                val = 0
            data_points.append({"date": r.record_date, "value": val})
            
        # Group by date (simple sum by month or raw)
        # For now, return raw sorted by date
        data_points.sort(key=lambda x: x["date"])
        
        labels = [d["date"].isoformat() for d in data_points]
        values = [d["value"] for d in data_points]
        
        return JSONResponse({
            "labels": labels,
            "datasets": [{
                "label": field,
                "data": values
            }],
            "type": widget.widget_type,
            "config": config
        })
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/dashboards/{id}/widgets")
async def create_widget(
    id: int,
    title: str = Form(...),
    widget_type: str = Form(...),
    source_id: int = Form(...),
    config: str = Form("{}"),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    # Verify dashboard ownership
    dashboard = db.query(Dashboard).filter(Dashboard.id == id, Dashboard.user_id == user.id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    widget = Widget(
        dashboard_id=id,
        title=title,
        widget_type=widget_type,
        source_id=source_id,
        config=config,
        position_x=0,
        position_y=0,
        width=4,
        height=2
    )
    db.add(widget)
    db.commit()
    return RedirectResponse(url=f"/dashboards/{id}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/widgets/{id}/delete")
async def delete_widget(
    id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    widget = db.query(Widget).filter(Widget.id == id).first()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
        
    # Check ownership
    dashboard = db.query(Dashboard).filter(Dashboard.id == widget.dashboard_id, Dashboard.user_id == user.id).first()
    if not dashboard:
        raise HTTPException(status_code=403, detail="Access denied")
        
    db.delete(widget)
    db.commit()
    return RedirectResponse(url=f"/dashboards/{dashboard.id}", status_code=status.HTTP_303_SEE_OTHER)
