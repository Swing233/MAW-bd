import { expect, test } from '@playwright/test';
import { join, resolve, dirname } from 'node:path';
import { existsSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { cleanupTempDir, findFreePort, generateWaveformPayload, makeTempDir, startServer } from './helpers.mjs';
let directory, server, video;
test.beforeAll(async()=>{
 directory=makeTempDir('frame-clock');video=join(directory,'source.mp4');
 const binary=[process.env.MAW_E2E_FFMPEG,resolve('dist/local-unified-filters/MAW-bd.app/Contents/MacOS/ffmpeg/bin/ffmpeg'),'/Applications/MAW-bd.app/Contents/MacOS/ffmpeg/bin/ffmpeg'].find(path => path && existsSync(path));
 if(!binary)throw Error('Frame tests require the bundled FFmpeg');
 process.env.PATH=dirname(binary)+':'+process.env.PATH;
 execFileSync(binary,['-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=25','-t','8','-c:v','libx264','-pix_fmt','yuv420p',video]);
 const project=join(directory,'project.mosp');writeFileSync(project,JSON.stringify({media:video,timebase:{unit:'frames',fps:25},segments:[{id:'a',start:401,end:1601,text:'测试毫秒编辑',start_frame:1,end_frame:2,items:[]},{id:'b',start:3000,end:4500,text:'后一句',items:[]}],waveform:generateWaveformPayload(8000)}));server=await startServer(project,video,await findFreePort());
});
test.afterAll(async()=>{await server?.stop();cleanupTempDir(directory);});
test.beforeEach(async({page})=>{await page.addInitScript(()=>{localStorage.setItem('moy.asr.editor.onboarding.v1','skipped');localStorage.setItem('moy.asr.editor.settings.v1',JSON.stringify({autoSaveProject:false}));});await page.goto(server.url);await page.locator('.cue').first().waitFor();});
test('video metadata remains available without remapping legacy millisecond times', async ({page}) => {
 expect(await page.evaluate(()=>DATA.media_metadata.video_fps)).toBe(25);
 expect(await page.evaluate(()=>DATA.media_metadata.video_frame_count)).toBe(200);
 expect(await page.evaluate(()=>DATA.timebase.unit)).toBe('milliseconds');
 expect(await page.evaluate(()=>DATA.segments[0].start)).toBe(401);
 expect(await page.evaluate(()=>timelineTimingAdapter().unit)).toBe('milliseconds');
 await expect(page.locator('#timeline-timebase')).toHaveCount(0);
 await expect(page.locator('#editor-settings-tab-timebase')).toHaveCount(0);
 await page.evaluate(()=>{selectOnly(0);waveformEditor.adjustSelectedByKeyboard(10,false,'main');});
 expect(await page.evaluate(()=>DATA.segments[0].start)).toBe(410);
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].start)).toBe(401);
 await page.locator('#cue-list-settings-toggle').click();
 await expect(page.locator('#list-gap-highlight-unit')).toHaveText('ms');
 await expect(page.locator('#list-gap-highlight-ms')).toHaveValue('200');
});

test('selecting MP4 probes export format without activating frame editing',async({page})=>{
 await page.evaluate(()=>{DATA.media_metadata.video_fps=60;DATA.media_metadata.video_frame_count=999;});
 await page.locator('#load-media-file').setInputFiles(video);
 await expect.poll(()=>page.evaluate(()=>DATA.media_metadata.video_frame_count)).toBe(200);
 expect(await page.evaluate(()=>DATA.timebase.unit)).toBe('milliseconds');
 expect(await page.evaluate(()=>DATA.segments[0].start)).toBe(401);
 expect(await page.evaluate(()=>timelineFrameAlignedMilliseconds(913))).toBe(913);
 expect(await page.evaluate(()=>JSON.parse(buildJson()).timebase.unit)).toBe('milliseconds');
});

test('audio import is rejected by the picker and drag and drop', async ({page}) => {
 const original = await page.evaluate(() => DATA.media);
 const audio = {name: 'voice.wav', mimeType: 'audio/wav', buffer: Buffer.from('audio')};
 await page.locator('#load-media-file').setInputFiles(audio);
 await expect(page.getByText('仅支持导入视频文件', {exact: true})).toBeVisible();
 await page.evaluate(async () => {
   await handleDroppedFiles([new File(['audio'], 'voice.m4a', {type: 'audio/mp4'})]);
 });
 await expect(page.getByText('不支持的文件类型（仅支持视频 / JSON / SRT / reapeaks）', {exact: true})).toBeVisible();
 expect(await page.evaluate(() => DATA.media)).toBe(original);
});
