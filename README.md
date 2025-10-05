# Video Frame Extractor

A desktop GUI application for extracting frames from video files at fixed time intervals. Built with Python and Tkinter, this drag-and-drop-enabled tool allows you to:

- Set a time interval (e.g., capture 1 frame every 5 seconds)
- Optionally limit the extraction to a fixed duration (e.g., only the first 10 minutes → 600 seconds)
- Save output frames in organized folders per file

This tool is designed to be frame-rate agnostic and works well for extracting thumbnails, analyzing video content, or comparing scenes across different videos.

---

## Features

- Drag and drop support for video files
- Configurable frame extraction interval (in seconds)
- Optional maximum duration limit for each video
- Multithreaded: processes multiple files concurrently
- Automatically organizes output frames into per-video folders

---

## Requirements

- Python 3.x
  
- FFmpeg

- Python Packages: `tkinterdnd2`

---

## Installation

1. Install Python 3: https://www.python.org/downloads/
    - Ensure `python` and `pip` are added to your system PATH

2. Install FFmpeg: https://ffmpeg.org/download.html  
   - Ensure the ffmpeg binary is added to your system's PATH environment variable

3. Install Python dependencies:
   ```bash
   pip install tkinterdnd2
   ```

4. Run the application:
   ```bash
   python video_comparison_app.py
   ```

---

## How to Use

1. Launch the application.
2. Drag and drop video files into the list, or use the "Add Video(s)" button to select them manually.
3. Enter:
   - The extraction interval (e.g., `5` for every 5 seconds)
   - Optional maximum duration (e.g., `600` for only the first 10 minutes of each video)
4. Click "Start Comparison" to begin processing.
5. When complete, frame captures will be available in a folder such as:

   ```
   ./out_YYYYMMDD_HHMMSS/
       00_sample-video/
           frame_001_sample-video.png
           frame_002_sample-video.png
       01_other-video/
           frame_001_other-video.png
   ```

---

## Notes

- Supported formats: `.mp4`, `.mkv`, `.avi`, `.mov`, `.flv` (and others supported by FFmpeg)
- Output filenames include the original video name and an indexed frame number
- If no duration is specified, the full video will be processed

---

## Troubleshooting

- **FFmpeg not found?**  
  Make sure `ffmpeg` is installed and accessible. Open a terminal or command prompt and check:
  ```bash
  ffmpeg -version
  ```

- **tkinterdnd2 install error?**  
  On Linux, you may need additional Tk packages:
  ```bash
  sudo apt install python3-tk
  ```

- **Tkinter GUI doesn't open or crashes?**  
  Ensure your Python installation includes tkinter. To test:
  ```bash
  python -m tkinter
  ```