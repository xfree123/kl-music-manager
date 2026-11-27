// Cầu nối an toàn renderer <-> main (contextIsolation): chỉ lộ đúng các hàm UI cần.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('klmm', {
    isElectron: true,
    selectFolder: () => ipcRenderer.invoke('klmm:select-folder'),
    selectFile: () => ipcRenderer.invoke('klmm:select-file'),
    selectFiles: () => ipcRenderer.invoke('klmm:select-audio-files'),
    showItemInFolder: filePath => ipcRenderer.invoke('klmm:show-item-in-folder', filePath),
    openFolder: dirPath => ipcRenderer.invoke('klmm:open-folder', dirPath),
});
