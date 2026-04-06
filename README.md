# GEDEON Renderer

Micro-service Flask + Playwright qui expose un endpoint HTTP permettant
de récupérer le HTML rendu (après exécution JS) de n'importe quelle URL.

Conçu pour être appelé par Claude via `web_fetch` depuis claude.ai.

---

## Déploiement sur Render

### 1. Créer un repo GitHub

```bash
git init
git add .
git commit -m "init gedeon-renderer"
git remote add origin https://github.com/ton-compte/gedeon-renderer.git
git push -u origin main
```

### 2. Créer le service sur Render

- Aller sur https://dashboard.render.com
- **New → Web Service → Connect a repository**
- Sélectionner `gedeon-renderer`
- Runtime : **Docker** (détecté automatiquement via Dockerfile)
- Plan : **Starter** (512MB RAM minimum pour Chromium)
- Region : **Frankfurt** (EU)

### 3. Variables d'environnement

Dans Render → Environment :

| Variable | Valeur |
|---|---|
| `RENDERER_API_KEY` | Générer une clé forte (ex: `openssl rand -hex 32`) |

### 4. Récupérer l'URL et la clé

Après déploiement, Render te donne une URL du type :
```
https://gedeon-renderer.onrender.com
```

Note bien la valeur de `RENDERER_API_KEY` — tu en auras besoin pour appeler le service.

---

## Utilisation

### Appel basique

```bash
curl "https://gedeon-renderer.onrender.com/render?url=https://fise.fr/fr/evenements" \
  -H "X-API-Key: ta-clé"
```

### Avec attente d'un sélecteur CSS

```bash
curl "https://gedeon-renderer.onrender.com/render?url=https://festival-avignon.com/fr/edition-2026/programmation/par-date&selector=.show-card&wait=5000" \
  -H "X-API-Key: ta-clé"
```

### Paramètres

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `url` | string | — | URL à rendre **(obligatoire)** |
| `wait` | int (ms) | 2000 | Délai après chargement JS |
| `selector` | string | — | Sélecteur CSS à attendre |
| `preview` | int | 50000 | Taille max du HTML renvoyé (en caractères) |

### Réponse

```json
{
  "success": true,
  "url": "https://fise.fr/fr/evenements",
  "title": "Events | FISE",
  "html_preview": "<!DOCTYPE html>...",
  "html_length": 142853,
  "truncated": true
}
```

---

## Utilisation depuis Claude

Donne à Claude l'URL et la clé, il appellera directement le service :

> "Utilise le renderer sur https://gedeon-renderer.onrender.com avec la clé XXX
> pour crawler https://fise.fr/fr/evenements"

Claude fera :
```
web_fetch("https://gedeon-renderer.onrender.com/render?url=https://fise.fr/fr/evenements",
          headers={"X-API-Key": "XXX"})
```

---

## Notes importantes

- **Plan Starter minimum** : Chromium a besoin de ~400MB RAM. Le plan Free (256MB) est insuffisant.
- **Cold start** : Le service s'endort après 15min d'inactivité sur Render. Premier appel ~30s.
- **1 worker** : Playwright est synchrone par nature sur ce setup — les requêtes sont traitées séquentiellement.
- **Timeout** : 60s max par rendu. Les sites très lents peuvent échouer.
- **`--single-process`** : flag Chromium nécessaire sur les environnements Docker sans accès aux namespaces kernel (cas Render).
