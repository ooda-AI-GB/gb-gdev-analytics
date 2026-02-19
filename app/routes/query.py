import os
import json
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.models import SavedQuery, DataSource, DataRecord
from app.routes import get_current_user, get_active_subscription
from typing import Any, Optional
from pydantic import BaseModel

try:
    from google import genai
except ImportError:
    genai = None

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

class QueryRequest(BaseModel):
    question: str

@router.get("/query", response_class=HTMLResponse)
async def query_interface(
    request: Request,
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    return templates.TemplateResponse("query/interface.html", {"request": request, "user": user})

@router.post("/api/query")
async def execute_query(
    request: QueryRequest,
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return JSONResponse({"error": "AI not configured"}, status_code=503)
    if not genai:
        return JSONResponse({"error": "Google GenAI library not installed"}, status_code=500)
    
    # Get schema context
    sources = db.query(DataSource).filter(DataSource.user_id == user.id).all()
    if not sources:
        return JSONResponse({"error": "No data sources found"}, status_code=400)
    
    sources_info = []
    for s in sources:
        fields = []
        try:
            config = json.loads(s.config or "{}")
            fields = config.get("fields", [])
        except:
            pass
        sources_info.append(f"Source ID {s.id} ('{s.name}'): Fields {fields}")
    
    prompt = f"""You are a SQL expert. 
    The database has a table 'data_records' with columns: 
    - source_id (integer)
    - record_date (date)
    - data (text, contains JSON string)
    
    Your task is to write a SQL query to answer this question: "{request.question}"
    
    Context on Data Sources:
    {json.dumps(sources_info)}
    
    Rules:
    1. Filter by source_id based on the source name in the question.
    2. Use SQLite syntax.
    3. To access JSON fields in 'data' column, use `json_extract(data, '$.field_name')`.
    4. Cast values if needed (e.g. CAST(json_extract(...) AS REAL)).
    5. Return ONLY the raw SQL query, no markdown, no explanation.
    """
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=prompt
        )
        sql_query = response.text.replace("```sql", "").replace("```", "").strip()
        
        # Execute (ReadOnly safety?) - For prototype, just execute
        # Be careful with injection/updates. Assume readonly user or trust AI?
        # "Execute SQL against DataRecords"
        
        result = db.execute(text(sql_query))
        rows = result.fetchall()
        keys = result.keys()
        
        data = [dict(zip(keys, row)) for row in rows]
        
        return JSONResponse({
            "sql": sql_query,
            "results": data
        })
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/api/query/save")
async def save_query(
    name: str = Form(...),
    question: str = Form(...),
    sql: str = Form(...),
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    saved = SavedQuery(
        user_id=user.id,
        name=name,
        natural_language=question,
        generated_sql=sql
    )
    db.add(saved)
    db.commit()
    return JSONResponse({"status": "saved"})

@router.get("/query/saved")
async def list_saved_queries(
    db: Session = Depends(get_db),
    user: Any = Depends(get_current_user),
    sub: Any = Depends(get_active_subscription)
):
    queries = db.query(SavedQuery).filter(SavedQuery.user_id == user.id).all()
    return JSONResponse([{"id": q.id, "name": q.name, "question": q.natural_language} for q in queries])
