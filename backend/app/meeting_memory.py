"""Evidence ledger with a deliberately bounded English extraction grammar.

No generated summary is evidence. This module never calls a model or reads a
different meeting. All state changes retain exact caption revision snapshots.
"""
import hashlib
import json
import re
from datetime import datetime,timedelta,date
from zoneinfo import ZoneInfo
from .errors import AppError

POLICY='meeting-ledger-v1'
STATES={
    'requirement':{'requested','withdrawn','invalidated'},
    'proposal':{'proposed','accepted','rejected','invalidated'},
    'decision':{'unconfirmed','confirmed','disputed','superseded','cancelled','invalidated'},
    'action_item':{'requested','accepted','completed','disputed','superseded','cancelled','invalidated'},
    'open_question':{'open','resolved','invalidated'},
    'spoken_fact':{'stated','invalidated'},
}
HISTORICAL={'superseded','invalidated','withdrawn','rejected'}
def current(item):
    return item['status'] not in HISTORICAL and not any(r['type'] in ('accepted_by','superseded_by','cancelled_by','completed_by') for r in item['relations'])
def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def rows(db,meeting):return [json.loads(r[0]) for r in db.execute('SELECT payload FROM memory_items WHERE meeting_id=? ORDER BY rowid',(meeting,))]

def due_value(raw,segment,timezone,confirmed):
    if not raw:return None,'none',None
    anchor=segment.get('observed_to') or segment.get('observed_at')
    if not confirmed:return None,'tentative',anchor
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):
        try:return date.fromisoformat(raw).isoformat(),'iso-date',anchor
        except ValueError:return None,'invalid-date',anchor
    if raw.casefold()=='tomorrow' and anchor:
        try:
            at=datetime.fromisoformat(anchor.replace('Z','+00:00'))
            if at.tzinfo:return (at.astimezone(ZoneInfo(timezone)).date()+timedelta(days=1)).isoformat(),'evidence-local-date-plus-one',anchor
        except (ValueError,KeyError):pass
    return None,'ambiguous',anchor

def extract(meeting,segment,order):
    if not segment['stable']:return []
    items=[]
    # Never split a decimal. Semicolon and sentence boundaries retain full clauses.
    clauses=re.split(r';\s*|(?<=[.!?])\s+(?=[A-Z“"\'])',segment['text'])
    for index,text in enumerate(clauses):
        text=text.strip()
        if not text:continue
        low=text.casefold();entities=re.findall(r'\b[A-Za-z]+-\d+\b',text);entity=entities[0] if entities else None
        ambiguous=len(set(entities))>1
        quoted=bool(re.search(r'\b(?:said|says|told|reports?|reported|quoted|according to)\b|["“”]',low))
        injection=bool(re.search(r'ignore (?:previous|all)|system (?:prompt|policy)|api.?key|instructions',low))
        tentative=bool(re.search(r'\b(?:if|unless|once|assuming|provided|maybe|might|would|could|propose|proposal|suggest|consider)\b|\bi can\b|subject to|upon approval|after approval|when approved',low))
        negative=bool(re.search(r"\b(?:not|never|pending|unapproved|cannot)\b|n't\b",low))
        verbs=re.findall(r'\b(?:deploy|review|test|approve|approved|check|implement|fix|release|investigate|migrate)\b',low)
        action=next((v for v in ('deploy','review','test','check','implement','fix','release','investigate','migrate') if v in verbs),'approve' if verbs else None)
        environments=re.findall(r'\b(?:staging|production|development)\b',low);environment=environments[0] if len(set(environments))==1 else None
        owner=None;candidate=None;replaces_owner=None
        cancel=bool(re.search(r'\b(?:cancel|cancelled|canceled|withdraw)\b',low))
        replace=bool(re.search(r'\b(?:correction|instead|replace|change|take over)\b',low))
        explicit=bool(re.search(r'\b(?:confirmed|approved|agreed|decided)\b',low)) and not negative
        if quoted or injection:kind,status='spoken_fact','stated'
        elif tentative:kind,status='proposal','proposed'
        elif cancel and entity and action:kind,status='decision','cancelled'
        elif re.search(r'\bi (?:will|accept|commit|completed|finished)\b',low) and entity and action:
            kind='action_item';status='completed' if re.search(r'\bi (?:completed|finished)\b',low) else 'accepted'
            owner=segment.get('speaker') if not negative and not ambiguous else None
            if not owner:status='requested'
            if negative and segment.get('speaker') and not ambiguous:status='cancelled';owner=segment['speaker']
            old=re.search(r'\btake over\b.*\bfrom\s+([\w-]+)',text,re.I)
            if old:replaces_owner=old[1]
        elif re.search(r'\b(?:can you|please|assigned|will)\b',low) and entity and action:
            kind,status='action_item','requested'
            named=re.match(r'([\w-]+)\s+will\b',text,re.I);candidate=named[1] if named else None
        elif (entity or environment or (negative and re.search(r'\bapprov',low))) and (explicit or re.search(r'\b(?:approval|approved|confirmed|decision)\b',low)):
            kind,status='decision','confirmed' if explicit and action and not ambiguous and len(set(environments))<=1 else 'unconfirmed'
        elif re.search(r'\b(?:need|must|required|requirement)\b',low):kind,status='requirement','requested'
        elif text.endswith('?') and entity:kind,status='open_question','open'
        elif entity or re.fullmatch(r'(?:yes|no)[.!?]*',low):kind,status='spoken_fact','stated'
        else:continue
        raw=None
        match=re.search(r'\b(?:by|due(?: on)?|deadline(?: is)?|on)\s+(\d{4}-\d{2}-\d{2}|tomorrow|(?:next\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|early next week)\b',text,re.I)
        if match and kind in ('action_item','decision','proposal') and action:raw=match[1]
        normalized,rule,anchor=due_value(raw,segment,meeting['timezone'],status in ('accepted','completed','confirmed'))
        id=hashlib.sha256(f'{meeting["id"]}:{segment["id"]}:{index}'.encode()).hexdigest()[:24]
        items.append(dict(id=id,meeting_id=meeting['id'],project_id=meeting['project_id'],kind=kind,text=text,entity=entity,entities=entities,ambiguous=ambiguous,action=action,environment=environment,speaker=segment.get('speaker'),owner=owner,candidate_owner=candidate,status=status,event_status=status,raw_due_text=raw,normalized_due=normalized,due_rule=rule,due_anchor=anchor,origin='transcript',evidence=[dict(segment_id=segment['id'],revision=segment['revision'])],order=[order,index],negative=negative,explicit_replace=replace,replaces_owner=replaces_owner,relations=[],policy=POLICY))
    return items

