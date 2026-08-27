#!/usr/bin/env node
// Dependency-free external browser driver for the production fixture smoke tests.

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const options = Object.fromEntries(process.argv.slice(2).reduce((pairs, value, index, values) => {
  if (value.startsWith('--')) pairs.push([value.slice(2), values[index + 1]]);
  return pairs;
}, []));

if (!options.browser || !options.url || !options.scenario) {
  throw new Error('usage: cdp_probe.mjs --browser PATH --url URL --scenario mui|vue|svelte|next');
}

const profile = mkdtempSync(join(tmpdir(), 'retro-web-ui-cdp-'));
const browser = spawn(options.browser, [
  '--headless=new',
  '--disable-gpu',
  '--no-first-run',
  '--no-default-browser-check',
  '--remote-debugging-port=0',
  `--user-data-dir=${profile}`,
  'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });

let stderr = '';
browser.stderr.setEncoding('utf8');
browser.stderr.on('data', (chunk) => { stderr += chunk; });

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function until(check, label, timeout = 10000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await check();
    if (value) return value;
    await delay(50);
  }
  throw new Error(`timeout waiting for ${label}`);
}

async function browserEndpoint() {
  return until(() => stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/)?.[1], 'Chrome DevTools endpoint');
}

class Cdp {
  constructor(socket) {
    this.socket = socket;
    this.sequence = 0;
    this.pending = new Map();
    this.events = [];
    socket.addEventListener('message', ({ data }) => {
      const message = JSON.parse(String(data));
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result);
      } else if (message.method) {
        this.events.push(message);
      }
    });
  }

  send(method, params = {}) {
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'browser evaluation failed');
    return result.result.value;
  }
}

