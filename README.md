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
