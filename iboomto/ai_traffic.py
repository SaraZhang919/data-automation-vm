"""GA4 AI-referral mapping and channel classification.

AI traffic is a session-attribution segment.  It is collected from GA4
``sessionSource`` rows and is assigned before normal Referral traffic so the
same session is never counted twice in the custom channel view.
"""
import re

AI_SOURCE_TAB = "AI Traffic Sources"
AI_TRAFFIC_TAB = "GA4 AI Traffic"
AI_MAPPING_VERSION = "ai-referral-v1"

# The list is deliberately explicit.  It is seeded once into the user-owned
# mapping tab and can then be extended without changing collector code.
DEFAULT_AI_TRAFFIC_SOURCES = [
    {"id": "chatgpt", "source_name": "ChatGPT", "pattern": r"(^|.*\.)chatgpt\.com$|(^|.*\.)chat\.openai\.com$", "priority": 10, "enabled": True, "match_dimension": "sessionSource", "description": "OpenAI ChatGPT referrals"},
    {"id": "perplexity", "source_name": "Perplexity", "pattern": r"(^|.*\.)perplexity\.ai$", "priority": 20, "enabled": True, "match_dimension": "sessionSource", "description": "Perplexity referrals"},
    {"id": "claude", "source_name": "Claude", "pattern": r"(^|.*\.)claude\.ai$", "priority": 30, "enabled": True, "match_dimension": "sessionSource", "description": "Anthropic Claude referrals"},
    {"id": "gemini", "source_name": "Gemini", "pattern": r"(^|.*\.)gemini\.google\.com$", "priority": 40, "enabled": True, "match_dimension": "sessionSource", "description": "Google Gemini referrals"},
    {"id": "copilot", "source_name": "Copilot", "pattern": r"(^|.*\.)copilot\.microsoft\.com$", "priority": 50, "enabled": True, "match_dimension": "sessionSource", "description": "Microsoft Copilot referrals"},
    {"id": "poe", "source_name": "Poe", "pattern": r"(^|.*\.)poe\.com$", "priority": 60, "enabled": True, "match_dimension": "sessionSource", "description": "Poe referrals"},
    {"id": "you", "source_name": "You.com", "pattern": r"(^|.*\.)you\.com$", "priority": 70, "enabled": True, "match_dimension": "sessionSource", "description": "You.com referrals"},
    {"id": "phind", "source_name": "Phind", "pattern": r"(^|.*\.)phind\.com$", "priority": 80, "enabled": True, "match_dimension": "sessionSource", "description": "Phind referrals"},
    {"id": "deepseek", "source_name": "DeepSeek", "pattern": r"(^|.*\.)deepseek\.com$", "priority": 90, "enabled": True, "match_dimension": "sessionSource", "description": "DeepSeek referrals"},
    {"id": "grok", "source_name": "Grok", "pattern": r"(^|.*\.)grok\.com$", "priority": 100, "enabled": True, "match_dimension": "sessionSource", "description": "Grok referrals"}
]


def _truthy(value):
    return value is True or str(value).strip().lower() in {"true", "1", "yes", "y"}


def source_rows(rows):
    """Return validated, enabled mappings, falling back to defaults."""
    raw = rows or DEFAULT_AI_TRAFFIC_SOURCES
    result = []
    for index, row in enumerate(raw):
        pattern = str(row.get("pattern", "")).strip()
        if not pattern or not _truthy(row.get("enabled", True)):
            continue
        try:
            re.compile(pattern, re.I)
        except re.error:
            # A bad user mapping must not break an otherwise valid GA run.
            continue
        result.append({
            "id": str(row.get("id") or row.get("source_name") or f"mapping-{index}").strip(),
            "source_name": str(row.get("source_name") or row.get("id") or "Unknown AI source").strip(),
            "pattern": pattern,
            "priority": int(float(row.get("priority", index + 1) or index + 1)),
            "enabled": True,
            "match_dimension": str(row.get("match_dimension") or "sessionSource"),
            "description": str(row.get("description") or ""),
            "mapping_version": str(row.get("mapping_version") or AI_MAPPING_VERSION)
        })
    return sorted(result, key=lambda item: (item["priority"], item["id"]))


def matches(row, mappings):
    """Return the first mapping matching a GA4 source row."""
    source = str(row.get("sessionSource") or row.get("session_source") or "").strip().lower()
    medium = str(row.get("sessionMedium") or row.get("session_medium") or "").strip().lower()
    source_medium = str(row.get("sessionSourceMedium") or "").strip().lower()
    haystack = (source, source_medium, medium)
    for mapping in mappings:
        if any(re.search(mapping["pattern"], value, re.I) for value in haystack if value):
            return mapping
    return None


def api_filter(base_filter, mappings):
    """Add a bounded OR filter for the configured AI source patterns."""
    expressions = []
    for mapping in mappings:
        # sessionSource is the stable session-scoped attribution dimension.
        # Patterns are written to match the complete source value.
        expressions.append({"filter": {"fieldName": "sessionSource", "stringFilter": {
            "matchType": "FULL_REGEXP", "value": mapping["pattern"]
        }}})
    if expressions:
        base_filter.setdefault("andGroup", {}).setdefault("expressions", []).append({"orGroup": {"expressions": expressions}})
    return base_filter
