"""
Zep Ontology Definitions

Define custom entity types for the Zep knowledge graph that align with our domain.
These provide structured entity extraction while keeping Neon payload flexible.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class CompanyEntity(BaseModel):
    """
    Company entity type for Zep graph.

    Extracted from flexible Neon V2 payload when fields are available.
    """
    name: str = Field(description="Company legal name")
    domain: str = Field(description="Company domain (e.g., evercore.com)")

    # Optional structured fields - extracted from payload if available
    industry: Optional[str] = Field(None, description="Primary industry")
    headquarters_city: Optional[str] = Field(None, description="HQ city")
    headquarters_country: Optional[str] = Field(None, description="HQ country")
    founded_year: Optional[int] = Field(None, description="Year founded")
    employee_range: Optional[str] = Field(None, description="Employee count range")
    company_type: Optional[str] = Field(None, description="Type: placement_agent, etc.")


class DealEntity(BaseModel):
    """
    Deal/Transaction entity type for Zep graph.

    Extracted from narrative sections when deal information is found.
    """
    deal_name: str = Field(description="Deal name or description")
    deal_type: Optional[str] = Field(None, description="M&A, capital_raising, IPO, etc.")
    value: Optional[str] = Field(None, description="Deal value (e.g., '$7.4B')")
    date: Optional[str] = Field(None, description="Deal date or timeframe")
    parties: Optional[List[str]] = Field(None, description="Companies involved")


class PersonEntity(BaseModel):
    """
    Person entity type for Zep graph.

    Extracted when key people/executives are mentioned.
    """
    name: str = Field(description="Person's full name")
    role: Optional[str] = Field(None, description="Job title or role")
    company: Optional[str] = Field(None, description="Associated company")


# Entity type configurations for Zep
COMPANY_ENTITY_TYPE = {
    "type": "Company",
    "description": "Investment banking firms, placement agents, financial institutions",
    "properties": {
        "name": {"type": "string", "required": True},
        "domain": {"type": "string", "required": True},
        "industry": {"type": "string"},
        "headquarters_city": {"type": "string"},
        "headquarters_country": {"type": "string"},
        "founded_year": {"type": "integer"},
        "employee_range": {"type": "string"},
        "company_type": {"type": "string"}
    }
}

DEAL_ENTITY_TYPE = {
    "type": "Deal",
    "description": "Transactions, M&A deals, capital raises, IPOs",
    "properties": {
        "deal_name": {"type": "string", "required": True},
        "deal_type": {"type": "string"},
        "value": {"type": "string"},
        "date": {"type": "string"},
        "parties": {"type": "array"}
    }
}

PERSON_ENTITY_TYPE = {
    "type": "Person",
    "description": "Executives, key people, board members",
    "properties": {
        "name": {"type": "string", "required": True},
        "role": {"type": "string"},
        "company": {"type": "string"}
    }
}

# Edge types for relationships
EDGE_TYPES = {
    "ADVISED_ON": {
        "from": "Company",
        "to": "Deal",
        "description": "Company advised on a deal"
    },
    "WORKS_AT": {
        "from": "Person",
        "to": "Company",
        "description": "Person works at company"
    },
    "INVESTED_IN": {
        "from": "Company",
        "to": "Company",
        "description": "Company invested in another company"
    },
    "PARTNERED_WITH": {
        "from": "Company",
        "to": "Company",
        "description": "Companies have partnership"
    }
}


def extract_company_entity_from_payload(company_name: str, domain: str, payload: dict) -> dict:
    """
    Extract structured company entity data from flexible V2 payload.

    Args:
        company_name: Company name
        domain: Company domain
        payload: V2 flexible payload

    Returns:
        Dict with Company entity attributes
    """
    return {
        "name": company_name,
        "domain": domain,
        "industry": payload.get("industry"),
        "headquarters_city": payload.get("headquarters_city"),
        "headquarters_country": payload.get("headquarters_country"),
        "founded_year": payload.get("founded_year"),
        "employee_range": payload.get("employee_range"),
        "company_type": payload.get("company_type", "unknown")
    }
