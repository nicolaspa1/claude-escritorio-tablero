# Chuleta de comandos

## Ver qué hay antes de tocar nada

```bash
ls -la ~/Desktop                          # qué hay suelto
du -sh ~/Desktop/*/ | sort -h             # qué pesa
ls ~/.claude/projects/                    # qué carpetas tienen sesiones
```

Sesiones con su tamaño y fecha (los nombres empiezan por `-`, de ahí el `./`):

```bash
bash -c 'shopt -s nullglob; cd ~/.claude/projects
for d in */; do d=${d%/}; f=(./"$d"/*.jsonl); [ ${#f[@]} -eq 0 ] && continue
  echo "$(du -ch "${f[@]}" | tail -1 | cut -f1)  ${#f[@]}x  $d"; done | sort -rh'
```

## Antes de mover: ¿hay alguna sesión abierta?

```bash
for pid in $(pgrep -f '(^|/)claude($| )'); do
  lsof -a -p $pid -d cwd -Fn 2>/dev/null | grep '^n' | cut -c2-
done | sort -u
```

Si una carpeta aparece aquí, **no la muevas**: cierra esa sesión primero.

## Mover sin perder el contexto

```bash
source organizar/mvproj.sh
mvproj  carpeta_vieja  01-clientes/nombre-nuevo
```

Mueve la carpeta y renombra su carpeta de sesiones y las de sus subcarpetas.
Dice cuántas reubicó.

## Comprobar que el contexto volvió

```bash
cd ~/Desktop/01-clientes/nombre-nuevo
claude --continue -p "En una linea: de que trata esta conversacion?"
```

- Responde con el contenido → funcionó.
- *"Prompt is too long"* → **también funcionó**: encontró la sesión pero es enorme.
  Repite con `--model sonnet` o superior.
- *"aún no hay conversación"* → `--continue` cogió una sesión vacía; usa
  `claude --resume` y elige de la lista.

## Recuperar espacio

```bash
find ~/Desktop -type d -name node_modules -prune | xargs du -sh | sort -h
find ~/Desktop -type d -name node_modules -prune -exec rm -rf {} +   # se restaura con npm install
```

## Refrescar el tablero

```bash
indice     # solo el markdown
refresh    # markdown + HTML
tablero    # servidor con botones
```

## Si tocas tablero.py, valida el JavaScript

```bash
curl -s http://127.0.0.1:7373/ | python3 -c "import re,sys;open('/tmp/t.js','w').write(re.search(r'<script>(.*?)</script>',sys.stdin.read(),re.S).group(1))"
node --check /tmp/t.js
```

Un error de sintaxis deja **todos** los botones muertos sin ningún aviso.
