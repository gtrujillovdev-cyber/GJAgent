#!/usr/bin/env python3
"""
FastAPI Server backend for the GeminiJobBot Settings Dashboard.
Manages configurations, handles resume file uploads (PDF, TXT, JSON),
updates environment files, and runs the agent bulk search automation pipeline asynchronously.
"""

import os
import json
import shutil
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Import bulk pipeline executor
from src.orchestrator import run_bulk_pipeline, LIVE_LOG_PATH

app = FastAPI(title="GeminiJobBot Dashboard API")

PROFILES_DIR = "./profiles"
BLUEPRINT_PATH = "./blueprints/candidate_spec.json"
ENV_PATH = "./.env"

# Ensure directories exist
os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(os.path.dirname(BLUEPRINT_PATH), exist_ok=True)


class SearchConfigUpdate(BaseModel):
    minimum_salary: int
    currency: str
    experience_years_range: Dict[str, int]
    target_keywords: List[str]


class RunAgentRequest(BaseModel):
    search_query: str
    max_applications: int
    portals: List[str]
    cv_path: str


class ApiKeyUpdate(BaseModel):
    gemini_api_key: str


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
        default_config = {
            "targeting": {"job_portals": ["LinkedIn", "Indeed"]},
            "filtering_rules": {
                "minimum_salary": 25000,
                "currency": "EUR",
                "target_keywords": ["Linux", "QA", "SDET", "Python"],
                "experience_years_range": {"min": 0, "max": 10}
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
    full_spec["filtering_rules"]["minimum_salary"] = config.minimum_salary
    full_spec["filtering_rules"]["currency"] = config.currency
    full_spec["filtering_rules"]["experience_years_range"] = config.experience_years_range
    full_spec["filtering_rules"]["target_keywords"] = config.target_keywords

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
    Saves an uploaded CV (PDF, TXT, or JSON) directly into the profiles directory.
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


@app.get("/api/apikey")
def get_api_key():
    """
    Fetches the loaded Gemini API Key masked for security, if configured.
    """
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY", "")
    if len(key) > 8:
        masked = key[:4] + "..." + key[-4:]
    else:
        masked = "Not Configured"
    return {"gemini_api_key": masked}


@app.post("/api/apikey")
def update_api_key(payload: ApiKeyUpdate):
    """
    Updates the GEMINI_API_KEY environment variable and writes it back to the local .env file.
    """
    key_val = payload.gemini_api_key.strip()
    if not key_val:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    lines = []
    found = False
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={key_val}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(f"GEMINI_API_KEY={key_val}\n")

    with open(ENV_PATH, "w") as f:
        f.writelines(new_lines)

    os.environ["GEMINI_API_KEY"] = key_val
    load_dotenv()

    return {"status": "success", "message": "API Key updated successfully."}


@app.get("/api/run/logs")
def get_run_logs():
    """
    Exposes the dynamically generated live log file lines.
    """
    if not os.path.exists(LIVE_LOG_PATH):
        return {"logs": []}
    try:
        with open(LIVE_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return {"logs": [line.strip() for line in lines]}
    except Exception as e:
        return {"logs": [f"Error reading live logs: {e}"]}


@app.post("/api/run")
def run_agent(req: RunAgentRequest, background_tasks: BackgroundTasks):
    """
    Triggers the Playwright + Gemini bulk search pipeline asynchronously.
    """
    if req.cv_path != "auto" and req.cv_path != "all" and not os.path.exists(req.cv_path):
        raise HTTPException(status_code=400, detail=f"The selected CV path '{req.cv_path}' does not exist.")

    # Trigger run_bulk_pipeline in the background thread
    background_tasks.add_task(
        run_bulk_pipeline,
        search_query=req.search_query,
        max_applications=req.max_applications,
        portals=req.portals,
        headless=True,
        blueprint_path=BLUEPRINT_PATH,
        user_data_dir="./.browser_session",
        cv_path=req.cv_path
    )

    return {"status": "triggered", "message": "Bulk automation pipeline successfully initiated in background."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
