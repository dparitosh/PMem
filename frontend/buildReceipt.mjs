import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export function buildInputHashes(root) {
  const paths = [];
  function walk(relative) {
    const absolute = join(root, relative);
    if (!existsSync(absolute)) return;
    for (const entry of readdirSync(absolute, { withFileTypes: true })) {
      const path = `${relative}/${entry.name}`;
      if (entry.isDirectory()) walk(path);
      else if (entry.isFile()) paths.push(path);
    }
  }
  walk('src'); walk('public');
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (entry.isFile() && (entry.name.startsWith('.env') || entry.name.startsWith('vite.config.') ||
      ['index.html', 'package.json', 'package-lock.json', 'buildReceipt.mjs'].includes(entry.name))) paths.push(entry.name);
  }
  return Object.fromEntries(paths.sort().map(path => [path, createHash('sha256').update(readFileSync(join(root, path))).digest('hex')]));
}
export function buildReceiptPlugin(root) {
  return { name: 'depo-build-receipt', apply: 'build', generateBundle() {
    this.emitFile({ type: 'asset', fileName: 'depo-build-receipt.json', source: JSON.stringify({ version: 1, inputs: buildInputHashes(root) }) });
  } };
}
