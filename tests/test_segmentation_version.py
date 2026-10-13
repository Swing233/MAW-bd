"""Verify unmodified v1.8.0 rules outside the user-requested length changes."""
import ast
import hashlib
import json
from pathlib import Path
import unittest


class SegmentationVersionTests(unittest.TestCase):
    def test_segmentation_functions_match_v180_release(self):
        reference = json.loads(Path('tests/fixtures/segmentation-v1.8.0.json').read_text())
        changed = {
            'generate_subtitle_qwen_api.py': {'split_words_to_segments', '_split_cjk_group_naturally', 'split_segments_auto'},
            'generate_subtitle_local.py': {'build_parser'},
            'maw/local_asr.py': {'build_local_segments'},
            'maw/bdversion/segment.py': {'split_items_sentence_aware', 'split_coarse_segments_sentence_aware'},
        }
        for filename, functions in reference['functions'].items():
            nodes = {n.name: n for n in ast.parse(Path(filename).read_text()).body
                     if isinstance(n, ast.FunctionDef)}
            for name, expected in functions.items():
                if name in changed.get(filename, set()):
                    continue
                with self.subTest(file=filename, function=name):
                    actual = hashlib.sha256(ast.dump(nodes[name], include_attributes=False).encode()).hexdigest()
                    self.assertEqual(actual, expected)
