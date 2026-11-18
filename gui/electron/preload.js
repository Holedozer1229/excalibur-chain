const { contextBridge, ipcRenderer } = require('electron');

// Expose safe IPC methods to the renderer process
contextBridge.exposeInMainWorld('electronAPI', {
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  getPlatform: () => ipcRenderer.invoke('get-platform'),
  rpc: (method) => ipcRenderer.invoke('dashboard:rpc', method),
  gameStats: () => ipcRenderer.invoke('dashboard:game-stats'),
  // Add more IPC methods as needed for game integration
});
