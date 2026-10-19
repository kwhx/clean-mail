import os
import re
import threading
import time
from typing import Dict, Any, List, Optional
from app.database import (
    get_sender_messages_for_ai,
    save_message_summaries_batch,
    save_message_categories_batch,
    save_sender_ai_categories,
    get_sender_ai_categories,
    get_sender_ai_stats
)

DEFAULT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

_model = None
_tokenizer = None
_model_lock = threading.Lock()

_analysis_status = {
    "status": "idle",
    "sender": "",
    "processed": 0,
    "total": 0,
    "percent": 0,
    "current_subject": "",
    "stage": "idle",
    "error": None
}
_status_lock = threading.Lock()

def get_analysis_status() -> Dict[str, Any]:
    with _status_lock:
        return dict(_analysis_status)

def set_analysis_status(**kwargs) -> None:
    with _status_lock:
        _analysis_status.update(kwargs)

def get_or_load_model():
    global _model, _tokenizer
    with _model_lock:
        if _model is not None and _tokenizer is not None:
            return _model, _tokenizer

        set_analysis_status(stage="loading_model")
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            raise RuntimeError(
                "Local AI packages (PyTorch and Transformers) are currently downloading and installing in the background. "
                "Please wait a few minutes for setup to finish before scanning."
            )

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        tokenizer = AutoTokenizer.from_pretrained(DEFAULT_MODEL_ID, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            DEFAULT_MODEL_ID,
            torch_dtype=dtype,
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True
        )
        if device == "cpu":
            model.to("cpu")

        model.eval()
        _model = model
        _tokenizer = tokenizer
        return _model, _tokenizer

def generate_local_text(prompt: str, max_new_tokens: int = 120, temperature: float = 0.2) -> str:
    model, tokenizer = get_or_load_model()
    import torch

    inputs = tokenizer(prompt, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.eos_token_id
        )

    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return response.strip()

