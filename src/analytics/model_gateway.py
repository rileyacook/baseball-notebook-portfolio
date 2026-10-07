"""Server-only model transport; never grants database or filesystem access."""
from copy import deepcopy
from collections import deque
import os
import threading
import time
import httpx

GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
SUPPORTED = {'qwen/qwen3.8-27b', 'openai/gpt-oss-20b', 'openai/gpt-oss-120b'}
_lock = threading.Lock()
_calls = deque()


def strict_schema(schema):
    result = deepcopy(schema)
    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get('type') == 'object':
            node['additionalProperties'] = False
            node['required'] = sorted(node.get('properties', {}))
        if 'enum' in node and 'type' not in node:
            types = set('null' if v is None else 'string' if isinstance(v, str) else 'integer' for v in node['enum'])
            node['type'] = sorted(types)
        for value in node.values():
            if isinstance(value, dict):
                walk(value)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
    walk(result)
    return result


def post_model(url, *, json, timeout):
    """Preserve Ollama's result shape so the existing validators stay in force."""
    if os.environ.get('MODEL_PROVIDER', 'ollama') == 'ollama':
        return httpx.post(url, json=json, timeout=timeout)
    if os.environ.get('MODEL_PROVIDER') != 'groq':
        raise httpx.RequestError('Unsupported model configuration.')
    key = os.environ.get('GROQ_API_KEY', '')
    model = os.environ.get('GROQ_MODEL', 'qwen/qwen3.8-27b')
    if not key or model not in SUPPORTED:
        raise httpx.RequestError('The hosted model needs valid server configuration.')
    payload = {
        'model': model, 'messages': json['messages'], 'stream': False,
        'temperature': 0, 'reasoning_effort': 'none' if model.startswith('qwen/') else 'low',
        'max_completion_tokens': 768 if 'query_id' in json['format'].get('properties', {}) else 1024,
        'response_format': {'type': 'json_schema', 'json_schema': {
            'name': 'baseball_request', 'strict': True, 'schema': strict_schema(json['format'])}},
    }
    with _lock:
        now = time.monotonic()
        while _calls and now - _calls[0] >= 60:
            _calls.popleft()
        if len(_calls) >= 2:
            raise httpx.RequestError('The free model allowance is busy. Please retry shortly.')
        # Allow an edit plus translation for a follow-up. Provider token limits still apply.
        _calls.append(now)
    response = httpx.post(GROQ_URL, json=payload, headers={'Authorization': 'Bearer ' + key}, timeout=timeout)
    response.raise_for_status()
    try:
        data = response.json()
        choice = data['choices'][0]
        content = choice['message']['content']
        if choice.get('finish_reason') != 'stop' or not isinstance(content, str):
            raise ValueError('Incomplete model output.')
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise httpx.RequestError('The model returned an incomplete response.') from error
    return httpx.Response(200, json={'message': {'content': content}}, request=httpx.Request('POST', GROQ_URL))
