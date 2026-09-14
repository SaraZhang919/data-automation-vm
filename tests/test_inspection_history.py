import unittest
from iboomto.inspection_history import merge_observation, seed_observations


def observation(verdict='PASS', date='2026-09-14T08:00:00Z', status='success'):
    return {'id': 'https://www.iboomto.com/es/a', 'url': 'https://www.iboomto.com/es/a',
            'api_status': status, 'verdict': verdict, 'checked_at': date}


class InspectionHistoryTests(unittest.TestCase):
    def test_first_observation_and_unchanged_state(self):
        first, event = merge_observation({}, observation())
        self.assertEqual(event['event_type'], 'baseline')
        second, event = merge_observation(first, observation(date='2026-09-15T08:00:00Z'))
        self.assertIsNone(event)
        self.assertEqual(second['first_observed_indexed_at'], first['checked_at'])
        self.assertEqual(second['index_state_observed_at'], second['checked_at'])

    def test_transitions_and_reindexing(self):
        row, _ = merge_observation({}, observation('NEUTRAL'))
        indexed, event = merge_observation(row, observation(date='2026-09-17T08:00:00Z'))
        self.assertEqual(event['previous_state'], 'not_indexed')
        self.assertEqual(event['previous_observed_at'], row['checked_at'])
        dropped, event = merge_observation(indexed, observation('FAIL', '2026-09-20T08:00:00Z'))
        self.assertEqual(event['current_state'], 'not_indexed')
        recovered, _ = merge_observation(dropped, observation(date='2026-09-23T08:00:00Z'))
        self.assertEqual(recovered['first_observed_indexed_at'], indexed['checked_at'])
        self.assertEqual(recovered['last_observed_not_indexed_at'], dropped['checked_at'])

    def test_failed_call_preserves_success_and_not_a_transition(self):
        row, _ = merge_observation({}, observation())
        failed, event = merge_observation(row, {'url': row['url'], 'id': row['id'],
            'checked_at': '2026-09-15T08:00:00Z', 'api_status': 'failed', 'error_type': 'ApiFailure'})
        self.assertIsNone(event)
        self.assertEqual(failed['verdict'], 'PASS')
        self.assertEqual(failed['last_successful_checked_at'], row['checked_at'])
        self.assertEqual(failed['last_known_index_state'], 'indexed')
        recovered, event = merge_observation(failed, observation(date='2026-09-16T08:00:00Z'))
        self.assertIsNone(event)
        self.assertEqual(recovered['error_type'], '')

    def test_unknown_success_is_not_deindexing(self):
        row, _ = merge_observation({}, observation())
        unknown, event = merge_observation(row, observation('VERDICT_UNSPECIFIED'))
        self.assertIsNone(event)
        self.assertEqual(unknown['last_known_index_state'], 'indexed')
        self.assertEqual(unknown['last_observed_not_indexed_at'], '')

    def test_seed_is_idempotent_and_explicit_about_history(self):
        seeded, events = seed_observations([observation(), observation(status='failed')])
        self.assertEqual(len(events), 1)
        self.assertEqual(seeded[0]['first_observed_indexed_basis'], 'retained_snapshot')
        self.assertEqual(seeded[1]['first_observed_indexed_at'], '')
        again, events = seed_observations(seeded)
        self.assertEqual(again, seeded)
        self.assertEqual(events, [])

    def test_history_retry_has_same_id(self):
        first = merge_observation({}, observation())[1]
        second = merge_observation({}, observation())[1]
        self.assertEqual(first['id'], second['id'])
