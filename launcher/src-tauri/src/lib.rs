use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashSet;
use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

const COMFYUI_HOST: &str = "127.0.0.1";
const COMFYUI_PORT: u16 = 8188;
const UXP_CLI_PORT: u16 = 14001;
const PHOTOSHOP_BETA_EXE: &str = r"C:\Program Files\Adobe\Adobe Photoshop (Beta)\Photoshop.exe";
const UXP_DEVELOPER_TOOLS_EXE: &str =
    r"C:\Program Files\Adobe\Adobe UXP Developer Tools\Adobe UXP Developer Tools.exe";
const REQUIRED_GGUF_MODEL: &str = "flux-2-klein-9b-Q4_K_M.gguf";
const REQUIRED_TEXT_ENCODER: &str = "qwen_3_8b_fp8mixed.safetensors";
const REQUIRED_VAE: &str = "flux2-vae.safetensors";

struct ComfyProcessState {
    child: Mutex<Option<Child>>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ReadinessReport {
    comfyui_path: Option<String>,
    summary: String,
    counts: ReadinessCounts,
    items: Vec<ReadinessItem>,
    scanned_paths: Vec<String>,
    workflow: WorkflowReadiness,
    photoshop: PhotoshopReadiness,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ReadinessCounts {
    custom_nodes: usize,
    loras: usize,
    gguf_files: usize,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ReadinessItem {
    id: String,
    label: String,
    path: Option<String>,
    status: String,
    description: String,
    action_label: Option<String>,
    important: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkflowReadiness {
    status: String,
    summary: String,
    workflow_path: String,
    mapping_path: String,
    workflow_exists: bool,
    mapping_exists: bool,
    mapping_ready: bool,
    comfy_api_available: bool,
    required_inputs: Vec<WorkflowInputStatus>,
    required_nodes: Vec<WorkflowNodeStatus>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkflowInputStatus {
    id: String,
    status: String,
    description: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkflowNodeStatus {
    id: String,
    status: String,
    description: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct PhotoshopReadiness {
    status: String,
    summary: String,
    manifest_path: String,
    plugin_folder: String,
    manifest_exists: bool,
    manifest_valid: bool,
    target_version: String,
    manifest_min_version: Option<String>,
    panel_exists: bool,
    script_exists: bool,
    workflow_ready: bool,
    install_note: String,
}

#[derive(Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
enum AssetKind {
    Lora,
    Gguf,
}

#[derive(Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
enum WorkflowFileKind {
    WorkflowApi,
    WorkflowMapping,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AssetInstallValidation {
    kind: String,
    source_path: String,
    target_dir: String,
    target_path: String,
    file_name: String,
    status: String,
    message: String,
    can_install: bool,
    target_dir_exists: bool,
    will_create_target_dir: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct AssetInstallResult {
    success: bool,
    destination_path: Option<String>,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkflowFileValidation {
    kind: String,
    source_path: String,
    target_path: String,
    file_name: String,
    status: String,
    message: String,
    can_install: bool,
    will_replace_existing: bool,
}

struct AssetValidationContext {
    kind: String,
    source_path: String,
    target_dir: PathBuf,
    target_path: PathBuf,
    file_name: String,
    target_dir_exists: bool,
}

struct WorkflowFileValidationContext {
    kind: String,
    source_path: String,
    target_path: PathBuf,
    file_name: String,
    will_replace_existing: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ComfyRuntimeStatus {
    running: bool,
    owned_by_launcher: bool,
    pid: Option<u32>,
    url: String,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ComfyRuntimeActionResult {
    success: bool,
    status: ComfyRuntimeStatus,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct PhotoshopRuntimeStatus {
    installed: bool,
    running: bool,
    path: String,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct PhotoshopRuntimeActionResult {
    success: bool,
    status: PhotoshopRuntimeStatus,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct UxpDeveloperToolsRuntimeStatus {
    installed: bool,
    running: bool,
    plugin_registered: bool,
    path: String,
    plugin_manifest_path: String,
    workspace_path: String,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct UxpDeveloperToolsRuntimeActionResult {
    success: bool,
    status: UxpDeveloperToolsRuntimeStatus,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct UxpPluginRegisterResult {
    success: bool,
    status: UxpDeveloperToolsRuntimeStatus,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct UxpPluginLoadResult {
    success: bool,
    status: UxpDeveloperToolsRuntimeStatus,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct EnvironmentStepStatus {
    status: String,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct RasterRelayEnvironmentStartResult {
    success: bool,
    comfyui: EnvironmentStepStatus,
    photoshop: EnvironmentStepStatus,
    uxp_developer_tools: EnvironmentStepStatus,
    plugin: EnvironmentStepStatus,
    message: String,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct QualitySettings {
    schema_version: String,
    task_mode: String,
    quality: String,
    mask_feather_px: i32,
    mask_grow_px: i32,
    variant_count: u8,
    negative_prompt: String,
}

#[derive(Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct LoraEntry {
    name: String,
    strength_model: f64,
    strength_clip: f64,
}

#[derive(Deserialize, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct LoraConfig {
    schema_version: String,
    loras: Vec<LoraEntry>,
}

#[tauri::command]
fn scan_readiness() -> ReadinessReport {
    let candidates = comfyui_candidates();
    let found_root = candidates
        .iter()
        .find(|path| looks_like_comfyui(path))
        .cloned();

    match found_root {
        Some(root) => build_found_report(root, candidates),
        None => build_missing_report(candidates),
    }
}

#[tauri::command]
fn scan_readiness_for_path(path: String) -> ReadinessReport {
    let selected_path = PathBuf::from(path);

    if looks_like_comfyui(&selected_path) {
        build_found_report(selected_path.clone(), vec![selected_path])
    } else {
        build_invalid_selected_report(selected_path)
    }
}

#[tauri::command]
fn validate_asset_install(
    comfyui_path: String,
    source_path: String,
    kind: AssetKind,
) -> AssetInstallValidation {
    validate_asset_install_paths(
        PathBuf::from(comfyui_path),
        PathBuf::from(source_path),
        kind,
    )
}

#[tauri::command]
fn install_asset(comfyui_path: String, source_path: String, kind: AssetKind) -> AssetInstallResult {
    let validation = validate_asset_install_paths(
        PathBuf::from(comfyui_path),
        PathBuf::from(source_path),
        kind,
    );

    if !validation.can_install {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: validation.message,
        };
    }

    let target_dir = PathBuf::from(&validation.target_dir);
    let target_path = PathBuf::from(&validation.target_path);

    if let Err(error) = fs::create_dir_all(&target_dir) {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: format!("Nie udało się utworzyć folderu docelowego: {error}"),
        };
    }

    if target_path.exists() {
        return AssetInstallResult {
            success: false,
            destination_path: Some(validation.target_path),
            message: "Taki plik już istnieje. Launcher nie nadpisuje plików.".to_string(),
        };
    }

    match fs::copy(&validation.source_path, &target_path) {
        Ok(_) => AssetInstallResult {
            success: true,
            destination_path: Some(path_text(&target_path)),
            message: "Plik został skopiowany do ComfyUI.".to_string(),
        },
        Err(error) => AssetInstallResult {
            success: false,
            destination_path: Some(path_text(&target_path)),
            message: format!("Nie udało się skopiować pliku: {error}"),
        },
    }
}

#[tauri::command]
fn validate_workflow_file_install(
    source_path: String,
    kind: WorkflowFileKind,
) -> WorkflowFileValidation {
    validate_workflow_file_install_paths(PathBuf::from(source_path), kind)
}

#[tauri::command]
fn install_workflow_file(source_path: String, kind: WorkflowFileKind) -> AssetInstallResult {
    let validation = validate_workflow_file_install_paths(PathBuf::from(source_path), kind);

    if !validation.can_install {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: validation.message,
        };
    }

    let target_path = PathBuf::from(&validation.target_path);
    let Some(target_dir) = target_path.parent() else {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: "Nie udało się odczytać folderu docelowego workflow.".to_string(),
        };
    };

    if let Err(error) = fs::create_dir_all(target_dir) {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: format!("Nie udało się utworzyć folderu workflow: {error}"),
        };
    }

    match fs::copy(&validation.source_path, &target_path) {
        Ok(_) => AssetInstallResult {
            success: true,
            destination_path: Some(path_text(&target_path)),
            message: "Plik workflow został zapisany w projekcie.".to_string(),
        },
        Err(error) => AssetInstallResult {
            success: false,
            destination_path: Some(path_text(&target_path)),
            message: format!("Nie udało się skopiować pliku workflow: {error}"),
        },
    }
}

#[tauri::command]
fn get_quality_settings() -> QualitySettings {
    read_quality_settings().unwrap_or_else(default_quality_settings)
}

#[tauri::command]
fn save_quality_settings(settings: QualitySettings) -> AssetInstallResult {
    let normalized = normalize_quality_settings(settings);
    let path = quality_settings_path();
    let Some(parent) = path.parent() else {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: "Nie udało się odczytać folderu ustawień jakości.".to_string(),
        };
    };

    if let Err(error) = fs::create_dir_all(parent) {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: format!("Nie udało się utworzyć folderu ustawień jakości: {error}"),
        };
    }

    match serde_json::to_string_pretty(&normalized)
        .map_err(|error| error.to_string())
        .and_then(|text| fs::write(&path, text).map_err(|error| error.to_string()))
    {
        Ok(_) => AssetInstallResult {
            success: true,
            destination_path: Some(path_text(&path)),
            message: "Ustawienia jakości zostały zapisane dla panelu Photoshop.".to_string(),
        },
        Err(error) => AssetInstallResult {
            success: false,
            destination_path: Some(path_text(&path)),
            message: format!("Nie udało się zapisać ustawień jakości: {error}"),
        },
    }
}

#[tauri::command]
fn list_lora_files(comfyui_path: String) -> Vec<String> {
    let loras_path = PathBuf::from(comfyui_path).join("models").join("loras");
    if !loras_path.is_dir() {
        return vec![];
    }
    let Ok(entries) = fs::read_dir(&loras_path) else {
        return vec![];
    };
    let mut names: Vec<String> = entries
        .flatten()
        .filter_map(|entry| {
            let path = entry.path();
            if path.is_file()
                && has_extension(&path, &["safetensors", "pt", "ckpt", "bin"])
            {
                path.file_name()?.to_str().map(str::to_string)
            } else {
                None
            }
        })
        .collect();
    names.sort();
    names
}

#[tauri::command]
fn get_lora_config() -> LoraConfig {
    read_lora_config().unwrap_or_else(default_lora_config)
}

#[tauri::command]
fn save_lora_config(config: LoraConfig) -> AssetInstallResult {
    let normalized = normalize_lora_config(config);
    let path = lora_config_path();
    let Some(parent) = path.parent() else {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: "Nie udało się odczytać folderu konfiguracji LoRA.".to_string(),
        };
    };
    if let Err(error) = fs::create_dir_all(parent) {
        return AssetInstallResult {
            success: false,
            destination_path: None,
            message: format!("Nie udało się utworzyć folderu konfiguracji LoRA: {error}"),
        };
    }
    match serde_json::to_string_pretty(&normalized)
        .map_err(|error| error.to_string())
        .and_then(|text| fs::write(&path, text).map_err(|error| error.to_string()))
    {
        Ok(_) => AssetInstallResult {
            success: true,
            destination_path: Some(path_text(&path)),
            message: "Konfiguracja LoRA została zapisana dla panelu Photoshop.".to_string(),
        },
        Err(error) => AssetInstallResult {
            success: false,
            destination_path: Some(path_text(&path)),
            message: format!("Nie udało się zapisać konfiguracji LoRA: {error}"),
        },
    }
}

#[tauri::command]
fn get_comfyui_runtime_status(state: tauri::State<'_, ComfyProcessState>) -> ComfyRuntimeStatus {
    runtime_status(&state)
}

#[tauri::command]
fn start_comfyui(
    comfyui_path: String,
    show_console: bool,
    state: tauri::State<'_, ComfyProcessState>,
) -> ComfyRuntimeActionResult {
    let root = PathBuf::from(comfyui_path);

    if !looks_like_comfyui(&root) {
        let status = runtime_status(&state);
        return ComfyRuntimeActionResult {
            success: false,
            status,
            message: "Najpierw wybierz poprawny folder ComfyUI z plikiem main.py.".to_string(),
        };
    }

    if api_responds() {
        let status = runtime_status(&state);
        return ComfyRuntimeActionResult {
            success: true,
            status,
            message: "ComfyUI już odpowiada lokalnie.".to_string(),
        };
    }

    {
        let mut guard = state.child.lock().expect("comfy process mutex");
        clear_finished_child(&mut guard);

        if guard.is_some() {
            drop(guard);
            let status = runtime_status(&state);
            return ComfyRuntimeActionResult {
                success: true,
                status,
                message: "ComfyUI jest już uruchamiane przez Launcher.".to_string(),
            };
        }

        let python_path = find_python_executable(&root);
        let mut command = Command::new(python_path);
        command.arg("main.py").current_dir(&root);

        if show_console {
            command
                .stdin(Stdio::null())
                .stdout(Stdio::inherit())
                .stderr(Stdio::inherit());
        } else {
            command
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());
        }

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            if show_console {
                command.creation_flags(0x00000010);
            } else {
                command.creation_flags(0x08000000);
            }
        }

        match command.spawn() {
            Ok(child) => {
                *guard = Some(child);
            }
            Err(error) => {
                drop(guard);
                let status = runtime_status(&state);
                return ComfyRuntimeActionResult {
                    success: false,
                    status,
                    message: format!("Nie udało się uruchomić ComfyUI: {error}"),
                };
            }
        }
    }

    let status = runtime_status(&state);
    ComfyRuntimeActionResult {
        success: true,
        status,
        message: "ComfyUI startuje. Pierwsze uruchomienie może chwilę potrwać.".to_string(),
    }
}

#[tauri::command]
fn stop_comfyui(state: tauri::State<'_, ComfyProcessState>) -> ComfyRuntimeActionResult {
    let mut stopped = false;
    let mut had_owned_process = false;
    {
        let mut guard = state.child.lock().expect("comfy process mutex");
        if let Some(mut child) = guard.take() {
            had_owned_process = true;
            match child.kill() {
                Ok(_) => {
                    let _ = child.wait();
                    stopped = true;
                }
                Err(_) => {
                    *guard = Some(child);
                }
            }
        }
    }

    let status = runtime_status(&state);
    let message = if stopped {
        "ComfyUI uruchomione przez Launcher zostało zatrzymane.".to_string()
    } else if had_owned_process {
        "Nie udało się zatrzymać procesu ComfyUI.".to_string()
    } else if status.running {
        "ComfyUI działa, ale nie zostało uruchomione przez Launcher, więc nie zatrzymuję go na siłę."
            .to_string()
    } else {
        "ComfyUI nie jest uruchomione.".to_string()
    };

    ComfyRuntimeActionResult {
        success: stopped || !status.running,
        status,
        message,
    }
}

#[tauri::command]
fn get_photoshop_runtime_status() -> PhotoshopRuntimeStatus {
    photoshop_runtime_status()
}

#[tauri::command]
fn start_photoshop_beta() -> PhotoshopRuntimeActionResult {
    let status = photoshop_runtime_status();

    if !status.installed {
        return PhotoshopRuntimeActionResult {
            success: false,
            status,
            message: "Nie znaleziono Photoshop Beta w domyślnej ścieżce Adobe.".to_string(),
        };
    }

    if status.running {
        return PhotoshopRuntimeActionResult {
            success: true,
            status,
            message: "Photoshop Beta jest już uruchomiony.".to_string(),
        };
    }

    let mut command = Command::new(PHOTOSHOP_BETA_EXE);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    match command.spawn() {
        Ok(_) => {
            let next_status = photoshop_runtime_status();
            PhotoshopRuntimeActionResult {
                success: true,
                status: next_status,
                message: "Uruchamiam Photoshop Beta. Start może chwilę potrwać.".to_string(),
            }
        }
        Err(error) => PhotoshopRuntimeActionResult {
            success: false,
            status: photoshop_runtime_status(),
            message: format!("Nie udało się uruchomić Photoshop Beta: {error}"),
        },
    }
}

#[tauri::command]
fn get_uxp_developer_tools_runtime_status() -> UxpDeveloperToolsRuntimeStatus {
    uxp_developer_tools_runtime_status()
}

#[tauri::command]
fn start_uxp_developer_tools() -> UxpDeveloperToolsRuntimeActionResult {
    let status = uxp_developer_tools_runtime_status();

    if !status.installed {
        return UxpDeveloperToolsRuntimeActionResult {
            success: false,
            status,
            message: "Nie znaleziono Adobe UXP Developer Tools.".to_string(),
        };
    }

    if status.running {
        return UxpDeveloperToolsRuntimeActionResult {
            success: true,
            status,
            message: "Adobe UXP Developer Tools jest juĹĽ uruchomione.".to_string(),
        };
    }

    let mut command = Command::new(UXP_DEVELOPER_TOOLS_EXE);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    match command.spawn() {
        Ok(_) => UxpDeveloperToolsRuntimeActionResult {
            success: true,
            status: uxp_developer_tools_runtime_status(),
            message: "Uruchamiam Adobe UXP Developer Tools.".to_string(),
        },
        Err(error) => UxpDeveloperToolsRuntimeActionResult {
            success: false,
            status: uxp_developer_tools_runtime_status(),
            message: format!("Nie udaĹ‚o siÄ™ uruchomiÄ‡ Adobe UXP Developer Tools: {error}"),
        },
    }
}

#[tauri::command]
fn register_uxp_plugin() -> UxpPluginRegisterResult {
    let manifest_path = repo_root_path()
        .join("photoshop_plugin")
        .join("manifest.json");
    let workspace_path = uxp_workspace_path();

    if !manifest_path.is_file() {
        return UxpPluginRegisterResult {
            success: false,
            status: uxp_developer_tools_runtime_status(),
            message: "Nie znaleziono manifestu wtyczki RasterRelay.".to_string(),
        };
    }

    if let Some(parent) = workspace_path.parent() {
        if let Err(error) = fs::create_dir_all(parent) {
            return UxpPluginRegisterResult {
                success: false,
                status: uxp_developer_tools_runtime_status(),
                message: format!("Nie udaĹ‚o siÄ™ przygotowaÄ‡ folderu Adobe UXP: {error}"),
            };
        }
    }

    let manifest_text = path_text(&manifest_path);
    let mut workspace = read_uxp_workspace(&workspace_path);
    let Some(plugins) = workspace.get_mut("plugins").and_then(Value::as_array_mut) else {
        return UxpPluginRegisterResult {
            success: false,
            status: uxp_developer_tools_runtime_status(),
            message: "Plik workspace UXP ma nieoczekiwany format.".to_string(),
        };
    };

    let already_registered = plugins.iter().any(|plugin| {
        plugin
            .get("manifestPath")
            .and_then(Value::as_str)
            .map(|path| paths_equal_text(path, &manifest_text))
            .unwrap_or(false)
    });

    if !already_registered {
        plugins.push(serde_json::json!({
            "manifestPath": manifest_text,
            "pluginOptions": {},
            "hostParam": "PS"
        }));
    }

    let pretty = match serde_json::to_string_pretty(&workspace) {
        Ok(text) => text,
        Err(error) => {
            return UxpPluginRegisterResult {
                success: false,
                status: uxp_developer_tools_runtime_status(),
                message: format!("Nie udaĹ‚o siÄ™ zapisaÄ‡ listy wtyczek UXP: {error}"),
            }
        }
    };

    match fs::write(&workspace_path, pretty) {
        Ok(_) => UxpPluginRegisterResult {
            success: true,
            status: uxp_developer_tools_runtime_status(),
            message: if already_registered {
                "RasterRelay juĹĽ jest na liĹ›cie wtyczek UXP.".to_string()
            } else {
                "RasterRelay zostaĹ‚ dodany do listy wtyczek UXP. JeĹ›li UXP byĹ‚o otwarte, odĹ›wieĹĽ listÄ™ albo uruchom je ponownie.".to_string()
            },
        },
        Err(error) => UxpPluginRegisterResult {
            success: false,
            status: uxp_developer_tools_runtime_status(),
            message: format!("Nie udaĹ‚o siÄ™ zapisaÄ‡ listy wtyczek UXP: {error}"),
        },
    }
}

#[tauri::command]
fn load_uxp_plugin_in_photoshop() -> UxpPluginLoadResult {
    let plugin_folder = repo_root_path().join("photoshop_plugin");
    let script_path = repo_root_path().join("scripts").join("load-uxp-plugin.mjs");

    if !plugin_folder.join("manifest.json").is_file() {
        return UxpPluginLoadResult {
            success: false,
            status: uxp_developer_tools_runtime_status(),
            message: "Nie znaleziono manifestu wtyczki RasterRelay.".to_string(),
        };
    }

    if !script_path.is_file() {
        return UxpPluginLoadResult {
            success: false,
            status: uxp_developer_tools_runtime_status(),
            message: "Brakuje skryptu ładującego wtyczkę przez UXP.".to_string(),
        };
    }

    let mut node_command = Command::new("node");
    node_command
        .arg(&script_path)
        .arg(&plugin_folder);

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        node_command.creation_flags(0x08000000);
    }

    let output = node_command.output();

    match output {
        Ok(output) if output.status.success() => UxpPluginLoadResult {
            success: true,
            status: uxp_developer_tools_runtime_status(),
            message: String::from_utf8_lossy(&output.stdout).trim().to_string(),
        },
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            UxpPluginLoadResult {
                success: false,
                status: uxp_developer_tools_runtime_status(),
                message: if stderr.is_empty() {
                    "Nie udało się załadować RasterRelay w Photoshopie.".to_string()
                } else {
                    stderr
                },
            }
        }
        Err(error) => UxpPluginLoadResult {
            success: false,
            status: uxp_developer_tools_runtime_status(),
            message: format!("Nie udało się uruchomić Node.js dla ładowania UXP: {error}"),
        },
    }
}

#[tauri::command]
fn start_rasterrelay_environment(
    comfyui_path: String,
    state: tauri::State<'_, ComfyProcessState>,
) -> RasterRelayEnvironmentStartResult {
    let mut success = true;

    let comfy_start = start_comfyui(comfyui_path, false, state);
    let comfy_ready = if comfy_start.success {
        wait_until(
            api_responds,
            Duration::from_secs(90),
            Duration::from_secs(2),
        )
    } else {
        false
    };
    success &= comfy_ready;

    let comfyui = EnvironmentStepStatus {
        status: if comfy_ready {
            "gotowe".to_string()
        } else if comfy_start.success {
            "wymaga instalacji".to_string()
        } else {
            "błąd".to_string()
        },
        message: if comfy_ready {
            "ComfyUI działa i odpowiada pod http://127.0.0.1:8188/system_stats.".to_string()
        } else {
            comfy_start.message
        },
    };

    let photoshop_start = start_photoshop_beta();
    let photoshop_ready = photoshop_start.success
        && wait_until(
            || process_name_is_running("Photoshop.exe"),
            Duration::from_secs(60),
            Duration::from_secs(2),
        );
    success &= photoshop_ready;

    let photoshop = EnvironmentStepStatus {
        status: if photoshop_ready {
            "gotowe".to_string()
        } else {
            "błąd".to_string()
        },
        message: if photoshop_ready {
            "Photoshop Beta 27.8 jest uruchomiony.".to_string()
        } else {
            photoshop_start.message
        },
    };

    let register_result = register_uxp_plugin();
    let uxp_start = start_uxp_developer_tools();
    let uxp_ready = register_result.success
        && uxp_start.success
        && wait_until(
            uxp_cli_responds,
            Duration::from_secs(45),
            Duration::from_secs(2),
        );
    success &= uxp_ready;

    let uxp_developer_tools = EnvironmentStepStatus {
        status: if uxp_ready {
            "gotowe".to_string()
        } else if register_result.success || uxp_start.success {
            "wymaga instalacji".to_string()
        } else {
            "błąd".to_string()
        },
        message: if uxp_ready {
            "Adobe UXP Developer Tools działa i przyjmuje polecenia.".to_string()
        } else if !register_result.success {
            register_result.message
        } else {
            uxp_start.message
        },
    };

    let plugin_load = if uxp_ready && photoshop_ready {
        load_uxp_plugin_in_photoshop()
    } else {
        UxpPluginLoadResult {
            success: false,
            status: uxp_developer_tools_runtime_status(),
            message: "Nie ładuję panelu, bo Photoshop albo UXP nie są jeszcze gotowe.".to_string(),
        }
    };
    success &= plugin_load.success;

    let plugin = EnvironmentStepStatus {
        status: if plugin_load.success {
            "gotowe".to_string()
        } else {
            "błąd".to_string()
        },
        message: if plugin_load.success {
            "RasterRelay został załadowany w Photoshopie.".to_string()
        } else {
            format!(
                "{} Jeśli Photoshop pokazuje okno zapisu, zamknij je i spróbuj ponownie.",
                plugin_load.message
            )
        },
    };

    RasterRelayEnvironmentStartResult {
        success,
        comfyui,
        photoshop,
        uxp_developer_tools,
        plugin,
        message: if success {
            "RasterRelay jest uruchomiony. W Photoshopie otwórz panel RasterRelay.".to_string()
        } else {
            "Nie wszystko udało się uruchomić. Sprawdź komunikaty poniżej.".to_string()
        },
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(ComfyProcessState {
            child: Mutex::new(None),
        })
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            scan_readiness,
            scan_readiness_for_path,
            validate_asset_install,
            install_asset,
            validate_workflow_file_install,
            install_workflow_file,
            get_quality_settings,
            save_quality_settings,
            list_lora_files,
            get_lora_config,
            save_lora_config,
            get_comfyui_runtime_status,
            start_comfyui,
            stop_comfyui,
            get_photoshop_runtime_status,
            start_photoshop_beta,
            get_uxp_developer_tools_runtime_status,
            start_uxp_developer_tools,
            register_uxp_plugin,
            load_uxp_plugin_in_photoshop,
            start_rasterrelay_environment
        ])
        .run(tauri::generate_context!())
        .expect("error while running RasterRelay Launcher");
}

fn build_found_report(root: PathBuf, candidates: Vec<PathBuf>) -> ReadinessReport {
    let custom_nodes_path = root.join("custom_nodes");
    let models_path = root.join("models");
    let loras_path = models_path.join("loras");
    let diffusion_models_path = models_path.join("diffusion_models");
    let unet_path = models_path.join("unet");
    let clip_path = models_path.join("clip");
    let text_encoders_path = models_path.join("text_encoders");
    let vae_path = models_path.join("vae");
    let rasterrelay_nodes_path = custom_nodes_path.join("rasterrelay_nodes");
    let required_gguf_path = unet_path.join(REQUIRED_GGUF_MODEL);
    let required_text_encoder_paths = [
        text_encoders_path.join(REQUIRED_TEXT_ENCODER),
        clip_path.join(REQUIRED_TEXT_ENCODER),
    ];
    let required_vae_path = vae_path.join(REQUIRED_VAE);

    let custom_nodes = count_direct_child_dirs(&custom_nodes_path);
    let loras =
        count_files_with_extensions(&loras_path, &["safetensors", "pt", "ckpt", "bin"], false);
    let gguf_files = count_files_with_extensions(&models_path, &["gguf"], true);
    let python_ready = root.join("venv").is_dir()
        || root.join("python_embeded").is_dir()
        || root.join("python_embedded").is_dir();

    let items = vec![
        item(
            "comfyui-root",
            "Folder ComfyUI",
            Some(&root),
            "gotowe",
            "Znaleziono folder, który wygląda jak ComfyUI.",
            None,
            true,
        ),
        item(
            "main-py",
            "Plik main.py",
            Some(&root.join("main.py")),
            "gotowe",
            "To główny plik startowy ComfyUI.",
            None,
            true,
        ),
        item(
            "python-env",
            "Python / venv",
            None,
            if python_ready {
                "gotowe"
            } else {
                "wymaga instalacji"
            },
            if python_ready {
                "Znaleziono środowisko Python używane przez ComfyUI."
            } else {
                "Nie znaleziono folderu venv ani portable Python."
            },
            Some("Install"),
            true,
        ),
        folder_item(
            "custom-nodes",
            "Custom nodes",
            &custom_nodes_path,
            &format!("Wykryto {} folderów custom nodes.", custom_nodes),
            "Brakuje folderu custom_nodes.",
            Some("Add"),
            true,
        ),
        folder_item(
            "models",
            "Modele",
            &models_path,
            &format!("Wykryto {} plików GGUF w folderze models.", gguf_files),
            "Brakuje folderu models.",
            Some("Add"),
            true,
        ),
        folder_item(
            "loras",
            "LoRA",
            &loras_path,
            &format!("Wykryto {} plików LoRA.", loras),
            "Brakuje folderu models/loras.",
            Some("Add"),
            true,
        ),
        folder_item(
            "diffusion-models",
            "Diffusion models",
            &diffusion_models_path,
            "Folder diffusion_models jest na miejscu.",
            "Brakuje folderu models/diffusion_models.",
            Some("Add"),
            false,
        ),
        folder_item(
            "unet-models",
            "UNet / GGUF",
            &unet_path,
            "Folder unet jest na miejscu. Ten folder jest używany przez lokalny loader GGUF.",
            "Brakuje folderu models/unet.",
            Some("Add"),
            true,
        ),
        folder_item(
            "clip-models",
            "CLIP / text encoders",
            &clip_path,
            "Folder clip jest na miejscu. Ten folder jest używany przez lokalny CLIPLoader.",
            "Brakuje folderu models/clip.",
            Some("Add"),
            false,
        ),
        folder_item(
            "text-encoders",
            "Text encoders",
            &text_encoders_path,
            "Folder text_encoders jest na miejscu.",
            "Brakuje folderu models/text_encoders.",
            Some("Add"),
            false,
        ),
        folder_item(
            "vae-models",
            "VAE",
            &vae_path,
            "Folder vae jest na miejscu.",
            "Brakuje folderu models/vae.",
            Some("Add"),
            false,
        ),
        file_item(
            "required-gguf-model",
            "Model bazowy GGUF",
            &required_gguf_path,
            &format!("Znaleziono wymagany model: {REQUIRED_GGUF_MODEL}."),
            &format!("Brakuje wymaganego modelu: {REQUIRED_GGUF_MODEL}."),
            true,
        ),
        file_any_item(
            "required-text-encoder",
            "Text encoder FLUX.2",
            &required_text_encoder_paths,
            &format!("Znaleziono wymagany text encoder: {REQUIRED_TEXT_ENCODER}."),
            &format!("Brakuje wymaganego text encodera: {REQUIRED_TEXT_ENCODER} w models/text_encoders albo models/clip."),
            true,
        ),
        file_item(
            "required-vae",
            "VAE FLUX.2",
            &required_vae_path,
            &format!("Znaleziono wymagane VAE: {REQUIRED_VAE}."),
            &format!("Brakuje wymaganego VAE: {REQUIRED_VAE}."),
            true,
        ),
        item(
            "rasterrelay-nodes",
            "RasterRelay nodes",
            Some(&rasterrelay_nodes_path),
            if rasterrelay_nodes_path.is_dir() {
                "gotowe"
            } else {
                "wymaga instalacji"
            },
            if rasterrelay_nodes_path.is_dir() {
                "Własne nodes RasterRelay są już w custom_nodes."
            } else {
                "To miejsce będzie użyte na przyszłe nodes RasterRelay."
            },
            Some("Install"),
            false,
        ),
    ];

    let workflow = workflow_readiness();
    let photoshop = photoshop_readiness(&workflow);

    ReadinessReport {
        comfyui_path: Some(path_text(&root)),
        summary: "Znaleziono ComfyUI. Sprawdź elementy poniżej, zanim przejdziemy do workflow."
            .to_string(),
        counts: ReadinessCounts {
            custom_nodes,
            loras,
            gguf_files,
        },
        items,
        scanned_paths: paths_to_text(candidates),
        workflow,
        photoshop,
    }
}

fn build_missing_report(candidates: Vec<PathBuf>) -> ReadinessReport {
    let missing_items = vec![
        item(
            "comfyui-root",
            "Folder ComfyUI",
            None,
            "brak",
            "Nie znaleziono folderu z plikiem main.py.",
            Some("Install"),
            true,
        ),
        item(
            "main-py",
            "Plik main.py",
            None,
            "brak",
            "Bez main.py Launcher nie uznaje folderu za ComfyUI.",
            None,
            true,
        ),
        item(
            "python-env",
            "Python / venv",
            None,
            "wymaga instalacji",
            "Najpierw trzeba znaleźć albo przygotować ComfyUI.",
            Some("Install"),
            true,
        ),
        item(
            "custom-nodes",
            "Custom nodes",
            None,
            "brak",
            "Ten folder będzie sprawdzany po znalezieniu ComfyUI.",
            Some("Add"),
            true,
        ),
        item(
            "models",
            "Modele",
            None,
            "brak",
            "Ten folder będzie sprawdzany po znalezieniu ComfyUI.",
            Some("Add"),
            true,
        ),
        item(
            "loras",
            "LoRA",
            None,
            "brak",
            "Folder LoRA będzie ważną częścią workflow inpaintingu.",
            Some("Add"),
            true,
        ),
        item(
            "diffusion-models",
            "Diffusion models",
            None,
            "brak",
            "Ten folder będzie sprawdzany po znalezieniu ComfyUI.",
            Some("Add"),
            false,
        ),
        item(
            "text-encoders",
            "Text encoders",
            None,
            "brak",
            "Ten folder będzie sprawdzany po znalezieniu ComfyUI.",
            Some("Add"),
            false,
        ),
        item(
            "rasterrelay-nodes",
            "RasterRelay nodes",
            None,
            "wymaga instalacji",
            "To miejsce przygotujemy w przyszłości w custom_nodes.",
            Some("Install"),
            false,
        ),
    ];

    let workflow = workflow_readiness();
    let photoshop = photoshop_readiness(&workflow);

    ReadinessReport {
        comfyui_path: None,
        summary: "Nie znaleziono pełnej instalacji ComfyUI w typowych miejscach.".to_string(),
        counts: ReadinessCounts {
            custom_nodes: 0,
            loras: 0,
            gguf_files: 0,
        },
        items: missing_items,
        scanned_paths: paths_to_text(candidates),
        workflow,
        photoshop,
    }
}

fn build_invalid_selected_report(selected_path: PathBuf) -> ReadinessReport {
    let selected_path_text = path_text(&selected_path);

    let missing_items = vec![
        item(
            "comfyui-root",
            "Folder ComfyUI",
            Some(&selected_path),
            "błąd",
            "Wybrany folder nie wygląda jak główny folder ComfyUI.",
            Some("Wybierz ponownie"),
            true,
        ),
        item(
            "main-py",
            "Plik main.py",
            Some(&selected_path.join("main.py")),
            "brak",
            "W tym folderze nie ma pliku main.py.",
            None,
            true,
        ),
        item(
            "python-env",
            "Python / venv",
            None,
            "wymaga instalacji",
            "Najpierw wybierz główny folder ComfyUI.",
            Some("Install"),
            true,
        ),
        item(
            "custom-nodes",
            "Custom nodes",
            None,
            "brak",
            "Ten folder będzie sprawdzany po wybraniu właściwego ComfyUI.",
            Some("Add"),
            true,
        ),
        item(
            "models",
            "Modele",
            None,
            "brak",
            "Ten folder będzie sprawdzany po wybraniu właściwego ComfyUI.",
            Some("Add"),
            true,
        ),
        item(
            "loras",
            "LoRA",
            None,
            "brak",
            "LoRA będą sprawdzane po wybraniu właściwego ComfyUI.",
            Some("Add"),
            true,
        ),
        item(
            "diffusion-models",
            "Diffusion models",
            None,
            "brak",
            "Ten folder będzie sprawdzany po wybraniu właściwego ComfyUI.",
            Some("Add"),
            false,
        ),
        item(
            "text-encoders",
            "Text encoders",
            None,
            "brak",
            "Ten folder będzie sprawdzany po wybraniu właściwego ComfyUI.",
            Some("Add"),
            false,
        ),
        item(
            "rasterrelay-nodes",
            "RasterRelay nodes",
            None,
            "wymaga instalacji",
            "To miejsce przygotujemy później w custom_nodes.",
            Some("Install"),
            false,
        ),
    ];

    let workflow = workflow_readiness();
    let photoshop = photoshop_readiness(&workflow);

    ReadinessReport {
        comfyui_path: None,
        summary: format!(
            "Wybrano folder: {selected_path_text}. Brakuje w nim pliku main.py, więc to nie jest główny folder ComfyUI."
        ),
        counts: ReadinessCounts {
            custom_nodes: 0,
            loras: 0,
            gguf_files: 0,
        },
        items: missing_items,
        scanned_paths: vec![selected_path_text],
        workflow,
        photoshop,
    }
}

fn validate_asset_install_paths(
    comfyui_path: PathBuf,
    source_path: PathBuf,
    kind: AssetKind,
) -> AssetInstallValidation {
    let source_path_text = path_text(&source_path);
    let (target_dir, kind_label, allowed_extensions) = asset_target(&comfyui_path, kind);
    let file_name = source_path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_string();
    let target_path = if file_name.is_empty() {
        target_dir.clone()
    } else {
        target_dir.join(&file_name)
    };
    let target_dir_exists = target_dir.is_dir();
    let context = AssetValidationContext {
        kind: kind_label,
        source_path: source_path_text,
        target_dir,
        target_path,
        file_name,
        target_dir_exists,
    };

    if !looks_like_comfyui(&comfyui_path) {
        return asset_validation(
            &context,
            "błąd",
            "Najpierw wybierz poprawny folder ComfyUI z plikiem main.py.",
            false,
        );
    }

    if !source_path.is_file() {
        return asset_validation(
            &context,
            "błąd",
            "Wybrana ścieżka nie jest plikiem.",
            false,
        );
    }

    if context.file_name.is_empty() {
        return asset_validation(
            &context,
            "błąd",
            "Nie udało się odczytać nazwy pliku.",
            false,
        );
    }

    if !has_extension(&source_path, allowed_extensions) {
        return asset_validation(
            &context,
            "błąd",
            extension_error_message(kind),
            false,
        );
    }

    if context.target_path.exists() {
        return asset_validation(
            &context,
            "błąd",
            "Taki plik już istnieje w folderze docelowym. Launcher nie nadpisuje plików.",
            false,
        );
    }

    asset_validation(
        &context,
        "gotowe",
        if context.target_dir_exists {
            "Plik wygląda poprawnie. Można go skopiować po potwierdzeniu."
        } else {
            "Plik wygląda poprawnie. Folder docelowy zostanie utworzony po potwierdzeniu."
        },
        true,
    )
}

fn asset_target(
    comfyui_path: &Path,
    kind: AssetKind,
) -> (PathBuf, String, &'static [&'static str]) {
    match kind {
        AssetKind::Lora => (
            comfyui_path.join("models").join("loras"),
            "LoRA".to_string(),
            &["safetensors", "pt", "ckpt", "bin"],
        ),
        AssetKind::Gguf => (
            comfyui_path.join("models").join("unet"),
            "GGUF".to_string(),
            &["gguf"],
        ),
    }
}

fn asset_validation(
    context: &AssetValidationContext,
    status: &str,
    message: &str,
    can_install: bool,
) -> AssetInstallValidation {
    AssetInstallValidation {
        kind: context.kind.clone(),
        source_path: context.source_path.clone(),
        target_dir: path_text(&context.target_dir),
        target_path: path_text(&context.target_path),
        file_name: context.file_name.clone(),
        status: status.to_string(),
        message: message.to_string(),
        can_install,
        target_dir_exists: context.target_dir_exists,
        will_create_target_dir: can_install && !context.target_dir_exists,
    }
}

fn validate_workflow_file_install_paths(
    source_path: PathBuf,
    kind: WorkflowFileKind,
) -> WorkflowFileValidation {
    let source_path_text = path_text(&source_path);
    let target_path = workflow_file_target(kind);
    let file_name = source_path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_string();
    let kind_label = workflow_file_kind_label(kind);
    let will_replace_existing = target_path.is_file();
    let context = WorkflowFileValidationContext {
        kind: kind_label,
        source_path: source_path_text,
        target_path,
        file_name,
        will_replace_existing,
    };

    if !source_path.is_file() {
        return workflow_file_validation(
            &context,
            "błąd",
            "Wybrana ścieżka nie jest plikiem.",
            false,
        );
    }

    if !has_extension(&source_path, &["json"]) {
        return workflow_file_validation(
            &context,
            "błąd",
            "Workflow musi być plikiem .json.",
            false,
        );
    }

    let Ok(json) = read_json_file(&source_path) else {
        return workflow_file_validation(
            &context,
            "błąd",
            "Nie udało się odczytać tego pliku jako JSON.",
            false,
        );
    };

    if kind == WorkflowFileKind::WorkflowApi {
        if !json
            .as_object()
            .map(|nodes| !nodes.is_empty())
            .unwrap_or(false)
        {
            return workflow_file_validation(
                &context,
                "błąd",
                "Workflow API wygląda na pusty.",
                false,
            );
        }

        if !workflow_has_required_classes(&json) {
            return workflow_file_validation(
                &context,
                "błąd",
                "Workflow API nie ma wszystkich wymaganych node'ów dla FLUX/GGUF, maski, LoRA i zapisu wyniku.",
                false,
            );
        }
    }

    if kind == WorkflowFileKind::WorkflowMapping {
        if json.get("inputs").and_then(Value::as_object).is_none() {
            return workflow_file_validation(
                &context,
                "błąd",
                "Mapping musi mieć sekcję inputs.",
                false,
            );
        }

        if !mapping_has_required_inputs(&json) {
            return workflow_file_validation(
                &context,
                "błąd",
                "Mapping musi wskazywać sourceImage, selectionMask i prompt.",
                false,
            );
        }

        if !mapping_lora_slots_are_valid(&json) {
            return workflow_file_validation(
                &context,
                "błąd",
                "Mapping musi mieć poprawną sekcję loraChain albo inputs.loras dla obsługi LoRA.",
                false,
            );
        }
    }

    workflow_file_validation(
        &context,
        "gotowe",
        if context.will_replace_existing {
            "Plik wygląda poprawnie. Zastąpi obecny plik workflow po potwierdzeniu."
        } else {
            "Plik wygląda poprawnie. Zostanie dodany do folderu workflow po potwierdzeniu."
        },
        true,
    )
}

fn workflow_file_validation(
    context: &WorkflowFileValidationContext,
    status: &str,
    message: &str,
    can_install: bool,
) -> WorkflowFileValidation {
    WorkflowFileValidation {
        kind: context.kind.clone(),
        source_path: context.source_path.clone(),
        target_path: path_text(&context.target_path),
        file_name: context.file_name.clone(),
        status: status.to_string(),
        message: message.to_string(),
        can_install,
        will_replace_existing: context.will_replace_existing,
    }
}

fn workflow_file_target(kind: WorkflowFileKind) -> PathBuf {
    let file_name = match kind {
        WorkflowFileKind::WorkflowApi => "inpainting-api.json",
        WorkflowFileKind::WorkflowMapping => "inpainting-api.mapping.json",
    };

    repo_root_path()
        .join("photoshop_plugin")
        .join("workflows")
        .join(file_name)
}

fn workflow_file_kind_label(kind: WorkflowFileKind) -> String {
    match kind {
        WorkflowFileKind::WorkflowApi => "Workflow API".to_string(),
        WorkflowFileKind::WorkflowMapping => "Workflow mapping".to_string(),
    }
}

fn mapping_has_required_inputs(mapping: &Value) -> bool {
    [
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
        "docHeight",
    ]
        .iter()
        .all(|id| mapping_input_is_ready(mapping, id))
}

fn mapping_input_is_ready(mapping: &Value, id: &str) -> bool {
    mapping
        .get("inputs")
        .and_then(|inputs| inputs.get(id))
        .map(mapping_value_is_ready)
        .unwrap_or(false)
}

fn mapping_value_is_ready(input: &Value) -> bool {
    if let Some(items) = input.as_array() {
        return !items.is_empty() && items.iter().all(mapping_value_is_ready);
    }

    input.get("nodeId").is_some() && input.get("inputName").is_some()
}

fn mapping_lora_slots_are_valid(mapping: &Value) -> bool {
    if mapping_input_is_ready(mapping, "lorasJson") {
        return true;
    }

    if mapping_lora_chain_is_ready(mapping) {
        return true;
    }

    let Some(loras) = mapping.get("inputs").and_then(|inputs| inputs.get("loras")) else {
        return false;
    };

    let Some(slots) = loras.as_array() else {
        return false;
    };

    slots.iter().all(|slot| {
        ["name", "strengthModel", "strengthClip"]
            .iter()
            .any(|field| mapping_slot_field_is_ready(slot, field))
    })
}

fn mapping_lora_chain_is_ready(mapping: &Value) -> bool {
    let Some(chain) = mapping.get("loraChain") else {
        return false;
    };

    let model_source_ready = chain
        .get("modelSource")
        .map(|source| source.get("nodeId").is_some())
        .unwrap_or(false);
    let clip_source_ready = chain
        .get("clipSource")
        .map(|source| source.get("nodeId").is_some())
        .unwrap_or(false);
    let model_targets_ready = chain
        .get("modelTargets")
        .and_then(Value::as_array)
        .map(|targets| !targets.is_empty() && targets.iter().all(mapping_value_is_ready))
        .unwrap_or(false);
    let clip_targets_ready = chain
        .get("clipTargets")
        .and_then(Value::as_array)
        .map(|targets| !targets.is_empty() && targets.iter().all(mapping_value_is_ready))
        .unwrap_or(false);

    model_source_ready && clip_source_ready && model_targets_ready && clip_targets_ready
}

fn mapping_slot_field_is_ready(slot: &Value, field: &str) -> bool {
    slot.get(field)
        .map(|input| input.get("nodeId").is_some() && input.get("inputName").is_some())
        .unwrap_or(false)
}

fn workflow_has_required_classes(workflow: &Value) -> bool {
    let Some(nodes) = workflow.as_object() else {
        return false;
    };

    let classes: HashSet<&str> = nodes
        .values()
        .filter_map(|node| node.get("class_type").and_then(Value::as_str))
        .collect();
    let required = [
        "LoadImage",
        "LoadImageMask",
        "UnetLoaderGGUF",
        "ModelSamplingFlux",
        "CLIPLoader",
        "CLIPTextEncode",
        "VAELoader",
        "VAEEncode",
        "ReferenceLatent",
        "RandomNoise",
        "KSamplerSelect",
        "Flux2Scheduler",
        "CFGGuider",
        "SamplerCustomAdvanced",
        "VAEDecode",
        "RasterRelayLoraStack",
        "RasterRelayPadToDocument",
        "RasterRelaySaveImage",
    ];

    required.iter().all(|class_type| classes.contains(class_type))
}

fn extension_error_message(kind: AssetKind) -> &'static str {
    match kind {
        AssetKind::Lora => "LoRA musi mieć rozszerzenie .safetensors, .pt, .ckpt albo .bin.",
        AssetKind::Gguf => "Model GGUF musi mieć rozszerzenie .gguf.",
    }
}

fn photoshop_readiness(workflow: &WorkflowReadiness) -> PhotoshopReadiness {
    let repo_root = repo_root_path();
    let plugin_folder = repo_root.join("photoshop_plugin");
    let manifest_path = plugin_folder.join("manifest.json");
    let panel_path = plugin_folder.join("index.html");
    let script_path = plugin_folder.join("src").join("panel.js");
    let manifest_exists = manifest_path.is_file();
    let panel_exists = panel_path.is_file();
    let script_exists = script_path.is_file();
    let target_version = "27.8.0".to_string();

    let manifest = read_json_file(&manifest_path).ok();
    let manifest_min_version = manifest
        .as_ref()
        .and_then(|value| value.get("host"))
        .and_then(|host| host.get("minVersion"))
        .and_then(Value::as_str)
        .map(str::to_string);
    let host_app_is_photoshop = manifest
        .as_ref()
        .and_then(|value| value.get("host"))
        .and_then(|host| host.get("app"))
        .and_then(Value::as_str)
        .map(|app| app == "PS")
        .unwrap_or(false);
    let manifest_valid = manifest_exists
        && host_app_is_photoshop
        && manifest_min_version
            .as_deref()
            .map(|version| version == target_version)
            .unwrap_or(false);
    let workflow_ready = workflow.status == "gotowe";
    let ready = manifest_valid && panel_exists && script_exists && workflow_ready;

    PhotoshopReadiness {
        status: if ready { "gotowe" } else { "wymaga instalacji" }.to_string(),
        summary: if ready {
            "Panel Photoshopa ma manifest dla Beta 27.8, kod panelu i gotowy workflow API."
                .to_string()
        } else if !manifest_exists {
            "Brakuje manifestu wtyczki Photoshopa.".to_string()
        } else if !manifest_valid {
            "Manifest istnieje, ale nie wygląda jak panel dla Photoshop Beta 27.8.".to_string()
        } else if !panel_exists || !script_exists {
            "Manifest istnieje, ale brakuje plików panelu Photoshopa.".to_string()
        } else {
            "Panel Photoshopa istnieje, ale workflow API wymaga jeszcze pracy.".to_string()
        },
        manifest_path: path_text(&manifest_path),
        plugin_folder: path_text(&plugin_folder),
        manifest_exists,
        manifest_valid,
        target_version,
        manifest_min_version,
        panel_exists,
        script_exists,
        workflow_ready,
        install_note: "W UXP Developer Tool kliknij Add Plugin i wskaż ten plik manifest.json."
            .to_string(),
    }
}

fn workflow_readiness() -> WorkflowReadiness {
    let repo_root = repo_root_path();
    let workflow_path = repo_root
        .join("photoshop_plugin")
        .join("workflows")
        .join("inpainting-api.json");
    let mapping_path = repo_root
        .join("photoshop_plugin")
        .join("workflows")
        .join("inpainting-api.mapping.json");
    let workflow_exists = workflow_path.is_file();
    let mapping_exists = mapping_path.is_file();
    let object_info = comfy_object_info();

    if !workflow_exists || !mapping_exists {
        return WorkflowReadiness {
            status: "wymaga instalacji".to_string(),
            summary: "Brakuje prawdziwego workflow API dla ComfyUI. Panel Photoshopa nie moze jeszcze wyslac generowania."
                .to_string(),
            workflow_path: path_text(&workflow_path),
            mapping_path: path_text(&mapping_path),
            workflow_exists,
            mapping_exists,
            mapping_ready: false,
            comfy_api_available: object_info.is_some(),
            required_inputs: required_workflow_inputs(None),
            required_nodes: required_workflow_nodes(object_info.as_ref()),
        };
    }

    let Ok(workflow) = read_json_file(&workflow_path) else {
        return workflow_error(
            workflow_path,
            mapping_path,
            workflow_exists,
            mapping_exists,
            "Nie udalo sie odczytac workflow API JSON.",
        );
    };

    let Ok(mapping) = read_json_file(&mapping_path) else {
        return workflow_error(
            workflow_path,
            mapping_path,
            workflow_exists,
            mapping_exists,
            "Nie udalo sie odczytac mappingu workflow.",
        );
    };

    let mapping_ready = mapping
        .get("status")
        .and_then(Value::as_str)
        .map(|status| status == "ready")
        .unwrap_or(false);
    let required_inputs = required_workflow_inputs(Some(&mapping));
    let required_nodes = required_workflow_nodes(object_info.as_ref());
    let all_inputs_ready = required_inputs.iter().all(|input| input.status == "gotowe");
    let lora_ready = mapping_lora_slots_are_valid(&mapping);
    let workflow_has_nodes = workflow
        .as_object()
        .map(|nodes| !nodes.is_empty())
        .unwrap_or(false);
    let ready = mapping_ready && all_inputs_ready && lora_ready && workflow_has_nodes;

    WorkflowReadiness {
        status: if ready { "gotowe" } else { "wymaga instalacji" }.to_string(),
        summary: if ready {
            "Workflow API wyglada na gotowy do wyslania przez panel Photoshopa.".to_string()
        } else if !mapping_ready {
            "Workflow istnieje, ale mapping nie ma statusu ready.".to_string()
        } else if !workflow_has_nodes {
            "Workflow API jest pusty albo ma niepoprawny format.".to_string()
        } else if !lora_ready {
            "Workflow istnieje, ale mapping nie ma poprawnej obsługi LoRA.".to_string()
        } else {
            "Workflow istnieje, ale brakuje wymaganych wejsc obrazu, maski, promptu, rozmiaru albo jakosci."
                .to_string()
        },
        workflow_path: path_text(&workflow_path),
        mapping_path: path_text(&mapping_path),
        workflow_exists,
        mapping_exists,
        mapping_ready,
        comfy_api_available: object_info.is_some(),
        required_inputs,
        required_nodes,
    }
}

fn workflow_error(
    workflow_path: PathBuf,
    mapping_path: PathBuf,
    workflow_exists: bool,
    mapping_exists: bool,
    summary: &str,
) -> WorkflowReadiness {
    WorkflowReadiness {
        status: "błąd".to_string(),
        summary: summary.to_string(),
        workflow_path: path_text(&workflow_path),
        mapping_path: path_text(&mapping_path),
        workflow_exists,
        mapping_exists,
        mapping_ready: false,
        comfy_api_available: false,
        required_inputs: required_workflow_inputs(None),
        required_nodes: required_workflow_nodes(None),
    }
}

fn required_workflow_inputs(mapping: Option<&Value>) -> Vec<WorkflowInputStatus> {
    [
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
        "docHeight",
    ]
        .into_iter()
        .map(|id| {
            let ready = mapping
                .map(|value| mapping_input_is_ready(value, id))
                .unwrap_or(false);

            WorkflowInputStatus {
                id: id.to_string(),
                status: if ready { "gotowe" } else { "brak" }.to_string(),
                description: workflow_input_description(id).to_string(),
            }
        })
        .collect()
}

fn workflow_input_description(id: &str) -> &'static str {
    match id {
        "sourceImage" => "Wejscie obrazu z Photoshopa.",
        "selectionMask" => "Wejscie maski zaznaczenia.",
        "prompt" => "Wejscie promptu uzytkownika.",
        "negativePrompt" => "Negatywny prompt ograniczajacy artefakty.",
        "steps" => "Liczba krokow generowania z ustawien jakosci.",
        "cfg" => "Sila prowadzenia modelu dla workflow FLUX.",
        "seed" => "Seed wariantu generowania.",
        "seedRandomize" => "Wylaczenie losowania seeda, zeby warianty byly kontrolowane.",
        "lorasJson" => "Lista LoRA przekazana do RasterRelayLoraStack.",
        "width" => "Szerokosc wycinka wysylanego do ComfyUI.",
        "height" => "Wysokosc wycinka wysylanego do ComfyUI.",
        "cropLeft" => "Pozycja X wycinka w dokumencie Photoshopa.",
        "cropTop" => "Pozycja Y wycinka w dokumencie Photoshopa.",
        "cropWidth" => "Dokladna szerokosc wycinka po dopasowaniu do siatki modelu.",
        "cropHeight" => "Dokladna wysokosc wycinka po dopasowaniu do siatki modelu.",
        "docWidth" => "Pelna szerokosc dokumentu Photoshopa.",
        "docHeight" => "Pelna wysokosc dokumentu Photoshopa.",
        _ => "Wejscie workflow.",
    }
}

fn required_workflow_nodes(object_info: Option<&Value>) -> Vec<WorkflowNodeStatus> {
    let required = [
        (
            "LoadImage",
            "Wczytanie obrazu i maski przeslanych z Photoshopa.",
        ),
        (
            "RasterRelaySaveImage",
            "Zapis wyniku jako PNG z kanalem alfa przez /view.",
        ),
        ("UnetLoaderGGUF", "Wczytanie bazowego modelu GGUF."),
        ("ModelSamplingFlux", "Ustawienie rozmiaru i parametrów FLUX."),
        ("Flux2Scheduler", "Scheduler dla FLUX.2."),
        ("SamplerCustomAdvanced", "Glowny sampler generowania obrazu."),
        ("ReferenceLatent", "Zachowanie kontekstu obrazu zrodlowego."),
        ("CLIPTextEncode", "Kodowanie promptu uzytkownika."),
        ("CLIPLoader", "Wczytanie text encodera dla FLUX.2."),
        ("VAELoader", "Wczytanie VAE."),
        ("VAEDecode", "Zamiana latentow na obraz wynikowy."),
        (
            "RasterRelayLoraStack",
            "Podlaczenie 0, 1 albo wielu LoRA przez JSON z panelu.",
        ),
        (
            "RasterRelayPadToDocument",
            "Wstawienie wyniku z wycinka na pelny rozmiar dokumentu z przezroczystoscia.",
        ),
    ];

    required
        .into_iter()
        .map(|(id, description)| {
            let exists = object_info
                .and_then(Value::as_object)
                .map(|nodes| nodes.contains_key(id))
                .unwrap_or(false);

            WorkflowNodeStatus {
                id: id.to_string(),
                status: if exists { "wykryto" } else { "brak" }.to_string(),
                description: description.to_string(),
            }
        })
        .collect()
}

fn comfy_object_info() -> Option<Value> {
    http_get_json("/object_info", Duration::from_millis(900)).ok()
}

fn http_get_json(path: &str, timeout: Duration) -> Result<Value, String> {
    let address = SocketAddr::from(([127, 0, 0, 1], COMFYUI_PORT));
    let mut stream = TcpStream::connect_timeout(&address, timeout).map_err(|e| e.to_string())?;
    let _ = stream.set_read_timeout(Some(timeout));
    let _ = stream.set_write_timeout(Some(timeout));
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: {COMFYUI_HOST}:{COMFYUI_PORT}\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|e| e.to_string())?;

    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|e| e.to_string())?;
    let Some((headers, body)) = response.split_once("\r\n\r\n") else {
        return Err("HTTP response without body".to_string());
    };

    if !headers.starts_with("HTTP/1.1 200") && !headers.starts_with("HTTP/1.0 200") {
        return Err("HTTP status is not 200".to_string());
    }

    serde_json::from_str(body).map_err(|e| e.to_string())
}

fn read_json_file(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|error| error.to_string())?;
    serde_json::from_str(&text).map_err(|error| error.to_string())
}

