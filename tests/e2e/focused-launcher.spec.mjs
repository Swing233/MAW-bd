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

test('direct media editor picks media first and forwards its explicit path', async ({ page }) => {
  await page.addInitScript(() => {
    window.__directEditCalls = [];
    const state = {
      status: { step: 'idle', message: '', error: '', stepProgress: {} },
      result: {},
      config: {},
    };
    window.pywebview = {
      api: {
        get_state: async () => state,
        browse_media: async () => {
          window.__directEditCalls.push(['browse_media', {}]);
          return { ok: true, path: '/tmp/direct-edit.mp4' };
        },
        open_media_editor: async (payload) => {
          window.__directEditCalls.push(['open_media_editor', payload]);
          return {
            ok: true,
            importedSrt: true,
            srtPath: '/tmp/direct-edit.srt',
            projectPath: '/tmp/direct-edit.maw-edit.mosp',
          };
        },
      },
    };
  });
  await page.goto(pathToFileURL(launcherPath).href);
  await page.evaluate(() => window.dispatchEvent(new Event('pywebviewready')));
  await page.locator('#btn-media-editor').click();

  await expect(page.locator('#media-path')).toHaveText('/tmp/direct-edit.mp4');
  await expect(page.locator('#msg')).toContainText('已生成波形并载入同名 SRT');
  await expect.poll(() => page.evaluate(() => window.__directEditCalls)).toEqual([
    ['browse_media', {}],
    ['open_media_editor', { mediaPath: '/tmp/direct-edit.mp4' }],
  ]);
});

test('available update appears after the bridge is ready and opens its trusted download', async ({ page }) => {
  await page.addInitScript(() => {
    window.__updateCalls = [];
    window.pywebview = {
      api: {
        get_state: async () => ({
          appVersion: '1.1.0',
          status: { step: 'idle', message: '', error: '', stepProgress: {} },
          result: {},
          config: {},
        }),
        check_for_updates: async () => ({
          ok: true,
          currentVersion: '1.1.0',
          latestVersion: '1.2.0',
          available: true,
          notes: '更新说明',
          downloadUrl: 'https://github.com/Swing233/MAW-bd/releases/download/v1.2.0/MAW-bd-1.2.0-macOS-arm64.zip',
        }),
        open_update_page: async (payload) => {
          window.__updateCalls.push(payload);
          return { ok: true, directDownload: true };
        },
      },
    };
  });
  await page.goto(pathToFileURL(launcherPath).href);
  await page.evaluate(() => window.dispatchEvent(new Event('pywebviewready')));

  await expect(page.locator('#app-version')).toHaveText('v1.1.0');
  await expect(page.locator('#update-banner')).toBeVisible();
  await expect(page.locator('#update-title')).toHaveText('发现新版本 v1.2.0');
  await expect(page.locator('#update-notes')).toHaveText('更新说明');
  await page.locator('#btn-update-download').click();
  await expect(page.locator('#msg')).toHaveText('已在浏览器开始下载更新');
  await expect.poll(() => page.evaluate(() => window.__updateCalls)).toEqual([{}]);
});
