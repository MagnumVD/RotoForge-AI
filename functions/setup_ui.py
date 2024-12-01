import bpy

import os
from time import process_time

try:
    import torch
    from . import generate_masks
    from . import prompt_utils
    from . import overlay
except:
    pass

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






class GenerateSingularMaskOperator(bpy.types.Operator):
    """Generates a singular .png mask"""
    bl_idname = "rotoforge.generate_singular_mask"
    bl_label = "Generate Mask"
    bl_options = {'REGISTER', 'UNDO'}
    

    def execute(self, context):
        space = context.space_data
        mask = space.mask
        layer = mask.layers.active
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
        guide_mask, polygons = prompt_utils.rasterize_mask_layer(layer, resolution)
        prompt_points, prompt_labels = prompt_utils.extract_prompt_points(mask, resolution)
        bounding_box = prompt_utils.calculate_bounding_box(polygons, None)
        
        guide_strength = maskgencontrols.guide_strength
        
        used_mask = f"{mask.name}.{layer.name}.layer"
        
        generate_masks.generate_mask(source_image = image, 
                                     used_mask = used_mask, 
                                     predictor = predictor, 
                                     guide_mask = guide_mask, 
                                     guide_strength = guide_strength,
                                     input_points = prompt_points,
                                     input_labels = prompt_labels,
                                     input_box = bounding_box,
                                     debug_logits = False)
        
        self.report({'INFO'}, f'Saved mask layer as image: {used_mask}')
        
        time_checkpoint(start, 'Mask generation')
        return {'FINISHED'}
    
    def invoke(self, context, event):
        if context.space_data.image.source in ['SEQUENCE', 'MOVIE']:
            wm = context.window_manager
            return wm.invoke_confirm(self, event, title="This file is animated!", message="You're currently trying to create a static (not animated) mask based on animated footage. Do you wish to continue?", confirm_text="Process anyways", translate=True)
        return self.execute(context)



class TrackMaskOperator(bpy.types.Operator):
    """Tracks a mask"""
    bl_idname = "rotoforge.track_mask"
    bl_label = "Track Mask"
    bl_options = {'REGISTER', 'UNDO'}
    
    
    _timer = None
    _next_processed_frame = None
    _used_mask_dir = None
    _running = False
    
    #Prompt data for the machine god
    resolution = None
    guide_mask, polygons = None, None
    prompt_points, prompt_labels = None, None
    bounding_box = None
    guide_strength = None
    search_radius = None
    tracking = None
    
    
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
            layer = mask.layers.active
            image = space.image
            maskgencontrols = context.scene.rotoforge_maskgencontrols

            # Force-update the viewport for internal use
            space.display_channels = space.display_channels


            print('----Info----')
            print('Frame: ', str(self._next_processed_frame))


            #Wake AI if not present
            global predictor
            global used_model

            if not maskgencontrols.tracking:
                #Get Prompt data to feed the machine god
                self.resolution = tuple(image.size)
                self.guide_mask, self.polygons = prompt_utils.rasterize_mask_layer(layer, self.resolution)
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
            
            if self._next_processed_frame  == endframe:
                self.cancel(context)
                return{'CANCELLED'}
            else:
                if not self.backwards: # Track last processed frame
                    self._next_processed_frame += 1
                else:
                    self._next_processed_frame -= 1
                context.scene.frame_current = self._next_processed_frame # Apply frame
                return {'PASS_THROUGH'}
        
        
        if event.type in ['ESC', 'RIGHTMOUSE']:
            self.cancel(context)
            return {'CANCELLED'}
        
        return {'PASS_THROUGH'}

    def execute(self, context):
        if not self._running:
            space = context.space_data
            mask = space.mask
            layer = mask.layers.active
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
            self.guide_mask, self.polygons = prompt_utils.rasterize_mask_layer(layer, self.resolution)
            self.prompt_points, self.prompt_labels = prompt_utils.extract_prompt_points(mask, self.resolution)
            self.bounding_box = prompt_utils.calculate_bounding_box(self.polygons, None)
            self.guide_strength = maskgencontrols.guide_strength
            self.search_radius = maskgencontrols.search_radius

            
            # Get the folder to write to
            used_mask = f"{mask.name}.{layer.name}.layer"
            # Get next free index by searching in '//RotoForge masksequences'
            rotoforge_directory = bpy.path.abspath('//RotoForge masksequences')
            
            if not os.path.exists(rotoforge_directory):
                os.makedirs(rotoforge_directory)
            
            self._used_mask_dir = used_mask
            
            
            self._next_processed_frame = context.scene.frame_current # Set last processed frame
            self._running = True
            context.window_manager.modal_handler_add(self)
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}

    def invoke(self, context, event):
        if bpy.data.is_saved == False:
            wm = context.window_manager
            return wm.invoke_confirm(self, event, title="This file is not saved!", message="The masks will be saved in a temporary folder which will get cleared once you exit blender (even in the case of a crash). Do you wish to continue?", confirm_text="Process anyways", translate=True)
        return self.execute(context)
    
    def cancel(self, context):
        
        context.window_manager.event_timer_remove(self._timer)
        self._running = False
        
        overlay.rotoforge_overlay_shader.custom_img = None
        generate_masks.load_sequential_mask(self._used_mask_dir)
        overlaycontrols = context.scene.rotoforge_overlaycontrols
        overlaycontrols.used_mask = self._used_mask_dir
        
        
        # Stop on the last done frame
        context.scene.frame_current = self._next_processed_frame

        # Release prompt data
        self.resolution = None
        self.guide_mask, self.polygons = None, None
        self.prompt_points, self.prompt_labels = None, None
        self.bounding_box = None
        self.guide_strength = None
        self.search_radius = None
        self.tracking = None
        
        self.report({'INFO'}, f'Saved mask layer as image sequence: {self._used_mask_dir}')
        print("Quitting...")



