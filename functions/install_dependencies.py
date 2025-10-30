import bpy
import subprocess
import sys
import shutil
import os
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
    print('RotoForge AI: Testing python packages...')
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            import segment_anything
            del segment_anything
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
        print('RotoForge AI: Python packages passed testing :)')
        return True

def test_models():
    print('RotoForge AI: Testing models...')
    sam_weights_dir = get_install_folder(sam_weights_dir_name)
    for file in model_file_names.keys():
        if not os.path.exists(os.path.join(sam_weights_dir, file)):
            print('Rotoforge AI: Missing model: ' + file)
            return False
    #If all files are present, return true
    print('RotoForge AI: All models are present :)')
    return True

# Evil code that kicks modules out of the sys.modules cache while blender is still running
def unload_modules_from_path(target_path):
    print('--- PYTHON PACKAGE UNLOAD STARTING ---')
    
    # Normalize the target path for comparison
    target_path = os.path.abspath(target_path)
    
    # Find modules loaded from the target path
    retry = True
    
    while retry:
        modules_to_remove = []
        retry=False
        print("Searching for active modules in: ", target_path)
        for module_name, module in sys.modules.items():
            # Ensure the module is valid and has a __file__ attribute
            if module and hasattr(module, '__file__') and module.__file__:
                # Get the absolute path of the module's file
                module_path = os.path.abspath(module.__file__)

                # Check if the module or any of its submodules belong to the target path
                if bpy.path.is_subdir(module_path, target_path):
                    # If it's a package, we need to recursively remove all submodules
                    if module_name.find('.') == -1:
                        print(f"Found module: {module_name}")
                        #for submodule_name in list(sys.modules.keys()):
                        #    if submodule_name.startswith(module_name + '.'):
                        #        modules_to_remove.append(submodule_name)
                        # Add the module itself
                        modules_to_remove.append(module_name)

        print('Unloading Modules')
        # Remove the collected modules from sys.modules
        for module_name in modules_to_remove:
            retry=True
            if module_name in sys.modules:
                del sys.modules[module_name]
    
    print('--- PYTHON PACKAGE UNLOAD FINISHED ---')
        

def install_packages(override = False):
    print('--- PYTHON PACKAGE INSTALL STARTING ---')
    python_exe = sys.executable
    requirements_txt = os.path.join(os.path.dirname(os.path.realpath(__file__)), "deps_requirements.txt")
    target = get_install_folder("py_packages")
    
    if override:
        unload_modules_from_path(target)
        shutil.rmtree(target)
        return
    
    subprocess.run([python_exe, '-m', 'ensurepip'])
    subprocess.run([python_exe, '-m', 'pip', 'install', '--upgrade', 'pip', '-t', target])
    
    subprocess.run([python_exe, '-m', 'pip', 'install', '--upgrade', '-r', requirements_txt, '-t', target])
        
    ensure_package_path()
    print('--- PYTHON PACKAGE INSTALL FINISHED ---')

def download_models(override = False):
    print('--- MODEL DOWNLOAD STARTING ---')
    import huggingface_hub as hf
    
    sam_weights_dir = get_install_folder(sam_weights_dir_name)
    
    for name, size in model_file_names.items():
        if override or not os.path.exists(os.path.join(sam_weights_dir, name)):
            print(f'downloading {name} ({size})')
            path = hf.hf_hub_download(repo_id="lkeab/hq-sam", filename=name, local_dir=sam_weights_dir)
            print(path)
    del hf
    print('--- MODEL DOWNLOAD FINISHED ---')

def register():
    #ensure_package_path()
    return {'REGISTERED'}
def unregister():
    return {'UNREGISTERED'}
    