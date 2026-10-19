"""Load labelled synthetic sources into an already-running local backend."""

import json

from meet import ROOT, request


def main():
    from dotenv import load_dotenv
    from app.config import data_directory

    load_dotenv(ROOT / '.env')
    directory = data_directory()
    if not (directory / 'pairing-token').exists():
        raise SystemExit('Start backend with the same data directory before loading demo.')

    def api(path, body=None):
        return request(path, directory=directory, body=body)

    corpus = json.loads((ROOT / 'fixtures/demo-project.json').read_text('utf8'))
    if any(project['name'] == corpus['name'] for project in api('/api/v1/projects')):
        print('Demo already exists; use Sources -> Reindex or delete the demo project to reset.')
        return
    project = api('/api/v1/projects', {key: corpus[key] for key in ('name', 'description', 'glossary')})
    for source in corpus['sources']:
        result = api('/api/v1/projects/' + project['id'] + '/sources',
                     {key: value for key, value in source.items() if key != 'key'})
        if result['job']['status'] != 'ready':
            raise SystemExit('Demo indexing failed; inspect the source error in the dashboard.')
    print('Created DEMO project with 12 synthetic sources. Choose Demo in Live; no API key required.')


if __name__ == '__main__':
    main()
