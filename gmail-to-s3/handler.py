"""
Gmail to S3 - Lambda Durable Functions Version
Handles 30K+ emails with checkpointing and automatic recovery
"""

import os
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from aws_durable_execution_sdk_python import DurableContext, durable_execution
from aws_durable_execution_sdk_python.context import StepContext, durable_step


# Configuration
SECRETS_NAME = os.environ.get('GMAIL_TOKEN_SECRET', 'gmail-oauth-token')
S3_BUCKET = os.environ['S3_BUCKET']
S3_PREFIX = os.environ.get('S3_PREFIX', 'gmail-exports')
PROGRESS_KEY = f"{S3_PREFIX}/progress.json"


def get_gmail_credentials():
    """Retrieve Gmail OAuth credentials from Secrets Manager"""
    secrets_client = boto3.client('secretsmanager')
    response = secrets_client.get_secret_value(SecretId=SECRETS_NAME)
    token_data = json.loads(response['SecretString'])
    
    creds = Credentials(
        token=token_data['token'],
        refresh_token=token_data['refresh_token'],
        token_uri=token_data['token_uri'],
        client_id=token_data['client_id'],
        client_secret=token_data['client_secret'],
        scopes=token_data['scopes']
    )
    
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        new_token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': list(creds.scopes)
        }
        secrets_client.put_secret_value(
            SecretId=SECRETS_NAME,
            SecretString=json.dumps(new_token_data)
        )
    
    return creds


def get_gmail_service():
    return build('gmail', 'v1', credentials=get_gmail_credentials())


def update_progress(s3, processed, total_found, status, timestamp):
    """Update progress file in S3 for easy monitoring"""
    progress = {
        'status': status,
        'emails_processed': processed,
        'emails_found': total_found,
        'last_updated': datetime.now().isoformat(),
        'timestamp': timestamp,
        'raw_path': f's3://{S3_BUCKET}/{S3_PREFIX}/raw/{timestamp}/'
    }
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=PROGRESS_KEY,
        Body=json.dumps(progress, indent=2),
        ContentType='application/json'
    )


def fetch_email_with_retry(service, msg_id, max_retries=3):
    """Fetch email with exponential backoff for rate limits"""
    for attempt in range(max_retries):
        try:
            return service.users().messages().get(
                userId='me',
                id=msg_id,
                format='full'
            ).execute()
        except HttpError as e:
            if e.resp.status in [429, 500, 503]:  # Rate limit or server errors
                wait_time = (2 ** attempt) + 1  # 2, 3, 5 seconds
                time.sleep(wait_time)
                continue
            raise
    return None


@durable_step
def fetch_page_step(step_context: StepContext, query: str, page_token: str) -> dict:
    """Fetch one page of message IDs"""
    service = get_gmail_service()
    
    results = service.users().messages().list(
        userId='me',
        q=query if query else None,
        maxResults=500,  # Max allowed by Gmail API
        pageToken=page_token if page_token else None
    ).execute()
    
    messages = results.get('messages', [])
    message_ids = [msg['id'] for msg in messages]
    next_token = results.get('nextPageToken', '')
    
    step_context.logger.info(f"Fetched {len(message_ids)} IDs")
    return {'ids': message_ids, 'next_token': next_token}


@durable_step
def process_batch_step(step_context: StepContext, batch_ids: list, timestamp: str, workers: int) -> int:
    """Process batch in parallel - raw upload only (no decoding)"""
    
    def process_one(msg_id):
        service = get_gmail_service()
        s3 = boto3.client('s3')
        
        email = fetch_email_with_retry(service, msg_id)
        if not email:
            return 0
        
        # Upload raw only
        key = f"{S3_PREFIX}/raw/{timestamp}/email_{msg_id}.json"
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(email),
            ContentType='application/json'
        )
        return 1
    
    processed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_one, msg_id) for msg_id in batch_ids]
        for future in as_completed(futures):
            try:
                processed += future.result()
            except Exception:
                pass
    
    return processed


@durable_execution
def handler(event, context: DurableContext) -> dict:
    """Main handler - fetches emails page by page with progress tracking"""
    
    query = event.get('query', '')
    max_emails = event.get('max_emails', 0)
    workers = event.get('workers', 20)
    batch_size = event.get('batch_size', 200)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    s3 = boto3.client('s3')
    total_processed = 0
    total_found = 0
    page_token = ''
    
    update_progress(s3, 0, 0, 'RUNNING', timestamp)
    
    while True:
        # Fetch page of IDs (up to 500)
        page_result = context.step(fetch_page_step(query, page_token))
        message_ids = page_result['ids']
        page_token = page_result['next_token']
        
        if not message_ids:
            break
        
        total_found += len(message_ids)
        
        # Process in batches
        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i:i + batch_size]
            processed = context.step(process_batch_step(batch, timestamp, workers))
            total_processed += processed
            
            # Update progress after each batch
            update_progress(s3, total_processed, total_found, 'RUNNING', timestamp)
            context.logger.info(f"Progress: {total_processed}/{total_found}")
        
        if max_emails and total_processed >= max_emails:
            break
        if not page_token:
            break
    
    update_progress(s3, total_processed, total_found, 'COMPLETE', timestamp)
    
    return {
        'status': 'complete',
        'emails_found': total_found,
        'emails_processed': total_processed,
        'raw_path': f's3://{S3_BUCKET}/{S3_PREFIX}/raw/{timestamp}/'
    }
