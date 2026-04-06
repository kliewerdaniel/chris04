import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

MEMORIES_FILE = Path("memories.json")


def load_memories() -> Dict[str, str]:
    """Load memories from JSON file."""
    if not MEMORIES_FILE.exists():
        return {}
    
    try:
        with open(MEMORIES_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_memories(data: Dict[str, str]):
    """Atomic write: write to .tmp then rename."""
    tmp_file = MEMORIES_FILE.with_suffix('.json.tmp')
    try:
        with open(tmp_file, 'w') as f:
            json.dump(data, f, indent=2)
        tmp_file.replace(MEMORIES_FILE)
    except Exception:
        if tmp_file.exists():
            tmp_file.unlink()
        raise


def _normalize_key(key: str) -> str:
    """Normalize key to UPPER_SNAKE_CASE."""
    key = key.strip().replace(' ', '_').replace('-', '_').upper()
    key = ''.join(c for c in key if c.isalnum() or c == '_')
    return key


def upsert_memory(key: str, value: str):
    """Insert or update a memory, enforcing 100 key cap."""
    memories = load_memories()
    normalized_key = _normalize_key(key)
    normalized_value = value.strip()
    
    if normalized_key in memories:
        existing_value = memories[normalized_key].strip()
        if existing_value.lower() == normalized_value.lower():
            return
    
    memories[normalized_key] = normalized_value
    
    core_keys = {'NAME', 'LAST_SEEN'}
    non_core_keys = [k for k in memories.keys() if k not in core_keys]
    
    if len(memories) > 100:
        for k in list(memories.keys()):
            if k not in core_keys:
                del memories[k]
                break
    
    save_memories(memories)


def delete_memory(key: str) -> bool:
    """Delete a memory by key. Returns True if deleted, False if not found."""
    memories = load_memories()
    normalized_key = _normalize_key(key)
    
    if normalized_key in memories:
        del memories[normalized_key]
        save_memories(memories)
        return True
    return False


def clear_memories():
    """Clear all memories."""
    save_memories({})


def format_for_prompt(max_chars: int = 800) -> str:
    """Format memories as '- KEY: value' lines, trimmed to max_chars keeping most recent."""
    memories = load_memories()
    if not memories:
        return ""
    
    lines = [f"- {k}: {v}" for k, v in memories.items()]
    text = "\n".join(lines)
    
    if len(text) <= max_chars:
        return text
    
    result_lines = []
    current_length = 0
    
    for line in reversed(lines):
        needed = len(line) + (1 if result_lines else 0)
        if current_length + needed > max_chars:
            break
        result_lines.append(line)
        current_length += needed
    
    return "\n".join(reversed(result_lines))


def extract_and_save(user_msg: str, assistant_msg: str):
    """Extract memories from conversation and save them."""
    from llm import call_llm
    
    extraction_prompt = f"<start_of_turn>user\nExtract key personal facts from this conversation. Return only KEY: VALUE pairs, one per line. Use concise keys like NAME, OCCUPATION, HOBBY. If no facts, return NONE.\n\nUser: {user_msg}\nAssistant: {assistant_msg}<end_of_turn>\n<start_of_turn>model\n"
    
    try:
        response = call_llm(extraction_prompt, max_tokens=150, temperature=0.2)
        if response is None:
            return
        
        response = response.strip()
        if response == "NONE":
            return
        
        for line in response.split('\n'):
            line = line.strip()
            line = re.sub(r'^[\-\*•\d\.]+\s*', '', line).strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    upsert_memory(key, value)
        
        upsert_memory("LAST_SEEN", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        
    except Exception:
        pass
