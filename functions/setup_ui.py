import bpy
import os
from time import process_time

import torch
from . import generate_masks
from . import prompt_utils
from . import overlay

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






class GenerateSingularMaskOperator(bpy.types.Operator):
    """Generates a singular .png mask"""
    bl_idname = "rotoforge.generate_singular_mask"
    bl_label = "Generate Mask"
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
    _last_processed_frame = None
    _used_mask_dir = None
    _running = False
    
    #Prompt data for the machine god
    resolution = None
    guide_mask, polygons = None, None
    prompt_points, prompt_labels = None, None
    bounding_box = None
    guide_strength = None
    search_radius = None
    manual_tracking = None
    
    
    backwards: bpy.props.BoolProperty(
        name="Backwards",
        description="Tracks backwards",
        default=False
    ) # type: ignore
    
    
    @classmethod
    def poll(self, context):
        return context.space_data.image.source in ['SEQUENCE', 'MOVIE']
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            
            space = context.space_data
            mask = space.mask
            image = space.image
            maskgencontrols = context.scene.rotoforge_maskgencontrols

            # Force-update the viewport for internal use
            space.display_channels = space.display_channels


            print('----Info----')
            print('Frame: ' + str(self._last_processed_frame))


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

            used_mask = self._used_mask_dir

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

            if not self.backwards:
                endframe = context.scene.frame_end
            else:
                endframe = context.scene.frame_start
            
            if self._last_processed_frame  == endframe:
                self.cancel(context)
                return{'CANCELLED'}
            else:
                if not self.backwards: # Track last processed frame
                    self._last_processed_frame += 1
                else:
                    self._last_processed_frame -= 1
                context.scene.frame_current = self._last_processed_frame # Apply frame
                return {'PASS_THROUGH'}
        
        
        if event.type in ['ESC', 'RIGHTMOUSE']:
            self.cancel(context)
            return {'CANCELLED'}
        
        return {'PASS_THROUGH'}

    def execute(self, context):
        if not self._running:
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

            
            # Get the folder to write to
            used_mask = maskgencontrols.used_mask
            if used_mask == 'new':
                folder = image.name

                # Get next free index by searching in '//RotoForge masksequences'
                rotoforge_directory = bpy.path.abspath('//RotoForge masksequences')
                if not os.path.exists(rotoforge_directory):
                    os.makedirs(rotoforge_directory)
                indices = []
                for mask_dir in os.listdir(rotoforge_directory):
                    indices.append(int(mask_dir[mask_dir.rfind('_mask.')+6:mask_dir.rfind('.')]))

                index = 1
                while index in indices:
                    index += 1

                index = '{:03}'.format(index) # Makes sure that there are 3 characters: 5 -> 005

                # Get save folder
                if folder.rfind('.') == -1:
                    self._used_mask_dir = folder + '_mask.' + index
                else:
                    self._used_mask_dir = folder[:folder.rfind('.')] + '_mask.' + index + folder[folder.rfind('.'):]
            else:
                self._used_mask_dir = used_mask
            
            
            self._last_processed_frame = context.scene.frame_current # Set last processed frame
            self._running = True
            context.window_manager.modal_handler_add(self)
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
            return {'RUNNING_MODAL'}
        else:
            self.cancel(context)
            return {'CANCELLED'}

    def cancel(self, context):
        
        context.window_manager.event_timer_remove(self._timer)
        self._running = False
        
        overlay.rotoforge_overlay_shader.custom_img = None
        generate_masks.load_sequential_mask(self._used_mask_dir)
        maskgencontrols = context.scene.rotoforge_maskgencontrols
        maskgencontrols.used_mask = self._used_mask_dir
        overlaycontrols = context.scene.rotoforge_overlaycontrols
        overlaycontrols.used_mask = self._used_mask_dir
        
        
        # Stop on the last done frame
        context.scene.frame_current = self._last_processed_frame

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
        
        
        # Global Settings
        global_settings = layout.box()
        global_settings.label(text="Global Settings")
        global_settings.prop(rotoforge_props, "used_model")
        global_settings.prop(rotoforge_props, "guide_strength")
        layout.separator()
        
        
        # Tracking Settings
        tracking_settings = layout.box()
        tracking_settings.label(text="Tracking Settings")
        tracking_settings.prop(rotoforge_props, "manual_tracking")
        tracking_settings.prop(rotoforge_props, "search_radius")
        layout.separator()
        
        
        # Generation buttons
        column = layout.box()
        column.label(text="Generation")
        column.prop(rotoforge_props, "used_mask")
        #   Static Mask
        row = column.row(align=True)
        row.label(text="Static:")
        row = row.row(align=True)
        row.alignment = 'RIGHT'
        op = row.operator("rotoforge.generate_singular_mask", text="Generate", icon='IMAGE_PLANE')
        #   Animated Mask
        row = column.row(align=True)
        row.label(text="Animated:")
        row.scale_x = 2.0
        op = row.operator("rotoforge.track_mask", text="", icon='TRACKING_BACKWARDS')
        op.backwards = True
        op = row.operator("rotoforge.track_mask", text="", icon='TRACKING_FORWARDS')
        op.backwards = False
        
        layout.separator()
        
        
        # Free Cache button
        layout.operator("rotoforge.free_predictor", text="Free Cache", icon='TRASH')
        layout.separator()
        
        
        # Active Spline Settings
        active_mask_spline = context.edit_mask.layers.active.splines.active
        spline_settings = layout.box()
        spline_settings.label(text="Active Spline Settings")
        if active_mask_spline is not None:
            spline_settings.prop(active_mask_spline, "use_cyclic", text="🗹Boundary|🗷Prompt points")
            if not active_mask_spline.use_cyclic:
                spline_settings.prop(active_mask_spline, "use_fill", text="🗹Mask|🗷Background")
        else:
            spline_settings.label(text="No active spline detected")
        layout.separator()
        







properties = [MaskGenControls]
classes = [GenerateSingularMaskOperator,
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