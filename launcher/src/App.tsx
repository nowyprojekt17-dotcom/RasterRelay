import { useEffect, useMemo, useState } from "react";
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
};

const savedComfyuiPathKey = "rasterrelay.comfyuiPath";

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
  const [notice, setNotice] = useState<string | null>(null);

  async function loadReadiness() {
    setIsLoading(true);
    setNotice(null);

    const savedPath = localStorage.getItem(savedComfyuiPathKey);

    try {
      const result = savedPath
        ? await invoke<ReadinessReport>("scan_readiness_for_path", { path: savedPath })
        : await invoke<ReadinessReport>("scan_readiness");
      setReport(result);

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
  }, []);

  const loraItem = useMemo(
    () => report?.items.find((item) => item.id === "loras"),
    [report]
  );

  const hasSavedPath = Boolean(localStorage.getItem(savedComfyuiPathKey));
  const readinessItems = report?.items ?? [];

  function showPlaceholder(actionLabel: string, label: string) {
    if (label === "Folder ComfyUI" || actionLabel === "Wybierz ponownie") {
      void chooseComfyuiFolder();
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
          <button className="primary-button" onClick={loadReadiness} disabled={isLoading}>
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
        <article className="lora-panel">
          <div>
            <p className="eyebrow">LoRA</p>
            <h2>{report?.counts.loras ?? 0} dostępne</h2>
            <p>
              Workflow będzie projektowany tak, żeby działał bez LoRA, z jedną LoRA albo z kilkoma LoRA.
            </p>
          </div>
          <StatusBadge status={loraItem?.status ?? "brak"} />
          <button
            className="secondary-button"
            onClick={() => showPlaceholder("Add", "LoRA")}
          >
            Add
          </button>
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
        Etap 2: autoskan plus ręczny wybór folderu ComfyUI. Nadal bez kopiowania plików i bez workflow.
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

export default App;
