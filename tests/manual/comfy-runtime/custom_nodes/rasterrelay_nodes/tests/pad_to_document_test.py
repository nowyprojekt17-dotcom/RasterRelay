import importlib.util
from pathlib import Path

import torch


def load_pad_to_document():
    path = Path(__file__).resolve().parents[1] / "nodes" / "pad_to_document.py"
    spec = importlib.util.spec_from_file_location("rasterrelay_pad_to_document_test_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RasterRelayPadToDocument


def test_resizes_generated_crop_and_uses_crop_alpha_by_default():
    node_class = load_pad_to_document()
    node = node_class()

    image = torch.ones((1, 384, 800, 3), dtype=torch.float32)
    mask = torch.zeros((1, 387, 803), dtype=torch.float32)
    mask[:, 10:377, 20:783] = 0.5

    (result,) = node.pad(
        image=image,
        mask=mask,
        crop_left=5,
        crop_top=7,
        crop_width=803,
        crop_height=387,
        doc_width=900,
        doc_height=500,
    )

    assert result.shape == (1, 500, 900, 4)
    assert torch.all(result[:, 7:394, 5:808, :3] >= 0.99)
    assert result[0, 7, 5, 3].item() == 1
    assert result[0, 17, 25, 3].item() == 1
    assert result[0, 394:, :, 3].sum().item() == 0
    assert result[0, :, 808:, 3].sum().item() == 0


def test_mask_alpha_mode_is_still_available():
    node_class = load_pad_to_document()
    node = node_class()

    image = torch.ones((1, 16, 16, 3), dtype=torch.float32)
    mask = torch.zeros((1, 16, 16), dtype=torch.float32)
    mask[:, 4:12, 4:12] = 0.5

    (result,) = node.pad(
        image=image,
        mask=mask,
        crop_left=2,
        crop_top=3,
        crop_width=16,
        crop_height=16,
        doc_width=24,
        doc_height=24,
        alpha_mode="mask",
    )

    assert result[0, 3, 2, 3].item() == 0
    assert result[0, 7, 6, 3].item() == 0.5


def test_change_alpha_mode_hides_unchanged_pixels_inside_broad_mask():
    node_class = load_pad_to_document()
    node = node_class()

    original = torch.full((1, 16, 16, 3), 0.4, dtype=torch.float32)
    image = original.clone()
    image[:, 6:10, 6:10, :] = torch.tensor([0.8, 0.2, 0.1])
    mask = torch.ones((1, 16, 16), dtype=torch.float32)

    (result,) = node.pad(
        image=image,
        mask=mask,
        crop_left=0,
        crop_top=0,
        crop_width=16,
        crop_height=16,
        doc_width=16,
        doc_height=16,
        alpha_mode="change",
        original_image=original,
        change_threshold=0.02,
        change_transition_width=0.002,
        alpha_grow=0,
        alpha_feather=0,
    )

    assert result[0, 2, 2, 3].item() == 0
    assert torch.allclose(result[0, 2, 2, :3], original[0, 2, 2, :3])
    assert result[0, 8, 8, 3].item() == 1
    assert torch.allclose(result[0, 8, 8, :3], image[0, 8, 8, :3])


def test_change_alpha_precompensates_partial_alpha_composite():
    node_class = load_pad_to_document()
    node = node_class()

    original = torch.full((1, 4, 4, 3), 0.4, dtype=torch.float32)
    image = torch.full((1, 4, 4, 3), 0.5, dtype=torch.float32)
    mask = torch.ones((1, 4, 4), dtype=torch.float32)

    (result,) = node.pad(
        image=image,
        mask=mask,
        crop_left=0,
        crop_top=0,
        crop_width=4,
        crop_height=4,
        doc_width=4,
        doc_height=4,
        alpha_mode="change",
        original_image=original,
        change_threshold=0.1,
        change_transition_width=0.1,
        alpha_grow=0,
        alpha_feather=0,
        precompensate_alpha_composite=True,
    )

    raw_u8 = (result[0, 0, 0, :3] * 255).round()
    alpha_u8 = (result[0, 0, 0, 3] * 255).round()
    original_u8 = (original[0, 0, 0] * 255).round()
    desired_u8 = (image[0, 0, 0] * 255).round()
    composite_u8 = ((raw_u8 * alpha_u8 + original_u8 * (255 - alpha_u8)) / 255).round()

    assert 0 < alpha_u8.item() < 255
    assert torch.equal(composite_u8, desired_u8)


def test_change_alpha_can_force_opaque_when_composite_lock_is_out_of_gamut():
    node_class = load_pad_to_document()
    node = node_class()

    original = torch.full((1, 4, 4, 3), 0.1, dtype=torch.float32)
    image = torch.full((1, 4, 4, 3), 0.9, dtype=torch.float32)
    mask = torch.ones((1, 4, 4), dtype=torch.float32)

    (result,) = node.pad(
        image=image,
        mask=mask,
        crop_left=0,
        crop_top=0,
        crop_width=4,
        crop_height=4,
        doc_width=4,
        doc_height=4,
        alpha_mode="change",
        original_image=original,
        change_threshold=0.8,
        change_transition_width=0.8,
        alpha_grow=0,
        alpha_feather=0,
        precompensate_alpha_composite=True,
        force_opaque_for_composite_lock=True,
    )

    assert result[0, 0, 0, 3].item() == 1
    assert torch.equal((result[0, 0, 0, :3] * 255).round(), (image[0, 0, 0] * 255).round())


if __name__ == "__main__":
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
            print(f"ok - {name}")
