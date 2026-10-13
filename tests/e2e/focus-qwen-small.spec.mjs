import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';

async function openLauncher(page) {
  await page.route('http://maw.test/**', async route => {
    const name = new URL(route.request().url()).pathname.slice(1) || 'launcher/index.html';
    const type = name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html';
    await route.fulfill({body: await readFile(resolve('web', name)), contentType: type});
  });
  await page.addInitScript(() => {
    window.calls = [];
    window.pywebview = {api: {
      start_asr: async payload => {window.calls.push({action:'asr', payload}); return {ok:false,error:'测试：不启动识别'};},
      download_local_model: async payload => {window.calls.push({action:'download', payload}); return {ok:false,error:'测试：不下载模型'};},
    }};
  });
  await page.goto('http://maw.test/launcher/index.html');
}

test('Qwen model choice reaches download and ASR, persists, and hides for other engines', async ({page}) => {
  await openLauncher(page);
  await expect(page.locator('#local-model')).toHaveValue('Qwen/Qwen3-ASR-1.7B');
  await page.locator('#local-model').selectOption('Qwen/Qwen3-ASR-0.6B');
  await page.locator('#btn-model-download').click();
  expect(await page.evaluate(() => window.calls[0].payload)).toEqual({localEngine:'qwen-asr',localModel:'Qwen/Qwen3-ASR-0.6B'});
  await page.locator('#btn-asr').click();
  expect(await page.evaluate(() => window.calls[1].payload.localModel)).toBe('Qwen/Qwen3-ASR-0.6B');
  await page.reload();
  await expect(page.locator('#local-model')).toHaveValue('Qwen/Qwen3-ASR-0.6B');
  await page.locator('#local-engine').selectOption('whisper');
  await expect(page.locator('#local-model-wrap')).toBeHidden();
  await page.locator('#local-engine').selectOption('qwen-asr');
  await expect(page.locator('#local-model-wrap')).toBeVisible();
  await page.locator('#asr-mode').selectOption('cloud');
  await expect(page.locator('#local-model-wrap')).toBeHidden();
});
