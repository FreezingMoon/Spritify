'''
Convert rendered frames into a sprite sheet once render is complete.
'''
# ***** BEGIN GPL LICENSE BLOCK *****
#
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ***** END GPL LICENCE BLOCK *****
import bpy
import os
import subprocess
import math
from bpy.app.handlers import persistent

bl_info = {
    "name": "Spritify",
    "author": "Jason van Gumster (Fweeb)",
    "version": (0, 6, 4),
    "blender": (2, 80, 0),
    "location": "Render > Spritify",
    "description": ("Converts rendered frames into a sprite sheet"
                    " once render is complete"),
    "warning": "Requires ImageMagick",
    "wiki_url": ("http://wiki.blender.org/index.php"
                 "?title=Extensions:2.6/Py/Scripts/Render/Spritify"),
    "tracker_url": "https://github.com/FreezingMoon/Spritify/issues",
    "category": "Render",
}


class SpriteSheetProperties(bpy.types.PropertyGroup):
    filepath: bpy.props.StringProperty(
        name="Sprite Sheet Filepath",
        description="Save location for sprite sheet (should be PNG format)",
        subtype='FILE_PATH',
        default=os.path.join(
            bpy.context.preferences.filepaths.render_output_directory,
            "sprites.png"
        ),
    )
    imagemagick_path: bpy.props.StringProperty(
        name="Imagemagick Path",
        description=("Path where the Imagemagick binaries can be found"
                     " (only on Linux and macOS)"),
        subtype='FILE_PATH',
        default='/usr/bin',
    )
    quality: bpy.props.IntProperty(
        name="Quality",
        description="Quality setting for sprite sheet image",
        subtype='PERCENTAGE',
        max=100,
        default=100,
    )
    is_rows: bpy.props.EnumProperty(
        name="Rows/Columns",
        description="Choose if tiles will be arranged by rows or columns",
        items=(('ROWS', "Rows", "Rows"), ('COLUMNS', "Columns", "Columns")),
        default='ROWS',
    )
    tiles: bpy.props.IntProperty(
        name="Tiles",
        description="Number of tiles in the chosen direction (rows or columns)",
        default=8,
    )
    files: bpy.props.IntProperty(
        name="File count",
        description="Number of files to split sheet into",
        default=1,
    )
    offset_x: bpy.props.IntProperty(
        name="Offset X",
        description="Horizontal offset between tiles (in pixels)",
        default=2,
    )
    offset_y: bpy.props.IntProperty(
        name="Offset Y",
        description="Vertical offset between tiles (in pixels)",
        default=2,
    )
    bg_color: bpy.props.FloatVectorProperty(
        name="Background Color",
        description="Fill color for sprite backgrounds",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(0.0, 0.0, 0.0, 0.0),
    )
    auto_sprite: bpy.props.BoolProperty(
        name="AutoSpritify",
        description=("Automatically create a spritesheet"
                     " when rendering is complete"),
        default=True,
    )
    auto_gif: bpy.props.BoolProperty(
        name="AutoGIF",
        description=("Automatically create an animated GIF"
                     " when rendering is complete"),
        default=True,
    )
    support_multiview: bpy.props.BoolProperty(
        name="Support Multiviews",
        description=("Render multiple spritesheets based on multiview"
                     " suffixes if stereoscopy/multiview is configured"),
        default=True,
    )


def find_bin_path_windows():
    import winreg

    REG_PATH = "SOFTWARE\\ImageMagick\\Current"

    try:
        registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0,
                                      winreg.KEY_READ)
        value, regtype = winreg.QueryValueEx(registry_key, "BinPath")
        winreg.CloseKey(registry_key)

    except WindowsError:
        return None

    print(value)
    return value


