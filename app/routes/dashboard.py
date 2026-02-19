from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Dashboard, Widget
from app.routes import get_current_user, get_active_subscription
from app.seed import seed_analytics
from typing import Any

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    # Seed data if empty
    seed_analytics(db, user.id)

    # Try to find default dashboard
    dashboard = db.query(Dashboard).filter(
        Dashboard.user_id == user.id, 
        Dashboard.is_default == True
    ).first()
    
    # Fallback to first dashboard
    if not dashboard:
        dashboard = db.query(Dashboard).filter(
            Dashboard.user_id == user.id
        ).order_by(Dashboard.created_at).first()
    
    widgets = []
    if dashboard:
        widgets = db.query(Widget).filter(Widget.dashboard_id == dashboard.id).all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": user, 
        "dashboard": dashboard,
        "widgets": widgets
    })
