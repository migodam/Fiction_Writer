from typing import List, Optional
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship

class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    chapters: List["Chapter"] = Relationship(back_populates="project")
    facts: List["CanonFact"] = Relationship(back_populates="project")

class Chapter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    order_index: int
    title: str
    content: Optional[str] = None

    project: Project = Relationship(back_populates="chapters")

class RevealRule(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    fact_id: int = Field(foreign_key="canonfact.id")
    revealed_in_chapter: int = Field(default=0)
    
    fact: "CanonFact" = Relationship(back_populates="reveal_rule")

class CanonFact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    current_version_id: Optional[int] = None
    
    # 新增 category 字段，用于对应槽位 (e.g., 'premise', 'character', 'world', 'conflict', 'tone', 'ending')
    category: str = Field(default="general")
    
    project: Project = Relationship(back_populates="facts")
    reveal_rule: Optional[RevealRule] = Relationship(back_populates="fact")
    versions: List["FactVersion"] = Relationship(back_populates="fact")

class FactVersion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    fact_id: int = Field(foreign_key="canonfact.id")
    version_number: int
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    provenance: str = Field(default="user") 
    
    fact: CanonFact = Relationship(back_populates="versions")
