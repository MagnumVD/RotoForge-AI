import bpy
from bpy.app.handlers import persistent

from packaging.version import Version
import os
import shutil


def get_rotoforge_dir(folder = ''):
    if bpy.data.is_saved:
        return os.path.join(bpy.path.abspath('//RotoForge'), folder)
    else:
        return os.path.join(bpy.app.tempdir, 'RotoForge', folder)

def get_image_filepath_in_dir(dir):
    frame = sorted(os.listdir(dir))[0]
    return os.path.join(dir, frame)

def load_sequential_maskseq(folder):
    mask_seq_dir = get_rotoforge_dir('masksequences')
    img_seq_dir = os.path.join(mask_seq_dir , folder)
    
    if os.path.isdir(img_seq_dir):
        if folder not in bpy.data.images:
            img = bpy.data.images.load(filepath=get_image_filepath_in_dir(img_seq_dir), check_existing=True)
            img.source = 'SEQUENCE'
            img.name = folder





pre_update_masks = set() # This is a temporary set that holds the masks before the depsgraph update
track_mask_updates = True
def lock_mask_update_tracking_before_load(origin):
    global track_mask_updates
    track_mask_updates = False

def append_rflayer_collection(origin):
    # Updates the pre_update_masks
    global pre_update_masks
    pre_update_masks = set(bpy.data.masks.keys())
    
    global track_mask_updates
    track_mask_updates = True
    
    # Creates all missing twins of the layers in mask.rotoforge_maskgencontrols
    for mask in bpy.data.masks:
        for layer in mask.layers:
            load_sequential_maskseq(f"{mask.name}/MaskLayers/{layer.name}")
            
            if layer.name not in mask.rotoforge_maskgencontrols:
                rf_layer = mask.rotoforge_maskgencontrols.add()
                rf_layer.name = layer.name





# Def function that changes files in '/RotoForge/masksequences' and changes rf_layers to reflect changes in the .blend file
# Will be called when a depsgraph change is made
def sync_mask_update(origin):
    mask_seq_dir = get_rotoforge_dir('masksequences')
    
    if track_mask_updates:
        global pre_update_masks
        post_update_masks = set(bpy.data.masks.keys())
        
        
        
        # Changes in Masks
        if pre_update_masks != post_update_masks:
            added = post_update_masks - pre_update_masks
            removed = pre_update_masks - post_update_masks

            pre_update_masks = post_update_masks

            if added != set():
                if removed != set():
                    # renamed Mask
                    mask_name_old = list(removed)[0]
                    mask_name_new = list(added)[0]
                    print('RotoForge AI: renamed mask:', mask_name_old, '->', mask_name_new)
                    
                    mask = bpy.data.masks[mask_name_new]
                    mask_path_old = os.path.join(mask_seq_dir, mask_name_old)
                    mask_path_new = os.path.join(mask_seq_dir, mask_name_new)
                    shutil.move(mask_path_old, mask_path_new)
                    
                    for image in bpy.data.images:
                        if image.name.startswith(mask_name_old):
                            image_name_new = mask_name_new + image.name.removeprefix(mask_name_old)
                            image_path_new = os.path.join(mask_seq_dir, image_name_new)
                            image.filepath = get_image_filepath_in_dir(image_path_new) # change the filepath to work with the changed dirs
                            image.name = image_name_new
                    
                    return

                # added Mask
                mask_name = list(added)[0]
                print('RotoForge AI: added mask:', mask_name)
                return

            # removed Mask
            mask_name = list(removed)[0]
            print('RotoForge AI: removed mask:', mask_name)
            
            for image in bpy.data.images:
                if image.name.startswith(mask_name):
                    bpy.data.images.remove(image) # change the filepath to work with the changed dirs
            return



        # Changes in layers
        for mask in bpy.data.masks:
            pre_update_layers = mask.rotoforge_maskgencontrols.keys()
            post_update_layers = mask.layers.keys()

            if pre_update_layers == post_update_layers:
                # this layer didn't change
                continue

            added = set(post_update_layers) - set(pre_update_layers)
            removed = set(pre_update_layers) - set(post_update_layers)

            if set(pre_update_layers) == set(post_update_layers):
                # moved layer

                # get list of all changes
                movements = []
                for i, value in enumerate(pre_update_layers):
                    new_index = post_update_layers.index(value)
                    if i != new_index:
                        movements.append((i, new_index))

                # Find the single displacement causing the changes
                # This works because the condition is "only one element moves"
                for start, end in movements:
                    # Simulate the move
                    temp_list = pre_update_layers[:] # Create a copy of the update layers
                    moved_value = temp_list.pop(start)  # Remove the element at 'start'
                    temp_list.insert(end, moved_value)  # Insert it at 'end'

                    # Check if the result matches the permuted list
                    if temp_list == post_update_layers:
                        print('RotoForge AI: moved layer:', moved_value, '->', end)
                        mask.rotoforge_maskgencontrols.move(start, end)
                        return

            if added != set():
                if removed != set():
                    # renamed layer
                    layer_name_old = list(removed)[0]
                    layer_name_new = list(added)[0]
                    print('RotoForge AI: renamed layer:', layer_name_old, '->', layer_name_new)
                    mask.rotoforge_maskgencontrols[layer_name_old].name = layer_name_new
                    
                    image_name_old = f"{mask.name}/MaskLayers/{layer_name_old}"
                    image_name_new = f"{mask.name}/MaskLayers/{layer_name_new}"
                    image_path_old = os.path.join(mask_seq_dir, image_name_old)
                    image_path_new = os.path.join(mask_seq_dir, image_name_new)
                    shutil.move(image_path_old, image_path_new)
                    if image_name_old in bpy.data.images:
                        image = bpy.data.images[image_name_old]
                        image.filepath = get_image_filepath_in_dir(image_path_new) # change the filepath to work with the changed dirs
                        image.name = image_name_new
                    
                    return

                # added layer
                layer_name = list(added)[0]
                print('RotoForge AI: added layer:', layer_name)
                rf_layer = mask.rotoforge_maskgencontrols.add()
                rf_layer.name = layer_name
                return

            if removed != set():
                # removed layer
                layer_name = list(removed)[0]
                print('RotoForge AI: removed layer:', layer_name)
                mask.rotoforge_maskgencontrols.remove(mask.rotoforge_maskgencontrols.find(layer_name))
                return

            print('RotoForge AI: Something went wrong in the Layer sync function - help!')
                
    
    
    

