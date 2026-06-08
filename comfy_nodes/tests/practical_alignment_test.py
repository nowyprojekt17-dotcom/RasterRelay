import argparse
import importlib.util
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFilter


def load_node_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def image_to_tensor(image):
    array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def mask_to_tensor(mask):
    array = np.asarray(mask.convert("L"), dtype=np.float32) / 255.0
    return torch.from_numpy(array).unsqueeze(0)


def tensor_to_image(tensor):
    if tensor.dim() == 4:
        tensor = tensor[0]
    array = (tensor.clamp(0.0, 1.0) * 255.0).round().to(torch.uint8).cpu().numpy()
    if array.shape[-1] == 4:
        return Image.fromarray(array, mode="RGBA")
    return Image.fromarray(array[:, :, :3], mode="RGB")


def save_mask(mask, path):
    if mask.dim() == 3:
        mask = mask[0]
    array = (mask.clamp(0.0, 1.0) * 255.0).round().to(torch.uint8).cpu().numpy()
    Image.fromarray(array, mode="L").save(path)


def simulate_generation_drift(image):
    """Simulates the blur/scale/color drift that can be introduced by VAE/model paths."""
    _, height, width, _ = image.shape
    channels_first = image.permute(0, 3, 1, 2)
    smaller = F.interpolate(
        channels_first,
        size=(max(1, height - 6), max(1, width - 6)),
        mode="bilinear",
        align_corners=False,
    )
    restored = F.interpolate(smaller, size=(height, width), mode="bilinear", align_corners=False)
    drifted = restored.permute(0, 2, 3, 1)
    return (drifted * 1.045 + 0.025).clamp(0.0, 1.0)


def mean_abs_in_mask(a, b, mask):
    expanded = mask.unsqueeze(-1)
    denom = expanded.sum().clamp(min=1.0)
    return ((a[..., :3] - b[..., :3]).abs() * expanded).sum().item() / denom.item()


def max_abs_in_mask(a, b, mask):
    expanded = mask.unsqueeze(-1)
    values = (a[..., :3] - b[..., :3]).abs() * expanded
    return values.max().item()


