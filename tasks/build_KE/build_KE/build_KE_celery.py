import os
import tempfile
import pandas as pd
from workflows.celery_app import celery
from webserver.model.message import MessageSchema
from webserver.model.task import Task
from webserver.storage import GCSFileStorage
from webserver.model.file import File
from pathlib import Path
from workflows.utils import (
    emit_status, 
    download_gcs_file_to_temp, 
    get_redis_connection, 
    emit_task_file, 
    emit_task_message
)
from build_KE.build_KE_nocache import process_single_pdf, create_llm
from build_KE.generate_report import generate_report


def extract_topic_from_query(user_query: str) -> str:
    """Extract the topic from user query. Returns just the topic name, e.g., 'endocrine disruption'."""
    llm = create_llm()
    prompt = f"""Extract only the topic name from the following query. Return ONLY the topic name, nothing else, no explanation.

Query: {user_query}

Topic:"""
    response = llm.invoke(prompt)
    topic = response.content if hasattr(response, 'content') else str(response)
    # Clean up the response - take only the first line and strip whitespace
    topic = topic.strip().split('\n')[0].strip()
    # Remove quotes if present
    topic = topic.strip('"').strip("'")
    return topic

   

@celery.task(bind=True, queue='build_KE')
def build_KE(self, payload):
    """emits progress messages and uploads files to GCS."""
    try:
        # --- Platform connections ---
        r = get_redis_connection()
        task_id = payload.get("task_id")
        user_id = payload.get("user_id")

        if not all([task_id, user_id]):
            raise ValueError(f"Missing required fields. task_id={task_id}, user_id={user_id}")

        # --- Inputs ---
        # Currently supported inputs are file_id and user_query.
        # - file_id: reference to an uploaded file stored in GCS
        # - user_query: free-form text input from the user
        file_id = payload.get("file_id")
        user_query = payload.get("user_query")

        # --- File handling (optional) ---
        # If your task requires a file, fetch its metadata and download it to a temp directory.
        # Skip this block or guard it if your tool is text-only.
        emit_status(task_id, "fetching file from GCS")
        # Get file info from DB
        file_obj = File.get_file(file_id)
        if not file_obj or not file_obj.filepath:
            raise FileNotFoundError(f"Input file not found for file_id={file_id}")

        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Download input file from GCS
            input_file = download_gcs_file_to_temp(file_obj.filepath, temp_path)
            emit_status(task_id, "starting")

            # --- Core tool execution ---
            emit_status(task_id, "running")
            topic = extract_topic_from_query(user_query)
            result_dict = process_single_pdf(input_file, topic)
            
            # Check for errors in result
            if 'error' in result_dict:
                error_msg = f"Error processing PDF: {result_dict.get('error', 'Unknown error')}"
                if 'message' in result_dict:
                    error_msg += f" - {result_dict['message']}"
                raise ValueError(error_msg)
            
            emit_status(task_id, "sending message")

            # --- Emit chat message ---
            # Generate comprehensive report
            report = generate_report(result_dict, topic)
            message = MessageSchema(role="assistant", content=report)
            emit_task_message(task_id, message.model_dump())
            
            # Extract filenames before temp directory is cleaned up
            KE_filename = f"KE_{input_file.stem}.csv"
            Relationships_filename = f"Relationships_{input_file.stem}.csv"
            Evidence_filename = f"Evidence_{input_file.stem}.csv"
        
        # --- Create and upload a csv result file ---
        emit_status(task_id, "uploading files to GCS")
        
        # Convert lists to DataFrames and write to CSV
        temp_ke_csv_path = None
        temp_relationships_csv_path = None
        temp_evidence_csv_path = None
        
        try:
            # Create temporary files and write CSV data
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as temp_ke_csv_file:
                temp_ke_csv_path = temp_ke_csv_file.name
                df_ke = pd.DataFrame(result_dict['key_events'])
                df_ke.to_csv(temp_ke_csv_path, index=False)
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as temp_relationships_csv_file:
                temp_relationships_csv_path = temp_relationships_csv_file.name
                df_relationships = pd.DataFrame(result_dict['relationships'])
                df_relationships.to_csv(temp_relationships_csv_path, index=False)
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as temp_evidence_csv_file:
                temp_evidence_csv_path = temp_evidence_csv_file.name
                df_evidence = pd.DataFrame(result_dict['evidence'])
                df_evidence.to_csv(temp_evidence_csv_path, index=False)
            
            # Upload to GCS
            gcs_storage = GCSFileStorage()  
            
            # Upload csv file
            KE_gcs_path = f"tasks/{task_id}/{KE_filename}"
            gcs_storage.upload_file(temp_ke_csv_path, KE_gcs_path, content_type='text/csv')
            Relationships_gcs_path = f"tasks/{task_id}/{Relationships_filename}"
            gcs_storage.upload_file(temp_relationships_csv_path, Relationships_gcs_path, content_type='text/csv')
            Evidence_gcs_path = f"tasks/{task_id}/{Evidence_filename}"
            gcs_storage.upload_file(temp_evidence_csv_path, Evidence_gcs_path, content_type='text/csv')
            emit_status(task_id, "files uploaded") # send status to frontend

            # Emit csv file event
            KE_file_data = {
                "user_id": user_id,
                "filename": KE_filename,
                "filepath": KE_gcs_path,
                "file_type": "csv",
                "content_type": "text/csv"
            }
            Relationships_file_data = {
                "user_id": user_id,
                "filename": Relationships_filename,
                "filepath": Relationships_gcs_path,
                "file_type": "csv",
                "content_type": "text/csv"
            }
            Evidence_file_data = {
                "user_id": user_id,
                "filename": Evidence_filename,
                "filepath": Evidence_gcs_path,
                "file_type": "csv",
                "content_type": "text/csv"
            }
            emit_task_file(task_id, KE_file_data) # send file to frontend
            emit_task_file(task_id, Relationships_file_data) # send file to frontend
            emit_task_file(task_id, Evidence_file_data) # send file to frontend
        finally:
            # Clean up temporary files
            if temp_ke_csv_path and os.path.exists(temp_ke_csv_path):
                os.unlink(temp_ke_csv_path)
            if temp_relationships_csv_path and os.path.exists(temp_relationships_csv_path):
                os.unlink(temp_relationships_csv_path)
            if temp_evidence_csv_path and os.path.exists(temp_evidence_csv_path):
                os.unlink(temp_evidence_csv_path)
        # --- Completion ---
        finished_at = Task.mark_finished(task_id)
        emit_status(task_id, "done")
        return {"done": True, "finished_at": finished_at}

    except Exception as e:
        # --- Error handling ---
        emit_status(task_id, "error")
        raise  # Re-raise the exception so Celery knows the task failed 