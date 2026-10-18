"""E2E ONLY: real app/Provider adapter, all provider I/O intercepted in process.

Never imported by the production launcher. No network or paid model calls.
"""
import asyncio
import json
import sys
from pathlib import Path
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.main import app


async def controlled_provider(request):
    wire=json.loads(json.loads(request.content)['messages'][1]['content'])
    question=wire.get('question','')
    if 'PHASE2_SLOW' in question:await asyncio.sleep(.8)
    if 'PHASE2_ERROR' in question:return httpx.Response(401,json={'error':'synthetic failure'})
    payload=dict(input_revision=wire['transcript_revision'],intent='question',meaning_vi='Cần làm rõ bước tiếp theo.',findings=[],reply_en='Could you clarify the next step?',reply_vi='Bạn làm rõ bước tiếp theo được không?',clarification_en='',evidence_status='missing',uncertainties=[],supporting_segment_ids=[s['id'] for s in wire['segments']])
    return httpx.Response(200,content='data: '+json.dumps({'choices':[{'delta':{'content':json.dumps(payload)}}]})+'\n\ndata: [DONE]\n\n')


app.state.provider.transport=httpx.MockTransport(controlled_provider)
