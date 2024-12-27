import bpy

from time import process_time

try:
    from . import generate_masks
    from . import prompt_utils
    from . import overlay
    from . import mask_rasterize
    from . import data_manager
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
    from torch import cuda
    if cuda.is_available:
        cuda.empty_cache()
    del cuda






class GenerateSingularMaskOperator(bpy.types.Operator):
    """Generates a singular .png mask"""
    bl_idname = "rotoforge.generate_singular_mask"
    bl_label = "Generate Mask"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(self, context):
        if context.space_data.image is None:
            return False
        return True

    def execute(self, context):
        space = context.space_data
        mask = space.mask
        layer = mask.layers.active
        image = space.image
        maskgencontrols = mask.rotoforge_maskgencontrols[layer.name]
        
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
        guide_mask = mask_rasterize.rasterize_layer_of_active_mask(layer, resolution)
        prompt_points, prompt_labels = prompt_utils.extract_prompt_points(mask, resolution)
        bounding_box = prompt_utils.calculate_bounding_box(guide_mask)
        
        guide_strength = maskgencontrols.guide_strength
        blur_radius = maskgencontrols.feather_radius
        
        used_mask = f"{mask.name}/MaskLayers/{layer.name}"
        
        generate_masks.generate_mask(source_image = image, 
                                     used_mask = used_mask, 
                                     predictor = predictor, 
                                     guide_mask = guide_mask, 
                                     guide_strength = guide_strength,
                                     blur_radius= blur_radius,
                                     input_points = prompt_points,
                                     input_labels = prompt_labels,
                                     input_box = bounding_box,
                                     debug_logits = False)
        data_manager.update_maskseq(used_mask)
        
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
    guide_mask = None
    prompt_points, prompt_labels = None, None
    bounding_box = None
    
    
    backwards: bpy.props.BoolProperty(
        name="Backwards",
        description="Tracks backwards",
        default=False
    ) # type: ignore
    
    
    @classmethod
    def poll(self, context):
        if context.space_data.image is None:
            return False
        if context.space_data.image.source not in ['SEQUENCE', 'MOVIE']:
            return False
        return True
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            
            space = context.space_data
            mask = space.mask
            layer = mask.layers.active
            image = space.image
            maskgencontrols = mask.rotoforge_maskgencontrols[layer.name]
            
            # Apply frame
            context.scene.frame_current = self._next_processed_frame 
            space.image_user.frame_current = self._next_processed_frame
            
            # Force-update the viewport for internal use
            space.display_channels = space.display_channels


            print('----Info----')
            print('Frame: ', str(self._next_processed_frame))


            #Wake AI if not present
            global predictor
            global used_model

            if not maskgencontrols.tracking:
                #Get Prompt data to feed the machine god
                resolution = tuple(image.size)
                self.guide_mask = mask_rasterize.rasterize_layer_of_active_mask(layer, resolution)
                self.prompt_points, self.prompt_labels = prompt_utils.extract_prompt_points(mask, resolution)
                self.bounding_box = prompt_utils.calculate_bounding_box(self.guide_mask)

            
            guide_strength = maskgencontrols.guide_strength
            search_radius = maskgencontrols.search_radius
            blur_radius = maskgencontrols.feather_radius

            used_mask = self._used_mask_dir

            self.guide_mask, self.prompt_points, self.prompt_labels, self.bounding_box, input_logits = generate_masks.track_mask(source_image = image, 
                                                                                                                                 used_mask = used_mask, 
                                                                                                                                 predictor = predictor, 
                                                                                                                                 guide_mask = self.guide_mask, 
                                                                                                                                 guide_strength = guide_strength, 
                                                                                                                                 blur_radius=blur_radius,
                                                                                                                                 search_radius = search_radius,
                                                                                                                                 input_points = self.prompt_points,
                                                                                                                                 input_labels = self.prompt_labels,
                                                                                                                                 input_box = self.bounding_box,
                                                                                                                                 input_logits = None)

            if not self.backwards:
                endframe = mask.frame_end
            else:
                endframe = mask.frame_start
            
            if self._next_processed_frame  == endframe:
                self.cancel(context)
                return{'CANCELLED'}
            else:
                if not self.backwards: # Track last processed frame
                    self._next_processed_frame += 1
                else:
                    self._next_processed_frame -= 1
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
            maskgencontrols = mask.rotoforge_maskgencontrols[layer.name]

            #Wake AI if not present
            global predictor
            global used_model

            if predictor == None or used_model != maskgencontrols.used_model:
                used_model = maskgencontrols.used_model
                predictor = generate_masks.get_predictor(model_type=used_model)

            #Get Prompt data to feed the machine god
            resolution = tuple(image.size)
            self.guide_mask = mask_rasterize.rasterize_layer_of_active_mask(layer, resolution)
            self.prompt_points, self.prompt_labels = prompt_utils.extract_prompt_points(mask, resolution)
            self.bounding_box = prompt_utils.calculate_bounding_box(self.guide_mask)

            
            # Get the folder to write to
            used_mask = f"{mask.name}/MaskLayers/{layer.name}"
            self._used_mask_dir = used_mask
            
            
            self._next_processed_frame = context.scene.frame_current # Set last processed frame
            self._running = True
            context.window_manager.modal_handler_add(self)
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}
    
    def cancel(self, context):
        
        context.window_manager.event_timer_remove(self._timer)
        self._running = False
        
        overlay.rotoforge_overlay_shader.custom_img = None
        data_manager.update_maskseq(self._used_mask_dir)
        overlaycontrols = context.scene.rotoforge_overlaycontrols
        overlaycontrols.used_mask = self._used_mask_dir
        
        
        # Stop on the last done frame
        context.scene.frame_current = self._next_processed_frame

        # Release prompt data
        self.guide_mask = None
        self.prompt_points, self.prompt_labels = None, None
        self.bounding_box = None
        
        self.report({'INFO'}, f'Saved mask layer as image sequence: {self._used_mask_dir}')
        print("Quitting...")
        
        

