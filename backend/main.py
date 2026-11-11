import os
import json
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

from .analytics import analytics_for, funnel_for, inventory_for, price_comparison_for, sales_trend_for, simulate_price_change
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
    conn.execute(text("CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, seller_id TEXT, product_id TEXT, action TEXT, status TEXT, created_at TEXT)"))

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

class SimulationRequest(BaseModel):
    product_id: str
    new_price: float = Field(gt=0)
    days: int = Field(default=7, ge=1, le=30)

class ApprovalRequest(BaseModel):
    product_id: str
    action: str = Field(min_length=1, max_length=240)

@app.get("/api/health")
def health():
    return {"status": "ok", "llm_configured": bool(os.getenv("GROQ_API_KEY")), "voice_mode": "browser-web-speech-with-local-upgrades"}

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

@app.get("/api/sellers/{seller_id}/conversations")
def conversations(seller_id: str):
    if not get_seller(seller_id): raise HTTPException(404, "Seller not found")
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, role, content, created_at FROM conversations WHERE seller_id = :seller_id ORDER BY created_at"), {"seller_id": seller_id}).mappings().all()
    return [dict(row) for row in rows]

@app.get("/api/sellers/{seller_id}/growth-radar")
def growth_radar(seller_id: str):
    seller = get_seller(seller_id)
    if not seller: raise HTTPException(404, "Seller not found")
    metrics = analytics_for(seller)
    return {"signals": [
        {"id": "revenue", "label": "Revenue momentum", "value": metrics["sales_change"], "unit": "%", "direction": "up" if metrics["sales_change"] >= 0 else "down", "priority": "high" if metrics["sales_change"] < -10 else "medium"},
        {"id": "conversion", "label": "Conversion movement", "value": metrics["changes"]["conversion"], "unit": " pts", "direction": "up" if metrics["changes"]["conversion"] >= 0 else "down", "priority": "high" if metrics["changes"]["conversion"] < -1 else "low"},
        {"id": "competition", "label": "Competitor price gap", "value": metrics["avg_competitor_gap"], "unit": "%", "direction": "up" if metrics["avg_competitor_gap"] > 0 else "down", "priority": "medium"},
        {"id": "inventory", "label": "Inventory pressure", "value": seller["products"][0]["inventory"], "unit": " units", "direction": "down", "priority": "high" if seller["products"][0]["inventory"] < 20 else "low"},
    ]}

@app.get("/api/sellers/{seller_id}/approvals")
def approvals(seller_id: str):
    if not get_seller(seller_id): raise HTTPException(404, "Seller not found")
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, product_id, action, status, created_at FROM approvals WHERE seller_id = :seller_id ORDER BY created_at DESC"), {"seller_id": seller_id}).mappings().all()
    return [dict(row) for row in rows]

@app.post("/api/sellers/{seller_id}/approvals")
def create_approval(seller_id: str, request: ApprovalRequest):
    seller = get_seller(seller_id)
    if not seller or not any(product["id"] == request.product_id for product in seller["products"]): raise HTTPException(404, "Seller or product not found")
    approval = {"id": str(uuid.uuid4()), "seller_id": seller_id, "product_id": request.product_id, "action": request.action, "status": "pending", "created_at": datetime.utcnow().isoformat()}
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO approvals VALUES (:id,:seller_id,:product_id,:action,:status,:created_at)"), approval)
    return approval

@app.patch("/api/approvals/{approval_id}")
def update_approval(approval_id: str, payload: dict):
    status = payload.get("status")
    if status not in ("approved", "rejected"): raise HTTPException(400, "Status must be approved or rejected")
    with engine.begin() as conn:
        result = conn.execute(text("UPDATE approvals SET status = :status WHERE id = :id"), {"id": approval_id, "status": status})
    if result.rowcount == 0: raise HTTPException(404, "Approval not found")
    return {"id": approval_id, "status": status}

@app.post("/api/sellers/{seller_id}/simulate")
def simulate(seller_id: str, request: SimulationRequest):
    seller = get_seller(seller_id)
    product = next((item for item in seller["products"] if item["id"] == request.product_id), None) if seller else None
    if not seller or not product: raise HTTPException(404, "Seller or product not found")
    return simulate_price_change(product, request.new_price, request.days)

@app.get("/api/sellers/{seller_id}/growth-memory")
def growth_memory(seller_id: str):
    if not get_seller(seller_id): raise HTTPException(404, "Seller not found")
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id, role, content, created_at FROM conversations WHERE seller_id = :seller_id ORDER BY created_at DESC LIMIT 20"), {"seller_id": seller_id}).mappings().all()
    return {"entries": [dict(row) for row in rows]}

