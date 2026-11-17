// stdout belongs exclusively to the MCP transport.
console.log = (...args) => console.error(...args);
try {
  const { startMcp } = await import('./mcp.js');
  await startMcp();
} catch (error) {
  console.error(`No se puede iniciar el MCP de 2MD: ${error.message}`);
  process.exitCode = 1;
}
