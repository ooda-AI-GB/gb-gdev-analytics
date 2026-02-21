from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import (
    AIInsight,
    Dashboard,
    DataRecord,
    DataSource,
    SavedQuery,
    ScheduledReport,
    Widget,
)
from app.database import get_db
from app.routes import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_dict(obj) -> dict:
    """Convert a SQLAlchemy model instance to a plain dict, serialising dates."""
    result = {}
    for column in obj.__table__.columns:
        value = getattr(obj, column.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, date):
            value = value.isoformat()
        result[column.name] = value
    return result


def get_or_404(db: Session, model, id_val: int, label: str):
    """Fetch a row by primary key or raise HTTP 404."""
    obj = db.get(model, id_val)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{label} {id_val} not found")
    return obj


# ---------------------------------------------------------------------------
# Pydantic schemas – Create
# ---------------------------------------------------------------------------

class DataSourceCreate(BaseModel):
    name: str
    source_type: str
    description: Optional[str] = None
    config: Optional[str] = None
    status: Optional[str] = "active"


class DataRecordCreate(BaseModel):
    source_id: int
    data: str
    record_date: date


class DashboardCreate(BaseModel):
    name: str
    description: Optional[str] = None
    layout: Optional[str] = None
    is_default: Optional[bool] = False
    shared: Optional[bool] = False


class WidgetCreate(BaseModel):
    dashboard_id: int
    title: str
    widget_type: str
    source_id: Optional[int] = None
    config: Optional[str] = None
    position_x: Optional[int] = 0
    position_y: Optional[int] = 0
    width: Optional[int] = 4
    height: Optional[int] = 2


class SavedQueryCreate(BaseModel):
    name: str
    natural_language: str
    generated_sql: Optional[str] = None
    result_cache: Optional[str] = None


class ScheduledReportCreate(BaseModel):
    name: str
    dashboard_id: int
    frequency: str
    recipients: Optional[str] = None
    next_send_at: datetime
    enabled: Optional[bool] = True


class AIInsightCreate(BaseModel):
    source_id: Optional[int] = None
    dashboard_id: Optional[int] = None
    insight_type: str
    title: str
    description: str
    severity: str
    data_context: Optional[str] = None
    model_used: Optional[str] = None
    acknowledged: Optional[bool] = False


# ---------------------------------------------------------------------------
# Pydantic schemas – Update (all fields Optional)
# ---------------------------------------------------------------------------

class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    description: Optional[str] = None
    config: Optional[str] = None
    row_count: Optional[int] = None
    status: Optional[str] = None


class DataRecordUpdate(BaseModel):
    source_id: Optional[int] = None
    data: Optional[str] = None
    record_date: Optional[date] = None


class DashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    layout: Optional[str] = None
    is_default: Optional[bool] = None
    shared: Optional[bool] = None


class WidgetUpdate(BaseModel):
    dashboard_id: Optional[int] = None
    title: Optional[str] = None
    widget_type: Optional[str] = None
    source_id: Optional[int] = None
    config: Optional[str] = None
    position_x: Optional[int] = None
    position_y: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


class SavedQueryUpdate(BaseModel):
    name: Optional[str] = None
    natural_language: Optional[str] = None
    generated_sql: Optional[str] = None
    result_cache: Optional[str] = None


class ScheduledReportUpdate(BaseModel):
    name: Optional[str] = None
    dashboard_id: Optional[int] = None
    frequency: Optional[str] = None
    recipients: Optional[str] = None
    next_send_at: Optional[datetime] = None
    enabled: Optional[bool] = None


class AIInsightUpdate(BaseModel):
    source_id: Optional[int] = None
    dashboard_id: Optional[int] = None
    insight_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    data_context: Optional[str] = None
    model_used: Optional[str] = None
    acknowledged: Optional[bool] = None


