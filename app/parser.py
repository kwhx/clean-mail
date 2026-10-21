import email
import email.header
import email.utils
import hashlib
import mailbox
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.classifier import classify_sender, analyze_message_intent, is_webmail_domain
from app.database import commit_batch, set_indexing_status

def decode_mime_header(header_val: Optional[str]) -> str:
    if not header_val:
        return ""
    try:
        decoded_parts = email.header.decode_header(header_val)
        result = []
        for text, encoding in decoded_parts:
            if isinstance(text, bytes):
                encoding = encoding or "utf-8"
                try:
                    result.append(text.decode(encoding, errors="replace"))
                except Exception:
                    result.append(text.decode("latin-1", errors="replace"))
            else:
                result.append(str(text))
        return " ".join(result).strip()
    except Exception:
        return str(header_val).strip()

def extract_body_snippet(msg: email.message.Message, max_chars: int = 240) -> str:
    text_content = ""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        text_content = payload.decode(charset, errors="replace")
                        break
                elif ctype == "text/html" and not text_content:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        text_content = payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                text_content = payload.decode(charset, errors="replace")
    except Exception:
        text_content = ""

    clean_text = " ".join(text_content.replace("\r", " ").replace("\n", " ").split())
    return clean_text[:max_chars]

def parse_mbox_stream(file_path: str, batch_size: int = 150) -> Dict[str, Any]:
    start_time = time.time()
    filename = os.path.basename(file_path)
    file_size_bytes = os.path.getsize(file_path)
    # Modern emails with HTML/attachments average ~125KB in mbox archives
    est_total_msgs = max(1, int(file_size_bytes / 125000))

    set_indexing_status(
        status="parsing",
        current_file=filename,
        messages_processed=0,
        total_estimated=est_total_msgs,
        senders_found=0,
        elapsed_seconds=0.0
    )

    box = mailbox.mbox(file_path, create=False)
    try:
        total_messages = len(box)
    except Exception:
        total_messages = est_total_msgs

    if total_messages > 0:
        set_indexing_status(
            status="parsing",
            current_file=filename,
            messages_processed=0,
            total_estimated=total_messages,
            senders_found=0,
            elapsed_seconds=round(time.time() - start_time, 1)
        )

    messages_batch: List[Dict[str, Any]] = []
    senders_meta: Dict[str, Dict[str, Any]] = {}
    domains_meta: Dict[str, Dict[str, Any]] = {}
    sender_history: Dict[str, Dict[str, int]] = {}

    total_processed = 0

    try:
        for idx, key in enumerate(box.iterkeys()):
            try:
                msg = box.get_message(key)
            except Exception:
                continue

            raw_from = msg.get("From", "")
            disp_name, email_addr = email.utils.parseaddr(raw_from)
            disp_name = decode_mime_header(disp_name)
            email_addr = email_addr.strip().lower()

            if not email_addr or "@" not in email_addr:
                continue

            domain = email_addr.split("@")[-1].strip().lower()
            subject = decode_mime_header(msg.get("Subject", "No Subject"))
            date_raw = msg.get("Date", "")
            
            timestamp = int(time.time())
            formatted_date = ""
            if date_raw:
                try:
                    dt = email.utils.parsedate_to_datetime(date_raw)
                    timestamp = int(dt.timestamp())
                    formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    formatted_date = str(date_raw)[:30]

            msg_id = msg.get("Message-ID", "")
            if not msg_id:
                msg_id = hashlib.sha256(f"{email_addr}:{timestamp}:{subject}".encode()).hexdigest()[:24]

            in_reply_to = msg.get("In-Reply-To", "")
            references = msg.get("References", "")
            thread_ref = in_reply_to or (references.split()[0] if references else "")
            if not thread_ref:
                clean_subj = "".join(ch for ch in subject.lower() if ch.isalnum())
                thread_ref = hashlib.sha256(f"{email_addr}:{clean_subj}".encode()).hexdigest()[:16]

            headers_dict = {
                "List-Unsubscribe": msg.get("List-Unsubscribe", ""),
                "List-Unsubscribe-Post": msg.get("List-Unsubscribe-Post", ""),
                "Precedence": msg.get("Precedence", ""),
                "X-Auto-Response-Suppress": msg.get("X-Auto-Response-Suppress", ""),
                "Auto-Submitted": msg.get("Auto-Submitted", "")
            }

            is_trans, is_promo = analyze_message_intent(headers_dict, subject)
            snippet = extract_body_snippet(msg)

            if email_addr not in sender_history:
                sender_history[email_addr] = {"transactional_count": 0, "promotional_count": 0}
            if is_trans:
                sender_history[email_addr]["transactional_count"] += 1
            if is_promo:
                sender_history[email_addr]["promotional_count"] += 1

            classification, confidence, is_junk = classify_sender(
                email=email_addr,
                name=disp_name,
                headers_sample=headers_dict,
                subject_sample=subject,
                historical_stats=sender_history[email_addr]
            )

            msg_record = {
                "message_id": msg_id,
                "sender_email": email_addr,
                "sender_name": disp_name,
                "recipient": msg.get("To", ""),
                "subject": subject,
                "date": formatted_date or datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": timestamp,
                "thread_id": thread_ref,
                "content_type": msg.get_content_type(),
                "body_snippet": snippet,
                "list_unsubscribe": headers_dict["List-Unsubscribe"],
                "precedence": headers_dict["Precedence"],
                "x_auto_response": headers_dict["X-Auto-Response-Suppress"],
                "is_transactional": 1 if is_trans else 0,
                "is_promotional": 1 if is_promo else 0
            }
            messages_batch.append(msg_record)

            if email_addr not in senders_meta:
                senders_meta[email_addr] = {
                    "domain": domain,
                    "name": disp_name,
                    "classification": classification,
                    "confidence": confidence,
                    "message_count": 0,
                    "thread_count": 1,
                    "first_seen": msg_record["date"],
                    "last_seen": msg_record["date"],
                    "has_unsubscribe": 1 if headers_dict["List-Unsubscribe"] else 0,
                    "has_bulk_precedence": 1 if headers_dict["Precedence"].lower() in ("bulk", "list") else 0,
                    "is_junk_candidate": 1 if is_junk else 0
                }
            s_entry = senders_meta[email_addr]
            s_entry["message_count"] += 1
            s_entry["classification"] = classification
            s_entry["first_seen"] = min(s_entry["first_seen"], msg_record["date"])
            s_entry["last_seen"] = max(s_entry["last_seen"], msg_record["date"])
            if headers_dict["List-Unsubscribe"]:
                s_entry["has_unsubscribe"] = 1
            if headers_dict["Precedence"].lower() in ("bulk", "list"):
                s_entry["has_bulk_precedence"] = 1
            if is_junk:
                s_entry["is_junk_candidate"] = 1

            if domain not in domains_meta:
                domains_meta[domain] = {
                    "is_webmail": 1 if is_webmail_domain(domain) else 0,
                    "sender_count": 0,
                    "message_count": 0,
                    "primary_classification": classification,
                    "organization_name": domain.split(".")[0].capitalize()
                }
            d_entry = domains_meta[domain]
            d_entry["message_count"] += 1

            total_processed += 1

            if len(messages_batch) >= batch_size:
                for dom in domains_meta:
                    domains_meta[dom]["sender_count"] = sum(1 for e in senders_meta if senders_meta[e]["domain"] == dom)
                commit_batch(messages_batch, senders_meta, domains_meta)
                messages_batch.clear()
                senders_meta.clear()
                domains_meta.clear()

                now = time.time()
                set_indexing_status(
                    status="parsing",
                    current_file=filename,
                    messages_processed=total_processed,
                    total_estimated=max(total_processed, total_messages),
                    senders_found=len(sender_history),
                    elapsed_seconds=round(now - start_time, 1)
                )

        if messages_batch:
            for dom in domains_meta:
                domains_meta[dom]["sender_count"] = sum(1 for e in senders_meta if senders_meta[e]["domain"] == dom)
            commit_batch(messages_batch, senders_meta, domains_meta)
            messages_batch.clear()
            senders_meta.clear()
            domains_meta.clear()

        total_elapsed = round(time.time() - start_time, 2)
        set_indexing_status(
            status="completed",
            current_file=filename,
            messages_processed=total_processed,
            total_estimated=total_processed,
            senders_found=len(sender_history),
            elapsed_seconds=total_elapsed
        )
        return {
            "status": "completed",
            "messages_processed": total_processed,
            "senders_found": len(sender_history),
            "elapsed_seconds": total_elapsed
        }

    except Exception as exc:
        set_indexing_status(
            status="error",
            current_file=filename,
            messages_processed=total_processed,
            total_estimated=max(total_processed, total_messages if 'total_messages' in locals() else est_total_msgs),
            senders_found=len(sender_history),
            elapsed_seconds=round(time.time() - start_time, 2),
            error_message=str(exc)
        )
        raise exc
    finally:
        box.close()
