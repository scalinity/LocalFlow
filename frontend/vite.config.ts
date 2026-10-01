import { defineConfig, type Plugin } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync, statSync, writeFileSync, existsSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

// The production build is committed into the Python package so LocalFlow
// (./run.sh and the app bundle) runs without Node installed. It is served
// by the native WKURLSchemeHandler under lfhub://app/ — relative asset
// paths, no inline scripts, no module-preload polyfill.

const ROOT = __dirname;
const OUT = join(ROOT, '../localflow/v2/ui/companion/web');

// Everything the bundle is made from. tests/v2/ui/test_companion_build.py
// recomputes this hash the same way, so a committed build that no longer
// matches its sources fails loudly.
const SOURCE_FILES = ['index.html', 'package.json', 'package-lock.json', 'svelte.config.js', 'tsconfig.json', 'vite.config.ts'];

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

export function sourceHash(): string {
  const files = [...SOURCE_FILES.map((f) => join(ROOT, f)), ...walk(join(ROOT, 'src'))]
    .map((p) => relative(ROOT, p).split(sep).join('/'))
    .sort();
  const h = createHash('sha256');
  for (const rel of files) {
    h.update(rel);
    h.update('\0');
    h.update(readFileSync(join(ROOT, rel)));
    h.update('\0');
  }
  return h.digest('hex');
}

// Third-party code that ends up in the bundle, with its licence text.
const BUNDLED = ['svelte', '@lucide/svelte', 'esm-env', 'clsx'];

function buildRecord(): Plugin {
  return {
    name: 'localflow-build-record',
    apply: 'build',
    closeBundle() {
      const pkg = (name: string) => JSON.parse(readFileSync(join(ROOT, 'node_modules', name, 'package.json'), 'utf8'));
      writeFileSync(
        join(OUT, 'BUILD.json'),
        JSON.stringify(
          {
            source_sha256: sourceHash(),
            vite: pkg('vite').version,
            svelte: pkg('svelte').version,
            note: 'Built by `npm run build` in frontend/. Do not edit files here by hand.',
          },
          null,
          1,
        ) + '\n',
      );
      const notices = BUNDLED.map((name) => {
        const dir = join(ROOT, 'node_modules', name);
        const lic = ['LICENSE', 'LICENSE.md', 'license', 'LICENSE.txt'].map((f) => join(dir, f)).find((f) => existsSync(f));
        const p = pkg(name);
        return `${name} ${p.version} (${p.license})\n\n${lic ? readFileSync(lic, 'utf8').trim() : ''}\n`;
      });
      writeFileSync(join(OUT, 'THIRD_PARTY_NOTICES.txt'), notices.join('\n' + '-'.repeat(72) + '\n\n'));
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [svelte(), buildRecord()],
  build: {
    outDir: OUT,
    emptyOutDir: true,
    assetsDir: 'assets',
    target: 'safari17',
    modulePreload: { polyfill: false },
    sourcemap: false,
    reportCompressedSize: false,
  },
  server: {
    host: '127.0.0.1',
    port: 5317,
    strictPort: true,
  },
});
