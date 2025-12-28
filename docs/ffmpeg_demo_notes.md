# ffmpeg and demo notes by OS

## Windows
- Install ffmpeg via [winget](https://learn.microsoft.com/en-us/windows/package-manager/winget/) (`winget install Gyan.FFmpeg`) or [Chocolatey](https://chocolatey.org/) (`choco install ffmpeg`).
- After installation, open a new terminal so `ffmpeg.exe` is available on `PATH`.
- Run the demo with `techsprint demo` or `techsprint make --demo`. If ffmpeg is not detected, run `techsprint doctor` for install hints.

## Linux
- Install ffmpeg with your package manager (e.g., `sudo apt-get install ffmpeg` on Debian/Ubuntu).
- Confirm `ffmpeg` and `ffprobe` are on `PATH` via `ffmpeg -version` and `ffprobe -version`.
- Run the demo with `techsprint demo` or `techsprint make --demo`. If binaries are missing, `techsprint doctor` will print Linux-specific guidance.
