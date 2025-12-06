import bpy
import subprocess
import sys
import shutil
import os
import warnings
import importlib
import addon_utils

import requests
try:
    from tqdm import tqdm
except ImportError:
    pass

EXTENSION_NAME = "RotoForge AI"

# Wheel install config
MANIFEST_FILE = "blender_manifest.toml"
WHEELS_DIR = "./wheels"
PACKAGED_WHEELS_DIR = "./packaged_wheels"
CACHE_DIR = "./whl_cache"
REQUIREMENTS_FILES = f"./functions/deps_requirements/"
TEMP_FILE = "blender_manifest_temp.toml"
TEST_MODULES = [
    "numpy",
    "PIL",
    "segment_anything",
]

# Model download config
SAM_WEIGHTS_DIR_NAME = "sam_hq_weights"
MODEL_FILE_NAMES = {
    'sam_hq_vit_b.pth': '379 MB',
    'sam_hq_vit_h.pth': '2.57 GB',
    'sam_hq_vit_l.pth': '1.25 GB',
    'sam_hq_vit_tiny.pth': '42.5 MB'
}

def get_install_folder(internal_folder):
    return os.path.join(bpy.context.preferences.addons[__package__.removesuffix('.functions')].preferences.dependencies_path, internal_folder)

def get_driver():
    return bpy.context.preferences.addons[__package__.removesuffix('.functions')].preferences.dependencies_driver

def test_packages():
    print(f'{EXTENSION_NAME}: Testing python packages...')

    passed = True
    
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning)
        for module_str in TEST_MODULES:
            try:
                module = importlib.import_module(module_str)
                if hasattr(module, '__version__'):
                    print(module_str, module.__version__)
                else:
                    print(module_str)
                del sys.modules[module_str]
            except ImportError as e:
                print(f'{EXTENSION_NAME}: An ImportError occured when importing the dependencies:')
                if hasattr(e, 'message'):
                    print(e.message)
                else:
                    print(e)
                passed = False
            except Exception as e:
                print(f'{EXTENSION_NAME}: Something went very wrong importing the dependencies, please get that checked:')
                if hasattr(e, 'message'):
                    print(e.message)
                else:
                    print(e)
                passed = False
            else:
                pass
    if passed:
        print(f'{EXTENSION_NAME}: Python packages passed testing :)')
    return passed

def test_models():
    print(f'{EXTENSION_NAME}: Testing models...')
    sam_weights_dir = get_install_folder(SAM_WEIGHTS_DIR_NAME)
    passed = True
    for file in MODEL_FILE_NAMES.keys():
        if not os.path.exists(os.path.join(sam_weights_dir, file)):
            print(f'{EXTENSION_NAME}: Missing model file: ' + file)
            passed = False
    
    if passed:
        print(f'{EXTENSION_NAME}: All models are present :)')
    return passed

        
def install_packages(override=False):
    print('--- PYTHON PACKAGE INSTALL STARTING ---')

    driver = get_driver()
    cache_dir = get_install_folder(CACHE_DIR)
    requirements_file = f"{REQUIREMENTS_FILES}{driver}.txt"

    python_exe = sys.executable
    root_path = os.path.realpath(os.path.join(os.path.realpath(__file__), "..", ".."))

    manifest_file = os.path.join(root_path, MANIFEST_FILE)
    packaged_wheels_dir = os.path.join(root_path, PACKAGED_WHEELS_DIR)
    wheels_dir = os.path.join(root_path, WHEELS_DIR)
    requirements_file = os.path.join(root_path, requirements_file)
    temp_file = os.path.join(root_path, TEMP_FILE)

    # --- Ensure directories exist ---
    if override: # Clean cache dir for override
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
    
    if os.path.exists(wheels_dir):
        shutil.rmtree(wheels_dir)

    os.makedirs(cache_dir, exist_ok=True)

    # Download missing wheels
    print("Downloading missing wheels...")
    subprocess.run([python_exe, '-m', 'pip', 'download', '-r', requirements_file, '--only-binary', ':all:', '-d', cache_dir, '--no-deps', '--no-cache-dir'], check=True)
    print("All wheels have been downloaded successfully.")

    # Copy wheels to wheels directory
    print("Copying wheel cache to wheels directory...")
    shutil.copytree(cache_dir, wheels_dir, dirs_exist_ok=True)
    shutil.copytree(packaged_wheels_dir, wheels_dir, dirs_exist_ok=True)

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

    print(f"Wheels list updated in {manifest_file}.\n")
    print('--- PYTHON PACKAGE INSTALL FINISHED ---')
    
    # Reload the scripts
    print(f"{EXTENSION_NAME}: Reloading extension")
    addon_utils.extensions_refresh(ensure_wheels=True, addon_modules_pending=[__package__])
    
    test_packages()

def download_models(override = False):
    print('--- MODEL DOWNLOAD STARTING ---')
    
    sam_weights_dir = get_install_folder(SAM_WEIGHTS_DIR_NAME)
    os.makedirs(sam_weights_dir, exist_ok=True)
    
    BASE_URL = "https://huggingface.co/lkeab/hq-sam/resolve/main/"
    
    for name, size in MODEL_FILE_NAMES.items():
        file_path = os.path.join(sam_weights_dir, name)
        if override or not os.path.exists(file_path):
            print(f'Downloading {name} ({size})')
            response = requests.get(BASE_URL + name, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            with open(file_path, 'wb') as f, tqdm(total=total_size, unit='B', unit_scale=True, desc=name) as bar:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        bar.update(len(chunk))
            print(f'Saved to {file_path}')
    
    print('--- MODEL DOWNLOAD FINISHED ---')

def register():
    return {'REGISTERED'}
def unregister():
    return {'UNREGISTERED'}
            
        