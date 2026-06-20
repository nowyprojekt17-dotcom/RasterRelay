"""Unit tests for RasterRelayColorCalibrate (model colour-response inversion)."""
import importlib.util
import os
import torch

_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "color_calibrate", os.path.join(_here, "..", "nodes", "color_calibrate.py")
)
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)
RasterRelayColorCalibrate = cc.RasterRelayColorCalibrate
RasterRelayReferenceColorLock = cc.RasterRelayReferenceColorLock


def _case(size=128):
    """Original: smooth gradient. Generated: SAME content but with a global
    affine cast (x1.1 + 0.05) and an intentional green patch in the middle."""
    ys = torch.linspace(0.2, 0.6, size).view(size, 1).repeat(1, size)
    orig = torch.stack([ys, ys * 0.9 + 0.05, ys * 0.8 + 0.1], -1).unsqueeze(0)
    cast = lambda img: (img * 1.1 + 0.05).clamp(0, 1)
    gen = cast(orig.clone())
    lo, hi = 48, 80
    gen[:, lo:hi, lo:hi, 0] = 0.10   # intentional green patch (after cast)
    gen[:, lo:hi, lo:hi, 1] = 0.55
    gen[:, lo:hi, lo:hi, 2] = 0.10
    mask = torch.ones((1, size, size))
    return orig, gen, mask, (lo, hi)


def test_drift_areas_recover_original():
    orig, gen, mask, (lo, hi) = _case()
    (out,) = RasterRelayColorCalibrate().calibrate(orig, gen, mask, drift_threshold=0.12, strength=1.0)
    # far from the intent patch the cast must be inverted back to ~original
    err_before = (gen[0, :32, :32] - orig[0, :32, :32]).abs().mean().item()
    err_after = (out[0, :32, :32] - orig[0, :32, :32]).abs().mean().item()
    assert err_after < 0.35 * err_before, f"cast not removed: {err_before:.4f} -> {err_after:.4f}"


def test_intent_hue_survives():
    orig, gen, mask, (lo, hi) = _case()
    (out,) = RasterRelayColorCalibrate().calibrate(orig, gen, mask, drift_threshold=0.12, strength=1.0)
    c = (lo + hi) // 2
    px = out[0, c, c]
    greenness = (px[1] - (px[0] + px[2]) / 2).item()
    assert greenness > 0.30, f"intentional green destroyed: {greenness:.3f}"


def test_identity_when_no_pairs():
    """All pixels strongly changed -> no calibration evidence -> identity."""
    orig = torch.full((1, 64, 64, 3), 0.2)
    gen = torch.full((1, 64, 64, 3), 0.8)
    mask = torch.ones((1, 64, 64))
    (out,) = RasterRelayColorCalibrate().calibrate(orig, gen, mask, drift_threshold=0.10, strength=1.0)
    assert torch.allclose(out, gen)


def test_strength_zero_identity():
    orig, gen, mask, _ = _case()
    (out,) = RasterRelayColorCalibrate().calibrate(orig, gen, mask, drift_threshold=0.12, strength=0.0)
    assert torch.allclose(out, gen)


def test_alpha_preserved():
    orig, gen, mask, _ = _case()
    gen4 = torch.cat([gen, torch.full((1, gen.shape[1], gen.shape[2], 1), 0.5)], -1)
    (out,) = RasterRelayColorCalibrate().calibrate(orig, gen4, mask, drift_threshold=0.12, strength=1.0)
    assert out.shape[-1] == 4 and torch.allclose(out[..., 3], gen4[..., 3])


def test_reference_color_lock_restores_masked_drift_to_original():
    original_px = torch.tensor([0.42, 0.50, 0.58]).view(1, 1, 1, 3)
    generated_px = torch.tensor([0.46, 0.54, 0.62]).view(1, 1, 1, 3)
    original = original_px.repeat(1, 64, 64, 1)
    generated = generated_px.repeat(1, 64, 64, 1)
    mask = torch.ones((1, 64, 64))

    (out,) = RasterRelayReferenceColorLock().lock_color(
        original,
        generated,
        mask,
        lock_threshold=0.075,
        transition_width=0.01,
        blur_radius=16,
        chroma_strength=1.0,
        luma_strength=0.35,
    )

    assert torch.allclose(out[:, 8:56, 8:56], original[:, 8:56, 8:56], atol=1e-5)


