/**
 * preload.js — Electron secure context bridge.
 * Exposes server configuration and window actions to the React renderer
 * without exposing raw Node.js APIs or weakening security boundaries.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('desktopAPI', {
  isDesktop: true,
  platform: process.platform,
  getServerUrl: () => ipcRenderer.sendSync('get-server-url'),
  setServerUrl: (url) => ipcRenderer.invoke('set-server-url', url),
  getServerConfig: () => ipcRenderer.invoke('get-server-config'),
  getVersion: () => ipcRenderer.sendSync('get-app-version'),
  openExternal: (url) => ipcRenderer.send('open-external', url),
});
