import { expect, test } from '@playwright/test';
import { join } from 'node:path';
import { cleanupTempDir, findFreePort, generateProjectJson, generateWav, makeTempDir, startServer } from './helpers.mjs';
let directory, server;
test.beforeAll(async () => { directory=makeTempDir('review-gaps'); const media=join(directory,'audio.wav'), project=join(directory,'project.json');generateWav(media,75);generateProjectJson(project);server=await startServer(project,media,await findFreePort()); });
test.afterAll(async()=>{await server?.stop();cleanupTempDir(directory);});
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('moy.asr.editor.settings.v1',JSON.stringify({autoSaveProject:false})));await page.goto(server.url);await expect(page.locator('.cue').first()).toBeVisible();});
async function fixture(page){await page.evaluate(()=>{DATA.segments=DATA.segments.slice(0,4).map((s,i)=>({...s,start:[0,1100,2300,3600][i],end:[1000,2100,3300,4600][i],text:['曲水，试验','二个苹果','hello','无标点'][i],items:[]}));DATA.segments[0].proofread={status:'verified',asr_original:'曲水，试验',corrected:'驱水，试验',reason:'同音'};DATA.segments[1].proofread={status:'uncertain',asr_original:'二个苹果',corrected:'2个苹果'};renderAll();waveformEditor.refreshCueOverlay();});}
test('punctuation filtering is available and filters subtitle list',async({page})=>{await fixture(page);await page.locator('#proofread-filter-btn').click();await page.locator('#proofread-filter-menu').getByText('含标点符号',{exact:true}).click();await expect(page.locator('.cue:visible')).toHaveCount(1);await expect(page.locator('.cue:visible').first()).toContainText('曲水，试验');});
test('LLM changes filter replaces review popup; badge applies suggestion with undo',async({page})=>{
 await fixture(page);const before=await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])));
 await page.evaluate(()=>{DATA.segments[2].proofread={status:'verified',review_original:'hello',review_text:'hello'};renderAll();});
 await expect(page.locator('#llm-review-btn')).toHaveCount(0);
 await page.locator('#proofread-filter-btn').click();await page.locator('[data-filter="llm_edited"]').click();
 await expect(page.locator('.cue:visible')).toHaveCount(2);
 await page.locator('#proofread-filter-btn').click();
 await page.locator('.cue:visible .proofread-badge').first().hover();
 await expect(page.locator('#cue-panel-proofread')).toBeVisible();
 await expect(page.locator('#cue-panel-proofread .proofread-diff-added')).toContainText('驱');
 await page.locator('#proofread-suggestion-accept').click();
 expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('驱水，试验');
 expect(await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])))).toBe(before);
 await expect(page.locator('#llm-review-dialog')).toHaveCount(0);
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('曲水，试验');
 await page.locator('.cue:visible .proofread-badge').first().hover();
 await page.locator('#proofread-suggestion-keep').click();
 expect(await page.evaluate(()=>DATA.segments[0].proofread.review_state)).toBe('rejected');
 expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('曲水，试验');
});
test('inline suggestion actions protect manual revisions',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[0].proofread.review_text='驱水，试验';DATA.segments[0].proofread.status='manual';renderAll();});
 await page.locator('.cue .proofread-badge').first().hover();
 await expect(page.locator('#proofread-suggestion-accept')).toBeDisabled();
 await expect(page.locator('#proofread-suggestion-keep')).toBeDisabled();
 await expect(page.locator('#proofread-suggestion-state')).toHaveText('人工修改受保护');
 expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('曲水，试验');
});
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
 await expect(page.locator('#llm-review-btn')).toHaveCount(0);await expect(page.locator('#llm-review-dialog')).toHaveCount(0);
});


