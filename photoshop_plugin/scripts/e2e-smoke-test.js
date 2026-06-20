(() => {
const photoshop = require("photoshop");
const uxp = require("uxp");

const COMFYUI_BASE_URL = "http://127.0.0.1:8188";
const WORKFLOW_FILE_NAME = "workflows/inpainting-api.json";
const WORKFLOW_MAPPING_FILE_NAME = "workflows/inpainting-api.mapping.json";
const TEST_SOURCE_FILE_NAME = "test_assets/can-source.png";
const TEST_CAN_MASK = {
  centerX: 711,
  centerY: 542,
  radiusX: 42,
  radiusY: 68,
  featherPx: 36
};
const TEST_PROMPT =
  "replace only the can in the selected area with a small red ceramic mug held in the hand, preserve the hand, body, face, text and the rest of the image";
const panelHelpers = globalThis.RasterRelayPanelHelpers || {};

function safeTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function getUnitValue(value) {
  if (typeof value === "number") {
    return value;
  }

  return value?.value ?? null;
}

const pngCrcTable = (() => {
  const table = new Uint32Array(256);

  for (let index = 0; index < 256; index += 1) {
    let value = index;

    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }

    table[index] = value >>> 0;
  }

  return table;
})();

function crc32(bytes) {
  let crc = 0xffffffff;

  for (const byte of bytes) {
    crc = pngCrcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }

  return (crc ^ 0xffffffff) >>> 0;
}

function adler32(bytes) {
  let a = 1;
  let b = 0;

  for (const byte of bytes) {
    a = (a + byte) % 65521;
    b = (b + a) % 65521;
  }

  return ((b << 16) | a) >>> 0;
}

function writeUint32(bytes, offset, value) {
  bytes[offset] = (value >>> 24) & 0xff;
  bytes[offset + 1] = (value >>> 16) & 0xff;
  bytes[offset + 2] = (value >>> 8) & 0xff;
  bytes[offset + 3] = value & 0xff;
}

function createPngChunk(type, data) {
  const typeBytes = new Uint8Array([
    type.charCodeAt(0),
    type.charCodeAt(1),
    type.charCodeAt(2),
    type.charCodeAt(3)
  ]);
  const chunk = new Uint8Array(12 + data.length);
  writeUint32(chunk, 0, data.length);
  chunk.set(typeBytes, 4);
  chunk.set(data, 8);

  const crcInput = new Uint8Array(typeBytes.length + data.length);
  crcInput.set(typeBytes, 0);
  crcInput.set(data, typeBytes.length);
  writeUint32(chunk, 8 + data.length, crc32(crcInput));
  return chunk;
}

function createZlibStoredData(rawData) {
  const blockCount = Math.ceil(rawData.length / 65535);
  const output = new Uint8Array(2 + rawData.length + blockCount * 5 + 4);
  let offset = 0;
  let sourceOffset = 0;

  output[offset++] = 0x78;
  output[offset++] = 0x01;

  while (sourceOffset < rawData.length) {
    const blockLength = Math.min(65535, rawData.length - sourceOffset);
    const isFinalBlock = sourceOffset + blockLength >= rawData.length;
    output[offset++] = isFinalBlock ? 0x01 : 0x00;
    output[offset++] = blockLength & 0xff;
    output[offset++] = (blockLength >>> 8) & 0xff;
    output[offset++] = (~blockLength) & 0xff;
    output[offset++] = ((~blockLength) >>> 8) & 0xff;
    output.set(rawData.subarray(sourceOffset, sourceOffset + blockLength), offset);
    offset += blockLength;
    sourceOffset += blockLength;
  }

  writeUint32(output, offset, adler32(rawData));
  return output;
}

function encodePngRgba(width, height, rgbaPixels) {
  const bytesPerRow = width * 4;
  const rawData = new Uint8Array((bytesPerRow + 1) * height);

  for (let row = 0; row < height; row += 1) {
    const rawOffset = row * (bytesPerRow + 1);
    const sourceOffset = row * bytesPerRow;
    rawData[rawOffset] = 0;
    rawData.set(rgbaPixels.subarray(sourceOffset, sourceOffset + bytesPerRow), rawOffset + 1);
  }

  const header = new Uint8Array(13);
  writeUint32(header, 0, width);
  writeUint32(header, 4, height);
  header[8] = 8;
  header[9] = 6;

  const signature = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]);
  const chunks = [
    createPngChunk("IHDR", header),
    createPngChunk("IDAT", createZlibStoredData(rawData)),
    createPngChunk("IEND", new Uint8Array())
  ];
  const png = new Uint8Array(signature.length + chunks.reduce((sum, chunk) => sum + chunk.length, 0));
  let offset = 0;

  png.set(signature, offset);
  offset += signature.length;

  for (const chunk of chunks) {
    png.set(chunk, offset);
    offset += chunk.length;
  }

  return png.buffer;
}

