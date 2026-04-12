from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

app = FastAPI(title="Neuroadaptive UX Backend")


# مهم جدًا: السماح للفرونت المحلي
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://neuroadaptive-ux-mvp.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# تخزين بسيط محلي للتجربة
profiles: Dict[str, Dict[str, Any]] = {}
experiments: List[Dict[str, Any]] = []


class RecommendationPayload(BaseModel):
    participant_id: str
    session_id: str
    created_at: Optional[str] = None
    baseline: Dict[str, Any] = Field(default_factory=dict)
    tasks: Dict[str, Any] = Field(default_factory=dict)
    gaze: Dict[str, Any] = Field(default_factory=dict)
    raw_trials: List[Dict[str, Any]] = Field(default_factory=list)


class ExperimentPayload(BaseModel):
    participant_id: str
    session_id: str
    created_at: Optional[str] = None
    baseline: Dict[str, Any] = Field(default_factory=dict)
    tasks: Dict[str, Any] = Field(default_factory=dict)
    gaze: Dict[str, Any] = Field(default_factory=dict)
    recommendation: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None
    raw_trials: List[Dict[str, Any]] = Field(default_factory=list)


@app.get("/")
def root():
    return {"status": "ok", "message": "Backend is running"}


@app.get("/api/profile/{participant_id}")
def get_profile(participant_id: str):
    profile = profiles.get(participant_id, {})
    return {
        "participant_id": participant_id,
        "sessions_completed": profile.get("sessions_completed", 0),
        "baseline_ready": bool(profile.get("baseline")),
        "baseline": profile.get("baseline", {}),
    }


def choose_ui(baseline: Dict[str, Any]) -> tuple[str, str]:
    page_style = baseline.get("page_style")
    guidance_need = baseline.get("guidance_need")
    screen_distraction = baseline.get("screen_distraction")
    dense_content_tolerance = baseline.get("dense_content_tolerance")

    if page_style == "Step-by-step guidance" or guidance_need in {"Often", "Very often"}:
        return "guided", "baseline_sensitive"

    if (
            page_style == "Simple page with fewer distractions"
            or screen_distraction in {"Easily", "Very easily"}
            or dense_content_tolerance in {"Very uncomfortable", "Uncomfortable"}
    ):
        return "reduced-distraction", "baseline_sensitive"

    return "standard", "rule_based"


@app.post("/api/recommend")
def recommend(payload: RecommendationPayload):
    stored_profile = profiles.get(payload.participant_id, {})
    baseline = payload.baseline or stored_profile.get("baseline", {})

    recommended_ui, source = choose_ui(baseline)

    return {
        "recommended_ui": recommended_ui,
        "source": source,
        "baseline_ready": bool(baseline),
        "sessions_completed_before": stored_profile.get("sessions_completed", 0),
    }


@app.post("/api/experiment")
def save_experiment(payload: ExperimentPayload):
    profile = profiles.setdefault(
        payload.participant_id,
        {
            "sessions_completed": 0,
            "baseline": {},
            "last_recommended_ui": "standard",
        },
    )

    if payload.baseline:
        profile["baseline"] = payload.baseline

    if payload.recommendation and payload.recommendation.get("recommended_ui"):
        profile["last_recommended_ui"] = payload.recommendation["recommended_ui"]

    profile["sessions_completed"] += 1

    if hasattr(payload, "model_dump"):
        record = payload.model_dump()
    else:
        record = payload.dict()

    experiments.append(record)

    return {
        "status": "saved",
        "sessions_completed": profile["sessions_completed"],
        "baseline_ready": bool(profile.get("baseline")),
        "recommended_ui": profile.get("last_recommended_ui", "standard"),
    }
