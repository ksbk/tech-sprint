# Pipeline steps: News -> Script -> TTS -> Subtitles -> Video

ComposeService is the canonical final assembly stage; the legacy `services/video.py`
renderer has been removed. Anchors may supply an optional RenderSpec (e.g. TikTok
vs YouTube) to the Pipeline so ComposeService can apply the appropriate render
profile. Defaults remain unchanged when no RenderSpec is provided.
