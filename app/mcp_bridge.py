import json
import os
import re
from typing import Dict, Any, List, Optional
from app.config import GEMINI_API_KEY
from app.database import get_sender_by_email, get_sender_messages, update_sender_triage

MCP_TOOLS = [
    {
        "name": "inspect_sender_thread",
        "description": "Inspects all email messages, headers, and thread subjects from a specific sender address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender_email": {
                    "type": "string",
                    "description": "The exact sender email address to analyze."
                }
            },
            "required": ["sender_email"]
        }
    },
    {
        "name": "analyze_thread_intent",
        "description": "Calculates the ratio of transactional vs promotional emails and determines safety score for triaging.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender_email": {
                    "type": "string",
                    "description": "The sender email address."
                }
            },
            "required": ["sender_email"]
        }
    },
    {
        "name": "generate_safe_triage_plan",
        "description": "Generates a fine grained filter rule to separate critical notifications from bulk marketing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sender_email": {
                    "type": "string",
                    "description": "The sender email to create a safe filter plan for."
                }
            },
            "required": ["sender_email"]
        }
    }
]

def execute_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    sender_email = arguments.get("sender_email", "").strip().lower()
    sender = get_sender_by_email(sender_email)
    if not sender:
        return {"error": f"Sender {sender_email} not found in local index"}

    messages = get_sender_messages(sender_email, limit=80)

    if tool_name == "inspect_sender_thread":
        subjects = [m["subject"] for m in messages]
        has_unsub = any(bool(m["list_unsubscribe"]) for m in messages)
        has_bulk = any(m["precedence"].lower() in ("bulk", "list") for m in messages)
        return {
            "sender": dict(sender),
            "total_inspected_messages": len(messages),
            "has_unsubscribe_headers": has_unsub,
            "has_bulk_precedence": has_bulk,
            "subject_samples": subjects[:15],
            "first_seen": sender["first_seen"],
            "last_seen": sender["last_seen"]
        }

    elif tool_name == "analyze_thread_intent":
        trans_count = sum(1 for m in messages if m["is_transactional"])
        promo_count = sum(1 for m in messages if m["is_promotional"])
        total = max(1, len(messages))
        trans_pct = round((trans_count / total) * 100, 1)
        promo_pct = round((promo_count / total) * 100, 1)

        risk_level = "Low"
        if trans_count > 0 and promo_count > 0:
            risk_level = "High" if trans_count >= promo_count else "Medium"
        elif trans_count > 0:
            risk_level = "High"

        return {
            "sender_email": sender_email,
            "total_messages": total,
            "transactional_count": trans_count,
            "promotional_count": promo_count,
            "transactional_percentage": trans_pct,
            "promotional_percentage": promo_pct,
            "risk_of_false_positive_filtering": risk_level
        }

    elif tool_name == "generate_safe_triage_plan":
        trans_msgs = [m for m in messages if m["is_transactional"]]
        promo_msgs = [m for m in messages if m["is_promotional"]]
        
        if trans_msgs and promo_msgs:
            recommendation = "Filter Ads Only"
            rule = f"from:{sender_email} -{{subject:(receipt OR order OR invoice OR statement OR security OR alert OR confirm)}}"
            explanation = "This sender sends both receipts and marketing ads. Keep your receipts safe by filtering only promotions."
        elif trans_msgs and not promo_msgs:
            recommendation = "Keep in Inbox"
            rule = f"from:{sender_email}"
            explanation = "This sender sends important receipts, bills, or security notices. Keep in your inbox."
        else:
            recommendation = "Safe to Block"
            rule = f"from:{sender_email}"
            explanation = "This sender only sends newsletters and ads. It is safe to remove or filter them."

        return {
            "sender_email": sender_email,
            "recommendation": recommendation,
            "recommended_query": rule,
            "explanation": explanation
        }

    return {"error": f"Unknown tool: {tool_name}"}

