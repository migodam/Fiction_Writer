"""
W1 Import Content Organizer — deterministic routing stage.

Enforces module ownership rules before proposal write:
  - World-only entities → World Model containers
  - Person names / role ranks → excluded (character or manuscript)
  - Module-contamination strings → excluded
  - categoryPath / parentId hierarchy attached to every world item
  - Items grouped into ProposalPackages by container key

No LLM calls. No file I/O. Pure dict → dict transformation.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict
from sidecar.supervisor.semantic_review import (
    CandidateLedgerEntry,
    RelocationPlan,
    WorldReviewDecision,
    assess_world_candidate,
    character_identity_index,
)

# ---------------------------------------------------------------------------
# TypedDict contracts
# ---------------------------------------------------------------------------


class OrganizerInput(TypedDict):
    characters: Dict[str, Any]          # entity_registry["characters"]
    events: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    world_candidates: Dict[str, Any]    # entity_registry["world_detailed"]
    manuscript_notes: List[Dict[str, Any]]
    timeline_architecture: Dict[str, Any]
    project_digest: Dict[str, Any]
    source_language: str                # "zh" | "en"


class WorldContainerProposal(TypedDict):
    id: str
    container_key: str
    label: str
    language: str
    type: str


class WorldItemProposal(TypedDict):
    entity_id: str
    name: str
    category: str
    categoryPath: List[str]
    parentId: Optional[str]
    description: str
    attributes: List[Dict[str, str]]
    confidence: float
    container_key: str
    containerId: str


class ExcludedItem(TypedDict):
    entity_id: str
    name: str
    original_category: str
    reason: str           # "module_contamination" | "person_name" | "person_title" | "event_phrase" | "identity_rank" | "role_rank"
    suggested_module: str # "relationship" | "character" | "manuscript" | "timeline" | "none"


class MergeCandidate(TypedDict):
    entity_ids: List[str]
    dedupe_key: str
    reason: str


class ProposalPackage(TypedDict):
    package_id: str
    container_key: str
    label: str
    items: List[WorldItemProposal]
    depends_on: List[str]


class OrganizerOutput(TypedDict):
    world_containers: List[WorldContainerProposal]
    world_items: List[WorldItemProposal]
    excluded_items: List[ExcludedItem]
    merge_candidates: List[MergeCandidate]
    proposal_packages: List[ProposalPackage]
    warnings: List[str]
    candidate_ledger: List[CandidateLedgerEntry]
    quarantine_items: List[CandidateLedgerEntry]
    review_decisions: List[WorldReviewDecision]
    relocation_plans: List[RelocationPlan]


# ---------------------------------------------------------------------------
# Taxonomy constants  (self-contained — not imported from w1_import.py)
# ---------------------------------------------------------------------------

WORLD_ONTOLOGY_CATEGORIES: tuple[str, ...] = (
    "location",
    "organization",
    "faction",
    "item",
    "artifact",
    "rule",
    "system",
    "cultivation_method",
    "concept",
    "culture",
    "custom",
)

# Chinese name-suffix patterns that indicate world entities (not person names)
_ORG_HINTS: tuple[str, ...] = ("门", "派", "宗", "帮", "会", "盟", "山庄", "书院")
_LOC_HINTS: tuple[str, ...] = (
    "城", "镇", "村", "谷", "山", "峰", "河", "湖", "岛", "国",
    "州", "府", "岭", "洞", "堂", "院", "阁", "殿", "宫", "楼", "台",
)
# Suffixes that disambiguate 堂/院/阁 as location rather than rank
_LOC_AMBIGUOUS_SUFFIXES: tuple[str, ...] = ("堂", "峰", "谷", "院", "阁", "殿", "宫", "楼", "台")
_LOCATION_FACILITY_HINTS: tuple[str, ...] = ("哨卡", "岗哨", "关卡", "关隘", "通道", "入口")
_INSTITUTION_LOCATION_SUFFIXES: tuple[str, ...] = ("总堂", "分堂")

# Module contamination: these strings are not world-model entities
_CONTAMINATION_NAMES: frozenset[str] = frozenset({
    "人物关系图", "人物关系", "关系图", "关系网络",
    "事件时间线", "时间线", "时间轴",
    "timeline", "relationship graph", "character map",
    "event timeline", "story timeline",
})
_CONTAMINATION_PATTERN = re.compile(
    r"(关系图|关系网络|时间线|时间轴|timeline|relationship.?graph|character.?map|event.?timeline)",
    re.IGNORECASE,
)

# Identity/institutional ranks — NOT cultivation methods; belong in manuscript notes
_IDENTITY_RANK_NAMES: frozenset[str] = frozenset({
    "记名弟子", "内门弟子", "外门弟子",
    "核心弟子", "真传弟子", "外院弟子",
})

# Role/rank titles that must NOT route to cultivation_method
_ROLE_RANK_NAMES: frozenset[str] = frozenset({
    "弟子", "门丁", "护法", "堂主",
    "师兄", "师弟", "师姐", "师妹",
    "长老", "供奉", "掌门", "副掌门",
    "执事", "内门", "外门",
})

# Person-bearing titles are not organizations.  The prefix check deliberately
# requires a short name-like stem so named institutions such as 七绝堂 remain
# eligible for normal world classification.
_PERSON_TITLE_SUFFIXES: tuple[str, ...] = (
    "副掌门", "副门主", "掌门", "门主", "堂主", "护法", "长老", "供奉",
    "执事", "大夫", "师父", "师傅", "师兄", "师姐", "师弟", "师妹",
)
_PERSON_TITLE_PATTERN = re.compile(
    rf"^[\u3400-\u9fff]{{1,3}}(?:{'|'.join(_PERSON_TITLE_SUFFIXES)})$"
)

# These phrases describe a story occurrence, not durable world lore.  Exact
# event-registry matches provide a second deterministic route for variants
# whose names do not contain one of these lexical markers.
_EVENT_PHRASE_MARKERS: tuple[str, ...] = (
    "测试", "考验", "考核", "选拔", "比试", "大会", "事件", "之战", "冲突",
    "相遇", "离开", "加入", "拜入", "抵达", "救下", "死亡", "突破",
)

# Name terminal suffixes that strongly signal a cultivation technique
_CULTIVATION_NAME_SUFFIXES: tuple[str, ...] = (
    "功", "法诀", "秘术", "术法", "功诀", "内功", "外功", "心法",
    "剑诀", "步法", "刀法", "拳法", "掌法", "指法", "气法",
)

# Name tokens that signal a rule/realm/system item (in the name itself, not raw_category)
_RULE_NAME_HINTS: tuple[str, ...] = (
    "境界", "层", "炼气期", "筑基期", "结丹期", "元婴期", "化神期",
    "制度", "门规", "法规",
)

# Category alias map (raw string → canonical category)
_CATEGORY_ALIASES: dict[str, str] = {
    "place": "location",
    "location": "location",
    "map": "location",
    "地名": "location",
    "地点": "location",
    "organization": "organization",
    "organisation": "organization",
    "faction": "faction",
    "势力": "faction",
    "sect": "organization",
    "门派": "organization",
    "宗门": "organization",
    "帮派": "organization",
    "clan": "organization",
    "guild": "organization",
    "object": "item",
    "artifact": "artifact",
    "法器": "artifact",
    "item": "item",
    "丹药": "item",
    "物品": "item",
    "weapon": "item",
    "treasure": "artifact",
    "concept": "concept",
    "lore": "concept",
    "rule": "rule",
    "规则": "rule",
    "system": "system",
    "功法": "cultivation_method",
    "法术": "cultivation_method",
    "术法": "cultivation_method",
    "法诀": "cultivation_method",
    "magic": "rule",
    "cultivation": "cultivation_method",
    "culture": "culture",
    "custom": "custom",
}

# Container key → (zh_label, en_label)
_CONTAINER_LABELS: dict[str, tuple[str, str]] = {
    "locations":           ("地理位置",       "Locations"),
    "organizations":       ("门派组织",        "Organizations & Factions"),
    "items":               ("物品与法器",       "Items & Artifacts"),
    "cultivation_methods": ("功法与术法",       "Cultivation Methods"),
    "rules":               ("修炼境界与制度",   "Rules & Systems"),
    "concepts":            ("概念与设定",       "Concepts & Lore"),
    "culture":             ("文化与习俗",       "Culture"),
}

# categoryPath for world items (zh, excludes item name — name appended at call site)
_CATEGORY_PATH_ROOTS: dict[str, list[str]] = {
    "location":          ["世界模型", "地理位置"],
    "organization":      ["世界模型", "门派组织"],
    "faction":           ["世界模型", "门派组织"],
    "item":              ["世界模型", "物品与法器"],
    "artifact":          ["世界模型", "物品与法器"],
    "cultivation_method":["世界模型", "功法与术法"],
    "rule":              ["世界模型", "修炼境界与制度"],
    "system":            ["世界模型", "修炼境界与制度"],
    "concept":           ["世界模型", "概念与设定"],
    "culture":           ["世界模型", "文化与习俗"],
    "custom":            ["世界模型", "概念与设定"],
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _is_module_contamination(name: str) -> bool:
    text = name.strip().lower()
    if not text:
        return False
    if text in {n.lower() for n in _CONTAMINATION_NAMES}:
        return True
    return bool(_CONTAMINATION_PATTERN.search(text))


def _is_person_name(name: str, candidate: dict, character_names: frozenset[str]) -> bool:
    if name in character_names:
        return True
    role = str(candidate.get("role") or "").lower()
    if role in {"character", "person", "protagonist", "antagonist", "npc"}:
        return True
    category_raw = str(candidate.get("category") or "").lower()
    return any(token in category_raw for token in ("person", "character", "人物", "角色", "人名"))


def _character_names(characters: dict[str, Any]) -> frozenset[str]:
    """Collect canonical names and aliases from the reconciled registry."""
    names: set[str] = set()
    for key, value in characters.items():
        if not isinstance(value, dict):
            continue
        for field in ("name", "canonical_name", "canonicalName"):
            text = str(value.get(field) or "").strip()
            if text:
                names.add(text)
        aliases = value.get("aliases") or []
        if isinstance(aliases, list):
            names.update(str(alias).strip() for alias in aliases if str(alias).strip())
        if not any(value.get(field) for field in ("name", "canonical_name", "canonicalName")):
            fallback = str(key).strip()
            if fallback:
                names.add(fallback)
    return frozenset(names)


def _is_person_title(name: str) -> bool:
    stripped = name.strip()
    return bool(_PERSON_TITLE_PATTERN.fullmatch(stripped))


def _event_names(events: list[dict[str, Any]]) -> frozenset[str]:
    names: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        for field in ("name", "title", "event_name", "eventName"):
            text = str(event.get(field) or "").strip()
            if text:
                names.add(text)
    return frozenset(names)


def _is_event_phrase(name: str, event_names: frozenset[str]) -> bool:
    stripped = name.strip()
    return stripped in event_names or any(marker in stripped for marker in _EVENT_PHRASE_MARKERS)


def _is_identity_rank(name: str) -> bool:
    stripped = name.strip()
    return stripped in _IDENTITY_RANK_NAMES


def _is_role_rank_misrouted(name: str, raw_category: str) -> bool:
    """True when a bare institutional title is incorrectly staged as World."""
    stripped = name.strip()
    normalized_cat = str(raw_category or "").lower().strip()
    # Allow if name ends with a place suffix (e.g. "执法堂" is a hall, not a rank)
    if any(stripped.endswith(suffix) for suffix in _LOC_AMBIGUOUS_SUFFIXES):
        return False
    if stripped in _ROLE_RANK_NAMES:
        return True
    return normalized_cat == "cultivation_method" and any(rank in stripped for rank in _ROLE_RANK_NAMES)


def classify_world_item(name: str, raw_category: str, description: str = "") -> str:
    """Deterministic taxonomy classifier. Returns a WORLD_ONTOLOGY_CATEGORIES value.

    Priority order (earlier rules win):
    1. Person/character markers in raw_category → custom
    2. Name ends with cultivation suffix AND description doesn't say rank/realm → cultivation_method
    3. Name contains rule/realm hints (境界, 层, 制度…) → rule
    4. Role/rank token in name AND not a location suffix → rule
    5. Explicit cultivation hint in raw_category → cultivation_method
    6. Name location / org suffix → location / organization
    7. Alias map on raw_category
    8. Substring matches on raw_category
    9. Name suffix fallback
    10. Default → concept
    """
    raw = str(raw_category or "").strip().lower()
    clean = name.strip()
    desc_lower = (description or "").lower()

    # 1. Person/character markers in raw → custom (defensive; exclusion handles this upstream)
    if any(t in raw for t in ("person", "character", "人物", "角色", "人名")):
        return "custom"

    # A headquarters/branch hall or a defensive facility can belong to an
    # organization, but is itself a visitable place.  This check deliberately
    # precedes the generic 门/堂 organization fallback below.
    if any(token in clean for token in _LOCATION_FACILITY_HINTS):
        return "location"
    if clean.endswith(_INSTITUTION_LOCATION_SUFFIXES) and any(
        token in desc_lower for token in ("位于", "坐落", "山峰", "山上", "建筑", "地点", "占据", "通道")
    ):
        return "location"

    # 2. Terminal cultivation-method suffix in name → cultivation_method
    #    "项甲功" ends in "功" — overrides raw rule/system signal unless desc says rank/realm
    if any(clean.endswith(s) for s in _CULTIVATION_NAME_SUFFIXES):
        if not any(t in desc_lower for t in ("境界", "层次", "等级制度", "rank")):
            return "cultivation_method"

    # 3. Name itself contains realm/rule tokens (e.g. 修炼境界, 弟子制度)
    if any(t in clean for t in _RULE_NAME_HINTS) and not any(
        clean.endswith(s) for s in _CULTIVATION_NAME_SUFFIXES
    ):
        return "rule"

    # 4. A council is an organization even if its name includes a rank token.
    if clean.endswith(("会", "盟")) and any(
        token in desc_lower for token in ("组织", "势力", "议事机构", "长老组成", "council")
    ):
        return "organization"

    # 5. Role/rank suffix in name AND name doesn't end in a location suffix → rule
    if any(t in clean for t in _ROLE_RANK_NAMES) and not any(
        clean.endswith(s) for s in _LOC_AMBIGUOUS_SUFFIXES
    ):
        return "rule"

    # 6. Explicit cultivation hints in raw category
    if any(t in raw for t in ("method", "spell", "cultivation", "功法", "法术", "术法", "法诀", "秘术", "修炼法门")):
        return "cultivation_method"

    # 7. Name suffix → organization / location (higher priority than alias map).
    # A sect such as 七玄门 contains a generic place-like character but is not a location.
    if any(t in clean for t in _ORG_HINTS):
        return "organization"
    if any(t in clean for t in _LOC_HINTS):
        return "location"

    # 8. Alias map
    alias = _CATEGORY_ALIASES.get(raw)
    if alias:
        return alias

    # 9. Raw string substring matches
    if any(t in raw for t in ("organization", "organisation", "sect", "clan", "guild", "组织", "门派", "宗门", "帮派")):
        return "organization"
    if any(t in raw for t in ("faction", "alliance", "势力", "阵营", "联盟", "派系")):
        return "faction"
    if any(t in raw for t in ("location", "place", "map", "地点", "位置", "地理")):
        return "location"
    if any(t in raw for t in ("artifact", "treasure", "法器", "宝物", "灵器")):
        return "artifact"
    if any(t in raw for t in ("item", "object", "物品", "丹药", "道具")):
        return "item"
    if any(t in raw for t in ("system", "体系", "修炼")):
        return "system"
    if any(t in raw for t in ("rule", "law", "规则", "法则", "制度")):
        return "rule"
    if any(t in raw for t in ("culture", "习俗")):
        return "culture"
    if any(t in raw for t in ("custom", "自定义")):
        return "custom"

    # 10. Name suffix fallback (catch cases where raw was empty)
    if any(t in clean for t in _LOC_HINTS):
        return "location"
    if any(t in clean for t in _ORG_HINTS):
        return "organization"

    return "concept"


def _normalize_category(name: str, raw_category: Any = "") -> str:
    """Thin wrapper kept for backward compatibility. Delegates to classify_world_item."""
    return classify_world_item(name, str(raw_category or ""))


def _container_key_for_category(category: str) -> str:
    if category == "location":
        return "locations"
    if category in {"organization", "faction"}:
        return "organizations"
    if category in {"item", "artifact"}:
        return "items"
    if category == "cultivation_method":
        return "cultivation_methods"
    if category in {"rule", "system"}:
        return "rules"
    if category == "culture":
        return "culture"
    return "concepts"


def _build_category_path(name: str, category: str) -> list[str]:
    root = _CATEGORY_PATH_ROOTS.get(category, _CATEGORY_PATH_ROOTS["concept"])
    return root + [name]


def _container_label(container_key: str, language: str) -> str:
    pair = _CONTAINER_LABELS.get(container_key)
    if not pair:
        return container_key
    return pair[0] if language == "zh" else pair[1]


def _candidate_entity_id(name: str, candidate: dict) -> str:
    return str(
        candidate.get("id")
        or candidate.get("entity_id")
        or f"world_{name[:32].replace(' ', '_')}"
    )


def _container_id(container_key: str) -> str:
    """Stable import target ID; safe to reference from every item proposal."""
    return f"world_container_{container_key}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def organize_project_content(organizer_input: OrganizerInput) -> OrganizerOutput:
    """
    Route import candidates to correct modules and produce structured proposal packages.

    Deterministic — no LLM calls, no I/O.
    """
    language = organizer_input.get("source_language") or "zh"
    world_candidates: dict[str, Any] = organizer_input.get("world_candidates") or {}
    characters: dict[str, Any] = organizer_input.get("characters") or {}
    warnings: list[str] = []

    # Reconciled registry evidence takes precedence, with narrow lexical
    # fallbacks for title-bearing people and event/episode phrases.
    character_names = _character_names(characters)
    character_index = character_identity_index(characters)
    event_names = _event_names(organizer_input.get("events") or [])

    world_items: list[WorldItemProposal] = []
    excluded_items: list[ExcludedItem] = []
    candidate_ledger: list[CandidateLedgerEntry] = []
    quarantine_items: list[CandidateLedgerEntry] = []
    review_decisions: list[WorldReviewDecision] = []
    relocation_plans: list[RelocationPlan] = []

    emitted_keys: set[tuple[str, str]] = set()
    for name, candidate in world_candidates.items():
        if not isinstance(candidate, dict):
            candidate = {}
        raw_category = str(candidate.get("category") or candidate.get("world_category") or "concept")
        entity_id = _candidate_entity_id(name, candidate)

        # --- Priority 1: module contamination ---
        if _is_module_contamination(name):
            suggested = "timeline" if any(
                t in name for t in ("时间线", "timeline", "时间轴")
            ) else "relationship"
            excluded_items.append(ExcludedItem(
                entity_id=entity_id,
                name=name,
                original_category=raw_category,
                reason="module_contamination",
                suggested_module=suggested,
            ))
            continue

        # Direct registry matches are not ambiguous and preserve the legacy
        # Character/Timeline ownership behavior before semantic assessment.
        if _is_person_name(name, candidate, character_names) and not _is_person_title(name):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id, name=name, original_category=raw_category,
                reason="person_name", suggested_module="character",
            ))
            continue
        if _is_event_phrase(name, event_names):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id, name=name, original_category=raw_category,
                reason="event_phrase", suggested_module="timeline",
            ))
            continue
        if _is_identity_rank(name):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id, name=name, original_category=raw_category,
                reason="identity_rank", suggested_module="manuscript",
            ))
            continue
        if _is_role_rank_misrouted(name, raw_category):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id, name=name, original_category=raw_category,
                reason="role_rank", suggested_module="manuscript",
            ))
            continue

        # Semantic review must run before legacy title/name filtering.  It
        # recognizes title+person mixtures (for example 正门主王六) and emits a
        # relocation plan rather than leaking the candidate into World.
        description = str(
            candidate.get("description")
            or candidate.get("summary")
            or candidate.get("notes")
            or ""
        )
        category = classify_world_item(name, raw_category, description)
        container_key = _container_key_for_category(category)
        assessment = assess_world_candidate(
            candidate_id=entity_id,
            raw_name=name,
            candidate=candidate,
            character_index=character_index,
            category=category,
            container_id=_container_id(container_key),
        )
        candidate_ledger.append(assessment["ledger"])
        review_decisions.append(assessment["decision"])
        if "relocation_plan" in assessment:
            relocation_plans.append(assessment["relocation_plan"])
        if assessment["ledger"]["status"] == "quarantined":
            quarantine_items.append(assessment["ledger"])
            reason_codes = assessment["ledger"]["reason_codes"]
            is_unresolved_person = "unresolved_person_title" in reason_codes
            excluded_items.append(ExcludedItem(
                entity_id=entity_id,
                name=name,
                original_category=raw_category,
                reason="person_title" if is_unresolved_person else reason_codes[0] if reason_codes else "semantic_hold",
                suggested_module="character" if is_unresolved_person else "none",
            ))
            continue
        if assessment["ledger"]["status"] == "relocation_required":
            excluded_items.append(ExcludedItem(
                entity_id=entity_id,
                name=name,
                original_category=raw_category,
                reason="person_title_mixed",
                suggested_module="character",
            ))
            continue

        # --- Priority 2: narrow lexical title-bearing person ---
        if _is_person_title(name):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id,
                name=name,
                original_category=raw_category,
                reason="person_title",
                suggested_module="character",
            ))
            continue

        # --- Priority 3: person name ---
        if _is_person_name(name, candidate, character_names):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id,
                name=name,
                original_category=raw_category,
                reason="person_name",
                suggested_module="character",
            ))
            continue

        # --- Priority 4: event/episode phrase, registry-correlated or lexical ---
        if _is_event_phrase(name, event_names):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id,
                name=name,
                original_category=raw_category,
                reason="event_phrase",
                suggested_module="timeline",
            ))
            continue

        # --- Priority 5: identity/institutional rank ---
        if _is_identity_rank(name):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id,
                name=name,
                original_category=raw_category,
                reason="identity_rank",
                suggested_module="manuscript",
            ))
            continue

        # --- Priority 6: role/rank misrouted to cultivation_method ---
        if _is_role_rank_misrouted(name, raw_category):
            excluded_items.append(ExcludedItem(
                entity_id=entity_id,
                name=name,
                original_category=raw_category,
                reason="role_rank",
                suggested_module="manuscript",
            ))
            continue

        # --- Classify and emit world item ---
        dedupe_key = (name.strip(), category)
        if dedupe_key in emitted_keys:
            warnings.append(f"Duplicate world placement rejected: '{name}' already routes to {container_key}.")
            continue
        emitted_keys.add(dedupe_key)
        category_path = _build_category_path(name, category)

        # Ambiguity warning for 堂/院 suffix that defaulted to location
        if any(name.endswith(s) for s in ("堂", "院")) and category == "location":
            warnings.append(
                f"Ambiguous: '{name}' defaulted to location; may be organization — verify context."
            )

        raw_attrs = candidate.get("attributes") or []
        attributes: list[dict[str, str]] = []
        if isinstance(raw_attrs, list):
            for attr in raw_attrs:
                if isinstance(attr, dict):
                    attributes.append({
                        "key": str(attr.get("key") or ""),
                        "value": str(attr.get("value") or ""),
                    })

        confidence = float(candidate.get("confidence") or 0.7)

        world_items.append(WorldItemProposal(
            entity_id=entity_id,
            name=name,
            category=category,
            categoryPath=category_path,
            parentId=None,
            description=description,
            attributes=attributes,
            confidence=confidence,
            container_key=container_key,
            containerId=_container_id(container_key),
        ))

    # --- Merge candidate detection ---
    merge_candidates = _detect_merge_candidates(world_items)

    # --- Build containers (only keys that have surviving items) ---
    used_keys: list[str] = []
    for k in _CONTAINER_LABELS:
        if any(item["container_key"] == k for item in world_items):
            used_keys.append(k)

    world_containers: list[WorldContainerProposal] = [
        WorldContainerProposal(
            id=_container_id(k),
            container_key=k,
            label=_container_label(k, language),
            language=language,
            type="notebook",
        )
        for k in used_keys
    ]

    # --- Group into proposal packages ---
    proposal_packages = _build_proposal_packages(world_items, used_keys, language)

    return OrganizerOutput(
        world_containers=world_containers,
        world_items=world_items,
        excluded_items=excluded_items,
        merge_candidates=merge_candidates,
        proposal_packages=proposal_packages,
        warnings=warnings,
        candidate_ledger=candidate_ledger,
        quarantine_items=quarantine_items,
        review_decisions=review_decisions,
        relocation_plans=relocation_plans,
    )


def _detect_merge_candidates(items: list[WorldItemProposal]) -> list[MergeCandidate]:
    seen: dict[str, list[str]] = {}
    for item in items:
        key = f"{item['name'].strip().lower()}::{item['category']}"
        seen.setdefault(key, []).append(item["entity_id"])
    result: list[MergeCandidate] = []
    for dedupe_key, ids in seen.items():
        if len(ids) >= 2:
            result.append(MergeCandidate(
                entity_ids=ids,
                dedupe_key=dedupe_key,
                reason="duplicate_dedupe_key",
            ))
    return result


def _build_proposal_packages(
    items: list[WorldItemProposal],
    used_keys: list[str],
    language: str,
) -> list[ProposalPackage]:
    packages: list[ProposalPackage] = []
    for key in used_keys:
        bucket = [item for item in items if item["container_key"] == key]
        if not bucket:
            continue
        packages.append(ProposalPackage(
            package_id=f"org_{key}_{uuid.uuid4().hex[:8]}",
            container_key=key,
            label=_container_label(key, language),
            items=bucket,
            depends_on=[],
        ))
    return packages
