#!/usr/bin/env python
"""Start an isolated ComfyUI instance and run RasterRelay's color-lock audit."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


def sync_rasterrelay_nodes(repo_root: Path, runtime: Path) -> None:
    source = repo_root / "comfy_nodes"
    target = runtime / "custom_nodes" / "rasterrelay_nodes"

    def ignore(_dir: str, names: list[str]) -> set[str]:
        ignored = {
            ".pytest_cache",
            "__pycache__",
            "*.pyc",
        }
        return {name for name in names if name in ignored or name.endswith(".pyc")}

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=ignore)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--comfy-root", default="E:/AI/ComfyUI")
    parser.add_argument("--python", default=None)
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--source-image", default=None)
    parser.add_argument("--case-name", default=None)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--mask-box", default=None)
    parser.add_argument("--mask-shape", choices=["ellipse", "rect"], default="ellipse")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--negative-prompt", default=None)
    parser.add_argument("--workflow", default=None)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    comfy_root = Path(args.comfy_root).resolve()
    python = Path(args.python).resolve() if args.python else comfy_root / ".venv/Scripts/python.exe"
    runtime = repo_root / "tests/manual/comfy-runtime"
    extra_paths = repo_root / "tests/manual/comfy-extra-model-paths.yaml"
    stdout_path = runtime / "comfy-audit.stdout.log"
    stderr_path = runtime / "comfy-audit.stderr.log"

    for folder in (
        runtime / "input",
        runtime / "output",
        runtime / "temp",
        runtime / "custom_nodes",
    ):
        folder.mkdir(parents=True, exist_ok=True)
    sync_rasterrelay_nodes(repo_root, runtime)

    stdout = stdout_path.open("w", encoding="utf-8", errors="replace")
    stderr = stderr_path.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        [
            str(python),
            str(comfy_root / "main.py"),
            "--listen",
            "127.0.0.1",
            "--port",
            str(args.port),
            "--base-directory",
            str(runtime),
            "--input-directory",
            str(runtime / "input"),
            "--output-directory",
            str(runtime / "output"),
            "--temp-directory",
            str(runtime / "temp"),
            "--extra-model-paths-config",
            str(extra_paths),
            "--database-url",
            f"sqlite:///{(runtime / 'comfyui.db').as_posix()}",
            "--disable-auto-launch",
            "--log-stdout",
        ],
        cwd=str(comfy_root),
        stdout=stdout,
        stderr=stderr,
    )

    try:
        audit_args = [
            str(python),
            str(repo_root / "scripts/audit-color-lock-workflow.py"),
            "--comfy-url",
            f"http://127.0.0.1:{args.port}",
            "--repo-root",
            str(repo_root),
            "--output-dir",
            "tests/manual/comfy-output",
            "--steps",
            str(args.steps),
            "--timeout",
            str(args.timeout),
            "--prefix",
            "RasterRelay/source-chroma-audit",
            "--width",
            str(args.width),
            "--height",
            str(args.height),
        ]
        if args.source_image:
            audit_args.extend(["--source-image", args.source_image])
        if args.case_name:
            audit_args.extend(["--case-name", args.case_name])
        if args.mask_box:
            audit_args.extend(["--mask-box", args.mask_box])
        if args.mask_shape:
            audit_args.extend(["--mask-shape", args.mask_shape])
        if args.prompt:
            audit_args.extend(["--prompt", args.prompt])
        if args.negative_prompt:
            audit_args.extend(["--negative-prompt", args.negative_prompt])
        if args.workflow:
            audit_args.extend(["--workflow", args.workflow])

        audit = subprocess.run(
            audit_args,
            cwd=str(repo_root),
            text=True,
            timeout=args.timeout + 240,
        )
        return audit.returncode
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=20)
        stdout.close()
        stderr.close()
        time.sleep(1)
        print(f"ComfyUI audit process stopped: {process.pid}")
        if stderr_path.exists():
            print("--- ComfyUI stderr tail ---")
            lines = stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()
            print("\n".join(lines[-80:]))


if __name__ == "__main__":
    raise SystemExit(main())
