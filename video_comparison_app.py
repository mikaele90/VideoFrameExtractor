import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import shlex
import datetime


class VideoComparerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Video Frame Comparer")
        self.video_files = []
        self.processed_count = 0
        self.total_files = 0
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.ffmpeg_processes = {}
        self.stop_requested = False
        self.row_ids = {}  # Maps file path -> Treeview item ID

        # Main controls
        self.frame = tk.Frame(master)
        self.frame.pack(pady=10)

        self.add_button = tk.Button(self.frame, text="Add Video(s)", command=self.add_files)
        self.add_button.pack(side=tk.LEFT, padx=10)

        self.start_button = tk.Button(self.frame, text="Start", command=self.start_comparison)
        self.start_button.pack(side=tk.LEFT, padx=10)

        self.stop_button = tk.Button(self.frame, text="Stop", command=self.abort_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=10)

        # Interval
        self.interval_label = tk.Label(self.frame, text="Interval (s):")
        self.interval_label.pack(side=tk.LEFT, padx=(20, 5))

        self.interval_var = tk.StringVar(value="5")
        self.interval_entry = tk.Entry(self.frame, textvariable=self.interval_var, width=5)
        self.interval_entry.pack(side=tk.LEFT)

        # Max duration
        self.duration_label = tk.Label(self.frame, text="Max Duration (s):")
        self.duration_label.pack(side=tk.LEFT, padx=(20, 5))

        self.duration_var = tk.StringVar(value="")
        self.duration_entry = tk.Entry(self.frame, textvariable=self.duration_var, width=7)
        self.duration_entry.pack(side=tk.LEFT)

        # Progress bar
        self.progress = ttk.Progressbar(master, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=(10, 0))

        # Treeview table for per-file status
        self.tree = ttk.Treeview(master, columns=("progress", "time", "eta"), show="headings", height=10)
        self.tree.heading("progress", text="Progress")
        self.tree.heading("time", text="Time")
        self.tree.heading("eta", text="ETA")
        self.tree.heading("#1", anchor="w")
        self.tree.column("progress", width=80, anchor="center")
        self.tree.column("time", width=80, anchor="center")
        self.tree.column("eta", width=80, anchor="center")
        self.tree.pack(padx=10, pady=10, fill="both", expand=False)

        self.tree.heading("#0", text="File", anchor="w")

        # Status label
        self.status_label = tk.Label(master, text="Ready")
        self.status_label.pack(pady=(0, 10))

        # Drag-and-drop support
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind("<<Drop>>", self.drop_files)

        master.resizable(False, False)  # Prevent resize flicker

    def add_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Video files", "*.mp4 *.mkv *.mov *.avi *.flv")])
        self.add_to_list(files)

    def drop_files(self, event):
        files = self.master.tk.splitlist(event.data)
        self.add_to_list(files)

    def add_to_list(self, files):
        for f in files:
            if f not in self.video_files and Path(f).suffix.lower() in {'.mp4', '.mkv', '.mov', '.avi', '.flv'}:
                filename = Path(f).name
                row_id = self.tree.insert("", "end", text=filename, values=("", "", ""))
                self.row_ids[f] = row_id
                self.video_files.append(f)

    def get_video_duration(self, video_path):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                 "default=noprint_wrappers=1:nokey=1", str(video_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return float(result.stdout.strip())
        except Exception as e:
            print(f"⚠️ FFprobe failed for {video_path}: {e}")
            return None

    def start_comparison(self):
        if not self.video_files:
            messagebox.showwarning("No Videos", "Please add video files first.")
            return

        try:
            interval_seconds = float(self.interval_var.get().strip())
            if interval_seconds <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Interval", "Please enter a valid interval.")
            return

        duration_seconds = None
        if self.duration_var.get().strip():
            try:
                duration_seconds = float(self.duration_var.get().strip())
                if duration_seconds <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid Duration", "Please enter a positive number.")
                return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.base_dir = Path.cwd() / f"out_{timestamp}"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.progress["maximum"] = 100
        self.progress["value"] = 0
        self.processed_count = 0
        self.total_files = len(self.video_files)

        self.add_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="Processing...")
        self.stop_requested = False
        self.ffmpeg_processes.clear()

        for idx, video in enumerate(self.video_files):
            self.executor.submit(self.process_video, idx, video, interval_seconds, duration_seconds)

    def process_video(self, idx, video, interval_seconds, duration_seconds):
        input_path = Path(video)
        safe_name = input_path.stem.replace(" ", "_")
        out_dir = self.base_dir / f"{idx:02}_{safe_name}"
        out_dir.mkdir(parents=True, exist_ok=True)

        output_pattern = out_dir / f"frame_%03d_{safe_name}.png"

        max_out_time = duration_seconds or self.get_video_duration(video)
        duration_arg = ["-t", str(duration_seconds)] if duration_seconds else []

        ffmpeg_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            *duration_arg,
            "-i", str(video),
            "-vf", f"fps=1/{interval_seconds}",
            "-progress", "pipe:1", "-nostats",
            str(output_pattern)
        ]

        try:
            start_time = time.time()
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.ffmpeg_processes[str(video)] = process

            for line in process.stdout:
                line = line.strip()
                if line.startswith("out_time_ms"):
                    value = line.split("=")[1].strip()
                    current_out_time = self.safe_parse_ms(value) / 1_000_000

                    eta_str = ""
                    time_str = str(datetime.timedelta(seconds=int(current_out_time)))
                    percent = 0

                    if max_out_time:
                        progress = min(current_out_time / max_out_time, 1.0)
                        percent = int(progress * 100)
                        eta_seconds = int((time.time() - start_time) / progress - (time.time() - start_time)) if progress > 0 else 0
                        eta_str = str(datetime.timedelta(seconds=eta_seconds))

                    self.master.after(0, self.update_row_progress, video, percent, time_str, eta_str)

                if "progress=end" in line:
                    break

            process.wait()
        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.master.after(0, self.handle_video_completion)

    def safe_parse_ms(self, value):
        try:
            if value.lower() == "n/a" or not value:
                return 0
            return int(float(value))
        except:
            return 0

    def update_row_progress(self, filepath, percent, time_txt, eta_txt):
        item_id = self.row_ids.get(filepath)
        if item_id:
            self.tree.item(item_id, values=(f"{percent}%", time_txt, eta_txt))

        self.update_overall_progress()

    def update_overall_progress(self):
        values = [
            int(self.tree.item(iid)["values"][0].replace("%", "") or 0)
            for iid in self.tree.get_children()
        ]
        average = sum(values) / len(values) if values else 0
        self.progress["value"] = average

    def handle_video_completion(self):
        self.processed_count += 1
        self.status_label.config(text=f"Processed {self.processed_count}/{self.total_files}")

        if self.processed_count == self.total_files or self.stop_requested:
            self.status_label.config(text="Complete." if not self.stop_requested else "Aborted.")
            self.add_button.config(state=tk.NORMAL)
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

            if not self.stop_requested:
                messagebox.showinfo("Done", f"Frames saved to:\n{self.base_dir}")

            self.video_files.clear()
            self.ffmpeg_processes.clear()

    def abort_processing(self):
        self.stop_requested = True
        self.status_label.config(text="Aborting...")
        self.stop_button.config(state=tk.DISABLED)

        for proc in self.ffmpeg_processes.values():
            if proc.poll() is None:
                proc.terminate()


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = VideoComparerApp(root)
    root.mainloop()