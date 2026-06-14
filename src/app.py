#!/usr/bin/env python3
"""
FastAPI Server backend for the GeminiJobBot Settings Dashboard.
Manages configurations, handles resume file uploads (PDF, TXT, JSON),
and runs the agent automation pipeline.
"""

import os
import json
import shutil
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Import pipeline executor
from src.orchestrator import run_pipeline

app = FastAPI(title="GeminiJobBot Dashboard API")

PROFILES_DIR = "./profiles"
BLUEPRINT_PATH = "./blueprints/candidate_spec.json"

# Ensure directories exist
os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(os.path.dirname(BLUEPRINT_PATH), exist_ok=True)


class SearchConfigUpdate(BaseModel):
    minimum_salary_usd: int
    experience_years_range: Dict[str, int]
    forbidden_keywords: List[str]


class RunAgentRequest(BaseModel):
    url: str
    cv_path: str


@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """
    Serves the settings panel HTML front-end interface.
    """
    template_path = "./src/templates/dashboard.html"
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Dashboard template html missing.")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/config")
def get_config():
    """
    Reads the current candidate specifications blueprint.
    """
    if not os.path.exists(BLUEPRINT_PATH):
        # Create a default if missing
        default_config = {
            "targeting": {"job_portals": ["LinkedIn", "Indeed"]},
            "filtering_rules": {
                "minimum_salary_usd": 130000,
                "forbidden_keywords": ["Junior", "Internship"],
                "experience_years_range": {"min": 4, "max": 12}
            },
            "dynamic_resume_routing": {
                "rules": [],
                "default_resume_path": "profiles/resume_template.json"
            }
        }
        with open(BLUEPRINT_PATH, "w") as f:
            json.dump(default_config, f, indent=2)
        return default_config

    with open(BLUEPRINT_PATH, "r") as f:
        return json.load(f)


@app.post("/api/config")
def update_config(config: SearchConfigUpdate):
    """
    Updates the search parameters inside candidate_spec.json.
    """
    if not os.path.exists(BLUEPRINT_PATH):
        raise HTTPException(status_code=404, detail="candidate_spec.json file not found.")

    with open(BLUEPRINT_PATH, "r") as f:
        full_spec = json.load(f)

    # Merge updates
    full_spec["filtering_rules"]["minimum_salary_usd"] = config.minimum_salary_usd
    full_spec["filtering_rules"]["experience_years_range"] = config.experience_years_range
    full_spec["filtering_rules"]["forbidden_keywords"] = config.forbidden_keywords

    with open(BLUEPRINT_PATH, "w") as f:
        json.dump(full_spec, f, indent=2)

    return {"status": "success", "message": "Blueprint specifications successfully updated"}


@app.get("/api/cvs")
def list_cvs():
    """
    Scans the profiles folder and lists all loaded CV profiles.
    """
    cvs = []
    for filename in os.listdir(PROFILES_DIR):
        path = os.path.join(PROFILES_DIR, filename)
        if os.path.isfile(path) and not filename.startswith('.'):
            ext = filename.split('.')[-1].lower()
            if ext in ["pdf", "json", "txt", "docx"]:
                cvs.append({"name": filename, "type": ext})
    return cvs


@app.post("/api/cvs/upload")
def upload_cv(file: UploadFile = File(...)):
    """
    Saves an uploaded CV (PDF, TXT, or JSON) directly into the profiles directory
    so that Gemini can use it as a data guide.
    """
    ext = file.filename.split('.')[-1].lower()
    if ext not in ["pdf", "txt", "json"]:
        raise HTTPException(status_code=400, detail="Only PDF, TXT, and JSON files are supported.")

    dest_path = os.path.join(PROFILES_DIR, file.filename)
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "filename": file.filename, "message": "CV successfully uploaded."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save error: {str(e)}")


@app.post("/api/run")
def run_agent(req: RunAgentRequest):
    """
    Triggers the Playwright + Gemini agent loop.
    """
    # Check if files exist
    if not os.path.exists(req.cv_path):
        raise HTTPException(status_code=400, detail=f"The selected CV path '{req.cv_path}' does not exist.")

    try:
        # Run pipeline
        logs = run_pipeline(
            url=req.url,
            headless=True,  # Headless mode when run via web dashboard api
            blueprint_path=BLUEPRINT_PATH,
            user_data_dir="./.browser_session",
            cv_path=req.cv_path
        )
        return {"status": "completed", "message": "Agent execution completed.", "logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent loop error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
