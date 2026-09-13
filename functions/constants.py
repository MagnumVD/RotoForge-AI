EXTENSION_NAME = "RotoForge AI"

try:
    from packaging.version import Version
    CURRENT_VERSION = Version('1.2.0')
except ImportError:
    CURRENT_VERSION = None

# Wheel install config
CACHE_DIR = "./whl_cache" # In install folder space
INSTALL_LOGFILE_PATH = "./package_install.log"

TEST_MODULES = [
    "PIL",
    "segment_anything",
]

# Model download config
SAM_WEIGHTS_DIR = "./sam_hq_weights" # In install folder space

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

# Platform specific
import platform
import signal
import subprocess
if platform.system() == "Windows":
    SIGINT = signal.CTRL_BREAK_EVENT
    NEW_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP
else:
    SIGINT = signal.SIGINT
    NEW_PROCESS_GROUP = 0