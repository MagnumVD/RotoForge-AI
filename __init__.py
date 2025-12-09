import bpy
import os
from .functions import install_dependencies

EXTENSION_NAME = "RotoForge AI"
deps_check = None # Holds the state of the last Dependencies check in [None, 'passed', 'failed']


class RotoForge_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    dependencies_path: bpy.props.StringProperty(
        name="Install path",
        description="Directory where additional dependencies for the addon are downloaded (NEEDS ~8GB SPACE)",
        subtype='DIR_PATH',
        default=os.path.realpath(os.path.expanduser(f"~/MVD-addons dependencies/{EXTENSION_NAME}"))
    ) # type: ignore
    
    dependencies_driver: bpy.props.EnumProperty(
        items=[("cuda12_7", "CUDA 12.7", "For NVIDIA GPUs with CUDA 12.7 support"),
               ("cuda12_8", "CUDA 12.8", "For NVIDIA GPUs with CUDA 12.8 support"),
               ("cuda12_9", "CUDA 12.9", "For NVIDIA GPUs with CUDA 12.9 support"),
               ("rocm6_4", "ROCm 6.4", "For AMD GPUs with ROCm 6.4 support"),
               ("cpu", "CPU Only", "Doesn't use GPU acceleration, only the CPU")],
        name="Driver",
        description="Select the appropriate driver for your GPU in order to use hardware acceleration",
        default="cuda12_9"
    ) # type: ignore
    
    def draw(self,context):
        layout = self.layout
        layout.prop(self, "dependencies_driver")
        layout.prop(self, "dependencies_path")
        row = layout.split(factor=0.7)
        
        labels = row.column()
        operators = row.column()
        
        operators.operator("rotoforge.test_dependencies")
        
        global deps_check
        
        if deps_check == None:
            labels.label(text="Please check the dependencies with the button to the right:")
            return
        
        install = operators.column_flow()
        install.scale_y = 2.0
        
        if deps_check == 'passed':
            labels.label(text="Dependencies are installed, nothing to do here!")
            install.operator("rotoforge.forceupdate_dependencies")
            return
        else:
            labels.label(text="Dependencies need to be installed,")
            labels.label(text="please press the button to the right:")

            install.operator("rotoforge.install_dependencies")
            install.operator("rotoforge.forceupdate_dependencies")

class Install_Dependencies_Operator(bpy.types.Operator):
    """Installs the dependencies needed (~8GB disk space)"""
    bl_idname = "rotoforge.install_dependencies"
    bl_label = "Install dependencies"
    bl_description = "Install dependencies (Downloads up to ~8GB)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Check permissions for network access
        if not bpy.app.online_access:
            print(f'{EXTENSION_NAME}: Network access is disabled in Blender preferences. Cannot install packages.')
            
            # Draw function for the popup menu
            def draw(self, context):
                self.layout.label(text="Network access is disabled in Blender preferences.")
                self.layout.label(text="Cannot install packages.")
            
            context.window_manager.popup_menu(title='Dependency Install Error', draw_func=draw)
            return {'CANCELLED'}

        # Run the script "install_packages"
        if not install_dependencies.test_packages():
            install_dependencies.install_packages()
        
        # Run the script "download_models"
        if not install_dependencies.test_models():
            install_dependencies.download_models()
        
        bpy.ops.rotoforge.test_dependencies()
        return {'FINISHED'}
    
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

class Forceupdate_Dependencies_Operator(bpy.types.Operator):
    """Reinstalls the dependencies needed (~8GB disk space)"""
    bl_idname = "rotoforge.forceupdate_dependencies"
    bl_label = "Forceupdate dependencies (Redownloads ~8GB)"
    bl_options = {'REGISTER', 'UNDO'}
    
    packages: bpy.props.BoolProperty(
        name="Forceupdate Packages (~3GB)",
        description="Forceupdate Packages (Redownloads ~3GB)",
        default=True
    ) # type: ignore
    
    models: bpy.props.BoolProperty(
        name="Forceupdate Models (~5GB)",
        description="Forceupdate Models (Redownloads ~5GB)",
        default=False
    ) # type: ignore
    
    def execute(self, context):
        # Check permissions for network access
        if not bpy.app.online_access:
            print(f'{EXTENSION_NAME}: Network access is disabled in Blender preferences. Cannot install packages.')
            
            # Draw function for the popup menu
            def draw(self, context):
                self.layout.label(text="Network access is disabled in Blender preferences.")
                self.layout.label(text="Cannot install packages.")
            
            context.window_manager.popup_menu(title='Dependency Install Error', draw_func=draw)
            return {'CANCELLED'}
        
        # Run the script "install_packages"
        if self.packages:
            install_dependencies.install_packages(override=True)
        # Run the script "download_models"
        if self.models:
            install_dependencies.download_models(override=True)
            
        bpy.ops.rotoforge.test_dependencies()
        return {'FINISHED'}
    
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

class Test_Dependencies_Operator(bpy.types.Operator):
    """Tests the dependencies needed"""
    bl_idname = "rotoforge.test_dependencies"
    bl_label = "Check Dependencies"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print('--- RotoForge AI: Dependencies Debug Info ---')
        
        debug_info = []
        packages = install_dependencies.test_packages()
        models = install_dependencies.test_models()
        
        global deps_check
        
        if not packages:
            debug_info.append('Issue found with packages')
        if not models:
            debug_info.append('Issue found with models')
        
        if packages and models:
            debug_info.append('No issues found')
            deps_check = 'passed'
        else:
            debug_info.append('Check the system console for more information')
            deps_check = 'failed'
        
        # Draw function for the popup menu
        def draw(self, context):
            # Add each string as a separate line
            for line in debug_info:
                self.layout.label(text=line)
        
        context.window_manager.popup_menu(title='Dependencies Debug Info', draw_func=draw)
        return {'FINISHED'}
            

classes = [RotoForge_Preferences,
           Install_Dependencies_Operator,
           Forceupdate_Dependencies_Operator,
           Test_Dependencies_Operator
           ]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    print(f"{EXTENSION_NAME}: Registering extension...")
    try:
        install_dependencies.register()
        from .functions import data_manager
        data_manager.register()
        from .functions import setup_ui
        setup_ui.register()
        from .functions import overlay
        overlay.register()
    except ImportError as e:
        print(f"{EXTENSION_NAME}: An ImportError occured when importing the dependencies")
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
    except Exception as e:
        print(f"{EXTENSION_NAME}: Something went very wrong importing the dependencies, please get that checked")
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)

def unregister():
    print(f"{EXTENSION_NAME}: Unregistering extension...")
    try:
        install_dependencies.unregister()
        from .functions import data_manager
        data_manager.unregister()
        from .functions import setup_ui
        setup_ui.unregister()
        from .functions import overlay
        overlay.unregister()
    except ImportError as e:
        print(f"{EXTENSION_NAME}: An ImportError occured when importing the dependencies")
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
    except Exception as e:
        print(f"{EXTENSION_NAME}: Something went very wrong importing the dependencies, please get that checked")
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
    
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()