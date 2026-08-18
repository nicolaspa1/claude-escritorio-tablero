#!/usr/bin/env python3
"""Tablero interactivo del escritorio: índice de proyectos con acciones.

  tablero          → levanta el servidor local y abre el navegador (botones vivos)
  tablero --html   → escribe ~/Desktop/TABLERO.html estático (botones inertes)

El servidor escucha SOLO en 127.0.0.1 (nadie de fuera lo alcanza) y expone dos
acciones: refrescar el índice y mandar una carpeta a la Papelera (nunca borra
de forma definitiva; todo queda en ~/.Trash y en ~/.panel/borrados.log).
"""
import html as H
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".panel"))
import indice as idx  # noqa: E402

HOME = Path.home()
DESKTOP = (HOME / "Desktop").resolve()
LOG = HOME / ".panel" / "borrados.log"
PEND = HOME / ".panel" / "PENDIENTES.md"
PUERTO = 7373
ICONO = idx.ICONO

# ---------------------------------------------------------------- seguridad
CATEGORIA = re.compile(r"^0\d-[^/]+$")


def ruta_segura(rel: str) -> Path:
    """Valida que `rel` sea una carpeta borrable dentro del escritorio."""
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise ValueError("ruta inválida")
    p = (DESKTOP / rel).resolve()
    if p == DESKTOP or DESKTOP not in p.parents:
        raise ValueError("fuera del escritorio")
    if CATEGORIA.match(rel):
        raise ValueError("no se puede borrar una categoría entera")
    if Path(rel).parts[0] in idx.PROTEGIDOS:
        raise ValueError(f"«{Path(rel).parts[0]}» está protegido")
    if not p.exists():
        raise ValueError("no existe")
    return p


def a_papelera(p: Path) -> Path:
    destino = HOME / ".Trash" / p.name
    i = 1
    while destino.exists():
        destino = HOME / ".Trash" / f"{p.name} {i}"
        i += 1
    shutil.move(str(p), str(destino))
    with LOG.open("a") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{p}\t→\t{destino}\n")
    return destino


CATEGORIAS = idx.CATEGORIAS          # se definen en ~/.panel/config.json

PLANTILLA_CLAUDE = """# {nombre}

{descripcion}

## Contexto
<!-- Para qué es este proyecto, quién es el cliente/usuario, qué hay que lograr. -->

## Cómo trabajar aquí
<!-- Comandos, convenciones, dónde está lo importante. -->

## Estado
- Creado el {fecha} desde el Tablero del escritorio.
"""


def slug(texto: str) -> str:
    """'Finanzas Personales 2026' → 'finanzas-personales-2026' (convención del escritorio)."""
    t = texto.strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                 ("ñ", "n"), ("ü", "u")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:60]


def crear_carpeta(nombre, categoria, con_claude, descripcion=""):
    """Crea la carpeta en su categoría; si es proyecto de Claude, deja un CLAUDE.md."""
    if categoria not in CATEGORIAS:
        raise ValueError("categoría desconocida")
    s = slug(nombre)
    if not s:
        raise ValueError("el nombre no puede quedar vacío")
    destino = (DESKTOP / categoria / s).resolve()
    if destino.parent != (DESKTOP / categoria).resolve():   # cinturón y tirantes
        raise ValueError("nombre no permitido")
    if destino.exists():
        raise ValueError(f"ya existe {categoria}/{s}")
    destino.mkdir(parents=True)
    # Se registra como ya conocida: lo nuevo que interesa marcar es lo que aparece
    # sin que te enteres, no lo que acabas de crear tú.
    try:
        est = json.loads(idx.ESTADO.read_text()) if idx.ESTADO.is_file() else {}
        est[f"{categoria}/{s}"] = datetime.now().astimezone().isoformat()
        tmp = idx.ESTADO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(est, indent=1, ensure_ascii=False))
        os.replace(tmp, idx.ESTADO)
    except Exception:
        pass
    if con_claude:
        (destino / "CLAUDE.md").write_text(PLANTILLA_CLAUDE.format(
            nombre=nombre.strip(),
            descripcion=descripcion.strip() or "<!-- describe el proyecto -->",
            fecha=datetime.now().strftime("%d-%m-%Y")))
    if descripcion.strip():          # se guarda para que sobreviva a los refrescos
        try:
            notas = json.loads(idx.NOTAS.read_text()) if idx.NOTAS.is_file() else {}
            notas[f"{categoria}/{s}"] = descripcion.strip()
            tmp = idx.NOTAS.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(notas, indent=1, ensure_ascii=False))
            os.replace(tmp, idx.NOTAS)
        except Exception:
            pass
    return destino


QUE_ES_CADA_UNA = idx.QUE_ES_CADA_UNA


def proponer(texto, datos):
    """A partir de «lo que vas a hacer», Claude propone qué crear, cómo llamarlo y dónde.

    Devuelve {tipo, nombre, extension, categoria, subcarpeta, descripcion, claude, razon}
    o None si Claude no está disponible o contesta algo que no encaja.
    """
    inventario = []
    for cat in CATEGORIAS:
        dentro = [f for f in datos["filas"] if f["cat"] == cat][:10]
        muestra = "; ".join(f"{f['rel'].split('/', 1)[-1]} ({f['desc'][:45]})" for f in dentro)
        inventario.append(f"- {cat}: {QUE_ES_CADA_UNA[cat]}.\n    Ya contiene: {muestra or '—'}")

    prompt = f"""Eres el organizador de este escritorio. El usuario te cuenta qué va a hacer y tú
decides QUÉ crear, CÓMO llamarlo y DÓNDE ponerlo. Él no sabe el nombre todavía: propónselo tú.

SU ESCRITORIO:
{chr(10).join(inventario)}

QUÉ CREAR SEGÚN EL CASO:
- "archivo": una sola cosa que se escribe y se lee (notas, un guion, una lista, un resumen).
  No inventes estructura si con un documento basta.
- "carpeta": varias cosas relacionadas que solo se guardan (PDFs, fotos, material recibido).
- "proyecto": algo en lo que va a TRABAJAR (código, investigación, contenido que evoluciona).
  Los proyectos llevan un CLAUDE.md para que las sesiones de Claude arranquen con contexto.

ÉL VA A HACER: "{texto}"

Responde SOLO un JSON, sin texto alrededor ni vallas de código:
{{"tipo":"archivo|carpeta|proyecto",
 "nombre":"<nombre corto en minúsculas y guiones, sin extensión, 2-4 palabras>",
 "extension":"<solo si tipo=archivo: md, txt, csv…; si no, cadena vacía>",
 "categoria":"<una de: {', '.join(CATEGORIAS)}>",
 "subcarpeta":"<IMPORTANTE: si ya existe una carpeta suya donde esto encaja de forma evidente, ponla aquí tal cual (ej. notas del trabajo final → rac-editor). Solo vacío si de verdad no hay sitio natural>",
 "descripcion":"<una frase que explique de qué trata, para el índice>",
 "razon":"<una frase corta tuteando: por qué ese tipo y ese sitio>"}}"""

    claude = shutil.which("claude") or str(HOME / ".local" / "bin" / "claude")
    try:
        r = subprocess.run([claude, "-p", prompt, "--model", "haiku"],
                           capture_output=True, text=True, timeout=90, cwd="/tmp")
        salida = re.sub(r"^```(?:json)?|```$", "", r.stdout.strip(), flags=re.M).strip()
        m = re.search(r"\{.*\}", salida, re.S)
        if not m:
            return None
        d = json.loads(m.group(0))
        if d.get("categoria") not in CATEGORIAS:
            return None
        if d.get("tipo") not in ("archivo", "carpeta", "proyecto"):
            return None
        d["nombre"] = slug(str(d.get("nombre", "")))
        if not d["nombre"]:
            return None
        d["extension"] = re.sub(r"[^a-z0-9]", "", str(d.get("extension", "")).lower())[:6]
        if d["tipo"] == "archivo" and not d["extension"]:
            d["extension"] = "md"
        # La subcarpeta solo vale si existe de verdad; si no, se ignora en silencio.
        sub = str(d.get("subcarpeta", "")).strip().strip("/")
        try:
            resolver_subcarpeta(d["categoria"], sub)
        except ValueError:
            sub = ""
        d["subcarpeta"] = sub
        d["descripcion"] = str(d.get("descripcion", ""))[:200]
        d["razon"] = str(d.get("razon", ""))[:200]
        d["claude"] = d["tipo"] == "proyecto"
        return d
    except Exception:
        return None


