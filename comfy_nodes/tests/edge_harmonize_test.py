import importlib.util
from pathlib import Path

import torch


def load_edge_harmonize():
    path = Path(__file__).resolve().parents[1] / "nodes" / "edge_harmonize.py"
    spec = importlib.util.spec_from_file_location("rasterrelay_edge_harmonize_test_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RasterRelayEdgeHarmonize


def test_edge_harmonize_basic():
    """Test basic edge harmonization."""
    EdgeHarmonizeClass = load_edge_harmonize()
    harmonizer = EdgeHarmonizeClass()

    original = torch.zeros((1, 80, 80, 3), dtype=torch.float32)
    original[:, :, :, 0] = 0.5  # Red channel

    generated = torch.ones((1, 80, 80, 3), dtype=torch.float32) * 0.8
    # Add artificial halo at edges
    generated[:, :10, :, :] = 0.9
    generated[:, -10:, :, :] = 0.9
    generated[:, :, :10, :] = 0.9
    generated[:, :, -10:, :] = 0.9

    mask = torch.zeros((1, 80, 80), dtype=torch.float32)
    mask[:, 20:60, 20:60] = 1.0

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        edge_width=40,
        strength=1.0,
    )

    assert result.shape == (1, 80, 80, 3)
    assert result.min() >= 0.0
    assert result.max() <= 1.0


def test_edge_harmonize_zero_strength():
    """Test that zero strength returns generated image unchanged."""
    EdgeHarmonizeClass = load_edge_harmonize()
    harmonizer = EdgeHarmonizeClass()

    original = torch.rand((1, 60, 60, 3), dtype=torch.float32)
    generated = torch.rand((1, 60, 60, 3), dtype=torch.float32) * 0.7
    mask = torch.ones((1, 60, 60), dtype=torch.float32)

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        edge_width=30,
        strength=0.0,
    )

    assert torch.allclose(result, generated, atol=0.01)


def test_edge_harmonize_reduces_halo():
    """Test that edge harmonization reduces visible halos."""
    EdgeHarmonizeClass = load_edge_harmonize()
    harmonizer = EdgeHarmonizeClass()

    # Create distinct color difference
    original = torch.zeros((1, 100, 100, 3), dtype=torch.float32)
    original[:, :, :, 0] = 0.3
    original[:, :, :, 1] = 0.6

    generated = torch.zeros((1, 100, 100, 3), dtype=torch.float32)
    generated[:, :, :, 0] = 0.8
    generated[:, :, :, 1] = 0.2
    # Add strong halo at mask boundary
    generated[:, 25:35, :, :] = 0.95  # Bright edge at mask top
    generated[:, 65:75, :, :] = 0.95  # Bright edge at mask bottom

    mask = torch.zeros((1, 100, 100), dtype=torch.float32)
    mask[:, 30:70, 30:70] = 1.0

    # Measure halo before harmonization
    before_diff = (generated[:, 25:35, :, :] - original[:, 25:35, :, :]).abs().mean().item()

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        edge_width=40,
        strength=1.0,
    )

    # Measure difference after harmonization
    after_diff = (result[:, 25:35, :, :] - original[:, 25:35, :, :]).abs().mean().item()

    # Halo should be reduced
    assert after_diff < before_diff, f"Edge harmonization should reduce halo. Before: {before_diff:.4f}, After: {after_diff:.4f}"


def test_edge_harmonize_with_rgba():
    """Test that RGBA images preserve alpha channel."""
    EdgeHarmonizeClass = load_edge_harmonize()
    harmonizer = EdgeHarmonizeClass()

    original = torch.rand((1, 50, 50, 4), dtype=torch.float32)
    generated = torch.rand((1, 50, 50, 4), dtype=torch.float32) * 0.6
    generated[:, :, :, 3] = 1.0  # Alpha

    mask = torch.ones((1, 50, 50), dtype=torch.float32)

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        edge_width=20,
        strength=0.8,
    )

    assert result.shape == (1, 50, 50, 4)
    assert torch.allclose(result[:, :, :, 3], generated[:, :, :, 3])


def test_edge_harmonize_empty_mask():
    """Test behavior with empty mask."""
    EdgeHarmonizeClass = load_edge_harmonize()
    harmonizer = EdgeHarmonizeClass()

    original = torch.rand((1, 60, 60, 3), dtype=torch.float32)
    generated = torch.rand((1, 60, 60, 3), dtype=torch.float32) * 0.5
    mask = torch.zeros((1, 60, 60), dtype=torch.float32)

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        edge_width=30,
        strength=1.0,
    )

    assert result.shape == (1, 60, 60, 3)
    assert torch.isfinite(result).all()


def test_edge_harmonize_batch():
    """Test batch processing."""
    EdgeHarmonizeClass = load_edge_harmonize()
    harmonizer = EdgeHarmonizeClass()

    original = torch.rand((2, 70, 70, 3), dtype=torch.float32)
    generated = torch.rand((2, 70, 70, 3), dtype=torch.float32) * 0.7
    mask = torch.zeros((2, 70, 70), dtype=torch.float32)
    mask[:, 20:50, 20:50] = 1.0

    (result,) = harmonizer.harmonize(
        original_image=original,
        generated_image=generated,
        mask=mask,
        edge_width=25,
        strength=0.9,
    )

    assert result.shape == (2, 70, 70, 3)
    assert torch.isfinite(result).all()


def test_edge_harmonize_different_widths():
    """Test with different edge_width values."""
    EdgeHarmonizeClass = load_edge_harmonize()
    harmonizer = EdgeHarmonizeClass()

    original = torch.rand((1, 80, 80, 3), dtype=torch.float32)
    generated = torch.rand((1, 80, 80, 3), dtype=torch.float32) * 0.6
    mask = torch.zeros((1, 80, 80), dtype=torch.float32)
    mask[:, 25:55, 25:55] = 1.0

    for width in [20, 40, 60]:
        (result,) = harmonizer.harmonize(
            original_image=original,
            generated_image=generated,
            mask=mask,
            edge_width=width,
            strength=1.0,
        )
        assert result.shape == (1, 80, 80, 3)
        assert torch.isfinite(result).all()


if __name__ == "__main__":
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
                print(f"ok - {name}")
            except Exception as e:
                print(f"FAIL - {name}: {e}")
                raise
