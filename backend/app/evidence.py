"""Bounded, deterministic claim checks against original excerpts.

Not a general entailment model. Unknown confirmed tasks and attributed numeric facts
fail closed; ordinary qualitative replies remain usable. English/Vietnamese aliases
are deliberately explicit. No model-generated evidence or cross-turn yes resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata

from .errors import AppError

VALIDATION_POLICY = 'bounded-evidence-v1'


def normalized(text):
    text = unicodedata.normalize('NFKD', text.casefold().replace('đ', 'd').replace('’', "'"))
    return ''.join(c for c in text if not unicodedata.combining(c))


def clauses(text):
    # Decimal points are retained. Contrast clauses never inherit confirmation.
    return [s.strip() for s in re.split(
        r'(?<=[.!?])\s+|[;\n]+|\bbut\b|\bnhung\b|\band\s+(?=(?:[a-z][a-z0-9_-]*)\s+(?:will|shall|se)\b)',
        normalized(text)) if s.strip()]


ALIASES = {
    'rewrite': r'rewrit(?:e|ing|ten)|viet lai',
    'review': r'review(?:s|ed|ing)?|inspect(?:s|ed|ing)?|examin(?:e|ed|ing)|ra soat|xem lai|kiem tra',
    'investigate': r'investigat(?:e|es|ed|ing)|look into|dieu tra',
    'test': r'test(?:s|ed|ing)?|kiem thu|thu nghiem',
    'deploy': r'deploy(?:s|ed|ing|ment)?|releas(?:e|es|ed|ing)|trien khai|phat hanh',
    'fix': r'fix(?:es|ed|ing)?|repair(?:s|ed|ing)?|sua loi|khac phuc',
    'share': r'shar(?:e|es|ed|ing)|send(?:s|ing)?|sent|gui|chia se',
    'implement': r'implement(?:s|ed|ing)?|build(?:s|ing)?|built|xay dung',
    'preserve': r'preserv(?:e|es|ed|ing)|retain(?:s|ed|ing)?|giu nguyen|giu lai|bao toan',
    'escape': r'escap(?:e|es|ed|ing)|vo hieu hoa',
    'choose': r'choos(?:e|es|ing)|chose|chosen|chon',
}
DOMAINS = {
    'csv': r'csv', 'auth': r'auth(?:entication|orization)?|xac thuc|phan quyen',
    'report': r'reports?|bao cao', 'invoice': r'invoices?|hoa don',
    'database': r'databases?|co so du lieu|\bdb\b', 'cache': r'cach(?:e|ing)|bo nho dem',
    'query': r'quer(?:y|ies)|truy van', 'index': r'index(?:es|ing)?|chi muc',
    'backup': r'backups?|sao luu', 'audit': r'audit|kiem toan',
}
ENVIRONMENTS = {'staging': r'staging|tien san xuat', 'production': r'production|\bprod\b', 'development': r'development|\bdev\b'}
PROPERTIES = {
    'timeout': r'timeout|thoi gian cho',
    'ttl': r'(?:cache\s+)?ttl|time to live|thoi gian song',
    'retries': r'retr(?:y|ies)(?:[ _-]?(?:count|limit|at most))?|so lan thu lai|thu lai',
    'upload': r'upload(?:[ _-]?(?:size|limit))?|tai len',
    'http': r'http(?:[ _-]?(?:status|code))?|ma trang thai',
}
UNITS = {
    'ms': ('time', Decimal('0.001')), 'millisecond': ('time', Decimal('0.001')), 'milliseconds': ('time', Decimal('0.001')),
    's': ('time', Decimal(1)), 'sec': ('time', Decimal(1)), 'second': ('time', Decimal(1)), 'seconds': ('time', Decimal(1)), 'giay': ('time', Decimal(1)),
    'minute': ('time', Decimal(60)), 'minutes': ('time', Decimal(60)), 'min': ('time', Decimal(60)), 'phut': ('time', Decimal(60)),
    'byte': ('size', Decimal(1)), 'bytes': ('size', Decimal(1)), 'mib': ('size', Decimal(1048576)), 'mb': ('size', Decimal(1000000)),
}
NUMBER = re.compile(r'(?<![\w.\-])\d+(?:\.\d+)?(?:\s*(?:-|–|to|den)\s*\d+(?:\.\d+)?)?')
ENTITY = re.compile(r'\b(?:api|svc)[-_][a-z0-9_-]+\b|/v\d+/[a-z0-9_/-]+')
UNCERTAIN = re.compile(r'\b(?:maybe|probably|possibly|perhaps|might|could we|unconfirmed|pending|chua|co le|chua chot)\b')
PROPOSAL = re.compile(r'\b(?:propos(?:e|al)|suggest(?:ion)?|could try|could test|de xuat|co the thu)\b')
FACTUAL = re.compile(r'\b(?:current(?:ly)?|actual|already|existing|approved|confirmed|hien tai|da cau hinh|dang la)\b')
CONDITION = re.compile(r'\b(?:if|when|unless|neu|khi|only for|chi khi)\b(.*)')


def labels(text, aliases):
    return frozenset(key for key, pattern in aliases.items() if re.search(r'\b(?:' + pattern + r')\b', text))


def terms(text):
    result = normalized(text)
    replacements = {**ALIASES, **DOMAINS, 'format': r'format(?:s|ted|ting)?|dinh dang',
                    'leading_zero': r'leading zero(?:s)?|so 0 o dau|so khong o dau',
                    'export': r'export(?:s|ed|ing)?|xuat', 'result': r'results?|ket qua',
                    'friday': r'friday|thu sau', 'monday': r'monday|thu hai'}
    for name, pattern in replacements.items():
        result = re.sub(r'\b(?:' + pattern + r')\b', name, result)
    stop = set('the a an of for to in on with and is are was will shall i we you it this that confirmed approved agreed only by at my our please toi se da duoc cua cho va la thi viec can mot nhung chi maybe probably still pending approval unconfirmed not chua xac nhan duyet no'.split())
    return frozenset(w for w in re.findall(r'[a-z_][a-z_0-9-]*', result) if w not in stop)


def status(text):
    if re.search(r'\b(?:reject(?:ed)?|denied|tu choi|bac bo)\b', text):
        return 'rejected'
    if re.search(r"\b(?:not|never|cannot|won't)\s+(?:be\s+)?(?:approved?|confirm(?:ed)?)\b|\b(?:pending|unapproved|chua duoc duyet|chua phe duyet|chua (?:duoc )?xac nhan|no deadline is confirmed)\b", text):
        return 'unapproved'
    if UNCERTAIN.search(text):
        return 'tentative'
    if re.search(r'\b(?:confirmed|approved|agreed|decided|we agree|we will|i will|chot|xac nhan|dong y|phe duyet|duoc duyet)\b', text):
        return 'confirmed'
    return None


@dataclass(frozen=True)
class Quantity:
    attribute: str | None
    entity: str
    environments: frozenset
    dimension: str
    values: tuple
    relation: str
    negative: bool
    condition: frozenset


def quantities(text, infer_http=False):
    result = []
    for clause in clauses(text):
        numbers = list(NUMBER.finditer(clause))
        attributes = sorted((m.start(), m.end(), name) for name, pattern in PROPERTIES.items()
                            for m in re.finditer(r'\b(?:' + pattern + r')\b', clause))
        for number in numbers:
            # ISO dates, clock parts and IDs belong to separate task/date scope checks.
            before, after = clause[:number.start()], clause[number.end():]
            if re.search(r'\d[-:]$', before) or re.match(r'[-:]\d', after):
                continue
            if number[0]=='0' and re.search(r'\bso\s*$',before) and re.match(r'\s*o dau\b',after):
                continue  # Vietnamese "leading zeros" is an identifier-format concept.
            candidates = []
            for start, end, name in attributes:
                between = clause[end:number.start()] if end <= number.start() else clause[number.end():start]
                if NUMBER.search(between) and not re.search(r'\b(?:not|khong)\b', between):
                    continue
                distance = number.start()-end if end <= number.start() else start-number.end()+6
                if 0 <= distance <= 100:
                    candidates.append((distance, start, end, name))
            chosen = min(candidates, default=None)
            attribute = chosen[3] if chosen else None
            unit = re.match(r'\s*([a-z]+)', after)
            dimension, factor = UNITS.get(unit[1] if unit else '', ('count', Decimal(1)))
            values = tuple(Decimal(v)*factor for v in re.findall(r'\d+(?:\.\d+)?', number[0]))
            if infer_http and attribute is None and not unit and len(values)==1 and Decimal(300) <= values[0] <= Decimal(599):
                attribute = 'http'
            if attribute in ('timeout','ttl') and dimension=='count':
                dimension = 'unspecified_time'
            context_start = chosen[1] if chosen else max(0, number.start()-40)
            prefix = clause[context_start:number.start()]
            relation = 'range' if len(values)>1 else '<=' if re.search(r'at most|up to|maximum|no more than|not exceed|khong vuot qua|toi da|<=', prefix) else '>=' if re.search(r'at least|minimum|toi thieu|>=', prefix) else '='
            previous = [item for item in numbers if item.end() <= number.start()]
            negative_start = previous[-1].end() if previous and previous[-1].end() <= context_start else (0 if not previous else context_start)
            negative = relation!='<=' and bool(re.search(r"\b(?:not|never|cannot|can't|won't|khong)\b",clause[negative_start:number.start()]))
            if UNCERTAIN.search(clause) or PROPOSAL.search(clause) or re.search(r'\bor\b',clause):
                relation = 'uncertain:' + relation
            entities = list(ENTITY.finditer(clause[:number.start()]))
            entity = entities[-1][0] if entities else ''
            condition = CONDITION.search(clause)
            result.append(Quantity(attribute, entity, labels(clause, ENVIRONMENTS), dimension,
                                   values, relation, negative, terms(condition[0]) if condition else frozenset()))
    return result


def same_quantity(claim, evidence):
    if claim.attribute is None or claim.attribute != evidence.attribute:
        return False
    if (claim.entity, claim.environments, claim.dimension, claim.condition) != (evidence.entity, evidence.environments, evidence.dimension, evidence.condition):
        return False
    if claim.negative and not evidence.negative:
        return claim.relation==evidence.relation=='=' and claim.values!=evidence.values
    return (claim.values,claim.relation,claim.negative)==(evidence.values,evidence.relation,evidence.negative)


def check_quantities(text, evidence, code, allow_proposals=False):
    for clause in clauses(text):
        if clause.endswith('?'):
            continue
        proposal = PROPOSAL.search(clause) and status(clause) != 'confirmed' and not FACTUAL.search(clause)
        if proposal and allow_proposals:
            continue
        claims = quantities(clause, infer_http=True)
        if not claims:
            continue
        # Literal excerpts are safe to quote, including unnamed/unparsed quantities.
        if any(clause.rstrip('.!?')==source.rstrip('.!?') for item in evidence for source in clauses(item)):
            continue
        available = [quantity for item in evidence for quantity in quantities(item)]
        for claim in claims:
            if not any(same_quantity(claim, item) for item in available):
                raise AppError(code, 'Numeric claim lacks matching attribute/entity/unit/range/condition evidence. Ask for clarification or label a genuine proposal.', 502)


def check_supported_finding(text, evidence):
    """Unrecognized qualitative paraphrases cannot silently acquire 'supported'."""
    negative = re.compile(r"\b(?:not|never|cannot|can't|don't|khong|chua)\b")
    for clause in clauses(text):
        if quantities(clause):
            continue  # Attribute/unit/scope checks have already run.
        supported = False
        for excerpt in evidence:
            for source in clauses(excerpt):
                if clause.rstrip('.!?') == source.rstrip('.!?'):
                    supported = True
                    break
                if source.endswith('?') or UNCERTAIN.search(source) or PROPOSAL.search(source):
                    continue
                if bool(negative.search(clause)) != bool(negative.search(source)):
                    continue
                condition = CONDITION.search(source)
                if condition and not CONDITION.search(clause):
                    continue
                if labels(clause, DOMAINS) != labels(source, DOMAINS):
                    continue
                if terms(clause) and terms(clause) <= terms(source):
                    supported = True
                    break
        if not supported:
            raise AppError('AI_UNVERIFIED', 'Qualitative finding is outside supported lexical/alias evidence checks. Remove it or keep the result explicitly partial, never supported.', 502)


@dataclass(frozen=True)
class Task:
    action: str
    objects: frozenset
    words: frozenset
    environments: frozenset
    negative: bool
    condition: frozenset
    text: str


def tasks(text):
    text = normalized(text)
    matches = sorted((m.start(),m.end(),name) for name,pattern in ALIASES.items()
                     for m in re.finditer(r'\b(?:' + pattern + r')\b', text))
    result = []
    for index,(start,end,action) in enumerate(matches):
        finish = matches[index+1][0] if index+1<len(matches) else len(text)
        chunk = text[start:finish]
        chunk = re.sub(r'\s+and(?:\s+(?:i|we|[a-z][a-z0-9_-]*))?(?:\s+(?:will|shall|se))?\s*$','',chunk)
        tail = text[end:start+len(chunk)]
        # Dates/acceptance/owner words must not turn a different task into a match.
        tail = re.split(r'\b(?:by|before|if|unless|truoc|vao ngay)\b',tail)[0]
        negative = bool(re.search(r"\b(?:not|never|won't|cannot|khong|chua)(?:\s+\w+){0,2}\s*$",text[:start]))
        if result and result[-1].negative:
            negative = True  # A shared negative auxiliary is not permission for the next action.
        condition = CONDITION.search(chunk)
        environments = labels(chunk,ENVIRONMENTS) or (labels(text[:start],ENVIRONMENTS) if index==0 else frozenset())
        result.append(Task(action, labels(tail,DOMAINS), terms(tail), environments,
                           negative, terms(condition[0]) if condition else frozenset(), chunk))
    return result


def same_task(claim, evidence):
    if (claim.action,claim.environments,claim.negative,claim.condition) != (evidence.action,evidence.environments,evidence.negative,evidence.condition):
        return False
    soft = frozenset(('export','file','files','service','component','the','task'))
    claim_detail = claim.words - claim.objects - claim.environments - soft
    evidence_detail = evidence.words - evidence.objects - evidence.environments - soft
    if not claim_detail <= evidence_detail:
        return False
    if claim.objects or evidence.objects:
        return bool(claim.objects) and claim.objects==evidence.objects
    return bool(claim.environments or claim.words & evidence.words)


def accepts(clause, speaker, owner):
    if '?' in clause or UNCERTAIN.search(clause) or CONDITION.search(clause):
        return False
    if re.search(r"\b(?:will|shall|se)\s+not\b|\b(?:will|shall)\s+never\b|\btoi\s+se\s+khong\b",clause):
        return False
    own = (speaker or '').casefold()==owner.casefold()
    first = re.search(r"\bi (?:will|shall|agree to|accept|am responsible for)\b|\bi'll\b|\btoi (?:se|dong y|nhan)\b",clause)
    named = re.search(r'\b'+re.escape(normalized(owner))+r'\s+(?:will|shall|se|owns?|is responsible for)\b',clause)
    return bool((own and first) or (named and (own or status(clause)=='confirmed')))


def accepted_tasks(segments, owner):
    return [(task, task.text) for segment in segments for clause in clauses(segment['text'])
            if accepts(clause,segment.get('speaker'),owner) for task in tasks(clause)]


def check_commitment(text, segments, owner, code='AI_COMMITMENT'):
    if not owner:
        return  # Unknown-role policy remains in llm.py.
    evidence = accepted_tasks(segments,owner)
    for clause in clauses(text):
        promise = re.search(r"\bi (?:will|shall|can)\s+(?!not\b|never\b)|\bi'll\s+|\btoi (?:se|co the)\s+(?!khong\b)",clause)
        if not promise:
            continue
        claims = tasks(clause[promise.start():])
        if not claims or any(not any(same_task(task, candidate) for candidate,_ in evidence) for task in claims):
            raise AppError(code, 'First-person commitment must match the named user acceptance of this action, task and environment.', 502)
        due = due_text(clause)
        if due and not any(due_text(source)==due and any(same_task(task,candidate) for task in claims) for candidate,source in evidence):
            raise AppError(code, 'Commitment deadline does not belong to the accepted task.', 502)


def due_text(text):
    match = re.search(r'\b(?:by|before|truoc|han)\s+(.+?)[.!?]*$',normalized(text))
    return match[1].rstrip('.!? ') if match else None


def matching_clauses(task, segments, owner=None, confirmed=False):
    result=[]
    for segment in segments:
        for clause in clauses(segment['text']):
            if owner and not accepts(clause,segment.get('speaker'),owner):
                continue
            if confirmed and status(clause)!='confirmed' and not (owner and accepts(clause,segment.get('speaker'),owner)):
                continue
            result.extend(candidate.text for candidate in tasks(clause) if same_task(task,candidate))
    return result


def check_approval(text, segments, code, force_confirmed=False):
    """Match approval state to the same clause subject/environment, not any 'yes'."""
    evidence=[clause for segment in segments for clause in clauses(segment['text'])]
    confirmed_proposition = False
    for clause in clauses(text):
        if clause.endswith('?'):
            continue
        claim_status=status(clause)
        if claim_status is None and not force_confirmed:
            continue
        claim_status=claim_status or 'confirmed'
        # Tentative descriptions do not assert confirmation.
        if claim_status=='tentative' and not force_confirmed:
            continue
        environments=labels(clause,ENVIRONMENTS)
        claim_tasks=tasks(clause)
        if force_confirmed and claim_status=='tentative':
            raise AppError(code,'Tentative speech cannot support a confirmed decision.',502)
        def supports(source):
            source_status=status(source)
            if not (source_status==claim_status or claim_status=='unapproved' and source_status=='tentative') or labels(source,ENVIRONMENTS)!=environments:
                return False
            source_condition=CONDITION.search(source)
            claim_condition=CONDITION.search(clause)
            if (terms(source_condition[0]) if source_condition else frozenset()) != (terms(claim_condition[0]) if claim_condition else frozenset()):
                return False
            if clause.rstrip('.!?')==source.rstrip('.!?'):
                return True
            source_tasks=tasks(source)
            if claim_tasks:
                return all(any(same_task(task,candidate) for candidate in source_tasks) for task in claim_tasks)
            # Environment approval without an action still needs the same subject.
            claim_domains=labels(clause,DOMAINS)
            if claim_domains!=labels(source,DOMAINS):
                return False
            claim_properties=labels(clause,PROPERTIES)
            if claim_properties!=labels(source,PROPERTIES):
                return False
            if set(ENTITY.findall(clause)) != set(ENTITY.findall(source)):
                return False
            if claim_properties:
                return True  # Same attributed approval; numeric value checks run separately.
            if environments:
                return True
            return bool(terms(clause)&terms(source)) and terms(clause)<=terms(source)
        matches = [source for source in evidence if supports(source)]
        if not matches:
            raise AppError(code,'Confirmation/status does not match the cited proposition, action and environment.',502)
        if claim_status=='confirmed' or any(re.search(r'\b(?:confirmed|agreed|decided|chot|xac nhan|dong y)\b',source) for source in matches):
            confirmed_proposition = True
    if force_confirmed and text.strip() and not confirmed_proposition:
        raise AppError(code,'A pending or negative status alone is not an explicitly confirmed decision.',502)


def check_report_task(item, segments, require_task=False):
    scoped = [s for s in segments if s['id'] in item.evidence_segment_ids]
    verified_task = False
    for text in filter(None, (item.text, item.text_en)):
        for clause in clauses(text):
            if status(clause) in ('unapproved', 'rejected') or clause.endswith('?'):
                continue  # Negative context is checked separately, not assigned as work.
            claims = tasks(clause)
            if not (item.owner or item.raw_due_text or item.confirmation == 'confirmed'):
                continue
            if not claims:
                if item.owner or item.raw_due_text or require_task:
                    raise AppError('REPORT_TASK', 'Cannot bind owner/deadline without an identifiable task.', 502)
                continue
            for task in claims:
                matches = matching_clauses(task, scoped, owner=item.owner,
                                           confirmed=item.confirmation == 'confirmed')
                if not matches:
                    raise AppError('REPORT_TASK', 'Owner/confirmation does not belong to this task.', 502)
                verified_task = True
                if item.raw_due_text and not any(normalized(item.raw_due_text) in source for source in matches):
                    raise AppError('REPORT_DUE', 'Deadline belongs to another task or unconfirmed clause.', 502)
    if require_task and item.confirmation=='confirmed' and not verified_task:
        raise AppError('REPORT_TASK', 'Confirmed work needs a supported task, not only a question or status.', 502)


def check_named_assignments(text, segments, code):
    for clause in clauses(text):
        if clause.endswith('?'):
            continue
        for match in re.finditer(r'\b([a-z][a-z0-9_-]*)\s+(?:will|shall|se)\s+(?!not\b|never\b|khong\b)',clause):
            owner=match[1]
            if owner in ('we','i','it','they','this','there'):
                continue
            evidence=accepted_tasks(segments,owner)
            claims=tasks(clause[match.end():])
            if not claims or any(not any(same_task(task,candidate) for candidate,_ in evidence) for task in claims):
                raise AppError(code,'Named assignment is not supported for this exact task.',502)
            due=due_text(clause)
            if due and not any(due_text(source)==due and any(same_task(task,candidate) for task in claims) for candidate,source in evidence):
                raise AppError(code,'Named assignment deadline belongs to a different task.',502)
