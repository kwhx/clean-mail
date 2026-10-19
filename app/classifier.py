import re
from typing import Dict, Any, Tuple

WEBMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "zoho.com", "gmx.com",
    "gmx.net", "mail.com", "yandex.com", "fastmail.com", "hey.com"
}

NEWSLETTER_NAME_KEYWORDS = {
    "newsletter", "digest", "weekly", "daily", "monthly", "dispatch",
    "bulletin", "insights", "roundup", "updates", "marketing", "promo",
    "promotions", "offers", "deals", "discounts", "clearance", "sale",
    "announcements", "editorial", "curated", "substack", "medium", "mailchimp"
}

ORGANIZATION_NAME_KEYWORDS = {
    "support", "billing", "team", "no-reply", "noreply", "service",
    "services", "security", "notifications", "alerts", "helpdesk",
    "operations", "desk", "invoicing", "customer care", "finance",
    "engineering", "system", "administrator", "orders", "verification"
}

TRANSACTIONAL_PREFIXES = {
    "noreply", "no-reply", "donotreply", "orders", "order", "receipts",
    "receipt", "billing", "invoice", "invoices", "support", "help",
    "notifications", "notification", "alerts", "alert", "security",
    "verify", "verification", "account", "service", "system", "auth"
}

MARKETING_PREFIXES = {
    "news", "newsletter", "marketing", "promo", "promotions", "deals",
    "offers", "events", "editor", "editorial", "digest", "info", "campaign"
}

TRANSACTIONAL_SUBJECT_KEYWORDS = {
    "receipt", "invoice", "order confirmation", "shipped", "tracking",
    "security alert", "password reset", "verification code", "two-factor",
    "statement", "payment received", "scheduled maintenance", "account update",
    "booking confirmed", "flight itinerary", "wire transfer", "deposit"
}

PROMOTIONAL_SUBJECT_KEYWORDS = {
    "discount", "off", "coupon", "limited time", "exclusive", "free shipping",
    "special offer", "save big", "sale", "newsletter", "weekly digest",
    "curated for you", "don't miss out", "flash sale", "weekend special"
}

def is_webmail_domain(domain: str) -> bool:
    return domain.lower() in WEBMAIL_DOMAINS

def analyze_message_intent(headers: Dict[str, str], subject: str = "") -> Tuple[bool, bool]:
    subj_lower = subject.lower()
    is_trans = False
    is_promo = False

    for kw in TRANSACTIONAL_SUBJECT_KEYWORDS:
        if kw in subj_lower:
            is_trans = True
            break

    for kw in PROMOTIONAL_SUBJECT_KEYWORDS:
        if kw in subj_lower:
            is_promo = True
            break

    has_unsub = bool(headers.get("List-Unsubscribe") or headers.get("List-Unsubscribe-Post"))
    precedence = headers.get("Precedence", "").lower()
    is_bulk = precedence in ("bulk", "list") or "bulk" in headers.get("X-Precedence", "").lower()

    if has_unsub or is_bulk:
        is_promo = True

    if not is_trans and not is_promo:
        x_auto = headers.get("X-Auto-Response-Suppress", "") or headers.get("Auto-Submitted", "")
        if x_auto:
            is_trans = True

    return is_trans, is_promo

def classify_sender(
    email: str,
    name: str = "",
    headers_sample: Dict[str, str] = None,
    subject_sample: str = "",
    historical_stats: Dict[str, Any] = None
) -> Tuple[str, float, bool]:
    headers_sample = headers_sample or {}
    email_clean = email.strip().lower()
    name_clean = name.strip().lower() if name else ""

    parts = email_clean.split("@")
    if len(parts) == 2:
        handle, domain = parts
    else:
        handle, domain = email_clean, "unknown.com"

    is_webmail = is_webmail_domain(domain)
    has_unsub = bool(headers_sample.get("List-Unsubscribe") or headers_sample.get("List-Unsubscribe-Post"))
    precedence = headers_sample.get("Precedence", "").lower()
    is_bulk = precedence in ("bulk", "list")

    name_tokens = set(re.findall(r"[a-z0-9\-]+", name_clean))
    has_news_name = any(k in name_tokens for k in NEWSLETTER_NAME_KEYWORDS)
    has_org_name = any(k in name_tokens for k in ORGANIZATION_NAME_KEYWORDS)

    clean_handle = re.sub(r"[0-9\._\-]", "", handle)
    has_trans_prefix = handle in TRANSACTIONAL_PREFIXES or any(handle.startswith(p) for p in TRANSACTIONAL_PREFIXES)
    has_mkt_prefix = handle in MARKETING_PREFIXES or any(handle.startswith(p) for p in MARKETING_PREFIXES)

    is_trans_subj, is_promo_subj = analyze_message_intent(headers_sample, subject_sample)

    if historical_stats:
        trans_count = historical_stats.get("transactional_count", 0)
        promo_count = historical_stats.get("promotional_count", 0)
        if trans_count > 0 and promo_count > 0:
            return "mixed", 0.95, False

    if has_unsub and is_trans_subj:
        return "mixed", 0.90, False

    if has_unsub or is_bulk or has_news_name or has_mkt_prefix or is_promo_subj:
        if has_trans_prefix and not has_unsub:
            return "organizations", 0.85, False
        is_junk = bool(has_unsub or is_bulk or has_mkt_prefix)
        return "newsletters", 0.92, is_junk

    if not is_webmail:
        if has_org_name or has_trans_prefix or is_trans_subj:
            return "organizations", 0.94, False
        return "organizations", 0.85, False

    if is_webmail:
        if has_trans_prefix or has_org_name:
            return "organizations", 0.88, False
        return "people", 0.96, False

    return "organizations", 0.80, False
