#!/usr/bin/env python3
"""
Orchestrator for the Gemini Job Application Subagent.
This script coordinates real browser automation using Playwright,
Gemini API calls via the modern google-genai SDK,
dynamic profile loading, and execution of the job application loop.
"""

import os
import sys
import json
import logging
import re
import argparse
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Import Playwright for real browser automation
try:
    from playwright.sync_api import sync_playwright, Page, BrowserContext
except ImportError:
    print("Error: Playwright is not installed. Run 'pip install playwright && playwright install'")
    sys.exit(1)

# Import Google GenAI SDK (Modern SDK)
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai is not installed. Run 'pip install google-genai'")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("JobBotOrchestrator")


class PlaywrightBrowserEngine:
    """
    Real Playwright Browser Engine executing browser commands,
    session caching (via persistent context), and interaction.
    """
    def __init__(self, headless: bool = True, user_data_dir: str = "./.browser_session"):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def start(self):
        logger.info(f"Launching Playwright (Headless={self.headless}, UserDataDir={self.user_data_dir})")
        self.playwright = sync_playwright().start()
        # Using persistent context to preserve cookies and login tokens between runs
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"] # Bypass simple bot detection
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def navigate_to(self, url: str) -> str:
        logger.info(f"Navigating to URL: {url}")
        self.page.goto(url, wait_until="networkidle")
        # Extract clean visible body content to minimize token payload
        return self.page.content()

    def fill_form_field(self, selector: str, value: str) -> bool:
        try:
            logger.info(f"Attempting to fill selector '{selector}' with value: '{value}'")
            self.page.wait_for_selector(selector, timeout=5000)
            self.page.fill(selector, value)
            return True
        except Exception as e:
            logger.warning(f"Could not fill selector {selector}: {e}")
            return False

    def click_element(self, selector: str) -> bool:
        try:
            logger.info(f"Attempting to click selector: {selector}")
            self.page.wait_for_selector(selector, timeout=5000)
            self.page.click(selector)
            return True
        except Exception as e:
            logger.warning(f"Could not click selector {selector}: {e}")
            return False

    def capture_screenshot(self, output_path: str = "./workflows/checkpoints/screen.png") -> str:
        # Ensure directories exist
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self.page.screenshot(path=output_path)
        logger.info(f"Screenshot successfully captured and saved to: {output_path}")
        return output_path

    def close(self):
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
        logger.info("Browser engine terminated.")


