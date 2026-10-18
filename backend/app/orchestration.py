"""Bounded, explainable local trigger policy. No inference of identity or approval."""
from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata

POLICY_VERSION='content-trigger-v1'
PROMPT_VERSION='live-context-v2'

def freshness_safe_smalltalk(text):
    # Bare acknowledgements can accept/reject a proposal; only social phrases
    # are safe to append without invalidating an in-flight answer.
    return bool(re.fullmatch(r'(?:hello|hi|good (?:morning|afternoon|evening)|thanks|thank you|cam on|xin chao)[? ]*',meaning_key(text)))

def retrieval_query(segments,question='',focus=()):
    primary=next((s for s in reversed(segments) if s['id'] in focus),segments[-1])
    text=question.strip() or primary['text']
    if len(text.split())<=12 and re.search(r'\b(?:that|this|it|those|option|approach|cach do|phuong an do)\b',text,re.I):
        index=segments.index(primary)
        text+=' '+' '.join(s['text'] for s in segments[max(0,index-3):index])
    return text

def card_key(payload,snapshot):
    # Exact output plus full semantic context. Different IDs/questions, approval,
    # numbers, owners or environment remain distinct even when output text repeats.
    body=payload.model_dump();body.pop('input_revision',None)
    context={k:v for k,v in snapshot.items() if k not in ('segments','memory','input_hash','transcript_revision','routing','retrieval_ms')}
    context['routing']={k:v for k,v in snapshot.get('routing',{}).items() if k!='classifier_ms'}
    for field in ('segments','memory'):
        context[field]=[dict(id=s['id'],speaker=s.get('speaker'),text=meaning_key(s['text'])) for s in snapshot.get(field,[])]
    return hashlib.sha256(json.dumps([body,context],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def meaning_key(text):
    text=unicodedata.normalize('NFKC',text).replace('’',"'")
    units=re.findall(r'\b(?:[kMGT]?[bB]|[kMGT]iB|m[sS]|[kMG]?Hz|[kMG]?W)\b|(?<=°)[CF]',text)
    literals=re.findall(r'\b[A-Za-z]+-\d+\b|(?:[A-Za-z0-9_-]+[./_])+(?:[A-Za-z0-9_-]+)',text)
    text=re.sub(r'(?<!\S)[.,!;:]+|[.,!;:]+(?!\S)',' ',text.casefold())
    return ' '.join(text.split())+(' |units:'+','.join(units) if units else '')+(' |literals:'+','.join(literals) if literals else '')

@dataclass(frozen=True)
class TriggerPolicy:
    question_wait_s:float=.15
    information_wait_s:float=.8
    max_batch_wait_s:float=2.
    recent_turns:int=8
    max_focus:int=32
    retrieval_timeout_s:float=10.
    def __post_init__(self):
        if not 0<=self.question_wait_s<=self.information_wait_s<=self.max_batch_wait_s<=5:raise ValueError('Invalid bounded trigger timings')
        if not 0<self.retrieval_timeout_s<=20:raise ValueError('Invalid retrieval timeout')

def decide(meeting,event,previous,participants):
    if meeting['status']!='active' or not meeting['auto_mode']:return 'skip','auto_disabled'
    speaker=event.get('speaker_label');own=meeting.get('self_speaker')
    if not own or not speaker:return 'skip','speaker_unknown'
    if speaker.casefold()==own.casefold():return 'skip','own_turn'
    text=event['text'].strip();key=meaning_key(text)
    if any(name.casefold()!=own.casefold() and re.match('^'+re.escape(name)+r'\s*[,，:]\s*',text,re.I) for name in participants):return 'skip','other_addressee'
    if not event['stable']:return 'wait','speaker_unfinished'
    if re.search(r"\b(?:let me (?:finish|continue|explain)|i(?: am|'m) not finished|hold on|one moment|de toi noi|chua noi xong)\b",key):return 'wait','speaker_unfinished'
    if previous and previous==(speaker,key):return 'skip','cosmetic_revision'
    if previous:return 'urgent','meaningful_correction'
    if re.fullmatch(r'(?:hello|hi|good (?:morning|afternoon|evening)|how are you\??|nice to meet you|thanks|thank you|okay|ok|cam on|xin chao|vâng|dạ)[? ]*',key):return 'skip','small_talk'
    if re.fullmatch(r'(?:yes|no)[? ]*',key):return 'urgent','important_change'
    if '?' in text or re.match(r'^(?:why|which|what|how|when|where|who|could you|can you|tai sao|vi sao)\b',key):return 'urgent','direct_question'
    if re.search(r'\b(?:not|cannot|blocked|blocker|deadline|owner|owns|approved|confirmed|decision|staging|production|timeout|retry|retries)\b|\d',key):return 'urgent','important_change'
    return 'batch','new_information'
