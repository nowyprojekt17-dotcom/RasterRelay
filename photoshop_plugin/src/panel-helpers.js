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

  const taskModePrompts = {
    replaceObject:
      "Replace only the selected object. Preserve hands, fingers, perspective, lighting, background, shadows and surrounding details.",
    removeTextLogo:
      "Remove readable text, logos and numbers only inside the mask. Reconstruct the original material, reflections, panel lines and texture. Do not create new readable letters.",
    detailRepair:
      "Repair only the selected detail. Keep the rest of the image unchanged. Preserve texture, lighting, edges and scale.",
    backgroundClean:
      "Fill the selected area with matching background. Preserve depth of field, lighting, grain, color and surrounding structure."
  };

  const defaultNegativePrompt =
    "hard square edges, visible seams, distorted hands, extra fingers, unreadable artifacts, duplicated object, damaged background";

  function normalizeTaskMode(mode) {
    return Object.prototype.hasOwnProperty.call(taskModePrompts, mode) ? mode : "replaceObject";
  }

  function normalizeQualitySettings(settings = {}) {
    return {
      schemaVersion: "rasterrelay.qualitySettings.v1",
      taskMode: normalizeTaskMode(settings.taskMode),
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

  function getVisibilityMaskOptions(settings = {}) {
    const normalized = normalizeQualitySettings(settings);
    return {
      role: "visibility",
      featherPx: Math.round(normalized.maskFeatherPx),
      growPx: Math.round(normalized.maskGrowPx),
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
    const normalized = normalizeQualitySettings(settings);
    const basePrompt = taskModePrompts[normalized.taskMode];
    const cleanUserPrompt = String(userPrompt || "").trim();
    return cleanUserPrompt ? `${basePrompt} User request: ${cleanUserPrompt}` : basePrompt;
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
    parseLoraItems,
    parseLoraToken,
    setWorkflowInput,
    softenGrayscaleMask,
    taskModePrompts
  };

  root.RasterRelayPanelHelpers = helpers;

  if (typeof module !== "undefined" && module.exports) {
    module.exports = helpers;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
