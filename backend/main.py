import os
import json
import uuid
import logging
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
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

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    database_path = Path("/tmp/virtual_kam.db") if os.getenv("VERCEL") else Path(__file__).parent / "virtual_kam.db"
    DATABASE_URL = f"sqlite:///{database_path}"
engine_options = {"connect_args": {"check_same_thread": False}} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, **engine_options)
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, seller_id TEXT, role TEXT, content TEXT, created_at TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, seller_id TEXT, product_id TEXT, action TEXT, status TEXT, created_at TEXT)"))
    conn.execute(text("CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, seller_id TEXT, type TEXT, params TEXT, status TEXT, created_at TEXT, executed_at TEXT, estimated_impact TEXT, measured_impact TEXT, applied_at TEXT)"))
    action_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(actions)"))}
    for column in ("type", "params", "executed_at", "estimated_impact", "measured_impact", "applied_at"):
        if column not in action_columns:
            conn.execute(text(f"ALTER TABLE actions ADD COLUMN {column} TEXT"))

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
    language: str = Field(default="en-IN", pattern=r"^(en-IN|hi-IN)$")

class SimulationRequest(BaseModel):
    product_id: str
    new_price: float = Field(gt=0)
    days: int = Field(default=7, ge=1, le=30)

class ApprovalRequest(BaseModel):
    product_id: str
    action: str = Field(min_length=1, max_length=240)

class AdvanceRequest(BaseModel):
    seller_id: str
    days: int = Field(default=3, ge=1, le=30)

@app.get("/api/health")
def health():
    return {"status": "ok", "llm_configured": bool(os.getenv("GROQ_API_KEY")), "voice_mode": "sarvam" if os.getenv("SARVAM_API_KEY") else "browser-fallback"}

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

@app.get("/api/sellers/{seller_id}/radar")
def seller_radar(seller_id: str):
    seller = get_seller(seller_id)
    if not seller: raise HTTPException(404, "Seller not found")
    metrics = analytics_for(seller)
    product = seller["products"][0]
    decline = abs(metrics["sales_change"])
    with engine.begin() as conn:
        last = conn.execute(text("SELECT measured_impact FROM actions WHERE seller_id = :seller_id AND status = 'executed' AND measured_impact IS NOT NULL ORDER BY executed_at DESC LIMIT 1"), {"seller_id": seller_id}).scalar()
    callback = ""
    if last:
        outcome = json.loads(last)
        callback = f" Last time, the simulated 3-day outcome changed orders by {outcome['measured_impact']['orders_change_percent']}%."
    return {"seller_id": seller_id, "top_issue": product["name"], "decline_percent": decline,
        "opening_line": f"I noticed {product['name']}'s sales dropped {decline:.1f}% this week.{callback} I have checked the signals and want to walk you through the next action."}

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

def _action_row(row):
    result = dict(row)
    for key in ("params", "estimated_impact", "measured_impact"):
        result[key] = json.loads(result[key]) if result.get(key) else None
    return result

@app.get("/api/sellers/{seller_id}/actions")
def seller_actions(seller_id: str):
    if not get_seller(seller_id): raise HTTPException(404, "Seller not found")
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT * FROM actions WHERE seller_id = :seller_id ORDER BY created_at DESC"), {"seller_id": seller_id}).mappings().all()
    return [_action_row(row) for row in rows]

