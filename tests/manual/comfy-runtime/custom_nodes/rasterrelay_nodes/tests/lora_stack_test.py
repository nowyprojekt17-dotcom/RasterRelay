import importlib.util
import sys
import types
from pathlib import Path


def load_lora_stack_with_mocks():
    folder_paths = types.ModuleType("folder_paths")
    folder_paths.get_full_path_or_raise = lambda kind, name: (_ for _ in ()).throw(FileNotFoundError(name))

    comfy = types.ModuleType("comfy")
    comfy_utils = types.ModuleType("comfy.utils")
    comfy_sd = types.ModuleType("comfy.sd")
    comfy_utils.load_torch_file = lambda path, safe_load=True: {"mock": "weights"}
    comfy_sd.load_lora_for_models = lambda model, clip, sd, strength_model, strength_clip: (
        f"{model}+lora:{strength_model}",
        f"{clip}+lora:{strength_clip}",
    )
    comfy.utils = comfy_utils
    comfy.sd = comfy_sd

    sys.modules["folder_paths"] = folder_paths
    sys.modules["comfy"] = comfy
    sys.modules["comfy.utils"] = comfy_utils
    sys.modules["comfy.sd"] = comfy_sd

    path = Path(__file__).resolve().parents[1] / "nodes" / "lora_stack.py"
    spec = importlib.util.spec_from_file_location("rasterrelay_lora_stack_test_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RasterRelayLoraStack, folder_paths


def assert_raises(expected, callback):
    try:
        callback()
    except expected:
        return
    raise AssertionError(f"Expected {expected.__name__}")


def test_empty_loras_returns_original_model_and_clip():
    stack_class, _ = load_lora_stack_with_mocks()
    stack = stack_class()

    model, clip = stack.apply_loras("model", "clip", "[]")

    assert model == "model"
    assert clip == "clip"


def test_invalid_json_raises_clear_error():
    stack_class, _ = load_lora_stack_with_mocks()
    stack = stack_class()

    assert_raises(ValueError, lambda: stack.apply_loras("model", "clip", "{bad json"))


def test_missing_lora_raises_instead_of_silent_skip():
    stack_class, _ = load_lora_stack_with_mocks()
    stack = stack_class()

    assert_raises(
        FileNotFoundError,
        lambda: stack.apply_loras("model", "clip", '[{"name":"missing.safetensors"}]'),
    )


def test_valid_lora_supports_camel_and_snake_strengths():
    stack_class, folder_paths = load_lora_stack_with_mocks()
    folder_paths.get_full_path_or_raise = lambda kind, name: "mock/path.safetensors"
    stack = stack_class()

    model, clip = stack.apply_loras(
        "model",
        "clip",
        '[{"name":"style.safetensors","strengthModel":0.75,"strength_clip":0.5}]',
    )

    assert model == "model+lora:0.75"
    assert clip == "clip+lora:0.5"


if __name__ == "__main__":
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
            print(f"ok - {name}")
