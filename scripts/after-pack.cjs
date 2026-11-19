const path = require('node:path');
const { writeFileSync } = require('node:fs');
const { execFileSync } = require('node:child_process');

// stdio passes straight through exec, so stdout stays reserved for the MCP protocol.
const linuxLauncher = `#!/bin/sh
root=$(dirname "$(readlink -f "$0")")
cd "$root" || exit 1
ELECTRON_RUN_AS_NODE=1 exec "$root/2MD" "$root/resources/app/app/mcp-entry.js"
`;

module.exports = async context => {
  if (context.electronPlatformName === 'linux') {
    writeFileSync(path.join(context.appOutDir, '2MD-MCP'), linuxLauncher, { mode: 0o755, flag: 'wx' });
    return;
  }
  if (context.electronPlatformName !== 'win32') throw new Error('La distribución portable requiere Windows o Linux.');
  execFileSync('powershell.exe', [
    '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
    '-File', path.join(__dirname, 'build-launcher.ps1'),
    '-Destination', path.join(context.appOutDir, '2MD-MCP.exe'),
  ], { stdio: 'inherit' });
};
