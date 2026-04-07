"""
GEDEON Renderer — Service de rendu Playwright pour GEDEON
Expose un endpoint HTTP que Claude peut appeler via web_fetch.

Endpoints:
  GET  /render?url=<url>&wait=<ms>&selector=<css>
  GET  /health
  GET  /

Auth: X-API-Key header
"""

import os
import asyncio
import logging
from functools import wraps

from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("RENDERER_API_KEY", "Gedeon2026Liza")
DEFAULT_WAIT_MS = 2000        # délai par défaut après chargement JS
MAX_WAIT_MS = 15000           # plafond de sécurité
DEFAULT_TIMEOUT_MS = 60000    # timeout navigation

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Auth ─────────────────────────────────────────────────────────────────────
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "") or request.args.get("key", "")
        if not API_KEY:
            # Pas de clé configurée = mode dev non sécurisé
            logger.warning("RENDERER_API_KEY non définie — auth désactivée")
        elif key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Rendu Playwright ─────────────────────────────────────────────────────────
async def render_page(url: str, wait_ms: int, selector: str | None) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-first-run",
                "--no-zygote",
                "--single-process",   # nécessaire sur Render free tier
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        try:
            await page.goto(url, timeout=DEFAULT_TIMEOUT_MS, wait_until="domcontentloaded")

            # Attendre le sélecteur si fourni
            if selector:
                try:
                    await page.wait_for_selector(selector, timeout=wait_ms)
                except Exception:
                    logger.warning(f"Sélecteur '{selector}' non trouvé dans {wait_ms}ms")
            else:
                # Attente fixe pour laisser le JS s'exécuter
                await page.wait_for_timeout(wait_ms)

            html = await page.content()
            title = await page.title()
            final_url = page.url

            return {
                "success": True,
                "url": final_url,
                "title": title,
                "html": html,
                "html_length": len(html),
            }

        except Exception as e:
            logger.error(f"Erreur rendu {url}: {e}")
            return {"success": False, "url": url, "error": str(e)}

        finally:
            await browser.close()


# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return jsonify({
        "service": "GEDEON Renderer",
        "version": "1.0.0",
        "endpoints": {
            "GET /render": "Rendu Playwright d'une URL",
            "GET /health": "Healthcheck",
        },
        "params": {
            "url": "URL à rendre (obligatoire)",
            "wait": f"Délai JS en ms (défaut: {DEFAULT_WAIT_MS}, max: {MAX_WAIT_MS})",
            "selector": "Sélecteur CSS à attendre avant de récupérer le HTML (optionnel)",
        },
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/render")
@require_api_key
def render():
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "Paramètre 'url' requis"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL invalide — doit commencer par http:// ou https://"}), 400

    wait_ms = min(int(request.args.get("wait", DEFAULT_WAIT_MS)), MAX_WAIT_MS)
    selector = request.args.get("selector", None)

    logger.info(f"Rendu: {url} (wait={wait_ms}ms, selector={selector})")

    result = asyncio.run(render_page(url, wait_ms, selector))

    if not result["success"]:
        return jsonify(result), 502

    # On ne renvoie pas le HTML brut dans le JSON pour éviter les gros payloads
    # Claude reçoit les métadonnées + les N premiers caractères
    preview_size = int(request.args.get("preview", 50000))
    html = result.pop("html")

    result["html_preview"] = html[:preview_size]
    result["truncated"] = len(html) > preview_size

    return jsonify(result)


# ── Lancement ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)