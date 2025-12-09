# ToxIndex Task Registry

A centralized repository for managing and deploying Celery-based computational tasks for the ToxIndex platform. This registry contains task definitions, deployment configurations, and workflow metadata.

## Overview

This repository serves as the single source of truth for:
- **Task Definitions**: Python packages implementing Celery tasks
- **Deployment Configs**: Docker images and Kubernetes deployments
- **Workflow Registry**: Metadata for available workflows in the web interface

Tasks are designed to be:
- **Input Flexible**: Accept user queries (text), file uploads, or structured data
- **Output Standardized**: Return files (CSV, JSON) or structured JSON responses
- **Platform Integrated**: Emit status updates, messages, and file events to the platform

---

## Repository Structure

```
toxindex-task-registry/
├── sync/                          # Workflow registration system
│   ├── default_workflows.json    # Workflow metadata (frontend + backend config)
│   ├── seed_workflows.py         # Script to sync workflows to database
│   ├── datastore.py              # Database operations
│   └── pyproject.toml             # Sync tool dependencies
│
└── tasks/                         # Task packages
    ├── affinity/                  # Example: Binding affinity calculation
    │   ├── affinity/             # Python package
    │   │   ├── __init__.py
    │   │   ├── affinity_celery.py      # Main Celery task
    │   │   └── celery_worker_affinity.py # Worker setup
    │   ├── deployment/           # Deployment configs
    │   │   ├── Dockerfile.affinity
    │   │   ├── deployment_affinity.yaml
    │   │   └── hpa_affinity.yaml
    │   ├── pyproject.toml        # Package dependencies
    │   └── README.md             # Task-specific documentation
    │
    └── protopred/                 # Example: ProtoPRED API integration
        ├── protopred/            # Python package
        │   ├── __init__.py
        │   ├── protopred_celery.py
        │   └── celery_worker_protopred.py
        ├── deployment/
        │   ├── Dockerfile.protopred
        │   └── deployment_protopred.yaml
        ├── original_script/      # Original standalone script (reference)
        │   └── query_protopred_api_json.py
        ├── pyproject.toml
        └── README.md
```

### Task Package Structure

Each task package must follow this structure:

```
taskname/
├── taskname/                     # Python package (same name as task)
│   ├── __init__.py              # Package initialization
│   ├── taskname_celery.py       # Main Celery task implementation
│   └── celery_worker_taskname.py # Celery worker setup
├── deployment/                   # Deployment configurations
│   ├── Dockerfile.taskname       # Docker image definition
│   └── deployment_taskname.yaml # Kubernetes deployment
├── pyproject.toml                # Python package dependencies
└── README.md                     # Task documentation
```

**Minimum Required Structure** (for task builders):
```
taskname/
├── taskname/
│   ├── __init__.py
│   └── script.py                # Core logic (can be converted to Celery later)
├── pyproject.toml
└── README.md
```

---

## Task Implementation Guide

### Step 1: Create Task Package Structure

1. Create a new directory under `tasks/` with your task name
2. Create the Python package directory (same name)
3. Add `__init__.py` and your core script

**Example:**
```bash
mkdir -p tasks/mytask/mytask
touch tasks/mytask/mytask/__init__.py
touch tasks/mytask/mytask/script.py
```

### Step 2: Implement Core Logic

Your script should accept flexible inputs and produce standardized outputs.

**Input Options:**
- `user_query`: String containing natural language or structured data
- `file_ids`: List of file IDs (GCS references) to download and process
- Structured parameters: Explicit configuration values

**Output Options:**
- Files: CSV, JSON, or other formats (uploaded to GCS)
- Structured JSON: Direct response data
- Status updates: Real-time progress messages

**Example Script** (`tasks/mytask/mytask/script.py`):
```python
def mytask_function(user_query: str = None, file_path: str = None):
    """
    Core task logic.
    
    Args:
        user_query: Optional text input
        file_path: Optional file path to process
        
    Returns:
        dict: Results or file path
    """
    # Your logic here
    if file_path:
        # Process file
        results = process_file(file_path)
    elif user_query:
        # Process query
        results = process_query(user_query)
    else:
        raise ValueError("No input provided")
    
    return {"results": results}
```

