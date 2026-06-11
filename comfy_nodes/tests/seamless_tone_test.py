"""Unit tests for RasterRelaySeamlessTone (low-frequency tone matching)."""
import importlib.util
import os
import torch

_here = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "seamless_tone", os.path.join(_here, "..", "nodes", "seamless_tone.py")
)
seamless_tone = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seamless_tone)
RasterRelaySeamlessTone = seamless_tone.RasterRelaySeamlessTone


def _make_case(size=128, box=48, surround=0.3, patch=0.6):
    """Original is uniform `surround`; generated has a brighter `patch` inside the mask."""
    orig = torch.full((1, size, size, 3), surround)
    gen = orig.clone()
    mask = torch.zeros((1, size, size))
    lo, hi = (size - box) // 2, (size + box) // 2
    gen[:, lo:hi, lo:hi, :] = patch
    mask[:, lo:hi, lo:hi] = 1.0
    return orig, gen, mask, (lo, hi)


def test_output_shape_and_range():
    orig, gen, mask, _ = _make_case()
    (out,) = RasterRelaySeamlessTone().match_tone(orig, gen, mask, tone_radius=20, strength=1.0)
    assert out.shape == gen.shape
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_interior_pulled_toward_surroundings():
    orig, gen, mask, (lo, hi) = _make_case(surround=0.3, patch=0.6)
    (out,) = RasterRelaySeamlessTone().match_tone(orig, gen, mask, tone_radius=20, strength=1.0)
    before = gen[:, lo:hi, lo:hi, :].mean().item()
    after = out[:, lo:hi, lo:hi, :].mean().item()
    # the bright patch (0.6) should move toward the 0.3 surroundings
    assert after < before
    assert abs(after - 0.3) < abs(before - 0.3)


def test_strength_zero_is_identity():
    orig, gen, mask, _ = _make_case()
    (out,) = RasterRelaySeamlessTone().match_tone(orig, gen, mask, tone_radius=20, strength=0.0)
    assert torch.allclose(out, gen)


def test_outside_mask_unchanged():
    orig, gen, mask, (lo, hi) = _make_case()
    (out,) = RasterRelaySeamlessTone().match_tone(orig, gen, mask, tone_radius=20, strength=1.0)
    # a corner well outside the mask must be untouched (mask == 0 there)
    assert torch.allclose(out[:, :8, :8, :], gen[:, :8, :8, :], atol=1e-4)


def test_alpha_channel_preserved():
    orig, gen, mask, _ = _make_case()
    gen4 = torch.cat([gen, torch.full((1, gen.shape[1], gen.shape[2], 1), 0.5)], dim=-1)
    (out,) = RasterRelaySeamlessTone().match_tone(orig, gen4, mask, tone_radius=20, strength=1.0)
    assert out.shape[-1] == 4
    assert torch.allclose(out[..., 3], gen4[..., 3])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok - {name}")
    print("All seamless_tone tests passed.")
