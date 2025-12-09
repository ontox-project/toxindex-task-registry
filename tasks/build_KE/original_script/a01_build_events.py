"""
Extract chemical-agnostic key events and relationships from PDFs.

Example script demonstrating file-based task with LLM extraction.
"""

import os
import json
import uuid
from pathlib import Path
from typing import Optional, Dict, List
from enum import Enum

import pandas as pd
from pydantic import BaseModel, Field
from langchain.prompts import ChatPromptTemplate
from langchain_google_vertexai import ChatVertexAI
from langchain_community.document_loaders import PyPDFLoader


# ============================================================================
# Data Models
# ============================================================================

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


class KeyEventsList(BaseModel):
    events: List[KeyEvent] = Field(default_factory=list)


class Relationship(BaseModel):
    source_event_id: str
    target_event_id: str


class RelationshipsList(BaseModel):
    relationships: List[Relationship] = Field(default_factory=list)


class RelationshipStrength(BaseModel):
    strength_score: float = Field(..., ge=0.0, le=1.0)
    justification: str


# ============================================================================
# LLM Setup
# ============================================================================

def create_llm():
    """Create Vertex AI Gemini LLM instance."""
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us-central1")
    
    return ChatVertexAI(
        model_name="gemini-2.5-pro",
        temperature=0.1,
        max_output_tokens=16384,
        project=project_id,
        location=location,
    )


def build_extraction_chains(llm):
    """Build LLM chains for event and relationship extraction."""
    extract_events_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Extract CHEMICAL-AGNOSTIC key events from article related to {topic}.\n\n"
            "Use format: '[Direction] of [Entity] in [Location]'\n"
            "Examples: 'Activation of aryl hydrocarbon receptor', "
            "'Increased CYP1A1 expression in hepatocytes'\n\n"
            "Output JSON only."
        )),
        ("human", "Article:\n{doc_text}\n\nExtract chemical-agnostic key events for {topic}.")
    ])
    
    extract_relationships_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Identify 'leads_to' relationships between key events.\n"
            "Relationships can ONLY go from one biological level to SAME or HIGHER level.\n"
            "Level hierarchy: molecular < cellular < tissue < organ < organism < population\n\n"
            "Output JSON only."
        )),
        ("human", "Article:\n{doc_text}\n\nEvents:\n{events_json}\n\nExtract relationships.")
    ])
    
    score_relationship_prompt = ChatPromptTemplate.from_messages([
        ("system", "Score evidence strength for causal relationship (0-1). Output JSON only."),
        ("human", "Article:\n{doc_text}\n\nUpstream:\n{source_event}\n\nDownstream:\n{target_event}")
    ])
    
    return {
        'extract_events': extract_events_prompt | llm.with_structured_output(KeyEventsList),
        'extract_relationships': extract_relationships_prompt | llm.with_structured_output(RelationshipsList),
        'score_relationship': score_relationship_prompt | llm.with_structured_output(RelationshipStrength)
    }


# ============================================================================
# PDF Processing
# ============================================================================

def read_pdf_text(pdf_path: Path) -> str:
    """Extract text from PDF file."""
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    return "\n\n".join([p.page_content for p in pages])[:500_000] if pages else ""


LEVEL_HIERARCHY = {
    'molecular': 0,
    'cellular': 1,
    'tissue': 2,
    'organ': 3,
    'organism': 4,
    'population': 5
}


def validate_relationship_transition(source_event: dict, target_event: dict) -> tuple[bool, str]:
    """Validate that relationship follows biological level progression rules."""
    src_level = source_event['biological_level']
    tgt_level = target_event['biological_level']
    
    src_rank = LEVEL_HIERARCHY.get(src_level, -1)
    tgt_rank = LEVEL_HIERARCHY.get(tgt_level, -1)
    
    if src_rank == -1 or tgt_rank == -1:
        return False, f"Unknown biological level: {src_level} or {tgt_level}"
    
    if tgt_rank < src_rank:
        return False, f"FORBIDDEN backward progression: {src_level} → {tgt_level}"
    
    return True, "Valid progression"


