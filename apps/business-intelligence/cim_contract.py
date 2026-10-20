"""CIM MCP read-tool registry. Source-only: no customer activation.

The existing HTTPS FastMCP server and Business API remain the only transports.
Never accept tenant, scope or Terms claims supplied as tool parameters.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolContract:
    name: str
    required_scope: str
    route: str
    customer_enabled: bool = False


# The first four names match the existing FastMCP @mcp.tool() surface exactly.
# CIM customer tools remain excluded from tools/list until the integration
# coordinator wires verified end-user access tokens to Laravel authorization.
TOOLS = (
    ToolContract("company_profile_by_oib", "business.read", "/ci-api/business/v1/companies/{oib}"),
    ToolContract("company_source_provenance_by_oib", "business.read", "/ci-api/business/v1/companies/{oib}"),
    ToolContract("business_profile_by_identifier", "business.read", "/ci-api/business/v1/profiles"),
    ToolContract("business_profile_by_subject_id", "business.read", "/ci-api/business/v1/profiles"),
)

# Planned typed CIM capability is a registry entry, NOT a publicly exposed tool.
CIM_CANDIDATES = (
    ToolContract("cim_mission_list", "cim.missions.read", "/ci-api/business/v1/cim/missions"),
    ToolContract("cim_opportunity_list", "cim.opportunities.read", "/ci-api/business/v1/cim/opportunities"),
    ToolContract("cim_recommendation_list", "cim.recommendations.read", "/ci-api/business/v1/cim/recommendations"),
)


class CimAccessDenied(PermissionError):
    pass


def require_verified_customer_context(context: dict | None) -> None:
    """Fail closed until a verified human principal comes from trusted middleware.

    A decoded JWT, MCP client ID, service bearer or caller-provided context is
    never sufficient evidence of a human user, tenant membership and Terms.
    The IAM/Business API lanes must supply server-verified evidence at integration.
    """
    if not isinstance(context, dict) or context.get("verification_source") != "laravel_cim_authority":
        raise CimAccessDenied("CIM_VERIFIED_AUTHORITY_REQUIRED")
    if context.get("principal_kind") != "human" or not context.get("subject"):
        raise CimAccessDenied("CIM_HUMAN_PRINCIPAL_REQUIRED")
    if not context.get("tenant_id") or context.get("membership_active") is not True:
        raise CimAccessDenied("CIM_ACTIVE_TENANT_MEMBERSHIP_REQUIRED")
    if context.get("terms_accepted") is not True or context.get("revoked") is not False:
        raise CimAccessDenied("CIM_TERMS_OR_REVOCATION_DENIED")
    # This is only an integration contract assertion. It MUST NOT be used as
    # standalone authentication based on unverified user-supplied dictionaries.


def public_customer_tools_enabled() -> bool:
    """No customer tools until end-to-end verified user authorization is wired."""
    return False
