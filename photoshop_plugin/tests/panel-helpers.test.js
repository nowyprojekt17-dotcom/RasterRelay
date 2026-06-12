const assert = require("node:assert/strict");
const helpers = require("../src/panel-helpers.js");

function test(name, fn) {
  try {
    fn();
    console.log(`ok - ${name}`);
  } catch (error) {
    console.error(`not ok - ${name}`);
    throw error;
  }
}

test("parseLoraItems handles empty input", () => {
  assert.deepEqual(helpers.parseLoraItems("", { model: 1, clip: 1 }), []);
});

test("parseLoraItems handles one LoRA with default strengths", () => {
  assert.deepEqual(helpers.parseLoraItems("style.safetensors", { model: 0.8, clip: 0.7 }), [
    {
      name: "style.safetensors",
      strengthModel: 0.8,
      strengthClip: 0.7
    }
  ]);
});

test("parseLoraItems handles multiple LoRA values and clamps strengths", () => {
  assert.deepEqual(
    helpers.parseLoraItems("style.safetensors:1.4:0.6, detail.safetensors:3", { model: 1, clip: 1 }),
    [
      {
        name: "style.safetensors",
        strengthModel: 1.4,
        strengthClip: 0.6
      },
      {
        name: "detail.safetensors",
        strengthModel: 2,
        strengthClip: 2
      }
    ]
  );
});

test("calculatePaddedBounds stays inside the document", () => {
  assert.deepEqual(
    helpers.calculatePaddedBounds({ left: 10, top: 20, right: 50, bottom: 80 }, 100, 120, 24),
    {
      left: 0,
      top: 0,
      right: 74,
      bottom: 104,
      width: 74,
      height: 104
    }
  );
});

test("calculateGenerationBounds expands crop to model-safe multiple without leaving document", () => {
  assert.deepEqual(
    helpers.calculateGenerationBounds(
      { left: 495, top: 204, right: 1298, bottom: 591, width: 803, height: 387 },
      1408,
      768,
      16
    ),
    {
      left: 495,
      top: 204,
      right: 1311,
      bottom: 604,
      width: 816,
      height: 400,
      multiple: 16
    }
  );
});

test("calculateGenerationBounds shifts expanded crop at document edge", () => {
  assert.deepEqual(
    helpers.calculateGenerationBounds(
      { left: 80, top: 80, right: 101, bottom: 101, width: 21, height: 21 },
      100,
      100,
      16
    ),
    {
      left: 68,
      top: 68,
      right: 100,
      bottom: 100,
      width: 32,
      height: 32,
      multiple: 16
    }
  );
});

test("softenGrayscaleMask turns a hard edge into gray transition pixels", () => {
  const width = 9;
  const height = 5;
  const values = new Uint8Array(width * height);

  for (let y = 1; y < 4; y += 1) {
    for (let x = 3; x < 6; x += 1) {
      values[y * width + x] = 255;
    }
  }

  const softened = helpers.softenGrayscaleMask(values, width, height, 1);
  assert.ok(helpers.getUniqueValueCount(softened) > 2);
  assert.equal(helpers.hasSoftEdge(softened), true);
});

test("growOrContractMask expands and contracts active pixels", () => {
  const width = 7;
  const height = 7;
  const values = new Uint8Array(width * height);
  values[3 * width + 3] = 255;

  const grown = helpers.growOrContractMask(values, width, height, 1);
  const contracted = helpers.growOrContractMask(grown, width, height, -1);

  assert.ok(Array.from(grown).filter((value) => value > 0).length > 1);
  assert.equal(contracted[3 * width + 3], 255);
});

test("dual mask options keep visibility settings exact", () => {
  const options = helpers.getDualMaskOptions({
    quality: "balanced",
    maskFeatherPx: 12,
    maskGrowPx: -4
  });

  assert.deepEqual(options.visibility, {
    role: "visibility",
    featherPx: 12,
    growPx: -4,
    haloPx: 0
  });
});

test("positive mask grow is generation-only and does not expand Photoshop visibility", () => {
  const options = helpers.getDualMaskOptions({
    quality: "balanced",
    maskFeatherPx: 0,
    maskGrowPx: 15
  });

  assert.equal(options.visibility.growPx, 0);
  assert.ok(options.generation.growPx > 15);
});

