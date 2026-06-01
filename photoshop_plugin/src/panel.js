(() => {
const COMFYUI_BASE_URL = "http://127.0.0.1:8188";
const COMFYUI_SYSTEM_STATS_URL = `${COMFYUI_BASE_URL}/system_stats`;
const JOB_FILE_NAME = "rasterrelay-inpainting-job.json";
const WORKFLOW_FILE_NAME = "workflows/inpainting-api.json";
const WORKFLOW_MAPPING_FILE_NAME = "workflows/inpainting-api.mapping.json";
const E2E_AUTOSTART_FILE_NAME = "e2e-autostart.flag";
const COMFY_HISTORY_TIMEOUT_MS = 10 * 60 * 1000;
const COMFY_HISTORY_POLL_MS = 2000;
const DEFAULT_MASK_FEATHER_RATIO = 0.015;
const DEFAULT_MASK_FEATHER_MIN_PX = 8;
const DEFAULT_MASK_FEATHER_MAX_PX = 32;
const SELECTION_PADDING_PX = 96;
const qualityPresets = {
  fast: {
    label: "Szybki test",
    steps: 8,
    cfg: 4.2
  },
  balanced: {
    label: "Dobra jakość",
    steps: 20,
    cfg: 5
  },
  quality: {
    label: "Dokładna edycja",
    steps: 32,
    cfg: 5.5
  }
};

let ui = null;
let autostartE2EConsumed = false;

const panelMarkup = `
  <main class="rr-panel-shell">
    <header class="rr-panel-header">
      <div class="rr-panel-title">RasterRelay</div>
      <div class="rr-panel-subtitle">Inpainting Brush Tool</div>
      <p id="heartbeatText">RasterRelay gotowy. Otwórz obraz, zrób zaznaczenie i wpisz prompt.</p>
    </header>

    <section class="status-card" aria-label="Status polaczenia">
      <div>
        <span class="status-dot" id="comfyDot"></span>
        <strong id="comfyStatus">ComfyUI: niesprawdzone</strong>
      </div>
      <button id="checkComfyButton">Sprawdz ComfyUI</button>
    </section>

    <section class="form-section" aria-label="Ustawienia inpaintingu">
      <label for="promptInput">Prompt</label>
      <textarea id="promptInput" rows="5" placeholder="Napisz, co ma sie pojawic w zaznaczonym miejscu."></textarea>

      <p class="hint">Reszta ustawien bedzie w Launcherze, zeby panel Photoshopa zostal lekki.</p>
    </section>

    <section class="action-section" aria-label="Funkcja RasterRelay">
      <button class="primary" id="prepareButton">Przygotuj edycje</button>
      <button class="dev-only" id="e2eSmokeButton">Test E2E</button>
      <button id="documentButton">Sprawdz dokument</button>
    </section>

    <section class="log-card" aria-live="polite">
      <p id="messageText">Otworz dokument w Photoshopie, uruchom ComfyUI w Launcherze i sprawdz polaczenie.</p>
    </section>

    <section class="rr-hidden-settings" aria-hidden="true">
      <select id="qualitySelect">
        <option value="balanced" selected>Dobra jakosc</option>
        <option value="fast">Szybki test</option>
        <option value="quality">Dokladna edycja</option>
      </select>
      <textarea id="loraNamesInput"></textarea>
      <input id="loraStrengthModelInput" type="number" value="1" />
      <input id="loraStrengthClipInput" type="number" value="1" />
      <button id="readinessButton" type="button"></button>
      <button id="packageButton" type="button"></button>
      <p id="loraCatalogText"></p>
      <div id="loraList"></div>
    </section>
  </main>
`;

function findPanelElement(rootNode, id) {
  return rootNode.querySelector(`#${id}`);
}

function mountPanelMarkup(rootNode) {
  if (rootNode.querySelector(".rr-panel-shell")) {
    return;
  }

  rootNode.innerHTML = "";
  rootNode.innerHTML = panelMarkup;
}

function collectUi(rootNode) {
  return {
    checkComfyButton: findPanelElement(rootNode, "checkComfyButton"),
    comfyDot: findPanelElement(rootNode, "comfyDot"),
    comfyStatus: findPanelElement(rootNode, "comfyStatus"),
    documentButton: findPanelElement(rootNode, "documentButton"),
    e2eSmokeButton: findPanelElement(rootNode, "e2eSmokeButton"),
    heartbeatText: findPanelElement(rootNode, "heartbeatText"),
    loraCatalogText: findPanelElement(rootNode, "loraCatalogText"),
    loraList: findPanelElement(rootNode, "loraList"),
    loraNamesInput: findPanelElement(rootNode, "loraNamesInput"),
    loraStrengthClipInput: findPanelElement(rootNode, "loraStrengthClipInput"),
    loraStrengthModelInput: findPanelElement(rootNode, "loraStrengthModelInput"),
    messageText: findPanelElement(rootNode, "messageText"),
    packageButton: findPanelElement(rootNode, "packageButton"),
    prepareButton: findPanelElement(rootNode, "prepareButton"),
    promptInput: findPanelElement(rootNode, "promptInput"),
    qualitySelect: findPanelElement(rootNode, "qualitySelect"),
    readinessButton: findPanelElement(rootNode, "readinessButton")
  };
}

function showRasterRelayPanel() {
  const uxp = getUxpApi();
  const plugins = Array.from(uxp?.pluginManager?.plugins || []);
  const rasterRelay = plugins.find((plugin) => plugin.id === "com.rasterrelay.photoshop");
  rasterRelay?.showPanel?.("rasterrelayPanel");
}

function getRequiredModule(moduleName) {
  if (typeof require !== "function") {
    return null;
  }

  try {
    return require(moduleName);
  } catch {
    return null;
  }
}

function getPhotoshopApi() {
  return getRequiredModule("photoshop");
}

function getUxpApi() {
  return getRequiredModule("uxp");
}

function setMessage(message) {
  if (ui?.messageText) {
    ui.messageText.textContent = message;
  }

  console.log(`[RasterRelay] ${message}`);
}

function setComfyStatus(isReady, message) {
  if (!ui?.comfyDot || !ui?.comfyStatus) {
    return;
  }

  ui.comfyDot.classList.toggle("ready", isReady);
  ui.comfyStatus.textContent = message;
}

async function checkComfyUi() {
  ui.checkComfyButton.disabled = true;
  setComfyStatus(false, "ComfyUI: sprawdzam...");

  try {
    const response = await fetch(COMFYUI_SYSTEM_STATS_URL);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    setComfyStatus(true, "ComfyUI: aktywne");
    setMessage("ComfyUI odpowiada. Możesz przygotować edycję z panelu RasterRelay.");
    void refreshLoraCatalog();
    return true;
  } catch {
    setComfyStatus(false, "ComfyUI: brak połączenia");
    setMessage("Nie widzę ComfyUI pod 127.0.0.1:8188. Uruchom je w Launcherze i spróbuj ponownie.");
    return false;
  } finally {
    ui.checkComfyButton.disabled = false;
  }
}

function getActiveDocument() {
  const photoshop = getPhotoshopApi();

  if (!photoshop) {
    return null;
  }

  return photoshop.app.activeDocument || null;
}

function getActiveDocumentSummary() {
  const photoshop = getPhotoshopApi();

  if (!photoshop) {
    return {
      ok: false,
      message: "Ten panel działa teraz w podglądzie. Prawdziwy dokument sprawdzimy po uruchomieniu w Photoshopie."
    };
  }

  const document = photoshop.app.activeDocument;

  if (!document) {
    return {
      ok: false,
      message: "Nie ma aktywnego dokumentu. Otwórz obraz w Photoshopie."
    };
  }

  const selection = getSelectionInfo(document);
  const selectionText = selection.hasSelection
    ? `Zaznaczenie: ${selection.bounds.width} x ${selection.bounds.height}.`
    : "Brakuje zaznaczenia.";

  return {
    ok: true,
    message: `Aktywny dokument: ${document.title || "bez nazwy"}. ${selectionText}`
  };
}

function readUnitValue(value) {
  if (typeof value === "number") {
    return value;
  }

  if (value && typeof value.value === "number") {
    return value.value;
  }

  return null;
}

function readDocumentSize(document) {
  return {
    width: readUnitValue(document.width),
    height: readUnitValue(document.height)
  };
}

function normalizeSelectionBounds(bounds) {
  if (!bounds) {
    return null;
  }

  const left = readUnitValue(bounds.left);
  const top = readUnitValue(bounds.top);
  const right = readUnitValue(bounds.right);
  const bottom = readUnitValue(bounds.bottom);

  if ([left, top, right, bottom].some((value) => value === null)) {
    return null;
  }

  return {
    left,
    top,
    right,
    bottom,
    width: Math.max(0, right - left),
    height: Math.max(0, bottom - top)
  };
}

function getSelectionInfo(document) {
  const bounds = normalizeSelectionBounds(document.selection?.bounds);

  return {
    hasSelection: Boolean(bounds && bounds.width > 0 && bounds.height > 0),
    bounds,
    solid: Boolean(document.selection?.solid)
  };
}

function calculatePaddedBounds(selectionBounds, docWidth, docHeight, padding) {
  const left = Math.max(0, Math.round(selectionBounds.left) - padding);
  const top = Math.max(0, Math.round(selectionBounds.top) - padding);
  const right = Math.min(docWidth, Math.round(selectionBounds.right) + padding);
  const bottom = Math.min(docHeight, Math.round(selectionBounds.bottom) + padding);

  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top
  };
}

async function checkDocument() {
  const summary = getActiveDocumentSummary();
  setMessage(summary.message);
  return summary.ok;
}

function getPrompt() {
  return ui.promptInput.value.trim();
}

function getQualityPreset() {
  return qualityPresets[ui.qualitySelect.value] || qualityPresets.balanced;
}

function readStrengthInput(element, fallback) {
  const value = Number(element?.value);
  if (!Number.isFinite(value)) {
    return fallback;
  }

  return Math.min(2, Math.max(0, value));
}

function getDefaultLoraStrengths() {
  return {
    model: readStrengthInput(ui.loraStrengthModelInput, 1),
    clip: readStrengthInput(ui.loraStrengthClipInput, 1)
  };
}

function parseLoraToken(token, defaultStrengths) {
  const trimmed = token.trim();
  if (!trimmed) {
    return null;
  }

  const parts = trimmed.split(":").map((part) => part.trim()).filter(Boolean);
  const name = parts[0];
  if (!name) {
    return null;
  }

  if (parts.length === 1) {
    return {
      name,
      strengthModel: defaultStrengths.model,
      strengthClip: defaultStrengths.clip
    };
  }

  const strengthModel = Number(parts[1]);
  const strengthClip = Number(parts[2]);

  return {
    name,
    strengthModel: Number.isFinite(strengthModel)
      ? Math.min(2, Math.max(0, strengthModel))
      : defaultStrengths.model,
    strengthClip: Number.isFinite(strengthClip)
      ? Math.min(2, Math.max(0, strengthClip))
      : Number.isFinite(strengthModel)
        ? Math.min(2, Math.max(0, strengthModel))
        : defaultStrengths.clip
  };
}

function getLoraItems() {
  const defaultStrengths = getDefaultLoraStrengths();
  const rawNames = ui.loraNamesInput.value || "";

  return rawNames
    .split(/[\n,]+/)
    .map((token) => parseLoraToken(token, defaultStrengths))
    .filter((item) => item?.name);
}

function createSafeTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function validateJobInputs(prompt, document) {
  if (!prompt) {
    return "Najpierw wpisz prompt, czyli prosty opis tego, co ma powstać w zaznaczeniu.";
  }

  if (!document) {
    return "Nie ma aktywnego dokumentu. Otwórz obraz w Photoshopie.";
  }

  const selection = getSelectionInfo(document);
  if (!selection.hasSelection) {
    return "Zaznacz obszar w Photoshopie. Inpainting potrzebuje maski albo zaznaczenia.";
  }

  return null;
}

function buildInpaintingJob(document, prompt, assets) {
  const size = readDocumentSize(document);
  const selection = getSelectionInfo(document);
  const loraItems = getLoraItems();
  const quality = getQualityPreset();

  return {
    schemaVersion: "rasterrelay.inpaintingJob.v1",
    createdAt: new Date().toISOString(),
    source: {
      host: "Photoshop UXP",
      pluginId: "com.rasterrelay.photoshop"
    },
    document: {
      id: document.id ?? null,
      title: document.title || "bez nazwy",
      width: size.width,
      height: size.height
    },
    selection: {
      required: true,
      hasSelection: selection.hasSelection,
      bounds: selection.bounds,
      solid: selection.solid
    },
    cropBounds: assets.cropBounds || null,
    assets,
    generation: {
      tool: "inpainting-brush",
      prompt,
      baseModelKind: "gguf",
      quality,
      lora: {
        enabled: loraItems.length > 0,
        items: loraItems
      }
    },
    outputs: {
      target: "newPhotoshopLayerWithMask"
    }
  };
}

async function getDataFolder() {
  const uxp = getUxpApi();

  if (!uxp) {
    throw new Error("UXP storage is unavailable.");
  }

  return uxp.storage.localFileSystem.getDataFolder();
}

async function getPluginTextFile(relativePath) {
  const uxp = getUxpApi();

  if (!uxp) {
    throw new Error("UXP storage is unavailable.");
  }

  const pluginFolder = await uxp.storage.localFileSystem.getPluginFolder();
  const parts = relativePath.split("/");
  let entry = pluginFolder;

  for (const part of parts) {
    entry = await entry.getEntry(part);
  }

  return entry.read({
    format: uxp.storage.formats.utf8
  });
}

async function getOptionalPluginTextFile(relativePath) {
  try {
    return await getPluginTextFile(relativePath);
  } catch {
    return null;
  }
}

async function exportDocumentPng(document, dataFolder, filePrefix) {
  const photoshop = getPhotoshopApi();
  if (!photoshop) {
    throw new Error("Photoshop API is unavailable.");
  }

  const file = await dataFolder.createFile(`${filePrefix}-source.png`, {
    overwrite: true
  });

  await photoshop.core.executeAsModal(
    async () => {
      await document.saveAs.png(file, { compression: 6 }, true);
    },
    { commandName: "RasterRelay Export Source PNG" }
  );

  return {
    asset: {
      kind: "sourceImage",
      format: "png",
      path: file.nativePath || file.name
    },
    file
  };
}

async function exportCroppedSourcePng(document, dataFolder, filePrefix, paddedBounds) {
  const photoshop = getPhotoshopApi();
  if (!photoshop?.imaging) {
    return exportDocumentPng(document, dataFolder, filePrefix);
  }

  const docSize = readDocumentSize(document);
  const image = await photoshop.imaging.getImage({
    documentID: document.id,
    sourceBounds: {
      left: paddedBounds.left,
      top: paddedBounds.top,
      right: paddedBounds.right,
      bottom: paddedBounds.bottom
    }
  });

  try {
    const pixelData = await image.imageData.getData();
    const width = paddedBounds.width;
    const height = paddedBounds.height;

    const rgbaPixels = new Uint8Array(width * height * 4);
    const components = Math.max(1, Math.round(pixelData.length / (width * height)));

    for (let i = 0; i < width * height; i++) {
      const srcIdx = i * components;
      const dstIdx = i * 4;

      if (components >= 3) {
        rgbaPixels[dstIdx] = pixelData[srcIdx];
        rgbaPixels[dstIdx + 1] = pixelData[srcIdx + 1];
        rgbaPixels[dstIdx + 2] = pixelData[srcIdx + 2];
        rgbaPixels[dstIdx + 3] = components >= 4 ? pixelData[srcIdx + 3] : 255;
      } else {
        const val = pixelData[srcIdx];
        rgbaPixels[dstIdx] = val;
        rgbaPixels[dstIdx + 1] = val;
        rgbaPixels[dstIdx + 2] = val;
        rgbaPixels[dstIdx + 3] = 255;
      }
    }

    const file = await dataFolder.createFile(`${filePrefix}-source.png`, {
      overwrite: true
    });
    const pngBuffer = encodePngRgba(width, height, rgbaPixels);
    await file.write(pngBuffer);

    return {
      asset: {
        kind: "sourceImage",
        format: "png",
        path: file.nativePath || file.name,
        cropBounds: paddedBounds
      },
      file
    };
  } finally {
    image.imageData?.dispose?.();
  }
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
  header[10] = 0;
  header[11] = 0;
  header[12] = 0;

  const signature = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]);
  const chunks = [
    createPngChunk("IHDR", header),
    createPngChunk("IDAT", createZlibStoredData(rawData)),
    createPngChunk("IEND", new Uint8Array())
  ];
  const totalLength = signature.length + chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const png = new Uint8Array(totalLength);
  let offset = 0;

  png.set(signature, offset);
  offset += signature.length;

  for (const chunk of chunks) {
    png.set(chunk, offset);
    offset += chunk.length;
  }

  return png.buffer;
}