def sueltos():
    """Lo que quedó en la raíz del escritorio sin clasificar (ni categorías ni protegidos)."""
    fuera = []
    for x in sorted(DESKTOP.iterdir()):
        if x.name.startswith(".") or x.name in idx.PROTEGIDOS or CATEGORIA.match(x.name):
            continue
        kb = int((idx.sh(["du", "-sk", str(x)]) or "0").split("\t")[0] or 0)
        fuera.append({"rel": x.name, "es_dir": x.is_dir() and not x.is_symlink(),
                      "enlace": x.is_symlink(), "tam": idx.humano(kb),
                      "sesiones": len(list(idx.PROJECTS.glob(idx.encode(x) + "*")))
                      if idx.PROJECTS.is_dir() else 0})
    return fuera


def proponer_destinos(items, datos):
    """Le pide a Claude a qué categoría (y subcarpeta) mandar cada cosa suelta."""
    if not items:
        return {}
    inventario = []
    for cat in CATEGORIAS:
        dentro = [f for f in datos["filas"] if f["cat"] == cat][:10]
        muestra = "; ".join(f['rel'].split('/', 1)[-1] for f in dentro)
        inventario.append(f"- {cat}: {QUE_ES_CADA_UNA[cat]}. Contiene: {muestra or '—'}")
    lista = "\n".join(f'- "{i["rel"]}" ({"carpeta" if i["es_dir"] else "archivo"}, {i["tam"]})'
                      for i in items)
    prompt = f"""El escritorio está organizado en categorías y quedaron cosas sueltas
en la raíz. Dime a dónde mover cada una.

CATEGORÍAS:
{chr(10).join(inventario)}

SUELTOS:
{lista}

Responde SOLO un JSON, sin vallas de código: un objeto donde cada clave es el nombre exacto
del suelto y el valor es {{"categoria":"<una de las categorías>","subcarpeta":"<carpeta que ya
exista dentro de esa categoría, o cadena vacía>","razon":"<media frase tuteando>"}}"""
    claude = shutil.which("claude") or str(HOME / ".local" / "bin" / "claude")
    try:
        r = subprocess.run([claude, "-p", prompt, "--model", "haiku"],
                           capture_output=True, text=True, timeout=120, cwd="/tmp")
        salida = re.sub(r"^```(?:json)?|```$", "", r.stdout.strip(), flags=re.M).strip()
        m = re.search(r"\{.*\}", salida, re.S)
        if not m:
            return {}
        crudo = json.loads(m.group(0))
    except Exception:
        return {}
    limpio = {}
    for i in items:
        d = crudo.get(i["rel"]) or {}
        cat = d.get("categoria")
        if cat not in CATEGORIAS:
            continue
        sub = str(d.get("subcarpeta", "")).strip().strip("/")
        try:
            resolver_subcarpeta(cat, sub)
        except ValueError:
            sub = ""
        limpio[i["rel"]] = {"categoria": cat, "subcarpeta": sub,
                            "razon": str(d.get("razon", ""))[:160]}
    return limpio


def mover_suelto(rel, categoria, subcarpeta=""):
    """Mueve algo de la raíz a su categoría, renombrando sus sesiones de Claude.

    Lo segundo es imprescindible: Claude Code localiza las sesiones por la ruta de la
    carpeta, así que mover sin renombrar rompería el --resume.
    """
    if categoria not in CATEGORIAS:
        raise ValueError("categoría desconocida")
    origen = ruta_segura(rel)
    if origen.parent != DESKTOP:
        raise ValueError("eso no está suelto en la raíz")
    base = resolver_subcarpeta(categoria, subcarpeta)
    destino = base / origen.name
    if destino.exists():
        raise ValueError(f"ya existe {destino.relative_to(DESKTOP)}")

    viejo = idx.encode(origen)
    shutil.move(str(origen), str(destino))
    nuevo = idx.encode(destino)
    renombradas = 0
    if idx.PROJECTS.is_dir():
        for d in list(idx.PROJECTS.iterdir()):
            if d.name == viejo or d.name.startswith(viejo + "-"):
                obj = idx.PROJECTS / (nuevo + d.name[len(viejo):])
                if not obj.exists():
                    d.rename(obj)
                    renombradas += 1
    _registrar(str(destino.relative_to(DESKTOP)), "", es_carpeta=destino.is_dir())
    return destino, renombradas


def resolver_subcarpeta(categoria, sub):
    """Devuelve la carpeta destino dentro de la categoría.

    La subcarpeta es una ruta que YA existe (puede llevar mayúsculas y varios niveles,
    p.ej. «rac-editor/ttf» o «estudio/Idiomas»), así que se usa literal. Aplicarle slug()
    la destrozaba: convertía las barras en guiones y bajaba las mayúsculas.
    """
    raiz = (DESKTOP / categoria).resolve()
    sub = (sub or "").strip().strip("/")
    if not sub:
        return raiz
    if ".." in Path(sub).parts:
        raise ValueError("subcarpeta inválida")
    destino = (raiz / sub).resolve()
    if destino != raiz and raiz not in destino.parents:
        raise ValueError("la subcarpeta se sale de la categoría")
    if not destino.is_dir():
        raise ValueError(f"no existe {categoria}/{sub}")
    return destino


def crear_cosa(tipo, nombre, categoria, descripcion="", extension="md",
               subcarpeta="", con_claude=False):
    """Crea un archivo, una carpeta o un proyecto en la categoría indicada."""
    if categoria not in CATEGORIAS:
        raise ValueError("categoría desconocida")
    if tipo not in ("archivo", "carpeta", "proyecto"):
        raise ValueError("tipo desconocido")
    s = slug(nombre)
    if not s:
        raise ValueError("el nombre no puede quedar vacío")

    base = resolver_subcarpeta(categoria, subcarpeta)

    if tipo == "archivo":
        ext = re.sub(r"[^a-z0-9]", "", (extension or "md").lower())[:6] or "md"
        destino = (base / f"{s}.{ext}").resolve()
    else:
        destino = (base / s).resolve()
    if base.resolve() not in destino.parents:
        raise ValueError("nombre no permitido")
    if destino.exists():
        raise ValueError(f"ya existe {destino.relative_to(DESKTOP)}")

    if tipo == "archivo":
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.suffix == ".md":
            destino.write_text(f"# {nombre.strip()}\n\n{descripcion.strip()}\n")
        else:
            destino.touch()
    else:
        destino.mkdir(parents=True)
        if con_claude or tipo == "proyecto":
            (destino / "CLAUDE.md").write_text(PLANTILLA_CLAUDE.format(
                nombre=nombre.strip(),
                descripcion=descripcion.strip() or "<!-- describe el proyecto -->",
                fecha=datetime.now().strftime("%d-%m-%Y")))

    rel = str(destino.relative_to(DESKTOP))
    _registrar(rel, descripcion, es_carpeta=(tipo != "archivo"))
    return destino


def _registrar(rel, descripcion, es_carpeta):
    """Guarda la descripción en notas.json y marca la ruta como ya conocida."""
    if descripcion.strip() and es_carpeta:
        try:
            notas = json.loads(idx.NOTAS.read_text()) if idx.NOTAS.is_file() else {}
            notas[rel] = descripcion.strip()
            tmp = idx.NOTAS.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(notas, indent=1, ensure_ascii=False))
            os.replace(tmp, idx.NOTAS)
        except Exception:
            pass
    try:
        est = json.loads(idx.ESTADO.read_text()) if idx.ESTADO.is_file() else {}
        est[rel] = datetime.now().astimezone().isoformat()
        tmp = idx.ESTADO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(est, indent=1, ensure_ascii=False))
        os.replace(tmp, idx.ESTADO)
    except Exception:
        pass


