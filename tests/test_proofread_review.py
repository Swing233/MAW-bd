import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from maw.bdversion.review import apply_review_decisions, review_rows
from maw.bdversion.revise import revise_project
from maw.focus_launcher import FocusedLauncherApi
from maw.project import normalize_project, validate_project

def project():
    return {"segments": [{"start": 0, "end": 1000, "text": "曲水", "items": [{"text": "曲水", "start": 0, "end": 1000}], "speaker": "1", "proofread": {"status": "verified", "asr_original": "曲水", "corrected": "驱水"}}, {"start": 1100, "end": 2000, "text": "二个", "items": [], "proofread": {"status": "uncertain", "asr_original": "二个", "corrected": "2个"}}]}

class ProofreadReviewTests(unittest.TestCase):
    def test_choices_keep_time_and_input_immutable(self):
        p = project(); before = copy.deepcopy(p)
        result = apply_review_decisions(p, [{"index": 0, "accepted": True}, {"index": 1, "accepted": False}])
        self.assertEqual(p, before)
        self.assertEqual([s["text"] for s in result["segments"]], ["驱水", "二个"])
        for old, new in zip(p["segments"], result["segments"]):
            for key in ("start", "end", "items", "speaker"):
                self.assertEqual(old.get(key), new.get(key))
        self.assertEqual(result["segments"][1]["proofread"]["review_state"], "rejected")
        normalize_project(result)

    def test_invalid_and_manual_choices_rejected(self):
        for choices in ([{"index": 0, "accepted": 1}], [{"index": True, "accepted": True}], [{"index": 9, "accepted": True}], [{"index": 0, "accepted": True}] * 2, [None]):
            with self.assertRaises(ValueError): apply_review_decisions(project(), choices)
        p = project(); p["segments"][0]["proofread"].update(status="manual", review_text="驱水")
        self.assertTrue(review_rows(p)[0]["locked"])
        with self.assertRaises(ValueError): apply_review_decisions(p, [{"index": 0, "accepted": True}])

    def test_old_project_and_optional_metadata_validation(self):
        normalize_project({"segments": [{"start": 0, "end": 1, "text": "旧"}]})
        p = project();p["segments"][0]["proofread"]["review_state"] = "bogus"
        self.assertTrue(validate_project(p).errors)

    def test_backend_saves_final_srt_and_refuses_stale_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"clip.mosp";source.write_text(json.dumps(project()),encoding="utf8")
            api=FocusedLauncherApi();api._result["revisedProjectPath"]=str(source)
            data=api.get_proofread_review();self.assertTrue(data["ok"])
            self.assertFalse(api.apply_proofread_review({"token":"stale","choices":[]})["ok"])
            out=api.apply_proofread_review({"token":data["token"],"choices":[{"index":0,"accepted":True},{"index":1,"accepted":False}]})
            self.assertTrue(out["ok"],out)
            srt=Path(out["srtPath"]).read_text();self.assertIn("驱水",srt);self.assertIn("二个",srt);self.assertNotIn("proofread",srt)
            self.assertEqual(json.loads(source.read_text()),project())

    def test_launcher_requests_suggestions_without_applying_text(self):
        api=FocusedLauncherApi()
        with patch("maw.focus_launcher.revise_project",return_value={"ok":True,"projectPath":"suggestions.mosp","changedCues":1}) as revise:
            api._revise_worker("original.mosp","deepseek","test-placeholder","deepseek-flash","","")
        self.assertFalse(revise.call_args.kwargs["apply_to_text"])
        self.assertTrue(api._result["reviewRun"])

    def test_deepseek_suggestions_preserve_timeline_and_manual_cues(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=project();p["segments"][1]["proofread"]["status"]="manual"
            source=Path(tmp)/"clip.mosp";source.write_text(json.dumps(p),encoding="utf8")
            def complete(settings, prompt, payload):
                self.assertEqual(len(payload),1)
                return {"results":[{"id":payload[0]["cue_id"],"corrected_text":"驱水","status":"verified","changed":True,"reason":"同音"}]}
            out=revise_project(source,api_key="test-placeholder",apply_to_text=False,complete=complete)
            self.assertTrue(out["ok"],out)
            revised=json.loads(Path(out["projectPath"]).read_text())
            self.assertEqual([s["text"] for s in revised["segments"]],["曲水","二个"])
            for old,new in zip(p["segments"],revised["segments"]):
                for key in ("start","end","items"):self.assertEqual(old[key],new[key])
            self.assertEqual(revised["segments"][0]["proofread"]["review_state"],"pending")

    def test_custom_mode_suggestions_wait_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/"clip.mosp";source.write_text(json.dumps(project()),encoding="utf8")
            def complete(settings, prompt, cues):
                return {"groups":[{"source_ids":[cue["id"]],"text":"驱水" if i==0 else cue["text"]} for i,cue in enumerate(cues)]}
            out=revise_project(source,mode="custom",custom_prompt="保守改错字",api_key="test-placeholder",apply_to_text=False,complete=complete)
            self.assertTrue(out["ok"],out)
            p=json.loads(Path(out["projectPath"]).read_text())
            self.assertEqual(p["segments"][0]["text"],"曲水")
            self.assertEqual(p["segments"][0]["proofread"]["review_text"],"驱水")
