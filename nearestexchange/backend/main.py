"""NearestExchange FastAPI app: complaint ingest, trace, VASP desk, dashboard."""

from __future__ import annotations

import copy
import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

import cache
import cases
from attribution import COVERAGE, CRIME_TYPES, attach_attribution
from binance_desk import SCENARIOS, attach_binance_desk
from exchanges import dataset_stats, validate_address
from tracer import TraceError, render_report, trace_wallet

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
EXTENSION_DIR = Path(__file__).resolve().parent.parent / "extension"

app = FastAPI(
    title="NearestExchange",
    description="SIH26183 real-time crypto fraud attribution — nearest VASP within 3 hops.",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TraceRequest(BaseModel):
    address: str = Field(..., min_length=1)
    chain: str = Field(..., min_length=2)


class ComplaintRequest(BaseModel):
    address: str = Field(..., min_length=1)
    chain: str = Field(..., min_length=2)
    crime_type: str = "unspecified"
    complaint_id: str = ""
    scenario: str = "unknown"
    order_id: str = ""
    notes: str = ""


def _normalize_chain(chain: str) -> str:
    c = (chain or "").strip().lower()
    if c in ("btc", "bitcoin"):
        return "btc"
    if c in ("eth", "ethereum"):
        return "eth"
    raise HTTPException(
        status_code=400,
        detail="Chain must be 'btc' or 'eth' (aliases: bitcoin, ethereum).",
    )


def _decorate(
    result: dict,
    *,
    scenario: str | None = None,
    crime_type: str | None = None,
    complaint_id: str | None = None,
    order_id: str | None = None,
    notes: str | None = None,
) -> dict:
    attach_binance_desk(result, scenario)
    attach_attribution(result, crime_type=crime_type, complaint_id=complaint_id)
    result["p2p"] = {
        "order_id": (order_id or "").strip() or None,
        "notes": (notes or "").strip() or None,
        "scenario": (result.get("binance") or {}).get("scenario"),
    }
    return result


def _run_trace(address: str, chain: str, use_cache: bool = True) -> dict:
    chain = _normalize_chain(chain)
    try:
        normalized = validate_address(address, chain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    key = cache.cache_key(chain, normalized)
    if use_cache:
        hit = cache.get(key)
        if hit:
            return copy.deepcopy(hit)
    try:
        result = trace_wallet(normalized, chain)
    except TraceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    cache.put(key, {**result, "cached": False})
    return result


@app.get("/api/health")
def health() -> dict:
    stats = dataset_stats()
    return {
        "status": "ok",
        "service": "nearestexchange",
        "product": "sih26183-attribution",
        "problem": "Real-Time Crypto Fraud Attribution — nearest VASP",
        "dataset": stats,
        "crime_types": {k: v["label"] for k, v in CRIME_TYPES.items()},
        "scenarios": {k: v["label"] for k, v in SCENARIOS.items()},
        "integrations": [
            "POST /api/complaint",
            "POST /api/trace",
            "POST /api/p2p/case",
            "GET /api/cases",
            "GET /api/coverage",
            "GET /embed.js",
            "GET /extension.zip",
        ],
    }


@app.get("/api/coverage")
def api_coverage() -> dict:
    return {
        "problem": "SIH26183 / I4C — Real-Time Crypto Fraud Attribution",
        "items": COVERAGE,
        "counts": {
            "in": sum(1 for i in COVERAGE if i["status"] == "in"),
            "partial": sum(1 for i in COVERAGE if i["status"] == "partial"),
            "out": sum(1 for i in COVERAGE if i["status"] == "out"),
        },
    }


@app.get("/api/cases")
def api_cases() -> dict:
    return cases.list_cases()


@app.post("/api/trace")
def api_trace(body: TraceRequest) -> dict:
    if not (body.address or "").strip():
        raise HTTPException(status_code=400, detail="Address is required.")
    return _run_trace(body.address, body.chain)


@app.post("/api/complaint")
def api_complaint(body: ComplaintRequest) -> dict:
    if not (body.address or "").strip():
        raise HTTPException(status_code=400, detail="Address is required.")
    result = _run_trace(body.address, body.chain)
    _decorate(
        result,
        scenario=body.scenario,
        crime_type=body.crime_type,
        complaint_id=body.complaint_id,
        order_id=body.order_id,
        notes=body.notes,
    )
    cases.record(result)
    return result


@app.post("/api/p2p/case")
def api_p2p_case(body: ComplaintRequest) -> dict:
    """VASP-desk alias of complaint ingest (Binance P2P module)."""
    if not (body.address or "").strip():
        raise HTTPException(status_code=400, detail="Address is required.")
    if not body.crime_type or body.crime_type == "unspecified":
        body.crime_type = "p2p"
    return api_complaint(body)


@app.post("/api/report")
def api_report(body: ComplaintRequest) -> PlainTextResponse:
    if not (body.address or "").strip():
        raise HTTPException(status_code=400, detail="Address is required.")
    result = _run_trace(body.address, body.chain)
    _decorate(
        result,
        scenario=body.scenario,
        crime_type=body.crime_type,
        complaint_id=body.complaint_id,
        order_id=body.order_id,
        notes=body.notes,
    )
    text = render_report(result)
    filename = f"nearestexchange-{result['chain']}-{result['address'][:10]}.txt"
    return PlainTextResponse(
        text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/embed.js")
def embed_js() -> FileResponse:
    path = FRONTEND_DIR / "embed.js"
    return FileResponse(
        path,
        media_type="application/javascript; charset=utf-8",
        headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
    )


@app.get("/extension.zip")
def extension_zip() -> Response:
    if not EXTENSION_DIR.exists():
        raise HTTPException(status_code=404, detail="Extension pack missing")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in EXTENSION_DIR.rglob("*"):
            if path.is_file() and "node_modules" not in path.parts:
                zf.write(path, path.relative_to(EXTENSION_DIR.parent))
    data = buf.getvalue()
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="nearestexchange-extension.zip"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/favicon.svg")
def favicon() -> FileResponse:
    path = FRONTEND_DIR / "favicon.svg"
    if path.exists():
        return FileResponse(path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="No favicon")
