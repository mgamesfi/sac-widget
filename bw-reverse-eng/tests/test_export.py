import json
from datetime import datetime, timezone

from extractor.export import ExecutionLog, export_objects, load_snapshot, make_snapshot_dir


def test_make_snapshot_dir_uses_empty_base_dir_as_is(tmp_path):
    base = tmp_path / "snapshot_x"
    result = make_snapshot_dir(base)
    assert result == base
    assert result.exists()


def test_make_snapshot_dir_avoids_overwriting_nonempty_dir(tmp_path):
    base = tmp_path / "snapshot_x"
    base.mkdir()
    (base / "existing.json").write_text("[]")

    result = make_snapshot_dir(base, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))
    assert result != base
    assert result.parent == base
    assert result.name.startswith("snapshot_20260721")


def test_export_objects_writes_one_file_per_type_plus_manifest(tmp_path):
    log = ExecutionLog(started_at=datetime.now(timezone.utc), technical_user="BWREVENG_TECH")
    objects_by_type = {
        "InfoCube": [{"INFOCUBE": "ZSALES"}],
        "DSO": [{"ODSOBJECT": "ZDSO1"}, {"ODSOBJECT": "ZDSO2"}],
    }
    export_objects(objects_by_type, tmp_path, log)

    assert json.loads((tmp_path / "InfoCube.json").read_text()) == [{"INFOCUBE": "ZSALES"}]
    assert len(json.loads((tmp_path / "DSO.json").read_text())) == 2

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["execution"]["counts"] == {"InfoCube": 1, "DSO": 2}
    assert manifest["execution"]["total_objects"] == 3
    assert manifest["execution"]["technical_user"] == "BWREVENG_TECH"


def test_load_snapshot_ignores_manifest_and_log_files(tmp_path):
    log = ExecutionLog(started_at=datetime.now(timezone.utc), technical_user="tech")
    export_objects({"InfoCube": [{"INFOCUBE": "ZSALES"}]}, tmp_path, log)

    loaded = load_snapshot(tmp_path)
    assert loaded == {"InfoCube": [{"INFOCUBE": "ZSALES"}]}
