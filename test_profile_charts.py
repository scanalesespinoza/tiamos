import datetime as dt
import json
import unittest

from profile_charts import chart_data
from session_metrics import SessionMetrics


class ChartDataTests(unittest.TestCase):
    def test_progression_is_bounded_and_duplicate_close_does_not_grow_it(self):
        metrics = SessionMetrics()
        now = dt.datetime.now().astimezone()
        for index in range(30):
            metrics.start(now, str(index))
            metrics.action('Edición de archivos', 'ok', now)
            metrics.finish(now, index % 2 == 0)
            metrics.finish(now, True)
        stats = metrics.summary()
        self.assertEqual(len(stats['progression']), 7)
        self.assertEqual(stats['progression'][-1]['xp'], stats['xp'])
        self.assertFalse(stats['progression'][-1]['completed'])
        self.assertEqual(stats['progression'][-1]['earned'], 2)
        self.assertEqual(stats['areas']['editing']['ok'], 30)
        self.assertEqual(sum(v['ok'] for v in stats['areas'].values()), stats['total']['ok'])

    def test_change_uses_known_outcomes_and_reports_improvement_or_decline(self):
        old = [{'ok': 2, 'errors': 3}] * 3
        new = [{'ok': 4, 'errors': 1}] * 3
        change = chart_data({'progression': old + new})['change']
        self.assertEqual(change, {'points': 40, 'before': (6, 15), 'after': (12, 15)})
        self.assertEqual(chart_data({'progression': new + old})['change']['points'], -40)
        self.assertEqual(chart_data({'progression': old + old})['change']['points'], 0)

    def test_missing_or_small_samples_cannot_claim_a_trend_or_strength(self):
        self.assertIsNone(chart_data({})['change'])
        self.assertIsNone(chart_data({'progression': [{'ok': 20, 'errors': 0}]})['change'])
        self.assertIsNone(chart_data({'progression': [{'ok': 1, 'errors': 0}] * 6})['change'])
        data = chart_data({'areas': {'editing': {'ok': 1, 'errors': 0, 'unknown': 100}}})
        self.assertFalse(any(a['best'] for a in data['areas']))
        self.assertEqual(data['areas'][1]['known'], 1)
        self.assertIsNone(data['areas'][0]['rate'])

    def test_strength_is_best_known_rate_with_visible_sample_not_raw_volume(self):
        areas = {'editing': {'ok': 8, 'errors': 2}, 'validation': {'ok': 5, 'errors': 0},
                 'exploration': {'ok': 1, 'errors': 0}, 'tools': {'ok': 100, 'errors': 100}}
        data = chart_data({'areas': areas})
        self.assertEqual([a['key'] for a in data['areas'] if a['best']], ['validation'])
        self.assertEqual(data['areas'][0]['known'], 5)
        self.assertEqual(data['areas'][0]['rate'], 1)

    def test_all_areas_are_fixed_and_waits_api_failures_do_not_become_skills(self):
        metrics = SessionMetrics()
        now = dt.datetime.now().astimezone()
        metrics.start(now, 'PRIVATE_TURN')
        for label in ('Pruebas y validación', 'Edición de archivos', 'Investigación',
                      'Revisión de cambios', 'PRIVATE_TOOL', 'Esperando una herramienta', 'Error de Claude'):
            metrics.action(label, 'info', now)
        stats = metrics.summary()
        self.assertEqual(sum(a['unknown'] for a in stats['areas'].values()), 5)
        self.assertNotIn('PRIVATE', json.dumps(stats))


if __name__ == '__main__':
    unittest.main()