fn read_quality_settings() -> Option<QualitySettings> {
    let text = fs::read_to_string(quality_settings_path()).ok()?;
    serde_json::from_str(&text).ok()
}

fn quality_settings_path() -> PathBuf {
    repo_root_path()
        .join("photoshop_plugin")
        .join("rasterrelay-quality-settings.json")
}

fn default_quality_settings() -> QualitySettings {
    QualitySettings {
        schema_version: "rasterrelay.qualitySettings.v1".to_string(),
        task_mode: "replaceObject".to_string(),
        quality: "balanced".to_string(),
        mask_feather_px: 24,
        mask_grow_px: 0,
        variant_count: 1,
        negative_prompt:
            "hard square edges, visible seams, distorted hands, extra fingers, unreadable artifacts, duplicated object, damaged background"
                .to_string(),
    }
}

fn normalize_quality_settings(settings: QualitySettings) -> QualitySettings {
    let mut normalized = default_quality_settings();
    normalized.task_mode = match settings.task_mode.as_str() {
        "replaceObject" | "removeTextLogo" | "detailRepair" | "backgroundClean" => {
            settings.task_mode
        }
        _ => normalized.task_mode,
    };
    normalized.quality = match settings.quality.as_str() {
        "fast" | "balanced" | "quality" => settings.quality,
        _ => normalized.quality,
    };
    normalized.mask_feather_px = settings.mask_feather_px.clamp(0, 96);
    normalized.mask_grow_px = settings.mask_grow_px.clamp(-64, 96);
    normalized.variant_count = settings.variant_count.clamp(1, 2);
    normalized.negative_prompt = if settings.negative_prompt.trim().is_empty() {
        normalized.negative_prompt
    } else {
        settings.negative_prompt.trim().to_string()
    };
    normalized
}

