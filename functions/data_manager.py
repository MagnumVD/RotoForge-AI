import bpy
from bpy.app.handlers import persistent

import os
import shutil

class MaskGenControls(bpy.types.PropertyGroup):
    used_model : bpy.props.EnumProperty(
        name = "Used Model",
        items = [
            ("vit_tiny", "Light", "Use the light HQ-Sam model (very fast with decent quality)"),
            ("vit_b", "Base", "Use the base HQ-Sam model that comes with SAM (fast with bad quality)"),
            ("vit_l", "Large", "Use the large HQ-Sam model that comes with SAM (slow with medium quality)"),
            ("vit_h", "Huge", "Use the huge HQ-Sam model that comes with SAM (very slow with best quality)"),
        ],
        default= 'vit_tiny'
    ) # type: ignore
    
    guide_strength : bpy.props.FloatProperty(
        name = "Guide Strength",
        default = 10
    ) # type: ignore
    
    tracking : bpy.props.BoolProperty(
        name = "Automatic Tracking",
        default = True
    ) # type: ignore
    
    search_radius : bpy.props.FloatProperty(
        name = "Search Radius",
        default = 10
    ) # type: ignore
    
    

# Def a func that moves masks from the tempdir and the os dir to the local dir
# Will be called when a file is opened or saved.
@persistent
def rf_handlers_move_files_to_local(dummy):
    if bpy.data.is_saved:
        for image in bpy.data.images:
            if image.source == 'SEQUENCE':
                image_path = bpy.path.abspath(image.filepath)
                tmp_path = os.path.join(bpy.app.tempdir, 'RotoForge masksequences', image.name)
                os_path = os.path.join(os.path.abspath(''), 'RotoForge masksequences', image.name)
                local_path = os.path.join(bpy.path.abspath('//RotoForge masksequences'), image.name)
                # If a folder for the mask seq exists in the tmp or or os rotoforge folders, move them to the local one
                if bpy.path.is_subdir(image_path, tmp_path):
                    shutil.copytree(tmp_path, local_path)
                    image.filepath = local_path # change the filepath to work with the changed dirs
                    print("RotoForge AI: Moved mask sequence to local: ", image.name)
                elif bpy.path.is_subdir(image_path, os_path):
                    shutil.copytree(os_path, local_path)
                    image.filepath = local_path # change the filepath to work with the changed dirs
                    print("RotoForge AI: Moved mask sequence to local: ", image.name)
                    shutil.rmtree(os_path)
                else:
                    # Goto next img if it's not stored there
                    continue



properties = [MaskGenControls]
classes = []

def register():
    for cls in properties:
        bpy.utils.register_class(cls)
    
    if rf_handlers_move_files_to_local not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(rf_handlers_move_files_to_local)
    if rf_handlers_move_files_to_local not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(rf_handlers_move_files_to_local)
    
    bpy.types.Scene.rotoforge_maskgencontrols = bpy.props.PointerProperty(type=MaskGenControls)
    
    for cls in classes:
        bpy.utils.register_class(cls)
        
    return {'REGISTERED'}

def unregister():
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    
    if rf_handlers_move_files_to_local in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(rf_handlers_move_files_to_local)
    if rf_handlers_move_files_to_local in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(rf_handlers_move_files_to_local)
    
    if hasattr(bpy.types.Scene, 'rotoforge_maskgencontrols'):
        del bpy.types.Scene.rotoforge_maskgencontrols
    
    for cls in properties:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
        
    return {'UNREGISTERED'}