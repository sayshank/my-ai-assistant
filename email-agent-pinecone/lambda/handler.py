"""
Lambda handler for Email Agent with Pinecone
Two tools: search_by_sender (email-senders index) and search_by_content (email-content index)
Agent decides which tool to use based on the question.
Uses LangChain 1.2.x create_agent (recommended approach).
"""

import json
import boto3
from mangum import Mangum
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pinecone import Pinecone

from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from langchain.agents import create_agent

import os

# Config
REGION = os.environ.get('REGION', 'eu-central-1')
DEFAULT_MODEL = os.environ.get('BEDROCK_MODEL_ID', 'eu.anthropic.claude-sonnet-4-20250514-v1:0')
PINECONE_SECRET_NAME = 'pinecone-api-key'
SENDERS_INDEX = 'email-senders'
CONTENT_INDEX = 'email-content'

app = FastAPI()
_pc_client = None


def get_pinecone_client():
    global _pc_client
    if _pc_client is None:
        secrets = boto3.client('secretsmanager', region_name=REGION)
        api_key = secrets.get_secret_value(SecretId=PINECONE_SECRET_NAME)['SecretString']
        _pc_client = Pinecone(api_key=api_key)
    return _pc_client


def search_index(index_name: str, query: str, top_k: int, year: int = None, 
                 sender_contains: str = None, subject_contains: str = None) -> list:
    """Search a Pinecone index and return results with optional metadata filters"""
    pc = get_pinecone_client()
    index = pc.Index(index_name)
    
    has_filters = year or sender_contains or subject_contains
    fetch_k = top_k * 3 if has_filters else top_k
    
    search_results = index.search(
        namespace="default",
        query={"inputs": {"text": query}, "top_k": fetch_k},
        fields=["message_id", "thread_id", "sender", "recipient", "subject", "date_sent", "snippet"]
    )
    
    docs = []
    if search_results.get('result', {}).get('hits'):
        for hit in search_results['result']['hits']:
            fields = hit.get('fields', {})
            date_sent = fields.get('date_sent', '')
            sender = fields.get('sender', '')
            subject = fields.get('subject', '')
            
            if year and str(year) not in date_sent:
                continue
            if sender_contains and sender_contains.lower() not in sender.lower():
                continue
            if subject_contains and subject_contains.lower() not in subject.lower():
                continue
            
            docs.append({
                "score": hit.get('_score', 0),
                "sender": sender,
                "subject": subject,
                "date_sent": date_sent,
                "snippet": fields.get('snippet', '')[:300]
            })
            
            if len(docs) >= top_k:
                break
    
    return docs


def format_results(docs: list) -> str:
    if not docs:
        return "No emails found."
    
    output = []
    for doc in docs:
        output.append(
            f"Score: {doc['score']:.3f}\n"
            f"From: {doc['sender']}\n"
            f"Subject: {doc['subject']}\n"
            f"Date: {doc['date_sent']}\n"
            f"Preview: {doc['snippet']}"
        )
    return "\n\n---\n\n".join(output)


@tool
def search_by_sender(sender_name: str, year: int = None, subject_contains: str = None, top_k: int = 20) -> str:
    """Search emails by sender/person name. Use this when looking for emails FROM a specific person or company.
    
    Args:
        sender_name: Name of the sender to search for (e.g., 'Samant', 'Amazon', 'Google', 'Apple')
        year: Optional - filter by year (e.g., 2026, 2025, 2024)
        subject_contains: Optional - filter by subject containing this text
        top_k: Number of results (default 20)
    """
    docs = search_index(SENDERS_INDEX, sender_name, top_k, year=year, subject_contains=subject_contains)
    
    if not docs:
        filters = [f"sender '{sender_name}'"]
        if year: filters.append(f"year {year}")
        if subject_contains: filters.append(f"subject containing '{subject_contains}'")
        return f"No emails found matching: {', '.join(filters)}"
    
    return f"Found {len(docs)} emails from '{sender_name}':\n\n" + format_results(docs)


@tool  
def search_by_content(query: str, year: int = None, sender_contains: str = None, top_k: int = 10) -> str:
    """Search emails by content/topic. Use this when looking for emails ABOUT something.
    
    Args:
        query: What to search for (e.g., 'flight booking', 'order confirmation', 'invoice', 'meeting')
        year: Optional - filter by year (e.g., 2026, 2025, 2024)
        sender_contains: Optional - filter by sender containing this text
        top_k: Number of results (default 10)
    """
    docs = search_index(CONTENT_INDEX, query, top_k, year=year, sender_contains=sender_contains)
    
    if not docs:
        filters = [f"content '{query}'"]
        if year: filters.append(f"year {year}")
        if sender_contains: filters.append(f"sender containing '{sender_contains}'")
        return f"No emails found matching: {', '.join(filters)}"
    
    return f"Found {len(docs)} emails about '{query}':\n\n" + format_results(docs)


tools = [search_by_sender, search_by_content]

SYSTEM_PROMPT = """You are an intelligent email assistant with access to ~70,000 emails.
Today is February 22, 2026.

You have TWO search tools - choose the right one based on the question:

1. search_by_sender - Use when looking for emails FROM a specific person or company
2. search_by_content - Use when looking for emails ABOUT a topic

Be concise and helpful. Summarize results clearly."""


class Question(BaseModel):
    question: str
    model: str = None
    history: list = []


def get_agent(model_id: str):
    llm = ChatBedrock(
        model_id=model_id,
        region_name=REGION,
        model_kwargs={"temperature": 0}
    )
    return create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)


async def agent_stream(question: str, model: str, history: list = None):
    yield f"data: {json.dumps({'type': 'status', 'message': 'Thinking...'})}\n\n"
    
    messages = []
    if history:
        for msg in history[-10:]:
            if msg.get("role") == "user":
                messages.append({"role": "user", "content": msg.get("content", "")})
            elif msg.get("role") == "assistant":
                messages.append({"role": "assistant", "content": msg.get("content", "")})
    
    messages.append({"role": "user", "content": question})
    
    try:
        agent = get_agent(model)
        result = agent.invoke({"messages": messages})
        
        answer = ""
        if isinstance(result, dict) and "messages" in result:
            for msg in reversed(result["messages"]):
                if isinstance(msg, AIMessage) and msg.content:
                    content = msg.content
                    if isinstance(content, str):
                        answer = content
                    elif isinstance(content, list):
                        answer = "".join(
                            b.get('text', '') if isinstance(b, dict) else str(b)
                            for b in content
                        )
                    break
        
        if not answer:
            answer = "No response generated."
        
        # Send as token (frontend expects this)
        yield f"data: {json.dumps({'type': 'token', 'content': answer})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


@app.post("/ask")
async def ask(q: Question):
    model = q.model or DEFAULT_MODEL
    return StreamingResponse(
        agent_stream(q.question, model, q.history),
        media_type="text/event-stream"
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


handler = Mangum(app, lifespan="off", api_gateway_base_path="/prod")
