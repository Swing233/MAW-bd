import { expect, test } from '@playwright/test';
import { join } from 'node:path';
import { cleanupTempDir, findFreePort, generateProjectJson, generateWav, makeTempDir, startServer } from './helpers.mjs';
let directory, server;
test.beforeAll(async () => { directory=makeTempDir('review-gaps'); const media=join(directory,'audio.wav'), project=join(directory,'project.json');generateWav(media,75);generateProjectJson(project);server=await startServer(project,media,await findFreePort()); });
test.afterAll(async()=>{await server?.stop();cleanupTempDir(directory);});
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('moy.asr.editor.settings.v1',JSON.stringify({autoSaveProject:false})));await page.goto(server.url);await expect(page.locator('.cue').first()).toBeVisible();});
async function fixture(page){await page.evaluate(()=>{DATA.segments=DATA.segments.slice(0,4).map((s,i)=>({...s,start:[0,1100,2300,3600][i],end:[1000,2100,3300,4600][i],text:['曲水，试验','二个苹果','hello','无标点'][i],items:[]}));DATA.segments[0].proofread={status:'verified',asr_original:'曲水，试验',corrected:'驱水，试验',reason:'同音'};DATA.segments[1].proofread={status:'uncertain',asr_original:'二个苹果',corrected:'2个苹果'};renderAll();waveformEditor.refreshCueOverlay();});}
test('punctuation filtering is available and filters subtitle list',async({page})=>{await fixture(page);await page.locator('#proofread-filter-btn').click();await page.locator('#proofread-filter-menu').getByText('含标点符号',{exact:true}).click();await expect(page.locator('.cue:visible')).toHaveCount(1);await expect(page.locator('.cue:visible').first()).toContainText('曲水，试验');});
test('review remembers hidden checkboxes, highlights differences, applies and undoes',async({page})=>{
 await fixture(page);const before=await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])));
 await page.locator('#llm-review-btn').click();await expect(page.locator('.llm-review-row')).toHaveCount(2);await expect(page.locator('.review-added').first()).toContainText('驱');
 await page.locator('.llm-review-row[data-index="0"] input').check();await page.locator('#llm-review-filter').selectOption('digits');await expect(page.locator('.llm-review-row')).toHaveCount(1);await page.locator('#llm-review-filter').selectOption('punctuation');await expect(page.locator('.llm-review-row')).toHaveCount(1);await expect(page.locator('.llm-review-row input')).toBeChecked();
 await page.locator('#llm-review-save').click();await expect(page.locator('#llm-review-dialog')).toHaveCount(0);expect(await page.evaluate(()=>DATA.segments.map(s=>s.text))).toEqual(['驱水，试验','二个苹果','hello','无标点']);expect(await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])))).toBe(before);
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('曲水，试验');
});
test('cancel review does not change text, manual revisions are protected',async({page})=>{await fixture(page);await page.evaluate(()=>{DATA.segments[0].proofread.review_text='驱水，试验';DATA.segments[0].proofread.status='manual';});await page.locator('#llm-review-btn').click();await expect(page.locator('.llm-review-row[data-index="0"] input')).toBeDisabled();await page.locator('.llm-review-row[data-index="1"] input').check();await page.locator('#llm-review-cancel').click();expect(await page.evaluate(()=>DATA.segments[1].text)).toBe('二个苹果');});
test('gap highlight is strict, survives redraw, and never changes project',async({page})=>{
 await fixture(page);const before=await page.evaluate(()=>JSON.stringify(DATA));await page.evaluate(()=>openSubtitleGapHighlight());await page.locator('#subtitle-gap-highlight-max').fill('200');await expect(page.locator('#subtitle-gap-highlight-summary')).toContainText('1 处');await page.locator('#subtitle-gap-highlight-apply').click();await expect(page.locator('.waveform-subtitle-gap-highlight')).toHaveCount(1);await expect(page.locator('.waveform-subtitle-gap-highlight')).toHaveAttribute('data-gap-ms','100');expect(await page.evaluate(()=>JSON.stringify(DATA))).toBe(before);
 await page.evaluate(()=>waveformEditor.refreshCueOverlay());await expect(page.locator('.waveform-subtitle-gap-highlight')).toHaveCount(1);await page.evaluate(()=>openSubtitleGapHighlight());await page.locator('#subtitle-gap-highlight-off').click();await expect(page.locator('.waveform-subtitle-gap-highlight')).toHaveCount(0);
});
test('gap removal previews selected neighbors and preserves items, media and count with undo',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[0].items=[{text:'曲水，试验',start:0,end:1000}];selectedIdxs.clear();selectedIdxs.add(0);selectedIdxs.add(1);});const before=await page.evaluate(()=>JSON.stringify(DATA));await page.evaluate(()=>openSubtitleGapClose());await expect(page.locator('#subtitle-gap-scope')).toHaveValue('selected');await expect(page.locator('#subtitle-gap-summary')).toContainText('1 处');await page.locator('#subtitle-gap-apply').click();expect(await page.evaluate(()=>DATA.segments.map(s=>s.end))).toEqual([1100,2100,3300,4600]);expect(await page.evaluate(()=>DATA.segments[0].items[0].end)).toBe(1000);await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].end)).toBe(1000);
});
test('custom navigation capture replaces W and persists in settings and hints',async({page})=>{
 await fixture(page);await page.evaluate(()=>selectOnly(2));await page.locator('#editor-settings-toggle').click();await page.locator('#editor-settings-tab-general').click();await page.locator('[data-editing-shortcut="navUp"]').click();await page.keyboard.press('F8');await expect(page.locator('[data-editing-shortcut-label="navUp"]').last()).toHaveText('F8');await page.locator('#editor-settings-close').click();await page.evaluate(()=>document.activeElement?.blur());await page.keyboard.press('F8');expect(await page.evaluate(()=>[...selectedIdxs])).toEqual([1]);await page.keyboard.press('w');expect(await page.evaluate(()=>[...selectedIdxs])).toEqual([1]);await page.keyboard.press('Shift+F8');expect(await page.evaluate(()=>[...selectedIdxs].sort())).toEqual([0,1]);
});


