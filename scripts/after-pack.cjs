const path = require('node:path');
const { execFileSync } = require('node:child_process');

module.exports = async context => {
  if (context.electronPlatformName !== 'win32') throw new Error('La distribución portable requiere Windows.');
  execFileSync('powershell.exe', [
    '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
    '-File', path.join(__dirname, 'build-launcher.ps1'),
    '-Destination', path.join(context.appOutDir, '2MD-MCP.exe'),
  ], { stdio: 'inherit' });
};
