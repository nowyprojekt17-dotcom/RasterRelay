#!/usr/bin/env python
"""Run practical RasterRelay color-lock audits on hand-selected project images."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


PRACTICAL_CASES = [
    {
        "name": "car-front-black-paint",
        "source": "tests/manual/test-images/car-color-test.jpg",
        "mask_box": "70,96,190,182",
        "mask_shape": "ellipse",
        "prompt": "Add subtle rain droplets and glossy reflection detail on the selected front hood and grille area. Keep the black car paint colour exactly the same as the source image.",
    },
    {
        "name": "gta-poster-vi-badge",
        "source": "tests/manual/test-images/aa0d7431-a296-464e-9b88-a4ee2e9efc89.png",
        "mask_box": "118,144,184,214",
        "mask_shape": "rect",
        "prompt": "Rework the selected VI badge into a slightly embossed printed badge integrated with the poster. Preserve the original orange, magenta and cream colour palette exactly.",
    },
    {
        "name": "desk-can-label",
        "source": "tests/manual/test-images/P1075287.jpg",
        "mask_box": "92,78,151,188",
        "mask_shape": "ellipse",
        "prompt": "Replace the selected drink can label with a cleaner abstract label design while keeping the same red and magenta can colours and the same desk lighting.",
    },
    {
        "name": "pickup-door-graphics",
        "source": "tests/manual/test-images/ComfyUI_00290_.png",
        "mask_box": "88,92,186,154",
        "mask_shape": "rect",
        "prompt": "Remove and simplify the selected door lettering into a clean racing stripe panel. Preserve the truck's teal, red and white livery colours exactly.",
    },
    {
        "name": "offroad-car-body-detail",
        "source": "tests/manual/test-images/ComfyUI_00096_.png",
        "mask_box": "82,112,176,176",
        "mask_shape": "ellipse",
        "prompt": "Add realistic mud splatter and small scratch detail on the selected car body panel. Keep the original yellow paint colour and mountain lighting exactly unchanged.",
    },
    {
        "name": "king-robe-ornament",
        "source": "tests/manual/test-images/domosul2.webp",
        "mask_box": "86,112,172,196",
        "mask_shape": "ellipse",
        "prompt": "Add ornate embroidery detail to the selected robe area while preserving the original gold, cream and smoky warm colour palette exactly.",
    },
    {
        "name": "superhero-costume-trim",
        "source": "tests/manual/test-images/ChatGPT Image 15 cze 2026, 00_18_58.png",
        "mask_box": "80,62,176,190",
        "mask_shape": "ellipse",
        "prompt": "Add fine stitched costume trim and subtle fabric texture in the selected superhero suit area. Preserve the original red, blue and gold comic colours exactly.",
    },
    {
        "name": "chibi-hoodie-emblem",
        "source": "tests/manual/test-images/ChatGPT Image 18 lip 2025, 22_10_57.png",
        "mask_box": "70,100,188,190",
        "mask_shape": "rect",
        "prompt": "Add a small embroidered emblem and seam detail to the selected black hoodie area. Keep the black cloth, skin tones and cartoon line colours exactly unchanged.",
    },
    {
        "name": "rider-suit-panel",
        "source": "tests/manual/test-images/envato-l3dit (72).png",
        "mask_box": "74,70,180,174",
        "mask_shape": "ellipse",
        "prompt": "Add realistic scuffs, zipper detail and panel stitching to the selected rider suit area. Preserve the white, black and grey outfit colours exactly.",
    },
    {
        "name": "lava-car-body-glow",
        "source": "tests/manual/test-images/envato-labs-ai-da532839-090d-4b70-9e60-1ed61c2e94a5.jpg",
        "mask_box": "72,114,178,168",
        "mask_shape": "ellipse",
        "prompt": "Add extra heat shimmer and small surface detail on the selected car body area. Keep the car paint and orange lava lighting colours exactly the same.",
    },
    {
        "name": "black-outfit-texture",
        "source": "tests/manual/test-images/generating-multiple-views-from-one-image-using-flux-kontext-v0-soz7274imchf1.jpg",
        "mask_box": "92,76,166,192",
        "mask_shape": "ellipse",
        "prompt": "Add subtle leather grain, seams and pocket detail to the selected black outfit. Preserve the black clothing colour and skin tones exactly unchanged.",
    },
]

NEGATIVE_PROMPT = (
    "hue shift, saturation shift, color cast, changed paint colour, changed fabric colour, "
    "altered unmasked area, visible seam, halo, pasted edge, washed out colour, oversaturated colour"
)


def sync_rasterrelay_nodes(repo_root: Path, runtime: Path) -> None:
    source = repo_root / "comfy_nodes"
    target = runtime / "custom_nodes" / "rasterrelay_nodes"

    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in {".pytest_cache", "__pycache__"} or name.endswith(".pyc")}

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=ignore)


def wait_comfy_ready(port: int, timeout: int) -> None:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/system_stats", timeout=5) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"ComfyUI did not become ready on port {port}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--comfy-root", default="E:/AI/ComfyUI")
    parser.add_argument("--python", default=None)
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    comfy_root = Path(args.comfy_root).resolve()
    python = Path(args.python).resolve() if args.python else comfy_root / ".venv/Scripts/python.exe"
    runtime = repo_root / "tests/manual/comfy-runtime"
    extra_paths = repo_root / "tests/manual/comfy-extra-model-paths.yaml"
    stdout_path = runtime / "comfy-practical-suite.stdout.log"
    stderr_path = runtime / "comfy-practical-suite.stderr.log"

    for folder in (runtime / "input", runtime / "output", runtime / "temp", runtime / "custom_nodes"):
        folder.mkdir(parents=True, exist_ok=True)
    sync_rasterrelay_nodes(repo_root, runtime)
    suite_output = repo_root / "tests/manual/comfy-output/practical-suite"
    suite_output.mkdir(parents=True, exist_ok=True)
    for old_report in suite_output.glob("color-lock-audit-report-*.json"):
        old_report.unlink()

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
            f"sqlite:///{(runtime / 'comfyui-practical-suite.db').as_posix()}",
            "--disable-auto-launch",
            "--log-stdout",
        ],
        cwd=str(comfy_root),
        stdout=stdout,
        stderr=stderr,
    )

    try:
        wait_comfy_ready(args.port, 180)
        for case in PRACTICAL_CASES:
            print(f"\n=== Practical audit: {case['name']} ===")
            result = subprocess.run(
                [
                    str(python),
                    str(repo_root / "scripts/audit-color-lock-workflow.py"),
                    "--comfy-url",
                    f"http://127.0.0.1:{args.port}",
                    "--repo-root",
                    str(repo_root),
                    "--output-dir",
                    "tests/manual/comfy-output/practical-suite",
                    "--steps",
                    str(args.steps),
                    "--timeout",
                    str(args.timeout),
                    "--prefix",
                    f"RasterRelay/practical-suite/{case['name']}",
                    "--source-image",
                    case["source"],
                    "--case-name",
                    case["name"],
                    "--width",
                    str(args.width),
                    "--height",
                    str(args.height),
                    "--mask-box",
                    case["mask_box"],
                    "--mask-shape",
                    case["mask_shape"],
                    "--prompt",
                    case["prompt"],
                    "--negative-prompt",
                    NEGATIVE_PROMPT,
                    "--min-changed-percent",
                    "0.5",
                ],
                cwd=str(repo_root),
                text=True,
                timeout=args.timeout + 180,
            )
            if result.returncode != 0:
                return result.returncode
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=20)
        stdout.close()
        stderr.close()
        print(f"ComfyUI practical suite process stopped: {process.pid}")
        if stderr_path.exists():
            print("--- ComfyUI stderr tail ---")
            print("\n".join(stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]))


if __name__ == "__main__":
    raise SystemExit(main())
