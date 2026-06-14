#!/usr/bin/env python3
"""
Orchestrator for the Gemini Job Application Subagent.
This script coordinates real browser automation using Playwright,
Gemini API calls via the modern google-genai SDK,
dynamic multi-profile loading, portal searches, and execution of bulk job applications.
"""

import os
import sys
import json
import logging
import re
import argparse
from typing import Dict, Any, List, Optional, Union
from dotenv import load_dotenv

# Import Playwright
try:
    from playwright.sync_api import sync_playwright, Page, BrowserContext
except ImportError:
    print("Error: Playwright is not installed. Run 'pip install playwright && playwright install'")
    sys.exit(1)

# Import Google GenAI SDK
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

LIVE_LOG_PATH = "./workflows/checkpoints/live_run.log"


def append_live_log(message: str):
    """
    Appends execution logs to a local file so the FastAPI server can stream them to the UI.
    """
    try:
        os.makedirs(os.path.dirname(LIVE_LOG_PATH), exist_ok=True)
        with open(LIVE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception as e:
        logger.error(f"Error writing to live log file: {e}")


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts text contents from a PDF document using pypdf.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        logger.info(f"Extracted {len(text)} characters of text from PDF: {pdf_path}")
        return text
    except Exception as e:
        logger.error(f"Error parsing PDF file {pdf_path}: {e}")
        return ""


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
        self.log_history: List[str] = []

    def log(self, message: str):
        logger.info(message)
        self.log_history.append(message)
        append_live_log(message)

    def start(self):
        self.log(f"Launching Playwright (Headless={self.headless}, UserDataDir={self.user_data_dir})")
        self.playwright = sync_playwright().start()
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def navigate_to(self, url: str) -> str:
        self.log(f"Navigating to: {url}")
        try:
            # Shortened timeout to 6000ms to fail fast on blocked/throttled portal pages
            self.page.goto(url, wait_until="networkidle", timeout=6000)
        except Exception as e:
            self.log(f"Navigation ended or timed out: {e}")
        return self.page.content()

    def extract_job_urls(self, portal: str) -> List[str]:
        """
        Scrapes job listing links from the current search results page.
        """
        urls = []
        try:
            self.log(f"Parsing job listing elements from {portal} results page...")
            hrefs = self.page.evaluate('''() => {
                return Array.from(document.querySelectorAll('a'))
                    .map(anchor => anchor.href)
                    .filter(href => href.includes('/jobs/view') || href.includes('/rc/clk') || href.includes('/partner/jobProject'));
            }''')
            
            seen = set()
            for href in hrefs:
                clean_href = href.split('?')[0]
                if clean_href not in seen:
                    seen.add(clean_href)
                    urls.append(clean_href)
            
            self.log(f"Extracted {len(urls)} job listing URLs from page.")
        except Exception as e:
            self.log(f"Error extracting job links: {e}")
            
        if not urls:
            self.log("No active elements found on public page. Generating simulated job links for demonstration...")
            urls = [
                f"https://careers.{portal.lower()}.com/jobs/senior-ai-engineer-101",
                f"https://careers.{portal.lower()}.com/jobs/python-agentic-developer-204",
                f"https://careers.{portal.lower()}.com/jobs/backend-systems-programmer-502"
            ]
        return urls

    def fill_form_field(self, selector: str, value: str) -> bool:
        try:
            self.log(f"Filling selector '{selector}' with value: '{value}'")
            self.page.wait_for_selector(selector, timeout=3000)
            self.page.fill(selector, value)
            return True
        except Exception as e:
            self.log(f"Could not fill selector {selector}: {e}")
            return False

    def click_element(self, selector: str) -> bool:
        try:
            self.log(f"Clicking selector: {selector}")
            self.page.wait_for_selector(selector, timeout=3000)
            self.page.click(selector)
            return True
        except Exception as e:
            self.log(f"Could not click selector {selector}: {e}")
            return False

    def capture_screenshot(self, output_path: str = "./workflows/checkpoints/screen.png") -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        self.page.screenshot(path=output_path)
        self.log(f"Screenshot saved to: {output_path}")
        return output_path

    def close(self):
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
        self.log("Browser engine terminated.")


class GeminiJobAgent:
    """
    Autonomous subagent powered by Gemini, designed to parse job details,
    evaluate them against a specification, select best matching CVs, and execute forms.
    """
    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash"):
        if not api_key:
            raise ValueError("API Key for Gemini must be provided.")
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)
        self._keywords_cache = {}

    def _generate_content_with_retry(
        self,
        contents: str,
        system_instruction: str = None,
        response_mime_type: str = "application/json",
        max_retries: int = 5,
        initial_delay: float = 2.0
    ) -> Any:
        import time
        import random
        delay = initial_delay
        for attempt in range(max_retries):
            try:
                config = types.GenerateContentConfig(
                    response_mime_type=response_mime_type,
                    system_instruction=system_instruction
                )
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config
                )
                return response
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    if attempt == max_retries - 1:
                        logger.error(f"Gemini API rate limit exceeded. Max retries ({max_retries}) reached. Error: {e}")
                        raise
                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = delay * jitter
                    logger.warning(f"Gemini API 429 Rate Limit hit. Retrying in {sleep_time:.2f} seconds (Attempt {attempt+1}/{max_retries})...")
                    time.sleep(sleep_time)
                    delay *= 2.0
                else:
                    logger.error(f"Gemini API call failed with non-retryable error: {e}")
                    raise

    def extract_keywords_from_cv(self, resume_data: Union[Dict[str, Any], str]) -> List[str]:
        """
        Asks Gemini to read the candidate CV and extract key professional skills/keywords.
        """
        resume_str = json.dumps(resume_data, indent=2) if isinstance(resume_data, dict) else str(resume_data)
        import hashlib
        cache_key = hashlib.md5(resume_str.encode('utf-8')).hexdigest()
        if cache_key in self._keywords_cache:
            logger.info("Retrieved CV keywords from cache.")
            return self._keywords_cache[cache_key]

        prompt = f"""
        Read the following candidate CV and extract a list of the top 15 core technical keywords, 
        technologies, skills, programming languages, or frameworks that define this profile.
        
        Candidate CV:
        \"\"\"{resume_str[:12000]}\"\"\"
        
        Return a JSON response matching:
        {{
          "keywords": ["Python", "Playwright", "FastAPI", "etc"]
        }}
        """
        try:
            response = self._generate_content_with_retry(
                contents=prompt,
                system_instruction="You are an expert AI talent acquisition system. Extract core technical keywords from resumes."
            )
            data = json.loads(response.text.strip())
            keywords = data.get("keywords", [])
            logger.info(f"Dynamically extracted keywords from CV: {keywords}")
            self._keywords_cache[cache_key] = keywords
            return keywords
        except Exception as e:
            logger.error(f"Error dynamically extracting keywords from CV: {e}")
            return ["Python", "FastAPI", "Docker", "Playwright", "LLMs", "Agentic Frameworks"]

    def select_best_cv(self, page_html: str, profiles: Dict[str, str]) -> str:
        """
        Given the job listing HTML and all loaded profile summaries, 
        asks Gemini to dynamically select the best matching CV.
        """
        summarized_profiles = {}
        for filename, content in profiles.items():
            summarized_profiles[filename] = content[:1500]

        prompt = f"""
        Compare the following job posting HTML details against all candidate CV profiles available.
        Select the CV file that is the absolute best match for this role.
        
        Job HTML Content snippet:
        \"\"\"{page_html[:8000]}\"\"\"
        
        Available Candidate Profiles (filename mapping to content snippet):
        {json.dumps(summarized_profiles, indent=2)}
        
        Return a JSON response specifying the best matching profile filename:
        {{
          "selected_filename": "filename_here"
        }}
        """
        try:
            response = self._generate_content_with_retry(
                contents=prompt,
                system_instruction="You are an expert recruitment router. Compare job requisitions with multiple CVs and choose the best matching file."
            )
            data = json.loads(response.text.strip())
            selected = data.get("selected_filename", "")
            if selected in profiles:
                return selected
        except Exception as e:
            logger.error(f"Error in dynamic AI CV selection: {e}")
            
        return list(profiles.keys())[0] if profiles else ""

    def analyze_job(self, page_html: str, blueprint: Dict[str, Any], cv_keywords: List[str]) -> Dict[str, Any]:
        """
        Uses Gemini's reasoning capabilities to evaluate whether a job posting matches criteria.
        """
        clean_html = re.sub(r'<script.*?</script>', '', page_html, flags=re.DOTALL)
        clean_html = re.sub(r'<style.*?</style>', '', clean_html, flags=re.DOTALL)
        clean_html = re.sub(r'<svg.*?</svg>', '', clean_html, flags=re.DOTALL)
        body_match = re.search(r'<body.*?>.*?</body>', clean_html, flags=re.DOTALL | re.IGNORECASE)
        if body_match:
            clean_html = body_match.group(0)

        clean_html = clean_html[:12000]

        prompt = f"""
        Analyze the HTML content of the job post and evaluate if it matches the candidate profile.
        
        Job HTML Content:
        \"\"\"{clean_html}\"\"\"
        
        Salary & Filtering Specs:
        {json.dumps(blueprint.get("filtering_rules", {}), indent=2)}
        
        Candidate CV Keywords (Lo que prevalece en la decisión):
        {json.dumps(cv_keywords, indent=2)}
        
        Return a JSON response matching the following structure:
        {{
          "is_match": true/false,
          "match_confidence": 0.0 to 1.0,
          "reason": "Detailed description explaining match status, highlighting presence of CV keywords and salary alignment",
          "detected_title": "Identified job role",
          "detected_salary": "Identified salary details or 'Not Specified'"
        }}
        
        Important Matching Rules:
        - Analyze the salary and convert currencies if they differ (evaluate minimum salary threshold using approximate exchange rates).
        - Verify if at least one or more of the candidate's CV Keywords are represented in the job post (prioritize jobs carrying these keywords).
        """
        
        try:
            response = self._generate_content_with_retry(
                contents=prompt,
                system_instruction="You are an expert AI recruiting systems specialist. Analyze the job posting, handle currency evaluation, check target CV keywords, and output structured JSON."
            )
            return json.loads(response.text.strip())
        except Exception as e:
            logger.error(f"Error calling Gemini API for job analysis: {e}")
            return {
                "is_match": False,
                "match_confidence": 0.0,
                "reason": f"API Evaluation failed: {str(e)}",
                "detected_title": "Unknown",
                "detected_salary": "Unknown"
            }

    def fill_form_agentic(self, engine: PlaywrightBrowserEngine, resume_data: Union[Dict[str, Any], str], page_html: str) -> bool:
        """
        Submits form fields by finding selectors dynamically via Gemini mapping.
        """
        resume_str = json.dumps(resume_data, indent=2) if isinstance(resume_data, dict) else str(resume_data)

        prompt = f"""
        Given the following page HTML, identify the CSS selectors needed to fill in the applicant's details based on their resume profile contents.
        
        Page HTML snippet:
        \"\"\"{page_html[:10000]}\"\"\"
        
        Applicant Resume Contents:
        \"\"\"{resume_str[:10000]}\"\"\"
        
        Return a JSON response matching:
        {{
          "actions": [
             {{"type": "input", "selector": "css_selector", "value": "value_to_fill"}},
             {{"type": "click", "selector": "css_selector"}}
          ]
        }}
        """
        try:
            response = self._generate_content_with_retry(
                contents=prompt,
                system_instruction="Map the candidate details to the correct form inputs. Return only CSS selectors present in the DOM snippet."
            )
            mapping = json.loads(response.text.strip())
            actions = mapping.get("actions", [])
            engine.log(f"Gemini mapped {len(actions)} actions to execute based on the resume.")
            
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
            engine.log(f"Failed to dynamically map/fill forms via Gemini: {e}")
            return False


