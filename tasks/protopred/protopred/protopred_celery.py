"""Celery task for ProtoPRED API queries."""

import os
import tempfile
import time
import pandas as pd
import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, List
import requests
from workflows.celery_app import celery
from webserver.model.task import Task
from webserver.storage import GCSFileStorage
from webserver.model.file import File
from workflows.utils import (
    emit_status,
    download_gcs_file_to_temp,
    get_redis_connection,
    emit_task_file,
    emit_task_message,
)
from webserver.model.message import MessageSchema

logger = logging.getLogger(__name__)

def query_protopred_api_json(smiles: str, models: str = "model_phys:water_solubility"):
    """
    Query ProtoPRED API using embedded JSON in request body.
    
    Args:
        smiles: SMILES string of the chemical compound
        models: Comma-separated list of models to query
        
    Returns:
        dict: API response as JSON
    """
    url = "https://protopred.protoqsar.com/API/v2/"
    
    # Construct JSON payload
    payload = {
        "account_token": "1JX3LP",
        "account_secret_key": "A8X9641JM",
        "account_user": "OOntox",
        "module": "ProtoPHYSCHEM",
        "input_type": "SMILES_TEXT",
        "input_data": smiles,
        "models_list": models
    }
    
    # Use json= parameter to automatically serialize and set headers
    response = requests.post(url, json=payload, timeout=30)
    
    # Raise exception for HTTP errors
    response.raise_for_status()
    
    return response.json()


def create_llm():
    """Create Vertex AI Gemini LLM instance."""
    from langchain_google_vertexai import ChatVertexAI
    return ChatVertexAI(
        model_name="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=1024,
        project="873471276793",
        location="us-east4",
    )
    
def extract_models_from_query(user_query: str) -> Optional[str]:
    """
    Extract model preferences from user query.
    
    Recognizes common model names and returns comma-separated model list.
    Default: "model_phys:water_solubility"
    
    Returns:
        str: Comma-separated model list, or None if not found
    """
    if not user_query or not user_query.strip():
        return None
    
    query_lower = user_query.lower()
    
    # Common model patterns
    models_map = {
        "water_solubility": "model_phys:water_solubility",
        "solubility": "model_phys:water_solubility",
        "logp": "model_phys:logp",
        "log_p": "model_phys:logp",
        "lipophilicity": "model_phys:logp",
    }
    
    # Try to find model mentions
    for keyword, model_name in models_map.items():
        if keyword in query_lower:
            return model_name
    
    return None


def extract_smiles_from_query(user_query: str) -> List[str]:
    """
    Extract SMILES strings from user query using Vertex AI Gemini.
    
    Uses LLM to intelligently extract SMILES strings from natural language queries.
    Falls back to simple regex if LLM extraction fails.
    
    Args:
        user_query: User query that may contain SMILES strings
        
    Returns:
        List[str]: List of extracted SMILES strings, empty if none found
    """
    if not user_query or not user_query.strip():
        return []
    
    # First, try LLM extraction
    try:
        llm = create_llm()
        
        prompt = f"""Extract all SMILES strings from the following user query for chemical compound property prediction.

SMILES (Simplified Molecular Input Line Entry System) are text representations of chemical structures.
They typically contain letters (C, N, O, etc.), numbers, and special characters like =, -, [, ], (, ), #, @, +, /, \\.

User query: "{user_query}"

Extract ALL valid SMILES strings from the query. Return them as a JSON array of strings.
If no SMILES are found, return an empty array [].

Examples:
- "predict properties for CCO and CCN" -> ["CCO", "CCN"]
- "analyze CC(=O)O" -> ["CC(=O)O"]
- "what are the properties of ethanol (CCO)?" -> ["CCO"]
- "no compounds mentioned" -> []

Return ONLY the JSON array, nothing else:"""

        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Extract JSON array from response
        json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
        if json_match:
            smiles_json = json_match.group(0)
            smiles_list = json.loads(smiles_json)
            # Validate that we got a list of strings
            if isinstance(smiles_list, list):
                # Filter out empty strings and validate basic SMILES structure
                valid_smiles = [
                    s.strip() for s in smiles_list 
                    if isinstance(s, str) and s.strip() and len(s.strip()) > 2
                ]
                if valid_smiles:
                    logger.info(f"LLM extracted {len(valid_smiles)} SMILES from query")
                    return valid_smiles
        
    except Exception as e:
        logger.warning(f"LLM extraction failed, falling back to regex: {str(e)}")
    
    # Fallback to simple regex-based extraction
    try:
        smiles_pattern = r'[A-Za-z0-9@+\-\[\]()=#\\\/]+'
        potential_smiles = re.findall(smiles_pattern, user_query)
        # Filter to likely SMILES (contain C, N, O, etc.)
        smiles_list = [s for s in potential_smiles if any(c in s for c in 'CNO') and len(s) > 3]
        if smiles_list:
            logger.info(f"Regex extracted {len(smiles_list)} SMILES from query")
            return smiles_list
    except Exception as e:
        logger.warning(f"Regex extraction also failed: {str(e)}")
    
    return []