test('all filters share one menu and selection resets to all', async({page})=>{
 await fixture(page);await page.locator('#proofread-filter-btn').click();
 expect(await page.locator('#proofread-filter-menu [data-filter]').evaluateAll(els=>els.map(el=>el.dataset.filter))).toEqual(['all','verified','improvised','uncertain','manual','llm_edited','digits','english','punctuation','spaces']);
 await page.locator('[data-filter="english"]').click();await expect(page.locator('.cue:visible')).toHaveCount(1);
 await expect(page.locator('#proofread-filter-btn')).toHaveText('审阅·含英文');
 await page.locator('[data-filter="all"]').click();
 await expect(page.locator('.cue:visible')).toHaveCount(4);await expect(page.locator('#proofread-filter-btn')).toHaveText('审阅');
});
test('gap dialogs and inline suggestions inherit MAWE themes', async ({page}) => {
 await fixture(page);
 for(const theme of ['dark','light']) {
  await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
  await page.locator('.cue .proofread-badge').first().hover();
  await expect(page.locator('#proofread-suggestion-actions')).toBeVisible();
  await page.screenshot({path:`/private/tmp/maw-filter-${theme}.png`});
  await page.mouse.move(0,0);
  await page.evaluate(()=>openSubtitleGapClose());
  await expect(page.locator('#subtitle-gap-close-dialog')).toHaveClass(/mawe-dialog/);
  await page.locator('#subtitle-gap-cancel').click();
  await page.evaluate(()=>openSubtitleGapHighlight());
  await expect(page.locator('#subtitle-gap-highlight-dialog')).toHaveClass(/mawe-dialog/);
  await page.locator('#subtitle-gap-highlight-cancel').click();
 }
});

test('new projects default to subtitle list workspace and can switch layouts', async({page})=>{
 await expect(page.locator('#workspace-preset')).toHaveValue('classic');
 const layout=await page.evaluate(()=>waveformEditor.getLayoutData());
 expect(layout.preset).toBe('custom');
 expect(layout.tree.children[1]).toEqual({type:'module',id:'cues'});
 await page.evaluate(()=>{SERVER_CONFIG.presetWorkspaces={};});
 await page.locator('#workspace-preset').selectOption('wave-right');
 await expect.poll(()=>page.evaluate(()=>waveformEditor.getLayoutData().preset)).toBe('wave-right');
 await page.locator('#workspace-preset').selectOption('classic');
 await expect.poll(()=>page.evaluate(()=>waveformEditor.getLayoutData().tree.children[1].id)).toBe('cues');
});

test('checked and unchecked captions align without proofread color stripe', async({page})=>{
 await fixture(page);
 const geometry=await page.locator('.cue').evaluateAll(rows=>rows.map(row=>({
  index:row.querySelector('.index').getBoundingClientRect().x,
  time:row.querySelector('.time').getBoundingClientRect().x,
  text:row.querySelector('.text').getBoundingClientRect().x,
  stripe:getComputedStyle(row.querySelector('.color-bar')).boxShadow,
 })));
 for(const key of ['index','time','text']) expect(new Set(geometry.map(row=>row[key])).size).toBe(1);
 expect(geometry.map(row=>row.stripe)).toEqual(['none','none','none','none']);
 await page.locator('.cue .proofread-badge').first().hover();
 await expect(page.locator('#cue-panel-proofread')).toBeVisible();
 await page.screenshot({path:'/private/tmp/maw-aligned-cues.png'});
});

test('retired joining tool is absent and batch gap closing remains available',async({page})=>{
 await fixture(page);await expect(page.locator('#auto-merge-manage')).toHaveCount(0);await expect(page.locator('#auto-merge-panel')).toHaveCount(0);
 await page.locator('#subtitle-gap-close-btn').click();await expect(page.locator('#subtitle-gap-close-dialog')).toBeVisible();
});
test('sticker UI is removed even in an old project containing stickers',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[0].sticker={name:'legacy',filename:'legacy.png',start:0,end:1000};EDITOR_SETTINGS.cueListShowSticker=true;EDITOR_SETTINGS.cueEditorShowSticker=true;renderAll();waveformEditor.refreshCueOverlay();selectOnly(0);});
 await expect(page.locator('[id*="sticker"]')).toHaveCount(0);
 await expect(page.locator('.sticker-slot,.cue-panel-sticker-wrap,.waveform-cue-badge.sticker')).toHaveCount(0);
 expect(await page.evaluate(()=>DATA.segments[0].sticker.name)).toBe('legacy');
 expect(await page.evaluate(()=>{DATA.segments[1].sticker_ref={name:'legacy',headIdx:0};return groupMemberIdxs(0);})).toEqual([0]);
 await page.locator('#editor-settings-toggle').click();
 await expect(page.locator('#editor-settings-panel')).not.toContainText('表情包');
 await page.locator('#editor-settings-close').click();
 await page.keyboard.press('t');
 await expect(page.locator('#sticker-modal')).toHaveCount(0);
});


