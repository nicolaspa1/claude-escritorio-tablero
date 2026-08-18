# Organizar el escritorio sin perder las sesiones de Claude + instalar el Tablero

Este repo reproduce un trabajo ya hecho y probado en otra máquina: ordenar un
escritorio con decenas de carpetas **sin romper `claude --resume`**, y dejar
instalado un tablero para retomar conversaciones, crear proyectos nuevos en el
sitio correcto e ir limpiando lo que ya no se usa.

Lee este archivo entero antes de tocar nada.

---

## Regla número uno: de dónde salen las categorías

**No copies la estructura del ejemplo.** El `config.json` que viene incluido son
categorías de muestra; existen para que el instalador no falle, no para que las
adoptes.

Las categorías se deducen **de lo que hay en ESTA máquina**. En un ordenador de
trabajo casi todo es trabajo, así que dividir en "trabajo / personal / cursos" no
sirve de nada: dejaría el 95% en un solo cajón. Hay que bajar un nivel y encontrar
los ejes reales, que suelen ser alguno de estos:

- por **cliente o cuenta** (si se trabaja para varios)
- por **producto o sistema** (si es un equipo de plataforma)
- por **tipo de trabajo**: código, documentación, investigación, presentaciones
- por **estado**: activo ahora / referencia / cerrado

La forma correcta de decidirlo es mirar el contenido primero (fase 1) y proponer la
estructura después (fase 2), no al revés. Y proponer **antes de mover nada**,
enseñándole al usuario el mapeo completo para que lo apruebe.

---

## Lo que hay que entender antes de mover una sola carpeta

Claude Code guarda cada conversación en una carpeta cuyo nombre es **la ruta
absoluta del proyecto con los separadores convertidos en guiones**. `/`, `_` y `.`
se convierten en `-`:

```
~/Desktop/mi_proyecto   →  ~/.claude/projects/-Users-<usuario>-Desktop-mi-proyecto
~/Desktop/a/b           →  ~/.claude/projects/-Users-<usuario>-Desktop-a-b
```

Por eso **mover una carpeta rompe `claude --resume`**: Claude busca por la ruta
nueva y no encuentra nada. El historial no se borra, queda huérfano.

La solución es mover la carpeta **y renombrar a la vez su carpeta de sesiones**, y
las de sus subcarpetas. Está implementado:

```bash
source organizar/mvproj.sh
mvproj  carpeta_vieja  01-loquesea/nombre-nuevo
```

Reglas que no se pueden saltar:

- **Nunca muevas una carpeta con una sesión de Claude abierta dentro.** Compruébalo:
  ```bash
  for pid in $(pgrep -f '(^|/)claude($| )'); do
    lsof -a -p $pid -d cwd -Fn 2>/dev/null | grep '^n' | cut -c2-
  done | sort -u
  ```
- Las sesiones **caducan a los ~30 días**. Si una carpeta muestra 0 sesiones puede
  ser que existieran y expiraran: no es un fallo tuyo.
- La codificación **no es reversible**. Para saber a qué carpeta pertenece una
  sesión, codifica las rutas reales y compara; no intentes decodificar el nombre.

---

## Fase 1 — Entender qué hay

```bash
ls -la ~/Desktop
du -sh ~/Desktop/*/ | sort -h            # qué pesa
ls ~/.claude/projects/                   # qué tiene sesiones
```

Para cada carpeta, averigua **qué es de verdad**: su `README.md`, `CLAUDE.md`,
`package.json`, `pom.xml`, o los tipos de archivo que contiene. **No te fíes del
nombre.** En el escritorio original, una carpeta llamada `fondo` resultaba ser los
fondos para grabar los vídeos de un curso, y `vinilos` era investigación sobre la
pared del set. Las dos parecían basura y no lo eran.

Si el nombre no dice nada y tiene sesiones, lee la primera pregunta real del
usuario en el transcript:

```bash
python3 -c "
import json,glob,sys
for f in glob.glob(sys.argv[1]+'/*.jsonl'):
    for line in open(f):
        d=json.loads(line)
        c=d.get('message',{}).get('content')
        if d.get('type')=='user' and isinstance(c,str) and 'local-command' not in c and len(c)>40:
            print(c[:300]); break
    break" ~/.claude/projects/<carpeta>
```

Esto es lo que más cambia el resultado: clasificar por lo que la carpeta **es**, no
por cómo se llama.

## Fase 2 — Proponer la estructura

Pocas categorías (4 a 7), nombres consistentes, prefijo numérico para fijar el
orden en Finder. Enséñale al usuario el árbol y el **mapeo completo origen →
destino** antes de mover nada, incluyendo qué se borraría y por qué.

Si el usuario quiere pensarlo bien, funciona lanzar dos agentes con enfoques
distintos (uno por dominio, otro por ciclo de vida) y un tercero que puntúe con
rúbrica: completitud, seguridad, usabilidad real, simplicidad y pragmatismo. Así se
hizo el original, y la síntesis de las dos propuestas superó a cualquiera sola.

Cuando esté acordada, escríbela en `~/.panel/config.json`: de ahí saca el tablero
las categorías y sus descripciones. **Las descripciones importan mucho**, porque son
lo que Claude lee para decidir dónde va cada cosa nueva. Si escribes que una
categoría es "solo microservicios de pagos", una charla técnica interna acabará
clasificada en el sitio equivocado.

## Fase 3 — Mover, en dos tandas

1. **Primero lo que NO tiene sesiones**: es un `mv` normal, sin riesgo.
2. **Después lo que sí las tiene**, con `mvproj`.