# This is all the controls that should be part of a layer, but can't be since a MaskLayer is a struct and not an ID
# So now instead this is bound to a collection property in bpy.types.Mask, which has an entry for each Layer in the mask
# With that same structure the details can be streamed from there
class MaskGenControls(bpy.types.PropertyGroup):
    name : bpy.props.StringProperty(
        name = "Layer name",
        description="Name of the layer this controlgroup represents",
        default=""
    ) # type: ignore
    
    is_rflayer :  bpy.props.BoolProperty(
        name = "Activate RotoForge",
        default = False
    ) # type: ignore
    
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



# Def a func that moves masksequences from tmp to a local dir
# Will be called after a file is saved
def move_from_tmp_to_local(origin):
    save_after_update = False
    
    # Move masks from the tempdir and the os dir to the local dir
    
    # Moves all files from temp to local
    tmp_path = os.path.join(bpy.app.tempdir, 'RotoForge/masksequences')
    local_path = bpy.path.abspath('//RotoForge/masksequences')
    if os.path.isdir(tmp_path):
        shutil.copytree(tmp_path, local_path, dirs_exist_ok=True)
    
    for image in bpy.data.images: 
        if image.source == 'SEQUENCE':
            image_path = bpy.path.abspath(image.filepath)
            tmp_path = os.path.join(bpy.app.tempdir, 'RotoForge/masksequences', image.name)
            local_path = os.path.join(bpy.path.abspath('//RotoForge/masksequences'), image.name)
            # If the mask seq path is set to the tmp folder, change it to the new local one
            if bpy.path.is_subdir(image_path, tmp_path):
                save_after_update = True
                
                image.filepath = get_image_filepath_in_dir(local_path) # change the filepath to work with the changed dirs
                
                print("RotoForge AI: Moved mask sequence to local: ", image.name)
                continue
            
            # Goto next img if it's not stored there
    
    if save_after_update and origin != {'SAVE_PRE'}:
        # Makes everything run recursively until all checks out
        print('RotoForge AI: Resaving the project since some folders were relocated')
        bpy.ops.wm.save_mainfile()
        
    


