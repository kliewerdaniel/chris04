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


def _rule_based_extract(user_msg: str) -> Dict[str, str]:
    """Extract obvious facts from user message using regex patterns."""
    facts = {}
    text = user_msg.lower()
    
    # Name patterns: "my name is X", "I'm X", "call me X"
    name_patterns = [
        r"my name is ([A-Z][a-z]+)",
        r"i'm ([A-Z][a-z]+)",
        r"i am ([A-Z][a-z]+)",
        r"call me ([A-Z][a-z]+)",
        r"name'?s ([A-Z][a-z]+)",
    ]
    for pattern in name_patterns:
        m = re.search(pattern, user_msg, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if name.lower() not in ('a', 'an', 'the', 'not', 'so', 'just', 'very', 'really'):
                facts['NAME'] = name
            break
    
    # Age: "I'm 28", "I am 35 years old"
    m = re.search(r"\bi(?:'m| am) (\d{1,2})(?: years? old)?\b", text)
    if m:
        age = int(m.group(1))
        if 5 < age < 120:
            facts['AGE'] = str(age)
    
    # Job/occupation: "I work as a X", "I'm a X", "I am a X"
    job_m = re.search(r"i(?:'m| am) a(?:n)? ([\w\s]{3,30}?)(?:\.|,|$| and | but )", text)
    if job_m:
        job = job_m.group(1).strip()
        # Filter out non-job words
        skip = {'bit', 'lot', 'fan', 'huge', 'big', 'small', 'little', 'pretty', 'very', 'really', 'quite'}
        if job and job not in skip and len(job) > 2:
            facts['JOB'] = job
    
    # City/location: "I live in X", "I'm from X", "I'm in X"  
    loc_m = re.search(r"(?:i live in|i'm from|from|i'm in|i am in) ([A-Z][a-zA-Z\s]{2,25}?)(?:\.|,|$)", user_msg)
    if loc_m:
        loc = loc_m.group(1).strip()
        if len(loc) > 1:
            facts['CITY'] = loc
    
    return facts


def extract_and_save(user_msg: str, assistant_msg: str):
    """Extract memories from conversation and save them."""
    from llm import call_llm
    import logging
    
    logger = logging.getLogger(__name__)

    extraction_prompt = (
        "<start_of_turn>user\n"
        "Read this conversation and list any personal facts about the user.\n"
        "Rules:\n"
        "- Write one fact per line in the format KEY: value\n"
        "- Keys must be short ALL_CAPS words like NAME, AGE, JOB, CITY, HOBBY, PET\n"
        "- Only include facts the user stated directly\n"
        "- If there are no facts, write only: NONE\n"
        "- Do not write explanations, sentences, or anything except KEY: value lines\n\n"
        "Examples of correct output:\n"
        "NAME: Sarah\n"
        "JOB: nurse\n"
        "HOBBY: painting\n\n"
        f"Conversation:\n"
        f"User: {user_msg}\n"
        f"Assistant: {assistant_msg}\n"
        "<end_of_turn>\n"
        "<start_of_turn>model\n"
    )

    # Rule-based extraction first (always works, no LLM needed)
    rule_facts = _rule_based_extract(user_msg)
    for k, v in rule_facts.items():
        print(f"[MEMORY] Rule-based: {k} = {v}")
        upsert_memory(k, v)

    try:
        response = call_llm(extraction_prompt, max_tokens=100, temperature=0.1)
        logger.debug(f"Memory extraction raw response: {repr(response)}")
        print(f"[MEMORY] Raw extraction: {repr(response)}")

        if response is None:
            print("[MEMORY] LLM returned None, skipping extraction")
            return

        response = response.strip()
        
        # Reject if the entire response is a refusal/none indicator
        if response.upper() in ("NONE", "NO FACTS", "N/A", "", "NONE."):
            print("[MEMORY] No facts found in conversation")
            return

        saved_count = 0
        for line in response.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Strip any leading bullet/number prefixes
            line = re.sub(r'^[\-\*•\d\.]+\s*', '', line).strip()
            if ':' not in line:
                print(f"[MEMORY] Skipping malformed line (no colon): {repr(line)}")
                continue
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            # Skip if key looks like prose (contains spaces after normalization)
            if not key or not value:
                continue
            if len(key.split()) > 3:
                print(f"[MEMORY] Skipping line with prose key: {repr(line)}")
                continue
            # Skip if value is too long to be a fact (likely a sentence)
            if len(value) > 120:
                print(f"[MEMORY] Skipping line with overlong value: {repr(line)}")
                continue
            print(f"[MEMORY] Saving: {key} = {value}")
            upsert_memory(key, value)
            saved_count += 1

        if saved_count > 0:
            upsert_memory("LAST_SEEN", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            print(f"[MEMORY] Saved {saved_count} memories")
        else:
            print("[MEMORY] Parsed response but found no valid KEY: VALUE pairs")

    except Exception as e:
        print(f"[MEMORY] extract_and_save failed: {e}")
        logger.exception("Memory extraction error")