def run_practical_alignment_test(source_image, output_root):
    repo_root = Path(__file__).resolve().parents[2]
    match_module = load_node_module(
        "rasterrelay_match_and_align_practical",
        repo_root / "comfy_nodes" / "nodes" / "match_and_align.py",
    )
    pad_module = load_node_module(
        "rasterrelay_pad_to_document_practical",
        repo_root / "comfy_nodes" / "nodes" / "pad_to_document.py",
    )

    run_dir = output_root / f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-alignment-practical-test"
    run_dir.mkdir(parents=True, exist_ok=True)

    doc_w = 1024
    doc_h = 768
    crop_l = 257
    crop_t = 221
    crop_w = 317
    crop_h = 413
    grid_size = 16

    source = Image.open(source_image)
    doc = source.convert("RGB").resize((doc_w, doc_h), Image.Resampling.BICUBIC)

    full_mask = Image.new("L", (doc_w, doc_h), 0)
    draw = ImageDraw.Draw(full_mask)
    selection_l = crop_l + 74
    selection_t = crop_t + 92
    selection_r = selection_l + 156
    selection_b = selection_t + 205
    draw.rounded_rectangle((selection_l, selection_t, selection_r, selection_b), radius=22, fill=255)
    full_mask = full_mask.filter(ImageFilter.GaussianBlur(radius=3))

    doc_tensor = image_to_tensor(doc)
    full_mask_tensor = mask_to_tensor(full_mask)

    aligner = match_module.RasterRelaySmartCropAligner()
    trimmer = match_module.RasterRelaySmartCropTrimmer()
    drift_matcher = match_module.RasterRelayVaeDriftMatch()
    padder = pad_module.RasterRelayPadToDocument()

    aligned_image, aligned_mask, pad_l, pad_t, pad_r, pad_b = aligner.align(
        document_image=doc_tensor,
        document_mask=full_mask_tensor,
        crop_left=crop_l,
        crop_top=crop_t,
        crop_width=crop_w,
        crop_height=crop_h,
        grid_size=grid_size,
    )
    original_crop, crop_mask = trimmer.trim(aligned_image, aligned_mask, pad_l, pad_t, pad_r, pad_b)

    generated_aligned = simulate_generation_drift(aligned_image)
    generated_crop, _ = trimmer.trim(generated_aligned, aligned_mask, pad_l, pad_t, pad_r, pad_b)

    matched_crop, = drift_matcher.match_drift(
        original_crop=original_crop,
        generated_crop=generated_crop,
        mask=crop_mask,
        blend_radius=0,
        restore_unmasked=True,
    )

    unmasked = (crop_mask <= 0.0001).to(torch.float32)
    selected = (crop_mask >= 0.999).to(torch.float32)
    unmasked_max_diff_before = max_abs_in_mask(generated_crop, original_crop, unmasked)
    unmasked_max_diff_after = max_abs_in_mask(matched_crop, original_crop, unmasked)
    selected_mean_diff_after = mean_abs_in_mask(matched_crop, original_crop, selected)

    if aligned_image.shape[1] % grid_size != 0 or aligned_image.shape[2] % grid_size != 0:
        raise AssertionError(f"Aligned crop is not grid-safe: {aligned_image.shape[2]}x{aligned_image.shape[1]}")
    if original_crop.shape[1:3] != (crop_h, crop_w):
        raise AssertionError(f"Trimmed crop mismatch: expected {crop_w}x{crop_h}, got {original_crop.shape[2]}x{original_crop.shape[1]}")
    if unmasked_max_diff_before <= 0.001:
        raise AssertionError("Synthetic drift did not create a measurable reference-area mismatch")
    if unmasked_max_diff_after > 0.000001:
        raise AssertionError(f"VAE drift match failed: unmasked max diff={unmasked_max_diff_after}")
    if selected_mean_diff_after <= 0.002:
        raise AssertionError("Selected region was not meaningfully changed")

    padded_output, = padder.pad(
        image=matched_crop,
        mask=crop_mask,
        crop_left=crop_l,
        crop_top=crop_t,
        crop_width=crop_w,
        crop_height=crop_h,
        doc_width=doc_w,
        doc_height=doc_h,
        alpha_mode="crop",
    )

    alpha = padded_output[..., 3]
    outside_alpha_max = torch.cat([
        alpha[:, :crop_t, :].flatten(),
        alpha[:, crop_t + crop_h:, :].flatten(),
        alpha[:, crop_t:crop_t + crop_h, :crop_l].flatten(),
        alpha[:, crop_t:crop_t + crop_h, crop_l + crop_w:].flatten(),
    ]).max().item()
    if outside_alpha_max > 0.000001:
        raise AssertionError(f"Padded output alpha leaked outside crop: {outside_alpha_max}")
    crop_alpha_min = alpha[:, crop_t:crop_t + crop_h, crop_l:crop_l + crop_w].min().item()
    if crop_alpha_min < 0.999999:
        raise AssertionError(f"Generated crop should stay fully present in PNG alpha, min={crop_alpha_min}")

    doc.save(run_dir / "doc-source.png")
    full_mask.save(run_dir / "mask-full-doc.png")
    tensor_to_image(aligned_image).save(run_dir / "aligned-crop.png")
    tensor_to_image(original_crop).save(run_dir / "original-crop.png")
    save_mask(crop_mask, run_dir / "crop-mask.png")
    tensor_to_image(generated_crop).save(run_dir / "simulated-drift-crop.png")
    tensor_to_image(matched_crop).save(run_dir / "vae-drift-matched-crop.png")
    tensor_to_image(padded_output).save(run_dir / "padded-output.png")

    report = f"""# Practical alignment test - {datetime.now().strftime('%Y-%m-%d')}

This test uses a real source image and a non-grid crop to validate the RasterRelay alignment/matching nodes without running a full model.

| Check | Value |
|---|---:|
| Document size | {doc_w} x {doc_h} |
| Original crop | x={crop_l}, y={crop_t}, {crop_w} x {crop_h} |
| Grid size | {grid_size} |
| Aligned crop | {aligned_image.shape[2]} x {aligned_image.shape[1]} |
| Trimmed crop | {original_crop.shape[2]} x {original_crop.shape[1]} |
| Pad left/top/right/bottom | {pad_l}/{pad_t}/{pad_r}/{pad_b} |
| Unmasked max diff before matching | {unmasked_max_diff_before:.8f} |
| Unmasked max diff after matching | {unmasked_max_diff_after:.8f} |
| Selected mean diff after matching | {selected_mean_diff_after:.8f} |
| Outside-crop alpha max | {outside_alpha_max:.8f} |
| Crop alpha min | {crop_alpha_min:.8f} |

## Result

PASS. The aligned crop stayed grid-safe without resizing, the trimmer restored the exact Photoshop crop size, `RasterRelayVaeDriftMatch` restored unmasked pixels to exact original values after simulated VAE/scale/color drift, and the output PNG kept the full generated crop present for Photoshop layer-mask editing.

## Artifacts

- `doc-source.png`
- `mask-full-doc.png`
- `aligned-crop.png`
- `original-crop.png`
- `crop-mask.png`
- `simulated-drift-crop.png`
- `vae-drift-matched-crop.png`
- `padded-output.png`
"""
    (run_dir / "REPORT.md").write_text(report, encoding="utf-8")
    print(f"PRACTICAL ALIGNMENT TEST SUCCEEDED: {run_dir}")
    return run_dir


def main():
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-image",
        default=str(repo_root / "Testy" / "Obrazy do testowania" / "envato-labs-ai-da532839-090d-4b70-9e60-1ed61c2e94a5.jpg"),
    )
    parser.add_argument(
        "--output-root",
        default=str(repo_root / "Testy" / "Wyniki testów"),
    )
    args = parser.parse_args()
    run_practical_alignment_test(Path(args.source_image), Path(args.output_root))


if __name__ == "__main__":
    main()
