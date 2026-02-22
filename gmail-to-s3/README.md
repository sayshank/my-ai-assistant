# Gmail to S3

Export your Gmail emails to S3 using AWS Lambda with OAuth2 authentication.

## Features

- Exports all emails (or filtered by query) to S3 as JSON
- Handles 30K+ emails with automatic checkpointing
- OAuth token stored securely in Secrets Manager
- Resumes from last checkpoint on timeout/failure

## Setup

### 1. Create Google Cloud OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `credentials.json`

### 2. Store OAuth token in Secrets Manager

```bash
pip install -r requirements.txt
python setup_token.py credentials.json gmail-oauth-token eu-central-1
```

This opens a browser for Gmail auth, then stores the token in Secrets Manager.

### 3. Deploy with SAM

```bash
sam build
sam deploy --guided
```

### 4. Run

```bash
# Fetch all emails
aws lambda invoke --function-name gmail-to-s3-durable --payload '{}' response.json

# With query filter
aws lambda invoke --function-name gmail-to-s3-durable \
  --payload '{"query": "after:2024/01/01", "max_emails": 1000}' response.json
```

## Output Format

Each email is stored as a JSON file in S3:
```
s3://your-bucket/gmail-exports/YYYY/MM/message_id.json
```

Fields: `id`, `threadId`, `sender`, `recipient`, `subject`, `date`, `snippet`, `body`

## Configuration

Environment variables (set in template.yaml):
- `S3_BUCKET`: Target S3 bucket
- `S3_PREFIX`: S3 key prefix (default: `gmail-exports`)
- `GMAIL_TOKEN_SECRET`: Secrets Manager secret name
- `BATCH_SIZE`: Emails per batch (default: `100`)
