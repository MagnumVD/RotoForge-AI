import bpy

import numpy as np
import PIL
import torch
import torchvision
import segment_anything_hq
from . import prompt_utils

from .overlay import rotoforge_overlay_shader
from .install_dependencies import get_install_folder
import os
from typing import Optional

def get_predictor(model_type):
    
    # Empty the memory cache before to clean up any mess that's been handed over
    if torch.cuda.is_available:
        torch.cuda.empty_cache()
    
    # Debug info
    print("PyTorch version: ", torch.__version__)
    print("Torchvision version: ", torchvision.__version__)
    
    if torch.cuda.is_available:
        print("Using CUDA accelleration")
        device = "cuda"
    else:
        print("Using CPU")
        device = "cpu"

    # Fetch predictor
    print('loading predictor')
    sam_checkpoint = os.path.join(get_install_folder("sam_hq_weights"), 'sam_hq_' + model_type + '.pth')

    sam = segment_anything_hq.sam_model_registry[model_type](checkpoint=sam_checkpoint)
    sam.to(device=device)

    predictor = segment_anything_hq.SamPredictor(sam)

    print('loaded predictor')
    
    # Empty the memory cache after using SAM because Meta forgot
    if torch.cuda.is_available:
        torch.cuda.empty_cache()
    
    return predictor




def bpyimg_to_HWCuint8(source_image):
    # Free any leftover buffers
    source_image.buffers_free()
    
    # Get the image pixel data as a numpy array:
    source_pixels = np.zeros(len(source_image.pixels), dtype=np.float32)
    source_image.pixels.foreach_get(source_pixels)

    # Determine the dimensions of the image
    width = source_image.size[0]
    height = source_image.size[1]

    # Reshape the pixel data into HWC uint8 format
    channels = 4
    pixels_HWC_uint8 = (np.array(source_pixels).reshape(height, width, channels)* 255).astype(np.uint8)
    return pixels_HWC_uint8



def get_cropped_image(pixels_uint8_rgba, guide_mask, input_points, input_box, input_logits):
    # Determine the dimensions of the image
    cropping_radius = 0.05
    width = pixels_uint8_rgba.shape[1]
    height = pixels_uint8_rgba.shape[0]
    
    # Load data into PIL
    img = PIL.Image.fromarray(pixels_uint8_rgba)
    img = img.convert('RGB')
    
    # Crop to box if box is supported
    if input_box is not None:
        mask = PIL.Image.fromarray(guide_mask[0])
        cropping_box = input_box + np.array([-width*cropping_radius, -height*cropping_radius, width*cropping_radius, height*cropping_radius])
        img = img.crop(cropping_box)
        mask = mask.crop(cropping_box)
        if input_points is not None:
            input_points = input_points - [cropping_box[0], cropping_box[1]]
        input_box = np.array([width*cropping_radius, height*cropping_radius, input_box[2]-input_box[0] + width*cropping_radius, input_box[3]-input_box[1] + height*cropping_radius])
        
        if input_logits is not None:
            input_logits = np.array([input_logits])
        else:
            input_logits = prompt_utils.fake_logits(mask)
    else:
        input_logits = None
        cropping_box = None
        
    
    pixels_uint8_rgb = np.asarray(img)

    return pixels_uint8_rgb, cropping_box, input_logits, input_box, input_points






def predict_mask(pixels_uint8_rgb, predictor, guide_mask, guide_strength, input_points, input_labels, input_box, input_logits):
    # Generate mask
    predictor.set_image(pixels_uint8_rgb)
    masks, scores, logits = predictor.predict(
        point_coords=input_points,
        point_labels=input_labels,
        box=input_box,
        mask_input=input_logits,
        multimask_output=True,
    )
    # Empty the memory cache after using SAM because Meta forgot
    if torch.cuda.is_available:
        torch.cuda.empty_cache()
    # Initialize variables outside the loop
    best_score = float('-inf')
    cropped_area = len(pixels_uint8_rgb.flatten())/3
    best_mask = None
    best_logits = None
    # Calculate sums outside the loop if they don't change
    if guide_mask is not None:
        sum_guide_mask = np.sum(guide_mask)
    for i, score in enumerate(scores):
        if guide_mask is not None:
            score += -abs(sum_guide_mask - np.sum(masks[i])) / cropped_area * guide_strength
        if score > best_score:
            best_score = score
            best_mask = masks[i]
            best_logits = logits[i]
    
    return best_mask, best_logits






