import importlib.util
from pathlib import Path
import torch


def load_color_harmonize():
    path = Path(__file__).resolve().parents[1] / "nodes" / "color_harmonize.py"
    spec = importlib.util.spec_from_file_location("rasterrelay_color_harmonize_test_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RasterRelayColorHarmonize


def test_color_harmonize_basic():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.full((1, 64, 64, 3), 0.0, dtype=torch.float32)
    original[..., 0] = 100 / 255.0
    original[..., 1] = 150 / 255.0
    original[..., 2] = 200 / 255.0

    generated = torch.full((1, 64, 64, 3), 0.0, dtype=torch.float32)
    generated[..., 0] = 150 / 255.0
    generated[..., 1] = 100 / 255.0
    generated[..., 2] = 50 / 255.0

    mask = torch.zeros((1, 64, 64), dtype=torch.float32)
    mask[:, 10:50, 10:50] = 1.0

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=0,
        margin=10,
    )

    assert result.shape == generated.shape, f"Expected shape {generated.shape}, got {result.shape}"
    assert result.dtype == torch.float32, f"Expected dtype float32, got {result.dtype}"


def test_color_harmonize_reduces_color_difference():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.full((1, 80, 80, 3), 0.0, dtype=torch.float32)
    original[..., 0] = 0.4
    original[..., 1] = 0.6
    original[..., 2] = 0.8

    generated = torch.full((1, 80, 80, 3), 0.0, dtype=torch.float32)
    generated[..., 0] = 0.8
    generated[..., 1] = 0.3
    generated[..., 2] = 0.1

    mask = torch.zeros((1, 80, 80), dtype=torch.float32)
    mask[:, 15:65, 15:65] = 1.0

    orig_mean = original[:, 15:65, 15:65, :].mean(dim=(0, 1, 2))
    gen_mean_before = generated[:, 15:65, 15:65, :].mean(dim=(0, 1, 2))
    diff_before = (orig_mean - gen_mean_before).abs().mean().item()

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=0,
        margin=10,
    )

    gen_mean_after = result[:, 15:65, 15:65, :].mean(dim=(0, 1, 2))
    diff_after = (orig_mean - gen_mean_after).abs().mean().item()

    assert diff_after < diff_before * 0.2, (
        f"Color difference should be < 20% of original. "
        f"Before: {diff_before:.4f}, After: {diff_after:.4f}"
    )


def test_color_harmonize_strength_zero():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.rand((1, 48, 48, 3), dtype=torch.float32)
    generated = torch.rand((1, 48, 48, 3), dtype=torch.float32)
    mask = torch.zeros((1, 48, 48), dtype=torch.float32)
    mask[:, 10:38, 10:38] = 1.0

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=0.0,
        blend_radius=10,
        margin=10,
    )

    assert torch.allclose(result, generated), (
        "strength=0.0 should return generated_image unchanged"
    )


def test_color_harmonize_strength_one():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.full((1, 48, 48, 3), 0.5, dtype=torch.float32)
    generated = torch.full((1, 48, 48, 3), 0.9, dtype=torch.float32)
    mask = torch.zeros((1, 48, 48), dtype=torch.float32)
    mask[:, 10:38, 10:38] = 1.0

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=10,
        margin=10,
    )

    assert not torch.allclose(result, generated), (
        "strength=1.0 should modify the generated image"
    )


def test_color_harmonize_blend_radius():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.rand((1, 64, 64, 3), dtype=torch.float32)
    generated = torch.rand((1, 64, 64, 3), dtype=torch.float32)
    mask = torch.zeros((1, 64, 64), dtype=torch.float32)
    mask[:, 16:48, 16:48] = 1.0

    (result_no_blend,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=0,
        margin=10,
    )
    assert result_no_blend.shape == generated.shape, (
        f"blend_radius=0: expected shape {generated.shape}, got {result_no_blend.shape}"
    )
    assert torch.isfinite(result_no_blend).all(), "blend_radius=0 produced non-finite values"

    (result_smooth,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=15,
        margin=10,
    )
    assert result_smooth.shape == generated.shape, (
        f"blend_radius=15: expected shape {generated.shape}, got {result_smooth.shape}"
    )
    assert torch.isfinite(result_smooth).all(), "blend_radius=15 produced non-finite values"


def test_color_harmonize_empty_mask():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.rand((1, 48, 48, 3), dtype=torch.float32)
    generated = torch.rand((1, 48, 48, 3), dtype=torch.float32)
    mask = torch.zeros((1, 48, 48), dtype=torch.float32)

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=10,
        margin=10,
    )

    assert torch.allclose(result, generated), (
        "All-zero mask should return generated_image unchanged"
    )


def test_color_harmonize_full_mask():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.rand((1, 48, 48, 3), dtype=torch.float32)
    generated = torch.rand((1, 48, 48, 3), dtype=torch.float32)
    mask = torch.ones((1, 48, 48), dtype=torch.float32)

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=10,
        margin=10,
    )

    assert result.shape == generated.shape, (
        f"All-ones mask: expected shape {generated.shape}, got {result.shape}"
    )
    assert torch.isfinite(result).all(), "All-ones mask produced non-finite values"


def test_color_harmonize_rgba():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.rand((1, 48, 48, 4), dtype=torch.float32)
    generated = torch.rand((1, 48, 48, 4), dtype=torch.float32)
    mask = torch.zeros((1, 48, 48), dtype=torch.float32)
    mask[:, 10:38, 10:38] = 1.0

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=10,
        margin=10,
    )

    assert result.shape == (1, 48, 48, 4), (
        f"RGBA: expected shape (1, 48, 48, 4), got {result.shape}"
    )
    assert torch.allclose(result[..., 3], generated[..., 3]), (
        "RGBA: alpha channel should be preserved from generated_image"
    )


def test_color_harmonize_batch():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.rand((2, 48, 48, 3), dtype=torch.float32)
    generated = torch.rand((2, 48, 48, 3), dtype=torch.float32)
    mask = torch.zeros((2, 48, 48), dtype=torch.float32)
    mask[:, 10:38, 10:38] = 1.0

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        strength=1.0,
        blend_radius=10,
        margin=10,
    )

    assert result.shape == (2, 48, 48, 3), (
        f"Batch: expected shape (2, 48, 48, 3), got {result.shape}"
    )
    assert torch.isfinite(result).all(), "Batch produced non-finite values"


def test_color_harmonize_margin():
    HarmonizeClass = load_color_harmonize()
    harmonizer = HarmonizeClass()

    original = torch.rand((1, 80, 80, 3), dtype=torch.float32)
    generated = torch.rand((1, 80, 80, 3), dtype=torch.float32)
    mask = torch.zeros((1, 80, 80), dtype=torch.float32)
    mask[:, 20:60, 20:60] = 1.0

    for margin_val in [5, 20, 50]:
        (result,) = harmonizer.harmonize(
            original_image=original,
            generated_image=generated,
            mask=mask,
            strength=1.0,
            blend_radius=10,
            margin=margin_val,
        )
        assert result.shape == generated.shape, (
            f"margin={margin_val}: expected shape {generated.shape}, got {result.shape}"
        )
        assert torch.isfinite(result).all(), (
            f"margin={margin_val} produced non-finite values"
        )


if __name__ == "__main__":
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
            print(f"ok - {name}")
