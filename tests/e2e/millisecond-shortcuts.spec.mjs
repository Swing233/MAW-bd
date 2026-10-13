import {expect,test} from '@playwright/test';
import {startScrollFixture} from './cue-scroll-fixture.mjs';
let server;
test.afterEach(async()=>{await server?.stop();server=null;});
async function open(page){
 server=await startScrollFixture({count:8});
 await page.addInitScript(()=>localStorage.setItem('moy.asr.editor.settings.v1',JSON.stringify({autoSaveProject:false})));
 await page.goto(server.url);await page.waitForFunction(()=>typeof renderAll==='function' && DATA.segments.length===8);
 await page.locator('#editor-loading').waitFor({state:'hidden'});
}
test('remove spaces shortcut affects selected cues only and can be undone',async({page})=>{
 await open(page);
 await expect(page.locator('#fcpxml-export-fps')).toHaveValue('30');
 await page.evaluate(()=>{DATA.segments[0].text='A B';DATA.segments[1].text='保 留';renderAll();selectOnly(0);});
 const before=await page.evaluate(()=>JSON.stringify(DATA.segments));
 await page.keyboard.press('Alt+Shift+Backspace');
 expect(await page.evaluate(()=>DATA.segments.slice(0,2).map(s=>s.text))).toEqual(['AB','保 留']);
 await page.evaluate(()=>performUndo());expect(await page.evaluate(()=>JSON.stringify(DATA.segments))).toBe(before);
});
test('custom space shortcut persists and does not fire in text inputs',async({page})=>{
 await open(page);
 await page.evaluate(()=>{DATA.segments[0].text='A B';renderAll();selectOnly(0);});
 await page.locator('#editor-settings-toggle').click();await page.locator('#editor-settings-tab-general').click();
 await page.locator('[data-editing-shortcut="removeSpaces"]').click();await page.keyboard.press('F8');
 await expect(page.locator('[data-editing-shortcut-label="removeSpaces"]')).toHaveText('F8');
 await page.locator('#editor-settings-close').click();await page.evaluate(()=>document.activeElement?.blur());
 await page.locator('#cue-panel-text').focus();await page.keyboard.press('F8');
 expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('A B');
 await page.evaluate(()=>document.activeElement?.blur());await page.keyboard.press('F8');
 expect(await page.evaluate(()=>DATA.segments[0].text)).toBe('AB');
 expect(await page.evaluate(()=>JSON.parse(localStorage.getItem('moy.asr.editor.settings.v1')).editingShortcuts.removeSpaces)).toBe('F8');
});