def save_singular_mask(source_image, used_mask, best_mask, cropping_box):
    
    width, height = source_image.size
    
    # Get the mask image to write to
    if used_mask == 'new':
        new_name = source_image.name
        if new_name.rfind('.') == -1:
            new_name = new_name + '_mask'
        else:
            new_name = new_name[:new_name.rfind('.')] + '_mask' + new_name[new_name.rfind('.'):]
        mask_image = bpy.data.images.new(new_name, width=width, height=height, is_data=True, alpha=False, float_buffer=True)
    else:
        mask_image = bpy.data.images[used_mask]
    # Convert Binary Mask to image data
    best_mask = PIL.Image.fromarray(best_mask)
    best_mask = best_mask.convert(mode='RGBA')
    best_mask = best_mask.filter(PIL.ImageFilter.BoxBlur(radius=0.2))
    # Paste the cropped mask in a black image with the original res at the original position if cropping was used
    if cropping_box is not None:
        empty_mask = PIL.Image.new('RGBA', (width, height), 'black')
        empty_mask.paste(best_mask, (int(cropping_box[0]), int(cropping_box[1] + 1)))
        best_mask = empty_mask
    np_mask_data = np.asarray(best_mask, dtype=np.float32).flatten()/255
    # Write mask to image
    mask_image.pixels.foreach_set(np_mask_data)
    # Save the image
    mask_image.pack()
    mask_image.update()







def save_sequential_mask(source_image, used_mask, best_mask, cropping_box):
    
    frame = str(bpy.context.scene.frame_current)
    width, height = source_image.size
    
    folder = used_mask # The img seq will be saved in a folder named after the mask
    
    # Use the folder the .blend is in if the blend was saved
    # If not, create a folder in the .tmp folder of the current blender instance
    if bpy.data.is_saved:
        img_seq_dir = os.path.join(bpy.path.abspath('//RotoForge masksequences') , folder)
    else:
        img_seq_dir = os.path.join(bpy.app.tempdir, 'RotoForge masksequences', folder)
    
    image_path = os.path.join(img_seq_dir, frame + '.png')
        
    # Convert Binary Mask to image data
    best_mask = PIL.Image.fromarray(best_mask)
    best_mask = best_mask.convert(mode='RGBA')
    best_mask = best_mask.filter(PIL.ImageFilter.BoxBlur(radius=0.2))
    # Paste the cropped mask in a black image with the original res at the original position if cropping was used
    if cropping_box is not None:
        empty_mask = PIL.Image.new('RGBA', (width, height), 'black')
        empty_mask.paste(best_mask, (int(cropping_box[0]), int(cropping_box[1] + 1)))
        best_mask = empty_mask
    # Save the image
    flipped_mask = best_mask.transpose(PIL.Image.FLIP_TOP_BOTTOM)
    if not os.path.isdir(img_seq_dir):
        os.makedirs(img_seq_dir)
    flipped_mask.save(image_path)
    return np.asarray(best_mask)






def load_sequential_mask(folder):
    if bpy.data.is_saved:
        img_seq_dir = os.path.join(bpy.path.abspath('//RotoForge masksequences') , folder)
    else:
        img_seq_dir = os.path.join(bpy.app.tempdir, 'RotoForge masksequences', folder)
    
    frame = sorted(os.listdir(img_seq_dir))[0]
    rel_dir = os.path.join(img_seq_dir, frame)
    
    if folder not in bpy.data.images:
        img = bpy.data.images.load(filepath=rel_dir, check_existing=True)
        img.source = 'SEQUENCE'
        img.name = folder
    
    
    
    
    
    
