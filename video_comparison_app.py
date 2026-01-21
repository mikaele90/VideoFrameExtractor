import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import math
import re
import time
import threading

VERSION = "0.2.2"


class VideoComparerApp:
    def __init__(self, master):
        self.master = master
        self.master.title(f"Video Frame Extractor v{VERSION}")
        self.master.resizable(True, True)

        # Set window icon
        try:
            icon_path = Path(__file__).parent / "app.ico"
            if icon_path.exists():
                self.master.iconbitmap(str(icon_path))
        except Exception:
            pass

        # Setup
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.video_files = []
        self.row_ids = {}
        self.frame_counts = {}
        self.frame_targets = {}
        self.total_expected_frames = 0
        self.total_extracted_frames = 0
        self.processed_files = 0
        self.stop_requested = False

        # Thread safety and process management
        self.lock = threading.Lock()
        self.active_processes = {}
        self.last_update_time = {}

        self._build_ui(master)

        # Handle window close
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self, master):
        # Top control panel
        self.frame = tk.Frame(master)
        self.frame.pack(pady=10, fill="x")

        self.add_button = tk.Button(self.frame, text="Add Videos", command=self.add_files)
        self.add_button.pack(side=tk.LEFT, padx=5)

        self.start_button = tk.Button(self.frame, text="Start", command=self.start_comparison)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = tk.Button(self.frame, text="Stop", command=self.abort_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.interval_label = tk.Label(self.frame, text="Interval (s):")
        self.interval_label.pack(side=tk.LEFT, padx=(20, 5))

        self.interval_var = tk.StringVar(value="5")
        self.interval_entry = tk.Entry(self.frame, textvariable=self.interval_var, width=5)
        self.interval_entry.pack(side=tk.LEFT)

        self.duration_label = tk.Label(self.frame, text="Max Duration (s):")
        self.duration_label.pack(side=tk.LEFT, padx=(20, 5))

        self.duration_var = tk.StringVar(value="")
        self.duration_entry = tk.Entry(self.frame, textvariable=self.duration_var, width=7)
        self.duration_entry.pack(side=tk.LEFT)

        self.format_label = tk.Label(self.frame, text="Format:")
        self.format_label.pack(side=tk.LEFT, padx=(20, 5))

        self.format_var = tk.StringVar(value="PNG")
        self.format_combo = ttk.Combobox(self.frame, textvariable=self.format_var,
                                          values=["PNG", "WebP (lossless)"], state="readonly", width=12)
        self.format_combo.pack(side=tk.LEFT, padx=(0, 5))

        # Progress bar
        self.progress = ttk.Progressbar(master, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=(10, 0), padx=10, fill="x")

        # Treeview for per-file tracking
        self.tree = ttk.Treeview(master, columns=("file", "frames", "progress"), show="headings", height=12)
        self.tree.heading("file", text="File")
        self.tree.heading("frames", text="Frames")
        self.tree.heading("progress", text="Progress")
        self.tree.column("file", width=300, anchor="w")
        self.tree.column("frames", width=120, anchor="center")
        self.tree.column("progress", width=80, anchor="center")
        self.tree.pack(padx=10, pady=10, fill="both", expand=True)

        # Status label
        self.status_label = tk.Label(master, text="Ready")
        self.status_label.pack(pady=(0, 10), padx=10, anchor="w")

        # Enable drag-and-drop
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind("<<Drop>>", self.drop_files)

    # File selection
    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Videos", "*.mp4 *.mkv *.mov *.avi *.flv")])
        self.add_to_list(files)

    def drop_files(self, event):
        self.add_to_list(self.master.tk.splitlist(event.data))

    def add_to_list(self, files):
        for file in files:
            if file not in self.video_files and Path(file).suffix.lower() in {'.mp4', '.mkv', '.mov', '.avi', '.flv'}:
                name = Path(file).name
                row_id = self.tree.insert("", "end", values=(name, "0 / ?", "0%"))
                self.row_ids[file] = row_id
                self.video_files.append(file)

    # Preprocessing
    def get_video_duration(self, path):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return float(result.stdout.strip())
        except Exception as e:
            print(f"ffprobe error for {path}: {e}")
            return 0

    def estimate_frame_count(self, duration, interval):
        if duration and interval:
            return max(1, math.ceil(duration / interval))
        return 0

    # Processing
    def start_comparison(self):
        if not self.video_files:
            messagebox.showwarning("No Videos", "Add video files to process.")
            return

        # Validate interval
        try:
            interval = float(self.interval_var.get())
            if interval <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Interval", "Provide a positive interval.")
            return

        # Optional max duration
        max_duration = None
        if self.duration_var.get().strip():
            try:
                max_duration = float(self.duration_var.get().strip())
                if max_duration <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid Duration", "Provide a positive max duration.")
                return

        # Reset state
        self.row_ids = {v: self.row_ids[v] for v in self.video_files}
        self.frame_counts.clear()
        self.frame_targets.clear()
        self.total_expected_frames = 0
        self.total_extracted_frames = 0
        self.processed_files = 0
        self.stop_requested = False

        self.status_label.config(text="Scanning...")
        self.add_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress["value"] = 0

        # Estimate all frames to be captured
        self.base_dir = Path.cwd() / f"out_{int(time.time())}"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        for file in self.video_files:
            actual_duration = self.get_video_duration(file)
            effective_duration = min(actual_duration, max_duration) if max_duration else actual_duration
            frames = self.estimate_frame_count(effective_duration, interval)
            self.frame_targets[file] = frames
            self.frame_counts[file] = 0
            self.total_expected_frames += frames

            row_id = self.row_ids[file]
            self.tree.set(row_id, "frames", f"0 / {frames}")
            self.tree.set(row_id, "progress", "0%")

        self.status_label.config(text="Processing...")
        output_format = self.format_var.get()
        for idx, file in enumerate(self.video_files):
            self.executor.submit(self.process_video, idx, file, interval, max_duration, output_format)

    def process_video(self, idx, file, interval, max_duration, output_format):
        input_path = Path(file)
        out_dir = self.base_dir / f"{idx:02}_{input_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Set extension and codec options based on format
        if output_format == "WebP (lossless)":
            ext = "webp"
            codec_opts = ["-lossless", "1", "-compression_level", "4"]
        else:  # PNG
            ext = "png"
            codec_opts = ["-compression_level", "5"]

        output_pattern = out_dir / f"frame_%03d_{input_path.stem}.{ext}"

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "info"]
        if max_duration:
            # Add small buffer to ensure frames at boundary are captured
            cmd += ["-t", str(max_duration + 0.5)]
        cmd += ["-i", str(file), "-vf", f"fps=1/{interval}"] + codec_opts + [str(output_pattern)]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            # Track process for potential abort
            with self.lock:
                self.active_processes[file] = proc

            # Regex to extract actual frame number (not just detect)
            frame_regex = re.compile(r"frame=\s*(\d+)")

            for line in proc.stdout:
                # Check if stop was requested
                if self.stop_requested:
                    proc.terminate()
                    break

                match = frame_regex.search(line)
                if match:
                    # Extract actual frame count from ffmpeg output
                    frame_received = int(match.group(1))

                    with self.lock:
                        self.frame_counts[file] = frame_received

                    # Throttle UI updates (max 10 per second per file)
                    current_time = time.time()
                    if current_time - self.last_update_time.get(file, 0) >= 0.1:
                        self.last_update_time[file] = current_time
                        self.master.after(0, self.update_progress, file)

            proc.wait()

            # Remove from active processes
            with self.lock:
                self.active_processes.pop(file, None)

            # Final UI update to ensure 100% is shown
            self.master.after(0, self.update_progress, file)
            self.master.after(0, self.mark_video_complete, file)
        except Exception as e:
            print(f"Error processing {file}: {e}")
            with self.lock:
                self.active_processes.pop(file, None)

    def update_progress(self, file):
        with self.lock:
            current = self.frame_counts.get(file, 0)
        target = max(self.frame_targets.get(file, 1), 1)  # Prevent division by zero
        percent = min(int((current / target) * 100), 100)
        row_id = self.row_ids.get(file)

        if row_id is None:
            return

        display_current = min(current, target)
        self.tree.set(row_id, "frames", f"{display_current} / {target}")
        self.tree.set(row_id, "progress", f"{percent}%")

        self.update_global_progress()

    def update_global_progress(self):
        with self.lock:
            total_done = sum(min(self.frame_counts.get(fp, 0), self.frame_targets.get(fp, 0)) for fp in self.video_files)
        if self.total_expected_frames > 0:
            pct = (total_done / self.total_expected_frames) * 100
            self.progress["value"] = pct

    def mark_video_complete(self, file):
        with self.lock:
            self.processed_files += 1
            processed = self.processed_files
            total = len(self.video_files)

        self.status_label.config(text=f"Processed {processed}/{total}")

        if processed == total or self.stop_requested:
            self.status_label.config(text="Done." if not self.stop_requested else "Aborted")
            self.add_button.config(state=tk.NORMAL)
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            if not self.stop_requested:
                messagebox.showinfo("Finished", "All videos have been processed.")

    def abort_processing(self):
        self.stop_requested = True
        self.status_label.config(text="Aborting...")
        self.stop_button.config(state=tk.DISABLED)

        # Terminate all active ffmpeg processes
        with self.lock:
            for proc in self.active_processes.values():
                try:
                    proc.terminate()
                except Exception:
                    pass
            self.active_processes.clear()

    def on_close(self):
        """Clean up resources when window is closed."""
        self.stop_requested = True

        # Terminate any running processes
        with self.lock:
            for proc in self.active_processes.values():
                try:
                    proc.terminate()
                except Exception:
                    pass

        # Shutdown thread pool
        self.executor.shutdown(wait=False)
        self.master.destroy()


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = VideoComparerApp(root)
    root.mainloop()