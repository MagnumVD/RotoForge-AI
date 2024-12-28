import bpy
import os
from .functions import install_dependencies



class Install_Dependencies_Operator(bpy.types.Operator):
    """Installs the dependencies needed (~8GB disk space)"""
    bl_idname = "rotoforge.install_dependencies"
    bl_label = "Install dependencies (Downloads up to ~8GB)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Run the script "install_packages"
        if not install_dependencies.test_packages():
            install_dependencies.install_packages()
        # Run the script "download_models"
        if not install_dependencies.test_models():
            install_dependencies.download_models()
        # Reload the scripts
        print("RotoForge AI: Reloading scripts")
        bpy.ops.script.reload()
        return {'FINISHED'}
    
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

class Test_Dependencies_Operator(bpy.types.Operator):
    """Tests the dependencies needed"""
    bl_idname = "rotoforge.test_dependencies"
    bl_label = "Dependencies Debug Info"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print('--- RotoForge AI: Dependencies Debug Info ---')
        
        debug_info = []
        install_dependencies.ensure_package_path()
        packages = install_dependencies.test_packages()
        models = install_dependencies.test_models()
        
        if not packages:
            debug_info.append('Issue found with packages')
        if not models:
            debug_info.append('Issue found with models')
        if packages and models:
            debug_info.append('No issues found')
        else:
            debug_info.append('Check the system console for more information')
        
        # Draw function for the popup menu
        def draw(self, context):
            # Add each string as a separate line
            for line in debug_info:
                self.layout.label(text=line)
        
        context.window_manager.popup_menu(title='Dependencies Debug Info', draw_func=draw)
        return {'FINISHED'}

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
        # Run the script "install_packages"
        if self.packages:
            install_dependencies.install_packages(override=True)
        # Run the script "download_models"
        if self.models:
            install_dependencies.download_models(override=True)
        # Reload the scripts
        print("RotoForge AI: Reloading scripts")
        bpy.ops.script.reload()
        return {'FINISHED'}
    
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

class RotoForge_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    dependencies_path: bpy.props.StringProperty(
        name="Install path",
        description="Directory where additional dependencies for the addon are downloaded (NEEDS ~8GB SPACE)",
        subtype='DIR_PATH',
        default=os.path.realpath(os.path.expanduser("~/MVD-addons dependencies/RotoForge AI"))
    ) # type: ignore
    
    def draw(self,context):
        layout = self.layout
        layout.prop(self, "dependencies_path")
        row = layout.row()
        
        labels = row.column()
        operators = row.column()
        if install_dependencies.register() == {'REGISTERED'}:
            labels.label(text="Dependencies are installed, nothing to do here!")
        else:
            labels.label(text="Dependencies need to be installed,")
            labels.label(text="please press the button to the right:")
            
            install = operators.column_flow()
            install.scale_y = 2.0
            
            install.operator("rotoforge.install_dependencies",text="Install")
        #operators.operator("rotoforge.forceupdate_dependencies",text="Forceupdate") Deactivated due to WinError 5
        operators.operator("rotoforge.test_dependencies")
            

classes = [RotoForge_Preferences,
           Install_Dependencies_Operator,
           Forceupdate_Dependencies_Operator,
           Test_Dependencies_Operator
           ]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    print("RotoForge AI: Registering extension...")
    try:
        install_dependencies.register()
        from .functions import data_manager
        data_manager.register()
        from .functions import setup_ui
        setup_ui.register()
        from .functions import overlay
        overlay.register()
    except ImportError as e:
        print('RotoForge AI: An ImportError occured when importing the dependencies')
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
    except Exception as e:
        print('RotoForge AI: Something went very wrong importing the dependencies, please get that checked')
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)

def unregister():
    print("RotoForge AI: Unregistering extension...")
    try:
        install_dependencies.unregister()
        from .functions import data_manager
        data_manager.unregister()
        from .functions import setup_ui
        setup_ui.unregister()
        from .functions import overlay
        overlay.unregister()
    except ImportError as e:
        print('RotoForge AI: An ImportError occured when importing the dependencies')
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
    except Exception as e:
        print('RotoForge AI: Something went very wrong importing the dependencies, please get that checked')
        if hasattr(e, 'message'):
            print(e.message)
        else:
            print(e)
    
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()