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
    vit_b_exists = os.path.exists(os.path.join(sam_weights_dir, 'sam_hq_vit_b.pth'))
    vit_h_exists = os.path.exists(os.path.join(sam_weights_dir, 'sam_hq_vit_h.pth'))
    vit_l_exists = os.path.exists(os.path.join(sam_weights_dir, 'sam_hq_vit_l.pth'))
    vit_tiny_exists = os.path.exists(os.path.join(sam_weights_dir, 'sam_hq_vit_tiny.pth'))
    readme_exists = os.path.exists(os.path.join(sam_weights_dir, 'README.md'))
    
    if not vit_b_exists:
        print('downloading vit_b model (379 MB)')
        path = hf.hf_hub_download(repo_id="lkeab/hq-sam", filename="sam_hq_vit_b.pth", local_dir=sam_weights_dir, local_dir_use_symlinks=False)
        print(path)
    if not vit_h_exists:
        print('downloading vit_h model (2.57 GB)')
        path = hf.hf_hub_download(repo_id="lkeab/hq-sam", filename="sam_hq_vit_h.pth", local_dir=sam_weights_dir, local_dir_use_symlinks=False)
        print(path)
    if not vit_l_exists:
        print('downloading vit_l model (1.25 GB)')
        path = hf.hf_hub_download(repo_id="lkeab/hq-sam", filename="sam_hq_vit_l.pth", local_dir=sam_weights_dir, local_dir_use_symlinks=False)
        print(path)
    if not vit_tiny_exists:
        print('downloading vit_tiny model (42.5 MB)')
        path = hf.hf_hub_download(repo_id="lkeab/hq-sam", filename="sam_hq_vit_tiny.pth", local_dir=sam_weights_dir, local_dir_use_symlinks=False)
        print(path)
    if not readme_exists:
        print('downloading README.md (28 Bytes)')
        path = hf.hf_hub_download(repo_id="lkeab/hq-sam", filename="README.md", local_dir=sam_weights_dir, local_dir_use_symlinks=False)
        print(path)


def test_packages():
    try:
        import segment_anything_hq
    except ImportError:
        return False
    else:
        return True

def test_models():
    sam_weights_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sam_hq_weights')
    vit_b_exists = os.path.exists(os.path.join(sam_weights_dir, 'sam_hq_vit_b.pth'))
    vit_h_exists = os.path.exists(os.path.join(sam_weights_dir, 'sam_hq_vit_h.pth'))
    vit_l_exists = os.path.exists(os.path.join(sam_weights_dir, 'sam_hq_vit_l.pth'))
    vit_tiny_exists = os.path.exists(os.path.join(sam_weights_dir, 'sam_hq_vit_tiny.pth'))
    readme_exists = os.path.exists(os.path.join(sam_weights_dir, 'README.md'))
    if vit_b_exists and vit_h_exists and vit_l_exists and vit_tiny_exists and readme_exists:
        return True
    else:
        return False


def register():
    if test_models() and test_packages():
        return {'REGISTERED'}
    else:
        print("RotoForge AI: Some dependencies are not installed, please install them using the button in the Preferences with Blender opened as administrator.")
        return {'FAILED'}

def unregister():
    if test_models and test_packages:
        return {'REGISTERED'}
    else:
        print("RotoForge AI: Some dependencies are not installed, please install them using the button in the Preferences with Blender opened as administrator.")
        return {'FAILED'}
    