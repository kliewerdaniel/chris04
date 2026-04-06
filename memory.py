import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

MEMORIES_FILE = Path("memories.json")

ALLOWED_MEMORY_KEYS = {
    'NAME', 'AGE', 'JOB', 'OCCUPATION', 'CITY', 'LOCATION', 'COUNTRY',
    'HOBBY', 'HOBBIES', 'PET', 'PETS', 'PARTNER', 'SPOUSE', 'KIDS',
    'CHILDREN', 'SIBLING', 'SIBLINGS', 'FRIEND', 'FAMILY',
    'FOOD', 'MUSIC', 'SPORT', 'LANGUAGE', 'SCHOOL', 'UNIVERSITY',
    'COMPANY', 'INDUSTRY', 'GOAL', 'FEAR', 'DREAM', 'VALUE',
    'HEALTH', 'DIET', 'SLEEP', 'EXERCISE', 'MOOD', 'LAST_SEEN'
}


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


def _is_valid_memory_value(value: str) -> bool:
    """Return False if value looks like a hallucinated sentence rather than a fact."""
    v = value.strip()
    
    # Too short or too long
    if len(v) < 1 or len(v) > 80:
        return False
    
    # Contains sentence-like patterns
    sentence_markers = [
        r'\bI\b', r'\bmy\b', r'\bme\b', r'\bwe\b', r'\bour\b',
        r'\byou\b', r'\byour\b', r'\bhe\b', r'\bshe\b', r'\bthey\b',
        r'\bis a\b', r'\bare a\b', r'\bwas a\b',
        r'\bActually\b', r'\bWell\b', r'\bSo\b', r'\bBut\b',
    ]
    import re as _re
    for pattern in sentence_markers:
        if _re.search(pattern, v, _re.IGNORECASE):
            return False
    
    # Multiple commas suggest a sentence, not a value
    if v.count(',') >= 2:
        return False
    
    # Ends with period and is long (a sentence, not an abbreviation)
    if v.endswith('.') and len(v) > 20:
        return False
    
    return True


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
    
    # Job/occupation: "I work as a X", "I'm a [job title]", "I am a [job title]"
    # Only match if the captured group looks like a role (no filler words)
    job_skip = {'bit', 'lot', 'fan', 'huge', 'big', 'small', 'little', 'pretty',
                'very', 'really', 'quite', 'little', 'total', 'huge', 'good',
                'bad', 'tired', 'busy', 'happy', 'sad', 'lucky', 'mess', 'wreck'}

    work_m = re.search(r"i work(?:ed)? as an? ([\w\s]{3,30}?)(?:\.|,|$)", text)
    if work_m:
        job = work_m.group(1).strip()
        if job and job.split()[0] not in job_skip:
            facts['JOB'] = job.title()

    if 'JOB' not in facts:
        role_m = re.search(r"i(?:'m| am) an? ([\w]+(?:\s[\w]+)?)\b", text)
        if role_m:
            job = role_m.group(1).strip()
            if (job not in job_skip and len(job) > 3
                    and not any(c.isdigit() for c in job)):
                facts['JOB'] = job.title()
    
    # City/location: require stronger anchors
    loc_patterns = [
        r"i live in ([A-Z][a-zA-Z\s]{2,25}?)(?:\.|,|$)",
        r"i(?:'m| am) from ([A-Z][a-zA-Z\s]{2,25}?)(?:\.|,|$)",
        r"i(?:'m| am) based in ([A-Z][a-zA-Z\s]{2,25}?)(?:\.|,|$)",
        r"i(?:'m| am) in ([A-Z][a-zA-Z\s]{2,25}?)(?:\.|,|$)",
        r"i(?:'m| am) currently in ([A-Z][a-zA-Z\s]{2,25}?)(?:\.|,|$)",
    ]
    for pattern in loc_patterns:
        loc_m = re.search(pattern, user_msg)
        if loc_m:
            loc = loc_m.group(1).strip()
            if len(loc) > 1 and loc.lower() not in ('a', 'an', 'the', 'here', 'there'):
                facts['CITY'] = loc
            break
    
    return facts


def extract_and_save(user_msg: str, assistant_msg: str, debug_out: dict = None):
    """Extract memories from conversation and save them."""
    from llm import call_llm
    import logging
    
    logger = logging.getLogger(__name__)

    extraction_prompt = (
        "<start_of_turn>user\n"
        "Extract ONLY facts the user explicitly stated in the message below.\n"
        "Do NOT invent, infer, or guess any facts.\n"
        "Do NOT include facts from the assistant's message.\n"
        "Format: one KEY: value per line. Keys from: NAME AGE JOB CITY HOBBY PET PARTNER KIDS SCHOOL COMPANY\n"
        "Values must be 1-5 words only. No sentences. No punctuation.\n"
        "If the user stated no personal facts, write: NONE\n\n"
        "WRONG example (invented facts):\n"
        "USER: my name is John and I am a developer\n"
        "WRONG output: USER: my name is John and I am a developer\n"
        "WRONG output: USER: John is a developer who likes coding\n\n"
        "CORRECT example:\n"
        "USER: my name is John and I am a developer\n"
        "CORRECT output:\n"
        "NAME: John\n"
        "JOB: developer\n\n"
        f"User message: {user_msg}\n"
        "<end_of_turn>\n"
        "<start_of_turn>model\n"
    )

    # Rule-based extraction first (always works, no LLM needed)
    rule_facts = _rule_based_extract(user_msg)
    for k, v in rule_facts.items():
        print(f"[MEMORY] Rule-based: {k} = {v}")
        upsert_memory(k, v)

    response = None
    saved_count = 0

    try:
        response = call_llm(extraction_prompt, max_tokens=100, temperature=0.1)
        logger.debug(f"Memory extraction raw response: {repr(response)}")
        print(f"[MEMORY] Raw extraction: {repr(response)}")

        if response is None:
            print("[MEMORY] LLM returned None, skipping extraction")
            if debug_out is not None:
                debug_out['rule_facts'] = rule_facts
                debug_out['llm_raw'] = None
                debug_out['saved'] = saved_count
            return

        response = response.strip()
        
        # Reject if the entire response is a refusal/none indicator
        if response.upper() in ("NONE", "NO FACTS", "N/A", "", "NONE."):
            print("[MEMORY] No facts found in conversation")
            if debug_out is not None:
                debug_out['rule_facts'] = rule_facts
                debug_out['llm_raw'] = response
                debug_out['saved'] = saved_count
            return

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

            normalized = _normalize_key(key)
            if normalized not in ALLOWED_MEMORY_KEYS:
                print(f"[MEMORY] Rejected key not in allowlist: {repr(normalized)}")
                continue

            if not _is_valid_memory_value(value):
                print(f"[MEMORY] Rejected sentence-like value: {repr(value)}")
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

    if debug_out is not None:
        debug_out['rule_facts'] = rule_facts
        debug_out['llm_raw'] = response
        debug_out['saved'] = saved_count
