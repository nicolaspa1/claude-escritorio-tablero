# Kit escritorio + Tablero para Claude Code

Ordena el escritorio de macOS **sin perder las sesiones de Claude Code**, y deja
instalado un tablero para retomar conversaciones, crear proyectos en el sitio
correcto e ir limpiando lo que ya no usas.

## Empezar

```bash
git clone https://github.com/nicolaspa1/claude-escritorio-tablero.git ~/Desktop/kit-escritorio
cd ~/Desktop/kit-escritorio
claude
```

Y pega el prompt de **[PROMPT-INICIAL.md](PROMPT-INICIAL.md)**.

Si solo quieres el tablero, sin reorganizar nada:

```bash
bash instalar.sh
```

Copia los scripts a `~/.panel`, compila `Tablero.app` en el escritorio y añade los
comandos `tablero`, `indice` y `refresh`. No borra ni mueve nada, y puedes repetirlo.
Luego edita `~/.panel/config.json` con tus categorías.

La primera vez que abras `Tablero.app`, macOS pedirá permiso para leer el Escritorio:
acéptalo o el tablero no verá nada. El primer arranque tarda ~15 s escaneando.

## Qué hace el tablero

- La **conversación en curso** arriba del todo, con lo último que escribiste y un
  botón para volver a ella.
- **Retomar** cualquier conversación por su título, con notas de "por dónde iba".
- **Crear** archivos, carpetas o proyectos describiendo con palabras lo que vas a
  hacer: Claude propone el tipo, el nombre y dónde va.
- **Limpiar**: manda a la Papelera lo que sobra y ordena lo que quede suelto.
- Indicadores de sobrecarga del escritorio, pendientes y espacio en disco.

## Dónde queda cada cosa

Nada de esto ensucia el escritorio: ahí solo aparece `Tablero.app`.

| Archivo | Qué es |
|---|---|
| `~/.panel/TABLERO.html` | La última foto del tablero. Es lo que abre la app mientras arranca el servidor |
| `~/.panel/INDICE_PROYECTOS.md` | El índice en markdown, para leerlo o pasárselo a Claude |
| `~/.panel/PENDIENTES.md` | Tus pendientes (también se editan desde el tablero) |
| `~/.panel/notas.json` | Las descripciones de cada proyecto |
| `~/.panel/borrados.log` | Qué se mandó a la Papelera y cuándo |

**Cuándo se refresca:** al abrir una terminal (máximo una vez al día), cada vez que
haces algo en el tablero (crear, borrar, mover, marcar un pendiente) y cuando pulsas
«Actualizar índice». A mano: `refresh`.

Si abres `Tablero.app` y ves datos viejos, es la foto: espera unos segundos a que
arranque el servidor y la página salta sola a la versión en vivo.

## Qué modelo usar y cuánto cuesta

```bash
claude --model sonnet --effort medium
```

**Sonnet** es la mejor relación calidad/precio aquí: el trabajo es leer carpetas y
mover archivos, mucho volumen y poca dificultad conceptual. Haiku se queda corto
como modelo principal (falla más al juzgar qué es cada carpeta, y tiene menos
contexto); Opus cuesta unas 2,5 veces más sin aportar lo suficiente en esta tarea —
súbelo solo para decidir la estructura, y vuelve a Sonnet para ejecutar.

Referencia por millón de tokens (entrada/salida): Haiku 4.5 $1/$5 · Sonnet 5 $3/$15
· Opus 4.8 $5/$25.

**Si pagas por token**, las tres palancas, en orden de impacto:

1. **`--effort medium`** — va en `high` por defecto; mover archivos no lo necesita.
2. **No retomes sesiones gigantes** — cada turno reenvía todo el historial, así que
   un `--resume` sobre cientos de MB se dispara. Mira el tamaño primero (comando en
   `CLAUDE.md`) y para las grandes empieza conversación nueva.
3. **`--max-budget-usd`** — tope duro, pero solo junto con `--print`.

El tablero usa **Haiku** por dentro para clasificar y proponer nombres: respuestas
cortas en JSON, céntimos por clic.

Si al retomar una conversación grande sale *"Prompt is too long"*, no está rota:
repite con `--model sonnet` o superior.

## Qué hay aquí

```
PROMPT-INICIAL.md        el prompt que le pegas a Claude
CLAUDE.md                el método completo y los errores ya cometidos
instalar.sh              instalador idempotente
config.json              categorías de EJEMPLO (no las copies: ver CLAUDE.md)
panel/                   los tres scripts del tablero
organizar/mvproj.sh      mover una carpeta renombrando sus sesiones de Claude
organizar/GUIA.md        chuleta de comandos
```

## Requisitos

macOS, `python3` 3.9+ (vale el del sistema) y Claude Code. Sin Claude solo pierdes
las propuestas automáticas; el resto funciona.

## Lo importante

Claude Code localiza las conversaciones por la **ruta** de la carpeta:
`~/Desktop/mi_proyecto` vive en `~/.claude/projects/-Users-<usuario>-Desktop-mi-proyecto`.
Mover una carpeta sin renombrar esa carpeta de sesiones rompe `claude --resume`. Por
eso todo se mueve con `mvproj`, que hace las dos cosas a la vez.

Nada se borra de forma definitiva: los borrados van a la Papelera y quedan
registrados en `~/.panel/borrados.log`.
