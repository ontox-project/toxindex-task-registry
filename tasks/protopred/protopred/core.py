"""
Standalone ProtoPRED API client.

Designed for direct (non-Celery) use inside the toxindex workflow so we can start
with core logic and layer orchestration later. Mirrors the request shapes shown in
ProtoPRED_API_ProtoQSAR_v2.pdf: single SMILES, embedded JSON batch, and file upload.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Union

import requests
import pandas as pd

DEFAULT_BASE_URL = "https://protopred.protoqsar.com/API/v2/"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _credentials() -> Dict[str, str]:
    """
    Resolve credentials from env vars, falling back to the demo values provided
    in the API PDF. Override via:
      PROTOPRED_ACCOUNT_TOKEN
      PROTOPRED_ACCOUNT_SECRET_KEY
      PROTOPRED_ACCOUNT_USER
    """
    return {
        "account_token": os.getenv("PROTOPRED_ACCOUNT_TOKEN", "1JX3LP"),
        "account_secret_key": os.getenv("PROTOPRED_ACCOUNT_SECRET_KEY", "A8X9641JM"),
        "account_user": os.getenv("PROTOPRED_ACCOUNT_USER", "OOntox"),
    }


def _normalize_models(models: Union[str, Iterable[str]]) -> str:
    """Return the comma-separated models_list string accepted by the API."""
    if isinstance(models, str):
        return models.strip()
    return ",".join(m.strip() for m in models if m and str(m).strip())


def _base_payload(
    *,
    module: str,
    models_list: Union[str, Iterable[str]],
    output_type: Optional[str],
) -> Dict[str, str]:
    creds = _credentials()
    models_value = _normalize_models(models_list)
    if not models_value:
        raise ValueError("models_list is required")

    payload: Dict[str, str] = {
        **creds,
        "module": module,
        "models_list": models_value,
    }
    if output_type:
        payload["output_type"] = output_type
    return payload


def _post(
    base_url: str,
    payload: Mapping,
    *,
    files: Optional[Dict[str, object]] = None,
    timeout: int,
    expect_excel: bool = False,
    output_path: Optional[Union[str, Path]] = None,
):
    response = requests.post(
        base_url,
        json=payload if files is None else None,
        data=payload if files is not None else None,
        files=files,
        timeout=timeout,
    )
    response.raise_for_status()

    if expect_excel:
        content = response.content
        if output_path:
            out = Path(output_path)
            out.write_bytes(content)
            return {"output_path": str(out), "bytes_written": len(content)}
        return {"content": content}

    return response.json()


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def predict_smiles(
    smiles: str,
    *,
    module: str = "ProtoPHYSCHEM",
    models_list: Union[str, Iterable[str]] = "model_phys:water_solubility",
    output_type: str = "JSON",
    output_path: Optional[Union[str, Path]] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 60,
) -> Mapping:
    """Single-SMILES prediction using SMILES_TEXT mode."""
    payload = _base_payload(module=module, models_list=models_list, output_type=output_type)
    payload.update({"input_type": "SMILES_TEXT", "input_data": smiles})
    expect_excel = str(output_type).upper() == "XLSX"
    return _post(base_url, payload, timeout=timeout, expect_excel=expect_excel, output_path=output_path)


def predict_batch_dict(
    molecules: Dict[str, Dict[str, str]],
    *,
    module: str = "ProtoPHYSCHEM",
    models_list: Union[str, Iterable[str]] = "model_phys:water_solubility",
    output_type: str = "JSON",
    output_path: Optional[Union[str, Path]] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 60,
) -> Mapping:
    """
    Batch prediction with an in-memory dictionary (embedded JSON mode).
    Expected shape: {\"ID_1\": {\"SMILES\": \"CCO\", ...}, ...}
    """
    payload = _base_payload(module=module, models_list=models_list, output_type=output_type)
    payload.update({"input_type": "SMILES_FILE", "input_data": molecules})
    expect_excel = str(output_type).upper() == "XLSX"
    return _post(base_url, payload, timeout=timeout, expect_excel=expect_excel, output_path=output_path)


def predict_file(
    file_path: Union[str, Path],
    *,
    module: str = "ProtoPHYSCHEM",
    models_list: Union[str, Iterable[str]] = "model_phys:water_solubility",
    output_type: str = "JSON",
    output_path: Optional[Union[str, Path]] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 60,
) -> Mapping:
    """
    Batch prediction from an Excel (.xlsx) or JSON file (file upload mode).
    The file must contain a SMILES column/field as described in the API PDF.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"input file not found: {path}")

    payload = _base_payload(module=module, models_list=models_list, output_type=output_type)
    payload.update({"input_type": "SMILES_FILE"})

    _validate_input_file(path)

    with path.open("rb") as fh:
        files = {"input_data": fh}
        expect_excel = str(output_type).upper() == "XLSX"
        return _post(base_url, payload, files=files, timeout=timeout, expect_excel=expect_excel, output_path=output_path)


# --------------------------------------------------------------------------- #
# Validators
# --------------------------------------------------------------------------- #
def _validate_input_file(path: Path) -> None:
    """
    Light validation to catch obvious format issues before hitting the API.
    - XLSX: must contain a column named SMILES/smi/smile (case-insensitive)
    - JSON: must be a dict whose values contain a SMILES key
    """
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, nrows=5)
        lower_cols = [c.lower() for c in df.columns]
        if not any(c in {"smiles", "smi", "smile"} for c in lower_cols):
            raise ValueError("Excel file must contain a SMILES column (SMILES/smi/smile)")
    elif suffix == ".json":
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not data:
            raise ValueError("JSON file must be a non-empty object mapping IDs to entries")
        sample = next(iter(data.values()))
        if not isinstance(sample, dict) or "SMILES" not in sample and "smiles" not in sample:
            raise ValueError("Each JSON entry must include a SMILES field")
    else:
        raise ValueError("Unsupported file type. Use .xlsx or .json")


# --------------------------------------------------------------------------- #
# Quick manual test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    result = predict_smiles("CCO", models_list="model_phys:water_solubility")
    print(json.dumps(result, indent=2, ensure_ascii=False))
