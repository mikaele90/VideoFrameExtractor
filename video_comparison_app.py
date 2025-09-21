import tkinter as tk
from tkinter import filedialog, messagebox
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

        self.frame = tk.Frame(master)
        self.frame.pack(pady=10)

        self.add_button = tk.Button(self.frame, text="Add Video(s)", command=self.add_files)
        self.add_button.pack(side=tk.LEFT, padx=10)

        self.start_button = tk.Button(self.frame, text="Start Comparison", command=self.start_comparison)
        self.start_button.pack(side=tk.LEFT, padx=10)

        self.listbox = tk.Listbox(master, width=80)
        self.listbox.pack(padx=10, pady=10)

        # Enable drag-and-drop
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

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.base_dir = Path.cwd() / f"video_comparison_{timestamp}"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.add_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)

        with ThreadPoolExecutor() as executor:
            futures = []
            for idx, video in enumerate(self.video_files):
                futures.append(executor.submit(self.process_video, idx, video))
            for future in futures:
                future.result()

        self.add_button.config(state=tk.NORMAL)
        self.start_button.config(state=tk.NORMAL)

        messagebox.showinfo("Done", f"Comparison frames saved to:\n{self.base_dir}")

    def process_video(self, idx, video):
        input_path = Path(video)
        safe_name = input_path.stem.replace(" ", "_")
        out_dir = self.base_dir / f"{idx:02}_{safe_name}"
        out_dir.mkdir(parents=True, exist_ok=True)

        output_pattern = out_dir / f"frame_%03d_{safe_name}.png"

        print(f"[{input_path.name}] Starting frame extraction...")

        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", str(video),
            "-vf", "fps=1/300",
            str(output_pattern)
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True)
            print(f"[{input_path.name}] ✅ Frames saved to {out_dir}")
        except subprocess.CalledProcessError as e:
            print(f"[{input_path.name}] ❌ Error: {e}")


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = VideoComparerApp(root)
    root.mainloop()