"""Explainable local routing. Targets are product goals, never confidence or an SLA.

Rules conservatively gate commitments; they do not verify facts or infer identity,
speech completion, or safety from source presence. No provider call is made here.
"""
from __future__ import annotations

import re
import time
import unicodedata
from .models import RoutingDecision

TARGETS = {'fast': (1, 2), 'explain': (2, 4), 'deep': (5, 10),
           'clarify': (1, 3), 'listen': (0, 0)}
INSTRUCTIONS = {
    'fast': 'Answer the latest question briefly using available evidence. One short spoken sentence is preferred. Do not infer unknown facts.',
    'explain': 'Explain the main reason and one limitation in simple English within sentence_limit. Preserve evidence and uncertainty.',
    'deep': 'Compare two or three genuinely different feasible approaches to the latest problem. State the main benefit, tradeoff and conditions for each, then a conditional recommendation. Keep reply_en speakable within sentence_limit; put Vietnamese reasoning in meaning_vi. Options are proposals, not confirmed decisions or project findings. Do not invent estimates, criterion weights, scores or success probabilities. If essential constraints are unknown, ask about them instead of pretending to rank options.',
    'clarify': 'Ask a specific neutral question for the missing fact, approval, owner, deadline or conflicting evidence. Do not confirm readiness, promise work or choose a consequential action from assumptions. Source presence is not approval.',
    'listen': 'Continue listening; no provider request should be made for this automatic turn.',
}

def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold().replace('đ', 'd'))
                   if not unicodedata.combining(c))

