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

import pandas as pd
import requests

DEFAULT_BASE_URL = "https://protopred.protoqsar.com/API/v2/"
DEFAULT_MODULE = "ProtoPHYSCHEM"
DEFAULT_MODELS_LIST = "model_phys:water_solubility"

# Model catalog pulled from ProtoPRED_API_ProtoQSAR_v2.pdf (page 2)
MODEL_CATALOG = {
    "ProtoPHYSCHEM": {
        "model_phys": {
            "melting_point": "Melting point",
            "boiling_point": "Boiling point",
            "vapour_pressure": "Vapour pressure",
            "water_solubility": "Water solubility",
            "log_kow": "Partition coefficient (log Kow/log P)",
            "log_d": "Partition coefficient (log D)",
            "surface_tension": "Surface tension",
        }
    },
    "ProtoADME": {
        "model_abs": {
            "bioavailability20": "Bioavailability 20%",
            "bioavailability30": "Bioavailability 30%",
            "caco-2_permeability": "Caco-2 permeability",
            "p-gp_inhibitor": "P-glycoprotein inhibitor",
            "p-gp_substrate": "P-glycoprotein substrate",
            "skin_permeability": "Skin permeability",
            "human_intestinal_absorption": "Human intestinal absorption",
        },
        "model_met": {
            "CYP450_1A2_inhibitor": "CYP450 1A2 inhibitor",
            "CYP450_1A2_substrate": "CYP450 1A2 substrate",
            "CYP450_2C19_inhibitor": "CYP450 2C19 inhibitor",
            "CYP450_2C19_substrate": "CYP450 2C19 substrate",
            "CYP450_2C9_inhibitor": "CYP450 2C9 inhibitor",
            "CYP450_2D6_inhibitor": "CYP450 2D6 inhibitor",
            "CYP450_2D6_substrate": "CYP450 2D6 substrate",
            "CYP450_3A4_inhibitor": "CYP450 3A4 inhibitor",
            "CYP450_3A4_substrate": "CYP450 3A4 substrate",
        },
        "model_dist": {
            "blood-brain_barrier": "Blood-brain barrier penetration",
            "plasma-protein_binding": "Plasma protein binding",
            "volume_of_distribution": "Volume of distribution",
        },
        "model_exc": {
            "half-life": "Half-life",
            "human_liver_microsomal": "Human liver microsomal stability",
            "OATP1B1": "OATP1B1 inhibitor",
            "OATP1B3": "OATP1B3 inhibitor",
            "BSEP": "BSEP inhibitor",
        },
    },
}


def _slug(text: str) -> str:
    return text.lower().replace(" ", "").replace("_", "").replace("-", "")


# Build lookup tables for flexible model resolution
_SHORT_NAME_TO_FQ = {}
for module, props in MODEL_CATALOG.items():
    for prop, models in props.items():
        for name in models.keys():
            fq = f"{prop}:{name}"
            _SHORT_NAME_TO_FQ[_slug(name)] = fq
            _SHORT_NAME_TO_FQ[_slug(f"{prop}:{name}")] = fq

# Common aliases
_ALIASES = {
    "logp": "log_kow",
    "log_p": "log_kow",
    "kow": "log_kow",
    "water": "water_solubility",
    "water_sol": "water_solubility",
    "bbb": "blood-brain_barrier",
    "hia": "human_intestinal_absorption",
    "half_life": "half-life",
}


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
        models_iter: Iterable[str] = [models]
    else:
        models_iter = models

    resolved = []
    for m in models_iter:
        if not m:
            continue
        m_str = str(m).strip()
        if not m_str:
            continue
        resolved.append(_resolve_model(m_str))

    return ",".join(dict.fromkeys(resolved))  # remove dups preserving order


def _base_payload(
    *,
    module: str,
    models_list: Union[str, Iterable[str]],
    output_type: Optional[str],
) -> Dict[str, str]:
    creds = _credentials()
    module_value = module.strip() if module else DEFAULT_MODULE
    models_value = _normalize_models(models_list)
    if not models_value:
        raise ValueError("models_list is required")

    payload: Dict[str, str] = {
        **creds,
        "module": module_value,
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
# Model resolution / discovery helpers
# --------------------------------------------------------------------------- #
def _resolve_model(name: str) -> str:
    """Resolve user-supplied model token to canonical 'model_x:property' form."""
    token = name.strip()
    if not token:
        raise ValueError("Empty model name")

    # Already looks like model_x:foo
    if token.lower().startswith("model_"):
        return token.replace(" ", "")

    # Apply alias mapping then slug match
    slugged = _slug(_ALIASES.get(token, token))
    match = _SHORT_NAME_TO_FQ.get(slugged)
    if not match:
        raise ValueError(f"Unknown model: {name}")
    return match


def list_models(module: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """Return available models grouped by module/property with full names."""
    if module is None:
        return MODEL_CATALOG
    module_norm = module.strip()
    if module_norm not in MODEL_CATALOG:
        raise ValueError(f"Unknown module: {module}")
    return {module_norm: MODEL_CATALOG[module_norm]}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def predict_smiles(
    smiles: str,
    *,
    module: str = DEFAULT_MODULE,
    models_list: Union[str, Iterable[str]] = DEFAULT_MODELS_LIST,
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
    module: str = DEFAULT_MODULE,
    models_list: Union[str, Iterable[str]] = DEFAULT_MODELS_LIST,
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
    module: str = DEFAULT_MODULE,
    models_list: Union[str, Iterable[str]] = DEFAULT_MODELS_LIST,
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
# MCP-friendly wrappers
# --------------------------------------------------------------------------- #
def mcp_list_models(module: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """
    Expose model catalog for MCP agent discovery.

    Returns mapping {module: {property_prefix: {model_name: full_name}}}
    """

    return list_models(module)


def mcp_predict(
    *,
    smiles: Optional[str] = None,
    batch: Optional[Dict[str, Dict[str, str]]] = None,
    file_path: Optional[Union[str, Path]] = None,
    module: str = DEFAULT_MODULE,
    models_list: Union[str, Iterable[str]] = DEFAULT_MODELS_LIST,
    output_type: str = "JSON",
    output_path: Optional[Union[str, Path]] = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 60,
):
    """
    Unified entry point for MCP tools. Only one of smiles/batch/file_path should be set.

    Args mirror the lower-level helpers; models_list accepts flexible names/aliases.
    """

    inputs = [bool(smiles), batch is not None, file_path is not None]
    if sum(inputs) != 1:
        raise ValueError("Provide exactly one smiles-string, a batch dictionary, or file path")

    if smiles:
        return predict_smiles(
            smiles,
            module=module,
            models_list=models_list,
            output_type=output_type,
            output_path=output_path,
            base_url=base_url,
            timeout=timeout,
        )
    if batch is not None:
        return predict_batch_dict(
            batch,
            module=module,
            models_list=models_list,
            output_type=output_type,
            output_path=output_path,
            base_url=base_url,
            timeout=timeout,
        )
    return predict_file(
        file_path,
        module=module,
        models_list=models_list,
        output_type=output_type,
        output_path=output_path,
        base_url=base_url,
        timeout=timeout,
    )


# --------------------------------------------------------------------------- #
# Quick manual test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    result = predict_smiles("CCO", models_list="model_phys:water_solubility")
    print(json.dumps(result, indent=2, ensure_ascii=False))
