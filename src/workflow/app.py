"""Internal workflow tasks; never expose this handler through the API.

Required environment variable:
    REQUESTS_TABLE_NAME
"""

import os
from datetime import datetime, timezone

import boto3


dynamodb = boto3.resource("dynamodb")

ALLOWED_PREVIOUS_STATES = {
    "INVALID": ("SUBMITTED",),
    "APPROVED": ("PENDING_REVIEW",),
    "REJECTED": ("PENDING_REVIEW",),
    "EXPIRED": ("PENDING_REVIEW",),
    "FAILED": ("SUBMITTED", "PENDING_REVIEW"),
}


def lambda_handler(event, context):
    if not isinstance(event, dict):
        raise ValueError("Workflow input must be an object.")

    request_id = event.get("requestId")
    action = event.get("action")

    if not isinstance(request_id, str) or not request_id:
        raise ValueError("requestId is required.")

    table = dynamodb.Table(os.environ["REQUESTS_TABLE_NAME"])
    timestamp = datetime.now(timezone.utc).isoformat()

    if action == "register_review":
        token = event.get("taskToken")

        if not isinstance(token, str) or not token:
            raise ValueError("taskToken is required.")

        table.update_item(
            Key={"requestId": request_id},
            UpdateExpression=(
                "SET #status = :pending, "
                "taskToken = :token, updatedAt = :now"
            ),
            ConditionExpression=(
                "attribute_exists(requestId) AND "
                "(#status = :submitted OR "
                "(#status = :pending AND taskToken = :token))"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":submitted": "SUBMITTED",
                ":pending": "PENDING_REVIEW",
                ":token": token,
                ":now": timestamp,
            },
        )

        # Never return or log the callback token.
        return {
            "requestId": request_id,
            "status": "PENDING_REVIEW",
        }

    if action != "set_status":
        raise ValueError("Unsupported workflow action.")

    target_status = event.get("status")

    if target_status not in ALLOWED_PREVIOUS_STATES:
        raise ValueError("Unsupported target status.")

    previous_states = ALLOWED_PREVIOUS_STATES[target_status]

    values = {
        ":target": target_status,
        ":now": timestamp,
    }
    placeholders = []

    for index, status in enumerate(previous_states):
        placeholder = f":previous{index}"
        placeholders.append(placeholder)
        values[placeholder] = status

    allowed = ", ".join(placeholders)

    table.update_item(
        Key={"requestId": request_id},
        UpdateExpression=(
            "SET #status = :target, updatedAt = :now "
            "REMOVE taskToken"
        ),
        ConditionExpression=(
            "attribute_exists(requestId) AND "
            f"(#status IN ({allowed}) OR #status = :target)"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=values,
    )

    return {
        "requestId": request_id,
        "status": target_status,
    }
