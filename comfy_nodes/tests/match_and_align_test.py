import importlib.util
from pathlib import Path
import torch


def load_match_and_align():
    path = Path(__file__).resolve().parents[1] / "nodes" / "match_and_align.py"
    spec = importlib.util.spec_from_file_location("rasterrelay_match_and_align_test_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return (
        module.RasterRelaySmartCropAligner,
        module.RasterRelaySmartCropTrimmer,
        module.RasterRelayVaeDriftMatch,
        module.RasterRelayGrainInjector,
    )


def test_smart_crop_aligner_and_trimmer():
    AlignerClass, TrimmerClass, _, _ = load_match_and_align()
    aligner = AlignerClass()
    trimmer = TrimmerClass()

    # Create dummy full document image (1000 x 1000) and mask
    doc_image = torch.ones((1, 1000, 1000, 3), dtype=torch.float32)
    doc_mask = torch.zeros((1, 1000, 1000), dtype=torch.float32)

    # Let's crop a region that is 317x412 at offset x=10, y=20.
    # Grid size is 16.
    # aligned width should be ((317 + 15) // 16) * 16 = 320.
    # aligned height should be ((412 + 15) // 16) * 16 = 416.
    (
        aligned_image,
        aligned_mask,
        pad_l,
        pad_t,
        pad_r,
        pad_b,
    ) = aligner.align(
        document_image=doc_image,
        document_mask=doc_mask,
        crop_left=10,
        crop_top=20,
        crop_width=317,
        crop_height=412,
        grid_size=16,
    )

    # Assert shape of aligned image is (1, aligned_height, aligned_width, 3)
    assert aligned_image.shape == (1, 416, 320, 3)
    assert aligned_mask.shape == (1, 416, 320)

    # Verify that trimmer restores original crop size of 317x412
    # Mocking generated image / mask with the aligned ones
    trimmed_image, trimmed_mask = trimmer.trim(
        generated_image=aligned_image,
        generated_mask=aligned_mask,
        pad_left=pad_l,
        pad_top=pad_t,
        pad_right=pad_r,
        pad_bottom=pad_b,
    )

    assert trimmed_image.shape == (1, 412, 317, 3)
    assert trimmed_mask.shape == (1, 412, 317)


def test_smart_crop_boundary_handling():
    AlignerClass, _, _, _ = load_match_and_align()
    aligner = AlignerClass()

    doc_image = torch.ones((1, 500, 500, 3), dtype=torch.float32)
    doc_mask = torch.zeros((1, 500, 500), dtype=torch.float32)

    # Crop near left/top boundary (left=0, top=1)
    # Width 317 (needs aligned 320), Height 412 (needs aligned 416)
    # Aligner should shift window right and down to keep bounds in [0, 500] and keep dimensions exact.
    (
        aligned_image,
        _,
        _,
        _,
        _,
        _,
    ) = aligner.align(
        document_image=doc_image,
        document_mask=doc_mask,
        crop_left=0,
        crop_top=1,
        crop_width=317,
        crop_height=412,
        grid_size=16,
    )

    assert aligned_image.shape == (1, 416, 320, 3)


def test_vae_drift_match():
    _, _, DriftMatchClass, _ = load_match_and_align()
    drift_matcher = DriftMatchClass()

    original_crop = torch.zeros((1, 100, 100, 3), dtype=torch.float32)
    # Put a specific value in the unmasked area
    original_crop[:, :, :, :] = 0.5

    generated_crop = torch.ones((1, 100, 100, 3), dtype=torch.float32)

    # Mask: 1 (edited) on left half, 0 (original) on right half
    mask = torch.zeros((1, 100, 100), dtype=torch.float32)
    mask[:, :, :50] = 1.0

    # With blend_radius = 0 (no feathering), the right half (mask=0) should be exactly 0.5 (original_crop)
    # and the left half (mask=1) should be 1.0 (generated_crop)
    (matched,) = drift_matcher.match_drift(
        original_crop=original_crop,
        generated_crop=generated_crop,
        mask=mask,
        blend_radius=0,
        restore_unmasked=True,
    )

    assert matched.shape == (1, 100, 100, 3)
    # Left half (edited) should remain generated (1.0)
    assert torch.allclose(matched[:, :, :40, :], torch.tensor(1.0))
    # Right half (original) should be restored to original (0.5)
    assert torch.allclose(matched[:, :, 60:, :], torch.tensor(0.5))


