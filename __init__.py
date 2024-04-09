bl_info = {
    "name" : "RotoForge AI",
    "author" : "MagnumVD",
    "description" : "Uses metas segment-anything model (SAM) + some other stuff to make rotoscoping fast af",
    "blender" : (4, 0, 0),
    "version" : (0, 1, 0),
    "location" : "",
    "warning" : "Here be dragons!",
    "category" : "Compositing"
}

import bpy
from .functions import install_dependencies


class Install_Dependencies_Operator(bpy.types.Operator):
    """Installs the python packages needed"""
    bl_idname = "rotoforge.install_packages"
    bl_label = "Install python libraries"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Run the script "install_packages"
        install_dependencies.install_packages()
        print("Reloading scripts")
        bpy.ops.script.reload()
        return {'FINISHED'}

class Download_Models_Operator(bpy.types.Operator):
    """Downloads the models from huggingface"""
    bl_idname = "rotoforge.download_models"
    bl_label = "Download Models"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Run the script "download_models"
        install_dependencies.download_models()
        return {'FINISHED'}

class RotoForge_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    
    def draw(self,context):
        layout = self.layout
        if install_dependencies.register() == {'REGISTERED'}:
            layout.label(text="Dependencies are installed, nothing to do here!")
        else:
            row = layout.row()
            
            labels = row.column()
            labels.label(text="Dependencies need to be installed,")
            labels.label(text="please press the button while in administrator mode:")
            
            operators = row.column()
            operators.scale_y = 2.0
            
            if not install_dependencies.test_packages():
                operators.operator("rotoforge.install_packages",text="Install")
            if not install_dependencies.test_models():
                operators.operator("rotoforge.download_models",text="Download Models (~4.2 GB)")

classes = [RotoForge_Preferences,
           Install_Dependencies_Operator,
           Download_Models_Operator
           ]

def register():
    
    if install_dependencies.register() == {'REGISTERED'}:
        from .functions import setup_ui
        from .functions import overlay
        setup_ui.register()
        overlay.register()
    
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():

    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    if install_dependencies.unregister() == {'UNREGISTERED'}:
        
        from .functions import setup_ui
        from .functions import overlay
        setup_ui.unregister()
        overlay.unregister()

if __name__ == "__main__":
    register()