"""
Generación de gráficas a partir de resultados.db, reportes.db y analisis.db.
Guarda las imágenes en images/<request_sanitized>/ por tipo de request.
"""
import json
import os
import re
import sqlite3
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Estilo (compatible con distintas versiones de matplotlib)
try:
    plt.style.use("seaborn-v0_8-darkgrid")
except OSError:
    try:
        plt.style.use("seaborn-darkgrid")
    except OSError:
        plt.style.use("default")
COLORS = {"Positivo": "#22c55e", "Negativo": "#ef4444", "Neutral": "#94a3b8", "Error": "#64748b"}
RED_COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b"]


def sanitize_request_for_folder(request_label: str) -> str:
    """Nombre de carpeta seguro a partir del request."""
    if not request_label or not request_label.strip():
        return "Sin_request"
    s = re.sub(r"[^\w\s\-]", "", request_label.strip())
    s = re.sub(r"\s+", "_", s)
    return s[:80] if s else "Sin_request"


def get_resultados_posts_per_red(conn, request_value: str | None) -> dict[str, int]:
    """Cuenta posts por RedSocial desde resultados. Si request_value, filtra por Request."""
    if request_value:
        cur = conn.execute(
            "SELECT RedSocial, COUNT(*) FROM resultados WHERE Request = ? GROUP BY RedSocial",
            (request_value,),
        )
    else:
        cur = conn.execute(
            "SELECT RedSocial, COUNT(*) FROM resultados GROUP BY RedSocial",
        )
    return dict(cur.fetchall())


def get_resultados_posts_per_request(conn) -> dict[str, int]:
    """Cuenta posts por Request (todos los requests)."""
    cur = conn.execute(
        "SELECT Request, COUNT(*) FROM resultados WHERE Request IS NOT NULL AND Request != '' GROUP BY Request",
    )
    return dict(cur.fetchall())


def get_resultados_fechas(conn, request_value: str | None) -> list[str]:
    """Lista de FechaPublicacion para histograma (strings YYYY-MM-DD o similares)."""
    if request_value:
        cur = conn.execute(
            "SELECT FechaPublicacion FROM resultados WHERE Request = ? AND FechaPublicacion IS NOT NULL AND FechaPublicacion != ''",
            (request_value,),
        )
    else:
        cur = conn.execute(
            "SELECT FechaPublicacion FROM resultados WHERE FechaPublicacion IS NOT NULL AND FechaPublicacion != ''",
        )
    return [r[0] for r in cur.fetchall()]


def get_analisis_sentiment_counts(conn, request_value: str | None) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """
    Desde analisis.db: (distribución global Positivo/Negativo/Neutral, por_red {network: {Positivo: n, ...}}).
    content_json es una lista de resultados por publicación; cada uno tiene sentimiento_general y analisis_post/analisis_comentarios.
    """
    if request_value:
        cur = conn.execute(
            "SELECT network, content_json FROM analisis WHERE request = ?",
            (request_value,),
        )
    else:
        cur = conn.execute("SELECT network, content_json FROM analisis")
    rows = cur.fetchall()
    global_counts = defaultdict(int)
    per_red = defaultdict(lambda: defaultdict(int))
    for network, content_json_str in rows:
        try:
            data = json.loads(content_json_str)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            # Contar solo post y comentarios (cada elemento una vez)
            ap = item.get("analisis_post")
            if ap and ap.get("sentimiento"):
                s = ap["sentimiento"]
                if s not in ("Positivo", "Negativo", "Neutral"):
                    s = "Neutral"
                global_counts[s] += 1
                per_red[network][s] += 1
            for c in item.get("analisis_comentarios") or []:
                s = c.get("sentimiento", "Neutral")
                if s not in ("Positivo", "Negativo", "Neutral"):
                    s = "Neutral"
                global_counts[s] += 1
                per_red[network][s] += 1
    return dict(global_counts), {k: dict(v) for k, v in per_red.items()}


def get_analisis_publicaciones_por_red(conn, request_value: str | None) -> dict[str, int]:
    """Cantidad de publicaciones analizadas por red (tamaño de la lista content_json)."""
    if request_value:
        cur = conn.execute(
            "SELECT network, content_json FROM analisis WHERE request = ?",
            (request_value,),
        )
    else:
        cur = conn.execute("SELECT network, content_json FROM analisis")
    out = defaultdict(int)
    for network, content_json_str in cur.fetchall():
        try:
            data = json.loads(content_json_str)
            out[network] = len(data) if isinstance(data, list) else 0
        except (json.JSONDecodeError, TypeError):
            pass
    return dict(out)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def chart_posts_por_red(data: dict[str, int], request_label: str, out_dir: str) -> str | None:
    """Gráfica de barras: posts por red social."""
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(8, 5))
    reds = list(data.keys())
    counts = [data[r] for r in reds]
    bars = ax.bar(reds, counts, color=RED_COLORS[: len(reds)], edgecolor="white", linewidth=0.5)
    ax.set_ylabel("Cantidad de posts")
    ax.set_title(f"Posts por red social\nRequest: {request_label[:50]}{'…' if len(request_label) > 50 else ''}")
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.2, str(c), ha="center", fontsize=10)
    plt.tight_layout()
    path = os.path.join(out_dir, "posts_por_red.png")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path


