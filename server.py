#!/usr/bin/env python3
"""
Workouts Dashboard Backend (Flask)
- Sirve index.html y data.json
- Endpoint /api/data — devuelve JSON con todos los stats
- Endpoint /api/since?ts=ISO — workouts nuevos desde timestamp
- Auto-detecta cambios releyendo los snapshots
- mtime del index.json y del último snapshot controlan la "version"
"""
import json
import os
import time
import glob
import hashlib
from datetime import datetime
from collections import defaultdict
from flask import Flask, jsonify, request, send_from_directory, abort

# Reutilizamos la lógica de build.py
import sys
sys.path.insert(0, os.path.dirname(__file__))
import build

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = build.VAULT_DIR
HTML_FILE = os.path.join(OUTPUT_DIR, "index.html")

app = Flask(__name__, static_folder=OUTPUT_DIR)

# Caché en memoria: workout_id -> workout dict, más "version" calculada
_cache = {
    "workouts": None,        # dict id -> workout
    "by_id": {},             # dict id -> workout  (para detectar nuevos)
    "stats": None,           # stats completas
    "version_ts": 0,         # mtime del último snapshot (epoch)
    "last_check": 0,         # última vez que revisamos disco
    "first_request": True,   # si es la primera vez, regenera HTML también
}

CHECK_INTERVAL = 30  # segundos entre chequeos de disco


def discover_version_ts():
    """Devuelve el mtime del snapshot/modified más reciente de VAULT_DIR."""
    latest = 0
    for path in glob.glob(os.path.join(VAULT_DIR, "*.json")):
        m = os.path.getmtime(path)
        if m > latest:
            latest = m
    # También chequea el index.json
    idx = os.path.join(os.path.dirname(VAULT_DIR), "index.json")
    if os.path.exists(idx):
        m = os.path.getmtime(idx)
        if m > latest:
            latest = m
    return latest


def load_workouts_from_disk():
    """Lee todos los snapshots y devuelve dict id -> workout."""
    out = {}
    for path in sorted(glob.glob(os.path.join(VAULT_DIR, "*.json"))):
        try:
            with open(path) as f:
                d = json.load(f)
            for w in d.get("workouts", []):
                wid = w.get("id")
                if wid:
                    out[wid] = w
        except Exception as e:
            print(f"Error leyendo {path}: {e}", file=sys.stderr)
    return out


def rebuild_stats():
    """Recalcula stats desde el caché en memoria y persiste en data.json."""
    workouts = list(_cache["by_id"].values())
    stats = build.compute_stats(workouts)
    _cache["stats"] = stats
    with open(os.path.join(OUTPUT_DIR, "data.json"), "w") as f:
        json.dump(stats, f, indent=2)
    # Regenera HTML si es la primera vez o si hay cambio grande
    if _cache["first_request"]:
        html = build.render_dashboard(stats)
        with open(HTML_FILE, "w") as f:
            f.write(html)
        _cache["first_request"] = False
    return stats


def maybe_refresh(force=False):
    """Si el mtime de los snapshots cambió, recarga y recalcula stats."""
    now = time.time()
    if not force and (now - _cache["last_check"]) < CHECK_INTERVAL:
        return
    _cache["last_check"] = now
    new_version = discover_version_ts()
    if new_version != _cache["version_ts"]:
        print(f"[{datetime.now().isoformat()}] Detectado cambio en snapshots (version {new_version})")
        _cache["by_id"] = load_workouts_from_disk()
        rebuild_stats()
        _cache["version_ts"] = new_version


@app.before_request
def _ensure_loaded():
    """Carga workouts y stats al primer request (lazy init)."""
    if not _cache["by_id"]:
        _cache["by_id"] = load_workouts_from_disk()
        _cache["version_ts"] = discover_version_ts()
        rebuild_stats()


@app.route("/")
def root():
    maybe_refresh()
    # Si el HTML no existe, regenerar
    if not os.path.exists(HTML_FILE):
        stats = _cache["stats"] or rebuild_stats()
        html = build.render_dashboard(stats)
        with open(HTML_FILE, "w") as f:
            f.write(html)
    return send_from_directory(OUTPUT_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(OUTPUT_DIR, filename)


@app.route("/data.json")
def data_json():
    maybe_refresh()
    if _cache["stats"] is None:
        rebuild_stats()
    return jsonify(_cache["stats"])


@app.route("/api/data")
def api_data():
    maybe_refresh()
    if _cache["stats"] is None:
        rebuild_stats()
    return jsonify({
        "version_ts": _cache["version_ts"],
        "last_check": _cache["last_check"],
        "stats": _cache["stats"],
    })


@app.route("/api/since")
def api_since():
    """Devuelve workouts con startDate > el timestamp dado."""
    since = request.args.get("ts", "0")
    maybe_refresh()
    if _cache["by_id"] is None:
        _cache["by_id"] = load_workouts_from_disk()
    new_ones = []
    for w in _cache["by_id"].values():
        sd = w.get("startDate", "")
        if sd > since:
            new_ones.append(w)
    new_ones.sort(key=lambda w: w.get("startDate", ""))
    return jsonify({
        "version_ts": _cache["version_ts"],
        "count": len(new_ones),
        "workouts": new_ones,
    })


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Fuerza recarga desde disco (útil para el botón 'Recargar')."""
    maybe_refresh(force=True)
    if _cache["stats"] is None:
        rebuild_stats()
    return jsonify({
        "ok": True,
        "version_ts": _cache["version_ts"],
        "total_workouts": len(_cache["by_id"]),
        "stats": _cache["stats"],
    })


@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "version_ts": _cache["version_ts"],
        "last_check": _cache["last_check"],
        "total_workouts": len(_cache["by_id"]) if _cache["by_id"] else 0,
        "vault_dir": VAULT_DIR,
        "html_exists": os.path.exists(HTML_FILE),
    })


if __name__ == "__main__":
    print("=== Workouts Dashboard Server ===")
    print(f"Vault: {VAULT_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Cargando workouts iniciales…")
    _cache["by_id"] = load_workouts_from_disk()
    _cache["version_ts"] = discover_version_ts()
    rebuild_stats()
    print(f"  → {len(_cache['by_id'])} workouts cargados")
    print(f"  → version_ts: {_cache['version_ts']}")
    print(f"Servidor en http://0.0.0.0:8091/")
    app.run(host="0.0.0.0", port=8091, debug=False, threaded=True)
