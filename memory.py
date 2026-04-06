import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

MEMORIES_FILE = Path("memories.json")

ALLOWED_MEMORY_KEYS = {
    # Identity
    'NAME', 'NICKNAME', 'AGE', 'BIRTHDAY', 'GENDER', 'PRONOUNS', 'NATIONALITY', 'ETHNICITY',

    # Location
    'CITY', 'TOWN', 'NEIGHBORHOOD', 'STATE', 'COUNTRY', 'LOCATION', 'HOMETOWN', 'TIMEZONE',

    # Work & Education
    'JOB', 'OCCUPATION', 'PROFESSION', 'ROLE', 'COMPANY', 'EMPLOYER', 'INDUSTRY', 'FIELD',
    'SCHOOL', 'UNIVERSITY', 'COLLEGE', 'DEGREE', 'MAJOR', 'GRADUATION_YEAR',
    'CAREER_GOAL', 'WORK_STYLE', 'WORK_HOURS', 'REMOTE', 'COWORKER', 'BOSS',

    # Relationships & Family
    'PARTNER', 'SPOUSE', 'BOYFRIEND', 'GIRLFRIEND', 'RELATIONSHIP_STATUS',
    'KIDS', 'CHILDREN', 'CHILD_NAME', 'CHILD_AGE',
    'PARENT', 'MOM', 'DAD', 'SIBLING', 'SIBLINGS', 'BROTHER', 'SISTER',
    'GRANDPARENT', 'FRIEND', 'BEST_FRIEND', 'FAMILY', 'LIVING_WITH',

    # Pets
    'PET', 'PETS', 'DOG', 'CAT', 'PET_NAME', 'PET_BREED',

    # Interests & Hobbies
    'HOBBY', 'HOBBIES', 'INTEREST', 'INTERESTS', 'PASSION', 'PASTIME',
    'SPORT', 'SPORTS_TEAM', 'EXERCISE', 'FITNESS', 'WORKOUT',
    'MUSIC', 'MUSIC_GENRE', 'FAVORITE_BAND', 'FAVORITE_ARTIST', 'INSTRUMENT',
    'BOOK', 'FAVORITE_BOOK', 'FAVORITE_AUTHOR', 'GENRE',
    'MOVIE', 'FAVORITE_MOVIE', 'FAVORITE_SHOW', 'TV_SHOW',
    'GAME', 'VIDEO_GAME', 'BOARD_GAME',
    'TRAVEL', 'FAVORITE_PLACE', 'BUCKET_LIST', 'VISITED',
    'CREATIVE', 'ART', 'WRITING', 'PHOTOGRAPHY', 'COOKING', 'CRAFTS',
    'COLLECTION', 'VOLUNTEERING', 'CAUSE',

    # Food & Drink
    'FOOD', 'FAVORITE_FOOD', 'CUISINE', 'DIETARY', 'DIET', 'ALLERGY', 'VEGETARIAN',
    'VEGAN', 'DRINK', 'COFFEE', 'ALCOHOL',

    # Personality & Values
    'PERSONALITY', 'VALUE', 'VALUES', 'BELIEF', 'RELIGION', 'POLITICS',
    'STRENGTH', 'WEAKNESS', 'FEAR', 'DREAM', 'GOAL', 'AMBITION',
    'LOVE_LANGUAGE', 'COMMUNICATION_STYLE', 'INTROVERT', 'EXTROVERT',

    # Health & Wellbeing
    'HEALTH', 'CONDITION', 'MEDICATION', 'THERAPY', 'MENTAL_HEALTH',
    'SLEEP', 'SLEEP_SCHEDULE', 'ENERGY', 'STRESS', 'MOOD', 'EMOTION',

    # Life circumstances
    'LIVING_SITUATION', 'HOME', 'RENT', 'OWN', 'ROOMMATE',
    'INCOME', 'FINANCIAL_GOAL', 'DEBT', 'SAVINGS',
    'CAR', 'TRANSPORT', 'COMMUTE',
    'LANGUAGE', 'LANGUAGES_SPOKEN',

    # Current context
    'CURRENT_PROJECT', 'CURRENT_CHALLENGE', 'CURRENT_GOAL', 'RECENT_EVENT',
    'UPCOMING_EVENT', 'ANNIVERSARY', 'WEDDING', 'MOVING', 'NEW_JOB',

    # Meta
    'LAST_SEEN', 'FIRST_CONVERSATION', 'NOTE',
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
    """Extract facts from user message using comprehensive regex patterns."""
    facts = {}
    original = user_msg.strip()
    text = original.lower()

    # ── Name ────────────────────────────────────────────
    for pattern in [
        r"my name(?:'s| is) ([A-Za-z]+)",
        r"(?:call me|i'm called|i go by) ([A-Za-z]+)",
        r"i'm ([A-Z][a-z]{1,20}) (?:and|but|so|,)",
        r"^([A-Z][a-z]{1,20}) here[,\.]",
        r"this is ([A-Z][a-z]{1,20}) (?:here|speaking)",
    ]:
        m = re.search(pattern, original, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            skip = {'a','an','the','not','so','just','very','really','going','trying',
                    'doing','feeling','having','getting','looking','thinking','talking'}
            if name.lower() not in skip and len(name) > 1:
                facts['NAME'] = name.capitalize()
                break

    # ── Nickname ─────────────────────────────────────────
    for pattern in [
        r"(?:everyone calls me|people call me|friends call me|my nickname is) ([A-Za-z]+)",
        r"(?:you can call me|just call me) ([A-Za-z]+)",
    ]:
        m = re.search(pattern, original, re.IGNORECASE)
        if m:
            facts['NICKNAME'] = m.group(1).strip().capitalize()
            break

    # ── Age ──────────────────────────────────────────────
    for pattern in [
        r"\bi(?:'m| am) (\d{1,3})(?: years? old)?",
        r"i(?:'m| am) turning (\d{1,3})",
        r"my age is (\d{1,3})",
        r"(\d{1,3}) years? old",
        r"just turned (\d{1,3})",
    ]:
        m = re.search(pattern, text)
        if m:
            try:
                age = int(m.group(1))
                if 5 < age < 110:
                    facts['AGE'] = str(age)
                    break
            except ValueError:
                pass

    # ── Birthday ─────────────────────────────────────────
    for pattern in [
        r"(?:my birthday is|born on|born in) ((?:january|february|march|april|may|june|july|august|september|october|november|december)[^,\.]{0,20})",
        r"(?:my birthday is|born on) (\d{1,2}(?:st|nd|rd|th)? (?:of )?(?:january|february|march|april|may|june|july|august|september|october|november|december))",
    ]:
        m = re.search(pattern, text)
        if m:
            facts['BIRTHDAY'] = m.group(1).strip().title()
            break

    # ── Job / Occupation ─────────────────────────────────
    job_skip = {'bit','lot','fan','huge','big','small','little','pretty','very','really',
                'quite','good','bad','tired','busy','happy','sad','lucky','mess','wreck',
                'okay','fine','great','terrible','awful','amazing','kind','nice','sure',
                'only','just','still','already','always','never','here','there'}

    for pattern in [
        r"i(?:'m| am) a(?:n)? ([\w]+(?: [\w]+){0,3}) (?:by profession|by trade|for work|for a living)",
        r"i work(?:ed)? as a(?:n)? ([\w]+(?: [\w]+){0,2})",
        r"i(?:'m| am) (?:currently )?(?:working|employed) as a(?:n)? ([\w]+(?: [\w]+){0,2})",
        r"my (?:job|occupation|profession|career|work) is ([\w]+(?: [\w]+){0,2})",
        r"my (?:job|occupation|profession) (?:is|was) a(?:n)? ([\w]+(?: [\w]+){0,2})",
        r"i(?:'m| am) a(?:n)? ([\w]+(?: [\w]+){0,2}) (?:at|for|with) [A-Z]",
        r"i work(?:ed)? (?:at|for|in) [\w\s]+ as a(?:n)? ([\w]+(?: [\w]+){0,2})",
    ]:
        m = re.search(pattern, text)
        if m:
            job = m.group(1).strip()
            if job and job.split()[0] not in job_skip and len(job) > 2:
                facts['JOB'] = job.title()
                break

    # Simpler job pattern as fallback — only if no job found yet
    if 'JOB' not in facts:
        m = re.search(r"\bi(?:'m| am) a(?:n)? ([\w]{4,}(?:(?: [\w]+){0,2}))\b", text)
        if m:
            job = m.group(1).strip()
            if job.split()[0] not in job_skip and not any(c.isdigit() for c in job):
                facts['JOB'] = job.title()

    # ── Company / Employer ───────────────────────────────
    for pattern in [
        r"i work (?:at|for) ([A-Z][A-Za-z0-9\s&]{1,30}?)(?:\.|,|$| as| and)",
        r"(?:my company|my employer|my workplace) is ([A-Za-z0-9\s&]{2,30}?)(?:\.|,|$)",
        r"employed (?:at|by) ([A-Z][A-Za-z0-9\s&]{1,30}?)(?:\.|,|$)",
    ]:
        m = re.search(pattern, original)
        if m:
            company = m.group(1).strip()
            if len(company) > 1:
                facts['COMPANY'] = company
                break

    # ── City / Location ──────────────────────────────────
    for pattern in [
        r"i(?:'m| am) (?:currently |now )?(?:living|based|located|staying|situated) in ([A-Z][a-zA-Z\s]{1,30}?)(?:\.|,|$)",
        r"i live(?:d)? in ([A-Z][a-zA-Z\s]{1,30}?)(?:\.|,|$)",
        r"i(?:'m| am) from ([A-Z][a-zA-Z\s]{1,30}?)(?:\.|,|$| originally)",
        r"i(?:'m| am) in ([A-Z][a-zA-Z\s]{1,30}?) (?:right now|currently|these days|at the moment)",
        r"(?:moved to|relocating to|just moved to) ([A-Z][a-zA-Z\s]{1,30}?)(?:\.|,|$)",
        r"(?:grew up in|raised in|born in) ([A-Z][a-zA-Z\s]{1,30}?)(?:\.|,|$)",
    ]:
        m = re.search(pattern, original)
        if m:
            loc = m.group(1).strip()
            loc_skip = {'a','an','the','here','there','this','that','home','work','school','college'}
            if len(loc) > 1 and loc.lower() not in loc_skip:
                facts['CITY'] = loc
                break

    # ── Hometown ─────────────────────────────────────────
    for pattern in [
        r"(?:grew up in|raised in|my hometown is|originally from) ([A-Z][a-zA-Z\s]{1,30}?)(?:\.|,|$)",
    ]:
        m = re.search(pattern, original)
        if m and 'CITY' not in facts:
            facts['HOMETOWN'] = m.group(1).strip()
            break

    # ── School / University ──────────────────────────────
    for pattern in [
        r"i(?:'m| am) (?:studying|enrolled) at ([A-Z][a-zA-Z\s]{1,40}?)(?:\.|,|$)",
        r"i (?:go|went|attend|attended) to ([A-Z][a-zA-Z\s]{1,40}?) (?:university|college|school|high school)",
        r"(?:my school|my university|my college) is ([A-Za-z\s]{2,40}?)(?:\.|,|$)",
        r"i(?:'m| am) a student at ([A-Z][a-zA-Z\s]{1,40}?)(?:\.|,|$)",
        r"i graduated from ([A-Z][a-zA-Z\s]{1,40}?)(?:\.|,|$)",
    ]:
        m = re.search(pattern, original, re.IGNORECASE)
        if m:
            facts['SCHOOL'] = m.group(1).strip()
            break

    # ── Major / Degree ───────────────────────────────────
    for pattern in [
        r"(?:studying|majoring in|i study|my major is|my degree is (?:in)?) ([\w\s]{3,30}?)(?:\.|,|$)",
        r"(?:i have a|i got my|i finished my) ([\w\s]{3,20}?) degree",
    ]:
        m = re.search(pattern, text)
        if m:
            facts['MAJOR'] = m.group(1).strip().title()
            break

    # ── Relationship status ───────────────────────────────
    for pattern, value in [
        (r"i(?:'m| am) (?:currently )?(?:married|wed)", "married"),
        (r"i(?:'m| am) (?:currently )?(?:single|not dating|not in a relationship)", "single"),
        (r"i(?:'m| am) (?:currently )?(?:engaged)", "engaged"),
        (r"i(?:'m| am) (?:currently )?(?:divorced|separated)", "divorced"),
        (r"i(?:'m| am) (?:currently )?(?:dating|seeing someone|in a relationship)", "in a relationship"),
        (r"i(?:'m| am) (?:currently )?(?:widowed)", "widowed"),
    ]:
        if re.search(pattern, text):
            facts['RELATIONSHIP_STATUS'] = value
            break

    # ── Partner / Spouse ─────────────────────────────────
    for pattern in [
        r"my (?:wife|husband|spouse|partner|girlfriend|boyfriend)(?:'s name)? is ([A-Za-z]+)",
        r"(?:married to|dating|engaged to|together with) ([A-Z][a-z]+)",
    ]:
        m = re.search(pattern, original, re.IGNORECASE)
        if m:
            facts['PARTNER'] = m.group(1).strip().capitalize()
            break

    # ── Kids / Children ──────────────────────────────────
    for pattern in [
        r"i have (\w+) (?:kids|children|sons|daughters)",
        r"(\w+) (?:kids|children)",
        r"my (?:son|daughter|child|kid)(?:'s name)? is ([A-Za-z]+)",
    ]:
        m = re.search(pattern, text)
        if m:
            if 'son' in pattern or 'daughter' in pattern or 'child' in pattern or 'kid' in pattern:
                if len(m.groups()) > 0:
                    val = m.group(1).strip()
                    if val not in ('name','called'):
                        facts['CHILD_NAME'] = val.capitalize()
            else:
                facts['KIDS'] = m.group(1).strip()
            break

    # ── Pets ─────────────────────────────────────────────
    for pattern in [
        r"(?:i have|i own|i got) (?:a |an )?(?:pet )?(?:dog|cat|rabbit|hamster|fish|bird|turtle|snake|lizard|guinea pig)",
        r"my (?:dog|cat|rabbit|hamster|fish|bird|turtle|snake|lizard|guinea pig)(?:'s name)? is ([A-Za-z]+)",
        r"(?:i have|i own) (\d+) (?:dogs|cats|pets|animals)",
    ]:
        m = re.search(pattern, text)
        if m:
            if m.groups() and m.group(1):
                facts['PET_NAME'] = m.group(1).strip().capitalize()
            else:
                # Extract the animal type from the matched string
                animals = ['dog','cat','rabbit','hamster','fish','bird','turtle','snake','lizard','guinea pig']
                for animal in animals:
                    if animal in m.group(0):
                        facts['PET'] = animal
                        break
            break

    # ── Hobbies / Interests ───────────────────────────────
    hobby_patterns = [
        r"(?:i love|i enjoy|i like|i'm into|i'm passionate about|i'm really into|i'm obsessed with|i adore) ([\w\s]{2,30}?)(?:\.|,|$| and | but )",
        r"(?:my hobby is|my hobbies (?:are|include)|i spend (?:my )?time) ([\w\s]{2,30}?)(?:\.|,|$)",
        r"(?:i've been|i've started) ([\w\s]{2,25}?)(?:ing\b) (?:a lot|lately|recently|these days|for fun)",
        r"i(?:'m| am) (?:really )?(?:into|passionate about) ([\w\s]{2,25}?)(?:\.|,|$)",
    ]
    hobby_skip = {'it','this','that','much','more','less','you','me','him','her','them',
                  'very','really','quite','just','only','always','never','doing','going'}
    for pattern in hobby_patterns:
        m = re.search(pattern, text)
        if m:
            hobby = m.group(1).strip().rstrip('ing').strip()
            if hobby and hobby not in hobby_skip and len(hobby) > 2:
                facts['HOBBY'] = hobby.title()
                break

    # ── Music ─────────────────────────────────────────────
    for pattern in [
        r"(?:i love|i listen to|i'm into|i like) ([\w\s]{2,25}?) (?:music|songs|bands?|artists?)",
        r"my favorite (?:music|genre|band|artist) is ([\w\s]{2,25}?)(?:\.|,|$)",
        r"(?:i love|i like|i'm a fan of) ([\w\s]{2,20}?) (?:is my favorite band|is my favorite artist)",
    ]:
        m = re.search(pattern, text)
        if m:
            facts['MUSIC'] = m.group(1).strip().title()
            break

    # ── Food ─────────────────────────────────────────────
    for pattern in [
        r"my favorite food is ([\w\s]{2,25}?)(?:\.|,|$)",
        r"i love (?:eating |to eat )?([\w\s]{2,25}?)(?:\.|,|$| for (?:breakfast|lunch|dinner))",
        r"(?:i'm|i am) (?:a )?(?:vegetarian|vegan|pescatarian|carnivore|omnivore)",
        r"i(?:'m| am) gluten.?(?:free|intolerant)",
        r"i(?:'m| am) lactose.?intolerant",
        r"i(?:'m| am) allergic to ([\w\s]{2,20}?)(?:\.|,|$)",
    ]:
        m = re.search(pattern, text)
        if m:
            if 'vegetarian' in m.group(0): facts['DIET'] = 'vegetarian'; break
            elif 'vegan' in m.group(0): facts['DIET'] = 'vegan'; break
            elif 'pescatarian' in m.group(0): facts['DIET'] = 'pescatarian'; break
            elif 'gluten' in m.group(0): facts['DIET'] = 'gluten-free'; break
            elif 'lactose' in m.group(0): facts['DIET'] = 'lactose-intolerant'; break
            elif 'allergic' in m.group(0) and m.groups():
                facts['ALLERGY'] = m.group(1).strip().title(); break
            elif m.groups():
                facts['FOOD'] = m.group(1).strip().title(); break

    # ── Sport ─────────────────────────────────────────────
    for pattern in [
        r"i (?:play|played) ([\w\s]{2,20}?)(?:\.|,|$| (?:competitively|recreationally|for fun|in a league|on a team))",
        r"i(?:'m| am) (?:a )?[\w\s]{0,10}? ([\w\s]{2,20}?) (?:player|athlete|runner|cyclist|swimmer|climber)",
        r"my favorite sport is ([\w\s]{2,20}?)(?:\.|,|$)",
        r"i (?:run|swim|cycle|hike|climb|ski|surf|skate|box|wrestle|lift)(?: weights)?(?:\b)",
    ]:
        m = re.search(pattern, text)
        if m:
            if m.groups():
                sport = m.group(1).strip()
                if len(sport) > 2:
                    facts['SPORT'] = sport.title()
            else:
                # Extract the verb
                verbs = ['run','swim','cycle','hike','climb','ski','surf','skate','box','wrestle','lift']
                for v in verbs:
                    if v in m.group(0):
                        facts['EXERCISE'] = v + 'ning' if v.endswith('n') else v + 'ing'
                        break
            break

    # ── Goals / Dreams ────────────────────────────────────
    for pattern in [
        r"(?:my goal is|i want to|i'm trying to|i hope to|i dream of|i'd love to) ([\w\s]{3,40}?)(?:\.|,|$)",
        r"(?:my dream is|my ambition is) (?:to )?([\w\s]{3,40}?)(?:\.|,|$)",
        r"(?:i'm working towards|i'm working on|i'm saving (?:up )?for) ([\w\s]{3,40}?)(?:\.|,|$)",
    ]:
        m = re.search(pattern, text)
        if m:
            goal = m.group(1).strip()
            if len(goal) > 4:
                facts['GOAL'] = goal.capitalize()
                break

    # ── Fears ─────────────────────────────────────────────
    for pattern in [
        r"(?:i(?:'m| am) afraid of|i fear|my biggest fear is|i(?:'m| am) scared of|i(?:'m| am) terrified of) ([\w\s]{2,30}?)(?:\.|,|$)",
    ]:
        m = re.search(pattern, text)
        if m:
            facts['FEAR'] = m.group(1).strip().title()
            break

    # ── Mood / Feeling ────────────────────────────────────
    for pattern in [
        r"i(?:'m| am) (?:feeling |really |so |pretty |quite )?(stressed|anxious|depressed|happy|excited|bored|lonely|overwhelmed|burnt out|exhausted|nervous|worried|sad|angry|frustrated|content|grateful|proud|motivated)(?:\b)",
    ]:
        m = re.search(pattern, text)
        if m:
            facts['MOOD'] = m.group(1).strip().lower()
            break

    # ── Health ────────────────────────────────────────────
    for pattern in [
        r"i(?:'m| am) (?:dealing with|struggling with|managing|living with) ([\w\s]{2,30}?)(?:\.|,|$)",
        r"i have (?:been diagnosed with|a condition called|chronic) ([\w\s]{2,30}?)(?:\.|,|$)",
        r"i(?:'ve| have) (?:been|had) ([\w\s]{2,25}?) for (?:\d+ )?(?:years?|months?)",
    ]:
        m = re.search(pattern, text)
        if m:
            condition = m.group(1).strip()
            if len(condition) > 3:
                facts['HEALTH'] = condition.title()
                break

    # ── Sleep ─────────────────────────────────────────────
    for pattern in [
        r"i (?:usually |normally |always |typically )?(?:go to (?:sleep|bed)|wake up|sleep) (?:at|around|by) ([\d:apm\s]{3,15}?)(?:\.|,|$)",
        r"i only get (\d[\w\s]{1,15}?) (?:of )?sleep",
        r"i(?:'m| am) a (?:night owl|morning person|early riser|light sleeper|heavy sleeper)",
    ]:
        m = re.search(pattern, text)
        if m:
            if m.groups():
                facts['SLEEP'] = m.group(1).strip()
            else:
                sleep_types = ['night owl','morning person','early riser','light sleeper','heavy sleeper']
                for st in sleep_types:
                    if st in m.group(0):
                        facts['SLEEP'] = st
                        break
            break

    # ── Language ──────────────────────────────────────────
    languages = ['english','spanish','french','german','italian','portuguese','chinese','japanese',
                 'korean','arabic','hindi','russian','dutch','swedish','polish','turkish','vietnamese',
                 'thai','greek','hebrew','indonesian','malay','czech','danish','finnish','norwegian',
                 'romanian','hungarian','ukrainian','persian','tagalog','swahili']
    for pattern in [
        r"i speak ([\w\s,and]{2,40}?)(?:\.|$| fluently| natively| as my| at home)",
        r"my (?:native|first|mother) (?:language|tongue) is ([\w\s]{2,20}?)(?:\.|,|$)",
        r"i(?:'m| am) (?:fluent|proficient|conversational) in ([\w\s]{2,20}?)(?:\.|,|$)",
        r"i(?:'m| am) learning ([\w\s]{2,20}?)(?:\.|,|$)",
    ]:
        m = re.search(pattern, text)
        if m:
            lang_match = m.group(1).strip()
            for lang in languages:
                if lang in lang_match:
                    facts['LANGUAGE'] = lang.capitalize()
                    break
            if 'LANGUAGE' in facts:
                break

    # ── Living situation ──────────────────────────────────
    for pattern, value in [
        (r"i(?:'m| am) (?:currently )?renting", "renting"),
        (r"i own (?:my )?(?:home|house|apartment|place|condo)", "owns home"),
        (r"i live (?:alone|by myself)", "lives alone"),
        (r"i live with (?:my )?(?:parents?|family)", "lives with family"),
        (r"i have (?:a |some )?roommates?", "has roommates"),
        (r"i live with (?:my )?(partner|wife|husband|girlfriend|boyfriend)", "lives with partner"),
    ]:
        if re.search(pattern, text):
            facts['LIVING_SITUATION'] = value
            break

    # ── Nationality ───────────────────────────────────────
    nationalities = ['american','british','canadian','australian','irish','scottish','welsh',
                     'french','german','italian','spanish','portuguese','dutch','swedish',
                     'norwegian','danish','finnish','polish','russian','ukrainian','greek',
                     'turkish','japanese','chinese','korean','indian','pakistani','brazilian',
                     'mexican','argentinian','colombian','south african','nigerian','egyptian',
                     'israeli','iranian','iraqi','saudi','emirati','singaporean','thai',
                     'vietnamese','indonesian','filipino','new zealander','swiss','belgian',
                     'austrian','czech','hungarian','romanian']
    for pattern in [
        r"i(?:'m| am) ([\w]+) (?:american|british|canadian|australian)",
        r"i(?:'m| am) (?:from |a )?([\w]+) (?:by birth|by nationality|citizen|national)",
    ]:
        m = re.search(pattern, text)
        if m:
            facts['NATIONALITY'] = m.group(1).strip().capitalize()
            break
    if 'NATIONALITY' not in facts:
        for nat in nationalities:
            if re.search(r"\bi(?:'m| am) " + nat + r"\b", text):
                facts['NATIONALITY'] = nat.capitalize()
                break

    return facts


def extract_and_save(user_msg: str, assistant_msg: str, debug_out: dict = None):
    """Extract memories from conversation and save them."""
    
    # Rule-based extraction first (always works, no LLM needed)
    rule_facts = _rule_based_extract(user_msg)
    for k, v in rule_facts.items():
        print(f"[MEMORY] Rule-based: {k} = {v}")
        upsert_memory(k, v)

    # LLM extraction disabled — rule-based extractor above handles extraction.
    # Re-enable when using a larger model that reliably follows the KEY: value format.
    if rule_facts:
        upsert_memory("LAST_SEEN", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    
    if debug_out is not None:
        debug_out['rule_facts'] = rule_facts
        debug_out['llm_raw'] = 'disabled'
        debug_out['saved'] = len(rule_facts)
