#!/usr/bin/env python3
"""Genera ~/Desktop/INDICE_PROYECTOS.md: inventario de proyectos del escritorio
cruzado con las sesiones de Claude Code, marcando novedades y candidatos a borrar.

Uso:  indice            (alias en .zshrc)   ·   python3 ~/.panel/indice.py
Notas curadas: ~/.panel/notas.json   {"ruta/relativa": "descripción"}
Estado previo: ~/.panel/estado.json  (para detectar proyectos nuevos)
"""
import json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
DESKTOP = HOME / "Desktop"
PROJECTS = HOME / ".claude" / "projects"
PANEL = HOME / ".panel"
NOTAS = PANEL / "notas.json"
ESTADO = PANEL / "estado.json"
SALIDA = PANEL / "INDICE_PROYECTOS.md"

CONFIG = PANEL / "config.json"

# Valores por defecto. Se pisan con ~/.panel/config.json, que es lo que permite
# llevarse esto a otra máquina con otras categorías sin tocar el código.
POR_DEFECTO = {
    "categorias": [
        {"id": "01-universidad", "icono": "🎓", "expandir": True,
         "que_es": "materias, trabajos prácticos y trabajos finales"},
        {"id": "02-negocio", "icono": "💼", "expandir": True,
         "que_es": "productos y clientes propios, lo que factura por su cuenta"},
        {"id": "03-trabajo", "icono": "🏦", "expandir": True,
         "que_es": "trabajo como empleado o consultor, y lo interno del puesto"},
        {"id": "04-cursos", "icono": "📚", "expandir": True,
         "que_es": "formación comprada o descargada para consumir"},
        {"id": "05-personal", "icono": "🏠", "expandir": False,
         "que_es": "documentos, finanzas, salud, casa, fotos"},
        {"id": "06-archivo", "icono": "🗄", "expandir": False,
         "que_es": "material cerrado que ya no se trabaja, solo se consulta"},
    ],
    "protegidos": ["Tablero.app"],
}


def cargar_config():
    cfg = dict(POR_DEFECTO)
    try:
        if CONFIG.is_file():
            propio = json.loads(CONFIG.read_text())
            cfg.update({k: v for k, v in propio.items() if v})
    except Exception:
        pass
    return cfg


CFG = cargar_config()
CATEGORIAS = [c["id"] for c in CFG["categorias"]]
QUE_ES_CADA_UNA = {c["id"]: c["que_es"] for c in CFG["categorias"]}
EXPANDIR = {c["id"] for c in CFG["categorias"] if c.get("expandir")}
ICONO = {c["id"]: c.get("icono", "📂") for c in CFG["categorias"]}
ICONO[""] = "📂"
PROTEGIDOS = set(CFG["protegidos"])
# Un directorio con alguno de estos ya es un proyecto: no se sigue abriendo.
MARCAS = {".claude", ".git", "package.json", "pyproject.toml", "CLAUDE.md",
          "build.gradle.kts", "build.gradle", "go.mod", "Cargo.toml",
          "requirements.txt", "Makefile", "docker-compose.yml"}
EXCLUIR = {"node_modules", ".git", ".venv", "__pycache__", ".next", "dist", "build"}
# Prefijo que identifica una categoría (01-…, 02-…).
RE_CATEGORIA = re.compile(r"^\d\d-")


def sh(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=180).stdout.strip()
    except Exception:
        return ""


def encode(path: Path) -> str:
    """Codifica una ruta como lo hace Claude Code para nombrar su carpeta de sesiones."""
    return re.sub(r"[/_.]", "-", str(path))


def es_proyecto(p: Path) -> bool:
    return any((p / m).exists() for m in MARCAS)


def subdirs(p: Path):
    try:
        return sorted(d for d in p.iterdir()
                      if d.is_dir() and not d.is_symlink() and d.name not in EXCLUIR
                      and not d.name.startswith("."))
    except OSError:
        return []


def dirs_con_sesion():
    """Nombres codificados de las carpetas de ~/.claude/projects que tienen transcript."""
    if not PROJECTS.is_dir():
        return set()
    return {d.name for d in PROJECTS.iterdir() if d.is_dir() and any(d.glob("*.jsonl"))}


