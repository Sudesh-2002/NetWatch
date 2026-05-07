const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {

    receiveStats: (callback) => {
        ipcRenderer.on('stats', (_, data) => callback(data));
    },

    setOpacity: (value) => {
        ipcRenderer.send('set-opacity', value);
    }

});