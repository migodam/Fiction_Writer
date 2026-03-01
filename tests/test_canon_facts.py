import pytest
from sqlmodel import SQLModel, Session, create_engine
from src.core.models import Project, Chapter
from src.core.narrative_engine import get_revealed_facts_for_chapter, add_canon_fact, update_canon_fact

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_reveal_filter(session: Session):
    # Setup test data
    project = Project(name="Test Novel")
    session.add(project)
    session.commit()
    session.refresh(project)

    # Fact 1: Revealed immediately (chapter 0/1)
    fact1 = add_canon_fact(session, project.id, "Protagonist has an old sword", reveal_in_chapter=1)
    
    # Fact 2: Revealed in chapter 5
    fact2 = add_canon_fact(session, project.id, "Mentor is the villain", reveal_in_chapter=5)

    # Test Chapter 1 View
    facts_chap1 = get_revealed_facts_for_chapter(session, project.id, 1)
    assert len(facts_chap1) == 1
    assert facts_chap1[0].content == "Protagonist has an old sword"

    # Test Chapter 4 View (should still not see Fact 2)
    facts_chap4 = get_revealed_facts_for_chapter(session, project.id, 4)
    assert len(facts_chap4) == 1

    # Test Chapter 5 View (should see both)
    facts_chap5 = get_revealed_facts_for_chapter(session, project.id, 5)
    assert len(facts_chap5) == 2
    contents = [f.content for f in facts_chap5]
    assert "Protagonist has an old sword" in contents
    assert "Mentor is the villain" in contents

def test_version_updates(session: Session):
    project = Project(name="Version Test Novel")
    session.add(project)
    session.commit()
    
    fact = add_canon_fact(session, project.id, "Initial fact", reveal_in_chapter=1)
    
    # Update fact
    new_version = update_canon_fact(session, fact.id, "Updated fact")
    
    assert new_version.version_number == 2
    assert new_version.content == "Updated fact"
    
    # Check what engine returns
    facts = get_revealed_facts_for_chapter(session, project.id, 1)
    assert len(facts) == 1
    assert facts[0].content == "Updated fact"
    assert facts[0].version_number == 2
