"""FastAPI application entry point for the Data Quality Research Assistant."""

import logging
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import run_full_pipeline
from app.api.routes import (
    database,
    connection,
    discovery,
    profiling,
    classification,
    dq_rules,
    dq_scores,
    pipeline,
)
from app.config.settings import settings
from app.utils.db_registry import list_database_names, list_snapshot_dates, snapshot_map
from app.utils.logging_config import configure_logging, install_request_logging

# Configure logging (file + console) before anything else uses it.
configure_logging()

app = FastAPI(
    title="Autonomous Data Governance Assistant",
    description=(
        "Autonomous agentic platform for data quality assessment. "
        "Performs discovery, profiling, classification, and data quality rule generation & execution."
    ),
    version="0.1.0",
    # Disable the default /docs so we can serve a customized Swagger UI that
    # filters the snapshot_date dropdown based on the chosen db_name.
    docs_url=None,
)

# Register routes
app.include_router(database.router)
app.include_router(connection.router)
app.include_router(discovery.router)
app.include_router(profiling.router)
app.include_router(classification.router)
app.include_router(dq_rules.router)
app.include_router(dq_scores.router)
app.include_router(pipeline.router)

# Log every incoming request to app/logs/api_access.log
install_request_logging(app)


def _patch_property(prop: dict[str, Any], values: list[str]) -> None:
    """Strip ``anyOf`` (so ``str | None`` becomes a plain enum) and set ``enum``."""
    if "anyOf" in prop:
        prop.pop("anyOf", None)
        prop["type"] = "string"
    prop["enum"] = values


def _inject_enum(schema: dict[str, Any], field: str, values: list[str]) -> None:
    """Walk the OpenAPI schema and set ``enum`` on every property/parameter named ``field``."""
    if not values:
        return

    for component in schema.get("components", {}).get("schemas", {}).values():
        props = component.get("properties", {})
        if field in props:
            _patch_property(props[field], values)

    for path_item in schema.get("paths", {}).values():
        for op in path_item.values():
            if not isinstance(op, dict):
                continue
            for param in op.get("parameters", []) or []:
                if param.get("name") == field:
                    _patch_property(param.setdefault("schema", {}), values)


def _customize_openapi():
    """Build the OpenAPI schema fresh on every call so dropdowns stay live."""
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    try:
        _inject_enum(schema, "db_name", list_database_names())
        all_snaps = list_snapshot_dates()
        _inject_enum(schema, "snapshot_date", all_snaps)
        # Same enum for range-style endpoints (e.g. /dq-scores/trend).
        _inject_enum(schema, "snapshot_date_start", all_snaps)
        _inject_enum(schema, "snapshot_date_end", all_snaps)
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).warning(
            "Failed to inject enum dropdowns into OpenAPI schema: %s", exc
        )
    # Do NOT cache: ensures dropdowns reflect newly registered databases/snapshots without restart.
    app.openapi_schema = None
    return schema


app.openapi = _customize_openapi


@app.get("/", tags=["Health"])
def root():
    """Health check endpoint."""
    return {
        "service": "Autonomous Data Governance Assistant",
        "version": "0.1.0",
        "status": "running",
    }


# ---------------------------------------------------------------------------
# Hackathon entry-point: POST /run
# ---------------------------------------------------------------------------
# Per the non-negotiable constraints, the platform must expose a single
# /run endpoint on port 8000 that performs end-to-end execution with no
# manual setup. It auto-loads sample data and runs the full pipeline.
class RunRequest(BaseModel):
    db_name: str | None = Field(
        default="mortgage_demo",
        description="Database name (sample SQLite file). Auto-created if missing.",
    )
    snapshot_date: str | None = Field(
        default=None,
        description=(
            "Snapshot date in ISO YYYY-MM-DD. Defaults to today if omitted. "
            "Same date replays in place; new dates append history."
        ),
    )
    description: str | None = Field(default=None)


