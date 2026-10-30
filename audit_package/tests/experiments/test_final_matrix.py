"""Validation tests for experiments/final_matrix.yaml — the final research
experiment matrix manifest produced by the research-methodology design
session (docs/experiment_protocol.md's FINAL EXPERIMENT MATRIX section).

These tests check the manifest's own internal consistency and that every
concrete file it references actually exists on disk — they do NOT run any
experiment, train any model, or validate research conclusions. A manifest
entry describing a NOT_IMPLEMENTED or template concept is expected to
reference non-file placeholders (e.g. "NOT_APPLICABLE") and is exempted
from the file-existence checks accordingly.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "experiments" / "final_matrix.yaml"

VALID_STATUSES = {"IMPLEMENTED", "PARTIALLY_IMPLEMENTED", "NOT_IMPLEMENTED"}
VALID_OBJECTIVES = {"O1", "O2", "O3", "O4", "context_only"}
# Sentinel strings a field may hold instead of a real repo-relative path —
# used by baseline entries (which generate no traffic of their own) and
# the matched-signature template entry (which has no single static config).
NON_PATH_SENTINELS = {"NOT_APPLICABLE", "NOT_YET_CREATED"}


@pytest.fixture(scope="module")
def matrix() -> dict:
    return yaml.safe_load(MATRIX_PATH.read_text())


def test_manifest_file_exists_and_parses():
    assert MATRIX_PATH.is_file()
    data = yaml.safe_load(MATRIX_PATH.read_text())
    assert isinstance(data, dict)


def test_manifest_declares_itself_as_a_design_document_not_a_results_record(matrix):
    """CLAUDE.md non-negotiable principle #3/#4 (no fabricated results):
    this manifest must not silently read as a claim that the matrix has
    been executed."""
    assert matrix["manifest"]["status"] == "DESIGN_FINALIZED_NOT_EXECUTED"
    assert len(matrix["manifest"]["explicit_non_claims"]) >= 1


def test_objectives_and_hypotheses_sections_present(matrix):
    assert set(matrix["objectives"].keys()) == {"O1", "O2", "O3", "O4"}
    for key in ("H1", "H0", "H2"):
        assert key in matrix["hypotheses"]
    assert "current_status" in matrix["hypotheses"]


def test_hypotheses_current_status_does_not_claim_proof(matrix):
    """Guards against exactly the phrasing CLAUDE.md forbids at this
    design stage ("the hypothesis is proven", "successfully distinguished",
    "the classifier achieves X")."""
    status_text = matrix["hypotheses"]["current_status"].lower()
    forbidden_phrases = ["hypothesis is proven", "successfully distinguish", "is proven", "has been proven"]
    for phrase in forbidden_phrases:
        assert phrase not in status_text


def test_repetition_policy_present_with_numeric_targets(matrix):
    policy = matrix["repetition_policy"]
    assert isinstance(policy["minimum_floor_per_condition"], int)
    assert isinstance(policy["target_for_confirmatory_claims_per_condition"], int)
    assert policy["target_for_confirmatory_claims_per_condition"] >= policy["minimum_floor_per_condition"]
    assert "what_the_seed_controls" in policy


def test_every_experiment_entry_has_required_fields(matrix):
    required = {
        "experiment_id", "category", "label", "class_type", "purpose",
        "objective_mapping", "duration_seconds", "repetitions", "seed_strategy",
        "status", "data_status", "expected_evidence",
    }
    for entry in matrix["experiments"]:
        missing = required - set(entry.keys())
        assert not missing, f"{entry.get('experiment_id')} missing fields: {missing}"


def test_every_status_is_a_valid_enum_value(matrix):
    for entry in matrix["experiments"]:
        assert entry["status"] in VALID_STATUSES, f"{entry['experiment_id']}: bad status {entry['status']!r}"


def test_every_objective_mapping_entry_is_a_declared_objective(matrix):
    for entry in matrix["experiments"]:
        for obj in entry["objective_mapping"]:
            assert obj in VALID_OBJECTIVES, f"{entry['experiment_id']}: unknown objective {obj!r}"


def test_experiment_ids_are_unique(matrix):
    ids = [e["experiment_id"] for e in matrix["experiments"]]
    assert len(ids) == len(set(ids)), "duplicate experiment_id in final_matrix.yaml"


def _referenced_paths(entry: dict) -> list[str]:
    """Only treats a field as a real file reference when it is a bare
    repo-relative path (no spaces, no free-text prose) — some entries
    (e.g. the matched-signature template) describe file relationships in
    a prose sentence that happens to MENTION a real path mid-sentence,
    which must not be mistaken for a direct reference."""
    paths = []
    for key in ("scenario_file", "config_file"):
        value = entry.get(key)
        if (
            isinstance(value, str)
            and value not in NON_PATH_SENTINELS
            and " " not in value
            and "/" in value
            and value.endswith((".yaml", ".yml"))
        ):
            paths.append(value)
    return paths


def test_every_referenced_scenario_and_config_file_exists_on_disk(matrix):
    """Every concrete (non-template, non-baseline) entry must point at a
    real file — a manifest that claims IMPLEMENTED status for a config
    that doesn't exist would itself be a fabricated-results violation."""
    checked_any = False
    for entry in matrix["experiments"]:
        for rel_path in _referenced_paths(entry):
            checked_any = True
            full_path = REPO_ROOT / rel_path
            assert full_path.is_file(), f"{entry['experiment_id']}: referenced file does not exist: {rel_path}"
    assert checked_any, "no scenario/config file paths were actually checked — test is not exercising anything"


