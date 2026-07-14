#!/usr/bin/env bash
# Installa il widget Low-Freq Hunter nella cartella plugin di SwiftBar.
# Crea un symlink (così un git pull aggiorna il widget senza reinstallare) e
# lo rende eseguibile.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/lowfreq.10s.py"

echo "Low-Freq Hunter · installazione widget menu bar"
echo

# 1) SwiftBar presente?
if ! open -Ra SwiftBar 2>/dev/null && ! command -v swiftbar >/dev/null 2>&1; then
  echo "⚠  SwiftBar non risulta installato."
  echo "   Installalo con:  brew install swiftbar"
  echo "   poi rilancia questo script."
  exit 1
fi

# 2) Python 3 presente?
if ! command -v python3 >/dev/null 2>&1; then
  echo "⚠  python3 non trovato. Installa gli strumenti da riga di comando:"
  echo "   xcode-select --install     (oppure  brew install python)"
  exit 1
fi

# 3) trova la cartella plugin di SwiftBar (dalle preferenze, con fallback)
PLUGIN_DIR="$(defaults read com.ambar.SwiftBar PluginDirectory 2>/dev/null || true)"
if [ -z "${PLUGIN_DIR:-}" ]; then
  PLUGIN_DIR="$HOME/Documents/SwiftBar"
  echo "Cartella plugin di SwiftBar non ancora impostata."
  echo "Uso il default: $PLUGIN_DIR"
  echo "(se in SwiftBar ne hai scelta un'altra, spostaci il file o rilancia)"
fi
mkdir -p "$PLUGIN_DIR"

# 4) symlink + permessi
chmod +x "$SRC"
ln -sf "$SRC" "$PLUGIN_DIR/lowfreq.10s.py"

echo
echo "✓ installato: $PLUGIN_DIR/lowfreq.10s.py → $SRC"
echo
echo "Ora:"
echo "  1. apri (o riavvia) SwiftBar"
echo "  2. dal menu del widget scegli \"configura…\" e imposta i telefoni"
