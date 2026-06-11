import importlib.util
from pathlib import Path

import torch


def load_grain_transfer():
    path = Path(__file__).resolve().parents[1] / "nodes" / "grain_transfer.py"
    spec = importlib.util.spec_from_file_location("rasterrelay_grain_transfer_test_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RasterRelayGrainTransfer


def test_grain_transfer_basic():
    """Test basic grain transfer with simple inputs."""
    GrainTransferClass = load_grain_transfer()
    transfer = GrainTransferClass()

    original = torch.rand((1, 100, 100, 3), dtype=torch.float32)
    generated = torch.rand((1, 100, 100, 3), dtype=torch.float32) * 0.5
    mask = torch.zeros((1, 100, 100), dtype=torch.float32)
    mask[:, 30:70, 30:70] = 1.0

    (result,) = transfer.inject_grain(
        original_image=original,
        generated_image=generated,
        mask=mask,
        grain_strength=0.8,
        blur_radius=3,
        edge_feather=16,
        preserve_luminance=True,
    )

    assert result.shape == (1, 100, 100, 3)
    assert result.min() >= 0.0
    assert result.max() <= 1.0


def test_grain_transfer_zero_strength():
    """Test that zero strength returns generated image unchanged."""
    GrainTransferClass = load_grain_transfer()
    transfer = GrainTransferClass()

    original = torch.rand((1, 50, 50, 3), dtype=torch.float32)
    generated = torch.rand((1, 50, 50, 3), dtype=torch.float32) * 0.6
    mask = torch.ones((1, 50, 50), dtype=torch.float32)

    (result,) = transfer.inject_grain(
        original_image=original,
        generated_image=generated,
        mask=mask,
        grain_strength=0.0,
        blur_radius=3,
        edge_feather=10,
        preserve_luminance=True,
    )

    assert torch.allclose(result, generated, atol=0.01)


def test_grain_transfer_with_rgba():
    """Test that RGBA images preserve alpha channel."""
    GrainTransferClass = load_grain_transfer()
    transfer = GrainTransferClass()

    original = torch.rand((1, 40, 40, 4), dtype=torch.float32)
    generated = torch.rand((1, 40, 40, 4), dtype=torch.float32) * 0.7
    mask = torch.ones((1, 40, 40), dtype=torch.float32)

    (result,) = transfer.inject_grain(
        original_image=original,
        generated_image=generated,
        mask=mask,
        grain_strength=0.5,
        blur_radius=2,
        edge_feather=8,
        preserve_luminance=True,
    )

    assert result.shape == (1, 40, 40, 4)
    assert torch.allclose(result[:, :, :, 3], generated[:, :, :, 3])


def test_grain_transfer_empty_mask():
    """Test behavior with empty mask."""
    GrainTransferClass = load_grain_transfer()
    transfer = GrainTransferClass()

    original = torch.rand((1, 50, 50, 3), dtype=torch.float32)
    generated = torch.rand((1, 50, 50, 3), dtype=torch.float32) * 0.5
    mask = torch.zeros((1, 50, 50), dtype=torch.float32)

    (result,) = transfer.inject_grain(
        original_image=original,
        generated_image=generated,
        mask=mask,
        grain_strength=1.0,
        blur_radius=3,
        edge_feather=10,
        preserve_luminance=True,
    )

    assert result.shape == (1, 50, 50, 3)
    assert torch.isfinite(result).all()


def test_grain_transfer_preserve_luminance():
    """Test preserve_luminance parameter."""
    GrainTransferClass = load_grain_transfer()
    transfer = GrainTransferClass()

    original = torch.rand((1, 60, 60, 3), dtype=torch.float32)
    generated = torch.rand((1, 60, 60, 3), dtype=torch.float32) * 0.5
    mask = torch.ones((1, 60, 60), dtype=torch.float32)

    (result_with_lum,) = transfer.inject_grain(
        original_image=original,
        generated_image=generated,
        mask=mask,
        grain_strength=0.8,
        blur_radius=3,
        edge_feather=10,
        preserve_luminance=True,
    )

    (result_without_lum,) = transfer.inject_grain(
        original_image=original,
        generated_image=generated,
        mask=mask,
        grain_strength=0.8,
        blur_radius=3,
        edge_feather=10,
        preserve_luminance=False,
    )

    assert result_with_lum.shape == result_without_lum.shape
    assert torch.isfinite(result_with_lum).all()
    assert torch.isfinite(result_without_lum).all()


def test_grain_transfer_batch():
    """Test batch processing."""
    GrainTransferClass = load_grain_transfer()
    transfer = GrainTransferClass()

    original = torch.rand((2, 50, 50, 3), dtype=torch.float32)
    generated = torch.rand((2, 50, 50, 3), dtype=torch.float32) * 0.6
    mask = torch.zeros((2, 50, 50), dtype=torch.float32)
    mask[:, 15:35, 15:35] = 1.0

    (result,) = transfer.inject_grain(
        original_image=original,
        generated_image=generated,
        mask=mask,
        grain_strength=0.7,
        blur_radius=3,
        edge_feather=12,
        preserve_luminance=True,
    )

    assert result.shape == (2, 50, 50, 3)
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