def verify_sender_with_gemini(sender_email: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    sender = get_sender_by_email(sender_email)
    if not sender:
        return {"error": f"Sender {sender_email} not found in database"}

    messages = get_sender_messages(sender_email, limit=60)
    if not messages:
        return {"error": "No messages available for sender"}

    inspection = execute_mcp_tool("inspect_sender_thread", {"sender_email": sender_email})
    intent = execute_mcp_tool("analyze_thread_intent", {"sender_email": sender_email})
    plan = execute_mcp_tool("generate_safe_triage_plan", {"sender_email": sender_email})

    effective_key = api_key or GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")

    if effective_key:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=effective_key)
            prompt = f"""
You are an email assistant helping a user clean up their Gmail. Analyze this sender and give simple, plain English advice.

Sender Email: {sender_email}
Sender Name: {sender.get('name', 'Unknown')}
Domain: {sender.get('domain', '')}
Total Emails: {len(messages)}
Receipts and Bills Count: {intent['transactional_count']}
Ads and Newsletters Count: {intent['promotional_count']}
Recent Subjects: {json.dumps([m['subject'] for m in messages[:12]])}

Provide a JSON response with:
- verification_status (one of: "mixed", "receipts_only", "newsletters_only", "personal")
- risk_score (integer between 0 and 100, where 100 means high risk of losing receipts if blocked)
- summary (a concise 2 sentence assessment in plain English without semicolons or em dashes)
- recommended_action (one of: "Filter Ads Only", "Keep in Inbox", "Safe to Block", "Keep Contact")
- safe_filter_query (actionable search string without semicolons)
- key_findings (array of 3 short factual bullet points in plain English without semicolons or em dashes)
"""
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            parsed = json.loads(response.text)
            clean_summary = parsed.get("summary", "").replace(";", ",").replace("—", "-").replace("–", "-")
            findings = [f.replace(";", ",").replace("—", "-").replace("–", "-") for f in parsed.get("key_findings", [])]

            update_sender_triage(
                sender_id=sender["id"],
                status=parsed.get("verification_status", "verified"),
                summary=clean_summary
            )

            return {
                "engine": "Gemini 2.5 Flash",
                "sender_id": sender["id"],
                "sender_email": sender_email,
                "sender_name": sender.get("name", ""),
                "domain": sender.get("domain", ""),
                "classification": sender.get("classification", ""),
                "message_count": len(messages),
                "transactional_count": intent["transactional_count"],
                "promotional_count": intent["promotional_count"],
                "transactional_percentage": intent["transactional_percentage"],
                "promotional_percentage": intent["promotional_percentage"],
                "verification_status": parsed.get("verification_status", "verified"),
                "risk_score": parsed.get("risk_score", 45),
                "summary": clean_summary,
                "recommended_action": parsed.get("recommended_action", plan["recommendation"]),
                "safe_filter_query": parsed.get("safe_filter_query", plan["recommended_query"]),
                "key_findings": findings,
                "sample_subjects": [m["subject"] for m in messages[:8]]
            }
        except Exception:
            pass

    t_count = intent["transactional_count"]
    p_count = intent["promotional_count"]
    total = max(1, len(messages))

    if t_count > 0 and p_count > 0:
        ver_status = "mixed"
        risk_score = 75
        action = "Filter Ads Only"
        summary = (
            f"This sender sends both order receipts and marketing emails. "
            f"If you block them completely you will miss your receipts. Filter only promotions instead."
        )
        findings = [
            f"Found {t_count} receipts or account notices",
            f"Found {p_count} newsletters or promotional deals",
            "Safe to filter marketing while keeping receipts"
        ]
        query = f"from:{sender_email} -{{subject:(receipt OR order OR invoice OR statement OR security OR alert OR confirm)}}"

    elif t_count > 0 and p_count == 0:
        ver_status = "receipts_only"
        risk_score = 95
        action = "Keep in Inbox"
        summary = (
            f"All emails from this sender are receipts, bills, or security alerts. "
            f"Keep this sender in your inbox."
        )
        findings = [
            "100 percent of recent emails are receipts or alerts",
            "No marketing emails or newsletter links found",
            "Important for keeping account records"
        ]
        query = f"from:{sender_email}"

    elif p_count > 0 and t_count == 0:
        ver_status = "newsletters_only"
        risk_score = 10
        action = "Safe to Block"
        summary = (
            f"This sender only sends newsletters and marketing ads. "
            f"It is safe to remove or filter them."
        )
        findings = [
            "Contains newsletter unsubscribe links",
            "No receipts or order confirmations found",
            "Safe to filter or unsubscribe"
        ]
        query = f"from:{sender_email}"

    else:
        ver_status = "personal"
        risk_score = 90
        action = "Keep Contact"
        summary = (
            f"This is a real personal email contact. "
            f"Keep this contact in your inbox."
        )
        findings = [
            "Personal webmail contact",
            "Real email conversations",
            "Keep in primary inbox"
        ]
        query = f"from:{sender_email}"

    clean_summary = summary.replace(";", ",").replace("—", "-").replace("–", "-")
    clean_findings = [f.replace(";", ",").replace("—", "-").replace("–", "-") for f in findings]

    update_sender_triage(
        sender_id=sender["id"],
        status=ver_status,
        summary=clean_summary
    )

    return {
        "engine": "Local MCP Reasoner (Deterministic)",
        "sender_id": sender["id"],
        "sender_email": sender_email,
        "sender_name": sender.get("name", ""),
        "domain": sender.get("domain", ""),
        "classification": sender.get("classification", ""),
        "message_count": len(messages),
        "transactional_count": t_count,
        "promotional_count": p_count,
        "transactional_percentage": intent["transactional_percentage"],
        "promotional_percentage": intent["promotional_percentage"],
        "verification_status": ver_status,
        "risk_score": risk_score,
        "summary": clean_summary,
        "recommended_action": action,
        "safe_filter_query": query,
        "key_findings": clean_findings,
        "sample_subjects": [m["subject"] for m in messages[:8]]
    }
