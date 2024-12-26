import bpy
import numpy as np

def rasterize_active_mask():
    context = bpy.context
    space = context.space_data
    mask = space.mask
    
    
    # Create a new scene
    original_scene = context.scene
    new_scene = bpy.data.scenes.new("RotoForge_MaskBakeScene")
    
    # Set the same frame
    new_scene.frame_current = original_scene.frame_current
    # Enable compositor
    new_scene.use_nodes = True
    # Set render resolution to match the image
    resolution = space.image.size
    width, height = resolution[0], resolution[1]
    new_scene.render.resolution_x = width
    new_scene.render.resolution_y = height
    
    
    # Clear default nodes
    nodes = new_scene.node_tree.nodes
    links = new_scene.node_tree.links
    nodes.clear()
    # Create and configure nodes
    mask_node = nodes.new(type="CompositorNodeMask")
    viewer_node = nodes.new(type="CompositorNodeViewer")
    mask_node.mask = mask
    # Link nodes
    links.new(mask_node.outputs["Mask"], viewer_node.inputs["Image"])
    
    
    # Update the scene by loading it into the window
    context.window.scene = new_scene
    context.window.scene = original_scene
    
    
    # Process the layers
    rasterized_img = np.zeros((height, width), dtype=np.float32)
    
    prev_hide_setting = dict()
    for other_layers in mask.layers:
        prev_hide_setting[other_layers.name] = [other_layers.hide_render, other_layers.blend]
        other_layers.blend = 'ADD'
    
    for layer in mask.layers:
        rf_props = mask.rotoforge_maskgencontrols[layer.name]
        
        #Skip the layer if it's hidden
        if prev_hide_setting[layer.name][0] == True:
            continue
        image_name = f"{mask.name}/MaskLayers/{layer.name}"
        
        if rf_props.is_rflayer and image_name in bpy.data.images:
            # Load the rotoforge masksequence
            render_result = bpy.data.images[image_name]

            # Update the image by switching the viewport
            current_image = space.image
            space.image = render_result
            space.display_channels = space.display_channels
            space.image = current_image
        else:
            # Render the layer
            for other_layers in mask.layers:
                other_layers.hide_render = True
            layer.hide_render = False
            
            bpy.ops.render.render(scene=new_scene.name)
            
            # Get the Viewer Node image
            render_result = bpy.data.images["Viewer Node"]
        
        # Read the pixels of the render result
        len_pixels = len(render_result.pixels)
        if len_pixels < 1:
            continue
        pixels = np.zeros(len_pixels, dtype=np.float32)
        render_result.pixels.foreach_get(pixels)
        
        # I only take the R channel since the image is grayscale
        rgba = pixels.reshape((height, width, 4))
        rasterized_layer = rgba[:, :, 0] 
        
        # Merge the rasterized layer on the rasterized image
        alpha = layer.alpha
        match prev_hide_setting[layer.name][1]:
            case 'MERGE_ADD':
                rasterized_img = 1-(1-rasterized_img)*(1-rasterized_layer*alpha)
            case 'MERGE_SUBTRACT':
                rasterized_img = np.clip(1-(1-rasterized_img)*(1-rasterized_layer*alpha)-rasterized_layer*alpha, 0, 1)
            case 'ADD':
                rasterized_img = np.clip(rasterized_img+rasterized_layer*alpha, 0, 1)
            case 'SUBTRACT':
                rasterized_img = np.clip(rasterized_img-rasterized_layer*alpha, 0, 1)
            case 'LIGHTEN':
                rasterized_img = np.maximum(rasterized_img, rasterized_layer)*alpha+rasterized_img*(1-alpha)
            case 'DARKEN':
                rasterized_img = np.minimum(rasterized_img, rasterized_layer)*alpha
            case 'MUL':
                rasterized_img *= rasterized_layer*alpha
            case 'REPLACE':
                rasterized_img = rasterized_layer*alpha+rasterized_img*(1-alpha)
            case 'DIFFERENCE':
                rasterized_img = np.absolute(rasterized_img-rasterized_layer*alpha)
    
    # Load the previous settings so they're not changed:
    for other_layers in mask.layers:
        other_layers.hide_render, other_layers.blend = prev_hide_setting[other_layers.name]
    
    # Clean up: delete the new scene
    bpy.data.scenes.remove(new_scene)
    return rasterized_img*255





def rasterize_layer_of_active_mask(layer, resolution, rf_allowed = False):
    context = bpy.context
    space = context.space_data
    mask = space.mask
    
    
    # Create a new scene
    original_scene = bpy.context.scene
    new_scene = bpy.data.scenes.new("RotoForge_MaskBakeScene")
    
    # Set the same frame
    new_scene.frame_current = original_scene.frame_current
    # Enable compositor
    new_scene.use_nodes = True
    # Set render resolution to match the image
    resolution = space.image.size
    new_scene.render.resolution_x = resolution[0]
    new_scene.render.resolution_y = resolution[1]
    
    
    # Clear default nodes
    nodes = new_scene.node_tree.nodes
    links = new_scene.node_tree.links
    for node in nodes:
        nodes.remove(node)
    # Create and configure nodes
    mask_node = nodes.new(type="CompositorNodeMask")
    viewer_node = nodes.new(type="CompositorNodeViewer")
    mask_node.mask = mask
    # Link nodes
    links.new(mask_node.outputs["Mask"], viewer_node.inputs["Image"])
    
    
    # Update the scene by loading it into the window
    context.window.scene = new_scene
    context.window.scene = original_scene
    
    
    # Process the layer
    prev_hide_setting = dict()
    for other_layers in mask.layers:
        prev_hide_setting[other_layers.name] = [other_layers.hide_render, other_layers.blend]
        other_layers.blend = 'ADD'
    
    rf_props = mask.rotoforge_maskgencontrols[layer.name]
    image_name = f"{mask.name}/MaskLayers/{layer.name}"
    
    if rf_allowed and rf_props.is_rflayer and image_name in bpy.data.images:
        # Load the rotoforge masksequence
        render_result = bpy.data.images[image_name]

        # Update the image by switching the viewport
        current_image = space.image
        space.image = render_result
        space.display_channels = space.display_channels
        space.image = current_image
    else:
        # Render the layer
        for other_layers in mask.layers:
            other_layers.hide_render = True
        layer.hide_render = False
        
        bpy.ops.render.render(scene=new_scene.name)
        
        # Get the Viewer Node image
        render_result = bpy.data.images["Viewer Node"]
    
    # Read the pixels of the render result
    len_pixels = len(render_result.pixels)
    if len_pixels < 1:
        return None
    
    pixels = np.zeros(len_pixels, dtype=np.float32)
    render_result.pixels.foreach_get(pixels)
    rgba = pixels.reshape((resolution[1], resolution[0], 4))
    rasterized_layer = rgba[:, :, 0] # I only take the R channel since the image is grayscale
    
    # Load the previous settings so they're not changed:
    for other_layers in mask.layers:
        other_layers.hide_render, other_layers.blend = prev_hide_setting[other_layers.name]
    
    # Clean up: delete the new scene
    bpy.data.scenes.remove(new_scene, do_unlink=True)
    return rasterized_layer