def summarize_single_email(subject: str, snippet: str) -> str:
    clean_sub = (subject or "No Subject").strip()
    clean_snip = (snippet or "").strip()[:200]
    prompt = (
        f"<|im_start|>system\n"
        f"You are an email analyzer. Write a direct 1-2 sentence summary of this email. Focus on its purpose (e.g., job notification, promotional sale, order confirmation). Do not use AI buzzwords.<|im_end|>\n"
        f"<|im_start|>user\n"
        f"Subject: {clean_sub}\n"
        f"Snippet: {clean_snip}\n"
        f"Summary:<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    res = generate_local_text(prompt, max_new_tokens=60, temperature=0.1)
    cleaned = " ".join(res.replace("\n", " ").split())
    if not cleaned or len(cleaned) < 5:
        cleaned = f"Email regarding {clean_sub}."
    return cleaned

def create_categories_from_summaries(sender_email: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    set_analysis_status(stage="categorizing")

    sample_items = []
    seen_subjects = set()
    for m in messages:
        sub = m.get("subject", "").strip()
        if sub and sub not in seen_subjects:
            seen_subjects.add(sub)
            sample_items.append(f"- Subject: {sub} | Summary: {m.get('summary', '')}")
            if len(sample_items) >= 40:
                break

    samples_text = "\n".join(sample_items[:35])

    cluster_prompt = (
        f"<|im_start|>system\n"
        f"Analyze these email samples from sender '{sender_email}'. "
        f"Group them into 2 to 5 distinct categories (for example: Job Recommendations, Account Notices, Marketing Offers). "
        f"For each category, provide:\n"
        f"Category: <Name>\n"
        f"Description: <1-2 sentences>\n"
        f"Keywords: <comma separated subject keywords>\n"
        f"<|im_end|>\n"
        f"<|im_start|>user\n"
        f"Emails:\n{samples_text}\n"
        f"<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    cluster_output = generate_local_text(cluster_prompt, max_new_tokens=400, temperature=0.2)

    categories = []
    cat_blocks = re.split(r"(?:Category:|\n###|\n\d+\.)", cluster_output)
    for block in cat_blocks:
        block = block.strip()
        if not block or len(block) < 10:
            continue
        lines = block.split("\n")
        cat_name = lines[0].replace("Category:", "").strip()
        cat_name = re.sub(r"^[0-9\.\-\:\*\#\s]+", "", cat_name).strip()
        if not cat_name:
            continue

        desc = ""
        keywords = []
        for line in lines[1:]:
            line_str = line.strip()
            if line_str.lower().startswith("description:"):
                desc = line_str[12:].strip()
            elif line_str.lower().startswith("keywords:"):
                raw_kw = line_str[9:].strip()
                keywords = [k.strip().lower() for k in raw_kw.split(",") if k.strip()]

        if not desc:
            desc = f"Emails related to {cat_name}."

        categories.append({
            "category_name": cat_name,
            "description": desc,
            "keywords": keywords,
            "message_ids": []
        })

    if not categories:
        categories = [
            {
                "category_name": "General Updates and Newsletters",
                "description": f"Standard recurring emails and updates from {sender_email}.",
                "keywords": [],
                "message_ids": []
            }
        ]

    cat_assignments = []
    for m in messages:
        m_id = m.get("message_id")
        sub_lower = (m.get("subject") or "").lower()
        sum_lower = (m.get("summary") or "").lower()

        assigned_cat = categories[0]
        for cat in categories:
            for kw in cat.get("keywords", []):
                if kw in sub_lower or kw in sum_lower:
                    assigned_cat = cat
                    break
            if assigned_cat != categories[0]:
                break

        assigned_cat["message_ids"].append(m_id)
        cat_assignments.append((assigned_cat["category_name"], m_id))

    save_message_categories_batch(cat_assignments)

    final_categories = []
    for cat in categories:
        count = len(cat["message_ids"])
        if count == 0 and len(categories) > 1:
            continue

        kw_list = cat.get("keywords", [])
        if kw_list:
            clean_kws = [f'"{k}"' if " " in k else k for k in kw_list[:4]]
            query_part = " OR ".join(clean_kws)
            gmail_query = f"from:{sender_email} ({query_part})"
        else:
            cat_words = [w.lower() for w in re.findall(r"\w+", cat["category_name"]) if len(w) > 3][:3]
            if cat_words:
                gmail_query = f"from:{sender_email} ({' OR '.join(cat_words)})"
            else:
                gmail_query = f"from:{sender_email}"

        final_categories.append({
            "category_name": cat["category_name"],
            "description": cat["description"],
            "message_count": count if count > 0 else len(messages),
            "gmail_query": gmail_query
        })

    save_sender_ai_categories(sender_email, final_categories)
    return final_categories

def run_sender_analysis(sender_email: str) -> None:
    try:
        messages = get_sender_messages_for_ai(sender_email)
        total_msgs = len(messages)
        if total_msgs == 0:
            set_analysis_status(status="error", error="No emails found for this sender", stage="idle")
            return

        set_analysis_status(
            status="running",
            sender=sender_email,
            processed=0,
            total=total_msgs,
            percent=0,
            stage="summarizing",
            error=None
        )

        pending_summaries = [m for m in messages if not m.get("summary")]
        already_done = total_msgs - len(pending_summaries)

        batch_updates = []
        for idx, m in enumerate(pending_summaries):
            subj = m.get("subject", "No Subject")
            snippet = m.get("body_snippet", "")
            m_id = m.get("message_id")

            current_count = already_done + idx + 1
            pct = int((current_count / total_msgs) * 90)

            set_analysis_status(
                processed=current_count,
                percent=pct,
                current_subject=subj[:60],
                stage="summarizing"
            )

            summary = summarize_single_email(subj, snippet)
            m["summary"] = summary
            batch_updates.append((summary, m_id))

            if len(batch_updates) >= 15:
                save_message_summaries_batch(batch_updates)
                batch_updates = []

        if batch_updates:
            save_message_summaries_batch(batch_updates)

        set_analysis_status(
            processed=total_msgs,
            percent=92,
            stage="categorizing"
        )

        all_updated = get_sender_messages_for_ai(sender_email)
        create_categories_from_summaries(sender_email, all_updated)

        set_analysis_status(
            status="completed",
            processed=total_msgs,
            percent=100,
            stage="completed"
        )
    except Exception as e:
        set_analysis_status(status="error", error=str(e), stage="idle")

def start_sender_analysis_thread(sender_email: str) -> bool:
    cur = get_analysis_status()
    if cur["status"] == "running":
        return False
    t = threading.Thread(target=run_sender_analysis, args=(sender_email,), daemon=True)
    t.start()
    return True
