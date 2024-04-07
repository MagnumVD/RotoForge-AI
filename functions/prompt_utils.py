import numpy as np
import PIL

def calculate_bounding_box(polygons, mask):
    
    box = None
    
    if polygons is not None:
        min_x = np.inf
        min_y = np.inf
        max_x = -np.inf
        max_y = -np.inf

        for polygon in polygons:
            x_values = polygon[:][0]
            y_values = polygon[:][1]
            min_x = min(min_x, np.min(x_values))
            min_y = min(min_y, np.min(y_values))
            max_x = max(max_x, np.max(x_values))
            max_y = max(max_y, np.max(y_values))

        if min_x != np.inf:
            box = np.array([min_x, min_y, max_x, max_y])
    elif mask is not None:
        mask = PIL.Image.fromarray(mask)
        box = mask.getbbox(alpha_only=False)
    
    return box



def rasterize_mask(mask, resolution):

    layer = mask.layers.active
    width, height = resolution

    scalar = max(width, height)
    if width > height:
        addend = np.array([0,(height-width)*0.5])
    else:
        addend = np.array([(height-width)*-0.5,0])

    img = PIL.Image.new('1', resolution)
    draw = PIL.ImageDraw.Draw(img)

    polygons = []
    
    for spline in layer.splines:
        if len(spline.points) != 0:
            if spline.use_cyclic and len(spline.points) > 1:
                coords = np.zeros(len(spline.points)*2)
                spline.points.foreach_get('co', coords)
                polygon = (coords.reshape(-1, 2) * scalar + addend)
                polygon = [(x, y) for x, y in polygon]

                polygons += polygon
                draw.polygon(polygon, fill='white', outline='white', width=3)
    
    if polygons == []:
        mask = None
        polygons == None
    else:
        mask = np.array([img])
        polygons = np.array(polygons).tolist()
    
    return mask, polygons





def fake_logits(img):
    if img is None:
        logits = None
    else:
        long_side = max(img.width, img.height)
        img = img.crop((0, 0, long_side, long_side)).resize((256, 256))
        logits = np.array([img])
    
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