async function readPluginTextFile(relativePath) {
  const pluginFolder = await uxp.storage.localFileSystem.getPluginFolder();
  const parts = relativePath.split("/");
  let entry = pluginFolder;

  for (const part of parts) {
    entry = await entry.getEntry(part);
  }

  return entry.read({ format: uxp.storage.formats.utf8 });
}

async function getPluginFile(relativePath) {
  const pluginFolder = await uxp.storage.localFileSystem.getPluginFolder();
  const parts = relativePath.split("/");
  let entry = pluginFolder;

  for (const part of parts) {
    entry = await entry.getEntry(part);
  }

  return entry;
}

async function loadWorkflowBundle() {
  const workflow = JSON.parse(await readPluginTextFile(WORKFLOW_FILE_NAME));
  const mapping = JSON.parse(await readPluginTextFile(WORKFLOW_MAPPING_FILE_NAME));

  if (mapping.status !== "ready") {
    throw new Error("Workflow mapping is not ready.");
  }

  return { workflow, mapping };
}

async function createTestDocument() {
  const testFile = await getPluginFile(TEST_SOURCE_FILE_NAME);

  await photoshop.core.executeAsModal(
    async () => {
      await photoshop.app.open(testFile);
      await photoshop.action.batchPlay(
        [
          {
            _obj: "set",
            _target: [{ _ref: "channel", _property: "selection" }],
            to: {
              _obj: "ellipse",
              top: { _unit: "pixelsUnit", _value: TEST_CAN_MASK.centerY - TEST_CAN_MASK.radiusY },
              left: { _unit: "pixelsUnit", _value: TEST_CAN_MASK.centerX - TEST_CAN_MASK.radiusX },
              bottom: { _unit: "pixelsUnit", _value: TEST_CAN_MASK.centerY + TEST_CAN_MASK.radiusY },
              right: { _unit: "pixelsUnit", _value: TEST_CAN_MASK.centerX + TEST_CAN_MASK.radiusX }
            }
          }
        ],
        {}
      );
    },
    { commandName: "RasterRelay Create E2E Test Document" }
  );

  return photoshop.app.activeDocument;
}

async function exportDocumentPng(document, dataFolder, prefix) {
  const file = await dataFolder.createFile(`${prefix}-source.png`, { overwrite: true });

  await photoshop.core.executeAsModal(
    async () => {
      await document.saveAs.png(file, { compression: 6 }, true);
    },
    { commandName: "RasterRelay E2E Export Source" }
  );

  return file;
}

function createSoftCanMaskPixels(width, height) {
  const pixels = new Uint8Array(width * height * 4);

  for (let index = 0; index < width * height; index += 1) {
    pixels[index * 4 + 3] = 255;
  }

  const edgeScale = Math.min(TEST_CAN_MASK.radiusX, TEST_CAN_MASK.radiusY);

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const dx = (x - TEST_CAN_MASK.centerX) / TEST_CAN_MASK.radiusX;
      const dy = (y - TEST_CAN_MASK.centerY) / TEST_CAN_MASK.radiusY;
      const distance = Math.sqrt(dx * dx + dy * dy);
      const outsideDistancePx = Math.max(0, (distance - 1) * edgeScale);
      let value = 0;

      if (distance <= 1) {
        value = 255;
      } else if (outsideDistancePx < TEST_CAN_MASK.featherPx) {
        const t = outsideDistancePx / TEST_CAN_MASK.featherPx;
        const smooth = t * t * (3 - 2 * t);
        value = Math.round(255 * (1 - smooth));
      }

      if (value === 0) {
        continue;
      }

      const offset = (y * width + x) * 4;
      pixels[offset] = value;
      pixels[offset + 1] = value;
      pixels[offset + 2] = value;
    }
  }

  return pixels;
}

