EXTENSION_NAME = "RotoForge AI"

try:
    from packaging.version import Version
    CURRENT_VERSION = Version('1.1.1')
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

MODEL_FILE_NAMES = {
    'sam_hq_vit_b.pth': '379 MB',
    'sam_hq_vit_h.pth': '2.57 GB',
    'sam_hq_vit_l.pth': '1.25 GB',
    'sam_hq_vit_tiny.pth': '42.5 MB'
}