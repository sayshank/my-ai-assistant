"""Configuration for Email Agent with Pinecone"""

# AWS Region
REGION = 'eu-central-1'

# Pinecone
PINECONE_SECRET_NAME = 'pinecone-api-key'
PINECONE_SENDERS_INDEX = 'email-senders'
PINECONE_CONTENT_INDEX = 'email-content'

# Reranking
RERANK_MODEL = 'bge-reranker-v2-m3'
INITIAL_RETRIEVAL_K = 20  # Get more candidates for reranking
FINAL_TOP_K = 5  # Return top results after reranking

# Bedrock Models
LLM_MODEL = 'eu.anthropic.claude-sonnet-4-20250514-v1:0'
