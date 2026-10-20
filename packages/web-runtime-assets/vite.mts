/** Serve/emit the exact installed ONNX WASM runtime; no floating CDN runtime. */
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createRequire } from 'node:module';

export function runtimeAssets(projectRoot: string) {
  const require = createRequire(join(projectRoot, 'package.json'));
  const directory = dirname(require.resolve('onnxruntime-web/wasm'));
  const version = JSON.parse(readFileSync(join(directory, '../package.json'), 'utf8')).version;
  const names = readdirSync(directory).filter(name => /^ort-wasm[\w.-]*\.(?:wasm|mjs)$/.test(name));
  if (!names.length) throw new Error('The installed ONNX runtime has no WASM assets');
  let prefix = '/ort/';
  let building = false;
  return {
    name: 'companion-runtime-assets',
    configResolved(config: any) { building = config.command === 'build'; prefix = (config.base === './' ? '/' : config.base) + 'ort/'; },
    configureServer(server: any) {
      server.middlewares.use((request: any, response: any, next: () => void) => {
        const pathname = request.url?.split('?')[0] || '';
        if (!pathname.startsWith(prefix)) return next();
        const filename = pathname.slice(prefix.length);
        if (!names.includes(filename) || !['GET', 'HEAD'].includes(request.method)) {
          response.statusCode = 404; response.end(); return;
        }
        const bytes = readFileSync(join(directory, filename));
        response.setHeader('Content-Type', filename.endsWith('.wasm') ? 'application/wasm' : 'text/javascript');
        response.setHeader('Content-Length', bytes.length);
        response.end(request.method === 'HEAD' ? undefined : bytes);
      });
    },
    buildStart(this: any) {
      if (!building) return;
      this.emitFile({ type: 'asset', fileName: 'ort/runtime.json', source: JSON.stringify({ version }) });
      for (const name of names) this.emitFile({ type: 'asset', fileName: 'ort/' + name, source: readFileSync(join(directory, name)) });
    },
  };
}
