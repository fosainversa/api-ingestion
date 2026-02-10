"""
Data Ingestion Lambda Handler
Receives JSON data and persists to DynamoDB
"""

import json
import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any
import boto3
from botocore.exceptions import ClientError

# Configure logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
table_name = os.environ.get("TABLE_NAME")
table = dynamodb.Table(table_name)
logger.info(f"Initialized with table: {table_name}")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for data ingestion.
    
    Args:
        event: API Gateway proxy event containing request data
        context: Lambda context object
    
    Returns:
        API Gateway proxy response
    """
    logger.info("Data ingestion handler invoked")
    
    try:
        # Extract user context from authorizer
        request_context = event.get("requestContext", {})
        authorizer_context = request_context.get("authorizer", {})
        user_id_from_token = authorizer_context.get("userId", "unknown")
        user_email = authorizer_context.get("email", "")
        
        logger.info(f"Request from user: {user_id_from_token} ({user_email})")
        
        # Parse request body
        try:
            body = json.loads(event.get("body", "{}"))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request body: {str(e)}")
            return create_response(400, {"error": "Invalid JSON format"})
        
        # Validate required fields (already validated by API Gateway, but double-check)
        if "userId" not in body or "data" not in body:
            logger.warning("Missing required fields in request")
            return create_response(400, {"error": "Missing required fields: userId, data"})
        
        # Extract fields
        user_id = body.get("userId")
        event_type = body.get("eventType", "unknown")
        data_payload = body.get("data", {})
        
        # Generate unique ID and timestamp
        item_id = str(uuid.uuid4())
        timestamp = int(datetime.now(timezone.utc).timestamp())
        
        # Prepare DynamoDB item
        item = {
            "id": item_id,
            "timestamp": timestamp,
            "userId": user_id,
            "eventType": event_type,
            "data": data_payload,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "authenticatedUser": user_id_from_token,
            "userEmail": user_email,
        }
        
        # Write to DynamoDB
        try:
            table.put_item(Item=item)
            logger.info(f"Item written successfully: {item_id}")
        except ClientError as e:
            logger.error(f"DynamoDB error: {str(e)}")
            return create_response(500, {"error": "Database error", "details": str(e)})
        
        # Return success response
        response_body = {
            "message": "Data ingested successfully",
            "id": item_id,
            "timestamp": timestamp,
        }
        
        logger.info(f"Successfully ingested data for user {user_id}")
        return create_response(200, response_body)
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return create_response(500, {"error": "Internal server error"})


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create API Gateway proxy response.
    
    Args:
        status_code: HTTP status code
        body: Response body dictionary
    
    Returns:
        API Gateway proxy response format
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Api-Key",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(body),
    }