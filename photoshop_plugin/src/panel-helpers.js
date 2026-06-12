(function registerRasterRelayPanelHelpers(root) {
  function clampNumber(value, fallback, min = 0, max = 2) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return fallback;
    }

    return Math.min(max, Math.max(min, numeric));
  }

  const generationMaskHaloPxByQuality = {
    fast: 8,
    balanced: 16,
    quality: 24
  };

  const maxMaskFeatherPx = 96;
  const maxMaskGrowPx = 96;

  function parseLoraToken(token, defaultStrengths = { model: 1, clip: 1 }) {
    const trimmed = String(token || "").trim();
    if (!trimmed) {
      return null;
    }

    const parts = trimmed.split(":").map((part) => part.trim()).filter(Boolean);
    const name = parts[0];
    if (!name) {
      return null;
    }

    const model = clampNumber(parts[1], defaultStrengths.model);
    const clipFallback = Number.isFinite(Number(parts[1])) ? model : defaultStrengths.clip;
    const clip = clampNumber(parts[2], clipFallback);

    return {
      name,
      strengthModel: model,
      strengthClip: clip
    };
  }

  function parseLoraItems(rawNames, defaultStrengths = { model: 1, clip: 1 }) {
    return String(rawNames || "")
      .split(/[\n,]+/)
      .map((token) => parseLoraToken(token, defaultStrengths))
      .filter((item) => item && item.name);
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

  function roundUpToMultiple(value, multiple) {
    const normalizedMultiple = Math.max(1, Math.round(multiple || 1));
    return Math.ceil(Math.max(1, Math.round(value || 1)) / normalizedMultiple) * normalizedMultiple;
  }

  function computeOptimalGenSize(cropWidth, cropHeight, options = {}) {
    // Phase D crop-engine (resolution guard-rail): crops at or below the
    // model's comfortable area (~1.15 MP) generate at NATIVE size (measured:
    // upscaling small crops gives no sharpness gain on Flux2 Klein and
    // weakens the edit). Huge crops get a controlled DOWNSCALE for
    // speed/VRAM and the model's trained resolution; the workflow scales
    // the result back to the native crop.
    const targetArea = options.targetArea || 1152 * 1024;
    const minScale = options.minScale || 0.5;
    const maxScale = options.maxScale || 1.0;
    const multiple = options.multiple || 16;
    const w = Math.max(1, Math.round(cropWidth));
    const h = Math.max(1, Math.round(cropHeight));
    const scale = Math.min(maxScale, Math.max(minScale, Math.sqrt(targetArea / (w * h))));
    const genWidth = Math.max(multiple, Math.round((w * scale) / multiple) * multiple);
    const genHeight = Math.max(multiple, Math.round((h * scale) / multiple) * multiple);
    return { genWidth, genHeight, scale };
  }

  function calculateGenerationBounds(cropBounds, docWidth, docHeight, multiple = 16) {
    const documentWidth = Math.max(1, Math.round(docWidth));
    const documentHeight = Math.max(1, Math.round(docHeight));
    const left = Math.max(0, Math.round(cropBounds.left));
    const top = Math.max(0, Math.round(cropBounds.top));
    const width = Math.max(1, Math.round(cropBounds.width || cropBounds.right - cropBounds.left));
    const height = Math.max(1, Math.round(cropBounds.height || cropBounds.bottom - cropBounds.top));
    const targetWidth = Math.min(documentWidth, roundUpToMultiple(width, multiple));
    const targetHeight = Math.min(documentHeight, roundUpToMultiple(height, multiple));
    const targetLeft = Math.min(left, Math.max(0, documentWidth - targetWidth));
    const targetTop = Math.min(top, Math.max(0, documentHeight - targetHeight));
    const targetRight = Math.min(documentWidth, targetLeft + targetWidth);
    const targetBottom = Math.min(documentHeight, targetTop + targetHeight);

    return {
      left: targetLeft,
      top: targetTop,
      right: targetRight,
      bottom: targetBottom,
      width: targetRight - targetLeft,
      height: targetBottom - targetTop,
      multiple: Math.max(1, Math.round(multiple || 1))
    };
  }

  function blurGrayscaleHorizontal(values, width, height, radius) {
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

  function blurGrayscaleVertical(values, width, height, radius) {
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

  function softenGrayscaleMask(values, width, height, radius) {
    const normalizedRadius = Math.max(0, Math.round(radius || 0));
    if (normalizedRadius <= 0) {
      return new Uint8Array(values);
    }

    const horizontal = blurGrayscaleHorizontal(values, width, height, normalizedRadius);
    return blurGrayscaleVertical(horizontal, width, height, normalizedRadius);
  }

  function growGrayscaleMask(values, width, height, radius) {
    const normalizedRadius = Math.max(0, Math.round(Math.abs(radius || 0)));
    if (normalizedRadius <= 0) {
      return new Uint8Array(values);
    }

    const grown = new Uint8Array(values.length);

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        let value = 0;

        for (let yy = Math.max(0, y - normalizedRadius); yy <= Math.min(height - 1, y + normalizedRadius); yy += 1) {
          for (let xx = Math.max(0, x - normalizedRadius); xx <= Math.min(width - 1, x + normalizedRadius); xx += 1) {
            value = Math.max(value, values[yy * width + xx]);
          }
        }

        grown[y * width + x] = value;
      }
    }

    return grown;
  }

  function contractGrayscaleMask(values, width, height, radius) {
    const normalizedRadius = Math.max(0, Math.round(Math.abs(radius || 0)));
    if (normalizedRadius <= 0) {
      return new Uint8Array(values);
    }

    const contracted = new Uint8Array(values.length);

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        let value = 255;

        for (let yy = Math.max(0, y - normalizedRadius); yy <= Math.min(height - 1, y + normalizedRadius); yy += 1) {
          for (let xx = Math.max(0, x - normalizedRadius); xx <= Math.min(width - 1, x + normalizedRadius); xx += 1) {
            value = Math.min(value, values[yy * width + xx]);
          }
        }

        contracted[y * width + x] = value;
      }
    }

    return contracted;
  }

  function growOrContractMask(values, width, height, growPx) {
    const amount = Math.round(growPx || 0);
    if (amount > 0) {
      return growGrayscaleMask(values, width, height, amount);
    }

    if (amount < 0) {
      return contractGrayscaleMask(values, width, height, Math.abs(amount));
    }

    return new Uint8Array(values);
  }

  function getUniqueValueCount(values) {
    return new Set(Array.from(values)).size;
  }

  function hasSoftEdge(values) {
    return Array.from(values).some((value) => value > 0 && value < 255);
  }

  function analyzeMask(values, width, height) {
    const total = Math.max(1, width * height);
    let active = 0;
    let soft = 0;
    let touchesEdge = false;

    for (let index = 0; index < values.length; index += 1) {
      const value = values[index];
      if (value > 10) {
        active += 1;
        const x = index % width;
        const y = Math.floor(index / width);
        if (x === 0 || y === 0 || x === width - 1 || y === height - 1) {
          touchesEdge = true;
        }
      }

      if (value > 0 && value < 255) {
        soft += 1;
      }
    }

    const coverageRatio = active / total;
    const warnings = [];

    if (coverageRatio < 0.03) {
      warnings.push("Maska jest bardzo mała. Model może nie mieć dość miejsca na zmianę.");
    }

    if (coverageRatio > 0.65) {
      warnings.push("Maska jest bardzo duża. Model może mieszać stary i nowy obiekt.");
    }

    if (!soft) {
      warnings.push("Maska wygląda na twardą. Zwiększ miękkość krawędzi.");
    }

    if (touchesEdge) {
      warnings.push("Maska dotyka krawędzi wycinka. Warto dodać większy margines albo zmniejszyć maskę.");
    }

    return {
      coverageRatio: Number(coverageRatio.toFixed(4)),
      activePixels: active,
      totalPixels: total,
      softPixels: soft,
      uniqueValues: getUniqueValueCount(values),
      hasSoftEdge: soft > 0,
      touchesEdge,
      warnings
    };
  }

  const universalEditPrompt =
    "Edit only the selected masked area according to the user's request. Keep the result photorealistic and naturally integrated with the original image. Match the surrounding perspective, lighting, shadows, color temperature, exposure, contrast, grain, texture sharpness and depth of field. Preserve unmasked areas exactly. Avoid visible seams, halos, pasted-on edges or color shifts between generated pixels and the original image.";

  const defaultNegativePrompt =
    "hard square edges, visible seams, distorted hands, extra fingers, unreadable artifacts, duplicated object, damaged background";

  function normalizeQualitySettings(settings = {}) {
    return {
      schemaVersion: "rasterrelay.qualitySettings.v1",
      quality: ["fast", "balanced", "quality"].includes(settings.quality) ? settings.quality : "balanced",
      maskFeatherPx: clampNumber(settings.maskFeatherPx, 24, 0, 96),
      maskGrowPx: clampNumber(settings.maskGrowPx, 0, -64, 96),
      variantCount: Math.round(clampNumber(settings.variantCount, 1, 1, 2)),
      negativePrompt: String(settings.negativePrompt || defaultNegativePrompt).trim()
    };
  }

  function getGenerationMaskHaloPx(quality) {
    return generationMaskHaloPxByQuality[quality] || generationMaskHaloPxByQuality.balanced;
  }

  // Single source of truth for quality presets. `refine` toggles the Phase-B
  // refine pass: when off, the workflow's SeamlessTone reads the base result
  // (node 93) and ComfyUI prunes the whole refine branch (faster); when on it
  // reads the refined result (node 89, smoothest internal blend).
  const qualityPlans = {
    fast: { steps: 8, refine: false },
    balanced: { steps: 14, refine: false },
    quality: { steps: 20, refine: true }
  };

  function resolveQualityPlan(quality) {
    const name = qualityPlans[quality] ? quality : "balanced";
    const plan = qualityPlans[name];
    return {
      name,
      steps: plan.steps,
      refine: plan.refine,
      refineSourceNodeId: plan.refine ? "89" : "93"
    };
  }

  function getVisibilityMaskOptions(settings = {}) {
    const normalized = normalizeQualitySettings(settings);
    return {
      role: "visibility",
      featherPx: Math.round(normalized.maskFeatherPx),
      growPx: Math.min(0, Math.round(normalized.maskGrowPx)),
      haloPx: 0
    };
  }

  function getGenerationMaskOptions(settings = {}) {
    const normalized = normalizeQualitySettings(settings);
    const haloPx = getGenerationMaskHaloPx(normalized.quality);
    return {
      role: "generation",
      featherPx: Math.round(
        clampNumber(Math.max(normalized.maskFeatherPx, haloPx), haloPx, 0, maxMaskFeatherPx)
      ),
      growPx: Math.round(
        clampNumber(Math.max(0, normalized.maskGrowPx) + haloPx, haloPx, 0, maxMaskGrowPx)
      ),
      haloPx
    };
  }

  function getDualMaskOptions(settings = {}) {
    return {
      visibility: getVisibilityMaskOptions(settings),
      generation: getGenerationMaskOptions(settings)
    };
  }

  function buildFinalPrompt(settings, userPrompt) {
    const cleanUserPrompt = String(userPrompt || "").trim();
    return cleanUserPrompt ? `${universalEditPrompt} User request: ${cleanUserPrompt}` : universalEditPrompt;
  }

  function setWorkflowInput(workflow, mappingItem, value) {
    if (!mappingItem) {
      return;
    }

    if (Array.isArray(mappingItem)) {
      mappingItem.forEach((item) => setWorkflowInput(workflow, item, value));
      return;
    }

    const node = workflow[mappingItem.nodeId];
    if (!node || !node.inputs) {
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
    if (!loraChain || !Array.isArray(loraItems) || !loraItems.length) {
      return false;
    }

    let modelSource = [loraChain.modelSource.nodeId, loraChain.modelSource.outputIndex || 0];
    let clipSource = [loraChain.clipSource.nodeId, loraChain.clipSource.outputIndex || 0];

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

  const helpers = {
    calculatePaddedBounds,
    calculateGenerationBounds,
    clampNumber,
    computeOptimalGenSize,
    defaultNegativePrompt,
    analyzeMask,
    buildFinalPrompt,
    getDualMaskOptions,
    getGenerationMaskOptions,
    getVisibilityMaskOptions,
    growOrContractMask,
    getUniqueValueCount,
    hasSoftEdge,
    insertDynamicLoraChain,
    normalizeQualitySettings,
    resolveQualityPlan,
    parseLoraItems,
    parseLoraToken,
    setWorkflowInput,
    softenGrayscaleMask,
    universalEditPrompt
  };

  root.RasterRelayPanelHelpers = helpers;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = helpers;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