def process_smiles_list(smiles_list: List[str], models: str, task_id: str) -> pd.DataFrame:
    """
    Process a list of SMILES strings through ProtoPRED API.
    
    Args:
        smiles_list: List of SMILES strings
        models: Comma-separated model list
        task_id: Task ID for status updates
        
    Returns:
        pd.DataFrame: Results with SMILES and predictions
    """
    results = []
    
    total = len(smiles_list)
    for idx, smiles in enumerate(smiles_list, 1):
        try:
            emit_status(task_id, f"querying API for SMILES {idx}/{total}")
            response = query_protopred_api_json(smiles, models)
            
            # Extract relevant data from response
            result_row = {
                "SMILES": smiles,
                "status": "success"
            }
            
            # Parse response structure (adjust based on actual API response format)
            if isinstance(response, dict):
                # Flatten response dict into columns
                for key, value in response.items():
                    if isinstance(value, (str, int, float, bool)):
                        result_row[key] = value
                    elif isinstance(value, dict):
                        # Flatten nested dicts with prefix
                        for nested_key, nested_value in value.items():
                            if isinstance(nested_value, (str, int, float, bool)):
                                result_row[f"{key}_{nested_key}"] = nested_value
                    elif isinstance(value, list) and len(value) > 0:
                        # Take first element if list
                        if isinstance(value[0], (str, int, float, bool)):
                            result_row[key] = value[0]
            
            results.append(result_row)
            
        except Exception as e:
            logger.error(f"Error processing SMILES {smiles}: {str(e)}")
            results.append({
                "SMILES": smiles,
                "status": "error",
                "error_message": str(e)
            })
    
    return pd.DataFrame(results)


