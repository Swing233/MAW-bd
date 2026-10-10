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

test('each export resolution shows aspect ratio and exports correct dimensions', async ({ page }) => {
  const options = [
    ['1920x1080', '1920 × 1080（16:9 横屏）', 1920, 1080],
    ['1080x1920', '1080 × 1920（9:16 竖屏）', 1080, 1920],
    ['3840x2160', '3840 × 2160（16:9 横屏）', 3840, 2160],
    ['2880x2160', '2880 × 2160（4:3）', 2880, 2160],
  ];
  for (const [value, label, width, height] of options) {
    await openExport(page);
    await expect(page.locator(`#fcpxml-export-resolution option[value="${value}"]`)).toHaveText(label);
    await page.locator('#fcpxml-export-resolution').selectOption(value);
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#fcpxml-export-confirm').click();
    const stream = await (await downloadPromise).createReadStream();
    const chunks = []; for await (const chunk of stream) chunks.push(chunk);
    const xml = Buffer.concat(chunks).toString();
    expect(xml).toContain(`width="${width}" height="${height}"`);
    expect(xml).toContain('Alpha');
  }
});

test('standalone local converter supports portrait and labels all aspect ratios', async ({ page }) => {
  const { resolve } = await import('node:path');
  const { pathToFileURL } = await import('node:url');
  await page.goto(pathToFileURL(resolve('web/srt2fcpxml-page/index.html')).href);
  await expect(page.locator('#res option')).toHaveText([
    '1920 × 1080（16:9 横屏）', '1080 × 1920（9:16 竖屏）',
    '3840 × 2160（16:9 横屏）', '2880 × 2160（4:3）',
  ]);
  await page.locator('#res').selectOption('1080x1920');
  await page.locator('#srtText').fill('1\n00:00:00,000 --> 00:00:01,500\n竖屏字幕\n');
  await page.locator('#convertBtn').click();
  await expect(page.locator('#preview')).toContainText('width="1080" height="1920"');
  await expect(page.locator('#preview')).toContainText('竖屏字幕');
  await expect(page.locator('#downloadBtn')).toBeEnabled();
});