function createSoftCanMaskGrayscale(width, height) {
  const pixels = new Uint8Array(width * height);
  const edgeScale = Math.min(TEST_CAN_MASK.radiusX, TEST_CAN_MASK.radiusY);

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const dx = (x - TEST_CAN_MASK.centerX) / TEST_CAN_MASK.radiusX;
      const dy = (y - TEST_CAN_MASK.centerY) / TEST_CAN_MASK.radiusY;
      const distance = Math.sqrt(dx * dx + dy * dy);
      const outsideDistancePx = Math.max(0, (distance - 1) * edgeScale);
      let value = 0;

      if (distance <= 1) {
        value = 255;
      } else if (outsideDistancePx < TEST_CAN_MASK.featherPx) {
        const t = outsideDistancePx / TEST_CAN_MASK.featherPx;
        const smooth = t * t * (3 - 2 * t);
        value = Math.round(255 * (1 - smooth));
      }

      pixels[y * width + x] = value;
    }
  }

  return pixels;
}

async function createMaskPng(dataFolder, prefix, size) {
  const width = Math.round(size.width);
  const height = Math.round(size.height);
  const pixels = createSoftCanMaskPixels(width, height);
  const file = await dataFolder.createFile(`${prefix}-mask.png`, { overwrite: true });
  await file.write(encodePngRgba(width, height, pixels));
  return file;
}

function getUploadFileName(file, fallbackName) {
  if (file?.name && file.name !== "blob") {
    return file.name;
  }

  const nativePath = file?.nativePath || "";
  const pathName = nativePath.split(/[\\/]/).pop();
  return pathName || fallbackName;
}

async function readPngBytes(file) {
  const binary = await file.read({ format: uxp.storage.formats.binary });
  return new Uint8Array(binary);
}

function asciiBytes(text) {
  const bytes = new Uint8Array(text.length);

  for (let index = 0; index < text.length; index += 1) {
    bytes[index] = text.charCodeAt(index);
  }

  return bytes;
}

function joinBytes(parts) {
  const totalLength = parts.reduce((sum, part) => sum + part.length, 0);
  const output = new Uint8Array(totalLength);
  let offset = 0;

  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }

  return output;
}

async function createComfyUploadBody(file, uploadName) {
  const boundary = `RasterRelayBoundary${Date.now()}`;
  const imageBytes = await readPngBytes(file);
  const body = joinBytes([
    asciiBytes(`--${boundary}\r\n`),
    asciiBytes(`Content-Disposition: form-data; name="image"; filename="${uploadName}"\r\n`),
    asciiBytes("Content-Type: image/png\r\n\r\n"),
    imageBytes,
    asciiBytes(`\r\n--${boundary}\r\n`),
    asciiBytes('Content-Disposition: form-data; name="type"\r\n\r\ninput\r\n'),
    asciiBytes(`--${boundary}\r\n`),
    asciiBytes('Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'),
    asciiBytes(`--${boundary}--\r\n`)
  ]);

  return { body, boundary };
}

async function uploadImage(file, role) {
  const uploadName = getUploadFileName(file, `rasterrelay-e2e-${role}-${safeTimestamp()}.png`);
  const upload = await createComfyUploadBody(file, uploadName);

  const response = await fetch(`${COMFYUI_BASE_URL}/upload/image`, {
    method: "POST",
    headers: {
      "Content-Type": `multipart/form-data; boundary=${upload.boundary}`
    },
    body: upload.body
  });

  if (!response.ok) {
    throw new Error(`ComfyUI upload failed: HTTP ${response.status}`);
  }

  return response.json();
}

function setWorkflowInput(workflow, mappingItem, value) {
  if (Array.isArray(mappingItem)) {
    mappingItem.forEach((item) => setWorkflowInput(workflow, item, value));
    return;
  }

  const node = workflow[mappingItem.nodeId];
  if (!node?.inputs) {
    throw new Error(`Missing workflow node ${mappingItem.nodeId}.`);
  }

  node.inputs[mappingItem.inputName] = value;
}