@celery.task(bind=True, queue='protopred')
def protopred(self, payload):
    """
    Query ProtoPRED API for physical-chemical property predictions.
    
    Input:
    - file_ids: Optional list of file IDs. If provided, expects CSV file with SMILES column
    - user_query: Optional query string. Can specify models to use (e.g., "water solubility", "logP")
    - models: Optional explicit model list (overrides user_query extraction)
      - Default: "model_phys:water_solubility"
    
    Output:
    - CSV file with SMILES and predicted properties
    """
    try:
        start_time = time.time()
        
        # --- Platform connections ---
        r = get_redis_connection()
        task_id = payload.get("task_id")
        user_id = payload.get("user_id")

        if not all([task_id, user_id]):
            raise ValueError(f"Missing required fields. task_id={task_id}, user_id={user_id}")

        # --- Inputs ---
        file_ids = payload.get("file_ids", [])
        user_query = payload.get("user_query", "")

        # Determine models to use
        if user_query:
            extracted_models = extract_models_from_query(user_query)
            models_to_use = extracted_models if extracted_models else "model_phys:water_solubility"
        
        emit_status(task_id, f"using models: {models_to_use}")

        # --- Get SMILES list ---
        smiles_list = []
        
        if file_ids:
            # Process file input
            emit_status(task_id, "fetching file from GCS")
            file_id = file_ids[0]  # Use first file
            file_obj = File.get_file(file_id)
            if not file_obj or not file_obj.filepath:
                raise FileNotFoundError(f"Input file not found for file_id={file_id}")

            # Download and process CSV file
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                input_file = download_gcs_file_to_temp(file_obj.filepath, temp_path)
                
                emit_status(task_id, "reading SMILES from file")
                df_input = pd.read_csv(input_file)
                
                # Look for SMILES column (case-insensitive)
                smiles_col = None
                for col in df_input.columns:
                    if col.lower() in ['smiles', 'smile', 'smi']:
                        smiles_col = col
                        break
                
                if not smiles_col:
                    raise ValueError("No SMILES column found in input file. Expected column named 'SMILES', 'smiles', 'SMILE', or 'smi'")
                
                smiles_list = df_input[smiles_col].dropna().tolist()
                emit_status(task_id, f"found {len(smiles_list)} SMILES in file")
        else:
            # Extract SMILES from user_query using Vertex AI
            if user_query:
                emit_status(task_id, "extracting SMILES from query using AI")
                smiles_list = extract_smiles_from_query(user_query)
            
            if not smiles_list:
                raise ValueError("No SMILES provided. Please provide a CSV file with SMILES column or SMILES in user query.")

        if not smiles_list:
            raise ValueError("No valid SMILES found to process")

        # --- Process SMILES ---
        emit_status(task_id, f"processing {len(smiles_list)} SMILES")
        results_df = process_smiles_list(smiles_list, models_to_use, task_id)

        # --- Generate summary message ---
        emit_status(task_id, "generating summary")
        success_count = len(results_df[results_df['status'] == 'success'])
        error_count = len(results_df[results_df['status'] == 'error'])
        
        summary = f"ProtoPRED prediction completed:\n"
        summary += f"- Processed {len(smiles_list)} SMILES\n"
        summary += f"- Successful: {success_count}\n"
        summary += f"- Errors: {error_count}\n"
        summary += f"- Models used: {models_to_use}\n"
        
        if error_count > 0:
            summary += f"\nNote: {error_count} SMILES failed to process. Check results file for details."
        
        message = MessageSchema(role="assistant", content=summary)
        emit_task_message(task_id, message.model_dump())

        # --- Upload results to GCS ---
        emit_status(task_id, "uploading results to GCS")
        
        temp_csv_path = None
        try:
            # Create temporary CSV file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as temp_csv_file:
                temp_csv_path = temp_csv_file.name
                results_df.to_csv(temp_csv_path, index=False)
            
            # Upload to GCS
            gcs_storage = GCSFileStorage()
            gcs_path = f"tasks/{task_id}/protopred_results.csv"
            gcs_storage.upload_file(temp_csv_path, gcs_path, content_type='text/csv')
            
            # Emit file event
            file_data = {
                "user_id": user_id,
                "filename": "protopred_results.csv",
                "filepath": gcs_path,
                "file_type": "csv",
                "content_type": "text/csv"
            }
            emit_task_file(task_id, file_data)
            
        finally:
            # Clean up temporary file
            if temp_csv_path and os.path.exists(temp_csv_path):
                os.unlink(temp_csv_path)

        # --- Completion ---
        execution_time = time.time() - start_time
        logger.info(f"ProtoPRED task {task_id} completed in {execution_time:.2f} seconds")
        finished_at = Task.mark_finished(task_id)
        emit_status(task_id, "done")
        return {"done": True, "finished_at": finished_at, "execution_time": execution_time}

    except Exception as e:
        # --- Error handling ---
        error_msg = str(e)
        logger.error(f"ProtoPRED task {task_id} failed: {error_msg}", exc_info=True)
        emit_status(task_id, f"error: {error_msg}")
        raise  # Re-raise the exception so Celery knows the task failed

