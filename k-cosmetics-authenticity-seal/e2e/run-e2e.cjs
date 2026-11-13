/*
 * End-to-end browser tests for the heartbeat seal (Phase 3).
 * Starts the prototype backend on 127.0.0.1:$KC_E2E_PORT (default 8799) with a throw-away data dir
 * and TEST records only, then drives Chromium at desktop, tablet and iPhone
 * sizes. Usage:  node e2e/run-e2e.cjs   (from k-cosmetics-authenticity-seal/)
 */
'use strict';
const { spawn, spawnSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { chromium, devices } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const PY = process.env.KC_PYTHON || path.resolve(ROOT, '..', '.venv', 'bin', 'python');
const PORT = process.env.KC_E2E_PORT || '8799';
const ORIGIN = 'http://127.0.0.1:' + PORT;
const SHOTS = path.join(ROOT, 'docs', 'screenshots');
const VERIFIED = 'KC-TEST-VERI-FIED-AAAA-AAAA-AAA2';
const SUSPENDED = 'KC-TEST-SUSP-ENDE-DAAA-AAAA-AAA3';
const REVOKED = 'KC-TEST-REVO-KEDA-AAAA-AAAA-AAA4';
const TOKEN = crypto.randomBytes(24).toString('base64url');
const report = (line) => process.stdout.write(line + '\n');

const results = [];
async function test(name, fn) {
  const t0 = Date.now();
  try {
    await fn();
    results.push({ name, ok: true, ms: Date.now() - t0 });
    report('  PASS  ' + name);
  } catch (e) {
    results.push({ name, ok: false, ms: Date.now() - t0, err: String((e && e.stack) || e) });
    report('  FAIL  ' + name + '\n        ' + String((e && e.message) || e));
  }
}
function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

async function admin(method, p, body) {
  const r = await fetch(ORIGIN + p, {
    method,
    headers: { Authorization: 'Bearer ' + TOKEN, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  });
  if (!r.ok) throw new Error(method + ' ' + p + ' -> ' + r.status + ' ' + (await r.text()));
  return r.json();
}
const fault = (mode) => admin('POST', '/api/v1/admin/demo/fault', { mode });

const state = (page) => page.locator('[data-kc-seal]').first().getAttribute('data-state');
const reason = (page) => page.locator('[data-kc-seal]').first().getAttribute('data-reason');
async function waitState(page, want, timeout = 8000) {
  await page.waitForFunction(
    (w) => document.querySelector('[data-kc-seal]').getAttribute('data-state') === w,
    want,
    { timeout }
  );
}

async function openSeal(context, seal, file = 'index.html') {
  const page = await context.newPage();
  page.beats = 0;
  page.on('request', (req) => {
    if (req.url().includes('/api/v1/heartbeat')) page.beats += 1;
  });
  await page.clock.install();
  await page.goto(ORIGIN + '/demo/' + file + (seal ? '?seal=' + seal : ''));
  return page;
}

async function main() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kc-seal-e2e-'));
  const env = {
    ...process.env,
    KC_SEAL_DATA_DIR: dataDir,
    KC_SEAL_DEMO_MODE: '1',
    KC_SEAL_DEV_GENERATE_KEY: '1',
    KC_SEAL_OFFICIAL_ORIGIN: ORIGIN,
    KC_SEAL_ALLOWED_ORIGINS: ORIGIN,
    KC_SEAL_RATE_LIMIT_PER_MINUTE: '600',
    KC_SEAL_ADMIN_TOKEN_SHA256: crypto.createHash('sha256').update(TOKEN).digest('hex')
  };
  const cwd = path.join(ROOT, 'backend');
  spawnSync(PY, ['-m', 'kc_seal', 'seed'], { cwd, env, stdio: 'inherit' });
  const server = spawn(PY, ['-m', 'kc_seal', 'serve', '--port', PORT], { cwd, env, stdio: ['ignore', 'ignore', 'pipe'] });
  let serverErr = '';
  server.stderr.on('data', (d) => {
    serverErr += d;
  });
  let up = false;
  for (let i = 0; i < 50 && !up; i++) {
    try {
      const h = await fetch(ORIGIN + '/healthz');
      up = h.ok && (await h.json()).environment === 'prototype';
    } catch (e) {
      /* still starting */
    }
    if (!up) await new Promise((r) => setTimeout(r, 200));
  }
  if (!up) {
    server.kill('SIGTERM');
    throw new Error('prototype server did not start on ' + ORIGIN + ' (port in use?)\n' + serverErr);
  }
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 1000 } });

  try {
    report('Heartbeat and statuses');
    await test('Verified Record shown with date, time and time zone', async () => {
      const page = await openSeal(desktop, VERIFIED);
      await waitState(page, 'verified');
      const status = await page.locator('[data-kc-status]').textContent();
      const time = await page.locator('[data-kc-time]').textContent();
      assert(status === 'Verified Record', 'status=' + status);
      assert(
        /^Last successful server verification: \d{1,2} \w+ 20\d\d(,| at) \d\d:\d\d:\d\d (CET|CEST|GMT\+1|GMT\+2) \(Europe\/Madrid\)$/.test(time),
        'time=' + time
      );
      assert(await page.locator('[data-kc-test]').isVisible(), 'TEST RECORD label hidden');
      const facts = await page.locator('.kc-seal__facts').textContent();
      assert(facts.includes('TEST-SKU-0001') && facts.includes('TESTBATCH-2608A') && facts.includes('Approved'), 'facts=' + facts);
      const msg = await page.locator('[data-kc-message]').textContent();
      assert(msg.includes('does not by itself prove that a physical product is authentic'), 'disclaimer missing');
      await page.screenshot({ path: path.join(SHOTS, 'desktop-1440-verified.png'), fullPage: true });
      await page.close();
    });

    await test('Heartbeat refreshes every 60 s (not sooner) and updates the time', async () => {
      const page = await openSeal(desktop, VERIFIED);
      await waitState(page, 'verified');
      const t1 = await page.locator('[data-kc-time]').textContent();
      const n1 = page.beats;
      await page.clock.runFor(30_000);
      await page.waitForTimeout(300);
      assert(page.beats === n1, 'polled before 60 s');
      await new Promise((r) => setTimeout(r, 1100)); // let the server clock advance a second
      await page.clock.runFor(30_500);
      await page.waitForFunction((t) => document.querySelector('[data-kc-time]').textContent !== t, t1, { timeout: 5000 });
      assert(page.beats === n1 + 1, 'expected exactly one more heartbeat, got ' + (page.beats - n1));
      assert((await state(page)) === 'verified', 'not verified after refresh');
      await page.close();
    });

    await test('Verification Suspended for suspended and revoked TEST records', async () => {
      for (const id of [SUSPENDED, REVOKED]) {
        const page = await openSeal(desktop, id);
        await waitState(page, 'suspended');
        assert((await page.locator('[data-kc-status]').textContent()) === 'Verification Suspended', 'label');
        if (id === SUSPENDED) await page.screenshot({ path: path.join(SHOTS, 'desktop-1440-suspended.png'), fullPage: true });
        await page.close();
      }
    });

    await test('Unknown and malformed codes -> Verification Unavailable', async () => {
      let page = await openSeal(desktop, 'KC-AAAA-BBBB-CCCC-DDDD-EEEE-FFFF');
      await waitState(page, 'unavailable');
      assert((await reason(page)) === 'not_found', 'reason');
      await page.close();
      page = await openSeal(desktop, 'NOT-A-CODE');
      await waitState(page, 'unavailable');
      assert((await reason(page)) === 'invalid_code', 'reason');
      await page.close();
    });

    await test('Code entry form checks a typed code', async () => {
      const page = await openSeal(desktop, '');
      await waitState(page, 'idle');
      assert((await page.locator('[data-kc-message]').textContent()).startsWith('Enter the code'), 'idle prompt');
      await page.fill('#kc-seal-code', VERIFIED.toLowerCase());
      await page.click('.kc-verify__form button');
      await waitState(page, 'verified');
      assert(page.url().includes('seal=' + VERIFIED), 'url not updated');
      await page.close();
    });

    report('Server failures');
    await test('Server outage -> Unavailable, keeps last successful time, recovers', async () => {
      const page = await openSeal(desktop, VERIFIED);
      await waitState(page, 'verified');
      const lastOk = await page.locator('[data-kc-time]').textContent();
      await fault('outage');
      await page.clock.runFor(61_000);
      await waitState(page, 'unavailable');
      assert((await reason(page)) === 'network', 'reason');
      assert((await page.locator('[data-kc-time]').textContent()) === lastOk, 'last successful time lost');
      await page.screenshot({ path: path.join(SHOTS, 'desktop-1440-unavailable-outage.png'), fullPage: true });
      await fault('none');
      await page.clock.runFor(61_000);
      await waitState(page, 'verified');
      await page.close();
    });

    await test('Server unreachable (connection refused) -> Unavailable', async () => {
      const page = await openSeal(desktop, VERIFIED);
      await waitState(page, 'verified');
      await page.route('**/api/v1/heartbeat**', (route) => route.abort('connectionrefused'));
      await page.clock.runFor(61_000);
      await waitState(page, 'unavailable');
      await page.unroute('**/api/v1/heartbeat**');
      await page.close();
    });

    await test('Forged signature -> rejected as Unavailable', async () => {
      const page = await openSeal(desktop, VERIFIED);
      await waitState(page, 'verified');
      await fault('forged_signature');
      await page.clock.runFor(61_000);
      await waitState(page, 'unavailable');
      assert((await reason(page)) === 'signature', 'reason');
      await fault('none');
      await page.close();
    });

    await test('Stale (replayed / wrong-clock) response -> rejected', async () => {
      await fault('stale_response');
      const page = await openSeal(desktop, VERIFIED);
      await waitState(page, 'unavailable');
      assert((await reason(page)) === 'stale', 'reason');
      await fault('none');
      await page.close();
    });

    await test('Tampered response (status flipped in transit) -> rejected', async () => {
      const page = await openSeal(desktop, SUSPENDED);
      await waitState(page, 'suspended');
      await page.route('**/api/v1/heartbeat**', async (route) => {
        const res = await route.fetch();
        const envl = await res.json();
        const p = Buffer.from(envl.payload, 'base64url').toString().replace('verification_suspended', 'verified_record');
        envl.payload = Buffer.from(p).toString('base64url');
        await route.fulfill({ response: res, json: envl });
      });
      await page.clock.runFor(61_000);
      await waitState(page, 'unavailable');
      assert((await reason(page)) === 'signature', 'reason');
      await page.close();
    });

    report('Revocation');
    await test('Live revocation: Verified -> Suspended at the next heartbeat', async () => {
      const rec = await admin('POST', '/api/v1/admin/records', {
        is_test: true,
        product_sku: 'TEST-SKU-0500',
        product_title: 'TEST RECORD - E2E revocation',
        manufacturer_batch: 'TESTBATCH-E2E',
        supplier: { supplier_id: 'TEST-SUP-9', supplier_name: 'TEST Supplier E2E', approval_status: 'approved' }
      });
      const page = await openSeal(desktop, rec.seal_id);
      await waitState(page, 'verified');
      await admin('POST', '/api/v1/admin/records/' + rec.seal_id + '/revoke', { reason: 'TEST: e2e revocation' });
      await page.clock.runFor(61_000);
      await waitState(page, 'suspended');
      const audit = await admin('GET', '/api/v1/admin/audit/verify');
      assert(audit.ok === true, 'audit chain broken');
      await page.close();
    });

    report('Copied seal / counterfeit sites');
    const keys = (await (await fetch(ORIGIN + '/api/v1/keys')).json()).keys;
    const copyHtml = (officialOrigin) =>
      fs
        .readFileSync(path.join(ROOT, 'demo', 'index.html'), 'utf8')
        .replace('<script src="demo-loader.js"></script>', '<script src="/kc-seal-heartbeat.js"></script>')
        .replace('href="/theme-assets/kc-seal.css"', 'href="/kc-seal.css"')
        .replace('/theme-assets/kc-seal-navy-gold.svg', '/kc-seal-navy-gold.svg')
        .replace('data-endpoint="/api/v1/heartbeat"', 'data-endpoint="' + ORIGIN + '/api/v1/heartbeat"')
        .replace('data-official-origin=""', 'data-official-origin="' + officialOrigin + '"')
        .replace('data-public-keys="[]"', "data-public-keys='" + JSON.stringify(keys) + "'");
    async function counterfeit(officialOrigin, relay) {
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      await page.route('https://k-cosmetics-copy.example/**', (route) => {
        const u = new URL(route.request().url());
        if (u.pathname.startsWith('/kc-seal')) return route.fulfill({ path: path.join(ROOT, 'theme', 'assets', path.basename(u.pathname)) });
        return route.fulfill({ contentType: 'text/html', body: copyHtml(officialOrigin) });
      });
      if (relay) {
        // attacker relays genuine signed responses and adds permissive CORS
        await page.route(ORIGIN + '/api/v1/heartbeat**', async (route) => {
          const res = await route.fetch();
          await route.fulfill({ response: res, headers: { ...res.headers(), 'access-control-allow-origin': '*' } });
        });
      }
      await page.goto('https://k-cosmetics-copy.example/verify?seal=' + VERIFIED);
      await page.waitForFunction(
        () => {
          const s = document.querySelector('[data-kc-seal]').getAttribute('data-state');
          return s && s !== 'checking';
        },
        null,
        { timeout: 8000 }
      );
      const out = { state: await state(page), reason: await reason(page) };
      if (relay) await page.screenshot({ path: path.join(SHOTS, 'counterfeit-copy-rejected.png'), fullPage: true });
      await ctx.close();
      return out;
    }
    await test('Copied page claiming the official origin -> Unavailable (origin)', async () => {
      const r = await counterfeit(ORIGIN, false);
      assert(r.state === 'unavailable' && r.reason === 'origin', JSON.stringify(r));
    });
    await test('Copied page using its own origin -> blocked by CORS -> Unavailable', async () => {
      const r = await counterfeit('https://k-cosmetics-copy.example', false);
      assert(r.state === 'unavailable' && r.reason === 'network', JSON.stringify(r));
    });
    await test('Copied page relaying genuine signed responses -> Unavailable (origin-bound)', async () => {
      const r = await counterfeit('https://k-cosmetics-copy.example', true);
      assert(r.state === 'unavailable' && r.reason === 'origin', JSON.stringify(r));
    });
    await test('Verification page refuses to be framed (X-Frame-Options / CSP)', async () => {
      const r = await fetch(ORIGIN + '/demo/index.html');
      assert(r.headers.get('x-frame-options') === 'DENY', 'xfo');
      assert((r.headers.get('content-security-policy') || '').includes("frame-ancestors 'none'"), 'csp');
    });

    report('Mobile and tablet');
    const layouts = [
      ['iphone-390', devices['iPhone 13']],
      ['tablet-768', { viewport: { width: 768, height: 1024 } }]
    ];
    for (const [label, dev] of layouts) {
      await test('Layout ' + label + ': pages fit, no horizontal scroll, 44px tap targets', async () => {
        const ctx = await browser.newContext(dev);
        const page = await openSeal(ctx, VERIFIED);
        await waitState(page, 'verified');
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        assert(overflow <= 0, 'horizontal overflow ' + overflow + 'px');
        const btn = await page.locator('.kc-verify__form button').boundingBox();
        assert(btn.height >= 44, 'tap target ' + btn.height);
        await page.screenshot({ path: path.join(SHOTS, label + '-verified.png'), fullPage: true });
        const prod = await openSeal(ctx, '', 'product.html');
        await waitState(prod, 'verified');
        const o2 = await prod.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        assert(o2 <= 0, 'product overflow ' + o2);
        await prod.screenshot({ path: path.join(SHOTS, label + '-product-badge.png'), fullPage: true });
        await ctx.close();
      });
    }
    await test('Desktop product page: small seal lower right, opposite Complete Your Routine', async () => {
      const page = await openSeal(desktop, '', 'product.html');
      await waitState(page, 'verified');
      const seal = await page.locator('.kc-seal--badge').boundingBox();
      const routine = await page.locator('.demo-routine').boundingBox();
      assert(seal.x > routine.x + routine.width, 'seal not right of routine');
      assert(seal.width <= 300, 'seal too large ' + seal.width);
      const href = await page.locator('[data-kc-link]').getAttribute('href');
      assert(href.endsWith('?seal=' + VERIFIED), 'badge link=' + href);
      await page.screenshot({ path: path.join(SHOTS, 'desktop-1440-product-badge.png'), fullPage: true });
      await page.close();
    });

    report('Accessibility and privacy');
    await test('Status announced via aria-live; no cookies set', async () => {
      const page = await openSeal(desktop, VERIFIED);
      await waitState(page, 'verified');
      const live = await page.locator('[data-kc-live]').textContent();
      assert(live.startsWith('Verified Record'), 'live=' + live);
      assert((await desktop.cookies()).length === 0, 'cookies were set');
      await page.close();
    });
  } finally {
    await browser.close();
    server.kill('SIGTERM');
    fs.rmSync(dataDir, { recursive: true, force: true });
  }

  const failed = results.filter((r) => !r.ok);
  fs.writeFileSync(path.join(ROOT, 'docs', 'e2e-results.json'), JSON.stringify({ ran_at: new Date().toISOString(), results }, null, 2) + '\n');
  report('\n' + (results.length - failed.length) + '/' + results.length + ' browser tests passed');
  if (failed.length && serverErr) report(serverErr.slice(-2000));
  process.exit(failed.length ? 1 : 0);
}

main().catch((e) => {
  process.stderr.write(String((e && e.stack) || e) + '\n');
  process.exit(1);
});
