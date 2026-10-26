"""Tests for the GUI-agnostic controller (no Qt required)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from epr_workflow.gui.controller import (
    PreprocessingStore,
    SpectrumView,
    load_spectrum,
    run_batch_processing,
    status_label,
)
from epr_workflow.plot_asc import AscDataError, AscFormatError

HEADER = "     index           Field [G]        Intensity []\n\n"


def asc_text(rows: list[str]) -> str:
    return HEADER + "\n".join(rows) + "\n"


def write_asc(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def make_sample(path: Path, offset: float = 0.0, n: int = 4) -> Path:
    rows = [f"{i + 1} {3280 + i / 10 + offset:.1f} {100 + i:.1f}" for i in range(n)]
    return write_asc(path, asc_text(rows))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# load_spectrum
# --------------------------------------------------------------------------
def test_load_spectrum_returns_view(tmp_path: Path) -> None:
    source = make_sample(tmp_path / "s.ASC")
    view = load_spectrum(source)

    assert isinstance(view, SpectrumView)
    assert view.n_points == 4
    assert view.field_min == 3280.0
    assert view.field_max == 3280.3
    assert view.field_order == "strictly increasing"
    assert view.warnings == []
    assert len(view.data) == 4
    np.testing.assert_array_equal(
        view.data["field_G"].to_numpy(), [3280.0, 3280.1, 3280.2, 3280.3]
    )


def test_load_spectrum_surfaces_warnings(tmp_path: Path) -> None:
    source = write_asc(
        tmp_path / "gap.ASC",
        asc_text(["1 3280 10", "2 3280.1 11", "4 3280.2 12", "5 3280.3 13"]),
    )
    view = load_spectrum(source)

    assert view.n_points == 4
    assert any("not consecutive" in w for w in view.warnings)


def test_load_spectrum_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_spectrum(tmp_path / "nope.ASC")


def test_load_spectrum_raises_on_bad_header(tmp_path: Path) -> None:
    source = write_asc(tmp_path / "bad.ASC", "wrong header\n1 2 3\n")
    with pytest.raises(AscFormatError):
        load_spectrum(source)


def test_load_spectrum_raises_on_non_monotonic(tmp_path: Path) -> None:
    source = write_asc(
        tmp_path / "nonmono.ASC",
        asc_text(["1 3280 10", "2 3280.1 11", "3 3280.0 12", "4 3280.2 13"]),
    )
    with pytest.raises(AscDataError):
        load_spectrum(source)


def test_load_spectrum_does_not_write_outputs(tmp_path: Path) -> None:
    source = make_sample(tmp_path / "s.ASC")
    load_spectrum(source)

    # read-only preview must not create any output files anywhere in tmp_path
    assert list(tmp_path.rglob("*_raw.csv")) == []
    assert list(tmp_path.rglob("*_raw.png")) == []
    assert list(tmp_path.rglob("*_metadata.json")) == []


def test_load_spectrum_does_not_modify_source(tmp_path: Path) -> None:
    source = make_sample(tmp_path / "s.ASC")
    before = sha256(source)
    load_spectrum(source)
    assert sha256(source) == before


# --------------------------------------------------------------------------
# run_batch_processing
# --------------------------------------------------------------------------
def test_batch_processing_success(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "a.ASC")
    make_sample(input_dir / "b.ASC", offset=5.0)

    outcome = run_batch_processing(input_dir, output_dir)

    assert outcome.summary["batch"]["files_succeeded"] == 2
    assert outcome.summary["batch"]["files_failed"] == 0
    assert outcome.summary["batch"]["overall_status"] == "success"
    assert outcome.summary_path == output_dir / "logs" / "batch_summary.json"
    assert outcome.summary_path.exists()
    assert (output_dir / "tables" / "a_raw.csv").exists()


def test_batch_processing_continues_after_failure(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "good.ASC")
    write_asc(input_dir / "broken.ASC", "not an asc\n")

    outcome = run_batch_processing(input_dir, output_dir)

    statuses = {f["source_file"]: f["status"] for f in outcome.summary["files"]}
    assert statuses == {"broken.ASC": "failed", "good.ASC": "success"}
    assert outcome.summary["batch"]["overall_status"] == "partial_failure"
    assert (output_dir / "tables" / "good_raw.csv").exists()


def test_batch_processing_missing_directory(tmp_path: Path) -> None:
    outcome = run_batch_processing(tmp_path / "missing", tmp_path / "out")

    assert outcome.summary["batch"]["files_discovered"] == 0
    assert outcome.summary["batch"]["overall_status"] == "failed"
    assert any("does not exist" in e for e in outcome.summary["batch"]["errors"])


def test_batch_processing_empty_directory(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    outcome = run_batch_processing(input_dir, tmp_path / "out")

    assert outcome.summary["batch"]["files_discovered"] == 0
    assert any("No .ASC files" in e for e in outcome.summary["batch"]["errors"])


def test_batch_processing_refuses_overwrite(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "a.ASC")

    assert run_batch_processing(input_dir, output_dir).summary["batch"]["overall_status"] == "success"
    with pytest.raises(FileExistsError, match="already exists"):
        run_batch_processing(input_dir, output_dir)

    # Explicit overwrite succeeds.
    outcome = run_batch_processing(input_dir, output_dir, overwrite=True)
    assert outcome.summary["batch"]["overall_status"] == "success"


def test_batch_processing_preserves_sources_and_values(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    source = make_sample(input_dir / "keep.ASC")
    before = sha256(source)

    outcome = run_batch_processing(input_dir, output_dir)

    assert sha256(source) == before
    record = outcome.summary["files"][0]
    assert record["source_unchanged"] is True
    assert record["source_sha256_before"] == before
    assert record["source_sha256_after"] == before

    metadata = json.loads(
        (output_dir / "logs" / "keep_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["processing"]["applied_in_this_run"]["smoothing"] is False
    assert metadata["processing"]["applied_in_this_run"]["baseline_correction"] is False
    assert metadata["processing"]["applied_in_this_run"]["normalisation"] is False
    assert metadata["processing"]["applied_in_this_run"]["field_axis_reversal"] is False


def test_batch_processing_non_monotonic_fails_by_default(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    write_asc(
        input_dir / "nm.ASC",
        asc_text(["1 3280 10", "2 3280.1 11", "3 3280.0 12", "4 3280.2 13"]),
    )

    outcome = run_batch_processing(input_dir, output_dir)

    record = outcome.summary["files"][0]
    assert record["status"] == "failed"
    assert "non-monotonic" in record["error"]

    # allow_non_monotonic surfaces a warning instead.
    outcome2 = run_batch_processing(input_dir, output_dir / ".." / "out2",
                                    allow_non_monotonic=True)
    assert outcome2.summary["files"][0]["status"] == "success_with_warnings"


def test_batch_processing_output_name_collision(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "a_b" / "C.ASC")
    make_sample(input_dir / "a" / "b_C.ASC")

    outcome = run_batch_processing(input_dir, output_dir, recursive=True)

    assert outcome.summary["batch"]["files_failed"] == 2
    assert all("collision" in f["error"] for f in outcome.summary["files"])
    assert not (output_dir / "tables" / "a_b_C_raw.csv").exists()


# --------------------------------------------------------------------------
# status_label mapping
# --------------------------------------------------------------------------
def test_status_label_maps_known_statuses() -> None:
    assert status_label("success") == "成功"
    assert status_label("success_with_warnings") == "成功（有警告）"
    assert status_label("failed") == "失败"
    assert status_label("unknown_status") == "unknown_status"
    assert status_label("success", "en") == "Succeeded"


# --------------------------------------------------------------------------
# PreprocessingStore
# --------------------------------------------------------------------------
def test_store_reuses_session_for_unchanged_file(tmp_path: Path) -> None:
    source = make_sample(tmp_path / "s.ASC")
    view = load_spectrum(source)
    store = PreprocessingStore()

    first = store.session_for(view)
    second = store.session_for(view)

    assert first is second
    assert len(store) == 1
    assert first.source_sha256 == view.sha256
    assert view.sha256 != ""


def test_store_replaces_session_when_source_changes(tmp_path: Path) -> None:
    source = make_sample(tmp_path / "s.ASC")
    first_view = load_spectrum(source)
    store = PreprocessingStore()
    first = store.session_for(first_view)

    source.write_text(
        source.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    second_view = load_spectrum(source)
    second = store.session_for(second_view)

    assert second is not first
    assert second.steps == ()
    assert second.source_sha256 == second_view.sha256
    assert second_view.sha256 != first_view.sha256


def test_store_discard_and_clear(tmp_path: Path) -> None:
    source = make_sample(tmp_path / "s.ASC")
    view = load_spectrum(source)
    store = PreprocessingStore()
    store.session_for(view)
    assert len(store) == 1

    store.discard(source)
    assert len(store) == 0

    store.session_for(view)
    store.clear()
    assert len(store) == 0
