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
    
    return True, ""