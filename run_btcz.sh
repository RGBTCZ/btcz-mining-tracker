#!/bin/bash
# =============================================
# Run BTCZ Mining Tracker with venv
# =============================================

echo "🚀 Lancement du BTCZ Mining Tracker..."

if [ -f "venv/Scripts/activate" ]; then
    VENV_PATH="venv/Scripts/activate"
elif [ -f "../venv/Scripts/activate" ]; then
    VENV_PATH="../venv/Scripts/activate"
elif [ -f "venv/bin/activate" ]; then
    VENV_PATH="venv/bin/activate"
else
    echo "❌ Impossible de trouver le dossier venv !"
    echo ""
    echo "Vérifie que tu as bien un dossier nommé 'venv' dans :"
    echo "→ $(pwd)"
    echo ""
    ls -la
    read -p "Appuie sur Entrée pour quitter..."
    exit 1
fi

echo "🔧 Activation du venv → $VENV_PATH"
source "$VENV_PATH"

if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✅ venv activé avec succès !"
else
    echo "⚠️  Le venv n'a pas pu s'activer correctement."
fi

echo "🚀 Lancement de btcz_ui.py..."
python btcz_ui.py

echo ""
read -p "✅ Fin du script - Appuie sur Entrée pour fermer..."