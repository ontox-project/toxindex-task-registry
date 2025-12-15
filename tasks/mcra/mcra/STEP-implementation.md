# STEP-by-step implementation plan for mcra-core task

1) **Clarify mcra-core artifact and runtime**
   - Identify the exact mcra-core version/JAR download URL (or local path) from https://github.com/rivm-syso/mcra-core releases.
   - Confirm Java runtime version requirement (e.g., Temurin/OpenJDK 17?); note minimum memory/CPU recommendations.
   - Determine mcra-core CLI invocation pattern (main class, arguments, input/output file expectations).
   - Collect sample input/output files for validation.

2) **Scaffold task package**
   - Create `tasks/mcra/mcra/__init__.py` and `tasks/mcra/mcra/script.py`.
   - In `script.py`, stub a `run_mcra_core(...)` function that accepts payload fields (user_query, file_ids, structured params) and returns structured JSON plus optional file paths.
   - Add payload validation, temp directory handling, and logging hooks.

3) **Input handling and file retrieval**
   - Support both file-based inputs (download first file_id via platform helpers `download_gcs_file_to_temp`) and optional text/params.
   - Validate required fields (task_id, user_id, inputs) early; emit clear errors.
   - Normalize/prepare inputs to the format mcra-core expects (e.g., config JSON/XML, data tables).

4) **Invoke mcra-core**
   - Assemble the command to run the mcra-core JAR (e.g., `java -Xmx4g -jar mcra-core.jar --config <cfg> --input <file> --output <dir>`).
   - Run via `subprocess.run` with timeouts and stdout/stderr capture; fail fast on non-zero exit codes.
   - Parse/log mcra-core output; collect generated files (reports, CSV, JSON) from the output directory.

5) **Output handling**
   - Upload generated result files to GCS via `GCSFileStorage` and emit via `emit_task_file`.
   - Build a concise summary (counts, warnings) and emit via `emit_task_message`.
   - Return a structured JSON payload (e.g., `{"done": true, "outputs": [...], "summary": ...}`).

6) **Celery adapter**
   - Implement `tasks/mcra/mcra/mcra_celery.py` with `@celery.task(bind=True, queue="mcra")`.
   - Parse payload, emit status updates, call `run_mcra_core`, handle exceptions with logging and `emit_status`.
   - Create `tasks/mcra/mcra/celery_worker_mcra.py` to register the task and set up logging.

7) **Dependencies and metadata**
   - Add `tasks/mcra/pyproject.toml` listing Python deps (e.g., `pydantic` for validation if used); note Java requirement in README.
   - Ensure `requires-python` aligns with platform (e.g., >=3.9,<3.13).

8) **Documentation**
   - Author `tasks/mcra/README.md` with: overview, inputs/outputs, sample payload, mcra-core version, Java requirement, known limitations.

9) **Deployment assets**
   - Create `tasks/mcra/deployment/Dockerfile.mcra`:
     - Base on `us-docker.pkg.dev/toxindex/toxindex-backend/base:latest` (or `basegpu` if needed).
     - Install required Java version; download/copy mcra-core JAR into the image.
     - Copy task code and `pip install ./mcra/`.
     - Set entrypoint to `celery -A mcra.celery_worker_mcra worker -Q mcra`.
   - Add `tasks/mcra/deployment/deployment_mcra.yaml` with container image, env from backend secrets, queue `mcra`, resource requests sized for mcra-core.

10) **Workflow registration**
    - Append an entry to `sync/default_workflows.json`:
      - `frontend_id`: `mcra`
      - `celery_task`: `mcra`
      - `task_name`: `mcra.mcra_celery.mcra`
      - `queue`: `mcra`
      - Provide title/description/initial_prompt/notes.

11) **Validation**
    - Local dry run: execute `python tasks/mcra/mcra/script.py` (or a small harness) against sample inputs to verify mcra-core invocation and outputs.
    - Start Celery worker locally: `python -m celery -A mcra.celery_worker_mcra worker -Q mcra -l info`; send a sample payload to confirm status/messages/files.

12) **Build and deploy**
    - Build image: `docker build -f tasks/mcra/deployment/Dockerfile.mcra -t mcra:latest .`.
    - Tag/push to registry; apply K8s manifest `deployment_mcra.yaml`.
    - Sync workflows to DB: `cd sync && python seed_workflows.py`.

13) **Post-deploy checks**
    - Verify worker registers task (`Registered tasks` log line), queue binding, and that sample workflow runs end-to-end (status updates + file emission).
    - Capture any mcra-core runtime warnings/errors and document mitigations.
