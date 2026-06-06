# CLAUDE.md — Workouts Dashboard

> Dashboard personal de fitness — 12 años, 7,060 workouts, dark mode.
> Lee snapshots de SyncSalud (iCloud Vault) y genera stats + visualización.

---

## Proyecto

**Nombre:** Workouts Dashboard
**Tipo:** Web app (Python Flask + HTML/CSS/JS vanilla + Chart.js)
**Descripción:** Lee los snapshots JSON de SyncSalud, calcula KPIs, PRs, ACWR, y renderiza un dashboard interactivo en el navegador.
**Repo:** `https://github.com/polidisio/workouts-dashboard`
**Owner:** @polidisio

---

## Tech Stack

| Capa | Tecnología |
|------|------------|
| Backend | Python 3 + Flask (servidor HTTP) |
|Frontend | HTML5 + CSS3 + JavaScript vanilla |
| Gráficos | Chart.js 4.4.0 (self-hosted, `chart.min.js`) |
| Datos | SyncSalud snapshots (JSON) desde iCloud Vault |
| Build | `build.py` (genera `data.json` + `index.html`) |

---

## Archivos Clave

```
workouts-dashboard/
├── build.py          # Lógica principal — lee snapshots, calcula stats, genera HTML
├── server.py         # Flask server — sirve la app y los endpoints API
├── data.json         # Stats calculadas (generado por build.py)
├── index.html        # Dashboard completo (generado por build.py)
├── styles.css        # Estilos dark theme
├── chart.min.js      # Chart.js embebido (205 KB, self-hosted)
├── screenshot_v2.png  # Screenshot del dashboard
├── CHANGELOG.md      # Historial de versiones
└── CLAUDE.md         # ← este archivo
```

---

## Fuente de Datos

**Path:** `~/Library/Mobile Documents/com~apple~CloudDocs/Vault/snapshots/`
(Vault de iCloud — mismo lugar donde SyncSalud guarda los snapshots)

El servidor detecta cambios automáticamente:
- Cada 30 segundos revisa el `mtime` de los snapshots
- Si cambió algo, recarga y recalcula stats
- También expone `/api/refresh` (POST) para forzar reload manual

---

## API Endpoints (Flask — puerto 8091)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Dashboard HTML |
| GET | `/data.json` | Stats completas (cacheadas) |
| GET | `/api/health` | Health check con version_ts y total workouts |
| GET | `/api/data` | `{version_ts, last_check, stats}` |
| GET | `/api/since?ts=ISO` | Workouts nuevos desde timestamp |
| POST | `/api/refresh` | Fuerza reload desde disco |

**Ejemplo:**
```bash
# Iniciar servidor
python3 server.py

# Health check
curl http://localhost:8091/api/health

# Forzar refresh
curl -X POST http://localhost:8091/api/refresh
```

---

## build.py — Estructura y Funciones Principales

### Flujo de ejecución:
```
build.py → load_workouts() → compute_stats() → render_dashboard() → data.json + index.html
```

### Funciones clave:

**`load_workouts()`**
- Lee todos los `*.json` de VAULT_DIR
- Devuelve dict `id → workout`
- Deduplicación por `id`

**`compute_stats(workouts)`** — Produce:
- `kpi`: total_workouts, total_distance_km, total_calories, total_duration_hours, first_date, last_date, unique_days, max_streak_days, current_streak_days, years_active, avg_hr_global, fav_type, yoy_current_km, yoy_prev_km, yoy_pct_change
- `by_type`: count, distance_km, duration_hours, calories, avg_hr por tipo
- `by_month`: stats mensuales agregadas
- `weekday_dist`: distribución por día de la semana
- `cumulative_km`: serie temporal de km acumulados
- `prs`: personal records por tipo (best distance, best calories, etc.)
- `acwr`: acutechronic workload ratio (series temporal)
- `scatter`: muestra de HR vs distance (max 2000 puntos)