function createBoundsMaskPixels(photoshopDocument, selection) {
  const size = readDocumentSize(photoshopDocument);
  const width = Math.max(1, Math.round(size.width || selection.bounds.right));
  const height = Math.max(1, Math.round(size.height || selection.bounds.bottom));
  const pixels = new Uint8Array(width * height * 4);
  const left = Math.max(0, Math.round(selection.bounds.left));
  const top = Math.max(0, Math.round(selection.bounds.top));
  const right = Math.min(width, Math.round(selection.bounds.right));
  const bottom = Math.min(height, Math.round(selection.bounds.bottom));

  for (let index = 0; index < width * height; index += 1) {
    pixels[index * 4 + 3] = 255;
  }

  for (let y = top; y < bottom; y += 1) {
    for (let x = left; x < right; x += 1) {
      const offset = (y * width + x) * 4;
      pixels[offset] = 255;
      pixels[offset + 1] = 255;
      pixels[offset + 2] = 255;
      pixels[offset + 3] = 255;
    }
  }

  return { width, height, pixels };
}

function getImageDataSize(selectionImage) {
  return {
    width:
      selectionImage.imageData?.width ||
      Math.round(selectionImage.sourceBounds.right - selectionImage.sourceBounds.left),
    height:
      selectionImage.imageData?.height ||
      Math.round(selectionImage.sourceBounds.bottom - selectionImage.sourceBounds.top)
  };
}

