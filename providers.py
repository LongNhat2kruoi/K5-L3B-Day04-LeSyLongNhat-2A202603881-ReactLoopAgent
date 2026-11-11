"""Provider adapters sharing one interface. Does not contain the agent loop."""
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid

CONFIG = {
    # ``grok`` is kept as a friendly alias for xAI so existing .env files work.
    'grok': ('GROK_API_KEY', 'https://api.x.ai/v1/chat/completions'),
    'xai': ('XAI_API_KEY', 'https://api.x.ai/v1/chat/completions'),
    'openai': ('OPENAI_API_KEY', 'https://api.openai.com/v1/chat/completions'),
    'gemini': ('GEMINI_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'),
    'openrouter': ('OPENROUTER_API_KEY', 'https://openrouter.ai/api/v1/chat/completions'),
    'anthropic': ('ANTHROPIC_API_KEY', 'https://api.anthropic.com/v1/messages'),
    'opencode': ('OPENCODE_API_KEY', 'https://opencode.ai/inference/go/openai/v1/chat/completions'),
}

_GEMINI_RATE_LOCK = threading.Lock()
_LAST_GEMINI_REQUEST = 0.0


def _post_json_once(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', **headers})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Do not print response bodies: they may contain account or request data.
        raise RuntimeError(f'Provider trả HTTP {exc.code}; kiểm tra model, key và quota.') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Không kết nối được provider: {exc.reason}') from exc


def post_json(url, headers, payload):
    """Retry transient HTTP failures without retrying auth/model errors."""
    try:
        max_retries = max(0, int(os.getenv('PROVIDER_MAX_RETRIES', '3')))
    except ValueError:
        max_retries = 3
    for attempt in range(max_retries + 1):
        try:
            return _post_json_once(url, headers, payload)
        except RuntimeError as exc:
            message = str(exc)
            retryable = any(f'HTTP {code}' in message for code in (429, 500, 502, 503, 504))
            if not retryable or attempt >= max_retries:
                raise
            time.sleep(min(30.0, 2.0 ** attempt))


class Provider:
    """complete(messages, schemas) -> {message, calls, finish, usage}.

    messages: system/user/assistant/tool theo format Chat Completions. message trả về
    cần được append nguyên vẹn; tool result có role, tool_call_id, content (JSON string).
    """
    def __init__(self, name, model):
        if name not in CONFIG:
            raise ValueError(f'Provider không hợp lệ: {name}')
        if not model:
            raise ValueError('Cần đặt MODEL là model có hỗ trợ tool calling.')
        self.name, self.model = name, model
        key_name, default_url = CONFIG[name]
        if name == 'grok' and not os.getenv(key_name) and os.getenv('XAI_API_KEY'):
            key_name = 'XAI_API_KEY'
        if name == 'opencode':
            if os.getenv('OPENCODE_GO_API_KEY'):
                key_name = 'OPENCODE_GO_API_KEY'
            elif not os.getenv(key_name) and os.getenv('API_KEY'):
                key_name = 'API_KEY'
        if name == 'opencode':
            endpoint = os.getenv('OPENCODE_API_ENDPOINT') or os.getenv('API_ENDPOINT') or default_url.rsplit('/chat/completions', 1)[0]
            self.url = endpoint.rstrip('/') + '/chat/completions'
        else:
            self.url = default_url
        self.key = os.getenv(key_name)
        if not self.key:
            raise ValueError(f'Thiếu {key_name}; xem README.md.')
        self.session_id = str(uuid.uuid4()) if name == 'opencode' else None

    def complete(self, messages, schemas):
        if self.name == 'anthropic':
            return self._anthropic(messages, schemas)
        payload = {'model': self.model, 'messages': messages}
        if schemas:
            payload['tools'] = schemas
        headers = {'Authorization': f'Bearer {self.key}'}
        if self.name == 'opencode':
            headers.update({
                'User-Agent': 'StatusAgentLab/1.0',
                'x-opencode-session': self.session_id,
            })
            payload.setdefault('max_tokens', 1024)
        self._throttle()
        data = post_json(self.url, headers, payload)
        choice = data['choices'][0]
        message = choice['message']
        calls = [{'id': c['id'], 'name': c['function']['name'], 'arguments': c['function']['arguments']} for c in message.get('tool_calls', [])]
        return {'message': message, 'calls': calls, 'finish': choice.get('finish_reason'), 'usage': data.get('usage', {})}

    def _throttle(self):
        """Space Gemini requests to avoid exhausting provider RPM quotas."""
        global _LAST_GEMINI_REQUEST
        if self.name != 'gemini':
            return
        try:
            rpm = float(os.getenv('REQUESTS_PER_MINUTE', '10'))
        except ValueError:
            rpm = 10.0
        if rpm <= 0:
            return
        interval = 60.0 / rpm
        with _GEMINI_RATE_LOCK:
            now = time.monotonic()
            wait = interval - (now - _LAST_GEMINI_REQUEST)
            if wait > 0:
                time.sleep(wait)
            _LAST_GEMINI_REQUEST = time.monotonic()

    def _anthropic(self, messages, schemas):
        system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
        native = []
        for m in messages:
            if m['role'] == 'system':
                continue
            if m['role'] == 'assistant':
                blocks = []
                if m.get('content'):
                    blocks.append({'type': 'text', 'text': m['content']})
                for call in m.get('tool_calls', []):
                    blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'], 'input': json.loads(call['function']['arguments'])})
                native.append({'role': 'assistant', 'content': blocks})
            elif m['role'] == 'tool':
                block = {'type': 'tool_result', 'tool_use_id': m['tool_call_id'], 'content': m['content']}
                if native and native[-1]['role'] == 'user' and isinstance(native[-1]['content'], list):
                    native[-1]['content'].append(block)
                else:
                    native.append({'role': 'user', 'content': [block]})
            else:
                native.append({'role': 'user', 'content': m['content']})
        tools = [{'name': x['function']['name'], 'description': x['function']['description'], 'input_schema': x['function']['parameters']} for x in schemas]
        payload = {'model': self.model, 'max_tokens': 1024, 'system': system, 'messages': native}
        if tools:
            payload['tools'] = tools
        data = post_json(self.url, {'x-api-key': self.key, 'anthropic-version': '2023-06-01'}, payload)
        blocks = data['content']
        calls = [{'id': b['id'], 'name': b['name'], 'arguments': json.dumps(b['input'], ensure_ascii=False)} for b in blocks if b['type'] == 'tool_use']
        text = '\n'.join(b['text'] for b in blocks if b['type'] == 'text')
        message = {'role': 'assistant', 'content': text or None}
        if calls:
            message['tool_calls'] = [{'id': c['id'], 'type': 'function', 'function': {'name': c['name'], 'arguments': c['arguments']}} for c in calls]
        reason = {'end_turn': 'stop', 'tool_use': 'tool_calls', 'max_tokens': 'length'}.get(data.get('stop_reason'), data.get('stop_reason'))
        return {'message': message, 'calls': calls, 'finish': reason, 'usage': data.get('usage', {})}
