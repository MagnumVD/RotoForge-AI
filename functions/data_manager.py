import bpy
from bpy.app.handlers import persistent

import os
import shutil

from packaging.version import Version
import numpy as np
import PIL.Image
import PIL.ImageFilter
current_version=Version('1.1.0')

def get_rotoforge_dir(folder = ''):
    return os.path.join(bpy.app.tempdir, 'RotoForge', folder)

def get_image_filepath_in_dir(dir):
    frame = sorted(os.listdir(dir))[0]
    return os.path.join(dir, frame)


def save_sequential_mask(source_image, used_mask, best_mask, cropping_box, blur = 0.0):
    
    frame = str(bpy.context.scene.frame_current)
    width, height = source_image.size
    
    # The img seq will be saved in a folder named after the mask in the RotoForge/masksequences dir
    folder = used_mask 
    img_seq_dir = os.path.join(get_rotoforge_dir('masksequences'), folder)
    image_path = os.path.join(img_seq_dir, frame + '.png')
        
    # Convert Binary Mask to image data
    best_mask = PIL.Image.fromarray(best_mask)
    best_mask = best_mask.convert(mode='RGBA')
    best_mask = best_mask.filter(PIL.ImageFilter.BoxBlur(radius=blur))
    # Paste the cropped mask in a black image with the original res at the original position if cropping was used
    if cropping_box is not None:
        empty_mask = PIL.Image.new('RGBA', (width, height), 'black')
        empty_mask.paste(best_mask, (int(cropping_box[0]), int(cropping_box[1] + 1)))
        best_mask = empty_mask
    # Save the image
    flipped_mask = best_mask.transpose(PIL.Image.FLIP_TOP_BOTTOM)
    if not os.path.isdir(img_seq_dir):
        os.makedirs(img_seq_dir)
    flipped_mask.save(image_path)
    best_mask = best_mask.convert(mode='L')
    return np.asarray(best_mask)

def save_singular_mask(source_image, used_mask, best_mask, cropping_box, blur = 0.0):
    # The img will be saved in a folder named after the mask in the RotoForge/masksequences dir
    folder = used_mask 
    img_seq_dir = os.path.join(get_rotoforge_dir('masksequences'), folder)
    
    # Ensure the image is unpacked
    if used_mask in bpy.data.images:
        img = bpy.data.images[used_mask]
        if img.packed_file is not None:
            img.unpack(method='USE_ORIGINAL')
    
    # Clear the dir if it exists (I just remove it and recreate it in the save func)
    if os.path.isdir(img_seq_dir):
        shutil.rmtree(img_seq_dir)
    
    save_sequential_mask(source_image, used_mask, best_mask, cropping_box, blur)

def update_maskseq(used_mask, outdated=False):
    if outdated:
        folder = 'outdated_masksequences'
    else:
        folder = 'masksequences'
    
    img_seq_dir = os.path.join(get_rotoforge_dir(folder), used_mask)
    
    if os.path.isdir(img_seq_dir):
        print('RotoForge AI: Updating Masksequence from path', img_seq_dir)
        new_path = os.path.join(img_seq_dir, sorted(os.listdir(img_seq_dir))[0])
        if used_mask in bpy.data.images:
            img = bpy.data.images[used_mask]
            img.filepath = new_path
        else:
            img = bpy.data.images.load(filepath=new_path, check_existing=True)
            if len(os.listdir(img_seq_dir)) > 1:
                img.source = 'SEQUENCE'
            else:
                img.source = 'FILE'
            img.name = used_mask
        img.colorspace_settings.name = 'Non-Color'





pre_update_masks = set() # This is a temporary set that holds the masks before the depsgraph update
track_mask_updates = True
def lock_mask_update_tracking_before_load(origin):
    global track_mask_updates
    track_mask_updates = False

def unlock_mask_update_tracking(origin):
    global track_mask_updates
    track_mask_updates = True

# Def function that syncs the masksequences folder and the rf_layers to reflect changes in the .blend file
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
    
    feather_radius : bpy.props.FloatProperty(
        name = "Feather Radius",
        default = 0.2,
        min=0
    ) # type: ignore
    
    tracking : bpy.props.BoolProperty(
        name = "Automatic Tracking",
        default = True
    ) # type: ignore
    
    search_radius : bpy.props.FloatProperty(
        name = "Search Radius",
        default = 10
    ) # type: ignore
    
    @classmethod 
    def register(cls):
        bpy.types.Mask.rotoforge_maskgencontrols = bpy.props.CollectionProperty(type=cls)
    
    @classmethod
    def unregister(cls):
        if hasattr(bpy.types.Mask, 'rotoforge_maskgencontrols'):
            del bpy.types.Mask.rotoforge_maskgencontrols






