"""
GEDEON Renderer — Service de rendu Playwright pour GEDEON
Expose un endpoint HTTP que Claude peut appeler via web_fetch.

Endpoints:
  GET  /render?url=<url>&wait=<ms>&selector=<css>&intercept=true
  GET  /health
  GET  /

Auth: X-API-Key header ou ?key= query param
"""

import os
import asyncio
import logging
from functools import wraps

from flask import Flask, request, jsonify
from playwright.async_api import async_playwright

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("RENDERER_API_KEY", "Gedeon2026Liza")
DEFAULT_WAIT_MS = 2000
MAX_WAIT_MS = 15000
DEFAULT_TIMEOUT_MS = 30000

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Auth ─────────────────────────────────────────────────────────────────────
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "") or request.args.get("key", "")
        if not API_KEY:
            logger.warning("RENDERER_API_KEY non definie — auth desactivee")
        elif key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Rendu Playwright ─────────────────────────────────────────────────────────
async def render_page(url, wait_ms, selector, intercept=False):
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
                "--single-process",
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

        api_calls = []
        if intercept:
            async def handle_request(req):
                if req.resource_type in ("xhr", "fetch"):
                    api_calls.append({
                        "url": req.url,
                        "method": req.method,
                        "type": req.resource_type,
                    })
            page.on("request", handle_request)

        try:
            await page.goto(url, timeout=DEFAULT_TIMEOUT_MS, wait_until="domcontentloaded")

            if selector:
                try:
                    await page.wait_for_selector(selector, timeout=wait_ms)
                except Exception:
                    logger.warning(f"Selecteur '{selector}' non trouve dans {wait_ms}ms")
            else:
                await page.wait_for_timeout(wait_ms)

            html = await page.content()
            title = await page.title()
            final_url = page.url

            result = {
                "success": True,
                "url": final_url,
                "title": title,
                "html": html,
                "html_length": len(html),
            }
            if intercept:
                result["api_calls"] = api_calls
            return result

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
        "version": "1.1.0",
        "params": {
            "url": "URL a rendre (obligatoire)",
            "wait": f"Delai JS en ms (defaut: {DEFAULT_WAIT_MS}, max: {MAX_WAIT_MS})",
            "selector": "Selecteur CSS a attendre (optionnel)",
            "intercept": "true = capturer les requetes XHR/fetch (optionnel)",
            "preview": "Taille max HTML renvoye en caracteres (defaut: 50000)",
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
        return jsonify({"error": "Parametre 'url' requis"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "URL invalide"}), 400

    wait_ms = min(int(request.args.get("wait", DEFAULT_WAIT_MS)), MAX_WAIT_MS)
    selector = request.args.get("selector", None)
    intercept = request.args.get("intercept", "false").lower() == "true"

    logger.info(f"Rendu: {url} (wait={wait_ms}ms, intercept={intercept})")

    result = asyncio.run(render_page(url, wait_ms, selector, intercept))

    if not result["success"]:
        return jsonify(result), 502

    preview_size = int(request.args.get("preview", 50000))
    html = result.pop("html")
    result["html_preview"] = html[:preview_size]
    result["truncated"] = len(html) > preview_size

    return jsonify(result)


# ── Lancement ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)


# ── Proxy fetch avec headers custom ─────────────────────────────────────────
import json
import urllib.request

@app.route("/fetch")
@require_api_key
def proxy_fetch():
    """
    Fait un GET/POST HTTP avec headers custom vers une URL cible.
    Params:
      url     : URL cible (obligatoire)
      method  : GET ou POST (defaut: GET)
      headers : JSON string des headers (optionnel)
      body    : body pour POST (optionnel)
    """
    target_url = request.args.get("url", "").strip()
    if not target_url:
        return jsonify({"error": "Parametre 'url' requis"}), 400

    method = request.args.get("method", "GET").upper()
    headers_raw = request.args.get("headers", "{}")
    body_raw = request.args.get("body", None)

    try:
        headers = json.loads(headers_raw)
    except Exception:
        headers = {}

    try:
        req = urllib.request.Request(target_url, method=method)
        for k, v in headers.items():
            req.add_header(k, v)

        if body_raw and method == "POST":
            req.data = body_raw.encode("utf-8")
            if "Content-Type" not in headers:
                req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return jsonify({
                "success": True,
                "status": resp.status,
                "url": target_url,
                "content": content[:50000],
                "truncated": len(content) > 50000,
            })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 502