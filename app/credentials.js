import { Entry } from '@napi-rs/keyring';

function entry(name) {
  if (!['win32', 'linux'].includes(process.platform)) throw new Error('Las credenciales requieren el almacén seguro de Windows o Linux.');
  if (!['api', 'proxy'].includes(name)) throw new Error('Credencial desconocida.');
  // Linux (Secret Service) ignores Windows targets; the same service/user identifies the secret.
  return process.platform === 'win32' ? Entry.withTarget(`2MD/${name}`, `2MD/${name}`, '2MD') : new Entry(`2MD/${name}`, '2MD');
}
export const getSecret = name => entry(name).getPassword();
export const setSecret = (name, value) => entry(name).setPassword(value);