See these complete examples:
- **API Integration**: [`query_protopred_api_json.py`](tasks/protopred/original_script/query_protopred_api_json.py) - Simple API query with SMILES input
- **File Processing**: [`a01_build_events.py`](tasks/build_KE/original_script/a01_build_events.py) - PDF processing with file input

### Step 3: Convert to Celery Task (Optional, You can let admin handle this and following steps)

Once the core logic is working, convert it to a Celery task format.

#### 3.1 Rename Task and Queue

In your Celery task file (`taskname_celery.py`):

```python
from workflows.celery_app import celery

@celery.task(bind=True, queue='taskname')  # Change 'taskname' to your task name
def taskname(self, payload):  # Change function name to match
    """Your task description."""
    pass
```

#### 3.2 Wire Your Logic

Replace placeholder logic with your actual function:

```python
@celery.task(bind=True, queue='taskname')
def taskname(self, payload):
    """
    Your task description.
    
    Input:
    - user_query: Optional query string
    - file_ids: Optional list of file IDs
    - [other parameters]
    
    Output:
    - Files or structured JSON
    """
    try:
        # Extract task metadata
        task_id = payload.get("task_id")
        user_id = payload.get("user_id")
        user_query = payload.get("user_query", "")
        file_ids = payload.get("file_ids", [])
        
        if not all([task_id, user_id]):
            raise ValueError(f"Missing required fields: task_id={task_id}, user_id={user_id}")
        
        # Emit status updates
        emit_status(task_id, "starting task")
        
        # Handle file inputs
        if file_ids:
            from webserver.model.file import File
            from workflows.utils import download_gcs_file_to_temp
            import tempfile
            from pathlib import Path
            
            file_obj = File.get_file(file_ids[0])
            if not file_obj or not file_obj.filepath:
                raise FileNotFoundError(f"File not found: {file_ids[0]}")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                local_file = download_gcs_file_to_temp(file_obj.filepath, temp_path)
                
                # Process file
                results = mytask_function(file_path=str(local_file))
        else:
            # Process query
            results = mytask_function(user_query=user_query)
        
        # Emit output (see Step 3.3)
        
        # Mark as finished
        from webserver.model.task import Task
        finished_at = Task.mark_finished(task_id)
        emit_status(task_id, "done")
        return {"done": True, "finished_at": finished_at}
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Task {task_id} failed: {error_msg}", exc_info=True)
        emit_status(task_id, f"error: {error_msg}")
        raise
```

#### 3.3 Emit Output to User

Use the provided helper functions to communicate with the platform:

**Status Updates:**
```python
from workflows.utils import emit_status

emit_status(task_id, "processing...")
emit_status(task_id, "step 1 of 3")
```

**Chat Messages:**
```python
from workflows.utils import emit_task_message
from webserver.model.message import MessageSchema

summary = "Task completed successfully!\n- Processed 10 items\n- Results ready"
message = MessageSchema(role="assistant", content=summary)
emit_task_message(task_id, message.model_dump())
```

**File Output:**
```python
from workflows.utils import emit_task_file
from webserver.storage import GCSFileStorage
import tempfile
import os

# Create output file
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    temp_path = f.name
    results_df.to_csv(temp_path, index=False)

try:
    # Upload to GCS
    gcs_storage = GCSFileStorage()
    gcs_path = f"tasks/{task_id}/results.csv"
    gcs_storage.upload_file(temp_path, gcs_path, content_type='text/csv')
    
    # Emit file event
    file_data = {
        "user_id": user_id,
        "filename": "results.csv",
        "filepath": gcs_path,
        "file_type": "csv",
        "content_type": "text/csv"
    }
    emit_task_file(task_id, file_data)
finally:
    # Clean up
    if os.path.exists(temp_path):
        os.unlink(temp_path)
```

#### 3.4 Create Celery Worker

Create `celery_worker_taskname.py`:

