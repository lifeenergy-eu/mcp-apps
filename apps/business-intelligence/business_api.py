"""Read-only Business API MCP adapter; reusable product source, no host authority.

This module intentionally never accesses Fabric or CRM storage directly.
Business API enforces user entitlements and source rights.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.parse import quote
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 524288


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_urlopen(request, timeout):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


class BusinessApiError(RuntimeError):
    pass


class BusinessApiClient:
    def __init__(self, base_url: str, token: str):
        if not base_url.startswith("https://") or not token or "@" in base_url.split("/")[2]:
            raise BusinessApiError("HTTPS_BASE_URL_AND_SERVICE_TOKEN_REQUIRED")
        self.base_url = base_url.rstrip("/")
        self.token = token

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("BUSINESS_API_BASE_URL", ""), os.environ.get("BUSINESS_API_SERVICE_TOKEN", ""))

    def get(self, path: str):
        request = Request(
            self.base_url + path,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/json"},
            method="GET",
        )
        try:
            with _safe_urlopen(request, timeout=12) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise BusinessApiError("API_RESPONSE_TOO_LARGE")
        except HTTPError as exc:
            raise BusinessApiError("BUSINESS_API_HTTP_" + str(exc.code)) from exc
        except (URLError, TimeoutError) as exc:
            raise BusinessApiError("BUSINESS_API_UNAVAILABLE") from exc
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeDecodeError) as exc:
            raise BusinessApiError("BUSINESS_API_INVALID_JSON") from exc
        if not isinstance(result, dict):
            raise BusinessApiError("BUSINESS_API_INVALID_ENVELOPE")
        if "data" not in result or not isinstance(result.get("meta"), dict):
            raise BusinessApiError("BUSINESS_API_PROVENANCE_ENVELOPE_REQUIRED")
        meta = result["meta"]
        if not isinstance(meta.get("provenance"), list) or not isinstance(meta.get("as_of"), str):
            raise BusinessApiError("BUSINESS_API_PROVENANCE_ENVELOPE_REQUIRED")
        if meta.get("redistribution_allowed") is not True:
            raise BusinessApiError("BUSINESS_API_RIGHTS_NOT_GRANTED")
        if not meta["provenance"] or not meta["as_of"]:
            raise BusinessApiError("BUSINESS_API_SOURCE_TRAIL_REQUIRED")
        for source in meta["provenance"]:
            if (not isinstance(source, dict)
                    or not isinstance(source.get("source_key"), str)
                    or not source["source_key"].strip()
                    or not isinstance(source.get("retrieved_at"), str)
                    or not source["retrieved_at"].strip()):
                raise BusinessApiError("BUSINESS_API_SOURCE_TRAIL_REQUIRED")
        return result

    def company_by_oib(self, oib: str):
        if len(oib) != 11 or not oib.isascii() or not oib.isdigit():
            raise BusinessApiError("OIB_FORMAT_INVALID")
        return self.get("/api/business/v1/companies/" + quote(oib, safe=""))