def descubrir(sesiones):
    """[(categoria, ruta)] de lo que cuenta como proyecto.

    Un directorio es una entrada del índice (hoja) si tiene sesión propia de Claude,
    si parece un repo/proyecto, si no tiene subcarpetas, si tiene demasiadas (>6, es
    un monorepo) o si ya llegamos al nivel 3. Si no, se abre un nivel más — salvo que
    algún descendiente tenga sesión, en cuyo caso siempre se baja a buscarlo para no
    esconder nada retomable.
    """
    def con_sesion(p):
        return encode(p) in sesiones

    def sesion_debajo(p):
        pref = encode(p) + "-"
        return any(s.startswith(pref) for s in sesiones)

    def caminar(p, cat, nivel, out):
        hijos = subdirs(p)
        hoja = (con_sesion(p) or es_proyecto(p) or not hijos
                or len(hijos) > 6 or nivel >= 3)
        if hoja and not (sesion_debajo(p) and not con_sesion(p)):
            out.append((cat, p))
            return
        if not hijos:
            out.append((cat, p))
            return
        for h in hijos:
            caminar(h, cat, nivel + 1, out)

    out = []
    for hijo in sorted(DESKTOP.iterdir()):
        if (hijo.is_symlink() or not hijo.is_dir() or hijo.name.startswith(".")
                or hijo.name in PROTEGIDOS):
            continue
        cat = hijo.name if RE_CATEGORIA.match(hijo.name) else ""
        if cat and cat in EXPANDIR:
            for nieto in subdirs(hijo):
                caminar(nieto, cat, 2, out)
        elif cat:                      # 05-personal, 06-archivo: hijos directos
            out.extend((cat, n) for n in subdirs(hijo))
        else:                          # carpeta suelta en la raíz
            out.append(("", hijo))
    return out


def humano(kb: int) -> str:
    if kb >= 1048576:
        return f"{kb/1048576:.1f}G"
    if kb >= 1024:
        return f"{kb/1024:.0f}M"
    return f"{kb}K"


def metricas(p: Path):
    """(tamaño legible, nº archivos, última modificación, kB).

    Un solo `du` (antes había dos: -sh y -sk) y los dos `find` imprescindibles.
    Se llama en paralelo desde recolectar(): son procesos independientes.
    """
    pod = []
    for e in EXCLUIR:
        pod += ["-not", "-path", f"*/{e}/*"]
    kb = int((sh(["du", "-sk", str(p)]) or "0").split("\t")[0] or 0)
    n = sh(["find", str(p), "-type", "f", *pod, "-not", "-name", ".DS_Store"])
    n = len([x for x in n.splitlines() if x])
    recientes = sh(["find", str(p), "-type", "f", "-mtime", "-120", *pod,
                    "-not", "-name", ".DS_Store"])
    ult = None
    for f in recientes.splitlines():
        try:
            m = os.stat(f).st_mtime
            ult = m if ult is None or m > ult else ult
        except OSError:
            pass
    return humano(kb), n, ult, kb


def mapa_sesiones(rutas):
    """Asigna cada carpeta de ~/.claude/projects al proyecto que mejor la contiene."""
    enc = {encode(r): r for r in rutas}
    res = {r: {"n": 0, "bytes": 0, "ult": None, "dirs": []} for r in rutas}
    if not PROJECTS.is_dir():
        return res
    for d in sorted(PROJECTS.iterdir()):
        if not d.is_dir():
            continue
        jsonls = list(d.glob("*.jsonl"))
        if not jsonls:
            continue
        mejor = None
        for e, ruta in enc.items():
            if d.name == e or d.name.startswith(e + "-"):
                if mejor is None or len(e) > len(encode(mejor)):
                    mejor = ruta
        if mejor is None:
            continue
        info = res[mejor]
        info["n"] += len(jsonls)
        info["dirs"].append(d.name)
        for j in jsonls:
            st = j.stat()
            info["bytes"] += st.st_size
            if info["ult"] is None or st.st_mtime > info["ult"]:
                info["ult"] = st.st_mtime
    return res


def describir(p, nota, n_arch, tam):
    """Descripción del proyecto: la nota curada, si no el README/CLAUDE.md, si no los tipos de archivo."""
    if nota:
        return nota
    for nombre in ("CLAUDE.md", "README.md"):
        f = p / nombre
        if f.is_file():
            try:
                for linea in f.read_text(errors="ignore").splitlines():
                    t = linea.strip().lstrip("#").strip()
                    if t and not t.startswith(("!", "[", "<", "---", "```", ">")):
                        return t[:150]
            except OSError:
                pass
    exts = {}
    try:
        for f in list(p.rglob("*"))[:400]:
            if f.is_file() and f.suffix:
                exts[f.suffix.lower()] = exts.get(f.suffix.lower(), 0) + 1
    except OSError:
        pass
    top = ", ".join(e for e, _ in sorted(exts.items(), key=lambda x: -x[1])[:3])
    return f"{n_arch} archivos ({tam}){' · ' + top if top else ''}"


