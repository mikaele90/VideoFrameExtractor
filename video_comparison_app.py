import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
import time
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import math
import re


class VideoComparerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Video Frame Comparer")
        self.video_files = []
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.processed_count = 0
        self.total_files = 0
        self.stop_requested = False

        self.row_ids = {}
        self.frame_counts = {}
        self.total_frame_estimates = {}

        # Frame + buttons
        self.frame = tk.Frame(master)
        self.frame.pack(pady=10, fill="x")

        self.add_button = tk.Button(self.frame, text="Add Video(s)", command=self.add_files)
        self.add_button.pack(side=tk.LEFT, padx=10)

        self.start_button = tk.Button(self.frame, text="Start", command=self.start_comparison)
        self.start_button.pack(side=tk.LEFT, padx=10)

        self.stop_button = tk.Button(self.frame, text="Stop", command=self.abort_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=10)

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

        # Treeview
        self.tree = ttk.Treeview(master, columns=("file", "frames", "progress"), show="headings", height=12)
        self.tree.heading("file", text="File")
        self.tree.heading("frames", text="Frames")
        self.tree.heading("progress", text="Progress")
        self.tree.column("file", width=250, anchor="w")
        self.tree.column("frames", width=100, anchor="center")
        self.tree.column("progress", width=100, anchor="center")
        self.tree.pack(padx=10, pady=10, fill="both", expand=True)

        # Status label
        self.status_label = tk.Label(master, text="Ready")
        self.status_label.pack(pady=(0, 10), padx=10, anchor="w")

        # Drag-and-drop
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind("<<Drop>>", self.drop_files)

        master.resizable(True, True)

    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[
            ("Video files", "*.mp4 *.mkv *.mov *.avi *.flv")
        ])
        self.add_to_list(files)

    def drop_files(self, event):
        files = self.master.tk.splitlist(event.data)
        self.add_to_list(files)

    def add_to_list(self, files):
        for file in files:
            if file not in self.video_files and Path(file).suffix.lower() in {'.mp4', '.mkv', '.mov', '.avi', '.flv'}:
                name = Path(file).name
                row_id = self.tree.insert("", "end", values=(name, "0 / ?", "0%"))
                self.row_ids[file] = row_id
                self.video_files.append(file)

    def get_video_duration(self, path):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return float(result.stdout.strip())
        except Exception as e:
            print(f"ffprobe error: {e}")
            return None

    def estimate_frame_count(self, duration, interval):
        if duration and interval:
            return math.floor(duration / interval) + 1  # include frame at 0s
        return 0

    def start_comparison(self):
        if not self.video_files:
            messagebox.showwarning("No Videos", "Please add videos first.")
            return

        try:
            interval = float(self.interval_var.get().strip())
            if interval <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Interval", "Enter a valid interval (in seconds).")
            return

        duration_seconds = None
        if self.duration_var.get().strip():
            try:
                duration_seconds = float(self.duration_var.get().strip())
                if duration_seconds <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid Duration", "Enter a positive duration.")
                return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.base_dir = Path.cwd() / f"out_{timestamp}"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.progress["maximum"] = 100
        self.progress["value"] = 0
        self.processed_count = 0
        self.total_files = len(self.video_files)
        self.frame_counts.clear()
        self.total_frame_estimates.clear()
        self.stop_requested = False

        self.add_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="Processing...")

        for idx, file in enumerate(self.video_files):
            self.executor.submit(self.process_video, idx, file, interval, duration_seconds)

    def process_video(self, idx, file, interval, max_duration):
        actual_duration = max_duration or self.get_video_duration(file)
        total_frames = self.estimate_frame_count(actual_duration, interval)
        self.total_frame_estimates[file] = total_frames
        self.frame_counts[file] = 0

        input_path = Path(file)
        out_dir = self.base_dir / f"{idx:02}_{input_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)

        output_pattern = out_dir / f"frame_%03d_{input_path.stem}.png"

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "info"
        ]
        if max_duration:
            cmd += ["-t", str(max_duration)]

        cmd += ["-i", str(file), "-vf", f"fps=1/{interval}", str(output_pattern)]

        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            frame_regex = re.compile(r"frame=\s*(\d+)")

            for line in process.stdout:
                if "frame=" in line:
                    match = frame_regex.search(line)
                    if match:
                        frame_num = int(match.group(1)) + 1  # Adjust: FFmpeg frames start at 0
                        self.frame_counts[file] = frame_num
                        self.master.after(0, self.update_row_progress, file)

            process.wait()
            self.master.after(0, self.mark_video_complete, file)

        except Exception as e:
            print(f"Error processing {file}: {e}")

    def update_row_progress(self, file_path):
        row_id = self.row_ids.get(file_path)
        if not row_id:
            return

        current = self.frame_counts.get(file_path, 0)
        total = self.total_frame_estimates.get(file_path, 1)
        percent = min(int((current / total) * 100), 100)

        self.tree.set(row_id, "frames", f"{current} / {total}")
        self.tree.set(row_id, "progress", f"{percent}%")
        self.update_overall_progress()

    def update_overall_progress(self):
        total_weight = sum(self.total_frame_estimates.values())
        weighted_progress = sum(
            min(self.frame_counts.get(path, 0), self.total_frame_estimates.get(path, 0))
            for path in self.video_files
        )

        if total_weight > 0:
            overall = (weighted_progress / total_weight) * 100
            self.progress["value"] = overall

    def mark_video_complete(self, filepath):
        self.processed_count += 1
        self.status_label.config(text=f"Processed {self.processed_count}/{self.total_files}")

        if self.processed_count == self.total_files or self.stop_requested:
            self.status_label.config(text="Done." if not self.stop_requested else "Aborted")
            self.add_button.config(state=tk.NORMAL)
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

            if not self.stop_requested:
                messagebox.showinfo("Done", "All videos processed.")

    def abort_processing(self):
        self.stop_requested = True
        self.status_label.config(text="Aborting...")
        self.stop_button.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = VideoComparerApp(root)
    root.mainloop()