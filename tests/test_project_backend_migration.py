import json
from pathlib import Path

from src.project_backend.project_repository import load_project, migrate_project
from src.project_backend.prompt_registry import get_prompt_template, load_prompt_registry


def test_project_backend_migration_creates_v4_scaffold(tmp_path: Path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'project.json').write_text(json.dumps({'metadata': {'schemaVersion': 3, 'name': 'Legacy'}, 'counts': {}}), encoding='utf-8')

    schema = migrate_project(root)

    assert schema['schemaVersion'] == 4
    assert (root / 'system' / 'schema' / 'schema.json').exists()
    assert (root / 'system' / 'imports' / 'jobs.json').exists()
    assert (root / 'system' / 'rag' / 'manifest.json').exists()
    assert (root / 'entities' / 'scripts').exists()
    assert (root / 'exports' / 'video').exists()


def test_prompt_registry_reads_project_local_templates(tmp_path: Path):
    root = tmp_path / 'proj'
    migrate_project(root)
    template = {
        'id': 'import-agent',
        'name': 'Import Agent',
        'agentType': 'import-agent',
        'purpose': 'Import source files',
        'inputContract': [],
        'outputContract': [],
        'reviewPolicy': 'manual_workbench',
        'promptTemplate': '[[USER_CUSTOM_REQUIREMENTS]]',
        'userCustomPromptSlot': '[[USER_CUSTOM_REQUIREMENTS]]',
        'modelHints': ['json'],
        'version': 1,
        'promptTemplateSlots': [],
        'forbiddenActions': [],
        'writeTargets': ['proposal'],
        'requiresWorkbenchReview': True,
    }
    template_path = root / 'system' / 'prompts' / 'templates' / 'import-agent.json'
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text(json.dumps(template, indent=2), encoding='utf-8')

    registry = load_prompt_registry(root)
    loaded = get_prompt_template(root, 'import-agent')
    project = load_project(root)

    assert len(registry) == 1
    assert loaded is not None
    assert loaded['id'] == 'import-agent'
    assert project['prompt_templates'][0]['name'] == 'Import Agent'