@app.post("/run", tags=["Run"])
def run_entrypoint(payload: RunRequest | None = None):
    """End-to-end automated run.

    Steps performed:
      1. Load (or replay) the bundled mortgage sample dataset for the given
         ``snapshot_date``. If none is provided, today's date is used.
      2. Execute the full agentic pipeline: connection → (discovery ∥
         profiling) → classification → DQ rule generation → DQ rule execution.
      3. Persist all artifacts under ``(db_name, snapshot_date, kind)`` and
         return a summary including the overall DQ score.

    The endpoint requires no manual setup. ``COMPASS_API_KEY`` must be set
    via environment variable or `.env` (see `.env.example`).
    """
    payload = payload or RunRequest()
    snap = payload.snapshot_date or date.today().isoformat()
    try:
        # setup_database=True triggers automatic data loading inside the
        # orchestrator, fulfilling the "no manual setup" constraint.
        return run_full_pipeline(
            db_name=payload.db_name,
            snapshot_date=snap,
            description=payload.description,
            properties=None,
            setup_database=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # pragma: no cover - defensive
        logging.getLogger(__name__).exception("/run failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/outputs", tags=["Outputs"])
def list_outputs():
    """List available output files."""
    outputs_dir = settings.outputs_path
    files = []
    if outputs_dir.exists():
        for f in outputs_dir.iterdir():
            if f.is_file():
                files.append({"name": f.name, "size_bytes": f.stat().st_size})
    return {"outputs": files}


@app.get("/api/v1/database/snapshot-map", tags=["Database"])
def get_snapshot_map():
    """Return ``{db_name: [snapshot_date, ...]}`` for the per-DB Swagger dropdown."""
    return snapshot_map()


# ---------------------------------------------------------------------------
# Custom Swagger UI: makes the snapshot_date dropdown depend on db_name.
# ---------------------------------------------------------------------------
# Strategy:
#   1. Render the standard Swagger UI HTML.
#   2. Inject a small script that, on load, fetches /api/v1/database/snapshot-map
#      once and stores it on window. It then watches every operation block for
#      changes to its db_name <select> and rewrites the sibling snapshot_date
#      <select> options to only those valid for the chosen database. When no
#      db_name is selected, the union of all snapshots is used (matches the
#      static OpenAPI enum).
_SNAPSHOT_FILTER_SCRIPT = """
<script>
(function () {
  var SNAP_MAP = {};
  var ALL_SNAPSHOTS = [];

  function fetchSnapshots() {
    return fetch('/api/v1/database/snapshot-map')
      .then(function (r) { return r.json(); })
      .then(function (m) {
        SNAP_MAP = m || {};
        var s = new Set();
        Object.keys(SNAP_MAP).forEach(function (k) {
          (SNAP_MAP[k] || []).forEach(function (d) { s.add(d); });
        });
        ALL_SNAPSHOTS = Array.from(s).sort();
      })
      .catch(function () { /* ignore */ });
  }

  function rebuildSelect(select, options, preferred) {
    var current = preferred != null ? preferred : select.value;
    var keep = options.indexOf(current) !== -1;
    select.innerHTML = '';
    var blank = document.createElement('option');
    blank.value = '';
    blank.textContent = '--';
    select.appendChild(blank);
    options.forEach(function (v) {
      var o = document.createElement('option');
      o.value = v;
      o.textContent = v;
      select.appendChild(o);
    });
    select.value = keep ? current : '';
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function findSiblingSnapshot(dbSelect) {
    // Walk up to the operation container, then find every snapshot-style
    // select inside it (snapshot_date, snapshot_date_start, snapshot_date_end).
    var op = dbSelect.closest('.opblock');
    if (!op) return [];
    var found = [];
    var SNAP_NAMES = ['snapshot_date', 'snapshot_date_start', 'snapshot_date_end'];
    var rows = op.querySelectorAll('tr.parameters, tr');
    for (var i = 0; i < rows.length; i++) {
      var labelCell = rows[i].querySelector('.parameter__name');
      if (!labelCell) continue;
      var label = labelCell.textContent;
      for (var k = 0; k < SNAP_NAMES.length; k++) {
        if (label.indexOf(SNAP_NAMES[k]) === 0) {
          var sel = rows[i].querySelector('select');
          if (sel) found.push(sel);
          break;
        }
      }
    }
    if (found.length === 0) {
      SNAP_NAMES.forEach(function (n) {
        var sel = op.querySelector('select[data-param-name="' + n + '"]');
        if (sel) found.push(sel);
      });
    }
    return found;
  }

  function applyFilter(dbSelect) {
    var snapSelects = findSiblingSnapshot(dbSelect);
    if (!snapSelects || snapSelects.length === 0) return;
    var dbName = dbSelect.value;
    var allowed = dbName && SNAP_MAP[dbName] ? SNAP_MAP[dbName] : ALL_SNAPSHOTS;
    snapSelects.forEach(function (s) { rebuildSelect(s, allowed); });
  }

  function findDbSelects(root) {
    // Heuristic: any <select> whose nearest .parameter__name starts with 'db_name'.
    var selects = root.querySelectorAll('select');
    var out = [];
    selects.forEach(function (s) {
      var row = s.closest('tr');
      if (!row) return;
      var label = row.querySelector('.parameter__name');
      if (label && label.textContent.indexOf('db_name') === 0) {
        out.push(s);
      }
    });
    return out;
  }

  function wire(root) {
    findDbSelects(root).forEach(function (s) {
      if (s.dataset.snapshotFilterWired) return;
      s.dataset.snapshotFilterWired = '1';
      s.addEventListener('change', function () { applyFilter(s); });
      // Also apply once now in case the operation was already expanded.
      applyFilter(s);
    });
  }

  function start() {
    fetchSnapshots().then(function () {
      wire(document.body);
      // Swagger UI lazily renders parameter widgets when an operation is
      // expanded. Observe DOM mutations so we wire new selects as they appear.
      var mo = new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
          var m = muts[i];
          for (var j = 0; j < m.addedNodes.length; j++) {
            var n = m.addedNodes[j];
            if (n.nodeType === 1) wire(n);
          }
        }
      });
      mo.observe(document.body, { childList: true, subtree: true });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
</script>
"""


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui():
    """Swagger UI with a script that filters snapshot_date by selected db_name."""
    html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
    ).body.decode("utf-8")
    html = html.replace("</body>", f"{_SNAPSHOT_FILTER_SCRIPT}</body>")
    return HTMLResponse(html)