function readMaskPixelValue(data, pixelIndex, components) {
  const index = pixelIndex * components;

  if (components === 1) {
    return data[index];
  }

  if (components === 2) {
    return data[index];
  }

  if (components === 4 && data[index + 3] !== undefined) {
    return data[index + 3];
  }

  const red = data[index] ?? 0;
  const green = data[index + 1] ?? red;
  const blue = data[index + 2] ?? red;
  return Math.round((red + green + blue) / 3);
}

function putSelectionPixelsOnMask(mask, selectionImage, pixelData) {
  const size = getImageDataSize(selectionImage);
  const components = Math.max(1, Math.round(pixelData.length / (size.width * size.height)));
  const left = Math.round(selectionImage.sourceBounds.left);
  const top = Math.round(selectionImage.sourceBounds.top);

  for (let y = 0; y < size.height; y += 1) {
    for (let x = 0; x < size.width; x += 1) {
      const sourcePixelIndex = y * size.width + x;
      const targetX = left + x;
      const targetY = top + y;

      if (targetX < 0 || targetY < 0 || targetX >= mask.width || targetY >= mask.height) {
        continue;
      }

      const maskValue = readMaskPixelValue(pixelData, sourcePixelIndex, components);
      const targetOffset = (targetY * mask.width + targetX) * 4;
      mask.pixels[targetOffset] = maskValue;
      mask.pixels[targetOffset + 1] = maskValue;
      mask.pixels[targetOffset + 2] = maskValue;
      mask.pixels[targetOffset + 3] = 255;
    }
  }
}

function getDefaultMaskFeatherRadius(width, height) {
  const imageScale = Math.min(width, height);
  return Math.min(
    DEFAULT_MASK_FEATHER_MAX_PX,
    Math.max(DEFAULT_MASK_FEATHER_MIN_PX, Math.round(imageScale * DEFAULT_MASK_FEATHER_RATIO))
  );
}

function getMaskChannel(mask) {
  const values = new Uint8Array(mask.width * mask.height);

  for (let index = 0; index < values.length; index += 1) {
    values[index] = mask.pixels[index * 4];
  }

  return values;
}

function writeMaskChannel(mask, values) {
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    const offset = index * 4;
    mask.pixels[offset] = value;
    mask.pixels[offset + 1] = value;
    mask.pixels[offset + 2] = value;
    mask.pixels[offset + 3] = 255;
  }
}

function blurMaskHorizontal(values, width, height, radius) {
  const blurred = new Uint8Array(values.length);
  const windowSize = radius * 2 + 1;

  for (let y = 0; y < height; y += 1) {
    const rowOffset = y * width;
    let sum = 0;

    for (let x = -radius; x <= radius; x += 1) {
      const sampleX = Math.min(width - 1, Math.max(0, x));
      sum += values[rowOffset + sampleX];
    }

    for (let x = 0; x < width; x += 1) {
      blurred[rowOffset + x] = Math.round(sum / windowSize);

      const outgoingX = Math.min(width - 1, Math.max(0, x - radius));
      const incomingX = Math.min(width - 1, Math.max(0, x + radius + 1));
      sum += values[rowOffset + incomingX] - values[rowOffset + outgoingX];
    }
  }

  return blurred;
}