def chart_posts_por_request(data: dict[str, int], out_dir: str) -> str | None:
    """Gráfica de barras: posts por request (comparativa de temas)."""
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(max(8, len(data) * 1.2), 5))
    labels = [k[:30] + ("…" if len(k) > 30 else "") for k in data.keys()]
    counts = list(data.values())
    bars = ax.barh(labels, counts, color=RED_COLORS * (len(counts) // 4 + 1), edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Cantidad de posts")
    ax.set_title("Posts por Request (tema de búsqueda)")
    for b, c in zip(bars, counts):
        ax.text(c + 0.2, b.get_y() + b.get_height() / 2, str(c), va="center", fontsize=9)
    plt.tight_layout()
    path = os.path.join(out_dir, "posts_por_request.png")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path


def chart_sentimientos_distribucion(global_counts: dict[str, int], request_label: str, out_dir: str) -> str | None:
    """Gráfica de torta: distribución global Positivo/Negativo/Neutral."""
    if not global_counts:
        return None
    labels = ["Positivo", "Negativo", "Neutral"]
    sizes = [global_counts.get(l, 0) for l in labels]
    if sum(sizes) == 0:
        return None
    colors = [COLORS[l] for l in labels]
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(sizes, labels=labels, autopct="%1.1f%%", colors=colors, startangle=90)
    ax.set_title(f"Distribución de sentimientos\nRequest: {request_label[:40]}{'…' if len(request_label) > 40 else ''}")
    path = os.path.join(out_dir, "sentimientos_distribucion.png")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path


def chart_sentimientos_por_red(per_red: dict[str, dict[str, int]], request_label: str, out_dir: str) -> str | None:
    """Barras agrupadas: Positivo/Negativo/Neutral por red."""
    if not per_red:
        return None
    fig, ax = plt.subplots(figsize=(9, 5))
    reds = list(per_red.keys())
    x = range(len(reds))
    w = 0.25
    p = [per_red[r].get("Positivo", 0) for r in reds]
    n = [per_red[r].get("Negativo", 0) for r in reds]
    ne = [per_red[r].get("Neutral", 0) for r in reds]
    ax.bar([i - w for i in x], p, w, label="Positivo", color=COLORS["Positivo"])
    ax.bar(x, n, w, label="Negativo", color=COLORS["Negativo"])
    ax.bar([i + w for i in x], ne, w, label="Neutral", color=COLORS["Neutral"])
    ax.set_xticks(x)
    ax.set_xticklabels(reds)
    ax.set_ylabel("Cantidad")
    ax.set_title(f"Sentimientos por red social\nRequest: {request_label[:40]}{'…' if len(request_label) > 40 else ''}")
    ax.legend()
    plt.tight_layout()
    path = os.path.join(out_dir, "sentimientos_por_red.png")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path


def chart_publicaciones_analizadas_por_red(data: dict[str, int], request_label: str, out_dir: str) -> str | None:
    """Barras: publicaciones analizadas por red."""
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(8, 5))
    reds = list(data.keys())
    counts = [data[r] for r in reds]
    ax.bar(reds, counts, color=RED_COLORS[: len(reds)], edgecolor="white", linewidth=0.5)
    ax.set_ylabel("Publicaciones analizadas")
    ax.set_title(f"Publicaciones analizadas por red (LLM)\nRequest: {request_label[:40]}{'…' if len(request_label) > 40 else ''}")
    for i, c in enumerate(counts):
        ax.text(i, c + 0.2, str(c), ha="center", fontsize=10)
    plt.tight_layout()
    path = os.path.join(out_dir, "publicaciones_analizadas_por_red.png")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path


def chart_fechas_publicacion(fechas: list[str], request_label: str, out_dir: str) -> str | None:
    """Histograma de fechas de publicación (por mes si hay muchas)."""
    if not fechas:
        return None
    from datetime import datetime
    parsed = []
    for f in fechas:
        if not f:
            continue
        try:
            # Intentar varios formatos
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
                try:
                    parsed.append(datetime.strptime(f[:19].replace("T", " "), fmt))
                    break
                except ValueError:
                    continue
        except Exception:
            continue
    if not parsed:
        return None
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(parsed, bins=min(20, max(5, len(set(parsed)))), color="#3b82f6", edgecolor="white")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=45)
    ax.set_ylabel("Cantidad")
    ax.set_title(f"Fechas de publicación\nRequest: {request_label[:40]}{'…' if len(request_label) > 40 else ''}")
    plt.tight_layout()
    path = os.path.join(out_dir, "fechas_publicacion.png")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path


