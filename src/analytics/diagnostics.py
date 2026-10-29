"""Allowlisted operational events. Never accept question, identity or transport text."""
import json,logging,re,sys
from uuid import uuid4

CODES={'supported','needs_clarification','unsupported','error','blocked','shared_model_limit',
'provider_rate_limit','model_timeout','model_unavailable','model_invalid_response','model_configuration',
'ollama_unavailable','unexpected_error','invalid_question','per_user_allowance','shared_query_busy',
'request_budget','preview_capacity','conversation_capacity','conversation_full','access_unavailable',
'access_denied','stale_conversation','http_error'}
ROUTES={'question','access','owner','chats','static','health','other'}
logger=logging.getLogger('baseball.operations')

def configure():
    if not logger.handlers:
        handler=logging.StreamHandler(sys.stderr);handler.setFormatter(logging.Formatter('%(message)s'));logger.addHandler(handler)
    logger.setLevel(logging.INFO);logger.propagate=False

def request_id():return uuid4().hex

def record(rid,route,status,code,elapsed_ms):
    if not isinstance(rid,str) or not re.fullmatch(r'[a-f0-9]{32}',rid):raise ValueError('Invalid diagnostic ID')
    event={'event':'baseball_request','request_id':rid,'route':route if route in ROUTES else 'other',
        'http_status':int(status),'code':code if code in CODES else 'http_error','elapsed_ms':max(0,int(elapsed_ms))}
    logger.info(json.dumps(event,separators=(',',':')))
    return event