# Def a func that handles compatibility with older projects
# Will be called after a file is opened or before it is saved.
def update_old_projects(origin):
    current_version=Version('1.1.0')
    
    save_after_update = False
    
    # Path to version file
    rotoforge_dir = get_rotoforge_dir()
    ver_txt_path = os.path.join(rotoforge_dir, 'version.txt')
    
    def write_version():
        # Saves version to RotoForge folder
        
        lines = [
            'RotoForge AI versioning\n',
            f'{str(current_version)}\n'
        ]
        
        if not os.path.isdir(rotoforge_dir):
            os.makedirs(rotoforge_dir)
            
        with open(ver_txt_path, 'w', encoding='utf-8') as file:
            file.writelines(lines)
    
    
    # When an old project is opened up again
    if bpy.data.is_saved and origin == {'LOAD_POST'}:
        # Get the current version of this project
        
        if os.path.isfile(ver_txt_path):
            with open(ver_txt_path, 'r', encoding='utf-8') as file:
                content = file.readlines()
            loaded_version = Version(content[1])
        else:
            loaded_version = Version('1.0.0')
        
        # If the loaded project is older, it will be updated - save it after that
        if loaded_version < current_version:
            write_version()
            save_after_update = True
                
    
        print(f'RotoForge AI: Extension version: {str(current_version)}; Project version: {str(loaded_version)}')
        
        if loaded_version == Version('1.0.0'):
            # Move '//RotoForge masksequences' to '//RotoForge\masksequences' and move from ospath to local
            
            # Moves all files from the old rf dir to the new rf dir
            mask_seq_path_old = bpy.path.abspath('//RotoForge masksequences')
            mask_seq_path_new = bpy.path.abspath('//RotoForge/outdated_masksequences')
            if os.path.isdir(mask_seq_path_old):
                # Iterate through all items in the source directory
                for item in os.listdir(mask_seq_path_old):
                    item_path = os.path.join(mask_seq_path_old, item)
                    dest_item_path = os.path.join(mask_seq_path_new, item)
                    shutil.move(item_path , dest_item_path)
                shutil.rmtree(mask_seq_path_old)
                
            for image in bpy.data.images: 
                if image.source == 'SEQUENCE':
                    image_path = bpy.path.abspath(image.filepath)
                    os_path = os.path.join(os.path.abspath(''), 'RotoForge masksequences', image.name)
                    local_path_old = os.path.join(mask_seq_path_old, image.name)
                    local_path_new = os.path.join(mask_seq_path_new, image.name)
                    
                    # If the mask seq path is set to the old local path rf folder, change it to the new local one
                    if bpy.path.is_subdir(image_path, local_path_old):
                        image.filepath = get_image_filepath_in_dir(local_path_new) # change the filepath to work with the changed dirs
                        print("RotoForge AI: Moved mask sequence to local: ", image.name)
                        continue
                        
                    # If a folder for the mask seq exists in the os rf folder, move them to the new local one
                    if bpy.path.is_subdir(image_path, os_path):
                        shutil.move(os_path, local_path_new)
                        
                        image.filepath = get_image_filepath_in_dir(local_path_new) # change the filepath to work with the changed dirs
                        print("RotoForge AI: Moved mask sequence to local: ", image.name)
                        continue
                    
                    # Goto next img if it's not stored there
        
        
    # When a new project is about to be saved
    if not bpy.data.is_saved and origin == {'SAVE_PRE'}:
        write_version()
    
    
    
    if save_after_update and origin != {'SAVE_PRE'}:
        # Makes everything run recursively until all checks out
        print('RotoForge AI: Resaving the project since RotoForge has been updated')
        bpy.ops.wm.save_mainfile()




# Def helper functions that call all other functions. These are the handlers that are added in register()
@persistent
def rf_handlers_load_pre(*args):
    origin = {'LOAD_PRE'}
    lock_mask_update_tracking_before_load(origin)

@persistent
def rf_handlers_load_post(*args):
    origin = {'LOAD_POST'}
    update_old_projects(origin)
    append_rflayer_collection(origin)

@persistent
def rf_handlers_save_pre(*args):
    origin = {'SAVE_PRE'}
    update_old_projects(origin)

@persistent
def rf_handlers_save_post(*args):
    origin = {'SAVE_POST'}
    move_from_tmp_to_local(origin)

@persistent
def rf_handlers_depsgraph_update_post(*args):
    origin = {'DEPSGRAPH_UPDATE_POST'}
    sync_mask_update(origin)






properties = [MaskGenControls]
classes = []

def register():
    for cls in properties:
        bpy.utils.register_class(cls)
    
    if rf_handlers_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(rf_handlers_load_pre)
    if rf_handlers_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(rf_handlers_load_post)
        
    if rf_handlers_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(rf_handlers_save_pre)
    if rf_handlers_save_post not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(rf_handlers_save_post)
        
    if rf_handlers_depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(rf_handlers_depsgraph_update_post)
    
    bpy.types.Mask.rotoforge_maskgencontrols = bpy.props.CollectionProperty(type=MaskGenControls)
    
    for cls in classes:
        bpy.utils.register_class(cls)
        
    return {'REGISTERED'}

def unregister():
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    
    if rf_handlers_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(rf_handlers_load_pre)
    if rf_handlers_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(rf_handlers_load_post)
        
    if rf_handlers_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(rf_handlers_save_pre)
    if rf_handlers_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(rf_handlers_save_post)
        
    if rf_handlers_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(rf_handlers_depsgraph_update_post)
    
    if hasattr(bpy.types.Mask, 'rotoforge_maskgencontrols'):
        del bpy.types.Mask.rotoforge_maskgencontrols
    
    for cls in properties:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
        
    return {'UNREGISTERED'}