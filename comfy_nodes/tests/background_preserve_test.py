import importlib.util
from pathlib import Path

import torch


def load_background_preserve():
    path = Path(__file__).resolve().parents[1] / "nodes" / "background_preserve.py"
    spec = importlib.util.spec_from_file_location("rasterrelay_background_preserve_test_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RasterRelayBackgroundPreserve


def test_preserve_keeps_bright_object_color_change():
    PreserveClass = load_background_preserve()
    preserve = PreserveClass()

    original = torch.full((1, 32, 32, 3), 0.82, dtype=torch.float32)
    generated = original.clone()
    generated[:, 8:24, 8:24, 0] = 0.70
    generated[:, 8:24, 8:24, 1] = 0.18
    generated[:, 8:24, 8:24, 2] = 0.16
    mask = torch.ones((1, 32, 32), dtype=torch.float32)

    (result,) = preserve.preserve(
        original_image=original,
        generated_image=generated,
        mask=mask,
        object_luma_max=0.58,
        red_keep_threshold=0.08,
        blend_radius=0,
        change_keep_threshold=0.04,
    )

    assert torch.allclose(result[:, 12:20, 12:20, :], generated[:, 12:20, 12:20, :])


def test_preserve_restores_subtle_background_shift():
    PreserveClass = load_background_preserve()
    preserve = PreserveClass()

    original = torch.full((1, 32, 32, 3), 0.82, dtype=torch.float32)
    generated = torch.full((1, 32, 32, 3), 0.88, dtype=torch.float32)
    mask = torch.ones((1, 32, 32), dtype=torch.float32)

    (result,) = preserve.preserve(
        original_image=original,
        generated_image=generated,
        mask=mask,
        object_luma_max=0.58,
        red_keep_threshold=0.08,
        blend_radius=0,
        change_keep_threshold=0.12,
    )

    assert torch.allclose(result, original)


def test_no_object_bleed_and_no_ghost_outline():
    """Removal case: red object on grey bg; generated = clean bg with slight
    drift. The keep-mask must be dilated so (a) the original RED never bleeds
    back near the object edge, (b) drift far from the object restores exactly."""
    PreserveClass = load_background_preserve()
    preserve = PreserveClass()

    size = 128
    original = torch.full((1, size, size, 3), 0.5, dtype=torch.float32)
    original[:, 40:88, 40:88, 0] = 0.9   # red object
    original[:, 40:88, 40:88, 1] = 0.1
    original[:, 40:88, 40:88, 2] = 0.1
    generated = torch.full((1, size, size, 3), 0.53, dtype=torch.float32)  # removed + drift
    mask = torch.ones((1, size, size), dtype=torch.float32)

    (result,) = preserve.preserve(
        original_image=original,
        generated_image=generated,
        mask=mask,
        object_luma_max=0.58,
        red_keep_threshold=0.08,
        blend_radius=16,
        change_keep_threshold=0.10,
    )

    # (a) no red bleed anywhere the object used to be or near its edge
    region = result[0, 36:92, 36:92, :]
    redness = (region[..., 0] - region[..., 1]).max().item()
    assert redness < 0.05, f"original object bled back: redness {redness:.3f}"
    # (b) far drift corner restored exactly to original
    assert torch.allclose(result[0, :8, :8, :], original[0, :8, :8, :])
