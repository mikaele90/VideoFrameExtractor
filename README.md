# Video Frame Extractor

A GUI tool for extracting frames from video files at fixed intervals.

## Features

- Drag-and-drop or browse for video files
- Configurable extraction interval and max duration
- PNG or WebP (lossless) output with adjustable compression
- Batch processing with concurrent extraction
- Live FFmpeg console output and per-file progress tracking

## Requirements

- FFmpeg (will prompt to browse if not in PATH)

## Installation

### Option 1: Download Executable (Windows)

Download the latest `.exe` from the [Releases](https://github.com/mikaele90/VideoFrameExtractor/releases) page. No Python installation required.

### Option 2: Run from Source

1. Clone the repository

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # Linux/macOS
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python video_comparison_app.py
   ```

## Usage

1. Add videos via drag-and-drop or the "Add Videos" button
2. Set the interval (seconds between frames)
3. Optionally set a max duration
4. Choose output format (PNG or WebP lossless)
5. Click "Start"

Output is saved to `out_<timestamp>/` with subfolders per video.

## Supported Formats

Input: `.mp4`, `.mkv`, `.avi`, `.mov`, `.flv`

## Troubleshooting

- **FFmpeg not found**: Verify with `ffmpeg -version`
- **tkinterdnd2 error on Linux**: Install `python3-tk` (`sudo apt install python3-tk`)