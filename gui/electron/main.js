const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'AetherionEXCAL Dashboard',
    icon: path.join(__dirname, '../build/logo.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // Load the React app build
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../build/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function startPythonBackend() {
  // Try to start the Python backend (fork_node RPC server) if it's not already running
  const pythonPaths = [
    path.join(__dirname, '../.venv/Scripts/python.exe'),  // Windows venv
    path.join(process.resourcesPath, '.venv/Scripts/python.exe'),  // Packaged Windows
    path.join(__dirname, '../.venv/bin/python'),  // Linux/Mac venv
    path.join(process.resourcesPath, '.venv/bin/python'),  // Packaged Linux/Mac
    'python',  // Fallback to system Python
    'python3'
  ];

  let pythonPath = null;
  for (const p of pythonPaths) {
    try {
      const fs = require('fs');
      if (fs.existsSync(p)) {
        pythonPath = p;
        break;
      }
    } catch (e) {
      // Continue to next path
    }
  }

  if (pythonPath) {
    const forkNodePath = path.join(__dirname, '../fork_node.py');
    try {
      const fs = require('fs');
      if (fs.existsSync(forkNodePath)) {
        pythonProcess = spawn(pythonPath, [forkNodePath], {
          detached: false,
          stdio: 'ignore'
        });

        pythonProcess.on('error', (err) => {
          console.error('Python backend error:', err);
        });

        pythonProcess.on('exit', (code) => {
          console.log(`Python backend exited with code ${code}`);
        });
      }
    } catch (e) {
      console.error('Failed to start Python backend:', e);
    }
  }
}

app.whenReady().then(() => {
  createWindow();

  // Optionally start the Python backend
  // Uncomment the line below to auto-start the RPC server
  // startPythonBackend();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  // Stop Python backend on exit
  if (pythonProcess) {
    pythonProcess.kill();
  }

  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Keep dashboard network access in the main process so the renderer does not
// need broad cross-origin access.
const dashboardRpcMethods = new Set(['getmetrics', 'getnetworkinfo']);

ipcMain.handle('dashboard:rpc', async (_event, method) => {
  if (!dashboardRpcMethods.has(method)) {
    throw new Error('This dashboard RPC method is not allowed.');
  }

  const response = await fetch('http://127.0.0.1:9432', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method, params: [], id: method }),
    signal: AbortSignal.timeout(4000)
  });
  if (!response.ok) throw new Error(`Node returned HTTP ${response.status}`);
  const payload = await response.json();
  if (payload.error) throw new Error(payload.error.message || payload.error);
  return payload.result;
});

ipcMain.handle('dashboard:game-stats', async () => {
  const response = await fetch('http://127.0.0.1:9436/api/game/stats', {
    signal: AbortSignal.timeout(4000)
  });
  if (!response.ok) throw new Error(`Game API returned HTTP ${response.status}`);
  return response.json();
});

// IPC handlers for Electron
ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

ipcMain.handle('get-platform', () => {
  return process.platform;
});
