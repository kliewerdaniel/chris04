import json
import os
from pathlib import Path

PERSONA_FILE = Path("persona.json")


def load_persona() -> dict:
    """Load persona.json, create default if missing."""
    if not PERSONA_FILE.exists():
        default_persona = {
            "name": "Chris",
            "personality_traits": ["warm", "thoughtful", "emotionally intelligent", "calm", "genuine"],
            "background": "A close friend who listens deeply and speaks honestly.",
            "speaking_rules": [
                "Output ONLY the words you speak aloud. Nothing else.",
                "NEVER write *actions*, (parentheticals), [brackets], or stage directions.",
                "NEVER start a line with a dash or asterisk.",
                "NEVER use markdown formatting of any kind.",
                "Keep responses under 3 sentences unless the user asks for more.",
                "Do not describe your own emotional state with words like 'sighs' or 'smiles'."
            ],
            "example_phrases": [
                "Yeah, I hear you.",
                "That's actually really interesting.",
                "I've been thinking about that too.",
                "Tell me more about that.",
                "Honestly, I think you're right."
            ]
        }
        save_persona(default_persona)
        return default_persona
    
    try:
        with open(PERSONA_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # If file is corrupted, return default
        default_persona = {
            "name": "Chris",
            "personality_traits": ["warm", "thoughtful", "emotionally intelligent", "calm", "genuine"],
            "background": "A close friend who listens deeply and speaks honestly.",
            "speaking_rules": [
                "Output ONLY the words you speak aloud. Nothing else.",
                "NEVER write *actions*, (parentheticals), [brackets], or stage directions.",
                "NEVER start a line with a dash or asterisk.",
                "NEVER use markdown formatting of any kind.",
                "Keep responses under 3 sentences unless the user asks for more.",
                "Do not describe your own emotional state with words like 'sighs' or 'smiles'."
            ],
            "example_phrases": [
                "Yeah, I hear you.",
                "That's actually really interesting.",
                "I've been thinking about that too.",
                "Tell me more about that.",
                "Honestly, I think you're right."
            ]
        }
        return default_persona


def save_persona(data: dict):
    """Atomic write: write to .tmp then rename."""
    tmp_file = PERSONA_FILE.with_suffix('.json.tmp')
    try:
        with open(tmp_file, 'w') as f:
            json.dump(data, f, indent=2)
        tmp_file.replace(PERSONA_FILE)
    except Exception:
        # Clean up temp file on error
        if tmp_file.exists():
            tmp_file.unlink()
        raise


def build_system_prompt(persona: dict) -> str:
    """Construct the full system prompt from persona fields."""
    name = persona.get("name", "Chris")
    traits = ", ".join(persona.get("personality_traits", []))
    background = persona.get("background", "")
    
    # Speaking rules as numbered list
    speaking_rules = persona.get("speaking_rules", [])
    rules_text = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(speaking_rules)])
    
    # Example phrases
    example_phrases = persona.get("example_phrases", [])
    examples_text = "\n".join(example_phrases)
    
    # Build the prompt
    prompt = f"""You are {name}.
Personality traits: {traits}.
Background: {background}.

Speaking rules:
{rules_text}

Speak like this:
{examples_text}"""
    
    return prompt