import sqlite3
import time
from typing import Dict, List, Optional, Tuple, Any
from app.config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db() -> None:
    conn = get_connection()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS senders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                domain TEXT NOT NULL,
                classification TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                message_count INTEGER DEFAULT 0,
                thread_count INTEGER DEFAULT 0,
                first_seen TEXT,
                last_seen TEXT,
                has_unsubscribe INTEGER DEFAULT 0,
                has_bulk_precedence INTEGER DEFAULT 0,
                is_junk_candidate INTEGER DEFAULT 0,
                triage_status TEXT DEFAULT 'unreviewed',
                triage_summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS domains (
                domain TEXT PRIMARY KEY,
                is_webmail INTEGER DEFAULT 0,
                sender_count INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                primary_classification TEXT,
                organization_name TEXT
            );

            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                sender_email TEXT,
                subject TEXT,
                message_count INTEGER DEFAULT 1,
                start_date TEXT,
                end_date TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                sender_email TEXT NOT NULL,
                sender_name TEXT,
                recipient TEXT,
                subject TEXT,
                date TEXT,
                timestamp INTEGER,
                thread_id TEXT,
                content_type TEXT,
                body_snippet TEXT,
                list_unsubscribe TEXT,
                precedence TEXT,
                x_auto_response TEXT,
                is_transactional INTEGER DEFAULT 0,
                is_promotional INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                sender_count INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS indexing_status (
                id INTEGER PRIMARY KEY,
                status TEXT DEFAULT 'idle',
                current_file TEXT,
                messages_processed INTEGER DEFAULT 0,
                total_messages_estimated INTEGER DEFAULT 0,
                senders_found INTEGER DEFAULT 0,
                elapsed_seconds REAL DEFAULT 0.0,
                error_message TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_senders_domain ON senders(domain);
            CREATE INDEX IF NOT EXISTS idx_senders_classification ON senders(classification);
            CREATE INDEX IF NOT EXISTS idx_senders_count ON senders(message_count DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_email);
            CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date);
            CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_domains_count ON domains(message_count DESC);
            CREATE TABLE IF NOT EXISTS sender_ai_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_email TEXT NOT NULL,
                category_name TEXT NOT NULL,
                description TEXT,
                message_count INTEGER DEFAULT 0,
                gmail_query TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sender_email, category_name)
            );

            CREATE INDEX IF NOT EXISTS idx_sender_ai_cat ON sender_ai_categories(sender_email);
        """)

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(messages);")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if "summary" not in existing_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN summary TEXT;")
        if "ai_category" not in existing_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN ai_category TEXT;")

        cursor.execute("SELECT COUNT(*) FROM indexing_status WHERE id = 1;")
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "INSERT INTO indexing_status (id, status, current_file, messages_processed, total_messages_estimated, senders_found, elapsed_seconds) "
                "VALUES (1, 'idle', '', 0, 0, 0, 0.0);"
            )
    conn.close()

def reset_db() -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM messages;")
        conn.execute("DELETE FROM threads;")
        conn.execute("DELETE FROM senders;")
        conn.execute("DELETE FROM domains;")
        conn.execute("DELETE FROM categories;")
        conn.execute(
            "UPDATE indexing_status SET status='idle', current_file='', messages_processed=0, total_messages_estimated=0, senders_found=0, elapsed_seconds=0.0, error_message=NULL WHERE id=1;"
        )
    conn.close()

def set_indexing_status(status: str, current_file: str = "", messages_processed: int = 0, total_estimated: int = 0, senders_found: int = 0, elapsed_seconds: float = 0.0, error_message: Optional[str] = None) -> None:
    conn = get_connection()
    with conn:
        conn.execute("""
            UPDATE indexing_status
            SET status = ?, current_file = ?, messages_processed = ?, total_messages_estimated = ?, senders_found = ?, elapsed_seconds = ?, error_message = ?
            WHERE id = 1;
        """, (status, current_file, messages_processed, total_estimated, senders_found, elapsed_seconds, error_message))
    conn.close()

def get_indexing_status() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM indexing_status WHERE id = 1;")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"status": "idle", "messages_processed": 0, "total_messages_estimated": 0, "senders_found": 0, "elapsed_seconds": 0.0}

def get_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages;")
    total_messages = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM senders;")
    total_senders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM domains;")
    total_domains = cursor.fetchone()[0]
    cursor.execute("SELECT classification, COUNT(*) FROM senders GROUP BY classification;")
    class_counts = {r[0]: r[1] for r in cursor.fetchall()}
    cursor.execute("SELECT COUNT(*) FROM senders WHERE is_junk_candidate = 1;")
    junk_candidates = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM senders WHERE triage_status != 'unreviewed';")
    triaged_count = cursor.fetchone()[0]
    conn.close()
    return {
        "total_messages": total_messages,
        "total_senders": total_senders,
        "total_domains": total_domains,
        "junk_candidates": junk_candidates,
        "triaged_count": triaged_count,
        "by_classification": {
            "people": class_counts.get("people", 0),
            "organizations": class_counts.get("organizations", 0),
            "newsletters": class_counts.get("newsletters", 0),
            "mixed": class_counts.get("mixed", 0)
        }
    }

def get_senders(
    filter_type: str = "all",
    sort_by: str = "volume",
    sort_order: str = "desc",
    search: str = "",
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[Dict[str, Any]], int]:
    conn = get_connection()
    cursor = conn.cursor()
    conditions = []
    params: List[Any] = []

    if filter_type in ("people", "organizations", "newsletters", "mixed"):
        conditions.append("classification = ?")
        params.append(filter_type)
    elif filter_type == "junk":
        conditions.append("is_junk_candidate = 1")
    elif filter_type == "triaged":
        conditions.append("triage_status != 'unreviewed'")

    if search.strip():
        term = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(email) LIKE ? OR LOWER(name) LIKE ? OR LOWER(domain) LIKE ?)")
        params.extend([term, term, term])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_query = f"SELECT COUNT(*) FROM senders {where_clause};"
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]

    valid_sort_cols = {
        "volume": "message_count",
        "first_seen": "first_seen",
        "last_seen": "last_seen",
        "classification": "classification",
        "email": "email",
        "name": "name"
    }
    col = valid_sort_cols.get(sort_by, "message_count")
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"

    data_query = f"""
        SELECT id, email, name, domain, classification, confidence, message_count, thread_count,
               first_seen, last_seen, has_unsubscribe, has_bulk_precedence, is_junk_candidate,
               triage_status, triage_summary
        FROM senders
        {where_clause}
        ORDER BY {col} {direction}
        LIMIT ? OFFSET ?;
    """
    cursor.execute(data_query, params + [limit, offset])
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows, total_count

def get_sender_by_id(sender_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM senders WHERE id = ?;", (sender_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_sender_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM senders WHERE email = ?;", (email.lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_sender_messages(email: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, message_id, sender_email, sender_name, recipient, subject, date, timestamp,
               thread_id, content_type, body_snippet, list_unsubscribe, precedence, x_auto_response,
               is_transactional, is_promotional
        FROM messages
        WHERE sender_email = ?
        ORDER BY timestamp DESC
        LIMIT ?;
    """, (email.lower(), limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_domains(sort_by: str = "volume", sort_order: str = "desc", limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM domains;")
    total_count = cursor.fetchone()[0]

    valid_sorts = {
        "volume": "message_count",
        "senders": "sender_count",
        "domain": "domain"
    }
    col = valid_sorts.get(sort_by, "message_count")
    direction = "ASC" if sort_order.lower() == "asc" else "DESC"

    cursor.execute(f"""
        SELECT domain, is_webmail, sender_count, message_count, primary_classification, organization_name
        FROM domains
        ORDER BY {col} {direction}
        LIMIT ? OFFSET ?;
    """, (limit, offset))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows, total_count

def update_sender_triage(sender_id: int, status: str, summary: str = "") -> bool:
    conn = get_connection()
    with conn:
        conn.execute("""
            UPDATE senders
            SET triage_status = ?, triage_summary = ?
            WHERE id = ?;
        """, (status, summary, sender_id))
    conn.close()
    return True

def commit_batch(messages: List[Dict[str, Any]], senders_dict: Dict[str, Dict[str, Any]], domains_dict: Dict[str, Dict[str, Any]]) -> None:
    conn = get_connection()
    with conn:
        for domain, d_info in domains_dict.items():
            conn.execute("""
                INSERT INTO domains (domain, is_webmail, sender_count, message_count, primary_classification, organization_name)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    sender_count = sender_count + excluded.sender_count,
                    message_count = message_count + excluded.message_count,
                    primary_classification = excluded.primary_classification,
                    organization_name = COALESCE(domains.organization_name, excluded.organization_name);
            """, (
                domain,
                d_info["is_webmail"],
                d_info["sender_count"],
                d_info["message_count"],
                d_info["primary_classification"],
                d_info.get("organization_name", domain)
            ))

        for email, s_info in senders_dict.items():
            conn.execute("""
                INSERT INTO senders (
                    email, name, domain, classification, confidence, message_count, thread_count,
                    first_seen, last_seen, has_unsubscribe, has_bulk_precedence, is_junk_candidate,
                    triage_status, triage_summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unreviewed', '')
                ON CONFLICT(email) DO UPDATE SET
                    name = COALESCE(senders.name, excluded.name),
                    classification = excluded.classification,
                    confidence = excluded.confidence,
                    message_count = senders.message_count + excluded.message_count,
                    thread_count = senders.thread_count + excluded.thread_count,
                    first_seen = MIN(senders.first_seen, excluded.first_seen),
                    last_seen = MAX(senders.last_seen, excluded.last_seen),
                    has_unsubscribe = MAX(senders.has_unsubscribe, excluded.has_unsubscribe),
                    has_bulk_precedence = MAX(senders.has_bulk_precedence, excluded.has_bulk_precedence),
                    is_junk_candidate = excluded.is_junk_candidate;
            """, (
                email,
                s_info.get("name", ""),
                s_info["domain"],
                s_info["classification"],
                s_info.get("confidence", 1.0),
                s_info["message_count"],
                s_info.get("thread_count", 1),
                s_info.get("first_seen", ""),
                s_info.get("last_seen", ""),
                s_info.get("has_unsubscribe", 0),
                s_info.get("has_bulk_precedence", 0),
                s_info.get("is_junk_candidate", 0)
            ))

        for msg in messages:
            conn.execute("""
                INSERT OR IGNORE INTO messages (
                    message_id, sender_email, sender_name, recipient, subject, date, timestamp,
                    thread_id, content_type, body_snippet, list_unsubscribe, precedence,
                    x_auto_response, is_transactional, is_promotional
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                msg.get("message_id", ""),
                msg["sender_email"],
                msg.get("sender_name", ""),
                msg.get("recipient", ""),
                msg.get("subject", ""),
                msg.get("date", ""),
                msg.get("timestamp", 0),
                msg.get("thread_id", ""),
                msg.get("content_type", "text/plain"),
                msg.get("body_snippet", ""),
                msg.get("list_unsubscribe", ""),
                msg.get("precedence", ""),
                msg.get("x_auto_response", ""),
                msg.get("is_transactional", 0),
                msg.get("is_promotional", 0)
            ))
    conn.close()

def get_sender_messages_for_ai(sender_email: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, message_id, subject, date, timestamp, body_snippet, summary, ai_category
        FROM messages
        WHERE sender_email = ?
        ORDER BY timestamp DESC;
    """, (sender_email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_message_summaries_batch(updates: List[Tuple[str, str]]) -> None:
    conn = get_connection()
    with conn:
        conn.executemany("UPDATE messages SET summary = ? WHERE message_id = ?;", updates)
    conn.close()

def save_message_categories_batch(updates: List[Tuple[str, str]]) -> None:
    conn = get_connection()
    with conn:
        conn.executemany("UPDATE messages SET ai_category = ? WHERE message_id = ?;", updates)
    conn.close()

def save_sender_ai_categories(sender_email: str, categories: List[Dict[str, Any]]) -> None:
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM sender_ai_categories WHERE sender_email = ?;", (sender_email,))
        for cat in categories:
            conn.execute("""
                INSERT INTO sender_ai_categories (sender_email, category_name, description, message_count, gmail_query)
                VALUES (?, ?, ?, ?, ?);
            """, (
                sender_email,
                cat.get("category_name", "General"),
                cat.get("description", ""),
                cat.get("message_count", 0),
                cat.get("gmail_query", "")
            ))
    conn.close()

def get_sender_ai_categories(sender_email: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, category_name, description, message_count, gmail_query, created_at
        FROM sender_ai_categories
        WHERE sender_email = ?
        ORDER BY message_count DESC;
    """, (sender_email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_sender_ai_stats(sender_email: str) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages WHERE sender_email = ?;", (sender_email,))
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM messages WHERE sender_email = ? AND summary IS NOT NULL AND summary != '';", (sender_email,))
    summarized = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sender_ai_categories WHERE sender_email = ?;", (sender_email,))
    cat_count = cursor.fetchone()[0]
    conn.close()
    return {
        "total_messages": total,
        "summarized_count": summarized,
        "categories_count": cat_count,
        "is_complete": total > 0 and summarized >= total and cat_count > 0
    }

