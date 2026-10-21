import asyncio
import os
import shutil
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, Query, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from pydantic import BaseModel

from app.config import BASE_DIR, UPLOAD_DIR, GEMINI_API_KEY
from app.database import (
    init_db, reset_db, get_stats, get_senders, get_sender_by_id,
    get_sender_by_email, get_sender_messages, get_domains,
    update_sender_triage, get_indexing_status, set_indexing_status,
    get_sender_ai_categories, get_sender_ai_stats, get_connection
)
from app.parser import parse_mbox_stream
from app.mcp_bridge import verify_sender_with_gemini, MCP_TOOLS, execute_mcp_tool
from app.local_ai import get_analysis_status, start_sender_analysis_thread

init_db()

app = FastAPI(title="CleanMail Local Analytics")

static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates_dir = BASE_DIR / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

is_indexing_lock = threading.Lock()

class LocalPathRequest(BaseModel):
    file_path: str

class VerifySenderRequest(BaseModel):
    sender_email: str
    api_key: Optional[str] = None

class TriageUpdateRequest(BaseModel):
    sender_id: int
    status: str
    summary: Optional[str] = ""

class FilterExportRequest(BaseModel):
    sender_emails: List[str]
    action: Optional[str] = "archive_skip_inbox"

class McpRpcRequest(BaseModel):
    jsonrpc: Optional[str] = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Any] = 1

def run_background_parse(file_path: str) -> None:
    try:
        parse_mbox_stream(file_path)
    except Exception as exc:
        set_indexing_status(
            status="error",
            current_file=os.path.basename(file_path),
            error_message=str(exc).replace(";", ",").replace("—", "-").replace("–", "-")
        )

@app.get("/")
def index_view():
    return FileResponse(templates_dir / "index.html")

@app.get("/api/status")
def status_endpoint():
    return get_indexing_status()

@app.get("/api/stats")
def stats_endpoint():
    return get_stats()

