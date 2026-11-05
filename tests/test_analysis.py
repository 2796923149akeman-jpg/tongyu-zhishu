"""Local emotion and summary logic, without live model requests."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('analysis_under_test', ROOT / 'dashboard/analysis.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
LEXICON = analysis.load_lexicon(ROOT / 'dashboard/emotion_lexicon.json')


class AnalysisTests(unittest.TestCase):
    def test_lexicon_labels_and_attention(self):
        self.assertEqual(analysis.analyze_lexicon('今天特别开心', LEXICON)['label'], 'happy')
        watched = analysis.analyze_lexicon('我每天都哭，不想上学', LEXICON)
        self.assertEqual((watched['label'], watched['attention']), ('sad', 'watch'))
        urgent = analysis.analyze_lexicon('有人打我，救命', LEXICON)
        self.assertEqual(urgent['attention'], 'urgent')

    def test_model_failure_uses_lexicon(self):
        config = analysis.DEFAULT_ANALYSIS_CONFIG | {'emotion_model_source': 'custom', 'emotion_api_key': 'x'}
        with patch.object(analysis, 'call_json_model', side_effect=OSError('offline')):
            result = analysis.analyze_emotion('我很难过', config, LEXICON, ROOT)
        self.assertEqual(result['source'], 'lexicon-fallback')
        self.assertEqual(result['label'], 'sad')

    def test_model_cannot_downgrade_explicit_attention(self):
        config = analysis.DEFAULT_ANALYSIS_CONFIG | {'emotion_model_source': 'custom', 'emotion_api_key': 'x'}
        response = {'label': 'neutral', 'confidence': .8, 'attention': 'none', 'reason': '平静', 'attention_reason': '无'}
        with patch.object(analysis, 'call_json_model', return_value=response):
            result = analysis.analyze_emotion('有人打我，救命', config, LEXICON, ROOT)
        self.assertEqual(result['attention'], 'urgent')

    def test_local_summary_uses_user_emotions(self):
        emotion = analysis.analyze_lexicon('我有点害怕', LEXICON)
        result = analysis.local_conversation_summary([
            {'role': 'user', 'text': '我有点害怕', 'device_id': 'one', 'emotion': emotion},
            {'role': 'assistant', 'text': '我在这里陪你'},
        ], 'session-one')
        self.assertEqual(result['dominant_emotion'], 'scared')
        self.assertEqual(result['message_count'], 2)


if __name__ == '__main__':
    unittest.main()
