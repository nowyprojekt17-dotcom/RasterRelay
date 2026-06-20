import io
import base64
import os
import tempfile
import numpy as np
from PIL import Image
from aiohttp import web

RASTERRELAY_NODES_VERSION = "2026.06.19-color-lock-v2"
RASTERRELAY_REQUIRED_INPUTS = {
    "RasterRelayReferenceColorLock": [
        "source_chroma_strength",
        "source_luma_strength",
        "source_saturation_strength",
    ],
    "RasterRelayPadToDocument": [
        "precompensate_alpha_composite",
        "force_opaque_for_composite_lock",
    ],
}

# ComfyUI server modules - optional imports for testing
try:
    import server
    import folder_paths
    COMFYUI_AVAILABLE = True
except ImportError:
    COMFYUI_AVAILABLE = False
    server = None
    folder_paths = None


# Register route only if ComfyUI is available
if COMFYUI_AVAILABLE:
    def _safe_child_path(path, roots):
        if not path:
            return None
        candidate = os.path.abspath(path)
        for root in roots:
            if not root:
                continue
            root_abs = os.path.abspath(root)
            try:
                if os.path.commonpath([candidate, root_abs]) == root_abs:
                    return candidate
            except ValueError:
                continue
        return None

    def _fallback_roots():
        roots = [
            os.environ.get("RASTERRELAY_OUTPUT_DIR"),
            os.path.join(tempfile.gettempdir(), "RasterRelay"),
            folder_paths.get_output_directory(),
        ]
        return [root for root in roots if root]

    @server.PromptServer.instance.routes.get("/rasterrelay/info")
    async def rasterrelay_info(_request):
        return web.json_response(
            {
                "ok": True,
                "nodes_version": RASTERRELAY_NODES_VERSION,
                "required_inputs": RASTERRELAY_REQUIRED_INPUTS,
            }
        )

    @server.PromptServer.instance.routes.get("/rasterrelay/view")
    async def view_rasterrelay_file(request):
        path = request.query.get("path", "")
        safe_path = _safe_child_path(path, _fallback_roots())
        if not safe_path:
            return web.json_response({"error": "Path is outside RasterRelay output roots"}, status=403)
        if not os.path.isfile(safe_path):
            return web.json_response({"error": "File not found"}, status=404)
        return web.FileResponse(safe_path, headers={"Content-Type": "image/png"})

    @server.PromptServer.instance.routes.post("/rasterrelay/upload-selection")
    async def upload_selection(request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        try:
            pixels_b64 = data.get("pixels", "")
            sel_width = int(data.get("sel_width", 0))
            sel_height = int(data.get("sel_height", 0))
            full_width = int(data.get("full_width", 0))
            full_height = int(data.get("full_height", 0))
            sel_left = int(data.get("sel_left", 0))
            sel_top = int(data.get("sel_top", 0))
            feather = int(data.get("feather", 0))
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid dimensions"}, status=400)

        if sel_width <= 0 or sel_height <= 0 or full_width <= 0 or full_height <= 0:
            return web.json_response({"error": "Dimensions must be positive"}, status=400)

        if sel_width > 16384 or sel_height > 16384 or full_width > 16384 or full_height > 16384:
            return web.json_response({"error": "Dimensions too large (max 16384)"}, status=400)

        if feather < 0 or feather > 256:
            return web.json_response({"error": "Feather must be between 0 and 256"}, status=400)

        if sel_left < 0 or sel_top < 0:
            return web.json_response({"error": "Selection offsets must be non-negative"}, status=400)

        if sel_left + sel_width > full_width or sel_top + sel_height > full_height:
            return web.json_response({"error": "Selection exceeds full image bounds"}, status=400)

        try:
            sel_pixels = base64.b64decode(pixels_b64)
            sel_array = np.frombuffer(sel_pixels, dtype=np.uint8)
        except Exception:
            return web.json_response({"error": "Invalid pixel data"}, status=400)

        expected_size = sel_width * sel_height
        if len(sel_array) != expected_size:
            return web.json_response(
                {"error": f"Pixel count {len(sel_array)} != {sel_width}x{sel_height}={expected_size}"},
                status=400,
            )

        sel_image = Image.fromarray(sel_array.reshape(sel_height, sel_width), mode="L")

        full_mask = Image.new("L", (full_width, full_height), 0)
        full_mask.paste(sel_image, (sel_left, sel_top))

        if feather > 0:
            from PIL import ImageFilter
            full_mask = full_mask.filter(ImageFilter.GaussianBlur(radius=feather / 3))

        output_dir = folder_paths.get_input_directory()
        import time
        filename = f"rasterrelay-mask-{int(time.time() * 1000)}.png"
        output_path = os.path.join(output_dir, filename)
        full_mask.save(output_path, "PNG")

        return web.json_response({"name": filename, "subfolder": "", "type": "input"})


def register_routes():
    """Register API routes with ComfyUI server (no-op when running outside ComfyUI)."""
    pass