def recomendar_carpeta(descripcion, datos):
    """Le pregunta a Claude en qué categoría va, mostrándole las carpetas reales.

    Devuelve {categoria, razon, parecidos}. Si Claude no está disponible o responde
    algo inesperado, devuelve None y la página se queda con la pista por palabras clave.
    """
    ejemplos = []
    for cat in CATEGORIAS:
        dentro = [f for f in datos["filas"] if f["cat"] == cat][:8]
        muestra = "; ".join(f"{f['rel'].split('/', 1)[-1]}: {f['desc'][:60]}" for f in dentro)
        ejemplos.append(f"- {cat} ({QUE_ES_CADA_UNA[cat]}). Ya contiene: {muestra or '—'}")

    prompt = (
        "Clasifica una carpeta nueva en este escritorio.\n\n"
        "CATEGORÍAS DISPONIBLES:\n" + "\n".join(ejemplos) +
        f"\n\nLA CARPETA NUEVA ES: \"{descripcion}\"\n\n"
        "Responde SOLO un JSON, sin texto alrededor, con esta forma exacta:\n"
        '{"categoria":"<una de las categorías, tal cual>",'
        '"razon":"<una frase corta en español, tuteando, explicando por qué>",'
        '"parecidos":["<nombres de hasta 2 carpetas ya existentes que se le parezcan>"]}'
    )
    claude = shutil.which("claude") or str(HOME / ".local" / "bin" / "claude")
    try:
        r = subprocess.run([claude, "-p", prompt, "--model", "haiku"],
                           capture_output=True, text=True, timeout=60, cwd="/tmp")
        salida = r.stdout.strip()
        salida = re.sub(r"^```(?:json)?|```$", "", salida, flags=re.M).strip()
        m = re.search(r"\{.*\}", salida, re.S)
        if not m:
            return None
        d = json.loads(m.group(0))
        if d.get("categoria") not in CATEGORIAS:
            return None
        d["parecidos"] = [str(x) for x in (d.get("parecidos") or [])][:2]
        d["razon"] = str(d.get("razon", ""))[:200]
        return d
    except Exception:
        return None


def abrir_en_terminal(ruta: Path, comando=None, resume=None):
    """Abre una terminal ya situada en la carpeta y lanza Claude.

    Se hace con un archivo .command que macOS abre en la terminal por defecto, en vez
    de con AppleScript: controlar iTerm por AppleScript exige el permiso de Automatización,
    que bloquea al servidor con un diálogo y acaba en timeout.
    """
    claude = shutil.which("claude") or str(HOME / ".local" / "bin" / "claude")
    guion = HOME / ".panel" / "abrir-claude.command"
    orden = shlex.quote(comando or claude)
    if resume:
        orden += f" --resume {shlex.quote(resume)}"
    guion.write_text("#!/bin/bash\n"
                     f"cd {shlex.quote(str(ruta))} || exit 1\n"
                     f"exec {orden}\n")
    guion.chmod(0o755)
    subprocess.run(["open", str(guion)], capture_output=True, timeout=15)


NOTAS_SESION = HOME / ".panel" / "pausas.json"
FIJADAS = HOME / ".panel" / "fijadas.json"
SECCION_POR_DEFECTO = "🛠 Modificaciones · organización tablero"


def leer_json(f, por_defecto=None):
    try:
        return json.loads(f.read_text()) if f.is_file() else (por_defecto or {})
    except Exception:
        return por_defecto or {}


def escribir_json(f, datos):
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(datos, indent=1, ensure_ascii=False))
    os.replace(tmp, f)


def _leer_titulos(f: Path):
    """Saca título y último mensaje de un transcript sin leerlo entero.

    Los transcripts llegan a 800 MB: se leen solo las primeras líneas (donde suele
    estar el título) y el final del archivo (donde está lo último que se escribió).
    """
    datos = {"titulo": "", "custom": "", "ultimo": ""}

    def absorber(linea):
        try:
            d = json.loads(linea)
        except Exception:
            return
        t = d.get("type")
        if t == "ai-title" and d.get("aiTitle"):
            datos["titulo"] = str(d["aiTitle"])[:120]
        elif t == "custom-title" and d.get("customTitle"):
            datos["custom"] = str(d["customTitle"])[:120]
        elif t == "last-prompt" and d.get("lastPrompt"):
            datos["ultimo"] = str(d["lastPrompt"])[:220]

    try:
        with f.open("rb") as fh:
            for i, linea in enumerate(fh):
                if i > 400:
                    break
                absorber(linea.decode("utf-8", "ignore"))
            tam = f.stat().st_size
            if tam > 262144:
                fh.seek(tam - 262144)
                fh.readline()                      # descartar la línea partida
            else:
                fh.seek(0)
            for linea in fh:
                absorber(linea.decode("utf-8", "ignore"))
    except OSError:
        pass
    return datos


def carpetas_con_claude_abierto():
    """Carpetas donde hay un Claude corriendo ahora mismo (por el cwd del proceso)."""
    vivas = set()
    try:
        # El proceso puede aparecer como "claude" o como ruta completa: ambos valen.
        # (Con "bin/claude" se escapaban las sesiones lanzadas con el comando pelado.)
        pids = subprocess.run(["pgrep", "-f", r"(^|/)claude($| )"], capture_output=True,
                              text=True, timeout=5).stdout.split()
        for pid in pids[:20]:
            r = subprocess.run(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"],
                               capture_output=True, text=True, timeout=5)
            for linea in r.stdout.splitlines():
                if linea.startswith("n"):
                    vivas.add(linea[1:])
    except Exception:
        pass
    return vivas


def conversaciones(limite=12):
    """Últimas conversaciones de Claude, con su título y dónde retomarlas."""
    if not idx.PROJECTS.is_dir():
        return []
    archivos = []
    for d in idx.PROJECTS.iterdir():
        # El prefijo se calcula del escritorio real: escribirlo a mano ataba
        # el tablero a un usuario concreto y en otra máquina no veía nada.
        if not d.is_dir() or not d.name.startswith(idx.encode(DESKTOP)):
            continue
        for f in d.glob("*.jsonl"):
            if f.stat().st_size > 2048:            # descartar sesiones vacías
                archivos.append((f.stat().st_mtime, f, d.name))
    archivos.sort(reverse=True)
    # Las fijadas nunca se caen de la lista aunque no estén entre las más recientes.
    fijadas = leer_json(FIJADAS)
    elegidos = archivos[:limite]
    ya = {f.stem for _, f, _ in elegidos}
    elegidos += [a for a in archivos[limite:] if a[1].stem in fijadas and a[1].stem not in ya]

    # La codificación es irreversible (/ _ . → -), así que se busca la carpeta real
    # probando qué ruta del escritorio codifica igual que el nombre del directorio.
    rutas = {}
    for raiz, dirs, _ in os.walk(DESKTOP):
        p = Path(raiz)
        nivel = len(p.relative_to(DESKTOP).parts)
        # Podar: sin esto recorrer node_modules y demás tardaba 30 s.
        dirs[:] = ([d for d in dirs if d not in idx.EXCLUIR and not d.startswith(".")]
                   if nivel < 4 else [])
        rutas[idx.encode(p)] = p

    notas = {}
    if NOTAS_SESION.is_file():
        try:
            notas = json.loads(NOTAS_SESION.read_text())
        except Exception:
            notas = {}

    vivas = carpetas_con_claude_abierto()
    # Una carpeta con Claude abierto tiene UNA sesión en curso: la más reciente.
    # Sin esto, las sesiones viejas de esa carpeta también salían como «en curso»
    # y copaban las tarjetas destacadas.
    ya_marcada = set()
    salida = []
    for mtime, f, dirname in elegidos:
        t = _leer_titulos(f)
        ruta = rutas.get(dirname)
        sid = f.stem
        # En curso = hay un Claude abierto en esa carpeta, o el transcript se acaba de
        # escribir (respaldo por si falla la detección de procesos).
        reciente = (time.time() - mtime) < 600
        viva = (bool(ruta) and str(ruta) in vivas or reciente) and dirname not in ya_marcada
        if viva:
            ya_marcada.add(dirname)
        salida.append({
            "id": sid,
            "titulo": t["custom"] or t["titulo"] or "(sin título)",
            "ultimo": t["ultimo"],
            "nota": notas.get(sid, ""),
            "seccion": fijadas.get(sid, ""),
            "rel": str(ruta.relative_to(DESKTOP)) if ruta and ruta != DESKTOP else ".",
            "existe": ruta is not None,
            "cuando": idx.fmt_dias(idx.dias(mtime)),
            "mb": f.stat().st_size / 1048576,
            "viva": viva,
            "minutos": int((time.time() - mtime) / 60),
        })
    return salida


