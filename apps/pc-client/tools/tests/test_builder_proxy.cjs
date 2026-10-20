// Exercise the builder's actual @electron/get proxy hook with the patched agent.
const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const { spawn } = require('node:child_process');

if (process.argv[2] === 'child') {
  const builder = path.dirname(require.resolve('app-builder-lib/package.json'));
  const getter = require(require.resolve('@electron/get', { paths: [builder] }));
  getter.initializeProxy();
  const request = http.get('http://synthetic.invalid/proxy-check', response => {
    let body = '';
    response.on('data', chunk => { body += chunk; });
    response.on('end', () => { assert.equal(body, 'verified-proxy'); });
  });
  request.setTimeout(3000, () => request.destroy(new Error('Proxy verification timed out')));
  request.on('error', () => { process.exitCode = 1; });
} else {
  let requests = 0;
  const server = http.createServer((request, response) => {
    if (request.url !== 'http://synthetic.invalid/proxy-check') {
      response.writeHead(400); response.end(); return;
    }
    requests++;
    response.end('verified-proxy');
  });
  server.listen(0, '127.0.0.1', () => {
    const env = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      ['PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'HOME', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH'].includes(key.toUpperCase())));
    const child = spawn(process.execPath, [__filename, 'child'], { windowsHide: true, stdio: 'ignore', env: {
      ...env, GLOBAL_AGENT_HTTP_PROXY: `http://127.0.0.1:${server.address().port}`,
      GLOBAL_AGENT_HTTPS_PROXY: '', GLOBAL_AGENT_NO_PROXY: '',
    } });
    const deadline = setTimeout(() => { child.kill(); process.exitCode = 1; server.closeAllConnections(); server.close(); }, 6000);
    child.once('error', () => { process.exitCode = 1; });
    child.once('exit', code => {
      clearTimeout(deadline);
      server.closeAllConnections(); server.close();
      if (code !== 0 || requests !== 1) process.exitCode = 1;
      else console.log('Patched builder proxy: actual download hook and loopback forwarding passed.');
    });
  });
}
