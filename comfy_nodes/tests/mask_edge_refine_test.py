"""Unit tests for RasterRelayMaskEdgeRefine (guided-filter mask snapping)."""
import importlib.util
import os
import torch

_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "mask_edge_refine", os.path.join(_here, "..", "nodes", "mask_edge_refine.py")
)
mer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mer)
RasterRelayMaskEdgeRefine = mer.RasterRelayMaskEdgeRefine


def _case(size=96):
    """Image with a sharp vertical luminance edge at x=48; soft mask whose
    transition is OFFSET from the image edge (centered at x=40)."""
    img = torch.zeros((1, size, size, 3))
    img[:, :, 48:, :] = 1.0
    xs = torch.arange(size, dtype=torch.float32)
    ramp = ((xs - 32.0) / 16.0).clamp(0.0, 1.0)  # 0 before x=32, 1 after x=48
    mask = ramp.view(1, 1, size).repeat(1, size, 1)
    return img, mask


def test_shape_and_range():
    img, mask = _case()
    (out,) = RasterRelayMaskEdgeRefine().refine(img, mask, radius=8, edge_sensitivity=0.02, strength=1.0)
    assert out.shape == mask.shape
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_transition_snaps_to_image_edge():
    img, mask = _case()
    (out,) = RasterRelayMaskEdgeRefine().refine(img, mask, radius=8, edge_sensitivity=0.02, strength=1.0)
    # input transition is spread over x in [32,48); refined mask should be
    # much closer to a step at the image edge (x=48): values just LEFT of the
    # edge should drop toward 0 relative to the input ramp
    row = out[0, 48, :]
    in_row = mask[0, 48, :]
    # at x=44 the input ramp is 0.75; refined should be substantially lower
    assert row[44] < in_row[44] - 0.15, f"refined {row[44]:.3f} vs input {in_row[44]:.3f}"
    # right side of the edge stays selected
    assert row[56] > 0.9


def test_interior_exterior_preserved():
    img, mask = _case()
    (out,) = RasterRelayMaskEdgeRefine().refine(img, mask, radius=8, edge_sensitivity=0.02, strength=1.0)
    assert torch.allclose(out[mask >= 0.995], mask[mask >= 0.995])
    assert torch.allclose(out[mask <= 0.005], mask[mask <= 0.005])


def test_strength_zero_identity():
    img, mask = _case()
    (out,) = RasterRelayMaskEdgeRefine().refine(img, mask, radius=8, edge_sensitivity=0.02, strength=0.0)
    assert torch.allclose(out, mask)


def test_flat_image_keeps_feather():
    """On a featureless guide the filter must roughly preserve the soft ramp."""
    img = torch.full((1, 96, 96, 3), 0.5)
    _, mask = _case()
    (out,) = RasterRelayMaskEdgeRefine().refine(img, mask, radius=8, edge_sensitivity=0.02, strength=1.0)
    assert (out - mask).abs().max() < 0.25


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok - {name}")
    print("All mask_edge_refine tests passed.")
