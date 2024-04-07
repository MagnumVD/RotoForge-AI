import bpy
import numpy as np
import gpu
import gpu_extras

vert_out = gpu.types.GPUStageInterfaceInfo("my_interface")
vert_out.smooth('VEC2', "uvInterp")

shader_info = gpu.types.GPUShaderCreateInfo()
shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
shader_info.push_constant('VEC3', "overlayColor")
shader_info.sampler(0, 'FLOAT_2D', "image")
shader_info.vertex_in(0, 'VEC2', "position")
shader_info.vertex_in(1, 'VEC2', "uv")
shader_info.vertex_out(vert_out)
shader_info.fragment_out(0, 'VEC4', "FragColor")

shader_info.vertex_source(
    "void main()"
    "{"
    "  uvInterp = uv;"
    "  gl_Position = ModelViewProjectionMatrix * vec4(position, 0.0, 1.0);"
    "}"
)

shader_info.fragment_source(
    "void main()"
    "{"
    "  vec4 baseColor = texture(image, uvInterp);"
    "  FragColor = baseColor * vec4(overlayColor.x, overlayColor.y, overlayColor.z, 0.0);"
    "}"
)

shader = gpu.shader.create_from_info(shader_info)
del vert_out
del shader_info

batch = gpu_extras.batch.batch_for_shader(
    shader, 'TRI_FAN',
    {
        "position": ((0, 0), (1, 0), (1, 1), (0, 1)),
        "uv": ((0, 0), (1, 0), (1, 1), (0, 1)),
    },
)
        


def rotoforge_overlay_shader():
    overlay_controls = bpy.context.scene.rotoforge_overlaycontrols
    color = overlay_controls.overlay_color
    active = overlay_controls.active_overlay
    image_name = overlay_controls.used_mask
    if image_name in bpy.data.images and active:
        image = bpy.data.images[image_name]
        
        image.buffers_free()
        
        #Update the image by switching the viewport
        viewer_space = bpy.context.space_data
        
        current_image = viewer_space.image
        viewer_space.image = image
        
        viewer_space.display_channels = viewer_space.display_channels
        
        viewer_space.image = current_image
        
        if len(image.pixels) >= 1:

            source_pixels = np.zeros(len(image.pixels), dtype=np.float32)
            image.pixels.foreach_get(source_pixels)
            buffer = gpu.types.Buffer('FLOAT', len(image.pixels), source_pixels)
            texture = gpu.types.GPUTexture(image.size, layers=0, is_cubemap=False, format='RGBA8', data=buffer)

            region = bpy.context.region
            view2d = region.view2d
            translation = view2d.view_to_region(0, 0, clip=False)
            scale = np.array(view2d.view_to_region(1, 1, clip=False)) - np.array(view2d.view_to_region(0, 0, clip=False))



            shader.bind()
            shader.uniform_float("overlayColor", color)
            shader.uniform_sampler("image", texture)

            gpu.matrix.load_identity()

            gpu.matrix.translate((translation[0], translation[1], 0.0))
            gpu.matrix.translate((1, 1, 0.0))
            gpu.matrix.scale((scale[0]-1, scale[1]-1, 1.0))

            
            batch.draw(shader)



class OverlayControls(bpy.types.PropertyGroup):
    
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

        return options
    
    used_mask : bpy.props.EnumProperty(
        name = "Used Mask",
        items = update_mask_options
    ) # type: ignore
    
    active_overlay : bpy.props.BoolProperty(
        name = "Activate Overlay",
        default = False
    ) # type: ignore
    
    overlay_color : bpy.props.FloatVectorProperty(
        name = "Overlay Color",
        subtype = "COLOR",
        min= 0,
        max= 1,
        size = 3,
        default = (1,0,0)
    ) # type: ignore



class OverlayPanel(bpy.types.Panel):
    """Overlay Panel"""
    bl_label = "Overlay"
    bl_idname = "ROTOFORGE_PT_OverlayPanel"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "RotoForge"
    
    @classmethod
    def poll(self, context):
        return context.space_data.mode == 'MASK'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rotoforge_props = scene.rotoforge_overlaycontrols
        
        layout.prop(rotoforge_props, "active_overlay")
        layout.prop(rotoforge_props, "used_mask")
        layout.prop(rotoforge_props, "overlay_color")







handler = None
properties = [OverlayControls]

classes = [OverlayPanel]

def register():
    for cls in properties:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.rotoforge_overlaycontrols = bpy.props.PointerProperty(type=OverlayControls)
    
    
    global handler
    if handler is None:
        handler = bpy.types.SpaceImageEditor.draw_handler_add(rotoforge_overlay_shader, (), 'WINDOW', 'POST_PIXEL')
    
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    global handler

    if handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(handler, 'WINDOW')
        handler = None
    
    del bpy.types.Scene.rotoforge_overlaycontrols
    
    for cls in properties:
        bpy.utils.unregister_class(cls)