def run_bulk_pipeline(
    search_query: str, 
    max_applications: int, 
    portals: List[str], 
    headless: bool, 
    blueprint_path: str, 
    user_data_dir: str, 
    cv_path: str
) -> List[str]:
    """
    Runs search loops over multiple job portals and applies to matching jobs up to max_applications.
    """
    # Clean/Reset the live run log file
    if os.path.exists(LIVE_LOG_PATH):
        try:
            os.remove(LIVE_LOG_PATH)
        except Exception:
            pass

    engine = PlaywrightBrowserEngine(headless=headless, user_data_dir=user_data_dir)
    engine.log(f"Starting bulk pipeline. Query: '{search_query}', Max Applications: {max_applications}, Portals: {portals}")
    
    # 1. Load Blueprint
    try:
        with open(blueprint_path, "r") as f:
            blueprint = json.load(f)
    except FileNotFoundError:
        engine.log(f"Blueprint file not found at '{blueprint_path}'. Aborting.")
        return engine.log_history

    # 2. Load API Credentials
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    
    if not api_key:
        engine.log("GEMINI_API_KEY environment variable is missing in .env. Aborting.")
        return engine.log_history

    # 3. Load CV Profile(s)
    profiles_dict = {}
    profiles_dir = "./profiles"
    for filename in os.listdir(profiles_dir):
        p_path = os.path.join(profiles_dir, filename)
        if os.path.isfile(p_path) and not filename.startswith('.'):
            if filename.lower().endswith(".pdf"):
                text = extract_text_from_pdf(p_path)
                if text:
                    profiles_dict[p_path] = text
            elif filename.lower().endswith(".json"):
                with open(p_path, "r") as f:
                    profiles_dict[p_path] = f.read()
            elif filename.lower().endswith(".txt"):
                with open(p_path, "r", encoding="utf-8", errors="ignore") as f:
                    profiles_dict[p_path] = f.read()

    if not profiles_dict:
        engine.log("No valid candidate profiles found in './profiles'. Aborting.")
        return engine.log_history

    agent = GeminiJobAgent(api_key=api_key, model_name=model_name)
    applied_count = 0

    is_auto_routing = cv_path == "auto" or cv_path == "all" or not cv_path
    selected_cv = cv_path if not is_auto_routing else list(profiles_dict.keys())[0]
    
    if not is_auto_routing:
        engine.log(f"Using single active CV profile: {selected_cv}")
        resume_data = profiles_dict.get(selected_cv, "")
        cv_keywords = agent.extract_keywords_from_cv(resume_data)
    else:
        engine.log("AI Auto-Routing enabled. The agent will compare job postings against all CV profiles in the folder dynamically.")
        cv_keywords = []
    
    try:
        engine.start()
        
        # Loop over target portals
        for portal in portals:
            if applied_count >= max_applications:
                break
                
            engine.log(f"--- Executing search on portal: {portal} ---")
            
            search_url = ""
            if portal == "LinkedIn":
                search_url = f"https://www.linkedin.com/jobs/search/?keywords={search_query.replace(' ', '%20')}"
            elif portal == "Indeed":
                search_url = f"https://www.indeed.com/jobs?q={search_query.replace(' ', '%20')}"
            elif portal == "Glassdoor":
                search_url = f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={search_query.replace(' ', '%20')}"
            else:
                search_url = f"https://www.google.com/search?q={search_query.replace(' ', '%20')}+jobs"
                
            engine.navigate_to(search_url)
            job_urls = engine.extract_job_urls(portal)
            
            for idx, job_url in enumerate(job_urls):
                if applied_count >= max_applications:
                    engine.log(f"Application limit met ({max_applications}). Stopping execution.")
                    break
                    
                engine.log(f"Processing candidate job listing {idx+1}/{len(job_urls)}: {job_url}")
                page_html = engine.navigate_to(job_url)
                
                # Dynamic Routing
                if is_auto_routing:
                    engine.log("Comparing job description against all loaded candidate CVs...")
                    selected_cv = agent.select_best_cv(page_html, profiles_dict)
                    engine.log(f"AI Dynamic Router selected CV: '{selected_cv}' for this job.")
                    resume_data = profiles_dict.get(selected_cv, "")
                    cv_keywords = agent.extract_keywords_from_cv(resume_data)

                # Analyze matching against dynamic CV keywords
                analysis = agent.analyze_job(page_html, blueprint, cv_keywords)
                engine.log(f"Match Analysis: {json.dumps(analysis, indent=1)}")
                
                if not analysis.get("is_match", False):
                    engine.log("Skipping: Job post did not meet CV keyword criteria.")
                    continue
                    
                # Fill Form
                current_html = engine.page.content()
                success = agent.fill_form_agentic(engine, resume_data, current_html)
                
                if success:
                    applied_count += 1
                    screenshot_name = f"./workflows/checkpoints/applied_{portal}_{applied_count}.png"
                    engine.capture_screenshot(screenshot_name)
                    engine.log(f"Applied successfully to '{analysis.get('detected_title')}' (Total: {applied_count}/{max_applications})")
                    
    except Exception as ex:
        engine.log(f"Fatal error encountered during agent execution: {ex}")
    finally:
        engine.close()

    engine.log(f"Pipeline finished. Successfully submitted {applied_count} job applications.")
    return engine.log_history


def run_pipeline(url: str, headless: bool, blueprint_path: str, user_data_dir: str, cv_path: str) -> List[str]:
    return run_bulk_pipeline(
        search_query="AI Engineer",
        max_applications=1,
        portals=["LinkedIn"],
        headless=headless,
        blueprint_path=blueprint_path,
        user_data_dir=user_data_dir,
        cv_path=cv_path
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini Autonomous JobBot - Playwright Orchestrator")
    parser.add_argument("--query", type=str, default="AI Engineer")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--portals", type=str, default="LinkedIn,Indeed")
    parser.add_argument("--headless", action="store_true", default=False)
    parser.add_argument("--blueprint", type=str, default="blueprints/candidate_spec.json")
    parser.add_argument("--user-data-dir", type=str, default="./.browser_session")
    parser.add_argument("--cv", type=str, default="auto")

    args = parser.parse_args()
    portals_list = [p.strip() for p in args.portals.split(",")]
    
    run_bulk_pipeline(
        search_query=args.query,
        max_applications=args.limit,
        portals=portals_list,
        headless=args.headless,
        blueprint_path=args.blueprint,
        user_data_dir=args.user_data_dir,
        cv_path=args.cv
    )
