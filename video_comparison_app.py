import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import math
import re
import time


class VideoComparerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Video Frame Comparer")
        self.master.resizable(True, True)

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

        self._build_ui(master)

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
            return max(1, math.floor(duration / interval) + 1)
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
        for idx, file in enumerate(self.video_files):
            self.executor.submit(self.process_video, idx, file, interval, max_duration)

    def process_video(self, idx, file, interval, max_duration):
        input_path = Path(file)
        out_dir = self.base_dir / f"{idx:02}_{input_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_pattern = out_dir / f"frame_%03d_{input_path.stem}.png"

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "info"]
        if max_duration:
            cmd += ["-t", str(max_duration)]
        cmd += ["-i", str(file), "-vf", f"fps=1/{interval}", str(output_pattern)]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            frame_regex = re.compile(r"frame=\s*(\d+)")
            for line in proc.stdout:
                match = frame_regex.search(line)
                if match:
                    count = int(match.group(1)) + 1
                    self.frame_counts[file] = count
                    self.master.after(0, self.update_progress, file)
            proc.wait()
            self.master.after(0, self.mark_video_complete, file)
        except Exception as e:
            print(f"Error processing {file}: {e}")

    def update_progress(self, file):
        current = self.frame_counts.get(file, 0)
        target = self.frame_targets.get(file, 1)
        percent = min(int((current / target) * 100), 100)
        row_id = self.row_ids[file]

        display_current = min(current, target)
        self.tree.set(row_id, "frames", f"{display_current} / {target}")
        self.tree.set(row_id, "progress", f"{percent}%")

        self.update_global_progress()

    def update_global_progress(self):
        total_done = sum(min(self.frame_counts.get(fp, 0), self.frame_targets.get(fp, 0)) for fp in self.video_files)
        if self.total_expected_frames > 0:
            pct = (total_done / self.total_expected_frames) * 100
            self.progress["value"] = pct

    def mark_video_complete(self, file):
        self.processed_files += 1
        self.status_label.config(
            text=f"Processed {self.processed_files}/{len(self.video_files)}"
        )

        if self.processed_files == len(self.video_files) or self.stop_requested:
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


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = VideoComparerApp(root)
    root.mainloop()