test("generation mask receives automatic FLUX support halo", () => {
  const options = helpers.getGenerationMaskOptions({
    quality: "balanced",
    maskFeatherPx: 0,
    maskGrowPx: 15
  });

  assert.equal(options.role, "generation");
  assert.equal(options.haloPx, 16);
  assert.equal(options.featherPx, 16);
  assert.equal(options.growPx, 31);
});

test("generation mask is never narrower than visibility mask for nonnegative grow", () => {
  const options = helpers.getDualMaskOptions({
    quality: "quality",
    maskFeatherPx: 36,
    maskGrowPx: 20
  });

  assert.ok(options.generation.featherPx >= options.visibility.featherPx);
  assert.ok(options.generation.growPx >= options.visibility.growPx);
});

test("analyzeMask warns about very large masks and detects soft edges", () => {
  const width = 10;
  const height = 10;
  const values = new Uint8Array(width * height).fill(255);
  values[0] = 128;

  const analysis = helpers.analyzeMask(values, width, height);

  assert.equal(analysis.hasSoftEdge, true);
  assert.ok(analysis.coverageRatio > 0.65);
  assert.ok(analysis.warnings.some((warning) => warning.includes("bardzo duża")));
});

test("analyzeMask warns about very small masks", () => {
  const width = 10;
  const height = 10;
  const values = new Uint8Array(width * height);
  values[55] = 255;

  const analysis = helpers.analyzeMask(values, width, height);

  assert.equal(analysis.coverageRatio, 0.01);
  assert.ok(analysis.warnings.some((warning) => warning.includes("bardzo ma")));
});

test("analyzeMask reports masks touching crop edges", () => {
  const width = 5;
  const height = 5;
  const values = new Uint8Array(width * height);
  values[0] = 255;
  values[1] = 128;

  const analysis = helpers.analyzeMask(values, width, height);

  assert.equal(analysis.touchesEdge, true);
  assert.ok(analysis.warnings.some((warning) => warning.includes("kraw")));
});

test("buildFinalPrompt combines universal edit instruction and user prompt", () => {
  const prompt = helpers.buildFinalPrompt(
    { quality: "balanced", maskFeatherPx: 24, maskGrowPx: 0, variantCount: 1 },
    "remove the phone number from the car door"
  );

  assert.ok(prompt.includes("Edit only the selected masked area"));
  assert.ok(prompt.includes("Match the surrounding perspective"));
  assert.ok(prompt.includes("remove the phone number"));
});

test("buildFinalPrompt keeps arbitrary user intent", () => {
  const prompt = helpers.buildFinalPrompt(
    { quality: "balanced", maskFeatherPx: 0, maskGrowPx: 15, variantCount: 1 },
    "add a snake coiling around the tree"
  );

  assert.ok(prompt.includes("Edit only the selected masked area"));
  assert.ok(prompt.includes("add a snake coiling around the tree"));
});

test("insertDynamicLoraChain creates one loader per LoRA and rewires targets", () => {
  const workflow = {
    "10": { class_type: "Model", inputs: {} },
    "20": { class_type: "Clip", inputs: {} },
    "30": { class_type: "CFGGuider", inputs: { model: ["10", 0] } },
    "31": { class_type: "CLIPTextEncode", inputs: { clip: ["20", 0] } }
  };
  const chain = {
    modelSource: { nodeId: "10", outputIndex: 0 },
    clipSource: { nodeId: "20", outputIndex: 0 },
    modelTargets: [{ nodeId: "30", inputName: "model" }],
    clipTargets: [{ nodeId: "31", inputName: "clip" }]
  };

  const inserted = helpers.insertDynamicLoraChain(workflow, chain, [
    { name: "style.safetensors", strengthModel: 0.8, strengthClip: 0.7 },
    { name: "detail.safetensors", strengthModel: 0.5, strengthClip: 0.4 }
  ]);

  assert.equal(inserted, true);
  assert.equal(workflow["32"].class_type, "LoraLoader");
  assert.equal(workflow["33"].class_type, "LoraLoader");
  assert.deepEqual(workflow["30"].inputs.model, ["33", 0]);
  assert.deepEqual(workflow["31"].inputs.clip, ["33", 1]);
});