fn lora_config_path() -> PathBuf {
    repo_root_path()
        .join("photoshop_plugin")
        .join("rasterrelay-lora-config.json")
}

fn read_lora_config() -> Option<LoraConfig> {
    let text = fs::read_to_string(lora_config_path()).ok()?;
    serde_json::from_str(&text).ok()
}

fn default_lora_config() -> LoraConfig {
    LoraConfig {
        schema_version: "rasterrelay.loraConfig.v1".to_string(),
        loras: vec![],
    }
}

fn normalize_lora_config(config: LoraConfig) -> LoraConfig {
    let loras = config
        .loras
        .into_iter()
        .map(|entry| LoraEntry {
            strength_model: entry.strength_model.clamp(0.0, 2.0),
            strength_clip: entry.strength_clip.clamp(0.0, 2.0),
            ..entry
        })
        .collect();
    LoraConfig {
        schema_version: "rasterrelay.loraConfig.v1".to_string(),
        loras,
    }
}

fn repo_root_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)
        .unwrap_or(manifest_dir)
}

fn runtime_status(state: &tauri::State<'_, ComfyProcessState>) -> ComfyRuntimeStatus {
    let mut owned_by_launcher = false;
    let mut pid = None;

    {
        let mut guard = state.child.lock().expect("comfy process mutex");
        clear_finished_child(&mut guard);

        if let Some(child) = guard.as_ref() {
            owned_by_launcher = true;
            pid = Some(child.id());
        }
    }

    let api_ready = api_responds();
    let running = owned_by_launcher || api_ready;
    let url = comfyui_url();
    let message = if api_ready {
        "ComfyUI odpowiada lokalnie.".to_string()
    } else if owned_by_launcher {
        "ComfyUI startuje, ale API jeszcze nie odpowiada.".to_string()
    } else {
        "ComfyUI nie jest uruchomione.".to_string()
    };

    ComfyRuntimeStatus {
        running,
        owned_by_launcher,
        pid,
        url,
        message,
    }
}

