"""Retrieve onboarding status through API Gateway REST API.

Required environment variable:
    REQUESTS_TABLE_NAME

Authentication and authorization are configured separately.
"""

import json
import logging
import os
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")


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

    if not isinstance(parameters, dict):
        return response(400, {"message": "Invalid path parameters."})

    request_id = parameters.get("requestId")

    if not isinstance(request_id, str):
        return response(400, {"message": "requestId is required."})

    try:
        parsed_id = uuid.UUID(request_id)
    except ValueError:
        return response(400, {"message": "Invalid requestId format."})

    if str(parsed_id) != request_id:
        return response(400, {"message": "Invalid requestId format."})

    table = dynamodb.Table(os.environ["REQUESTS_TABLE_NAME"])

    try:
        result = table.get_item(
            Key={"requestId": request_id},
            ConsistentRead=True,
            ProjectionExpression=(
                "requestId, #status, createdAt, updatedAt"
            ),
            ExpressionAttributeNames={"#status": "status"},
        )
    except (ClientError, BotoCoreError):
        logger.error(
            "Status retrieval failed: requestId=%s",
            request_id,
        )
        return response(
            503,
            {"message": "Request status is temporarily unavailable."},
        )

    item = result.get("Item")

    if not item:
        return response(404, {"message": "Request not found."})

    return response(200, item)
