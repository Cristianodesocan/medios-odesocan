#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# setup_github.sh — Configura el repo de GitHub con el pipeline de scraping
# Ejecutar desde la carpeta del pipeline:
#   chmod +x setup_github.sh && ./setup_github.sh
# ──────────────────────────────────────────────────────────────────────────────

set -e

REPO="Cristianodesocan/medios-odesocan"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Configuración del pipeline de scraping — ODESOCAN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Verificar que estamos en la carpeta correcta ─────────────────────────────
if [ ! -f "scraper.py" ] || [ ! -f "config.py" ]; then
    echo "❌ Error: ejecuta este script desde la carpeta del pipeline (donde está scraper.py)"
    exit 1
fi

# ── Verificar gh CLI ─────────────────────────────────────────────────────────
if ! command -v gh &> /dev/null; then
    echo "❌ gh CLI no está instalado. Instalando con Homebrew..."
    brew install gh
fi

# ── Verificar autenticación ──────────────────────────────────────────────────
if ! gh auth status &> /dev/null; then
    echo "⚠️  No estás autenticado en gh. Iniciando login..."
    gh auth login
fi

echo ""
echo "▶ Paso 1/3: Inicializando repositorio git..."
echo ""

# Si ya tiene .git, usarlo; si no, inicializar
if [ ! -d ".git" ]; then
    git init
    git remote add origin "https://github.com/${REPO}.git"
else
    # Asegurar que el remote apunta al repo correcto
    git remote set-url origin "https://github.com/${REPO}.git" 2>/dev/null || \
    git remote add origin "https://github.com/${REPO}.git" 2>/dev/null || true
fi

git add .
git commit -m "Migrar pipeline de scraping a GitHub Actions" || echo "(sin cambios que commitear)"

echo ""
echo "▶ Paso 2/3: Haciendo push al repositorio..."
echo ""

git branch -M main
git push --force origin main

echo ""
echo "▶ Paso 3/3: Configurando secrets de Supabase..."
echo ""

# Configurar cada secret
gh secret set SUPABASE_HOST     --repo "$REPO" --body "aws-1-eu-west-1.pooler.supabase.com"
gh secret set SUPABASE_PORT     --repo "$REPO" --body "5432"
gh secret set SUPABASE_DBNAME   --repo "$REPO" --body "postgres"
gh secret set SUPABASE_USER     --repo "$REPO" --body "postgres.kdpsjutsgvghdtzoskkg"
gh secret set SUPABASE_SSLMODE  --repo "$REPO" --body "require"
gh secret set SUPABASE_SCHEMA   --repo "$REPO" --body "medios"

# La contraseña se pide interactivamente por seguridad
echo ""
echo "🔐 Introduce la contraseña de Supabase (no se mostrará en pantalla):"
read -s SUPABASE_PW
gh secret set SUPABASE_PASSWORD --repo "$REPO" --body "$SUPABASE_PW"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ ¡Todo configurado!"
echo ""
echo "  El workflow se ejecutará automáticamente cada día a las 10:00 UTC."
echo "  Para ejecutar ahora: ve a GitHub → Actions → Run workflow"
echo ""
echo "  O ejecuta desde terminal:"
echo "    gh workflow run scraping.yml --repo $REPO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