test('selected numeric and English transformations preserve times and undo',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[0].text='二十五个hELLo';DATA.segments[1].text='二个苹果';selectOnly(0);renderAll();});
 const times=await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end])));
 await page.evaluate(()=>openTextProcessModal());await page.locator('#text-process-numbers').selectOption('toArabic');await page.locator('#text-process-english-case').selectOption('initial');
 await expect(page.locator('#text-process-preview')).toContainText('25个Hello');await page.locator('#text-process-confirm').click();
 expect(await page.evaluate(()=>DATA.segments.map(s=>s.text))).toEqual(['25个Hello','二个苹果','hello','无标点']);
 expect(await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end])))).toBe(times);
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('二十五个hELLo');
 await page.evaluate(()=>{DATA.segments[0].text='25个';selectOnly(0);openTextProcessModal();});await page.locator('#text-process-numbers').selectOption('toChinese');await page.locator('#text-process-confirm').click();expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('二十五个');
});
test('list dragging selects rows while clicks and double clicks remain available',async({page})=>{
 await fixture(page);await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));const rows=page.locator('.cue[data-idx]');const a=await rows.nth(0).boundingBox(),b=await rows.nth(2).boundingBox();
 await page.mouse.move(a.x+12,a.y+8);await page.mouse.down();await page.mouse.move(b.x+70,b.y+b.height-4,{steps:12});await page.mouse.up();
 expect(await page.evaluate(()=>[...selectedIdxs].sort())).toEqual([0,1,2]);await expect(page.locator('.cue-list-marquee')).toBeHidden();
 await rows.nth(3).click();expect(await page.evaluate(()=>[...selectedIdxs])).toEqual([3]);
 await rows.nth(3).locator('.text').dblclick();await expect(rows.nth(3).locator('[contenteditable]')).toBeVisible();
});


test('marquee Shift appends selection and Escape cancels without changing text',async({page})=>{
 await fixture(page);await page.evaluate(()=>selectOnly(3));await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));const before=await page.evaluate(()=>JSON.stringify(DATA.segments));
 const a=await page.locator('.cue[data-idx="0"]').boundingBox(),b=await page.locator('.cue[data-idx="1"]').boundingBox();
 await page.keyboard.down('Shift');await page.mouse.move(a.x+8,a.y+5);await page.mouse.down();await page.mouse.move(b.x+65,b.y+b.height-5,{steps:8});await page.mouse.up();await page.keyboard.up('Shift');
 expect(await page.evaluate(()=>[...selectedIdxs].sort())).toEqual([0,1,3]);
 await page.mouse.move(a.x+8,a.y+5);await page.mouse.down();await page.mouse.move(b.x+65,b.y+b.height-5,{steps:8});await page.keyboard.press('Escape');await page.mouse.up();
 expect(await page.evaluate(()=>[...selectedIdxs])).toEqual([]);expect(await page.evaluate(()=>JSON.stringify(DATA.segments))).toBe(before);
});


test('bilingual UI and shortcuts are removed while legacy project data survives',async({page})=>{
 await fixture(page);const old=await page.evaluate(()=>{DATA.multi_subtitle={schema:'moy.asr.multi_subtitle.v1',enabled:true,display_mode:'extension',tracks:[{id:'legacy',role:'extension',name:'old',split_mode:'word',segments:[{id:'legacy-1',start:0,end:1000,text:'Hello world',items:[]}]}],bindings:[]};renderAll({waveform:'full'});return JSON.stringify(DATA.multi_subtitle);});
 await expect(page.locator('#multi-subtitle-controls')).toHaveCount(0);await expect(page.locator('#multi-subtitle-import-modal')).toHaveCount(0);await expect(page.locator('.cue[data-idx]')).toHaveCount(4);await expect(page.locator('.waveform-cue-block[data-track="extension"]')).toHaveCount(0);
 await page.keyboard.press('g');await page.keyboard.press('h');expect(await page.evaluate(()=>JSON.stringify(DATA.multi_subtitle))).toBe(old);expect(await page.evaluate(()=>JSON.parse(buildJson()).multi_subtitle.tracks.map(t=>({id:t.id,segments:t.segments})))).toEqual(JSON.parse(old).tracks.map(t=>({id:t.id,segments:t.segments})));
 await page.locator('#help-toggle').click();await expect(page.locator('#help-panel')).not.toContainText('双语字幕');
});


