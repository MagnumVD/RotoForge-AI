import bpy
import subprocess
import sys
import os
from typing import Optional
import warnings

def get_install_folder(internal_folder):
    return os.path.join(bpy.context.preferences.addons[__package__.removesuffix('.functions')].preferences.dependencies_path, internal_folder)

model_file_names = {
    'sam_hq_vit_b.pth': '379 MB',
    'sam_hq_vit_h.pth': '2.57 GB',
    'sam_hq_vit_l.pth': '1.25 GB',
    'sam_hq_vit_tiny.pth': '42.5 MB',
    'README.md': '28 Bytes'
}

sam_weights_dir_name = "sam_hq_weights"

def ensure_package_path():
    # Add the python path to the dependencies dir if missing
    target = get_install_folder("py_packages")
    if os.path.isdir(target) and target not in sys.path:
        print('RotoForge AI: Found missing deps path in sys.path, appending...')
        sys.path.append(target)
        print('RotoForge AI: Deps path has been appended to sys.path')

def test_packages():
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            import segment_anything_hq
            del segment_anything_hq
    except ImportError as e:
        print('RotoForge AI: An ImportError occured when importing the dependencies')
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
        return False
    except Exception as e:
        print('RotoForge AI: Something went very wrong importing the dependencies, please get that checked')
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
        return False
    else:
        return True

def test_models():
    sam_weights_dir = get_install_folder(sam_weights_dir_name)
    for file in model_file_names.keys():
        if not os.path.exists(os.path.join(sam_weights_dir, file)):
            print('Rotoforge AI: missing model ' + file)
            return False
    #If all files are present, return true
    return True

def install_packages(override: Optional[bool] = False):
    python_exe = os.path.join(sys.prefix, 'bin', 'python.exe')
    requirements_txt = os.path.join(os.path.dirname(os.path.realpath(__file__)), "deps_requirements.txt")
    target = get_install_folder("py_packages")
    
    subprocess.call([python_exe, '-m', 'ensurepip'])
    subprocess.call([python_exe, '-m', 'pip', 'install', '--upgrade', 'pip', '-t', target])
    
    if override:
        subprocess.call([python_exe, '-m', 'pip', 'install', '--upgrade', '--force-reinstall', '-r', requirements_txt, '-t', target])
    else:
        subprocess.call([python_exe, '-m', 'pip', 'install', '--upgrade', '-r', requirements_txt, '-t', target])
        
    ensure_package_path()
    print('FINISHED')

def download_models(override: Optional[bool] = False):
    import huggingface_hub as hf
    
    sam_weights_dir = get_install_folder(sam_weights_dir_name)
    
    for name, size in model_file_names.items():
        if override or not os.path.exists(os.path.join(sam_weights_dir, name)):
            print('downloading ', name, ' (', size, ')')
            path = hf.hf_hub_download(repo_id="lkeab/hq-sam", filename=name, local_dir=sam_weights_dir)
            print(path)
    del hf

def register():
    ensure_package_path()
    if test_models() and test_packages():
        return {'REGISTERED'}
    else:
        print("RotoForge AI: Some dependencies are not installed, please install them using the button in the Preferences.")
        return {'FAILED'}

def unregister():
    if test_models and test_packages:
        return {'REGISTERED'}
    else:
        print("RotoForge AI: Some dependencies are not installed, please install them using the button in the Preferences.")
        return {'FAILED'}
    