test('highlight aligns with main caption lanes in basic and dual-track modes', async ({page}) => {
  await fixture(page);
  await page.evaluate(()=>{subtitleGapHighlightMs=200;waveformEditor.settings.mode='basic';waveformEditor.render();});
  const aligned = () => page.evaluate(()=>{
    const marker=document.querySelector('.waveform-subtitle-gap-highlight'), block=document.querySelector('.waveform-cue-block[data-track="main"]');
    const a=getComputedStyle(marker),b=getComputedStyle(block);return [a.bottom,a.height,b.bottom,b.height];
  });
  let layout=await aligned();expect(layout.slice(0,2)).toEqual(layout.slice(2));
  await page.evaluate(()=>{
    DATA.multi_subtitle.enabled=true;DATA.multi_subtitle.display_mode='both';
    const track=getActiveExtensionTrack();if(track) track.segments=DATA.segments.map((s,i)=>({...s,id:'extension-'+i}));
    renderAll({waveform:'full'});
  });
  layout=await aligned();expect(layout.slice(0,2)).toEqual(layout.slice(2));
});


test('space filter only appears in caption filters', async ({page}) => {
 await fixture(page);await page.evaluate(()=>{DATA.segments[2].text='Hello world';renderAll();});
 await page.locator('#proofread-filter-btn').click();await page.locator('#proofread-filter-menu [data-filter="spaces"]').click();
 await expect(page.locator('.cue:visible')).toHaveCount(1);await expect(page.locator('.cue:visible')).toContainText('Hello world');
 await page.locator('#llm-review-btn').click();await expect(page.locator('#llm-review-filter option[value="spaces"]')).toHaveCount(0);
});


test('new dialogs inherit MAWE themes and remain inside the viewport', async ({page}) => {
  await fixture(page);
  for (const theme of ['dark', 'light']) {
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    await page.locator('#llm-review-btn').click();
    const colors = await page.locator('#llm-review-dialog').evaluate(el => {
      const css = getComputedStyle(el); const swatch = document.createElement('div');
      swatch.style.background = 'var(--bg-panel)'; el.appendChild(swatch);
      const panel = getComputedStyle(swatch).backgroundColor; swatch.remove();
      return [css.backgroundColor, panel];
    });
    expect(colors[0]).toBe(colors[1]);
    const box = await page.locator('#llm-review-dialog').boundingBox();
    const viewport = page.viewportSize();
    expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    await expect(page.locator('.review-comparison').first()).toBeVisible();
    await page.screenshot({path:`/private/tmp/maw-review-${theme}.png`});
    await page.locator('#llm-review-cancel').click();
    await page.evaluate(() => openSubtitleGapClose());
    await expect(page.locator('#subtitle-gap-close-dialog')).toHaveClass(/mawe-dialog/);
    await page.screenshot({path:`/private/tmp/maw-gap-${theme}.png`});
    await page.locator('#subtitle-gap-cancel').click();
    await page.evaluate(() => openSubtitleGapHighlight());
    await expect(page.locator('#subtitle-gap-highlight-dialog')).toHaveClass(/mawe-dialog/);
    await page.locator('#subtitle-gap-highlight-cancel').click();
  }
  await page.setViewportSize({width:580,height:800});
  await page.locator('#llm-review-btn').click();
  expect(await page.locator('.review-comparison').first().evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(1);
  await page.locator('#llm-review-cancel').click();
});
