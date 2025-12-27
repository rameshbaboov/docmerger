import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WebUIConfig:
    interval_seconds: int = 300


def load_config(path: Path) -> WebUIConfig:
    """Load config from a json file. Invalid/missing values use defaults."""
    if not path.exists():
        return WebUIConfig()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        interval = int(data.get("interval_seconds", 300))
        if interval <= 0:
            interval = 300
        return WebUIConfig(interval_seconds=interval)
    except Exception:
        return WebUIConfig()


def save_config(path: Path, cfg: WebUIConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"interval_seconds": int(cfg.interval_seconds)}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