class FreePredictorOperator(bpy.types.Operator):
    """Frees the Predictor from GPU memory"""
    bl_idname = "rotoforge.free_predictor"
    bl_label = "Free Cache"
    bl_options = {'REGISTER', 'UNDO'}
    

    def execute(self, context):
        free_predictor()
        return {'FINISHED'}



class LayerPanel(bpy.types.Panel):
    """Mask Layers"""
    bl_label = "Mask Layers"
    bl_idname = "ROTOFORGE_PT_LayerPanel"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "RotoForge"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data.mask and space_data.mode == 'MASK'

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        sc = context.space_data
        mask = sc.mask
        active_layer = mask.layers.active

        rows = 4 if active_layer else 1

        row = layout.row()
        row.template_list(
            "MASK_UL_layers", "", mask, "layers",
            mask, "active_layer_index", rows=rows,
        )

        sub = row.column(align=True)

        sub.operator("mask.layer_new", icon='ADD', text="")
        sub.operator("mask.layer_remove", icon='REMOVE', text="")

        if active_layer:
            sub.separator()

            sub.operator("mask.layer_move", icon='TRIA_UP', text="").direction = 'UP'
            sub.operator("mask.layer_move", icon='TRIA_DOWN', text="").direction = 'DOWN'

            # blending
            row = layout.row(align=True)
            row.prop(active_layer, "alpha")
            row.prop(active_layer, "invert", text="", icon='IMAGE_ALPHA')

            layout.prop(active_layer, "blend")
            layout.prop(active_layer, "falloff")

            col = layout.column()
            col.prop(active_layer, "use_fill_overlap", text="Overlap")
            col.prop(active_layer, "use_fill_holes", text="Holes")



class RotoForgePanel(bpy.types.Panel):
    """RotoForge Panel"""
    bl_label = "RotoForge"
    bl_idname = "ROTOFORGE_PT_RotoForgePanel"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "RotoForge"
    
    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return (space_data.mask) and (space_data.mask.layers.active is not None) and (space_data.mode == 'MASK')
    
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
        tracking_settings.prop(rotoforge_props, "tracking")
        tracking_settings.prop(rotoforge_props, "search_radius")
        layout.separator()
        
        
        # Generation buttons
        column = layout.box()
        column.label(text="Generation")
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
        spline_settings = layout.box()
        spline_settings.label(text="Active Spline Settings")
        
        if hasattr(context.edit_mask.layers.active, 'splines'):
            active_mask_spline = context.edit_mask.layers.active.splines.active
        else:
            active_mask_spline = None
        
        if active_mask_spline is not None:
            spline_settings.prop(active_mask_spline, "use_cyclic", text="🗹Boundary|🗷Prompt points")
            if not active_mask_spline.use_cyclic:
                spline_settings.prop(active_mask_spline, "use_fill", text="🗹Mask|🗷Background")
        else:
            spline_settings.label(text="No active spline detected")
        layout.separator()



properties = []
classes = [GenerateSingularMaskOperator,
           TrackMaskOperator,
           FreePredictorOperator,
           LayerPanel,
           RotoForgePanel
           ]

def register():
    for cls in properties:
        bpy.utils.register_class(cls)
    
    for cls in classes:
        bpy.utils.register_class(cls)
        
    return {'REGISTERED'}

def unregister():
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    
    for cls in properties:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
        
    return {'UNREGISTERED'}