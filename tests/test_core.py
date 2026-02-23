import pathlib
import sys

import pytest

# Ensure the in-repo package is importable when running pytest from the repo root.
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tasks/protopred"))

from protopred import core


def test_list_models_includes_known_modules():
    models = core.list_models()
    assert "ProtoPHYSCHEM" in models
    assert "ProtoADME" in models


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("logp", "model_phys:log_kow"),
        ("water", "model_phys:water_solubility"),
        ("bbb", "model_dist:blood-brain_barrier"),
    ],
)
def test_alias_resolution(alias, expected):
    assert core._resolve_model(alias) == expected  # noqa: SLF001 (testing internal helper)


def test_mcp_predict_requires_single_input():
    with pytest.raises(ValueError):
        core.mcp_predict(smiles="CCO", batch={"ID_1": {"SMILES": "CCO"}})
