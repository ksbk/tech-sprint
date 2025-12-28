from __future__ import annotations

from techsprint.config.settings import Settings
from techsprint.utils import doctor


def test_doctor_all_ok(monkeypatch, capsys) -> None:
    def fake_run(cmd):  # noqa: ANN001
        if cmd[0] == "ffmpeg":
            return 0, "ffmpeg version x"
        if cmd[0] == "ffprobe":
            return 0, "ffprobe version y"
        return 0, ""

    monkeypatch.setattr(doctor, "_run_cmd", fake_run)
    monkeypatch.setattr(doctor, "_check_writable", lambda _: True)
    monkeypatch.setattr(doctor, "_module_available", lambda _: True)
    monkeypatch.setattr(doctor, "_get_version", lambda: "0.0.0")

    settings = Settings()
    code = doctor.run_doctor(settings)
    out = capsys.readouterr().out

    assert code == 0
    assert "ffmpeg version x" in out


def test_doctor_missing_ffmpeg(monkeypatch, capsys) -> None:
    def fake_run(cmd):  # noqa: ANN001
        if cmd[0] == "ffmpeg":
            return 1, ""
        if cmd[0] == "ffprobe":
            return 0, "ffprobe version y"
        return 0, ""

    monkeypatch.setattr(doctor, "_run_cmd", fake_run)
    monkeypatch.setattr(doctor, "_check_writable", lambda _: True)
    monkeypatch.setattr(doctor, "_module_available", lambda _: True)
    monkeypatch.setattr(doctor, "_get_version", lambda: "0.0.0")

    settings = Settings()
    code = doctor.run_doctor(settings)
    assert code == 1
    hint = doctor._ffmpeg_hint()  # noqa: SLF001
    assert hint in capsys.readouterr().out


def test_doctor_missing_edge_tts(monkeypatch) -> None:
    def fake_run(cmd):  # noqa: ANN001
        return 0, "ok"

    def fake_module_available(name):  # noqa: ANN001
        return name != "edge_tts"

    monkeypatch.setattr(doctor, "_run_cmd", fake_run)
    monkeypatch.setattr(doctor, "_check_writable", lambda _: True)
    monkeypatch.setattr(doctor, "_module_available", fake_module_available)
    monkeypatch.setattr(doctor, "_get_version", lambda: "0.0.0")

    settings = Settings()
    code = doctor.run_doctor(settings)
    assert code == 0
