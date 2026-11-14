"""Accept API Gateway REST API requests and start onboarding.

Required environment variables:
    REQUESTS_TABLE_NAME
    STATE_MACHINE_ARN

Deployment configuration will be added to template.yaml.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.validation.app import validate_request


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

    if event.get("isBase64Encoded"):
        return response(
            400,
            {"message": "Send an unencoded JSON request body."},
        )

    body = event.get("body")

    if not isinstance(body, str):
        return response(400, {"message": "A JSON body is required."})

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, RecursionError):
        return response(400, {"message": "Body must be valid JSON."})

    validation = validate_request(payload)

    if not validation["isValid"]:
        return response(
            400,
            {
                "message": "Request validation failed.",
                "errors": validation["errors"],
            },
        )

    request_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        "requestId": request_id,
        **validation["customer"],
        "status": "SUBMITTED",
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }

    table = dynamodb.Table(os.environ["REQUESTS_TABLE_NAME"])

    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(requestId)",
        )
    except (ClientError, BotoCoreError):
        logger.error(
            "Request storage did not confirm success: requestId=%s",
            request_id,
        )
        return response(
            503,
            {
                "message": "Request storage could not be confirmed.",
                "requestId": request_id,
            },
        )

    try:
        stepfunctions.start_execution(
            stateMachineArn=os.environ["STATE_MACHINE_ARN"],
            name=request_id,
            input=json.dumps(item),
        )
    except (ClientError, BotoCoreError):
        # A timeout can occur after AWS accepts the execution.
        # Preserve SUBMITTED for reconciliation rather than
        # incorrectly recording a definitive workflow failure.
        logger.error(
            "Workflow start requires reconciliation: requestId=%s",
            request_id,
        )
        return response(
            503,
            {
                "message": (
                    "Request was stored, but workflow startup "
                    "could not be confirmed. Check its status "
                    "before submitting another request."
                ),
                "requestId": request_id,
            },
        )

    return response(
        202,
        {
            "requestId": request_id,
            "status": "SUBMITTED",
            "message": "Request accepted for processing.",
        },
    )
