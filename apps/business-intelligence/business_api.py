"""Read-only Business API MCP adapter; reusable product source, no host authority.

This module intentionally never accesses Fabric or CRM storage directly.
Business API enforces user entitlements and source rights.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request

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
        parts = urlsplit(base_url)
        if (parts.scheme != "https" or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.query or parts.fragment or not token):
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
            # A permissive aggregate flag cannot override a restricted source.
            # Preserve an explicit deny even when an upstream API has a bug.
            if (source.get("redistribution_allowed") is False
                    or source.get("rights_status") in ("DENIED", "RESTRICTED", "UNKNOWN")):
                raise BusinessApiError("BUSINESS_API_SOURCE_RIGHTS_NOT_GRANTED")
        return result

    def company_by_oib(self, oib: str):
        if len(oib) != 11 or not oib.isascii() or not oib.isdigit():
            raise BusinessApiError("OIB_FORMAT_INVALID")
        return self.get("/api/business/v1/companies/" + quote(oib, safe=""))

    def profile_by_identifier(self, *, oib=None, subject_id=None,
                              identifier_type=None, identifier_value=None,
                              source_id=None, limit=20):
        """Typed Fabric identity query via the *central* Business API, never P620 directly."""
        selectors = sum((oib is not None, subject_id is not None,
                         identifier_type is not None or identifier_value is not None))
        if selectors != 1:
            raise BusinessApiError("EXACTLY_ONE_IDENTIFIER_REQUIRED")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise BusinessApiError("PROFILE_PAGE_LIMIT_INVALID")
        params = {"limit": limit}
        if oib is not None:
            if not isinstance(oib, str) or len(oib) != 11 or not oib.isascii() or not oib.isdigit():
                raise BusinessApiError("OIB_FORMAT_INVALID")
            params["oib"] = oib
        elif subject_id is not None:
            if not isinstance(subject_id, str) or not __import__("re").fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", subject_id):
                raise BusinessApiError("SUBJECT_ID_INVALID")
            params["subject_id"] = subject_id
        else:
            import re
            kind = str(identifier_type or "").strip().upper()
            value = str(identifier_value or "").strip()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", kind) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,127}", value):
                raise BusinessApiError("TYPED_IDENTIFIER_INVALID")
            params.update(identifier_type=kind, identifier_value=value)
            if kind not in {"OIB", "MBS", "MB", "VAT_ID", "LEI"} and not source_id:
                raise BusinessApiError("SOURCE_SCOPE_REQUIRED")
            if source_id is not None:
                if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", source_id):
                    raise BusinessApiError("SOURCE_SCOPE_INVALID")
                params["source_id"] = source_id.upper()
        result = self.get("/api/business/v1/profiles?" + urlencode(params))
        identity = result.get("data", {}).get("identity")
        if not isinstance(identity, dict):
            raise BusinessApiError("PROFILE_IDENTITY_MISSING")
        if "oib" in params and identity.get("oib") != params["oib"]:
            raise BusinessApiError("PROFILE_IDENTITY_MISMATCH")
        if "subject_id" in params and identity.get("subject_id") != params["subject_id"]:
            raise BusinessApiError("PROFILE_IDENTITY_MISMATCH")
        if "identifier_type" in params and not any(
            isinstance(row, dict)
            and row.get("identifier_type", "").upper() == params["identifier_type"]
            and row.get("identifier_value") == params["identifier_value"]
            and (not params.get("source_id") or row.get("source_id", "").upper() == params["source_id"])
            for row in (identity.get("identifiers") or [])
        ):
            raise BusinessApiError("PROFILE_IDENTITY_MISMATCH")
        return result

    def company_source_provenance_by_oib(self, oib: str):
        """Return only the verified data-source trail; enforce the same rights gate."""
        envelope = self.company_by_oib(oib)
        return {
            "oib": oib,
            "as_of": envelope["meta"]["as_of"],
            "provenance": envelope["meta"]["provenance"],
            "redistribution_allowed": True,
        }
