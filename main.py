from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pathlib import Path
from openai import OpenAI
import os
import json
import re
import time
import random
import asyncio

from db import (
    init_db,
    create_session,
    save_message,
    get_messages,
    save_dashboard,
    clear_traceability,
    save_traceability,
    get_traceability
)

# -----------------------------------
# Load Environment
# -----------------------------------
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# -----------------------------------
# FastAPI Setup
# -----------------------------------
app = FastAPI()
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------
# Simulation State
# -----------------------------------
vehicle_state = {
    "vehicle_speed": 0.0,
    "engine_rpm": 800.0,
    "battery_soc": 100.0,
    "coolant_temperature": 70.0,
    "fuel_efficiency": 8.0,
    "brake_status": False,
    "vehicle_latitude": 12.9716,
    "vehicle_longitude": 77.5946,
    "media_track": "No Track",
    "media_status": "Stopped"
}

last_update_time = time.time()

# -----------------------------------
# Signal Registry
# -----------------------------------
SIGNAL_REGISTRY = {
    "vehicle_speed": {"unit": "km/h"},
    "engine_rpm": {"unit": "RPM"},
    "battery_soc": {"unit": "%"},
    "coolant_temperature": {"unit": "°C"},
    "fuel_efficiency": {"unit": "L/100km"},
    "brake_status": {"unit": "boolean"},
    "vehicle_latitude": {"unit": "deg"},
    "vehicle_longitude": {"unit": "deg"},
    "media_track": {"unit": "text"},
    "media_status": {"unit": "text"}
}

APPROVED_PRIMITIVES = {
    "circular_meter",
    "panel_container",
    "list_container",
    "map_container",
    "status_indicator",
    "linear_bar"
}

REPRESENTATION_MAP = {
    "rectangular_panel": "panel_container",
    "info_panel": "panel_container",
    "card": "panel_container",
    "gauge": "circular_meter",
    "dial": "circular_meter",
    "meter": "circular_meter",
    "speedometer": "circular_meter",
    "tachometer": "circular_meter",
    "analog_gauge": "circular_meter",
    "map_view": "map_container",
    "list_view": "list_container",
    "progress_bar": "linear_bar"
}

# -----------------------------------
# Simulation Update
# -----------------------------------
def update_vehicle_state():
    global last_update_time
    current_time = time.time()
    dt = current_time - last_update_time
    last_update_time = current_time

    vehicle_state["vehicle_speed"] += 10 * dt
    if vehicle_state["vehicle_speed"] > 180:
        vehicle_state["vehicle_speed"] = 0

    vehicle_state["engine_rpm"] = 800 + vehicle_state["vehicle_speed"] * 30

    vehicle_state["battery_soc"] -= 0.02 * dt
    if vehicle_state["battery_soc"] < 0:
        vehicle_state["battery_soc"] = 100

    vehicle_state["coolant_temperature"] = 70 + (vehicle_state["engine_rpm"] / 100)
    vehicle_state["fuel_efficiency"] = 8 + random.uniform(-0.5, 0.5)
    vehicle_state["brake_status"] = random.random() < 0.05
    vehicle_state["vehicle_latitude"] += 0.00001 * dt
    vehicle_state["vehicle_longitude"] += 0.00001 * dt
    # Demo music simulation
    vehicle_state["media_track"] = f"Track {random.randint(1,5)}"
    vehicle_state["media_status"] = random.choice(["Playing", "Paused"])

# -----------------------------------
# Normalize Schema
# -----------------------------------
def normalize_schema(schema: dict) -> dict:
    for widget in schema.get("widgets", []):
        rep = widget.get("representation")

        if rep in REPRESENTATION_MAP:
            widget["representation"] = REPRESENTATION_MAP[rep]

        if widget.get("representation") not in APPROVED_PRIMITIVES:
            widget["representation"] = "panel_container"

    return schema

# -----------------------------------
# Request Models
# -----------------------------------
class ChatRequest(BaseModel):
    session_id: str
    message: str

class FinalizeRequest(BaseModel):
    session_id: str

