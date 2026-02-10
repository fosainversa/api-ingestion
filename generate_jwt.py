#!/usr/bin/env python3
"""
Generate JWT tokens for testing - FREE TIER VERSION
Uses SSM Parameter Store instead of Secrets Manager
"""
import argparse
import jwt
import boto3
from datetime import datetime, timedelta


def get_secret_from_aws(environment):
    """Retrieve JWT secret from SSM Parameter Store"""
    session = boto3.Session()
    ssm_client = session.client('ssm')
    cfn = session.client('cloudformation')
    
    # Determine stack name
    stack_name = f"DataIngestionStack-{environment.capitalize()}"
    
    try:
        # Get the parameter name from CloudFormation outputs
        response = cfn.describe_stacks(StackName=stack_name)
        outputs = response['Stacks'][0]['Outputs']
        
        param_name = None
        for output in outputs:
            if output['OutputKey'] == 'JWTSecretParamOutput':
                param_name = output['OutputValue']
                break
        
        if not param_name:
            raise ValueError("JWTSecretParamOutput not found in stack outputs")
        
        # Get parameter value
        param_response = ssm_client.get_parameter(
            Name=param_name,
            WithDecryption=True
        )
        return param_response['Parameter']['Value']
        
    except Exception as e:
        print(f"Error retrieving parameter from AWS: {e}")
        raise


def generate_token(secret_key, user_id, email=None, scope=None, expiry_hours=24):
    """Generate a JWT token"""
    
    now = datetime.utcnow()
    payload = {
        'sub': user_id,
        'iat': now,
        'exp': now + timedelta(hours=expiry_hours),
    }
    
    if email:
        payload['email'] = email
    
    if scope:
        payload['scope'] = scope
    
    token = jwt.encode(payload, secret_key, algorithm='HS256')
    return token


def main():
    parser = argparse.ArgumentParser(description='Generate JWT tokens for API testing')
    parser.add_argument('--environment', '-e', choices=['dev', 'prod'], 
                       help='Environment to use (retrieves secret from AWS)')
    parser.add_argument('--secret', '-s', 
                       help='Custom secret key (for local testing)')
    parser.add_argument('--user-id', '-u', required=True,
                       help='User ID to encode in token')
    parser.add_argument('--email', 
                       help='User email (optional)')
    parser.add_argument('--scope', 
                       help='Token scope (optional)')
    parser.add_argument('--expiry', type=int, default=24,
                       help='Token expiry in hours (default: 24)')
    
    args = parser.parse_args()
    
    # Get secret key
    if args.environment:
        print(f"Retrieving JWT secret from AWS SSM ({args.environment})...")
        secret_key = get_secret_from_aws(args.environment)
    elif args.secret:
        secret_key = args.secret
    else:
        print("Error: Either --environment or --secret must be provided")
        return 1
    
    # Generate token
    token = generate_token(
        secret_key=secret_key,
        user_id=args.user_id,
        email=args.email,
        scope=args.scope,
        expiry_hours=args.expiry
    )
    
    print("\n" + "="*80)
    print("JWT Token Generated Successfully")
    print("="*80)
    print(f"\nUser ID: {args.user_id}")
    if args.email:
        print(f"Email: {args.email}")
    if args.scope:
        print(f"Scope: {args.scope}")
    print(f"Expires in: {args.expiry} hours")
    print("\n" + "-"*80)
    print("Token:")
    print("-"*80)
    print(token)
    print("-"*80)
    print("\nUse with curl:")
    print("-"*80)
    print(f'curl -X POST https://your-api-url/data \\')
    print(f'  -H "Authorization: Bearer {token}" \\')
    print(f'  -H "x-api-key: YOUR_API_KEY" \\')
    print(f'  -H "Content-Type: application/json" \\')
    print(f'  -d \'{{"userId": "{args.user_id}", "eventType": "test", "data": {{"message": "hello"}}}}\'')
    print("="*80 + "\n")
    
    return 0


if __name__ == '__main__':
    exit(main())