async function connectPage(browserWebSocket) {
  const port = new URL(browserWebSocket).port;
  const targets = await until(async () => {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`);
      const values = await response.json();
      return values.find((target) => target.type === 'page' && target.webSocketDebuggerUrl);
    } catch {
      return null;
    }
  }, 'page target');
  const socket = new WebSocket(targets.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  return new Cdp(socket);
}

async function waitFor(cdp, expression, label) {
  return until(() => cdp.evaluate(`Boolean(${expression})`), label);
}

async function setNativeInput(cdp, selector, value) {
  await cdp.evaluate(`(() => {
    const input = document.querySelector(${JSON.stringify(selector)});
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, ${JSON.stringify(value)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return input.value;
  })()`);
}

async function pressEscape(cdp) {
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27, nativeVirtualKeyCode: 27 });
}

const scenarios = {
  async mui(cdp) {
    await setNativeInput(cdp, '[data-fixture-name]', '  外部操作  ');
    await cdp.evaluate(`document.querySelector('[data-fixture-form]').requestSubmit()`);
    await waitFor(cdp, `document.querySelector('[data-fixture-status]')?.textContent.includes('外部操作を保存しました')`, 'MUI form result');
    await cdp.evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent.includes('確認'))?.click()`);
    await waitFor(cdp, `document.querySelector('[data-fixture-dialog]')`, 'MUI dialog');
    const themed = await cdp.evaluate(`document.querySelector('[data-fixture-dialog]')?.closest('[data-retro-theme="windows-98"]') !== null`);
    if (!themed) throw new Error('MUI portal is outside the theme root');
    await pressEscape(cdp);
    await waitFor(cdp, `!document.querySelector('[data-fixture-dialog]')`, 'MUI Escape close');
    const focusReturned = await cdp.evaluate(`document.activeElement?.textContent.includes('確認')`);
    if (!focusReturned) throw new Error('MUI dialog did not return focus');
  },

  async vue(cdp) {
    await setNativeInput(cdp, '[data-fixture-name]', '  外部接続  ');
    await cdp.evaluate(`document.querySelector('[data-fixture-form]').requestSubmit()`);
    await waitFor(cdp, `document.querySelector('[data-fixture-status]')?.textContent.includes('外部接続を保存しました')`, 'Vue form result');
    const shown = await cdp.evaluate(`new Promise((resolve) => {
      const modal = document.querySelector('#confirm-dialog');
      const timeout = setTimeout(() => resolve(false), 2000);
      modal.addEventListener('shown.bs.modal', () => { clearTimeout(timeout); resolve(true); }, { once: true });
      document.querySelector('[data-bs-toggle="modal"]').click();
    })`);
    if (!shown) throw new Error('Bootstrap shown lifecycle event did not fire');
    const hidden = await cdp.evaluate(`new Promise((resolve) => {
      const modal = document.querySelector('#confirm-dialog');
      const timeout = setTimeout(() => resolve(false), 2000);
      modal.addEventListener('hidden.bs.modal', () => { clearTimeout(timeout); resolve(true); }, { once: true });
      document.querySelector('[data-bs-dismiss="modal"]').click();
    })`);
    if (!hidden) throw new Error('Bootstrap hidden lifecycle event did not fire');
  },

  async svelte(cdp) {
    await cdp.evaluate(`document.querySelector('[data-fixture-check]').click()`);
    await setNativeInput(cdp, '[data-fixture-folder]', '  E:\\External  ');
    await cdp.evaluate(`document.querySelector('[data-fixture-form]').requestSubmit()`);
    await waitFor(cdp, `document.querySelector('[data-fixture-status]')?.textContent.includes('E:\\\\Externalへ自動保存します')`, 'Svelte form result');
  },

  async next(cdp) {
    await setNativeInput(cdp, '[data-fixture-name]', '  外部プロファイル  ');
    await cdp.evaluate(`document.querySelector('[data-fixture-form]').requestSubmit()`);
    await waitFor(cdp, `document.querySelector('[data-fixture-status]')?.textContent.includes('外部プロファイルを保存しました')`, 'Next form result');
    await cdp.evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent.includes('詳細'))?.click()`);
    await waitFor(cdp, `document.querySelector('[data-fixture-dialog]')`, 'Radix dialog');
    const themed = await cdp.evaluate(`document.querySelector('[data-fixture-dialog]')?.closest('[data-retro-theme="windows-7"]') !== null`);
    if (!themed) throw new Error('Radix portal is outside the theme root');
    await pressEscape(cdp);
    await waitFor(cdp, `!document.querySelector('[data-fixture-dialog]')`, 'Radix Escape close');
    const focusReturned = await cdp.evaluate(`document.activeElement?.textContent.includes('詳細')`);
    if (!focusReturned) throw new Error('Radix dialog did not return focus');
  },
};

let cdp;
try {
  const endpoint = await browserEndpoint();
  cdp = await connectPage(endpoint);
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');
  await cdp.send('Log.enable');
  await cdp.send('Page.navigate', { url: options.url });
  await waitFor(cdp, `document.readyState === 'complete'`, 'page load');
  await waitFor(cdp, `document.querySelector('[data-fixture-form]')`, 'hydrated fixture form');
  // A prerendered form can exist before its framework has attached listeners.
  await delay(250);
  const scenario = scenarios[options.scenario];
  if (!scenario) throw new Error(`unknown scenario: ${options.scenario}`);
  await scenario(cdp);
  await delay(200);
  const failures = cdp.events.filter((event) =>
    event.method === 'Runtime.exceptionThrown'
    || (event.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(event.params.type))
    || (event.method === 'Log.entryAdded'
      && ['error', 'warning'].includes(event.params.entry.level)
      && !event.params.entry.url?.endsWith('/favicon.ico'))
  );
  if (failures.length) throw new Error(`browser console/runtime failures: ${JSON.stringify(failures.slice(-5))}`);
  console.log(`${options.scenario} external CDP interaction passed`);
} finally {
  if (cdp?.socket) cdp.socket.close();
  browser.kill('SIGTERM');
  await Promise.race([new Promise((resolve) => browser.once('exit', resolve)), delay(2000)]);
  if (browser.exitCode === null) browser.kill('SIGKILL');
  rmSync(profile, { recursive: true, force: true });
}