function blurMaskVertical(values, width, height, radius) {
  const blurred = new Uint8Array(values.length);
  const windowSize = radius * 2 + 1;

  for (let x = 0; x < width; x += 1) {
    let sum = 0;

    for (let y = -radius; y <= radius; y += 1) {
      const sampleY = Math.min(height - 1, Math.max(0, y));
      sum += values[sampleY * width + x];
    }

    for (let y = 0; y < height; y += 1) {
      blurred[y * width + x] = Math.round(sum / windowSize);

      const outgoingY = Math.min(height - 1, Math.max(0, y - radius));
      const incomingY = Math.min(height - 1, Math.max(0, y + radius + 1));
      sum += values[incomingY * width + x] - values[outgoingY * width + x];
    }
  }

  return blurred;
}

function softenMaskPixels(mask, radius = getDefaultMaskFeatherRadius(mask.width, mask.height)) {
  if (radius <= 0) {
    return 0;
  }

  const original = getMaskChannel(mask);
  const horizontal = blurMaskHorizontal(original, mask.width, mask.height, radius);
  const vertical = blurMaskVertical(horizontal, mask.width, mask.height, radius);
  writeMaskChannel(mask, vertical);
  return radius;
}

function createSoftMaskChannelFromSelection(selectionImage, pixelData, radius) {
  const size = getImageDataSize(selectionImage);
  const components = Math.max(1, Math.round(pixelData.length / (size.width * size.height)));
  const maskValues = new Uint8Array(size.width * size.height);

  for (let index = 0; index < maskValues.length; index += 1) {
    maskValues[index] = readMaskPixelValue(pixelData, index, components);
  }

  if (radius <= 0) {
    return maskValues;
  }

  const horizontal = blurMaskHorizontal(maskValues, size.width, size.height, radius);
  return blurMaskVertical(horizontal, size.width, size.height, radius);
}

async function exportExactSelectionMaskPng(photoshopDocument, dataFolder, filePrefix, paddedBounds) {
  const photoshop = getPhotoshopApi();
  if (!photoshop?.imaging) {
    throw new Error("Photoshop Imaging API is unavailable.");
  }

  const selection = getSelectionInfo(photoshopDocument);
  const selectionImage = await photoshop.imaging.getSelection({
    documentID: photoshopDocument.id,
    sourceBounds: selection.bounds
  });

  try {
    const pixelData = await selectionImage.imageData.getData();
    const width = paddedBounds.width;
    const height = paddedBounds.height;
    const pixels = new Uint8Array(width * height * 4);

    const selBounds = selectionImage.sourceBounds || selection.bounds;
    const selLeft = Math.round(selBounds.left);
    const selTop = Math.round(selBounds.top);
    const selWidth = Math.round(selBounds.right - selBounds.left);
    const selHeight = Math.round(selBounds.bottom - selBounds.top);
    const components = Math.max(1, Math.round(pixelData.length / (selWidth * selHeight)));

    for (let y = 0; y < selHeight; y++) {
      for (let x = 0; x < selWidth; x++) {
        const srcIdx = (y * selWidth + x) * components;
        const docX = selLeft + x;
        const docY = selTop + y;
        const cropX = docX - paddedBounds.left;
        const cropY = docY - paddedBounds.top;

        if (cropX < 0 || cropY < 0 || cropX >= width || cropY >= height) {
          continue;
        }

        let maskValue;
        if (components === 1) {
          maskValue = pixelData[srcIdx];
        } else if (components === 4) {
          maskValue = pixelData[srcIdx + 3];
        } else {
          maskValue = pixelData[srcIdx];
        }

        const dstIdx = (cropY * width + cropX) * 4;
        pixels[dstIdx] = maskValue;
        pixels[dstIdx + 1] = maskValue;
        pixels[dstIdx + 2] = maskValue;
        pixels[dstIdx + 3] = 255;
      }
    }

    const featherRadius = softenMaskPixels({ width, height, pixels });

    const file = await dataFolder.createFile(`${filePrefix}-mask-selection.png`, {
      overwrite: true
    });
    const pngBuffer = encodePngRgba(width, height, pixels);
    await file.write(pngBuffer);

    return {
      asset: {
        kind: "selectionMask",
        format: "png",
        path: file.nativePath || file.name,
        mode: "photoshop-selection-pixels",
        cropBounds: paddedBounds,
        featherRadius,
        note:
          "Maska została utworzona z pikselowej reprezentacji zaznaczenia Photoshopa i ma miękką krawędź."
      },
      file
    };
  } finally {
    selectionImage.imageData?.dispose?.();
  }
}

async function exportBoundsMaskPng(photoshopDocument, dataFolder, filePrefix, paddedBounds) {
  const selection = getSelectionInfo(photoshopDocument);
  const file = await dataFolder.createFile(`${filePrefix}-mask-bounds.png`, {
    overwrite: true
  });

  const width = paddedBounds.width;
  const height = paddedBounds.height;
  const pixels = new Uint8Array(width * height * 4);

  const selBounds = selection.bounds;
  const selLeft = Math.max(0, Math.round(selBounds.left) - paddedBounds.left);
  const selTop = Math.max(0, Math.round(selBounds.top) - paddedBounds.top);
  const selRight = Math.min(width, Math.round(selBounds.right) - paddedBounds.left);
  const selBottom = Math.min(height, Math.round(selBounds.bottom) - paddedBounds.top);

  for (let y = selTop; y < selBottom; y++) {
    for (let x = selLeft; x < selRight; x++) {
      const idx = (y * width + x) * 4;
      pixels[idx] = 255;
      pixels[idx + 1] = 255;
      pixels[idx + 2] = 255;
      pixels[idx + 3] = 255;
    }
  }

  const featherRadius = softenMaskPixels({ width, height, pixels });
  const pngBuffer = encodePngRgba(width, height, pixels);

  await file.write(pngBuffer);

  return {
    asset: {
      kind: "selectionMask",
      format: "png",
      path: file.nativePath || file.name,
      mode: selection.solid ? "solid-selection-bounds" : "selection-bounds-preview",
      cropBounds: paddedBounds,
      featherRadius,
      note:
        "Awaryjna maska używa granic zaznaczenia i dodaje miękką krawędź. Nieregularna selekcja nadal jest lepsza od prostego prostokąta."
    },
    file
  };
}

async function exportInpaintingAssets(document, dataFolder) {
  const filePrefix = `rasterrelay-${createSafeTimestamp()}`;
  const docSize = readDocumentSize(document);
  const selection = getSelectionInfo(document);

  const paddedBounds = calculatePaddedBounds(
    selection.bounds,
    docSize.width,
    docSize.height,
    SELECTION_PADDING_PX
  );

  const sourceImageExport = await exportCroppedSourcePng(document, dataFolder, filePrefix, paddedBounds);
  let selectionMask;

  try {
    selectionMask = await exportExactSelectionMaskPng(document, dataFolder, filePrefix, paddedBounds);
  } catch (error) {
    selectionMask = await exportBoundsMaskPng(document, dataFolder, filePrefix, paddedBounds);
    selectionMask.asset.fallbackReason = error.message || String(error);
  }

  return {
    assets: {
      sourceImage: sourceImageExport.asset,
      selectionMask: selectionMask.asset,
      cropBounds: paddedBounds
    },
    files: {
      sourceImage: sourceImageExport.file,
      selectionMask: selectionMask.file
    }
  };
}

function getUploadFileName(file, fallbackName) {
  if (file?.name && file.name !== "blob") {
    return file.name;
  }

  const nativePath = file?.nativePath || "";
  const pathName = nativePath.split(/[\\/]/).pop();
  return pathName || fallbackName;
}

