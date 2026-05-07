const { app, BrowserWindow, ipcMain, Tray, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let py;
let mainWindow;
let overlayWindow;

function createMainWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        title: 'NetWatch',
        autoHideMenuBar: true,
        frame: true,
        titleBarStyle: 'default',
        backgroundColor: '#080b12',
        show: false,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });

    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    mainWindow.loadFile('frontend/index.html');
    mainWindow.setMenuBarVisibility(false);
    mainWindow.webContents.setVisualZoomLevelLimits(1, 1);
    mainWindow.webContents.setZoomFactor(1);
    mainWindow.webContents.on('devtools-opened', () => {
        mainWindow.webContents.closeDevTools();
    });
}

function createOverlayWindow() {
    // If already open, just focus it
    if (overlayWindow && !overlayWindow.isDestroyed()) {
        overlayWindow.show();
        overlayWindow.focus();
        return;
    }

    overlayWindow = new BrowserWindow({
        width: 300,
        height: 500,
        frame: false,
        transparent: true,
        alwaysOnTop: true,
        resizable: false,
        skipTaskbar: false,
        hasShadow: false,
        movable: true,
        title: 'NetWatch Overlay',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });

    overlayWindow.loadFile('frontend/mini.html');
    overlayWindow.setOpacity(0.92);
    overlayWindow.setIgnoreMouseEvents(false);
    overlayWindow.setVisibleOnAllWorkspaces(true);

    overlayWindow.on('closed', () => {
        overlayWindow = null;
    });
}

app.whenReady().then(() => {

    Menu.setApplicationMenu(null);

    createMainWindow();
    // ✅ Overlay NOT created on startup — only on button press

    // ─── IPC HANDLERS (inside whenReady so app is guaranteed ready) ──
    ipcMain.on('open-overlay', () => {
        createOverlayWindow();
    });

    ipcMain.on('close-overlay', () => {
        if (overlayWindow && !overlayWindow.isDestroyed()) {
            overlayWindow.close();
        }
    });

    ipcMain.on('toggle-pin', (event, pinned) => {
        if (overlayWindow && !overlayWindow.isDestroyed()) {
            overlayWindow.setAlwaysOnTop(pinned);
        }
    });

    ipcMain.on('set-opacity', (event, opacity) => {
        if (overlayWindow && !overlayWindow.isDestroyed()) {
            overlayWindow.setOpacity(opacity);
        }
    });

    // ─── PYTHON BACKEND ───────────────────────────────────────────
    const isPackaged = app.isPackaged;

    const backendPath = isPackaged
        ? path.join(process.resourcesPath, 'backend', 'bridge.py')
        : path.join(__dirname, 'backend', 'bridge.py');

    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

    py = spawn(pythonCmd, [backendPath]);

    let buffer = '';

    py.stdout.on('data', (data) => {
        buffer += data.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (let line of lines) {
            line = line.trim();
            if (!line) continue;
            try {
                const json = JSON.parse(line);
                if (mainWindow && !mainWindow.isDestroyed()) {
                    mainWindow.webContents.send('stats', json);
                }
                if (overlayWindow && !overlayWindow.isDestroyed()) {
                    overlayWindow.webContents.send('stats', json);
                }
            } catch (e) {
                console.log("JSON ERROR:", line);
            }
        }
    });

    py.stderr.on('data', (err) => {
        console.error("PYTHON ERROR:", err.toString());
    });

    py.on('close', (code) => {
        console.log("Python exited:", code);
    });

    // ─── TRAY ─────────────────────────────────────────────────────
    const tray = new Tray(path.join(__dirname, 'icon.png'));

    const menu = Menu.buildFromTemplate([
        {
            label: 'Show Main Window',
            click: () => mainWindow && mainWindow.show()
        },
        {
            label: 'Open Mini Overlay',
            click: () => createOverlayWindow()
        },
        {
            label: 'Close Mini Overlay',
            click: () => {
                if (overlayWindow && !overlayWindow.isDestroyed()) overlayWindow.close();
            }
        },
        { type: 'separator' },
        { label: 'Exit', click: () => app.quit() }
    ]);

    tray.setToolTip('NetWatch');
    tray.setContextMenu(menu);
});