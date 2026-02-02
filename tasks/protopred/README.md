## Package Structure

```
protopred/
├── protopred/
│   ├── protopred_celery.py      # Main Celery task implementation
│   └── celery_worker_protopred.py  # Celery worker setup
├── pyproject.toml               # Project dependencies
├── Dockerfile.protopred         # Docker image definition
└── README.md                    # This file
```

## Core logic (non‑Celery)

Everything lives in `protopred/core.py`:

- `predict_smiles(smiles, *, module="ProtoPHYSCHEM", models_list="model_phys:water_solubility", output_type="JSON"| "XLSX")`
- `predict_batch_dict(molecules_dict, *, module, models_list, output_type)`
- `predict_file(file_path, *, module, models_list, output_type)` for `.xlsx` or `.json` uploads (light validation on SMILES column/field).
- Model resolution helpers:
  - `list_models(module=None)` returns the full catalog grouped by module/property.
  - Models accept flexible names/aliases (`logp`, `water`, `model_phys:water_solubility`, etc.) and normalize to canonical `model_<prop>:<name>`.

Defaults: `DEFAULT_MODULE="ProtoPHYSCHEM"`, `DEFAULT_MODELS_LIST="model_phys:water_solubility"`, `DEFAULT_BASE_URL="https://protopred.protoqsar.com/API/v2/"`. Credentials are read from env (`PROTOPRED_ACCOUNT_TOKEN`, `PROTOPRED_ACCOUNT_SECRET_KEY`, `PROTOPRED_ACCOUNT_USER`) with demo defaults from the API PDF.

### MCP wrapper for ToxIndex agents

The MCP-friendly surface is just a thin layer on top of the core functions:

- `mcp_list_models(module=None)` → same as `list_models`; agents can discover available models/properties to build UI choices.
- `mcp_predict(..., smiles=None, batch=None, file_path=None, module=DEFAULT_MODULE, models_list=DEFAULT_MODELS_LIST, output_type="JSON", output_path=None, base_url=DEFAULT_BASE_URL, timeout=60)` → unified entrypoint. Exactly one of `smiles`, `batch` (dict), or `file_path` must be provided. Internally dispatches to `predict_smiles`, `predict_batch_dict`, or `predict_file`.

Design goals:
- Single discovery call (`mcp_list_models`) and single execution call (`mcp_predict`) for agent tool schemas.
- Flexible model selection with aliases and deduplication.
- Output type switchable between JSON and XLSX (if `output_path` is set, XLSX is streamed to disk).

### Quick examples (Python)

```python
from protopred import core

# Discover models
print(core.list_models())                      # full catalog
print(core.list_models("ProtoADME"))           # filter by module

# Single SMILES
res = core.predict_smiles("CCO", models_list="logp,water")   # aliases resolve automatically
print(res)

# Batch dict (embedded JSON)
batch = {"ID_1": {"SMILES": "CCO"}, "ID_2": {"SMILES": "CCN"}}
res = core.predict_batch_dict(batch, models_list="model_met:CYP450_3A4_inhibitor")

# File upload (xlsx/json) -> Excel output
res = core.predict_file("data.xlsx", models_list=["log_kow", "melting_point"], output_type="XLSX", output_path="out.xlsx")

# MCP unified
res = core.mcp_predict(smiles="CCO", models_list="logp")
```

### Notes
- The demo credentials in the PDF are baked in as fallbacks; override with env vars in production.
- `_validate_input_file` ensures Excel has a SMILES column or JSON has SMILES fields before calling the API.
- Model aliases include common shorthand (`logp`, `water`, `bbb`, `hia`, `half_life`, etc.); add more in `MODEL_CATALOG` / `_ALIASES` if needed.

### Available models (from ProtoPRED_API_ProtoQSAR_v2.pdf)

**Module ProtoPHYSCHEM** (prefix `model_phys:`)
- `melting_point` — Melting point
- `boiling_point` — Boiling point
- `vapour_pressure` — Vapour pressure
- `water_solubility` — Water solubility
- `log_kow` — Partition coefficient (log Kow/log P)
- `log_d` — Partition coefficient (log D)
- `surface_tension` — Surface tension

**Module ProtoADME — Absorption** (prefix `model_abs:`)
- `bioavailability20` — Bioavailability 20%
- `bioavailability30` — Bioavailability 30%
- `caco-2_permeability` — Caco-2 permeability
- `p-gp_inhibitor` — P-glycoprotein inhibitor
- `p-gp_substrate` — P-glycoprotein substrate
- `skin_permeability` — Skin permeability
- `human_intestinal_absorption` — Human intestinal absorption

**Module ProtoADME — Metabolism** (prefix `model_met:`)
- `CYP450_1A2_inhibitor` — CYP450 1A2 inhibitor
- `CYP450_1A2_substrate` — CYP450 1A2 substrate
- `CYP450_2C19_inhibitor` — CYP450 2C19 inhibitor
- `CYP450_2C19_substrate` — CYP450 2C19 substrate
- `CYP450_2C9_inhibitor` — CYP450 2C9 inhibitor
- `CYP450_2D6_inhibitor` — CYP450 2D6 inhibitor
- `CYP450_2D6_substrate` — CYP450 2D6 substrate
- `CYP450_3A4_inhibitor` — CYP450 3A4 inhibitor
- `CYP450_3A4_substrate` — CYP450 3A4 substrate

**Module ProtoADME — Distribution** (prefix `model_dist:`)
- `blood-brain_barrier` — Blood-brain barrier penetration
- `plasma-protein_binding` — Plasma protein binding
- `volume_of_distribution` — Volume of distribution

**Module ProtoADME — Excretion** (prefix `model_exc:`)
- `half-life` — Half-life
- `human_liver_microsomal` — Human liver microsomal stability
- `OATP1B1` — OATP1B1 inhibitor
- `OATP1B3` — OATP1B3 inhibitor
- `BSEP` — BSEP inhibitor
