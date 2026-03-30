from pathlib import Path

from emtranscriber.shared import paths


def test_default_base_dir_uses_exe_data_folder_when_frozen(monkeypatch, tmp_path: Path) -> None:
    fake_exe = tmp_path / "PortableApp" / "EMtranscriber.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_text("stub", encoding="utf-8")

    monkeypatch.delenv("EMTRANSCRIBER_HOME", raising=False)
    monkeypatch.setattr(paths, "_is_frozen_app", lambda: True)
    monkeypatch.setattr(paths.sys, "executable", str(fake_exe))

    assert paths._default_base_dir() == fake_exe.parent.resolve() / "data"


def test_default_base_dir_prefers_env_override(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "custom_home"
    override.mkdir(parents=True)

    monkeypatch.setenv("EMTRANSCRIBER_HOME", str(override))
    monkeypatch.setattr(paths, "_is_frozen_app", lambda: True)

    assert paths._default_base_dir() == override.resolve()


def test_get_app_paths_falls_back_to_appdata_for_frozen_permission_error(monkeypatch, tmp_path: Path) -> None:
    portable_base = tmp_path / "portable" / "data"
    appdata_base = tmp_path / "appdata" / "EMtranscriber"

    monkeypatch.delenv("EMTRANSCRIBER_HOME", raising=False)
    monkeypatch.setattr(paths, "_is_frozen_app", lambda: True)
    monkeypatch.setattr(paths, "_default_base_dir", lambda: portable_base)
    monkeypatch.setattr(paths, "_appdata_base_dir", lambda: appdata_base)

    original_ensure = paths.AppPaths.ensure

    def fake_ensure(self):  # noqa: ANN001
        if self.base_dir == portable_base:
            raise PermissionError("no write")
        return original_ensure(self)

    monkeypatch.setattr(paths.AppPaths, "ensure", fake_ensure)

    resolved = paths.get_app_paths()

    assert resolved.base_dir == appdata_base
    assert resolved.db_file == appdata_base / "emtranscriber.db"
