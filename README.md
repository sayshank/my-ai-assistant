# My AI Assistant

AI-powered email assistant that exports Gmail to AWS and enables natural language search over ~70,000 emails.

## Project Structure

```
├── gmail-to-s3/          # Export Gmail to S3
└── email-agent-pinecone/ # AI agent with Pinecone vector search
```

## Components

### gmail-to-s3
Lambda function that exports Gmail emails to S3 using OAuth2. Handles 30K+ emails with checkpointing for durability.

### email-agent-pinecone
The main AI agent - a web app with:
- LangChain ReAct agent with Claude Sonnet 4
- Two search tools (by sender, by content)
- Pinecone vector search with `llama-text-embed-v2`
- Cognito authentication
- CloudFront + S3 frontend

**Live at:** [ai.sayshank.com](https://ai.sayshank.com)

## Architecture

```
Gmail → Lambda → S3 → Pinecone
                         ↓
        User → CloudFront → API Gateway → Lambda (Agent) → Bedrock
```

## Tech Stack

- AWS Lambda (Python 3.11)
- Amazon Bedrock (Claude Sonnet 4)
- Pinecone (vector search)
- Amazon Cognito (auth)
- S3 + CloudFront (frontend)
- AWS SAM (IaC)

## License

MIT
