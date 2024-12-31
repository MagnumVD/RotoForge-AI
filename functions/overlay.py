import bpy
from bpy.app.handlers import persistent
import numpy as np
import gpu
import gpu_extras.batch
from . import mask_rasterize
from mathutils import Matrix

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
    "  vec2 texelSize = 1.0 / (textureSize(image, 0));"
    "  vec2 nearestUV = floor(uvInterp / texelSize) * texelSize + texelSize * 0.5;"
    "  vec4 texColor = texture(image, nearestUV);"
    "  FragColor = texColor * vec4(overlayColor.rgb, overlayColor.a * (1.0 - texColor));"
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
    context = bpy.context
    space = context.space_data
    region = context.region
    view2d = region.view2d
    
    overlay_controls = context.scene.rotoforge_overlaycontrols
    
    mask = space.mask
    if mask is None:
        return
    
    color = overlay_controls.overlay_color
    alpha = overlay_controls.overlay_opacity
    color = (color[0],color[1],color[2],alpha) # Extend to 4D vector (rgba)

    custom_img = rotoforge_overlay_shader.custom_img
    
    source_pixels_rgba = None

    if custom_img is not None:
        source_pixels = custom_img
        
    elif not overlay_controls.active_overlay or space.mode != 'MASK':
        return
    
    else:
        image_name = f"{mask.name}\\Combined"
        
        use_combined = overlay_controls.use_combined
        only_active_layer = overlay_controls.only_active_layer
        
        if image_name in bpy.data.images and use_combined and not only_active_layer:
            # Process active image
            image = bpy.data.images[image_name]

            # Update the image by switching the viewport
            current_image = space.image
            space.image = image
            space.display_channels = space.display_channels
            space.image = current_image
            
            len_pixels = len(image.pixels)
            if len_pixels >= 1:
                source_pixels_rgba = np.zeros(len_pixels, dtype=np.float32)
                image.pixels.foreach_get(source_pixels_rgba)
                
        if source_pixels_rgba is None:
            if only_active_layer:
                source_pixels = mask_rasterize.rasterize_layer_of_active_mask(mask.layers.active, resolution=space.image.size, rf_allowed=True, hide_uncyclic=False, use_255_range=True)
            else:
                source_pixels = mask_rasterize.rasterize_active_mask()
    
    if source_pixels_rgba is None:
        source_pixels = source_pixels.flatten()/255
        # Convert L to RGBA with RGB = L and A = 1
        source_pixels_rgba = np.ones((source_pixels.size, 4), dtype=np.float32)
        source_pixels_rgba[:, :3] = source_pixels[:, None]  # Broadcast grayscale to RGB
        source_pixels_rgba = source_pixels_rgba.flatten()

    buffer = gpu.types.Buffer('FLOAT', len(source_pixels_rgba), source_pixels_rgba)
    texture = gpu.types.GPUTexture(tuple(space.image.size), layers=0, is_cubemap=False, format='RGBA8', data=buffer)
    
    # draw the shader
    translation = view2d.view_to_region(0, 0, clip=False)
    scale = np.array(view2d.view_to_region(1, 1, clip=False)) - np.array(view2d.view_to_region(0, 0, clip=False))

    transform = np.eye(4, dtype=np.float32)
    transform[0, 3] = translation[0]
    transform[1, 3] = translation[1]
    transform[0, 0] = scale[0]
    transform[1, 1] = scale[1]
    
    gpu.matrix.load_matrix(Matrix(transform))
    
    shader.uniform_float("overlayColor", color)
    shader.uniform_sampler("image", texture)
    batch.draw(shader)

class OverlayControls(bpy.types.PropertyGroup):
    active_overlay : bpy.props.BoolProperty(
        name = "Activate Overlay",
        default = False
    ) # type: ignore
    
    only_active_layer : bpy.props.BoolProperty(
        name = "Only Render active layer",
        default = True
    ) # type: ignore
    
    use_combined : bpy.props.BoolProperty(
        name = "Use baked Mask",
        default = True
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
    
    @classmethod 
    def register(cls):
        bpy.types.Scene.rotoforge_overlaycontrols = bpy.props.PointerProperty(type=cls)
    
    @classmethod
    def unregister(cls):
        if hasattr(bpy.types.Scene, 'rotoforge_overlaycontrols'):
            del bpy.types.Scene.rotoforge_overlaycontrols



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
        return (space_data.mask) and (space_data.mode == 'MASK')
    
    def draw_header_preset(self, context):
        layout = self.layout
        scene = context.scene
        rotoforge_props = scene.rotoforge_overlaycontrols
        layout.prop(rotoforge_props, "active_overlay", text="Active", icon='OVERLAY')
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        rotoforge_props = scene.rotoforge_overlaycontrols
        
        row = layout.row(align=True)
        row.prop(rotoforge_props, "only_active_layer")
        if not rotoforge_props.only_active_layer:
            row.prop(rotoforge_props, "use_combined")
        layout.template_color_picker(rotoforge_props, "overlay_color",value_slider=True)
        layout.prop(rotoforge_props, "overlay_opacity", text="Opacity", slider=True)





overlay_handler = None

classes = [OverlayControls,
           OverlayPanel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    global overlay_handler
    if overlay_handler is None:
        rotoforge_overlay_shader.custom_img = None
        overlay_handler = bpy.types.SpaceImageEditor.draw_handler_add(rotoforge_overlay_shader, (), 'WINDOW', 'POST_PIXEL')

def unregister():
    global overlay_handler
    if overlay_handler is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(overlay_handler, 'WINDOW')
        overlay_handler = None
    
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
