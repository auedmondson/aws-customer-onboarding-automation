"""Validate synthetic customer onboarding requests.

Expected workflow input:
{
    "requestId": "example-request-id",
    "businessName": "Example Company",
    "contactName": "Jordan Smith",
    "contactEmail": "jordan@example.com"
}

This function returns validation results without logging customer data.
It does not write to DynamoDB; workflow tasks handle status updates.
"""

import re
from typing import Any


# Basic format screening, not email ownership verification.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

FIELD_LIMITS = {
    "businessName": 200,
    "contactName": 100,
    "contactEmail": 254,
}


def validate_request(payload: Any) -> dict:
    """Validate required fields and return normalized customer data."""
    if not isinstance(payload, dict):
        return {
            "isValid": False,
            "errors": ["Request must be a JSON object."],
        }

    errors = []
    normalized = {}

    for field, max_length in FIELD_LIMITS.items():
        value = payload.get(field)

        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string.")
            continue

        value = value.strip()

        if len(value) > max_length:
            errors.append(
                f"{field} must not exceed {max_length} characters."
            )
            continue

        normalized[field] = value

    email = normalized.get("contactEmail")
    if email and not EMAIL_PATTERN.fullmatch(email):
        errors.append("contactEmail must have a valid email format.")

    if errors:
        return {
            "isValid": False,
            "errors": errors,
        }

    return {
        "isValid": True,
        "errors": [],
        "customer": normalized,
    }


def lambda_handler(event: Any, context: Any) -> dict:
    """Return a result that Step Functions can evaluate."""
    return validate_request(event)