def _tool_definitions():
    return [
        {"type": "function", "function": {"name": "get_sales_trend", "description": "Get observed revenue and order trend for the seller or product.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_funnel", "description": "Get observed impressions, views, CTR, conversion, and returns to diagnose traffic versus conversion.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_competitor_prices", "description": "Get the seller price, competitor price, and price gap for products.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_inventory", "description": "Get observed stock, velocity, ratings, and returns to diagnose availability and quality.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "simulate_price_change", "description": "Project orders, revenue, conversion, and margin for a price change. This is directional, not a guarantee.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "new_price": {"type": "number"}, "days": {"type": "integer"}}, "required": ["product_id", "new_price"]}}},
        {"type": "function", "function": {"name": "record_approval", "description": "Record an approved proposed action only when the seller explicitly says yes, approve, or go ahead.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "action": {"type": "string"}}, "required": ["product_id", "action"]}}},
    ]


def _tool_result(name: str, arguments: dict, seller: dict, seller_id: str):
    product = next((item for item in seller["products"] if item["id"] == arguments.get("product_id")), seller["products"][0])
    if name == "get_sales_trend": return sales_trend_for(seller, product)
    if name == "get_funnel": return funnel_for(seller, product)
    if name == "get_competitor_prices": return price_comparison_for(seller, product)
    if name == "get_inventory": return inventory_for(seller, product)
    if name == "simulate_price_change": return simulate_price_change(product, float(arguments["new_price"]), int(arguments.get("days", 7)))
    if name == "record_approval":
        approval = {"id": str(uuid.uuid4()), "seller_id": seller_id, "product_id": arguments["product_id"], "action": arguments["action"], "status": "approved", "created_at": datetime.utcnow().isoformat()}
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO approvals VALUES (:id,:seller_id,:product_id,:action,:status,:created_at)"), approval)
        return approval
    raise ValueError(f"Unknown tool: {name}")


def _grounded_fallback(request: ChatRequest, seller: dict):
    product = seller["products"][0]
    message = request.message.lower()
    if not request.history and not any(word in message for word in (product["name"].lower(), seller["category"].lower())):
        return "Which product or category dropped? I will check traffic, conversion, price, stock, ratings, and returns in that order."
    funnel = funnel_for(seller, product)
    pricing = price_comparison_for(seller, product)
    inventory = inventory_for(seller, product)
    return (f"For {product['name']}, impressions are {funnel['impressions']} and conversion fell from "
            f"{product['previous_conversion']}% to {product['conversion']}%. The price is {pricing['gap_percent']}% "
            f"above the competitor and only {inventory['inventory']} units remain. Traffic looks stable, so I rank "
            f"conversion and price ahead of stock. Should I propose {product['name']} at ₹899 for 7 days and restocking 40 units?")


def _fallback_approval(request: ChatRequest, seller: dict):
    previous_assistant = next((turn.get("content", "").lower() for turn in reversed(request.history) if turn.get("role") == "assistant"), "")
    explicit_yes = any(phrase in request.message.lower() for phrase in ("yes", "approve", "approved", "go ahead", "do it"))
    if not explicit_yes or "restocking 40 units" not in previous_assistant:
        return None
    product = seller["products"][0]
    approval = {"id": str(uuid.uuid4()), "seller_id": request.seller_id, "product_id": product["id"], "action": f"Cut {product['name']} to ₹899 for 7 days and restock 40 units", "status": "approved", "created_at": datetime.utcnow().isoformat()}
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO approvals VALUES (:id,:seller_id,:product_id,:action,:status,:created_at)"), approval)
    return approval


@app.post("/api/chat")
def chat(request: ChatRequest):
    seller = get_seller(request.seller_id)
    if not seller: raise HTTPException(404, "Seller not found")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO conversations VALUES (:id,:seller_id,'user',:content,:created_at)"), {"id": str(uuid.uuid4()), "seller_id": request.seller_id, "content": request.message, "created_at": datetime.utcnow().isoformat()})
    context = analytics_for(seller)
    response = _grounded_fallback(request, seller)
    source = "grounded-fallback"
    fallback_approval = _fallback_approval(request, seller) if not (OpenAI and os.getenv("GROQ_API_KEY")) else None
    if fallback_approval:
        response = f"Approved and recorded. I will cut {seller['products'][0]['name']} to ₹899 for 7 days, restock 40 units, and check back in 3 days."
        source = "grounded-fallback-approval"
    if OpenAI and os.getenv("GROQ_API_KEY"):
        client = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1", timeout=20, max_retries=2)
        system = "You are Snapdeal Virtual KAM. Diagnose one product or category at a time. Start by asking which product or category dropped if unclear. Check hypotheses in this order: traffic, conversion, price, stock, ratings, returns. You MUST use tools for numbers and cite their returned facts. Rank causes with evidence, separate facts from hypotheses, and never invent or guarantee numbers. Propose an action plan for seller approval. Call record_approval only after explicit approval in the current conversation. Be concise and ask one question at a time."
        messages = [{"role": "system", "content": system}]
        for turn in request.history[-20:]:
            if turn.get("role") in ("user", "assistant") and turn.get("content"):
                messages.append({"role": turn["role"], "content": turn["content"]})
        facts = {"seller": seller["name"], "category": seller["category"], "analytics_context": context, "user_message": request.message}
        messages.append({"role": "user", "content": json.dumps(facts)})
        try:
            for _ in range(4):
                completion = client.chat.completions.create(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"), messages=messages, tools=_tool_definitions(), tool_choice="auto", temperature=0.2)
                assistant = completion.choices[0].message
                messages.append(assistant.model_dump(exclude_none=True))
                if not assistant.tool_calls:
                    response = assistant.content or response
                    break
                for tool_call in assistant.tool_calls:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    result = _tool_result(tool_call.function.name, arguments, seller, request.seller_id)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_call.function.name, "content": json.dumps(result)})
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

