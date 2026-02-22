"""Tools for the Email Agent with Pinecone + Reranking"""

import boto3
import json
from pinecone import Pinecone

from config import (
    REGION, PINECONE_SECRET_NAME,
    PINECONE_SENDERS_INDEX, PINECONE_CONTENT_INDEX,
    RERANK_MODEL, INITIAL_RETRIEVAL_K, FINAL_TOP_K
)

_pc_client = None


def get_pinecone_client():
    """Get Pinecone client with API key from Secrets Manager"""
    global _pc_client
    if _pc_client is None:
        secrets = boto3.client('secretsmanager', region_name=REGION)
        api_key = secrets.get_secret_value(SecretId=PINECONE_SECRET_NAME)['SecretString']
        _pc_client = Pinecone(api_key=api_key)
    return _pc_client


def search_and_rerank(query: str, index_name: str, k: int = FINAL_TOP_K) -> list:
    """
    Two-stage retrieval: vector search then rerank.
    1. Get INITIAL_RETRIEVAL_K candidates from Pinecone
    2. Rerank with bge-reranker-v2-m3
    3. Return top k results
    """
    pc = get_pinecone_client()
    index = pc.Index(index_name)
    
    # Stage 1: Vector search with integrated embedding
    search_results = index.search(
        namespace="default",
        query={"inputs": {"text": query}, "top_k": INITIAL_RETRIEVAL_K},
        fields=["message_id", "thread_id", "sender", "recipient", "subject", "date_sent", "snippet", "text"]
    )
    
    if not search_results.get('result', {}).get('hits'):
        return []
    
    hits = search_results['result']['hits']
    
    # Prepare documents for reranking
    documents = []
    for hit in hits:
        fields = hit.get('fields', {})
        # Use the text field (what was embedded) for reranking
        doc_text = fields.get('text', fields.get('subject', ''))
        documents.append({
            "id": hit['_id'],
            "text": doc_text,
            "fields": fields,
            "original_score": hit.get('_score', 0)
        })
    
    # Stage 2: Rerank
    rerank_docs = [{"id": d["id"], "text": d["text"]} for d in documents]
    
    rerank_result = pc.inference.rerank(
        model=RERANK_MODEL,
        query=query,
        documents=rerank_docs,
        top_n=k,
        return_documents=True
    )
    
    # Merge rerank scores with original metadata
    results = []
    for item in rerank_result.data:
        # Find original document with full metadata
        orig_doc = next((d for d in documents if d["id"] == item.document.id), None)
        if orig_doc:
            results.append({
                "id": item.document.id,
                "rerank_score": item.score,
                "original_score": orig_doc["original_score"],
                "fields": orig_doc["fields"]
            })
    
    return results


def semantic_search(query: str, k: int = FINAL_TOP_K, search_type: str = "content") -> str:
    """
    Search emails using Pinecone with reranking.
    
    Args:
        query: Natural language search query
        k: Number of results to return (after reranking)
        search_type: "content" (subject+snippet), "sender", or "both"
    
    Returns:
        Formatted string with matching emails
    """
    all_results = []
    
    if search_type in ["content", "both"]:
        content_results = search_and_rerank(query, PINECONE_CONTENT_INDEX, k)
        for r in content_results:
            r["source"] = "content"
        all_results.extend(content_results)
    
    if search_type in ["sender", "both"]:
        sender_results = search_and_rerank(query, PINECONE_SENDERS_INDEX, k)
        for r in sender_results:
            r["source"] = "sender"
        all_results.extend(sender_results)
    
    # Sort by rerank score and take top k
    all_results.sort(key=lambda x: x["rerank_score"], reverse=True)
    all_results = all_results[:k]
    
    if not all_results:
        return "No matching emails found."
    
    # Format output
    output = []
    for r in all_results:
        f = r["fields"]
        output.append(
            f"Rerank Score: {r['rerank_score']:.3f} (vector: {r['original_score']:.3f})\n"
            f"Source: {r['source']} index\n"
            f"Subject: {f.get('subject', 'N/A')}\n"
            f"From: {f.get('sender', 'N/A')}\n"
            f"To: {f.get('recipient', 'N/A')}\n"
            f"Date: {f.get('date_sent', 'N/A')}\n"
            f"Preview: {f.get('snippet', f.get('text', 'N/A'))[:200]}"
        )
    
    return "\n\n---\n\n".join(output)


def search_by_sender(sender_query: str, k: int = FINAL_TOP_K) -> str:
    """
    Search emails by sender name/email.
    Uses the email-senders index which embeds sender field.
    
    Args:
        sender_query: Name or email to search for (e.g., "Amazon", "john@example.com")
        k: Number of results
    
    Returns:
        Formatted string with matching emails
    """
    results = search_and_rerank(sender_query, PINECONE_SENDERS_INDEX, k)
    
    if not results:
        return f"No emails found from sender matching '{sender_query}'."
    
    output = []
    for r in results:
        f = r["fields"]
        output.append(
            f"Rerank Score: {r['rerank_score']:.3f}\n"
            f"From: {f.get('sender', 'N/A')}\n"
            f"Subject: {f.get('subject', 'N/A')}\n"
            f"Date: {f.get('date_sent', 'N/A')}"
        )
    
    return "\n\n---\n\n".join(output)
