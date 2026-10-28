/**
 * main.js — Electron main process for GEC Student Database ERP Desktop Client.
 *
 * Packaging & LAN rules:
 * - Reads central college backend URL from config.json or environment.
 * - Enforces contextIsolation and disables nodeIntegration.
 * - Never bundles credentials, database passwords or AI keys on staff desktops.
 */

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

let mainWindow = null;

// Determine paths for config.json (prefers executable directory, falls back to userData)
function getConfigPaths() {
  const exeDir = path.dirname(app.getPath('exe'));
  const userDir = app.getPath('userData');
  return [
    path.join(exeDir, 'config.json'),
    path.join(__dirname, 'config.json'),
    path.join(userDir, 'config.json'),
  ];
}

function loadConfig() {
  const defaults = {
    apiBaseUrl: process.env.COLLEGE_API_URL || 'http://127.0.0.1:8000/api',
    appName: 'GEC Student Database ERP',
    lanOnly: true,
  };

  for (const cfgPath of getConfigPaths()) {
    try {
      if (fs.existsSync(cfgPath)) {
        const raw = fs.readFileSync(cfgPath, 'utf8');
        const parsed = JSON.parse(raw);
        return { ...defaults, ...parsed };
      }
    } catch (e) {
      console.warn(`[Desktop] Could not parse config at ${cfgPath}:`, e.message);
    }
  }
  return defaults;
}

let activeConfig = loadConfig();

function saveUserConfig(newConfig) {
  try {
    const userDir = app.getPath('userData');
    fs.mkdirSync(userDir, { recursive: true });
    const targetPath = path.join(userDir, 'config.json');
    activeConfig = { ...activeConfig, ...newConfig };
    fs.writeFileSync(targetPath, JSON.stringify(activeConfig, null, 2), 'utf8');
    return { success: true, path: targetPath };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

function createWindow() {
  const iconPath = path.join(__dirname, '../frontend/public/app-icon.svg');

  mainWindow = new BrowserWindow({
    width: 1366,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    title: activeConfig.appName || 'GEC Student Database ERP',
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    autoHideMenuBar: true,
    backgroundColor: '#FFFDF7',
  });

  // Load production bundle or Vite dev server
  const isDev = process.env.NODE_ENV === 'development' || process.argv.includes('--dev');
  const distIndex = path.join(__dirname, '../frontend/dist/index.html');

  if (isDev) {
    const devUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';
    mainWindow.loadURL(devUrl).catch((err) => {
      console.error('[Desktop] Failed to load dev server:', err);
    });
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else if (fs.existsSync(distIndex)) {
    mainWindow.loadFile(distIndex);
  } else {
    // If frontend hasn't been built yet, show a helpful diagnostic screen
    mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
      <html>
        <body style="font-family:sans-serif;padding:40px;background:#FFFDF7;color:#24344B;text-align:center;">
          <h2>GEC Student Database ERP — Desktop Client</h2>
          <p>Frontend production bundle not found at: <code>frontend/dist/index.html</code></p>
          <p>Please build the frontend before launching:</p>
          <pre style="background:#F3E8D0;padding:12px;border-radius:6px;display:inline-block;">cd frontend && npm run build</pre>
        </body>
      </html>
    `)}`);
  }

  // Intercept external links and open in system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── IPC Handlers ──────────────────────────────────────────────
ipcMain.on('get-server-url', (event) => {
  event.returnValue = activeConfig.apiBaseUrl;
});

ipcMain.on('get-app-version', (event) => {
  event.returnValue = app.getVersion();
});

ipcMain.handle('get-server-config', async () => {
  return activeConfig;
});

ipcMain.handle('set-server-url', async (event, newUrl) => {
  if (!newUrl || typeof newUrl !== 'string') {
    return { success: false, error: 'Invalid URL' };
  }
  const cleanUrl = newUrl.trim().replace(/\/+$/, '');
  const res = saveUserConfig({ apiBaseUrl: cleanUrl });
  if (res.success && mainWindow) {
    // Reload page to re-initialize API service with new base URL
    mainWindow.reload();
  }
  return res;
});

ipcMain.on('open-external', (event, url) => {
  if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
    shell.openExternal(url);
  }
});

// ── App Lifecycle ─────────────────────────────────────────────
app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
