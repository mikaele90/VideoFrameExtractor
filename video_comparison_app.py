import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor


class VideoComparerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Video Frame Comparer with Drag-and-Drop")
        self.video_files = []
        self.processed_count = 0

        # Main top frame
        self.frame = tk.Frame(master)
        self.frame.pack(pady=10)

        self.add_button = tk.Button(self.frame, text="Add Video(s)", command=self.add_files)
        self.add_button.pack(side=tk.LEFT, padx=10)

        self.start_button = tk.Button(self.frame, text="Start Comparison", command=self.start_comparison)
        self.start_button.pack(side=tk.LEFT, padx=10)

        # Interval input
        self.interval_label = tk.Label(self.frame, text="Interval (s):")
        self.interval_label.pack(side=tk.LEFT, padx=(20, 5))

        self.interval_var = tk.StringVar(value="5")  # Default interval
        self.interval_entry = tk.Entry(self.frame, textvariable=self.interval_var, width=5)
        self.interval_entry.pack(side=tk.LEFT)

        # Duration limit input
        self.duration_label = tk.Label(self.frame, text="Max Duration (s):")
        self.duration_label.pack(side=tk.LEFT, padx=(20, 5))

        self.duration_var = tk.StringVar(value="")  # Optional max duration
        self.duration_entry = tk.Entry(self.frame, textvariable=self.duration_var, width=7)
        self.duration_entry.pack(side=tk.LEFT)

        # Progress bar
        self.progress = ttk.Progressbar(master, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=(10, 0))

        # File list
        self.listbox = tk.Listbox(master, width=80)
        self.listbox.pack(padx=10, pady=10)

        # Status label
        self.status_label = tk.Label(master, text="Ready")
        self.status_label.pack()

        # Drag-and-drop support
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind('<<Drop>>', self.drop_files)

        drop_label = tk.Label(master, text="💡 Drag and drop video files onto the list above.")
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

        # Validate interval input
        try:
            interval_seconds = float(self.interval_var.get().strip())
            if interval_seconds <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Interval", "Please enter a valid number of seconds (e.g. 5).")
            return

        # Optional: Validate max duration
        duration_seconds = None
        duration_raw = self.duration_var.get().strip()
        if duration_raw:
            try:
                duration_seconds = float(duration_raw)
                if duration_seconds <= 0:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Invalid Duration", "Max duration must be in seconds (e.g. 600 for 10 minutes).")
                return

        # Set up output
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.base_dir = Path.cwd() / f"video_comparison_{timestamp}"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # UI states
        self.progress["maximum"] = len(self.video_files)
        self.progress["value"] = 0
        self.processed_count = 0
        self.add_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.status_label.config(text="Processing...")

        # Start threaded work
        with ThreadPoolExecutor() as executor:
            for idx, video in enumerate(self.video_files):
                executor.submit(self.process_video, idx, video, interval_seconds, duration_seconds)

    def process_video(self, idx, video, interval_seconds, duration_seconds):
        input_path = Path(video)
        safe_name = input_path.stem.replace(" ", "_")
        out_dir = self.base_dir / f"{idx:02}_{safe_name}"
        out_dir.mkdir(parents=True, exist_ok=True)

        output_pattern = out_dir / f"frame_%03d_{safe_name}.png"

        print(f"[{input_path.name}] Starting frame extraction...")

        # Construct ffmpeg command
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(video)
        ]

        if duration_seconds:
            ffmpeg_cmd.extend(["-t", str(duration_seconds)])

        ffmpeg_cmd.extend([
            "-vf", f"fps=1/{interval_seconds}",
            str(output_pattern)
        ])

        try:
            subprocess.run(ffmpeg_cmd, check=True)
            print(f"[{input_path.name}] ✅ Frames saved to {out_dir}")
        except subprocess.CalledProcessError as e:
            print(f"[{input_path.name}] ❌ Error: {e}")

        # Update progress safely from thread
        self.master.after(0, self.update_progress)

    def update_progress(self):
        self.processed_count += 1
        self.progress["value"] = self.processed_count
        self.status_label.config(text=f"Processed {self.processed_count}/{len(self.video_files)}")

        if self.processed_count == len(self.video_files):
            self.add_button.config(state=tk.NORMAL)
            self.start_button.config(state=tk.NORMAL)
            self.status_label.config(text="✅ Done!")
            messagebox.showinfo("Done", f"Comparison frames saved to:\n{self.base_dir}")


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = VideoComparerApp(root)
    root.mainloop()