@persistent
def spritify(scene):
    if scene.spritesheet.auto_sprite:
        print("Making sprite sheet")
        # Remove existing spritesheet if it's already there
        if os.path.exists(bpy.path.abspath(scene.spritesheet.filepath)):
            os.remove(bpy.path.abspath(scene.spritesheet.filepath))

        if scene.spritesheet.is_rows == 'ROWS':
            tile_setting = str(scene.spritesheet.tiles) + "x"
        else:
            tile_setting = "x" + str(scene.spritesheet.tiles)

        suffixes = []

        if (scene.spritesheet.support_multiview and scene.render.use_multiview
                and scene.render.views_format == 'MULTIVIEW'):
            for view in scene.render.views:
                suffixes.append(view.file_suffix)
        else:
            suffixes.append('')

        for suffix in suffixes:
            print("Preloading {}".format(suffix))
            # Preload images
            images = []
            render_dir = bpy.path.abspath(scene.render.filepath)
            for dirname, dirnames, filenames in os.walk(render_dir):
                for filename in sorted(filenames):
                    if filename.endswith("%s.png" % suffix):
                        images.append(os.path.join(dirname, filename))

            # Calc number of images per file
            per_file = math.ceil(len(images) / scene.spritesheet.files)
            offset = 0
            index = 0

            if len(images) < 1:
                raise FileNotFoundError(
                    'There are 0 images in "{}".'
                    '\nGenerate Sprite Sheet requires:'
                    '\n1. Output Properties: Set format to PNG'
                    '\n2. Render, Render Animation.'
                    ''.format(render_dir)
                )
            # While is faster than for+range
            while offset < len(images):
                current_images = images[offset:offset+per_file]
                filename = scene.spritesheet.filepath
                if scene.spritesheet.files > 1:
                    filename = "%s-%d-%s%s" % (scene.spritesheet.filepath[:-4],
                                               index, suffix,
                                               scene.spritesheet.filepath[-4:])
                else:
                    filename = "%s%s%s" % (scene.spritesheet.filepath[:-4],
                                           suffix,
                                           scene.spritesheet.filepath[-4:])

                bin_path = scene.spritesheet.imagemagick_path

                if os.name == "nt":
                    bin_path = find_bin_path_windows()

                width = (scene.render.resolution_x
                         * scene.render.resolution_percentage / 100)
                height = (scene.render.resolution_y
                          * scene.render.resolution_percentage / 100)

                if scene.render.use_crop_to_border:
                    width = (scene.render.border_max_x
                             * width - scene.render.border_min_x * width)
                    height = (scene.render.border_max_y
                              * height - scene.render.border_min_y * height)
                background = (
                    "rgba({},{},{},{})".format(
                        str(scene.spritesheet.bg_color[0] * 100),
                        str(scene.spritesheet.bg_color[1] * 100),
                        str(scene.spritesheet.bg_color[2] * 100),
                        str(scene.spritesheet.bg_color[3] * 100),
                    )
                )
                geometry = "{}x{}+{}+{}".format(
                    width,
                    height,
                    scene.spritesheet.offset_x,
                    scene.spritesheet.offset_y
                )

                depth = "8"
                montage_call = [
                    "{}/montage".format(bin_path),
                    "-depth",
                    depth,
                    "-tile",
                    tile_setting,
                    "-geometry",
                    geometry,
                    "-background",
                    background,
                    "-quality{}".format(scene.spritesheet.quality),
                ]
                montage_call.extend(current_images)
                montage_call.append(bpy.path.abspath(filename))

                result = subprocess.call(montage_call)
                # print(montage_call, "result:", result)
                # ^ still 1 even if succeeds for some reason
                offset += per_file
                index += 1


@persistent
def gifify(scene):
    if scene.spritesheet.auto_gif:
        print("Generating animated GIF")
        # Remove existing animated GIF if it's already there
        #   (uses the same path as the spritesheet)
        if os.path.exists(
                bpy.path.abspath(scene.spritesheet.filepath[:-3] + "gif")
                ):
            os.remove(bpy.path.abspath(scene.spritesheet.filepath[:-3] + "gif"))

        # If windows, try and find binary
        convert_path = "%s/convert" % scene.spritesheet.imagemagick_path

        if os.name == "nt":
            bin_path = find_bin_path_windows()

            if bin_path:
                convert_path = os.path.join(bin_path, "convert")

        if not os.path.isfile(convert_path):
            raise FileNotFoundError(
                'The executable "{}" does not exist.'
                ' Ensure ImageMagick is installed and that'
                ' the bin directory is correct in Render Options, Spritify.'
                ''.format(convert_path)
            )

        if not os.path.isfile(scene.render.filepath):
            caveat = ""
            raise FileNotFoundError(
                '"{}" does not exist.'
                '\nGenerating GIF requires:'
                '\n1. Output Properties: Set format to PNG'
                '\n2. Render, Render Animation.'
                '\n3. Generate Sprite Sheet'
            )

        subprocess.call([
            convert_path,
            "-delay", "1x" + str(scene.render.fps),
            "-dispose", "background",
            "-loop", "0",
            bpy.path.abspath(scene.render.filepath) + "*",
            # FIXME: ^ scene.render.filepath assumes the files in the
            #   render path are only for the rendered animation
            bpy.path.abspath(scene.spritesheet.filepath[:-3] + "gif")
        ])