```python
"""Celery worker setup for taskname workflow."""

import os
import logging
from webserver.logging_utils import setup_logging, log_service_startup, get_logger
from workflows.celery_app import celery

# Import your task to register it
import taskname.taskname_celery  # noqa: F401

def setup_celery_worker():
    """Setup logging and startup for celery worker."""
    setup_logging("celery-worker-taskname", log_level=logging.INFO)
    logger = get_logger("celery-worker-taskname")
    log_service_startup("celery-worker-taskname")
    logger.info(f"Registered tasks: {list(celery.tasks.keys())}")

if __name__ == '__main__':
    setup_celery_worker()
```

### Step 4: Add Dependencies

Create `pyproject.toml`:

```toml
[project]
name = "taskname"
version = "0.1.0"
description = "Description of your task"
requires-python = ">=3.9,<3.13"
dependencies = [
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    # Add your dependencies here
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["taskname"]
```

### Step 5: Create Deployment Configs

#### Dockerfile

Create `deployment/Dockerfile.taskname`:

```dockerfile
# Use shared base image
FROM us-docker.pkg.dev/toxindex/toxindex-backend/base:latest

# Copy task files
COPY taskname/taskname/ /app/taskname/taskname/
COPY taskname/pyproject.toml /app/taskname/pyproject.toml
COPY taskname/README.md /app/taskname/README.md

USER root
RUN pip install ./taskname/

USER app

# Entrypoint: Celery worker
CMD ["python", "-m", "celery", "-A", "taskname.celery_worker_taskname", "worker", "--loglevel=info", "-Q", "taskname"]
```

**For GPU tasks**, use `basegpu:latest` instead:
```dockerfile
FROM us-docker.pkg.dev/toxindex/toxindex-backend/basegpu:latest
```

#### Kubernetes Deployment

Create `deployment/deployment_taskname.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: celery-worker-taskname
  namespace: toxindex-app
spec:
  replicas: 1
  selector:
    matchLabels:
      app: celery-worker-taskname
  template:
    metadata:
      labels:
        app: celery-worker-taskname
    spec:
      serviceAccountName: toxindex-app-sa
      containers:
      - name: celery-worker-taskname
        image: us-docker.pkg.dev/toxindex/toxindex-backend/taskname:latest
        command: ["python", "-m", "celery", "-A", "taskname.celery_worker_taskname", "worker", "--loglevel=info", "-Q", "taskname"]
        envFrom:
        - secretRef:
            name: backend-secrets
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
```

### Step 6: Register Workflow

Add your workflow to `sync/default_workflows.json`:

```json
{
  "workflow_id": 12,
  "frontend_id": "taskname",
  "title": "Task Name",
  "label": "Task Label",
  "description": "User-facing description of what the task does",
  "initial_prompt": "Example prompt shown in UI",
  "celery_task": "taskname",
  "task_name": "taskname.taskname_celery.taskname",
  "queue": "taskname",
  "notes": "Additional notes for maintainers"
}
```

**Field Descriptions:**
- `workflow_id`: Unique integer ID
- `frontend_id`: Identifier used by frontend (kebab-case)
- `title`: Display title in UI
- `label`: Short label for UI
- `description`: User-facing description
- `initial_prompt`: Example prompt shown in chat
- `celery_task`: Logical workflow key (used by router)
- `task_name`: Full dotted path to Celery task function
- `queue`: Celery queue name (must match `@celery.task(queue='...')`)
- `notes`: Internal notes (ignored by code)

### Step 7: Sync Workflows to Database

Run the sync script to register workflows:

```bash
cd sync
python seed_workflows.py
```

This reads `default_workflows.json` and inserts/updates workflows in the database.

---

## Examples

### Example 1: Simple API Integration (ProtoPRED)

See `tasks/protopred/` for a complete example:
- Extracts SMILES from user queries using LLM
- Queries external API
- Processes file inputs (CSV with SMILES)
- Returns CSV results

**Key Features:**
- LLM-based input extraction
- File handling (CSV input/output)
- Status updates and summary messages

### Example 2: Complex Computational Task (Affinity)

