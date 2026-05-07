# NetWatch 📡
> Real-time desktop network monitor with a floating mini overlay — built with Electron + Python.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What It Does

NetWatch monitors your network in real time — download/upload speeds, session totals, peak speeds, and per-application traffic. It runs as a native desktop app with a sleek dark UI and an optional always-on-top mini overlay you can keep visible while using other apps.

---

## Features

- **Live speed monitoring** — download & upload in B/s, KB/s, MB/s, GB/s
- **60-second history charts** — visual sparkline graphs for both download and upload
- **Per-application tracking** — see which process is consuming bandwidth, sorted by speed or total data
- **Session statistics** — total downloaded/uploaded, peak speeds since launch
- **Mini overlay** — compact floating window, always on top, with pin/unpin and opacity control
- **System tray** — minimize to tray, open/close overlay from tray menu
- **1-second refresh rate** — powered by a Python psutil backend

---

## Project Structure

```
netwatch/
├── main.js                 # Electron main process
├── preload.js              # Context bridge (IPC between main ↔ renderer)
├── package.json
├── icon.png                # App icon (512×512 recommended)
├── backend/
│   └── bridge.py           # Python backend — collects network stats via psutil
│   └── monitor.py
└── frontend/
    ├── index.html          # Main dashboard UI
    └── mini.html           # Mini overlay UI
```

---

## Requirements

- [Node.js](https://nodejs.org/) v18+
- [Python](https://www.python.org/) 3.8+
- psutil Python package

---

## Setup

**1. Install Node dependencies**
```bash
npm install
```

**2. Install Python dependency**
```bash
pip install psutil
```

**3. Run in development**
```bash
npm start
```

---

## Building a Portable `.exe`

```bash
npm run build
```

Output will be in the `dist/` folder as `NetWatch-Portable.exe`.

> The build bundles the Electron runtime and sets the app icon. Python must be installed separately on the target machine, or you can bundle it using PyInstaller — see notes below.

### Bundling Python (optional)

To ship without requiring Python on the target machine, freeze `bridge.py` with PyInstaller:

```bash
pip install pyinstaller
pyinstaller --onefile backend/bridge.py --distpath backend/dist
```

Then update the `backendPath` in `main.js` to point to the compiled executable instead of the `.py` file.

---

## How It Works

```
Python (bridge.py)
  └── psutil collects net_io_counters + per-process stats every 1s
  └── outputs JSON lines to stdout

Electron (main.js)
  └── spawns Python as child process
  └── reads stdout line by line, parses JSON
  └── sends data to both windows via IPC (webContents.send)

Frontend (index.html / mini.html)
  └── receives stats via window.electron.receiveStats()
  └── updates UI, charts, app table in real time
```

---

## Mini Overlay

Click **⊞ Mini Overlay** in the main window header to open the floating overlay.

| Control | Action |
|---|---|
| 📌 Pin button | Toggle always-on-top |
| ✕ Close button | Close the overlay |
| Opacity slider | Adjust overlay transparency |

The overlay shows current speeds, sparklines, session totals, and top 3 apps by speed and data usage.

---

## Known Limitations

- Per-process network tracking requires `proc.net_io_counters()` support. On Windows this may require running as Administrator for full process visibility.
- On systems where per-process net IO is unavailable, the app falls back to estimating traffic by connection count (less accurate).

---

## Author

Built by **Sudesh**

---

## License

MIT