def process_single_pdf(pdf_path: Path, topic: str, chains: dict) -> dict:
    """Process a single PDF and extract events/relationships."""
    work_id = pdf_path.stem
    
    try:
        # Read PDF text
        doc_text = read_pdf_text(pdf_path)
        if not doc_text.strip():
            return {"path": str(pdf_path), "error": "Empty PDF"}
        
        # Extract events
        events_result = chains['extract_events'].invoke({"doc_text": doc_text, "topic": topic})
        if not events_result or not events_result.events:
            return {"path": str(pdf_path), "error": "No events extracted"}
        
        # Add IDs to events
        events = []
        for event in events_result.events:
            event_dict = event.model_dump()
            event_dict["id"] = str(uuid.uuid4())
            event_dict["reference"] = work_id
            events.append(event_dict)
        
        # Extract relationships
        relationships_result = chains['extract_relationships'].invoke({
            "doc_text": doc_text,
            "events_json": json.dumps(events, indent=2)
        })
        if not relationships_result:
            return {"path": str(pdf_path), "error": "No relationships extracted"}
        
        # Process and validate relationships
        events_dict = {e["id"]: e for e in events}
        key_events = {}
        relationships = []
        evidence_records = []
        
        for rel in relationships_result.relationships:
            src_id, tgt_id = rel.source_event_id, rel.target_event_id
            if src_id not in events_dict or tgt_id not in events_dict:
                continue
            
            # Validate transition
            is_valid, reason = validate_relationship_transition(events_dict[src_id], events_dict[tgt_id])
            if not is_valid:
                continue
            
            key_events[src_id] = events_dict[src_id]
            key_events[tgt_id] = events_dict[tgt_id]
            
            # Score relationship
            score = chains['score_relationship'].invoke({
                "doc_text": doc_text,
                "source_event": json.dumps(events_dict[src_id], indent=2),
                "target_event": json.dumps(events_dict[tgt_id], indent=2)
            })
            
            rel_id = str(uuid.uuid4())
            relationships.append({
                "relationship_id": rel_id,
                "source_event_id": src_id,
                "target_event_id": tgt_id,
                "relationship_type": "leads_to",
                "evidence_strength": score.strength_score if score else 0.5,
                "evidence_justification": score.justification if score else "",
            })
            
            evidence_records.append({
                "evidence_id": str(uuid.uuid4()),
                "relationship_id": rel_id,
                "source_id": f"OPENALEX:{work_id}",
                "reference": work_id,
            })
        
        return {
            "path": str(pdf_path),
            "key_events": list(key_events.values()),
            "relationships": relationships,
            "evidence": evidence_records
        }
        
    except Exception as e:
        return {"path": str(pdf_path), "error": type(e).__name__, "message": str(e)}


# ============================================================================
# Main Function
# ============================================================================

def build_events(user_query: str = None, file_path: str = None) -> Dict:
    """
    Extract key events from PDF files.
    
    Args:
        user_query: Topic/query string (e.g., "endocrine disruption")
        file_path: Path to PDF file or directory of PDFs
        
    Returns:
        dict: Results with extracted events, relationships, and evidence
    """
    if not file_path:
        raise ValueError("file_path is required")
    
    pdf_path = Path(file_path)
    topic = user_query or "general"
    
    # Setup LLM and chains
    llm = create_llm()
    chains = build_extraction_chains(llm)
    
    # Process single file or directory
    if pdf_path.is_file():
        result = process_single_pdf(pdf_path, topic, chains)
        return {
            "events": result.get("key_events", []),
            "relationships": result.get("relationships", []),
            "evidence": result.get("evidence", []),
            "status": "success" if "error" not in result else "error"
        }
    
    elif pdf_path.is_dir():
        pdf_files = list(pdf_path.glob("*.pdf"))
        all_events = []
        all_relationships = []
        all_evidence = []
        
        for pdf_file in pdf_files:
            result = process_single_pdf(pdf_file, topic, chains)
            if "error" not in result:
                all_events.extend(result.get("key_events", []))
                all_relationships.extend(result.get("relationships", []))
                all_evidence.extend(result.get("evidence", []))
        
        return {
            "events": all_events,
            "relationships": all_relationships,
            "evidence": all_evidence,
            "status": "success"
        }
    
    else:
        raise ValueError(f"File not found: {file_path}")


# Example usage
if __name__ == "__main__":
    result = build_events(
        user_query="endocrine disruption",
        file_path="path/to/document.pdf"
    )
    
    with open("output.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"Extracted {len(result['events'])} events, {len(result['relationships'])} relationships")
