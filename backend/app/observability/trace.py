"""Per-turn accounting shared by the classifier, SDK runners and answer reviewer."""
from contextvars import ContextVar
from datetime import datetime, timezone
import time
import uuid

from agents import RunHooks

current_trace = ContextVar('pet_chat_trace', default=None)


def usage_values(usage):
    if usage is None:
        return None
    def field(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
    values = {name: field(usage, name) for name in ('input_tokens', 'output_tokens', 'total_tokens')}
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in values.values()):
        return None
    # SDK normalises omitted provider usage to zero; don't report that as measured usage.
    if not values['total_tokens']:
        return None
    values['cached_tokens'] = field(field(usage, 'input_tokens_details'), 'cached_tokens')
    values['reasoning_tokens'] = field(field(usage, 'output_tokens_details'), 'reasoning_tokens')
    return values


class TurnTrace:
    def __init__(self, session_id, question, language):
        self.trace_id = 'trace_' + uuid.uuid4().hex
        self.session_id = session_id or 'anonymous_' + uuid.uuid4().hex
        self.question, self.language = question, language
        self.started_at = datetime.now(timezone.utc)
        self.started = time.perf_counter()
        self.first_token_ms = None
        self.duration_ms = None
        self.spans = []
        self.answer = None
        self.model = None
        self.routing = None
        self.status = 'running'
        self.error_type = None
        self.storage_status = 'disabled'

    def start(self, kind, name, model=None):
        span = {'id': uuid.uuid4().hex, 'kind': kind, 'name': str(name), 'model': model,
                'started_ms': round((time.perf_counter()-self.started)*1000, 2), 'status': 'running', 'usage': None}
        self.spans.append(span)
        return span

    def end(self, span, status='success', usage=None, error=None):
        span.update(status=status, duration_ms=round((time.perf_counter()-self.started)*1000-span['started_ms'], 2))
        span['usage'] = usage_values(usage)
        if error:
            span['error_type'] = type(error).__name__

    def delta(self, text):
        if text and self.first_token_ms is None:
            self.first_token_ms = round((time.perf_counter()-self.started)*1000, 2)

    def finish(self, status, response=None, error=None):
        self.status = status
        self.duration_ms = round((time.perf_counter()-self.started)*1000, 2)
        if response is not None:
            self.answer, self.model = response.answer, response.model
            self.routing = response.routing.model_dump() if response.routing else None
        self.error_type = type(error).__name__ if error else None
        for span in self.spans:
            if span['status'] == 'running':
                self.end(span, 'cancelled' if status == 'cancelled' else 'error')

    def metrics(self):
        models = [s for s in self.spans if s['kind'] == 'model']
        measured = [s['usage'] for s in models if s['usage'] is not None]
        complete = len(models) == len(measured)
        def total(key):
            return sum(u[key] for u in measured) if measured and all(u.get(key) is not None for u in measured) else (0 if not models else None)
        return {'duration_ms': self.duration_ms, 'first_token_ms': self.first_token_ms,
                'model_calls': len(models), 'tool_calls': sum(s['kind'] == 'tool' for s in self.spans),
                'input_tokens': total('input_tokens'), 'output_tokens': total('output_tokens'),
                'total_tokens': total('total_tokens'), 'cached_tokens': total('cached_tokens'),
                'reasoning_tokens': total('reasoning_tokens'), 'usage_complete': complete,
                'storage_status': self.storage_status}

    def record(self):
        return {'trace_id': self.trace_id, 'session_id': self.session_id, 'question': self.question,
                'language': self.language, 'started_at': self.started_at, 'status': self.status,
                'answer': self.answer, 'model': self.model, 'routing': self.routing,
                'error_type': self.error_type, 'metrics': self.metrics(), 'spans': self.spans}


async def observed_response(stage, model, call):
    trace = current_trace.get()
    span = trace.start('model', stage, model) if trace else None
    try:
        result = await call()
    except BaseException as exc:
        if trace:
            trace.end(span, 'error', error=exc)
        raise
    if trace:
        trace.end(span, usage=getattr(result, 'usage', None))
    return result


class TraceHooks(RunHooks):
    def __init__(self, stage, model):
        self.stage, self.model = stage, model
        self.models, self.tools = [], {}

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        if trace := current_trace.get():
            self.models.append(trace.start('model', self.stage, self.model))

    async def on_llm_end(self, context, agent, response):
        if (trace := current_trace.get()) and self.models:
            trace.end(self.models.pop(0), usage=response.usage)
            # Hosted web tools execute at the provider, so local tool hooks don't see them.
            for item in response.output:
                if getattr(item, 'type', None) == 'web_search_call':
                    span = trace.start('tool', 'web_search')
                    trace.end(span, 'success' if getattr(item, 'status', None) == 'completed' else 'error')
                    span['duration_ms'] = None  # Provider does not supply hosted-tool timing.

    async def on_tool_start(self, context, agent, tool):
        if trace := current_trace.get():
            key = getattr(context, 'tool_call_id', None) or id(context)
            self.tools[key] = trace.start('tool', tool.name)

    async def on_tool_end(self, context, agent, tool, result):
        key = getattr(context, 'tool_call_id', None) or id(context)
        if (trace := current_trace.get()) and (span := self.tools.pop(key, None)):
            trace.end(span)
