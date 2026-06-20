import importlib.util
from pathlib import Path


def load_save_image():
    path = Path(__file__).resolve().parents[1] / "nodes" / "save_image_rgba.py"
    spec = importlib.util.spec_from_file_location("rasterrelay_save_image_test_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_target_flattens_subfolder_when_creation_is_denied(monkeypatch):
    module = load_save_image()

    def deny_makedirs(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(module.os, "makedirs", deny_makedirs)

    output_dir, subfolder, prefix = module.RasterRelaySaveImage._resolve_output_target(
        r"C:\ComfyUI\output",
        "RasterRelay/inpainting",
    )

    assert output_dir == r"C:\ComfyUI\output"
    assert subfolder == ""
    assert prefix == "RasterRelay_inpainting"


def test_output_target_keeps_subfolder_when_creation_succeeds(monkeypatch):
    module = load_save_image()
    created = []

    def fake_makedirs(path, exist_ok=False):
        created.append((path, exist_ok))

    monkeypatch.setattr(module.os, "makedirs", fake_makedirs)

    output_dir, subfolder, prefix = module.RasterRelaySaveImage._resolve_output_target(
        r"C:\ComfyUI\output",
        "RasterRelay/inpainting",
    )

    assert output_dir == r"C:\ComfyUI\output\RasterRelay"
    assert subfolder == "RasterRelay"
    assert prefix == "inpainting"
    assert created == [(r"C:\ComfyUI\output\RasterRelay", True)]


def test_fallback_target_uses_configured_rasterrelay_output_dir(monkeypatch):
    module = load_save_image()
    created = []

    def fake_makedirs(path, exist_ok=False):
        created.append((path, exist_ok))

    monkeypatch.setattr(module.os, "makedirs", fake_makedirs)
    monkeypatch.setenv("RASTERRELAY_OUTPUT_DIR", r"C:\RasterRelay\out")

    output_dir, subfolder, prefix = module.RasterRelaySaveImage._fallback_target("RasterRelay/inpainting")

    assert output_dir == r"C:\RasterRelay\out"
    assert subfolder == ""
    assert prefix == "RasterRelay_inpainting"
    assert created == [(r"C:\RasterRelay\out", True)]


def test_alpha_bbox_reports_visible_rgba_bounds():
    module = load_save_image()
    array = module.np.zeros((8, 10, 4), dtype=module.np.uint8)
    array[2:6, 3:8, 3] = 255

    assert module.RasterRelaySaveImage._alpha_bbox(array) == {
        "left": 3,
        "top": 2,
        "right": 8,
        "bottom": 6,
        "width": 5,
        "height": 4,
    }


def test_alpha_bbox_is_none_for_fully_transparent_rgba():
    module = load_save_image()
    array = module.np.zeros((8, 10, 4), dtype=module.np.uint8)

    assert module.RasterRelaySaveImage._alpha_bbox(array) is None


def test_saved_png_is_tagged_srgb_and_preserves_alpha(tmp_path, monkeypatch):
    module = load_save_image()

    icc = module._srgb_icc_bytes()
    assert icc, "ImageCms sRGB profile unavailable - cannot tag the PNG as sRGB"

    class FakeFolderPaths:
        @staticmethod
        def get_output_directory():
            return str(tmp_path)

    monkeypatch.setattr(module, "folder_paths", FakeFolderPaths())

    torch = module.torch
    np = module.np
    # BHWC RGBA image: red fill, alpha visible only in an inner box.
    image = torch.zeros((1, 4, 5, 4), dtype=torch.float32)
    image[0, :, :, 0] = 1.0            # R = 255 everywhere
    image[0, 1:3, 1:4, 3] = 1.0        # alpha = 255 in a 2x3 box, else 0

    result = module.RasterRelaySaveImage().save(image, "RasterRelay/icc-test")
    path = Path(result["ui"]["images"][0]["absolute_path"])

    raw = path.read_bytes()
    idat = raw.index(b"IDAT")
    assert b"iCCP" in raw[:idat], "sRGB iCCP chunk must be written before IDAT"

    from PIL import Image as PILImage

    with PILImage.open(path) as reopened:
        assert reopened.mode == "RGBA", "alpha channel must survive the save"
        assert reopened.info.get("icc_profile"), "PNG must carry an embedded ICC profile"
        saved = np.array(reopened)

    expected_alpha = (image[0, :, :, 3].numpy() * 255).round().astype(np.uint8)
    assert (saved[..., 3] == expected_alpha).all(), "alpha channel corrupted by ICC tagging"
    # Tag only - pixel values must be identical (no colour conversion).
    assert (saved[..., 0] == 255).all(), "RGB pixels changed; tagging must not convert pixels"


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