class GeminiJobAgent:
    """
    Autonomous subagent powered by Gemini, designed to parse job details,
    evaluate them against a specification, and execute form submissions.
    """
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        if not api_key:
            raise ValueError("API Key for Gemini must be provided.")
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)

    def analyze_job(self, page_html: str, blueprint: Dict[str, Any]) -> Dict[str, Any]:
        """
        Uses Gemini's reasoning capabilities to evaluate whether a job posting matches criteria.
        """
        # Clean HTML to prevent passing excess token overhead to Gemini
        clean_html = re.sub(r'<script.*?</script>', '', page_html, flags=re.DOTALL)
        clean_html = re.sub(r'<style.*?</style>', '', clean_html, flags=re.DOTALL)
        clean_html = re.sub(r'<svg.*?</svg>', '', clean_html, flags=re.DOTALL)
        # Keep only basic structural tags or body text
        body_match = re.search(r'<body.*?>.*?</body>', clean_html, flags=re.DOTALL | re.IGNORECASE)
        if body_match:
            clean_html = body_match.group(0)

        # Cap length to stay within safe token usage
        clean_html = clean_html[:15000]

        prompt = f"""
        Analyze the following HTML content of a job post and match it against the applicant's blueprint requirements.
        
        Job HTML Content:
        \"\"\"{clean_html}\"\"\"
        
        Applicant Blueprint:
        {json.dumps(blueprint, indent=2)}
        
        Return a JSON response matching the following structure:
        {{
          "is_match": true/false,
          "match_confidence": 0.0 to 1.0,
          "reason": "Detailed description explaining how it matches or why it was skipped",
          "detected_title": "Identified job role",
          "detected_salary": "Identified salary details or 'Not Specified'"
        }}
        """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    system_instruction="You are an expert AI recruiting systems specialist. Analyze the job posting and extract information accurately, strictly adhering to the JSON schema output."
                )
            )
            return json.loads(response.text.strip())
        except Exception as e:
            logger.error(f"Error calling Gemini API for job analysis: {e}")
            # Dynamic fallback
            return {
                "is_match": False,
                "match_confidence": 0.0,
                "reason": f"API Evaluation failed: {str(e)}",
                "detected_title": "Unknown",
                "detected_salary": "Unknown"
            }

    def route_resume(self, job_title: str, blueprint: Dict[str, Any]) -> str:
        """
        Evaluates dynamic resume routing regex rules defined in the blueprint.
        """
        routing_rules = blueprint.get("dynamic_resume_routing", {})
        rules = routing_rules.get("rules", [])
        
        for rule in rules:
            regex = rule.get("role_regex", "")
            if re.search(regex, job_title, re.IGNORECASE):
                logger.info(f"Dynamic CV Match: '{job_title}' matched rule targeting path '{rule.get('resume_path')}'")
                return rule.get("resume_path")
                
        default_path = routing_rules.get("default_resume_path", "profiles/resume_template.json")
        logger.info(f"Dynamic CV Match: Using default resume path '{default_path}'")
        return default_path

    def fill_form_agentic(self, engine: PlaywrightBrowserEngine, resume_data: Dict[str, Any], page_html: str) -> bool:
        """
        Submits form fields by finding selectors dynamically via Gemini mapping.
        """
        # Ask Gemini to map resume keys to form elements based on DOM HTML structure
        prompt = f"""
        Given the following page HTML, identify the CSS selectors needed to fill in the applicant's details.
        
        Page HTML snippet:
        \"\"\"{page_html[:12000]}\"\"\"
        
        Applicant Resume:
        {json.dumps(resume_data.get('personal_info', {}), indent=2)}
        
        Return a JSON response matching:
        {{
          "actions": [
             {{"type": "input", "selector": "css_selector", "value": "value_to_fill"}},
             {{"type": "click", "selector": "css_selector"}}
          ]
        }}
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    system_instruction="Map the candidate details to the correct form inputs. Return only CSS selectors present in the DOM snippet."
                )
            )
            mapping = json.loads(response.text.strip())
            actions = mapping.get("actions", [])
            logger.info(f"Gemini mapped {len(actions)} actions to execute.")
            
            for action in actions:
                a_type = action.get("type")
                selector = action.get("selector")
                val = action.get("value", "")
                if a_type == "input":
                    engine.fill_form_field(selector, val)
                elif a_type == "click":
                    engine.click_element(selector)
            return True
        except Exception as e:
            logger.error(f"Failed to dynamically map/fill forms via Gemini: {e}")
            return False


def run_pipeline(url: str, headless: bool, blueprint_path: str, user_data_dir: str):
    """
    Main orchestrator execution pipeline using Playwright.
    """
    logger.info("Starting production pipeline execution...")
    
    # 1. Load Blueprint and Configurations
    try:
        with open(blueprint_path, "r") as f:
            blueprint = json.load(f)
    except FileNotFoundError:
        logger.error(f"Blueprint file not found at '{blueprint_path}'. Aborting.")
        sys.exit(1)

    # 2. Load Env Credentials
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable is missing in .env. Aborting.")
        sys.exit(1)
        
    # 3. Initialize Gemini Agent & Browser Engine
    agent = GeminiJobAgent(api_key=api_key, model_name=model_name)
    engine = PlaywrightBrowserEngine(headless=headless, user_data_dir=user_data_dir)
    
    try:
        engine.start()
        
        # 4. Navigate to target URL
        page_html = engine.navigate_to(url)
        
        # 5. Evaluate matching
        analysis = agent.analyze_job(page_html, blueprint)
        logger.info(f"Analysis Results: {json.dumps(analysis, indent=2)}")
        
        if not analysis.get("is_match", False):
            logger.info("Job does not meet specifications. Skipping application submission.")
            return

        # 6. Route Resume Dynamic Selection
        resume_path = agent.route_resume(analysis.get("detected_title", ""), blueprint)
        if not os.path.exists(resume_path):
            logger.warning(f"Routed resume path '{resume_path}' missing, falling back to 'profiles/resume_template.json'")
            resume_path = "profiles/resume_template.json"
            
        with open(resume_path, "r") as f:
            resume_data = json.load(f)

        # 7. Apply agentic form filling
        # Pass a current snapshot of the page HTML
        current_html = engine.page.content()
        success = agent.fill_form_agentic(engine, resume_data, current_html)
        
        if success:
            # Capturing validation screen
            engine.capture_screenshot()
            logger.info("Autonomous application run successfully completed!")
            
    except Exception as ex:
        logger.exception(f"Fatal error encountered during agent execution: {ex}")
    finally:
        engine.close()


if __name__ == "__main__":
    # Command line argument parser for CLI execution
    parser = argparse.ArgumentParser(description="Gemini Autonomous JobBot - Playwright Orchestrator")
    parser.add_argument("--url", type=str, default="https://careers.example.com/jobs/senior-ai-engineer-102",
                        help="Target job posting URL to analyze and apply for")
    parser.add_argument("--headless", action="store_true", default=False,
                        help="Run browser context in headless background mode (default: False/headed)")
    parser.add_argument("--blueprint", type=str, default="blueprints/candidate_spec.json",
                        help="Path to JSON targeting blueprint configuration")
    parser.add_argument("--user-data-dir", type=str, default="./.browser_session",
                        help="Path to browser storage directory (maintains cookies/auth)")

    args = parser.parse_args()
    
    # Run the pipeline
    run_pipeline(
        url=args.url,
        headless=args.headless,
        blueprint_path=args.blueprint,
        user_data_dir=args.user_data_dir
    )