class SpritifyOperator(bpy.types.Operator):
    """
    Generate a sprite sheet from completed animation render
    (This operator just wraps the handler to make things easy if
    auto_sprite is False).
    """
    bl_idname = "render.spritify"
    bl_label = "Generate a sprite sheet from a completed animation render"

    @classmethod
    def poll(cls, context):
        '''
        Check if rendering is finished.
        See FIXME notes below regarding:
        - context.scene.render.filepath is //tmp which resolves to tmp
          in directory of blend file. However, being missing/empty
          isn't a reliable way of determining if the render finished.
        '''
        tmp_path = bpy.path.abspath(context.scene.render.filepath)
        if context.scene is not None:
            if not os.path.isdir(tmp_path):
                return True  # FIXME: See comment in next line.
        if (context.scene is not None) and len(os.listdir(tmp_path)) > 0:
            # FIXME: a bit hacky; an empty dir doesn't necessarily mean
            #   that the render has been done
            return True
        else:
            return False
            print("not done yet")

    def execute(self, context):
        toggle = False
        if not context.scene.spritesheet.auto_sprite:
            context.scene.spritesheet.auto_sprite = True
            toggle = True
        spritify(context.scene)
        if toggle:
            context.scene.spritesheet.auto_sprite = False
        return {'FINISHED'}


class GIFifyOperator(bpy.types.Operator):
    """
    Generate an animated GIF from completed animation render
    (This Operator just wraps the handler if auto_gif is False).
    """
    bl_idname = "render.gifify"
    bl_label = "Generate an animated GIF from a completed animation render"

    @classmethod
    def poll(cls, context):
        '''
        Check if rendering is finished.
        See FIXME notes below regarding:
        - context.scene.render.filepath is //tmp which resolves to tmp
          in directory of blend file. However, being missing/empty
          isn't a reliable way of determining if the render finished.
        '''
        tmp_path = bpy.path.abspath(context.scene.render.filepath)
        if context.scene is not None:
            if not os.path.isdir(tmp_path):
                return True  # FIXME: See comment in next line.
        if ((context.scene is not None) and (len(os.listdir(tmp_path)) > 0)):
            # FIXME: a bit hacky; an empty dir doesn't necessarily mean
            #   that the render has been done
            return True
        else:
            return False
            print("not done yet")

    def execute(self, context):
        toggle = False
        if not context.scene.spritesheet.auto_gif:
            context.scene.spritesheet.auto_gif = True
            toggle = True
        gifify(context.scene)
        if toggle:
            context.scene.spritesheet.auto_gif = False
        return {'FINISHED'}


class SpritifyPanel(bpy.types.Panel):
    """UI Panel for Spritify"""
    bl_label = "Spritify"
    bl_idname = "RENDER_PT_spritify"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"

    def draw(self, context):
        layout = self.layout

        layout.prop(context.scene.spritesheet, "imagemagick_path")
        layout.prop(context.scene.spritesheet, "filepath")
        box = layout.box()
        split = box.split(factor=0.5)
        col = split.column()
        col.operator("render.spritify", text="Generate Sprite Sheet")
        col = split.column()
        col.prop(context.scene.spritesheet, "auto_sprite")
        split = box.split(factor=0.5)
        col = split.column(align=True)
        col.row().prop(context.scene.spritesheet, "is_rows", expand=True)
        col.prop(context.scene.spritesheet, "tiles")
        sub = col.split(factor=0.5)
        sub.prop(context.scene.spritesheet, "offset_x")
        sub.prop(context.scene.spritesheet, "offset_y")
        col = split.column()
        col.prop(context.scene.spritesheet, "bg_color")
        col.prop(context.scene.spritesheet, "quality", slider=True)
        box.prop(context.scene.spritesheet, "support_multiview")
        box = layout.box()
        split = box.split(factor=0.5)
        col = split.column()
        col.operator("render.gifify", text="Generate Animated GIF")
        col = split.column()
        col.prop(context.scene.spritesheet, "auto_gif")
        box.label(text="Animated GIF uses the spritesheet filepath")


def register():
    '''
    Register the add-on.
    '''
    bpy.utils.register_class(SpriteSheetProperties)
    bpy.types.Scene.spritesheet = bpy.props.PointerProperty(
        type=SpriteSheetProperties
    )
    bpy.app.handlers.render_complete.append(spritify)
    bpy.app.handlers.render_complete.append(gifify)
    bpy.utils.register_class(SpritifyOperator)
    bpy.utils.register_class(GIFifyOperator)
    bpy.utils.register_class(SpritifyPanel)


def unregister():
    bpy.utils.unregister_class(SpritifyPanel)
    bpy.utils.unregister_class(SpritifyOperator)
    bpy.utils.unregister_class(GIFifyOperator)
    bpy.app.handlers.render_complete.remove(spritify)
    bpy.app.handlers.render_complete.remove(gifify)
    del bpy.types.Scene.spritesheet
    bpy.utils.unregister_class(SpriteSheetProperties)


if __name__ == '__main__':
    register()
