import unittest
from generate_subtitle_qwen_api import split_segments_auto, build_segments_from_api_sentences
from maw.chinese_segmentation import analyze_clauses, split_clauses
from maw.local_asr import LocalTranscription, build_local_segments
from maw.bdversion.segment import resegment_segments


def items(text):
    return [{'text':char,'start':i*150,'end':i*150+140} for i,char in enumerate(text)]


def split(text):
    return split_segments_auto(items(text),max_len=30,min_len=0,gap_split_ms=750,split_mode='continuous')


class ChineseClauseSegmentationTests(unittest.TestCase):
    def test_enumeration_keeps_comma_and_original_characters(self):
        text='我喜欢苹果，香蕉和橙子'
        self.assertEqual([s['text'] for s in split(text)],[text])
        cuts,scores=analyze_clauses(text)
        self.assertNotIn(text.index('，')+1,cuts)
        self.assertLess(scores[text.index('，')+1],0)

    def test_comma_between_complete_clauses_splits(self):
        text='今天我们完成语音识别，我们继续检查字幕'
        self.assertEqual([s['text'] for s in split(text)],['今天我们完成语音识别，','我们继续检查字幕'])

    def test_connectors_stay_with_following_clauses(self):
        text='我们已经完成语音识别因为这段音频非常清楚所以我们可以直接进入字幕编辑'
        self.assertEqual([s['text'] for s in split(text)],['我们已经完成语音识别','因为这段音频非常清楚','所以我们可以直接进入字幕编辑'])

    def test_nominal_connector_phrase_is_not_split(self):
        text='我们还需要进一步了解因为这个原因造成的变化'
        self.assertEqual(''.join(s['text'] for s in split(text)),text)
        self.assertNotIn(text.index('因为'),analyze_clauses(text)[0])

    def test_no_character_minimum_and_no_added_spaces(self):
        text='好。我们使用QwenASR进行识别，所以字幕能直接导出'
        result=split(text)
        self.assertEqual(result[0]['text'],'好。')
        self.assertEqual(''.join(s['text'] for s in result),text)
        self.assertEqual([i for s in result for i in s['items']],items(text))

    def test_atomic_real_items_are_not_interpolated(self):
        data=[{'text':'我们完成识别因为','start':100,'end':800}, {'text':'音频清楚','start':810,'end':1300}]
        self.assertEqual(split_clauses(data),[data])

    def test_cloud_local_and_manual_share_clause_boundaries(self):
        text='我们已经完成语音识别因为这段音频非常清楚所以我们可以直接进入字幕编辑'
        data=items(text)
        sentence={'start':0,'end':data[-1]['end'],'text':text,'items':data,'speaker':'A','color':'red','proofread':{'status':'verified'}}
        cloud=build_segments_from_api_sentences([sentence],max_len=30,min_len=0,gap_split_ms=750,split_mode='continuous')
        local=build_local_segments(LocalTranscription(text=text,language='zh',items=data,segments=[],model='test',split_mode='continuous'),duration_ms=data[-1]['end'],strip_tail_punct='')
        manual=resegment_segments([sentence])
        expected=[(s['text'],s['start'],s['end']) for s in cloud]
        self.assertEqual([(s['text'],s['start'],s['end']) for s in local],expected)
        self.assertEqual([(s['text'],s['start'],s['end']) for s in manual],expected)
        for s in manual:
            self.assertEqual((s['color'],s['speaker'],s['proofread']),('red','A',{'status':'verified'}))

    def test_long_chinese_keeps_thirty_limit_and_real_times(self):
        text='今天我们详细介绍字幕编辑的完整流程接下来演示如何导入视频并检查最终结果' * 15
        result=split(text)
        self.assertTrue(all(0<len(s['text'])<=30 for s in result))
        self.assertEqual(''.join(s['text'] for s in result),text)
        self.assertEqual([i for s in result for i in s['items']],items(text))
