from techsprint.core.workspace import Workspace


def test_workspace_paths(tmp_path):
    ws = Workspace.create(str(tmp_path / ".techsprint"), run_id="abc123")
    assert ws.root.name == "abc123"
    assert ws.script_txt.name == "script.txt"
    assert ws.audio_wav.name == "audio.wav"
    assert ws.subtitles_srt.name == "captions.srt"
    assert ws.output_mp4.name == "final.mp4"
