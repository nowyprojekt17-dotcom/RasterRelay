import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import logoUrl from "../../assets/brand/rasterrelay-logo.png";

type ReadinessStatus = "gotowe" | "brak" | "wykryto" | "wymaga instalacji" | "błąd";

type ReadinessItem = {
  id: string;
  label: string;
  path?: string | null;
  status: ReadinessStatus;
  description: string;
  actionLabel?: string | null;
  important: boolean;
};

type ReadinessCounts = {
  customNodes: number;
  loras: number;
  ggufFiles: number;
};

type ReadinessReport = {
  comfyuiPath?: string | null;
  summary: string;
  counts: ReadinessCounts;
  items: ReadinessItem[];
  scannedPaths: string[];
  workflow: WorkflowReadiness;
  photoshop: PhotoshopReadiness;
};

type WorkflowInputStatus = {
  id: string;
  status: ReadinessStatus;
  description: string;
};

type WorkflowReadiness = {
  status: ReadinessStatus;
  summary: string;
  workflowPath: string;
  mappingPath: string;
  workflowExists: boolean;
  mappingExists: boolean;
  mappingReady: boolean;
  comfyApiAvailable: boolean;
  requiredInputs: WorkflowInputStatus[];
  requiredNodes: WorkflowInputStatus[];
};

type PhotoshopReadiness = {
  status: ReadinessStatus;
  summary: string;
  manifestPath: string;
  pluginFolder: string;
  manifestExists: boolean;
  manifestValid: boolean;
  targetVersion: string;
  manifestMinVersion?: string | null;
  panelExists: boolean;
  scriptExists: boolean;
  workflowReady: boolean;
  installNote: string;
};

type AssetKind = "lora" | "gguf";

type AssetInstallValidation = {
  kind: string;
  sourcePath: string;
  targetDir: string;
  targetPath: string;
  fileName: string;
  status: ReadinessStatus;
  message: string;
  canInstall: boolean;
  targetDirExists: boolean;
  willCreateTargetDir: boolean;
};

type AssetInstallResult = {
  success: boolean;
  destinationPath?: string | null;
  message: string;
};

type WorkflowFileKind = "workflowApi" | "workflowMapping";

type WorkflowFileValidation = {
  kind: string;
  sourcePath: string;
  targetPath: string;
  fileName: string;
  status: ReadinessStatus;
  message: string;
  canInstall: boolean;
  willReplaceExisting: boolean;
};

type ComfyRuntimeStatus = {
  running: boolean;
  ownedByLauncher: boolean;
  pid?: number | null;
  url: string;
  message: string;
};

type ComfyRuntimeActionResult = {
  success: boolean;
  status: ComfyRuntimeStatus;
  message: string;
};

type PhotoshopRuntimeStatus = {
  installed: boolean;
  running: boolean;
  path: string;
  message: string;
};

type PhotoshopRuntimeActionResult = {
  success: boolean;
  status: PhotoshopRuntimeStatus;
  message: string;
};

type UxpDeveloperToolsRuntimeStatus = {
  installed: boolean;
  running: boolean;
  pluginRegistered: boolean;
  path: string;
  pluginManifestPath: string;
  workspacePath: string;
  message: string;
};

type UxpDeveloperToolsRuntimeActionResult = {
  success: boolean;
  status: UxpDeveloperToolsRuntimeStatus;
  message: string;
};

type UxpPluginRegisterResult = {
  success: boolean;
  status: UxpDeveloperToolsRuntimeStatus;
  message: string;
};

type UxpPluginLoadResult = {
  success: boolean;
  status: UxpDeveloperToolsRuntimeStatus;
  message: string;
};

type EnvironmentStepStatus = {
  status: ReadinessStatus;
  message: string;
};

type RasterRelayEnvironmentStartResult = {
  success: boolean;
  comfyui: EnvironmentStepStatus;
  photoshop: EnvironmentStepStatus;
  uxpDeveloperTools: EnvironmentStepStatus;
  plugin: EnvironmentStepStatus;
  message: string;
};

type TaskMode = "replaceObject" | "removeTextLogo" | "detailRepair" | "backgroundClean";
type QualityLevel = "fast" | "balanced" | "quality";

type QualitySettings = {
  schemaVersion: "rasterrelay.qualitySettings.v1";
  taskMode: TaskMode;
  quality: QualityLevel;
  maskFeatherPx: number;
  maskGrowPx: number;
  variantCount: 1 | 2;
  negativePrompt: string;
};

type LoraEntry = {
  name: string;
  strengthModel: number;
  strengthClip: number;
};

type LoraConfig = {
  schemaVersion: "rasterrelay.loraConfig.v1";
  loras: LoraEntry[];
};

const savedComfyuiPathKey = "rasterrelay.comfyuiPath";

const defaultQualitySettings: QualitySettings = {
  schemaVersion: "rasterrelay.qualitySettings.v1",
  taskMode: "replaceObject",
  quality: "balanced",
  maskFeatherPx: 24,
  maskGrowPx: 0,
  variantCount: 1,
  negativePrompt:
    "hard square edges, visible seams, distorted hands, extra fingers, unreadable artifacts, duplicated object, damaged background"
};

const defaultLoraConfig: LoraConfig = {
  schemaVersion: "rasterrelay.loraConfig.v1",
  loras: []
};

const taskModeCopy: Record<TaskMode, { label: string; description: string }> = {
  replaceObject: {
    label: "Zamiana obiektu",
    description: "Najlepsze do zadań typu puszka na kubek. Chroni ręce, światło i tło."
  },
  removeTextLogo: {
    label: "Usuń tekst/logo",
    description: "Do czyszczenia napisów, numerów i znaków bez tworzenia nowych liter."
  },
  detailRepair: {
    label: "Popraw detal",
    description: "Do małych poprawek, gdzie reszta obrazu ma zostać prawie nietknięta."
  },
  backgroundClean: {
    label: "Wyczyść tło",
    description: "Do uzupełniania tła zgodnie z otoczeniem i światłem sceny."
  }
};