def save_singular_logits(source_image, input_logits, sam_logits):
    
    # Create new image
    new_name = source_image.name
    if new_name.rfind('.') == -1:
        new_name = new_name + '_FAKElogits'
    else:
        new_name = new_name[:new_name.rfind('.')] + '_FAKElogits' + new_name[new_name.rfind('.'):]
    logits_image = bpy.data.images.new(new_name, width=256, height=256, is_data=True, alpha=False, float_buffer=True)
    print('Fake logits')
    print('Shape: ', str(input_logits.shape))
    print('Min: ', str(np.min(input_logits)))
    print('Max: ', str(np.max(input_logits)))
    # Convert Binary Mask to image data
    best_logits_flat = np.array(input_logits).flatten()
    logits_data_data = np.where(best_logits_flat[:, None], [1, 1, 1, 1], [0, 0, 0, 1])
    np_logits_data = np.array(logits_data_data, dtype=np.float32).flatten()
    # Write mask to image
    logits_image.pixels.foreach_set(np_logits_data)
    # Save the image
    logits_image.pack()
    logits_image.update()
    
    
    
    
    
    # Create new image
    new_name = source_image.name
    if new_name.rfind('.') == -1:
        new_name = new_name + '_SAMlogits'
    else:
        new_name = new_name[:new_name.rfind('.')] + '_SAMlogits' + new_name[new_name.rfind('.'):]
    logits_image = bpy.data.images.new(source_image.name + "_SAMlogits", width=256, height=256, is_data=True, alpha=False, float_buffer=True)
    
    print('Sam logits')
    print('Shape: ', str(sam_logits.shape))
    print('Min: ', str(np.min(sam_logits)))
    print('Max: ', str(np.max(sam_logits)))
    logits_data = (sam_logits-np.min(sam_logits))/np.max(sam_logits-np.min(sam_logits))
    logits_data =  np.expand_dims(logits_data, axis=2)  # Add an additional dimension
    logits_data = np.concatenate([logits_data]*3, axis=2)
    # Set the alpha channel to 1 for all pixels
    alpha_channel = np.ones_like(logits_data[:, :, :1])  # Set alpha channel to 1 (fully opaque)
    logits_data = np.concatenate([logits_data, alpha_channel], axis=2)  # Concatenate alpha channel
    np_logits_data = np.array(logits_data, dtype=np.float32).flatten()
    # Write mask to image
    logits_image.pixels.foreach_set(np_logits_data)
    # Save the image
    logits_image.pack()
    logits_image.update()










def generate_mask(
    source_image, 
    used_mask,
    predictor, 
    guide_mask: Optional[np.ndarray] = None,
    guide_strength: Optional[float] = 10,
    input_points: Optional[np.ndarray] = None,
    input_labels: Optional[np.ndarray] = None,
    input_box: Optional[np.ndarray] = None,
    debug_logits: Optional[bool] = False,
):

    

    print('loading image')
    pixels_uint8_rgba = bpyimg_to_HWCuint8(source_image)
    pixels_uint8_rgb, cropping_box, input_logits, input_box, input_points = get_cropped_image(pixels_uint8_rgba, guide_mask, input_points, input_box, None)
    print('loaded image')

    print('predicting masks')
    best_mask, best_logits = predict_mask(pixels_uint8_rgb, predictor, guide_mask, guide_strength, input_points, input_labels, input_box, input_logits)
    print('predicted masks')

    print('saving mask')
    save_singular_mask(source_image, used_mask, best_mask, cropping_box)
    print('saved mask')
    
    if debug_logits:
        print('saving logits')
        save_singular_logits(source_image, input_logits, best_logits)
        print('saved logits')
        







def track_mask(
    source_image, 
    used_mask,
    predictor, 
    guide_mask: Optional[np.ndarray] = None,
    guide_strength: Optional[float] = 10,
    search_radius: Optional[float] = 10,
    input_points: Optional[np.ndarray] = None,
    input_labels: Optional[np.ndarray] = None,
    input_box: Optional[np.ndarray] = None,
    input_logits: Optional[np.ndarray] = None
):
    
    #Process the frame
    pixels_uint8_rgba = bpyimg_to_HWCuint8(source_image)
    pixels_uint8_rgb, cropping_box, input_logits, input_box, input_points = get_cropped_image(pixels_uint8_rgba, guide_mask, input_points, input_box, input_logits)
    
    best_mask, best_logits = predict_mask(pixels_uint8_rgb, predictor, guide_mask, guide_strength, input_points, input_labels, input_box, input_logits)
    
    best_mask_np = save_sequential_mask(source_image, used_mask, best_mask, cropping_box)
    
    rotoforge_overlay_shader.custom_img = PIL.Image.fromarray(best_mask_np)
    
    #Set input data for next frame
    input_box = prompt_utils.calculate_bounding_box(None, best_mask)
    input_box = np.array([input_box[0] - search_radius, input_box[1] - search_radius, input_box[2] + search_radius, input_box[3] + search_radius])
    if cropping_box is not None:
        input_box = np.array([input_box[0] + cropping_box[0], input_box[1] + cropping_box[1], input_box[2] + cropping_box[0], input_box[3] + cropping_box[1]])
    guide_mask = best_mask
    input_logits = best_logits
    input_points = None
    input_labels = None
    return guide_mask, input_points, input_labels, input_box, input_logits