function applyWorkflowInputs(workflow, mapping, sourceUpload, maskUpload, size) {
  setWorkflowInput(workflow, mapping.inputs.sourceImage, sourceUpload.name);
  setWorkflowInput(workflow, mapping.inputs.selectionMask, maskUpload.name);
  setWorkflowInput(workflow, mapping.inputs.prompt, TEST_PROMPT);
  setWorkflowInput(workflow, mapping.inputs.negativePrompt, "hard square edges, visible seams, distorted hands, extra fingers");
  setWorkflowInput(workflow, mapping.inputs.steps, 8);
  setWorkflowInput(workflow, mapping.inputs.cfg, 1);
  setWorkflowInput(workflow, mapping.inputs.seed, 424242);
  setWorkflowInput(workflow, mapping.inputs.seedRandomize, "disable");

  if (size?.width && size?.height) {
    setWorkflowInput(workflow, mapping.inputs.width, Math.round(size.width));
    setWorkflowInput(workflow, mapping.inputs.height, Math.round(size.height));
  }

  if (mapping.inputs?.cropLeft) {
    setWorkflowInput(workflow, mapping.inputs.cropLeft, 0);
    setWorkflowInput(workflow, mapping.inputs.cropTop, 0);
  }
  if (mapping.inputs?.docWidth) {
    setWorkflowInput(workflow, mapping.inputs.docWidth, Math.round(size.width));
    setWorkflowInput(workflow, mapping.inputs.docHeight, Math.round(size.height));
  }
}