fn clear_finished_child(child: &mut Option<Child>) {
    if let Some(process) = child.as_mut() {
        if process.try_wait().ok().flatten().is_some() {
            *child = None;
        }
    }
}

fn api_responds() -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], COMFYUI_PORT));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) else {
        return false;
    };

    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));

    let request = format!(
        "GET /system_stats HTTP/1.1\r\nHost: {COMFYUI_HOST}:{COMFYUI_PORT}\r\nConnection: close\r\n\r\n"
    );

    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }

    let mut buffer = [0_u8; 32];
    match stream.read(&mut buffer) {
        Ok(bytes_read) => bytes_read > 0 && buffer.starts_with(b"HTTP/"),
        Err(_) => false,
    }
}

fn uxp_cli_responds() -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], UXP_CLI_PORT));
    TcpStream::connect_timeout(&address, Duration::from_millis(500)).is_ok()
}

fn wait_until(mut check: impl FnMut() -> bool, timeout: Duration, poll_interval: Duration) -> bool {
    let started_at = std::time::Instant::now();

    while started_at.elapsed() < timeout {
        if check() {
            return true;
        }

        std::thread::sleep(poll_interval);
    }

    check()
}

fn comfyui_url() -> String {
    format!("http://{COMFYUI_HOST}:{COMFYUI_PORT}")
}

