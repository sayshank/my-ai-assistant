"""
Email Agent with Pinecone + Reranking
Uses Bedrock Claude with tool use for intelligent email search.
Two-stage retrieval: vector search → rerank for better relevance.
"""

import boto3
from config import REGION, LLM_MODEL
from tools import semantic_search, search_by_sender

# Initialize Bedrock client
bedrock = boto3.client('bedrock-runtime', region_name=REGION)

# Define tools
TOOLS = [
    {
        "toolSpec": {
            "name": "semantic_search",
            "description": "Search emails by content (subject and snippet). Uses vector search + reranking for best relevance. Use for finding emails about a topic or specific content.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        },
                        "k": {
                            "type": "integer",
                            "description": "Number of results (default 5)",
                            "default": 5
                        },
                        "search_type": {
                            "type": "string",
                            "enum": ["content", "sender", "both"],
                            "description": "Which index to search: content (subject+snippet), sender, or both",
                            "default": "content"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    },
    {
        "toolSpec": {
            "name": "search_by_sender",
            "description": "Search emails by sender name or email address. Use when looking for emails from a specific person or company.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "sender_query": {
                            "type": "string",
                            "description": "Sender name or email to search for (e.g., 'Amazon', 'john@example.com')"
                        },
                        "k": {
                            "type": "integer",
                            "description": "Number of results (default 5)",
                            "default": 5
                        }
                    },
                    "required": ["sender_query"]
                }
            }
        }
    }
]


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return result"""
    if tool_name == "semantic_search":
        return semantic_search(
            tool_input.get("query", ""),
            tool_input.get("k", 5),
            tool_input.get("search_type", "content")
        )
    elif tool_name == "search_by_sender":
        return search_by_sender(
            tool_input.get("sender_query", ""),
            tool_input.get("k", 5)
        )
    else:
        return f"Unknown tool: {tool_name}"


def ask(question: str) -> str:
    """Ask the email agent a question using Bedrock Converse API with tool use"""
    
    messages = [{"role": "user", "content": [{"text": question}]}]
    
    system_prompt = """You are an intelligent email assistant with access to a user's email archive (~70,000 emails).

Today's date is February 21, 2026.

You have two search tools:
1. semantic_search - Search by email content (subject + snippet). Can also search by sender or both.
2. search_by_sender - Specifically search for emails from a person/company.

The search uses two-stage retrieval:
1. Vector similarity search to find candidates
2. Reranking with a cross-encoder for better relevance

Guidelines:
- Use search_by_sender when the user asks about emails from a specific person/company
- Use semantic_search for topic-based queries
- Results show both rerank score (relevance) and original vector score
- Be concise and helpful in your answers"""

    # Initial request
    response = bedrock.converse(
        modelId=LLM_MODEL,
        messages=messages,
        system=[{"text": system_prompt}],
        toolConfig={"tools": TOOLS}
    )
    
    # Handle tool use loop
    max_loops = 10
    loop_count = 0
    
    while response['stopReason'] == 'tool_use' and loop_count < max_loops:
        loop_count += 1
        assistant_message = response['output']['message']
        messages.append(assistant_message)
        
        # Process tool calls
        tool_results = []
        for block in assistant_message['content']:
            if 'toolUse' in block:
                tool_use = block['toolUse']
                tool_name = tool_use['name']
                tool_input = tool_use['input']
                tool_id = tool_use['toolUseId']
                
                print(f"  → Using tool: {tool_name}")
                print(f"    Input: {tool_input}")
                
                result = execute_tool(tool_name, tool_input)
                print(f"    Result: {result[:300]}..." if len(result) > 300 else f"    Result: {result}")
                
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool_id,
                        "content": [{"text": result}]
                    }
                })
        
        # Send tool results back
        messages.append({"role": "user", "content": tool_results})
        
        response = bedrock.converse(
            modelId=LLM_MODEL,
            messages=messages,
            system=[{"text": system_prompt}],
            toolConfig={"tools": TOOLS}
        )
    
    # Extract final text response
    final_message = response['output']['message']
    for block in final_message['content']:
        if 'text' in block:
            return block['text']
    
    return "No response generated."


def main():
    """Interactive CLI"""
    print("=" * 60)
    print("Email Agent (Pinecone + Reranking)")
    print("Type 'quit' to exit")
    print("=" * 60)
    
    while True:
        question = input("\nYou: ").strip()
        if question.lower() in ['quit', 'exit', 'q']:
            break
        if not question:
            continue
        
        print()
        answer = ask(question)
        print(f"\nAnswer: {answer}")


if __name__ == "__main__":
    main()
