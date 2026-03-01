from typing import List
from sqlmodel import Session, select
from .models import CanonFact, FactVersion, RevealRule

def get_revealed_facts_for_chapter(session: Session, project_id: int, target_chapter_order: int) -> List[FactVersion]:
    """
    获取指定项目在指定章节进度下的“有限视角知识快照”。
    
    逻辑：
    1. 查找属于该 project 的所有 CanonFact。
    2. 检查其 RevealRule：如果 revealed_in_chapter <= target_chapter_order，则认为已揭示。
    3. 返回已揭示事实的当前活动版本 (latest Version)。
    """
    statement = (
        select(CanonFact, FactVersion, RevealRule)
        .join(FactVersion, CanonFact.current_version_id == FactVersion.id)
        .join(RevealRule, CanonFact.id == RevealRule.fact_id)
        .where(CanonFact.project_id == project_id)
    )
    
    results = session.exec(statement).all()
    
    revealed_versions = []
    for fact, version, rule in results:
        # 如果 rule 设置了章节条件，并且当前请求的章节大于等于该条件，则通过
        if rule.revealed_in_chapter <= target_chapter_order:
            revealed_versions.append(version)
            
    return revealed_versions

def add_canon_fact(session: Session, project_id: int, content: str, category: str = "general", reveal_in_chapter: int = 0, provenance: str = "user") -> CanonFact:
    """
    辅助函数：添加一条包含版本和 Reveal 规则的事实
    """
    # 1. 创建 Fact 实体
    fact = CanonFact(project_id=project_id, category=category)
    session.add(fact)
    session.commit()
    session.refresh(fact)
    
    # 2. 创建 Version 1
    version = FactVersion(fact_id=fact.id, version_number=1, content=content, provenance=provenance)
    session.add(version)
    session.commit()
    session.refresh(version)
    
    # 3. 更新 Fact 指向 Version 1
    fact.current_version_id = version.id
    session.add(fact)
    
    # 4. 创建 Reveal Rule
    rule = RevealRule(fact_id=fact.id, revealed_in_chapter=reveal_in_chapter)
    session.add(rule)
    session.commit()
    session.refresh(fact)
    
    return fact

def update_canon_fact(session: Session, fact_id: int, new_content: str, provenance: str = "user") -> FactVersion:
    """
    辅助函数：更新事实内容，采用追加版本的方式（不可变历史）
    """
    fact = session.get(CanonFact, fact_id)
    if not fact:
        raise ValueError(f"Fact {fact_id} not found")
        
    # 获取当前版本号
    statement = select(FactVersion).where(FactVersion.fact_id == fact.id).order_by(FactVersion.version_number.desc())
    latest_version = session.exec(statement).first()
    next_version_num = latest_version.version_number + 1 if latest_version else 1
    
    # 创建新版本
    new_version = FactVersion(fact_id=fact.id, version_number=next_version_num, content=new_content, provenance=provenance)
    session.add(new_version)
    session.commit()
    session.refresh(new_version)
    
    # 更新当前指针
    fact.current_version_id = new_version.id
    session.add(fact)
    session.commit()
    
    return new_version
