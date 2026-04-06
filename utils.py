import re

def validate_speech(text: str) -> tuple[bool, str]:
    """
    Validate that text contains only spoken words, no stage directions or formatting.
    Returns (True, "") if valid, or (False, reason) if invalid.
    """
    if not text or not text.strip():
        return False, "Empty response"
    
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        # Check for asterisks anywhere in the line
        if '*' in line:
            return False, f"Line {i+1}: Contains asterisks"
        
        # Check for parentheses or brackets
        if '(' in line or ')' in line or '[' in line or ']' in line:
            return False, f"Line {i+1}: Contains parentheses or brackets"
        
        # Check for lines beginning with em-dash or hyphen (stage directions)
        if line.startswith('—') or line.startswith('-'):
            return False, f"Line {i+1}: Begins with dash (possible stage direction)"
        
        # Check for isolated stage-direction words (case-insensitive)
        stage_direction_words = {
            'smiles', 'nods', 'pauses', 'sighs', 'laughs', 'thinks', 
            'whispers', 'glances', 'hesitates', 'chuckles'
        }
        
        # Split line into words and check if any word is a stage direction word
        words = re.findall(r'\b\w+\b', line.lower())
        for word in words:
            if word in stage_direction_words:
                return False, f"Line {i+1}: Contains stage-direction word '{word}'"
    
    return True, ""