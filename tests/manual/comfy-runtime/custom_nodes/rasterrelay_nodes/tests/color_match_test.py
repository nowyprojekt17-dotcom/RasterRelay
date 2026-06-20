import importlib.util
import os
import sys

import torch


spec = importlib.util.spec_from_file_location(
    "color_match",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nodes", "color_match.py"),
)
color_match = importlib.util.module_from_spec(spec)
spec.loader.exec_module(color_match)
RasterRelayColorMatch = color_match.RasterRelayColorMatch


def _make_image(b, h, w, c, r=0.5, g=0.3, b_val=0.7):
    img = torch.zeros(b, h, w, c, dtype=torch.float32)
    img[..., 0] = r
    img[..., 1] = g
    img[..., 2] = b_val
    if c == 4:
        img[..., 3] = 1.0
    return img


def test_identity_reinhard():
    node = RasterRelayColorMatch()
    ref = _make_image(1, 64, 64, 3)
    tgt = ref.clone()
    result, = node.match_colors(ref, tgt, "reinhard_lab", 1.0)
    assert torch.allclose(result, tgt, atol=0.01), f"max diff: {(result - tgt).abs().max()}"


def test_identity_histogram():
    node = RasterRelayColorMatch()
    ref = _make_image(1, 64, 64, 3)
    tgt = ref.clone()
    result, = node.match_colors(ref, tgt, "histogram_match", 1.0)
    assert torch.allclose(result, tgt, atol=0.02), f"max diff: {(result - tgt).abs().max()}"


def test_identity_mkl():
    node = RasterRelayColorMatch()
    ref = _make_image(1, 64, 64, 3)
    tgt = ref.clone()
    result, = node.match_colors(ref, tgt, "mkl_transfer", 1.0)
    assert torch.allclose(result, tgt, atol=0.01), f"max diff: {(result - tgt).abs().max()}"


def test_shift_correction_reinhard():
    node = RasterRelayColorMatch()
    ref = _make_image(1, 64, 64, 3, r=0.5, g=0.4, b_val=0.6)
    tgt = _make_image(1, 64, 64, 3, r=0.7, g=0.5, b_val=0.3)
    result, = node.match_colors(ref, tgt, "reinhard_lab", 1.0)
    assert abs(result[..., 0].mean() - 0.5) < 0.15
    assert abs(result[..., 1].mean() - 0.4) < 0.15
    assert abs(result[..., 2].mean() - 0.6) < 0.15


def test_shift_correction_histogram():
    node = RasterRelayColorMatch()
    ref = torch.rand(1, 128, 128, 3, dtype=torch.float32) * 0.3 + 0.2
    tgt = torch.rand(1, 128, 128, 3, dtype=torch.float32) * 0.3 + 0.6
    result, = node.match_colors(ref, tgt, "histogram_match", 1.0)
    assert result.min() >= 0.0 and result.max() <= 1.0
    assert (result.mean() - ref.mean()).abs() < 0.15


def test_shift_correction_mkl():
    node = RasterRelayColorMatch()
    ref = torch.rand(1, 64, 64, 3, dtype=torch.float32)
    tgt = torch.rand(1, 64, 64, 3, dtype=torch.float32)
    result, = node.match_colors(ref, tgt, "mkl_transfer", 1.0)
    assert result.min() >= 0.0 and result.max() <= 1.0
    assert (result.mean() - ref.mean()).abs() < 0.15


def test_strength_zero_returns_target():
    node = RasterRelayColorMatch()
    ref = _make_image(1, 32, 32, 3, r=0.1, g=0.2, b_val=0.3)
    tgt = _make_image(1, 32, 32, 3, r=0.9, g=0.8, b_val=0.7)
    result, = node.match_colors(ref, tgt, "reinhard_lab", 0.0)
    assert torch.allclose(result, tgt, atol=0.01)


def test_strength_one_full_correction():
    node = RasterRelayColorMatch()
    ref = _make_image(1, 32, 32, 3, r=0.2, g=0.3, b_val=0.4)
    tgt = _make_image(1, 32, 32, 3, r=0.9, g=0.8, b_val=0.7)
    result, = node.match_colors(ref, tgt, "reinhard_lab", 1.0)
    assert not torch.allclose(result, tgt, atol=0.01)


