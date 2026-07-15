import bpy
from bpy_extras.io_utils import ImportHelper
import os



class SN_OT_AddAsset(bpy.types.Operator):
    bl_idname = "sn.add_asset"
    bl_label = "Add Asset"
    bl_description = "Adds a asset to the addon"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    
    add_type: bpy.props.EnumProperty(default="FILE",
                                items=[("FILE", "File", "Import a single file"),
                                       ("DIRECTORY", "Directory", "Import a full directory")],
                                name="Type",
                                description="Add this directory or this file as an asset",
                                options={"SKIP_SAVE"})
    
    def execute(self, context):
        bpy.ops.sn.load_asset("INVOKE_DEFAULT", add_type=self.add_type)
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "add_type", expand=True)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=200)



class SN_OT_LoadAsset(bpy.types.Operator, ImportHelper):
    bl_idname = "sn.load_asset"
    bl_label = "Add Asset"
    bl_description = "Adds a asset to the addon"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    
    add_type: bpy.props.EnumProperty(default="FILE",
                                items=[("FILE", "File", "Import a single file"),
                                       ("DIRECTORY", "Directory", "Import a full directory")],
                                name="Type",
                                description="Add this directory or this file as an asset",
                                options={"SKIP_SAVE"})
    
    def execute(self, context):
        sn = context.scene.sn
        new_asset = sn.assets.add()
        if self.add_type == "DIRECTORY":
            new_asset.path = os.path.dirname(self.filepath)
        else:
            new_asset.path = self.filepath
        for index, asset in enumerate(sn.assets):
            if asset == new_asset:
                sn.asset_index = index
        return {"FINISHED"}




class SN_OT_RemoveAsset(bpy.types.Operator):
    bl_idname = "sn.remove_asset"
    bl_label = "Remove Asset"
    bl_description = "Removes this asset from the addon"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return context.scene.sn.asset_index < len(context.scene.sn.assets)

    def execute(self, context):
        sn = context.scene.sn
        asset = sn.assets[sn.asset_index]
        # remove removed from asset nodes
        for ntree in bpy.data.node_groups:
            if ntree.bl_idname == "ScriptingNodesTree":
                for node in ntree.nodes:
                    if node.bl_idname == "SN_AssetNode":
                        if node.asset == asset.name:
                            node.asset = ""
        # remove asset
        sn.assets.remove(sn.asset_index)
        sn.asset_index -= 1
        return {"FINISHED"}
    
    
    
class SN_OT_FindMissingAssets(bpy.types.Operator):
    bl_idname = "sn.find_missing_assets"
    bl_label = "Find Missing Assets"
    bl_description = "Try to find missing asset files below the selected directory and update their paths"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    directory: bpy.props.StringProperty(
        subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"}
    )
    filter_folder: bpy.props.BoolProperty(
        default=True, options={"HIDDEN", "SKIP_SAVE"}
    )

    @classmethod
    def poll(cls, context):
        return len(context.scene.sn.assets)

    def execute(self, context):
        sn = context.scene.sn
        missing = [
            asset
            for asset in sn.assets
            if asset.path and not os.path.exists(bpy.path.abspath(asset.path))
        ]
        if not missing:
            self.report({"INFO"}, message="No missing assets found")
            return {"FINISHED"}

        # index the search directory once; os.walk is top down, so the
        # shallowest occurrence of a name wins when there are duplicates
        found_files = {}
        found_dirs = {}
        search_root = os.path.normpath(bpy.path.abspath(self.directory))
        found_dirs.setdefault(
            os.path.basename(search_root).lower(), search_root
        )
        for root, dirs, files in os.walk(search_root):
            for name in files:
                found_files.setdefault(name.lower(), os.path.join(root, name))
            for name in dirs:
                found_dirs.setdefault(name.lower(), os.path.join(root, name))

        updated = 0
        still_missing = []
        for asset in missing:
            old_path = os.path.normpath(bpy.path.abspath(asset.path))
            basename = os.path.basename(old_path).lower()
            # file assets usually have an extension, directory assets don't
            if os.path.splitext(old_path)[1]:
                new_path = found_files.get(basename) or found_dirs.get(basename)
            else:
                new_path = found_dirs.get(basename) or found_files.get(basename)
            if new_path:
                asset.path = new_path
                updated += 1
            else:
                still_missing.append(asset.name)

        if still_missing:
            self.report(
                {"WARNING"},
                message=f"Updated {updated} asset paths, still missing:"
                f" {', '.join(still_missing)}",
            )
        else:
            self.report({"INFO"}, message=f"Updated {updated} asset paths")
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}



