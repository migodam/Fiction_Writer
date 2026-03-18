from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from .contracts import EntityReference, TaskArtifact, TaskRequest, TaskRun, make_id, utc_now
from .project_repository import append_run_log, migrate_project, write_artifact, write_proposals, write_task_request, write_task_run


CHAPTER_PATTERN = re.compile(r"^(chapter\s+\d+|第.+章|序章|尾声)\s*(.*)$", re.IGNORECASE)


def _split_markdown(text: str) -> Tuple[List[Dict], List[Dict], str]:
    chapters: List[Dict] = []
    scenes: List[Dict] = []
    current_chapter = None
    current_scene_title = None
    current_scene_lines: List[str] = []

    def flush_scene() -> None:
        nonlocal current_scene_lines, current_scene_title, current_chapter
        if current_chapter is None or not current_scene_lines:
            return
        scene_id = make_id("scene")
        scenes.append(
            {
                "id": scene_id,
                "chapterId": current_chapter["id"],
                "title": current_scene_title or f"{current_chapter['title']} Scene {len([scene for scene in scenes if scene['chapterId'] == current_chapter['id']]) + 1}",
                "summary": "Imported from markdown source.",
                "content": "\n".join(current_scene_lines).strip(),
            }
        )
        current_chapter["sceneIds"].append(scene_id)
        current_scene_lines = []
        current_scene_title = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("# "):
            flush_scene()
            current_chapter = {
                "id": make_id("chap"),
                "title": line[2:].strip() or "Imported Chapter",
                "summary": "Imported chapter.",
                "goal": "",
                "notes": "Imported from markdown.",
                "sceneIds": [],
            }
            chapters.append(current_chapter)
        elif line.startswith("## "):
            flush_scene()
            current_scene_title = line[3:].strip() or "Imported Scene"
        elif current_chapter is None and line:
            current_chapter = {
                "id": make_id("chap"),
                "title": "Imported Chapter 1",
                "summary": "Imported chapter.",
                "goal": "",
                "notes": "Imported from markdown.",
                "sceneIds": [],
            }
            chapters.append(current_chapter)
            current_scene_lines.append(line)
        else:
            current_scene_lines.append(raw_line)
    flush_scene()
    return chapters, scenes, "high" if chapters else "low"


def _split_txt(text: str) -> Tuple[List[Dict], List[Dict], str]:
    chapters: List[Dict] = []
    scenes: List[Dict] = []
    lines = text.splitlines()
    current_chapter = None
    current_scene_lines: List[str] = []
    confidence = "low"

    def ensure_chapter(title: str) -> Dict:
        nonlocal current_chapter
        if current_chapter is None:
            current_chapter = {
                "id": make_id("chap"),
                "title": title,
                "summary": "Imported chapter.",
                "goal": "",
                "notes": "Imported from txt.",
                "sceneIds": [],
            }
            chapters.append(current_chapter)
        return current_chapter

    def flush_scene() -> None:
        nonlocal current_scene_lines, current_chapter
        if not current_scene_lines:
            return
        chapter = ensure_chapter("Imported Chapter 1")
        scene_id = make_id("scene")
        scenes.append(
            {
                "id": scene_id,
                "chapterId": chapter["id"],
                "title": f"{chapter['title']} Scene {len([scene for scene in scenes if scene['chapterId'] == chapter['id']]) + 1}",
                "summary": "Imported scene.",
                "content": "\n".join(current_scene_lines).strip(),
            }
        )
        chapter["sceneIds"].append(scene_id)
        current_scene_lines = []

    for line in lines:
        stripped = line.strip()
        match = CHAPTER_PATTERN.match(stripped)
        if match:
            flush_scene()
            current_chapter = {
                "id": make_id("chap"),
                "title": stripped,
                "summary": "Imported chapter.",
                "goal": "",
                "notes": "Imported from txt.",
                "sceneIds": [],
            }
            chapters.append(current_chapter)
            confidence = "medium"
            continue
        if stripped == "" and current_scene_lines:
            flush_scene()
            continue
        if stripped:
            ensure_chapter("Imported Chapter 1")
            current_scene_lines.append(line)

    flush_scene()
    return chapters, scenes, confidence


