"""Live web research for growth/expansion signals — Gemini + Google Search grounding.

`research_customer` asks Gemini (with the built-in Google Search tool) to find
real, recent expansion signals about a business and return a structured verdict.
Real source URLs come from the response's `grounding_metadata` (not the model's
free text), so evidence links are verifiable on camera.

Verified against google-genai 1.75.0:
  - grounding tool : types.Tool(google_search=types.GoogleSearch())
  - passed via     : GenerateContentConfig(tools=[tool])
  - citations at   : response.candidates[0].grounding_metadata.grounding_chunks[i].web.uri
Note: Search grounding cannot be combined with response_schema JSON mode, so the
model emits a JSON block in text which we parse tolerantly and then enrich with
the real grounded URLs.
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable, Optional

from shared.config import DEFAULT_MODEL

_TRANSIENT = (
    "503", "unavailable", "resource_exhausted", "overloaded", "high demand", "429",
)

_VALID_TYPES = ("expansion", "risk", "health", "neutral")
_VALID_SEVERITY = ("low", "medium", "high")

_PROMPT = """You are a B2B growth-signal researcher. Research the business below on the web and \
find the most significant REAL, RECENT (ideally last 12 months) growth or expansion signal: \
a new location/clinic opening, new senior hires, funding/acquisition, awards, or notable press.

Business: {name}
Location: {location}
Services: {services}

Use web search. Base every claim on what you actually find. If you find nothing concrete and \
recent, say so honestly (has_signal=false).

Respond with ONLY a single JSON object (no prose, no markdown fences) of exactly this shape:
{{
  "has_signal": true|false,
  "signal_type": "expansion"|"risk"|"health"|"neutral",
  "severity": "low"|"medium"|"high",
  "summary": "one or two sentences on the specific signal",
  "evidence": [{{"claim": "the specific fact", "source_url": "https://..."}}],
  "confidence": 0.0-1.0
}}"""


def _is_transient(err: str) -> bool:
    e = err.lower()
    return any(t in e for t in _TRANSIENT)


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of model text, tolerant of ```json fences."""
    if not text:
        return None
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _grounding_urls(resp) -> list[dict]:
    """Extract real {url, title} citations from grounding_metadata. Never raises."""
    out: list[dict] = []
    try:
        cands = getattr(resp, "candidates", None) or []
        for cand in cands:
            meta = getattr(cand, "grounding_metadata", None)
            chunks = getattr(meta, "grounding_chunks", None) or []
            for ch in chunks:
                web = getattr(ch, "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri:
                    out.append({"url": uri, "title": getattr(web, "title", "") or ""})
    except Exception:  # noqa: BLE001 — citations are best-effort
        return out
    return out


def _response_text(resp) -> str:
    """Best-effort text from a grounded response (some SDK paths leave .text empty)."""
    txt = getattr(resp, "text", None)
    if txt:
        return txt
    try:
        parts = resp.candidates[0].content.parts or []
        return "".join(getattr(p, "text", "") or "" for p in parts)
    except Exception:  # noqa: BLE001
        return ""


def _normalize(obj: dict, name: str, grounded: list[dict]) -> dict:
    """Validate/clamp model fields and attach real grounded source URLs."""
    has_signal = bool(obj.get("has_signal"))
    stype = obj.get("signal_type") if obj.get("signal_type") in _VALID_TYPES else "neutral"
    sev = obj.get("severity") if obj.get("severity") in _VALID_SEVERITY else "low"
    try:
        conf = max(0.0, min(1.0, float(obj.get("confidence", 0.0))))
    except (TypeError, ValueError):
        conf = 0.0

    evidence = []
    raw_ev = obj.get("evidence") or []
    if isinstance(raw_ev, list):
        for i, ev in enumerate(raw_ev):
            if not isinstance(ev, dict):
                continue
            claim = str(ev.get("claim", "")).strip()
            url = str(ev.get("source_url", "")).strip()
            # Prefer a real grounded URL; backfill if the model's looks empty/fake.
            if (not url.startswith("http")) and i < len(grounded):
                url = grounded[i]["url"]
            if claim:
                evidence.append({"claim": claim, "source_url": url})
    # If the model gave no evidence but grounding has URLs, surface them.
    if not evidence and grounded:
        evidence = [{"claim": g["title"] or "source", "source_url": g["url"]} for g in grounded[:3]]

    return {
        "name": name,
        "has_signal": has_signal,
        "signal_type": stype,
        "severity": sev,
        "summary": str(obj.get("summary", "")).strip(),
        "evidence": evidence,
        "confidence": conf,
        "grounded_urls": [g["url"] for g in grounded],
        "error": "",
    }


def _error_result(name: str, error: str) -> dict:
    return {
        "name": name,
        "has_signal": False,
        "signal_type": "neutral",
        "severity": "low",
        "summary": "",
        "evidence": [],
        "confidence": 0.0,
        "grounded_urls": [],
        "error": error,
    }


def research_customer(
    name: str,
    location: str = "",
    services: str = "",
    *,
    client=None,
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
    backoff: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Research one business for a real, recent expansion signal. Never raises.

    Returns a dict: has_signal, signal_type, severity, summary,
    evidence:[{claim, source_url}], confidence, plus name/grounded_urls/error.
    """
    name = (name or "").strip()
    if not name:
        return _error_result(name, "empty business name")

    prompt = _PROMPT.format(
        name=name, location=location or "(unknown)", services=services or "(unknown)"
    )

    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            from google import genai  # local import: no API key needed to import module
            from google.genai import types

            cli = client or genai.Client()
            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2,
            )
            resp = cli.models.generate_content(model=model, contents=prompt, config=config)
            text = _response_text(resp)
            grounded = _grounding_urls(resp)
            obj = _extract_json(text)
            if obj is None:
                last_error = "could not parse JSON from model response"
            else:
                return _normalize(obj, name, grounded)
        except Exception as e:  # noqa: BLE001 — surface as data, never crash the scan
            last_error = f"{type(e).__name__}: {e}"
            if not _is_transient(last_error):
                break
        if attempt < max_retries:
            sleep(backoff * (2**attempt))

    return _error_result(name, last_error)