test("clampNumber returns fallback for non-numeric values", () => {
  assert.equal(helpers.clampNumber("abc", 5), 5);
  assert.equal(helpers.clampNumber(NaN, 10), 10);
  assert.equal(helpers.clampNumber(undefined, 15), 15);
});

test("clampNumber clamps to min and max", () => {
  assert.equal(helpers.clampNumber(10, 5, 0, 8), 8);
  assert.equal(helpers.clampNumber(-5, 5, 0, 10), 0);
  assert.equal(helpers.clampNumber(5, 5, 0, 10), 5);
});

test("normalizeQualitySettings defaults to balanced", () => {
  const settings = helpers.normalizeQualitySettings({});
  assert.equal(settings.quality, "balanced");
  assert.equal(settings.schemaVersion, "rasterrelay.qualitySettings.v1");
});

test("normalizeQualitySettings clamps feather and grow values", () => {
  const settings = helpers.normalizeQualitySettings({
    quality: "fast",
    maskFeatherPx: 200,
    maskGrowPx: -100
  });
  assert.equal(settings.quality, "fast");
  assert.equal(settings.maskFeatherPx, 96);
  assert.equal(settings.maskGrowPx, -64);
});

test("setWorkflowInput sets value on correct node", () => {
  const workflow = {
    "10": { class_type: "Loader", inputs: { model: "old" } }
  };
  helpers.setWorkflowInput(workflow, { nodeId: "10", inputName: "model" }, "new");
  assert.equal(workflow["10"].inputs.model, "new");
});

test("setWorkflowInput handles array of targets", () => {
  const workflow = {
    "10": { class_type: "A", inputs: { x: 0 } },
    "20": { class_type: "B", inputs: { y: 0 } }
  };
  helpers.setWorkflowInput(workflow, [
    { nodeId: "10", inputName: "x" },
    { nodeId: "20", inputName: "y" }
  ], 42);
  assert.equal(workflow["10"].inputs.x, 42);
  assert.equal(workflow["20"].inputs.y, 42);
});

test("insertDynamicLoraChain returns false for empty loraItems", () => {
  const workflow = {};
  const chain = { modelSource: { nodeId: "1" }, clipSource: { nodeId: "1" } };
  assert.equal(helpers.insertDynamicLoraChain(workflow, chain, []), false);
  assert.equal(helpers.insertDynamicLoraChain(workflow, chain, null), false);
});

test("computeOptimalGenSize keeps small crops at native size (no upscale)", () => {
  const r = helpers.computeOptimalGenSize(400, 300);
  assert.ok(Math.abs(r.scale - 1.0) < 1e-9);
  assert.equal(r.genWidth, 400);
  assert.equal(r.genHeight, 304);
});

test("computeOptimalGenSize downscales huge crops toward ~1.15MP", () => {
  const r = helpers.computeOptimalGenSize(3200, 2400);
  // 7.68MP -> scale sqrt(1.18/7.68)=0.392 -> clamped to 0.5
  assert.ok(Math.abs(r.scale - 0.5) < 1e-9);
  assert.equal(r.genWidth, 1600);
  assert.equal(r.genHeight, 1200);
});

test("computeOptimalGenSize output is multiple of 16", () => {
  const r = helpers.computeOptimalGenSize(2000, 1500);
  assert.equal(r.genWidth % 16, 0);
  assert.equal(r.genHeight % 16, 0);
  assert.ok(r.scale < 1.0 && r.scale >= 0.5);
});

test("resolveQualityPlan maps presets to steps + refine source", () => {
  const fast = helpers.resolveQualityPlan("fast");
  assert.equal(fast.steps, 8);
  assert.equal(fast.refine, false);
  assert.equal(fast.refineSourceNodeId, "93");

  const balanced = helpers.resolveQualityPlan("balanced");
  assert.equal(balanced.refine, false);
  assert.equal(balanced.refineSourceNodeId, "93");

  const quality = helpers.resolveQualityPlan("quality");
  assert.equal(quality.steps, 20);
  assert.equal(quality.refine, true);
  assert.equal(quality.refineSourceNodeId, "89");
});

test("resolveQualityPlan falls back to balanced for unknown names", () => {
  const r = helpers.resolveQualityPlan("nonsense");
  assert.equal(r.name, "balanced");
  assert.equal(r.refineSourceNodeId, "93");
});
