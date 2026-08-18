# Prompt inicial

Clona el repo, abre Claude Code **dentro de la carpeta** y pega el bloque de abajo
como primer mensaje.

```bash
git clone https://github.com/nicolaspa1/claude-escritorio-tablero.git ~/Desktop/kit-escritorio
cd ~/Desktop/kit-escritorio
claude --model sonnet --effort medium
```

> Sonnet con esfuerzo medio es la mejor relación calidad/precio para esto. Si pagas
> por token, mira la sección de coste en `CLAUDE.md` antes de empezar — sobre todo
> lo de no retomar sesiones gigantes, que es lo que más presupuesto quema.

---

## Pégale esto

> Lee `CLAUDE.md` entero antes de hacer nada: lleva el método y los errores que ya
> se cometieron, no los repitas.
>
> Este es mi **computador del trabajo** y tengo el escritorio hecho un desastre, con
> muchas carpetas y muchas sesiones de Claude Code abiertas a lo largo del tiempo.
> Quiero dos cosas: **ordenarlo sin perder el contexto de ninguna conversación**, y
> dejar instalado el Tablero para poder retomar proyectos y ir borrando lo que ya no
> uso.
>
> Aquí casi todo es trabajo, así que **no me propongas categorías tipo "trabajo /
> personal / cursos"**: eso me dejaría todo en un mismo cajón. Mira lo que hay de
> verdad dentro de cada carpeta y propón los ejes que salgan del contenido (por
> cliente, por sistema, por tipo de trabajo, por estado… lo que encaje). Las
> categorías del `config.json` del repo son solo un ejemplo, no las copies.
>
> Empieza así, y **no muevas nada hasta que yo apruebe el plan**:
>
> 1. Inventaría el escritorio: qué hay, cuánto pesa, qué tiene sesiones de Claude y
>    de cuándo son. Para cada carpeta averigua qué es realmente mirando dentro, no
>    por el nombre.
> 2. Dime qué encontraste y propón una estructura, con el mapeo completo de origen →
>    destino y qué sugieres borrar o archivar, explicando por qué.
> 3. Cuando yo te diga que sí: crea las carpetas, mueve primero lo que no tiene
>    sesiones y después lo que sí, con `mvproj` para no romper `claude --resume`.
>    Antes de mover cada cosa, comprueba que no tenga una sesión abierta dentro.
> 4. Verifica de verdad que el contexto vuelve: entra en dos o tres proyectos
>    movidos y comprueba que la conversación se recupera.
> 5. Instala el Tablero (`bash instalar.sh`), escribe mis categorías en
>    `~/.panel/config.json` y rellena `~/.panel/notas.json` con una frase por
>    proyecto para que el índice nazca documentado.
>
> Al terminar, dime qué quedó, qué no pudiste mover y por qué, y qué me conviene
> revisar a mano.

---

## Si prefieres ir por partes

**Solo el tablero, sin reorganizar nada:**

> Lee `CLAUDE.md` y hazme solo la instalación del Tablero: `bash instalar.sh`,
> y ayúdame a escribir mis categorías en `~/.panel/config.json` mirando lo que
> tengo en el escritorio. No muevas ninguna carpeta.

**Solo el inventario, para decidir después:**

> Lee `CLAUDE.md` y hazme solo la fase 1: dime qué hay en mi escritorio, qué pesa,
> qué tiene sesiones de Claude y qué es cada carpeta de verdad. No propongas
> estructura todavía ni muevas nada.

**Ya está organizado y solo quiero limpiar:**

> Lee `CLAUDE.md`, instala el Tablero y ayúdame a identificar qué proyectos llevo
> meses sin tocar y cuáles no tienen ya sesiones, para ir borrándolos desde el
> tablero.

---

## Lo único que debes tener presente

Claude Code encuentra las conversaciones por la **ruta** de la carpeta. Si mueves
una carpeta sin renombrar su carpeta de sesiones, `--resume` deja de encontrar el
historial. Por eso todo se mueve con `organizar/mvproj.sh`, y nunca con una sesión
abierta dentro.

Si algo sale mal, nada se borra de forma definitiva: los borrados del tablero van a
la Papelera y quedan registrados en `~/.panel/borrados.log`.