def test_reference_color_lock_restores_soft_mask_drift_rgb_to_original():
    original_px = torch.tensor([0.42, 0.50, 0.58]).view(1, 1, 1, 3)
    generated_px = torch.tensor([0.46, 0.54, 0.62]).view(1, 1, 1, 3)
    original = original_px.repeat(1, 64, 64, 1)
    generated = generated_px.repeat(1, 64, 64, 1)
    mask = torch.full((1, 64, 64), 0.35)

    (out,) = RasterRelayReferenceColorLock().lock_color(
        original,
        generated,
        mask,
        lock_threshold=0.075,
        transition_width=0.01,
        blur_radius=16,
        chroma_strength=1.0,
        luma_strength=0.35,
    )

    assert torch.allclose(out[:, 8:56, 8:56], original[:, 8:56, 8:56], atol=1e-5)


def test_reference_color_lock_moves_changed_pixels_toward_source_chroma():
    original_px = torch.tensor([0.36, 0.46, 0.58]).view(1, 1, 1, 3)
    original = original_px.repeat(1, 96, 96, 1)
    generated = original.clone()
    generated[:, 32:64, 32:64, :] = torch.tensor([0.72, 0.34, 0.28])
    mask = torch.zeros((1, 96, 96))
    mask[:, 24:72, 24:72] = 1.0

    (out,) = RasterRelayReferenceColorLock().lock_color(
        original,
        generated,
        mask,
        lock_threshold=0.05,
        transition_width=0.01,
        blur_radius=16,
        chroma_strength=1.0,
        luma_strength=0.35,
    )

    def chroma(pixel):
        return pixel - pixel.mean()

    target_chroma = chroma(original[0, 48, 48])
    before_chroma = chroma(generated[0, 48, 48])
    after_chroma = chroma(out[0, 48, 48])
    assert (after_chroma - target_chroma).abs().mean() < (before_chroma - target_chroma).abs().mean()


def test_reference_color_lock_source_chroma_preserves_original_channel_differences():
    original_px = torch.tensor([0.25, 0.48, 0.70]).view(1, 1, 1, 3)
    generated_px = torch.tensor([0.86, 0.24, 0.18]).view(1, 1, 1, 3)
    original = original_px.repeat(1, 64, 64, 1)
    generated = generated_px.repeat(1, 64, 64, 1)
    mask = torch.ones((1, 64, 64))

    (out,) = RasterRelayReferenceColorLock().lock_color(
        original,
        generated,
        mask,
        lock_threshold=0.01,
        transition_width=0.002,
        blur_radius=16,
        chroma_strength=0.0,
        luma_strength=0.0,
        source_chroma_strength=1.0,
        source_luma_strength=1.0,
    )

    def channel_differences(rgb):
        return torch.stack([
            rgb[..., 0] - rgb[..., 1],
            rgb[..., 0] - rgb[..., 2],
            rgb[..., 1] - rgb[..., 2],
        ], dim=-1)

    source_diffs = channel_differences(original[:, 8:56, 8:56])
    output_diffs = channel_differences(out[:, 8:56, 8:56])
    assert torch.allclose(output_diffs, source_diffs, atol=1e-5)

    weights = torch.tensor([0.2126, 0.7152, 0.0722])
    generated_luma = (generated[:, 8:56, 8:56] * weights).sum(dim=-1)
    output_luma = (out[:, 8:56, 8:56] * weights).sum(dim=-1)
    assert torch.allclose(output_luma, generated_luma, atol=1e-5)


def test_reference_color_lock_source_chroma_limits_luma_to_avoid_channel_clipping():
    original_px = torch.tensor([0.04, 0.35, 0.88]).view(1, 1, 1, 3)
    generated_px = torch.tensor([1.0, 1.0, 1.0]).view(1, 1, 1, 3)
    original = original_px.repeat(1, 64, 64, 1)
    generated = generated_px.repeat(1, 64, 64, 1)
    mask = torch.ones((1, 64, 64))

    (out,) = RasterRelayReferenceColorLock().lock_color(
        original,
        generated,
        mask,
        lock_threshold=0.01,
        transition_width=0.002,
        blur_radius=16,
        chroma_strength=0.0,
        luma_strength=0.0,
        source_chroma_strength=1.0,
        source_luma_strength=1.0,
    )

    assert out.min().item() >= 0.0
    assert out.max().item() <= 1.0
    assert torch.allclose(out[..., 0] - out[..., 1], original[..., 0] - original[..., 1], atol=1e-5)
    assert torch.allclose(out[..., 0] - out[..., 2], original[..., 0] - original[..., 2], atol=1e-5)


