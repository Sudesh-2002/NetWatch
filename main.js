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
        backgroundColor: '#080b12',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true
        }
    });

    mainWindow.loadFile('frontend/index.html');
}

function createOverlayWindow() {

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
            contextIsolation: true
        }
    });

    overlayWindow.loadFile('frontend/mini.html');
    overlayWindow.setOpacity(0.92);
    overlayWindow.setIgnoreMouseEvents(false);
    overlayWindow.setVisibleOnAllWorkspaces(true);
}

app.whenReady().then(() => {

    createMainWindow();
    createOverlayWindow();

    // ==============================
    // 🔥 FIXED PYTHON PATH LOGIC
    // ==============================

    const isPackaged = app.isPackaged;

    const backendPath = isPackaged
        ? path.join(process.resourcesPath, 'backend', 'bridge.py')
        : path.join(__dirname, 'backend', 'bridge.py');

    const pythonCmd =
        process.platform === 'win32'
            ? 'python'
            : 'python3';

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

                mainWindow.webContents.send('stats', json);
                overlayWindow.webContents.send('stats', json);

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

    // Tray
    const tray = new Tray(path.join(__dirname, 'icon.png'));

    const menu = Menu.buildFromTemplate([
        {
            label: 'Show Main Window',
            click: () => mainWindow.show()
        },
        {
            label: 'Toggle Overlay',
            click: () => {
                overlayWindow.isVisible()
                    ? overlayWindow.hide()
                    : overlayWindow.show();
            }
        },
        {
            label: 'Exit',
            click: () => app.quit()
        }
    ]);

    tray.setToolTip('NetWatch');
    tray.setContextMenu(menu);
});

ipcMain.on('set-opacity', (event, opacity) => {
    if (overlayWindow) {
        overlayWindow.setOpacity(opacity);
    }
});