test('subtitle menus are compact grouped lists with filters in one place',async({page})=>{
 await fixture(page);await page.locator('#proofread-filter-btn').click();
 await expect(page.locator('#proofread-filter-menu .menu-section-label')).toHaveText(['校对状态','字幕内容','长度与可见性']);
 const menu=page.locator('#proofread-filter-menu');await expect(menu.locator('#charcount-threshold')).toBeVisible();await expect(menu.locator('#hide-disabled-toggle')).toBeVisible();await expect(menu.locator('#filter-over')).toBeVisible();
 const rects=await menu.locator('[data-filter]').evaluateAll(els=>els.map(el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};}));expect(new Set(rects.map(r=>r.x)).size).toBe(2);expect(rects.every(r=>r.height<40)).toBe(true);
 await page.screenshot({path:'/private/tmp/maw-ui-filters.png'});
 await page.locator('#proofread-filter-btn').click();await page.locator('#cue-list-settings-toggle').click();await expect(page.locator('#cue-list-settings-panel .settings-panel-title')).toHaveText(['浏览行为','显示列','字幕空隙']);await expect(page.locator('#cue-list-settings-panel #charcount-threshold')).toHaveCount(0);await page.screenshot({path:'/private/tmp/maw-ui-list-settings.png'});await page.locator('#cue-list-settings-toggle').click();
 await page.locator('#batch-operations-btn').click();await expect(page.locator('#batch-operations-menu .menu-section-label')).toHaveText(['文字编辑']);await page.screenshot({path:'/private/tmp/maw-ui-batch.png'});
 await page.setViewportSize({width:720,height:650});await expect.poll(async()=>{const r=await page.locator('#batch-operations-menu').boundingBox();return r.x+r.width;}).toBeLessThanOrEqual(720);const bounds=await page.locator('#batch-operations-menu').boundingBox();expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.x+bounds.width).toBeLessThanOrEqual(720);await page.screenshot({path:'/private/tmp/maw-ui-narrow.png'});
});

test('subtitle panel can disable Enter splitting and retain preference',async({page})=>{
 await fixture(page);await page.evaluate(()=>selectOnly(0));await page.locator('#cue-editor-settings-toggle').click();await page.locator('#cue-editor-disable-enter-split').check();await page.locator('#cue-editor-settings-toggle').click();
 await page.locator('#cue-panel-text').fill('这是修改后的一条字幕');await page.locator('#cue-panel-text').press('Enter');expect(await page.evaluate(()=>DATA.segments.length)).toBe(4);expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('这是修改后的一条字幕');
 expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('moy.asr.editor.settings.v1')).splitKey)).toBe('none');
 await page.locator('.cue[data-idx="0"] .text').dblclick();await page.locator('.cue[data-idx="0"] [contenteditable]').press('Enter');expect(await page.evaluate(()=>DATA.segments.length)).toBe(4);
});

test('review tiles and independent tools match the simplified subtitle workflow',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await fixture(page);
 await expect(page.locator('#proofread-filter-btn')).toHaveText('审阅');await expect(page.locator('#cue-list-settings-panel #cue-list-follow')).toHaveCount(1);
 await expect(page.locator('.subtitle-task-actions button')).toHaveText(['文本处理','消除字幕空隙']);
 await page.locator('#text-process-btn').click();await expect(page.locator('#text-process-modal .text-process-operation')).toHaveCount(2);await expect(page.locator('#text-process-trim')).toHaveCount(0);await page.locator('#text-process-cancel').click();
 await page.evaluate(()=>document.documentElement.dataset.theme='light');await page.locator('#proofread-filter-btn').click();await page.screenshot({path:'/private/tmp/maw-review-final-light.png'});
 expect(errors).toEqual([]);
});

