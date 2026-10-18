import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app.storage import Storage,uid,now
from app.config import Config
from app.main import create_app
from fastapi.testclient import TestClient

@pytest.fixture
def store(tmp_path):
    storage=Storage(tmp_path/'data')
    yield storage
    storage.close()

@pytest.fixture
def project(store):return store.create_project(dict(name='Project A',description='',glossary={}))

@pytest.fixture
def meeting(store,project):return store.create_meeting(dict(project_id=project['id'],title='Test meeting',timezone='America/Los_Angeles',persistence_mode='local',demo=False,meeting_key='/aaa-bbbb-ccc'))

def caption(text='Can we deploy?',segment='seg-1',revision=1,seq=1,**kwargs):
    return dict(type='caption.upsert',protocol_version=1,event_id=uid(),capture_epoch='epoch-1',segment_id=segment,revision=revision,seq=seq,speaker_label='Client',text=text,observed_at=now(),stable=True,adapter_version='fixture-v1',**kwargs)

@pytest.fixture
def client(tmp_path):
    config=Config(tmp_path/'api','test-pairing-token',('chrome-extension://'+'a'*32,'http://127.0.0.1:5173'))
    application=create_app(config)
    with TestClient(application,base_url='http://127.0.0.1:8765',headers={'Authorization':'Bearer test-pairing-token'}) as c:yield c

def pytest_runtest_makereport(item,call):
    # IDs also appear in JUnit evidence, independent of final reporting prose.
    if call.when=='call':
        ids=[value for marker in item.iter_markers('acceptance') for value in marker.args]
        if ids:item.user_properties.append(('acceptance_ids',','.join(ids)))