const statusClass: Record<ReadinessStatus, string> = {
  gotowe: "status-ready",
  wykryto: "status-detected",
  brak: "status-missing",
  "wymaga instalacji": "status-needs",
  błąd: "status-error"
};

function browserFallbackReport(): ReadinessReport {
  return {
    comfyuiPath: null,
    summary: "Podgląd UI działa. Pełny skan folderów działa po uruchomieniu przez Tauri.",
    counts: {
      customNodes: 0,
      loras: 0,
      ggufFiles: 0
    },
    scannedPaths: [],
    workflow: {
      status: "wymaga instalacji",
      summary: "Workflow API sprawdzimy po uruchomieniu przez Tauri.",
      workflowPath: "photoshop_plugin/workflows/inpainting-api.json",
      mappingPath: "photoshop_plugin/workflows/inpainting-api.mapping.json",
      workflowExists: false,
      mappingExists: false,
      mappingReady: false,
      comfyApiAvailable: false,
      requiredInputs: [],
      requiredNodes: []
    },
    photoshop: {
      status: "wymaga instalacji",
      summary: "Panel Photoshopa sprawdzimy po uruchomieniu przez Tauri.",
      manifestPath: "photoshop_plugin/manifest.json",
      pluginFolder: "photoshop_plugin",
      manifestExists: false,
      manifestValid: false,
      targetVersion: "27.8.0",
      manifestMinVersion: null,
      panelExists: false,
      scriptExists: false,
      workflowReady: false,
      installNote: "W UXP Developer Tool kliknij Add Plugin i wskaż manifest.json."
    },
    items: [
      {
        id: "comfyui-root",
        label: "Folder ComfyUI",
        status: "brak",
        description: "Uruchom Launcher przez Tauri, żeby sprawdzić foldery na dysku.",
        actionLabel: "Install",
        important: true
      },
      {
        id: "loras",
        label: "LoRA",
        status: "brak",
        description: "Sekcja LoRA jest gotowa w UI, ale licznik wymaga skanu Tauri.",
        actionLabel: "Add",
        important: true
      }
    ]
  };
}

