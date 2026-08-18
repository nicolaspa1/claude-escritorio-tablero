#!/bin/bash
# Instala el Tablero del escritorio en esta máquina.
#   bash instalar.sh
# No borra ni mueve nada: solo copia los scripts, compila la app y añade
# tres funciones al shell. Es idempotente: puedes volver a ejecutarlo.
set -u
AQUI="$(cd "$(dirname "$0")" && pwd)"
DESTINO="$HOME/.panel"
ESCRITORIO="$HOME/Desktop"

echo "▸ Instalando en $DESTINO"
mkdir -p "$DESTINO"
cp "$AQUI/panel/indice.py" "$AQUI/panel/tablero.py" "$AQUI/panel/tablero-app.applescript" "$DESTINO/"

# --- configuración de categorías -------------------------------------------
if [ ! -f "$DESTINO/config.json" ]; then
  if [ -f "$AQUI/config.json" ]; then
    cp "$AQUI/config.json" "$DESTINO/config.json"
    echo "  · config.json copiado del kit"
  else
    cat > "$DESTINO/config.json" <<'JSON'
{
 "categorias": [
  {"id": "01-clientes",  "icono": "🏦", "expandir": true,
   "que_es": "proyectos por cliente o cuenta"},
  {"id": "02-interno",   "icono": "🛠", "expandir": true,
   "que_es": "trabajo interno del equipo: herramientas, procesos, documentación"},
  {"id": "03-formacion", "icono": "📚", "expandir": true,
   "que_es": "cursos, charlas y material de formación"},
  {"id": "04-personal",  "icono": "🏠", "expandir": false,
   "que_es": "cosas propias que no son del trabajo"},
  {"id": "05-archivo",   "icono": "🗄", "expandir": false,
   "que_es": "material cerrado que ya no se trabaja, solo se consulta"}
 ],
 "protegidos": ["Tablero.app"]
}
JSON
    echo "  · config.json de ejemplo creado — EDÍTALO antes de organizar"
  fi
else
  echo "  · config.json ya existía, no se toca"
fi

[ -f "$DESTINO/notas.json" ]     || echo '{}' > "$DESTINO/notas.json"
[ -f "$DESTINO/PENDIENTES.md" ]  || printf '# ✅ Pendientes\n\n## 🔴 Alta\n\n## 🟡 Media\n\n## 🟢 Baja\n' > "$DESTINO/PENDIENTES.md"

# --- app del escritorio -----------------------------------------------------
echo "▸ Compilando Tablero.app"
rm -rf "$ESCRITORIO/Tablero.app"
if osacompile -o "$ESCRITORIO/Tablero.app" "$DESTINO/tablero-app.applescript" 2>/dev/null; then
  ICONO=/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/SmartFolderIcon.icns
  [ -f "$ICONO" ] && cp "$ICONO" "$ESCRITORIO/Tablero.app/Contents/Resources/applet.icns"
  touch "$ESCRITORIO/Tablero.app"
  echo "  · Tablero.app creado en el escritorio"
else
  echo "  ! No se pudo compilar la app; usarás el comando 'tablero'"
fi

# --- funciones de shell -----------------------------------------------------
PERFIL="$HOME/.zshrc"
if ! grep -q 'panel/tablero.py' "$PERFIL" 2>/dev/null; then
  cat >> "$PERFIL" <<'SHELL'

# --- tablero del escritorio ---
tablero(){ python3 ~/.panel/tablero.py; }   # servidor local + navegador
indice(){ python3 ~/.panel/indice.py; }     # solo el markdown del índice
refresh(){ python3 ~/.panel/indice.py; python3 ~/.panel/tablero.py --html; }
if [ -f ~/.panel/tablero.py ]; then
  if [ ! -f ~/.panel/TABLERO.html ] || [ -n "$(find ~/.panel/TABLERO.html -mtime +1 2>/dev/null)" ]; then
    (python3 ~/.panel/indice.py >/dev/null 2>&1; python3 ~/.panel/tablero.py --html >/dev/null 2>&1 &)
  fi
fi
SHELL
  echo "▸ Funciones añadidas a $PERFIL (tablero · indice · refresh)"
else
  echo "▸ Las funciones ya estaban en $PERFIL"
fi

# --- comprobaciones ---------------------------------------------------------
echo "▸ Comprobando"
python3 -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" \
  && echo "  · python3 $(python3 -V 2>&1 | cut -d' ' -f2) OK" \
  || echo "  ! Necesitas python3 3.9 o superior"
command -v claude >/dev/null \
  && echo "  · claude encontrado en $(command -v claude)" \
  || echo "  ! No encuentro 'claude': las propuestas automáticas no funcionarán"

cat <<FIN

Listo. Siguiente paso:

  1. Revisa  ~/.panel/config.json  y pon TUS categorías.
  2. Abre una terminal nueva (o ejecuta:  source ~/.zshrc )
  3. Doble clic en Tablero.app, o escribe:  tablero
     La primera vez macOS pedirá permiso para leer el Escritorio: acéptalo.

Para organizar el escritorio, abre Claude en la carpeta del kit y dile:
  "lee CLAUDE.md y ayúdame a organizar el escritorio"

FIN