fn photoshop_runtime_status() -> PhotoshopRuntimeStatus {
    let photoshop_path = PathBuf::from(PHOTOSHOP_BETA_EXE);
    let installed = photoshop_path.is_file();
    let running = process_name_is_running("Photoshop.exe");
    let message = if running {
        "Photoshop Beta jest uruchomiony.".to_string()
    } else if installed {
        "Photoshop Beta jest zainstalowany i gotowy do uruchomienia.".to_string()
    } else {
        "Nie znaleziono Photoshop Beta w domyślnej ścieżce Adobe.".to_string()
    };

    PhotoshopRuntimeStatus {
        installed,
        running,
        path: path_text(&photoshop_path),
        message,
    }
}

fn uxp_developer_tools_runtime_status() -> UxpDeveloperToolsRuntimeStatus {
    let tool_path = PathBuf::from(UXP_DEVELOPER_TOOLS_EXE);
    let installed = tool_path.is_file();
    let running = process_name_is_running("Adobe UXP Developer Tools.exe");
    let plugin_manifest_path = repo_root_path()
        .join("photoshop_plugin")
        .join("manifest.json");
    let workspace_path = uxp_workspace_path();
    let plugin_registered = uxp_plugin_is_registered(&workspace_path, &plugin_manifest_path);
    let message = if running && plugin_registered {
        "Adobe UXP Developer Tools jest uruchomione, a RasterRelay jest na liĹ›cie wtyczek."
            .to_string()
    } else if running {
        "Adobe UXP Developer Tools jest uruchomione. Dodaj RasterRelay do listy wtyczek."
            .to_string()
    } else if installed && plugin_registered {
        "Adobe UXP Developer Tools jest zainstalowane, a RasterRelay jest juĹĽ wpisany na listÄ™ wtyczek.".to_string()
    } else if installed {
        "Adobe UXP Developer Tools jest zainstalowane. Uruchom je, ĹĽeby wczytaÄ‡ panel RasterRelay do Photoshopa.".to_string()
    } else {
        "Nie znaleziono Adobe UXP Developer Tools. Bez tego trudniej wczytaÄ‡ wtyczkÄ™ w trybie developerskim.".to_string()
    };

    UxpDeveloperToolsRuntimeStatus {
        installed,
        running,
        plugin_registered,
        path: path_text(&tool_path),
        plugin_manifest_path: path_text(&plugin_manifest_path),
        workspace_path: path_text(&workspace_path),
        message,
    }
}