def test_batch_broadcast():
    node = RasterRelayColorMatch()
    ref = torch.rand(1, 32, 32, 3, dtype=torch.float32)
    tgt = torch.rand(4, 32, 32, 3, dtype=torch.float32)
    result, = node.match_colors(ref, tgt, "reinhard_lab", 0.7)
    assert result.shape == tgt.shape


def test_rgba_preserves_alpha():
    node = RasterRelayColorMatch()
    ref = _make_image(1, 32, 32, 4, r=0.5, g=0.3, b_val=0.7)
    tgt = _make_image(1, 32, 32, 4, r=0.2, g=0.8, b_val=0.4)
    result, = node.match_colors(ref, tgt, "reinhard_lab", 1.0)
    assert result.shape[-1] == 4
    assert torch.allclose(result[..., 3], tgt[..., 3], atol=0.01)


def test_mask_applies_only_inside():
    node = RasterRelayColorMatch()
    ref = _make_image(1, 64, 64, 3, r=0.8, g=0.2, b_val=0.2)
    tgt = _make_image(1, 64, 64, 3, r=0.2, g=0.8, b_val=0.8)
    mask = torch.zeros(1, 64, 64, dtype=torch.float32)
    mask[:, 16:48, 16:48] = 1.0
    result, = node.match_colors(ref, tgt, "reinhard_lab", 1.0, mask=mask)
    outside = result[:, :6, :, :]
    assert torch.allclose(outside, tgt[:, :6, :, :], atol=0.01)


def test_preserve_luminance():
    node = RasterRelayColorMatch()
    ref = torch.ones(1, 32, 32, 3, dtype=torch.float32) * 0.5
    ref[..., 1] *= 0.3
    ref[..., 2] *= 0.8
    tgt = torch.ones(1, 32, 32, 3, dtype=torch.float32) * 0.9
    result_full, = node.match_colors(ref, tgt, "reinhard_lab", 1.0, preserve_luminance=False)
    result_preserve, = node.match_colors(ref, tgt, "reinhard_lab", 1.0, preserve_luminance=True)
    assert not torch.allclose(result_full, result_preserve, atol=0.01)


def test_no_nan():
    node = RasterRelayColorMatch()
    ref = torch.zeros(1, 32, 32, 3, dtype=torch.float32) + 0.5
    tgt = torch.ones(1, 32, 32, 3, dtype=torch.float32)
    for method in ["reinhard_lab", "histogram_match", "mkl_transfer"]:
        result, = node.match_colors(ref, tgt, method, 1.0)
        assert not torch.isnan(result).any(), f"{method} produced NaN"
        assert not torch.isinf(result).any(), f"{method} produced Inf"


def test_different_resolutions():
    node = RasterRelayColorMatch()
    ref = torch.rand(1, 100, 100, 3, dtype=torch.float32)
    tgt = torch.rand(1, 64, 64, 3, dtype=torch.float32)
    for method in ["reinhard_lab", "histogram_match", "mkl_transfer"]:
        result, = node.match_colors(ref, tgt, method, 0.5)
        assert result.shape == tgt.shape


def test_grayscale_no_colour_introduced():
    node = RasterRelayColorMatch()
    values = torch.linspace(0, 1, 256, dtype=torch.float32)
    gray = values.view(1, 16, 16, 1).repeat(1, 1, 1, 3)
    result, = node.match_colors(gray, gray, "reinhard_lab", 0.5)
    assert (result[..., 0] - result[..., 1]).abs().max() < 0.05


def test_mkl_preserve_luminance():
    node = RasterRelayColorMatch()
    ref = torch.rand(1, 32, 32, 3, dtype=torch.float32)
    tgt = torch.rand(1, 32, 32, 3, dtype=torch.float32)
    result, = node.match_colors(ref, tgt, "mkl_transfer", 1.0, preserve_luminance=True)
    assert result.min() >= 0.0 and result.max() <= 1.0


if __name__ == "__main__":
    tests = [
        test_identity_reinhard,
        test_identity_histogram,
        test_identity_mkl,
        test_shift_correction_reinhard,
        test_shift_correction_histogram,
        test_shift_correction_mkl,
        test_strength_zero_returns_target,
        test_strength_one_full_correction,
        test_batch_broadcast,
        test_rgba_preserves_alpha,
        test_mask_applies_only_inside,
        test_preserve_luminance,
        test_no_nan,
        test_different_resolutions,
        test_grayscale_no_colour_introduced,
        test_mkl_preserve_luminance,
    ]

    passed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {fn.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