function App() {
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isInstalling, setIsInstalling] = useState(false);
  const [isRuntimeBusy, setIsRuntimeBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingInstall, setPendingInstall] = useState<AssetInstallValidation | null>(null);
  const [pendingWorkflowInstall, setPendingWorkflowInstall] = useState<WorkflowFileValidation | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<ComfyRuntimeStatus | null>(null);
  const [photoshopRuntimeStatus, setPhotoshopRuntimeStatus] = useState<PhotoshopRuntimeStatus | null>(null);
  const [uxpRuntimeStatus, setUxpRuntimeStatus] = useState<UxpDeveloperToolsRuntimeStatus | null>(null);
  const [environmentResult, setEnvironmentResult] = useState<RasterRelayEnvironmentStartResult | null>(null);
  const [qualitySettings, setQualitySettings] = useState<QualitySettings>(defaultQualitySettings);
  const [isSavingQuality, setIsSavingQuality] = useState(false);
  const [loraFiles, setLoraFiles] = useState<string[]>([]);
  const [loraConfig, setLoraConfig] = useState<LoraConfig>(defaultLoraConfig);
  const [isSavingLora, setIsSavingLora] = useState(false);

  async function loadReadiness(clearNotice = true) {
    setIsLoading(true);
    if (clearNotice) {
      setNotice(null);
    }

    const savedPath = localStorage.getItem(savedComfyuiPathKey);

    try {
      const result = savedPath
        ? await invoke<ReadinessReport>("scan_readiness_for_path", { path: savedPath })
        : await invoke<ReadinessReport>("scan_readiness");
      setReport(result);

      if (result.comfyuiPath) {
        void loadLoraFilesForPath(result.comfyuiPath);
      }

      if (savedPath && !result.comfyuiPath) {
        localStorage.removeItem(savedComfyuiPathKey);
      }
    } catch {
      setReport(browserFallbackReport());
      setNotice("To jest podgląd w przeglądarce. Prawdziwy skan działa w oknie Tauri.");
    } finally {
      setIsLoading(false);
    }
  }

  async function refreshRuntimeStatus() {
    try {
      const status = await invoke<ComfyRuntimeStatus>("get_comfyui_runtime_status");
      setRuntimeStatus(status);
    } catch {
      setRuntimeStatus({
        running: false,
        ownedByLauncher: false,
        pid: null,
        url: "http://127.0.0.1:8188",
        message: "Status ComfyUI działa tylko w oknie Tauri."
      });
    }
  }

  async function refreshPhotoshopRuntimeStatus() {
    try {
      const status = await invoke<PhotoshopRuntimeStatus>("get_photoshop_runtime_status");
      setPhotoshopRuntimeStatus(status);
    } catch {
      setPhotoshopRuntimeStatus({
        installed: false,
        running: false,
        path: "C:\\Program Files\\Adobe\\Adobe Photoshop (Beta)\\Photoshop.exe",
        message: "Status Photoshopa działa tylko w oknie Tauri."
      });
    }
  }

  async function refreshUxpRuntimeStatus() {
    try {
      const status = await invoke<UxpDeveloperToolsRuntimeStatus>("get_uxp_developer_tools_runtime_status");
      setUxpRuntimeStatus(status);
    } catch {
      setUxpRuntimeStatus({
        installed: false,
        running: false,
        pluginRegistered: false,
        path: "C:\\Program Files\\Adobe\\Adobe UXP Developer Tools\\Adobe UXP Developer Tools.exe",
        pluginManifestPath: "photoshop_plugin\\manifest.json",
        workspacePath: "plugins_workspace.json",
        message: "Status Adobe UXP Developer Tools dziaĹ‚a tylko w oknie Tauri."
      });
    }
  }

  async function loadLoraConfig() {
    try {
      const config = await invoke<LoraConfig>("get_lora_config");
      setLoraConfig(config);
    } catch {
      setLoraConfig(defaultLoraConfig);
    }
  }

  async function loadLoraFilesForPath(path: string) {
    try {
      const files = await invoke<string[]>("list_lora_files", { comfyuiPath: path });
      setLoraFiles(files);
    } catch {
      setLoraFiles([]);
    }
  }

  function toggleLoraEntry(name: string) {
    setLoraConfig((prev) => {
      const existing = prev.loras.find((l) => l.name === name);
      if (existing) {
        return { ...prev, loras: prev.loras.filter((l) => l.name !== name) };
      }
      return {
        ...prev,
        loras: [...prev.loras, { name, strengthModel: 1, strengthClip: 1 }]
      };
    });
  }

  function updateLoraStrength(name: string, field: "strengthModel" | "strengthClip", value: number) {
    setLoraConfig((prev) => ({
      ...prev,
      loras: prev.loras.map((l) => (l.name === name ? { ...l, [field]: value } : l))
    }));
  }

  async function saveLoraConfig() {
    setIsSavingLora(true);
    setNotice(null);
    try {
      const result = await invoke<AssetInstallResult>("save_lora_config", {
        config: loraConfig
      });
      setNotice(result.message);
    } catch {
      setNotice("Nie udało się zapisać konfiguracji LoRA. Zapis działa w oknie Tauri.");
    } finally {
      setIsSavingLora(false);
    }
  }

  async function handleAddLoraAndRefresh() {
    await startAssetInstall("lora");
  }
  async function loadQualitySettings() {
    try {
      const settings = await invoke<QualitySettings>("get_quality_settings");
      setQualitySettings({
        ...defaultQualitySettings,
        ...settings,
        variantCount: settings.variantCount === 2 ? 2 : 1
      });
    } catch {
      setQualitySettings(defaultQualitySettings);
    }
  }

  function updateQualitySettings(patch: Partial<QualitySettings>) {
    setQualitySettings((current) => ({
      ...current,
      ...patch
    }));
  }

  async function saveQualitySettings() {
    setIsSavingQuality(true);
    setNotice(null);

    try {
      const result = await invoke<AssetInstallResult>("save_quality_settings", {
        settings: qualitySettings
      });
      setNotice(result.message);
    } catch {
      setNotice("Nie udało się zapisać ustawień jakości. Zapis działa w oknie Tauri.");
    } finally {
      setIsSavingQuality(false);
    }
  }

  async function chooseComfyuiFolder() {
    setIsLoading(true);
    setNotice(null);

    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: "Wybierz główny folder ComfyUI"
      });

      if (!selected) {
        setNotice("Nie wybrano folderu. Nic nie zostało zmienione.");
        return;
      }

      const result = await invoke<ReadinessReport>("scan_readiness_for_path", {
        path: selected
      });

      setReport(result);

      if (result.comfyuiPath) {
        localStorage.setItem(savedComfyuiPathKey, result.comfyuiPath);
        setNotice("Folder ComfyUI zapisany dla tego Launchera.");
      } else {
        localStorage.removeItem(savedComfyuiPathKey);
        setNotice("Ten folder nie wygląda jak ComfyUI. Wybierz folder, w którym jest plik main.py.");
      }
    } catch {
      setNotice("Wybór folderu działa tylko w oknie Tauri, nie w zwykłej przeglądarce.");
    } finally {
      setIsLoading(false);
    }
  }

  function clearSavedComfyuiFolder() {
    localStorage.removeItem(savedComfyuiPathKey);
    setNotice("Zapamiętana ścieżka została wyczyszczona. Następne odświeżenie użyje autoskanu.");
  }

  useEffect(() => {
    void loadReadiness();
    void refreshRuntimeStatus();
    void refreshPhotoshopRuntimeStatus();
    void refreshUxpRuntimeStatus();
    void loadQualitySettings();
    void loadLoraConfig();

    const timer = window.setInterval(() => {
      void refreshRuntimeStatus();
      void refreshPhotoshopRuntimeStatus();
      void refreshUxpRuntimeStatus();
    }, 3000);

    return () => window.clearInterval(timer);
  }, []);

  const hasSavedPath = Boolean(localStorage.getItem(savedComfyuiPathKey));
  const readinessItems = report?.items ?? [];

  async function startAssetInstall(kind: AssetKind) {
    if (!report?.comfyuiPath) {
      setNotice("Najpierw wybierz poprawny folder ComfyUI.");
      return;
    }

    setNotice(null);

    try {
      const selected = await open({
        multiple: false,
        title: kind === "lora" ? "Wybierz plik LoRA" : "Wybierz plik GGUF",
        filters: [
          kind === "lora"
            ? {
                name: "LoRA",
                extensions: ["safetensors", "pt", "ckpt", "bin"]
              }
            : {
                name: "GGUF",
                extensions: ["gguf"]
              }
        ]
      });

      if (!selected || Array.isArray(selected)) {
        setNotice("Nie wybrano pliku. Nic nie zostało zmienione.");
        return;
      }

      const validation = await invoke<AssetInstallValidation>("validate_asset_install", {
        comfyuiPath: report.comfyuiPath,
        sourcePath: selected,
        kind
      });

      setPendingInstall(validation);
    } catch {
      setNotice("Wybór pliku działa tylko w oknie Tauri, nie w zwykłej przeglądarce.");
    }
  }

  async function confirmAssetInstall() {
    if (!pendingInstall || !report?.comfyuiPath) {
      return;
    }

    setIsInstalling(true);
    setNotice(null);

    try {
      const kind: AssetKind = pendingInstall.kind === "LoRA" ? "lora" : "gguf";
      const result = await invoke<AssetInstallResult>("install_asset", {
        comfyuiPath: report.comfyuiPath,
        sourcePath: pendingInstall.sourcePath,
        kind
      });

      if (result.success) {
        setPendingInstall(null);
        await loadReadiness(false);
        setNotice(result.message);
      } else {
        setNotice(result.message);
      }
    } catch {
      setNotice("Nie udało się skopiować pliku. Sprawdź, czy plik nadal istnieje.");
    } finally {
      setIsInstalling(false);
    }
  }

  async function startWorkflowFileInstall(kind: WorkflowFileKind) {
    setNotice(null);

    try {
      const selected = await open({
        multiple: false,
        title:
          kind === "workflowApi"
            ? "Wybierz workflow API JSON z ComfyUI"
            : "Wybierz mapping workflow JSON",
        filters: [
          {
            name: "JSON",
            extensions: ["json"]
          }
        ]
      });

      if (!selected || Array.isArray(selected)) {
        setNotice("Nie wybrano pliku. Nic nie zostało zmienione.");
        return;
      }

      const validation = await invoke<WorkflowFileValidation>("validate_workflow_file_install", {
        sourcePath: selected,
        kind
      });

      setPendingWorkflowInstall(validation);
    } catch {
      setNotice("Wybór pliku workflow działa tylko w oknie Tauri.");
    }
  }

  async function confirmWorkflowFileInstall() {
    if (!pendingWorkflowInstall) {
      return;
    }

    setIsInstalling(true);
    setNotice(null);

    try {
      const kind: WorkflowFileKind =
        pendingWorkflowInstall.kind === "Workflow API" ? "workflowApi" : "workflowMapping";
      const result = await invoke<AssetInstallResult>("install_workflow_file", {
        sourcePath: pendingWorkflowInstall.sourcePath,
        kind
      });

      if (result.success) {
        setPendingWorkflowInstall(null);
        await loadReadiness(false);
      }

      setNotice(result.message);
    } catch {
      setNotice("Nie udało się zapisać pliku workflow.");
    } finally {
      setIsInstalling(false);
    }
  }

  async function startComfyui() {
    if (!report?.comfyuiPath) {
      setNotice("Najpierw wybierz poprawny folder ComfyUI.");
      return;
    }

    setIsRuntimeBusy(true);
    setNotice(null);

    try {
      const result = await invoke<ComfyRuntimeActionResult>("start_comfyui", {
        comfyuiPath: report.comfyuiPath,
        showConsole: false
      });
      setRuntimeStatus(result.status);
      setNotice(result.message);
    } catch {
      setNotice("Nie udało się uruchomić ComfyUI z Launchera.");
    } finally {
      setIsRuntimeBusy(false);
    }
  }

  async function startComfyuiWithTerminal() {
    if (!report?.comfyuiPath) {
      setNotice("Najpierw wybierz poprawny folder ComfyUI.");
      return;
    }

    setIsRuntimeBusy(true);
    setNotice(null);

    try {
      const result = await invoke<ComfyRuntimeActionResult>("start_comfyui", {
        comfyuiPath: report.comfyuiPath,
        showConsole: true
      });
      setRuntimeStatus(result.status);
      setNotice(result.message);
    } catch {
      setNotice("Nie udało się uruchomić ComfyUI z terminalem.");
    } finally {
      setIsRuntimeBusy(false);
    }
  }

  async function stopComfyui() {
    setIsRuntimeBusy(true);
    setNotice(null);

    try {
      const result = await invoke<ComfyRuntimeActionResult>("stop_comfyui");
      setRuntimeStatus(result.status);
      setNotice(result.message);
    } catch {
      setNotice("Nie udało się zatrzymać ComfyUI z Launchera.");
    } finally {
      setIsRuntimeBusy(false);
    }
  }

  async function startPhotoshopBeta() {
    setIsRuntimeBusy(true);
    setNotice(null);

    try {
      const result = await invoke<PhotoshopRuntimeActionResult>("start_photoshop_beta");
      setPhotoshopRuntimeStatus(result.status);
      setNotice(result.message);
    } catch {
      setNotice("Nie udało się uruchomić Photoshop Beta z Launchera.");
    } finally {
      setIsRuntimeBusy(false);
    }
  }

  async function startUxpDeveloperTools() {
    setIsRuntimeBusy(true);
    setNotice(null);

    try {
      const result = await invoke<UxpDeveloperToolsRuntimeActionResult>("start_uxp_developer_tools");
      setUxpRuntimeStatus(result.status);
      setNotice(result.message);
    } catch {
      setNotice("Nie udaĹ‚o siÄ™ uruchomiÄ‡ Adobe UXP Developer Tools z Launchera.");
    } finally {
      setIsRuntimeBusy(false);
    }
  }

  async function registerUxpPlugin() {
    setIsRuntimeBusy(true);
    setNotice(null);

    try {
      const result = await invoke<UxpPluginRegisterResult>("register_uxp_plugin");
      setUxpRuntimeStatus(result.status);
      setNotice(result.message);
    } catch {
      setNotice("Nie udaĹ‚o siÄ™ dopisaÄ‡ RasterRelay do Adobe UXP Developer Tools.");
    } finally {
      setIsRuntimeBusy(false);
    }
  }

  async function loadUxpPluginInPhotoshop() {
    setIsRuntimeBusy(true);
    setNotice(null);

    try {
      const result = await invoke<UxpPluginLoadResult>("load_uxp_plugin_in_photoshop");
      setUxpRuntimeStatus(result.status);
      setNotice(result.message || "RasterRelay zaĹ‚adowany w Photoshopie.");
    } catch {
      setNotice("Nie udaĹ‚o siÄ™ zaĹ‚adowaÄ‡ RasterRelay w Photoshopie.");
    } finally {
      setIsRuntimeBusy(false);
    }
  }

  async function startRasterRelayEnvironment() {
    if (!report?.comfyuiPath) {
      setNotice("Najpierw wybierz poprawny folder ComfyUI.");
      return;
    }

    setIsRuntimeBusy(true);
    setEnvironmentResult(null);
    setNotice("Uruchamiam RasterRelay: ComfyUI, Photoshop, UXP i panel. To może potrwać chwilę.");

    try {
      const result = await invoke<RasterRelayEnvironmentStartResult>("start_rasterrelay_environment", {
        comfyuiPath: report.comfyuiPath
      });
      setEnvironmentResult(result);
      setNotice(result.message);
      await Promise.all([
        refreshRuntimeStatus(),
        refreshPhotoshopRuntimeStatus(),
        refreshUxpRuntimeStatus(),
        loadReadiness(false)
      ]);
    } catch {
      setNotice(
        "Nie udało się uruchomić całego RasterRelay. Jeśli Photoshop pokazuje okno zapisu, zamknij je i spróbuj ponownie."
      );
    } finally {
      setIsRuntimeBusy(false);
    }
  }

  function showPlaceholder(actionLabel: string, label: string) {
    if (label === "Folder ComfyUI" || actionLabel === "Wybierz ponownie") {
      void chooseComfyuiFolder();
      return;
    }

    if (label === "LoRA") {
      void startAssetInstall("lora");
      return;
    }

    if (label === "Modele" || label === "Diffusion models" || label === "UNet / GGUF") {
      void startAssetInstall("gguf");
      return;
    }

    setNotice(
      `${actionLabel} dla "${label}" jest przygotowane jako szkic. Na tym etapie Launcher niczego jeszcze nie kopiuje.`
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">
          <img src={logoUrl} alt="RasterRelay" />
          <div>
            <p className="eyebrow">RasterRelay Launcher</p>
            <h1>Readiness</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <button
            className="primary-button"
            onClick={startRasterRelayEnvironment}
            disabled={isRuntimeBusy || isLoading || !report?.comfyuiPath}
          >
            {isRuntimeBusy ? "Uruchamiam..." : "Start RasterRelay"}
          </button>
          <button className="primary-button" onClick={() => void loadReadiness()} disabled={isLoading}>
            {isLoading ? "Skanuję..." : "Odśwież"}
          </button>
          <button className="secondary-button" onClick={chooseComfyuiFolder} disabled={isLoading}>
            Wybierz folder ComfyUI
          </button>
        </div>
      </header>

      <section className="summary-band">
        <div>
          <p className="eyebrow">Status ComfyUI</p>
          <h2>{report?.comfyuiPath ? "ComfyUI wykryte" : "ComfyUI nie znalezione"}</h2>
          <p>{report?.summary ?? "Sprawdzam lokalne środowisko."}</p>
          {report?.comfyuiPath ? <code>{report.comfyuiPath}</code> : null}
          {hasSavedPath ? (
            <button className="text-button" onClick={clearSavedComfyuiFolder}>
              Wyczyść zapamiętaną ścieżkę
            </button>
          ) : null}
        </div>
        <div className="stats-grid" aria-label="Liczniki środowiska">
          <StatTile label="Custom nodes" value={report?.counts.customNodes ?? 0} />
          <StatTile label="LoRA" value={report?.counts.loras ?? 0} />
          <StatTile label="GGUF" value={report?.counts.ggufFiles ?? 0} />
        </div>
      </section>

      {notice ? <div className="notice">{notice}</div> : null}

      <section className="settings-panel" aria-label="Centrum ustawień RasterRelay">
        <div>
          <p className="eyebrow">Centrum ustawień</p>
          <h2>Jakość edycji</h2>
          <p>
            Panel Photoshopa zostaje mały. Tutaj ustawiasz tryb zadania, miękkość maski i liczbę
            wariantów, a panel użyje tych ustawień przy generowaniu.
          </p>
        </div>
        <StatusBadge status="gotowe" />
        <div className="quality-controls">
          <label>
            <span>Tryb zadania</span>
            <select
              value={qualitySettings.taskMode}
              onChange={(event) => updateQualitySettings({ taskMode: event.target.value as TaskMode })}
            >
              {Object.entries(taskModeCopy).map(([value, copy]) => (
                <option value={value} key={value}>
                  {copy.label}
                </option>
              ))}
            </select>
            <small>{taskModeCopy[qualitySettings.taskMode].description}</small>
          </label>
          <label>
            <span>Jakość</span>
            <select
              value={qualitySettings.quality}
              onChange={(event) => updateQualitySettings({ quality: event.target.value as QualityLevel })}
            >
              <option value="fast">Szybka</option>
              <option value="balanced">Dobra</option>
              <option value="quality">Dokładna</option>
            </select>
          </label>
          <label>
            <span>Miękkość maski: {qualitySettings.maskFeatherPx}px</span>
            <input
              type="range"
              min="0"
              max="96"
              step="1"
              value={qualitySettings.maskFeatherPx}
              onChange={(event) => updateQualitySettings({ maskFeatherPx: Number(event.target.value) })}
            />
          </label>
          <label>
            <span>
              Rozszerzenie maski: {qualitySettings.maskGrowPx > 0 ? "+" : ""}
              {qualitySettings.maskGrowPx}px
            </span>
            <input
              type="range"
              min="-64"
              max="96"
              step="1"
              value={qualitySettings.maskGrowPx}
              onChange={(event) => updateQualitySettings({ maskGrowPx: Number(event.target.value) })}
            />
            <small>Wartość ujemna zwęża maskę, dodatnia ją rozszerza.</small>
          </label>
          <label>
            <span>Liczba wariantów</span>
            <select
              value={qualitySettings.variantCount}
              onChange={(event) =>
                updateQualitySettings({ variantCount: Number(event.target.value) === 2 ? 2 : 1 })
              }
            >
              <option value={1}>1 wariant</option>
              <option value={2}>2 warianty</option>
            </select>
          </label>
          <label className="wide-control">
            <span>Negatywny prompt</span>
            <textarea
              rows={3}
              value={qualitySettings.negativePrompt}
              onChange={(event) => updateQualitySettings({ negativePrompt: event.target.value })}
            />
          </label>
        </div>
        <div className="settings-actions">
          <button className="primary-button" onClick={saveQualitySettings} disabled={isSavingQuality}>
            {isSavingQuality ? "Zapisuję..." : "Zapisz ustawienia dla Photoshopa"}
          </button>
          <button className="ghost-button" onClick={() => setQualitySettings(defaultQualitySettings)}>
            Przywróć domyślne
          </button>
        </div>
        <div className="settings-summary">
          <div>
            <span>Tryb</span>
            <p>{taskModeCopy[qualitySettings.taskMode].label}</p>
          </div>
          <div>
            <span>Maska</span>
            <p>
              Miękkość {qualitySettings.maskFeatherPx}px, zmiana {qualitySettings.maskGrowPx}px.
            </p>
          </div>
          <div>
            <span>Warianty</span>
            <p>{qualitySettings.variantCount} wynik(i) dla trudniejszych masek.</p>
          </div>
        </div>
      </section>

      {environmentResult ? (
        <section className="environment-panel" aria-label="Start RasterRelay">
          <div>
            <p className="eyebrow">Start RasterRelay</p>
            <h2>{environmentResult.success ? "Środowisko działa" : "Wymaga uwagi"}</h2>
            <p>{environmentResult.message}</p>
          </div>
          <StatusBadge status={environmentResult.success ? "gotowe" : "wymaga instalacji"} />
          <div className="environment-steps">
            <EnvironmentStep label="ComfyUI" step={environmentResult.comfyui} />
            <EnvironmentStep label="Photoshop Beta 27.8" step={environmentResult.photoshop} />
            <EnvironmentStep label="UXP Developer Tool" step={environmentResult.uxpDeveloperTools} />
            <EnvironmentStep label="Panel RasterRelay" step={environmentResult.plugin} />
          </div>
        </section>
      ) : null}

      {report?.workflow ? (
        <section className="workflow-panel" aria-label="GotowoĹ›Ä‡ workflow API">
          <div>
            <p className="eyebrow">Workflow API</p>
            <h2>{report.workflow.status === "gotowe" ? "Gotowy" : "Wymaga pracy"}</h2>
            <p>{report.workflow.summary}</p>
          </div>
          <StatusBadge status={report.workflow.status} />
          <dl className="workflow-details">
            <div>
              <dt>Workflow</dt>
              <dd>
                <code>{report.workflow.workflowPath}</code>
              </dd>
            </div>
            <div>
              <dt>Mapping</dt>
              <dd>
                <code>{report.workflow.mappingPath}</code>
              </dd>
            </div>
            <div>
              <dt>Status mappingu</dt>
              <dd>{report.workflow.mappingReady ? "ready" : "brak ready"}</dd>
            </div>
            <div>
              <dt>API ComfyUI</dt>
              <dd>{report.workflow.comfyApiAvailable ? "object_info wykryte" : "brak połączenia"}</dd>
            </div>
          </dl>
          {report.workflow.requiredInputs.length ? (
            <div className="workflow-inputs">
              {report.workflow.requiredInputs.map((input) => (
                <div key={input.id}>
                  <span>{input.description}</span>
                  <StatusBadge status={input.status} />
                </div>
              ))}
            </div>
          ) : null}
          {report.workflow.requiredNodes.length ? (
            <div className="workflow-inputs">
              {report.workflow.requiredNodes.map((node) => (
                <div key={node.id}>
                  <span>
                    {node.id}: {node.description}
                  </span>
                  <StatusBadge status={node.status} />
                </div>
              ))}
            </div>
          ) : null}
          <div className="workflow-actions">
            <button className="secondary-button" onClick={() => startWorkflowFileInstall("workflowApi")}>
              Dodaj workflow API
            </button>
            <button className="ghost-button" onClick={() => startWorkflowFileInstall("workflowMapping")}>
              Dodaj mapping
            </button>
          </div>
        </section>
      ) : null}

      {report?.photoshop ? (
        <section className="photoshop-panel" aria-label="Gotowość panelu Photoshop">
          <div>
            <p className="eyebrow">Photoshop Beta 27.8</p>
            <h2>{report.photoshop.status === "gotowe" ? "Panel gotowy" : "Wymaga sprawdzenia"}</h2>
            <p>{report.photoshop.summary}</p>
          </div>
          <StatusBadge status={report.photoshop.status} />
          <dl className="workflow-details">
            <div>
              <dt>Manifest</dt>
              <dd>
                <code>{report.photoshop.manifestPath}</code>
              </dd>
            </div>
            <div>
              <dt>Folder panelu</dt>
              <dd>
                <code>{report.photoshop.pluginFolder}</code>
              </dd>
            </div>
            <div>
              <dt>Wersja hosta</dt>
              <dd>{report.photoshop.manifestMinVersion ?? "brak"} / cel {report.photoshop.targetVersion}</dd>
            </div>
            <div>
              <dt>Workflow</dt>
              <dd>{report.photoshop.workflowReady ? "gotowy" : "wymaga pracy"}</dd>
            </div>
          </dl>
          <div className="workflow-inputs">
            <div>
              <span>Manifest UXP</span>
              <StatusBadge status={report.photoshop.manifestValid ? "gotowe" : "brak"} />
            </div>
            <div>
              <span>Plik panelu HTML</span>
              <StatusBadge status={report.photoshop.panelExists ? "gotowe" : "brak"} />
            </div>
            <div>
              <span>Kod panelu JS</span>
              <StatusBadge status={report.photoshop.scriptExists ? "gotowe" : "brak"} />
            </div>
          </div>
          <div className="runtime-actions">
            <button
              className="primary-button"
              disabled={isRuntimeBusy || !photoshopRuntimeStatus?.installed}
              onClick={startPhotoshopBeta}
            >
              {photoshopRuntimeStatus?.running ? "Photoshop działa" : "Start Photoshop"}
            </button>
            <button className="ghost-button" disabled={isRuntimeBusy} onClick={refreshPhotoshopRuntimeStatus}>
              Sprawdź status
            </button>
          </div>
          <p className="runtime-note">
            {photoshopRuntimeStatus?.message ?? "Sprawdzam instalację Photoshop Beta."}
          </p>
          <p className="runtime-note">
            <code>{photoshopRuntimeStatus?.path ?? "C:\\Program Files\\Adobe\\Adobe Photoshop (Beta)\\Photoshop.exe"}</code>
          </p>
          <div className="uxp-loader-box">
            <div>
              <p className="eyebrow">Wczytanie wtyczki</p>
              <h3>Adobe UXP Developer Tools</h3>
              <p>{uxpRuntimeStatus?.message ?? "Sprawdzam narzÄ™dzie do wczytania panelu RasterRelay."}</p>
            </div>
            <StatusBadge status={uxpRuntimeStatus?.running ? "gotowe" : uxpRuntimeStatus?.installed ? "wykryto" : "brak"} />
            <div className="runtime-actions">
              <button
                className="primary-button"
                disabled={isRuntimeBusy || !uxpRuntimeStatus?.installed}
                onClick={registerUxpPlugin}
              >
                {uxpRuntimeStatus?.pluginRegistered ? "RasterRelay dodany" : "Dodaj RasterRelay"}
              </button>
              <button
                className="secondary-button"
                disabled={isRuntimeBusy || !uxpRuntimeStatus?.installed}
                onClick={startUxpDeveloperTools}
              >
                {uxpRuntimeStatus?.running ? "UXP dziaĹ‚a" : "Start UXP"}
              </button>
              <button
                className="secondary-button"
                disabled={isRuntimeBusy || !uxpRuntimeStatus?.running || !photoshopRuntimeStatus?.running}
                onClick={loadUxpPluginInPhotoshop}
              >
                ZaĹ‚aduj w Photoshopie
              </button>
              <button className="ghost-button" disabled={isRuntimeBusy} onClick={refreshUxpRuntimeStatus}>
                SprawdĹş UXP
              </button>
            </div>
            <p className="runtime-note">
              Manifest do dodania:
              <br />
              <code>{uxpRuntimeStatus?.pluginManifestPath ?? report.photoshop.manifestPath}</code>
            </p>
            <p className="runtime-note">
              Lista wtyczek UXP:
              <br />
              <code>{uxpRuntimeStatus?.workspacePath ?? "plugins_workspace.json"}</code>
            </p>
          </div>
          <p className="runtime-note">{report.photoshop.installNote}</p>
        </section>
      ) : null}

      <section className="runtime-panel" aria-label="Sterowanie ComfyUI">
        <div>
          <p className="eyebrow">ComfyUI</p>
          <h2>{runtimeStatus?.running ? "Aktywne" : "Nieaktywne"}</h2>
          <p>{runtimeStatus?.message ?? "Sprawdzam, czy ComfyUI działa lokalnie."}</p>
          <code>{runtimeStatus?.url ?? "http://127.0.0.1:8188"}</code>
        </div>
        <StatusBadge status={runtimeStatus?.running ? "gotowe" : "brak"} />
        <div className="runtime-actions">
          <button
            className="primary-button"
            disabled={isRuntimeBusy || !report?.comfyuiPath}
            onClick={startComfyui}
          >
            {isRuntimeBusy ? "Pracuję..." : "Start ComfyUI"}
          </button>
          <button
            className="secondary-button"
            disabled={isRuntimeBusy || !report?.comfyuiPath}
            onClick={startComfyuiWithTerminal}
          >
            Start z terminalem
          </button>
          <button className="ghost-button" disabled={isRuntimeBusy} onClick={stopComfyui}>
            Stop
          </button>
        </div>
        {runtimeStatus?.pid ? (
          <p className="runtime-note">Proces Launchera: PID {runtimeStatus.pid}</p>
        ) : null}
      </section>

      {pendingInstall ? (
        <section className="install-panel" aria-label="Potwierdź dodanie pliku">
          <div>
            <p className="eyebrow">Potwierdź dodanie pliku</p>
            <h2>{pendingInstall.kind}</h2>
            <p>{pendingInstall.message}</p>
          </div>
          <StatusBadge status={pendingInstall.status} />
          <dl className="install-details">
            <div>
              <dt>Plik</dt>
              <dd>{pendingInstall.fileName}</dd>
            </div>
            <div>
              <dt>Źródło</dt>
              <dd>
                <code>{pendingInstall.sourcePath}</code>
              </dd>
            </div>
            <div>
              <dt>Folder docelowy</dt>
              <dd>
                <code>{pendingInstall.targetDir}</code>
              </dd>
            </div>
            <div>
              <dt>Efekt</dt>
              <dd>
                {pendingInstall.willCreateTargetDir
                  ? "Launcher utworzy brakujący folder i skopiuje plik."
                  : "Launcher skopiuje plik do istniejącego folderu."}
              </dd>
            </div>
          </dl>
          <div className="install-actions">
            <button
              className="primary-button"
              disabled={!pendingInstall.canInstall || isInstalling}
              onClick={confirmAssetInstall}
            >
              {isInstalling ? "Kopiuję..." : "Kopiuj"}
            </button>
            <button
              className="ghost-button"
              disabled={isInstalling}
              onClick={() => setPendingInstall(null)}
            >
              Anuluj
            </button>
          </div>
        </section>
      ) : null}

      {pendingWorkflowInstall ? (
        <section className="install-panel" aria-label="Potwierdź dodanie workflow">
          <div>
            <p className="eyebrow">Potwierdź workflow</p>
            <h2>{pendingWorkflowInstall.kind}</h2>
            <p>{pendingWorkflowInstall.message}</p>
          </div>
          <StatusBadge status={pendingWorkflowInstall.status} />
          <dl className="install-details">
            <div>
              <dt>Plik</dt>
              <dd>{pendingWorkflowInstall.fileName}</dd>
            </div>
            <div>
              <dt>Źródło</dt>
              <dd>
                <code>{pendingWorkflowInstall.sourcePath}</code>
              </dd>
            </div>
            <div>
              <dt>Cel</dt>
              <dd>
                <code>{pendingWorkflowInstall.targetPath}</code>
              </dd>
            </div>
            <div>
              <dt>Efekt</dt>
              <dd>
                {pendingWorkflowInstall.willReplaceExisting
                  ? "Launcher zastąpi obecny plik workflow."
                  : "Launcher doda nowy plik workflow."}
              </dd>
            </div>
          </dl>
          <div className="install-actions">
            <button
              className="primary-button"
              disabled={!pendingWorkflowInstall.canInstall || isInstalling}
              onClick={confirmWorkflowFileInstall}
            >
              {isInstalling ? "Zapisuję..." : "Zapisz"}
            </button>
            <button
              className="ghost-button"
              disabled={isInstalling}
              onClick={() => setPendingWorkflowInstall(null)}
            >
              Anuluj
            </button>
          </div>
        </section>
      ) : null}

      {!report?.comfyuiPath ? (
        <section className="guidance-panel" aria-label="Instrukcja wyboru ComfyUI">
          <div>
            <p className="eyebrow">Co dalej?</p>
            <h2>Wskaż prawdziwy folder ComfyUI</h2>
            <p>
              Wybierz główny folder ComfyUI, czyli ten, w którym leży plik <code>main.py</code>.
              Folder z samymi workflow albo notatkami nie wystarczy.
            </p>
          </div>
          <ol>
            <li>Kliknij „Wybierz folder ComfyUI”.</li>
            <li>Otwórz folder, który zawiera <code>main.py</code>.</li>
            <li>Launcher sprawdzi folder i pokaże status modeli, LoRA oraz custom nodes.</li>
          </ol>
          {report?.scannedPaths.length ? (
            <details className="scanned-paths">
              <summary>Ścieżki sprawdzone przez autoskan</summary>
              <ul>
                {report.scannedPaths.map((path) => (
                  <li key={path}>
                    <code>{path}</code>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ) : null}

      <section className="content-grid">
        <article className="lora-stack-panel">
          <div>
            <p className="eyebrow">LoRA Stack</p>
            <h2>{loraConfig.loras.length} aktywnych</h2>
            <p>
              Zaznacz LoRA, które mają być użyte w workflow. Ustaw osobno siłę modelu i siłę CLIP dla każdej.
            </p>
          </div>
          <StatusBadge status={loraFiles.length > 0 ? "wykryto" : "brak"} />
          {loraFiles.length > 0 ? (
            <div className="lora-stack-list">
              {loraFiles.map((fileName) => {
                const configEntry = loraConfig.loras.find((l) => l.name === fileName);
                const isActive = Boolean(configEntry);
                const strengthModel = configEntry?.strengthModel ?? 1;
                const strengthClip = configEntry?.strengthClip ?? 1;
                return (
                  <div className={`lora-item ${isActive ? "lora-item-active" : ""}`} key={fileName}>
                    <label className="lora-item-check">
                      <input
                        type="checkbox"
                        checked={isActive}
                        onChange={() => toggleLoraEntry(fileName)}
                      />
                      <span className="lora-item-name">{fileName}</span>
                    </label>
                    {isActive ? (
                      <div className="lora-item-sliders">
                        <label className="lora-slider-group">
                          <span>Model: {strengthModel.toFixed(2)}</span>
                          <input
                            type="range"
                            min="0"
                            max="2"
                            step="0.05"
                            value={strengthModel}
                            onChange={(e) => updateLoraStrength(fileName, "strengthModel", Number(e.target.value))}
                          />
                        </label>
                        <label className="lora-slider-group">
                          <span>CLIP: {strengthClip.toFixed(2)}</span>
                          <input
                            type="range"
                            min="0"
                            max="2"
                            step="0.05"
                            value={strengthClip}
                            onChange={(e) => updateLoraStrength(fileName, "strengthClip", Number(e.target.value))}
                          />
                        </label>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="lora-stack-empty">
              {report?.comfyuiPath
                ? "Brak plików LoRA w folderze models/loras."
                : "Najpierw wybierz folder ComfyUI."}
            </p>
          )}
          <div className="lora-stack-actions">
            <button
              className="secondary-button"
              disabled={!report?.comfyuiPath}
              onClick={handleAddLoraAndRefresh}
            >
              Dodaj
            </button>
            <button
              className="primary-button"
              disabled={isSavingLora || !report?.comfyuiPath}
              onClick={saveLoraConfig}
            >
              {isSavingLora ? "Zapisuję..." : "Zapisz konfigurację"}
            </button>
          </div>
        </article>

        <section className="checklist" aria-label="Lista gotowości">
          {readinessItems.map((item) => (
            <article className="status-card" key={item.id}>
              <div className="status-card-main">
                <div>
                  <p className="item-label">{item.label}</p>
                  <p className="item-description">{item.description}</p>
                  {item.path ? <code>{item.path}</code> : null}
                </div>
                <StatusBadge status={item.status} />
              </div>
              {item.actionLabel ? (
                <button
                  className="ghost-button"
                  onClick={() => showPlaceholder(item.actionLabel ?? "Add", item.label)}
                >
                  {item.actionLabel}
                </button>
              ) : null}
            </article>
          ))}
        </section>
      </section>

      <footer className="footer-note">
        RasterRelay sprawdza ComfyUI, modele, workflow, LoRA i panel Photoshop Beta 27.8. Konfiguracja LoRA (wybór i siły) jest teraz w Launcherze.
      </footer>
    </main>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusBadge({ status }: { status: ReadinessStatus }) {
  return (
    <span className={`status-badge ${statusClass[status]}`}>
      <span aria-hidden="true" />
      {status}
    </span>
  );
}

function EnvironmentStep({ label, step }: { label: string; step: EnvironmentStepStatus }) {
  return (
    <div>
      <span>{label}</span>
      <p>{step.message}</p>
      <StatusBadge status={step.status} />
    </div>
  );
}

export default App;
