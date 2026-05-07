const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {

    receiveStats: (callback) => {
        ipcRenderer.on('stats', (_, data) => callback(data));
    },

    setOpacity: (value) => {
        ipcRenderer.send('set-opacity', value);
    },

    // Open the mini overlay window (called from main window button)
    openOverlay: () => {
        ipcRenderer.send('open-overlay');
    },

    // Close the overlay window (called from overlay's own close button)
    closeOverlay: () => {
        ipcRenderer.send('close-overlay');
    },

    // Toggle always-on-top pin state
    togglePin: (pinned) => {
        ipcRenderer.send('toggle-pin', pinned);
    }

});