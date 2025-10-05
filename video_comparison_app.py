import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import shlex


class VideoComparerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Video Frame Comparer with Drag-and-Drop")
        self.video_files = []
        self.processed_count = 0
        self.total_files = 0
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.ffmpeg_processes = {}
        self.stop_requested = False

        # Main frame
        self.frame = tk.Frame(master)
        self.frame.pack(pady=10)

        self.add_button = tk.Button(self.frame, text="Add Video(s)", command=self.add_files)
        self.add_button.pack(side=tk.LEFT, padx=10)

        self.start_button = tk.Button(self.frame, text="Start Comparison", command=self.start_comparison)
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
        self.progress = ttk.Progressbar(master, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=(10, 0))

        # File list
        self.listbox = tk.Listbox(master, width=80)
        self.listbox.pack(padx=10, pady=10)

        # Status labels
        self.status_label = tk.Label(master, text="Ready")
        self.status_label.pack()

        self.file_progress_var = tk.StringVar(value="")
        self.file_progress_label = tk.Label(master, textvariable=self.file_progress_var)
        self.file_progress_label.pack()

        # Drag and drop
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind("<<Drop>>", self.drop_files)

        drop_label = tk.Label(master, text="Drag and drop video files onto the list above.")
        drop_label.pack()

    def add_files(self):
        files = filedialog.askopenfilenames(
            filetypes=[("Video files", "*.mp4 *.mkv *.mov *.avi *.flv")]
        )
        self.add_to_list(files)

    def drop_files(self, event):
        files = self.master.tk.splitlist(event.data)
        self.add_to_list(files)

    def add_to_list(self, files):
        for f in files:
            if f not in self.video_files and Path(f).suffix.lower() in {'.mp4', '.mkv', '.mov', '.avi', '.flv'}:
                self.video_files.append(f)
                self.listbox.insert(tk.END, f)

    def start_comparison(self):
        if not self.video_files:
            messagebox.showwarning("No Videos", "Please add video files first.")
            return

        # Validate interval
        try:
            interval_seconds = float(self.interval_var.get().strip())
            if interval_seconds <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Interval", "Please enter a valid number of seconds (e.g. 5).")
            return

        # Validate max duration
        duration_seconds = None
        duration_raw = self.duration_var.get().strip()
        if duration_raw:
            try:
                duration_seconds = float(duration_raw)
                if duration_seconds <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid Duration", "Max duration must be in seconds (e.g. 600).")
                return

        # Set up
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.base_dir = Path.cwd() / f"out_{timestamp}"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.progress["maximum"] = len(self.video_files)
        self.progress["value"] = 0
        self.processed_count = 0
        self.total_files = len(self.video_files)

        self.add_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="Processing...")
        self.stop_requested = False
        self.ffmpeg_processes.clear()
        self.file_progress_var.set("")

        # Start all jobs (non-blocking)
        for idx, video in enumerate(self.video_files):
            self.executor.submit(self.process_video, idx, video, interval_seconds, duration_seconds)

    def process_video(self, idx, video, interval_seconds, duration_seconds):
        input_path = Path(video)
        safe_name = input_path.stem.replace(" ", "_")
        out_dir = self.base_dir / f"{idx:02}_{safe_name}"
        out_dir.mkdir(parents=True, exist_ok=True)

        output_pattern = out_dir / f"frame_%03d_{safe_name}.png"

        duration_arg = ["-t", str(duration_seconds)] if duration_seconds else []

        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            *duration_arg,
            "-i", str(video),
            "-vf", f"fps=1/{interval_seconds}",
            "-progress", "pipe:1",
            "-nostats",
            str(output_pattern)
        ]

        try:
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.ffmpeg_processes[str(video)] = process

            max_out_time = duration_seconds if duration_seconds else None

            for line in process.stdout:
                line = line.strip()
                if line.startswith("out_time_ms"):
                    value = line.split("=")[1].strip()
                    ms = self.safe_parse_ms(value)
                    current_out_time = ms / 1_000_000

                    if max_out_time:
                        progress = min(current_out_time / max_out_time, 1.0)
                        percent_str = f"{int(progress * 100)}%"
                        self.master.after(0, self.update_file_progress_label, input_path.name, percent_str)

                if "progress=end" in line:
                    break

            process.wait()

            if not self.stop_requested:
                print(f"[{input_path.name}] ✅ Done.")
        except Exception as e:
            print(f"[{input_path.name}] ❌ Error: {e}")
        finally:
            self.master.after(0, self.update_progress)

    def safe_parse_ms(self, value):
        try:
            if value.lower() == "n/a" or not value:
                return 0
            return int(float(value))
        except Exception:
            return 0

    def update_progress(self):
        self.processed_count += 1
        self.progress["value"] = self.processed_count
        self.status_label.config(text=f"Processed {self.processed_count}/{self.total_files}")

        if self.processed_count == self.total_files or self.stop_requested:
            self.progress["value"] = self.total_files
            self.status_label.config(text="Done." if not self.stop_requested else "Aborted.")
            self.add_button.config(state=tk.NORMAL)
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)

            if not self.stop_requested:
                messagebox.showinfo("Done", f"Frames saved to:\n{self.base_dir}")

            self.video_files.clear()
            self.listbox.delete(0, tk.END)
            self.file_progress_var.set("")

    def update_file_progress_label(self, filename, percent):
        self.file_progress_var.set(f"{filename}: {percent}")

    def abort_processing(self):
        self.stop_requested = True
        self.status_label.config(text="Aborting...")
        self.stop_button.config(state=tk.DISABLED)

        for key, proc in self.ffmpeg_processes.items():
            if proc.poll() is None:
                print(f"Terminating: {key}")
                proc.terminate()

        self.file_progress_var.set("Aborted by user.")


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = VideoComparerApp(root)
    root.mainloop()