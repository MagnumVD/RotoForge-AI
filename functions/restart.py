import bpy
import subprocess
import os
import sys


def reload_and_restart(reopen_current_file=True):
    bpy.ops.extensions.repo_refresh_all()

    if reopen_current_file:
        current_blend_path = bpy.data.filepath
        relaunch_command = [sys.argv[0]] + ([current_blend_path] if current_blend_path else [])
    else:
        relaunch_command = [sys.argv[0]]

    try:
        # Delay the restart to ensure current instance fully closes first
        # This prevents race conditions with GPU cache files and other resources
        if os.name == 'nt':
            # Windows: Properly quote paths with spaces
            quoted_command = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in relaunch_command)
            delay_command = f'timeout /t 1 /nobreak >nul && start "" {quoted_command}'
            subprocess.Popen(delay_command, shell=True)
        else:
            # Linux/Mac: Use sleep command
            delay_command = ['sh', '-c', f'sleep 1 && {" ".join(relaunch_command)}']
            subprocess.Popen(delay_command)
        bpy.ops.wm.quit_blender()
    except Exception as error_instance:
        print(f"Failed to restart Blender: {error_instance}")


class RestartAction(bpy.types.Operator):
    bl_idname = "rotoforge.restart_action"
    bl_label = "Restart Action"
    bl_options = {'INTERNAL'}

    action: bpy.props.EnumProperty(
        items=[
            ('SAVE', "Save", ""), 
            ('DONT_SAVE', "Don't Save", ""), 
        ]
    ) # type: ignore

    def modal(self, context, event):
        if context.blend_data.filepath:  # Wait until file is saved
            reload_and_restart(reopen_current_file=True)
            return {'FINISHED'}
        return {'PASS_THROUGH'}
    
    def execute(self, context):
        if self.action == 'SAVE':
            if not context.blend_data.filepath:
                bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            else:
                bpy.ops.wm.save_mainfile()
                reload_and_restart(reopen_current_file=True)
                return {'FINISHED'}
        elif self.action == 'DONT_SAVE':
            # Just restart - if there's a saved file, Blender will load the last saved version
            # If unsaved, Blender will start fresh
            # We pass the filepath so saved files reopen at their last saved state
            reload_and_restart(reopen_current_file=bool(bpy.data.filepath))
            return {'FINISHED'}
        return {'CANCELLED'}

class RestartBlenderDialogue(bpy.types.Operator):
    bl_idname = "rotoforge.restart_blender"
    bl_label = "Save changes before restarting?"
    bl_options = {'INTERNAL'}
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)
    def draw(self, context):
        layout = self.layout
        layout.label(text="RotoForge needs to restart Blender to complete the update.")
        col = layout.column()
        if not context.blend_data.filepath:
            box = col.box()
            box.alert = True
            box.label(text="Untitled.blend")
        else:
            filename = os.path.basename(context.blend_data.filepath)
            col.label(text=filename)
        col.separator()
        master_row = col.row()
        split = master_row.split(factor=0.78)
        left_row = split.row()
        left_row.operator("rotoforge.restart_action", text="Save").action = 'SAVE'
        left_row.operator("rotoforge.restart_action", text="Don't Save").action = 'DONT_SAVE'
        right_row = split.row()
        right_row.template_popup_confirm("wm.doc_view", text="", cancel_text="Cancel")
    def execute(self, context):
        return {'CANCELLED'}

classes_to_register = (
    RestartAction,
    RestartBlenderDialogue,
)

def register():
    for cls in classes_to_register:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes_to_register):
        if hasattr(bpy.types, cls.__name__):
            bpy.utils.unregister_class(cls)