def _tool_definitions():
    return [
        {"type": "function", "function": {"name": "get_sales_trend", "description": "Get observed revenue and order trend for the seller or product.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_funnel", "description": "Get observed impressions, views, CTR, conversion, and returns to diagnose traffic versus conversion.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_competitor_prices", "description": "Get the seller price, competitor price, and price gap for products.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "get_inventory", "description": "Get observed stock, velocity, ratings, and returns to diagnose availability and quality.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}}, "required": []}}},
        {"type": "function", "function": {"name": "simulate_price_change", "description": "Project orders, revenue, conversion, and margin for a price change. This is directional, not a guarantee.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "new_price": {"type": "number"}, "days": {"type": "integer"}}, "required": ["product_id", "new_price"]}}},
        {"type": "function", "function": {"name": "propose_action", "description": "Create a concrete, measurable proposed action for seller approval. Never approve it.", "parameters": {"type": "object", "properties": {"product_id": {"type": "string"}, "type": {"type": "string"}, "params": {"type": "object"}, "estimated_impact": {"type": "object"}}, "required": ["product_id", "type", "params", "estimated_impact"]}}},
        {"type": "function", "function": {"name": "confirm_action", "description": "Approve and execute a pending action only after the latest seller message is an explicit yes, approve, or go ahead.", "parameters": {"type": "object", "properties": {"action_id": {"type": "string"}}, "required": ["action_id"]}}},
    ]


APPROVAL_PHRASES = ("yes", "yeah", "approve", "approved", "go ahead", "do it", "haan", "ha", "kar do", "theek hai")
NEGATION_WORDS = ("no", "not", "don't", "nahi", "mat")


def is_explicit_approval(message: str) -> bool:
    normalized = message.lower()
    if any(re.search(rf"\b{re.escape(word)}\b", normalized) for word in NEGATION_WORDS):
        return False
    return any(re.search(rf"\b{re.escape(phrase)}\b", normalized) for phrase in APPROVAL_PHRASES)


def _trace_item(tool: str, arguments: dict, result: dict):
    product = result.get("product", "the product")
    if tool == "get_funnel":
        hypothesis = "Traffic is the cause"
        verdict = "flagged" if abs(result.get("impressions_change_percent", 0)) > 5 else "ruled out"
        summary = f"{result.get('impressions')} impressions versus {result.get('previous_impressions')} previously; conversion {result.get('previous_conversion_percent')}% to {result.get('conversion_percent')}%"
    elif tool == "get_competitor_prices":
        hypothesis = "Price is the cause"
        verdict = "flagged" if result.get("gap_percent", 0) > 0 else "ruled out"
        summary = f"Seller {result.get('seller_price')} versus competitor {result.get('competitor_price')} ({result.get('gap_percent')}% gap)"
    elif tool == "get_inventory":
        hypothesis = "Inventory, ratings, or returns are the cause"
        verdict = "flagged" if result.get("days_of_cover") is not None and result["days_of_cover"] < 7 or result.get("rating", 5) < 4 or result.get("returns_percent", 0) >= 10 else "ruled out"
        summary = f"{result.get('inventory')} units; {result.get('days_of_cover')} days of cover; rating {result.get('rating')}; returns {result.get('returns_percent')}%"
    elif tool == "get_sales_trend":
        hypothesis = "The sales trend confirms a meaningful drop"
        verdict = "flagged" if result.get("sales_change_percent", 0) < 0 else "ruled out"
        summary = f"14-day revenue trend changed {result.get('sales_change_percent')}%"
    elif tool == "simulate_price_change":
        hypothesis = "The proposed price can recover conversion"
        verdict = "flagged" if result.get("projected_orders", 0) >= 0 else "ruled out"
        summary = f"{product}: {result.get('projected_orders')} projected orders in {result.get('days')} days at {result.get('new_price')}"
    else:
        hypothesis = "The proposed action is ready for seller approval"
        verdict = "flagged" if not result.get("error") else "ruled out"
        summary = "Action proposed" if not result.get("error") else result["error"]
    return {"tool": tool, "args": arguments, "result_summary": summary, "hypothesis": hypothesis, "verdict": verdict}


def _record_trace(trace: list, tool: str, arguments: dict, result: dict):
    trace.append(_trace_item(tool, arguments, result))
    if tool == "get_funnel":
        conversion_drop = result.get("previous_conversion_percent", 0) - result.get("conversion_percent", 0)
        trace.append({"tool": tool, "args": arguments, "result_summary": f"Conversion declined {round(conversion_drop, 2)} points", "hypothesis": "Conversion is the cause", "verdict": "flagged" if conversion_drop > 0 else "ruled out"})
    elif tool == "get_inventory":
        quality_issue = result.get("rating", 5) < 4 or result.get("returns_percent", 0) >= 10
        trace.append({"tool": tool, "args": arguments, "result_summary": f"Rating {result.get('rating')}; returns {result.get('returns_percent')}%", "hypothesis": "Ratings or returns are the cause", "verdict": "flagged" if quality_issue else "ruled out"})


def _confirm_action(seller_id: str, action_id: str):
    with engine.begin() as conn:
        latest = conn.execute(text("SELECT id FROM actions WHERE seller_id = :seller_id AND status = 'proposed' ORDER BY created_at DESC LIMIT 1"), {"seller_id": seller_id}).scalar()
        if latest != action_id:
            return {"error": "Only the most recent pending action can be approved"}
        row = conn.execute(text("SELECT * FROM actions WHERE id = :id AND seller_id = :seller_id AND status = 'proposed'"), {"id": action_id, "seller_id": seller_id}).mappings().first()
        if not row:
            return {"error": "No pending action found"}
        action = dict(row)
        executed_at = datetime.utcnow().isoformat()
        conn.execute(text("UPDATE actions SET status = 'executed', executed_at = :executed_at WHERE id = :id"), {"id": action_id, "executed_at": executed_at})
        params = json.loads(action["params"])
        approval = {"id": str(uuid.uuid4()), "seller_id": seller_id, "product_id": params["product_id"], "action": action["type"], "status": "approved", "created_at": executed_at}
        conn.execute(text("INSERT INTO approvals VALUES (:id,:seller_id,:product_id,:action,:status,:created_at)"), approval)
    return {**_action_row(action), "status": "executed", "executed_at": executed_at, "approval": "seller-approved", "execution": "mock"}


def _tool_result(name: str, arguments: dict, seller: dict, seller_id: str, trace: list | None = None):
    product = next((item for item in seller["products"] if item["id"] == arguments.get("product_id")), seller["products"][0])
    if name == "get_sales_trend": result = sales_trend_for(seller, product)
    elif name == "get_funnel": result = funnel_for(seller, product)
    elif name == "get_competitor_prices": result = price_comparison_for(seller, product)
    elif name == "get_inventory": result = inventory_for(seller, product)
    elif name == "simulate_price_change": result = simulate_price_change(product, float(arguments["new_price"]), int(arguments.get("days", 7)))
    elif name == "propose_action":
        params = {"product_id": arguments["product_id"], **arguments["params"]}
        with engine.begin() as conn:
            existing = conn.execute(text("SELECT * FROM actions WHERE seller_id = :seller_id AND status = 'proposed' AND json_extract(params, '$.product_id') = :product_id ORDER BY created_at DESC LIMIT 1"), {"seller_id": seller_id, "product_id": arguments["product_id"]}).mappings().first()
            if existing:
                result = _action_row(existing)
            else:
                action = {"id": str(uuid.uuid4()), "seller_id": seller_id, "type": arguments["type"], "params": json.dumps(params), "status": "proposed", "created_at": datetime.utcnow().isoformat(), "executed_at": None, "estimated_impact": json.dumps(arguments["estimated_impact"]), "measured_impact": None, "applied_at": None}
                conn.execute(text("INSERT INTO actions (id,seller_id,type,params,status,created_at,executed_at,estimated_impact,measured_impact,applied_at) VALUES (:id,:seller_id,:type,:params,:status,:created_at,:executed_at,:estimated_impact,:measured_impact,:applied_at)"), action)
                result = _action_row(action)
    elif name == "confirm_action":
        result = _confirm_action(seller_id, arguments["action_id"])
    else:
        raise ValueError(f"Unknown tool: {name}")
    if trace is not None:
        _record_trace(trace, name, arguments, result)
    return result

def _grounded_fallback(request: ChatRequest, seller: dict, trace: list):
    product = seller["products"][0]
    message = request.message.lower()
    if not request.history and not any(word in message for word in (product["name"].lower(), seller["category"].lower())):
        return "Which product or category dropped? I will check traffic, conversion, price, stock, ratings, and returns in that order."
    with engine.begin() as conn:
        latest = conn.execute(text("SELECT * FROM actions WHERE seller_id = :seller_id ORDER BY created_at DESC LIMIT 1"), {"seller_id": seller["id"]}).mappings().first()
    if latest and latest["status"] == "executed" and latest["measured_impact"]:
        outcome = json.loads(latest["measured_impact"])
        return f"The approved mock action is executed. Its simulated 3-day outcome changed orders by {outcome['measured_impact']['orders_change_percent']}% and conversion moved from {outcome['measured_impact']['conversion_before']}% to {outcome['measured_impact']['conversion_after']}%."
    if latest and latest["status"] == "proposed":
        params = json.loads(latest["params"])
        return f"The proposal is still pending approval: {params['new_price']} rupees for {params['days']} days and {params['restock_units']} restock units. Do you approve?"
    funnel = _tool_result("get_funnel", {"product_id": product["id"]}, seller, seller["id"], trace)
    pricing = _tool_result("get_competitor_prices", {"product_id": product["id"]}, seller, seller["id"], trace)
    inventory = _tool_result("get_inventory", {"product_id": product["id"]}, seller, seller["id"], trace)
    price = pricing["competitor_price"]
    days = 7
    restock = max(0, round(product["velocity"] * 21 - product["inventory"]))
    estimate = _tool_result("simulate_price_change", {"product_id": product["id"], "new_price": price, "days": days}, seller, seller["id"], trace)
    _tool_result("propose_action", {"product_id": product["id"], "type": "price_and_restock", "params": {"new_price": price, "days": days, "restock_units": restock}, "estimated_impact": estimate}, seller, seller["id"], trace)
    return (f"For {product['name']}, impressions changed {funnel['impressions_change_percent']}% and conversion fell from "
            f"{funnel['previous_conversion_percent']}% to {funnel['conversion_percent']}%. The price is {pricing['gap_percent']}% "
            f"above the competitor and there are {inventory['days_of_cover']} days of cover. I propose {price} rupees for {days} days "
            f"and restocking {restock} units. The directional estimate is {estimate['projected_orders']} orders and {estimate['projected_conversion']}% conversion. Do you approve?")


def _fallback_approval(request: ChatRequest, seller: dict):
    if not is_explicit_approval(request.message):
        return None
    with engine.begin() as conn:
        action_id = conn.execute(text("SELECT id FROM actions WHERE seller_id = :seller_id AND status = 'proposed' ORDER BY created_at DESC LIMIT 1"), {"seller_id": request.seller_id}).scalar()
    return _confirm_action(request.seller_id, action_id) if action_id else None

@app.post("/api/chat")
def chat(request: ChatRequest):
    seller = get_seller(request.seller_id)
    if not seller: raise HTTPException(404, "Seller not found")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO conversations VALUES (:id,:seller_id,'user',:content,:created_at)"), {"id": str(uuid.uuid4()), "seller_id": request.seller_id, "content": request.message, "created_at": datetime.utcnow().isoformat()})
    context = analytics_for(seller)
    trace = []
    response = "I am checking the seller signals now."
    source = "grounded-fallback"
    using_groq = bool(OpenAI and os.getenv("GROQ_API_KEY"))
    if not using_groq:
        if is_explicit_approval(request.message):
            approval = _fallback_approval(request, seller)
            if approval:
                params = approval["params"]
                response = f"Approved. I will set {params['new_price']} rupees for {params['days']} days and restock {params['restock_units']} units. This is a mock marketplace action. I will check back in 3 days."
                source = "grounded-fallback-approval"
                _record_trace(trace, "confirm_action", {"action_id": approval["id"]}, approval)
            else:
                response = "I do not have a pending action to approve yet. I will diagnose the drop first."
        else:
            response = _grounded_fallback(request, seller, trace)
    if OpenAI and os.getenv("GROQ_API_KEY"):
        client = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1", timeout=20, max_retries=2)
        system = "You are Snapdeal Virtual KAM. Own the seller's problem from diagnosis to simulated result. Use tools for every number; never invent figures. Separate observed facts from hypotheses. Check traffic, conversion, price, stock, ratings, and returns. Propose one concrete action, but never approve it yourself. Call confirm_action only when the latest seller message is an explicit approval. Use concise spoken-style replies, no markdown, no emoji, and ask one question at a time."
        if request.language == "hi-IN":
            system += " Reply in simple Hindi using Devanagari or Hinglish, with short spoken sentences."
        messages = [{"role": "system", "content": system}]
        persisted_history = request.history
        if not persisted_history:
            with engine.begin() as conn:
                persisted_history = [dict(row) for row in conn.execute(text("SELECT role, content FROM conversations WHERE seller_id = :seller_id ORDER BY created_at DESC LIMIT 8"), {"seller_id": request.seller_id}).mappings().all()][::-1]
        for turn in persisted_history[-20:]:
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
                    if tool_call.function.name == "confirm_action" and not is_explicit_approval(request.message):
                        result = {"error": "Seller approval is required"}
                        _record_trace(trace, tool_call.function.name, arguments, result)
                    else:
                        result = _tool_result(tool_call.function.name, arguments, seller, request.seller_id, trace)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_call.function.name, "content": json.dumps(result)})
            source = "groq"
        except Exception:
            source = "deterministic-fallback-after-groq-error"
            trace = []
            response = _grounded_fallback(request, seller, trace)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO conversations VALUES (:id,:seller_id,'assistant',:content,:created_at)"), {"id": str(uuid.uuid4()), "seller_id": request.seller_id, "content": response, "created_at": datetime.utcnow().isoformat()})
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT * FROM actions WHERE seller_id = :seller_id ORDER BY created_at DESC"), {"seller_id": request.seller_id}).mappings().all()
    actions = [_action_row(row) for row in rows]
    proposed_action = next((action for action in actions if action["status"] == "proposed"), None)
    return {"response": response, "source": source, "trace": trace, "proposed_action": proposed_action, "actions": actions}

