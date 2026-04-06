import asyncio
import random
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Import our modules
from persona import load_persona, build_system_prompt
from db import init_db, save_message, get_messages, clear_messages, get_message_count
from memory import load_memories, format_for_prompt, extract_and_save
from llm import call_llm, build_prompt, get_context_pressure, summarize
from tts import generate_speech
from utils import validate_speech

# Global state
persona = {}
cached_summary = None
turn_counter = 0
system_prompt = ""
last_extraction_debug = {}
auto_mode_enabled = False
last_message_time = 0.0

# Pydantic models
class ChatRequest(BaseModel):
    message: str

class MemoriesUpdate(BaseModel):
    memories: dict

class PersonaUpdate(BaseModel):
    persona: dict

class AutoModeRequest(BaseModel):
    enabled: bool

@asynccontextmanager
async def lifespan(app: FastAPI):
    global persona, system_prompt
    init_db()
    persona = load_persona()
    system_prompt = build_system_prompt(persona)
    memories = load_memories()
    message_count = get_message_count()
    voice_file_present = Path("chris.wav").exists()
    
    llama_reachable = False
    try:
        import requests
        response = requests.get("http://localhost:8080/health", timeout=2)
        llama_reachable = response.status_code == 200
    except Exception:
        pass
    
    Path("audio_outputs").mkdir(exist_ok=True)
    print("=== Chris Voice Companion Started ===")
    print(f"Personality: {persona.get('name', 'Chris')}")
    print(f"Memories: {len(memories)}")
    print(f"Messages in DB: {message_count}")
    print(f"Voice file present: {voice_file_present}")
    print(f"Llama.cpp reachable: {llama_reachable}")
    print(f"Persona file: {Path('persona.json').absolute()}")
    print("=====================================")
    
    yield

app = FastAPI(lifespan=lifespan)

app.mount("/audio", StaticFiles(directory="audio_outputs"), name="audio")

@app.get("/")
async def root():
    return FileResponse("index.html")

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    global cached_summary, turn_counter, system_prompt, persona
    
    user_message = request.message.strip()
    global last_message_time
    last_message_time = time.time()
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty message")
    
    save_message("user", user_message)
    
    memories_str = format_for_prompt()
    recent_messages = get_messages(n=21)[:-1]
    
    prompt = build_prompt(
        system=system_prompt,
        memories=memories_str,
        summary=cached_summary,
        recent=recent_messages,
        user_message=user_message
    )
    
    context_info = get_context_pressure(prompt)
    
    turn_counter += 1
    total_messages = get_message_count()
    
    if turn_counter % 10 == 0 and total_messages > 20:
        all_messages = get_messages(n=100)
        if len(all_messages) > 10:
            older_messages = all_messages[:-10]
            summary = summarize(older_messages)
            if summary:
                cached_summary = summary
    
    if context_info["level"] == "high":
        all_messages = get_messages(n=50)
        if len(all_messages) > 10:
            older_messages = all_messages[:-10]
            summary = summarize(older_messages)
            if summary:
                cached_summary = summary
        prompt = build_prompt(
            system=system_prompt,
            memories=memories_str,
            summary=cached_summary,
            recent=recent_messages,
            user_message=user_message
        )
        context_info = get_context_pressure(prompt)
    
    def _get_response(p: str) -> Optional[str]:
        resp = call_llm(p, max_tokens=512, temperature=0.7)
        if resp and validate_speech(resp)[0]:
            return resp
        return None

    strict_prompt = "Reply with spoken words only — no asterisks, no actions, no parentheses.\n\n" + prompt
    assistant_response = _get_response(prompt) or _get_response(strict_prompt)
    is_fallback = assistant_response is None
    if is_fallback:
        assistant_response = "I'm having trouble right now. Give me a moment."
    
    save_message("assistant", assistant_response)
    last_message_time = time.time()
    
    if not is_fallback:
        global last_extraction_debug
        last_extraction_debug = {}
        try:
            await asyncio.wait_for(
                asyncio.to_thread(extract_and_save, user_message, assistant_response, last_extraction_debug),
                timeout=8.0
            )
        except asyncio.TimeoutError:
            print("[MEMORY] Extraction timed out after 8s")
            last_extraction_debug['error'] = 'timeout'
        except Exception as e:
            print(f"[MEMORY] Extraction failed: {e}")
            last_extraction_debug['error'] = str(e)
    
    audio_path = None
    audio_task = asyncio.to_thread(generate_speech, assistant_response)
    try:
        audio_path = await asyncio.wait_for(audio_task, timeout=25.0)
    except asyncio.TimeoutError:
        audio_path = None
    
    audio_url = None
    if audio_path:
        filename = Path(audio_path).name
        audio_url = f"/audio/{filename}"
    
    return JSONResponse({
        "text": assistant_response,
        "audio_url": audio_url,
        "context": context_info
    })

@app.get("/memories")
async def get_memories():
    try:
        return load_memories()
    except Exception:
        return {}

@app.put("/memories")
async def update_memories(update: MemoriesUpdate):
    from memory import save_memories
    save_memories(update.memories)
    return JSONResponse({"status": "ok"})

@app.delete("/memories")
async def clear_memories_endpoint():
    from memory import clear_memories
    clear_memories()
    return JSONResponse({"status": "ok"})

@app.get("/persona")
async def get_persona():
    return JSONResponse(persona)

