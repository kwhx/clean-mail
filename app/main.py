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
    update_sender_triage, get_indexing_status, set_indexing_status
)
from app.parser import parse_mbox_stream
from app.mcp_bridge import verify_sender_with_gemini, MCP_TOOLS, execute_mcp_tool

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

    with open(target_path, "wb") as f_out:
        shutil.copyfileobj(file.file, f_out, length=1024 * 1024)

    file_size_bytes = os.path.getsize(target_path)

    set_indexing_status(
        status="parsing",
        current_file=safe_filename,
        messages_processed=0,
        total_estimated=max(10, int(file_size_bytes / 2500)),
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
