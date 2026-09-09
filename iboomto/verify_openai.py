"""Manual connection test. Sends fixed synthetic text, never analytics data."""
import json
import os
import requests
from .core import MODEL


def main():
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit('OPENAI_API_KEY is missing')
    try:
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': 'Bearer ' + key},
            json={
                'model': MODEL,
                'reasoning_effort': 'medium',
                'max_completion_tokens': 1024,
                'response_format': {'type': 'json_object'},
                'messages': [{'role': 'user', 'content':
                    'Synthetic API connection test. Return only JSON: '
                    '{"connection_test":"ok"}'}],
            },
            timeout=120,
        )
    except requests.RequestException:
        raise SystemExit('OpenAI connection failed; no automatic retry') from None
    if response.status_code != 200:
        raise SystemExit(f'OpenAI HTTP {response.status_code}')
    try:
        data = response.json()
        passed = json.loads(data['choices'][0]['message']['content']).get('connection_test') == 'ok'
        if not passed:
            raise ValueError('Unexpected test result')
    except (ValueError, KeyError, IndexError, TypeError):
        raise SystemExit('OpenAI responded, but the fixed JSON test did not pass') from None
    result = {'status': 'success', 'test': 'synthetic_connection_only',
              'model': data.get('model'), 'reasoning_effort': 'medium',
              'usage': data.get('usage'), 'response_id': data.get('id')}
    print(json.dumps(result))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as handle:
            handle.write('OpenAI connection test passed using fixed synthetic text. '
                         'No website, GA, GSC or other business data was sent.\n\n')
            handle.write('```json\n' + json.dumps(result, indent=2) + '\n```\n')


if __name__ == '__main__':
    main()
