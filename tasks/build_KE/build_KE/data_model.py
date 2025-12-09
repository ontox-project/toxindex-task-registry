from typing import List, Optional
from pydantic import BaseModel, Field, model_validator, field_validator
from enum import Enum

class EventType(str, Enum):
    MIE = "MIE"
    KE = "KE"
    AO = "AO"


class BiologicalLevel(str, Enum):
    MOLECULAR = "molecular"
    CELLULAR = "cellular"
    TISSUE = "tissue"
    ORGAN = "organ"
    ORGANISM = "organism"
    POPULATION = "population"


class KeyEvent(BaseModel):
    name: str
    description: Optional[str] = None
    event_type: EventType
    biological_level: BiologicalLevel
    organ: Optional[str] = None

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, v):
        return v.upper() if v else v

    @field_validator("biological_level", mode="before")
    @classmethod
    def normalize_bio_level(cls, v):
        return v.lower() if v else v


class KeyEventsList(BaseModel):
    events: List[KeyEvent] = Field(default_factory=list)


class Relationship(BaseModel):
    source_event_id: str = Field(..., min_length=1)
    target_event_id: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def no_self_loop(self):
        if self.source_event_id == self.target_event_id:
            raise ValueError("Self-loops not allowed")
        return self


class RelationshipsList(BaseModel):
    relationships: List[Relationship] = Field(default_factory=list)


class RelationshipStrength(BaseModel):
    strength_score: float = Field(..., ge=0.0, le=1.0)
    justification: str


class PaperMetadata(BaseModel):
    title: str = Field(..., description="The title of the research paper")
    summary: str = Field(..., description="A brief summary (2-3 sentences) of the paper's main findings and focus")
