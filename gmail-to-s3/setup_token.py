#!/usr/bin/env python3
"""
One-time setup script to:
1. Run OAuth flow locally
2. Store the token in AWS Secrets Manager

Run this ONCE on your local machine before deploying Lambda.
"""

import json
import os
import sys

import boto3
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_token.py <credentials.json> [secret-name] [region]")
        print("\nExample:")
        print("  python setup_token.py credentials.json gmail-oauth-token us-east-1")
        sys.exit(1)
    
    creds_file = sys.argv[1]
    secret_name = sys.argv[2] if len(sys.argv) > 2 else 'gmail-oauth-token'
    region = sys.argv[3] if len(sys.argv) > 3 else 'us-east-1'
    
    if not os.path.exists(creds_file):
        print(f"Error: {creds_file} not found")
        sys.exit(1)
    
    print("Starting OAuth flow...")
    print("A browser window will open for Gmail authentication.\n")
    
    # Run OAuth flow
    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
    creds = flow.run_local_server(port=0)
    
    print("\nAuthentication successful!")
    
    # Prepare token data for Secrets Manager
    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes)
    }
    
    # Store in Secrets Manager
    print(f"\nStoring token in Secrets Manager: {secret_name}")
    
    secrets_client = boto3.client('secretsmanager', region_name=region)
    
    try:
        # Try to create new secret
        secrets_client.create_secret(
            Name=secret_name,
            SecretString=json.dumps(token_data),
            Description='Gmail OAuth token for Lambda Gmail-to-S3'
        )
        print(f"Created new secret: {secret_name}")
    except secrets_client.exceptions.ResourceExistsException:
        # Update existing secret
        secrets_client.put_secret_value(
            SecretId=secret_name,
            SecretString=json.dumps(token_data)
        )
        print(f"Updated existing secret: {secret_name}")
    
    print("\n✓ Setup complete!")
    print(f"\nNext steps:")
    print(f"1. Deploy the Lambda function")
    print(f"2. Set environment variable: GMAIL_TOKEN_SECRET={secret_name}")
    print(f"3. Ensure Lambda has secretsmanager:GetSecretValue permission")


if __name__ == '__main__':
    main()
