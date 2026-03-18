import json
from pathlib import Path

from src.project_backend.import_pipeline import import_novel
from src.project_backend.rag_store import query_rag
from src.project_backend.task_runtime import create_task_request, start_task_run


TXT_SOURCE = '''Chapter 1
Aria enters the archive.

Rowan follows with a map.
'''


def test_task_runtime_and_rag_query_work_on_project_folder(tmp_path: Path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'project.json').write_text(json.dumps({'metadata': {'schemaVersion': 3, 'name': 'Runtime Test'}, 'counts': {}}), encoding='utf-8')
    source = tmp_path / 'novel.txt'
    source.write_text(TXT_SOURCE, encoding='utf-8')
    import_novel(root, source)

    task_request = create_task_request(
        root,
        {
            'taskType': 'qa_review',
            'agentType': 'qa-consistency-agent',
            'source': 'local-cli',
            'title': 'Run QA',
            'input': {'scope': 'project'},
            'contextScope': {},
            'reviewPolicy': 'manual_workbench',
            'targetIds': [],
            'prompt': 'Review the imported project.',
        },
    )
    task_run = start_task_run(root, task_request['id'])
    retrieval = query_rag(
        root,
        {
            'id': 'retrieval_test',
            'query': 'Aria archive map',
            'scope': {},
            'filters': {},
            'topK': 3,
            'includeNeighborChunks': False,
        },
    )

    assert task_request['status'] == 'queued'
    assert task_run['status'] == 'running'
    assert retrieval['backend'] == 'keyword'
    assert len(retrieval['items']) >= 1
    assert 'Aria' in retrieval['items'][0]['excerpt']
