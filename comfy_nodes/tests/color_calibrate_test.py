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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok - {name}")
    print("All color_calibrate tests passed.")
