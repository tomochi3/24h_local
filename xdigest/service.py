"""macOS の launchd（LaunchAgent）に登録する。

- com.xdigest.run   : 毎日 run_hour:run_minute に1回 `xdigest run`（スリープ中だった場合は起きたときに実行）
- com.xdigest.serve : PDF閲覧用サーバーを常時起動（落ちたら再起動）
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .config import Config

RUN_LABEL = "com.xdigest.run"
SERVE_LABEL = "com.xdigest.serve"


def agent_path(label: str) -> Path:
    return Path(f"~/Library/LaunchAgents/{label}.plist").expanduser()


def _base(label: str, args: list[str], cfg: Config, workdir: str, path_env: str) -> dict:
    log = str(cfg.output_dir / f"{label.split('.')[-1]}.log")
    return {"Label": label, "ProgramArguments": args, "WorkingDirectory": workdir,
            "EnvironmentVariables": {"PATH": path_env, "LANG": "ja_JP.UTF-8", "PYTHONUNBUFFERED": "1"},
            "StandardOutPath": log, "StandardErrorPath": log}


def plists(cfg: Config, config_path: str, *, python: str | None = None, workdir: str | None = None,
           path_env: str | None = None) -> dict[str, bytes]:
    python = python or sys.executable
    workdir = workdir or str(Path(__file__).resolve().parent.parent)
    path_env = path_env or os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    cmd = [python, "-m", "xdigest", "--config", config_path]
    run = _base(RUN_LABEL, [*cmd, "run"], cfg, workdir, path_env)
    run["StartCalendarInterval"] = {"Hour": cfg.run_hour, "Minute": cfg.run_minute}
    serve = _base(SERVE_LABEL, [*cmd, "serve"], cfg, workdir, path_env)
    serve.update(RunAtLoad=True, KeepAlive=True, ThrottleInterval=10)
    return {RUN_LABEL: plistlib.dumps(run), SERVE_LABEL: plistlib.dumps(serve)}


def _launchctl(*args: str) -> None:
    subprocess.run(["launchctl", *args], check=False)


def install(cfg: Config, config_path: str) -> None:
    if sys.platform != "darwin":
        raise SystemExit("install は macOS 用です（Linuxでは cron / systemd で `python -m xdigest run` を呼んでください）")
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    for label, content in plists(cfg, str(Path(config_path).expanduser().resolve())).items():
        path = agent_path(label)
        path.parent.mkdir(parents=True, exist_ok=True)
        _launchctl("bootout", f"{domain}/{label}")
        path.write_bytes(content)
        _launchctl("bootstrap", domain, str(path))
        print(f"登録しました: {path}")


def uninstall() -> None:
    domain = f"gui/{os.getuid()}"
    for label in (RUN_LABEL, SERVE_LABEL):
        _launchctl("bootout", f"{domain}/{label}")
        agent_path(label).unlink(missing_ok=True)
        print(f"解除しました: {label}")
