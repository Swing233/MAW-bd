import inspect
import unittest
from generate_subtitle_local import build_parser
from generate_subtitle_qwen_api import (
    QWEN_AUDIO_NATURAL_MAX_LEN, QWEN_AUDIO_NATURAL_MIN_LEN, QWEN_AUDIO_HARD_MAX_LEN,
    split_words_to_segments, split_segments_auto, build_segments_from_api_sentences,
)
from maw.bdversion.segment import resegment_segments, DEFAULT_MAX_LEN, DEFAULT_MIN_LEN
from maw.bdversion.revise import resegment_project
from maw.local_asr import build_local_segments, LocalTranscription


def items(text):
    return [{'text': c, 'start': i * 100, 'end': (i + 1) * 100} for i, c in enumerate(text)]


class SegmentationLengthTests(unittest.TestCase):
    def test_all_defaults_have_no_minimum_and_thirty_maximum(self):
        parsed = build_parser().parse_args(['input.wav'])
        self.assertEqual((parsed.max_len, parsed.min_len), (30, 0))
        self.assertEqual((DEFAULT_MAX_LEN, DEFAULT_MIN_LEN), (30, 0))
        self.assertEqual((QWEN_AUDIO_NATURAL_MAX_LEN, QWEN_AUDIO_HARD_MAX_LEN, QWEN_AUDIO_NATURAL_MIN_LEN), (30, 30, 0))
        for function in (build_local_segments, resegment_project):
            params = inspect.signature(function).parameters
            self.assertEqual((params['max_len'].default, params['min_len'].default), (30, 0))

    def test_short_unpunctuated_tail_is_not_merged(self):
        data = items('今天开始。好')
        segments = split_words_to_segments(data, max_len=30)
        self.assertEqual([s['text'] for s in segments], ['今天开始。', '好'])
        self.assertEqual([i for s in segments for i in s['items']], data)

    def test_twenty_nine_characters_stay_whole(self):
        text = '今天我们继续介绍字幕编辑的完整流程然后演示如何导入音频文件'
        text = text[:29]
        result = split_segments_auto(items(text), max_len=30, min_len=0, gap_split_ms=750, natural_cjk=True, split_mode='continuous')
        self.assertEqual([s['text'] for s in result], [text])

    def test_long_cloud_and_local_cues_stay_within_thirty(self):
        text = '我们先检查音频然后继续编辑字幕因为需要保留实际语音所以最后导出字幕' * 3
        data = items(text)
        cloud = build_segments_from_api_sentences([{'text': text, 'start': 0, 'end': data[-1]['end'], 'items': data}], max_len=30, min_len=0, gap_split_ms=750, split_mode='continuous')
        local = build_local_segments(LocalTranscription(text=text, language='zh', items=data, segments=[], model='test', split_mode='continuous'), duration_ms=data[-1]['end'], strip_tail_punct='')
        for result in (cloud, local):
            self.assertTrue(all(0 < len(s['text']) <= 30 for s in result))
            self.assertEqual(''.join(s['text'] for s in result), text)
            self.assertEqual([i for s in result for i in s['items']], data)

    def test_manual_coarse_split_retains_metadata_and_thirty_limit(self):
        text = '我们先检查音频然后继续编辑字幕因为需要保留实际语音所以最后导出字幕' * 2
        result = resegment_segments([{'text':text, 'start':100, 'end':8100, 'speaker':'A', 'color':'#ff0000'}])
        self.assertEqual(''.join(s['text'] for s in result), text)
        self.assertTrue(all(0 < len(s['text']) <= 30 for s in result))
        self.assertTrue(all(s['speaker']=='A' and s['color']=='#ff0000' for s in result))
        self.assertEqual((result[0]['start'], result[-1]['end']), (100, 8100))
