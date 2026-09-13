import bpy
import os
import importlib
import sys

from .functions import dependency_manager
from .functions.constants import EXTENSION_NAME, SIGINT

install_logfile_path = None # Path to the deps_install log file
install_process = None      # External dependency installation process
install_timer = None        # bpy.app.timers callback while installation is running
install_override = False    # Whether the current installation is a force update


def _tag_preferences_redraw(wm):
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'PREFERENCES':
                area.tag_redraw()

class Test_Dependencies_Operator(bpy.types.Operator):
    """Tests the dependencies needed"""
    bl_idname = "rotoforge.test_dependencies"
    bl_label = "Check Dependencies"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        prefs = dependency_manager.get_addon_prefs(context)
        return not prefs.deps_check == 'INSTALLING'
    
    def execute(self, context):
        print(f'--- {EXTENSION_NAME} Dependencies Debug Info ---')
        
        debug_info = []
        prefs = dependency_manager.get_addon_prefs(context)
        packages = dependency_manager.test_packages()
        models = dependency_manager.test_models()
        install_info = dependency_manager.get_install_info()

        prefs.dependencies_driver = install_info.get("driver", prefs.dependencies_driver)
        debug_info.append(f'Using driver: {prefs.dependencies_driver}')
        
        if not packages:
            debug_info.append('Issue found with packages')
        if not models:
            debug_info.append('Issue found with models')
        
        if packages and models:
            debug_info.append('No issues found')
            prefs.deps_check = 'PASSED'
        else:
            debug_info.append('Check the system console for more information')
            prefs.deps_check = 'CHECK_ERROR'
        
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
    
    @classmethod
    def poll(cls, context):
        prefs = dependency_manager.get_addon_prefs(context)
        return not prefs.deps_check == 'INSTALLING'

    def execute(self, context):
        global install_logfile_path
        global install_process
        global install_timer
        global install_override

        prefs = dependency_manager.get_addon_prefs(context)

        if prefs.deps_check == 'INSTALLING' or install_process is not None:
            self.report({'WARNING'}, "Dependencies are already installing")
            return {'CANCELLED'}

        if not bpy.app.online_access:
            print(f'{EXTENSION_NAME}: Network access is disabled in Blender preferences. Cannot install packages.')
            
            # Draw function for the popup menu
            def draw(self, context):
                self.layout.label(text="Network access is disabled in Blender preferences.")
                self.layout.label(text="Cannot install packages.")
            
            context.window_manager.popup_menu(title='Dependency Install Error', draw_func=draw)
            return {'CANCELLED'}

        self.report({'INFO'}, "Installing dependencies")
        print(f"{EXTENSION_NAME}: Installing dependencies...")
        try:
            install_process, install_logfile_path = dependency_manager.install_deps_start(
                override=self.override
            )
        except Exception as e:
            prefs.deps_check = 'CHECK_ERROR'
            print(f"{EXTENSION_NAME}: Failed to start dependency installation: {e!r}")
            self.report({'ERROR'}, "Failed to start dependency installation")
            _tag_preferences_redraw(context.window_manager)
            return {'CANCELLED'}

        if install_process is None:
            prefs.deps_check = 'CHECK_ERROR'
            print(f"{EXTENSION_NAME}: Dependency installer returned no process")
            self.report({'ERROR'}, "Dependency installer returned no process")
            _tag_preferences_redraw(context.window_manager)
            return {'CANCELLED'}

        install_override = self.override
        prefs.deps_check = 'INSTALLING'
        prefs.show_log = False

        def poll_install():
            global install_process
            global install_timer
            global install_override

            process = install_process
            if process is None:
                install_timer = None
                return None

            returncode = process.poll()
            if returncode is None:
                _tag_preferences_redraw(bpy.context.window_manager)
                return 0.5

            install_process = None
            install_timer = None

            try:
                current_prefs = dependency_manager.get_addon_prefs(bpy.context)
                current_prefs.deps_check = (
                    'PASSED' if returncode == 0 else 'CHECK_ERROR'
                )
            except Exception as e:
                print(f"{EXTENSION_NAME}: Failed to update dependency state: {e!r}")

            _tag_preferences_redraw(bpy.context.window_manager)

            if returncode == 0:
                print(f"{EXTENSION_NAME}: Install finished")
                print(f"{EXTENSION_NAME}: Reloading addon...")
                bpy.ops.rotoforge.restart_blender('INVOKE_DEFAULT')
            else:
                print(
                    f"{EXTENSION_NAME}: Dependency installation exited "
                    f"with return code {returncode}"
                )

            install_override = False
            return None

        install_timer = poll_install
        bpy.app.timers.register(
            install_timer,
            first_interval=0.5,
            persistent=True,
        )

        _tag_preferences_redraw(context.window_manager)
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
    
    deps_check: bpy.props.EnumProperty(
        items=[
            ('NONE', 'NONE', 'not tested'), 
            ('PASSED', 'PASSED', 'passed test'), 
            ('INSTALLING', 'INSTALLING', 'Currently installing'), 
            ('SETUP_ERROR', 'SETUP_ERROR', 'Error during register/setup'), 
            ('CHECK_ERROR', 'CHECK_ERROR', 'Explicit error from test')
        ],
        name="Deps check",
        description="Holds the state of the last Dependencies check",
        default='NONE'
    ) # type: ignore
    
    def draw(self, context):
        prefs = dependency_manager.get_addon_prefs(context)
        layout = self.layout
        
        props = layout.column()
        props.enabled = not prefs.deps_check == 'INSTALLING'
        props.prop(self, "dependencies_driver")
        props.prop(self, "dependencies_path")
        
        row = layout.split(factor=0.7)
        
        labels = row.column()
        operators = row.column()
        
        operators.operator("rotoforge.test_dependencies", icon='FILE_REFRESH')
        
        if prefs.deps_check in ['NONE', 'SETUP_ERROR']:
            labels.label(text="Please check the dependencies with the button to the right:")
            return
        
        install = operators.column_flow()
        install.scale_y = 2.0
        
        if prefs.deps_check == 'PASSED':
            labels.label(text="Dependencies are installed, nothing to do here!")
            install_op = install.operator("rotoforge.install_dependencies", text="Forceupdate (Redownloads ~8GB)")
            install_op.override = True
        else:
            if prefs.deps_check == 'INSTALLING':
                labels.label(text="Dependencies are installing...")
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
            box = layout.box()
            if log_filepath is None:
                return
            with open(log_filepath, 'r') as file:
                lines = file.readlines()
                for line in lines if prefs.show_log else lines[-10:]:
                    if line.startswith("Progress "):
                        line = line.removeprefix("Progress ")
                        cur, max_val = line.split(" of ")
                        cur = float(cur)
                        max_val = float(max_val)

                        # Convert to MB/GB format
                        cur_mb = cur / (1024 * 1024)
                        max_mb = max_val / (1024 * 1024)

                        # Format based on size
                        if max_mb >= 1024:
                            cur_display = f"{cur_mb/1024:.1f} GB"
                            max_display = f"{max_mb/1024:.1f} GB"
                        else:
                            cur_display = f"{cur_mb:.1f} MB"
                            max_display = f"{max_mb:.1f} MB"
                        
                        factor = cur/max_val

                        box.progress(text=f"Download: {factor*100:.1f}% - {cur_display} / {max_display}", factor=factor)
                    else:
                        box.label(text=line)

        
        log_label(install_logfile_path)
            