test('numeric processing restores 两 from original ASR and keeps LLM corrections',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[0].text='这2个驱水效果很好';DATA.segments[0].proofread={status:'verified',asr_original:'这两个曲水效果很好',corrected:'这2个驱水效果很好'};selectOnly(0);renderAll();});
 await page.locator('#text-process-btn').click();await page.locator('#text-process-numbers').selectOption('toChinese');await expect(page.locator('#text-process-preview')).toContainText('这两个驱水效果很好');await page.locator('#text-process-confirm').click();expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('这两个驱水效果很好');
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('这2个驱水效果很好');
});


test('review conditions stay open, combine, deselect and reset',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[0].text='2个hello，';DATA.segments[1].text='2个';renderAll();});
 await page.locator('#proofread-filter-btn').click();const menu=page.locator('#proofread-filter-menu');
 await menu.locator('[data-filter="digits"]').click();await menu.locator('[data-filter="english"]').click();
 await expect(menu).toBeVisible();await expect(menu.locator('[aria-checked="true"][data-filter]')).toHaveCount(2);await expect(page.locator('.cue:visible')).toHaveCount(1);
 await menu.locator('[data-filter="verified"]').click();await menu.locator('[data-filter="uncertain"]').click();await expect(page.locator('.cue:visible')).toHaveCount(1);
 await menu.locator('[data-filter="english"]').click();await expect(page.locator('.cue:visible')).toHaveCount(2);
 await menu.locator('[data-filter="all"]').click();await expect(page.locator('.cue:visible')).toHaveCount(4);await expect(menu.locator('[data-filter="all"]')).toHaveAttribute('aria-checked','true');
 await menu.locator('[data-filter="spaces"]').focus();await page.keyboard.press('Space');await expect(menu).toBeVisible();await expect(menu.locator('[data-filter="spaces"]')).toHaveAttribute('aria-checked','true');await page.keyboard.press('Escape');await expect(menu).not.toBeVisible();
});

test('text and gap tools anchor below buttons without modal blocking',async({page})=>{
 await fixture(page);
 const toolbar=await page.locator('.cues-container').boundingBox();
 for(const selector of ['#text-process-btn','#subtitle-gap-close-btn','#cue-list-settings-toggle']) { const r=await page.locator(selector).boundingBox(); expect(r.x+r.width).toBeLessThanOrEqual(toolbar.x+toolbar.width+1); }
 for(const [button,panel] of [['#text-process-btn','#text-process-modal'],['#subtitle-gap-close-btn','#subtitle-gap-close-dialog']]) {
  await page.locator(button).click();await expect(page.locator(panel)).toBeVisible();
  expect(await page.evaluate(()=>document.querySelector(':modal')!==null)).toBe(false);
  const a=await page.locator(button).boundingBox(),b=await page.locator(panel).boundingBox();expect(Math.abs(b.y-a.y-a.height-6)).toBeLessThan(2);expect(b.width).toBeLessThanOrEqual(430);
  await page.screenshot({path:panel.includes('text')?'/private/tmp/maw-text-popover.png':'/private/tmp/maw-gap-popover.png'});
  await page.keyboard.press('Escape');await expect(page.locator(panel)).not.toBeVisible();await expect(page.locator(button)).toBeFocused();
 }
 await page.locator('#text-process-btn').click();await page.locator('#subtitle-gap-close-btn').click();await expect(page.locator('#text-process-modal')).not.toBeVisible();await expect(page.locator('#text-process-btn')).toHaveAttribute('aria-expanded','false');
 await page.mouse.click(5,5);await expect(page.locator('#subtitle-gap-close-dialog')).not.toBeVisible();
});

