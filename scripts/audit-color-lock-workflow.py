#!/usr/bin/env python
"""
Run a deterministic RasterRelay color-lock audit against a running ComfyUI.

The audit submits the production workflow on a synthetic source/mask pair and
verifies the final PNG invariant that matters for Photoshop:

1. Pixels with zero output alpha composite back to the source with max diff 0.
2. Pixels with zero output alpha also carry source RGB in the PNG itself.
3. Pixels with positive output alpha preserve source hue and saturation after
   compositing, allowing generated value/luminance structure without
   model-colour drift. RGB channel-difference chroma is also reported as a
   diagnostic for older lock modes.
4. SaveImage returned alpha_bbox metadata so the Photoshop panel can skip the
   broad layer mask and rely on PNG change alpha.

Start ComfyUI with writable input/output directories when running from the
sandbox, for example:

  python main.py --listen 127.0.0.1 --port 8188 ^
    --input-directory C:\\Users\\Mierz\\Desktop\\RasterRelay\\tests\\manual\\comfy-input ^
    --output-directory C:\\Users\\Mierz\\Desktop\\RasterRelay\\tests\\manual\\comfy-output ^
    --temp-directory C:\\Users\\Mierz\\Desktop\\RasterRelay\\tests\\manual\\comfy-temp
"""

from __future__ import annotations

import argparse
import io
import json
import re
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps


def wait_server(base_url: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/system_stats", timeout=5)
            if response.ok:
                return response.json()
            last_error = f"HTTP {response.status_code}"
        except Exception as error:  # pragma: no cover - diagnostic path
            last_error = repr(error)
        time.sleep(2)
    raise RuntimeError(f"ComfyUI did not become ready: {last_error}")


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def upload_png(base_url: str, name: str, image: Image.Image) -> dict:
    response = requests.post(
        f"{base_url}/upload/image",
        files={"image": (name, png_bytes(image), "image/png")},
        data={"type": "input", "overwrite": "true"},
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Upload failed for {name}: HTTP {response.status_code}: {response.text[:500]}")
    return response.json()


def set_workflow_input(workflow: dict, mapping_item, value) -> None:
    if isinstance(mapping_item, list):
        for item in mapping_item:
            set_workflow_input(workflow, item, value)
        return
    workflow[str(mapping_item["nodeId"])]["inputs"][mapping_item["inputName"]] = value


def get_comfy_input_names(node_info: dict | None) -> set[str]:
    inputs = (node_info or {}).get("input") or {}
    names: set[str] = set()
    for section in ("required", "optional", "hidden"):
        names.update((inputs.get(section) or {}).keys())
    return names


def find_unsupported_workflow_inputs(workflow: dict, object_info: dict) -> list[str]:
    unsupported: list[str] = []
    for node_id, node in workflow.items():
        class_type = node.get("class_type")
        if not class_type or not class_type.startswith("RasterRelay"):
            continue
        input_names = get_comfy_input_names(object_info.get(class_type))
        if not input_names:
            continue
        for input_name in (node.get("inputs") or {}).keys():
            if input_name not in input_names:
                unsupported.append(f"{node_id}:{class_type}.{input_name}")
    return unsupported


def assert_workflow_compatible(repo_root: Path, object_info: dict, workflow_path: Path) -> None:
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    missing_nodes = [
        node_name
        for node_name in ("RasterRelayReferenceColorLock", "RasterRelayPadToDocument", "RasterRelaySaveImage")
        if node_name not in object_info
    ]
    unsupported_inputs = find_unsupported_workflow_inputs(workflow, object_info)

    failures = []
    if missing_nodes:
        failures.append(f"missing required nodes: {', '.join(missing_nodes)}")
    if unsupported_inputs:
        failures.append(
            "unsupported RasterRelay workflow inputs: "
            + ", ".join(unsupported_inputs)
            + ". Reinstall RasterRelay nodes into ComfyUI custom_nodes and restart ComfyUI."
        )
    if failures:
        raise RuntimeError("; ".join(failures))


def wait_history(base_url: str, prompt_id: str, timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = requests.get(f"{base_url}/history/{prompt_id}", timeout=20)
        response.raise_for_status()
        history = response.json()
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(3)
    raise TimeoutError(f"Timed out waiting for prompt {prompt_id}")


def find_first_output_image(history_entry: dict) -> dict:
    for output in history_entry.get("outputs", {}).values():
        images = output.get("images") or []
        if images:
            return images[0]
    raise RuntimeError("Workflow completed without an output image")


def download_output(base_url: str, output_dir: Path, image_meta: dict) -> Path:
    absolute_path = image_meta.get("absolute_path") or image_meta.get("absolutePath")
    if absolute_path and Path(absolute_path).exists():
        return Path(absolute_path)

    if absolute_path:
        response = requests.get(f"{base_url}/rasterrelay/view", params={"path": absolute_path}, timeout=60)
    else:
        response = requests.get(
            f"{base_url}/view",
            params={
                "filename": image_meta["filename"],
                "subfolder": image_meta.get("subfolder") or "",
                "type": image_meta.get("type") or "output",
            },
            timeout=60,
        )
    if not response.ok:
        raise RuntimeError(f"Output download failed: HTTP {response.status_code}: {response.text[:500]}")

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ("downloaded-" + image_meta["filename"].replace("/", "_").replace("\\", "_"))
    path.write_bytes(response.content)
    return path


def synthetic_case(width: int, height: int) -> tuple[Image.Image, Image.Image]:
    source = Image.new("RGB", (width, height), (238, 238, 238))
    draw = ImageDraw.Draw(source)
    draw.rectangle((48, 48, width - 48, height - 48), fill=(42, 111, 219))

    mask = Image.new("RGB", (width, height), (0, 0, 0))
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((64, 64, width - 64, height - 64), fill=(255, 255, 255))
    return source, mask


def practical_case(source_image: Path, width: int, height: int) -> tuple[Image.Image, Image.Image]:
    source = ImageOps.fit(
        Image.open(source_image).convert("RGB"),
        (width, height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    source_array = np.asarray(source).astype(np.float32) / 255.0
    max_channel = source_array.max(axis=-1)
    min_channel = source_array.min(axis=-1)
    saturation = np.where(max_channel > 1e-6, (max_channel - min_channel) / np.maximum(max_channel, 1e-6), 0.0)
    value = max_channel

    yy, xx = np.mgrid[0:height, 0:width]
    center_bias = 1.0 - np.clip(
        np.sqrt(((xx - width / 2.0) / max(width, 1)) ** 2 + ((yy - height / 2.0) / max(height, 1)) ** 2) * 1.8,
        0.0,
        0.85,
    )
    score = saturation * np.clip(value, 0.1, 1.0) * center_bias
    if float(score.max()) <= 0.02:
        center_x = width // 2
        center_y = height // 2
    else:
        center_y, center_x = np.unravel_index(int(score.argmax()), score.shape)

    radius_x = max(28, int(width * 0.18))
    radius_y = max(28, int(height * 0.18))
    left = int(np.clip(center_x - radius_x, 0, width - 1))
    top = int(np.clip(center_y - radius_y, 0, height - 1))
    right = int(np.clip(center_x + radius_x, left + 1, width))
    bottom = int(np.clip(center_y + radius_y, top + 1, height))

    mask_l = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask_l)
    mask_draw.ellipse((left, top, right, bottom), fill=255)
    return source, Image.merge("RGB", (mask_l, mask_l, mask_l))


def parse_mask_box(text: str | None, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not text:
        return None
    parts = [int(round(float(part.strip()))) for part in text.split(",") if part.strip()]
    if len(parts) != 4:
        raise ValueError("--mask-box must be left,top,right,bottom")
    left, top, right, bottom = parts
    left = int(np.clip(left, 0, width - 1))
    top = int(np.clip(top, 0, height - 1))
    right = int(np.clip(right, left + 1, width))
    bottom = int(np.clip(bottom, top + 1, height))
    return left, top, right, bottom


def manual_practical_case(
    source_image: Path,
    width: int,
    height: int,
    mask_box: tuple[int, int, int, int],
    mask_shape: str,
) -> tuple[Image.Image, Image.Image]:
    source = ImageOps.fit(
        Image.open(source_image).convert("RGB"),
        (width, height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    mask_l = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask_l)
    if mask_shape == "rect":
        mask_draw.rectangle(mask_box, fill=255)
    else:
        mask_draw.ellipse(mask_box, fill=255)
    return source, Image.merge("RGB", (mask_l, mask_l, mask_l))


def build_workflow(
    repo_root: Path,
    source_upload: dict,
    mask_upload: dict,
    width: int,
    height: int,
    steps: int,
    prefix: str,
    prompt: str,
    negative_prompt: str,
    workflow_path: Path,
) -> dict:
    mapping_path = workflow_path.with_name(workflow_path.stem + ".mapping.json")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    inputs = mapping["inputs"]

    set_workflow_input(workflow, inputs["sourceImage"], source_upload["name"])
    set_workflow_input(workflow, inputs["selectionMask"], mask_upload["name"])
    set_workflow_input(
        workflow,
        inputs["prompt"],
        prompt,
    )
    set_workflow_input(
        workflow,
        inputs["negativePrompt"],
        negative_prompt,
    )
    set_workflow_input(workflow, inputs["steps"], steps)
    set_workflow_input(workflow, inputs["cfg"], 1)
    set_workflow_input(workflow, inputs["seed"], 777)
    set_workflow_input(workflow, inputs["seedRandomize"], "disable")
    if "lorasJson" in inputs:
        set_workflow_input(workflow, inputs["lorasJson"], "[]")
    if "width" in inputs:
        set_workflow_input(workflow, inputs["width"], width)
    if "height" in inputs:
        set_workflow_input(workflow, inputs["height"], height)
    for key, value in (
        ("cropLeft", 0),
        ("cropTop", 0),
        ("cropWidth", width),
        ("cropHeight", height),
        ("docWidth", width),
        ("docHeight", height),
    ):
        if key in inputs:
            set_workflow_input(workflow, inputs[key], value)

    workflow["80"]["inputs"]["filename_prefix"] = prefix
    return workflow


def seam_band_metrics(composite: np.ndarray, source: np.ndarray, alpha_positive: np.ndarray, band: int = 8) -> dict:
    """Tonal step across the mask boundary.

    Compares the mean colour of a thin ring just INSIDE the patch (generated,
    composited) against a ring just OUTSIDE (original). A visible "stitch" shows
    up as a non-zero step. We also measure the same step on the source image and
    report the excess, so natural content gradients at the boundary are not
    counted as a seam.
    """
    outside = ~alpha_positive
    if not alpha_positive.any() or not outside.any():
        return {"seam_measured": False}
    k = 2 * int(band) + 1
    m = Image.fromarray((alpha_positive.astype(np.uint8) * 255), "L")
    dilated = np.asarray(m.filter(ImageFilter.MaxFilter(k))) > 127
    eroded = np.asarray(m.filter(ImageFilter.MinFilter(k))) > 127
    inner = alpha_positive & (~eroded)   # inside mask, within `band` of the edge
    outer = outside & dilated            # outside mask, within `band` of the edge
    if not inner.any() or not outer.any():
        return {"seam_measured": False}

    comp = composite.astype(np.float32)
    src = source.astype(np.float32)
    lw = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    c_in, c_out = comp[inner].mean(axis=0), comp[outer].mean(axis=0)
    s_in, s_out = src[inner].mean(axis=0), src[outer].mean(axis=0)
    seam_rgb = float(np.abs(c_in - c_out).max())
    src_rgb = float(np.abs(s_in - s_out).max())
    seam_luma = float(abs(float((c_in * lw).sum()) - float((c_out * lw).sum())))
    src_luma = float(abs(float((s_in * lw).sum()) - float((s_out * lw).sum())))
    return {
        "seam_measured": True,
        "seam_band_px": int(band),
        "seam_inner_pixels": int(inner.sum()),
        "seam_outer_pixels": int(outer.sum()),
        "seam_rgb_step_levels": seam_rgb,
        "seam_rgb_step_excess_vs_source_levels": seam_rgb - src_rgb,
        "seam_luma_step_levels": seam_luma,
        "seam_luma_step_excess_vs_source_levels": seam_luma - src_luma,
    }


def measure_result(source: Image.Image, result_path: Path, image_meta: dict, prompt_id: str) -> dict:
    result = Image.open(result_path).convert("RGBA")
    source_array = np.asarray(source.convert("RGB"))
    result_array = np.asarray(result)

    alpha = result_array[..., 3].astype(np.float32) / 255.0
    composite = np.rint(
        result_array[..., :3].astype(np.float32) * alpha[..., None]
        + source_array.astype(np.float32) * (1 - alpha[..., None])
    ).clip(0, 255).astype(np.uint8)

    composite_diff = np.abs(composite.astype(np.int16) - source_array.astype(np.int16)).max(axis=2)
    raw_rgb_diff = np.abs(result_array[..., :3].astype(np.int16) - source_array.astype(np.int16)).max(axis=2)
    alpha_positive = alpha > (0.5 / 255.0)
    alpha_zero = ~alpha_positive
    ys, xs = np.where(alpha_positive)

    def channel_diffs(rgb: np.ndarray) -> np.ndarray:
        rgb16 = rgb.astype(np.int16)
        return np.stack(
            [
                rgb16[..., 0] - rgb16[..., 1],
                rgb16[..., 0] - rgb16[..., 2],
                rgb16[..., 1] - rgb16[..., 2],
            ],
            axis=-1,
        )

    def hsv_hue_saturation(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rgb_float = rgb.astype(np.float32) / 255.0
        red = rgb_float[..., 0]
        green = rgb_float[..., 1]
        blue = rgb_float[..., 2]
        max_channel = rgb_float.max(axis=-1)
        min_channel = rgb_float.min(axis=-1)
        delta = max_channel - min_channel
        hue = np.zeros_like(max_channel)
        active = delta > (2.0 / 255.0)

        red_is_max = active & (max_channel == red)
        green_is_max = active & (max_channel == green)
        blue_is_max = active & (max_channel == blue)
        hue[red_is_max] = ((green[red_is_max] - blue[red_is_max]) / delta[red_is_max]) % 6.0
        hue[green_is_max] = ((blue[green_is_max] - red[green_is_max]) / delta[green_is_max]) + 2.0
        hue[blue_is_max] = ((red[blue_is_max] - green[blue_is_max]) / delta[blue_is_max]) + 4.0
        hue = hue * 60.0
        saturation = np.where(max_channel > 1e-6, delta / np.maximum(max_channel, 1e-6), 0.0)
        return hue, saturation, delta

    def hue_error_degrees(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        diff = np.abs(a - b)
        return np.minimum(diff, 360.0 - diff)

    source_chroma = channel_diffs(source_array)
    composite_chroma = channel_diffs(composite)
    raw_chroma = channel_diffs(result_array[..., :3])
    composite_chroma_error = np.abs(composite_chroma - source_chroma).max(axis=2)
    raw_chroma_error = np.abs(raw_chroma - source_chroma).max(axis=2)
    source_hue, source_saturation, source_delta = hsv_hue_saturation(source_array)
    composite_hue, composite_saturation, _ = hsv_hue_saturation(composite)
    raw_hue, raw_saturation, _ = hsv_hue_saturation(result_array[..., :3])
    hue_checked = alpha_positive & (source_saturation > 0.05) & (source_delta >= (40.0 / 255.0))
    hue_skipped_low_chroma = alpha_positive & (source_saturation > 0.05) & (source_delta < (40.0 / 255.0))
    composite_hue_error = hue_error_degrees(composite_hue, source_hue)
    raw_hue_error = hue_error_degrees(raw_hue, source_hue)
    composite_saturation_error = np.abs(composite_saturation - source_saturation)
    raw_saturation_error = np.abs(raw_saturation - source_saturation)

    in_mask_mean_diff = float(composite_diff[alpha_positive].mean()) if alpha_positive.any() else None
    seam = seam_band_metrics(composite, source_array, alpha_positive)

    report = {
        "prompt_id": prompt_id,
        "result_path": str(result_path),
        "image_meta": image_meta,
        "result_size": list(result.size),
        "alpha_positive_pixels": int(alpha_positive.sum()),
        "alpha_positive_percent": float(alpha_positive.mean() * 100),
        "alpha_bbox": None
        if xs.size == 0
        else {
            "left": int(xs.min()),
            "top": int(ys.min()),
            "right": int(xs.max() + 1),
            "bottom": int(ys.max() + 1),
        },
        "max_diff_where_alpha_zero_after_composite": int(composite_diff[alpha_zero].max()) if alpha_zero.any() else None,
        "max_diff_anywhere_after_composite": int(composite_diff.max()),
        "raw_rgb_max_diff_where_alpha_zero": int(raw_rgb_diff[alpha_zero].max()) if alpha_zero.any() else None,
        "source_chroma_max_error_where_alpha_positive_after_composite": int(composite_chroma_error[alpha_positive].max()) if alpha_positive.any() else None,
        "source_chroma_mean_error_where_alpha_positive_after_composite": float(composite_chroma_error[alpha_positive].mean()) if alpha_positive.any() else None,
        "raw_source_chroma_max_error_where_alpha_positive": int(raw_chroma_error[alpha_positive].max()) if alpha_positive.any() else None,
        "source_hue_checked_pixels": int(hue_checked.sum()),
        "source_hue_skipped_low_chroma_pixels": int(hue_skipped_low_chroma.sum()),
        "source_hue_min_checked_delta_rgb_levels": 40,
        "source_hue_max_error_degrees_where_alpha_positive_after_composite": float(composite_hue_error[hue_checked].max()) if hue_checked.any() else None,
        "source_hue_mean_error_degrees_where_alpha_positive_after_composite": float(composite_hue_error[hue_checked].mean()) if hue_checked.any() else None,
        "raw_source_hue_max_error_degrees_where_alpha_positive": float(raw_hue_error[hue_checked].max()) if hue_checked.any() else None,
        "source_saturation_max_error_where_alpha_positive_after_composite": float(composite_saturation_error[hue_checked].max()) if hue_checked.any() else None,
        "source_saturation_mean_error_where_alpha_positive_after_composite": float(composite_saturation_error[hue_checked].mean()) if hue_checked.any() else None,
        "raw_source_saturation_max_error_where_alpha_positive": float(raw_saturation_error[hue_checked].max()) if hue_checked.any() else None,
        "composite_changed_pixels": int((composite_diff > 0).sum()),
        "composite_changed_percent": float((composite_diff > 0).mean() * 100),
        "in_mask_mean_composite_diff_levels": in_mask_mean_diff,
    }
    report.update(seam)
    return report


def assert_report(report: dict, min_changed_percent: float = 0.0) -> None:
    failures = []
    if not report["image_meta"].get("alpha_bbox"):
        failures.append("SaveImage did not return alpha_bbox metadata")
    if report["max_diff_where_alpha_zero_after_composite"] != 0:
        failures.append("Zero-alpha pixels do not composite exactly to source")
    if report["raw_rgb_max_diff_where_alpha_zero"] != 0:
        failures.append("Zero-alpha pixels do not carry source RGB")
    if (
        report["source_chroma_max_error_where_alpha_positive_after_composite"] is None
        or report["source_chroma_max_error_where_alpha_positive_after_composite"] > 1
    ):
        failures.append("Positive-alpha pixels do not preserve source RGB channel relationships after compositing")
    if (
        report["source_hue_checked_pixels"] > 0
        and report["source_hue_max_error_degrees_where_alpha_positive_after_composite"] is not None
        and report["source_hue_max_error_degrees_where_alpha_positive_after_composite"] > 1.5
    ):
        failures.append("Positive-alpha pixels do not preserve source hue after compositing")
    if report["alpha_positive_pixels"] <= 0:
        failures.append("Result has no visible changed alpha")
    if report["composite_changed_percent"] < float(min_changed_percent):
        failures.append(
            f"Composite changed only {report['composite_changed_percent']:.3f}% of pixels, below required {min_changed_percent:.3f}%"
        )
    if failures:
        raise AssertionError("; ".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", default="tests/manual/comfy-output")
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--prefix", default="RasterRelay/color-lock-audit")
    parser.add_argument("--source-image", default=None)
    parser.add_argument("--case-name", default=None)
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--mask-box", default=None, help="Manual mask box as left,top,right,bottom in audit image coordinates.")
    parser.add_argument("--mask-shape", choices=["ellipse", "rect"], default="ellipse")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--negative-prompt", default=None)
    parser.add_argument("--min-changed-percent", type=float, default=0.0)
    parser.add_argument(
        "--workflow",
        default="photoshop_plugin/workflows/inpainting-api.json",
        help="Workflow JSON to audit (its <stem>.mapping.json must sit next to it).",
    )
    parser.add_argument(
        "--measure-only",
        action="store_true",
        help="Write metrics but skip the pass/fail invariant asserts (for A/B comparison runs).",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    workflow_path = Path(args.workflow)
    if not workflow_path.is_absolute():
        workflow_path = (repo_root / workflow_path).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    source_image = Path(args.source_image).resolve() if args.source_image else None
    case_name = args.case_name or (source_image.stem if source_image else "synthetic")
    case_slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", case_name).strip("-") or "case"
    report_path = output_dir / f"color-lock-audit-report-{case_slug}.json"

    wait_server(args.comfy_url, timeout=180)
    object_info = requests.get(f"{args.comfy_url}/object_info", timeout=30).json()
    assert_workflow_compatible(repo_root, object_info, workflow_path)

    mask_box = parse_mask_box(args.mask_box, args.width, args.height)
    if source_image and mask_box:
        source, mask = manual_practical_case(source_image, args.width, args.height, mask_box, args.mask_shape)
        prompt = args.prompt or "edit the selected element naturally while preserving the exact original colour palette"
        negative_prompt = args.negative_prompt or "color shift, hue shift, saturation shift, tint, altered unmasked area, visible seam"
    elif source_image:
        source, mask = practical_case(source_image, args.width, args.height)
        prompt = args.prompt or "replace the selected region with a plausible in-scene painted detail while preserving the original colour palette"
        negative_prompt = args.negative_prompt or "color shift, hue shift, saturation shift, tint, altered unmasked area, visible seam"
    else:
        source, mask = synthetic_case(args.width, args.height)
        prompt = args.prompt or "replace the blue square with a red circular patch, preserve the gray background exactly"
        negative_prompt = args.negative_prompt or "hard square edges, visible seams, color shift, tint, altered background"

    output_dir.mkdir(parents=True, exist_ok=True)
    audit_source_path = output_dir / f"{case_slug}-audit-source.png"
    audit_mask_path = output_dir / f"{case_slug}-audit-mask.png"
    source.save(audit_source_path)
    mask.save(audit_mask_path)

    source_upload = upload_png(args.comfy_url, f"rasterrelay-color-lock-{case_slug}-source.png", source)
    mask_upload = upload_png(args.comfy_url, f"rasterrelay-color-lock-{case_slug}-mask.png", mask)
    workflow = build_workflow(
        repo_root,
        source_upload,
        mask_upload,
        args.width,
        args.height,
        args.steps,
        args.prefix,
        prompt,
        negative_prompt,
        workflow_path,
    )

    response = requests.post(
        f"{args.comfy_url}/prompt",
        json={"client_id": "rasterrelay-color-lock-audit", "prompt": workflow},
        timeout=60,
    )
    queued = response.json()
    if (not response.ok) or queued.get("error") or queued.get("node_errors"):
        raise RuntimeError(json.dumps(queued, indent=2)[:4000])

    prompt_id = queued["prompt_id"]
    history = wait_history(args.comfy_url, prompt_id, args.timeout)
    if history.get("status", {}).get("status_str") != "success":
        raise RuntimeError(json.dumps(history.get("status"), indent=2))

    image_meta = find_first_output_image(history)
    result_path = download_output(args.comfy_url, output_dir, image_meta)
    report = measure_result(source, result_path, image_meta, prompt_id)
    report["workflow"] = str(workflow_path)
    report["case_name"] = case_name
    report["source_image"] = str(source_image) if source_image else None
    report["prompt"] = prompt
    report["negative_prompt"] = negative_prompt
    report["mask_box"] = list(mask_box) if mask_box else None
    report["mask_shape"] = args.mask_shape
    report["audit_source_path"] = str(audit_source_path)
    report["audit_mask_path"] = str(audit_mask_path)

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if args.measure_only:
        print(f"RasterRelay color-lock metrics written (no assert): {report_path}")
        return 0
    assert_report(report, args.min_changed_percent)
    print(f"RasterRelay color-lock audit OK: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
