import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class JobStatus:
    running: bool
    pid: int | None
    started_at: str | None
    interval_seconds: int | None
    error: str | None = None


class DocMergerJobManager:
    """Start/stop/monitor the docmerger.py process using a PID json file."""

    def __init__(self, project_dir: Path, pid_file: Path):
        self.project_dir = project_dir
        self.pid_file = pid_file

    def _read_pidfile(self) -> dict:
        if not self.pid_file.exists():
            return {}
        try:
            return json.loads(self.pid_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_pidfile(self, payload: dict) -> None:
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _is_pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            if os.name == "posix":
                os.kill(pid, 0)
                return True
            # Best-effort for Windows: terminate check by sending 0 is not available.
            # We treat PID as alive if pidfile exists; stop() still works via taskkill.
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def status(self) -> JobStatus:
        data = self._read_pidfile()
        pid = data.get("pid")
        started_at = data.get("started_at")
        interval_seconds = data.get("interval_seconds")
        if isinstance(pid, int) and self._is_pid_alive(pid):
            return JobStatus(True, pid, started_at, interval_seconds)

        # Stale pid file
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except Exception:
                pass
        return JobStatus(False, None, None, None)

    def start(self, interval_seconds: int) -> JobStatus:
        st = self.status()
        if st.running:
            return st

        script = self.project_dir / "docmerger.py"
        if not script.exists():
            return JobStatus(False, None, None, None, error="docmerger.py not found")

        cmd = [sys.executable, str(script), "--interval", str(int(interval_seconds))]
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.project_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=(os.name == "posix"),
        )

        payload = {
            "pid": proc.pid,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "interval_seconds": int(interval_seconds),
        }
        self._write_pidfile(payload)
        return JobStatus(True, proc.pid, payload["started_at"], int(interval_seconds))

    def stop(self, timeout_seconds: int = 5) -> JobStatus:
        data = self._read_pidfile()
        pid = data.get("pid")
        if not isinstance(pid, int):
            return JobStatus(False, None, None, None)

        try:
            if os.name == "posix":
                os.kill(pid, signal.SIGTERM)
                end = time.time() + timeout_seconds
                while time.time() < end:
                    if not self._is_pid_alive(pid):
                        break
                    time.sleep(0.2)
                if self._is_pid_alive(pid):
                    os.kill(pid, signal.SIGKILL)
            else:
                # Windows best-effort
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
        except Exception:
            pass

        try:
            self.pid_file.unlink()
        except Exception:
            pass

        return JobStatus(False, None, None, None)

    def run_once_async(self) -> None:
        """Run a single merge pass in a separate process (non-blocking)."""
        script = self.project_dir / "docmerger.py"
        if not script.exists():
            return
        cmd = [sys.executable, str(script), "--once"]
        subprocess.Popen(
            cmd,
            cwd=str(self.project_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=(os.name == "posix"),
        )
