"""
This script is the worker that runs in a subprocess to download and install
the required Python packages and model files.
It is designed to be launched from within the Blender extension, and includes a watchdog
thread that monitors the Blender process and terminates itself if Blender exits.
"""


import subprocess
import sys
import shutil
import os
import requests
import time
import threading
import platform
import ctypes
from ctypes import wintypes

MANIFEST_FILE = "./blender_manifest.toml" # In package space
WHEELS_DIR = "./wheels"
PACKAGED_WHEELS_DIR = "./packaged_wheels"
REQUIREMENTS_FILES = f"./functions/deps_requirements/"
TEMP_FILE = "./blender_manifest_temp.toml"

MODEL_FILE_NAMES = {
    'sam_hq_vit_b.pth': '379 MB',
    'sam_hq_vit_h.pth': '2.57 GB',
    'sam_hq_vit_l.pth': '1.25 GB',
    'sam_hq_vit_tiny.pth': '42.5 MB'
}


# Platform‑specific “process still exists?” helpers
if platform.system() == "Windows":
    # Ctypes wrapper around OpenProcess / GetExitCodeProcess
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259

    def _process_exists(pid: int) -> bool:
        handle = _kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            _kernel32.CloseHandle(handle)

else:
    # POSIX (Linux / macOS) – os.kill(pid, 0) is the canonical test
    def _process_exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True


class TeeToFile:
    """
    Tee stdout/stderr to terminal and file.
    Handles carriage returns so progress bars overwrite instead of appending.
    Is not thread-safe.
    """

    def __init__(self, filename):
        self.file = open(filename, "w", encoding="utf-8", buffering=1)
        self.terminal = sys.__stdout__
        self.line_start_pos = 0
        self.text_buffer = ""
        self.carriage_return_on_next = False

    def write(self, text: str | bytes):
        if not text:
            return

        if isinstance(text, bytes):
            text = text.decode('utf-8', errors='ignore')
            text = text.replace('\r\n', '\n')
        
        self.text_buffer += text
        lines = self.text_buffer.splitlines(True)
        for line in lines:
            if self.carriage_return_on_next and line[-1] in ['\r', '\n']:
                # Move back to start of line
                self.file.seek(self.line_start_pos)
                self.file.truncate()
                self.carriage_return_on_next = False
            # Grab the last overwrite after carriage returns
            if line[-1] == '\n':
                self.text_buffer = self.text_buffer[len(line):]
                line = line.split('\r')[-1]
                self.file.write(line)
                self.line_start_pos = self.file.tell()
                continue
            if line[-1] == '\r':
                self.text_buffer = self.text_buffer[len(line):]
                line = line[:-1].split('\r')[-1]
                self.file.write(line)
                self.carriage_return_on_next = True
                continue
            # Else: Incomplete line, keep in buffer
            continue

        self.file.flush()
        self.terminal.write(text)
        self.terminal.flush()

    def flush(self):
        self.file.flush()
        self.terminal.flush()

    def close(self):
        self.file.close()


# Watchdog thread
class BlenderWatchdog(threading.Thread):
    """
    Checks every *poll_interval* seconds whether the given parent PID (Blender) is alive.
    If it disappears, all registered subprocesses are terminated and the script
    exits.
    """

    def __init__(self, poll_interval: float = 2.0, parent_pid: int | None = None):
        super().__init__(daemon=True)
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        # Use the supplied PID or fall back to the immediate parent PID
        self.parent_pid = parent_pid if parent_pid is not None else os.getppid()
        self.children: list[subprocess.Popen] = []

    # Public API – tell the watchdog about a child process
    def add_child(self, proc: subprocess.Popen):
        """Register a subprocess that should be killed if the parent exits"""
        self.children.append(proc)

    # Main loop
    def run(self):
        while not self._stop.is_set():
            if not _process_exists(self.parent_pid):
                self._cleanup_and_exit()
            time.sleep(self.poll_interval)

    def stop(self):
        """Ask the watchdog to stop (e.g., from Blender's unregister())"""
        self._stop.set()

    # Cleanup
    def _cleanup_and_exit(self):
        # Terminate every child we know about
        for child in self.children:
            if child.poll() is None:          # still running
                try:
                    child.terminate()
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill()
                except Exception as exc:
                    print(f"[Watchdog] could not stop child {child.pid}: {exc}")

        # End the whole script – Blender is gone, nothing left to do
        print("--- DEPS INSTALL STOPPED BY WATCHDOG ---")
        done_event.set()