@app.post("/api/simulate/advance")
def advance_simulation(request: AdvanceRequest):
    seller = get_seller(request.seller_id)
    if not seller: raise HTTPException(404, "Seller not found")
    product = deepcopy(seller["products"][0])
    before = {"orders": round(product["orders"] * request.days / 14), "conversion": product["conversion"], "price": product["price"], "inventory": product["inventory"]}
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT * FROM actions WHERE seller_id = :seller_id AND status = 'executed' ORDER BY executed_at ASC"), {"seller_id": request.seller_id}).mappings().all()
        stored = next((json.loads(row["measured_impact"]) for row in reversed(rows) if row["measured_impact"]), None)
    if stored:
        return stored
    assumptions = ["conversion and orders use the shared capped price-elasticity model", "restock affects availability only when baseline cover is below the simulated period", "all values are a simulated 3-day outcome, not a guarantee"]
    applicable = [row for row in rows if json.loads(row["params"]).get("product_id") == product["id"]]
    for row in applicable:
        params = json.loads(row["params"])
        projection = simulate_price_change(product, float(params.get("new_price", product["price"])), request.days)
        available = product["inventory"] + int(params.get("restock_units", 0))
        required = product["velocity"] * request.days
        availability_factor = min(1.0, available / required) if required else 1.0
        product["price"] = float(params.get("new_price", product["price"]))
        product["conversion"] = projection["projected_conversion"]
        product["orders"] = round(projection["projected_orders"] * availability_factor)
        product["inventory"] = available
    product["inventory"] = max(0, product["inventory"] - round(product["velocity"] * request.days))
    after = {"orders": product["orders"], "conversion": product["conversion"], "price": product["price"], "inventory": product["inventory"]}
    measured = {"orders_change_percent": round((after["orders"] - before["orders"]) / before["orders"] * 100, 1), "conversion_before": before["conversion"], "conversion_after": after["conversion"]}
    result = {"seller_id": request.seller_id, "days": request.days, "before": before, "after": after, "measured_impact": measured, "assumptions": assumptions, "callback": f"Simulated 3-day outcome: orders changed {measured['orders_change_percent']}%. Conversion moved from {before['conversion']}% to {after['conversion']}%. Should I extend the price cut and reorder?"}
    with engine.begin() as conn:
        for row in applicable:
            conn.execute(text("UPDATE actions SET measured_impact = :measured, applied_at = :applied_at WHERE id = :id AND measured_impact IS NULL"), {"id": row["id"], "measured": json.dumps(result), "applied_at": datetime.utcnow().isoformat()})
    return result

