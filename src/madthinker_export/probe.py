"""Endpoint probe: prove that a URL is the correct, live export endpoint.

This is a *diagnostic*, not part of the sync contract. It exists because the
single most common integration failure is calling the wrong URL — the response
is a bare ``404`` that says nothing about what is wrong. The probe localises the
fault in two layers:

1. **Static** (offline, deterministic): compare the URL against the canonical
   value baked into the sample (:data:`CANONICAL`). Catches host/path typos with
   no key and no network.
2. **Live** (one ``GET``, no retries): classify the response so the status code
   tells you exactly where it's wrong —

   ===== ===================================================
   404   function not at this URL          → URL WRONG
   401   function reached, key missing/bad → URL RIGHT, key wrong
   400   function reached, params off      → URL RIGHT
   200   function reached + key valid      → FULLY VALIDATED (shape checked)
   ===== ===================================================

Unlike the sync client this deliberately does **not** retry and tolerates a
missing key: a keyless call against the right URL returns 401, against a wrong
URL returns 404 — that split is itself proof of where the problem lives.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import requests

# The one true endpoint, identical to config.env / README / docs / config.py.
CANONICAL = "https://koxeklkffxewmkasocvk.supabase.co/functions/v1/tca-catch-reports-export"

PROBE_TIMEOUT = 30


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of a probe. ``ok`` is true only when fully validated (200 + shape)."""

    ok: bool
    verdict: str


def _parts(url: str) -> tuple[str, str, str]:
    """(scheme, host, path) lower-cased, with query/fragment and trailing slash dropped."""
    p = urlsplit(url.strip())
    return p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/").lower()


def static_diff(url: str) -> list[str]:
    """Human-readable mismatches between ``url`` and :data:`CANONICAL` (empty == match)."""
    got = _parts(url)
    want = _parts(CANONICAL)
    labels = ("scheme", "host", "path")
    return [
        f"{label}: got {g!r}, expected {w!r}"
        for label, g, w in zip(labels, got, want, strict=True)
        if g != w
    ]


def _error_text(response) -> str:
    """Pull ``error``/``message`` from a JSON body, tolerating a non-JSON one."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        return body.get("error") or body.get("message") or ""
    return ""


def _live_verdict(url: str, api_key: str | None, session, timeout: float) -> tuple[bool, str]:
    headers = {"x-tca-api-key": api_key} if api_key else {}
    params = {"since": "1970-01-01T00:00:00Z", "limit": 1}
    try:
        response = session.get(url, headers=headers, params=params, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        return False, f"NETWORK ERROR -- could not reach host. {exc}"

    code = response.status_code
    if code == 200:
        try:
            body = response.json()
        except ValueError:
            body = None
        if (
            isinstance(body, dict)
            and isinstance(body.get("rows"), list)
            and "next_cursor" in body
            and isinstance(body.get("has_more"), bool)
        ):
            n = body.get("returned_count", len(body["rows"]))
            return True, f"FULLY VALIDATED -- 200 OK, contract matches, {n} row(s) returned."
        return False, "200 OK but the JSON does not match the contract (rows/next_cursor/has_more)."

    msg = _error_text(response)
    if code == 404:
        return False, f"URL WRONG -- 404 Not Found; no function at this URL. {msg}".strip()
    if code == 401:
        text = f"URL RIGHT, KEY WRONG -- 401; function reached, key missing/invalid. {msg}"
        return False, text.strip()
    if code == 400:
        return False, f"URL RIGHT -- 400 Bad Request; function reached, check params. {msg}".strip()
    if code == 429:
        return False, "URL RIGHT -- 429 rate limited; function reached, retry later."
    return False, f"Unexpected HTTP {code}. {msg}".strip()


def probe(
    url: str,
    api_key: str | None = None,
    *,
    session=None,
    timeout: float = PROBE_TIMEOUT,
) -> ProbeResult:
    """Run the static and live checks and return a verdict.

    ``ok`` is true only when the URL matches the canonical endpoint *and* a live
    call returns 200 with the expected contract shape.
    """
    session = session or requests.Session()
    notes = static_diff(url)

    lines = [f"Probing:   {url}", f"Canonical: {CANONICAL}", ""]
    if notes:
        lines.append("STATIC CHECK: FAIL -- URL does not match the canonical endpoint:")
        lines += [f"  - {note}" for note in notes]
    else:
        lines.append("STATIC CHECK: PASS -- URL matches the canonical endpoint.")

    if api_key is None:
        lines.append("(No API key given -- a correct URL returns 401, a wrong URL returns 404.)")

    live_ok, live_verdict = _live_verdict(url, api_key, session, timeout)
    lines.append(f"LIVE CHECK:   {live_verdict}")

    return ProbeResult(ok=live_ok and not notes, verdict="\n".join(lines))
