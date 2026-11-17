import { Entry } from '@napi-rs/keyring';

function entry(name) {
  if (process.platform !== 'win32') throw new Error('Las credenciales requieren el almacén seguro de Windows.');
  if (!['api', 'proxy'].includes(name)) throw new Error('Credencial desconocida.');
  return Entry.withTarget(`2MD/${name}`, `2MD/${name}`, '2MD');
}
export const getSecret = name => entry(name).getPassword();
export const setSecret = (name, value) => entry(name).setPassword(value);
