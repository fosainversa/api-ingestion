"""
JWT Token Authorizer for API Gateway - FREE TIER VERSION
Uses SSM Parameter Store instead of Secrets Manager
"""
import json
import os
import logging
import boto3
import jwt
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Initialize AWS clients
ssm = boto3.client('ssm')

# Cache the JWT secret
_jwt_secret_cache = None


def get_jwt_secret():
    """Retrieve JWT secret from SSM Parameter Store (with caching)"""
    global _jwt_secret_cache
    
    if _jwt_secret_cache is None:
        param_name = os.environ['JWT_SECRET_PARAM']
        response = ssm.get_parameter(
            Name=param_name,
            WithDecryption=True  # Still encrypted at rest
        )
        _jwt_secret_cache = response['Parameter']['Value']
    
    return _jwt_secret_cache


def handler(event, context):
    """
    Validate JWT token and generate IAM policy
    """
    token = event.get('authorizationToken', '')
    
    logger.info(f"Authorizer invoked")
    
    try:
        # Extract token from "Bearer <token>"
        if not token.startswith('Bearer '):
            raise ValueError("Invalid token format")
        
        token = token[7:]  # Remove "Bearer " prefix
        
        # Get JWT secret
        secret_key = get_jwt_secret()
        
        # Decode and verify JWT
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=['HS256'],
            options={
                'verify_exp': True,
                'verify_iat': True,
            }
        )
        
        # Extract user information
        user_id = payload.get('sub', 'unknown')
        
        logger.info(f"Token validated for user: {user_id}")
        
        # Generate Allow policy
        policy = generate_policy(user_id, 'Allow', event['methodArn'], payload)
        
        return policy
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise Exception('Unauthorized')  # API Gateway returns 401
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        raise Exception('Unauthorized')  # API Gateway returns 401
    except Exception as e:
        logger.error(f"Authorization error: {str(e)}")
        raise Exception('Unauthorized')  # API Gateway returns 401


def generate_policy(principal_id, effect, resource, context_data=None):
    """Generate IAM policy for API Gateway"""
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        }
    }
    
    # Add context (passed to Lambda via event.requestContext.authorizer)
    if context_data:
        policy['context'] = {
            'userId': str(context_data.get('sub', '')),
            'email': str(context_data.get('email', '')),
            'scope': str(context_data.get('scope', '')),
        }
    
    return policy