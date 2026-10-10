"""ASR output separators must use one space without moving the timeline."""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from maw.bdversion.text_format import normalize_asr_spacing
from maw.focus_launcher import FocusedLauncherApi
from maw.project_io import write_mosp
from maw.bdversion.revise import _load_project


class AsrSpacingTests(unittest.TestCase):
    def test_comma_and_existing_spaces_use_one_separator(self):
        project = {'segments': [{'start': 12, 'end': 1000, 'text': '你好，  世界  hello, world  1,000元',
                    'speaker': 'A', 'color_ref': 0, 'proofread': {'status': 'verified'},
                    'items': [{'text': '你好， ', 'start': 12, 'end': 500}, {'text': ' 世界', 'start': 500, 'end': 1000}]}]}
        before = deepcopy(project)
        normalize_asr_spacing(project)
        self.assertEqual(project['segments'][0]['text'], '你好 世界 hello world 1,000元')
        self.assertEqual(''.join(i['text'] for i in project['segments'][0]['items']), '你好 世界')
        for original, actual in zip(before['segments'], project['segments']):
            self.assertEqual({k: v for k, v in original.items() if k not in ('text', 'items')},
                             {k: v for k, v in actual.items() if k not in ('text', 'items')})
            self.assertEqual([(i['start'], i['end']) for i in original['items']],
                             [(i['start'], i['end']) for i in actual['items']])
        stable = deepcopy(project)
        normalize_asr_spacing(project)
        self.assertEqual(project, stable)

    def test_asr_artifacts_use_same_text_and_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            mosp = Path(directory) / 'test.mosp'; srt = Path(directory) / 'test.srt'
            write_mosp(mosp, {'segments': [{'start': 100, 'end': 1000, 'text': '你好，  世界', 'items': []}]})
            FocusedLauncherApi._normalize_asr_outputs(mosp, srt)
            project = _load_project(mosp)
            self.assertEqual(project['segments'][0]['text'], '你好 世界')
            self.assertIn('00:00:00,100 --> 00:00:01,000\n你好 世界', srt.read_text(encoding='utf-8-sig'))

    def test_thousands_separator_across_items_is_preserved(self):
        project = {'segments': [{'text': '1,000元', 'items': [{'text': text, 'start': i, 'end': i + 1} for i, text in enumerate(['1', ',', '000元'])]}]}
        normalize_asr_spacing(project)
        self.assertEqual(''.join(i['text'] for i in project['segments'][0]['items']), '1,000元')
