#!/bin/bash
# Descarga el kit sin necesidad de git ni de bajar un zip.
#
#   curl -fsSL https://raw.githubusercontent.com/nicolaspa1/claude-escritorio-tablero/main/bootstrap.sh | bash
#
# O bien: guarda este archivo y ejecútalo con  bash bootstrap.sh
# Deja el kit en ~/Desktop/kit-escritorio y no instala nada por su cuenta.
set -u
BASE="https://raw.githubusercontent.com/nicolaspa1/claude-escritorio-tablero/main"
DESTINO="${1:-$HOME/Desktop/kit-escritorio}"

ARCHIVOS=(
  "CLAUDE.md"
  "README.md"
  "PROMPT-INICIAL.md"
  "config.json"
  "instalar.sh"
  "panel/indice.py"
  "panel/tablero.py"
  "panel/tablero-app.applescript"
  "organizar/mvproj.sh"
  "organizar/GUIA.md"
)

echo "▸ Descargando el kit en $DESTINO"
mkdir -p "$DESTINO/panel" "$DESTINO/organizar" || exit 1

fallos=0
for f in "${ARCHIVOS[@]}"; do
  if curl -fsSL "$BASE/$f" -o "$DESTINO/$f"; then
    printf '  ✓ %-32s %s bytes\n' "$f" "$(wc -c < "$DESTINO/$f" | tr -d ' ')"
  else
    printf '  ✗ %-32s FALLÓ\n' "$f"
    fallos=$((fallos + 1))
  fi
done

if [ "$fallos" -gt 0 ]; then
  cat <<FIN

No se pudieron descargar $fallos archivo(s). Si tu red bloquea GitHub, abre Claude
Code en cualquier carpeta y pégale esto:

  Descarga con WebFetch cada archivo de
  $BASE/<ruta>
  para estas rutas: ${ARCHIVOS[*]}
  y escríbelos con la misma estructura de carpetas en ~/Desktop/kit-escritorio

FIN
  exit 1
fi

chmod +x "$DESTINO/instalar.sh" 2>/dev/null

cat <<FIN

Listo. El kit está en $DESTINO

Siguiente paso:
  cd $DESTINO
  bash instalar.sh                          # instala el Tablero
  claude --model sonnet --effort medium     # y pega el prompt de PROMPT-INICIAL.md

FIN
