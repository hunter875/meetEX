"""Collect authorized local live evidence into ignored .local; never print credentials.

No model calls, meeting messages or automatic browser operations. RAM meetings cannot
be exported by this helper. Review/anonymise evidence before sharing it.
"""
import argparse
import json
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--meeting-id',required=True)
    parser.add_argument('--token-file',type=Path,default=ROOT/'.local/pairing-token')
    parser.add_argument('--observations',type=Path,help='Optional manually collected DOM observation JSON')
    parser.add_argument('--output',type=Path,default=ROOT/'.local/phase2-live-evidence')
    args=parser.parse_args()
    target=args.output.resolve()
    if not target.is_relative_to((ROOT/'.local').resolve()):parser.error('Evidence output must remain under ignored .local')
    if not args.meeting_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.meeting_id):parser.error('Invalid meeting ID')
    token=args.token_file.read_text('utf-8').strip()
    def get(path):
        request=urllib.request.Request('http://127.0.0.1:8765/api/v1/'+path,headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=15) as response:return json.load(response)
    snapshot=get('meetings/'+args.meeting_id)
    if snapshot['persistence_mode']=='memory':parser.error('RAM-only meeting: disk export is disabled; inspect in the application')
    target.mkdir(parents=True,exist_ok=True)
    record=dict(provenance='manual live evidence; not automatically verified',live_gate='PENDING_REVIEW',snapshot=snapshot,metrics=get('metrics'))
    if args.observations:record['dom_observations']=json.loads(args.observations.read_text('utf-8'))
    path=target/(args.meeting_id+'.json');path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Local evidence saved. Review using docs/PHASE2_LIVE_RUNBOOK.md; no live gate was closed.')


if __name__=='__main__':main()