def chart_sentimientos_barras_global(global_counts: dict[str, int], request_label: str, out_dir: str) -> str | None:
    """Barras horizontales: Positivo / Negativo / Neutral (alternativa a la torta)."""
    if not global_counts:
        return None
    labels = ["Positivo", "Negativo", "Neutral"]
    values = [global_counts.get(l, 0) for l in labels]
    if sum(values) == 0:
        return None
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(labels, values, color=[COLORS[l] for l in labels])
    ax.set_xlabel("Cantidad")
    ax.set_title(f"Sentimientos (elementos analizados)\nRequest: {request_label[:40]}{'…' if len(request_label) > 40 else ''}")
    plt.tight_layout()
    path = os.path.join(out_dir, "sentimientos_barras.png")
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path


def generate_charts_for_request(
    request_label: str,
    db_path: str,
    analisis_path: str,
    images_base_dir: str,
) -> list[str]:
    """
    Genera todas las gráficas para un request y las guarda en images_base_dir/<request_sanitized>/.
    Devuelve lista de rutas absolutas de archivos generados.
    """
    folder_name = sanitize_request_for_folder(request_label)
    out_dir = os.path.join(images_base_dir, folder_name)
    _ensure_dir(out_dir)
    generated = []

    # Resultados: posts por red, fechas
    if os.path.isfile(db_path):
        conn_res = sqlite3.connect(db_path)
        posts_red = get_resultados_posts_per_red(conn_res, request_label)
        p = chart_posts_por_red(posts_red, request_label, out_dir)
        if p:
            generated.append(os.path.abspath(p))
        fechas = get_resultados_fechas(conn_res, request_label)
        pf = chart_fechas_publicacion(fechas, request_label, out_dir)
        if pf:
            generated.append(os.path.abspath(pf))
        conn_res.close()

    # Analisis: sentimientos
    if os.path.isfile(analisis_path):
        conn_ana = sqlite3.connect(analisis_path)
        global_counts, per_red = get_analisis_sentiment_counts(conn_ana, request_label)
        pub_por_red = get_analisis_publicaciones_por_red(conn_ana, request_label)
        conn_ana.close()

        p = chart_sentimientos_distribucion(global_counts, request_label, out_dir)
        if p:
            generated.append(os.path.abspath(p))
        p = chart_sentimientos_barras_global(global_counts, request_label, out_dir)
        if p:
            generated.append(os.path.abspath(p))
        p = chart_sentimientos_por_red(per_red, request_label, out_dir)
        if p:
            generated.append(os.path.abspath(p))
        p = chart_publicaciones_analizadas_por_red(pub_por_red, request_label, out_dir)
        if p:
            generated.append(os.path.abspath(p))

    return generated


def generate_charts_all_requests(
    db_path: str,
    analisis_path: str,
    images_base_dir: str,
) -> list[str]:
    """
    Genera gráficas por cada request distinto y opcionalmente una comparativa global.
    Devuelve lista de rutas de archivos generados.
    """
    all_generated = []
    requests_list = []
    if os.path.isfile(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.execute("SELECT DISTINCT Request FROM resultados WHERE Request IS NOT NULL AND Request != '' ORDER BY Request")
        requests_list = [r[0] for r in cur.fetchall()]
        conn.close()

    if not requests_list:
        # Aún así intentar carpeta "All" con posts_por_request si hay datos
        if os.path.isfile(db_path):
            conn = sqlite3.connect(db_path)
            posts_per_req = get_resultados_posts_per_request(conn)
            conn.close()
            out_dir = os.path.join(images_base_dir, "All")
            _ensure_dir(out_dir)
            p = chart_posts_por_request(posts_per_req, out_dir)
            if p:
                all_generated.append(os.path.abspath(p))
        return all_generated

    for req in requests_list:
        all_generated.extend(
            generate_charts_for_request(req, db_path, analisis_path, images_base_dir),
        )

    # Comparativa global: posts por request
    if os.path.isfile(db_path):
        conn = sqlite3.connect(db_path)
        posts_per_req = get_resultados_posts_per_request(conn)
        conn.close()
        out_dir = os.path.join(images_base_dir, "All")
        _ensure_dir(out_dir)
        p = chart_posts_por_request(posts_per_req, out_dir)
        if p:
            all_generated.append(os.path.abspath(p))

    return all_generated
