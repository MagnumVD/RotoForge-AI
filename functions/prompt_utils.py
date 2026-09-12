import bpy

exception = None
try:
    import numpy as np
    import PIL.Image

    from time import process_time

    from . import generate_masks
    from . import prompt_utils
    from . import overlay
    from . import mask_rasterize
    from . import data_manager
except Exception as e:
    exception = e

predictor = None
used_model = None

def calculate_bounding_box(mask):
    if np.sum(mask) == 0:
        return None
    mask = PIL.Image.fromarray(mask)
    box = mask.getbbox(alpha_only=False)
    return box

def fake_logits(img):
    if img is None:
        logits = None
    else:
        long_side = max(img.width, img.height)
        img = img.crop((0, 0, long_side, long_side)).resize((256, 256))
        logits = [np.array(img)]
    
    return logits

def extract_prompt_points(mask, resolution):

    layer = mask.layers.active
    width, height = resolution

    scalar = max(width, height)
    if width > height:
        addend = np.array([0,(height-width)*0.5])
    else:
        addend = np.array([(height-width)*-0.5,0])
    
    prompt_points = []
    prompt_labels = []
    
    for spline in layer.splines:
        if len(spline.points) != 0:
            if spline.use_cyclic == False or len(spline.points) == 1:
                coords = np.zeros(len(spline.points)*2)
                spline.points.foreach_get('co', coords)
                polygon = (coords.reshape(-1, 2) * scalar + addend)
                polygon = [(x, y) for x, y in polygon]
                
                prompt_points += polygon

                if spline.use_fill:
                    prompt_labels += np.ones(len(spline.points)).tolist()
                else:
                    prompt_labels += np.zeros(len(spline.points)).tolist()
    
    if prompt_points == []:
        prompt_points = None
        prompt_labels = None
    else:
        prompt_points = np.array(prompt_points)
        prompt_labels = np.array(prompt_labels)

    return prompt_points, prompt_labels

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
    def poll(cls, context):
        if context.space_data.image is None:
            return False
        return True

    def execute(self, context):
        space = context.space_data
        mask = space.mask
        layer = mask.layers.active
        image = space.image
        maskgencontrols = mask.rotoforge_maskgencontrols.get(layer.name)
        
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
            maskgencontrols = mask.rotoforge_maskgencontrols.get(layer.name)
            
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

            if not maskgencontrols.tracking and self.prompt_points is None: # Run if tracking is disabled and it's not the 1st frame
                #Get Prompt data to feed the machine god
                resolution = tuple(image.size)
                self.guide_mask = mask_rasterize.rasterize_layer_of_active_mask(layer, resolution)
                self.prompt_points, self.prompt_labels = prompt_utils.extract_prompt_points(mask, resolution)
                self.bounding_box = prompt_utils.calculate_bounding_box(self.guide_mask)

            
            guide_strength = maskgencontrols.guide_strength
            search_radius = maskgencontrols.search_radius
            blur_radius = maskgencontrols.feather_radius

            used_mask = self._used_mask_dir

            self.guide_mask, self.bounding_box, overlay_l, _ = generate_masks.track_mask(source_image = image, 
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
            
            overlay.rotoforge_overlay_shader.custom_img = overlay_l

            self.prompt_points = None
            self.prompt_labels = None
            
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
            maskgencontrols = mask.rotoforge_maskgencontrols.get(layer.name)

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
            data_manager.save_sequential_mask(image, used_mask, img, None)
            
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

class FreePredictorOperator(bpy.types.Operator):
    """Frees the predictor from GPU memory"""
    bl_idname = "rotoforge.free_predictor"
    bl_label = "Free Cache"
    bl_options = {'REGISTER', 'UNDO'}
    

    def execute(self, context):
        free_predictor()
        return {'FINISHED'}


classes = [
    GenerateSingularMaskOperator,
    TrackMaskOperator,
    MergeMaskOperator,
    FreePredictorOperator,
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

if exception is not None:
    raise exception