def classify(snapshot, response_mode='auto'):
    began = time.perf_counter()
    segments = snapshot.get('segments', [])
    latest = segments[-1] if segments else {}
    context_segments = []
    question = snapshot.get('question', '').strip()
    text = fold(question or latest.get('text', ''))
    sources = snapshot.get('sources', [])
    state = 'missing' if not sources else 'stale' if any(s.get('stale') for s in sources) else 'available'
    # Respect explicit conflict metadata/wording; source existence alone is not entailment.
    if any(s.get('conflicting') for s in sources) or re.search(
        r'\b(?:conflicting|contradict(?:s|ory|ion)?|disagree|not agreed|different results|mau thuan|chua thong nhat)\b', text):
        state = 'conflicting'
    reasons, risks = [], []
    auto = snapshot.get('action') == 'auto'
    deep = bool(re.search(r'\b(?:compar(?:e|ison)|trade[ -]?offs?|alternatives?|options?|approaches|pros and cons|'
                          r'which (?:approach|option|architecture)|which\b.{0,60}\b(?:better|best)|recommend(?:ation)?|'
                          r'strateg(?:y|ies)|what would you (?:do|suggest)|how (?:should|can|do) we (?:solve|handle|address|fix)|'
                          r'should we|so sanh|phuong an|phuong huong|de xuat|chien luoc|giai phap|'
                          r'huong (?:xu ly|giai quyet)|nen (?:chon|dung|lam|sua|xay)|uu nhuoc|danh doi)\b', text))
    explain = bool(re.search(r'\b(?:why|explain|how does|how do|tai sao|vi sao|giai thich|hoat dong the nao)\b', text))
    deployment = bool(re.search(r'\b(?:deploy|deployment|release|rollout|go[ -]live|production|trien khai|phat hanh)\b', text))
    data_loss = bool(re.search(r'\b(?:delete|drop|truncate|wipe|xoa)\b.{0,45}\b(?:database|table|data|du lieu|bang)\b', text))
    elliptical = bool(re.fullmatch(r'(?:can|could|should|may) we (?:do (?:that|it)|proceed|go ahead)[?!. ]*|'
                                   r'(?:is it|are we) ready[?!. ]*|(?:duoc chua|lam duoc chu|tien hanh nhe)[?!. ]*', text))
    if elliptical:
        prior = segments[-3:] if question else segments[-4:-1]
        context_segments = prior
        context_text = fold(' '.join(s.get('text','') for s in prior))
        deployment = deployment or bool(re.search(r'\b(?:deploy|deployment|production|release|trien khai)\b', context_text))
        data_loss = data_loss or bool(re.search(r'\b(?:delete|drop|truncate|wipe|xoa)\b.{0,45}\b(?:database|table|data|du lieu|bang)\b', context_text))
    security = bool(re.search(r'\b(?:security|authentication|authorization|credentials|bao mat|xac thuc|phan quyen)\b', text))
    commitment = bool(re.search(r'\b(?:can (?:we|you|i)|will (?:we|you|i)|are we|is it|ready|approved|confirm|'
                                r'promise|guarantee|deadline|by (?:friday|monday|tomorrow|\d)|'
                                r'co (?:the|duoc)|duoc chua|san sang|phe duyet|xac nhan|cam ket|han chot)\b', text))
    if deployment: risks.append('deployment')
    if data_loss: risks.append('data_loss')
    if security: risks.append('security')
    if commitment: risks.append('commitment')
    if re.search(r'\b(?:budget|cost|pricing|ngan sach|chi phi|bao gia)\b', text): risks.append('cost')
    # Consequential permission/commitment is a gate even when sources were retrieved.
    delivery = bool(re.search(r'\b(?:can|will|could|would) you\s+(?:please\s+)?(?:deliver|finish|ship|complete|send|fix|take|own)\b|'
                              r'\bban (?:co the|se)\b.{0,60}\b(?:hoan thanh|gui|nhan viec|phu trach)\b', text))
    operational_request = bool(re.search(
        r'\b(?:can|could|may|will|should) (?:we|you|i)\s+(?:please\s+)?(?:not\s+)?(?:deploy|release|roll out|go live)\b|'
        r'\b(?:ready|approved|confirm|promise|guarantee|safe to|ok(?:ay)? to|san sang|phe duyet|xac nhan|duoc chua|cam ket)\b|'
        r'\bco (?:the|duoc)\b.{0,30}\b(?:trien khai|phat hanh)\b', text))
    if delivery and 'commitment' not in risks: risks.append('commitment')
    if elliptical: risks.append('ambiguous_reference')
    verification = elliptical or data_loss or delivery or (deployment and operational_request) or bool(re.search(
        r'\b(?:promise|guarantee|cam ket|deadline|han chot|who (?:will|owns)|ai (?:nhan|phu trach))\b', text))
    continuation = bool(re.search(r'\b(?:let me (?:finish|continue|explain)|i(?: am|\x27m) not finished|'
                                  r'hold on|one moment|de toi (?:noi|giai thich)|chua noi xong|khoan da)\b', text))
    acknowledgement = bool(re.fullmatch(r'(?:thanks|thank you|okay|ok|yes|no|cam on|vang|da)[.! ]*', text))
    self_speaker = snapshot.get('self_speaker')
    own_turn = bool(self_speaker and (latest.get('speaker') or '').casefold() == self_speaker.casefold())
    other_addressee = False
    if self_speaker and not question:
        participants = {s.get('speaker') for s in segments if s.get('speaker')}
        other_addressee = any(p.casefold() != self_speaker.casefold() and
                              re.match(r'^' + re.escape(fold(p)) + r'\s*[,，:]\s*', text)
                              for p in participants)
    if not text or (auto and not question and (continuation or acknowledgement or own_turn or other_addressee or not latest.get('stable',True))):
        route = 'listen'
        reasons.append('Tiếp tục nghe: chưa có yêu cầu cần bạn trả lời hoặc đang nhường lượt nói.')
    elif verification:
        route = 'clarify'
        reasons.append('Cần xác minh quyền thực hiện/cam kết; có nguồn chưa đồng nghĩa đã được duyệt.')
    elif state == 'conflicting':
        route = 'clarify'
        verification = True
        reasons.append('Có dấu hiệu thông tin mâu thuẫn; cần làm rõ trước khi kết luận.')
    elif snapshot.get('action') == 'clarify':
        route = 'clarify'
        reasons.append('Bạn yêu cầu tạo câu hỏi làm rõ.')
    elif snapshot.get('action') == 'explain':
        route = 'explain'
        reasons.append('Bạn yêu cầu giải thích từ snapshot đã chọn.')
    elif deep:
        route = 'deep'
        reasons.append('Câu hỏi yêu cầu cân nhắc hướng xử lý hoặc so sánh phương án.')
    elif explain:
        route = 'explain'
        reasons.append('Cần giải thích nguyên nhân/cách hoạt động và giới hạn.')
    elif state in ('missing', 'stale') and re.search(
        r'\b(?:what (?:is|are)|how (?:many|much)|status|limit|timeout|bao nhieu|trang thai|gioi han)\b', text):
        route = 'clarify'
        verification = True
        reasons.append('Chưa có nguồn hiện hành để đối chiếu câu hỏi về dữ kiện dự án.')
    else:
        route = 'fast'
        reasons.append('Chưa thấy yêu cầu phân tích nhiều hướng; ưu tiên câu trả lời ngắn có căn cứ.')
    automatic_route = route
    # Explicit UI mode is per request, not a persistent override of Auto or a safety bypass.
    source = 'automatic'
    if response_mode != 'auto':
        source = 'manual'
        if verification:
            route = 'clarify'
            reasons.append('Giữ bước xác minh dù bạn chọn chế độ khác.')
        else:
            route = response_mode
            reasons.append('Chế độ do bạn chọn cho yêu cầu này.')
    if state == 'missing': reasons.append('Chưa có nguồn dự án; phương án nếu có chỉ là đề xuất cần kiểm chứng.')
    elif state == 'stale': reasons.append('Nguồn được truy xuất có bản cũ; cần đối chiếu lại.')
    elif state == 'available': reasons.append('Có đoạn nguồn để đối chiếu; chưa chứng minh mọi khẳng định đúng.')
    minimum, maximum = TARGETS[route]
    return RoutingDecision(route=route, automatic_route=automatic_route, source=source,
                           reasons=reasons, risks=risks, evidence_state=state,
                           requires_verification=bool(verification),
                           trigger_segment_ids=list(dict.fromkeys(s['id'] for s in context_segments+[latest] if s.get('id'))),
                           target_min_s=minimum, target_max_s=maximum,
                           classifier_ms=(time.perf_counter()-began)*1000).model_dump()

def prompt_routing(routing):
    """Only backend-derived policy enters the system prompt, never user text/reasons."""
    return INSTRUCTIONS.get((routing or {}).get('route'), '')
