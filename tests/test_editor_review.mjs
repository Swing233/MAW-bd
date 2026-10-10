import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
const sandbox = {}; vm.createContext(sandbox);
for (const file of ['web/editor-proofread.js', 'web/editor-review.js']) vm.runInContext(readFileSync(file, 'utf8'), sandbox);
const R = sandbox.MaweReview, P = sandbox.MaweProofread;
const plain = value => JSON.parse(JSON.stringify(value));
function cues() { return [{ id:'a',start:0,end:1000,text:'曲水',items:[{text:'曲水',start:0,end:1000}],speaker:'1',color:null,proofread:{status:'verified',asr_original:'曲水',corrected:'驱水',review_state:'pending'} }, {id:'b',start:1100,end:2000,text:'二个',items:[],proofread:{status:'uncertain',asr_original:'二个',corrected:'2个'}}]; }
test('review applies independent choices while preserving all time and metadata', () => {
 const segments=cues(), before=structuredClone(segments); const rows=R.rowsFromSegments(segments);
 R.applyDecisions(segments,rows,[{index:0,accepted:true},{index:1,accepted:false}]);
 assert.deepEqual(segments.map(s=>s.text),['驱水','二个']);
 for(let i=0;i<segments.length;i++) for(const key of ['id','start','end','items','speaker','color']) assert.deepEqual(segments[i][key],before[i][key]);
 assert.equal(segments[0].proofread.review_state,'accepted'); assert.equal(segments[1].proofread.review_state,'rejected');
 R.applyDecisions(segments,R.rowsFromSegments(segments),[{index:0,accepted:false}]); assert.equal(segments[0].text,'曲水');
});
test('stale and manual decisions fail before any mutation', () => {
 for(const mutate of [s=>s[1].text='人工文字',s=>s[1].proofread.status='manual',s=>s[1].start=1200]) {
 const segments=cues(),rows=R.rowsFromSegments(segments); mutate(segments); const before=structuredClone(segments);
 assert.throws(()=>R.applyDecisions(segments,rows,[{index:0,accepted:true},{index:1,accepted:true}])); assert.deepEqual(segments,before);
 }
});
test('old manual edits are excluded and unchanged suggestions omitted', () => {
 const segments=cues();segments[0].proofread.status='manual';segments[1].proofread.corrected='二个';assert.equal(R.rowsFromSegments(segments).length,0);
});
test('gap plan uses adjacency, threshold, selection, disabled and overlaps', () => {
 const segments=[{start:0,end:1000},{start:1100,end:2000},{start:2200,end:3000},{start:3300,end:4000}];
 assert.deepEqual(plain(R.gapPlan(segments,null,200)).map(g=>g.gap),[100,200]);
 assert.deepEqual(plain(R.gapPlan(segments,[0,2],200)),[]);
 assert.deepEqual(plain(R.gapPlan(segments,[1,2],200)).map(g=>g.index),[1]);
 assert.equal(R.gapPlan(segments,null,200).filter(g=>g.gap<200).length,1);
 segments[1].disabled=true;assert.equal(R.gapPlan(segments,null,200).length,0);
 assert.throws(()=>R.gapPlan(segments,null,-1));assert.throws(()=>R.gapPlan(segments,null,1.5));
 assert.equal(R.gapPlan([{start:0,end:1000},{start:900,end:2000}],null,500).length,0);
});
test('content filters support mixed languages and Unicode punctuation', () => {
 for(const text of ['你好，世界。','问？答！','a,b; c:','“引号”','(括号)','3.14','长—短','……']) assert.equal(P.filterPass({text},'punctuation'),true,text);
 for(const text of ['无标点','Hello world','123','🙂','空 白','a+b']) assert.equal(P.filterPass({text},'punctuation'),false,text);
 assert.equal(P.filterPass({text:'Qwen 3模型'},'english'),true);assert.equal(P.filterPass({text:'Qwen 3模型'},'digits'),true);
 assert.ok(P.FILTERS.some(f=>f.id==='punctuation'));
});


test('space filtering supports ordinary, ideographic and non-breaking spaces', () => {
 for(const text of ['hello world','中文 空格','全角　空格','不换行\u00a0空格']) assert.equal(P.filterPass({text},'spaces'),true,text);
 for(const text of ['没有空格','Hello','123','中文，标点','换\n行','制\t表']) assert.equal(P.filterPass({text},'spaces'),false,text);
});
