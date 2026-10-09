import { expect, test } from '@playwright/test';
import { join } from 'node:path';
import { cleanupTempDir, findFreePort, generateProjectJson, generateWav, makeTempDir, startServer } from './helpers.mjs';

let directory, server;
test.beforeAll(async () => {
  directory = makeTempDir('fcpxml-format');
  const media = join(directory, 'synthetic.wav');
  const project = join(directory, 'project.json');
  generateWav(media, 75); generateProjectJson(project);
  server = await startServer(project, media, await findFreePort());
});
test.afterAll(async () => { await server?.stop(); cleanupTempDir(directory); });
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('moy.asr.editor.settings.v1', JSON.stringify({ autoSaveProject: false }));
    window.showSaveFilePicker = undefined;
  });
  await page.goto(server.url);
});
async function openExport(page) {
  await page.locator('#subtitle-export-btn').click();
  await page.locator('#download-fcpxml').click();
  await expect(page.locator('#fcpxml-export-modal')).toBeVisible();
}
test('source video dimensions and fractional frame rate show next to export choices', async ({ page }) => {
  await page.evaluate(() => { DATA.media_metadata = { video_width: 3840, video_height: 2160,
    video_fps: 30000 / 1001, video_fps_ratio: '30000/1001' }; });
  await openExport(page);
  await expect(page.locator('#fcpxml-source-resolution')).toHaveText('3840 × 2160');
  await expect(page.locator('#fcpxml-source-fps')).toHaveText('29.97 fps（30000/1001）');
  await page.locator('#fcpxml-export-fps').selectOption('30');
  await page.locator('#fcpxml-export-resolution').selectOption('1920x1080');
  await page.locator('#fcpxml-export-cancel').click();
  await openExport(page);
  await expect(page.locator('#fcpxml-export-fps')).toHaveValue('30');
  await expect(page.locator('#fcpxml-source-resolution')).toHaveText('3840 × 2160');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#fcpxml-export-confirm').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.fcpxml$/);
  const stream = await download.createReadStream();
  const chunks = []; for await (const chunk of stream) chunks.push(chunk);
  const xml = Buffer.concat(chunks).toString();
  expect(xml).toContain('frameDuration="100/3000s"');
  expect(xml).toContain('width="1920" height="1080"');
});
test('missing source data is explicit and never substituted by timeline FPS', async ({ page }) => {
  await page.evaluate(() => { DATA.media_metadata = null; DATA.timebase = { unit: 'frames', fps: 60 }; });
  await openExport(page);
  await expect(page.locator('#fcpxml-source-resolution')).toHaveText('未读取到分辨率');
  await expect(page.locator('#fcpxml-source-fps')).toHaveText('未读取到帧率');
});
test('current media dimensions and reopened source rate refresh the display', async ({ page }) => {
  await page.evaluate(() => {
    DATA.media_metadata = { video_width: 1920, video_height: 1080, video_fps: 24 };
    Object.defineProperty(player, 'videoWidth', { configurable: true, value: 1280 });
    Object.defineProperty(player, 'videoHeight', { configurable: true, value: 720 });
  });
  await openExport(page);
  await expect(page.locator('#fcpxml-source-resolution')).toHaveText('1280 × 720');
  await expect(page.locator('#fcpxml-source-fps')).toHaveText('24 fps');
  await page.locator('#fcpxml-export-cancel').click();
  await page.evaluate(() => { DATA.media_metadata = { video_fps: 50 }; });
  await openExport(page);
  await expect(page.locator('#fcpxml-source-fps')).toHaveText('50 fps');
});