# ---------------------------------------------------------------- métricas
def metricas_escritorio(datos):
    items = len([x for x in DESKTOP.iterdir() if not x.name.startswith(".")])
    libre = int(subprocess.run(["df", "-g", "/"], capture_output=True, text=True)
                .stdout.splitlines()[1].split()[3])
    pend = 0
    f = PEND
    if f.is_file():
        pend = sum(1 for l in f.read_text(errors="ignore").splitlines()
                   if l.startswith("- [ ]"))
    est = lambda v, a, b: "ok" if v <= a else ("warning" if v <= b else "critical")
    return [
        (items, "ítems en la raíz", est(items, 12, 22),
         ["al día", "se está llenando", "sobrecargado"][0 if items <= 12 else (1 if items <= 22 else 2)]),
        (f"{libre} GB", "libres en disco",
         "ok" if libre >= 30 else ("warning" if libre >= 20 else "critical"),
         "holgado" if libre >= 30 else ("ajustado" if libre >= 20 else "crítico")),
        (pend, "pendientes abiertos", est(pend, 4, 9),
         ["manejable", "acumulando", "demasiados"][0 if pend <= 4 else (1 if pend <= 9 else 2)]),
        (len(datos["filas"]), "proyectos indexados", "ok", f"{len(datos['pesados'])} pesados dormidos"),
    ]


# ---------------------------------------------------------------- HTML
CSS = """
:root{color-scheme:light;--surface:#fcfcfb;--card:#f4f4f2;--text-1:#0b0b0b;--text-2:#52514e;
 --muted:#8a897f;--series-1:#2a78d6;--track:#e8e8e4;--border:#e2e1dc;
 --good:#0ca30c;--warning:#fab219;--critical:#d03b3b}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--surface:#1a1a19;--card:#242423;
 --text-1:#fff;--text-2:#c3c2b7;--muted:#8a897f;--series-1:#3987e5;--track:#33332f;--border:#33332f}}
*{box-sizing:border-box;margin:0}
body{background:var(--surface);color:var(--text-1);font:14px/1.5 -apple-system,system-ui,sans-serif;
 max-width:1140px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:21px;font-weight:650}
h2{font-size:14px;font-weight:600;margin:30px 0 12px;color:var(--text-2);
 text-transform:uppercase;letter-spacing:.04em}
.sub{color:var(--muted);font-size:12.5px;margin:3px 0 22px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:11px}
.tile{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:13px 15px}
.tile .k{font-size:25px;font-weight:700;font-variant-numeric:tabular-nums}
.tile .d{font-size:12.5px;color:var(--text-2)}
.tile .e{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;margin-top:5px}
.dot{width:8px;height:8px;border-radius:50%}
.ok .dot{background:var(--good)}.ok .e{color:var(--good)}
.warning .dot{background:var(--warning)}.warning .e{color:var(--text-2)}
.critical .dot{background:var(--critical)}.critical .e{color:var(--critical)}
.bar-tools{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin:22px 0 4px}
button{font:inherit;font-size:13px;border:1px solid var(--border);background:var(--card);
 color:var(--text-1);border-radius:7px;padding:7px 13px;cursor:pointer}
button:hover{border-color:var(--series-1)}
button.danger{color:var(--critical);border-color:transparent;background:transparent;padding:4px 8px}
button.danger:hover{border-color:var(--critical)}
button[disabled]{opacity:.45;cursor:not-allowed}
input[type=search]{font:inherit;font-size:13px;padding:7px 11px;border-radius:7px;
 border:1px solid var(--border);background:var(--card);color:var(--text-1);min-width:230px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{text-align:left;font-weight:600;color:var(--muted);font-size:11.5px;text-transform:uppercase;
 letter-spacing:.03em;padding:6px 9px;border-bottom:1px solid var(--border)}
td{padding:7px 9px;border-bottom:1px solid var(--border);vertical-align:top}
tr:hover td{background:var(--card)}
code{font-size:12px;background:var(--card);border:1px solid var(--border);border-radius:4px;padding:1px 5px}
.copiar{cursor:pointer;border:none;background:none;color:var(--series-1);padding:0;font-size:12px}
.muted{color:var(--muted)}
.nuevo{color:var(--good);font-weight:600}
.wrap{overflow-x:auto}
.aviso{background:var(--card);border:1px solid var(--border);border-left:3px solid var(--warning);
 border-radius:7px;padding:11px 14px;font-size:13px;margin:14px 0}
.crear{display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:var(--card);
 border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.crear input[type=text],.crear input:not([type]){min-width:230px}
.crear input:not([type]),.crear select{font:inherit;font-size:13px;padding:7px 10px;border-radius:7px;
 border:1px solid var(--border);background:var(--surface);color:var(--text-1)}
.crear label{font-size:12.5px;color:var(--text-2);display:flex;align-items:center;gap:5px;cursor:pointer}
.crear .pista{font-size:12px;color:var(--good)}
.destacada{background:var(--card);border:1px solid var(--border);
 border-left:3px solid var(--good);border-radius:10px;padding:13px 15px;margin:14px 0}
.destacada .cab{display:flex;gap:9px;align-items:baseline;flex-wrap:wrap;font-size:14px}
.destacada .ult{font-size:12.5px;color:var(--text-2);margin-top:7px}
.destacada .pie{display:flex;gap:8px;align-items:center;margin-top:10px}
.viva{color:var(--good);font-weight:700;font-size:11.5px;letter-spacing:.04em}
input.nota{font:inherit;font-size:12.5px;padding:5px 8px;border-radius:6px;
 border:1px solid var(--border);background:var(--surface);color:var(--text-1);min-width:170px;width:100%}
.propuesta{background:var(--card);border:1px solid var(--border);
 border-left:3px solid var(--series-1);border-radius:10px;padding:13px 15px;margin-top:10px}
.propuesta .razon{font-size:13px;color:var(--text-2);margin-bottom:10px}
.prios h3{font-size:13.5px;font-weight:600;margin:13px 0 5px}
.todo{display:flex;gap:9px;align-items:baseline;padding:3px 0;cursor:pointer;border-radius:5px}
.todo:hover{background:var(--card)}
.todo .box{flex:none;width:15px;height:15px;border:1.5px solid var(--muted);border-radius:4px;
 position:relative;top:2px;font-size:11px;line-height:12px;text-align:center;color:var(--surface)}
.todo .box.ok{background:var(--good);border-color:var(--good)}
.todo.hecho{color:var(--muted);text-decoration:line-through}
#toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:var(--text-1);
 color:var(--surface);padding:10px 18px;border-radius:8px;font-size:13px;opacity:0;
 transition:opacity .25s;pointer-events:none;max-width:80vw}
#toast.on{opacity:1}
"""

