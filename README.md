<div align="center">
  <h1>🤖 GeminiJobBot</h1>
  <p><strong>An autonomous, Agentic AI Job Application Subagent powered by Google Gemini and Playwright.</strong></p>
  <p><strong>Un subagente autónomo de postulación de empleo impulsado por Google Gemini y Playwright.</strong></p>

  [![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-teal.svg)](https://fastapi.tiangolo.com/)
  [![Playwright](https://img.shields.io/badge/Playwright-Browser%20Automation-green.svg)](https://playwright.dev/)
  [![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-orange.svg)](https://aistudio.google.com/)
</div>

<hr>

## 🚀 Overview / Resumen

### English
**GeminiJobBot** is a next-generation automation tool that moves beyond fragile web scraping. Instead of relying on hardcoded HTML selectors, it uses the reasoning capabilities of **Google Gemini** (via multimodal DOM analysis) and **Playwright** to visually and semantically navigate job portals, read job descriptions, select the best matching CV profile, and apply dynamically.

### Español
**GeminiJobBot** es una herramienta de automatización de próxima generación que va más allá del web scraping frágil. En lugar de depender de selectores HTML rígidos, utiliza las capacidades de razonamiento de **Google Gemini** (mediante análisis multimodal del DOM) y **Playwright** para navegar de forma visual y semántica por los portales de empleo, leer las descripciones de las ofertas, seleccionar el mejor currículum de tu carpeta y postularse dinámicamente.

---

## 🌟 Key Features / Características Principales

### English
* 🧠 **Cognitive Pre-Filtering**: Analyzes search result snippets using Gemini to discard irrelevant jobs before clicking them, saving API quota.
* 🔀 **Dynamic Context Routing**: Reads the job requirements and automatically picks the best matching CV profile from your folder (e.g., *Frontend Dev* vs *QA Automation*).
* 🛡️ **DOM Resilience**: Evaluates the page conceptually rather than strictly by XPath, preventing breakages when websites update their designs.
* 🌐 **Native Portal Search**: Connects directly to LinkedIn & Indeed internal search engines with an automatic Google Search fallback mechanism.
* ⏸️ **Human-in-the-Loop Login**: Detects authentication walls (Captchas/Logins) and safely pauses the bot via a UI alert, allowing manual interaction before resuming.
* 🚦 **Smart Rate Limit Handling**: Mathematically parses API limits to pause operations dynamically for Google Gemini's Free Tier quotas.
* 🖥️ **Glassmorphic UI**: Comes with a sleek, real-time FastAPI dashboard to monitor logs, set salaries, and configure target parameters natively in your browser.

### Español
* 🧠 **Pre-Filtrado Cognitivo**: Analiza los resúmenes de búsqueda usando Gemini para descartar empleos irrelevantes antes de hacer clic en ellos, ahorrando cuota de la API.
* 🔀 **Enrutamiento Dinámico de Contexto**: Lee los requisitos del puesto y elige automáticamente el mejor CV de tu carpeta (ej. *Desarrollador Frontend* vs *QA Automation*).
* 🛡️ **Resiliencia al DOM**: Evalúa la página conceptualmente en lugar de estrictamente por XPath, evitando que se rompa cuando las webs se actualizan.
* 🌐 **Búsqueda Nativa en Portales**: Se conecta directamente a los buscadores internos de LinkedIn e Indeed con un mecanismo de respaldo (Fallback) en Google.
* ⏸️ **Login Interactivo (Human-in-the-Loop)**: Detecta muros de autenticación o Captchas y pausa el bot alertando en la interfaz, permitiéndote resolverlo manualmente antes de continuar.
* 🚦 **Gestor Inteligente de Límites de API**: Interpreta matemáticamente los bloqueos de Rate Limit de Gemini (429) para pausar la ejecución con precisión clínica en cuentas gratuitas.
* 🖥️ **Interfaz UI Glassmorphic**: Incluye un elegante panel en tiempo real con FastAPI para monitorizar los logs, fijar salarios y configurar parámetros directamente desde el navegador.

---

## 📚 Documentation / Documentación

All deep-dive technical documentation is located in the `docs/` folder.  
Toda la documentación técnica detallada se encuentra en la carpeta `docs/`.

1. 🏗️ **[Architecture Overview / Arquitectura](docs/ARCHITECTURE.md)**: Deep dive into the Agentic Pipeline. / Explicación profunda del Pipeline Agéntico.
2. 📖 **[User Guide / Guía de Usuario](docs/USER_GUIDE.md)**: Setup, UI, and CV configuration. / Instalación, uso de la UI y configuración de CVs.
3. 💻 **[Development Guide / Guía de Desarrollo](docs/DEVELOPMENT.md)**: Contributing and expanding the bot. / Contribuir y expandir el bot.

---

## ⚡ Quick Start / Inicio Rápido

### 1. Installation / Instalación
```bash
git clone https://github.com/tu-usuario/GeminiJobBot.git
cd GeminiJobBot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Configuration / Configuración
Create your environment variables file and add your [Google Gemini API Key](https://aistudio.google.com/):  
Crea tu archivo de variables de entorno y añade tu clave de API de Gemini:
```bash
cp .env.example .env
```
Add your PDF resumes into the `profiles/` directory.  
Añade tus currículums en PDF dentro del directorio `profiles/`.

### 3. Run the Dashboard / Ejecutar el Panel
Start the local control panel:  
Arranca el panel de control local:
```bash
python -m uvicorn src.app:app --reload
```
Open your browser at `http://127.0.0.1:8000`. Configure your Location, Expected Salary, and Keywords, and hit **Start Automation Loop**!  
Abre tu navegador en `http://127.0.0.1:8000`. Configura tu Ubicación, Salario Esperado y Palabras Clave, ¡y pulsa **Iniciar Automatización**!

---

## 📸 Screenshots / Capturas de Pantalla

*(Add your UI screenshots here / Añade tus capturas de pantalla aquí)*
- Dashboard Interface: `![Dashboard](google_search.png)`

---
<div align="center">
  <i>Built with ❤️ for autonomous job hunting. / Construido con ❤️ para la búsqueda autónoma de empleo.</i>
</div>
