import json
from pathlib import Path

from src.project_backend.import_pipeline import import_novel


MD_SOURCE = '''# Chapter One
## Scene A
Aria arrives at the station.

## Scene B
Rowan reveals the hidden route.
'''


def test_import_pipeline_creates_canonical_structure_and_review_artifacts(tmp_path: Path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'project.json').write_text(json.dumps({'metadata': {'schemaVersion': 3, 'name': 'Import Test'}, 'counts': {}}), encoding='utf-8')
    source = tmp_path / 'novel.md'
    source.write_text(MD_SOURCE, encoding='utf-8')

    job = import_novel(root, source)

    assert job['sourceFormat'] == 'md'
    assert len(job['canonicalChapterIds']) == 1
    assert len(job['canonicalSceneIds']) == 2
    assert (root / 'writing' / 'chapters' / f"{job['canonicalChapterIds'][0]}.json").exists()
    assert (root / 'writing' / 'scenes' / f"{job['canonicalSceneIds'][0]}.meta.json").exists()
    inbox = json.loads((root / 'system' / 'inbox.json').read_text(encoding='utf-8'))
    issues = json.loads((root / 'system' / 'issues.json').read_text(encoding='utf-8'))
    rag_docs = list((root / 'system' / 'rag' / 'documents').glob('*.json'))
    rag_chunks = list((root / 'system' / 'rag' / 'chunks').glob('*.json'))

    assert inbox[0]['source'] == 'import'
    assert issues[0]['source'] == 'import'
    assert rag_docs
    assert rag_chunks
