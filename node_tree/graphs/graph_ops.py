from bpy_extras.io_utils import ImportHelper
import bpy
import os

from ...interface.panels.graph_ui_list import get_selected_graph, get_selected_graph_offset
from ...nodes.compiler import unregister_addon, compile_addon
from ...utils import collection_has_item
from .node_tree import ScriptingNodesTree



def _remove_temporarily_linked_ids(collection, previous):
    """Remove datablocks that a temporary library link pulled in.

    Removing a library also frees every id linked from it, and a file can
    pull in further libraries indirectly, so wrappers in the diff may already
    be dead by the time they are removed.
    """
    for item in set(collection.values()) - previous:
        try:
            collection.remove(item)
        except (ReferenceError, RuntimeError):
            pass


def append_missing_properties(context, path):
    """Copy Serpens property definitions from another file into this scene.

    Appended graphs reference addon properties by name, but property
    definitions live on the source file's scenes, not on the node tree, so
    they don't come along with the appended datablock. This temporarily links
    the source scenes, copies any property definitions (and their categories)
    that don't exist here yet, and unlinks everything again. Properties that
    already exist by name are kept as they are so appended nodes bind to them.
    """
    sn = context.scene.sn
    copied = []

    prev_scenes = set(bpy.data.scenes.values())
    prev_libraries = set(bpy.data.libraries.values())
    try:
        with bpy.data.libraries.load(path, link=True) as (data_from, data_to):
            data_to.scenes = list(data_from.scenes)
    except (OSError, RuntimeError) as error:
        print(
            "Serpens Warning: could not read properties from"
            f" '{path}': {error}"
        )
        return copied

    try:
        for scene in bpy.data.scenes:
            if scene in prev_scenes or not hasattr(scene, "sn"):
                continue
            for prop in scene.sn.properties:
                if not prop.name or collection_has_item(sn.properties, prop.name):
                    continue
                if prop.category and not collection_has_item(
                    sn.property_categories, prop.category
                ):
                    if prop.category != "OTHER":
                        sn.property_categories.add().name = prop.category
                new_prop = sn.properties.add()
                prop.match_settings(new_prop)
                new_prop.attach_to = prop.attach_to
                copied.append(new_prop.name)
    finally:
        # remove everything the temporary link pulled in
        _remove_temporarily_linked_ids(bpy.data.libraries, prev_libraries)
        _remove_temporarily_linked_ids(bpy.data.scenes, prev_scenes)

    return copied


def get_serpens_graphs_in_file(path):
    """Return the names of the Serpens node trees in the given blend file.

    A library load only exposes datablock names, not their types, so the
    file's node groups are linked temporarily to check their bl_idname and
    unlinked again right away.
    """
    graphs = []
    prev_groups = set(bpy.data.node_groups.values())
    prev_libraries = set(bpy.data.libraries.values())
    try:
        with bpy.data.libraries.load(path, link=True) as (data_from, data_to):
            data_to.node_groups = list(data_from.node_groups)
    except (OSError, RuntimeError) as error:
        print(
            "Serpens Warning: could not read node trees from"
            f" '{path}': {error}"
        )
        return graphs

    try:
        for group in bpy.data.node_groups:
            if group not in prev_groups and group.bl_idname == "ScriptingNodesTree":
                graphs.append(group.name)
    finally:
        # drop any cached link data for the trees that are about to go away
        # so a later tree at a recycled id can't pick up dangling sockets
        for group in set(bpy.data.node_groups.values()) - prev_groups:
            ScriptingNodesTree.link_cache.pop(id(group), None)
        _remove_temporarily_linked_ids(bpy.data.libraries, prev_libraries)
        _remove_temporarily_linked_ids(bpy.data.node_groups, prev_groups)

    return graphs


def get_serpens_graphs():
    graphs = []
    for group in bpy.data.node_groups:
        if group.bl_idname == "ScriptingNodesTree":
            graphs.append(group)
    return graphs


def reassign_tree_indices():
    trees = []
    for ngroup in bpy.data.node_groups:
        if ngroup.bl_idname == "ScriptingNodesTree":
            trees.append(ngroup)
    trees = sorted(trees, key=lambda tree: tree.index)

    for i in range(len(trees)):
        trees[i].index = i
    return trees



class SN_OT_AddGraph(bpy.types.Operator):
    bl_idname = "sn.add_graph"
    bl_label = "Add Node Tree"
    bl_description = "Adds a node tree to the addon"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def execute(self, context):
        sn = context.scene.sn
        trees = reassign_tree_indices()
        
        curr_index = 0
        if sn.node_tree_index < len(bpy.data.node_groups) and bpy.data.node_groups[sn.node_tree_index].bl_idname == "ScriptingNodesTree":
            curr_index = bpy.data.node_groups[sn.node_tree_index].index
            for i in range(curr_index+1, len(trees)):
                trees[i].index += 1

        graph = bpy.data.node_groups.new("NodeTree", "ScriptingNodesTree")
        graph.index = curr_index - 1
        if sn.active_graph_category != "ALL":
            graph.category = sn.active_graph_category

        for i, group in enumerate(bpy.data.node_groups):
            if group == graph:
                sn.node_tree_index = i
        return {"FINISHED"}