def test_implemented_entries_with_data_have_a_locatable_config(matrix):
    """Any entry claiming IMPLEMENTED status AND a LIVE_DATA_EXISTS_*
    data_status must have a real config_file — status IMPLEMENTED must
    not be claimed for something that only exists as a plan."""
    for entry in matrix["experiments"]:
        if entry["status"] == "IMPLEMENTED" and str(entry.get("data_status", "")).startswith("LIVE_DATA_EXISTS"):
            config_file = entry.get("config_file")
            assert isinstance(config_file, str) and config_file not in NON_PATH_SENTINELS
            assert (REPO_ROOT / config_file).is_file(), f"{entry['experiment_id']}: config_file missing on disk"


def test_contaminated_entries_are_flagged_with_a_contamination_note(matrix):
    """CLAUDE.md principle #3/#4: an entry marked CONTAMINATED must carry
    an explanation, not just the label."""
    for entry in matrix["experiments"]:
        if entry.get("data_status") == "LIVE_DATA_EXISTS_CONTAMINATED":
            assert entry.get("contamination_note"), f"{entry['experiment_id']}: contaminated but no contamination_note"


def test_calibration_required_entries_are_explicit_about_the_blocker(matrix):
    stealth = next(e for e in matrix["experiments"] if e["experiment_id"] == "EDOS_STEALTH_001")
    assert stealth["status"] == "PARTIALLY_IMPLEMENTED"
    assert "calibration_required" in stealth
    assert stealth["calibration_required"]["blocking"] is True


def test_matched_signature_template_does_not_claim_completed_data(matrix):
    template = next(e for e in matrix["experiments"] if e["experiment_id"] == "MATCHED_SIGNATURE_PAIR_TEMPLATE")
    assert template["data_status"] == "NO_DATA"
    assert template["status"] == "PARTIALLY_IMPLEMENTED"
    assert template["mechanism_status"]["calibration_search_loop"] == "IMPLEMENTED"


def test_all_nine_categories_from_the_task_are_represented(matrix):
    """Phase 2 explicitly lists categories A-I; every one must appear on
    at least one entry (as a category or excluded-with-reason), so the
    matrix can't silently omit a required category."""
    category_prefixes = set()
    for entry in matrix["experiments"]:
        cat = entry["category"]
        cats = cat if isinstance(cat, list) else [cat]
        for c in cats:
            category_prefixes.add(c.split("_")[0])
    expected = {"A", "B", "C", "D", "E", "F", "G", "H", "I"}
    assert expected <= category_prefixes, f"missing categories: {expected - category_prefixes}"


def test_excluded_from_matrix_section_present_and_non_empty(matrix):
    assert len(matrix["excluded_from_matrix"]) >= 1
    for item in matrix["excluded_from_matrix"]:
        assert item.get("reason")