class MergeMaskOperator(bpy.types.Operator):
    """Rasterizes all masks down to image"""
    bl_idname = "rotoforge.merge_mask"
    bl_label = "Bake Mask to Texture"
    bl_options = {'REGISTER', 'UNDO'}
    
    _timer = None
    _next_processed_frame = None
    _used_mask_dir = None
    _running = False
    
    @classmethod
    def poll(self, context):
        if context.space_data.image is None:
            return False
        return True
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            
            space = context.space_data
            mask = space.mask
            image = space.image
            
            # Apply frame
            context.scene.frame_current = self._next_processed_frame 
            space.image_user.frame_current = self._next_processed_frame

            print('----Info----')
            print('Frame: ', str(self._next_processed_frame))

            used_mask = self._used_mask_dir
            img = mask_rasterize.rasterize_active_mask()
            overlay.rotoforge_overlay_shader.custom_img = img
            generate_masks.save_sequential_mask(image, used_mask, img, None)
            
            if self._next_processed_frame  == mask.frame_end:
                self.cancel(context)
                return{'CANCELLED'}
            else:
                self._next_processed_frame += 1
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

            #Get Prompt data to feed the machine god
            self.resolution = tuple(image.size)

            
            # Get the folder to write to
            used_mask = f"{mask.name}/Combined"
            self._used_mask_dir = used_mask
            
            self._next_processed_frame = mask.frame_start # Set last processed frame
            self._running = True
            context.window_manager.modal_handler_add(self)
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}
    
    def cancel(self, context):
        
        context.window_manager.event_timer_remove(self._timer)
        self._running = False
        
        overlay.rotoforge_overlay_shader.custom_img = None
        data_manager.update_maskseq(self._used_mask_dir)
        overlaycontrols = context.scene.rotoforge_overlaycontrols
        overlaycontrols.used_mask = self._used_mask_dir
        
        
        # Stop on the last done frame
        context.scene.frame_current = self._next_processed_frame
        
        # Release prompt data
        self.resolution = None
        self.tracking = None
        
        self.report({'INFO'}, f'Saved combined mask as image sequence: {self._used_mask_dir}')
        print("Quitting...")