def reconcile(items):
    # User annotations overlay the speech ledger; they never erase the original
    # transcript transition or become its evidence. Reconcile immutable speech
    # bases first, then restore the user's separately labelled view.
    overlays={i['id']:i for i in items if i['origin']=='user_edit' and i.get('transcript_basis') and (i['status']!='invalidated' or i.get('invalidation_reason')=='transcript_transition_changed')}
    if overlays:
        projected=[json.loads(encoded(overlays[i['id']]['transcript_basis'] if i['id'] in overlays else i)) for i in items]
        result=reconcile(projected);merged=[]
        for item in result:
            if item['id'] in overlays:
                overlay=overlays[item['id']];basis=overlay['transcript_basis']
                overlay['transcript_state']=item['status'];overlay['transcript_relations']=item['relations']
                if item['status']!=basis['status'] and overlay['status']!=item['status'] and item['status'] in ('superseded','cancelled','disputed'):
                    overlay['status']='invalidated';overlay['invalidation_reason']='transcript_transition_changed'
                merged.append(overlay)
            else:merged.append(item)
        return merged
    groups={}
    edited={i['id'] for i in items if i['origin']=='user_edit' and i['status']!='invalidated'}
    for item in sorted(items,key=lambda x:x['order']):
        if item['status']=='invalidated' or item['origin']!='transcript':continue
        preserved=[r for r in item['relations'] if r['item_id'] in edited and r['type'] in ('accepted_by','superseded_by','cancelled_by','completed_by')]
        # Editing a successor is not evidence that an earlier superseded decision
        # became current again. Its original transition evidence remains archived.
        if preserved:item['relations']=preserved;continue
        item['status']=item['event_status'];item['relations']=[]
        if not item['entity'] or not item['action'] or item.get('ambiguous'):
            # An unbound denial is a clarification signal, not permission to pick
            # a task. Mark adjacent possible decisions disputed, never cancelled.
            if item['kind']=='decision' and item['negative'] and not item['entity']:
                for values in groups.values():
                    for old in values:
                        if old['kind']=='decision' and old['status']=='confirmed' and 0<=item['order'][0]-old['order'][0]<=1:
                            old['status']='disputed';old['relations'].append(dict(type='uncertain_conflict',item_id=item['id']))
            continue
        key=(item['entity'],item['action'],item['environment']);prior=groups.setdefault(key,[])
        relevant=[p for p in prior if p['status'] not in HISTORICAL and p['kind'] in ('decision','action_item','proposal')]
        if item['kind']=='decision' and item['event_status']=='confirmed':
            for old in relevant:
                if old['kind']=='proposal' and old['status']=='proposed':old['status']='accepted';old['relations'].append(dict(type='accepted_by',item_id=item['id']))
                elif old['kind']=='decision' and old['status'] in ('confirmed','disputed'):
                    if old['speaker']==item['speaker'] and item['explicit_replace']:
                        old['status']='superseded';old['relations'].append(dict(type='superseded_by',item_id=item['id']))
                    elif old['text']!=item['text']:
                        old['status']=item['status']='disputed';old['relations'].append(dict(type='disputed_by',item_id=item['id']));item['relations'].append(dict(type='disputes',item_id=old['id']))
        elif item['kind'] in ('decision','action_item') and item['event_status']=='cancelled':
            matches=[p for p in relevant if p['kind'] in ('decision','action_item') and p['speaker']==item['speaker']]
            if not matches:item['status']='requested' if item['kind']=='action_item' else 'unconfirmed'
            for old in matches:
                old['status']='cancelled';old['relations'].append(dict(type='cancelled_by',item_id=item['id']));item['relations'].append(dict(type='cancels',item_id=old['id']))
        elif item['kind']=='decision' and item['negative']:
            for old in relevant:
                if old['kind']=='decision' and old['status']=='confirmed':
                    old['status']=item['status']='disputed';old['relations'].append(dict(type='disputed_by',item_id=item['id']));item['relations'].append(dict(type='disputes',item_id=old['id']))
        elif item['kind']=='action_item' and item['event_status'] in ('accepted','completed'):
            for old in relevant:
                if old['kind']=='action_item' and old['status']=='requested' and item['status']=='accepted' and (not old['candidate_owner'] or old['candidate_owner']==item['owner']):
                    old['relations'].append(dict(type='accepted_by',item_id=item['id']));continue
                if old['kind']!='action_item' or old['status'] not in ('accepted','completed','disputed'):continue
                if item['status']=='completed' and item['owner']==old['owner']:
                    old['status']='completed';old['relations'].append(dict(type='completed_by',item_id=item['id']))
                elif item['replaces_owner'] and old['owner'] and item['replaces_owner'].casefold()==old['owner'].casefold():
                    old['status']='superseded';old['relations'].append(dict(type='superseded_by',item_id=item['id']))
                elif old['owner']!=item['owner']:
                    old['status']=item['status']='disputed';old['relations'].append(dict(type='disputed_by',item_id=item['id']))
                elif item['explicit_replace']:
                    old['status']='superseded';old['relations'].append(dict(type='superseded_by',item_id=item['id']))
        prior.append(item)
    return items