def _build_rag_artifacts(import_job_id: str, source_relative_path: str, scenes: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    doc_id = f"rag_doc_{import_job_id}"
    chunk_id = f"rag_chunk_{import_job_id}_1"
    joined_text = " ".join(scene["content"] for scene in scenes)[:500]
    documents = [
        {
            "id": doc_id,
            "sourceType": "import_source",
            "sourceId": import_job_id,
            "title": f"Import source {import_job_id}",
            "path": source_relative_path,
            "entityRefs": [{"type": "import_job", "id": import_job_id}],
            "chunkIds": [chunk_id],
            "updatedAt": utc_now(),
        }
    ]
    chunks = [
        {
            "id": chunk_id,
            "documentId": doc_id,
            "text": joined_text,
            "tokenCount": len(joined_text.split()),
            "keywords": list({word.lower() for word in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", joined_text)[:20]}),
            "entityRefs": [{"type": "import_job", "id": import_job_id}],
            "sourcePath": source_relative_path,
        }
    ]
    return documents, chunks


def import_novel(root_path: str | Path, source_path: str | Path, source_format: str | None = None) -> Dict:
    root = Path(root_path)
    migrate_project(root)
    source = Path(source_path)
    fmt = (source_format or source.suffix.lstrip(".") or "txt").lower()
    if fmt not in {"txt", "md", "docx"}:
        raise ValueError(f"Unsupported import format: {fmt}")
    if fmt == "docx":
        raise ValueError("docx import is reserved as a future extension; this round keeps it as a placeholder.")

    text = source.read_text(encoding="utf-8")
    chapters, scenes, confidence = _split_markdown(text) if fmt == "md" else _split_txt(text)

    import_job_id = make_id("import")
    request = TaskRequest(
        id=make_id("task"),
        taskType="novel_import",
        agentType="import-agent",
        source="local-cli",
        title=f"Import {source.name}",
        input={"sourceFileName": source.name, "sourceFormat": fmt},
        contextScope={},
        reviewPolicy="manual_workbench",
        createdAt=utc_now(),
        targetIds=[EntityReference(type="import_job", id=import_job_id)],
        prompt="Import raw novel source into deterministic structure and staged review artifacts.",
    )
    write_task_request(root, request)
    run = TaskRun(
        id=make_id("run"),
        taskRequestId=request.id,
        status="awaiting_user_input",
        attempt=1,
        executor="local-cli",
        adapter="rule-import-adapter",
        startedAt=utc_now(),
        heartbeatAt=utc_now(),
        summary=f"Imported {source.name} and staged metadata review artifacts.",
    )
    write_task_run(root, run)
    append_run_log(root, run.id, {"at": utc_now(), "event": "import_started", "source": source.name})

    staging_dir = root / "system" / "imports" / "staging" / import_job_id
    staging_dir.mkdir(parents=True, exist_ok=True)
    source_relative_path = f"system/imports/staging/{import_job_id}/source.{fmt}"
    (root / source_relative_path).write_text(text, encoding="utf-8")

    for index, chapter in enumerate(chapters):
        chapter.update({"orderIndex": index, "status": "draft"})
    for index, scene in enumerate(scenes):
        scene.update(
            {
                "orderIndex": index,
                "povCharacterId": None,
                "linkedCharacterIds": [],
                "linkedEventIds": [],
                "linkedWorldItemIds": [],
                "status": "draft",
            }
        )

    for chapter in chapters:
        chapter_path = root / "writing" / "chapters" / f"{chapter['id']}.json"
        chapter_path.parent.mkdir(parents=True, exist_ok=True)
        chapter_path.write_text(json.dumps(chapter, indent=2, ensure_ascii=False), encoding="utf-8")
    for scene in scenes:
        scene_meta_path = root / "writing" / "scenes" / f"{scene['id']}.meta.json"
        scene_body_path = root / "writing" / "scenes" / f"{scene['id']}.md"
        scene_meta_path.parent.mkdir(parents=True, exist_ok=True)
        scene_body_path.write_text(scene["content"], encoding="utf-8")
        scene_payload = dict(scene)
        scene_payload.pop("content", None)
        scene_meta_path.write_text(json.dumps(scene_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    proposal = {
        "id": make_id("proposal"),
        "title": f"Review metadata extracted from {source.name}",
        "source": "import",
        "kind": "import_review",
        "description": "Imported structure has been written canonically, but inferred metadata remains staged for Workbench review.",
        "targetEntityType": "proposal",
        "targetEntityId": None,
        "targetEntityRefs": [{"type": "import_job", "id": import_job_id}],
        "preview": f"Review character, location, organization, and event candidates extracted from {source.name}.",
        "reviewPolicy": "manual_workbench",
        "status": "pending",
        "createdAt": utc_now(),
        "originTaskRunId": run.id,
    }
    write_proposals(root, [proposal])

    issue = {
        "id": make_id("issue"),
        "title": "Imported metadata needs confirmation",
        "description": "This import wrote only deterministic chapter/scene structure. Metadata inference remains staged.",
        "severity": "medium",
        "status": "open",
        "source": "import",
        "referenceIds": [{"type": "import_job", "id": import_job_id}],
        "originTaskRunId": run.id,
        "suggestedProposalIds": [proposal["id"]],
        "fixSuggestion": "Review the import proposal batch in Workbench before metadata becomes canonical.",
    }
    issues_path = root / "system" / "issues.json"
    issues = json.loads(issues_path.read_text(encoding="utf-8"))
    issues.insert(0, issue)
    issues_path.write_text(json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8")

    import_job = {
        "id": import_job_id,
        "sourceFileName": source.name,
        "sourcePath": source_relative_path,
        "sourceFormat": fmt,
        "status": "awaiting_user_input",
        "stage": "proposal_generated",
        "segmentationConfidence": confidence,
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
        "taskRequestId": request.id,
        "taskRunId": run.id,
        "canonicalChapterIds": [chapter["id"] for chapter in chapters],
        "canonicalSceneIds": [scene["id"] for scene in scenes],
        "chapterCandidates": [
            {"id": chapter["id"], "title": chapter["title"], "summary": chapter["summary"], "confidence": confidence}
            for chapter in chapters
        ],
        "sceneCandidates": [
            {"id": scene["id"], "title": scene["title"], "summary": scene["summary"], "confidence": confidence}
            for scene in scenes
        ],
        "proposalIds": [proposal["id"]],
        "issueIds": [issue["id"]],
        "notes": ["Canonical chapter/scene skeleton created from deterministic parsing only."],
    }
    jobs_path = root / "system" / "imports" / "jobs.json"
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs.insert(0, import_job)
    jobs_path.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")

    (staging_dir / "manifest.json").write_text(json.dumps(import_job, indent=2, ensure_ascii=False), encoding="utf-8")
    (staging_dir / "chapter_candidates.json").write_text(json.dumps(import_job["chapterCandidates"], indent=2, ensure_ascii=False), encoding="utf-8")
    (staging_dir / "scene_candidates.json").write_text(json.dumps(import_job["sceneCandidates"], indent=2, ensure_ascii=False), encoding="utf-8")

    documents, chunks = _build_rag_artifacts(import_job_id, source_relative_path, scenes)
    for document in documents:
        (root / "system" / "rag" / "documents" / f"{document['id']}.json").write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    for chunk in chunks:
        (root / "system" / "rag" / "chunks" / f"{chunk['id']}.json").write_text(json.dumps(chunk, indent=2, ensure_ascii=False), encoding="utf-8")
    keyword_index_path = root / "system" / "rag" / "indexes" / "keyword-index.json"
    keyword_index = json.loads(keyword_index_path.read_text(encoding="utf-8"))
    keyword_index["documents"].extend([{"id": doc["id"], "title": doc["title"], "chunkIds": doc["chunkIds"]} for doc in documents])
    keyword_index["chunks"].extend([{"id": chunk["id"], "documentId": chunk["documentId"], "keywords": chunk["keywords"]} for chunk in chunks])
    keyword_index_path.write_text(json.dumps(keyword_index, indent=2, ensure_ascii=False), encoding="utf-8")

    artifact = TaskArtifact(
        id=make_id("artifact"),
        taskRunId=run.id,
        artifactType="import-manifest",
        path=f"system/imports/staging/{import_job_id}/manifest.json",
        summary=f"Import manifest for {source.name}",
    )
    write_artifact(root, run.id, artifact)
    append_run_log(root, run.id, {"at": utc_now(), "event": "import_completed", "chapters": len(chapters), "scenes": len(scenes)})
    return import_job