def test_reference_color_lock_source_chroma_survives_partial_alpha_composite():
    original_px = torch.tensor([0.18, 0.42, 0.71]).view(1, 1, 1, 3)
    generated_px = torch.tensor([0.76, 0.22, 0.14]).view(1, 1, 1, 3)
    original = original_px.repeat(1, 64, 64, 1)
    generated = generated_px.repeat(1, 64, 64, 1)
    mask = torch.ones((1, 64, 64))

    (out,) = RasterRelayReferenceColorLock().lock_color(
        original,
        generated,
        mask,
        lock_threshold=0.01,
        transition_width=0.002,
        blur_radius=16,
        chroma_strength=0.0,
        luma_strength=0.0,
        source_chroma_strength=1.0,
        source_luma_strength=1.0,
    )

    alpha = torch.full_like(out[..., :1], 0.37)
    composite = out * alpha + original * (1.0 - alpha)

    def channel_differences(rgb):
        return torch.stack([
            rgb[..., 0] - rgb[..., 1],
            rgb[..., 0] - rgb[..., 2],
            rgb[..., 1] - rgb[..., 2],
        ], dim=-1)

    assert torch.allclose(channel_differences(composite), channel_differences(original), atol=1e-5)


def test_reference_color_lock_source_saturation_preserves_source_hsv_colour():
    original_px = torch.tensor([0.18, 0.42, 0.71]).view(1, 1, 1, 3)
    generated_px = torch.tensor([0.76, 0.22, 0.14]).view(1, 1, 1, 3)
    original = original_px.repeat(1, 64, 64, 1)
    generated = generated_px.repeat(1, 64, 64, 1)
    mask = torch.ones((1, 64, 64))

    (out,) = RasterRelayReferenceColorLock().lock_color(
        original,
        generated,
        mask,
        lock_threshold=0.01,
        transition_width=0.002,
        blur_radius=16,
        chroma_strength=0.0,
        luma_strength=0.0,
        source_chroma_strength=0.0,
        source_luma_strength=1.0,
        source_saturation_strength=1.0,
    )

    def hue_and_saturation(rgb):
        red = rgb[..., 0]
        green = rgb[..., 1]
        blue = rgb[..., 2]
        max_channel = rgb.amax(dim=-1)
        min_channel = rgb.amin(dim=-1)
        delta = max_channel - min_channel
        hue = torch.zeros_like(max_channel)
        active = delta > 1e-6
        hue = torch.where((max_channel == red) & active, ((green - blue) / delta.clamp(min=1e-6)).remainder(6.0), hue)
        hue = torch.where((max_channel == green) & active, ((blue - red) / delta.clamp(min=1e-6)) + 2.0, hue)
        hue = torch.where((max_channel == blue) & active, ((red - green) / delta.clamp(min=1e-6)) + 4.0, hue)
        hue = hue / 6.0
        saturation = torch.where(max_channel > 1e-6, delta / max_channel.clamp(min=1e-6), torch.zeros_like(max_channel))
        return hue, saturation

    source_hue, source_sat = hue_and_saturation(original)
    out_hue, out_sat = hue_and_saturation(out)
    assert torch.allclose(out_hue, source_hue, atol=1e-5)
    assert torch.allclose(out_sat, source_sat, atol=1e-5)
    assert not torch.allclose(out, original, atol=1e-5)


def test_reference_color_lock_production_combo_ends_with_source_rgb_chroma():
    original_px = torch.tensor([0.18, 0.42, 0.71]).view(1, 1, 1, 3)
    generated_px = torch.tensor([0.76, 0.22, 0.14]).view(1, 1, 1, 3)
    original = original_px.repeat(1, 64, 64, 1)
    generated = generated_px.repeat(1, 64, 64, 1)
    mask = torch.ones((1, 64, 64))

    (out,) = RasterRelayReferenceColorLock().lock_color(
        original,
        generated,
        mask,
        lock_threshold=0.01,
        transition_width=0.002,
        blur_radius=16,
        chroma_strength=0.0,
        luma_strength=0.0,
        source_chroma_strength=1.0,
        source_luma_strength=1.0,
        source_saturation_strength=1.0,
    )

    def channel_differences(rgb):
        return torch.stack([
            rgb[..., 0] - rgb[..., 1],
            rgb[..., 0] - rgb[..., 2],
            rgb[..., 1] - rgb[..., 2],
        ], dim=-1)

    assert torch.allclose(channel_differences(out), channel_differences(original), atol=1e-5)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok - {name}")
    print("All color_calibrate tests passed.")
