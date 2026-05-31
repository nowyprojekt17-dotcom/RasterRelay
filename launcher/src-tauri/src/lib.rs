use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ReadinessReport {
    comfyui_path: Option<String>,
    summary: String,
    counts: ReadinessCounts,
    items: Vec<ReadinessItem>,
    scanned_paths: Vec<String>,
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

#[derive(Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
enum AssetKind {
    Lora,
    Gguf,
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            scan_readiness,
            scan_readiness_for_path,
            validate_asset_install,
            install_asset
        ])
        .run(tauri::generate_context!())
        .expect("error while running RasterRelay Launcher");
}

fn build_found_report(root: PathBuf, candidates: Vec<PathBuf>) -> ReadinessReport {
    let custom_nodes_path = root.join("custom_nodes");
    let models_path = root.join("models");
    let loras_path = models_path.join("loras");
    let diffusion_models_path = models_path.join("diffusion_models");
    let text_encoders_path = models_path.join("text_encoders");
    let rasterrelay_nodes_path = custom_nodes_path.join("rasterrelay_nodes");

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
            "text-encoders",
            "Text encoders",
            &text_encoders_path,
            "Folder text_encoders jest na miejscu.",
            "Brakuje folderu models/text_encoders.",
            Some("Add"),
            false,
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

    if !looks_like_comfyui(&comfyui_path) {
        return asset_validation(
            kind_label,
            source_path_text,
            target_dir,
            target_path,
            file_name,
            "błąd",
            "Najpierw wybierz poprawny folder ComfyUI z plikiem main.py.",
            false,
            target_dir_exists,
        );
    }

    if !source_path.is_file() {
        return asset_validation(
            kind_label,
            source_path_text,
            target_dir,
            target_path,
            file_name,
            "błąd",
            "Wybrana ścieżka nie jest plikiem.",
            false,
            target_dir_exists,
        );
    }

    if file_name.is_empty() {
        return asset_validation(
            kind_label,
            source_path_text,
            target_dir,
            target_path,
            file_name,
            "błąd",
            "Nie udało się odczytać nazwy pliku.",
            false,
            target_dir_exists,
        );
    }

    if !has_extension(&source_path, allowed_extensions) {
        return asset_validation(
            kind_label,
            source_path_text,
            target_dir,
            target_path,
            file_name,
            "błąd",
            extension_error_message(kind),
            false,
            target_dir_exists,
        );
    }

    if target_path.exists() {
        return asset_validation(
            kind_label,
            source_path_text,
            target_dir,
            target_path,
            file_name,
            "błąd",
            "Taki plik już istnieje w folderze docelowym. Launcher nie nadpisuje plików.",
            false,
            target_dir_exists,
        );
    }

    asset_validation(
        kind_label,
        source_path_text,
        target_dir,
        target_path,
        file_name,
        "gotowe",
        if target_dir_exists {
            "Plik wygląda poprawnie. Można go skopiować po potwierdzeniu."
        } else {
            "Plik wygląda poprawnie. Folder docelowy zostanie utworzony po potwierdzeniu."
        },
        true,
        target_dir_exists,
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
            comfyui_path.join("models").join("diffusion_models"),
            "GGUF".to_string(),
            &["gguf"],
        ),
    }
}

fn asset_validation(
    kind: String,
    source_path: String,
    target_dir: PathBuf,
    target_path: PathBuf,
    file_name: String,
    status: &str,
    message: &str,
    can_install: bool,
    target_dir_exists: bool,
) -> AssetInstallValidation {
    AssetInstallValidation {
        kind,
        source_path,
        target_dir: path_text(&target_dir),
        target_path: path_text(&target_path),
        file_name,
        status: status.to_string(),
        message: message.to_string(),
        can_install,
        target_dir_exists,
        will_create_target_dir: can_install && !target_dir_exists,
    }
}

fn extension_error_message(kind: AssetKind) -> &'static str {
    match kind {
        AssetKind::Lora => "LoRA musi mieć rozszerzenie .safetensors, .pt, .ckpt albo .bin.",
        AssetKind::Gguf => "Model GGUF musi mieć rozszerzenie .gguf.",
    }
}

fn comfyui_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();

    push_candidate(&mut candidates, PathBuf::from("C:\\ComfyUI"));
    push_candidate(&mut candidates, PathBuf::from("C:\\AI\\ComfyUI"));
    push_candidate(
        &mut candidates,
        PathBuf::from("C:\\ComfyUI_windows_portable\\ComfyUI"),
    );

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
    fn validates_gguf_file_for_diffusion_models_folder() {
        let root = temp_comfyui("valid-gguf");
        let source = root.join("flux.gguf");
        fs::write(&source, "gguf").expect("write gguf");

        let validation = validate_asset_install_paths(root.clone(), source, AssetKind::Gguf);

        assert!(validation.can_install);
        assert_eq!(validation.kind, "GGUF");
        assert!(validation
            .target_path
            .ends_with("models\\diffusion_models\\flux.gguf"));

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
}
