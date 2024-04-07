import subprocess
import sys
import os


def install_packages():
    python_exe = os.path.join(sys.prefix, 'bin', 'python.exe')
    target = os.path.join(sys.prefix, 'lib', 'site-packages')
    
    subprocess.call([python_exe, '-m', 'ensurepip'])
    subprocess.call([python_exe, '-m', 'pip', 'install', '--upgrade', 'pip', '-t', target])
    
    subprocess.call([python_exe, '-m', 'pip', 'uninstall', '-y', 'numpy', 'charset_normalizer', 'pillow'])
    subprocess.call([python_exe, '-m', 'pip', 'install', '--upgrade', 'timm', 'segment-anything-hq', '-t', target])
    subprocess.call([python_exe, '-m', 'pip', 'install', '--upgrade', '--no-dependencies', 'torch', 'torchvision', '--index-url', 'https://download.pytorch.org/whl/cu121', '-t', target])
    
    print('FINISHED')

def download_models():
    import huggingface_hub as hf
    sam_weights_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sam_hq_weights')
    hf.hf_hub_download(repo_id="lkeab/hq-sam", filename="README.md", local_dir="sam_weights_dir", local_dir_use_symlinks=False)

def register():
    try:
        import segment_anything_hq
    except ImportError:
        print("RotoForge AI: Some dependencies are not installed, please install them using the button in the Preferences with Blender opened as administrator.")
        return {'FAILED'}
    else:
        return {'REGISTERED'}

def unregister():
    try:
        import segment_anything_hq
    except ImportError:
        print("RotoForge AI: Some dependencies are not installed, please install them using the button in the Preferences with Blender opened as administrator.")
        return {'FAILED'}
    else:
        return {'UNREGISTERED'}
    