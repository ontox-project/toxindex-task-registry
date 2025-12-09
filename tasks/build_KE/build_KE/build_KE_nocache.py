import json
import uuid
import time
import random
import logging
from pathlib import Path
from langchain_google_vertexai import ChatVertexAI
from langchain_community.document_loaders import PyPDFLoader
from build_KE.build_extraction_chains import build_extraction_chains
import dotenv

dotenv.load_dotenv()
logging.getLogger().info("rap.py module loaded")
logger = logging.getLogger(__name__)

def create_llm():
    return ChatVertexAI(
        model_name="gemini-2.5-pro", # Vertex AI model naming convention
        temperature=0.1,
        max_output_tokens=16384,
        project="873471276793",
        location="us-east4",
    )

# Define biological level hierarchy
LEVEL_HIERARCHY = {
    'molecular': 0,
    'cellular': 1,
    'tissue': 2,
    'organ': 3,
    'organism': 4,
    'population': 5
}


def validate_relationship_transition(source_event: dict, target_event: dict) -> tuple[bool, str]:
    """
    Validate that relationship follows biological level progression rules.
    Levels can only stay same or increase (go up hierarchy).
    """
    src_level = source_event['biological_level']
    tgt_level = target_event['biological_level']
    
    src_rank = LEVEL_HIERARCHY.get(src_level, -1)
    tgt_rank = LEVEL_HIERARCHY.get(tgt_level, -1)
    
    if src_rank == -1 or tgt_rank == -1:
        return False, f"Unknown biological level: {src_level} or {tgt_level}"
    
    # Target must be same level or higher
    if tgt_rank < src_rank:
        return False, f"FORBIDDEN backward progression: {src_level} (level {src_rank}) → {tgt_level} (level {tgt_rank})"
    
    # Warn if skipping more than 2 levels (but still allow it)
    if tgt_rank - src_rank > 2:
        return True, f"Large level jump: {src_level} → {tgt_level} (skips {tgt_rank - src_rank - 1} intermediate levels)"
    
    return True, "Valid progression"


def read_pdf_text(pdf_path: Path) -> str:
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    return "\n\n".join([p.page_content for p in pages])[:500_000] if pages else ""


def invoke_with_retry(chain, inputs: dict, max_attempts: int = 3):
    for attempt in range(max_attempts):
        try:
            time.sleep(random.uniform(0.5, 1.5))
            return chain.invoke(inputs)
        except Exception as e:
            if attempt == max_attempts - 1:
                logging.error(f"Failed after {max_attempts} attempts: {e}")
                raise
            logging.warning(f"Attempt {attempt + 1} failed: {e}")
    return None


def process_single_pdf(pdf_path: Path, topic: str) -> dict:
    llm = create_llm()
    chains = build_extraction_chains(llm)

    work_id = pdf_path.stem
    pmid = work_id

    try:
        doc_text = read_pdf_text(pdf_path) # up to 500,000 characters, should we label pdf that is too long?
        if not doc_text.strip():
            logging.warning(f"{work_id}: Empty PDF")
            result = {"path": str(pdf_path), "error": "Empty PDF", "pmid": pmid}
            return result
        
        # Extract paper metadata (title and summary)
        metadata_result = invoke_with_retry(chains['extract_metadata'], {"doc_text": doc_text})
        paper_title = metadata_result.title if metadata_result else "Unknown Title"
        paper_summary = metadata_result.summary if metadata_result else "Summary not available"
        
        # Extract events
        events_result = invoke_with_retry(chains['extract_events'], {"doc_text": doc_text, "topic": topic})
        if not events_result or not events_result.events:
            logging.warning(f"{work_id}: No events extracted")
            result = {"path": str(pdf_path), "error": "No events", "pmid": pmid}
            return result
        
        # Add IDs and PMID
        events = []
        for event in events_result.events:
            event_dict = event.model_dump()
            event_dict["id"] = str(uuid.uuid4())
            event_dict["reference"] = work_id
            event_dict["pmid"] = pmid
            events.append(event_dict)
        
        logging.info(f"{work_id}: Extracted {len(events)} events")
        
        # Extract relationships
        relationships_result = invoke_with_retry(
            chains['extract_relationships'],
            {"doc_text": doc_text, "events_json": json.dumps(events, indent=2)}
        )
        if not relationships_result:
            logging.warning(f"{work_id}: No relationships extracted")
            result = {"path": str(pdf_path), "error": "No relationships", "pmid": pmid}
            return result
        
        logging.info(f"{work_id}: Extracted {len(relationships_result.relationships)} relationships")
        
        # Process and validate relationships
        events_dict = {e["id"]: e for e in events}
        key_events = {}
        relationships = {}
        evidence_records = {}
        invalid_transitions = 0
        
        for rel in relationships_result.relationships:
            src_id, tgt_id = rel.source_event_id, rel.target_event_id
            if src_id not in events_dict or tgt_id not in events_dict:
                continue
            
            # Validate transition
            is_valid, reason = validate_relationship_transition(events_dict[src_id], events_dict[tgt_id])
            if not is_valid:
                invalid_transitions += 1
                logging.warning(
                    f"{work_id}: {reason}: "
                    f"{events_dict[src_id]['name']} ({events_dict[src_id]['biological_level']}) → "
                    f"{events_dict[tgt_id]['name']} ({events_dict[tgt_id]['biological_level']})"
                )
                continue
            
            # Log large jumps but don't filter
            if "Large level jump" in reason:
                logging.info(f"{work_id}: {reason}")
            
            key_events[src_id] = events_dict[src_id]
            key_events[tgt_id] = events_dict[tgt_id]
            
            # Score relationship
            score = invoke_with_retry(
                chains['score_relationship'],
                {
                    "doc_text": doc_text,
                    "source_event": json.dumps(events_dict[src_id], indent=2),
                    "target_event": json.dumps(events_dict[tgt_id], indent=2)
                }
            )
            
            rel_id = str(uuid.uuid4())
            relationships[rel_id] = {
                "relationship_id": rel_id,
                "source_event_id": src_id,
                "target_event_id": tgt_id,
                "relationship_type": "leads_to",
                "evidence_strength": score.strength_score if score else 0.5,
                "evidence_justification": score.justification if score else "",
                "pmid": pmid
            }
            
            evidence_id = str(uuid.uuid4())
            evidence_records[evidence_id] = {
                "evidence_id": evidence_id,
                "relationship_id": rel_id,
                "source_id": f"OPENALEX:{work_id}",
                "reference": work_id,
                "pmid": pmid
            }
        
        if invalid_transitions > 0:
            logging.info(f"{work_id}: Filtered {invalid_transitions} backward transitions")
        
        logging.info(f"{work_id}: Success - {len(key_events)} events, {len(relationships)} valid relationships")
        
        result = {
            "path": str(pdf_path),
            "pmid": pmid,
            "title": paper_title,
            "summary": paper_summary,
            "key_events": list(key_events.values()),
            "relationships": list(relationships.values()),
            "evidence": list(evidence_records.values())
        }
        
        # Cache the result
        return result
        
    except Exception as e:
        logging.error(f"{work_id}: {type(e).__name__} - {str(e)}")
        result = {"path": str(pdf_path), "error": type(e).__name__, "message": str(e), "pmid": pmid}
        return result