class SN_OT_MoveAsset(bpy.types.Operator):
    bl_idname = "sn.move_asset"
    bl_label = "Move Asset"
    bl_description = "Moves this asset in the list"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    move_up: bpy.props.BoolProperty(options={"SKIP_SAVE", "HIDDEN"})

    @classmethod
    def poll(cls, context):
        return context.scene.sn.asset_index < len(context.scene.sn.assets)

    def execute(self, context):
        sn = context.scene.sn
        new_index = sn.asset_index + (-1 if self.move_up else 1)
        if 0 <= new_index < len(sn.assets):
            sn.assets.move(sn.asset_index, new_index)
            sn.asset_index = new_index
        return {"FINISHED"}



class SN_OT_FindNode(bpy.types.Operator):
    bl_idname = "sn.find_node"
    bl_label = "Find Node"
    bl_description = "Find Node"
    bl_options = {"REGISTER", "INTERNAL"}
    
    node_tree: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})
    node: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        ntree = bpy.data.node_groups[self.node_tree]
        # set active graph and select
        context.space_data.node_tree = ntree
        for index, group in enumerate(bpy.data.node_groups):
            if group == ntree:
                context.scene.sn.node_tree_index = index
        # select node and frame
        for node in ntree.nodes:
            node.select = node.name == self.node
        bpy.ops.node.view_selected("INVOKE_DEFAULT")
        return {"FINISHED"}



class SN_OT_FindAsset(bpy.types.Operator):
    bl_idname = "sn.find_asset"
    bl_label = "Find Asset"
    bl_description = "Finds this asset in the addon"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def execute(self, context):
        return {"FINISHED"}
    
    def draw(self, context):
        layout = self.layout
        
        # init asset nodes
        empty_nodes = []
        asset_nodes = []
        asset = None
        if context.scene.sn.asset_index < len(context.scene.sn.assets):
            asset = context.scene.sn.assets[context.scene.sn.asset_index]

        # find assets nodes
        for ntree in bpy.data.node_groups:
            if ntree.bl_idname == "ScriptingNodesTree":
                for node in ntree.nodes:
                    if node.bl_idname == "SN_AssetNode":
                        if asset and node.asset == asset.name:
                            asset_nodes.append(node)
                        elif not node.asset:
                            empty_nodes.append(node)
                        
        # draw nodes for selected asset    
        if context.scene.sn.asset_index < len(context.scene.sn.assets):
            col = layout.column()
            row = col.row()
            row.enabled = False
            row.label(text=f"Asset: {asset.name}")
            
            for node in asset_nodes:
                op = col.operator("sn.find_node", text=node.name, icon="RESTRICT_SELECT_OFF")
                op.node_tree = node.node_tree.name
                op.node = node.name
            
            if not asset_nodes:
                col.label(text="No nodes found for this asset", icon="INFO")
        
        # draw nodes with empty asset
        col = layout.column()
        row = col.row()
        row.label(text="Empty Asset Nodes")
        row.enabled = False
        
        for node in empty_nodes:
            op = col.operator("sn.find_node", text=node.name, icon="RESTRICT_SELECT_OFF")
            op.node_tree = node.node_tree.name
            op.node = node.name

        if not empty_nodes:
            col.label(text="No empty asset nodes found", icon="INFO")
    
    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=250)
    
    

class SN_OT_AddAssetNode(bpy.types.Operator):
    bl_idname = "sn.add_asset_node"
    bl_label = "Add Asset Node"
    bl_description = "Adds an asset node"
    bl_options = {"REGISTER", "INTERNAL"}
    
    def execute(self, context):
        bpy.ops.node.add_node("INVOKE_DEFAULT", type="SN_AssetNode", use_transform=True)
        node = context.space_data.node_tree.nodes.active
        if context.scene.sn.asset_index < len(context.scene.sn.assets):
            node.asset = context.scene.sn.assets[context.scene.sn.asset_index].name
        return {"FINISHED"}