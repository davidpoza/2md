const { contextBridge, ipcRenderer, webUtils } = require('electron');

const invoke = async (method, ...args) => {
  const response = await ipcRenderer.invoke('2md', method, ...args);
  if (!response.ok) throw new Error(response.error);
  return response.value;
};
contextBridge.exposeInMainWorld('twomd', {
  state: () => invoke('state'),
  chooseFiles: () => invoke('choose-files'),
  chooseFolder: () => invoke('choose-folder'),
  chooseDestination: () => invoke('choose-destination'),
  openDestination: () => invoke('open-destination'),
  addDropped: files => invoke('add', Array.from(files, file => webUtils.getPathForFile(file))),
  saveSettings: (settings, secrets) => invoke('save-settings', settings, secrets),
  chooseDirectory: () => invoke('choose-directory'),
  chooseCa: () => invoke('choose-ca'),
  checkConnection: kind => invoke('check-connection', kind),
  start: (automatic, retry) => invoke('start', automatic, retry),
  cancel: () => invoke('cancel'),
  review: id => invoke('review', id),
  closeReview: () => invoke('close-review'),
  propose: (id, index, revision) => invoke('propose', id, index, revision),
  validate: (id, index, revision, code, model) => invoke('validate', id, index, revision, code, model),
  accept: token => invoke('accept', token),
  fullscreen: enabled => invoke('fullscreen', enabled),
  onEvent: listener => {
    const callback = (_event, data) => listener(data);
    ipcRenderer.on('2md-event', callback);
    return () => ipcRenderer.removeListener('2md-event', callback);
  },
});