JS = """
const vivo = %(vivo)s;
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.classList.add('on');
  clearTimeout(window._tt);window._tt=setTimeout(()=>t.classList.remove('on'),3200);}
async function refrescar(b){
  if(!vivo) return toast('Arranca el servidor con  tablero  para usar los botones');
  b.disabled=true;b.textContent='Actualizando…';
  try{const r=await fetch('/api/refresh',{method:'POST'});const j=await r.json();
    toast(j.msg||'Listo');setTimeout(()=>location.reload(),700);}
  catch(e){toast('Error: '+e);b.disabled=false;b.textContent='Actualizar índice';}
}
async function borrar(rel,ses){
  if(!vivo) return toast('Arranca el servidor con  tablero  para usar los botones');
  let aviso='¿Mandar a la Papelera?\\n\\n'+rel;
  if(ses>0) aviso+='\\n\\nOJO: tiene '+ses+' sesión(es) de Claude asociadas.';
  aviso+='\\n\\nSe puede recuperar desde la Papelera de macOS.';
  if(!confirm(aviso)) return;
  try{const r=await fetch('/api/borrar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({path:rel})});
    const j=await r.json();
    if(!r.ok){toast('No se pudo: '+(j.error||r.status));return;}
    toast('A la Papelera: '+rel);setTimeout(()=>location.reload(),800);}
  catch(e){toast('Error: '+e);}
}
document.addEventListener('DOMContentLoaded',function(){
  if(document.getElementById('c-nombre')) pintarRuta();});
function pintarRuta(){
  const tipo=document.getElementById('c-tipo').value;
  const sub=document.getElementById('c-sub').value.trim();
  const ext=document.getElementById('c-ext').value.trim()||'md';
  const n=document.getElementById('c-nombre').value.trim()||'…';
  const base=document.getElementById('c-cat').value+(sub?'/'+sub:'');
  document.getElementById('c-ext').style.display = tipo==='archivo'?'':'none';
  document.getElementById('c-ruta').textContent='→ '+base+'/'+n+(tipo==='archivo'?'.'+ext:'/');
}
async function pedirPropuesta(b){
  if(!vivo) return toast('Abre el Tablero con la app para poder crear');
  const texto=document.getElementById('q-texto').value.trim();
  if(!texto) return toast('Cuéntame qué vas a hacer');
  b.disabled=true;b.textContent='Pensando…';
  try{const r=await fetch('/api/proponer',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({texto:texto})});
    const j=await r.json();
    if(j.sin_respuesta){toast('No pude consultarlo. Rellena los campos a mano.');}
    else if(j.tipo){
      document.getElementById('c-tipo').value=j.tipo;
      document.getElementById('c-nombre').value=j.nombre||'';
      document.getElementById('c-ext').value=j.extension||'md';
      document.getElementById('c-cat').value=j.categoria;
      document.getElementById('c-sub').value=j.subcarpeta||'';
      document.getElementById('c-desc').value=j.descripcion||'';
      document.getElementById('p-razon').textContent=j.razon||'';
      pintarRuta();
    } else {toast('No se pudo: '+(j.error||''));}}
  catch(e){toast('Error: '+e);}
  b.disabled=false;b.textContent='Proponme algo';
}
async function crear(b){
  if(!vivo) return toast('Abre el Tablero con la app para poder crear');
  const nombre=document.getElementById('c-nombre').value.trim();
  if(!nombre) return toast('Ponle un nombre');
  const tipo=document.getElementById('c-tipo').value;
  const cuerpo={tipo:tipo,nombre:nombre,
    categoria:document.getElementById('c-cat').value,
    subcarpeta:document.getElementById('c-sub').value.trim(),
    extension:document.getElementById('c-ext').value.trim()||'md',
    descripcion:document.getElementById('c-desc').value.trim(),
    claude:tipo==='proyecto',
    abrir:document.getElementById('c-abrir').checked};
  b.disabled=true;b.textContent='Creando…';
  try{const r=await fetch('/api/crear',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(cuerpo)});
    const j=await r.json();
    if(!r.ok){toast('No se pudo: '+(j.error||r.status));b.disabled=false;b.textContent='Crear';return;}
    toast(j.msg);setTimeout(()=>location.reload(),900);}
  catch(e){toast('Error: '+e);b.disabled=false;b.textContent='Crear';}
}
async function retomar(id,rel){
  if(!vivo) return toast('Abre el Tablero con la app para retomar');
  try{const r=await fetch('/api/retomar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:id,rel:rel})});
    const j=await r.json(); toast(r.ok?j.msg:('No se pudo: '+(j.error||r.status)));}
  catch(e){toast('Error: '+e);}
}
async function verSueltos(b){
  if(!vivo) return toast('Abre el Tablero con la app para organizar');
  b.disabled=true;b.textContent='Mirando…';
  const caja=document.getElementById('sueltos');
  try{const r=await fetch('/api/sueltos',{method:'POST'});
    const j=await r.json();
    if(!r.ok){toast('No se pudo: '+(j.error||r.status));}
    else if(!j.items.length){caja.hidden=false;
      caja.innerHTML='<b>Nada suelto.</b> El escritorio solo tiene las categorías, '+
        'el Tablero y Mi Semana.';}
    else{
      let h='<b>'+j.items.length+' cosa(s) sueltas en la raíz</b>'+
        '<div class="sub">Revisa el destino y aplica una por una. Las sesiones de Claude '+
        'se reubican solas.</div><table style="margin-top:8px">';
      for(const i of j.items){
        const p=i.propuesta;
        const sel=p?('<code>'+p.categoria+(p.subcarpeta?'/'+p.subcarpeta:'')+'</code>'):
                    '<span class="muted">sin propuesta</span>';
        const ses=i.sesiones?(' · '+i.sesiones+' sesión(es)'):'';
        h+='<tr><td><code>'+i.rel+'</code><br><span class="muted">'+
           (i.enlace?'enlace':(i.es_dir?'carpeta':'archivo'))+' · '+i.tam+ses+'</span></td>'+
           '<td>'+sel+(p&&p.razon?'<br><span class="muted">'+p.razon+'</span>':'')+'</td>'+
           '<td>'+(p?'<button class="copiar mover-btn" data-rel="'+encodeURIComponent(i.rel)+
             '" data-cat="'+p.categoria+'" data-sub="'+(p.subcarpeta||'')+'">mover</button>':'')+
           '</td></tr>';
      }
      caja.innerHTML=h+'</table>';caja.hidden=false;
      caja.querySelectorAll('.mover-btn').forEach(function(bt){
        bt.addEventListener('click',function(){
          mover(decodeURIComponent(bt.dataset.rel),bt.dataset.cat,bt.dataset.sub);});});
    }}
  catch(e){toast('Error: '+e);}
  b.disabled=false;b.textContent='Organizar lo suelto';
}
async function mover(rel,cat,sub){
  try{const r=await fetch('/api/mover',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({rel:rel,categoria:cat,subcarpeta:sub})});
    const j=await r.json();
    if(!r.ok) return toast('No se pudo: '+(j.error||r.status));
    toast(j.msg);setTimeout(()=>location.reload(),900);}
  catch(e){toast('Error: '+e);}
}
async function fijar(id){
  if(!vivo) return toast('Abre el Tablero con la app para fijar conversaciones');
  try{const r=await fetch('/api/fijar',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:id})});
    const j=await r.json();
    if(!r.ok) return toast('No se pudo: '+(j.error||r.status));
    toast(j.msg);setTimeout(()=>location.reload(),700);}
  catch(e){toast('Error: '+e);}
}
async function guardarPausa(id,texto){
  if(!vivo) return toast('Abre el Tablero con la app para guardar notas');
  try{const r=await fetch('/api/pausa',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id:id,texto:texto})});
    const j=await r.json(); toast(r.ok?j.msg:('No se pudo: '+(j.error||r.status)));}
  catch(e){toast('Error: '+e);}
}
async function abrirClaude(rel){
  if(!vivo) return toast('Abre el Tablero con la app para poder abrir Claude');
  try{const r=await fetch('/api/abrir',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({path:rel})});
    const j=await r.json(); toast(r.ok?j.msg:('No se pudo: '+(j.error||r.status)));}
  catch(e){toast('Error: '+e);}
}
async function anadirPend(b){
  if(!vivo) return toast('Abre el Tablero con la app para añadir pendientes');
  const i=document.getElementById('p-texto'), texto=i.value.trim();
  if(!texto) return toast('Escribe el pendiente');
  try{const r=await fetch('/api/nuevo-pendiente',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({texto:texto,seccion:document.getElementById('p-sec').value})});
    const j=await r.json();
    if(!r.ok) return toast('No se pudo: '+(j.error||r.status));
    i.value='';location.reload();}
  catch(e){toast('Error: '+e);}
}
async function marcar(linea,hecho){
  if(!vivo) return toast('Arranca el servidor con  tablero  para marcar pendientes');
  try{const r=await fetch('/api/pendiente',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({linea:linea,hecho:hecho})});
    if(!r.ok){const j=await r.json();return toast('No se pudo: '+(j.error||r.status));}
    location.reload();}
  catch(e){toast('Error: '+e);}
}
// Foto estática: sondea el servidor y salta solo a la versión viva en cuanto arranque
// (el primer escaneo tarda ~15 s, así que reintenta durante un par de minutos).
if(!vivo){
  let intentos=0;
  const sonda=setInterval(()=>{
    if(++intentos>60){clearInterval(sonda);const a=document.getElementById('foto');
      if(a) a.innerHTML='📸 Sigues viendo la foto: el servidor no arrancó. Mira <code>/tmp/tablero.log</code>.';
      return;}
    const ctrl=new AbortController(); setTimeout(()=>ctrl.abort(),1500);
    fetch('http://127.0.0.1:7373/',{mode:'no-cors',signal:ctrl.signal})
      .then(()=>{clearInterval(sonda);location.replace('http://127.0.0.1:7373/');})
      .catch(()=>{});
  },2000);
}
function copiar(t){navigator.clipboard.writeText(t).then(()=>toast('Copiado: '+t));}
function filtrar(q){q=q.toLowerCase();
  document.querySelectorAll('tr[data-buscar]').forEach(tr=>{
    tr.style.display = tr.dataset.buscar.includes(q) ? '' : 'none';});}
"""


