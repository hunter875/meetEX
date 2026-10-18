import json
from pathlib import Path
from app.models import ReportPayload, SuggestionPayload
from app.llm import validate_report, validate_suggestion

CASES = json.loads((Path(__file__).resolve().parents[2]/'fixtures/phase1-semantic-cases.json').read_text('utf-8'))

def exercise(case):
    speech = case.get('speech', [dict(id='s1',speaker='Alex',text='Please restate the documented setting.')])
    if case['kind']=='suggestion':
        snapshot = dict(transcript_revision=1,self_speaker='Minh',segments=speech,memory=[],
                        sources=[dict(id='c1',content=case['source'])] if case.get('source') else [])
        fields=dict(input_revision=1,intent='update',meaning_vi='Đối chiếu thông tin.',findings=[],
                    reply_en='Could you clarify?',reply_vi='Bạn làm rõ giúp nhé?',clarification_en='',
                    evidence_status='missing',uncertainties=[],supporting_segment_ids=[speech[-1]['id']])
        if case['field']=='finding':
            fields['findings']=[dict(text_vi=case['claim'],source_ids=['c1'])]
            fields['evidence_status']='supported'
        else:
            fields[case['field']]=case['claim']
        return validate_suggestion(SuggestionPayload(**fields),snapshot)
    fields={}
    if case['section']=='summary':
        fields[case['field']]=case['claim']
        fields['summary_segment_ids']=[s['id'] for s in speech]
    else:
        item=dict(id='item',text='',text_en='',origin='transcript',confirmation='confirmed',
                  evidence_segment_ids=[s['id'] for s in speech])
        item[case['field']]=case['claim']
        item.update({key:case[key] for key in ('owner','raw_due_text','normalized_due') if key in case})
        fields[case['section']]=[item]
    return validate_report(ReportPayload(**fields),speech,check_coverage=False)
