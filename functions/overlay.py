import bpy
import numpy as np
import gpu
import gpu_extras.batch

vert_out = gpu.types.GPUStageInterfaceInfo("my_interface")
vert_out.smooth('VEC2', "uvInterp")

shader_info = gpu.types.GPUShaderCreateInfo()
shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
shader_info.push_constant('VEC4', "overlayColor")
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
    "  FragColor = baseColor * overlayColor;"
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

    space = bpy.context.space_data
    mask = space.mask
    layer = mask.layers.active
    
    color = overlay_controls.overlay_color
    alpha = overlay_controls.overlay_opacity
    color = (color[0],color[1],color[2],alpha) # Extend to 4D vector (rgba)
    
    active = overlay_controls.active_overlay
    if hasattr(mask, 'name') and hasattr(layer, 'name'):
        image_name = mask.name+'.'+layer.name
    else:
        image_name = ''
        active = False
    if not ((space.mask) and (space.mask.layers.active is not None) and (space.mode == 'MASK')):
        active = False

    custom_img = rotoforge_overlay_shader.custom_img
    
    shader.bind()  # Bind the shader once outside the conditional branches

    region = bpy.context.region
    view2d = region.view2d
    translation = view2d.view_to_region(0, 0, clip=False)
    scale = np.array(view2d.view_to_region(1, 1, clip=False)) - np.array(view2d.view_to_region(0, 0, clip=False))

    gpu.matrix.load_identity()
    gpu.matrix.translate((translation[0], translation[1], 0.0))
    gpu.matrix.translate((1, 1, 0.0))
    gpu.matrix.scale((scale[0]-1, scale[1]-1, 1.0))

    if custom_img is not None:
        # Process custom image
        source_pixels = np.asarray(custom_img, dtype=np.float32).flatten() / 255
        buffer = gpu.types.Buffer('FLOAT', len(source_pixels), source_pixels)
        texture = gpu.types.GPUTexture((custom_img.width, custom_img.height), layers=0, is_cubemap=False, format='RGBA8', data=buffer)
        
    elif image_name in bpy.data.images and active:
        # Process active image
        image = bpy.data.images[image_name]
        image.buffers_free()

        # Update the image by switching the viewport
        viewer_space = bpy.context.space_data
        current_image = viewer_space.image
        viewer_space.image = image
        viewer_space.display_channels = viewer_space.display_channels
        viewer_space.image = current_image
        
        len_pixels = len(image.pixels)
        if len_pixels >= 1:
            source_pixels = np.zeros(len_pixels, dtype=np.float32)
            image.pixels.foreach_get(source_pixels)
            buffer = gpu.types.Buffer('FLOAT', len(source_pixels), source_pixels)
            texture = gpu.types.GPUTexture(image.size, layers=0, is_cubemap=False, format='RGBA8', data=buffer)
            
    if 'texture' in locals():
        shader.uniform_float("overlayColor", color)
        shader.uniform_sampler("image", texture)
        batch.draw(shader)

class OverlayControls(bpy.types.PropertyGroup):
    active_overlay : bpy.props.BoolProperty(
        name = "Activate Overlay",
        default = False
    ) # type: ignore
    
    overlay_opacity : bpy.props.FloatProperty(
        name = "Opacity",
        default = 0, 
        min=0.0, 
        max=1.0, 
        soft_min=0.0, 
        soft_max=1.0
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
    def poll(cls, context):
        space_data = context.space_data
        return (space_data.mask) and (space_data.mask.layers.active is not None) and (space_data.mode == 'MASK')
    
    def draw_header_preset(self, context):
        layout = self.layout
        scene = context.scene
        rotoforge_props = scene.rotoforge_overlaycontrols
        layout.prop(rotoforge_props, "active_overlay", text="Active", icon='OVERLAY')
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rotoforge_props = scene.rotoforge_overlaycontrols
        
        layout.template_color_picker(rotoforge_props, "overlay_color",value_slider=True)
        layout.prop(rotoforge_props, "overlay_opacity", text="Opacity", slider=True)







overlay_handler = None
properties = [OverlayControls]

classes = [OverlayPanel]

def register():
    for cls in properties:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.rotoforge_overlaycontrols = bpy.props.PointerProperty(type=OverlayControls)
    
    
    global overlay_handler
    if overlay_handler is None:
        rotoforge_overlay_shader.custom_img = None
        overlay_handler = bpy.types.SpaceImageEditor.draw_handler_add(rotoforge_overlay_shader, (), 'WINDOW', 'POST_PIXEL')
    
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    
    global overlay_handler
    if overlay_handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(overlay_handler, 'WINDOW')
        overlay_handler = None
    
    if hasattr(bpy.types.Scene, 'rotoforge_overlaycontrols'):
        del bpy.types.Scene.rotoforge_overlaycontrols
    
    for cls in properties:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
