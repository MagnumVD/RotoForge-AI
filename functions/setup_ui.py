import bpy
from . import dependency_manager

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

        used_mask = bpy.data.masks.get(import_props.used_mask)
        used_mask_img = bpy.data.images.get(f"{import_props.used_mask}/Combined")

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
                node.inputs.get('Image').default_value = used_mask_img
            case _:
                raise Exception("Unknown nodetree type: ", nodetree_type)

        ui_scale = context.preferences.system.ui_scale
        x, y = view2d.region_to_view(self.mouse_pos[0], self.mouse_pos[1])
        node.location = x / ui_scale, y / ui_scale
        
        # Make the node stick to the cursor
        bpy.ops.node.translate_attach_remove_on_cancel('INVOKE_DEFAULT')
        
        self.report({'INFO'}, f'Created new image node linked to mask: {import_props.used_mask}')
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
        return (space_data.mode == 'MASK')

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        space_data = context.space_data
        mask = space_data.mask
        deps_check = dependency_manager.get_addon_prefs(bpy.context).deps_check
        if deps_check not in ['NONE', 'PASSED']:
            if deps_check == 'SETUP_ERROR':
                layout.label(text="An Error occured while registering the extension,")
            else:
                layout.label(text="There's an issue with the dependencies,")
            layout.label(text="please check your install in the addon preferences")
            return
        if not mask:
            layout.label(text="No mask selected")
            return
        
        active_layer = mask.layers.active

        row = layout.split(factor=0.4)
        row.operator("rotoforge.set_mask_range_to_scene")
        sub = row.row(align=True)
        sub.use_property_split = False
        sub.prop(mask, "frame_start", text="Start")
        sub.prop(mask, "frame_end", text="End")
        layout.operator("rotoforge.merge_mask", icon='RENDER_RESULT')
        layout.operator("rotoforge.export_masksequence", icon='EXPORT')
        
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
            rotoforge_props = mask.rotoforge_maskgencontrols.get(active_layer.name)
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
            is_rflayer = mask.rotoforge_maskgencontrols.get(active_layer.name).is_rflayer
            return is_rflayer
        return False
    
    def draw(self, context):
        layout = self.layout
        space_data = context.space_data
        mask = space_data.mask
        active_layer = mask.layers.active
        rotoforge_props = mask.rotoforge_maskgencontrols.get(active_layer.name)
        
        
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
        
        
        # Free Cache button
        layout.operator("rotoforge.resync_masksequence", icon='FILE_REFRESH')
        layout.operator("rotoforge.free_predictor", text="Free Cache", icon='TRASH')



class NodeImportControls(bpy.types.PropertyGroup):
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





classes = [
    NodeImportControls,
    ImportMaskNodeOperator,
    MaskRangeToSceneOperator,
    LayerPanel,
    RotoForgeMaskPanel,
    RotoForgeNodePanel,
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