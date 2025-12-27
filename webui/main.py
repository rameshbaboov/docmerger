from __future__ import annotations

import csv
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from .config import WebUIConfig, load_config, save_config
from .job_manager import DocMergerJobManager
from .utils import list_files, safe_filename, tail_text


PROJECT_DIR = Path(__file__).resolve().parents[1]  # .../docmerger
INPUT_DIR = PROJECT_DIR / "input_docs"
OUTPUT_DIR = PROJECT_DIR / "merged_output"
LOG_PATH = OUTPUT_DIR / "docmerger.log"
CONFIG_PATH = OUTPUT_DIR / "webui_config.json"
PID_PATH = OUTPUT_DIR / "docmerger.pid.json"
PROCESSED_CSV = PROJECT_DIR / "processed.csv"


app = FastAPI(title="DocMerger WebUI")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)

job_mgr = DocMergerJobManager(project_dir=PROJECT_DIR, pid_file=PID_PATH)


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


def _read_processed(max_rows: int = 500) -> list[tuple[str, str]]:
    if not PROCESSED_CSV.exists():
        return []
    rows: list[tuple[str, str]] = []
    try:
        with PROCESSED_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                if len(row) == 2:
                    rows.append((row[0], row[1]))
    except Exception:
        return []
    return rows


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    cfg = load_config(CONFIG_PATH)
    status = job_mgr.status()

    input_files = list_files(INPUT_DIR)
    output_files = list_files(OUTPUT_DIR)
    log_tail = tail_text(LOG_PATH, max_lines=120)
    processed_rows = list(reversed(_read_processed(max_rows=200)))

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": cfg,
            "status": status,
            "input_files": input_files,
            "output_files": output_files,
            "log_tail": log_tail,
            "processed_rows": processed_rows,
        },
    )


@app.post("/job/start")
def start_job():
    cfg = load_config(CONFIG_PATH)
    job_mgr.start(cfg.interval_seconds)
    return _redirect("/")


@app.post("/job/stop")
def stop_job():
    job_mgr.stop()
    return _redirect("/")


@app.post("/job/run-once")
def run_once(background_tasks: BackgroundTasks):
    # If the daemon is running, don't start a second concurrent run.
    if job_mgr.status().running:
        return _redirect("/")
    background_tasks.add_task(job_mgr.run_once_async)
    return _redirect("/")


@app.get("/schedule", response_class=HTMLResponse)
def schedule_get(request: Request):
    cfg = load_config(CONFIG_PATH)
    return templates.TemplateResponse("schedule.html", {"request": request, "config": cfg})


@app.post("/schedule")
def schedule_post(interval_minutes: int = Form(...)):
    # Clamp to a sensible minimum
    if interval_minutes < 1:
        interval_minutes = 1
    cfg = WebUIConfig(interval_seconds=int(interval_minutes) * 60)
    save_config(CONFIG_PATH, cfg)

    # If job is already running, restart it with the new interval
    if job_mgr.status().running:
        job_mgr.stop()
        job_mgr.start(cfg.interval_seconds)

    return _redirect("/")


@app.get("/upload", response_class=HTMLResponse)
def upload_get(request: Request):
    input_files = list_files(INPUT_DIR)
    return templates.TemplateResponse("upload.html", {"request": request, "input_files": input_files})


@app.post("/upload")
async def upload_post(file: UploadFile = File(...)):
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    name = safe_filename(file.filename or "")
    if not name.lower().endswith(".docx"):
        return _redirect("/upload")

    dest = INPUT_DIR / name
    # Avoid overwriting existing documents by default
    if dest.exists():
        return _redirect("/upload")

    content = await file.read()
    dest.write_bytes(content)
    return _redirect("/upload")


@app.get("/outputs", response_class=HTMLResponse)
def outputs_get(request: Request):
    output_files = list_files(OUTPUT_DIR)
    return templates.TemplateResponse("outputs.html", {"request": request, "output_files": output_files})


@app.get("/processed", response_class=HTMLResponse)
def processed_get(request: Request):
    rows = list(reversed(_read_processed(max_rows=2000)))
    return templates.TemplateResponse("processed.html", {"request": request, "rows": rows})


@app.get("/logs", response_class=HTMLResponse)
def logs_get(request: Request):
    log_tail = tail_text(LOG_PATH, max_lines=800)
    return templates.TemplateResponse("logs.html", {"request": request, "log_tail": log_tail})


@app.get("/download/output/{filename}")
def download_output(filename: str):
    name = safe_filename(filename)
    path = (OUTPUT_DIR / name).resolve()

    # Ensure the path stays under OUTPUT_DIR
    if OUTPUT_DIR.resolve() not in path.parents and path != OUTPUT_DIR.resolve():
        return _redirect("/outputs")
    if not path.exists() or not path.is_file():
        return _redirect("/outputs")

    return FileResponse(path=str(path), filename=name)
