import bpy
import os
import importlib
import sys

from .functions import dependency_manager
from .functions.constants import EXTENSION_NAME

deps_check = None # Holds the state of the last Dependencies check in [None, 'passed', 'failed']
install_logfile_path = None # Path to the deps_install log file

class Test_Dependencies_Operator(bpy.types.Operator):
    """Tests the dependencies needed"""
    bl_idname = "rotoforge.test_dependencies"
    bl_label = "Check Dependencies"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        print(f'--- {EXTENSION_NAME} Dependencies Debug Info ---')
        
        debug_info = []
        prefs = dependency_manager.get_addon_prefs(context)
        packages = dependency_manager.test_packages()
        models = dependency_manager.test_models()
        install_info = dependency_manager.get_install_info()
        
        global deps_check

        prefs.dependencies_driver = install_info.get("driver", prefs.dependencies_driver)
        debug_info.append(f'Using driver: {prefs.dependencies_driver}')
        
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

class Install_Dependencies_Operator(bpy.types.Operator):
    """Installs the dependencies needed (~8GB disk space)"""
    bl_idname = "rotoforge.install_dependencies"
    bl_label = "Install dependencies"
    bl_description = "Install dependencies (Downloads ~8GB)"
    bl_options = {'REGISTER', 'UNDO'}

    override: bpy.props.BoolProperty(
        name="Override existing installations",
        description="Force reinstallation of dependencies even if they are already installed",
        default=False
    ) # type: ignore

    _timer = None
    _process = None

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

        # Start the install process
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        self.report({'INFO'}, "Installing dependencies")
        print(f"{EXTENSION_NAME}: Installing dependencies...")
        try:
            global install_logfile_path
            self._process, install_logfile_path = dependency_manager.install_deps_start(override=self.override)
            return {'RUNNING_MODAL'}
        except:
            return {'CANCELLED'}

    def modal(self, context, event):
        if self._process.poll() is not None:
            self.finish(context)
            return {'FINISHED'}
        
        if event.type == 'TIMER':
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'PREFERENCES':
                        area.tag_redraw()  # Marks the area for redraw
        
        mx, my = event.mouse_x, event.mouse_y
        a = context.area
        ax, ay = a.x, a.y          # lower‑left corner (origin is bottom‑left)
        aw, ah = a.width, a.height
    
        # Simple bounding‑box test
        same_area = (ax <= mx < ax + aw) and (ay <= my < ay + ah)
        
        if event.type in ['TRACKPADPAN', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'] and same_area:
            # Let Blender handle panning in the window
            return {'PASS_THROUGH'}
        # Block all other events
        return {'RUNNING_MODAL'}
    
    def finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        
        if self._process.poll() is None:
            self.report({'INFO'}, "Terminating Process")
            self._process.terminate()
        
        self._process.wait()

        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'PREFERENCES':
                    area.tag_redraw()  # Marks the area for redraw

        print(f"{EXTENSION_NAME}: Install finished")

        print(f"{EXTENSION_NAME}: Reloading addon...")
        bpy.ops.rotoforge.restart_blender('INVOKE_DEFAULT')
        

    
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)


class RotoForge_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    dependencies_path: bpy.props.StringProperty(
        name="Install path",
        description="Directory where additional dependencies for the addon are downloaded (NEEDS ~8GB SPACE)",
        subtype='DIR_PATH',
        default=os.path.realpath(os.path.expanduser(f"~/MVD-addons dependencies/{EXTENSION_NAME}"))
    ) # type: ignore
    
    dependencies_driver: bpy.props.EnumProperty(
        items=[("cuda12_6", "CUDA 12.6", "For NVIDIA GPUs with CUDA 12.6 support"),
               ("cuda12_8", "CUDA 12.8", "For NVIDIA GPUs with CUDA 12.8 support"),
               ("cuda12_9", "CUDA 12.9", "For NVIDIA GPUs with CUDA 12.9 support"),
               ("rocm6_4", "ROCm 6.4", "For AMD GPUs with ROCm 6.4 support (Linux only)"),
               ("cpu", "CPU Only", "Doesn't use GPU acceleration, only the CPU")],
        name="Driver",
        description="Select the appropriate driver for your GPU in order to use hardware acceleration",
        default="cuda12_9"
    ) # type: ignore

    show_log: bpy.props.BoolProperty(
        name="Show Install Log",
        description="Show the install log in the preferences panel",
        default=False
    ) # type: ignore
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "dependencies_driver")
        layout.prop(self, "dependencies_path")
        row = layout.split(factor=0.7)
        
        labels = row.column()
        operators = row.column()
        
        operators.operator("rotoforge.test_dependencies", icon='FILE_REFRESH')
        
        global deps_check
        
        if deps_check == None:
            labels.label(text="Please check the dependencies with the button to the right:")
            return
        
        install = operators.column_flow()
        install.scale_y = 2.0
        
        if deps_check == 'passed':
            labels.label(text="Dependencies are installed, nothing to do here!")
            install_op = install.operator("rotoforge.install_dependencies", text="Forceupdate (Redownloads ~8GB)")
            install_op.override = True
            return
        else:
            labels.label(text="Dependencies need to be installed,")
            labels.label(text="please press the button to the right:")

            install_op = install.operator("rotoforge.install_dependencies", text="Install")
            install_op.override = False
            forceupdate_op = install.operator("rotoforge.install_dependencies", text="Forceupdate (Redownloads ~8GB)")
            forceupdate_op.override = True

        def log_label(log_filepath: str):
            header, body = layout.panel_prop(self, "show_log")
            header.label(text=f"Install Log: {log_filepath}")
            if body is None:
                return
            box = body.box()
            if log_filepath is None:
                return
            with open(log_filepath, 'r') as file:
                for line in file:
                    box.label(text=line)
        
        log_label(install_logfile_path)
            

CLASSES = [RotoForge_Preferences,
           Test_Dependencies_Operator,
           Install_Dependencies_Operator,
           ]

FUNCTION_MODULES = ["restart", "data_manager", "dependency_manager", "overlay", "setup_ui"]

def register():
    global deps_check, install_logfile_path
    deps_check = None
    install_logfile_path = None

    for cls in CLASSES:
        bpy.utils.register_class(cls)
    
    print(f"{EXTENSION_NAME}: Registering extension...")
    for module in FUNCTION_MODULES:
        try:
            print(f"{EXTENSION_NAME}: Registering module: {module}")
            if module in sys.modules:
                globals()[module] = importlib.reload(sys.modules[module])
            else:
                globals()[module] = importlib.import_module(f".functions.{module}", package=__package__)
            globals()[module].register()
        except ImportError as e:
            print(f"{EXTENSION_NAME}: An ImportError occured while registering the extension")
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
        except Exception as e:
            print(f"{EXTENSION_NAME}: Something went very wrong while registering the extension, please get that checked")
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)

def unregister():
    print(f"{EXTENSION_NAME}: Unregistering extension...")
    for module in FUNCTION_MODULES:
        try:
            print(f"{EXTENSION_NAME}: Unregistering module: {module}")
            if module in sys.modules:
                globals()[module] = importlib.reload(sys.modules[module])
            else:
                globals()[module] = importlib.import_module(f".functions.{module}", package=__package__)
            globals()[module].unregister()
        except ImportError as e:
            print(f"{EXTENSION_NAME}: An ImportError occured while unregistering the extension")
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
        except Exception as e:
            print(f"{EXTENSION_NAME}: Something went very wrong while unregistering the extension, please get that checked")
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
    
    for cls in CLASSES:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()