class SN_OT_RemoveGraph(bpy.types.Operator):
    bl_idname = "sn.remove_graph"
    bl_label = "Remove Node Tree"
    bl_description = "Removes this node tree from the addon"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        if context.scene.sn.node_tree_index < len(bpy.data.node_groups):
            return bpy.data.node_groups[context.scene.sn.node_tree_index].bl_idname == "ScriptingNodesTree"

    def execute(self, context):
        sn = context.scene.sn
        group = bpy.data.node_groups[sn.node_tree_index]
        curr_index = group.index
        bpy.data.node_groups.remove(group)

        trees = reassign_tree_indices()
        for tree in trees:
            if tree.index == curr_index:
                for i, ntree in enumerate(bpy.data.node_groups):
                    if ntree == tree:
                        sn.node_tree_index = i
                break
            elif tree.index == curr_index - 1:
                for i, ntree in enumerate(bpy.data.node_groups):
                    if ntree == tree:
                        sn.node_tree_index = i
                break
        else:
            sn.node_tree_index = 0
            

        compile_addon()
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    
    
    
class SN_OT_AppendGraph(bpy.types.Operator, ImportHelper):
    bl_idname = "sn.append_graph"
    bl_label = "Append Node Tree"
    bl_description = "Appends a node tree from another file to this addon"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    
    filter_glob: bpy.props.StringProperty( default='*.blend', options={'HIDDEN'} )

    def execute(self, context):
        _, extension = os.path.splitext(self.filepath)
        if extension == ".blend":
            bpy.ops.sn.append_popup("INVOKE_DEFAULT", path=self.filepath)
        return {"FINISHED"}



class SN_OT_AppendPopup(bpy.types.Operator):
    bl_idname = "sn.append_popup"
    bl_label = "Append Node Tree"
    bl_description = "Appends this node tree from the addon"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    # cached on invoke; also keeps the enum item strings referenced
    graph_items = [("NONE", "NONE", "NONE")]

    def get_graph_items(self, context):
        """ Returns the Serpens node trees found in the selected file """
        return SN_OT_AppendPopup.graph_items

    path: bpy.props.StringProperty(options={"HIDDEN", "SKIP_SAVE"})

    graph: bpy.props.EnumProperty(name="Node Tree",
                                   description="Node Tree to import",
                                   items=get_graph_items,
                                   options={"HIDDEN", "SKIP_SAVE"})

    def execute(self, context):
        if self.graph != "NONE":
            # save previous groups
            prev_groups = bpy.data.node_groups.values()

            # append node group
            with bpy.data.libraries.load(self.path) as (_, data_to):
                data_to.node_groups = [self.graph]
            
            # bring the property definitions the graph references with it
            copied_props = append_missing_properties(context, self.path)
            if copied_props:
                self.report(
                    {"INFO"},
                    message=f"Appended {len(copied_props)} properties:"
                    f" {', '.join(copied_props)}",
                )

            # register new graph
            new_groups = set(prev_groups) ^ set(bpy.data.node_groups.values())
            for group in new_groups:
                context.scene.sn.node_tree_index = bpy.data.node_groups.values().index(group)
            compile_addon()

            # redraw screen
            context.area.tag_redraw()
        return {"FINISHED"}
    
    def draw(self, context):
        if self.graph == "NONE":
            self.layout.label(text="No Serpens node trees found in this blend file",icon="ERROR")
        else:
            self.layout.prop(self, "graph", text="Node Tree")

    def invoke(self, context, event):
        graphs = get_serpens_graphs_in_file(self.path)
        SN_OT_AppendPopup.graph_items = [
            (name, name, name) for name in graphs
        ] or [("NONE", "NONE", "NONE")]
        return context.window_manager.invoke_props_dialog(self)



class SN_OT_ForceCompile(bpy.types.Operator):
    bl_idname = "sn.force_compile"
    bl_label = "This might be slow for large addons!"
    bl_description = "Forces all node trees to compile"
    bl_options = {"REGISTER", "INTERNAL"}

    def fix_compile_order(self, refs):
        for node in refs.nodes:
            if node.order == 0:
                node.order = 3

    def execute(self, context):
        for ntree in bpy.data.node_groups:
            if ntree.bl_idname == "ScriptingNodesTree":
                for refs in ntree.node_refs:
                    refs.clear_unused_refs()
                    refs.fix_ref_names()
                    if refs.name == "SN_OnKeypressNode":
                        self.fix_compile_order(refs)
                ntree.reevaluate()
        compile_addon()
        self.report({"INFO"}, message="Compiled successfully!")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)



class SN_OT_ForceUnregister(bpy.types.Operator):
    bl_idname = "sn.force_unregister"
    bl_label = "Force Unregister"
    bl_description = "Forces all node trees to unregister"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        unregister_addon()
        return {"FINISHED"}



class SN_OT_MoveNodeTree(bpy.types.Operator):
    bl_idname = "sn.move_node_tree"
    bl_label = "Move Node Tree"
    bl_description = "Moves this node tree in the list"
    bl_options = {"REGISTER", "INTERNAL"}
    
    move_up: bpy.props.IntProperty(options={"SKIP_SAVE", "HIDDEN"})

    def execute(self, context):
        reassign_tree_indices()

        ntree = get_selected_graph()
        before = get_selected_graph_offset(-1)
        after = get_selected_graph_offset(1)

        # move trees
        if ntree:
            if self.move_up and before:
                temp_index = ntree.index
                ntree.index = before.index
                before.index = temp_index
            elif not self.move_up and after:
                temp_index = ntree.index
                ntree.index = after.index
                after.index = temp_index
        return {"FINISHED"}