class ImportMaskNodeOperator(bpy.types.Operator):
    """Imports a Mask as a texture node"""
    bl_idname = "rotoforge.import_mask_node"
    bl_label = "Import Mask"
    bl_options = {'REGISTER', 'UNDO'}
    
    mouse_pos = (0,0)
    
    @classmethod
    def poll(self, context):
        if context.space_data.node_tree is None or context.scene.rotoforge_importcontrols.used_mask == '':
            return False
        return True

    def invoke(self, context, event):
        self.mouse_pos = (event.mouse_region_x, event.mouse_region_y)
        return self.execute(context)
    
    def execute(self, context):
        # Error for non-existent node-tree
        nodetree = context.space_data.node_tree
        import_props = context.scene.rotoforge_importcontrols
        region = context.region
        view2d = region.view2d

        # Get info
        def get_selected(nodetree):
            select = False
            for node in nodetree.nodes:
                if select == False:
                    select = node.select
            return select

        bpy.ops.node.select_all(action='DESELECT')
        while get_selected(nodetree) and nodetree.nodes.active and nodetree.nodes.active.type == 'GROUP':
            nodetree = nodetree.nodes.active.node_tree

        used_mask = bpy.data.masks[import_props.used_mask]
        used_mask_img = bpy.data.images[f"{import_props.used_mask}/Combined"]

        # Add node
        nodetree_type = nodetree.type
        
        match nodetree_type:
            case 'COMPOSITING':
                bpy.ops.node.add_node(type='CompositorNodeImage')
                node = nodetree.nodes.active
                node.image = used_mask_img
                node.use_auto_refresh = True
                node.frame_duration = used_mask.frame_end
            case 'SHADER':
                bpy.ops.node.add_node(type='ShaderNodeTexImage')
                node = nodetree.nodes.active
                node.image = used_mask_img
                node.image_user.use_auto_refresh = True
                node.image_user.frame_duration = used_mask.frame_end
            case 'GEOMETRY':
                bpy.ops.node.add_node(type='GeometryNodeImageTexture')
                node = nodetree.nodes.active
                node.inputs['Image'].default_value = used_mask_img
            case _:
                raise Exception("Unknown nodetree type: ", nodetree_type)

        ui_scale = context.preferences.system.ui_scale
        x, y = view2d.region_to_view(self.mouse_pos[0], self.mouse_pos[1])
        node.location = x / ui_scale, y / ui_scale
        
        # Make the node stick to the cursor
        bpy.ops.node.translate_attach_remove_on_cancel('INVOKE_DEFAULT')
        return {'FINISHED'}



class MaskRangeToSceneOperator(bpy.types.Operator):
    """Set the mask range to the scene range"""
    bl_idname = "rotoforge.set_mask_range_to_scene"
    bl_label = "Set Scene Frames"
    bl_options = {'REGISTER', 'UNDO'}
    

    def execute(self, context):
        scene = context.scene
        mask = context.space_data.mask
        mask.frame_start = scene.frame_start
        mask.frame_end = scene.frame_end
        return {'FINISHED'}



class FreePredictorOperator(bpy.types.Operator):
    """Frees the predictor from GPU memory"""
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

        space_data = context.space_data
        mask = space_data.mask
        active_layer = mask.layers.active

        row = layout.split(factor=0.4)
        row.operator("rotoforge.set_mask_range_to_scene")
        sub = row.row(align=True)
        sub.use_property_split = False
        sub.prop(mask, "frame_start", text="Start")
        sub.prop(mask, "frame_end", text="End")
        layout.operator("rotoforge.merge_mask", icon='RENDER_RESULT')
        
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
            rotoforge_props = mask.rotoforge_maskgencontrols[active_layer.name]
            sub.separator()
            
            sub.operator("mask.layer_move", icon='TRIA_UP', text="").direction = 'UP'
            sub.operator("mask.layer_move", icon='TRIA_DOWN', text="").direction = 'DOWN'

            # blending
            row = layout.row(align=True)
            row.prop(active_layer, "alpha")
            row.prop(active_layer, "invert", text="", icon='IMAGE_ALPHA')
            
            layout.prop(active_layer, "blend")
            
            # RotoForge layer
            layout.prop(rotoforge_props, "is_rflayer")
            layout.separator()
            if rotoforge_props.is_rflayer:
                pass
            else:
                layout.prop(active_layer, "falloff")
                
                col = layout.column()
                col.prop(active_layer, "use_fill_overlap", text="Overlap")
                col.prop(active_layer, "use_fill_holes", text="Holes")