def dias(ts):
    return None if ts is None else int((time.time() - ts) / 86400)


def fmt_dias(d):
    if d is None:
        return "+120 d"
    if d == 0:
        return "hoy"
    return f"hace {d} d"


def recolectar(guardar_estado=True):
    """Escanea el escritorio y devuelve los datos del índice.

    Lo usan tanto main() (markdown) como tablero.py (HTML interactivo).
    """
    hoy = datetime.now().astimezone()
    notas = json.loads(NOTAS.read_text()) if NOTAS.is_file() else {}
    try:
        estado = json.loads(ESTADO.read_text()) if ESTADO.is_file() else {}
    except (json.JSONDecodeError, OSError):
        estado = {}          # si se corrompió, se reconstruye solo
    primera_vez = not estado

    proyectos = descubrir(dirs_con_sesion())
    ses = mapa_sesiones([p for _, p in proyectos])
    # du/find son E/S: en paralelo el escaneo baja de ~45 s a unos pocos.
    with ThreadPoolExecutor(max_workers=10) as pool:
        medidas = dict(zip((str(p) for _, p in proyectos),
                           pool.map(lambda cp: metricas(cp[1]), proyectos)))

    filas, nuevos, borrables, pesados = [], [], [], []
    estado_nuevo = {}
    for cat, p in proyectos:
        rel = str(p.relative_to(DESKTOP))
        tam, n_arch, ult, kb = medidas[str(p)]
        s = ses[p]
        d_arch, d_ses = dias(ult), dias(s["ult"])
        visto = estado.get(rel)
        estado_nuevo[rel] = visto or hoy.isoformat()
        es_nuevo = visto is None and not primera_vez
        fila = {"cat": cat, "rel": rel, "nom": p.name, "tam": tam, "n": n_arch,
                "d_arch": d_arch, "ses": s, "d_ses": d_ses, "nuevo": es_nuevo,
                "desc": describir(p, notas.get(rel), n_arch, tam)}
        filas.append(fila)
        if es_nuevo:
            nuevos.append(fila)
        # Restos: vacíos, o casi vacíos y sin tocar hace mucho, sin sesiones.
        # 05-personal nunca entra: son recuerdos y documentos, no restos de trabajo.
        resto = n_arch == 0 or (cat != "05-personal" and s["n"] == 0 and n_arch <= 3
                                and (d_arch is None or d_arch > 120))
        if resto:
            borrables.append(fila)
        # Pesados dormidos: candidatos a disco externo, no a borrar.
        fila["kb"] = kb
        if kb > 512_000 and (d_arch is None or d_arch > 45):
            pesados.append(fila)

    if guardar_estado:
        PANEL.mkdir(exist_ok=True)
        tmp = ESTADO.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(estado_nuevo, indent=1, ensure_ascii=False))
        os.replace(tmp, ESTADO)
    return {"hoy": hoy, "filas": filas, "nuevos": nuevos, "borrables": borrables,
            "pesados": pesados, "primera_vez": primera_vez}


