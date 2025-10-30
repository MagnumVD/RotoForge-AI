import bpy

import numpy as np
import PIL.Image
import torch

from .prompt_utils import fake_logits, calculate_bounding_box
from .data_manager import save_sequential_mask, save_singular_mask



def get_predictor(model_type):
    import segment_anything
    from .install_dependencies import get_install_folder
    
    # Empty the memory cache before to clean up any mess that's been handed over
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    # Debug info
    print("PyTorch version: ", torch.__version__)
    
    if torch.cuda.is_available():
        print("Using CUDA accelleration")
        device = "cuda"
    else:
        print("Using CPU")
        device = "cpu"

    # Fetch predictor
    print('loading predictor')
    sam_checkpoint = f"{get_install_folder('sam_hq_weights')}/sam_hq_{model_type}.pth"

    sam = segment_anything.sam_model_registry[model_type](checkpoint=sam_checkpoint)
    sam.to(device=device)

    predictor = segment_anything.SamPredictor(sam)

    print('loaded predictor')
    
    # Empty the memory cache after using SAM because Meta forgot
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    return predictor




def bpyimg_to_HWCuint8(source_image):
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
        mask = PIL.Image.fromarray(guide_mask)
        cropping_box = input_box + np.array([-width*cropping_radius, -height*cropping_radius, width*cropping_radius, height*cropping_radius])
        img = img.crop(cropping_box)
        mask = mask.crop(cropping_box)
        if input_points is not None:
            input_points = input_points - [cropping_box[0], cropping_box[1]]
        input_box = np.array([width*cropping_radius, height*cropping_radius, input_box[2]-input_box[0] + width*cropping_radius, input_box[3]-input_box[1] + height*cropping_radius])
        
        if input_logits is not None:
            input_logits = np.array([input_logits])
        else:
            input_logits = fake_logits(mask)
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
    if torch.cuda.is_available():
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





# Debug func for testing model input
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
    guide_mask = None,
    guide_strength = 10,
    blur_radius = 0.2,
    input_points = None,
    input_labels = None,
    input_box = None,
    debug_logits = False,
):

    

    print('loading image')
    pixels_uint8_rgba = bpyimg_to_HWCuint8(source_image)
    pixels_uint8_rgb, cropping_box, input_logits, input_box, input_points = get_cropped_image(pixels_uint8_rgba, guide_mask, input_points, input_box, None)
    print('loaded image')

    print('predicting masks')
    best_mask, best_logits = predict_mask(pixels_uint8_rgb, predictor, guide_mask, guide_strength, input_points, input_labels, input_box, input_logits)
    print('predicted masks')

    print('saving mask')
    save_singular_mask(source_image, used_mask, best_mask, cropping_box, blur_radius)
    print('saved mask')
    
    if debug_logits:
        print('saving logits')
        save_singular_logits(source_image, input_logits, best_logits)
        print('saved logits')
        







def track_mask(
    source_image, 
    used_mask,
    predictor, 
    guide_mask = None,
    guide_strength = 10,
    blur_radius = 0.2,
    search_radius = 10,
    input_points = None,
    input_labels = None,
    input_box = None,
    input_logits = None
):
    
    #Process the frame
    pixels_uint8_rgba = bpyimg_to_HWCuint8(source_image)
    pixels_uint8_rgb, cropping_box, input_logits, input_box, input_points = get_cropped_image(pixels_uint8_rgba, guide_mask, input_points, input_box, input_logits)
    
    best_mask, best_logits = predict_mask(pixels_uint8_rgb, predictor, guide_mask, guide_strength, input_points, input_labels, input_box, input_logits)
    
    overlay_l = save_sequential_mask(source_image, used_mask, best_mask, cropping_box, blur_radius)
    
    #Set input data for next frame
    input_box = calculate_bounding_box(best_mask)
    input_box = np.array([input_box[0] - search_radius, input_box[1] - search_radius, input_box[2] + search_radius, input_box[3] + search_radius])
    if cropping_box is not None:
        input_box = np.array([input_box[0] + cropping_box[0], input_box[1] + cropping_box[1], input_box[2] + cropping_box[0], input_box[3] + cropping_box[1]])
        
    return best_mask, input_box, overlay_l, best_logits
