(() => {
const COMFYUI_BASE_URL = "http://127.0.0.1:8188";
const COMFYUI_WS_URL = "ws://127.0.0.1:8188/ws";
const COMFY_CLIENT_ID = "rasterrelay-photoshop";
const COMFYUI_SYSTEM_STATS_URL = `${COMFYUI_BASE_URL}/system_stats`;
const JOB_FILE_NAME = "rasterrelay-inpainting-job.json";
const QUALITY_SETTINGS_FILE_NAME = "rasterrelay-quality-settings.json";
const LORA_CONFIG_FILE_NAME = "rasterrelay-lora-config.json";
const WORKFLOW_FILE_NAME = "workflows/inpainting-api.json";
const WORKFLOW_MAPPING_FILE_NAME = "workflows/inpainting-api.mapping.json";
const INSTALL_NODES_COMMAND = "powershell -ExecutionPolicy Bypass -File .\\scripts\\install-comfy-nodes.ps1 -ComfyRoot E:\\AI\\ComfyUI";
const E2E_AUTOSTART_FILE_NAME = "e2e-autostart.flag";
const GEOMETRY_AUTOSTART_FILE_NAME = "geometry-autostart.flag";
const GEOMETRY_TEST_SOURCE_FILE_NAME = "test_assets/can-source.png";
const COMFY_HISTORY_TIMEOUT_MS = 10 * 60 * 1000;
const COMFY_HISTORY_POLL_MS = 2000;
const DEFAULT_MASK_FEATHER_RATIO = 0.015;
const DEFAULT_MASK_FEATHER_MIN_PX = 8;
const DEFAULT_MASK_FEATHER_MAX_PX = 32;
const SELECTION_PADDING_PX = 96;
const GENERATION_SIZE_MULTIPLE = 16;
const GEOMETRY_TEST_SELECTION = {
  centerX: 711,
  centerY: 542,
  radiusX: 42,
  radiusY: 68
};
const panelHelpers = globalThis.RasterRelayPanelHelpers || {};
const defaultQualitySettings = panelHelpers.normalizeQualitySettings
  ? panelHelpers.normalizeQualitySettings({})
  : {
      schemaVersion: "rasterrelay.qualitySettings.v1",
      quality: "balanced",
      maskFeatherPx: 24,
      maskGrowPx: 0,
      variantCount: 1,
      negativePrompt:
        "hard square edges, visible seams, distorted hands, extra fingers, unreadable artifacts, duplicated object, damaged background"
    };
function buildQualityPreset(name, label) {
  const plan = panelHelpers.resolveQualityPlan
    ? panelHelpers.resolveQualityPlan(name)
    : { name, steps: 14, refine: false, refineSourceNodeId: "93" };
  return { label, cfg: 1, ...plan };
}

const qualityPresets = {
  fast: buildQualityPreset("fast", "Szybki (8 kroków)"),
  balanced: buildQualityPreset("balanced", "Dobra jakość (14 kroków)"),
  quality: buildQualityPreset("quality", "Maks (20 kroków)")
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
      <button id="checkComfyButton">Sprawdź ComfyUI</button>
    </section>

    <section class="form-section" aria-label="Ustawienia inpaintingu">
      <label for="promptInput">Prompt</label>
      <textarea id="promptInput" rows="5" placeholder="Napisz, co ma się pojawić w zaznaczonym miejscu."></textarea>

      <label for="editModeSelect">Tryb</label>
      <select id="editModeSelect">
        <option value="edit" selected>Edycja — zmień zaznaczony obszar</option>
        <option value="remove">Usuwanie obiektu — szersza maska</option>
      </select>

      <label for="qualitySelectVisible">Jakość</label>
      <select id="qualitySelectVisible">
        <option value="fast">Szybki — 8 kroków, najszybszy</option>
        <option value="balanced" selected>Dobra jakość — 14 kroków, zalecane</option>
        <option value="quality">Maks — 20 kroków, najgładszy</option>
      </select>
    </section>

    <section class="action-section" aria-label="Funkcja RasterRelay">
      <button class="primary" id="prepareButton">Przygotuj edycje</button>
      <button class="dev-only" id="e2eSmokeButton">Test E2E</button>
      <button id="documentButton">Sprawdź dokument</button>
    </section>

    <section class="progress-card" id="progressCard" aria-live="polite" hidden>
      <div class="rr-progress-track"><div class="rr-progress-bar" id="progressBar"></div></div>
      <span id="progressLabel" class="rr-progress-label"></span>
    </section>

    <section class="log-card" aria-live="polite">
      <p id="messageText">Otwórz dokument w Photoshopie, uruchom ComfyUI w Launcherze i sprawdź połączenie.</p>
    </section>

    <section class="rr-hidden-settings" aria-hidden="true">
      <select id="qualitySelect">
        <option value="balanced" selected>Dobra jakość</option>
        <option value="fast">Szybki test</option>
        <option value="quality">Dokładna edycja</option>
      </select>
      <button id="readinessButton" type="button"></button>
      <button id="packageButton" type="button"></button>
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
    messageText: findPanelElement(rootNode, "messageText"),
    packageButton: findPanelElement(rootNode, "packageButton"),
    prepareButton: findPanelElement(rootNode, "prepareButton"),
    promptInput: findPanelElement(rootNode, "promptInput"),
    qualitySelect: findPanelElement(rootNode, "qualitySelect"),
    qualitySelectVisible: findPanelElement(rootNode, "qualitySelectVisible"),
    editModeSelect: findPanelElement(rootNode, "editModeSelect"),
    progressCard: findPanelElement(rootNode, "progressCard"),
    progressBar: findPanelElement(rootNode, "progressBar"),
    progressLabel: findPanelElement(rootNode, "progressLabel"),
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

function setProgress(fraction, label) {
  if (!ui?.progressCard) {
    return;
  }
  if (fraction === null) {
    ui.progressCard.hidden = true;
    return;
  }
  ui.progressCard.hidden = false;
  const pct = Math.max(0, Math.min(100, Math.round(fraction * 100)));
  if (ui.progressBar) {
    ui.progressBar.style.width = `${pct}%`;
    ui.progressBar.classList.toggle("indeterminate", fraction === undefined);
  }
  if (ui.progressLabel) {
    ui.progressLabel.textContent = label || (fraction === undefined ? "Pracuję..." : `${pct}%`);
  }
}

// Live progress from ComfyUI over WebSocket. Display-only and best-effort: the
// authoritative completion still comes from history polling, so a WS failure
// never blocks a generation. Schema confirmed via ComfyUI docs:
// {type, data} with types progress(value,max), executing(node), execution_*.
function subscribeComfyProgress(promptId, onUpdate) {
  let socket = null;
  try {
    socket = new WebSocket(`${COMFYUI_WS_URL}?clientId=${COMFY_CLIENT_ID}`);
  } catch {
    return () => {};
  }
  socket.onmessage = (event) => {
    if (typeof event.data !== "string") {
      return; // binary preview frames
    }
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    const data = msg?.data || {};
    if (data.prompt_id && promptId && data.prompt_id !== promptId) {
      return;
    }
    if (msg.type === "progress" && data.max) {
      onUpdate({ fraction: data.value / data.max, label: `Generuję… ${data.value}/${data.max}` });
    } else if (msg.type === "executing") {
      if (data.node === null) {
        onUpdate({ fraction: undefined, label: "Składam wynik…" });
      } else {
        onUpdate({ fraction: undefined, label: "Przetwarzam…" });
      }
    }
  };
  socket.onerror = () => {};
  return () => {
    try {
      socket?.close();
    } catch {
      /* ignore */
    }
  };
}

// Turn a raw failure into a clear, actionable Polish message.
function describeComfyError(error) {
  const raw = String(error?.message || error || "");
  const lower = raw.toLowerCase();
  if (
    lower.includes("failed to fetch") ||
    lower.includes("networkerror") ||
    lower.includes("err_connection") ||
    lower.includes("econnrefused")
  ) {
    return "ComfyUI nie odpowiada (http://127.0.0.1:8188). Uruchom je w Launcherze przyciskiem „Start ComfyUI” i sprawdź połączenie.";
  }
  if (lower.includes("nieaktualne albo niezgodne custom nodes") || lower.includes("brakuje wejsc")) {
    return `${raw}`;
  }
  if (lower.includes("out of memory") || lower.includes("cuda") || lower.includes("oom") || lower.includes("alloc")) {
    return "Zabrakło pamięci GPU (VRAM). Zmniejsz zaznaczenie albo użyj presetu „Szybki”. Szczegóły: " + raw;
  }
  if (lower.includes("odrzucilo workflow") || lower.includes("node_errors")) {
    return "ComfyUI odrzuciło workflow — najczęściej brak modelu lub węzła. Przeinstaluj RasterRelay nodes i sprawdź modele. Szczegóły: " + raw;
  }
  return raw || "Nieznany błąd.";
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

function normalizeAlphaBBox(outputMetadata = {}) {
  const alphaBBox =
    outputMetadata.alphaBBox ||
    outputMetadata.alpha_bbox ||
    outputMetadata.comfy?.alphaBBox ||
    outputMetadata.comfy?.alpha_bbox ||
    null;

  if (!alphaBBox || typeof alphaBBox !== "object") {
    return null;
  }

  const normalized = {
    left: Number(alphaBBox.left),
    top: Number(alphaBBox.top),
    right: Number(alphaBBox.right),
    bottom: Number(alphaBBox.bottom)
  };

  if (!["left", "top", "right", "bottom"].every((key) => Number.isFinite(normalized[key]))) {
    return null;
  }

  return {
    left: Math.round(normalized.left),
    top: Math.round(normalized.top),
    right: Math.round(normalized.right),
    bottom: Math.round(normalized.bottom)
  };
}

function createSkippedCompositeAudit(reason) {
  return {
    checked: false,
    skipped: true,
    passed: null,
    reason: reason || "Composite audit was not available."
  };
}

function createCompositeAuditError(message, audit) {
  const error = new Error(message);
  error.compositeAudit = audit || null;
  return error;
}

function shouldRejectCompositeAudit(audit) {
  if (panelHelpers.shouldRejectCompositeAudit) {
    return panelHelpers.shouldRejectCompositeAudit(audit);
  }

  if (!audit || audit.skipped) {
    return true;
  }

  return audit.checked ? audit.passed !== true : true;
}

async function getDocumentCompositeSnapshot(document, size = readDocumentSize(document)) {
  const photoshop = getPhotoshopApi();

  if (!photoshop?.imaging?.getPixels) {
    throw new Error("Photoshop imaging.getPixels is unavailable.");
  }

  if (!document?.id) {
    throw new Error("Active Photoshop document is unavailable.");
  }

  const width = Math.round(size.width);
  const height = Math.round(size.height);
  if (!width || !height) {
    throw new Error(`Invalid document size for composite audit: ${width}x${height}.`);
  }

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

    return {
      width: imageData.width,
      height: imageData.height,
      components: imageData.components,
      componentSize: imageData.componentSize,
      pixelFormat: imageData.pixelFormat,
      sourceBounds: pixelResult.sourceBounds || { left: 0, top: 0, right: width, bottom: height },
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
    throw new Error(
      `${label} snapshot has unsupported format components=${snapshot.components}, componentSize=${snapshot.componentSize}.`
    );
  }
  const bounds = snapshot.sourceBounds || {};
  if (Math.round(bounds.left || 0) !== 0 || Math.round(bounds.top || 0) !== 0) {
    throw new Error(`${label} snapshot source bounds start at ${JSON.stringify(bounds)}, expected document origin.`);
  }
}

function maxCompositeSourceChromaError(beforeData, beforeOffset, afterData, afterOffset) {
  if (panelHelpers.maxSourceChromaError) {
    return panelHelpers.maxSourceChromaError(beforeData, beforeOffset, afterData, afterOffset);
  }

  const beforeDiffs = [
    beforeData[beforeOffset] - beforeData[beforeOffset + 1],
    beforeData[beforeOffset] - beforeData[beforeOffset + 2],
    beforeData[beforeOffset + 1] - beforeData[beforeOffset + 2]
  ];
  const afterDiffs = [
    afterData[afterOffset] - afterData[afterOffset + 1],
    afterData[afterOffset] - afterData[afterOffset + 2],
    afterData[afterOffset + 1] - afterData[afterOffset + 2]
  ];

  return beforeDiffs.reduce((maxError, beforeDiff, index) => {
    return Math.max(maxError, Math.abs(beforeDiff - afterDiffs[index]));
  }, 0);
}

function auditCompositeColorLock(beforeSnapshot, afterSnapshot, outputMetadata, size) {
  const alphaBBox = normalizeAlphaBBox(outputMetadata);
  if (!alphaBBox) {
    throw new Error("Output image did not include valid alphaBBox metadata.");
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
          const chromaError = maxCompositeSourceChromaError(
            beforeSnapshot.data,
            beforeOffset,
            afterSnapshot.data,
            afterOffset
          );
          sourceChromaMaxErrorInsideChanged = Math.max(sourceChromaMaxErrorInsideChanged, chromaError);
          sourceChromaErrorSumInsideChanged += chromaError;
          sourceChromaCheckedPixels += 1;

          if (panelHelpers.sourceHueError) {
            const hueError = panelHelpers.sourceHueError(
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
          }
          if (panelHelpers.sourceSaturationError) {
            const saturationError = panelHelpers.sourceSaturationError(
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
        }
      } else if (diff > 0) {
        outsideChangedPixels += 1;
        maxDiffOutsideAlphaBBox = Math.max(maxDiffOutsideAlphaBBox, diff);
      }
    }
  }

  return {
    checked: true,
    skipped: false,
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

async function createCompositeAuditContext(outputMetadata = {}) {
  const usesChangeAlpha = panelHelpers.shouldUsePngAlphaOnly
    ? panelHelpers.shouldUsePngAlphaOnly(outputMetadata)
    : Boolean(normalizeAlphaBBox(outputMetadata));

  if (!usesChangeAlpha) {
    return {
      required: true,
      beforeSnapshot: null,
      documentSize: null,
      skippedAudit: createSkippedCompositeAudit("Output has no change-alpha bbox metadata.")
    };
  }

  try {
    const document = getActiveDocument();
    const documentSize = readDocumentSize(document);
    const beforeSnapshot = await getDocumentCompositeSnapshot(document, documentSize);

    return {
      required: true,
      beforeSnapshot,
      documentSize,
      skippedAudit: null
    };
  } catch (error) {
    return {
      required: true,
      beforeSnapshot: null,
      documentSize: null,
      skippedAudit: createSkippedCompositeAudit(error.message || String(error))
    };
  }
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
  if (panelHelpers.calculatePaddedBounds) {
    return panelHelpers.calculatePaddedBounds(selectionBounds, docWidth, docHeight, padding);
  }

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
  const value = ui?.qualitySelectVisible?.value || ui?.qualitySelect?.value;
  return qualityPresets[value] || qualityPresets.balanced;
}

function getEditMode() {
  return ui?.editModeSelect?.value === "remove" ? "remove" : "edit";
}

function getQualityPresetForSettings(settings) {
  return qualityPresets[settings?.quality] || qualityPresets.balanced;
}

async function loadQualitySettings() {
  const text = await getOptionalPluginTextFile(QUALITY_SETTINGS_FILE_NAME);
  if (!text) {
    return defaultQualitySettings;
  }

  try {
    const parsed = JSON.parse(text);
    return panelHelpers.normalizeQualitySettings
      ? panelHelpers.normalizeQualitySettings(parsed)
      : { ...defaultQualitySettings, ...parsed };
  } catch {
    return defaultQualitySettings;
  }
}

async function loadLoraConfig() {
  const text = await getOptionalPluginTextFile(LORA_CONFIG_FILE_NAME);
  if (!text) {
    return { schemaVersion: "rasterrelay.loraConfig.v1", loras: [] };
  }
  try {
    const parsed = JSON.parse(text);
    return {
      schemaVersion: parsed.schemaVersion || "rasterrelay.loraConfig.v1",
      loras: Array.isArray(parsed.loras) ? parsed.loras : []
    };
  } catch {
    return { schemaVersion: "rasterrelay.loraConfig.v1", loras: [] };
  }
}

function createSafeTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function readPngUint32(bytes, offset) {
  return (
    ((bytes[offset] << 24) >>> 0) +
    ((bytes[offset + 1] << 16) >>> 0) +
    ((bytes[offset + 2] << 8) >>> 0) +
    (bytes[offset + 3] >>> 0)
  );
}

async function readPngDimensions(file) {
  const uxp = getUxpApi();
  const binaryFormat = uxp?.storage?.formats?.binary;
  const buffer = await file.read(binaryFormat ? { format: binaryFormat } : {});
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  const pngSignature = [137, 80, 78, 71, 13, 10, 26, 10];

  if (bytes.length < 24 || pngSignature.some((value, index) => bytes[index] !== value)) {
    throw new Error("Wyeksportowany plik nie wyglada jak poprawny PNG.");
  }

  return {
    width: readPngUint32(bytes, 16),
    height: readPngUint32(bytes, 20)
  };
}

function createVariantSeeds(count) {
  const normalizedCount = Math.max(1, Math.min(2, Math.round(count || 1)));
  const baseSeed = Date.now() % 1000000000;
  return Array.from({ length: normalizedCount }, (_, index) => baseSeed + index * 1009);
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

function calculateGenerationBounds(cropBounds, docWidth, docHeight, multiple = GENERATION_SIZE_MULTIPLE) {
  if (panelHelpers.calculateGenerationBounds) {
    return panelHelpers.calculateGenerationBounds(cropBounds, docWidth, docHeight, multiple);
  }

  const targetWidth = Math.min(docWidth, Math.ceil(cropBounds.width / multiple) * multiple);
  const targetHeight = Math.min(docHeight, Math.ceil(cropBounds.height / multiple) * multiple);
  const left = Math.min(cropBounds.left, Math.max(0, docWidth - targetWidth));
  const top = Math.min(cropBounds.top, Math.max(0, docHeight - targetHeight));

  return {
    left,
    top,
    right: left + targetWidth,
    bottom: top + targetHeight,
    width: targetWidth,
    height: targetHeight,
    multiple
  };
}

function buildInpaintingJob(
  document,
  prompt,
  assets,
  cropBounds,
  qualitySettings,
  maskMetadata,
  variantSeeds,
  loraConfig,
  geometry = {}
) {
  const size = readDocumentSize(document);
  const selection = getSelectionInfo(document);
  const loraItems = (loraConfig?.loras) || [];
  const quality = getQualityPresetForSettings(qualitySettings);
  const finalPrompt = panelHelpers.buildFinalPrompt
    ? panelHelpers.buildFinalPrompt(qualitySettings, prompt)
    : prompt;
  const visibilityMask = maskMetadata?.visibility || {};
  const generationMask = maskMetadata?.generation || {};
  const primaryMaskAnalysis = generationMask.analysis || visibilityMask.analysis || maskMetadata?.analysis || { warnings: [] };
  const maskWarnings = Array.from(new Set([
    ...(generationMask.analysis?.warnings || []),
    ...(visibilityMask.analysis?.warnings || []),
    ...(primaryMaskAnalysis.warnings || [])
  ]));

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
    selectionBounds: selection.bounds,
    paddedBounds: geometry.paddedBounds || cropBounds,
    generationBounds: geometry.generationBounds || cropBounds,
    cropBounds,
    assets,
    generation: {
      tool: "inpainting-brush",
      prompt,
      finalPrompt,
      negativePrompt: qualitySettings.negativePrompt,
      baseModelKind: "gguf",
      quality,
      editMode: qualitySettings.editMode || "edit",
      editModePlan: panelHelpers.resolveEditModePlan
        ? panelHelpers.resolveEditModePlan(qualitySettings.editMode)
        : { editMode: "edit", extraGrowPx: 0, backgroundPreserveThreshold: 0.1 },
      mask: {
        mode: "dual-mask",
        featherPx: visibilityMask.options?.featherPx ?? qualitySettings.maskFeatherPx,
        growPx: visibilityMask.options?.growPx ?? qualitySettings.maskGrowPx,
        visibility: {
          role: "photoshop-layer-mask",
          mode: visibilityMask.mode || "photoshop-selection-pixels-soft",
          featherPx: visibilityMask.options?.featherPx ?? qualitySettings.maskFeatherPx,
          growPx: visibilityMask.options?.growPx ?? qualitySettings.maskGrowPx,
          analysis: visibilityMask.analysis || null
        },
        generation: {
          role: "comfy-denoise-mask",
          mode: generationMask.mode || "processed-crop-selection-mask",
          featherPx: generationMask.options?.featherPx ?? qualitySettings.maskFeatherPx,
          growPx: generationMask.options?.growPx ?? qualitySettings.maskGrowPx,
          haloPx: generationMask.options?.haloPx ?? 0,
          analysis: generationMask.analysis || null
        },
        analysis: primaryMaskAnalysis,
        warnings: maskWarnings
      },
      variants: variantSeeds.map((seed, index) => ({
        index: index + 1,
        seed
      })),
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

  const text = await entry.read({
    format: uxp.storage.formats.utf8
  });
  return String(text).replace(/^\uFEFF/, "");
}

async function getOptionalPluginTextFile(relativePath) {
  try {
    return await getPluginTextFile(relativePath);
  } catch {
    return null;
  }
}

async function getPluginEntry(relativePath) {
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

  return entry;
}

async function removeOptionalPluginFile(relativePath) {
  const uxp = getUxpApi();

  if (!uxp) {
    return false;
  }

  try {
    const pluginFolder = await uxp.storage.localFileSystem.getPluginFolder();
    const parts = relativePath.split("/");
    const fileName = parts.pop();
    let entry = pluginFolder;

    for (const part of parts) {
      entry = await entry.getEntry(part);
    }

    const file = await entry.getEntry(fileName);
    await file.delete();
    return true;
  } catch {
    return false;
  }
}

// Best-effort outward ICC guard. The FLUX model and RasterRelay colour nodes
// assume sRGB, but Photoshop Beta can reject the Convert-to-Profile action for
// the temporary export document with a blocking modal. Therefore export-side
// conversion is intentionally disabled here rather than breaking generation. The
// load-bearing inward fix is in RasterRelaySaveImage: every result PNG is tagged
// with an sRGB iCCP profile, and placeImageFileAsLayer records/fallbacks the
// document profile on placement.
async function convertExportDocumentToSrgb(_photoshop) {
  // Photoshop Beta can report "Convert to Profile is not currently available"
  // as a blocking modal from batchPlay, even when the promise is caught. Do not
  // block generation for this best-effort guard. The inward path is now closed at
  // the source: RasterRelaySaveImage embeds an sRGB iCCP tag in every result PNG,
  // and placeImageFileAsLayer logs/fallbacks wide-gamut placement.
  console.warn("[RasterRelay] Pomijam konwersję eksportowej kopii do sRGB: Photoshop zgłasza tę komendę jako niedostępną w części konfiguracji.");
  return false;
}

async function exportCroppedSourcePng(document, dataFolder, filePrefix, paddedBounds) {
  const photoshop = getPhotoshopApi();
  if (!photoshop) {
    throw new Error("Photoshop API is unavailable.");
  }

  const file = await dataFolder.createFile(`${filePrefix}-source.png`, {
    overwrite: true
  });

  await photoshop.core.executeAsModal(
    async () => {
      let exportDocument = null;

      try {
        // Export from a temporary merged duplicate so the user's document, layers
        // and selection are not modified while we crop the source image.
        exportDocument = await document.duplicate(`RasterRelay export ${filePrefix}`, true);
        await clearActiveSelection(photoshop);
        await exportDocument.crop({
          left: Math.round(paddedBounds.left),
          top: Math.round(paddedBounds.top),
          right: Math.round(paddedBounds.right),
          bottom: Math.round(paddedBounds.bottom)
        });
        // Pin the exported source to sRGB so ComfyUI never misreads a wide-gamut
        // working space as sRGB (a profile mismatch produces tonal drift that
        // looks identical to a VAE seam). Runs on the export copy only.
        await convertExportDocumentToSrgb(photoshop);
        await exportDocument.saveAs.png(file, { compression: 6 }, true);
      } finally {
        if (exportDocument) {
          try {
            exportDocument.closeWithoutSaving();
          } catch {
            // The export document is temporary; failure to close should not hide
            // the original export error.
          }
        }
      }
    },
    { commandName: "RasterRelay Export Cropped Source PNG" }
  );

  const exportedSize = await readPngDimensions(file);
  if (exportedSize.width !== paddedBounds.width || exportedSize.height !== paddedBounds.height) {
    throw new Error(
      `Eksport z Photoshopa ma zły rozmiar: ${exportedSize.width} x ${exportedSize.height}, a powinien mieć ${paddedBounds.width} x ${paddedBounds.height}.`
    );
  }

  return {
    asset: {
      kind: "sourceImage",
      format: "png",
      path: file.nativePath || file.name,
      width: exportedSize.width,
      height: exportedSize.height,
      croppedBounds: paddedBounds
    },
    file
  };
}

async function captureGenerationMaskData(document, paddedBounds, qualitySettings) {
  const photoshop = getPhotoshopApi();
  if (!photoshop?.imaging) {
    throw new Error("Photoshop Imaging API is not available. Update Photoshop or check UXP permissions in manifest.");
  }

  const selection = getSelectionInfo(document);
  if (!selection.hasSelection) {
    throw new Error("No selection found.");
  }

  return await photoshop.core.executeAsModal(async () => {
    const selectionImage = await photoshop.imaging.getSelection({
      documentID: document.id,
      sourceBounds: selection.bounds
    });

    try {
      const size = getImageDataSize(selectionImage);
      const pixelData = await selectionImage.imageData.getData();
      const components = Math.max(1, Math.round(pixelData.length / (size.width * size.height)));
      const cropMaskValues = new Uint8Array(paddedBounds.width * paddedBounds.height);

      const selLeft = Math.round(selectionImage.sourceBounds?.left ?? selection.bounds.left);
      const selTop = Math.round(selectionImage.sourceBounds?.top ?? selection.bounds.top);

      for (let y = 0; y < size.height; y += 1) {
        for (let x = 0; x < size.width; x += 1) {
          const targetX = selLeft + x - paddedBounds.left;
          const targetY = selTop + y - paddedBounds.top;

          if (targetX < 0 || targetY < 0 || targetX >= paddedBounds.width || targetY >= paddedBounds.height) {
            continue;
          }

          cropMaskValues[targetY * paddedBounds.width + targetX] = readMaskPixelValue(
            pixelData,
            y * size.width + x,
            components
          );
        }
      }

      const processedMask = processMaskChannel(
        cropMaskValues,
        paddedBounds.width,
        paddedBounds.height,
        qualitySettings,
        "generation"
      );

      return {
        role: "generationMask",
        pixels: processedMask.values,
        selWidth: paddedBounds.width,
        selHeight: paddedBounds.height,
        selLeft: 0,
        selTop: 0,
        fullWidth: paddedBounds.width,
        fullHeight: paddedBounds.height,
        feather: 0,
        featherRadius: processedMask.options.featherPx,
        growPx: processedMask.options.growPx,
        haloPx: processedMask.options.haloPx,
        options: processedMask.options,
        analysis: processedMask.analysis,
        mode: "processed-crop-selection-mask"
      };
    } finally {
      selectionImage.imageData?.dispose?.();
    }
  }, { commandName: "RasterRelay Capture Selection" });
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
  const vertical = panelHelpers.softenGrayscaleMask
    ? panelHelpers.softenGrayscaleMask(original, mask.width, mask.height, radius)
    : blurMaskVertical(blurMaskHorizontal(original, mask.width, mask.height, radius), mask.width, mask.height, radius);
  writeMaskChannel(mask, vertical);
  return radius;
}

function getMaskOptions(settings, width, height, role = "visibility") {
  if (role === "generation" && panelHelpers.getGenerationMaskOptions) {
    return panelHelpers.getGenerationMaskOptions(settings);
  }
  if (role === "visibility" && panelHelpers.getVisibilityMaskOptions) {
    return panelHelpers.getVisibilityMaskOptions(settings);
  }

  const normalized = panelHelpers.normalizeQualitySettings
    ? panelHelpers.normalizeQualitySettings(settings)
    : defaultQualitySettings;
  const fallbackFeather = getDefaultMaskFeatherRadius(width, height);
  if (role === "generation") {
    const haloPx = {
      fast: 8,
      balanced: 16,
      quality: 24
    }[normalized.quality] || 16;
    return {
      role: "generation",
      featherPx: Math.min(96, Math.max(Math.round(normalized.maskFeatherPx), haloPx)),
      growPx: Math.min(96, Math.max(0, Math.round(normalized.maskGrowPx)) + haloPx),
      haloPx
    };
  }

  return {
    role: "visibility",
    featherPx: Number.isFinite(Number(normalized.maskFeatherPx))
      ? Math.max(0, Math.round(normalized.maskFeatherPx))
      : fallbackFeather,
    growPx: Number.isFinite(Number(normalized.maskGrowPx))
      ? Math.min(0, Math.round(normalized.maskGrowPx))
      : 0,
    haloPx: 0
  };
}

function processMaskChannel(values, width, height, settings, role = "visibility") {
  const options = getMaskOptions(settings, width, height, role);
  const grown = panelHelpers.growOrContractMask
    ? panelHelpers.growOrContractMask(values, width, height, options.growPx)
    : new Uint8Array(values);
  const softened = panelHelpers.softenGrayscaleMask
    ? panelHelpers.softenGrayscaleMask(grown, width, height, options.featherPx)
    : blurMaskVertical(
        blurMaskHorizontal(grown, width, height, options.featherPx),
        width,
        height,
        options.featherPx
      );

  return {
    values: softened,
    role,
    options,
    analysis: panelHelpers.analyzeMask
      ? panelHelpers.analyzeMask(softened, width, height)
      : {
          warnings: []
        }
  };
}

async function captureSoftFullDocumentMaskPixels(photoshop, document, qualitySettings) {
  if (!photoshop?.imaging?.getSelection) {
    return null;
  }

  const selection = getSelectionInfo(document);
  if (!selection.hasSelection) {
    return null;
  }

  return await photoshop.core.executeAsModal(
    async () => {
      const docSize = readDocumentSize(document);
      const docWidth = Math.round(docSize.width);
      const docHeight = Math.round(docSize.height);
      const selectionImage = await photoshop.imaging.getSelection({
        documentID: document.id,
        sourceBounds: selection.bounds
      });

      try {
        const selSize = getImageDataSize(selectionImage);
        const selectionPixels = await selectionImage.imageData.getData();
        const components = Math.max(1, Math.round(selectionPixels.length / (selSize.width * selSize.height)));
        const fullMaskPixels = new Uint8Array(docWidth * docHeight);
        const selLeft = Math.round(selectionImage.sourceBounds?.left ?? selection.bounds.left);
        const selTop = Math.round(selectionImage.sourceBounds?.top ?? selection.bounds.top);

        for (let y = 0; y < selSize.height; y += 1) {
          for (let x = 0; x < selSize.width; x += 1) {
            const targetX = selLeft + x;
            const targetY = selTop + y;

            if (targetX < 0 || targetY < 0 || targetX >= docWidth || targetY >= docHeight) {
              continue;
            }

            fullMaskPixels[targetY * docWidth + targetX] = readMaskPixelValue(
              selectionPixels,
              y * selSize.width + x,
              components
            );
          }
        }

        const processedMask = processMaskChannel(fullMaskPixels, docWidth, docHeight, qualitySettings, "visibility");

        return {
          role: "visibilityMask",
          width: docWidth,
          height: docHeight,
          pixels: processedMask.values,
        featherRadius: processedMask.options.featherPx,
          growPx: processedMask.options.growPx,
          haloPx: processedMask.options.haloPx,
          options: processedMask.options,
          analysis: processedMask.analysis,
          sourceBounds: selectionImage.sourceBounds || selection.bounds,
          mode: "photoshop-selection-pixels-soft"
        };
      } finally {
        selectionImage.imageData?.dispose?.();
      }
    },
    { commandName: "RasterRelay Capture Soft Layer Mask" }
  );
}

function summarizeMaskData(maskData) {
  if (!maskData) {
    return null;
  }

  return {
    role: maskData.role,
    mode: maskData.mode,
    width: maskData.width || maskData.fullWidth || maskData.selWidth,
    height: maskData.height || maskData.fullHeight || maskData.selHeight,
    selWidth: maskData.selWidth,
    selHeight: maskData.selHeight,
    featherRadius: maskData.featherRadius,
    growPx: maskData.growPx,
    haloPx: maskData.haloPx,
    options: maskData.options,
    analysis: maskData.analysis,
    sourceBounds: maskData.sourceBounds
  };
}

async function exportInpaintingAssets(document, dataFolder, qualitySettings) {
  const filePrefix = `rasterrelay-${createSafeTimestamp()}`;
  const size = readDocumentSize(document);
  const selection = getSelectionInfo(document);
  const photoshop = getPhotoshopApi();

  const paddedBounds = calculatePaddedBounds(
    selection.bounds,
    Math.round(size.width),
    Math.round(size.height),
    SELECTION_PADDING_PX
  );
  const generationBounds = calculateGenerationBounds(
    paddedBounds,
    Math.round(size.width),
    Math.round(size.height),
    GENERATION_SIZE_MULTIPLE
  );

  const layerMaskData = await captureSoftFullDocumentMaskPixels(photoshop, document, qualitySettings);
  const generationMaskData = await captureGenerationMaskData(document, generationBounds, qualitySettings);
  const sourceImageExport = await exportCroppedSourcePng(document, dataFolder, filePrefix, generationBounds);

  return {
    assets: {
      sourceImage: sourceImageExport.asset,
      generationMask: summarizeMaskData(generationMaskData),
      visibilityMask: summarizeMaskData(layerMaskData),
      maskData: generationMaskData
    },
    files: {
      sourceImage: sourceImageExport.file
    },
    paddedBounds,
    generationBounds,
    cropBounds: generationBounds,
    layerMaskData,
    maskMetadata: {
      generation: generationMaskData,
      visibility: layerMaskData,
      analysis: generationMaskData.analysis || layerMaskData?.analysis || { warnings: [] }
    },
    maskAnalysis: generationMaskData.analysis || layerMaskData?.analysis || { warnings: [] }
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

  const result = await response.json().catch(() => ({}));

  return {
    role,
    name: result.name || file.name,
    subfolder: result.subfolder || "",
    type: result.type || "input"
  };
}

function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

async function uploadMaskViaEndpoint(maskData) {
  if (!maskData || maskData.fallback) {
    return null;
  }

  const pixelsB64 = arrayBufferToBase64(maskData.pixels.buffer);
  const body = JSON.stringify({
    pixels: pixelsB64,
    sel_width: maskData.selWidth,
    sel_height: maskData.selHeight,
    full_width: maskData.fullWidth,
    full_height: maskData.fullHeight,
    sel_left: maskData.selLeft,
    sel_top: maskData.selTop,
    feather: maskData.feather
  });

  const response = await fetch(`${COMFYUI_BASE_URL}/rasterrelay/upload-selection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(`Mask upload failed: ${errorData.error || `HTTP ${response.status}`}`);
  }

  return response.json();
}

async function uploadAssetsToComfy(files, maskData) {
  const sourceImage = await uploadComfyImage(files.sourceImage, "sourceImage");

  try {
    const maskResult = await uploadMaskViaEndpoint(maskData);
    const generationMaskUpload = {
      role: "generationMask",
      name: maskResult.name,
      subfolder: maskResult.subfolder || "",
      type: maskResult.type || "input"
    };
    return {
      sourceImage,
      generationMask: generationMaskUpload,
      selectionMask: generationMaskUpload
    };
  } catch (error) {
    throw new Error(`Could not upload mask to ComfyUI: ${error?.message || error}. Make sure ComfyUI is running and the rasterrelay_nodes package is installed.`);
  }
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

function getWorkflowClassTypes(workflow) {
  return [...new Set(Object.values(workflow).map((node) => node.class_type).filter(Boolean))];
}

function findMissingWorkflowClasses(workflow, objectInfo) {
  return getWorkflowClassTypes(workflow).filter((classType) => !objectInfo[classType]);
}

function getComfyNodeInputNames(nodeInfo) {
  const input = nodeInfo?.input || {};
  return new Set([
    ...Object.keys(input.required || {}),
    ...Object.keys(input.optional || {}),
    ...Object.keys(input.hidden || {})
  ]);
}

function findUnsupportedWorkflowInputs(workflow, objectInfo) {
  const unsupported = [];

  for (const [nodeId, node] of Object.entries(workflow)) {
    const classType = node?.class_type;
    const inputNames = getComfyNodeInputNames(objectInfo?.[classType]);

    if (!classType || !classType.startsWith("RasterRelay") || inputNames.size === 0 || !node.inputs) {
      continue;
    }

    for (const inputName of Object.keys(node.inputs)) {
      if (!inputNames.has(inputName)) {
        unsupported.push(`${nodeId}:${classType}.${inputName}`);
      }
    }
  }

  return unsupported;
}

function isMappingInputReady(input) {
  if (Array.isArray(input)) {
    return input.length > 0 && input.every(isMappingInputReady);
  }

  return Boolean(input?.nodeId && input?.inputName);
}

function validateWorkflowMapping(mapping) {
  const requiredInputs = [
    "sourceImage",
    "selectionMask",
    "prompt",
    "negativePrompt",
    "steps",
    "cfg",
    "seed",
    "seedRandomize",
    "lorasJson",
    "width",
    "height",
    "cropLeft",
    "cropTop",
    "cropWidth",
    "cropHeight",
    "docWidth",
    "docHeight"
  ];
  const missingInputs = requiredInputs.filter((id) => {
    const input = mapping.inputs?.[id];
    return !isMappingInputReady(input);
  });

  if (missingInputs.length) {
    throw new Error(`Mapping workflow nie ma wymaganych wejść: ${missingInputs.join(", ")}.`);
  }
}

function setWorkflowInput(workflow, mappingItem, value) {
  if (panelHelpers.setWorkflowInput) {
    panelHelpers.setWorkflowInput(workflow, mappingItem, value);
    return;
  }

  if (!mappingItem) {
    return;
  }

  if (Array.isArray(mappingItem)) {
    mappingItem.forEach((item) => setWorkflowInput(workflow, item, value));
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
  return false;
}

function applyWorkflowInputs(workflow, mapping, job, comfyUploads) {
  setWorkflowInput(workflow, mapping.inputs.sourceImage, comfyUploads.sourceImage.name);
  setWorkflowInput(workflow, mapping.inputs.selectionMask, comfyUploads.selectionMask.name);
  setWorkflowInput(workflow, mapping.inputs.prompt, job.generation.finalPrompt || job.generation.prompt);
  setWorkflowInput(workflow, mapping.inputs.negativePrompt, job.generation.negativePrompt || "");
  setWorkflowInput(workflow, mapping.inputs.steps, job.generation.quality?.steps);
  setWorkflowInput(workflow, mapping.inputs.cfg, job.generation.quality?.cfg);

  // Quality preset -> refine pass on/off. Switch SeamlessTone's source between
  // the refined branch (node 89) and the base result (node 93); ComfyUI prunes
  // the refine branch when unused, so Fast/Balanced run noticeably faster.
  if (mapping.inputs.refineSource) {
    const refineNodeId = job.generation.quality?.refineSourceNodeId || "93";
    setWorkflowInput(workflow, mapping.inputs.refineSource, [refineNodeId, 0]);
  }

  // Removal mode trusts the generated background more so BackgroundPreserve
  // doesn't restore the object when the new fill resembles the surroundings.
  if (mapping.inputs.backgroundPreserveThreshold && job.generation.editModePlan) {
    setWorkflowInput(
      workflow,
      mapping.inputs.backgroundPreserveThreshold,
      job.generation.editModePlan.backgroundPreserveThreshold
    );
  }
  setWorkflowInput(workflow, mapping.inputs.seed, job.generation.activeSeed);
  setWorkflowInput(workflow, mapping.inputs.seedRandomize, "disable");

  if (job.cropBounds) {
    setWorkflowInput(workflow, mapping.inputs.cropLeft, Math.round(job.cropBounds.left));
    setWorkflowInput(workflow, mapping.inputs.cropTop, Math.round(job.cropBounds.top));
    setWorkflowInput(workflow, mapping.inputs.cropWidth, Math.round(job.cropBounds.width));
    setWorkflowInput(workflow, mapping.inputs.cropHeight, Math.round(job.cropBounds.height));
  }
  if (job.document?.width && job.document?.height) {
    setWorkflowInput(workflow, mapping.inputs.docWidth, Math.round(job.document.width));
    setWorkflowInput(workflow, mapping.inputs.docHeight, Math.round(job.document.height));
  }

  const genWidth = job.cropBounds?.width || job.document?.width;
  const genHeight = job.cropBounds?.height || job.document?.height;
  if (genWidth && genHeight) {
    // Phase D crop-engine: generate at the model's optimal resolution
    // (small crops upscaled = sharper detail, huge crops downscaled);
    // the workflow scales the result back to the native crop size.
    const optimal = panelHelpers.computeOptimalGenSize
      ? panelHelpers.computeOptimalGenSize(genWidth, genHeight)
      : { genWidth: Math.round(genWidth), genHeight: Math.round(genHeight) };
    setWorkflowInput(workflow, mapping.inputs.width, optimal.genWidth);
    setWorkflowInput(workflow, mapping.inputs.height, optimal.genHeight);

    // SeamlessTone: scale the tone-diffusion radius to the crop so colour/
    // brightness matching works on small and very large crops alike
    // (~1/8 of the smaller crop dimension ≈ 1/4 of the selection radius).
    const toneRadius = Math.max(16, Math.min(200, Math.round(Math.min(genWidth, genHeight) / 8)));
    setWorkflowInput(workflow, mapping.inputs.toneRadius, toneRadius);
    setWorkflowInput(workflow, mapping.inputs.toneStrength, 1.0);

    // 2nd pass: large-radius chroma-only colour-cast correction (~crop/3)
    const chromaRadius = Math.max(32, Math.min(320, Math.round(Math.min(genWidth, genHeight) / 3)));
    setWorkflowInput(workflow, mapping.inputs.chromaRadius, chromaRadius);
  }

  applyLoraWorkflowInputs(workflow, mapping, job.generation.lora.items);
}

function applyLoraWorkflowInputs(workflow, mapping, loraItems) {
  if (!mapping.inputs.lorasJson) {
    return;
  }

  const lorasJson = JSON.stringify(
    loraItems.map((lora) => ({
      name: lora.name,
      strength_model: lora.strengthModel,
      strength_clip: lora.strengthClip
    }))
  );

  setWorkflowInput(workflow, mapping.inputs.lorasJson, lorasJson);
}

async function queueComfyWorkflow(job, comfyUploads) {
  const { workflow, mapping } = await loadWorkflowBundle();
  applyWorkflowInputs(workflow, mapping, job, comfyUploads);
  const objectInfo = await getComfyObjectInfo();
  const unsupportedInputs = findUnsupportedWorkflowInputs(workflow, objectInfo);
  if (unsupportedInputs.length) {
    throw new Error(
      `ComfyUI ma nieaktualne albo niezgodne custom nodes. Brakuje wejsc workflow: ${unsupportedInputs.join(", ")}. Zatrzymaj ComfyUI, uruchom w katalogu projektu: ${INSTALL_NODES_COMMAND}, potem zrestartuj ComfyUI.`
    );
  }

  const response = await fetch(`${COMFYUI_BASE_URL}/prompt`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      client_id: COMFY_CLIENT_ID,
      prompt: workflow
    })
  });

  const result = await response.json().catch(() => ({}));

  if (!response.ok || result.error) {
    throw new Error(`ComfyUI odrzucilo workflow: ${formatComfyError(result.error) || `HTTP ${response.status}`}`);
  }

  return {
    promptId: result.prompt_id,
    number: result.number,
    nodeErrors: result.node_errors || null
  };
}

function formatComfyError(error) {
  if (!error) {
    return "";
  }

  if (typeof error === "string") {
    return error;
  }

  if (error.message) {
    return error.message;
  }

  if (error.details) {
    return String(error.details);
  }

  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function summarizeComfyHistoryFailure(entry) {
  const status = entry?.status || {};
  const messages = Array.isArray(status.messages) ? status.messages : [];
  const errorMessages = messages
    .map((message) => {
      if (Array.isArray(message)) {
        const payload = message[1] || {};
        return payload.exception_message || payload.message || payload.node_type || message[0];
      }

      if (message && typeof message === "object") {
        return message.exception_message || message.message || message.node_type;
      }

      return message;
    })
    .filter(Boolean);

  return errorMessages.join(" | ") || status.status_str || "ComfyUI zakonczyl workflow bledem.";
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
  const closeProgress = subscribeComfyProgress(promptId, (update) => {
    setProgress(update.fraction, update.label);
  });
  setProgress(undefined, "Wysłano do ComfyUI…");

  try {
    while (Date.now() - startedAt < COMFY_HISTORY_TIMEOUT_MS) {
      const history = await getComfyHistory(promptId);
      const entry = history[promptId];
      const outputImage = findFirstOutputImage(entry);

      if (outputImage) {
        setProgress(1, "Gotowe — pobieram wynik…");
        return {
          history: entry,
          image: outputImage
        };
      }

      const status = entry?.status?.status_str;
      if (status === "error" || status === "failed") {
        throw new Error(`ComfyUI zakonczyl workflow bledem: ${summarizeComfyHistoryFailure(entry)}`);
      }

      await wait(COMFY_HISTORY_POLL_MS);
    }

    throw new Error("ComfyUI nie zwróciło obrazu w wyznaczonym czasie.");
  } finally {
    closeProgress();
  }
}

async function downloadComfyImage(image, dataFolder) {
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
      width: image.width || null,
      height: image.height || null,
      alphaBBox: image.alpha_bbox || image.alphaBBox || null,
      comfy: {
        filename: image.filename,
        subfolder: image.subfolder || "",
        type: image.type || "output",
        absolutePath,
        width: image.width || null,
        height: image.height || null,
        alphaBBox: image.alpha_bbox || image.alphaBBox || null
      }
    }
  };
}

function readBoundsObject(bounds) {
  if (!bounds) {
    return null;
  }

  const left = readUnitValue(bounds.left);
  const top = readUnitValue(bounds.top);
  const right = readUnitValue(bounds.right);
  const bottom = readUnitValue(bounds.bottom);

  if (![left, top, right, bottom].every(Number.isFinite)) {
    return null;
  }

  return {
    left,
    top,
    right,
    bottom,
    width: right - left,
    height: bottom - top
  };
}

function createExpectedPlacementGeometry(document, fileSize, outputMetadata = {}) {
  const docSize = readDocumentSize(document);
  const alphaBBox = outputMetadata.alphaBBox || outputMetadata.alpha_bbox || null;
  const fallbackBounds = {
    left: 0,
    top: 0,
    right: Math.round(docSize.width),
    bottom: Math.round(docSize.height),
    width: Math.round(docSize.width),
    height: Math.round(docSize.height)
  };
  return {
    document: {
      width: Math.round(docSize.width),
      height: Math.round(docSize.height)
    },
    png: {
      width: fileSize?.width || outputMetadata.width || null,
      height: fileSize?.height || outputMetadata.height || null
    },
    alphaBBox,
    expectedBounds: alphaBBox || fallbackBounds,
    actualBounds: null,
    actualMatchesExpected: null,
    matchesDocumentSize:
      Math.round(fileSize?.width || 0) === Math.round(docSize.width) &&
      Math.round(fileSize?.height || 0) === Math.round(docSize.height)
  };
}

function boundsMatch(expected, actual, tolerance = 1) {
  if (!expected || !actual) {
    return null;
  }

  return ["left", "top", "right", "bottom"].every((key) => {
    return Math.abs(Math.round(expected[key]) - Math.round(actual[key])) <= tolerance;
  });
}

function boundsSizeMatches(expected, actual, tolerance = 2) {
  if (!expected || !actual) {
    return null;
  }

  return ["width", "height"].every((key) => {
    return Math.abs(Math.round(expected[key]) - Math.round(actual[key])) <= tolerance;
  });
}

async function alignLayerToExpectedBounds(activeLayer, placementGeometry) {
  const expected = placementGeometry?.expectedBounds;
  let actual = readBoundsObject(activeLayer?.bounds);

  if (!expected || !actual || boundsMatch(expected, actual)) {
    return actual;
  }

  if (boundsSizeMatches(expected, actual) === false) {
    throw new Error(
      `Warstwa wyniku ma rozmiar bounds ${JSON.stringify(actual)}, a oczekiwano ${JSON.stringify(expected)}. Photoshop prawdopodobnie przeskalowal wstawiany PNG.`
    );
  }

  const dx = Math.round(expected.left - actual.left);
  const dy = Math.round(expected.top - actual.top);
  if (dx !== 0 || dy !== 0) {
    await activeLayer.translate(dx, dy);
  }

  actual = readBoundsObject(activeLayer.bounds);
  if (boundsMatch(expected, actual) === false) {
    throw new Error(
      `Nie udało się dopasować pozycji warstwy wyniku. Po przesunięciu bounds=${JSON.stringify(actual)}, oczekiwano=${JSON.stringify(expected)}.`
    );
  }

  return actual;
}

// Read the active document's ICC colour profile name (e.g. "sRGB IEC61966-2.1",
// "Adobe RGB (1998)", "ProPhoto RGB"). Returns null if it cannot be read.
async function getActiveDocumentColorProfile(photoshop) {
  try {
    const [desc] = await photoshop.action.batchPlay(
      [
        {
          _obj: "get",
          _target: [
            { _property: "profile" },
            { _ref: "document", _enum: "ordinal", _value: "targetEnum" }
          ]
        }
      ],
      { synchronousExecution: true }
    );
    return desc?.profile ?? null;
  } catch (error) {
    console.warn(`[RasterRelay] Nie udało się odczytać profilu koloru dokumentu: ${error}`);
    return null;
  }
}

function isSrgbProfileName(name) {
  return typeof name === "string" && /srgb/i.test(name);
}

// ICC inward direction (belt-and-suspenders). The result PNG is already tagged
// sRGB at the source (RasterRelaySaveImage embeds an iCCP chunk), so Photoshop
// converts it into the document space on placement. This is a fallback for the
// case where that tag is missing/stripped AND the document is wide-gamut: we
// reinterpret the placed smart object's contents as sRGB so Photoshop converts
// them to the document profile instead of assigning the document profile to
// untagged RGB (which would drift tone exactly like a seam). Fully contained:
// it never throws and always restores the original document as active. The sRGB
// path is an explicit no-op so the common case is never touched.
async function ensurePlacedResultColorSpace(photoshop, placement) {
  let documentProfile = null;
  let action = "none";
  let detail = null;

  await photoshop.core.executeAsModal(
    async () => {
      documentProfile = await getActiveDocumentColorProfile(photoshop);
      placement.documentColorProfile = documentProfile;

      if (documentProfile == null) {
        action = "unknown-profile-noop";
        return;
      }
      if (isSrgbProfileName(documentProfile)) {
        action = "srgb-noop";
        return;
      }

      const originalDocId = photoshop.app.activeDocument?.id;
      let editingOpened = false;
      try {
        await photoshop.action.batchPlay(
          [{ _obj: "placedLayerEditContents", _options: { dialogOptions: "dontDisplay" } }],
          { synchronousExecution: true }
        );
        editingOpened = true;
        await photoshop.action.batchPlay(
          [
            {
              _obj: "assignProfile",
              to: { _obj: "profile", profile: "sRGB IEC61966-2.1" },
              _options: { dialogOptions: "dontDisplay" }
            }
          ],
          { synchronousExecution: true }
        );
        await photoshop.app.activeDocument.save();
        action = "assigned-srgb-on-smart-object";
      } catch (innerError) {
        action = "fallback-failed-relying-on-embedded-tag";
        detail = String(innerError);
        console.warn(`[RasterRelay] Fallback sRGB na smart obiekcie nie powiódł się; polegam na tagu iCCP z węzła zapisu: ${innerError}`);
      } finally {
        // Always return to the source document so later steps don't act on the
        // smart-object editing tab. The SO change (if any) was already saved.
        try {
          const current = photoshop.app.activeDocument;
          if (editingOpened && current && current.id !== originalDocId) {
            await current.closeWithoutSaving();
          }
        } catch (closeError) {
          console.warn(`[RasterRelay] Nie udało się zamknąć kontekstu edycji smart obiektu: ${closeError}`);
        }
      }
    },
    { commandName: "RasterRelay Ensure Result sRGB" }
  );

  console.log(`[RasterRelay] Profil dokumentu: ${documentProfile ?? "nieznany"}; ICC inward: ${action}`);
  return { documentProfile, action, detail };
}

async function placeImageFileAsLayer(file, layerName = "RasterRelay - wynik", layerMaskData = null, outputMetadata = {}) {
  const photoshop = getPhotoshopApi();
  const uxp = getUxpApi();

  if (!photoshop || !uxp) {
    throw new Error("Photoshop API albo UXP storage jest niedostępne.");
  }

  const token = await uxp.storage.localFileSystem.createSessionToken(file);
  const usePngAlphaOnly = panelHelpers.shouldUsePngAlphaOnly(outputMetadata);
  const placement = {
    layerMode: "placed-embedded",
    layerMask: {
      applied: false,
      source: usePngAlphaOnly ? "png-change-alpha" : "active-selection",
      skipped: usePngAlphaOnly,
      reason: usePngAlphaOnly
        ? "ComfyUI result carries exact change alpha; Photoshop layer mask would reintroduce broad-mask color blending."
        : null
    },
    geometry: null
  };
  const fileSize = await readPngDimensions(file);
  placement.geometry = createExpectedPlacementGeometry(photoshop.app.activeDocument, fileSize, outputMetadata);

  if (!placement.geometry.matchesDocumentSize) {
    throw new Error(
      `Wynik ComfyUI ma rozmiar ${fileSize.width} x ${fileSize.height}, a dokument ma ${placement.geometry.document.width} x ${placement.geometry.document.height}.`
    );
  }

  await photoshop.core.executeAsModal(
    async () => {
      try {
        const capturedMask = usePngAlphaOnly
          ? null
          : layerMaskData
            ? await createCapturedMaskFromPixels(photoshop, layerMaskData)
            : await captureSoftSelectionMaskForLayer(photoshop);

        await photoshop.action.batchPlay(
          [
            {
              _obj: "placeEvent",
              null: {
                _path: token,
                _kind: "local"
              },
              offset: {
                _obj: "offset",
                horizontal: {
                  _unit: "pixelsUnit",
                  _value: 0
                },
                vertical: {
                  _unit: "pixelsUnit",
                  _value: 0
                }
              }
            }
          ],
          {}
        );

        placement.layerId = getActiveLayerId(photoshop);
        const activeLayer = photoshop.app.activeDocument?.activeLayers?.[0];
        if (activeLayer) {
          activeLayer.name = layerName;
          placement.geometry.initialBounds = readBoundsObject(activeLayer.bounds);
          placement.geometry.actualBounds = await alignLayerToExpectedBounds(activeLayer, placement.geometry);
          placement.geometry.actualMatchesExpected = boundsMatch(
            placement.geometry.expectedBounds,
            placement.geometry.actualBounds
          );
          if (placement.geometry.actualMatchesExpected === false) {
            throw new Error(
              `Warstwa wyniku ma bounds ${JSON.stringify(placement.geometry.actualBounds)}, a oczekiwano ${JSON.stringify(placement.geometry.expectedBounds)}.`
            );
          }
        }
        if (usePngAlphaOnly) {
          placement.layerMask = {
            applied: false,
            skipped: true,
            source: "png-change-alpha",
            reason: "ComfyUI result carries exact change alpha; Photoshop layer mask was intentionally skipped."
          };
        } else {
          placement.layerMask = capturedMask?.captured
            ? await applyCapturedMaskToActiveLayer(photoshop, placement.layerId, capturedMask)
            : await applySelectionMaskToActiveLayer(photoshop, placement.layerId);
          if (!placement.layerMask?.applied) {
            throw new Error(`Nie udało się nałożyć maski warstwy wyniku: ${placement.layerMask?.error || placement.layerMask?.fallback || "unknown error"}`);
          }
        }
        await clearActiveSelection(photoshop);
      } catch (error) {
        if (placement.layerId) {
          await deleteLayerById(photoshop, placement.layerId).catch(() => {});
        }
        throw error;
      }
    },
    { commandName: "RasterRelay Place Result Layer" }
  );

  // Close the ICC inward direction: detect the document profile, log it into the
  // placement metadata, and (only for wide-gamut docs) re-assert sRGB on the
  // placed result as a fallback to the embedded iCCP tag.
  placement.colorManagement = await ensurePlacedResultColorSpace(photoshop, placement).catch((error) => ({
    documentProfile: placement.documentColorProfile ?? null,
    action: "error",
    detail: String(error)
  }));

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

  const docSize = readDocumentSize(document);
  const docWidth = Math.round(docSize.width);
  const docHeight = Math.round(docSize.height);

  const selectionImage = await photoshop.imaging.getSelection({
    documentID: document.id,
    sourceBounds: selection.bounds
  });

  try {
    const selSize = getImageDataSize(selectionImage);
    const selectionPixels = await selectionImage.imageData.getData();
    const components = Math.max(1, Math.round(selectionPixels.length / (selSize.width * selSize.height)));

    const fullMaskPixels = new Uint8Array(docWidth * docHeight);
    const selLeft = Math.round(selectionImage.sourceBounds?.left ?? selection.bounds.left);
    const selTop = Math.round(selectionImage.sourceBounds?.top ?? selection.bounds.top);

    for (let y = 0; y < selSize.height; y += 1) {
      for (let x = 0; x < selSize.width; x += 1) {
        const targetX = selLeft + x;
        const targetY = selTop + y;

        if (targetX < 0 || targetY < 0 || targetX >= docWidth || targetY >= docHeight) {
          continue;
        }

        const srcIdx = (y * selSize.width + x) * components;
        let maskValue;

        if (components === 1) {
          maskValue = selectionPixels[srcIdx];
        } else if (components === 4) {
          maskValue = selectionPixels[srcIdx + 3];
        } else {
          maskValue = selectionPixels[srcIdx];
        }

        fullMaskPixels[targetY * docWidth + targetX] = maskValue;
      }
    }

    const featherRadius = getDefaultMaskFeatherRadius(docWidth, docHeight);
    const softenedPixels = panelHelpers.softenGrayscaleMask
      ? panelHelpers.softenGrayscaleMask(fullMaskPixels, docWidth, docHeight, featherRadius)
      : blurMaskVertical(
          blurMaskHorizontal(fullMaskPixels, docWidth, docHeight, featherRadius),
          docWidth,
          docHeight,
          featherRadius
        );

    const imageData = await photoshop.imaging.createImageDataFromBuffer(softenedPixels, {
      width: docWidth,
      height: docHeight,
      components: 1,
      chunky: false,
      colorProfile: "Gray Gamma 2.2",
      colorSpace: "Grayscale"
    });

    return {
      captured: true,
      source: "active-selection-before-place",
      mode: "photoshop-selection-pixels-soft",
      imageData,
      pixels: softenedPixels,
      width: docWidth,
      height: docHeight,
      featherRadius,
      targetBounds: {
        left: 0,
        top: 0
      },
      sourceBounds: selectionImage.sourceBounds || selection.bounds
    };
  } finally {
    selectionImage.imageData?.dispose?.();
  }
}

async function createCapturedMaskFromPixels(photoshop, layerMaskData) {
  if (!photoshop.imaging?.createImageDataFromBuffer || !layerMaskData?.pixels) {
    return {
      captured: false,
      source: "saved-layer-mask-before-generation",
      fallback: "saved-mask-unavailable"
    };
  }

  const imageData = await photoshop.imaging.createImageDataFromBuffer(layerMaskData.pixels, {
    width: layerMaskData.width,
    height: layerMaskData.height,
    components: 1,
    chunky: false,
    colorProfile: "Gray Gamma 2.2",
    colorSpace: "Grayscale"
  });

  return {
    captured: true,
    source: "saved-selection-before-generation",
    mode: layerMaskData.mode || "photoshop-selection-pixels-soft",
    imageData,
    pixels: layerMaskData.pixels,
    width: layerMaskData.width,
    height: layerMaskData.height,
    featherRadius: layerMaskData.featherRadius,
    targetBounds: {
      left: 0,
      top: 0
    },
    sourceBounds: layerMaskData.sourceBounds
  };
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

async function createGrayscaleImageData(photoshop, pixels, width, height) {
  return await photoshop.imaging.createImageDataFromBuffer(new Uint8Array(pixels), {
    width,
    height,
    components: 1,
    chunky: false,
    colorProfile: "Gray Gamma 2.2",
    colorSpace: "Grayscale"
  });
}

async function selectLayerById(photoshop, layerId) {
  await photoshop.action.batchPlay(
    [
      {
        _obj: "select",
        _target: [{ _ref: "layer", _id: layerId }],
        makeVisible: false
      }
    ],
    {}
  );
}

async function deleteLayerById(photoshop, layerId) {
  await photoshop.action.batchPlay(
    [
      {
        _obj: "delete",
        _target: [{ _ref: "layer", _id: layerId }]
      }
    ],
    {}
  );
}

async function deletePlacedLayerAfterFailedAudit(layerId) {
  const photoshop = getPhotoshopApi();

  if (!photoshop?.action?.batchPlay || !layerId) {
    return {
      deleted: false,
      error: "Photoshop layer deletion API is unavailable or layer id is missing."
    };
  }

  try {
    if (photoshop.core?.executeAsModal) {
      await photoshop.core.executeAsModal(
        async () => {
          await deleteLayerById(photoshop, layerId);
        },
        { commandName: "RasterRelay Remove Failed Color Audit Layer" }
      );
    } else {
      await deleteLayerById(photoshop, layerId);
    }

    return { deleted: true };
  } catch (error) {
    return {
      deleted: false,
      error: error.message || String(error)
    };
  }
}

async function makeLayerMaskFromActiveSelection(photoshop, layerId) {
  await selectLayerById(photoshop, layerId);
  await photoshop.action.batchPlay(
    [
      {
        _obj: "make",
        new: { _class: "channel" },
        at: {
          _ref: "channel",
          _enum: "channel",
          _value: "mask"
        },
        using: {
          _enum: "userMaskEnabled",
          _value: "revealSelection"
        }
      }
    ],
    {}
  );
}

async function restoreSelectionFromCapturedMask(photoshop, capturedMask) {
  if (!photoshop.imaging?.putSelection || !capturedMask?.pixels) {
    throw new Error("Photoshop imaging.putSelection is unavailable or captured mask pixels are missing.");
  }

  const imageData = await createGrayscaleImageData(
    photoshop,
    capturedMask.pixels,
    capturedMask.width,
    capturedMask.height
  );

  try {
    await photoshop.imaging.putSelection({
      documentID: photoshop.app.activeDocument.id,
      imageData,
      replace: true,
      targetBounds: capturedMask.targetBounds || { left: 0, top: 0 },
      commandName: "RasterRelay Restore Selection For Layer Mask"
    });
  } finally {
    imageData?.dispose?.();
  }
}

async function verifyLayerMaskExists(photoshop, layerId) {
  if (!photoshop.imaging?.getLayerMask) {
    return true;
  }

  let maskImage = null;
  try {
    maskImage = await photoshop.imaging.getLayerMask({
      documentID: photoshop.app.activeDocument.id,
      layerID: layerId,
      kind: "user",
      sourceBounds: { left: 0, top: 0, right: 1, bottom: 1 }
    });
    return Boolean(maskImage?.imageData);
  } catch {
    return false;
  } finally {
    maskImage?.imageData?.dispose?.();
  }
}

async function applyCapturedMaskToActiveLayer(photoshop, layerId, capturedMask) {
  if (!photoshop.imaging?.putLayerMask || !capturedMask?.imageData) {
    throw new Error("Photoshop imaging.putLayerMask is unavailable or captured mask image data is missing.");
  }

  let primaryError = null;
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

    if (!(await verifyLayerMaskExists(photoshop, layerId))) {
      throw new Error("putLayerMask finished, but no user layer mask could be verified.");
    }

    return {
      applied: true,
      source: capturedMask.source,
      mode: capturedMask.mode,
      featherRadius: capturedMask.featherRadius,
      targetBounds: capturedMask.sourceBounds
    };
  } catch (error) {
    primaryError = error;
    try {
      await restoreSelectionFromCapturedMask(photoshop, capturedMask);
      await makeLayerMaskFromActiveSelection(photoshop, layerId);
      if (!(await verifyLayerMaskExists(photoshop, layerId))) {
        throw new Error("batchPlay fallback finished, but no user layer mask could be verified.");
      }

      return {
        applied: true,
        source: capturedMask.source,
        mode: capturedMask.mode,
        featherRadius: capturedMask.featherRadius,
        targetBounds: capturedMask.sourceBounds,
        fallback: "selection-batchplay-mask",
        primaryError: primaryError.message || String(primaryError)
      };
    } catch (fallbackError) {
      throw new Error(
        `Mask application failed. putLayerMask: ${primaryError?.message || primaryError}. batchPlay fallback: ${fallbackError?.message || fallbackError}`
      );
    }
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
    throw new Error("Photoshop imaging API is unavailable for layer-mask application.");
  }

  const document = photoshop.app.activeDocument;
  const selection = getSelectionInfo(document);
  if (!selection.hasSelection) {
    throw new Error("Active Photoshop selection is missing; cannot create result layer mask.");
  }

  const docSize = readDocumentSize(document);
  const docWidth = Math.round(docSize.width);
  const docHeight = Math.round(docSize.height);

  let selectionImage = null;
  let hardMaskImageData = null;

  try {
    selectionImage = await photoshop.imaging.getSelection({
      documentID: document.id,
      sourceBounds: selection.bounds
    });
    const selSize = getImageDataSize(selectionImage);
    const selectionPixels = await selectionImage.imageData.getData();
    const components = Math.max(1, Math.round(selectionPixels.length / (selSize.width * selSize.height)));

    const fullMaskPixels = new Uint8Array(docWidth * docHeight);
    const selLeft = Math.round(selectionImage.sourceBounds?.left ?? selection.bounds.left);
    const selTop = Math.round(selectionImage.sourceBounds?.top ?? selection.bounds.top);

    for (let y = 0; y < selSize.height; y += 1) {
      for (let x = 0; x < selSize.width; x += 1) {
        const targetX = selLeft + x;
        const targetY = selTop + y;

        if (targetX < 0 || targetY < 0 || targetX >= docWidth || targetY >= docHeight) {
          continue;
        }

        const srcIdx = (y * selSize.width + x) * components;
        let maskValue;

        if (components === 1) {
          maskValue = selectionPixels[srcIdx];
        } else if (components === 4) {
          maskValue = selectionPixels[srcIdx + 3];
        } else {
          maskValue = selectionPixels[srcIdx];
        }

        fullMaskPixels[targetY * docWidth + targetX] = maskValue;
      }
    }

    const featherRadius = getDefaultMaskFeatherRadius(docWidth, docHeight);
    const softenedPixels = panelHelpers.softenGrayscaleMask
      ? panelHelpers.softenGrayscaleMask(fullMaskPixels, docWidth, docHeight, featherRadius)
      : blurMaskVertical(
          blurMaskHorizontal(fullMaskPixels, docWidth, docHeight, featherRadius),
          docWidth,
          docHeight,
          featherRadius
        );

    hardMaskImageData = await photoshop.imaging.createImageDataFromBuffer(softenedPixels, {
      width: docWidth,
      height: docHeight,
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
        left: 0,
        top: 0
      },
      commandName: "RasterRelay Apply Selection Mask"
    });

    if (!(await verifyLayerMaskExists(photoshop, layerId))) {
      throw new Error("putLayerMask finished, but no user layer mask could be verified.");
    }

    return {
      applied: true,
      source: "active-selection",
      mode: "photoshop-selection-pixels-soft",
      featherRadius,
      targetBounds: selectionImage.sourceBounds || selection.bounds
    };
  } catch (error) {
    throw new Error(`Selection layer-mask application failed: ${error.message || String(error)}`);
  } finally {
    hardMaskImageData?.dispose?.();
    selectionImage?.imageData?.dispose?.();
  }
}

async function receiveComfyResult(promptId, dataFolder, cropBounds, layerMaskData = null) {
  const output = await waitForComfyOutput(promptId);
  const downloaded = await downloadComfyImage(output.image, dataFolder);
  const auditContext = await createCompositeAuditContext(downloaded.asset);

  try {
    if (auditContext.required && auditContext.skippedAudit) {
      throw createCompositeAuditError(
        `Nie wstawiam wyniku bez pixel-audytu koloru: ${auditContext.skippedAudit.reason}`,
        auditContext.skippedAudit
      );
    }

    const placement = await placeImageFileAsLayer(downloaded.file, "RasterRelay - wynik", layerMaskData, downloaded.asset);
    let compositeAudit = auditContext.skippedAudit;

    if (auditContext.beforeSnapshot && auditContext.documentSize) {
      try {
        const document = getActiveDocument();
        const afterSnapshot = await getDocumentCompositeSnapshot(document, auditContext.documentSize);
        compositeAudit = auditCompositeColorLock(
          auditContext.beforeSnapshot,
          afterSnapshot,
          downloaded.asset,
          auditContext.documentSize
        );
      } catch (auditError) {
        compositeAudit = createSkippedCompositeAudit(auditError.message || String(auditError));
      }
    }

    if (auditContext.required && compositeAudit?.skipped) {
      const deletion = await deletePlacedLayerAfterFailedAudit(placement.layerId);
      compositeAudit.failedLayerCleanup = deletion;
      throw createCompositeAuditError(
        `Nie zostawiam wyniku bez pelnego pixel-audytu koloru: ${compositeAudit.reason}`,
        compositeAudit
      );
    }

    if (compositeAudit?.checked && shouldRejectCompositeAudit(compositeAudit)) {
      const deletion = await deletePlacedLayerAfterFailedAudit(placement.layerId);
      compositeAudit.failedLayerCleanup = deletion;
      throw createCompositeAuditError(
        `RasterRelay pixel audit failed: outsideChanged=${compositeAudit.outsideChangedPixels}, outsideMaxDiff=${compositeAudit.maxDiffOutsideAlphaBBox}, sourceChromaMax=${compositeAudit.sourceChromaMaxErrorInsideChanged}.`,
        compositeAudit
      );
    }

    downloaded.asset.photoshop = {
      placedAsLayer: true,
      layerMode: placement.layerMode,
      layerId: placement.layerId,
      layerMask: placement.layerMask,
      placementGeometry: placement.geometry,
      documentColorProfile: placement.documentColorProfile ?? null,
      colorManagement: placement.colorManagement ?? null,
      compositeAudit
    };
    downloaded.asset.placementGeometry = placement.geometry;
  } catch (error) {
    downloaded.asset.photoshop = {
      placedAsLayer: false,
      fallback: "downloaded-only",
      error: error.message || String(error),
      compositeAudit:
        error.compositeAudit ||
        auditContext.skippedAudit ||
        createSkippedCompositeAudit("Result was not placed as a Photoshop layer.")
    };
  }

  return downloaded.asset;
}

function describeCompositeAuditForStatus(audit) {
  if (!audit) {
    return "";
  }

  if (audit.checked) {
    return audit.passed
      ? ` Pixel audit OK: outsideChanged=${audit.outsideChangedPixels}, sourceHueMax=${audit.sourceHueMaxErrorInsideChanged ?? "n/a"}, sourceSatMax=${audit.sourceSaturationMaxErrorInsideChanged ?? "n/a"}.`
      : ` Pixel audit FAILED: outsideChanged=${audit.outsideChangedPixels}, outsideMaxDiff=${audit.maxDiffOutsideAlphaBBox}, sourceChromaMax=${audit.sourceChromaMaxErrorInsideChanged}, sourceHueMax=${audit.sourceHueMaxErrorInsideChanged ?? "n/a"}, sourceSatMax=${audit.sourceSaturationMaxErrorInsideChanged ?? "n/a"}.`;
  }

  if (audit.skipped) {
    return ` Pixel audit skipped: ${audit.reason}`;
  }

  return "";
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
  const qualitySettings = await loadQualitySettings();
  qualitySettings.editMode = getEditMode(); // runtime override from the panel
  const loraConfig = await loadLoraConfig();
  const variantSeeds = createVariantSeeds(qualitySettings.variantCount);
  const exported = await exportInpaintingAssets(document, dataFolder, qualitySettings);
  const job = buildInpaintingJob(
    document,
    prompt,
    exported.assets,
    exported.cropBounds,
    qualitySettings,
    exported.maskMetadata,
    variantSeeds,
    loraConfig,
    {
      paddedBounds: exported.paddedBounds,
      generationBounds: exported.generationBounds
    }
  );
  const savedPath = await saveJobPackage(job, dataFolder);
  const warningText = job.generation.mask.warnings.length
    ? ` Ostrzeżenia maski: ${job.generation.mask.warnings.join(" ")}`
    : "";
  setMessage(`Paczka zadania została zapisana: ${savedPath}. Obraz i maska PNG są gotowe.${warningText}`);
  return {
    job,
    files: exported.files,
    layerMaskData: exported.layerMaskData,
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

    const comfyUploads = await uploadAssetsToComfy(packageResult.files, packageResult.job.assets.maskData);
    packageResult.job.comfy = {
      uploaded: true,
      uploads: comfyUploads,
      workflowQueued: false,
      note: "Pliki wejściowe są w ComfyUI. Kolejny krok to podpiąć workflow API JSON i wysłać /prompt."
    };
    await saveJobPackage(packageResult.job, packageResult.dataFolder);

    packageResult.job.comfy.workflowQueued = true;
    packageResult.job.comfy.queues = [];
    packageResult.job.outputs.resultImages = [];

    for (const variant of packageResult.job.generation.variants) {
      packageResult.job.generation.activeSeed = variant.seed;
      packageResult.job.comfy.note = `Workflow wariantu ${variant.index} został wysłany do kolejki ComfyUI.`;
      const queuedWorkflow = await queueComfyWorkflow(packageResult.job, comfyUploads);
      packageResult.job.comfy.queues.push({
        ...queuedWorkflow,
        variantIndex: variant.index,
        seed: variant.seed
      });
      await saveJobPackage(packageResult.job, packageResult.dataFolder);

      const resultAsset = await receiveComfyResult(
        queuedWorkflow.promptId,
        packageResult.dataFolder,
        packageResult.job.cropBounds,
        packageResult.layerMaskData
      );
      resultAsset.variantIndex = variant.index;
      resultAsset.seed = variant.seed;
      packageResult.job.outputs.resultImages.push(resultAsset);
    }

    const resultAsset = packageResult.job.outputs.resultImages[0];
    packageResult.job.outputs.resultImage = resultAsset;
    packageResult.job.placementGeometry = resultAsset?.placementGeometry || resultAsset?.photoshop?.placementGeometry || null;
    const maskApplied = panelHelpers.isLayerVisibilityProtected(resultAsset?.photoshop?.layerMask);
    const compositeAudit = resultAsset?.photoshop?.compositeAudit || null;
    const auditStatusText = describeCompositeAuditForStatus(compositeAudit);
    const placedCount = packageResult.job.outputs.resultImages.filter((image) => image.photoshop?.placedAsLayer).length;
    packageResult.job.comfy.note = placedCount
      ? compositeAudit?.checked && shouldRejectCompositeAudit(compositeAudit)
        ? `Pobrano ${packageResult.job.outputs.resultImages.length} wynik(i), ale pixel audit koloru nie przeszedl.${auditStatusText}`
        : maskApplied
          ? `Pobrano ${packageResult.job.outputs.resultImages.length} wynik(i). Warstwy zostaly wstawione do Photoshopa z ochrona alfa/maski.${auditStatusText}`
          : `Pobrano ${packageResult.job.outputs.resultImages.length} wynik(i). Ochrona pierwszej warstwy wymaga sprawdzenia.${auditStatusText}`
      : "Wyniki ComfyUI zostały pobrane, ale nie udało się wstawić ich automatycznie jako warstw.";
    await saveJobPackage(packageResult.job, packageResult.dataFolder);

    setMessage(
      resultAsset?.photoshop?.placedAsLayer
        ? compositeAudit?.checked && shouldRejectCompositeAudit(compositeAudit)
          ? `Pobrano ${packageResult.job.outputs.resultImages.length} wynik(i), ale pixel audit koloru nie przeszedl.${auditStatusText}`
          : maskApplied
            ? `Pobrano ${packageResult.job.outputs.resultImages.length} wynik(i) i wstawiono jako warstwy z ochrona alfa/maski.${auditStatusText}`
            : `Pobrano ${packageResult.job.outputs.resultImages.length} wynik(i). Ochrona warstwy wymaga recznego sprawdzenia.${auditStatusText}`
        : `Wyniki ComfyUI pobrane do plików, ale nie udało się wstawić warstw automatycznie: ${resultAsset?.photoshop?.error}`
    );
  } catch (error) {
    setProgress(null);
    setMessage(`Nie udało się przygotować edycji: ${describeComfyError(error)}`);
  } finally {
    setProgress(null);
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

    const unsupportedInputs = findUnsupportedWorkflowInputs(workflow, objectInfo);
    if (unsupportedInputs.length) {
      setMessage(
        `ComfyUI ma nieaktualne RasterRelay nodes. Brakuje wejsc: ${unsupportedInputs.join(", ")}. Zatrzymaj ComfyUI, uruchom w katalogu projektu: ${INSTALL_NODES_COMMAND}, potem zrestartuj ComfyUI.`
      );
      return false;
    }

    const quality = getQualityPreset();
    const loraConfig = await loadLoraConfig();
    const loraCount = (loraConfig?.loras || []).length;
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

  // keep the legacy hidden quality select in sync with the visible one
  if (ui.qualitySelectVisible) {
    ui.qualitySelectVisible.addEventListener("change", () => {
      if (ui.qualitySelect) {
        ui.qualitySelect.value = ui.qualitySelectVisible.value;
      }
      const preset = getQualityPreset();
      setMessage(`Jakość: ${preset.label} (${preset.steps} kroków${preset.refine ? ", refine" : ""}).`);
    });
  }

  if (ui.editModeSelect) {
    ui.editModeSelect.addEventListener("change", () => {
      setMessage(
        getEditMode() === "remove"
          ? "Tryb: Usuwanie obiektu — maska zostanie poszerzona, by obiekt zniknął bez obwódki."
          : "Tryb: Edycja — zmiana w obrębie zaznaczenia."
      );
    });
  }

  if (ui.e2eSmokeButton) {
    ui.e2eSmokeButton.addEventListener("click", () => {
      void runE2ESmokeTest();
    });
  }

  rootNode.__rasterRelayInitialized = true;

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
    const audit = result?.compositeAudit;
    setMessage(
      result?.promptId
        ? `Test E2E zakończony. Wynik wstawiony jako warstwa. Prompt ID: ${result.promptId}.`
        : "Test E2E zakończony. Sprawdź nowy dokument i warstwę w Photoshopie."
    );
    if (audit?.checked) {
      setMessage(
        `Test E2E OK. Pixel audit: outsideChanged=${audit.outsideChangedPixels}, maxDiff=${audit.maxDiffOutsideAlphaBBox}, sourceHueMax=${audit.sourceHueMaxErrorInsideChanged ?? "n/a"}, sourceSatMax=${audit.sourceSaturationMaxErrorInsideChanged ?? "n/a"}.`
      );
    }
  } catch (error) {
    setMessage(`Test E2E nie przeszedł: ${error.message || error}`);
  } finally {
    if (ui?.e2eSmokeButton) {
      ui.e2eSmokeButton.disabled = false;
    }
  }
}

async function createGeometrySmokeDocument() {
  const photoshop = getPhotoshopApi();
  const testFile = await getPluginEntry(GEOMETRY_TEST_SOURCE_FILE_NAME);

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
              top: { _unit: "pixelsUnit", _value: GEOMETRY_TEST_SELECTION.centerY - GEOMETRY_TEST_SELECTION.radiusY },
              left: { _unit: "pixelsUnit", _value: GEOMETRY_TEST_SELECTION.centerX - GEOMETRY_TEST_SELECTION.radiusX },
              bottom: { _unit: "pixelsUnit", _value: GEOMETRY_TEST_SELECTION.centerY + GEOMETRY_TEST_SELECTION.radiusY },
              right: { _unit: "pixelsUnit", _value: GEOMETRY_TEST_SELECTION.centerX + GEOMETRY_TEST_SELECTION.radiusX }
            }
          }
        ],
        {}
      );
    },
    { commandName: "RasterRelay Geometry Smoke Document" }
  );

  return photoshop.app.activeDocument;
}

async function runGeometrySmokeTest() {
  const dataFolder = await getDataFolder();
  const qualitySettings = await loadQualitySettings();
  const document = await createGeometrySmokeDocument();
  const exported = await exportInpaintingAssets(document, dataFolder, qualitySettings);
  const report = {
    ok: true,
    test: "manual-export-geometry",
    document: readDocumentSize(document),
    selection: getSelectionInfo(document),
    paddedBounds: exported.paddedBounds,
    generationBounds: exported.generationBounds,
    cropBounds: exported.cropBounds,
    sourceImage: exported.assets.sourceImage,
    mask: {
      role: exported.assets.generationMask?.role || "generationMask",
      width: exported.assets.maskData.selWidth,
      height: exported.assets.maskData.selHeight,
      options: exported.assets.generationMask?.options || null,
      warnings: exported.maskAnalysis?.warnings || []
    },
    layerMask: exported.layerMaskData
      ? {
          role: exported.layerMaskData.role || "visibilityMask",
          width: exported.layerMaskData.width,
          height: exported.layerMaskData.height,
          options: exported.layerMaskData.options || null,
          warnings: exported.layerMaskData.analysis?.warnings || []
        }
      : null,
    checks: {
      sourceMatchesCrop:
        exported.assets.sourceImage.width === exported.cropBounds.width &&
        exported.assets.sourceImage.height === exported.cropBounds.height,
      maskMatchesCrop:
        exported.assets.maskData.selWidth === exported.cropBounds.width &&
        exported.assets.maskData.selHeight === exported.cropBounds.height,
      layerMaskMatchesDocument:
        !exported.layerMaskData ||
        (exported.layerMaskData.width === Math.round(readDocumentSize(document).width) &&
          exported.layerMaskData.height === Math.round(readDocumentSize(document).height)),
      cropMatchesGeneration:
        exported.cropBounds.width === exported.generationBounds.width &&
        exported.cropBounds.height === exported.generationBounds.height
    }
  };

  const reportFile = await dataFolder.createFile(`rasterrelay-geometry-smoke-${createSafeTimestamp()}.json`, {
    overwrite: true
  });
  await reportFile.write(JSON.stringify(report, null, 2));
  setMessage(
    report.checks.sourceMatchesCrop && report.checks.maskMatchesCrop
      ? `Test geometrii OK: source i maska maja rozmiar cropu ${exported.cropBounds.width} x ${exported.cropBounds.height}.`
      : "Test geometrii wykryl rozjazd rozmiarow source/maski."
  );
  console.log(JSON.stringify(report));
  return report;
}

async function runAutostartE2EIfRequested() {
  if (autostartE2EConsumed) {
    return;
  }

  const geometryFlag = await getOptionalPluginTextFile(GEOMETRY_AUTOSTART_FILE_NAME);
  if (geometryFlag) {
    autostartE2EConsumed = true;
    await removeOptionalPluginFile(GEOMETRY_AUTOSTART_FILE_NAME);
    await runGeometrySmokeTest();
    return;
  }

  const flag = await getOptionalPluginTextFile(E2E_AUTOSTART_FILE_NAME);
  if (!flag) {
    return;
  }

  autostartE2EConsumed = true;
  await removeOptionalPluginFile(E2E_AUTOSTART_FILE_NAME);
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
      },
      runGeometrySmokeTest: {
        run() {
          return runGeometrySmokeTest();
        }
      }
    }
  });
} else {
  window.addEventListener("DOMContentLoaded", () => initializePanel(document.body));
}
})();