async function readPngFileAsBytes(file) {
  const uxp = getUxpApi();
  const binary = await file.read({
    format: uxp.storage.formats.binary
  });

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
  const imageBytes = await readPngFileAsBytes(file);
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

async function uploadComfyImage(file, role) {
  const uploadName = getUploadFileName(file, `rasterrelay-${role}-${createSafeTimestamp()}.png`);
  const upload = await createComfyUploadBody(file, uploadName);

  const response = await fetch(`${COMFYUI_BASE_URL}/upload/image`, {
    method: "POST",
    headers: {
      "Content-Type": `multipart/form-data; boundary=${upload.boundary}`
    },
    body: upload.body
  });

  if (!response.ok) {
    throw new Error(`ComfyUI upload failed for ${role}: HTTP ${response.status}`);
  }

  const result = await response.json();

  return {
    role,
    name: result.name || file.name,
    subfolder: result.subfolder || "",
    type: result.type || "input"
  };
}

async function uploadAssetsToComfy(files) {
  const sourceImage = await uploadComfyImage(files.sourceImage, "sourceImage");
  const selectionMask = await uploadComfyImage(files.selectionMask, "selectionMask");

  return {
    sourceImage,
    selectionMask
  };
}

async function loadWorkflowBundle() {
  let workflowText;
  let mappingText;

  try {
    workflowText = await getPluginTextFile(WORKFLOW_FILE_NAME);
    mappingText = await getPluginTextFile(WORKFLOW_MAPPING_FILE_NAME);
  } catch {
    throw new Error(
      "Brakuje workflow API JSON. Dodaj prawdziwy eksport ComfyUI do photoshop_plugin/workflows/inpainting-api.json."
    );
  }

  const workflow = JSON.parse(workflowText);
  const mapping = JSON.parse(mappingText);

  if (mapping.status !== "ready") {
    throw new Error(
      "Workflow jest jeszcze szkicem. Najpierw trzeba wkleić prawdziwy eksport API z ComfyUI i ustawić mapping.status na ready."
    );
  }

  return {
    workflow,
    mapping
  };
}

async function getComfyObjectInfo() {
  const response = await fetch(`${COMFYUI_BASE_URL}/object_info`);

  if (!response.ok) {
    throw new Error(`Nie udało się sprawdzić node'ów ComfyUI: HTTP ${response.status}`);
  }

  return response.json();
}

function extractLoraNamesFromObjectInfo(objectInfo) {
  const loraInput = objectInfo?.LoraLoader?.input?.required?.lora_name;
  const names = Array.isArray(loraInput?.[0]) ? loraInput[0] : [];
  return names.filter((name) => typeof name === "string" && name.trim()).sort();
}

function addLoraNameToInput(name) {
  const current = ui.loraNamesInput.value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);

  if (!current.some((item) => item.split(":")[0] === name)) {
    current.push(name);
  }

  ui.loraNamesInput.value = current.join("\n");
  refreshActiveLoraSummary();
}

function refreshActiveLoraSummary() {
  if (!ui?.loraCatalogText) {
    return;
  }

  const active = getLoraItems();
  ui.loraCatalogText.textContent = active.length
    ? `Aktywne LoRA: ${active.length}. Workflow użyje ich po kolei przez LoraLoader.`
    : "LoRA: brak aktywnych. Workflow uruchomi się bez LoRA.";
}

function renderLoraCatalog(names) {
  if (!ui?.loraList || !ui?.loraCatalogText) {
    return;
  }

  ui.loraList.innerHTML = "";
  refreshActiveLoraSummary();

  if (!names.length) {
    ui.loraList.textContent = "ComfyUI nie zwróciło listy LoRA. Możesz wpisać nazwę ręcznie.";
    return;
  }

  names.slice(0, 24).forEach((name) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "lora-chip";
    button.textContent = name;
    button.addEventListener("click", () => addLoraNameToInput(name));
    ui.loraList.appendChild(button);
  });
}

async function refreshLoraCatalog() {
  if (!ui?.loraCatalogText || !ui?.loraList) {
    return;
  }

  ui.loraCatalogText.textContent = "LoRA: sprawdzam listę w ComfyUI...";

  try {
    const objectInfo = await getComfyObjectInfo();
    const names = extractLoraNamesFromObjectInfo(objectInfo);
    renderLoraCatalog(names);
  } catch {
    ui.loraCatalogText.textContent =
      "LoRA: nie mogę pobrać listy z ComfyUI. Wpisz nazwę pliku ręcznie, jeśli ją znasz.";
    ui.loraList.textContent = "";
  }
}

function getWorkflowClassTypes(workflow) {
  return [...new Set(Object.values(workflow).map((node) => node.class_type).filter(Boolean))];
}

function findMissingWorkflowClasses(workflow, objectInfo) {
  return getWorkflowClassTypes(workflow).filter((classType) => !objectInfo[classType]);
}

function validateWorkflowMapping(mapping) {
  const requiredInputs = ["sourceImage", "selectionMask", "prompt"];
  const missingInputs = requiredInputs.filter((id) => {
    const input = mapping.inputs?.[id];
    return !input?.nodeId || !input?.inputName;
  });

  if (missingInputs.length) {
    throw new Error(`Mapping workflow nie ma wymaganych wejść: ${missingInputs.join(", ")}.`);
  }
}

function setWorkflowInput(workflow, mappingItem, value) {
  if (!mappingItem) {
    return;
  }

  const node = workflow[mappingItem.nodeId];
  if (!node?.inputs) {
    throw new Error(`Nie znaleziono node ${mappingItem.nodeId} w workflow.`);
  }

  node.inputs[mappingItem.inputName] = value;
}

function getNextWorkflowNodeId(workflow) {
  const numericIds = Object.keys(workflow)
    .map((id) => Number(id))
    .filter((id) => Number.isFinite(id));

  return String(Math.max(0, ...numericIds) + 1);
}

function updateWorkflowTargets(workflow, targets, source) {
  if (!Array.isArray(targets)) {
    return;
  }

  targets.forEach((target) => {
    setWorkflowInput(workflow, target, source);
  });
}

function insertDynamicLoraChain(workflow, loraChain, loraItems) {
  if (!loraChain || !loraItems.length) {
    return false;
  }

  let modelSource = [loraChain.modelSource.nodeId, loraChain.modelSource.outputIndex ?? 0];
  let clipSource = [loraChain.clipSource.nodeId, loraChain.clipSource.outputIndex ?? 0];

  loraItems.forEach((lora) => {
    const nodeId = getNextWorkflowNodeId(workflow);
    workflow[nodeId] = {
      class_type: "LoraLoader",
      inputs: {
        model: modelSource,
        clip: clipSource,
        lora_name: lora.name,
        strength_model: lora.strengthModel,
        strength_clip: lora.strengthClip
      }
    };

    modelSource = [nodeId, 0];
    clipSource = [nodeId, 1];
  });

  updateWorkflowTargets(workflow, loraChain.modelTargets, modelSource);
  updateWorkflowTargets(workflow, loraChain.clipTargets, clipSource);
  return true;
}

