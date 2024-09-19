# RotoForge AI

RotoForge is an implementation of [SAM-HQ](https://github.com/SysCV/sam-hq/tree/main) + some other custom stuff to make rotoscoping fast af

## What can it do? (features):

Rotoforge generates bitmasks (grayscale images which show how much a pixel is part of a mask) based on prompts which the user provides. It can both generate masks for images and videos.

During this process you have multiple methods of fixing/adjusting incorrect masks.

### Different mask prompts:

The AI is prompted via mask splines which you (the user) draws on the image.
Currently it treats all splines as poly splines because I need to write my own conversion script, that will be fixed in the future.

You can change the prompt type per spline either manually by changing it's property or by using the 'Active Spline Settings' block in the menu where all settings are in one place.

* For closed/cyclic masks the encapsulated area is prompted. It is always recommended because with that info the output and performance are improved drastically.
* For open masks every control point is counted as a prompt. 
    * Points part of a spline with fill are inclusion points and counted positive. (put those into areas you want filled)
    * Points part of a spline without fill are exclusion points and counted nagative. (put those into areas which you don't want filled)

## Installation

Go into the preferences and install the addon. After that in the drop down menu under the addon, you can set an installation dir and then install the dependencies. This can take a little bit of time since it's ~8GB of data and will freeze blender.

Now, you can find RotoForge in your image editor in the masking tab.

### Useful info here (tips and tricks):

* I recommend you **open up the system console window before you start the download/installation process**, that way you can track it's progress.

* **Save your .blend file first before you start creating a mask**, as it saves it externally in the dir of the .blend file, which won't be transferred over from tmp if you save the file afterwards. This will result in the loss of the mask data.

* **Only the splines in the current mask layer are used!** Mask layers will later be implemented as a way to manage multiple masks easily.

* As a rule of thumb: **Less is more!** Don't go overboard with prompts or the quality will suffer. I normally use 1 closed mask + 2 positive/negative prompt points each.

* The base model is really dumb and not the fastest, **use the light or large model** instead.
The large model is generally my go-to, but sometimes the light or huge models come in handy.

* If you have 1min to spare, just animate your prompts (input masks) loosely and **check the manual tracking option**. The automatic tracking does work pretty nice, but with manual tracking you can help it with concave shapes by adding additional prompt points as the tracking is purely boundary based (for now).

## Versions and compatibility

### Hardware
This addon was originally created for Windows operating systems with Nvidia cards which support CUDA acceleration.

In order to learn about the required memory: The following tests were performed with an Nvidia GeForce RTX 2070 Max-Q, the dedicated Memory and GPU Memory of the machine were both tracked during the mask generation process.

| Used Model    | Dedicated Memory | GPU Memory | Estimated model usage |
| ------------- |:----------------:|:----------:|:---------------------:|
| None (idle)   | 0.8GB            | 0.6GB      | *baseline*            |
| light         | 1.1GB            | 0.9GB      | 0.3GB                 |
| base          | 3.9GB            | 3.7GB      | 3.1GB                 |
| large         | 5.6GB            | 5.4GB      | 4.8GB                 |
| huge          | 7.0GB            | 6.8GB      | 6.2GB                 |


>There is an experimental branch for Metal gpus in the process, but nothing is guaranteed. 
>
>Although very unlikely, This experimental branch COULD POTENTIALLY HARM YOUR MACHINE, if you want to stay completely safe use a VM!

### Blender versions
The addon was tested with the following blender versions:

* 4.0 (Not working due to a bug in the masking editor)
* 4.1
* 4.2 

Older versions or custom blender forks probably work, I just didn't test them.

## License

RotoForge AI as a whole is licensed under the GNU General Public License, Version 3. 
Individual files may have a different, but compatible license.
