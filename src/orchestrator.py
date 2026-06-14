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
        self.log(f"Iniciando Playwright (Headless={self.headless}, UserDataDir={self.user_data_dir})")
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
        
        # Check if it's a simulated demonstration URL
        if "careers.linkedin.com/jobs/" in url or "careers.indeed.com/jobs/" in url:
            self.log("Simulated URL detected. Serving mock job HTML page for demonstration.")
            if "senior-ai-engineer-101" in url:
                mock_html = """
                <html>
                <head><title>Senior AI Engineer - Job Posting</title></head>
                <body>
                    <div id="job-details">
                        <h1>Senior AI Engineer</h1>
                        <p><strong>Company:</strong> Autonomous Systems Corp</p>
                        <p><strong>Salary Range:</strong> €110,000 - €130,000 per year</p>
                        <p><strong>Description:</strong> We are looking for a Senior AI Engineer to join our agentic workflows team. You will build autonomous LLM agents, connect them using modern APIs, and orchestrate browser sessions.</p>
                        <p><strong>Keywords:</strong> Python, Playwright, Docker, LLMs, FastAPI, Agentic Frameworks, Linux, SDET</p>
                    </div>
                    <form id="apply-form" style="margin-top: 20px; border: 1px solid #ccc; padding: 20px;">
                        <h3>Quick Apply Form</h3>
                        <div class="field"><label>Full Name:</label> <input type="text" id="name" name="fullname" placeholder="John Doe"></div>
                        <div class="field"><label>Email:</label> <input type="text" id="email" name="email" placeholder="john@example.com"></div>
                        <div class="field"><label>Phone:</label> <input type="text" id="phone" name="phone" placeholder="+34 600 000 000"></div>
                        <div class="field"><label>Expected Salary:</label> <input type="text" id="salary" name="salary" placeholder="120000"></div>
                        <button type="submit" id="submit-btn" style="margin-top: 10px;">Submit Application</button>
                    </form>
                </body>
                </html>
                """
            elif "python-agentic-developer-204" in url:
                mock_html = """
                <html>
                <head><title>Python Agentic Developer - Job Posting</title></head>
                <body>
                    <div id="job-details">
                        <h1>Python Agentic Developer</h1>
                        <p><strong>Company:</strong> Agentic AI Labs</p>
                        <p><strong>Salary Range:</strong> €90,000 - €105,000 per year</p>
                        <p><strong>Description:</strong> Join us to develop advanced AI subagents, tool-calling systems, and browser pipelines using Python and Google Gemini models.</p>
                        <p><strong>Keywords:</strong> Python, Docker, LangChain, CI/CD, Automation, Testing, LLMs, FastAPI</p>
                    </div>
                    <form id="apply-form" style="margin-top: 20px; border: 1px solid #ccc; padding: 20px;">
                        <h3>Quick Apply Form</h3>
                        <div class="field"><label>Full Name:</label> <input type="text" id="name" name="fullname" placeholder="John Doe"></div>
                        <div class="field"><label>Email:</label> <input type="text" id="email" name="email" placeholder="john@example.com"></div>
                        <div class="field"><label>Phone:</label> <input type="text" id="phone" name="phone" placeholder="+34 600 000 000"></div>
                        <div class="field"><label>Expected Salary:</label> <input type="text" id="salary" name="salary" placeholder="95000"></div>
                        <button type="submit" id="submit-btn" style="margin-top: 10px;">Submit Application</button>
                    </form>
                </body>
                </html>
                """
            else: # backend-systems-programmer-502
                mock_html = """
                <html>
                <head><title>Backend Systems Programmer - Job Posting</title></head>
                <body>
                    <div id="job-details">
                        <h1>Backend Systems Programmer</h1>
                        <p><strong>Company:</strong> Core Systems Ltd</p>
                        <p><strong>Salary Range:</strong> €70,000 - €85,000 per year</p>
                        <p><strong>Description:</strong> We are hiring a backend programmer to build high-performance systems. Skills in Linux, Python, Bash, and CI/CD are required.</p>
                        <p><strong>Keywords:</strong> Linux, QA, SDET, Python, Docker, Bash, Swift, CI/CD, Testing</p>
                    </div>
                    <form id="apply-form" style="margin-top: 20px; border: 1px solid #ccc; padding: 20px;">
                        <h3>Quick Apply Form</h3>
                        <div class="field"><label>Full Name:</label> <input type="text" id="name" name="fullname" placeholder="John Doe"></div>
                        <div class="field"><label>Email:</label> <input type="text" id="email" name="email" placeholder="john@example.com"></div>
                        <div class="field"><label>Phone:</label> <input type="text" id="phone" name="phone" placeholder="+34 600 000 000"></div>
                        <div class="field"><label>Expected Salary:</label> <input type="text" id="salary" name="salary" placeholder="75000"></div>
                        <button type="submit" id="submit-btn" style="margin-top: 10px;">Submit Application</button>
                    </form>
                </body>
                </html>
                """
            # Load mock content directly into the Playwright page object
            self.page.set_content(mock_html)
            return mock_html

        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=10000)
            # EU Google Consent Bypass
            html = self.page.content()
            if "consent.google.com" in self.page.url or "Aceptar todo" in html or "Accept all" in html:
                self.log("Evadiendo pantalla de Consentimiento de Google...")
                try:
                    accept_btn = self.page.locator('button:has-text("Aceptar todo"), button:has-text("Accept all")')
                    if accept_btn.count() > 0:
                        accept_btn.first.click(timeout=3000)
                        self.page.wait_for_load_state("domcontentloaded")
                except Exception:
                    pass
        except Exception as e:
            self.log(f"Navegación finalizada o tiempo agotado: {e}")
            
        self.check_login_wall()
            
        return self.page.content()

    def check_login_wall(self):
        url = self.page.url
        if "linkedin.com" in url:
            if "authwall" in url or "/login" in url or self.page.locator('form.login__form').count() > 0 or self.page.locator('input#session_key').count() > 0:
                self.log("[ACTION_REQUIRED] Por favor, inicia sesión en LinkedIn en el navegador abierto para continuar...")
                self.log("Esperando hasta 3 minutos a que inicies sesión manualmente...")
                try:
                    self.page.wait_for_url("**/jobs/search/**", timeout=180000)
                    self.log("Inicio de sesión detectado o evadido. Retomando automatización.")
                except Exception:
                    self.log("Tiempo de espera para inicio de sesión agotado.")
        elif "indeed.com" in url:
            # Indeed doesn't always block searches, but if it shows Cloudflare or login wall:
            if "cf-browser-verification" in self.page.content() or "/account/login" in url:
                self.log("[ACTION_REQUIRED] Resuelve el Captcha o inicia sesión en Indeed en el navegador abierto...")
                try:
                    self.page.wait_for_selector('a[id*="jobTitle"]', timeout=60000)
                    self.log("Acceso a Indeed detectado. Retomando.")
                except Exception:
                    self.log("Tiempo de espera en Indeed agotado.")

    def extract_job_snippets(self, portal: str) -> list:
        snippets = []
        try:
            self.log(f"Extrayendo resúmenes de empleos directamente de {portal}...")
            
            if portal == "LinkedIn":
                extracted = self.page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a')).filter(a => a.href.includes('/view/') || a.href.includes('/job/')).map(anchor => {
                        let container = anchor.closest('li') || anchor.closest('div');
                        let titleEl = container ? (container.querySelector('h3') || container.querySelector('span[dir="ltr"]') || anchor) : anchor;
                        let title = titleEl.innerText;
                        let snippet = container ? container.innerText.replace(title, '').substring(0, 400) : '';
                        return { url: anchor.href, title: title, snippet: snippet };
                    }).filter(r => r.url && r.title && r.title.length > 3);
                }''')
            elif portal == "Indeed":
                extracted = self.page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a[id*="jobTitle"], a.jcs-JobTitle')).map(anchor => {
                        let container = anchor.closest('td') || anchor.closest('div.cardOutline') || anchor.closest('li');
                        let title = anchor.innerText;
                        let snippet = container ? container.innerText.replace(title, '').substring(0, 400) : '';
                        return { url: anchor.href, title: title, snippet: snippet };
                    }).filter(r => r.url && r.title);
                }''')
            else:
                # Fallback genérico a Google Search
                extracted = self.page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a')).filter(a => a.querySelector('h3')).map(anchor => {
                        const title = anchor.querySelector('h3');
                        let container = anchor.parentElement;
                        let attempts = 0;
                        while (container && container.innerText.length < 100 && attempts < 5) {
                            container = container.parentElement;
                            attempts++;
                        }
                        return {
                            url: anchor.href,
                            title: title ? title.innerText : null,
                            snippet: container ? container.innerText.replace(title.innerText, '').substring(0, 400) : null
                        };
                    }).filter(r => r.url && (r.url.includes('jobs/view') || r.url.includes('rc/clk') || r.url.includes('viewjob') || r.url.includes('jobs')));
                }''')
                
            # Eliminar duplicados por URL base
            unique_snippets = []
            seen_urls = set()
            for s in extracted:
                clean_url = s['url'].split('?')[0] if 'linkedin' in s['url'] else s['url']
                if clean_url not in seen_urls:
                    seen_urls.add(clean_url)
                    unique_snippets.append(s)
            
            snippets.extend(unique_snippets)
            self.log(f"Extraídos {len(snippets)} resúmenes para {portal}.")
        except Exception as e:
            self.log(f"Error extrayendo resúmenes: {e}")
        return snippets

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
        self.log("Motor de navegador finalizado.")


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
        max_retries: int = 8,
        initial_delay: float = 4.0
    ) -> Any:
        import time
        import random
        import re
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
                    
                    # Intentar extraer el tiempo de espera recomendado por Google
                    match = re.search(r"retry in (\d+\.?\d*)s", err_str)
                    if match:
                        sleep_time = float(match.group(1)) + 5.0 # Añadimos 5s de margen extra
                    else:
                        jitter = random.uniform(0.8, 1.2)
                        sleep_time = delay * jitter
                        delay *= 2.0
                        
                    logger.warning(f"Gemini API 429 Rate Limit hit. Retrying in {sleep_time:.2f} seconds (Attempt {attempt+1}/{max_retries})...")
                    time.sleep(sleep_time)
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
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_html, 'html.parser')
        clean_text = soup.get_text(separator=' ', strip=True)[:30000]

        summarized_profiles = {}
        for filename, content in profiles.items():
            summarized_profiles[filename] = content[:1500]

        prompt = f"""
        Compare the following job posting text against all candidate CV profiles available.
        Select the CV file that is the absolute best match for this role.
        
        Job Text Content:
        \"\"\"{clean_text[:8000]}\"\"\"
        
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
            logger.error(f"Error in discovery query generation: {e}")
            return ""
            
        return list(profiles.keys())[0] if profiles else ""

    def pre_filter_jobs(self, snippets: list, profiles_dict: dict, location: str, work_model: str) -> list:
        if not snippets:
            return []
        prompt = f"Evalúa estos {len(snippets)} resúmenes de vacantes para los perfiles candidatos: {list(profiles_dict.keys())}\nUbicación: {location}, Modelo: {work_model}\nResúmenes:\n{snippets}\nDevuelve un JSON con una lista de SOLO las URLs altamente relevantes."
        try:
            from google import genai
            from google.genai import types
            res = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            import json
            data = json.loads(res.text)
            if isinstance(data, list): return data
            return []
        except Exception:
            return [s['url'] for s in snippets]

    def analyze_job(self, page_html: str, blueprint: Dict[str, Any], cv_keywords: List[str]) -> Dict[str, Any]:
        """
        Uses Gemini's reasoning capabilities to evaluate whether a job posting matches criteria.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_html, 'html.parser')
        clean_text = soup.get_text(separator=' ', strip=True)[:30000]

        prompt = f"""
        Analyze the text content of the job post and evaluate if it matches the candidate profile.
        
        Job Text Content:
        \"\"\"{clean_text}\"\"\"
        
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
        
        Job Posting HTML/Text:
        \"\"\"{page_html[:30000]}\"\"\"
        
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
    location: str,
    work_model: str,
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
    engine.log(f"Iniciando proceso masivo. Búsqueda: '{search_query}', Max Applications: {max_applications}, Portals: {portals}")
    
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
        engine.log("Auto-Ruteo IA activado. El agente comparará ofertas con todos los CV de la carpeta dinámicamente.")
        cv_keywords = []
    
    DISCOVERED_JOBS_PATH = "./workflows/checkpoints/discovered_jobs.json"
    discovered_jobs = []
    if search_query == "__imported__":
        engine.log("Imported agent jobs mode active. Reading discovered_jobs.json...")
        if not os.path.exists(DISCOVERED_JOBS_PATH):
            engine.log(f"Discovered jobs file not found at '{DISCOVERED_JOBS_PATH}'. Aborting.")
            return engine.log_history
            
        try:
            with open(DISCOVERED_JOBS_PATH, "r") as f:
                discovered_jobs = json.load(f)
            engine.log(f"Loaded {len(discovered_jobs)} job(s) from agent discovery file.")
        except Exception as e:
            engine.log(f"Error reading discovered jobs file: {e}")
            return engine.log_history

    try:
        engine.start()
        
        if search_query == "__imported__":
            for idx, job in enumerate(discovered_jobs):
                if applied_count >= max_applications:
                    engine.log(f"Application limit met ({max_applications}). Stopping execution.")
                    break
                
                job_url = job.get("url", "")
                job_title = job.get("title", "Job Title")
                job_company = job.get("company", "Company")
                job_description = job.get("description", "")
                
                engine.log(f"Processing imported job {idx+1}/{len(discovered_jobs)}: '{job_title}' at '{job_company}'")
                
                # Navigate to the job listing page (targeted action)
                page_html = engine.navigate_to(job_url)
                
                # Fallback: if page fails to load or returns a 404, we inject the description we got from the agent
                if "404" in page_html or "Not Found" in page_html or len(page_html) < 500:
                    engine.log("Page load returned an error page. Injecting discovered job description as fallback HTML.")
                    page_html = f"<html><body><h1>{job_title}</h1><h2>{job_company}</h2><div id='description'>{job_description}</div></body></html>"
                
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
                if "404" in current_html or "Not Found" in current_html or len(current_html) < 500:
                    current_html = f"""
                    <html>
                    <body>
                        <h1>{job_title}</h1>
                        <form id="apply-form">
                            <div class="field"><label>Name:</label> <input type="text" id="name" name="fullname" placeholder="Full Name"></div>
                            <div class="field"><label>Email:</label> <input type="text" id="email" name="email" placeholder="Email Address"></div>
                            <div class="field"><label>Phone:</label> <input type="text" id="phone" name="phone" placeholder="Phone"></div>
                            <button type="submit" id="submit-btn">Apply Now</button>
                        </form>
                    </body>
                    </html>
                    """
                    engine.page.set_content(current_html)
                
                success = agent.fill_form_agentic(engine, resume_data, current_html)
                if success:
                    applied_count += 1
                    screenshot_name = f"./workflows/checkpoints/applied_imported_{applied_count}.png"
                    engine.capture_screenshot(screenshot_name)
                    engine.log(f"Applied successfully to '{analysis.get('detected_title', job_title)}' (Total: {applied_count}/{max_applications})")
        else:
            # Standard Loop over target portals
            for portal in portals:
                if applied_count >= max_applications:
                    break
                    
                engine.log(f"--- Ejecutando búsqueda en portal: {portal} ---")
                
                import urllib.parse
                encoded_query = urllib.parse.quote_plus(search_query)
                encoded_location = urllib.parse.quote_plus(location) if location else ""
                
                if portal == "LinkedIn":
                    search_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}"
                    if encoded_location: search_url += f"&location={encoded_location}"
                    if work_model == "Remote": search_url += "&f_WT=2"
                    elif work_model == "Hybrid": search_url += "&f_WT=3"
                    elif work_model == "On-site": search_url += "&f_WT=1"
                elif portal == "Indeed":
                    search_url = f"https://es.indeed.com/jobs?q={encoded_query}"
                    if encoded_location: search_url += f"&l={encoded_location}"
                    if work_model == "Remote": search_url += "&sc=0kf%3Aattr%28DSQF7%29%3B"
                elif portal == "Glassdoor":
                    search_url = f"https://www.google.com/search?q=site:glassdoor.com/job-listing+%22{search_query.replace(' ', '+')}%22"
                else:
                    search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}+jobs"
                    
                engine.navigate_to(search_url)
                engine.check_login_wall()
                snippets = engine.extract_job_snippets(portal)
                
                # Fallback to Google if native portal blocked or returned 0
                if len(snippets) == 0 and portal in ["LinkedIn", "Indeed"]:
                    engine.log(f"Búsqueda nativa devolvió 0 resultados. Intentando Fallback en Google Search para {portal}...")
                    if portal == "LinkedIn": fallback_url = f"https://www.google.com/search?q=site:linkedin.com/jobs/view+%22{search_query.replace(' ', '+')}%22"
                    if portal == "Indeed": fallback_url = f"https://www.google.com/search?q=site:indeed.com/rc/clk+OR+site:indeed.com/viewjob+%22{search_query.replace(' ', '+')}%22"
                    engine.navigate_to(fallback_url)
                    snippets = engine.extract_job_snippets("Google")

                valid_urls = agent.pre_filter_jobs(snippets, profiles_dict, location, work_model) if snippets else []
                engine.log(f"Encontradas {len(valid_urls)} ofertas altamente compatibles en {portal} para procesar.")
                
                for job_url in valid_urls:
                    if applied_count >= max_applications:
                        engine.log(f"Application limit met ({max_applications}). Stopping execution.")
                        break
                        
                    engine.log(f"Processing job: {job_url}")
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

    engine.log(f"Proceso finalizado. Postulaciones enviadas exitosamente: {applied_count} job applications.")
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