function applyWorkflowInputs(workflow, mapping, job, comfyUploads) {
  setWorkflowInput(workflow, mapping.inputs.sourceImage, comfyUploads.sourceImage.name);
  setWorkflowInput(workflow, mapping.inputs.selectionMask, comfyUploads.selectionMask.name);
  setWorkflowInput(workflow, mapping.inputs.prompt, job.generation.prompt);
  setWorkflowInput(workflow, mapping.inputs.steps, job.generation.quality?.steps);
  setWorkflowInput(workflow, mapping.inputs.cfg, job.generation.quality?.cfg);

  applyLoraWorkflowInputs(workflow, mapping, job.generation.lora.items);
}

function applyLoraWorkflowInputs(workflow, mapping, loraItems) {
  if (insertDynamicLoraChain(workflow, mapping.loraChain, loraItems)) {
    return;
  }

  const loraSlots = Array.isArray(mapping.inputs.loras) ? mapping.inputs.loras : [];

  loraSlots.forEach((slot, index) => {
    const lora = loraItems[index] || null;
    const strengthModel = lora?.strengthModel ?? slot.emptyStrength ?? 0;
    const strengthClip = lora?.strengthClip ?? slot.emptyStrength ?? 0;

    setWorkflowInput(workflow, slot.name, lora?.name || slot.emptyName || "");
    setWorkflowInput(workflow, slot.strengthModel, strengthModel);
    setWorkflowInput(workflow, slot.strengthClip, strengthClip);
  });

  if (mapping.inputs.loraStrength) {
    const firstLora = loraItems[0];
    setWorkflowInput(workflow, mapping.inputs.loraStrength, firstLora?.strengthModel ?? 0);
  }

  if (mapping.inputs.loraName) {
    const firstLora = loraItems[0];
    setWorkflowInput(workflow, mapping.inputs.loraName, firstLora?.name || "");
  }
}

async function queueComfyWorkflow(job, comfyUploads) {
  const { workflow, mapping } = await loadWorkflowBundle();
  applyWorkflowInputs(workflow, mapping, job, comfyUploads);

  const response = await fetch(`${COMFYUI_BASE_URL}/prompt`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      client_id: "rasterrelay-photoshop",
      prompt: workflow
    })
  });

  const result = await response.json();

  if (!response.ok || result.error) {
    throw new Error(`ComfyUI odrzuciło workflow: ${result.error || `HTTP ${response.status}`}`);
  }

  return {
    promptId: result.prompt_id,
    number: result.number,
    nodeErrors: result.node_errors || null
  };
}

function wait(milliseconds) {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}

function findFirstOutputImage(historyEntry) {
  const outputs = historyEntry?.outputs || {};

  for (const nodeOutput of Object.values(outputs)) {
    const images = nodeOutput.images || [];
    const outputImage = images.find((image) => image.type === "output") || images[0];

    if (outputImage) {
      return outputImage;
    }
  }

  return null;
}

async function getComfyHistory(promptId) {
  const response = await fetch(`${COMFYUI_BASE_URL}/history/${encodeURIComponent(promptId)}`);

  if (!response.ok) {
    throw new Error(`Nie udało się pobrać historii ComfyUI: HTTP ${response.status}`);
  }

  return response.json();
}

async function waitForComfyOutput(promptId) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < COMFY_HISTORY_TIMEOUT_MS) {
    const history = await getComfyHistory(promptId);
    const entry = history[promptId];
    const outputImage = findFirstOutputImage(entry);

    if (outputImage) {
      return {
        history: entry,
        image: outputImage
      };
    }

    await wait(COMFY_HISTORY_POLL_MS);
  }

  throw new Error("ComfyUI nie zwróciło obrazu w wyznaczonym czasie.");
}

async function downloadComfyImage(image, dataFolder) {
  const params = new URLSearchParams({
    filename: image.filename,
    subfolder: image.subfolder || "",
    type: image.type || "output"
  });
  const response = await fetch(`${COMFYUI_BASE_URL}/view?${params.toString()}`);

  if (!response.ok) {
    throw new Error(`Nie udało się pobrać wyniku z ComfyUI: HTTP ${response.status}`);
  }

  const imageBuffer = await response.arrayBuffer();
  const file = await dataFolder.createFile(`rasterrelay-result-${createSafeTimestamp()}.png`, {
    overwrite: true
  });

  await file.write(imageBuffer);

  return {
    file,
    asset: {
      kind: "comfyOutputImage",
      format: "png",
      path: file.nativePath || file.name,
      comfy: {
        filename: image.filename,
        subfolder: image.subfolder || "",
        type: image.type || "output"
      }
    }
  };
}

async function placeImageFileAsLayer(file, cropBounds) {
  const photoshop = getPhotoshopApi();
  const uxp = getUxpApi();

  if (!photoshop || !uxp) {
    throw new Error("Photoshop API albo UXP storage jest niedostępne.");
  }

  const token = await uxp.storage.localFileSystem.createSessionToken(file);
  const placement = {
    layerMode: "placed-embedded",
    layerMask: {
      applied: false,
      source: "active-selection"
    }
  };

  const offsetX = cropBounds ? cropBounds.left : 0;
  const offsetY = cropBounds ? cropBounds.top : 0;

  await photoshop.core.executeAsModal(
    async () => {
      const capturedMask = await captureSoftSelectionMaskForLayer(photoshop);
      if (capturedMask?.captured) {
        await clearActiveSelection(photoshop);
      }

      await photoshop.action.batchPlay(
        [
          {
            _obj: "placeEvent",
            null: {
              _path: token,
              _kind: "local"
            },
            freeTransformCenterState: {
              _enum: "quadCenterState",
              _value: "QCSAverage"
            },
            offset: {
              _obj: "offset",
              horizontal: {
                _unit: "pixelsUnit",
                _value: offsetX
              },
              vertical: {
                _unit: "pixelsUnit",
                _value: offsetY
              }
            }
          }
        ],
        {}
      );

      placement.layerId = getActiveLayerId(photoshop);
      const activeLayer = photoshop.app.activeDocument?.activeLayers?.[0];
      if (activeLayer) {
        activeLayer.name = "RasterRelay - wynik";
      }
      placement.layerMask = capturedMask?.captured
        ? await applyCapturedMaskToActiveLayer(photoshop, placement.layerId, capturedMask)
        : await applySelectionMaskToActiveLayer(photoshop, placement.layerId);
    },
    { commandName: "RasterRelay Place Result Layer" }
  );

  return placement;
}

function getActiveLayerId(photoshop) {
  const activeLayer = photoshop.app.activeDocument?.activeLayers?.[0];
  if (!activeLayer?.id) {
    throw new Error("Nie udało się odczytać aktywnej warstwy po wstawieniu wyniku.");
  }

  return activeLayer.id;
}