# PROJECT LOAD/SAVE HANDLING

# Def a func that prepares new projects
# Will be called after a new project is loaded
def prepare_new_project(origin):
    print(f'RotoForge AI: Preparing new project...')
    global current_version
    tmp_path = os.path.join(bpy.app.tempdir, 'RotoForge')
    # Clear tmp
    if os.path.isdir(tmp_path):
        shutil.rmtree(tmp_path)
    os.makedirs(tmp_path)
    
    # Loads the pre_update_masks
    global pre_update_masks
    pre_update_masks = set(bpy.data.masks.keys())
    
    unlock_mask_update_tracking(origin)

# Def a func that copies masksequences from local to tmp and then loads them into blender
# Will be called when an old project is loaded
def load_project(origin):
    # Copy the masksequences to tmp
    tmp_path = os.path.join(bpy.app.tempdir, 'RotoForge')
    local_path = bpy.path.abspath('//RotoForge')
    # Copy all files from local to tmp
    if os.path.isdir(local_path):
        shutil.copytree(local_path, tmp_path, dirs_exist_ok=True)
    
    # Creates all missing twins of the layers in mask.rotoforge_maskgencontrols
    for mask in bpy.data.masks:
        for layer in mask.layers:
            # Load masksequence into blenders memory
            folder = f"{mask.name}/MaskLayers/{layer.name}"
            update_maskseq(folder)
            
            # Append the layer to the rf layer collection
            if layer.name not in mask.rotoforge_maskgencontrols:
                rf_layer = mask.rotoforge_maskgencontrols.add()
                rf_layer.name = layer.name

# Def a func that overwrites the RotoForge dir from tmp to local
# Acts as 'saving' the masks and RotoForge version
# Will be called after a file is saved
def save_project(origin):
    tmp_path = os.path.join(bpy.app.tempdir, 'RotoForge')
    local_path = bpy.path.abspath('//RotoForge')
    # Copies all files from tmp to local
    if os.path.isdir(tmp_path):
        shutil.rmtree(local_path)
        shutil.copytree(tmp_path, local_path, dirs_exist_ok=True)







# VERSION HANDLING

# Def a func that handles compatibility with older projects
# Will be called after an old project is loaded.
def update_old_projects(origin):
    global current_version
    
    save_after_update = False
    
    # Path to version file
    rotoforge_dir = get_rotoforge_dir()
    ver_txt_path = os.path.join(rotoforge_dir, 'version.txt')
    
    # Get the current version of this project
    
    if os.path.isfile(ver_txt_path):
        with open(ver_txt_path, 'r', encoding='utf-8') as file:
            content = file.readlines()
        loaded_version = Version(content[1])
    else:
        loaded_version = Version('1.0.0')

    print(f'RotoForge AI: Extension version: {str(current_version)}; Project version: {str(loaded_version)}')
    
    if loaded_version < current_version:
        save_after_update = True
    
    if loaded_version == Version('1.0.0'):
        # Move '//RotoForge masksequences' to '//RotoForge/outdated_masksequences' and move from ospath to local
        
        # Moves all files from the old rf dir to the new rf dir for outdates masksequences
        mask_seq_path_old = bpy.path.abspath('//RotoForge masksequences')
        mask_seq_path_new = bpy.path.abspath('//RotoForge/outdated_masksequences')
        
        if os.path.isdir(mask_seq_path_old):
            # Iterate through all items in the source directory
            for item in os.listdir(mask_seq_path_old):
                item_path = os.path.join(mask_seq_path_old, item)
                dest_item_path = os.path.join(mask_seq_path_new, item)
                shutil.move(item_path, dest_item_path)
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
    
    if save_after_update:
        print('RotoForge AI: Reloading the file since it has been updated to the newest version')
        origin = {'SAVE_AFTER_UPDATE'}
        write_version(origin)
        bpy.ops.wm.save_mainfile()
        load_project(origin)

# Def a function that writes the current RotoForge version into the tmp folder
# Will be called when a project is loaded, regardless of if its new or old
def write_version(origin):
    global current_version
    
    # Path to version file
    rotoforge_dir = get_rotoforge_dir()
    ver_txt_path = os.path.join(rotoforge_dir, 'version.txt')
    
    # Saves version to RotoForge folder (tmp)
    lines = [
        'RotoForge AI versioning\n',
        f'{str(current_version)}\n'
    ]
        
    with open(ver_txt_path, 'w', encoding='utf-8') as file:
        file.writelines(lines)



