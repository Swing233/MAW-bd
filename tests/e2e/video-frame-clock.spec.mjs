import { expect, test } from '@playwright/test';
import { join, resolve, dirname } from 'node:path';
import { existsSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { cleanupTempDir, findFreePort, generateWaveformPayload, makeTempDir, startServer } from './helpers.mjs';
let directory, server, video;
test.beforeAll(async()=>{
 directory=makeTempDir('frame-clock');video=join(directory,'source.mp4');
 const binary=[resolve('dist/local-unified-filters/MAW-bd.app/Contents/MacOS/ffmpeg/bin/ffmpeg'),'/Applications/MAW-bd.app/Contents/MacOS/ffmpeg/bin/ffmpeg'].find(existsSync);
 if(!binary)throw Error('Frame tests require the bundled FFmpeg');
 process.env.PATH=dirname(binary)+':'+process.env.PATH;
 execFileSync(binary,['-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=25','-t','8','-c:v','libx264','-pix_fmt','yuv420p',video]);
 const project=join(directory,'project.mosp');writeFileSync(project,JSON.stringify({media:video,segments:[{id:'a',start:401,end:1601,text:'测试精确按帧移动',items:[]},{id:'b',start:3000,end:4500,text:'后一句',items:[]}],waveform:generateWaveformPayload(8000)}));server=await startServer(project,video,await findFreePort());
});
test.afterAll(async()=>{await server?.stop();cleanupTempDir(directory);});
test.beforeEach(async({page})=>{await page.addInitScript(()=>{localStorage.setItem('moy.asr.editor.onboarding.v1','skipped');localStorage.setItem('moy.asr.editor.settings.v1',JSON.stringify({autoSaveProject:false}));});await page.goto(server.url);await page.locator('.cue').first().waitFor();});
test('native video import probes FPS and frame count and moves exactly one frame',async({page})=>{
 expect(await page.evaluate(()=>DATA.media_metadata.video_fps)).toBe(25);expect(await page.evaluate(()=>DATA.media_metadata.video_frame_count)).toBe(200);expect(await page.evaluate(()=>DATA.timebase)).toEqual({unit:'frames',fps:25});
 await page.evaluate(()=>{selectOnly(0);waveformEditor.adjustSelectedByKeyboard(1,false,'main');});expect(await page.evaluate(()=>[DATA.segments[0].start_frame,DATA.segments[0].start])).toEqual([11,440]);
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].start)).toBe(400);
 await page.evaluate(()=>selectOnly(0));await page.locator('#cue-list-settings-toggle').click();await expect(page.locator('#list-gap-highlight-unit')).toHaveText('帧');await expect(page.locator('#list-gap-highlight-ms')).toHaveValue('5');
});
test('browser-selected MP4 reads source clock and replaces stale metadata',async({page})=>{
 await page.evaluate(()=>{DATA.media_metadata.video_fps=60;DATA.media_metadata.video_frame_count=999;DATA.timebase={unit:'milliseconds',fps:30};});
 await page.locator('#load-media-file').setInputFiles(video);
 await expect.poll(()=>page.evaluate(()=>DATA.timebase.unit)).toBe('frames');expect(await page.evaluate(()=>DATA.timebase.fps)).toBe(25);expect(await page.evaluate(()=>DATA.media_metadata.video_frame_count)).toBe(200);
 await expect(page.locator('#subtitle-extend-forward-ms')).toHaveAttribute('step','1');
 await page.evaluate(()=>{selectOnly(0);player.currentTime=0.91;});
 const cut=await page.evaluate(()=>timelineFrameAlignedMilliseconds(player.currentTime*1000));expect(cut).toBe(920);
 const before=await page.evaluate(()=>JSON.stringify(DATA.segments));await page.evaluate(()=>{const adapter=timelineTimingAdapter();for(let i=0;i<100;i++)waveformEditor.adjustSelectedByKeyboard(1,false,'main');});
 expect(await page.evaluate(()=>DATA.segments.every(s=>s.start===millisecondsFromFrameNumber(s.start_frame,25)&&s.end===millisecondsFromFrameNumber(s.end_frame,25)))).toBe(true);
 expect(await page.evaluate(()=>JSON.parse(buildJson()).timebase.unit)).toBe('frames');expect(before.length).toBeGreaterThan(0);
});

test('fractional frame seeks do not accumulate millisecond rounding errors',async({page})=>{
 await page.evaluate(()=>{DATA.timebase={unit:'frames',fps:30000/1001};syncProjectTimebase(DATA,{preferFrames:false});player.currentTime=0;for(let i=0;i<100;i++)seekMediaBy(timelineMediaSeekStepMilliseconds()/1000);});
 expect(await page.evaluate(()=>player.currentTime)).toBeCloseTo(100*1001/30000,5);
});

test('fractional-rate gap thresholds compare whole frames', async ({page}) => {
 const result = await page.evaluate(() => {
  DATA.timebase = {unit:'frames', fps:30000/1001};
  DATA.segments[0].end = 934; DATA.segments[1].start = 1134;
  syncProjectTimebase(DATA, {preferFrames:false});
  return subtitleGapPlan(null, 6).map(change => ({gapFrames:change.gapFrames, end:change.end}));
 });
 expect(result).toEqual([{gapFrames:6, end:1134}]);
});
