import bpy
from time import process_time

from bpy.types import Context
import numpy as np
import torch
from . import generate_masks
from . import prompt_utils

predictor = None
used_model = None



def time_checkpoint(start, name):
    
    # Get the elapsed time
    elapsed_time = process_time() - start

    # Convert the elapsed time into minutes, seconds
    minutes = int(elapsed_time // 60)
    seconds = round(elapsed_time % 60, 2)
    
    # Print the speed of the Code
    print(f"{name} finished in {minutes} min {seconds} sec")


def free_predictor():
    global predictor
    predictor = None
    if torch.cuda.is_available:
        torch.cuda.empty_cache()










class MaskGenControls(bpy.types.PropertyGroup):
    def update_mask_options(self, context):
    
        space = bpy.context.space_data
        
        # Create an lists to store the images
        possible_mask = []
        options = []
        
        if space.image is not None:
            name = space.image.name_full

            # Get a list of all images
            images = bpy.data.images

            # Iterate over the images
            for img in images:
                # If the image name starts with the same as the open image, add it to the image list
                if img.name_full.startswith(name.rsplit('.', 1)[0]) and img.name_full != name:
                    possible_mask.append(img.name_full)


            # Change the format to option tuples
            for element in possible_mask:
                options.append((element, element, 'Use the Mask "' + element + '"'))

        options.append(('new', 'New Mask', 'Create a new Mask'))
        return options
    
    used_mask : bpy.props.EnumProperty(
        name = "Used Mask",
        items = update_mask_options
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
    
    manual_tracking : bpy.props.BoolProperty(
        name = "Manual animated mask input",
        default = False
    ) # type: ignore
    
    search_radius : bpy.props.FloatProperty(
        name = "Search Radius",
        default = 10
    ) # type: ignore






class CreateMaskOperator(bpy.types.Operator):
    """Generates a mask"""
    bl_idname = "rotoforge.create_mask"
    bl_label = "Create Mask"
    bl_options = {'REGISTER', 'UNDO'}
    

    def execute(self, context):
        space = context.space_data
        mask = space.mask
        image = space.image
        maskgencontrols = context.scene.rotoforge_maskgencontrols
        
        #Wake AI if not present
        global predictor
        global used_model
        
        
        if predictor == None or used_model != maskgencontrols.used_model:
            # Start the timer
            fetching = process_time()
            used_model = maskgencontrols.used_model
            predictor = generate_masks.get_predictor(model_type=used_model)
            time_checkpoint(fetching, 'Predictor fetching')
        
        # Start the timer
        start = process_time()
        
        #Get Prompt data to feed the machine god
        resolution = tuple(image.size)
        guide_mask, polygons = prompt_utils.rasterize_mask(mask, resolution)
        prompt_points, prompt_labels = prompt_utils.extract_prompt_points(mask, resolution)
        bounding_box = prompt_utils.calculate_bounding_box(polygons, None)
        
        guide_strength = maskgencontrols.guide_strength
        
        used_mask = maskgencontrols.used_mask
        
        generate_masks.generate_mask(source_image = image, 
                                     used_mask = used_mask, 
                                     predictor = predictor, 
                                     guide_mask = guide_mask, 
                                     guide_strength = guide_strength,
                                     input_points = prompt_points,
                                     input_labels = prompt_labels,
                                     input_box = bounding_box,
                                     debug_logits = False)
        time_checkpoint(start, 'Mask generation')
        return {'FINISHED'}



class TrackMaskOperator(bpy.types.Operator):
    """Tracks a mask"""
    bl_idname = "rotoforge.track_mask"
    bl_label = "Track Mask"
    bl_options = {'REGISTER', 'UNDO'}
    
    
    _timer = None
    
    #Prompt data for the machine god
    resolution = None
    guide_mask, polygons = None, None
    prompt_points, prompt_labels = None, None
    bounding_box = None
    guide_strength = None
    search_radius = None
    manual_tracking = None
    
    @classmethod
    def poll(self, context):
        return context.space_data.image.source in ['SEQUENCE', 'MOVIE']
    
    def modal(self, context, event):
        if event.type in ['ESC', 'RIGHTMOUSE']:
            self.cancel(context)
            return {'CANCELLED'}
        
        if event.type == 'TIMER':
            space = context.space_data
            mask = space.mask
            image = space.image
            maskgencontrols = context.scene.rotoforge_maskgencontrols

            # Force-update the viewport for internal use
            space.display_channels = space.display_channels


            print('----Info----')
            print('Frame: ' + str(context.scene.frame_current))


            #Wake AI if not present
            global predictor
            global used_model

            if maskgencontrols.manual_tracking:
                #Get Prompt data to feed the machine god
                self.resolution = tuple(image.size)
                self.guide_mask, self.polygons = prompt_utils.rasterize_mask(mask, self.resolution)
                self.prompt_points, self.prompt_labels = prompt_utils.extract_prompt_points(mask, self.resolution)
                self.bounding_box = prompt_utils.calculate_bounding_box(self.polygons, None)

                self.guide_strength = maskgencontrols.guide_strength
                self.search_radius = maskgencontrols.search_radius

            used_mask = maskgencontrols.used_mask

            self.guide_mask, self.prompt_points, self.prompt_labels, self.bounding_box, input_logits = generate_masks.track_mask(source_image = image, 
                                                                                                                                 used_mask = used_mask, 
                                                                                                                                 predictor = predictor, 
                                                                                                                                 guide_mask = self.guide_mask, 
                                                                                                                                 guide_strength = self.guide_strength, 
                                                                                                                                 search_radius = self.search_radius,
                                                                                                                                 input_points = self.prompt_points,
                                                                                                                                 input_labels = self.prompt_labels,
                                                                                                                                 input_box = self.bounding_box,
                                                                                                                                 input_logits = None)
            
            
            if context.scene.frame_current  == context.scene.frame_end:
                self.cancel(context)
                return{'CANCELLED'}
            else:
                context.scene.frame_current = context.scene.frame_current+1
                return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def execute(self, context):
        wm = context.window_manager
        # Modal Operator run
        self._timer = wm.event_timer_add(0.00001, window=context.window)
        wm.modal_handler_add(self)
        
        space = context.space_data
        mask = space.mask
        image = space.image
        maskgencontrols = context.scene.rotoforge_maskgencontrols
        
        #Wake AI if not present
        global predictor
        global used_model
        
        if predictor == None or used_model != maskgencontrols.used_model:
            used_model = maskgencontrols.used_model
            predictor = generate_masks.get_predictor(model_type=used_model)
        
        #Get Prompt data to feed the machine god
        self.resolution = tuple(image.size)

        self.guide_mask, self.polygons = prompt_utils.rasterize_mask(mask, self.resolution)

        self.prompt_points, self.prompt_labels = prompt_utils.extract_prompt_points(mask, self.resolution)

        self.bounding_box = prompt_utils.calculate_bounding_box(self.polygons, None)

        self.guide_strength = maskgencontrols.guide_strength
        self.search_radius = maskgencontrols.search_radius
        
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        
        space = context.space_data
        image = space.image
        maskgencontrols = context.scene.rotoforge_maskgencontrols
        used_mask = maskgencontrols.used_mask
        generate_masks.load_sequential_mask(image, used_mask)
        
        # Release prompt data
        self.resolution = None
        self.guide_mask, self.polygons = None, None
        self.prompt_points, self.prompt_labels = None, None
        self.bounding_box = None
        self.guide_strength = None
        self.search_radius = None
        self.manual_tracking = None
        print("Quitting...")



class FreePredictorOperator(bpy.types.Operator):
    """Frees the Predictor from GPU memory"""
    bl_idname = "rotoforge.free_predictor"
    bl_label = "Free Cache"
    bl_options = {'REGISTER', 'UNDO'}
    

    def execute(self, context):
        free_predictor()
        return {'FINISHED'}



class RotoForgePanel(bpy.types.Panel):
    """RotoForge Panel"""
    bl_label = "RotoForge"
    bl_idname = "ROTOFORGE_PT_RotoForgePanel"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "RotoForge"
    
    @classmethod
    def poll(self, context):
        return context.space_data.mode == 'MASK'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rotoforge_props = scene.rotoforge_maskgencontrols
        
        #Props
        layout.prop(rotoforge_props, "used_model")
        layout.prop(rotoforge_props, "guide_strength")
        layout.separator()
        layout.prop(rotoforge_props, "manual_tracking")
        layout.prop(rotoforge_props, "search_radius")
        layout.separator()
        layout.prop(rotoforge_props, "used_mask")
        
        #Big fat button
        run_button = layout.row()
        run_button.scale_y = 3.0
        run_button.operator("rotoforge.create_mask", text="Create Mask")
        
        # Smaller Buttons for less important stuff
        layout.operator("rotoforge.track_mask", text="Track Mask Forwards")
        layout.operator("rotoforge.free_predictor", text="Free Cache")


properties = [MaskGenControls]
classes = [
           CreateMaskOperator,
           TrackMaskOperator,
           FreePredictorOperator,
           RotoForgePanel
           ]

def register():
    for cls in properties:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.rotoforge_maskgencontrols = bpy.props.PointerProperty(type=MaskGenControls)
    
    for cls in classes:
        bpy.utils.register_class(cls)
        
    return {'REGISTERED'}

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.rotoforge_maskgencontrols
    
    for cls in properties:
        bpy.utils.unregister_class(cls)
        
    return {'UNREGISTERED'}