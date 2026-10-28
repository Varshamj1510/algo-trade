import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const outputDir = resolve(frontendDir, 'dist');
const excludedEntries = new Set(['dist', 'node_modules', 'package.json', 'package-lock.json', 'scripts', 'src']);
const apiBaseUrl = (process.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

if (process.env.VERCEL && !apiBaseUrl) {
  throw new Error('Set VITE_API_BASE_URL to the public Render backend URL before deploying to Vercel.');
}

await rm(outputDir, { force: true, recursive: true });
await mkdir(outputDir, { recursive: true });

for (const entry of await readdir(frontendDir, { withFileTypes: true })) {
  if (!excludedEntries.has(entry.name)) {
    await cp(resolve(frontendDir, entry.name), resolve(outputDir, entry.name), { recursive: true });
  }
}

const apiPath = resolve(outputDir, 'js', 'api.js');
const apiSource = await readFile(apiPath, 'utf8');
const apiOutput = apiSource.replace('window.__ALGOMIND_API_BASE__ || \'\'', JSON.stringify(apiBaseUrl));

if (apiOutput === apiSource) {
  throw new Error('Could not configure the API base URL in js/api.js.');
}

await writeFile(apiPath, apiOutput);
await cp(resolve(outputDir, 'register.html'), resolve(outputDir, 'index.html'));