@app.post("/api/voice/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("audio/"): raise HTTPException(400, "Upload an audio file")
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        return {"text": "", "source": "fallback", "message": "SARVAM_API_KEY is not configured."}
    contents = await file.read()
    if len(contents) > 15 * 1024 * 1024: raise HTTPException(413, "Audio file is too large")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": api_key},
                files={"file": (file.filename or "recording.webm", contents, file.content_type)},
                data={"model": os.getenv("SARVAM_STT_MODEL", "saarika:v2.5"), "language_code": os.getenv("SARVAM_LANGUAGE", "en-IN")},
            )
        if response.is_error:
            logger.error("Sarvam STT failed: status=%s body=%s", response.status_code, response.text)
            return {"text": "", "source": "fallback", "message": f"Sarvam STT failed ({response.status_code}): {response.text[:500]}"}
        return {"text": response.json().get("transcript", "").strip(), "source": "sarvam"}
    except Exception as error:
        logger.exception("Sarvam STT request failed")
        return {"text": "", "source": "fallback", "message": f"Sarvam transcription is unavailable: {error}"}

@app.post("/api/voice/synthesize")
async def synthesize(payload: dict):
    text_value = str(payload.get("text", "")).strip()
    if not text_value: raise HTTPException(400, "Text is required")
    speech_text = clean_text_for_speech(text_value)
    if not speech_text: raise HTTPException(400, "Text has no speakable content")
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        return {"audio_base64": None, "speech_text": speech_text, "source": "fallback", "message": "SARVAM_API_KEY is not configured."}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"api-subscription-key": api_key, "Content-Type": "application/json"},
                json={
                    "inputs": [speech_text],
                    "target_language_code": payload.get("language", os.getenv("SARVAM_LANGUAGE", "en-IN")),
                    "speaker": os.getenv("SARVAM_TTS_SPEAKER", "anushka"),
                    "model": os.getenv("SARVAM_TTS_MODEL", "bulbul:v2"),
                    "pace": 1.0,
                    "speech_sample_rate": 22050,
                    "enable_preprocessing": True,
                },
            )
        if response.is_error:
            logger.error("Sarvam TTS failed: status=%s body=%s", response.status_code, response.text)
            return {"audio_base64": None, "speech_text": speech_text, "source": "fallback", "message": f"Sarvam TTS failed ({response.status_code}): {response.text[:500]}"}
        audio = response.json().get("audios", [None])[0]
        return {"audio_base64": audio, "audio_format": "wav", "speech_text": speech_text, "source": "sarvam"}
    except Exception as error:
        logger.exception("Sarvam TTS request failed")
        return {"audio_base64": None, "speech_text": speech_text, "source": "fallback", "message": f"Sarvam speech synthesis is unavailable: {error}"}