**`render_dashboard(stats)`** — Genera `index.html`:
- Hero strip: longest streak, favourite type, YoY km, ACWR status, top distance PR
- KPI bar: 8 métricas
- Filter bar: multi-select type chips, year-range, compare-last-year toggle
- Charts lazy-loaded via IntersectionObserver
- Activity heatmap (GitHub-style)
- Personal Records cards
- Annual Goals con localStorage
- Live polling cada 60s (`/api/since`)
- URL state: `?types=running&from=2020&to=2026&compare=1`

---

## Modelo de Datos (data.json)

```json
{
  "kpi": {
    "total_workouts": 7060,
    "total_distance_km": 117725.4,
    "total_calories": 4598042.0,
    "total_duration_hours": 7405.7,
    "first_date": "2015-04-19T09:36:09Z",
    "last_date": "2026-06-03T16:14:29Z",
    "unique_days": 3064,
    "max_streak_days": 61,
    "current_streak_days": 0,
    "years_active": 12,
    "avg_hr_global": 142.0,
    "fav_type": "running",
    "yoy_current_km": 1569.0,
    "yoy_prev_km": 3887.1,
    "yoy_pct_change": -59.6
  },
  "by_type": {
    "running": { "count": 4319, "distance_km": 45028.6, ... },
    "cycling": { "count": 1812, "distance_km": 67891.6, ... },
    ...
  },
  "by_month": { "2015-04": { "count": 14, "distance_km": 126.9, ... } },
  "weekday_dist": [...],
  "cumulative_km": [...],
  "prs": { "running": { "best_distance_km": 42.195, ... }, ... },
  "acwr": [...],
  "scatter": [...]
}
```

---

## Workflow

### Para tareas simples
Sé directo: "Cambia el color del KPI de streak a verde" — no necesitas explicar contexto.

### Para tareas complejas (>3 pasos)
1. Agent propone plan primero
2. Usuario confirma
3. Agent ejecuta
4. Agent verifica

### Para cada tarea
1. **Plan** → Si son >3 pasos, escribir en `tasks/todo.md`
2. **Verify** → Confirmar antes de cambios grandes
3. **Execute** → Cambio más pequeño posible
4. **Document** → Actualizar si es necesario

---

## Patrones de Prompting (Boris/Claude Code)

### Para features nuevas:
```
"Before you write code, make a plan and run it by me for approval."
```

### Para commits automáticos:
```
"I want to think with this one, this commit push here."
```

---

## Code Quality

### SIEMPRE
- Código legible y mantenible
- DRY — no duplicar lógica
- Probar cambios en `test_chart.html` antes de mergear
- Mantener `chart.min.js` self-hosted (no CDN)

### NUNCA
- Hardcodear paths — usar constantes (`VAULT_DIR`, `OUTPUT_DIR`)
- Commitear `data.json` grande (supera 1MB) si no es necesario
- Hacer fetch a CDNs externos — todo local
- Commits sin mensaje descriptivo

---

## Debugging

**Servidor no inicia:**
```bash
# Verificar que el vault existe
ls ~/Library/Mobile\ Documents/com~apple~CloudDocs/Vault/snapshots/

# Test manual de build
python3 build.py
```

**Dashboard no carga datos:**
```bash
# Verificar health del servidor
curl http://localhost:8091/api/health

# Forzar refresh
curl -X POST http://localhost:8091/api/refresh
```

**Revisar stats generadas:**
```bash
cat data.json | python3 -m json.tool | head -50
```

---

## Recursos

**Vault Saraiba (contexto personal):**
- `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Saraiba/`
- Skills en: `~/.hermes/skills/`

**Repos relacionados:**
- `~/Projects/syncsalud/` — fuente de los snapshots
- Vault snapshots: `~/Library/Mobile Documents/com~apple~CloudDocs/Vault/snapshots/`

---

## Contacto

**Jose Maudisio** — @polidisio
**Issues:** Abrir en GitHub o preguntar en Telegram

---

*Último actualizado: 2026-06-06*
*Versión actual: v2.0.0 (2026-06-05)*