Después de mover, **verifica que el contexto vuelve de verdad**. Que la carpeta esté
en su sitio no demuestra nada:

```bash
cd ~/Desktop/<ruta-nueva>
claude --continue -p "En una linea: de que trata esta conversacion?"
```

- Responde con el contenido → funcionó.
- *"Prompt is too long"* → **también funcionó**: encontró la sesión, pero es enorme
  para ese modelo. Repite con `--model sonnet` o superior.
- *"aún no hay conversación"* → `--continue` cogió una sesión vacía (coge la más
  reciente). Usa `claude --resume` y elige de la lista.

Comprueba dos o tres, no lo des por hecho.

## Fase 4 — Limpiar y documentar

- Poda `node_modules` antes de mover repos grandes (vuelve con `npm install`).
- Material pesado e inactivo: candidato a disco externo, **no a borrar**.
- Borra solo lo verificado: carpetas vacías, duplicados comprobados con `md5`.
- Rellena `~/.panel/notas.json` con una frase por proyecto, para que el índice nazca
  documentado en vez de decir "43 archivos (2M)".

---

## El Tablero

```bash
bash instalar.sh
```

Idempotente: no borra ni mueve nada.

| Pieza | Para qué |
|---|---|
| `~/.panel/indice.py` | Escanea el escritorio, lo cruza con las sesiones y genera el índice |
| `~/.panel/tablero.py` | Sirve el tablero en `127.0.0.1:7373` y lo escribe como HTML estático |
| `~/Desktop/Tablero.app` | Doble clic: arranca el servidor y abre el navegador |
| `~/.panel/config.json` | **Las categorías**: id, icono, descripción, si se expande |
| `~/.panel/notas.json` | Descripciones curadas por ruta; sobreviven a cada refresco |
| `~/.panel/PENDIENTES.md` | Lista de tareas, editable desde el tablero |

Qué se puede hacer desde la página: ver la conversación en curso arriba del todo y
volver a ella; retomar cualquier conversación por su título; dejar una nota de "por
dónde iba"; fijar conversaciones en secciones propias; crear archivos, carpetas o
proyectos describiendo con palabras lo que vas a hacer (Claude propone tipo, nombre
y sitio); mandar a la papelera lo que sobra; y organizar lo que quede suelto.

El servidor escucha **solo en 127.0.0.1**. Los borrados van a `~/.Trash`, nunca `rm`,
y quedan registrados en `~/.panel/borrados.log`.

---

## Errores ya cometidos — no repetirlos

**launchd no puede leer `~/Desktop`.** Un LaunchAgent para refrescar el tablero
falló en silencio durante un mes con `Operation not permitted`: es la protección TCC
de macOS. Por eso el refresco va en un hook de `.zshrc`, que hereda el permiso de la
terminal. Si automatizas algo que lea Desktop, Documents o Downloads, no uses
launchd.

**Un error de sintaxis en el JavaScript deja la página muerta y muda.** Todos los
botones dejan de responder sin ningún aviso, y el HTML se ve perfecto. Comprobar el
HTML NO basta. Después de tocar `tablero.py`, siempre:

```bash
curl -s http://127.0.0.1:7373/ | python3 -c "import re,sys;open('/tmp/t.js','w').write(re.search(r'<script>(.*?)</script>',sys.stdin.read(),re.S).group(1))"
node --check /tmp/t.js
```

Para botones generados desde JavaScript, nada de `onclick` en línea: `data-*` y
`addEventListener`. Y al inyectar valores en atributos, `html.escape(json.dumps(v),
quote=True)`.

**Dos procesos escribiendo el mismo JSON lo corrompen.** Pasó con `estado.json` y la
regeneración empezó a fallar en silencio. Escribe a un temporal y renombra con
`os.replace`; y tolera un JSON roto reconstruyéndolo en vez de reventar.

**`slug()` es solo para nombres NUEVOS.** Una subcarpeta destino es una ruta que ya
existe: puede llevar mayúsculas y varios niveles (`estudio/Idiomas`). Pasarla por
slug convertía las barras en guiones y rompía la creación con un "no existe".

**Nada de rutas atadas a un usuario.** El filtro de sesiones llegó a tener escrito
`-Users-<alguien>-Desktop`; en otra máquina no mostraba ninguna conversación. Se
calcula con `encode(DESKTOP)`.

**Un escaneo completo tarda ~15 s** (du + find sobre decenas de GB). El servidor lo
cachea en memoria; solo "Actualizar índice" reescanea, y al borrar se quita la fila
del caché. Al recorrer el escritorio, poda `node_modules` y limita la profundidad:
sin eso tardaba 34 s en vez de 0,1.

**Toda acción debe reescribir también los archivos de salida.** Si el HTML estático
no se regenera, el usuario ve fantasmas de lo que ya borró y cree que nada funciona.

**No escondas el formulario de crear detrás del botón de proponer.** La propuesta
debe rellenar el formulario, nunca ser el único camino para llegar a él.

---

## Cómo saber que quedó bien

```bash
python3 ~/.panel/indice.py     # cuántos proyectos y cuántos conservan sesiones
open ~/Desktop/Tablero.app     # que abra y muestre la conversación en curso
cd ~/Desktop/<algo-movido> && claude --continue -p "de que trata esta conversacion?"
```

Lo que de verdad importa no es que el escritorio se vea ordenado, sino que el
usuario pueda abrir cualquier proyecto y **recuperar su contexto**.