class RotoForgeMaskPanel(bpy.types.Panel):
    """RotoForge Mask Panel"""
    bl_label = "RotoForge"
    bl_idname = "ROTOFORGE_PT_RotoForgeMaskPanel"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "RotoForge"
    
    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        if (space_data.mask) and (space_data.mask.layers.active is not None) and (space_data.mode == 'MASK'):
            mask = space_data.mask
            active_layer = mask.layers.active
            is_rflayer = mask.rotoforge_maskgencontrols[active_layer.name].is_rflayer
            return is_rflayer
        return False
    
    def draw(self, context):
        layout = self.layout
        space_data = context.space_data
        mask = space_data.mask
        active_layer = mask.layers.active
        rotoforge_props = mask.rotoforge_maskgencontrols[active_layer.name]
        
        
        # Global Settings
        global_settings = layout.box()
        global_settings.label(text="Global Settings")
        global_settings.prop(rotoforge_props, "used_model")
        global_settings.prop(rotoforge_props, "guide_strength")
        global_settings.prop(rotoforge_props, "feather_radius")
        layout.separator()
        
        
        # Tracking Settings
        tracking_settings = layout.box()
        tracking_settings.label(text="Tracking Settings")
        tracking_settings.prop(rotoforge_props, "tracking")
        tracking_settings.prop(rotoforge_props, "search_radius")
        layout.separator()
        
        
        # Generation buttons
        box = layout.box()
        box.label(text="Generation")
        #   Static Mask
        row = box.row(align=True)
        row.label(text="Static:")
        row = row.row(align=True)
        row.alignment = 'RIGHT'
        op = row.operator("rotoforge.generate_singular_mask", text="Generate", icon='IMAGE_PLANE')
        #   Animated Mask
        row = box.row(align=True)
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
        
        if hasattr(active_layer, 'splines'):
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



class NodeImportControls(bpy.types.PropertyGroup):
    # Define the property directly within the Panel class
    def update_mask_options(self, context):
        possible_mask = []
        for mask in bpy.data.masks:
            image_name = f"{mask.name}/Combined"
            if image_name in bpy.data.images:
                possible_mask.append(mask.name)
        return [(element, element, f'Import the mask "{element}"') for element in possible_mask]
    
    used_mask : bpy.props.EnumProperty(
        name="Used Mask",
        items=update_mask_options
    ) # type: ignore
    
    @classmethod 
    def register(cls):
        bpy.types.Scene.rotoforge_importcontrols = bpy.props.PointerProperty(type=cls)
    
    @classmethod
    def unregister(cls):
        if hasattr(bpy.types.Scene, 'rotoforge_importcontrols'):
            del bpy.types.Scene.rotoforge_importcontrols
    
class RotoForgeNodePanel(bpy.types.Panel):
    """RotoForge Node Panel"""
    bl_label = "RotoForge"
    bl_idname = "ROTOFORGE_PT_RotoForgeNodePanel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "RotoForge"
    bl_context = "node_editor"
    
    def draw(self, context):
        layout = self.layout
        space_data = context.space_data
        import_props = bpy.context.scene.rotoforge_importcontrols
        
        layout.prop(import_props, 'used_mask')
        layout.operator('rotoforge.import_mask_node')





classes = [NodeImportControls,
           GenerateSingularMaskOperator,
           TrackMaskOperator,
           MergeMaskOperator,
           ImportMaskNodeOperator,
           MaskRangeToSceneOperator,
           FreePredictorOperator,
           LayerPanel,
           RotoForgeMaskPanel,
           RotoForgeNodePanel
           ]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    return {'REGISTERED'}

def unregister():
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
        
    return {'UNREGISTERED'}