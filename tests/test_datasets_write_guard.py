"""The autouse guard in conftest.py must refuse CSV writes into the real
datasets/ tree. Regression test for a run that left real Dataset A output
behind in datasets/a/repos/ during the test suite."""

import pytest

from collection import csv_adapter, paths


def test_csv_write_into_real_datasets_tree_is_refused():
    target = paths.DATASETS_ROOT / "a" / "repos" / "guard_probe.csv"
    with pytest.raises(AssertionError, match="real datasets path"):
        csv_adapter.get_adapter().append_dicts(target, [{"x": 1}], ["x"])
    assert not target.exists()


def test_csv_write_into_tmp_path_is_allowed(tmp_path):
    target = tmp_path / "ok.csv"
    csv_adapter.get_adapter().append_dicts(target, [{"x": 1}], ["x"])
    assert target.exists()
