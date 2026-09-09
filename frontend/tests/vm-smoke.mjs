// Standalone developer smoke test. Do not use it to bypass browser security denials.
// No mocks, no recorded authentication state, no traces containing credentials.
import { chromium } from '@playwright/test';
import { readFile, mkdir } from 'node:fs/promises';
import assert from 'node:assert/strict';

const credentialsPath = process.env.REELVAULT_CREDENTIALS || new URL('../../.vmtest/access.txt', import.meta.url);
const credentialText = await readFile(credentialsPath, 'utf8');
const base = (process.env.REELVAULT_URL || credentialText.match(/Dashboard: (.+)/)?.[1] || 'http://127.0.0.1:18765').replace(/\/$/, '');
const token = credentialText.match(/Owner access token: (.+)/)?.[1];
assert(token, 'Missing owner access token in private credentials file');
const output = process.env.REELVAULT_QA_OUTPUT || '/private/tmp/reelvault-vmtest-qa';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  const requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('request', request => requests.push(request.url()));
  assert.equal((await context.request.get(`${base}/api/reels`)).status(), 401);
  await page.goto(base, { waitUntil: 'networkidle' });
  assert.match(await page.title(), /ReelVault/);
  await page.getByRole('heading', { name: 'ReelVault', exact: true }).waitFor();
  await page.screenshot({ path: `${output}/01-login.png`, fullPage: true });
  await page.getByLabel('Owner access token').fill(token);
  await page.getByRole('button', { name: 'Unlock archive' }).click();
  await page.getByRole('button', { name: 'Settings', exact: true }).waitFor();
  await page.waitForTimeout(1200);
  assert(!requests.some(url => /\/\d+\/video/.test(url)), 'Dashboard must not download videos on load');
  const storage = await (await context.request.get(`${base}/api/v1/storage`)).json();
  assert.equal(storage.cache.max_downloads, 5);
  assert.equal(storage.cache.budget_bytes, 5000000000);
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('heading', { name: 'Cloud storage & VM' }).waitFor();
  if (storage.provider === 'dropbox' && !storage.dropbox.connected) {
    await page.getByRole('heading', { name: 'Connect your Dropbox archive' }).waitFor();
    assert.equal(await page.getByLabel('Dropbox-relative archive folder').inputValue(), '/Cody Viveiros/SnapTik_Reel_Archive');
    assert(await page.getByRole('button', { name: 'Create authorization link' }).isDisabled());
    const buttonStyle = await page.getByRole('button', { name: 'Create authorization link' }).evaluate(element => {
      const style = getComputedStyle(element);
      return { text: style.color, background: style.backgroundColor };
    });
    assert.notEqual(buttonStyle.text, buttonStyle.background, 'Connection button must remain readable while disabled');
    assert.notEqual(buttonStyle.background, 'rgba(0, 0, 0, 0)', 'Connection button needs its theme background');
  }
  await page.screenshot({ path: `${output}/02-storage.png`, fullPage: true });
  if (process.env.REELVAULT_TEST_MEDIA === 'true') {
    await page.getByRole('button', { name: /^Home/ }).click();
    await page.getByTitle('Quick Look (full size + audio)').first().click();
    const video = page.locator('video').last();
    await video.waitFor();
    await page.waitForFunction(() => [...document.querySelectorAll('video')].some(video => video.readyState >= 2 && video.currentTime > 0));
    await page.screenshot({ path: `${output}/03-playback.png`, fullPage: true });
    const list = await (await context.request.get(`${base}/api/v1/reels`)).json();
    const id = list.items[0].id;
    const agentToken = credentialText.match(/Agent bearer token: (.+)/)?.[1];
    assert(agentToken, 'Missing agent bearer token');
    const agentHeaders = { Authorization: `Bearer ${agentToken}` };
    const submitted = await context.request.post(`${base}/api/v1/reels/${id}/materialize`, { headers: agentHeaders });
    assert.equal(submitted.status(), 202);
    let job = await submitted.json();
    const deadline = Date.now() + 30000;
    while (job.status === 'queued' || job.status === 'running') {
      assert(Date.now() < deadline, 'Materialization job did not finish');
      await page.waitForTimeout(500);
      job = await (await context.request.get(`${base}/api/v1/jobs/${job.id}`, { headers: agentHeaders })).json();
    }
    assert.equal(job.status, 'succeeded', job.error);
    const partial = await context.request.get(`${base}/api/v1/reels/${id}/download`, { headers: { ...agentHeaders, Range: 'bytes=0-99' } });
    assert.equal(partial.status(), 206);
    assert.equal((await partial.body()).length, 100);
    assert.equal((await context.request.post(`${base}/api/reels/${id}/mark-ready`, { headers: agentHeaders })).status(), 403);
    console.log(JSON.stringify({ materialization_job: job.id, status: job.status, agent_approval_blocked: true }));
  }
  assert.deepEqual(errors, [], `Browser errors: ${errors.join('; ')}`);
  await context.request.post(`${base}/api/auth/logout`);
  assert.equal((await context.request.get(`${base}/api/reels`)).status(), 401);
  console.log(JSON.stringify({ status: 'passed', url: base, provider: storage.provider, real_media_playback: process.env.REELVAULT_TEST_MEDIA === 'true', screenshots: output, console_errors: errors.length }));
  await context.close();
} finally {
  await browser.close();
}