CLASSES = [RotoForge_Preferences,
           Test_Dependencies_Operator,
           Install_Dependencies_Operator,
           ]

FUNCTION_MODULES = ["restart", "data_manager", "dependency_manager", "overlay", "setup_ui", "prompt_utils"]

def register():
    global install_logfile_path
    global install_process
    global install_timer
    global install_override

    install_logfile_path = None
    install_process = None
    install_timer = None
    install_override = False

    for cls in CLASSES:
        bpy.utils.register_class(cls)
    
    print(f"{EXTENSION_NAME}: Registering extension...")
    prefs = dependency_manager.get_addon_prefs(bpy.context)
    prefs.deps_check = 'NONE'
    for module in FUNCTION_MODULES:
        try:
            print(f"{EXTENSION_NAME}: Registering module: {module}")
            if module in sys.modules:
                globals()[module] = importlib.reload(sys.modules[module])
            else:
                globals()[module] = importlib.import_module(f".functions.{module}", package=__package__)
            globals()[module].register()
        except ImportError as e:
            prefs.deps_check = 'SETUP_ERROR'
            print(f"{EXTENSION_NAME}: An ImportError occured while registering the extension")
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
        except Exception as e:
            prefs.deps_check = 'SETUP_ERROR'
            print(f"{EXTENSION_NAME}: Something went very wrong while registering the extension, please get that checked")
            if hasattr(e, 'message'):
                print(e.message)
            else:
                print(e)
    

def unregister():
    global install_process
    global install_timer

    print(f"{EXTENSION_NAME}: Unregistering extension...")

    if install_timer is not None:
        try:
            bpy.app.timers.unregister(install_timer)
            install_timer = None
        except Exception:
            pass

    if install_process is not None:
        try:
            if install_process.poll() is None:
                print(f"{EXTENSION_NAME}: Terminating active installer: {install_process}")
                install_process.send_signal(SIGINT)
                install_process.wait()
            install_process = None
        except Exception as e:
            print(f"{EXTENSION_NAME}: Failed to terminate installer: {e!r}")
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