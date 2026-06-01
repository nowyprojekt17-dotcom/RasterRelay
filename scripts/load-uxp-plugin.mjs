const pluginFolder = process.argv[2];
const serviceUrl = process.argv[3] ?? "ws://localhost:14001/socket/cli";

if (!pluginFolder) {
  console.error("Brakuje ścieżki folderu wtyczki.");
  process.exit(1);
}

if (typeof WebSocket !== "function") {
  console.error("Ta wersja Node.js nie ma wbudowanego WebSocket.");
  process.exit(1);
}

let requestId = 1;
let photoshopClientId = null;
let loadSent = false;
let finished = false;

const socket = new WebSocket(serviceUrl);

function finish(exitCode) {
  if (finished) {
    return;
  }

  finished = true;
  try {
    socket.close();
  } catch {
    // Closing is best-effort; the result was already decided.
  }

  setTimeout(() => process.exit(exitCode), 100);
}

function sendLoadMessage() {
  if (!photoshopClientId || loadSent) {
    return;
  }

  loadSent = true;
  socket.send(
    JSON.stringify({
      command: "proxy",
      clientId: photoshopClientId,
      requestId: requestId++,
      message: {
        command: "Plugin",
        action: "load",
        params: {
          provider: {
            type: "disk",
            path: pluginFolder
          }
        },
        breakOnStart: false,
        isPlaygroundPlugin: false
      }
    })
  );
}

socket.addEventListener("message", (event) => {
  const data = JSON.parse(event.data);

  if (data.command === "didAddRuntimeClient" && data.app?.appId === "PS") {
    photoshopClientId = data.id;
    sendLoadMessage();
    return;
  }

  if (data.command === "didCompleteConnection") {
    sendLoadMessage();
    return;
  }

  if (data.command === "reply") {
    if (data.error || data.success === false) {
      console.error(data.error || data.errorMessage || "Photoshop odrzucił wtyczkę.");
      finish(1);
      return;
    }

    console.log("RasterRelay załadowany w Photoshopie.");
    finish(0);
  }
});

socket.addEventListener("error", () => {
  console.error("Nie udało się połączyć z Adobe UXP Developer Tools.");
  finish(1);
});

setTimeout(() => {
  console.error("Photoshop nie odpowiedział na próbę załadowania wtyczki.");
  finish(2);
}, 15000);
