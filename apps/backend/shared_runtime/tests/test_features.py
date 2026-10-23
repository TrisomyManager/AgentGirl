import json

import pytest

from shared_runtime.features import FeatureManager


def test_pending_change_is_persisted_but_current_process_stays_frozen(tmp_path):
    path = tmp_path / "features.json"
    manager = FeatureManager(path, defaults={"voice_layer", "proactive_care"})
    manager.write_enabled([])
    assert manager.is_active("voice_layer")
    assert manager.status()["restart_required"]
    assert not FeatureManager(path).is_active("voice_layer")
    assert manager.is_active("core_orchestrator")


def test_dependencies_unknown_ids_and_write_failure_preserve_configuration(tmp_path, monkeypatch):
    path = tmp_path / "features.json"
    manager = FeatureManager(path)
    manager.write_enabled(["proactive_care"])
    original = path.read_bytes()
    for enabled in (["desktop_context"], ["unknown"]):
        with pytest.raises(ValueError):
            manager.write_enabled(enabled)
        assert path.read_bytes() == original
    monkeypatch.setattr("shared_runtime.features.os.replace", lambda *_: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        manager.write_enabled([])
    assert path.read_bytes() == original
    assert manager.status()["pending_enabled"] == ["proactive_care"]


def test_corrupt_config_never_silently_enables_optional_modules(tmp_path):
    path = tmp_path / "features.json"
    path.write_text(json.dumps({"version": 99, "enabled": ["voice_layer"]}))
    with pytest.raises(ValueError):
        FeatureManager(path)
    assert json.loads(path.read_text())["version"] == 99
