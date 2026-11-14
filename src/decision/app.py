"""Submit an approval or rejection through API Gateway REST API.

Required environment variable:
    REQUESTS_TABLE_NAME

The API must restrict this handler to authorized reviewers.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
stepfunctions = boto3.client("stepfunctions")


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    if not isinstance(event, dict):
        return response(400, {"message": "Invalid API event."})

    parameters = event.get("pathParameters") or {}
    request_id = (
        parameters.get("requestId")
        if isinstance(parameters, dict)
        else None
    )

    try:
        if not isinstance(request_id, str):
            raise ValueError
        if str(uuid.UUID(request_id)) != request_id:
            raise ValueError
    except ValueError:
        return response(400, {"message": "Invalid requestId."})

    if event.get("isBase64Encoded"):
        return response(400, {"message": "Send an unencoded JSON body."})

    body = event.get("body")

    if not isinstance(body, str):
        return response(400, {"message": "A JSON body is required."})

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, RecursionError):
        return response(400, {"message": "Body must be valid JSON."})

    decision = payload.get("decision") if isinstance(payload, dict) else None

    if decision not in ("APPROVED", "REJECTED"):
        return response(
            400,
            {"message": "decision must be APPROVED or REJECTED."},
        )

    table = dynamodb.Table(os.environ["REQUESTS_TABLE_NAME"])
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        # Persist the first decision before sending the callback.
        # A retry may repeat that decision but cannot reverse it.
        result = table.update_item(
            Key={"requestId": request_id},
            UpdateExpression=(
                "SET reviewDecision = :decision, "
                "decisionAt = if_not_exists(decisionAt, :now), "
                "updatedAt = :now"
            ),
            ConditionExpression=(
                "attribute_exists(requestId) AND "
                "#status = :pending AND attribute_exists(taskToken) AND "
                "(attribute_not_exists(reviewDecision) OR "
                "reviewDecision = :decision)"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":decision": decision,
                ":pending": "PENDING_REVIEW",
                ":now": timestamp,
            },
            ReturnValues="ALL_NEW",
        )

        token = result["Attributes"]["taskToken"]

        stepfunctions.send_task_success(
            taskToken=token,
            output=json.dumps({"decision": decision}),
        )

    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")

        if code == "ConditionalCheckFailedException":
            return response(
                409,
                {
                    "message": (
                        "Request is unavailable for review or "
                        "already has a conflicting decision."
                    )
                },
            )

        if code in ("TaskTimedOut", "TaskDoesNotExist", "InvalidToken"):
            return response(
                409,
                {
                    "message": (
                        "Review is no longer active. "
                        "Check the request's current status."
                    )
                },
            )

        logger.error(
            "Decision delivery requires verification: requestId=%s",
            request_id,
        )
        return response(
            503,
            {
                "message": (
                    "Decision delivery could not be confirmed. "
                    "Check status before retrying the same decision."
                ),
                "requestId": request_id,
            },
        )

    except BotoCoreError:
        logger.error(
            "Decision delivery requires verification: requestId=%s",
            request_id,
        )
        return response(
            503,
            {
                "message": (
                    "Decision delivery could not be confirmed. "
                    "Check status before retrying the same decision."
                ),
                "requestId": request_id,
            },
        )

    return response(
        202,
        {
            "requestId": request_id,
            "decision": decision,
            "message": "Decision accepted; status update is pending.",
        },
    )
