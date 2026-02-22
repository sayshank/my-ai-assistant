# Email Agent with Pinecone + LangChain

AI-powered email assistant that searches ~70,000 emails using Pinecone vector search and Claude.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (CloudFront)                   │
│                     ai.sayshank.com                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway (HTTP API)                    │
│                    + Cognito JWT Auth                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Lambda (Python 3.11)                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              LangChain Agent (ReAct)                │    │
│  │                                                     │    │
│  │  Tools:                                             │    │
│  │  • search_by_sender - Find emails FROM someone     │    │
│  │  • search_by_content - Find emails ABOUT something │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   Pinecone (us-east-1)  │     │   Bedrock (eu-central-1)│
│                         │     │                         │
│ • email-senders index   │     │ Claude Sonnet 4         │
│ • email-content index   │     │                         │
│ • llama-text-embed-v2   │     │                         │
└─────────────────────────┘     └─────────────────────────┘
```

## Pinecone Indexes

Both indexes use integrated inference with `llama-text-embed-v2`:

| Index | Embeds | Purpose |
|-------|--------|---------|
| `email-senders` | Sender name | Find emails from specific people/companies |
| `email-content` | Subject + snippet | Find emails about specific topics |

## Tools

The agent has two tools and decides which to use based on the question:

1. **search_by_sender** - Use when looking for emails FROM a specific person or company
   - Filters: year, subject_contains
   - Returns up to 20 results

2. **search_by_content** - Use when looking for emails ABOUT a topic
   - Filters: year, sender_contains  
   - Returns up to 10 results

## Deployment

### Prerequisites
- AWS CLI configured
- SAM CLI installed
- Pinecone API key in Secrets Manager (`pinecone-api-key`)

### Deploy

```bash
cd lambda
sam build
sam deploy --no-confirm-changeset
```

### Update Frontend

```bash
aws s3 cp frontend/index.html s3://<bucket-name>/index.html
aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/index.html"
```

## Stack Resources

- **Lambda**: `email-agent-pinecone`
- **API Gateway**: HTTP API with JWT authorizer
- **Cognito**: User pool with admin-only signup
- **S3 + CloudFront**: Static frontend hosting
- **WAF**: IP allowlist (optional)

## Configuration

Environment variables in Lambda:
- `REGION`: eu-central-1
- `BEDROCK_MODEL_ID`: eu.anthropic.claude-sonnet-4-20250514-v1:0

## Local Development

```bash
pip install -r requirements.txt
# Set PINECONE_API_KEY environment variable
python agent.py
```