def install_packages(driver: str, cache_dir: str, override: bool = False):
    print('--- PYTHON PACKAGE INSTALL STARTING ---')
    print("Preparing environment...")

    requirements_file = f"{REQUIREMENTS_FILES}{driver}.txt"

    python_exe = sys.executable
    root_path = os.path.realpath(os.path.join(os.path.realpath(__file__), "..", ".."))

    wheels_dir = os.path.join(root_path, WHEELS_DIR)
    requirements_file = os.path.join(root_path, requirements_file)
    manifest_file = os.path.join(root_path, MANIFEST_FILE)
    packaged_wheels_dir = os.path.join(root_path, PACKAGED_WHEELS_DIR)
    temp_file = os.path.join(root_path, TEMP_FILE)

    # --- Ensure directories exist ---
    if override: # Clean cache dir for override
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
    
    if os.path.exists(wheels_dir):
        shutil.rmtree(wheels_dir)

    os.makedirs(cache_dir, exist_ok=True)


    # Download missing wheels
    print("Downloading missing wheels pip...")
    pip_process = subprocess.Popen([python_exe, '-m', 
                                    'pip', 'download', 
                                    '-r', requirements_file, 
                                    '--only-binary', ':all:', 
                                    '-d', cache_dir, 
                                    '--no-deps', 
                                    '--progress-bar=off',
                                    '--no-cache-dir'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    bufsize=0,
                                    )
    watchdog.add_child(pip_process)
    
    # Stream output
    # Stream output live
    while pip_process.poll() is None:
        pip_process.stdout.flush()
        chunk = pip_process.stdout.read(1024)
        if chunk:
            sys.stdout.write(chunk)
    
    pip_process.stdout.close()
    if pip_process.returncode != 0:
        raise RuntimeError(f"Pip download failed with exit code {pip_process.returncode}")

    # Copy wheels to wheels directory
    print("Copying wheel cache to wheels directory...")
    shutil.copytree(cache_dir, wheels_dir, dirs_exist_ok=True)
    shutil.copytree(packaged_wheels_dir, wheels_dir, dirs_exist_ok=True)

    print(f"Updating wheels in {manifest_file}...")

    # Read and modify manifest
    with open(manifest_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    in_wheels_section = False

    for line in lines:
        stripped = line.strip()

        if stripped == "wheels = [":
            new_lines.append(line)  # keep the header line
            # Add all .whl files from the directory
            for filename in sorted(os.listdir(wheels_dir)):
                if filename.endswith(".whl"):
                    new_lines.append(f'  "./wheels/{filename}",\n')
            new_lines.append("]\n")  # closing bracket
            in_wheels_section = True
        elif in_wheels_section:
            # Skip existing lines until the end of the wheels section
            if stripped == "]":
                in_wheels_section = False
            continue
        else:
            new_lines.append(line)

    # Write the updated manifest
    with open(temp_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # Replace the original file
    shutil.move(temp_file, manifest_file)

    print('--- PYTHON PACKAGE INSTALL FINISHED ---')

def download_models(sam_weights_dir: str, base_url: str, override: bool = False):
    # install the default dependencies
    print('--- MODEL DOWNLOAD STARTING ---')
    os.makedirs(os.path.join(sam_weights_dir, ".temp"), exist_ok=True)
    
    base_url = "https://huggingface.co/lkeab/hq-sam/resolve/main/"
    
    for name, size in MODEL_FILE_NAMES.items():
        file_path = os.path.join(sam_weights_dir, name)
        file_path_temp = os.path.join(sam_weights_dir, '.temp', name)
        if override or not os.path.exists(file_path):
            print(f'Downloading {name} ({size})')
            # download module in subprocess
            response = requests.get(base_url + name, stream=True, timeout=10)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            with open(file_path_temp, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(f'{name}: {percent:.1f}% ({downloaded / (1024**2):.1f} MB / {total_size / (1024**2):.1f} MB)', end='\r')

            shutil.move(file_path_temp, file_path)
        print(f'Saved to {file_path}')
    
    print('--- MODEL DOWNLOAD FINISHED ---')


def main(override: bool, driver: str, cache_dir: str, sam_weights_dir: str):
    try:
        print("--- DEPS INSTALL WORKER STARTING ---")
        print("Settings:")
        print(f"    override: {override}")
        print(f"    driver: {driver}")
        print(f"    cache_dir: {cache_dir}")
        print(f"    sam_weights_dir: {sam_weights_dir}")
        install_packages(driver, cache_dir, override)
        download_models(sam_weights_dir, override)
        print("--- DEPS INSTALL WORKER FINISHED ---")
    except Exception as exc:
        print("--- DEPS INSTALL STOPPED WITH ERROR ---")
        print(exc)
    done_event.set()
    

if __name__ == "__main__":
    args = sys.argv[1:] # Args: override, driver, cache_dir, sam_weights_dir
    if len(args) == 5:
        log_path = args[0]
        # Convert string to boolean
        override_arg = args[1].lower()
        if override_arg in ("true", "1", "yes", "y"):
            override = True
        elif override_arg in ("false", "0", "no", "n"):
            override = False
        else:
            override = False

        driver = args[2]
        cache_dir = args[3]
        sam_weights_dir = args[4]

        # Redirect stdout and stderr
        sys.stdout = sys.stderr = TeeToFile(log_path)

        # Create global watchdog instance
        watchdog = BlenderWatchdog(poll_interval=1.0)   # check every second
        main_thread =threading.Thread(target=main, args=[override, driver, cache_dir, sam_weights_dir])
        done_event = threading.Event()

        watchdog.daemon = True
        main_thread.daemon = True

        watchdog.start()
        main_thread.start()

        done_event.wait()
        watchdog.stop()

    else:
        raise IndexError("Invalid options called")