test('selected text processing and context transforms preserve unselected subtitles and time',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[0].text='两个hello';DATA.segments[0].proofread.asr_original='两个hello';DATA.segments[1].text='三个WORLD';DATA.segments[1].proofread.asr_original='三个WORLD';DATA.segments[2].text='四个other';selectOnly(0);addToSelection(1);});
 const timing=await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])));
 await page.locator('#text-process-btn').click();await expect(page.locator('#text-process-scope-info')).toContainText('仅选中的 2 条');await expect(page.locator('#text-process-selected-only')).toBeDisabled();
 await page.locator('#text-process-numbers').selectOption('toArabic');await page.locator('#text-process-confirm').click();expect(await page.evaluate(()=>DATA.segments.map(s=>s.text))).toEqual(['2个hello','3个WORLD','四个other','无标点']);
 await page.evaluate(()=>showContextMenu(500,300,0));await page.locator('#ctxmenu .ctx-submenu-trigger').getByText('英文大小写',{exact:true}).hover();await page.locator('#ctxmenu button').getByText('全大写',{exact:true}).click();expect(await page.evaluate(()=>DATA.segments.map(s=>s.text))).toEqual(['2个HELLO','3个WORLD','四个other','无标点']);
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('2个hello');
 await page.evaluate(()=>showContextMenu(500,300,0));await page.locator('#ctxmenu .ctx-submenu-trigger').getByText('数字转换',{exact:true}).hover();await page.locator('#ctxmenu button').getByText('233→二三三',{exact:true}).click();expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('两个hello');expect(await page.evaluate(()=>DATA.segments[2].text)).toBe('四个other');expect(await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])))).toBe(timing);
});

test('gap highlight defaults to 200ms and is controlled from list settings',async({page})=>{
 await fixture(page);expect(await page.evaluate(()=>subtitleGapHighlightMs)).toBe(200);await expect(page.locator('.waveform-subtitle-gap-highlight')).toHaveCount(1);await expect(page.locator('#subtitle-gap-highlight-btn')).toHaveCount(0);
 await page.locator('#cue-list-settings-toggle').click();await expect(page.locator('#list-gap-highlight-enabled')).toBeChecked();await expect(page.locator('#list-gap-highlight-ms')).toHaveValue('200');
 await page.locator('#list-gap-highlight-ms').fill('350');await page.locator('#list-gap-highlight-ms').press('Tab');await expect(page.locator('.waveform-subtitle-gap-highlight')).toHaveCount(3);
 await page.locator('#list-gap-highlight-enabled').uncheck();await expect(page.locator('.waveform-subtitle-gap-highlight')).toHaveCount(0);await page.reload();await fixture(page);expect(await page.evaluate(()=>subtitleGapHighlightMs)).toBe(0);
});


test('silent audio removal is absent and Alt drag cannot create gaps',async({page})=>{
 await fixture(page);await expect(page.locator('#gap-remove-manage,#gap-remove-panel,#gap-removed-export-dropdown,#help-tab-gap,#gap-remove-operation-mode,#gap-skip-playback,#gap-operation-mode-settings-title,#gap-settings-help')).toHaveCount(0);
 await page.evaluate(()=>showWaveformBlankMenu(5000,500,300));await expect(page.locator('#ctxmenu')).not.toContainText('添加空隙');await page.keyboard.press('Escape');
 const before=await page.evaluate(()=>JSON.stringify(DATA.gap_remove));const row=page.locator('.waveform-row').first(),r=await row.boundingBox();await page.keyboard.down('Alt');await page.mouse.move(r.x+100,r.y+10);await page.mouse.down();await page.mouse.move(r.x+160,r.y+10,{steps:6});await page.mouse.up();await page.keyboard.up('Alt');expect(await page.evaluate(()=>JSON.stringify(DATA.gap_remove))).toBe(before);
 await page.evaluate(()=>{DATA.gap_remove={version:1,gaps:[{start:100,end:200,removed:true,source:'manual'}]};waveformEditor.render();});await expect(page.locator('.waveform-gap-block')).toHaveCount(0);expect(await page.evaluate(()=>JSON.parse(buildJson()).gap_remove.gaps.length)).toBe(1);
});


test('context space removal affects selection only and supports undo',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[0].text=' A　B  C ';DATA.segments[1].text='D E';renderAll();selectOnly(0);});
 const timing=await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])));
 await page.evaluate(()=>showContextMenu(500,300,0));await page.locator('#ctxmenu .item').getByText('删除空格',{exact:true}).click();
 expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('ABC');expect(await page.evaluate(()=>DATA.segments[1].text)).toBe('D E');expect(await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])))).toBe(timing);
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>DATA.segments[0].text)).toBe(' A　B  C ');
});

