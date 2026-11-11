import os
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from .analytics import analytics_for
from .data import SELLERS, get_seller
from .speech import clean_text_for_speech

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    database_path = Path("/tmp/virtual_kam.db") if os.getenv("VERCEL") else Path(__file__).parent / "virtual_kam.db"
    DATABASE_URL = f"sqlite:///{database_path}"
whisper_model = None
engine_options = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, **engine_options)
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, seller_id TEXT, role TEXT, content TEXT, created_at TEXT)"))

app = FastAPI(title="Snapdeal Virtual KAM", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in ["http://localhost:5173", "http://127.0.0.1:5173", os.getenv("FRONTEND_ORIGIN")] if origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    seller_id: str
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)

@app.get("/api/health")
def health():
    return {"status": "ok", "llm_configured": bool(os.getenv("GROQ_API_KEY")), "voice_mode": "local-models-when-installed"}

@app.get("/api/sellers")
def sellers():
    return [{k: seller[k] for k in ("id", "name", "category", "location", "synthetic")} for seller in SELLERS]

@app.get("/api/sellers/{seller_id}/analytics")
def seller_analytics(seller_id: str):
    seller = get_seller(seller_id)
    if not seller: raise HTTPException(404, "Seller not found")
    result = analytics_for(seller)
    result["seller"] = {k: v for k, v in seller.items() if k != "products"}
    return result

@app.get("/api/sellers/{seller_id}/products")
def products(seller_id: str):
    seller = get_seller(seller_id)
    if not seller: raise HTTPException(404, "Seller not found")
    return seller["products"]

@app.post("/api/chat")
def chat(request: ChatRequest):
    seller = get_seller(request.seller_id)
    if not seller: raise HTTPException(404, "Seller not found")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO conversations VALUES (:id,:seller_id,'user',:content,:created_at)"), {"id": str(uuid.uuid4()), "seller_id": request.seller_id, "content": request.message, "created_at": datetime.utcnow().isoformat()})
    context = analytics_for(seller)
    response = f"I checked {seller['name']}'s recent numbers. The clearest signal is conversion: your top product moved from {seller['products'][0]['previous_conversion']}% to {seller['products'][0]['conversion']}%, while impressions remain healthy. I see this as a pricing hypothesis, not a proven cause. Would you like to test a ₹50 reduction on {seller['products'][0]['name']} for seven days?"
    source = "deterministic-demo-context"
    previous_assistant_message = next(
        (turn["content"] for turn in reversed(request.history) if turn.get("role") == "assistant"),
        "",
    ).lower()
    if "what area" in previous_assistant_message or "focus" in previous_assistant_message:
        response = f"Got it. We will focus on {request.message.strip()} first. I will use the seller data to separate what changed from what might be causing it, then suggest one measurable next step."
        source = "deterministic-contextual-follow-up"
    if OpenAI and os.getenv("GROQ_API_KEY"):
        client = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1", timeout=20, max_retries=2)
        system = "You are Snapdeal Virtual KAM. Be concise and conversational. Use only the supplied seller facts. Separate observed facts from hypotheses, never guarantee projections, and never approve an action yourself. Ask one question at a time."
        messages = [{"role": "system", "content": system}]
        for turn in request.history[-20:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        facts = {"seller": seller["name"], "analytics": context, "user_message": request.message}
        messages.append({"role": "user", "content": str(facts)})
        try:
            completion = client.chat.completions.create(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"), messages=messages, temperature=0.2)
            response = completion.choices[0].message.content or response
            source = "groq"
        except Exception:
            source = "deterministic-fallback-after-groq-error"
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO conversations VALUES (:id,:seller_id,'assistant',:content,:created_at)"), {"id": str(uuid.uuid4()), "seller_id": request.seller_id, "content": response, "created_at": datetime.utcnow().isoformat()})
    return {"response": response, "source": source}

@app.post("/api/voice/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("audio/"): raise HTTPException(400, "Upload an audio file")
    contents = await file.read()
    if len(contents) > 15 * 1024 * 1024: raise HTTPException(413, "Audio file is too large")
    audio_suffix = "." + (file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "webm")
    try:
        from faster_whisper import WhisperModel
        global whisper_model
        if whisper_model is None:
            whisper_model = WhisperModel(
                os.getenv("WHISPER_MODEL", "base"),
                device="cpu",
                compute_type="int8",
                use_auth_token=os.getenv("HF_TOKEN") or None,
            )
        with tempfile.NamedTemporaryFile(suffix=audio_suffix, delete=False) as audio_file:
            audio_file.write(contents)
            audio_path = audio_file.name
        segments, _ = whisper_model.transcribe(audio_path, language="en", vad_filter=True)
        text_value = " ".join(segment.text.strip() for segment in segments).strip()
        return {"text": text_value, "source": "faster-whisper"}
    except Exception as error:
        return {"text": "", "source": "fallback", "message": f"Local transcription is unavailable: {error.__class__.__name__}. Install faster-whisper and its model."}
    finally:
        if "audio_path" in locals():
            Path(audio_path).unlink(missing_ok=True)

@app.post("/api/voice/synthesize")
async def synthesize(payload: dict):
    text_value = str(payload.get("text", "")).strip()
    if not text_value: raise HTTPException(400, "Text is required")
    speech_text = clean_text_for_speech(text_value)
    if not speech_text: raise HTTPException(400, "Text has no speakable content")
    output_path = Path(tempfile.gettempdir()) / f"virtual-kam-{uuid.uuid4()}.wav"
    configured_voice = os.getenv("PIPER_VOICE", "en_US-lessac-medium")
    voice_path = Path(configured_voice).expanduser()
    if not voice_path.is_file():
        model_dir = Path(os.getenv("PIPER_MODEL_DIR", Path.home() / ".local/share/piper")).expanduser()
        voice_path = model_dir / f"{configured_voice.removesuffix('.onnx')}.onnx"
    if not voice_path.is_file():
        return {"audio_url": None, "source": "fallback", "message": "Piper voice model is unavailable. Download the configured voice model first."}
    try:
        subprocess.run(["piper", "--model", str(voice_path), "--output_file", str(output_path)], input=speech_text, text=True, capture_output=True, check=True, timeout=30)
        return {"audio_url": f"/api/voice/audio/{output_path.name}", "source": "piper"}
    except (OSError, subprocess.SubprocessError):
        return {"audio_url": None, "source": "fallback", "message": "Piper could not synthesize this response. Check the local voice installation."}

@app.get("/api/voice/audio/{filename}")
def voice_audio(filename: str):
    audio_path = Path(tempfile.gettempdir()) / filename
    if not audio_path.is_file() or audio_path.suffix != ".wav": raise HTTPException(404, "Audio not found")
    return FileResponse(audio_path, media_type="audio/wav", filename=filename)

