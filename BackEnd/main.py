from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from pathlib import Path
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


class ExperimentPayload(BaseModel):
    participant_id: str
    session_id: str
    created_at: str
    baseline: Dict[str, Any]
    tasks: Dict[str, Any]
    raw_trials: List[Dict[str, Any]]
    gaze: Optional[Dict[str, Any]] = None


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def recommend_ui(payload: ExperimentPayload) -> str:
    baseline = payload.baseline or {}
    task1 = payload.tasks.get("task1", {})
    task2 = payload.tasks.get("task2", {})

    guided_score = 0
    reduced_score = 0
    standard_score = 0

    confidence = baseline.get("digital_confidence", "")
    page_style = baseline.get("page_style", "")
    guidance_need = baseline.get("guidance_need", "")
    distraction = baseline.get("screen_distraction", "")
    dense_content = baseline.get("dense_content_tolerance", "")
    content_format = baseline.get("content_format", "")

    if confidence in ["Very low", "Low"]:
        guided_score += 2
    elif confidence in ["High", "Very high"]:
        standard_score += 2
    else:
        standard_score += 1

    if page_style == "Step-by-step guidance":
        guided_score += 2
    elif page_style == "Simple page with fewer distractions":
        reduced_score += 2
    elif page_style in ["Clear sections and headings", "Full detailed text"]:
        standard_score += 2
    elif page_style == "Visual highlights and summaries":
        standard_score += 1
        guided_score += 1

    if guidance_need in ["Often", "Very often"]:
        guided_score += 2
    elif guidance_need in ["Never", "Rarely"]:
        standard_score += 1
    else:
        guided_score += 1

    if distraction in ["Easily", "Very easily"]:
        reduced_score += 3
    elif distraction in ["Not at all", "Slightly"]:
        standard_score += 1
    else:
        reduced_score += 1

    if dense_content in ["Very uncomfortable", "Uncomfortable"]:
        reduced_score += 2
    elif dense_content in ["Comfortable", "Very comfortable"]:
        standard_score += 2

    if content_format == "Written text":
        standard_score += 1
    elif content_format == "Visual summaries / infographics":
        standard_score += 1
        reduced_score += 1
    elif content_format in ["Audio / video explanation", "Interactive activities"]:
        guided_score += 1

    total_errors = int(task1.get("errors", 0)) + int(task2.get("errors", 0))
    total_hesitation = int(task1.get("hesitation", 0)) + int(task2.get("hesitation", 0))
    total_backtracking = int(task1.get("backtracking", 0)) + int(task2.get("backtracking", 0))
    total_changes = int(task1.get("answer_changes", 0)) + int(task2.get("answer_changes", 0))

    if total_errors >= 2:
        guided_score += 2
    if total_hesitation >= 1:
        guided_score += 2
    if total_backtracking >= 1:
        reduced_score += 2
    if total_changes >= 2:
        guided_score += 1

    gaze = payload.gaze or {}
    task1_gaze = ((gaze.get("task1_reading") or {}).get("metrics") or {})
    task2_gaze = ((gaze.get("task2_info") or {}).get("metrics") or {})

    valid_gaze_metrics = [
        g for g in [task1_gaze, task2_gaze]
        if int(safe_float(g.get("total_samples"), 0)) > 0
    ]

    if valid_gaze_metrics:
        low_focus_runs = sum(
            1 for g in valid_gaze_metrics
            if g.get("on_target_ratio") is not None and safe_float(g.get("on_target_ratio"), 1.0) < 0.35
        )

        delayed_fixation_runs = sum(
            1 for g in valid_gaze_metrics
            if g.get("first_fixation_latency_ms") is not None and safe_float(g.get("first_fixation_latency_ms"), 0.0) > 2500
        )

        if low_focus_runs >= 1:
            reduced_score += 1

        if delayed_fixation_runs >= 1:
            guided_score += 1

    if reduced_score >= guided_score and reduced_score >= standard_score:
        return "reduced-distraction"
    if guided_score >= standard_score:
        return "guided"
    return "standard"


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/api/experiment")
def save_experiment(payload: ExperimentPayload):
    participant_dir = DATA_DIR / payload.participant_id
    participant_dir.mkdir(exist_ok=True)

    session_file = participant_dir / f"{payload.session_id}.json"
    session_file.write_text(
        json.dumps(payload.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    recommended_ui = recommend_ui(payload)

    gaze = payload.gaze or {}
    task1_samples = int((((gaze.get("task1_reading") or {}).get("metrics") or {}).get("total_samples") or 0))
    task2_samples = int((((gaze.get("task2_info") or {}).get("metrics") or {}).get("total_samples") or 0))

    return {
        "status": "saved",
        "participant_id": payload.participant_id,
        "session_id": payload.session_id,
        "recommended_ui": recommended_ui,
        "gaze_samples": {
            "task1": task1_samples,
            "task2": task2_samples
        }
    }