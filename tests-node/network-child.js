// Converts documents with the app's real pipeline so a parent test can watch its network activity.
import { readFile } from 'node:fs/promises';
import { convertDocument } from '../app/conversion.js';

const [destination, ...documents] = process.argv.slice(2);
const results = [];
for (const document of documents) {
  const { markdown, warnings } = await convertDocument(document, destination);
  results.push({ document, markdown: await readFile(markdown, 'utf8'), warnings });
}
process.stdout.write(`${JSON.stringify(results)}\n`);
// Stay alive until the parent has sampled any connection left open, then exit even if handles remain.
await new Promise(resolve => process.stdin.once('end', resolve).resume());
process.exit(0);
