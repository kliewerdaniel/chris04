import asyncio
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

# Pydantic models
class ChatRequest(BaseModel):
    message: str

class MemoriesUpdate(BaseModel):
    memories: dict

class PersonaUpdate(BaseModel):
    persona: dict

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
    
    async def _run_extraction(user_message: str, assistant_response: str):
        try:
            await asyncio.to_thread(extract_and_save, user_message, assistant_response)
        except Exception as e:
            print(f"[MEMORY] Background extraction task failed: {e}")

    if not is_fallback:
        asyncio.create_task(_run_extraction(user_message, assistant_response))
    
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