def e(s):
    return H.escape(str(s))


def arg(v):
    """Serializa un valor JS para meterlo en un atributo HTML entre comillas dobles."""
    return H.escape(json.dumps(v), quote=True)


def fila_html(f, con_borrar=True, extra=""):
    ses = f["ses"]["n"]
    ses_txt = (f'<span title="{ses} sesión(es), {f["ses"]["bytes"]/1048576:.0f} MB">'
               f'{ses} · {idx.fmt_dias(f["d_ses"])}</span>') if ses else '<span class="muted">—</span>'
    cmd = f'cd ~/Desktop/{f["rel"]} && claude --resume'
    # El botón va en TODAS las filas: en las que ya tienen sesión abre el selector de
    # --resume; en un proyecto recién creado es justo la forma de empezar la primera.
    etiqueta = "retomar en Claude" if ses else "abrir en Claude"
    retomar = (f'<button class="copiar" onclick="abrirClaude({arg(f["rel"])})" '
               f'title="Abre una terminal en la carpeta y lanza claude">{etiqueta}</button>')
    borrar = (f'<button class="danger" onclick="borrar({arg(f["rel"])},{ses})" '
              f'title="Mandar a la Papelera">🗑</button>') if con_borrar else ""
    marca = ' <span class="nuevo">NUEVO</span>' if f.get("nuevo") else ""
    return (f'<tr data-buscar="{e((f["rel"]+" "+f["desc"]).lower())}">'
            f'<td>{ICONO.get(f["cat"],"📂")} <code>{e(f["rel"])}</code>{marca}</td>'
            f'<td>{e(f["desc"][:110])}</td>'
            f'<td class="muted">{e(f["tam"])}</td>'
            f'<td class="muted">{e(idx.fmt_dias(f["d_arch"]))}</td>'
            f'<td>{ses_txt}</td>'
            f'<td style="white-space:nowrap">{retomar} {borrar}</td></tr>{extra}')


MD_FUERTE = re.compile(r"\*\*([^*]+)\*\*")
MD_CODIGO = re.compile(r"`([^`]+)`")


def md_inline(s):
    s = e(s)
    s = MD_FUERTE.sub(r"<strong>\1</strong>", s)
    return MD_CODIGO.sub(r"<code>\1</code>", s)


def prioridades_html():
    """Renderiza PENDIENTES.md con casillas que se pueden marcar desde la página."""
    f = PEND
    if not f.is_file():
        return '<p class="muted">No hay PENDIENTES.md.</p>', 0
    P, abiertos = [], 0
    for i, linea in enumerate(f.read_text(errors="ignore").splitlines()):
        if linea.startswith("## "):
            P.append(f"<h3>{md_inline(linea[3:])}</h3>")
        elif linea.startswith("- [ ] "):
            abiertos += 1
            P.append(f'<div class="todo" onclick="marcar({i},true)">'
                     f'<span class="box"></span><span>{md_inline(linea[6:])}</span></div>')
        elif linea.startswith("- [x] "):
            P.append(f'<div class="todo hecho" onclick="marcar({i},false)">'
                     f'<span class="box ok">✓</span><span>{md_inline(linea[6:])}</span></div>')
    return ("".join(P) or '<p class="muted">Sin pendientes.</p>'), abiertos


def tabla_convs(lista, fijada=False):
    cab = ("<thead><tr><th>Conversación</th><th>Dónde</th><th>Último mensaje tuyo</th>"
           "<th>Nota de pausa</th><th></th></tr></thead>")
    filas = []
    for c in lista:
        nota = (f'<input class="nota" value="{e(c["nota"])}" placeholder="por dónde ibas…" '
                f'onchange="guardarPausa({arg(c["id"])},this.value)">')
        acciones = ""
        if c["existe"]:
            acciones += (f'<button class="copiar" onclick="retomar({arg(c["id"])},{arg(c["rel"])})">'
                         f'retomar</button> ')
        acciones += (f'<button class="copiar" onclick="fijar({arg(c["id"])})" '
                     f'title="{"Quitar de la sección" if fijada else "Añadir a Modificaciones"}">'
                     f'{"quitar" if fijada else "📌"}</button>')
        viva = '<span class="viva">▶ </span>' if c["viva"] else ""
        filas.append(
            f'<tr data-buscar="{e((c["titulo"]+" "+c["rel"]+" "+c["ultimo"]).lower())}">'
            f'<td>{viva}<b>{e(c["titulo"])}</b><br><span class="muted">{c["cuando"]} · '
            f'{c["mb"]:.0f} MB</span></td>'
            f'<td><code>{e(c["rel"])}</code></td>'
            f'<td class="muted">{e(c["ultimo"][:110])}</td>'
            f'<td>{nota}</td><td style="white-space:nowrap">{acciones}</td></tr>')
    return '<div class="wrap"><table>' + cab + "<tbody>" + "".join(filas) + "</tbody></table></div>"


def tabla(filas, con_borrar=True):
    if not filas:
        return '<p class="muted">Nada por aquí.</p>'
    cab = ("<thead><tr><th>Proyecto</th><th>Qué es</th><th>Tamaño</th>"
           "<th>Últ. edición</th><th>Sesiones</th><th></th></tr></thead>")
    return ('<div class="wrap"><table>' + cab + "<tbody>"
            + "".join(fila_html(f, con_borrar) for f in filas)
            + "</tbody></table></div>")