async function captureSoftSelectionMaskForLayer(photoshop) {
  if (
    !photoshop.imaging?.getSelection ||
    !photoshop.imaging?.createImageDataFromBuffer
  ) {
    return {
      captured: false,
      source: "active-selection",
      fallback: "imaging-api-unavailable"
    };
  }

  const document = photoshop.app.activeDocument;
  const selection = getSelectionInfo(document);
  if (!selection.hasSelection) {
    return {
      captured: false,
      source: "active-selection",
      fallback: "selection-missing"
    };
  }

  const selectionImage = await photoshop.imaging.getSelection({
    documentID: document.id,
    sourceBounds: selection.bounds
  });

  try {
    const size = getImageDataSize(selectionImage);
    const selectionPixels = await selectionImage.imageData.getData();
    const components = Math.max(1, Math.round(selectionPixels.length / (size.width * size.height)));
    const hardMaskPixels = new Uint8Array(size.width * size.height);

    for (let i = 0; i < size.width * size.height; i++) {
      const srcIdx = i * components;
      let maskValue;

      if (components === 1) {
        maskValue = selectionPixels[srcIdx];
      } else if (components === 4) {
        maskValue = selectionPixels[srcIdx + 3];
      } else {
        maskValue = selectionPixels[srcIdx];
      }

      hardMaskPixels[i] = maskValue;
    }

    const imageData = await photoshop.imaging.createImageDataFromBuffer(hardMaskPixels, {
      width: size.width,
      height: size.height,
      components: 1,
      chunky: false,
      colorProfile: "Gray Gamma 2.2",
      colorSpace: "Grayscale"
    });

    return {
      captured: true,
      source: "active-selection-before-place",
      mode: "photoshop-selection-pixels-hard",
      imageData,
      featherRadius: 0,
      targetBounds: {
        left: Math.round(selectionImage.sourceBounds?.left ?? selection.bounds.left),
        top: Math.round(selectionImage.sourceBounds?.top ?? selection.bounds.top)
      },
      sourceBounds: selectionImage.sourceBounds || selection.bounds
    };
  } finally {
    selectionImage.imageData?.dispose?.();
  }
}

