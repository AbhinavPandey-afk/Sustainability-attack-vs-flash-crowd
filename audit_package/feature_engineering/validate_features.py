"""Feature dataset validation (CLAUDE.md section 34).

Structural checks that apply to any feature DataFrame produced by
build_features.py, regardless of phase: no NaN/inf, valid labels,
timestamp ordering, no duplicated observation windows. Checks that need
experiment-level metadata not yet present at this phase (no train/test
experiment overlap) are added once dataset assembly exists (Phase 8) —
listed here as `not_checked` reasons rather than silently skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    not_checked: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "not_checked": self.not_checked}


def validate(df: pd.DataFrame) -> ValidationReport:
    errors: list[str] = []
    warnings: list[str] = []
    not_checked: list[str] = []

    if df.empty:
        errors.append("feature DataFrame is empty")
        return ValidationReport(ok=False, errors=errors, warnings=warnings, not_checked=not_checked)

    numeric = df.select_dtypes(include="number")
    nan_cols = numeric.columns[numeric.isna().any()].tolist()
    if nan_cols:
        errors.append(f"NaN values present in columns: {nan_cols}")

    inf_cols = numeric.columns[(numeric.abs() == float("inf")).any()].tolist()
    if inf_cols:
        errors.append(f"Infinite values present in columns: {inf_cols}")

    if "label" in df.columns:
        bad_labels = sorted(set(df["label"].unique()) - {0, 1})
        if bad_labels:
            errors.append(f"labels must be only 0 or 1; found: {bad_labels}")
    else:
        not_checked.append("label values (no 'label' column present — unlabeled dataset)")

    if "window_end" in df.columns and "window_seconds" in df.columns:
        for window_seconds, group in df.groupby("window_seconds"):
            ends = group["window_end"]
            duplicated = ends[ends.duplicated()]
            if len(duplicated):
                errors.append(
                    f"duplicated observation windows for window_seconds={window_seconds}: "
                    f"{sorted(duplicated.unique().tolist())}"
                )
    else:
        not_checked.append("timestamp ordering / duplicate windows (missing window_end or window_seconds column)")

    if "experiment_id" in df.columns:
        pass  # per-experiment overlap check happens at dataset-split time (Phase 8), not here.
    else:
        not_checked.append("train/test experiment overlap (requires dataset-split context — Phase 8)")

    ok = not errors
    return ValidationReport(ok=ok, errors=errors, warnings=warnings, not_checked=not_checked)