def escribir_markdown(d):
    hoy, filas = d["hoy"], d["filas"]
    nuevos, borrables, pesados = d["nuevos"], d["borrables"], d["pesados"]
    primera_vez = d["primera_vez"]

    L = []
    A = L.append
    A("# 📇 Índice de proyectos")
    A("")
    A(f"> Generado automáticamente el **{hoy.strftime('%d-%m-%Y %H:%M')}** · "
      f"{len(filas)} proyectos · se regenera desde Tablero.app")
    A("> Editable: las descripciones curadas viven en `~/.panel/notas.json` y "
      "sobreviven a cada refresh.")
    A("")

    if nuevos:
        A(f"## 🆕 Nuevos desde el último refresh ({len(nuevos)})")
        A("")
        for f in nuevos:
            A(f"- **{f['rel']}** — {f['desc']} · {f['tam']} · última edición {fmt_dias(f['d_arch'])}")
        A("")
    elif primera_vez:
        A("> Primer refresh: se registró el inventario base. A partir de ahora "
          "los proyectos que aparezcan se marcarán aquí como nuevos.")
        A("")

    con_ses = [f for f in filas if f["ses"]["n"]]
    A("## 🤖 Con sesiones de Claude recuperables")
    A("")
    A("| Proyecto | Qué es | Sesiones | Último uso | Retomar |")
    A("|---|---|---|---|---|")
    for f in sorted(con_ses, key=lambda x: x["d_ses"] if x["d_ses"] is not None else 9999):
        mb = f["ses"]["bytes"] / 1048576
        A(f"| {ICONO.get(f['cat'],'📂')} `{f['rel']}` | {f['desc'][:90]} | "
          f"{f['ses']['n']} ({mb:.0f} MB) | {fmt_dias(f['d_ses'])} | "
          f"`cd ~/Desktop/{f['rel']} && claude --resume` |")
    A("")

    A("## 📂 Inventario completo por categoría")
    A("")
    for cat in ["01-universidad", "02-negocio", "03-trabajo", "04-cursos",
                "05-personal", "06-archivo", ""]:
        grupo = [f for f in filas if f["cat"] == cat]
        if not grupo:
            continue
        titulo = cat or "Sueltos en la raíz (pendientes de clasificar)"
        A(f"### {ICONO.get(cat,'📂')} {titulo}")
        A("")
        A("| Proyecto | Qué es | Tamaño | Últ. edición | Sesiones |")
        A("|---|---|---|---|---|")
        for f in sorted(grupo, key=lambda x: x["d_arch"] if x["d_arch"] is not None else 9999):
            marca = " 🆕" if f["nuevo"] else ""
            ses_txt = f"{f['ses']['n']}" if f["ses"]["n"] else "—"
            nom = f["rel"].split("/", 1)[1] if "/" in f["rel"] else f["rel"]
            A(f"| `{nom}`{marca} | {f['desc'][:90]} | {f['tam']} | "
              f"{fmt_dias(f['d_arch'])} | {ses_txt} |")
        A("")

    A("## 🗑 Restos candidatos a borrar")
    A("")
    if borrables:
        A("Vacíos, o con muy poco dentro y sin tocar en +120 días, y sin sesiones "
          "de Claude. Revisa antes de borrar.")
        A("")
        A("| Proyecto | Qué es | Archivos | Últ. edición |")
        A("|---|---|---|---|")
        for f in sorted(borrables, key=lambda x: (x["n"] or 0)):
            A(f"| `{f['rel']}` | {f['desc'][:80]} | {f['n']} | {fmt_dias(f['d_arch'])} |")
    else:
        A("Nada que proponer: no hay carpetas vacías ni restos olvidados.")
    A("")

    A("## 💾 Pesados dormidos (candidatos a disco externo, no a borrar)")
    A("")
    if pesados:
        total = sum(f["kb"] for f in pesados) / 1048576
        A(f"Más de 500 MB y sin tocar en +45 días. En total **{total:.1f} GB**.")
        A("")
        A("| Proyecto | Qué es | Tamaño | Últ. edición |")
        A("|---|---|---|---|")
        for f in sorted(pesados, key=lambda x: -x["kb"]):
            A(f"| `{f['rel']}` | {f['desc'][:80]} | {f['tam']} | {fmt_dias(f['d_arch'])} |")
    else:
        A("Nada pesado y dormido ahora mismo.")
    A("")

    A("---")
    A("")
    A("## Cómo usar esto")
    A("")
    A("| Quiero… | Comando |")
    A("|---|---|")
    A("| Refrescar este índice | `indice` |")
    A("| Retomar un proyecto | `cd ~/Desktop/<ruta> && claude --resume` (abre el selector) |")
    A("| Ver prioridades y sobrecarga | abrir `PANEL.html` · regenerar con `panel` |")
    A("| Fijar la descripción de un proyecto | editar `~/.panel/notas.json` |")
    A("")
    A("> Las sesiones de Claude Code caducan a los ~30 días: si un proyecto muestra "
      "0 sesiones puede ser que existiera y expirara. Mover una carpeta rompe el "
      "`--resume` salvo que se renombre también su carpeta en `~/.claude/projects/`.")

    SALIDA.write_text("\n".join(L) + "\n")
    return len(filas), len(con_ses), len(nuevos), len(borrables)


def main():
    n, con_ses, nuevos, borrables = escribir_markdown(recolectar())
    print(f"Índice generado: {SALIDA}")
    print(f"  {n} proyectos · {con_ses} con sesiones · "
          f"{nuevos} nuevos · {borrables} candidatos a limpiar")


if __name__ == "__main__":
    main()