async function queueWorkflow(workflow) {
  const response = await fetch(`${COMFYUI_BASE_URL}/prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: "rasterrelay-e2e-smoke",
      prompt: workflow
    })
  });

  const result = await response.json();
  if (!response.ok || result.error) {
    throw new Error(`ComfyUI rejected workflow: ${result.error || response.status}`);
  }

  return result.prompt_id;
}

async function waitForOutput(promptId) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < 10 * 60 * 1000) {
    const response = await fetch(`${COMFYUI_BASE_URL}/history/${encodeURIComponent(promptId)}`);
    const history = await response.json();
    const entry = history[promptId];
    const outputs = entry?.outputs || {};

    for (const output of Object.values(outputs)) {
      const image = output.images?.[0];
      if (image) {
        return image;
      }
    }

    await new Promise((resolve) => setTimeout(resolve, 2000));
  }

  throw new Error("Timed out waiting for ComfyUI output.");
}

async function downloadOutput(image, dataFolder, prefix) {
  const absolutePath = image.absolute_path || image.absolutePath || "";
  const params = absolutePath
    ? new URLSearchParams({ path: absolutePath })
    : new URLSearchParams({
        filename: image.filename,
        subfolder: image.subfolder || "",
        type: image.type || "output"
      });

  const response = await fetch(
    absolutePath
      ? `${COMFYUI_BASE_URL}/rasterrelay/view?${params.toString()}`
      : `${COMFYUI_BASE_URL}/view?${params.toString()}`
  );
  if (!response.ok) {
    throw new Error(`Could not download ComfyUI output: HTTP ${response.status}`);
  }

  const file = await dataFolder.createFile(`${prefix}-result.png`, { overwrite: true });
  await file.write(await response.arrayBuffer());
  return file;
}

function hasValidAlphaBBox(alphaBBox) {
  if (!alphaBBox || typeof alphaBBox !== "object") {
    return false;
  }

  return ["left", "top", "right", "bottom"].every((key) => Number.isFinite(Number(alphaBBox[key])));
}

function shouldUsePngAlphaOnly(image) {
  return hasValidAlphaBBox(image?.alpha_bbox || image?.alphaBBox || null);
}

async function getDocumentCompositeSnapshot(document, size) {
  if (!photoshop.imaging?.getPixels) {
    throw new Error("Photoshop imaging.getPixels is unavailable.");
  }

  const width = Math.round(size.width);
  const height = Math.round(size.height);
  const pixelResult = await photoshop.imaging.getPixels({
    documentID: document.id,
    sourceBounds: {
      left: 0,
      top: 0,
      right: width,
      bottom: height
    },
    componentSize: 8,
    colorSpace: "RGB",
    applyAlpha: true
  });

  try {
    const imageData = pixelResult.imageData;
    const data = await imageData.getData({ chunky: true });
    const bounds = pixelResult.sourceBounds || { left: 0, top: 0, right: width, bottom: height };

    return {
      width: imageData.width,
      height: imageData.height,
      components: imageData.components,
      componentSize: imageData.componentSize,
      pixelFormat: imageData.pixelFormat,
      sourceBounds: bounds,
      data: new Uint8Array(data)
    };
  } finally {
    pixelResult.imageData?.dispose?.();
  }
}

function assertFullDocumentSnapshot(snapshot, size, label) {
  const width = Math.round(size.width);
  const height = Math.round(size.height);
  if (snapshot.width !== width || snapshot.height !== height) {
    throw new Error(`${label} snapshot has ${snapshot.width}x${snapshot.height}, expected ${width}x${height}.`);
  }
  if (snapshot.components < 3 || snapshot.componentSize !== 8) {
    throw new Error(`${label} snapshot has unsupported format components=${snapshot.components}, componentSize=${snapshot.componentSize}.`);
  }
  const bounds = snapshot.sourceBounds || {};
  if (Math.round(bounds.left || 0) !== 0 || Math.round(bounds.top || 0) !== 0) {
    throw new Error(`${label} snapshot source bounds start at ${JSON.stringify(bounds)}, expected document origin.`);
  }
}

function channelDifferenceTriplet(data, offset) {
  const red = data[offset];
  const green = data[offset + 1];
  const blue = data[offset + 2];
  return [red - green, red - blue, green - blue];
}

function maxSourceChromaError(beforeData, beforeOffset, afterData, afterOffset) {
  if (panelHelpers.maxSourceChromaError) {
    return panelHelpers.maxSourceChromaError(beforeData, beforeOffset, afterData, afterOffset);
  }

  const beforeDiffs = channelDifferenceTriplet(beforeData, beforeOffset);
  const afterDiffs = channelDifferenceTriplet(afterData, afterOffset);
  let maxError = 0;

  for (let index = 0; index < beforeDiffs.length; index += 1) {
    maxError = Math.max(maxError, Math.abs(beforeDiffs[index] - afterDiffs[index]));
  }

  return maxError;
}

function sourceHueError(beforeData, beforeOffset, afterData, afterOffset) {
  if (panelHelpers.sourceHueError) {
    return panelHelpers.sourceHueError(beforeData, beforeOffset, afterData, afterOffset);
  }

  return null;
}

function sourceSaturationError(beforeData, beforeOffset, afterData, afterOffset) {
  if (panelHelpers.sourceSaturationError) {
    return panelHelpers.sourceSaturationError(beforeData, beforeOffset, afterData, afterOffset);
  }

  return null;
}

function auditCompositeColorLock(beforeSnapshot, afterSnapshot, outputImage, size) {
  const alphaBBox = outputImage?.alpha_bbox || outputImage?.alphaBBox || null;
  if (!hasValidAlphaBBox(alphaBBox)) {
    throw new Error("Output image did not include alpha_bbox metadata; Photoshop color-lock audit cannot run.");
  }

  assertFullDocumentSnapshot(beforeSnapshot, size, "before");
  assertFullDocumentSnapshot(afterSnapshot, size, "after");

  const width = Math.round(size.width);
  const height = Math.round(size.height);
  const beforeStep = beforeSnapshot.components;
  const afterStep = afterSnapshot.components;
  let outsideChangedPixels = 0;
  let maxDiffOutsideAlphaBBox = 0;
  let insideChangedPixels = 0;
  let sourceChromaMaxErrorInsideChanged = 0;
  let sourceChromaErrorSumInsideChanged = 0;
  let sourceChromaCheckedPixels = 0;
  let sourceHueMaxErrorInsideChanged = 0;
  let sourceHueErrorSumInsideChanged = 0;
  let sourceHueCheckedPixels = 0;
  let sourceSaturationMaxErrorInsideChanged = 0;
  let sourceSaturationErrorSumInsideChanged = 0;
  let sourceSaturationCheckedPixels = 0;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const beforeOffset = (y * width + x) * beforeStep;
      const afterOffset = (y * width + x) * afterStep;
      let diff = 0;

      for (let channel = 0; channel < 3; channel += 1) {
        diff = Math.max(diff, Math.abs(beforeSnapshot.data[beforeOffset + channel] - afterSnapshot.data[afterOffset + channel]));
      }

      const insideAlphaBBox =
        x >= alphaBBox.left &&
        x < alphaBBox.right &&
        y >= alphaBBox.top &&
        y < alphaBBox.bottom;

      if (insideAlphaBBox) {
        if (diff > 0) {
          insideChangedPixels += 1;
          const chromaError = maxSourceChromaError(
            beforeSnapshot.data,
            beforeOffset,
            afterSnapshot.data,
            afterOffset
          );
          sourceChromaMaxErrorInsideChanged = Math.max(sourceChromaMaxErrorInsideChanged, chromaError);
          sourceChromaErrorSumInsideChanged += chromaError;
          sourceChromaCheckedPixels += 1;
          const hueError = sourceHueError(
            beforeSnapshot.data,
            beforeOffset,
            afterSnapshot.data,
            afterOffset
          );
          if (hueError !== null) {
            sourceHueMaxErrorInsideChanged = Math.max(sourceHueMaxErrorInsideChanged, hueError);
            sourceHueErrorSumInsideChanged += hueError;
            sourceHueCheckedPixels += 1;
          }
          const saturationError = sourceSaturationError(
            beforeSnapshot.data,
            beforeOffset,
            afterSnapshot.data,
            afterOffset
          );
          if (saturationError !== null) {
            sourceSaturationMaxErrorInsideChanged = Math.max(sourceSaturationMaxErrorInsideChanged, saturationError);
            sourceSaturationErrorSumInsideChanged += saturationError;
            sourceSaturationCheckedPixels += 1;
          }
        }
      } else if (diff > 0) {
        outsideChangedPixels += 1;
        maxDiffOutsideAlphaBBox = Math.max(maxDiffOutsideAlphaBBox, diff);
      }
    }
  }

  return {
    checked: true,
    alphaBBox,
    outsideChangedPixels,
    maxDiffOutsideAlphaBBox,
    insideChangedPixels,
    sourceChromaCheckedPixels,
    sourceChromaMaxErrorInsideChanged,
    sourceChromaMeanErrorInsideChanged: sourceChromaCheckedPixels
      ? sourceChromaErrorSumInsideChanged / sourceChromaCheckedPixels
      : 0,
    sourceHueCheckedPixels,
    sourceHueMaxErrorInsideChanged,
    sourceHueMeanErrorInsideChanged: sourceHueCheckedPixels
      ? sourceHueErrorSumInsideChanged / sourceHueCheckedPixels
      : 0,
    sourceSaturationCheckedPixels,
    sourceSaturationMaxErrorInsideChanged,
    sourceSaturationMeanErrorInsideChanged: sourceSaturationCheckedPixels
      ? sourceSaturationErrorSumInsideChanged / sourceSaturationCheckedPixels
      : 0,
    passed:
      outsideChangedPixels === 0 &&
      maxDiffOutsideAlphaBBox === 0 &&
      sourceChromaMaxErrorInsideChanged <= 1 &&
      (sourceHueCheckedPixels === 0 || sourceHueMaxErrorInsideChanged <= 1.5)
  };
}

async function applySoftCanMaskToActiveLayer(size) {
  const layer = photoshop.app.activeDocument?.activeLayers?.[0];
  if (!layer?.id) {
    throw new Error("Could not find the placed RasterRelay result layer.");
  }

  const width = Math.round(size.width);
  const height = Math.round(size.height);
  const maskPixels = createSoftCanMaskGrayscale(width, height);
  const imageData = await photoshop.imaging.createImageDataFromBuffer(maskPixels, {
    width,
    height,
    components: 1,
    chunky: false,
    colorProfile: "Gray Gamma 2.2",
    colorSpace: "Grayscale"
  });

  try {
    await photoshop.imaging.putLayerMask({
      documentID: photoshop.app.activeDocument.id,
      layerID: layer.id,
      kind: "user",
      imageData,
      replace: true,
      targetBounds: {
        left: 0,
        top: 0
      },
      commandName: "RasterRelay E2E Apply Soft Mask"
    });

    layer.name = "RasterRelay - wynik E2E";

    return {
      applied: true,
      layerId: layer.id,
      featherPx: TEST_CAN_MASK.featherPx
    };
  } finally {
    imageData.dispose();
  }
}

async function clearActiveSelection() {
  await photoshop.action.batchPlay(
    [
      {
        _obj: "set",
        _target: [{ _ref: "channel", _property: "selection" }],
        to: {
          _enum: "ordinal",
          _value: "none"
        }
      }
    ],
    {}
  );
}

async function placeResultAsLayer(file, size, outputImage) {
  const token = await uxp.storage.localFileSystem.createSessionToken(file);
  let layerMask;
  const usePngAlphaOnly = shouldUsePngAlphaOnly(outputImage);

  await photoshop.core.executeAsModal(
    async () => {
      await clearActiveSelection();
      await photoshop.action.batchPlay(
        [
          {
            _obj: "placeEvent",
            null: { _path: token, _kind: "local" },
            freeTransformCenterState: {
              _enum: "quadCenterState",
              _value: "QCSAverage"
            },
            offset: {
              _obj: "offset",
              horizontal: { _unit: "pixelsUnit", _value: 0 },
              vertical: { _unit: "pixelsUnit", _value: 0 }
            }
          }
        ],
        {}
      );
      layerMask = usePngAlphaOnly
        ? {
            applied: false,
            skipped: true,
            source: "png-change-alpha",
            reason: "ComfyUI result carries exact change alpha; Photoshop layer mask was intentionally skipped."
          }
        : await applySoftCanMaskToActiveLayer(size);
    },
    { commandName: "RasterRelay E2E Place Result" }
  );

  return {
    placed: true,
    layerMask
  };
}

async function runRasterRelayE2ESmokeTest() {
  const dataFolder = await uxp.storage.localFileSystem.getDataFolder();
  const prefix = `rasterrelay-e2e-${safeTimestamp()}`;
  const document = await createTestDocument();
  const size = {
    width: getUnitValue(document.width),
    height: getUnitValue(document.height)
  };
  const beforePlacementComposite = await getDocumentCompositeSnapshot(document, size);

  const sourceFile = await exportDocumentPng(document, dataFolder, prefix);
  const maskFile = await createMaskPng(dataFolder, prefix, size);
  const sourceUpload = await uploadImage(sourceFile, "source");
  const maskUpload = await uploadImage(maskFile, "mask");
  const { workflow, mapping } = await loadWorkflowBundle();
  applyWorkflowInputs(workflow, mapping, sourceUpload, maskUpload, size);
  const promptId = await queueWorkflow(workflow);
  const outputImage = await waitForOutput(promptId);
  const resultFile = await downloadOutput(outputImage, dataFolder, prefix);
  const placement = await placeResultAsLayer(resultFile, size, outputImage);
  const afterPlacementComposite = await getDocumentCompositeSnapshot(document, size);
  const compositeAudit = auditCompositeColorLock(beforePlacementComposite, afterPlacementComposite, outputImage, size);

  if (!compositeAudit.passed) {
    throw new Error(
      `RasterRelay E2E color-lock audit failed: outsideChanged=${compositeAudit.outsideChangedPixels}, outsideMaxDiff=${compositeAudit.maxDiffOutsideAlphaBBox}, sourceChromaMaxError=${compositeAudit.sourceChromaMaxErrorInsideChanged}, sourceHueMaxError=${compositeAudit.sourceHueMaxErrorInsideChanged}, sourceHueChecked=${compositeAudit.sourceHueCheckedPixels}, sourceSaturationMaxError=${compositeAudit.sourceSaturationMaxErrorInsideChanged}, sourceSaturationChecked=${compositeAudit.sourceSaturationCheckedPixels}`
    );
  }

  const summary = {
    ok: true,
    promptId,
    document: {
      title: document.title,
      width: size.width,
      height: size.height
    },
    source: sourceFile.nativePath || sourceFile.name,
    mask: maskFile.nativePath || maskFile.name,
    result: resultFile.nativePath || resultFile.name,
    placement,
    compositeAudit,
    target: TEST_CAN_MASK
  };
  const reportFile = await dataFolder.createFile(`${prefix}-summary.json`, { overwrite: true });
  summary.report = reportFile.nativePath || reportFile.name;
  await reportFile.write(JSON.stringify(summary, null, 2));

  console.log(JSON.stringify(summary));
  return summary;
}

globalThis.RasterRelayE2ESmokeTest = {
  run: runRasterRelayE2ESmokeTest
};
})();