@app.put("/persona")
async def update_persona(update: PersonaUpdate):
    global persona, system_prompt
    from persona import save_persona, build_system_prompt as bsp
    save_persona(update.persona)
    persona = update.persona
    system_prompt = bsp(persona)
    return JSONResponse({"status": "ok"})

@app.delete("/reset")
async def reset_endpoint():
    global cached_summary, turn_counter
    clear_messages()
    cached_summary = None
    turn_counter = 0
    return JSONResponse({"status": "ok"})

@app.get("/export")
async def export_conversation():
    messages = get_messages(n=1000)
    lines = []
    for msg in messages:
        timestamp = time.strftime("%H:%M", time.localtime(msg["timestamp"]))
        role = msg["role"].capitalize()
        content = msg["content"]
        lines.append(f"[{timestamp}] {role}: {content}")
    content = "\n".join(lines)
    return PlainTextResponse(content, headers={"Content-Disposition": "attachment; filename=conversation.txt"})

@app.get("/health")
async def health_check():
    global persona
    memories = load_memories()
    message_count = get_message_count()
    voice_file_present = Path("chris.wav").exists()
    
    llama_reachable = False
    try:
        import requests
        response = requests.get("http://localhost:8080/health", timeout=2)
        llama_reachable = response.status_code == 200
    except Exception:
        pass
    
    return JSONResponse({
        "status": "ok",
        "memories": len(memories),
        "messages": message_count,
        "llama_reachable": llama_reachable,
        "voice_file_present": voice_file_present
    })

@app.get("/context")
async def get_context():
    memories_str = format_for_prompt()
    recent_messages = get_messages(n=20)
    prompt = build_prompt(
        system=system_prompt,
        memories=memories_str,
        summary=cached_summary,
        recent=recent_messages,
        user_message="test"
    )
    return JSONResponse(get_context_pressure(prompt))

@app.get("/debug/memories")
async def debug_memories():
    from memory import load_memories, MEMORIES_FILE
    memories = load_memories()
    file_exists = MEMORIES_FILE.exists()
    file_size = MEMORIES_FILE.stat().st_size if file_exists else 0
    return JSONResponse({
        "file_exists": file_exists,
        "file_path": str(MEMORIES_FILE.absolute()),
        "file_size_bytes": file_size,
        "memory_count": len(memories),
        "memories": memories
    })

@app.get("/debug/last-extraction")
async def debug_last_extraction():
    return JSONResponse(last_extraction_debug)

@app.post("/auto-mode")
async def set_auto_mode(request: AutoModeRequest):
    global auto_mode_enabled, last_message_time
    auto_mode_enabled = request.enabled
    if request.enabled:
        last_message_time = time.time()
    print(f"[AUTO] Auto mode {'enabled' if request.enabled else 'disabled'}")
    return JSONResponse({"enabled": auto_mode_enabled})

@app.get("/auto-mode/poll")
async def auto_mode_poll():
    global last_message_time, cached_summary, system_prompt

    if not auto_mode_enabled:
        return JSONResponse({"message": None})

    now = time.time()
    silence_seconds = now - last_message_time

    if silence_seconds < 4:
        return JSONResponse({"message": None})

    memories_str = format_for_prompt()
    recent_messages = get_messages(n=10)

    proactive_modes = [
        "Ask the user a genuine curious question about their life, feelings, or day. One question only.",
        "Share a brief observation, thought, or something on your mind. Keep it to 1-2 sentences.",
        "Tell a short joke or funny observation. Keep it light.",
        "Check in on how the user is feeling right now. One sentence.",
        "Bring up something from earlier in the conversation or from your memories of them, naturally.",
        "Share a short interesting thought or fact about something you've been thinking about.",
        "Ask the user what they're up to right now.",
    ]

    chosen_mode = random.choice(proactive_modes)

    if recent_messages:
        last_content = recent_messages[-1].get("content", "")
        if len(last_content) > 10:
            chosen_mode = random.choice([
                f"Continue naturally from the last thing discussed: '{last_content[:80]}'. React to it or build on it in one sentence.",
                "Ask a follow-up question about what was just discussed. One sentence.",
                chosen_mode,
                chosen_mode,
            ])

    proactive_system = (
        f"{system_prompt}\n\n"
        f"IMPORTANT: {chosen_mode}\n"
        "Do not wait for the user. Just speak."
    )

    prompt = build_prompt(
        system=proactive_system,
        memories=memories_str,
        summary=cached_summary,
        recent=recent_messages,
        user_message="[continue the conversation naturally]"
    )

    def _generate():
        from utils import validate_speech
        resp = call_llm(prompt, max_tokens=120, temperature=0.85)
        if resp and validate_speech(resp)[0]:
            return resp
        simple = build_prompt(
            system=system_prompt,
            memories="",
            summary=None,
            recent=[],
            user_message="Say one friendly thing to start a conversation."
        )
        return call_llm(simple, max_tokens=80, temperature=0.9)

    try:
        message = await asyncio.wait_for(asyncio.to_thread(_generate), timeout=20.0)
    except asyncio.TimeoutError:
        message = None

    if not message or not message.strip():
        return JSONResponse({"message": None})

    save_message("assistant", message)
    last_message_time = time.time()

    audio_url = None
    try:
        audio_path = await asyncio.wait_for(
            asyncio.to_thread(generate_speech, message),
            timeout=25.0
        )
        if audio_path:
            audio_url = f"/audio/{Path(audio_path).name}"
    except asyncio.TimeoutError:
        pass

    return JSONResponse({"message": message, "audio_url": audio_url})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