def construir(datos, vivo: bool) -> str:
    filas = datos["filas"]
    hoy = datos["hoy"].strftime("%d-%m-%Y %H:%M")
    convs = conversaciones()
    convs_todas = list(convs)   # copia intacta: abajo se filtran las destacadas
    tiles = "".join(
        f'<div class="tile {est}"><div class="k">{e(k)}</div><div class="d">{e(d)}</div>'
        f'<div class="e"><span class="dot"></span>{e(t)}</div></div>'
        for k, d, est, t in metricas_escritorio(datos))

    con_ses = sorted([f for f in filas if f["ses"]["n"]],
                     key=lambda x: x["d_ses"] if x["d_ses"] is not None else 9999)
    P = []
    A = P.append
    A(f'<h1>Tablero del escritorio</h1><p class="sub">Actualizado {e(hoy)} · '
      f'{len(filas)} proyectos · {len(con_ses)} con sesiones de Claude'
      + ("" if vivo else " · <b>modo lectura</b>: arranca <code>tablero</code> para usar los botones")
      + "</p>")
    # Lo primero de la página: en qué estás ahora (o lo último que tocaste).
    destacadas = [c for c in convs if c["viva"]] or convs[:1]
    for c in destacadas[:3]:
        etiqueta = ('<span class="viva">▶ EN CURSO</span>' if c["viva"]
                    else '<span class="muted">última conversación</span>')
        boton = (f'<button onclick="retomar({arg(c["id"])},{arg(c["rel"])})">'
                 f'{"ir a la terminal" if c["viva"] else "retomar"}</button>'
                 if c["existe"] else "")
        A(f'<div class="destacada">'
          f'<div class="cab">{etiqueta}<b>{e(c["titulo"])}</b>'
          f'<code>{e(c["rel"])}</code>'
          f'<span class="muted">· {"hace " + str(c["minutos"]) + " min" if c["minutos"] < 120 else c["cuando"]}</span></div>'
          + (f'<div class="ult">Lo último que escribiste: «{e(c["ultimo"][:150])}»</div>'
             if c["ultimo"] else "")
          + f'<div class="pie">'
            f'<input class="nota" value="{e(c["nota"])}" '
            f'placeholder="Guarda aquí por dónde vas, para retomarlo luego…" '
            f'onchange="guardarPausa({arg(c["id"])},this.value)">{boton}</div>'
          f'</div>')

    A(f'<div class="tiles">{tiles}</div>')

    opciones = "".join(f'<option value="{c}">{ICONO[c]} {c[3:]}</option>' for c in CATEGORIAS)
    A('<h2>➕ Crear algo nuevo</h2>')
    A('<div class="crear">'
      '<input id="q-texto" style="flex:1;min-width:340px" '
      'placeholder="¿Qué vas a hacer? — p.ej. «llevar el control de mis gastos del mes»" '
      'onkeydown="if(event.key===\'Enter\')pedirPropuesta(document.getElementById(\'q-btn\'))">'
      '<button id="q-btn" onclick="pedirPropuesta(this)">Proponme algo</button></div>')
    A('<p class="sub">Cuéntalo con tus palabras. Claude decide si conviene un archivo, una '
      'carpeta o un proyecto, le pone nombre y elige dónde va mirando tu escritorio. '
      'Puedes cambiar lo que quieras antes de crearlo.</p>')
    A('<div id="propuesta" class="propuesta">'
      '<div class="razon" id="p-razon">O rellénalo tú mismo y dale a Crear.</div>'
      '<div class="crear" style="border:none;padding:0;background:none">'
      '<select id="c-tipo" onchange="pintarRuta()">'
      '<option value="archivo">📄 archivo</option>'
      '<option value="carpeta">📁 carpeta</option>'
      '<option value="proyecto" selected>🤖 proyecto</option>'
      '</select>'
      '<input id="c-nombre" placeholder="nombre" oninput="pintarRuta()">'
      '<input id="c-ext" style="min-width:70px;max-width:90px" placeholder="md">'
      f'<select id="c-cat" onchange="pintarRuta()">{opciones}</select>'
      '<input id="c-sub" style="min-width:120px" placeholder="subcarpeta (opcional)" oninput="pintarRuta()">'
      '</div>'
      '<div class="crear" style="border:none;padding:0;background:none;margin-top:8px">'
      '<input id="c-desc" style="flex:1;min-width:300px" placeholder="de qué trata">'
      '<label><input type="checkbox" id="c-abrir"> abrir Claude al crear</label>'
      '<button onclick="crear(this)">Crear</button>'
      '<span class="pista" id="c-ruta"></span>'
      '</div></div>')

    prios, _ = prioridades_html()
    A('<h2>Prioridades <span style="text-transform:none;font-weight:400">· '
      'clic para marcar como hecho</span></h2>')
    A('<div class="crear" style="margin-bottom:12px">'
      '<input id="p-texto" placeholder="Nuevo pendiente…" '
      'onkeydown="if(event.key===\'Enter\')anadirPend(this)">'
      '<select id="p-sec">'
      '<option>🔴 Alta</option><option selected>🟡 Media</option><option>🟢 Baja</option>'
      '</select>'
      '<button onclick="anadirPend(this)">Añadir</button></div>')
    A(f'<div class="prios">{prios}</div>')

    A('<div class="bar-tools">'
      '<button onclick="refrescar(this)">Actualizar índice</button>'
      '<button onclick="verSueltos(this)" title="Busca lo que quedó suelto en la raíz y '
      'propone a qué carpeta llevarlo">Organizar lo suelto</button>'
      '<input type="search" placeholder="Filtrar proyectos…" oninput="filtrar(this.value)">'
      '<span class="muted">🗑 manda a la Papelera de macOS (recuperable)</span></div>'
      '<div id="sueltos" class="propuesta" hidden></div>')

    if datos["nuevos"]:
        A(f'<h2>🆕 Nuevos desde el último refresh ({len(datos["nuevos"])})</h2>')
        A(tabla(datos["nuevos"]))
    if datos["primera_vez"]:
        A('<div class="aviso">Primer refresh: se registró el inventario base. '
          'A partir de ahora, lo que aparezca se marcará como nuevo.</div>')

    secciones = {}
    for c in convs_todas:
        if c["seccion"]:
            secciones.setdefault(c["seccion"], []).append(c)
    for nombre, lista in secciones.items():
        A(f'<h2>{e(nombre)} ({len(lista)})</h2>')
        A(tabla_convs(lista, fijada=True))

    A(f'<h2>🤖 Con sesiones de Claude recuperables ({len(con_ses)})</h2>')
    A(tabla(con_ses))

    if datos["borrables"]:
        A(f'<h2>🗑 Restos candidatos a borrar ({len(datos["borrables"])})</h2>')
        A('<p class="sub">Vacíos o casi vacíos, sin tocar en +120 días y sin sesiones.</p>')
        A(tabla(datos["borrables"]))

    if datos["pesados"]:
        gb = sum(f["kb"] for f in datos["pesados"]) / 1048576
        A(f'<h2>💾 Pesados dormidos — {gb:.1f} GB</h2>')
        A('<p class="sub">Más de 500 MB sin tocar en +45 días. Candidatos a disco externo, '
          'no a borrar.</p>')
        A(tabla(datos["pesados"]))

    ids_arriba = {c['id'] for c in destacadas[:3]}
    convs = [c for c in convs if c['id'] not in ids_arriba]
    A(f'<h2>💬 Otras conversaciones ({len(convs)})</h2>')
    A('<p class="sub">Pausa una y retómala cuando quieras: se abre exactamente esa charla, '
      'con su contexto. La nota es para ti, para acordarte de por dónde ibas.</p>')
    if convs:
        A(tabla_convs(convs))
    else:
        A('<p class="muted">Sin más conversaciones.</p>')

    A("<h2>📂 Inventario completo</h2>")
    for cat in ["01-universidad", "02-negocio", "03-trabajo", "04-cursos",
                "05-personal", "06-archivo", ""]:
        g = [f for f in filas if f["cat"] == cat]
        if not g:
            continue
        A(f'<h2 style="margin-top:20px">{ICONO.get(cat,"📂")} '
          f'{e(cat or "Sueltos en la raíz")}</h2>')
        A(tabla(sorted(g, key=lambda x: x["d_arch"] if x["d_arch"] is not None else 9999)))

    if not vivo:
        A(f'<div class="aviso" id="foto">📸 Esto es una <b>foto del {e(hoy)}</b>, no la vista '
          f'en vivo: los botones no actúan y lo que borres en otro sitio seguirá apareciendo aquí '
          f'hasta el próximo refresco. Para la versión con botones, ejecuta <code>tablero</code> '
          f'en la terminal o abre <a href="http://127.0.0.1:7373/" '
          f'style="color:var(--series-1)">127.0.0.1:7373</a> si ya está corriendo.</div>')
    A('<p class="sub" style="margin-top:34px">Las descripciones se editan en '
      '<code>~/.panel/notas.json</code> y sobreviven a cada refresh · '
      'Las sesiones de Claude caducan a los ~30 días · '
      'Registro de borrados en <code>~/.panel/borrados.log</code></p>')
    A('<div id="toast"></div>')

    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Tablero del escritorio</title><style>{CSS}</style></head><body>'
            + "".join(P)
            + f'<script>{JS % {"vivo": "true" if vivo else "false"}}</script></body></html>')


# ---------------------------------------------------------------- servidor
# Un escaneo completo del escritorio tarda ~40 s (du + find sobre 20 GB), así que
# se cachea en memoria: las páginas y las acciones baratas se sirven al instante y
# solo se reescanea cuando el usuario lo pide o cuando cambia el árbol de verdad.
_CACHE = {"datos": None, "ts": 0.0}


def datos_actuales(forzar=False):
    if forzar or _CACHE["datos"] is None:
        _CACHE["datos"] = idx.recolectar()
        _CACHE["ts"] = time.time()
    return _CACHE["datos"]


