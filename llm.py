import json
import time
import requests
from typing import List, Dict, Optional, Any

ENDPOINT = "http://localhost:8080/completion"
MAX_TOKENS = 3072  # total prompt budget

STOP_TOKENS = ["<end_of_turn>", "<start_of_turn>"]


def count_tokens(text: str) -> int:
    """Estimate token count as len(text) // 4."""
    return len(text) // 4


def call_llm(prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> Optional[str]:
    """Call llama.cpp HTTP server and return the generated text."""
    payload = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "temperature": temperature,
        "n_keep": -1,
        "stop": STOP_TOKENS
    }
    
    try:
        response = requests.post(ENDPOINT, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        content = result.get("content", "")
        return content.strip()
    except Exception:
        return None


def build_prompt(system: str, memories: str, summary: Optional[str], recent: List[Dict], user_message: str) -> str:
    """Assemble tiered prompt with token budget enforcement using Gemma 4 chat format."""
    context_parts = [system]
    if memories:
        context_parts.append("--- MEMORY ---\n" + memories)
    if summary:
        context_parts.append("--- EARLIER CONTEXT ---\n" + summary)
    system_block = "\n\n".join(context_parts)

    turns = [f"<start_of_turn>user\n{system_block}<end_of_turn>\n<start_of_turn>model\nUnderstood.<end_of_turn>"]

    for msg in recent:
        role = "user" if msg["role"] == "user" else "model"
        turns.append(f"<start_of_turn>{role}\n{msg['content']}<end_of_turn>")

    turns.append(f"<start_of_turn>user\n{user_message}<end_of_turn>")
    turns.append("<start_of_turn>model\n")

    prompt = "\n".join(turns)

    while count_tokens(prompt) > MAX_TOKENS and len(recent) > 2:
        recent = recent[1:]
        turns = [f"<start_of_turn>user\n{system_block}<end_of_turn>\n<start_of_turn>model\nUnderstood.<end_of_turn>"]
        for msg in recent:
            role = "user" if msg["role"] == "user" else "model"
            turns.append(f"<start_of_turn>{role}\n{msg['content']}<end_of_turn>")
        turns.append(f"<start_of_turn>user\n{user_message}<end_of_turn>")
        turns.append("<start_of_turn>model\n")
        prompt = "\n".join(turns)

    return prompt


def get_context_pressure(prompt: str) -> Dict[str, Any]:
    """Return context usage statistics."""
    used = count_tokens(prompt)
    pct = (used / MAX_TOKENS) * 100 if MAX_TOKENS > 0 else 0
    
    if pct < 60:
        level = "low"
    elif pct < 85:
        level = "medium"
    else:
        level = "high"
    
    return {
        "used": used,
        "max": MAX_TOKENS,
        "pct": round(pct, 1),
        "level": level
    }


def summarize(messages: List[Dict]) -> Optional[str]:
    """Create a summary of messages using the LLM."""
    if not messages:
        return None
    
    conversation = ""
    for msg in messages:
        role = msg["role"].capitalize()
        content = msg["content"]
        conversation += f"{role}: {content}\n"
    
    prompt = f"<start_of_turn>user\nSummarize the following conversation concisely, preserving key information and context:\n\n{conversation}<end_of_turn>\n<start_of_turn>model\n"
    
    return call_llm(prompt, max_tokens=200, temperature=0.2)
