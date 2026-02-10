"""
Weekly Summary Lambda Handler
Scans DynamoDB and generates summary report to S3
"""
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError

# Configure logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

table_name = os.environ.get("TABLE_NAME")
bucket_name = os.environ.get("BUCKET_NAME")

table = dynamodb.Table(table_name)

logger.info(f"Initialized with table: {table_name}, bucket: {bucket_name}")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for weekly summary generation.
    
    Args:
        event: EventBridge scheduled event
        context: Lambda context object
        
    Returns:
        Execution summary
    """
    logger.info("Weekly summary handler invoked")
    
    try:
        # Calculate time range (last 7 days)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=7)
        start_timestamp = int(start_time.timestamp())
        end_timestamp = int(end_time.timestamp())
        
        logger.info(f"Generating summary from {start_time} to {end_time}")
        
        # Scan DynamoDB table
        try:
            total_count, user_stats, event_stats = scan_table(start_timestamp, end_timestamp)
        except ClientError as e:
            logger.error(f"DynamoDB scan error: {str(e)}")
            raise
        
        # Generate summary report
        summary = {
            "generated_at": end_time.isoformat(),
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            "statistics": {
                "total_items": total_count,
                "unique_users": len(user_stats),
                "unique_event_types": len(event_stats),
            },
            "top_users": get_top_items(user_stats, 10),
            "top_event_types": get_top_items(event_stats, 10),
            "daily_breakdown": {
                # Could add daily breakdown here if needed
            }
        }
        
        logger.info(f"Summary generated: {total_count} items, {len(user_stats)} users")
        
        # Upload to S3
        try:
            s3_key = upload_summary_to_s3(summary, end_time)
            logger.info(f"Summary uploaded to S3: {s3_key}")
        except ClientError as e:
            logger.error(f"S3 upload error: {str(e)}")
            raise
        
        # Return success
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Summary generated successfully",
                "total_items": total_count,
                "s3_key": s3_key,
                "summary": summary,
            }),
        }
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to generate summary"}),
        }


def scan_table(start_timestamp: int, end_timestamp: int) -> tuple:
    """
    Scan DynamoDB table and collect statistics.
    
    Args:
        start_timestamp: Start of time range (Unix timestamp)
        end_timestamp: End of time range (Unix timestamp)
        
    Returns:
        Tuple of (total_count, user_stats, event_stats)
    """
    total_count = 0
    user_stats = {}
    event_stats = {}
    
    # Initial scan
    response = table.scan(
        ProjectionExpression="userId, eventType, #ts",
        ExpressionAttributeNames={"#ts": "timestamp"},
        FilterExpression="attribute_exists(userId) AND #ts BETWEEN :start AND :end",
        ExpressionAttributeValues={
            ":start": start_timestamp,
            ":end": end_timestamp,
        }
    )
    
    # Process items
    items = response.get("Items", [])
    process_items(items, user_stats, event_stats)
    total_count += len(items)
    
    # Handle pagination
    while "LastEvaluatedKey" in response:
        logger.info(f"Scanning next page... Current count: {total_count}")
        response = table.scan(
            ProjectionExpression="userId, eventType, #ts",
            ExpressionAttributeNames={"#ts": "timestamp"},
            FilterExpression="attribute_exists(userId) AND #ts BETWEEN :start AND :end",
            ExpressionAttributeValues={
                ":start": start_timestamp,
                ":end": end_timestamp,
            },
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        
        items = response.get("Items", [])
        process_items(items, user_stats, event_stats)
        total_count += len(items)
    
    logger.info(f"Scan complete: {total_count} items processed")
    return total_count, user_stats, event_stats


def process_items(items: List[Dict], user_stats: Dict, event_stats: Dict) -> None:
    """
    Process items and update statistics dictionaries.
    
    Args:
        items: List of DynamoDB items
        user_stats: Dictionary to track user counts
        event_stats: Dictionary to track event type counts
    """
    for item in items:
        user_id = item.get("userId")
        event_type = item.get("eventType", "unknown")
        
        # Count by user
        if user_id:
            user_stats[user_id] = user_stats.get(user_id, 0) + 1
        
        # Count by event type
        event_stats[event_type] = event_stats.get(event_type, 0) + 1


def get_top_items(stats_dict: Dict[str, int], limit: int) -> List[Dict[str, Any]]:
    """
    Get top N items from statistics dictionary.
    
    Args:
        stats_dict: Dictionary of item counts
        limit: Maximum number of items to return
        
    Returns:
        List of top items with counts
    """
    sorted_items = sorted(stats_dict.items(), key=lambda x: x[1], reverse=True)
    return [
        {"name": name, "count": count}
        for name, count in sorted_items[:limit]
    ]


def upload_summary_to_s3(summary: Dict[str, Any], timestamp: datetime) -> str:
    """
    Upload summary report to S3.
    
    Args:
        summary: Summary data dictionary
        timestamp: Timestamp for file naming
        
    Returns:
        S3 key of uploaded file
    """
    # Generate S3 key
    date_str = timestamp.strftime("%Y-%m-%d")
    s3_key = f"summaries/weekly-summary-{date_str}.json"
    
    # Upload to S3
    s3.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=json.dumps(summary, indent=2),
        ContentType="application/json",
        ServerSideEncryption="AES256",
        Metadata={
            "generated-at": timestamp.isoformat(),
            "total-items": str(summary["statistics"]["total_items"]),
        }
    )
    
    return s3_key
