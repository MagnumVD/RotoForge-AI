import bpy
import subprocess
import sys
import os
import shutil
import warnings
import importlib

from .constants import EXTENSION_NAME, CACHE_DIR, INSTALL_LOGFILE_PATH, TEST_MODULES, SAM_WEIGHTS_DIR, MODEL_FILE_NAMES

def get_addon_prefs(context=None):
    if context is None:
        context = bpy.context
    return bpy.context.preferences.addons[__package__.removesuffix('.functions')].preferences

def get_install_folder(internal_folder = ''):
    return os.path.join(get_addon_prefs().dependencies_path, internal_folder)

def get_script_path():
    # Get the absolute path of the current script's directory
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Build the full path to the target script
    return os.path.join(current_dir, 'download_deps.py')

def get_install_info():
    logfile = get_install_folder(INSTALL_LOGFILE_PATH)
    settings = {}
    if os.path.exists(logfile):
        with open(logfile, 'r') as f:
            lines = f.readlines()
            lines = lines[2:6]
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    settings[key.strip()] = value.strip()
    return settings
    

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
    sam_weights_dir = get_install_folder(SAM_WEIGHTS_DIR)
    passed = True
    for file in MODEL_FILE_NAMES.keys():
        if not os.path.exists(os.path.join(sam_weights_dir, file)):
            print(f'{EXTENSION_NAME}: Missing model file: ' + file)
            passed = False
    
    if passed:
        print(f'{EXTENSION_NAME}: All models are present :)')
    return passed

        
def install_deps_start(override=False):
    driver = get_addon_prefs().dependencies_driver
    get_addon_prefs().show_log = True
    
    cache_dir = get_install_folder(CACHE_DIR)
    logfile = get_install_folder(INSTALL_LOGFILE_PATH)
    sam_weights_dir = get_install_folder(SAM_WEIGHTS_DIR)

    python_exe = sys.executable

    # Build the full path to the target script
    script_path = get_script_path()

    os.makedirs(get_install_folder(), exist_ok=True)
    shutil.rmtree(logfile, ignore_errors=True)
    
    process = subprocess.Popen([python_exe, 
                                script_path, 
                                str(logfile),
                                str(override).lower(), 
                                str(driver), 
                                str(cache_dir), 
                                str(sam_weights_dir)],
                                )
    return process, logfile

def register():
    return {'REGISTERED'}
def unregister():
    return {'UNREGISTERED'}
            
        