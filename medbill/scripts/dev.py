"""Start MedBill's API and UI together. Defaults to a reproducible, offline synthetic demo."""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent


def dependencies() -> tuple[str, Path]:
    missing = [name for name in ("fastapi", "uvicorn", "pymupdf", "PIL", "reportlab") if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError("Missing Python dependencies: " + ", ".join(missing) + ". Run: python -m pip install -e .")
    node = shutil.which("node")
    vite = ROOT / "web/node_modules/vite/bin/vite.js"
    if not node or not vite.is_file():
        raise RuntimeError("Install Node.js and run npm ci in medbill/web first.")
    if not (ROOT / "data/samples/overcharge/extraction.json").is_file():
        raise RuntimeError("Sample files are missing. Run: python scripts/make_samples.py")
    return node, vite


def port_in_use(port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(.4)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Offline sample workflow, no model or API key (default)")
    mode.add_argument("--local", action="store_true", help="Use the configured local Ollama model for free-form questions and translations")
    parser.add_argument("--check", action="store_true", help="Check dependencies without starting servers")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=5173)
    args = parser.parse_args()
    try:
        if not all(0 < port < 65536 for port in (args.api_port, args.web_port)) or args.api_port == args.web_port:
            raise RuntimeError("Choose distinct API and web ports between 1 and 65535.")
        node, vite = dependencies()
        if args.check:
            print("Ready: Python dependencies, Vite, Node.js, and sample documents are installed.")
            return 0
        busy = [str(port) for port in (args.api_port, args.web_port) if port_in_use(port)]
        if busy:
            raise RuntimeError("Port(s) " + ", ".join(busy) + " already in use. Open the running app or stop its servers before launching another copy.")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    environment = os.environ.copy()
    environment["DEMO_MODE"] = "0" if args.local else "1"
    environment["MEDBILL_API_PORT"] = str(args.api_port)
    if args.local:
        environment["LLM_PROVIDER"] = "ollama"
    commands = [([sys.executable, "-m", "uvicorn", "api.main:app_factory", "--factory", "--host", "127.0.0.1", "--port", str(args.api_port), "--no-access-log"], ROOT),
                ([node, str(vite), "--host", "127.0.0.1", "--port", str(args.web_port), "--strictPort"], ROOT / "web")]
    children = []
    print("MedBill: " + ("LOCAL OLLAMA" if args.local else "OFFLINE SYNTHETIC DEMO"), flush=True)
    print(f"Open http://127.0.0.1:{args.web_port} | API http://127.0.0.1:{args.api_port}/docs | Ctrl+C stops both servers.", flush=True)
    try:
        for command, directory in commands:
            children.append(subprocess.Popen(command, cwd=directory, env=environment,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0))
        while all(child.poll() is None for child in children):
            time.sleep(.4)
        print("A server stopped. See its message above.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        # Only terminate the processes started by this launcher. No ports/process-name killing.
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