def escribir_salidas(datos):
    """Reescribe markdown + HTML del escritorio desde unos datos ya calculados.

    Una sola pasada a propósito: dos procesos escribiendo estado.json a la vez lo
    corrompían y la regeneración fallaba en silencio.
    """
    idx.escribir_markdown(datos)
    (HOME / ".panel" / "TABLERO.html").write_text(construir(datos, vivo=False))


def olvidar(rel):
    """Quita del caché la carpeta borrada (y lo que colgaba de ella), sin reescanear."""
    d = _CACHE["datos"]
    if not d:
        return
    fuera = lambda f: f["rel"] == rel or f["rel"].startswith(rel + "/")
    for k in ("filas", "nuevos", "borrables", "pesados"):
        d[k] = [f for f in d[k] if not fuera(f)]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            return self._json(404, {"error": "no existe"})
        cuerpo = construir(datos_actuales(), vivo=True).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(n) if n else b"{}"
        if self.path == "/api/refresh":
            d = datos_actuales(forzar=True)
            escribir_salidas(d)
            return self._json(200, {"msg": f"{len(d['filas'])} proyectos · "
                                           f"{len(d['nuevos'])} nuevos"})
        if self.path == "/api/retomar":
            try:
                d = json.loads(cuerpo)
                sid = str(d.get("id", ""))
                if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", sid):
                    raise ValueError("sesión inválida")
                rel = d.get("rel") or "."
                destino = DESKTOP if rel == "." else ruta_segura(rel)
                abrir_en_terminal(destino, comando=None, resume=sid)
                return self._json(200, {"msg": "Retomando la conversación…"})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/sueltos":
            try:
                items = sueltos()
                props = proponer_destinos(items, datos_actuales())
                for i in items:
                    i["propuesta"] = props.get(i["rel"])
                return self._json(200, {"items": items})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/mover":
            try:
                d = json.loads(cuerpo)
                destino, n = mover_suelto(d.get("rel", ""), d.get("categoria", ""),
                                          d.get("subcarpeta", ""))
                datos_actuales(forzar=True)
                escribir_salidas(_CACHE["datos"])
                extra = f" · {n} sesión(es) reubicadas" if n else ""
                return self._json(200, {"msg": f"→ {destino.relative_to(DESKTOP)}{extra}"})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/fijar":
            try:
                d = json.loads(cuerpo)
                sid = str(d.get("id", ""))
                if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", sid):
                    raise ValueError("sesión inválida")
                fij = leer_json(FIJADAS)
                if sid in fij:
                    fij.pop(sid)
                    msg = "Quitada de la sección"
                else:
                    fij[sid] = (d.get("seccion") or SECCION_POR_DEFECTO)[:80]
                    msg = "Añadida a la sección"
                escribir_json(FIJADAS, fij)
                escribir_salidas(datos_actuales())
                return self._json(200, {"msg": msg})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/pausa":
            try:
                d = json.loads(cuerpo)
                sid = str(d.get("id", ""))
                if not re.fullmatch(r"[0-9a-fA-F-]{8,64}", sid):
                    raise ValueError("sesión inválida")
                notas = {}
                if NOTAS_SESION.is_file():
                    try:
                        notas = json.loads(NOTAS_SESION.read_text())
                    except Exception:
                        notas = {}
                texto = (d.get("texto") or "").strip()[:400]
                if texto:
                    notas[sid] = texto
                else:
                    notas.pop(sid, None)
                tmp = NOTAS_SESION.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(notas, indent=1, ensure_ascii=False))
                os.replace(tmp, NOTAS_SESION)
                escribir_salidas(datos_actuales())
                return self._json(200, {"msg": "Nota guardada" if texto else "Nota borrada"})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/proponer":
            try:
                texto = (json.loads(cuerpo).get("texto") or "").strip()
                if not texto:
                    raise ValueError("cuéntame qué vas a hacer")
                prop = proponer(texto, datos_actuales())
                if not prop:
                    return self._json(200, {"sin_respuesta": True})
                return self._json(200, prop)
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/sugerir":
            try:
                d = json.loads(cuerpo)
                texto = (d.get("texto") or "").strip()
                if not texto:
                    raise ValueError("describe la carpeta")
                rec = recomendar_carpeta(texto, datos_actuales())
                if not rec:
                    return self._json(200, {"sin_respuesta": True})
                return self._json(200, rec)
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/crear":
            try:
                d = json.loads(cuerpo)
                destino = crear_cosa(d.get("tipo", "carpeta"), d.get("nombre", ""),
                                     d.get("categoria", ""), d.get("descripcion", ""),
                                     d.get("extension", "md"), d.get("subcarpeta", ""),
                                     bool(d.get("claude")))
                rel = str(destino.relative_to(DESKTOP))
                datos_actuales(forzar=True)          # el árbol cambió: reescanear
                escribir_salidas(_CACHE["datos"])
                if d.get("abrir"):
                    abrir_en_terminal(destino if destino.is_dir() else destino.parent)
                return self._json(200, {"msg": f"Creado {rel}", "rel": rel})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/abrir":
            try:
                rel = json.loads(cuerpo).get("path", "")
                p = ruta_segura(rel)
                abrir_en_terminal(p)
                return self._json(200, {"msg": f"Abriendo Claude en {rel}"})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/nuevo-pendiente":
            try:
                d = json.loads(cuerpo)
                texto = (d.get("texto") or "").strip().replace("\n", " ")
                if not texto:
                    raise ValueError("escribe algo")
                seccion = d.get("seccion") or "🟡 Media"
                lineas = PEND.read_text().splitlines() if PEND.is_file() else ["# ✅ Pendientes", ""]
                try:
                    i = next(k for k, l in enumerate(lineas) if l.startswith("## ") and seccion in l)
                    j = next((k for k in range(i + 1, len(lineas))
                              if lineas[k].startswith("## ")), len(lineas))
                    while j > i + 1 and not lineas[j - 1].strip():
                        j -= 1
                    lineas.insert(j, f"- [ ] {texto}")
                except StopIteration:
                    lineas += ["", f"## {seccion}", "", f"- [ ] {texto}"]
                PEND.write_text("\n".join(lineas) + "\n")
                escribir_salidas(datos_actuales())
                return self._json(200, {"msg": "Pendiente añadido"})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/pendiente":
            try:
                d = json.loads(cuerpo)
                i, hecho = int(d["linea"]), bool(d["hecho"])
                f = PEND
                lineas = f.read_text().splitlines()
                if not 0 <= i < len(lineas):
                    raise ValueError("línea fuera de rango")
                actual = lineas[i]
                if hecho and actual.startswith("- [ ] "):
                    lineas[i] = "- [x] " + actual[6:]
                elif not hecho and actual.startswith("- [x] "):
                    lineas[i] = "- [ ] " + actual[6:]
                else:
                    raise ValueError("esa línea no es un pendiente")
                f.write_text("\n".join(lineas) + "\n")
                escribir_salidas(datos_actuales())
                return self._json(200, {"msg": "ok"})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        if self.path == "/api/borrar":
            try:
                rel = json.loads(cuerpo).get("path", "")
                p = ruta_segura(rel)
                destino = a_papelera(p)
                olvidar(rel)
                escribir_salidas(_CACHE["datos"] or datos_actuales())
                return self._json(200, {"msg": f"{rel} → Papelera", "destino": str(destino)})
            except Exception as ex:
                return self._json(400, {"error": str(ex)})
        return self._json(404, {"error": "no existe"})


def servir():
    print("Escaneando el escritorio…", flush=True)
    t0 = time.time()
    datos_actuales(forzar=True)
    print(f"  listo en {time.time()-t0:.0f} s", flush=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler)
    url = f"http://127.0.0.1:{PUERTO}/"
    print(f"Tablero en {url}   (Ctrl-C para parar)")
    threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)),
                     daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nTablero detenido.")
        srv.shutdown()


if __name__ == "__main__":
    if "--html" in sys.argv:
        salida = HOME / ".panel" / "TABLERO.html"
        salida.write_text(construir(idx.recolectar(), vivo=False))
        print(f"Tablero estático: {salida}")
    else:
        servir()
