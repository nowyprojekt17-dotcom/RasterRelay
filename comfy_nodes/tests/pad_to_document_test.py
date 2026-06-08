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


if __name__ == "__main__":
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
            print(f"ok - {name}")
