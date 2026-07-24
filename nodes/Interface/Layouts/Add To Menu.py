import bpy
from ...base_node import SN_ScriptingBaseNode



class SN_AddToMenuNodeNew(SN_ScriptingBaseNode, bpy.types.Node):

    bl_idname = "SN_AddToMenuNodeNew"
    bl_label = "Add To Menu"
    bl_width_default = 200
    def layout_type(self, _): return "layout"
    is_trigger = True
    node_color = "INTERFACE"

    def on_create(self, context):
        self.add_boolean_input("Hide")
        self.add_dynamic_interface_output("Menu")


    append: bpy.props.EnumProperty(default="APPEND", items=[
                                    ("PREPEND", "Prepend", "Prepend this to the start of the menu"),
                                    ("APPEND", "Append", "Append this to the end of the menu")],
                                    name="Position",
                                    description="Position of this interface to the selected menu",
                                    update=SN_ScriptingBaseNode._evaluate)

    menu_parent: bpy.props.StringProperty(default="VIEW3D_MT_add",
                                    name="Parent",
                                    description="The menu id this interface should be shown in",
                                    update=SN_ScriptingBaseNode._evaluate)


    def evaluate(self, context):
        uid = self.uuid
        func_name = f"sna_add_to_{self.menu_parent.lower()}_{uid}"
        register_func_name = f"sna_register_add_to_menu_{uid}"
        append_mode = self.append.lower()

        self.code = f"""
            def {func_name}(self, context):
                if not ({self.inputs["Hide"].python_value}):
                    layout = self.layout
                    {self.indent([out.python_value if out.name == 'Menu' else '' for out in self.outputs], 5)}


            def {register_func_name}():
                menu_type = getattr(bpy.types, "{self.menu_parent}", None)
                if menu_type is not None:
                    try:
                        menu_type.remove({func_name})
                    except Exception:
                        pass
                    menu_type.{append_mode}({func_name})
                return None
        """
        
        if self.menu_parent == "WM_MT_button_context":
            self.code_imperative = """
                class WM_MT_button_context(bpy.types.Menu):
                    bl_label = ""
                    
                    def draw(self, context):
                        pass
            """

        if context.scene.sn.is_exporting:
            register_code = f"bpy.types.{self.menu_parent}.{append_mode}({func_name})"
            unregister_code = f"bpy.types.{self.menu_parent}.remove({func_name})"
        else:
            register_code = (
                f"bpy.app.timers.register({register_func_name}, first_interval=0.01)"
            )
            unregister_code = f"""
                try: bpy.app.timers.unregister({register_func_name})
                except Exception: pass
                menu_type = getattr(bpy.types, "{self.menu_parent}", None)
                if menu_type is not None:
                    try: menu_type.remove({func_name})
                    except Exception: pass
            """

        self.code_register = f"""
            {"if getattr(bpy.types, 'WM_MT_button_context', None) == None: bpy.utils.register_class(WM_MT_button_context)" if self.menu_parent == "WM_MT_button_context" else ""}
            {register_code}
        """
        self.code_unregister = f"""
            {unregister_code}
        """


    def draw_node(self, context, layout):
        row = layout.row()
        row.scale_y = 1.3
        op = row.operator("sn.activate_menu_picker", text=f"{self.menu_parent.replace('_MT_', ' ').replace('_', ' ').title()}", icon="EYEDROPPER")
        op.node_tree = self.node_tree.name
        op.node = self.name
        
        layout.prop(self, "append", expand=True)


    def draw_node_panel(self, context, layout):
        layout.prop(self, "menu_parent")
