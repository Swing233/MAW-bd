import { test, expect } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const launcherPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../web/launcher/index.html',
);

test('focused launcher waits for pywebview without showing a false startup error', async ({ page }) => {
  await page.goto(pathToFileURL(launcherPath).href);

  await expect(page.locator('#log-scroll')).not.toContainText('请通过 MAW-bd 应用启动本界面');
  await expect(page.locator('#msg')).not.toHaveClass(/err/);
});

test('one media selection produces one log entry', async ({ page }) => {
  await page.addInitScript(() => {
    const state = {
      status: { step: 'idle', message: '', error: '', stepProgress: {} },
      result: {},
      config: {},
    };
    window.pywebview = {
      api: {
        get_state: async () => state,
        browse_media: async () => {
          state.status = { step: 'ready', message: '已选择媒体', error: '', stepProgress: {} };
          state.result.mediaPath = '/tmp/example.mp4';
          window.dispatchEvent(new CustomEvent('focusStatus', { detail: state.status }));
          return { ok: true, path: state.result.mediaPath };
        },
      },
    };
  });
  await page.goto(pathToFileURL(launcherPath).href);
  await page.evaluate(() => window.dispatchEvent(new Event('pywebviewready')));
  await page.locator('#btn-media').click();

  await expect(page.locator('#media-path')).toHaveText('/tmp/example.mp4');
  await expect(page.locator('#log-scroll .log-line')).toHaveCount(1);
  await expect(page.locator('#log-scroll .log-line')).toHaveText(/已选择媒体/);
});
