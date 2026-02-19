from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Dashboard, Widget
from app.routes import get_current_user, get_active_subscription
from typing import Any, Optional

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/dashboards", response_class=HTMLResponse)
async def list_dashboards(
    request: Request,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    dashboards = db.query(Dashboard).filter(Dashboard.user_id == user.id).order_by(desc(Dashboard.updated_at)).all()
    # Count widgets for each dashboard
    for d in dashboards:
        d.widget_count = db.query(Widget).filter(Widget.dashboard_id == d.id).count()
        
    return templates.TemplateResponse("dashboards/list.html", {
        "request": request, 
        "user": user, 
        "dashboards": dashboards
    })

@router.get("/dashboards/new", response_class=HTMLResponse)
async def new_dashboard_form(
    request: Request,
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    return templates.TemplateResponse("dashboards/form.html", {"request": request, "user": user})

@router.post("/dashboards/new")
async def create_dashboard(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    is_default: bool = Form(False),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    if is_default:
        # Unset other defaults
        db.query(Dashboard).filter(Dashboard.user_id == user.id).update({"is_default": False})
    
    new_dashboard = Dashboard(
        user_id=user.id,
        name=name,
        description=description,
        is_default=is_default
    )
    db.add(new_dashboard)
    db.commit()
    db.refresh(new_dashboard)
    return RedirectResponse(url=f"/dashboards/{new_dashboard.id}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/dashboards/{id}", response_class=HTMLResponse)
async def view_dashboard(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    dashboard = db.query(Dashboard).filter(Dashboard.id == id, Dashboard.user_id == user.id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    
    widgets = db.query(Widget).filter(Widget.dashboard_id == dashboard.id).all()
    
    return templates.TemplateResponse("dashboards/view.html", {
        "request": request, 
        "user": user, 
        "dashboard": dashboard,
        "widgets": widgets
    })

@router.get("/dashboards/{id}/edit", response_class=HTMLResponse)
async def edit_dashboard_form(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    dashboard = db.query(Dashboard).filter(Dashboard.id == id, Dashboard.user_id == user.id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
        
    return templates.TemplateResponse("dashboards/form.html", {
        "request": request, 
        "user": user, 
        "dashboard": dashboard
    })

@router.post("/dashboards/{id}/edit")
async def update_dashboard(
    request: Request,
    id: int,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    dashboard = db.query(Dashboard).filter(Dashboard.id == id, Dashboard.user_id == user.id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    
    dashboard.name = name
    dashboard.description = description
    db.commit()
    
    return RedirectResponse(url=f"/dashboards/{id}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/dashboards/{id}/default")
async def set_default_dashboard(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    dashboard = db.query(Dashboard).filter(Dashboard.id == id, Dashboard.user_id == user.id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    
    # Unset other defaults
    db.query(Dashboard).filter(Dashboard.user_id == user.id).update({"is_default": False})
    
    dashboard.is_default = True
    db.commit()
    
    # Referrer or dashboard view
    return RedirectResponse(url=f"/dashboards/{id}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/dashboards/{id}/delete")
async def delete_dashboard(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    dashboard = db.query(Dashboard).filter(Dashboard.id == id, Dashboard.user_id == user.id).first()
    if not dashboard:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    
    db.delete(dashboard)
    db.commit()
    
    return RedirectResponse(url="/dashboards", status_code=status.HTTP_303_SEE_OTHER)