test('context transforms hover sideways, stay open across transition and flip at right edge',async({page})=>{
 await fixture(page);
 for(const x of [450,1270]) {
  await page.evaluate(x=>showContextMenu(x,350,0),x);const trigger=page.locator('.ctx-submenu-trigger').getByText('数字转换',{exact:true});await trigger.hover();
  const submenu=page.locator('.ctx-submenu[aria-label="数字转换"]');await expect(submenu).toBeVisible();await expect(submenu.locator('button')).toHaveText(['233→二三三','二三三→233']);const a=await trigger.boundingBox(),b=await submenu.boundingBox();
  if(x===450) expect(b.x).toBeGreaterThanOrEqual(a.x+a.width-2);else expect(b.x+b.width).toBeLessThanOrEqual(a.x+2);
  expect(b.x).toBeGreaterThanOrEqual(0);expect(b.x+b.width).toBeLessThanOrEqual(1280);await submenu.locator('button').first().hover();await page.waitForTimeout(220);await expect(submenu).toBeVisible();
  await page.locator('.ctx-submenu-trigger').getByText('英文大小写',{exact:true}).hover();await expect(submenu).not.toBeVisible();await expect(page.locator('.ctx-submenu[aria-label="英文大小写"]')).toBeVisible();
  await page.keyboard.press('Escape');
 }
 await page.evaluate(()=>showContextMenu(450,350,0));const trigger=page.locator('.ctx-submenu-trigger').getByText('英文大小写',{exact:true});await trigger.focus();await page.keyboard.press('ArrowRight');await expect(page.locator('.ctx-submenu[aria-label="英文大小写"] button').first()).toBeFocused();await page.keyboard.press('ArrowDown');await expect(page.locator('.ctx-submenu[aria-label="英文大小写"] button').nth(1)).toBeFocused();await page.keyboard.press('ArrowLeft');await expect(trigger).toBeFocused();await expect(page.locator('.ctx-submenu[aria-label="英文大小写"]')).not.toBeVisible();
});

test('review cohort stays visible after numeric edits and resets on changed conditions',async({page})=>{
 await fixture(page);await page.evaluate(()=>{DATA.segments[1].text='2个苹果';renderAll();});await page.locator('#proofread-filter-btn').click();await page.locator('[data-filter="digits"]').click();await expect(page.locator('.cue:visible')).toHaveCount(1);await page.locator('#proofread-filter-btn').click();
 await page.evaluate(()=>selectOnly(1));const before=await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])));
 await page.evaluate(()=>showContextMenu(500,300,1));await page.locator('.ctx-submenu-trigger').getByText('数字转换',{exact:true}).hover();await page.locator('#ctxmenu button').getByText('233→二三三',{exact:true}).click();
 await expect(page.locator('.cue:visible')).toHaveCount(1);await expect(page.locator('.cue:visible')).toContainText('二个苹果');await page.evaluate(()=>renderAll());await expect(page.locator('.cue:visible')).toHaveCount(1);
 expect(await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])))).toBe(before);
 await page.evaluate(()=>performUndo());await expect(page.locator('.cue:visible')).toContainText('2个苹果');
 await page.evaluate(()=>performRedo());await expect(page.locator('.cue:visible')).toContainText('二个苹果');
 await page.locator('#proofread-filter-btn').click();await page.locator('[data-filter="all"]').click();await page.locator('[data-filter="digits"]').click();await expect(page.locator('.cue:visible')).toHaveCount(0);
});

test('punctuation deletion retains filtered rows, respects selection and undoes',async({page})=>{
 await fixture(page);await page.locator('#proofread-filter-btn').click();await page.locator('[data-filter="punctuation"]').click();await page.locator('#proofread-filter-btn').click();await page.evaluate(()=>selectOnly(0));
 const before=await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])));
 await page.evaluate(()=>showContextMenu(500,300,0));await page.locator('#ctxmenu .item').getByText('删除标点符号',{exact:true}).click();
 await expect(page.locator('.cue:visible')).toHaveCount(1);await expect(page.locator('.cue:visible')).toContainText('曲水试验');expect(await page.evaluate(()=>DATA.segments[1].text)).toBe('二个苹果');expect(await page.evaluate(()=>JSON.stringify(DATA.segments.map(s=>[s.start,s.end,s.items])))).toBe(before);
 await page.evaluate(()=>performUndo());await expect(page.locator('.cue:visible')).toContainText('曲水，试验');
});