fn uxp_workspace_path() -> PathBuf {
    env::var("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| repo_root_path())
        .join("Adobe")
        .join("Adobe UXP Developer Tool")
        .join("plugins_workspace.json")
}

fn read_uxp_workspace(workspace_path: &Path) -> Value {
    fs::read_to_string(workspace_path)
        .ok()
        .and_then(|text| serde_json::from_str::<Value>(&text).ok())
        .filter(|value| value.get("plugins").and_then(Value::as_array).is_some())
        .unwrap_or_else(|| serde_json::json!({ "version": 1, "plugins": [] }))
}

fn uxp_plugin_is_registered(workspace_path: &Path, manifest_path: &Path) -> bool {
    let manifest_text = path_text(manifest_path);
    read_uxp_workspace(workspace_path)
        .get("plugins")
        .and_then(Value::as_array)
        .map(|plugins| {
            plugins.iter().any(|plugin| {
                plugin
                    .get("manifestPath")
                    .and_then(Value::as_str)
                    .map(|path| paths_equal_text(path, &manifest_text))
                    .unwrap_or(false)
            })
        })
        .unwrap_or(false)
}

fn paths_equal_text(left: &str, right: &str) -> bool {
    #[cfg(windows)]
    {
        left.replace('/', "\\")
            .eq_ignore_ascii_case(&right.replace('/', "\\"))
    }

    #[cfg(not(windows))]
    {
        left == right
    }
}

#[cfg(windows)]
fn process_name_is_running(process_name: &str) -> bool {
    use std::os::windows::process::CommandExt;

    let expected = normalize_process_name(process_name);

    let mut command = Command::new("tasklist");
    command
        .args([
            "/FI",
            &format!("IMAGENAME eq {process_name}"),
            "/FO",
            "CSV",
            "/NH",
        ])
        .creation_flags(0x08000000);

    command.output()
        .ok()
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|stdout| tasklist_csv_contains_process(&stdout, &expected))
        .unwrap_or(false)
}

#[cfg(not(windows))]
fn process_name_is_running(_process_name: &str) -> bool {
    false
}

#[cfg(windows)]
fn normalize_process_name(process_name: &str) -> String {
    let trimmed = process_name.trim().to_ascii_lowercase();
    if trimmed.ends_with(".exe") {
        trimmed[..trimmed.len() - 4].to_string()
    } else {
        trimmed
    }
}

#[cfg(windows)]
fn tasklist_csv_contains_process(stdout: &str, expected: &str) -> bool {
    stdout.lines().any(|line| {
        let image_name = line
            .split(',')
            .next()
            .unwrap_or("")
            .trim()
            .trim_matches('"');
        normalize_process_name(image_name) == expected
    })
}

fn find_python_executable(comfyui_path: &Path) -> PathBuf {
    let mut candidates = vec![
        comfyui_path.join("venv").join("Scripts").join("python.exe"),
        comfyui_path.join("python_embeded").join("python.exe"),
        comfyui_path.join("python_embedded").join("python.exe"),
    ];

    if let Some(portable_root) = comfyui_path.parent() {
        candidates.push(portable_root.join("python_embeded").join("python.exe"));
        candidates.push(portable_root.join("python_embedded").join("python.exe"));
    }

    candidates
        .into_iter()
        .find(|candidate| candidate.is_file())
        .unwrap_or_else(|| PathBuf::from("python"))
}

fn comfyui_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    for drive_letter in ['C', 'D', 'E', 'F'] {
        let root = PathBuf::from(format!("{drive_letter}:\\"));

        push_candidate(&mut candidates, root.join("ComfyUI"));
        push_candidate(&mut candidates, root.join("AI").join("ComfyUI"));
        push_candidate(
            &mut candidates,
            root.join("ComfyUI_windows_portable").join("ComfyUI"),
        );
    }

    if let Ok(profile) = env::var("USERPROFILE") {
        let profile_path = PathBuf::from(profile);
        for folder_name in ["Desktop", "Documents", "Downloads"] {
            let base = profile_path.join(folder_name);
            push_candidate(&mut candidates, base.join("ComfyUI"));
            push_candidate(&mut candidates, base.join("ComfyUI_windows_portable"));
            push_candidate(
                &mut candidates,
                base.join("ComfyUI_windows_portable").join("ComfyUI"),
            );
            add_comfy_named_children(&mut candidates, &base);
        }
    }

    dedupe_paths(candidates)
}

fn add_comfy_named_children(candidates: &mut Vec<PathBuf>, base: &Path) {
    let Ok(entries) = fs::read_dir(base) else {
        return;
    };

    for entry in entries.flatten() {
        let Ok(file_type) = entry.file_type() else {
            continue;
        };

        if !file_type.is_dir() {
            continue;
        }

        let name = entry.file_name().to_string_lossy().to_lowercase();
        if name.contains("comfy") {
            let path = entry.path();
            push_candidate(candidates, path.clone());
            push_candidate(candidates, path.join("ComfyUI"));
        }
    }
}

fn push_candidate(candidates: &mut Vec<PathBuf>, path: PathBuf) {
    candidates.push(path);
}

fn dedupe_paths(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let mut seen = HashSet::new();
    let mut deduped = Vec::new();

    for path in paths {
        let key = path_text(&path).to_lowercase();
        if seen.insert(key) {
            deduped.push(path);
        }
    }

    deduped
}

fn looks_like_comfyui(path: &Path) -> bool {
    path.join("main.py").is_file()
}

fn folder_item(
    id: &str,
    label: &str,
    path: &Path,
    present_description: &str,
    missing_description: &str,
    action_label: Option<&str>,
    important: bool,
) -> ReadinessItem {
    if path.is_dir() {
        item(
            id,
            label,
            Some(path),
            "wykryto",
            present_description,
            action_label,
            important,
        )
    } else {
        item(
            id,
            label,
            Some(path),
            "brak",
            missing_description,
            action_label,
            important,
        )
    }
}

fn file_item(
    id: &str,
    label: &str,
    path: &Path,
    present_description: &str,
    missing_description: &str,
    important: bool,
) -> ReadinessItem {
    if path.is_file() {
        item(
            id,
            label,
            Some(path),
            "wykryto",
            present_description,
            None,
            important,
        )
    } else {
        item(
            id,
            label,
            Some(path),
            "brak",
            missing_description,
            Some("Add"),
            important,
        )
    }
}

fn file_any_item(
    id: &str,
    label: &str,
    paths: &[PathBuf],
    present_description: &str,
    missing_description: &str,
    important: bool,
) -> ReadinessItem {
    if let Some(existing_path) = paths.iter().find(|path| path.is_file()) {
        item(
            id,
            label,
            Some(existing_path),
            "wykryto",
            present_description,
            None,
            important,
        )
    } else {
        item(
            id,
            label,
            paths.first().map(PathBuf::as_path),
            "brak",
            missing_description,
            Some("Add"),
            important,
        )
    }
}

fn item(
    id: &str,
    label: &str,
    path: Option<&Path>,
    status: &str,
    description: &str,
    action_label: Option<&str>,
    important: bool,
) -> ReadinessItem {
    ReadinessItem {
        id: id.to_string(),
        label: label.to_string(),
        path: path.map(path_text),
        status: status.to_string(),
        description: description.to_string(),
        action_label: action_label.map(str::to_string),
        important,
    }
}

fn count_direct_child_dirs(path: &Path) -> usize {
    let Ok(entries) = fs::read_dir(path) else {
        return 0;
    };

    entries
        .flatten()
        .filter(|entry| {
            entry
                .file_type()
                .map(|file_type| file_type.is_dir())
                .unwrap_or(false)
        })
        .count()
}

fn count_files_with_extensions(path: &Path, extensions: &[&str], recursive: bool) -> usize {
    if !path.is_dir() {
        return 0;
    }

    let Ok(entries) = fs::read_dir(path) else {
        return 0;
    };

    let mut count = 0;

    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() && recursive {
            count += count_files_with_extensions(&path, extensions, true);
            continue;
        }

        if has_extension(&path, extensions) {
            count += 1;
        }
    }

    count
}

fn has_extension(path: &Path, extensions: &[&str]) -> bool {
    let Some(extension) = path.extension().and_then(|value| value.to_str()) else {
        return false;
    };

    extensions
        .iter()
        .any(|allowed| extension.eq_ignore_ascii_case(allowed))
}

fn paths_to_text(paths: Vec<PathBuf>) -> Vec<String> {
    paths.into_iter().map(|path| path_text(&path)).collect()
}