def test_vae_drift_match_keeps_unmasked_exact_with_blend():
    _, _, DriftMatchClass, _ = load_match_and_align()
    drift_matcher = DriftMatchClass()

    original_crop = torch.rand((1, 80, 80, 3), dtype=torch.float32)
    generated_crop = (original_crop * 0.75 + 0.13).clamp(0.0, 1.0)
    mask = torch.zeros((1, 80, 80), dtype=torch.float32)
    mask[:, 20:60, 20:60] = 1.0

    (matched,) = drift_matcher.match_drift(
        original_crop=original_crop,
        generated_crop=generated_crop,
        mask=mask,
        blend_radius=10,
        restore_unmasked=True,
    )

    unmasked = (mask <= 0.0001).unsqueeze(-1)
    assert torch.allclose(matched[unmasked.expand_as(matched)], original_crop[unmasked.expand_as(original_crop)])


def test_vae_drift_match_binary_mode_avoids_double_soft_masking():
    _, _, DriftMatchClass, _ = load_match_and_align()
    drift_matcher = DriftMatchClass()

    original_crop = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
    generated_crop = torch.ones((1, 8, 8, 3), dtype=torch.float32)
    mask = torch.zeros((1, 8, 8), dtype=torch.float32)
    mask[:, 2:6, 2:6] = 0.25

    (matched,) = drift_matcher.match_drift(
        original_crop=original_crop,
        generated_crop=generated_crop,
        mask=mask,
        blend_radius=0,
        restore_unmasked=True,
    )

    assert torch.allclose(matched[:, 2:6, 2:6, :], torch.tensor(1.0))
    assert torch.allclose(matched[:, :2, :, :], torch.tensor(0.0))


def test_vae_drift_match_resizes_generated_crop_to_original_geometry():
    _, _, DriftMatchClass, _ = load_match_and_align()
    drift_matcher = DriftMatchClass()

    original_crop = torch.full((1, 1338, 16, 3), 0.5, dtype=torch.float32)
    generated_crop = torch.ones((1, 1328, 16, 3), dtype=torch.float32)
    mask = torch.zeros((1, 1338, 16), dtype=torch.float32)
    mask[:, :100, :] = 1.0

    (matched,) = drift_matcher.match_drift(
        original_crop=original_crop,
        generated_crop=generated_crop,
        mask=mask,
        blend_radius=0,
        restore_unmasked=True,
    )

    assert matched.shape == original_crop.shape
    assert torch.allclose(matched[:, :100, :, :], torch.tensor(1.0))
    assert torch.allclose(matched[:, 120:, :, :], original_crop[:, 120:, :, :])


def test_vae_drift_match_soft_mode_keeps_legacy_preblend():
    _, _, DriftMatchClass, _ = load_match_and_align()
    drift_matcher = DriftMatchClass()

    original_crop = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
    generated_crop = torch.ones((1, 8, 8, 3), dtype=torch.float32)
    mask = torch.zeros((1, 8, 8), dtype=torch.float32)
    mask[:, 2:6, 2:6] = 0.25

    (matched,) = drift_matcher.match_drift(
        original_crop=original_crop,
        generated_crop=generated_crop,
        mask=mask,
        blend_radius=0,
        restore_unmasked=True,
        mask_mode="soft",
    )

    assert torch.allclose(matched[:, 2:6, 2:6, :], torch.tensor(0.25))
    assert torch.allclose(matched[:, :2, :, :], torch.tensor(0.0))


def test_grain_injector():
    _, _, _, GrainClass = load_match_and_align()
    injector = GrainClass()

    original_crop = torch.rand((1, 50, 50, 3), dtype=torch.float32)
    generated_crop = torch.ones((1, 50, 50, 3), dtype=torch.float32) * 0.5
    mask = torch.zeros((1, 50, 50), dtype=torch.float32)
    mask[:, 10:40, 10:40] = 1.0

    (grained,) = injector.inject_grain(
        original_crop=original_crop,
        generated_crop=generated_crop,
        mask=mask,
        grain_strength=1.0,
    )

    assert grained.shape == (1, 50, 50, 3)
    # Areas where mask = 0 should have exactly 0.5 (no grain added to unedited regions)
    assert torch.all(grained[:, :10, :10, :] == 0.5)
    # Areas where mask = 1 should have some variance added (grain injected)
    assert not torch.all(grained[:, 10:40, 10:40, :] == 0.5)

    edited_delta = grained[:, 10:40, 10:40, :] - generated_crop[:, 10:40, 10:40, :]
    assert torch.allclose(edited_delta[..., 0], edited_delta[..., 1])
    assert torch.allclose(edited_delta[..., 1], edited_delta[..., 2])


if __name__ == "__main__":
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
            print(f"ok - {name}")