async function clearActiveSelection(photoshop) {
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

async function applyCapturedMaskToActiveLayer(photoshop, layerId, capturedMask) {
  if (!photoshop.imaging?.putLayerMask || !capturedMask?.imageData) {
    return {
      applied: false,
      source: capturedMask?.source || "captured-selection",
      fallback: "captured-mask-unavailable"
    };
  }

  try {
    await photoshop.imaging.putLayerMask({
      documentID: photoshop.app.activeDocument.id,
      layerID: layerId,
      kind: "user",
      imageData: capturedMask.imageData,
      replace: true,
      targetBounds: capturedMask.targetBounds,
      commandName: "RasterRelay Apply Captured Selection Mask"
    });

    return {
      applied: true,
      source: capturedMask.source,
      mode: capturedMask.mode,
      featherRadius: capturedMask.featherRadius,
      targetBounds: capturedMask.sourceBounds
    };
  } catch (error) {
    return {
      applied: false,
      source: capturedMask.source,
      fallback: "captured-layer-mask-failed",
      error: error.message || String(error)
    };
  } finally {
    capturedMask.imageData?.dispose?.();
  }
}

async function applySelectionMaskToActiveLayer(photoshop, layerId) {
  if (
    !photoshop.imaging?.putLayerMask ||
    !photoshop.imaging?.getSelection ||
    !photoshop.imaging?.createImageDataFromBuffer
  ) {
    return {
      applied: false,
      source: "active-selection",
      fallback: "imaging-api-unavailable"
    };
  }

  const document = photoshop.app.activeDocument;
  const selection = getSelectionInfo(document);
  if (!selection.hasSelection) {
    return {
      applied: false,
      source: "active-selection",
      fallback: "selection-missing"
    };
  }

  let selectionImage = null;
  let hardMaskImageData = null;

  try {
    selectionImage = await photoshop.imaging.getSelection({
      documentID: document.id,
      sourceBounds: selection.bounds
    });
    const size = getImageDataSize(selectionImage);
    const selectionPixels = await selectionImage.imageData.getData();
    const components = Math.max(1, Math.round(selectionPixels.length / (size.width * size.height)));
    const hardMaskPixels = new Uint8Array(size.width * size.height);

    for (let i = 0; i < size.width * size.height; i++) {
      const srcIdx = i * components;
      let maskValue;

      if (components === 1) {
        maskValue = selectionPixels[srcIdx];
      } else if (components === 4) {
        maskValue = selectionPixels[srcIdx + 3];
      } else {
        maskValue = selectionPixels[srcIdx];
      }

      hardMaskPixels[i] = maskValue;
    }

    hardMaskImageData = await photoshop.imaging.createImageDataFromBuffer(hardMaskPixels, {
      width: size.width,
      height: size.height,
      components: 1,
      chunky: false,
      colorProfile: "Gray Gamma 2.2",
      colorSpace: "Grayscale"
    });

    await photoshop.imaging.putLayerMask({
      documentID: document.id,
      layerID: layerId,
      kind: "user",
      imageData: hardMaskImageData,
      replace: true,
      targetBounds: {
        left: Math.round(selectionImage.sourceBounds?.left ?? selection.bounds.left),
        top: Math.round(selectionImage.sourceBounds?.top ?? selection.bounds.top)
      },
      commandName: "RasterRelay Apply Selection Mask"
    });

    return {
      applied: true,
      source: "active-selection",
      mode: "photoshop-selection-pixels-hard",
      featherRadius: 0,
      targetBounds: selectionImage.sourceBounds || selection.bounds
    };
  } catch (error) {
    return {
      applied: false,
      source: "active-selection",
      fallback: "selection-layer-mask-failed",
      error: error.message || String(error)
    };
  } finally {
    hardMaskImageData?.dispose?.();
    selectionImage?.imageData?.dispose?.();
  }
}

async function receiveComfyResult(promptId, dataFolder, cropBounds) {
  const output = await waitForComfyOutput(promptId);
  const downloaded = await downloadComfyImage(output.image, dataFolder);

  try {
    const placement = await placeImageFileAsLayer(downloaded.file, cropBounds);
    downloaded.asset.photoshop = {
      placedAsLayer: true,
      layerMode: placement.layerMode,
      layerId: placement.layerId,
      layerMask: placement.layerMask
    };
  } catch (error) {
    downloaded.asset.photoshop = {
      placedAsLayer: false,
      fallback: "downloaded-only",
      error: error.message || String(error)
    };
  }

  return downloaded.asset;
}

async function saveJobPackage(job, dataFolder) {
  const file = await dataFolder.createFile(JOB_FILE_NAME, {
    overwrite: true
  });

  await file.write(JSON.stringify(job, null, 2));
  return file.nativePath || file.name;
}

async function createInpaintingJobPackage() {
  const prompt = getPrompt();
  const document = getActiveDocument();
  const error = validateJobInputs(prompt, document);

  if (error) {
    setMessage(error);
    return null;
  }

  const dataFolder = await getDataFolder();
  const exported = await exportInpaintingAssets(document, dataFolder);
  const job = buildInpaintingJob(document, prompt, exported.assets);
  const savedPath = await saveJobPackage(job, dataFolder);
  setMessage(`Paczka zadania została zapisana: ${savedPath}. Obraz i pierwsza maska PNG są gotowe.`);
  return {
    job,
    files: exported.files,
    dataFolder,
    savedPath
  };
}

async function prepareInpaintingEdit() {
  ui.prepareButton.disabled = true;

  try {
    const packageResult = await createInpaintingJobPackage();
    if (!packageResult) {
      return;
    }

    const comfyReady = await checkComfyUi();
    if (!comfyReady) {
      return;
    }

    const comfyUploads = await uploadAssetsToComfy(packageResult.files);
    packageResult.job.comfy = {
      uploaded: true,
      uploads: comfyUploads,
      workflowQueued: false,
      note: "Pliki wejściowe są w ComfyUI. Kolejny krok to podpiąć workflow API JSON i wysłać /prompt."
    };
    await saveJobPackage(packageResult.job, packageResult.dataFolder);

    const queuedWorkflow = await queueComfyWorkflow(packageResult.job, comfyUploads);
    packageResult.job.comfy.workflowQueued = true;
    packageResult.job.comfy.queue = queuedWorkflow;
    packageResult.job.comfy.note = "Workflow został wysłany do kolejki ComfyUI. Czekam na obraz wynikowy.";
    await saveJobPackage(packageResult.job, packageResult.dataFolder);

    const resultAsset = await receiveComfyResult(
      queuedWorkflow.promptId,
      packageResult.dataFolder,
      packageResult.job.cropBounds
    );
    packageResult.job.outputs.resultImage = resultAsset;
    const maskApplied = Boolean(resultAsset.photoshop?.layerMask?.applied);
    packageResult.job.comfy.note = resultAsset.photoshop?.placedAsLayer
      ? maskApplied
        ? "Wynik ComfyUI został pobrany i wstawiony do Photoshopa jako nowa warstwa z maską."
        : "Wynik ComfyUI został pobrany i wstawiony do Photoshopa jako nowa warstwa. Maska warstwy wymaga sprawdzenia."
      : "Wynik ComfyUI został pobrany, ale nie udało się wstawić go automatycznie jako warstwy.";
    await saveJobPackage(packageResult.job, packageResult.dataFolder);

    setMessage(
      resultAsset.photoshop?.placedAsLayer
        ? maskApplied
          ? `Wynik ComfyUI pobrany i wstawiony jako nowa warstwa z maską. Prompt ID: ${queuedWorkflow.promptId}.`
          : `Wynik ComfyUI pobrany i wstawiony jako nowa warstwa. Maska wymaga ręcznego sprawdzenia. Prompt ID: ${queuedWorkflow.promptId}.`
        : `Wynik ComfyUI pobrany do pliku, ale nie udało się wstawić warstwy automatycznie: ${resultAsset.photoshop?.error}`
    );
  } catch (error) {
    setMessage(`Nie udało się przygotować edycji: ${error.message || error}`);
  } finally {
    ui.prepareButton.disabled = false;
  }
}

async function runInpaintingEdit() {
  return prepareInpaintingEdit();
}

async function handleSaveJobPackage() {
  ui.packageButton.disabled = true;

  try {
    await createInpaintingJobPackage();
  } catch (error) {
    setMessage(`Nie udało się zapisać paczki zadania: ${error.message || error}`);
  } finally {
    ui.packageButton.disabled = false;
  }
}

async function checkRasterRelayReadiness() {
  ui.readinessButton.disabled = true;
  setMessage("Sprawdzam gotowość: dokument, ComfyUI i workflow...");

  try {
    const prompt = getPrompt();
    const document = getActiveDocument();
    const inputError = validateJobInputs(prompt, document);
    if (inputError) {
      setMessage(inputError);
      return false;
    }

    const comfyReady = await checkComfyUi();
    if (!comfyReady) {
      return false;
    }

    const { workflow, mapping } = await loadWorkflowBundle();
    validateWorkflowMapping(mapping);

    const objectInfo = await getComfyObjectInfo();
    const missingClasses = findMissingWorkflowClasses(workflow, objectInfo);
    if (missingClasses.length) {
      setMessage(`ComfyUI nie ma wymaganych node'ów: ${missingClasses.join(", ")}.`);
      return false;
    }

    const quality = getQualityPreset();
    const loraCount = getLoraItems().length;
    setMessage(
      `Gotowe do edycji. Jakość: ${quality.label}, kroki: ${quality.steps}, LoRA: ${loraCount}. Możesz kliknąć Przygotuj edycję.`
    );
    return true;
  } catch (error) {
    setMessage(`Gotowość nie przeszła: ${error.message || error}`);
    return false;
  } finally {
    ui.readinessButton.disabled = false;
  }
}

function initializePanel(rootNode) {
  if (rootNode.__rasterRelayInitialized) {
    return;
  }

  mountPanelMarkup(rootNode);
  ui = collectUi(rootNode);

  ui.checkComfyButton.addEventListener("click", () => {
    void checkComfyUi();
  });

  ui.documentButton.addEventListener("click", () => {
    void checkDocument();
  });

  ui.packageButton.addEventListener("click", () => {
    void handleSaveJobPackage();
  });

  ui.readinessButton.addEventListener("click", () => {
    void checkRasterRelayReadiness();
  });

  ui.prepareButton.addEventListener("click", () => {
    void runInpaintingEdit();
  });

  ui.loraNamesInput.addEventListener("input", refreshActiveLoraSummary);
  ui.loraStrengthModelInput.addEventListener("input", refreshActiveLoraSummary);
  ui.loraStrengthClipInput.addEventListener("input", refreshActiveLoraSummary);

  if (ui.e2eSmokeButton) {
    ui.e2eSmokeButton.addEventListener("click", () => {
      void runE2ESmokeTest();
    });
  }

  rootNode.__rasterRelayInitialized = true;
  refreshActiveLoraSummary();

  window.setTimeout(() => {
    void runAutostartE2EIfRequested();
  }, 1000);
}

async function runE2ESmokeTest() {
  if (!globalThis.RasterRelayE2ESmokeTest?.run) {
    setMessage("Test E2E nie jest załadowany w panelu.");
    return;
  }

  if (ui?.e2eSmokeButton) {
    ui.e2eSmokeButton.disabled = true;
  }

  setMessage("Uruchamiam test E2E: Photoshop -> ComfyUI -> warstwa wynikowa...");

  try {
    const result = await globalThis.RasterRelayE2ESmokeTest.run();
    setMessage(
      result?.promptId
        ? `Test E2E zakończony. Wynik wstawiony jako warstwa. Prompt ID: ${result.promptId}.`
        : "Test E2E zakończony. Sprawdź nowy dokument i warstwę w Photoshopie."
    );
  } catch (error) {
    setMessage(`Test E2E nie przeszedł: ${error.message || error}`);
  } finally {
    if (ui?.e2eSmokeButton) {
      ui.e2eSmokeButton.disabled = false;
    }
  }
}

async function runAutostartE2EIfRequested() {
  if (autostartE2EConsumed) {
    return;
  }

  const flag = await getOptionalPluginTextFile(E2E_AUTOSTART_FILE_NAME);
  if (!flag) {
    return;
  }

  autostartE2EConsumed = true;
  await runE2ESmokeTest();
}

const uxpApi = getUxpApi();

if (uxpApi?.entrypoints) {
  uxpApi.entrypoints.setup({
    plugin: {
      create() {
        console.log("RasterRelay plugin loaded.");
        window.setTimeout(showRasterRelayPanel, 500);
        window.setTimeout(() => {
          void runAutostartE2EIfRequested();
        }, 1200);
      }
    },
    panels: {
      rasterrelayPanel: {
        create(rootNode) {
          console.log("RasterRelay panel create.");
          initializePanel(rootNode);
        },
        show(rootNode) {
          console.log("RasterRelay panel show.");
          initializePanel(rootNode);
        }
      }
    },
    commands: {
      runE2ESmokeTest: {
        run() {
          return runE2ESmokeTest();
        }
      }
    }
  });
} else {
  window.addEventListener("DOMContentLoaded", () => initializePanel(document.body));
}
})();