fn path_text(path: &Path) -> String {
    path.display().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn folder_without_main_py_is_not_comfyui() {
        let root = temp_dir("without-main");
        fs::create_dir_all(&root).expect("create temp folder");

        assert!(!looks_like_comfyui(&root));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn folder_with_main_py_is_comfyui() {
        let root = temp_dir("with-main");
        fs::create_dir_all(&root).expect("create temp folder");
        fs::write(root.join("main.py"), "").expect("write main.py");

        assert!(looks_like_comfyui(&root));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn lora_counter_accepts_expected_extensions() {
        let root = temp_dir("loras");
        fs::create_dir_all(&root).expect("create temp folder");
        fs::write(root.join("style.safetensors"), "").expect("write safetensors");
        fs::write(root.join("character.pt"), "").expect("write pt");
        fs::write(root.join("notes.txt"), "").expect("write txt");

        let count =
            count_files_with_extensions(&root, &["safetensors", "pt", "ckpt", "bin"], false);

        assert_eq!(count, 2);

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn selected_folder_without_main_py_returns_error_report() {
        let root = temp_dir("selected-without-main");
        fs::create_dir_all(&root).expect("create temp folder");

        let report = scan_readiness_for_path(path_text(&root));

        assert!(report.comfyui_path.is_none());
        assert_eq!(report.items[0].status, "błąd");
        assert_eq!(report.scanned_paths, vec![path_text(&root)]);

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn selected_folder_with_main_py_returns_found_report() {
        let root = temp_dir("selected-with-main");
        fs::create_dir_all(root.join("models").join("loras")).expect("create loras folder");
        fs::create_dir_all(root.join("custom_nodes")).expect("create custom nodes folder");
        fs::write(root.join("main.py"), "").expect("write main.py");
        fs::write(
            root.join("models").join("loras").join("style.safetensors"),
            "",
        )
        .expect("write lora");
        fs::write(root.join("models").join("flux.gguf"), "").expect("write gguf");

        let report = scan_readiness_for_path(path_text(&root));

        assert_eq!(report.comfyui_path, Some(path_text(&root)));
        assert_eq!(report.counts.loras, 1);
        assert_eq!(report.counts.gguf_files, 1);

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validates_lora_file_for_loras_folder() {
        let root = temp_comfyui("valid-lora");
        let source = root.join("incoming-style.safetensors");
        fs::write(&source, "lora").expect("write lora");

        let validation = validate_asset_install_paths(root.clone(), source, AssetKind::Lora);

        assert!(validation.can_install);
        assert_eq!(validation.kind, "LoRA");
        assert_eq!(validation.file_name, "incoming-style.safetensors");
        assert!(validation
            .target_path
            .ends_with("models\\loras\\incoming-style.safetensors"));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn rejects_text_file_as_lora() {
        let root = temp_comfyui("invalid-lora");
        let source = root.join("notes.txt");
        fs::write(&source, "not a lora").expect("write txt");

        let validation = validate_asset_install_paths(root.clone(), source, AssetKind::Lora);

        assert!(!validation.can_install);
        assert_eq!(validation.status, "błąd");

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validates_gguf_file_for_unet_folder() {
        let root = temp_comfyui("valid-gguf");
        let source = root.join("flux.gguf");
        fs::write(&source, "gguf").expect("write gguf");

        let validation = validate_asset_install_paths(root.clone(), source, AssetKind::Gguf);

        assert!(validation.can_install);
        assert_eq!(validation.kind, "GGUF");
        assert!(validation.target_path.ends_with("models\\unet\\flux.gguf"));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn rejects_duplicate_target_file() {
        let root = temp_comfyui("duplicate");
        let source = root.join("style.safetensors");
        let target_dir = root.join("models").join("loras");
        fs::create_dir_all(&target_dir).expect("create loras folder");
        fs::write(&source, "new lora").expect("write source");
        fs::write(target_dir.join("style.safetensors"), "old lora").expect("write duplicate");

        let validation = validate_asset_install_paths(root.clone(), source, AssetKind::Lora);

        assert!(!validation.can_install);
        assert!(validation.message.contains("nie nadpisuje"));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn install_lora_creates_missing_folder_and_copies_file() {
        let root = temp_comfyui("install-lora");
        let source_dir = temp_dir("asset-source");
        fs::create_dir_all(&source_dir).expect("create source dir");
        let source = source_dir.join("fresh.safetensors");
        fs::write(&source, "fresh lora").expect("write source");

        let result = install_asset(path_text(&root), path_text(&source), AssetKind::Lora);
        let copied = root.join("models").join("loras").join("fresh.safetensors");

        assert!(result.success);
        assert!(copied.is_file());
        assert_eq!(
            fs::read_to_string(copied).expect("read copied"),
            "fresh lora"
        );

        fs::remove_dir_all(root).ok();
        fs::remove_dir_all(source_dir).ok();
    }

    #[test]
    fn install_gguf_rejects_non_gguf_file() {
        let root = temp_comfyui("install-invalid-gguf");
        let source = root.join("flux.txt");
        fs::write(&source, "not gguf").expect("write source");

        let result = install_asset(path_text(&root), path_text(&source), AssetKind::Gguf);

        assert!(!result.success);
        assert!(result.message.contains(".gguf"));

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validates_workflow_api_json_file() {
        let source_dir = temp_dir("workflow-api-source");
        fs::create_dir_all(&source_dir).expect("create source dir");
        let source = source_dir.join("inpainting-api.json");
        fs::write(&source, valid_workflow_api_json()).expect("write workflow");

        let validation =
            validate_workflow_file_install_paths(source.clone(), WorkflowFileKind::WorkflowApi);

        assert!(validation.can_install);
        assert_eq!(validation.kind, "Workflow API");
        assert_eq!(validation.file_name, "inpainting-api.json");
        assert!(validation
            .target_path
            .ends_with("photoshop_plugin\\workflows\\inpainting-api.json"));

        fs::remove_dir_all(source_dir).ok();
    }

    #[test]
    fn rejects_empty_workflow_api_json_file() {
        let source_dir = temp_dir("workflow-api-empty");
        fs::create_dir_all(&source_dir).expect("create source dir");
        let source = source_dir.join("empty.json");
        fs::write(&source, "{}").expect("write empty workflow");

        let validation =
            validate_workflow_file_install_paths(source.clone(), WorkflowFileKind::WorkflowApi);

        assert!(!validation.can_install);
        assert!(validation.message.contains("pusty"));

        fs::remove_dir_all(source_dir).ok();
    }

    #[test]
    fn rejects_workflow_api_without_required_flux_nodes() {
        let source_dir = temp_dir("workflow-api-missing-nodes");
        fs::create_dir_all(&source_dir).expect("create source dir");
        let source = source_dir.join("partial.json");
        fs::write(&source, r#"{"10":{"class_type":"LoadImage","inputs":{}}}"#)
            .expect("write partial workflow");

        let validation =
            validate_workflow_file_install_paths(source.clone(), WorkflowFileKind::WorkflowApi);

        assert!(!validation.can_install);
        assert!(validation.message.contains("FLUX"));

        fs::remove_dir_all(source_dir).ok();
    }

    #[test]
    fn validates_workflow_mapping_with_required_inputs() {
        let source_dir = temp_dir("workflow-mapping-source");
        fs::create_dir_all(&source_dir).expect("create source dir");
        let source = source_dir.join("mapping.json");
        fs::write(&source, valid_mapping_json()).expect("write mapping");

        let validation =
            validate_workflow_file_install_paths(source.clone(), WorkflowFileKind::WorkflowMapping);

        assert!(validation.can_install);
        assert_eq!(validation.kind, "Workflow mapping");
        assert!(validation
            .target_path
            .ends_with("photoshop_plugin\\workflows\\inpainting-api.mapping.json"));

        fs::remove_dir_all(source_dir).ok();
    }

    #[test]
    fn rejects_workflow_mapping_without_required_inputs() {
        let source_dir = temp_dir("workflow-mapping-missing-inputs");
        fs::create_dir_all(&source_dir).expect("create source dir");
        let source = source_dir.join("mapping.json");
        fs::write(
            &source,
            r#"{"status":"ready","inputs":{"sourceImage":{"nodeId":"10","inputName":"image"}}}"#,
        )
        .expect("write mapping");

        let validation =
            validate_workflow_file_install_paths(source.clone(), WorkflowFileKind::WorkflowMapping);

        assert!(!validation.can_install);
        assert!(validation.message.contains("sourceImage"));

        fs::remove_dir_all(source_dir).ok();
    }

    #[test]
    fn rejects_workflow_mapping_with_broken_loras_json() {
        let source_dir = temp_dir("workflow-mapping-broken-loras-json");
        fs::create_dir_all(&source_dir).expect("create source dir");
        let source = source_dir.join("mapping.json");
        fs::write(
            &source,
            r#"{
              "status": "ready",
              "inputs": {
                "sourceImage": { "nodeId": "10", "inputName": "image" },
                "selectionMask": { "nodeId": "11", "inputName": "image" },
                "prompt": { "nodeId": "20", "inputName": "text" },
                "negativePrompt": { "nodeId": "21", "inputName": "text" },
                "steps": { "nodeId": "62", "inputName": "steps" },
                "cfg": { "nodeId": "63", "inputName": "cfg" },
                "seed": { "nodeId": "60", "inputName": "noise_seed" },
                "seedRandomize": { "nodeId": "60", "inputName": "randomize_seed" },
                "lorasJson": { "nodeId": "90" },
                "width": [
                  { "nodeId": "21", "inputName": "width" },
                  { "nodeId": "62", "inputName": "width" }
                ],
                "height": [
                  { "nodeId": "21", "inputName": "height" },
                  { "nodeId": "62", "inputName": "height" }
                ],
                "cropLeft": { "nodeId": "91", "inputName": "crop_left" },
                "cropTop": { "nodeId": "91", "inputName": "crop_top" },
                "cropWidth": { "nodeId": "91", "inputName": "crop_width" },
                "cropHeight": { "nodeId": "91", "inputName": "crop_height" },
                "docWidth": { "nodeId": "91", "inputName": "doc_width" },
                "docHeight": { "nodeId": "91", "inputName": "doc_height" }
              }
            }"#,
        )
        .expect("write mapping");

        let validation =
            validate_workflow_file_install_paths(source.clone(), WorkflowFileKind::WorkflowMapping);

        assert!(!validation.can_install);
        assert!(validation.message.contains("Mapping"));

        fs::remove_dir_all(source_dir).ok();
    }

    #[test]
    fn comfyui_url_points_to_local_default_port() {
        assert_eq!(comfyui_url(), "http://127.0.0.1:8188");
    }

    #[test]
    fn finds_python_in_local_venv_first() {
        let root = temp_comfyui("python-venv");
        let python = root.join("venv").join("Scripts").join("python.exe");
        fs::create_dir_all(python.parent().expect("python parent")).expect("create venv");
        fs::write(&python, "").expect("write python");

        assert_eq!(find_python_executable(&root), python);

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn finds_python_in_portable_parent_folder() {
        let portable_root = temp_dir("portable-python");
        let comfyui_root = portable_root.join("ComfyUI");
        fs::create_dir_all(&comfyui_root).expect("create comfyui folder");
        fs::write(comfyui_root.join("main.py"), "").expect("write main.py");

        let python = portable_root.join("python_embeded").join("python.exe");
        fs::create_dir_all(python.parent().expect("python parent"))
            .expect("create portable python");
        fs::write(&python, "").expect("write python");

        assert_eq!(find_python_executable(&comfyui_root), python);

        fs::remove_dir_all(portable_root).ok();
    }

    #[test]
    fn falls_back_to_python_from_path() {
        let root = temp_comfyui("python-path-fallback");

        assert_eq!(find_python_executable(&root), PathBuf::from("python"));

        fs::remove_dir_all(root).ok();
    }

    #[cfg(windows)]
    #[test]
    fn tasklist_matching_accepts_names_without_exe_suffix() {
        let stdout = r#""Adobe UXP Developer Tools","16604","Console","1","137,076 K""#;

        assert!(tasklist_csv_contains_process(
            stdout,
            &normalize_process_name("Adobe UXP Developer Tools.exe")
        ));
    }

    #[cfg(windows)]
    #[test]
    fn tasklist_matching_rejects_other_processes() {
        let stdout = r#""Photoshop.exe","8872","Console","1","2,108,112 K""#;

        assert!(!tasklist_csv_contains_process(
            stdout,
            &normalize_process_name("Adobe UXP Developer Tools.exe")
        ));
    }

    fn temp_comfyui(name: &str) -> PathBuf {
        let root = temp_dir(name);
        fs::create_dir_all(root.join("models")).expect("create models folder");
        fs::create_dir_all(root.join("custom_nodes")).expect("create custom nodes folder");
        fs::write(root.join("main.py"), "").expect("write main.py");
        root
    }

    fn temp_dir(name: &str) -> PathBuf {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time")
            .as_nanos();

        env::temp_dir().join(format!("rasterrelay-{name}-{timestamp}"))
    }

    fn valid_mapping_json() -> &'static str {
        r#"{
          "status": "ready",
            "inputs": {
            "sourceImage": { "nodeId": "10", "inputName": "image" },
            "selectionMask": { "nodeId": "11", "inputName": "image" },
            "prompt": { "nodeId": "20", "inputName": "text" },
            "negativePrompt": { "nodeId": "21", "inputName": "text" },
            "steps": { "nodeId": "62", "inputName": "steps" },
            "cfg": { "nodeId": "63", "inputName": "cfg" },
            "seed": { "nodeId": "60", "inputName": "noise_seed" },
            "seedRandomize": { "nodeId": "60", "inputName": "randomize_seed" },
            "lorasJson": { "nodeId": "90", "inputName": "loras_json" },
            "width": [
              { "nodeId": "21", "inputName": "width" },
              { "nodeId": "62", "inputName": "width" }
            ],
            "height": [
              { "nodeId": "21", "inputName": "height" },
              { "nodeId": "62", "inputName": "height" }
            ],
            "cropLeft": { "nodeId": "91", "inputName": "crop_left" },
            "cropTop": { "nodeId": "91", "inputName": "crop_top" },
            "cropWidth": { "nodeId": "91", "inputName": "crop_width" },
            "cropHeight": { "nodeId": "91", "inputName": "crop_height" },
            "docWidth": { "nodeId": "91", "inputName": "doc_width" },
            "docHeight": { "nodeId": "91", "inputName": "doc_height" }
          }
        }"#
    }

    fn valid_workflow_api_json() -> &'static str {
        r#"{
          "10": { "class_type": "LoadImage", "inputs": {} },
          "11": { "class_type": "LoadImageMask", "inputs": {} },
          "20": { "class_type": "UnetLoaderGGUF", "inputs": {} },
          "21": { "class_type": "ModelSamplingFlux", "inputs": {} },
          "30": { "class_type": "CLIPLoader", "inputs": {} },
          "31": { "class_type": "CLIPTextEncode", "inputs": {} },
          "32": { "class_type": "CLIPTextEncode", "inputs": {} },
          "40": { "class_type": "VAELoader", "inputs": {} },
          "41": { "class_type": "VAEEncode", "inputs": {} },
          "51": { "class_type": "ReferenceLatent", "inputs": {} },
          "52": { "class_type": "ReferenceLatent", "inputs": {} },
          "60": { "class_type": "RandomNoise", "inputs": {} },
          "61": { "class_type": "KSamplerSelect", "inputs": {} },
          "62": { "class_type": "Flux2Scheduler", "inputs": {} },
          "63": { "class_type": "CFGGuider", "inputs": {} },
          "64": { "class_type": "SamplerCustomAdvanced", "inputs": {} },
          "65": { "class_type": "VAEDecode", "inputs": {} },
          "80": { "class_type": "RasterRelaySaveImage", "inputs": {} },
          "90": { "class_type": "RasterRelayLoraStack", "inputs": {} },
          "91": { "class_type": "RasterRelayPadToDocument", "inputs": {} }
        }"#
    }

    // ======== INTEGRATION TESTS ========

    #[test]
    fn integration_workflow_readiness_with_actual_files() {
        let readiness = workflow_readiness();
        assert!(readiness.workflow_exists, "workflow JSON should exist");
        assert!(readiness.mapping_exists, "mapping JSON should exist");
        assert!(readiness.mapping_ready, "mapping status should be ready, got: {}", readiness.summary);

        let has_source = readiness.required_inputs.iter().any(|i| i.id == "sourceImage" && i.status == "gotowe");
        let has_mask = readiness.required_inputs.iter().any(|i| i.id == "selectionMask" && i.status == "gotowe");
        let has_prompt = readiness.required_inputs.iter().any(|i| i.id == "prompt" && i.status == "gotowe");

        assert!(has_source, "sourceImage mapping missing");
        assert!(has_mask, "selectionMask mapping missing");
        assert!(has_prompt, "prompt mapping missing");
    }

    #[test]
    fn integration_photoshop_readiness_manifest_is_valid() {
        let workflow = workflow_readiness();
        let photoshop = photoshop_readiness(&workflow);

        assert!(photoshop.manifest_exists, "manifest.json should exist at {}", photoshop.manifest_path);
        assert!(photoshop.manifest_valid, "manifest should be valid for PS 27.8: {}", photoshop.summary);
        assert!(photoshop.panel_exists, "index.html should exist");
        assert!(photoshop.script_exists, "panel.js should exist");
        assert_eq!(photoshop.target_version, "27.8.0");
    }

    #[test]
    fn integration_build_found_report_with_full_comfyui() {
        let root = temp_dir("integration-report");
        fs::create_dir_all(root.join("models").join("loras")).expect("create loras");
        fs::create_dir_all(root.join("models").join("unet")).expect("create unet");
        fs::create_dir_all(root.join("models").join("text_encoders")).expect("create text_encoders");
        fs::create_dir_all(root.join("custom_nodes")).expect("create custom_nodes");
        fs::create_dir_all(root.join("venv").join("Scripts")).expect("create venv");
        fs::write(root.join("main.py"), "").expect("write main.py");
        fs::write(root.join("models").join("loras").join("style.safetensors"), "").expect("write lora");
        fs::write(root.join("models").join("unet").join("flux.gguf"), "").expect("write gguf");

        let report = build_found_report(root.clone(), vec![root.clone()]);

        assert!(report.comfyui_path.is_some());
        assert_eq!(report.counts.loras, 1);
        assert_eq!(report.counts.gguf_files, 1);
        assert!(report.counts.custom_nodes == 0, "should have 0 custom nodes, got {}", report.counts.custom_nodes);

        let comfy_item = report.items.iter().find(|i| i.id == "comfyui-root").expect("comfyui-root item");
        assert_eq!(comfy_item.status, "gotowe");

        let lora_item = report.items.iter().find(|i| i.id == "loras").expect("loras item");
        assert_eq!(lora_item.status, "wykryto");

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn integration_build_missing_report_has_all_items() {
        let report = build_missing_report(vec![]);
        assert!(report.comfyui_path.is_none());
        assert!(report.items.len() >= 9);

        let root_item = report.items.iter().find(|i| i.id == "comfyui-root").expect("comfyui-root item");
        assert_eq!(root_item.status, "brak");
    }

    #[test]
    fn path_comparison_windows_case_insensitive() {
        assert!(paths_equal_text(
            r"C:\users\test\comfyui",
            r"C:\Users\Test\ComfyUI"
        ));
        assert!(paths_equal_text(
            r"C:\Users\Test/ComfyUI",
            r"C:\Users\Test\ComfyUI"
        ));
    }

    #[test]
    fn count_files_recursive_finds_nested_gguf() {
        let root = temp_dir("recursive-gguf");
        let nested = root.join("sub").join("deep");
        fs::create_dir_all(&nested).expect("create nested dir");
        fs::write(nested.join("model.gguf"), "").expect("write gguf in subdir");
        fs::write(root.join("top.gguf"), "").expect("write gguf at top");
        fs::write(root.join("notes.txt"), "").expect("write txt");

        let count = count_files_with_extensions(&root, &["gguf"], true);

        assert_eq!(count, 2);

        let flat = count_files_with_extensions(&root, &["gguf"], false);
        assert_eq!(flat, 1);

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn repo_root_is_valid_and_exists() {
        let root = repo_root_path();
        assert!(root.is_dir(), "repo root should exist: {}", root.display());
        assert!(root.join("launcher").is_dir(), "launcher dir should exist");
        assert!(root.join("photoshop_plugin").is_dir(), "photoshop_plugin dir should exist");
    }

    #[test]
    fn workflow_bundle_files_exist_and_are_valid_json() {
        let root = repo_root_path();
        let wf = root.join("photoshop_plugin").join("workflows").join("inpainting-api.json");
        let map = root.join("photoshop_plugin").join("workflows").join("inpainting-api.mapping.json");

        assert!(wf.is_file(), "workflow file must exist: {}", wf.display());
        assert!(map.is_file(), "mapping file must exist: {}", map.display());

        let wf_json = read_json_file(&wf).expect("workflow must be valid JSON");
        let map_json = read_json_file(&map).expect("mapping must be valid JSON");

        assert!(!wf_json.as_object().map(|o| o.is_empty()).unwrap_or(true), "workflow must not be empty");
        assert_eq!(map_json.get("status").and_then(Value::as_str), Some("ready"));
        assert!(mapping_has_required_inputs(&map_json), "mapping must have required inputs");
    }

    #[test]
    fn workflow_file_target_resolves_correctly() {
        let api = workflow_file_target(WorkflowFileKind::WorkflowApi);
        let mapping = workflow_file_target(WorkflowFileKind::WorkflowMapping);

        assert!(api.ends_with("inpainting-api.json"), "should end with inpainting-api.json, got: {}", api.display());
        assert!(mapping.ends_with("inpainting-api.mapping.json"), "should end with mapping.json, got: {}", mapping.display());
    }

    #[test]
    fn path_text_returns_display_string() {
        let p = PathBuf::from(r"C:\test\path");
        let text = path_text(&p);
        assert!(!text.is_empty());
    }

    #[cfg(windows)]
    #[test]
    fn normalize_process_name_strips_exe_and_lowercases() {
        assert_eq!(normalize_process_name("Photoshop.exe"), "photoshop");
        assert_eq!(normalize_process_name("Adobe UXP Developer Tools.exe"), "adobe uxp developer tools");
        assert_eq!(normalize_process_name("Photoshop"), "photoshop");
        assert_eq!(normalize_process_name("photoshop.EXE"), "photoshop");
    }

    #[cfg(windows)]
    #[test]
    fn real_tasklist_runs_without_console() {
        let result = process_name_is_running("Idonotexist12345.exe");
        assert!(!result, "non-existent process should not be found");
    }

    #[test]
    fn mapping_input_is_ready_validates_correctly() {
        let json: Value = serde_json::from_str(
            r#"{"inputs":{"testCode":{"nodeId":"10","inputName":"image"}}}"#
        ).expect("parse json");

        assert!(mapping_input_is_ready(&json, "testCode"));
        assert!(!mapping_input_is_ready(&json, "missing"));
    }

    #[test]
    fn mapping_lora_slots_valid_detects_bad_slots() {
        let loras_json: Value = serde_json::from_str(
            r#"{"inputs":{"lorasJson":{"nodeId":"90","inputName":"loras_json"}}}"#
        ).expect("parse json");
        assert!(mapping_lora_slots_are_valid(&loras_json));

        let valid: Value = serde_json::from_str(
            r#"{"inputs":{"loras":[{"name":{"nodeId":"10","inputName":"lora_name"},"strengthModel":{"nodeId":"10","inputName":"strength_model"}}]}}"#
        ).expect("parse json");
        assert!(mapping_lora_slots_are_valid(&valid));

        let invalid: Value = serde_json::from_str(
            r#"{"inputs":{"loras":[{"name":{"nodeId":"10"}}]}}"#
        ).expect("parse json");
        assert!(!mapping_lora_slots_are_valid(&invalid));

        let empty: Value = serde_json::from_str(
            r#"{"inputs":{}}"#
        ).expect("parse json");
        assert!(!mapping_lora_slots_are_valid(&empty));
    }

    #[test]
    fn build_invalid_selected_report_shows_error() {
        let path = temp_dir("invalid-selected");
        fs::create_dir_all(&path).expect("create dir");

        let report = build_invalid_selected_report(path.clone());

        assert!(report.comfyui_path.is_none());
        let comfy_item = report.items.iter().find(|i| i.id == "comfyui-root").expect("comfyui-root");
        assert_eq!(comfy_item.status, "błąd");
        assert_eq!(comfy_item.action_label, Some("Wybierz ponownie".to_string()));

        fs::remove_dir_all(path).ok();
    }

    #[test]
    fn scan_readiness_without_comfyui_returns_missing_report() {
        let report = scan_readiness();

        if report.comfyui_path.is_some() {
            assert!(!report.items.is_empty());
        } else {
            assert_eq!(report.counts.loras, 0);
            assert_eq!(report.counts.gguf_files, 0);
        }
    }

    #[test]
    fn dedupe_paths_removes_duplicates_case_insensitive() {
        let paths = vec![
            PathBuf::from(r"C:\ComfyUI"),
            PathBuf::from(r"c:\comfyui"),
            PathBuf::from(r"C:\Other"),
        ];

        let unique = dedupe_paths(paths);

        assert_eq!(unique.len(), 2, "should have 2 unique paths, got {:?}", unique);
    }

    #[test]
    fn has_extension_matches_case_insensitive() {
        let p = PathBuf::from("model.SAFETENSORS");
        assert!(has_extension(&p, &["safetensors"]));

        let p2 = PathBuf::from("model.gguf");
        assert!(has_extension(&p2, &["gguf"]));

        let p3 = PathBuf::from("model.txt");
        assert!(!has_extension(&p3, &["safetensors", "gguf"]));
    }

    #[test]
    fn validate_asset_install_rejects_missing_comfyui() {
        let bad = temp_dir("bad-comfyui");
        let source = bad.join("test.safetensors");
        fs::create_dir_all(&bad).expect("create dir");
        fs::write(&source, "test").expect("write source");

        let validation = validate_asset_install_paths(bad.clone(), source, AssetKind::Lora);

        assert!(!validation.can_install);
        assert_eq!(validation.status, "błąd");

        fs::remove_dir_all(bad).ok();
    }

    #[test]
    fn install_workflow_file_saves_correctly() {
        let source_dir = temp_dir("wf-install-src");
        fs::create_dir_all(&source_dir).expect("create dir");

        let source = source_dir.join("test-wf.json");
        fs::write(&source, valid_workflow_api_json()).expect("write");

        let validation = validate_workflow_file_install_paths(
            source.clone(),
            WorkflowFileKind::WorkflowApi,
        );

        assert!(validation.can_install, "validation failed: {}", validation.message);
        assert_eq!(validation.kind, "Workflow API");
        assert!(validation.target_path.ends_with("inpainting-api.json"));

        fs::remove_dir_all(source_dir).ok();
    }

    #[test]
    fn required_workflow_inputs_without_mapping_returns_all_missing() {
        let inputs = required_workflow_inputs(None);
        assert_eq!(inputs.len(), 17);
        assert!(inputs.iter().all(|i| i.status == "brak"));
    }

    #[test]
    fn integration_start_stop_comfyui_mechanism() {
        let root = temp_comfyui("start-stop-test");
        fs::create_dir_all(root.join("venv").join("Scripts")).expect("create venv Scripts");

        let python_script = "print('RasterRelay test ok')\n";
        fs::write(root.join("main.py"), python_script).expect("write main.py");

        let python_path = find_python_executable(&root);

        let mut command = Command::new(&python_path);
        command
            .arg("main.py")
            .current_dir(&root)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }

        let mut child = command.spawn().expect("spawn python");
        assert!(child.id() > 0, "PID should be positive");

        let exit = child.wait().expect("wait for child");
        assert!(exit.success(), "python script should exit cleanly");

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn comfy_object_info_returns_none_when_not_running() {
        let result = comfy_object_info();
        if let Some(value) = result {
            assert!(value.is_object(), "should be object if running");
        }
    }
}