# ---------------------------------------------------------------------------
# GET /dashboard – aggregate stats
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def get_stats(
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    uid = user.id

    user_source_ids = [
        r[0] for r in db.query(DataSource.id).filter(DataSource.user_id == uid).all()
    ]
    user_dashboard_ids = [
        r[0] for r in db.query(Dashboard.id).filter(Dashboard.user_id == uid).all()
    ]

    ds_total = db.query(DataSource).filter(DataSource.user_id == uid).count()
    ds_active = (
        db.query(DataSource)
        .filter(DataSource.user_id == uid, DataSource.status == "active")
        .count()
    )

    rec_total = (
        db.query(DataRecord).filter(DataRecord.source_id.in_(user_source_ids)).count()
        if user_source_ids
        else 0
    )

    dash_total = db.query(Dashboard).filter(Dashboard.user_id == uid).count()
    dash_shared = (
        db.query(Dashboard)
        .filter(Dashboard.user_id == uid, Dashboard.shared == True)
        .count()
    )

    widget_total = (
        db.query(Widget).filter(Widget.dashboard_id.in_(user_dashboard_ids)).count()
        if user_dashboard_ids
        else 0
    )

    query_total = db.query(SavedQuery).filter(SavedQuery.user_id == uid).count()

    report_total = db.query(ScheduledReport).filter(ScheduledReport.user_id == uid).count()
    report_enabled = (
        db.query(ScheduledReport)
        .filter(ScheduledReport.user_id == uid, ScheduledReport.enabled == True)
        .count()
    )

    insight_filters = []
    if user_source_ids:
        insight_filters.append(AIInsight.source_id.in_(user_source_ids))
    if user_dashboard_ids:
        insight_filters.append(AIInsight.dashboard_id.in_(user_dashboard_ids))

    if insight_filters:
        insight_total = db.query(AIInsight).filter(or_(*insight_filters)).count()
        insight_unacked = (
            db.query(AIInsight)
            .filter(or_(*insight_filters), AIInsight.acknowledged == False)
            .count()
        )
    else:
        insight_total = 0
        insight_unacked = 0

    return {
        "data_sources": {"total": ds_total, "active": ds_active},
        "data_records": {"total": rec_total},
        "dashboards": {"total": dash_total, "shared": dash_shared},
        "widgets": {"total": widget_total},
        "saved_queries": {"total": query_total},
        "scheduled_reports": {"total": report_total, "enabled": report_enabled},
        "ai_insights": {"total": insight_total, "unacknowledged": insight_unacked},
    }


# ---------------------------------------------------------------------------
# DataSource CRUD
# ---------------------------------------------------------------------------

@router.get("/sources")
def list_sources(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    q = db.query(DataSource).filter(DataSource.user_id == user.id)
    if status is not None:
        q = q.filter(DataSource.status == status)
    return [to_dict(r) for r in q.limit(limit).all()]


@router.get("/sources/{source_id}")
def get_source(
    source_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, DataSource, source_id, "DataSource")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return to_dict(obj)


@router.post("/sources", status_code=201)
def create_source(
    body: DataSourceCreate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = DataSource(**body.model_dump(), user_id=user.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.put("/sources/{source_id}")
def update_source(
    source_id: int,
    body: DataSourceUpdate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, DataSource, source_id, "DataSource")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(
    source_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, DataSource, source_id, "DataSource")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# DataRecord CRUD
# ---------------------------------------------------------------------------

@router.get("/records")
def list_records(
    source_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    user_source_ids = [
        r[0] for r in db.query(DataSource.id).filter(DataSource.user_id == user.id).all()
    ]
    q = db.query(DataRecord).filter(DataRecord.source_id.in_(user_source_ids))
    if source_id is not None:
        q = q.filter(DataRecord.source_id == source_id)
    return [to_dict(r) for r in q.limit(limit).all()]


@router.get("/records/{record_id}")
def get_record(
    record_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, DataRecord, record_id, "DataRecord")
    src = db.get(DataSource, obj.source_id)
    if src is None or src.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return to_dict(obj)


@router.post("/records", status_code=201)
def create_record(
    body: DataRecordCreate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    src = db.get(DataSource, body.source_id)
    if src is None or src.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    obj = DataRecord(**body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.put("/records/{record_id}")
def update_record(
    record_id: int,
    body: DataRecordUpdate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, DataRecord, record_id, "DataRecord")
    src = db.get(DataSource, obj.source_id)
    if src is None or src.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.delete("/records/{record_id}", status_code=204)
def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, DataRecord, record_id, "DataRecord")
    src = db.get(DataSource, obj.source_id)
    if src is None or src.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Dashboard CRUD
# ---------------------------------------------------------------------------

@router.get("/dashboards")
def list_dashboards(
    shared: Optional[bool] = Query(None),
    is_default: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    q = db.query(Dashboard).filter(Dashboard.user_id == user.id)
    if shared is not None:
        q = q.filter(Dashboard.shared == shared)
    if is_default is not None:
        q = q.filter(Dashboard.is_default == is_default)
    return [to_dict(r) for r in q.limit(limit).all()]


@router.get("/dashboards/{dashboard_id}")
def get_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, Dashboard, dashboard_id, "Dashboard")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return to_dict(obj)


@router.post("/dashboards", status_code=201)
def create_dashboard(
    body: DashboardCreate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = Dashboard(**body.model_dump(), user_id=user.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.put("/dashboards/{dashboard_id}")
def update_dashboard(
    dashboard_id: int,
    body: DashboardUpdate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, Dashboard, dashboard_id, "Dashboard")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.delete("/dashboards/{dashboard_id}", status_code=204)
def delete_dashboard(
    dashboard_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, Dashboard, dashboard_id, "Dashboard")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# Widget CRUD
# ---------------------------------------------------------------------------

@router.get("/widgets")
def list_widgets(
    dashboard_id: Optional[int] = Query(None),
    widget_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    user_dashboard_ids = [
        r[0] for r in db.query(Dashboard.id).filter(Dashboard.user_id == user.id).all()
    ]
    q = db.query(Widget).filter(Widget.dashboard_id.in_(user_dashboard_ids))
    if dashboard_id is not None:
        q = q.filter(Widget.dashboard_id == dashboard_id)
    if widget_type is not None:
        q = q.filter(Widget.widget_type == widget_type)
    return [to_dict(r) for r in q.limit(limit).all()]


@router.get("/widgets/{widget_id}")
def get_widget(
    widget_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, Widget, widget_id, "Widget")
    dash = db.get(Dashboard, obj.dashboard_id)
    if dash is None or dash.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return to_dict(obj)


@router.post("/widgets", status_code=201)
def create_widget(
    body: WidgetCreate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    dash = db.get(Dashboard, body.dashboard_id)
    if dash is None or dash.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    obj = Widget(**body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.put("/widgets/{widget_id}")
def update_widget(
    widget_id: int,
    body: WidgetUpdate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, Widget, widget_id, "Widget")
    dash = db.get(Dashboard, obj.dashboard_id)
    if dash is None or dash.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.delete("/widgets/{widget_id}", status_code=204)
def delete_widget(
    widget_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, Widget, widget_id, "Widget")
    dash = db.get(Dashboard, obj.dashboard_id)
    if dash is None or dash.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# SavedQuery CRUD
# ---------------------------------------------------------------------------

@router.get("/queries")
def list_queries(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    q = db.query(SavedQuery).filter(SavedQuery.user_id == user.id)
    return [to_dict(r) for r in q.limit(limit).all()]


@router.get("/queries/{query_id}")
def get_query(
    query_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, SavedQuery, query_id, "SavedQuery")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return to_dict(obj)


@router.post("/queries", status_code=201)
def create_query(
    body: SavedQueryCreate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = SavedQuery(**body.model_dump(), user_id=user.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.put("/queries/{query_id}")
def update_query(
    query_id: int,
    body: SavedQueryUpdate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, SavedQuery, query_id, "SavedQuery")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.delete("/queries/{query_id}", status_code=204)
def delete_query(
    query_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, SavedQuery, query_id, "SavedQuery")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# ScheduledReport CRUD
# ---------------------------------------------------------------------------

@router.get("/reports")
def list_reports(
    enabled: Optional[bool] = Query(None),
    dashboard_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    q = db.query(ScheduledReport).filter(ScheduledReport.user_id == user.id)
    if enabled is not None:
        q = q.filter(ScheduledReport.enabled == enabled)
    if dashboard_id is not None:
        q = q.filter(ScheduledReport.dashboard_id == dashboard_id)
    return [to_dict(r) for r in q.limit(limit).all()]


@router.get("/reports/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, ScheduledReport, report_id, "ScheduledReport")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return to_dict(obj)


@router.post("/reports", status_code=201)
def create_report(
    body: ScheduledReportCreate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = ScheduledReport(**body.model_dump(), user_id=user.id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.put("/reports/{report_id}")
def update_report(
    report_id: int,
    body: ScheduledReportUpdate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, ScheduledReport, report_id, "ScheduledReport")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, ScheduledReport, report_id, "ScheduledReport")
    if obj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(obj)
    db.commit()


# ---------------------------------------------------------------------------
# AIInsight CRUD
# ---------------------------------------------------------------------------

def _insight_authorized(db: Session, obj: AIInsight, user_id: int) -> bool:
    """Return True if the insight belongs to a source or dashboard owned by user_id."""
    if obj.source_id:
        src = db.get(DataSource, obj.source_id)
        if src and src.user_id == user_id:
            return True
    if obj.dashboard_id:
        dash = db.get(Dashboard, obj.dashboard_id)
        if dash and dash.user_id == user_id:
            return True
    return False


@router.get("/insights")
def list_insights(
    acknowledged: Optional[bool] = Query(None),
    severity: Optional[str] = Query(None),
    insight_type: Optional[str] = Query(None),
    source_id: Optional[int] = Query(None),
    dashboard_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    user_source_ids = [
        r[0] for r in db.query(DataSource.id).filter(DataSource.user_id == user.id).all()
    ]
    user_dashboard_ids = [
        r[0] for r in db.query(Dashboard.id).filter(Dashboard.user_id == user.id).all()
    ]

    ownership_filters = []
    if user_source_ids:
        ownership_filters.append(AIInsight.source_id.in_(user_source_ids))
    if user_dashboard_ids:
        ownership_filters.append(AIInsight.dashboard_id.in_(user_dashboard_ids))

    q = db.query(AIInsight)
    if ownership_filters:
        q = q.filter(or_(*ownership_filters))
    else:
        # User has no sources or dashboards; return empty
        return []

    if acknowledged is not None:
        q = q.filter(AIInsight.acknowledged == acknowledged)
    if severity is not None:
        q = q.filter(AIInsight.severity == severity)
    if insight_type is not None:
        q = q.filter(AIInsight.insight_type == insight_type)
    if source_id is not None:
        q = q.filter(AIInsight.source_id == source_id)
    if dashboard_id is not None:
        q = q.filter(AIInsight.dashboard_id == dashboard_id)

    return [to_dict(r) for r in q.limit(limit).all()]


@router.get("/insights/{insight_id}")
def get_insight(
    insight_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, AIInsight, insight_id, "AIInsight")
    if not _insight_authorized(db, obj, user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return to_dict(obj)


@router.post("/insights", status_code=201)
def create_insight(
    body: AIInsightCreate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    if body.source_id:
        src = db.get(DataSource, body.source_id)
        if src is None or src.user_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    if body.dashboard_id:
        dash = db.get(Dashboard, body.dashboard_id)
        if dash is None or dash.user_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    obj = AIInsight(**body.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.put("/insights/{insight_id}")
def update_insight(
    insight_id: int,
    body: AIInsightUpdate,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, AIInsight, insight_id, "AIInsight")
    if not _insight_authorized(db, obj, user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return to_dict(obj)


@router.delete("/insights/{insight_id}", status_code=204)
def delete_insight(
    insight_id: int,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
):
    obj = get_or_404(db, AIInsight, insight_id, "AIInsight")
    if not _insight_authorized(db, obj, user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(obj)
    db.commit()