class ResyncMaskOperator(bpy.types.Operator):
    """Resyncs an outdated mask sequence to a mask"""
    bl_idname = "rotoforge.resync_masksequence"
    bl_label = "Resync old Masksequence"
    bl_options = {'REGISTER', 'UNDO'}
    
    def update_mask_options(self, context):
        possible_mask = []
        
        for maskseq_name in os.listdir(get_rotoforge_dir('outdated_masksequences')):
            possible_mask.append(maskseq_name)
        
        return [(element, element, f'Resync the masksequence "{element}"') for element in possible_mask]
    
    mask_seq_name: bpy.props.EnumProperty(
        name="Outdated Masksequence Name",
        items=update_mask_options
    ) # type: ignore
    
    @classmethod
    def poll(self, context):
        if context.space_data.mask is None or self.update_mask_options(self, context) == []:
            return False
        return True
    
    def execute(self, context):
        space = context.space_data
        mask = space.mask
        layer = mask.layers.active
        
        
        mask_seq_dir_old = get_rotoforge_dir('outdated_masksequences')
        mask_seq_dir_new = get_rotoforge_dir('masksequences')
        update_maskseq(self.mask_seq_name, outdated=True)
        
        image_name_old = self.mask_seq_name
        image_name_new = f"{mask.name}/MaskLayers/{layer.name}"
        image_path_old = os.path.join(mask_seq_dir_old, image_name_old)
        image_path_new = os.path.join(mask_seq_dir_new, image_name_new)
        
        # Relocate the Masksequence
        shutil.move(image_path_old, image_path_new)
        image = bpy.data.images[image_name_old]
        image.filepath = get_image_filepath_in_dir(image_path_new) # change the filepath to work with the changed dirs
        image.name = image_name_new
        
        self.report({'INFO'}, f'Resynced masksequence "{self.mask_seq_name}" with layer "{layer.name}" of mask "{mask.name}"')
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)





# Def helper functions that call all other functions. These are the handlers that are added in register()
@persistent
def rf_dm_handlers_load_pre(*args):
    origin = {'LOAD_PRE'}
    lock_mask_update_tracking_before_load(origin)

@persistent
def rf_dm_handlers_load_post(*args):
    origin = {'LOAD_POST'}
    prepare_new_project(origin)
    if bpy.data.is_saved: # If it's an old project
        load_project(origin)
        update_old_projects(origin)
    write_version(origin)

@persistent
def rf_dm_handlers_load_post_fail(*args):
    origin = {'LOAD_POST_FAIL'}
    unlock_mask_update_tracking(origin)


@persistent
def rf_dm_handlers_save_pre(*args):
    origin = {'SAVE_PRE'}

@persistent
def rf_dm_handlers_save_post(*args):
    origin = {'SAVE_POST'}
    save_project(origin)


@persistent
def rf_dm_handlers_depsgraph_update_post(*args):
    origin = {'DEPSGRAPH_UPDATE_POST'}
    sync_mask_update(origin)





classes = [MaskGenControls,
           ResyncMaskOperator]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    if rf_dm_handlers_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(rf_dm_handlers_load_pre)
    if rf_dm_handlers_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(rf_dm_handlers_load_post)
    if rf_dm_handlers_load_post_fail not in bpy.app.handlers.load_post_fail:
        bpy.app.handlers.load_post_fail.append(rf_dm_handlers_load_post_fail)
        
    if rf_dm_handlers_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(rf_dm_handlers_save_pre)
    if rf_dm_handlers_save_post not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(rf_dm_handlers_save_post)
        
    if rf_dm_handlers_depsgraph_update_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(rf_dm_handlers_depsgraph_update_post)
        
    return {'REGISTERED'}

def unregister():
    if rf_dm_handlers_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(rf_dm_handlers_load_pre)
    if rf_dm_handlers_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(rf_dm_handlers_load_post)
    if rf_dm_handlers_load_post_fail in bpy.app.handlers.load_post_fail:
        bpy.app.handlers.load_post_fail.remove(rf_dm_handlers_load_post_fail)
        
    if rf_dm_handlers_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(rf_dm_handlers_save_pre)
    if rf_dm_handlers_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(rf_dm_handlers_save_post)
        
    if rf_dm_handlers_depsgraph_update_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(rf_dm_handlers_depsgraph_update_post)
    
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
        
    return {'UNREGISTERED'}