See `tasks/affinity/` for a GPU-accelerated task:
- Processes PDB complex files
- Parallel processing with Celery chords
- Multiple calculation methods
- Ground truth comparison
- Comprehensive reporting

**Key Features:**
- GPU acceleration (OpenMM with CUDA)
- Parallel subtasks with aggregation
- Complex input validation
- Multi-method comparison

---

## Best Practices

### Input Handling

1. **Support Multiple Input Types:**
   - Text queries (with LLM extraction if needed)
   - File uploads (CSV, JSON, etc.)
   - Structured parameters

2. **Validate Early:**
   - Check required fields immediately
   - Provide clear error messages
   - Use `emit_status()` to inform users of validation issues

### Output Handling

1. **Always Emit Status Updates:**
   ```python
   emit_status(task_id, "starting...")
   emit_status(task_id, "processing step 1/3")
   emit_status(task_id, "uploading results...")
   ```

2. **Provide Summary Messages:**
   - Include key statistics
   - Highlight important results
   - Mention any errors or warnings

3. **Clean Up Temporary Files:**
   ```python
   try:
       # Process and upload
   finally:
       if os.path.exists(temp_path):
           os.unlink(temp_path)
   ```

### Error Handling

1. **Always Use Try/Except:**
   ```python
   try:
       # Task logic
   except Exception as e:
       error_msg = str(e)
       logger.error(f"Task failed: {error_msg}", exc_info=True)
       emit_status(task_id, f"error: {error_msg}")
       raise  # Re-raise so Celery knows task failed
   ```

2. **Log Thoroughly:**
   - Use structured logging
   - Include task_id in log messages
   - Log exceptions with `exc_info=True`

### Performance

1. **Use Parallel Processing:**
   - Celery groups for independent tasks
   - Celery chords for aggregation
   - See `affinity` task for example

2. **Optimize Resource Usage:**
   - Request appropriate CPU/memory
   - Use GPU when beneficial
   - Clean up resources promptly

### Testing

1. **Test Core Logic Separately:**
   - Test your `script.py` independently
   - Mock external dependencies
   - Validate input/output formats

2. **Test Celery Integration:**
   - Run worker locally
   - Test with sample payloads
   - Verify status updates and outputs

---

## Deployment

### Building Docker Images

```bash
# Build image
docker build -f tasks/taskname/deployment/Dockerfile.taskname -t taskname:latest .

# Tag for GCR
docker tag taskname:latest us-docker.pkg.dev/toxindex/toxindex-backend/taskname:latest

# Push to GCR
docker push us-docker.pkg.dev/toxindex/toxindex-backend/taskname:latest
```

### Deploying to Kubernetes

```bash
# Apply deployment
kubectl apply -f tasks/taskname/deployment/deployment_taskname.yaml

# Check status
kubectl get pods -n toxindex-app -l app=celery-worker-taskname
```

### Updating Workflows

After adding/updating workflows in `default_workflows.json`:

```bash
cd sync
python seed_workflows.py
```

---

## Troubleshooting

### Task Not Appearing in UI

1. Check `default_workflows.json` has correct entry
2. Run `seed_workflows.py` to sync to database
3. Verify `celery_task` matches task name
4. Check `task_name` is correct dotted path

### Task Not Executing

1. Verify worker is running: `kubectl get pods -n toxindex-app`
2. Check queue name matches: `@celery.task(queue='...')`
3. Verify task is registered: Check worker logs for "Registered tasks"
4. Check Redis/Celery broker connection

### File Upload Issues

1. Verify GCS credentials in secrets
2. Check file permissions
3. Verify `GCSFileStorage().upload_file()` succeeds
4. Check `emit_task_file()` is called with correct data

### Status Updates Not Showing

1. Verify `emit_status()` is called
2. Check Redis connection
3. Verify task_id is correct
4. Check frontend WebSocket connection

---

## Contributing

1. Create a new task package following the structure above
2. Implement core logic and test independently
3. Convert to Celery task format
4. Add deployment configs
5. Update `default_workflows.json`
6. Document in task-specific README
7. Submit for review

---

## License

See LICENSE file in project root.
