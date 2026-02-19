from fastapi import APIRouter, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import DataSource, DataRecord
from app.routes import get_current_user, get_active_subscription
from typing import Any, Optional
import csv
import io
import json
from datetime import datetime, date

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/sources", response_class=HTMLResponse)
async def list_sources(
    request: Request,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    sources = db.query(DataSource).filter(DataSource.user_id == user.id).order_by(desc(DataSource.updated_at)).all()
    return templates.TemplateResponse("sources/list.html", {"request": request, "user": user, "sources": sources})

@router.get("/sources/new", response_class=HTMLResponse)
async def new_source_form(
    request: Request,
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    return templates.TemplateResponse("sources/form.html", {"request": request, "user": user})

@router.post("/sources/new/csv")
async def upload_csv_source(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    # Create Source
    source = DataSource(
        user_id=user.id,
        name=name,
        source_type="csv_upload",
        description=description,
        status="active"
    )
    db.add(source)
    db.flush() # Get ID

    try:
        content = await file.read()
        decoded = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        
        records = []
        fieldnames = reader.fieldnames or []
        
        # Identify date column
        date_col = None
        for col in fieldnames:
            if "date" in col.lower() or "time" in col.lower():
                date_col = col
                break
        
        count = 0
        for row in reader:
            record_date = datetime.now().date()
            if date_col and row.get(date_col):
                try:
                    # Try parsing common formats
                    dt = datetime.strptime(row[date_col], "%Y-%m-%d")
                    record_date = dt.date()
                except:
                    try:
                         dt = datetime.strptime(row[date_col], "%m/%d/%Y")
                         record_date = dt.date()
                    except:
                        pass # Fallback to today
            
            # Store row data as JSON
            data_json = json.dumps(row)
            
            record = DataRecord(
                source_id=source.id,
                data=data_json,
                record_date=record_date
            )
            db.add(record)
            count += 1
        
        source.row_count = count
        source.config = json.dumps({"fields": fieldnames, "date_col": date_col})
        source.last_synced_at = datetime.now()
        
        db.commit()
        return RedirectResponse(url=f"/sources/{source.id}", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to process CSV: {str(e)}")

@router.post("/sources/new/manual")
async def create_manual_source(
    request: Request,
    name: str = Form(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    source = DataSource(
        user_id=user.id,
        name=name,
        source_type="manual_entry",
        description=description,
        status="active"
    )
    db.add(source)
    db.commit()
    return RedirectResponse(url=f"/sources/{source.id}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/sources/{id}", response_class=HTMLResponse)
async def view_source(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    source = db.query(DataSource).filter(DataSource.id == id, DataSource.user_id == user.id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
        
    records = db.query(DataRecord).filter(DataRecord.source_id == source.id).order_by(desc(DataRecord.record_date)).limit(20).all()
    
    # Parse data for display
    display_records = []
    for r in records:
        try:
            d = json.loads(r.data)
            d['record_date'] = r.record_date
            display_records.append(d)
        except:
            pass
            
    fields = []
    if source.config:
        try:
            config = json.loads(source.config)
            fields = config.get("fields", [])
        except:
            pass
            
    # If manual, extract fields from first record if config empty
    if not fields and display_records:
        fields = [k for k in display_records[0].keys() if k != 'record_date']

    return templates.TemplateResponse("sources/detail.html", {
        "request": request, 
        "user": user, 
        "source": source,
        "records": display_records,
        "fields": fields
    })

@router.post("/sources/{id}/delete")
async def delete_source(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    source = db.query(DataSource).filter(DataSource.id == id, DataSource.user_id == user.id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
        
    db.delete(source)
    db.commit()
    return RedirectResponse(url="/sources", status_code=status.HTTP_303_SEE_OTHER)