# -----------------------------------
# CHAT
# -----------------------------------
@app.post("/chat")
def chat(request: ChatRequest):

    create_session(request.session_id)
    save_message(request.session_id, "user", request.message)

    history = get_messages(request.session_id)

    history.insert(0, {
        "role": "system",
        "content": """
You are an Automotive Requirement Engineering Assistant.
Ask clarification questions.
Do NOT generate final dashboard schema yet.
"""
    })

    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=history,
        temperature=0.4
    )

    reply = completion.choices[0].message.content.strip()
    save_message(request.session_id, "assistant", reply)

    return {"reply": reply}

# -----------------------------------
# FINALIZE
# -----------------------------------
@app.post("/finalize")
def finalize(request: FinalizeRequest):

    history = get_messages(request.session_id)

    if not history:
        return {"error": "Invalid session"}

    schema_prompt = f"""
You are an Automotive HMI Design Engineer.

Follow professional instrument cluster conventions.
Generate ONLY widgets explicitly requested in the current conversation.
Do NOT add additional signals that were not mentioned.

Representation rules:
- vehicle_speed → circular_meter
- engine_rpm → circular_meter
- battery_soc → circular_meter
- fuel_efficiency → linear_bar
- coolant_temperature → linear_bar
- brake_status → status_indicator
- vehicle_latitude + vehicle_longitude → map_container
- media_track → panel_container
- media_status → panel_container

VALID SIGNALS:
{list(SIGNAL_REGISTRY.keys())}

STRICT JSON ONLY:

{{
  "layout": {{
    "rows": integer,
    "columns": integer
  }},
  "widgets": [
    {{
      "id": "unique_id",
      "representation": "circular_meter | panel_container | list_container | map_container | status_indicator | linear_bar",
      "title": "Widget Title",
      "signal_binding": "valid_signal",
      "refresh_rate_ms": integer,
      "position": integer,
      "alert_condition": {{
          "operator": "< | > | <= | >=",
          "threshold": number
      }}
    }}
  ]
}}

Rules:
- No explanation.
- No markdown.
- Only valid JSON.
"""

    messages = history + [
        {"role": "system", "content": schema_prompt}
    ]

    completion = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0
    )

    output = completion.choices[0].message.content.strip()

    try:
        cleaned = re.sub(r"```json|```", "", output).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found")

        parsed = json.loads(match.group(0))

        # Validate + Inject units
        for widget in parsed.get("widgets", []):
            signal = widget.get("signal_binding")

            if signal not in SIGNAL_REGISTRY:
                widget["signal_binding"] = "vehicle_speed"

            widget["unit"] = SIGNAL_REGISTRY[widget["signal_binding"]]["unit"]

        normalized = normalize_schema(parsed)

        # Save dashboard
        save_dashboard(request.session_id, normalized)

        # Save traceability
        clear_traceability(request.session_id)

        counter = 1
        for widget in normalized.get("widgets", []):
            save_traceability(
                request.session_id,
                f"REQ-{counter:03d}",
                f"Display {widget.get('title')}",
                widget.get("signal_binding"),
                widget.get("id"),
                "VERIFIED"
            )
            counter += 1

        return {"dashboard_schema": normalized}

    except Exception as e:
        return {
            "error": "Failed to parse JSON",
            "details": str(e),
            "raw_output": output
        }

# -----------------------------------
# WebSocket Telemetry
# -----------------------------------
@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        requested_signals = data.get("signals", [])

        while True:
            update_vehicle_state()

            response = {
                sig: round(vehicle_state[sig], 2)
                for sig in requested_signals
                if sig in vehicle_state
            }

            await websocket.send_json(response)
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        pass

# -----------------------------------
# TRACEABILITY
# -----------------------------------
@app.get("/traceability")
def trace(session_id: str):

    matrix = get_traceability(session_id)

    if not matrix:
        return {"error": "No traceability data for this session"}

    return {
        "traceability_matrix": matrix,
        "coverage_summary": {
            "total_requirements": len(matrix),
            "verified": len(matrix),
            "failed": 0
        }
    }