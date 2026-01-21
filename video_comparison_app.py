import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinterdnd2 import DND_FILES, TkinterDnD
import subprocess
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import math
import re
import time
import threading

VERSION = "0.4.0"


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

        # Per-file status and console output
        self.file_status = {}       # file -> status string
        self.file_output = {}       # file -> list of output lines (last N lines)
        self.file_out_dirs = {}     # file -> output directory path
        self.console_tabs = {}      # file -> (tab_frame, text_widget)
        self.max_console_lines = 100  # Max lines to keep per file
        self.base_dir = None        # Base output directory for current run

        self._build_ui(master)

        # Handle window close
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self, master):
        # Top control panel
        self.frame = tk.Frame(master)
        self.frame.pack(pady=10, fill="x")

        self.add_button = tk.Button(self.frame, text="Add Videos", command=self.add_files)
        self.add_button.pack(side=tk.LEFT, padx=5)

        self.start_button = tk.Button(self.frame, text="Start", command=self.start_comparison, state=tk.DISABLED)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = tk.Button(self.frame, text="Stop", command=self.abort_processing, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.open_output_button = tk.Button(self.frame, text="Open Output", command=self.open_output_folder, state=tk.DISABLED)
        self.open_output_button.pack(side=tk.LEFT, padx=5)

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
        self.format_combo.bind("<<ComboboxSelected>>", self.on_format_change)

        # Compression level dropdown
        self.compression_label = tk.Label(self.frame, text="Compression:")
        self.compression_label.pack(side=tk.LEFT, padx=(10, 5))

        self.compression_var = tk.StringVar()
        self.compression_combo = ttk.Combobox(self.frame, textvariable=self.compression_var,
                                               state="readonly", width=22)
        self.compression_combo.pack(side=tk.LEFT, padx=(0, 5))

        # Compression options per format
        self.png_compression_options = [
            "0 [None - Fastest]",
            "1 [Very Low]",
            "2 [Low]",
            "3 [Low-Medium]",
            "4 [Medium]",
            "5 [Medium - Default]",
            "6 [Medium-High]",
            "7 [High]",
            "8 [Very High]",
            "9 [Maximum - Slowest]"
        ]
        self.webp_compression_options = [
            "0 [Fastest]",
            "1 [Very Fast]",
            "2 [Fast]",
            "3 [Medium]",
            "4 [Medium - Default]",
            "5 [Slow]",
            "6 [Slowest - Best]"
        ]

        # Initialize with PNG options
        self.compression_combo["values"] = self.png_compression_options
        self.compression_var.set(self.png_compression_options[5])  # Default: 5

        # Progress bar
        self.progress = ttk.Progressbar(master, orient="horizontal", length=500, mode="determinate")
        self.progress.pack(pady=(10, 0), padx=10, fill="x")

        # Treeview for per-file tracking
        self.tree = ttk.Treeview(master, columns=("file", "frames", "progress", "status"), show="headings", height=8)
        self.tree.heading("file", text="File")
        self.tree.heading("frames", text="Frames")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("status", text="Status")
        self.tree.column("file", width=250, anchor="w")
        self.tree.column("frames", width=100, anchor="center")
        self.tree.column("progress", width=70, anchor="center")
        self.tree.column("status", width=180, anchor="w")
        self.tree.pack(padx=10, pady=(10, 5), fill="both", expand=True)

        # Console notebook for FFmpeg output
        self.console_frame = tk.LabelFrame(master, text="FFmpeg Console Output")
        self.console_frame.pack(padx=10, pady=(0, 5), fill="both", expand=True)

        self.console_notebook = ttk.Notebook(self.console_frame)
        self.console_notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Placeholder tab when no processes are running
        self.placeholder_frame = tk.Frame(self.console_notebook)
        self.placeholder_label = tk.Label(self.placeholder_frame, text="Console output will appear here when processing starts",
                                          fg="gray")
        self.placeholder_label.pack(expand=True)
        self.console_notebook.add(self.placeholder_frame, text="No Active Process")

        # Status label
        self.status_label = tk.Label(master, text="Ready")
        self.status_label.pack(pady=(0, 10), padx=10, anchor="w")

        # Enable drag-and-drop
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind("<<Drop>>", self.drop_files)

        # Bind treeview selection to console tab switching
        self.tree.bind("<<TreeviewSelect>>", self.on_treeview_select)

        # Context menu for file operations
        self.tree_context_menu = tk.Menu(self.tree, tearoff=0)
        self.tree_context_menu.add_command(label="Play", command=self.play_selected_file)
        self.tree_context_menu.add_command(label="Open File Location", command=self.open_file_location)
        self.tree_context_menu.add_separator()
        self.tree_context_menu.add_command(label="Open Extraction Folder", command=self.open_extraction_folder)
        self.tree_context_menu.add_separator()
        self.tree_context_menu.add_command(label="Remove", command=self.remove_selected_files)
        self.tree.bind("<Button-3>", self.show_tree_context_menu)
        self.tree.bind("<Delete>", lambda e: self.remove_selected_files())

    def on_format_change(self, event=None):
        """Update compression options when format changes."""
        if self.format_var.get() == "PNG":
            self.compression_combo["values"] = self.png_compression_options
            self.compression_var.set(self.png_compression_options[5])  # Default: 5
        else:  # WebP
            self.compression_combo["values"] = self.webp_compression_options
            self.compression_var.set(self.webp_compression_options[4])  # Default: 4

    def show_tree_context_menu(self, event):
        """Show context menu on right-click."""
        # Select the item under cursor
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)

            # Enable/disable extraction folder option based on existence
            file = self.get_selected_file()
            extraction_exists = file and file in self.file_out_dirs and self.file_out_dirs[file].exists()

            # Index 3 = "Open Extraction Folder"
            self.tree_context_menu.entryconfig(3, state=tk.NORMAL if extraction_exists else tk.DISABLED)

            self.tree_context_menu.post(event.x_root, event.y_root)

    def get_selected_file(self):
        """Get the file path for the first selected item."""
        selection = self.tree.selection()
        if not selection:
            return None
        row_id = selection[0]
        for file, rid in self.row_ids.items():
            if rid == row_id:
                return file
        return None

    def play_selected_file(self):
        """Play the selected video with default player."""
        file = self.get_selected_file()
        if not file:
            return

        if sys.platform == 'win32':
            os.startfile(file)
        elif sys.platform == 'darwin':  # macOS
            subprocess.run(['open', file])
        else:  # Linux and others
            subprocess.run(['xdg-open', file])

    def open_file_location(self):
        """Open file manager with the file selected."""
        file = self.get_selected_file()
        if not file:
            return
        self._open_in_file_manager(file, select_file=True)

    def open_extraction_folder(self):
        """Open the extraction folder for the selected file."""
        file = self.get_selected_file()
        if file and file in self.file_out_dirs:
            folder = self.file_out_dirs[file]
            if folder.exists():
                self._open_in_file_manager(str(folder))

    def open_output_folder(self):
        """Open the main output folder."""
        if self.base_dir and self.base_dir.exists():
            self._open_in_file_manager(str(self.base_dir))

    def _open_in_file_manager(self, path, select_file=False):
        """Open path in the system file manager."""
        if sys.platform == 'win32':
            normalized_path = os.path.normpath(path)
            if select_file:
                subprocess.run(f'explorer /select,"{normalized_path}"', shell=True)
            else:
                subprocess.run(f'explorer "{normalized_path}"', shell=True)
        elif sys.platform == 'darwin':  # macOS
            if select_file:
                subprocess.run(['open', '-R', path])
            else:
                subprocess.run(['open', path])
        else:  # Linux
            if select_file:
                # Try nautilus (GNOME) with select
                result = subprocess.run(['nautilus', '--select', path], capture_output=True)
                if result.returncode != 0:
                    # Try dolphin (KDE)
                    result = subprocess.run(['dolphin', '--select', path], capture_output=True)
                if result.returncode != 0:
                    # Fall back to just opening the containing folder
                    subprocess.run(['xdg-open', str(Path(path).parent)])
            else:
                subprocess.run(['xdg-open', path])

    def remove_selected_files(self):
        """Remove selected files from the list."""
        selection = self.tree.selection()
        if not selection:
            return

        # Find and remove the files
        for row_id in selection:
            # Find the file path for this row
            file_to_remove = None
            for file, rid in self.row_ids.items():
                if rid == row_id:
                    file_to_remove = file
                    break

            if file_to_remove:
                # Remove from all data structures
                self.video_files.remove(file_to_remove)
                del self.row_ids[file_to_remove]
                self.file_status.pop(file_to_remove, None)
                self.file_output.pop(file_to_remove, None)
                self.tree.delete(row_id)

        # Disable Start button if no videos left
        if not self.video_files:
            self.start_button.config(state=tk.DISABLED)

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
                row_id = self.tree.insert("", "end", values=(name, "0 / ?", "0%", "Queued"))
                self.row_ids[file] = row_id
                self.video_files.append(file)
                self.file_status[file] = "Queued"
                self.file_output[file] = []

        # Enable Start button if we have videos
        if self.video_files:
            self.start_button.config(state=tk.NORMAL)

    # Console tab management
    def on_treeview_select(self, event):
        """Switch to the console tab for the selected file."""
        selection = self.tree.selection()
        if not selection:
            return

        # Find the file path for this row
        row_id = selection[0]
        for file, rid in self.row_ids.items():
            if rid == row_id and file in self.console_tabs:
                tab_frame, _ = self.console_tabs[file]
                try:
                    self.console_notebook.select(tab_frame)
                except tk.TclError:
                    pass  # Tab may not exist yet
                break

    def create_console_tab(self, file):
        """Create a console tab for a file."""
        name = Path(file).name
        # Truncate long names for tab title
        tab_title = name if len(name) <= 20 else name[:17] + "..."

        tab_frame = tk.Frame(self.console_notebook)
        text_widget = ScrolledText(tab_frame, height=8, wrap=tk.WORD, font=("Consolas", 9))
        text_widget.pack(fill="both", expand=True)
        text_widget.config(state=tk.DISABLED)  # Read-only

        # Remove placeholder tab if it exists
        try:
            self.console_notebook.forget(self.placeholder_frame)
        except tk.TclError:
            pass

        self.console_notebook.add(tab_frame, text=tab_title)
        self.console_tabs[file] = (tab_frame, text_widget)

        # Select this tab
        self.console_notebook.select(tab_frame)

    def append_console_output(self, file, line, is_progress=False):
        """Append a line to a file's console output."""
        if file not in self.console_tabs:
            return

        _, text_widget = self.console_tabs[file]
        text_widget.config(state=tk.NORMAL)

        if is_progress:
            # Progress lines: replace the last line instead of appending
            # Delete from start of last line to end
            text_widget.delete("end-2l linestart", "end-1c")
            text_widget.insert(tk.END, line.strip() + "\n")
        else:
            # Regular lines: append normally
            self.file_output[file].append(line)
            if len(self.file_output[file]) > self.max_console_lines:
                self.file_output[file] = self.file_output[file][-self.max_console_lines:]
            text_widget.insert(tk.END, line)

        text_widget.see(tk.END)  # Auto-scroll to bottom
        text_widget.config(state=tk.DISABLED)

    def update_file_status(self, file, status):
        """Update the status column for a file."""
        self.file_status[file] = status
        row_id = self.row_ids.get(file)
        if row_id:
            self.tree.set(row_id, "status", status)

    def close_console_tab(self, file):
        """Mark a console tab as completed (change tab title)."""
        if file not in self.console_tabs:
            return
        tab_frame, _ = self.console_tabs[file]
        name = Path(file).name
        tab_title = name if len(name) <= 18 else name[:15] + "..."
        try:
            self.console_notebook.tab(tab_frame, text=f"{tab_title}")
        except tk.TclError:
            pass

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

        # Clear console tabs from previous run
        for file in list(self.console_tabs.keys()):
            tab_frame, _ = self.console_tabs[file]
            try:
                self.console_notebook.forget(tab_frame)
            except tk.TclError:
                pass
        self.console_tabs.clear()
        self.file_output = {f: [] for f in self.video_files}
        self.file_out_dirs.clear()

        # Re-add placeholder if no tabs
        try:
            self.console_notebook.add(self.placeholder_frame, text="No Active Process")
        except tk.TclError:
            pass

        # Reset file statuses
        for file in self.video_files:
            self.file_status[file] = "Queued"
            row_id = self.row_ids[file]
            self.tree.set(row_id, "status", "Queued")

        self.status_label.config(text="Scanning...")
        self.add_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.progress["value"] = 0

        # Estimate all frames to be captured
        self.base_dir = Path.cwd() / f"out_{int(time.time())}"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.open_output_button.config(state=tk.NORMAL)

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
        # Extract compression level number from selection (e.g., "5 [Medium - Default]" -> "5")
        compression_level = self.compression_var.get().split()[0]
        for idx, file in enumerate(self.video_files):
            self.executor.submit(self.process_video, idx, file, interval, max_duration, output_format, compression_level)

    def process_video(self, idx, file, interval, max_duration, output_format, compression_level):
        input_path = Path(file)
        out_dir = self.base_dir / f"{idx:02}_{input_path.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Track output directory for this file
        self.file_out_dirs[file] = out_dir

        # Create console tab for this file (must be done on main thread)
        self.master.after(0, self.create_console_tab, file)
        self.master.after(0, self.update_file_status, file, "Starting...")

        # Set extension and codec options based on format
        if output_format == "WebP (lossless)":
            ext = "webp"
            codec_opts = ["-lossless", "1", "-compression_level", compression_level]
        else:  # PNG
            ext = "png"
            codec_opts = ["-compression_level", compression_level]

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

            # Enhanced regex patterns
            frame_regex = re.compile(r"frame=\s*(\d+)")
            time_regex = re.compile(r"time=(\d+:\d+:\d+\.\d+)")
            time_na_regex = re.compile(r"time=N/A")
            speed_regex = re.compile(r"speed=\s*([\d.]+)x")
            elapsed_regex = re.compile(r"elapsed=(\d+:\d+:\d+\.\d+)")

            last_frame = 0
            last_time = ""
            last_speed = ""
            last_elapsed = ""

            for line in proc.stdout:
                # Check if stop was requested
                if self.stop_requested:
                    proc.terminate()
                    self.master.after(0, self.update_file_status, file, "Aborted")
                    break

                # Detect if this is a progress line (starts with "frame=" after stripping)
                stripped = line.strip()
                is_progress_line = stripped.startswith("frame=")

                # Append line to console (on main thread)
                # Progress lines replace the previous progress line instead of appending
                self.master.after(0, self.append_console_output, file, line, is_progress_line)

                # Parse frame count
                frame_match = frame_regex.search(line)
                if frame_match:
                    frame_received = int(frame_match.group(1))
                    with self.lock:
                        self.frame_counts[file] = frame_received

                    # Check if we got a new frame (encoding completed)
                    if frame_received > last_frame:
                        last_frame = frame_received

                # Parse time position (video timestamp)
                time_match = time_regex.search(line)
                if time_match:
                    last_time = time_match.group(1)
                    # Truncate microseconds for display
                    if '.' in last_time:
                        last_time = last_time.rsplit('.', 1)[0]

                # Check for time=N/A (seeking phase)
                time_na = time_na_regex.search(line) is not None

                # Parse speed
                speed_match = speed_regex.search(line)
                if speed_match:
                    last_speed = speed_match.group(1)

                # Parse elapsed time
                elapsed_match = elapsed_regex.search(line)
                if elapsed_match:
                    last_elapsed = elapsed_match.group(1)
                    if '.' in last_elapsed:
                        last_elapsed = last_elapsed.rsplit('.', 1)[0]

                # Build status string based on current state
                if frame_match or time_match or time_na:
                    target = self.frame_targets.get(file, 0)

                    if time_na and last_frame == 0:
                        # Seeking to first frame
                        status = f"Seeking to first frame..."
                        if last_elapsed:
                            status = f"Seeking... ({last_elapsed})"
                    elif last_frame < target:
                        # Processing frames
                        if last_time:
                            status = f"Frame {last_frame}/{target} @ {last_time}"
                        else:
                            status = f"Encoding frame {last_frame + 1}/{target}"
                        if last_speed:
                            status += f" ({last_speed}x)"
                    else:
                        # Done with frames, finalizing
                        status = f"Finalizing..."
                        if last_speed:
                            status += f" ({last_speed}x)"

                    # Throttle UI updates (max 10 per second per file)
                    current_time = time.time()
                    if current_time - self.last_update_time.get(file, 0) >= 0.1:
                        self.last_update_time[file] = current_time
                        self.master.after(0, self.update_file_status, file, status)
                        self.master.after(0, self.update_progress, file)

            proc.wait()

            # Remove from active processes
            with self.lock:
                self.active_processes.pop(file, None)

            # Final status update
            if not self.stop_requested:
                self.master.after(0, self.update_file_status, file, "Done")

            # Final UI update to ensure 100% is shown
            self.master.after(0, self.update_progress, file)
            self.master.after(0, self.mark_video_complete, file)
        except Exception as e:
            print(f"Error processing {file}: {e}")
            self.master.after(0, self.update_file_status, file, f"Error: {str(e)[:30]}")
            self.master.after(0, self.append_console_output, file, f"\nERROR: {e}\n")
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
            active_files = list(self.active_processes.keys())
            for proc in self.active_processes.values():
                try:
                    proc.terminate()
                except Exception:
                    pass
            self.active_processes.clear()

        # Update status for aborted files
        for file in active_files:
            self.update_file_status(file, "Aborted")

        # Also mark queued files as not started
        for file in self.video_files:
            if self.file_status.get(file) == "Queued":
                self.update_file_status(file, "Cancelled")

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