def save_versions(db,meeting,items,old):
    changed=False
    for item in items:
        previous=old.get(item['id']);body={k:v for k,v in item.items() if k!='version'}
        if previous and encoded(body)==encoded({k:v for k,v in previous.items() if k!='version'}):continue
        version=(previous or {}).get('version',0)+1;item['version']=version
        db.execute('INSERT INTO memory_items VALUES(?,?,?,?,?) ON CONFLICT(meeting_id,id) DO UPDATE SET version=excluded.version,payload=excluded.payload',(meeting['id'],item['id'],meeting['project_id'],version,encoded(item)))
        db.execute('INSERT INTO memory_versions VALUES(?,?,?,?)',(meeting['id'],item['id'],version,encoded(item)));changed=True
    if changed:meeting['memory_revision']=meeting.get('memory_revision',0)+1
    return changed

def update(db,meeting,segment):
    """Inside caption transaction; stable incremental extraction, correction invalidates immediately."""
    old={item['id']:item for item in rows(db,meeting['id'])}
    related=[item for item in old.values() if any(e['segment_id']==segment['id'] for e in item['evidence'])]
    order=db.execute('SELECT rowid FROM caption_segments WHERE meeting_id=? AND id=?',(meeting['id'],segment['id'])).fetchone()[0]
    parsed=extract(meeting,segment,order)
    if not related and not parsed:return False
    values=json.loads(encoded(list(old.values())))
    lookup={item['id']:item for item in values}
    for item in related:
        current=lookup[item['id']]
        if any(e['segment_id']==segment['id'] and e['revision']!=segment['revision'] for e in item['evidence']):
            current['status']='invalidated';current['invalidation_reason']='caption_revision_changed'
    for item in parsed:
        previous=lookup.get(item['id'])
        while previous and previous['origin']=='user_edit':
            if previous['status']!='invalidated':item=None;break
            # Preserve the user's annotation and derive the corrected speech in a
            # separate stable lineage; an edit must not suppress future corrections.
            item['derived_after_user_edit']=previous['id'];item['id']+='-speech';previous=lookup.get(item['id'])
        if item is None:continue
        if previous:values[values.index(previous)]=item
        else:values.append(item)
    return save_versions(db,meeting,reconcile(values),old)