@app.get("/api/senders")
def senders_endpoint(
    filter_type: str = Query("all"),
    sort_by: str = Query("volume"),
    sort_order: str = Query("desc"),
    search: str = Query(""),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    senders, total = get_senders(
        filter_type=filter_type,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
        limit=limit,
        offset=offset
    )
    return {
        "items": senders,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.get("/api/senders/{sender_id}")
def sender_details_endpoint(sender_id: int):
    sender = get_sender_by_id(sender_id)
    if not sender:
        raise HTTPException(status_code=404, detail="Sender was not found in archive index")
    
    messages = get_sender_messages(sender["email"], limit=40)
    return {
        "sender": sender,
        "messages": messages,
        "message_count": len(messages)
    }

@app.get("/api/domains")
def domains_endpoint(
    sort_by: str = Query("volume"),
    sort_order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    domains, total = get_domains(sort_by=sort_by, sort_order=sort_order, limit=limit, offset=offset)
    return {
        "items": domains,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.post("/api/upload-mbox")
async def upload_mbox_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Please choose an mbox file to upload")

    safe_filename = Path(file.filename).name
    target_path = str(UPLOAD_DIR / safe_filename)

    try:
        with open(target_path, "wb") as f_out:
            shutil.copyfileobj(file.file, f_out, length=1024 * 1024)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(exc)}")

    file_size_bytes = os.path.getsize(target_path)

    # Initial realistic estimation until mailbox is opened (~125KB per email average)
    initial_est_msgs = max(1, int(file_size_bytes / 125000))

    set_indexing_status(
        status="parsing",
        current_file=safe_filename,
        messages_processed=0,
        total_estimated=initial_est_msgs,
        senders_found=0,
        elapsed_seconds=0.0
    )

    background_tasks.add_task(run_background_parse, target_path)
    return {
        "status": "upload_complete",
        "file_name": safe_filename,
        "file_size_bytes": file_size_bytes,
        "message": "Upload complete. Organizing emails now."
    }

@app.post("/api/reset-db")
def reset_db_endpoint():
    reset_db()
    return {
        "status": "ok",
        "message": "Database archive reset successfully"
    }

@app.post("/api/mcp/verify-sender")
def mcp_verify_sender_endpoint(req: VerifySenderRequest):
    result = verify_sender_with_gemini(req.sender_email, api_key=req.api_key)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.post("/api/triage-sender")
def triage_sender_endpoint(req: TriageUpdateRequest):
    success = update_sender_triage(req.sender_id, req.status, req.summary or "")
    if not success:
        raise HTTPException(status_code=400, detail="Could not update triage state")
    return {"status": "ok", "sender_id": req.sender_id, "triage_status": req.status}

@app.post("/api/filter-export")
def filter_export_endpoint(req: FilterExportRequest):
    emails = [e.strip().lower() for e in req.sender_emails if e.strip()]
    if not emails:
        raise HTTPException(status_code=400, detail="No sender emails provided for filter generation")

    if len(emails) == 1:
        gmail_query = f"from:{emails[0]}"
    else:
        gmail_query = f"from:({' OR '.join(emails)})"

    xml_entries = []
    for email_addr in emails:
        entry = (
            f"  <entry>\n"
            f"    <category term='filter'></category>\n"
            f"    <title>Mail Filter</title>\n"
            f"    <apps:property name='from' value='{email_addr}'/>\n"
            f"    <apps:property name='shouldArchive' value='true'/>\n"
            f"    <apps:property name='label' value='Junk Auto Archive'/>\n"
            f"  </entry>"
        )
        xml_entries.append(entry)

    xml_content = (
        f"<?xml version='1.0' encoding='UTF-8'?>\n"
        f"<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>\n"
        f"  <title>Mail Filters Exported from CleanMail</title>\n"
        + "\n".join(xml_entries) + "\n"
        f"</feed>"
    )

    return {
        "sender_count": len(emails),
        "gmail_search_query": gmail_query,
        "xml_content": xml_content
    }

@app.post("/api/mcp/rpc")
def mcp_rpc_endpoint(req: McpRpcRequest):
    method = req.method
    params = req.params or {}

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "result": {
                "tools": MCP_TOOLS
            }
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        result = execute_mcp_tool(tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        }
    else:
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "error": {
                "code": -32601,
                "message": f"Method {method} not found on MCP Server"
            }
        }

@app.get("/api/viz-stats")
def get_viz_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages;")
    total_messages = cursor.fetchone()[0] or 1
    cursor.execute("SELECT COUNT(*) FROM senders;")
    total_senders = cursor.fetchone()[0] or 1

    cursor.execute("""
        SELECT classification, COUNT(*) as sender_cnt, COALESCE(SUM(message_count), 0) as msg_cnt
        FROM senders
        GROUP BY classification;
    """)
    rows = cursor.fetchall()

    class_data = {}
    for r in rows:
        c_name = r["classification"]
        s_cnt = r["sender_cnt"]
        m_cnt = r["msg_cnt"]
        class_data[c_name] = {
            "sender_count": s_cnt,
            "message_count": m_cnt,
            "message_percent": round((m_cnt / total_messages) * 100, 1),
            "sender_percent": round((s_cnt / total_senders) * 100, 1)
        }

    newsletters = class_data.get("newsletters", {"sender_count": 0, "message_count": 0, "message_percent": 0.0})
    mixed = class_data.get("mixed", {"sender_count": 0, "message_count": 0, "message_percent": 0.0})
    orgs = class_data.get("organizations", {"sender_count": 0, "message_count": 0, "message_percent": 0.0})
    people = class_data.get("people", {"sender_count": 0, "message_count": 0, "message_percent": 0.0})

    cursor.execute("""
        SELECT COUNT(DISTINCT s.email) FROM senders s
        WHERE s.classification = 'people' AND s.email IN (
            SELECT DISTINCT sender_email FROM messages WHERE is_transactional = 1
        );
    """)
    people_trans = cursor.fetchone()[0] or 0

    conn.close()

    return {
        "total_messages": total_messages,
        "total_senders": total_senders,
        "categories": {
            "newsletters": newsletters,
            "mixed": mixed,
            "organizations": orgs,
            "people": people
        },
        "venn": {
            "spam_senders": newsletters["sender_count"],
            "spam_messages": newsletters["message_count"],
            "receipt_senders": orgs["sender_count"],
            "receipt_messages": orgs["message_count"],
            "personal_senders": people["sender_count"],
            "personal_messages": people["message_count"],
            "mixed_senders": mixed["sender_count"],
            "mixed_messages": mixed["message_count"],
            "personal_receipt_senders": people_trans
        }
    }

class AiCleanAnalyzeRequest(BaseModel):
    email: str

class AiCleanFilterRequest(BaseModel):
    email: str
    category_name: str
    gmail_query: str

@app.get("/api/ai-clean/senders")
def list_ai_clean_senders(search: Optional[str] = Query(None)):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT s.id, s.email, s.name, s.classification, s.message_count, s.last_seen,
               (SELECT COUNT(*) FROM messages m WHERE m.sender_email = s.email AND m.summary IS NOT NULL AND m.summary != '') as summarized_count,
               (SELECT COUNT(*) FROM sender_ai_categories sac WHERE sac.sender_email = s.email) as categories_count
        FROM senders s
    """
    params = []
    if search:
        query += " WHERE s.email LIKE ? OR s.name LIKE ?"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY s.message_count DESC LIMIT 100;"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return {"senders": [dict(r) for r in rows]}

@app.post("/api/ai-clean/analyze")
def start_ai_clean_analysis(req: AiCleanAnalyzeRequest):
    email = req.email.strip().lower()
    try:
        import torch
        import transformers
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Local AI packages (PyTorch and Transformers) are currently downloading and installing in the background. Please wait a few minutes for setup to finish before scanning."
        )
    started = start_sender_analysis_thread(email)
    if not started:
        cur = get_analysis_status()
        if cur.get("sender") == email and cur.get("status") == "running":
            return {"status": "already_running", "message": "Analysis is already in progress for this sender"}
        raise HTTPException(status_code=409, detail="Another sender analysis is currently running")
    return {"status": "started", "email": email}

@app.get("/api/ai-clean/status")
def get_ai_clean_status():
    return get_analysis_status()

@app.get("/api/ai-clean/categories")
def get_ai_clean_categories(email: str = Query(...)):
    cats = get_sender_ai_categories(email)
    stats = get_sender_ai_stats(email)
    return {"categories": cats, "stats": stats}

@app.post("/api/ai-clean/category-filter")
def generate_ai_clean_category_filter(req: AiCleanFilterRequest):
    safe_query = req.gmail_query.strip()
    safe_cat = req.category_name.strip()
    entry = (
        f"  <entry>\n"
        f"    <category term='filter'></category>\n"
        f"    <title>CleanMail - {safe_cat}</title>\n"
        f"    <apps:property name='hasTheWord' value='{safe_query}'/>\n"
        f"    <apps:property name='shouldArchive' value='true'/>\n"
        f"    <apps:property name='label' value='CleanMail {safe_cat}'/>\n"
        f"  </entry>"
    )
    xml_content = (
        f"<?xml version='1.0' encoding='UTF-8'?>\n"
        f"<feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>\n"
        f"  <title>CleanMail Filter - {safe_cat}</title>\n"
        f"{entry}\n"
        f"</feed>"
    )
    return {
        "gmail_query": safe_query,
        "xml_content": xml_content
    }