def edit(db,meeting,item_id,patch,expected_version):
    old={i['id']:i for i in rows(db,meeting['id'])}
    if item_id not in old:raise AppError('NOT_FOUND','Memory item not in this meeting',404)
    item=json.loads(encoded(old[item_id]))
    if expected_version!=item['version']:raise AppError('VERSION_CONFLICT','Memory changed; keep your draft and reload',409,current_version=item['version'])
    if patch.get('status',item['status']) not in STATES[item['kind']]:raise AppError('MEMORY_STATE','State is not valid for this kind',422)
    if item['origin']=='transcript':item['transcript_basis']=json.loads(encoded(item))
    changed_fields=sorted(k for k,v in patch.items() if item.get(k)!=v)
    if 'status' in changed_fields:item['relations']=[]
    item.update(patch);item['origin']='user_edit';item['edit_provenance']=dict(actor='local_user',previous_version=expected_version,changed_fields=changed_fields)
    # A manual due edit is not retroactively participant speech or an anchored date.
    if 'raw_due_text' in patch:item.update(normalized_due=None,due_rule='user-raw-unverified',due_anchor=None)
    save_versions(db,meeting,[item],old);return item

def create(db,meeting,body,id):
    if body['status'] not in STATES[body['kind']]:raise AppError('MEMORY_STATE','Invalid state for this item type',422)
    item=dict(id=id,meeting_id=meeting['id'],project_id=meeting['project_id'],action=None,environment=None,speaker=None,candidate_owner=None,normalized_due=None,due_anchor=None,due_rule='user-raw-unverified',origin='user_edit',evidence=[],relations=[],order=[10**9,0],policy=POLICY,entities=[body['entity']] if body.get('entity') else [],**body)
    item['edit_provenance']=dict(actor='local_user',previous_version=None,changed_fields=sorted(body))
    save_versions(db,meeting,[item],{});return item

def select(items,query,max_chars=2000):
    terms=set(re.findall(r'\w+',query.casefold()));entities=set(re.findall(r'\b[A-Za-z]+-\d+\b',query))
    ranked=[]
    for item in items:
        if not current(item):continue
        score=5*bool(entities.intersection(item.get('entities',[])))+len(terms.intersection(re.findall(r'\w+',item['text'].casefold())))
        if item['kind']=='decision' and item['status']=='unconfirmed' and not item['entity']:score=max(score,1)
        if score:ranked.append((score,item))
    selected=[];used=0
    for _,item in sorted(ranked,key=lambda pair:(pair[0],pair[1]['order']),reverse=True):
        compact={k:item.get(k) for k in ('id','kind','text','entity','action','environment','status','owner','raw_due_text','normalized_due','origin','evidence','version','relations')}
        size=len(encoded(compact))
        if used+size<=max_chars and len(selected)<8:selected.append(compact);used+=size
    return selected,len(ranked)-len(selected)

def check_live_claims(payload,snapshot):
    from .evidence import normalized,ALIASES,status
    for item in snapshot.get('structured_memory',[]):
        for text in (payload.reply_en,payload.reply_vi):
            for clause in re.split(r'(?<=[.!?])\s+',text):
                if clause.endswith('?'):continue
                normalized_clause=normalized(clause)
                if item.get('entity') and item['entity'].casefold() not in clause.casefold():
                    if re.search(r'\b[A-Za-z]+-\d+\b',clause):continue
                    action=item.get('action')
                    if not action or not re.search(r'\b(?:'+ALIASES.get(action,re.escape(action))+r')\b',normalized_clause):continue
                if item.get('environment') and any(e in clause.casefold() for e in ('staging','production','development')) and item['environment'] not in clause.casefold():continue
                positive=status(normalized_clause)=='confirmed' or re.search(r'\b(?:will|accepted|se)\b',normalized_clause)
                negative=re.search(r"\b(?:not|never|pending|cancelled|disputed|unconfirmed|chua|khong|huy)\b|n't",normalized_clause)
                if item['status'] in ('cancelled','disputed','unconfirmed','requested','proposed') and positive and not negative:
                    raise AppError('AI_MEMORY_STATE','Claim contradicts unresolved/cancelled meeting memory; clarify using current evidence',502)
                if item['origin']=='user_edit' and not re.search(r'user (?:edit|note)|manual note|ghi chú|bạn (?:ghi|sửa)',clause,re.I):
                    raise AppError('AI_MEMORY_ORIGIN','User-edited memory must be attributed as a note, never participant speech',502)
