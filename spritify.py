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
import sys
import shutil

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


def show_message(operator, message, title="Spritify", icon='INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    print("[{}]".format(title), message, file=sys.stderr)
    if operator is not None:
        operator.report({'INFO'}, "[{}] {}".format(title, message))
    else:
        print("[{}] operator is None in show_message."
              "".format(title), file=sys.stderr)
    '''
    try:
        bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)
        # ^ crashes, but does *not* raise exception!
        #   The reason seems to be bad pointer (access violation)
        #   according to <https://devtalk.blender.org/t/impossible-to-invoke-
        #   a-message-inside-of-a-timer-app-make-blender-2-8-crash/7451/3>
    except Exception:
        print(exn, file=sys.stderr)
    '''

@persistent
def spritify(scene, operator):
    if scene.spritesheet.auto_sprite:
        print("[Spritify] Making sprite sheet")
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
        destination = None
        for suffix in suffixes:
            print('[Spritify] Preloading suffix "{}"'.format(suffix))
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
                    '\n\nGenerate Sprite Sheet requires:'
                    '\n1. Output Properties: Set format to PNG'
                    '\n2. Render, Render Animation.'
                    ''.format(render_dir)
                )
            print("[Spritify] Processing {} image(s)".format(len(images)))
            # While is faster than for+range
            if per_file < 1:
                raise ValueError("The offset cannot be less than 1.")
                # ^ Prevent an infinite loop.

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
                print('[Spritify] processing "{}"'.format(filename))
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
                montage_path = os.path.join(bin_path, "montage")
                if not os.path.isfile(montage_path):
                    raise FileNotFoundError(
                        'The executable "{}" does not exist.'
                        '\nTIP: Make sure ImageMagick is installed and that'
                        ' the bin directory is correct'
                        ' in Render Properties, Spritify.'
                        ''.format(montage_path)
                    )
                depth = "8"
                destination = bpy.path.abspath(filename)
                montage_call = [
                    montage_path,
                    "-depth",
                    depth,
                    "-tile",
                    tile_setting,
                    "-geometry",
                    geometry,
                    "-background",
                    background,
                    "-quality",
                    str(scene.spritesheet.quality),
                ]  # See extend below for source, & append for destination
                montage_call.extend(current_images)
                montage_call.append(destination)

                result = subprocess.call(montage_call)
                # print("[Spritify]", montage_call, "result:", result)
                # ^ still 1 even if succeeds for some reason
                offset += per_file
                index += 1
        if os.path.isfile(destination):
            msg = ('Spritify finished writing auto_sprite "{}".'
                   ''.format(destination))
            show_message(operator, msg, title="spritify")
            return {'message': msg}
        else:
            msg = ('Spritify failed to write auto_sprite "{}".'
                   ''.format(destination))
            show_message(operator, msg, icon="ERROR", title="spritify")
            return {'error': msg}



@persistent
def gifify(scene, operator):
    if scene.spritesheet.auto_gif:
        print("[Spritify] Generating animated GIF")
        # Remove existing animated GIF if it's already there
        #   (uses the same path as the spritesheet)
        if os.path.exists(
                bpy.path.abspath(scene.spritesheet.filepath[:-3] + "gif")
                ):
            os.remove(bpy.path.abspath(scene.spritesheet.filepath[:-3] + "gif"))

        # If windows, try and find binary
        converter_path = "%s/convert" % scene.spritesheet.imagemagick_path
        # ^ formerly convert_path which was ambiguous (See new try_path
        #   for temp image files).

        if os.name == "nt":
            bin_path = find_bin_path_windows()

            if bin_path:
                converter_path = os.path.join(bin_path, "convert")

        if not os.path.isfile(converter_path):
            raise FileNotFoundError(
                'The executable "{}" does not exist.'
                '\n\nTIP: Make sure ImageMagick is installed and that'
                ' the bin directory is correct in Render Properties, Spritify.'
                ''.format(converter_path)
            )

        mixed_files_path, name_partial = os.path.split(scene.render.filepath)
        # ^ It is a partial name--It may have numbers after it.
        # partial, dotext = os.path.splitext(name_partial)
        found_any_file = None
        source = bpy.path.abspath(scene.render.filepath) + "*"
        # ^ The scene render filepath becomes part of each png
        #   frame filename.
        convert_tmp_dir = os.path.join(mixed_files_path, "spritify")
        if os.path.isdir(convert_tmp_dir):
            shutil.rmtree(convert_tmp_dir)
        os.makedirs(convert_tmp_dir)
        if os.path.isdir(mixed_files_path):
            for sub in os.listdir(mixed_files_path):
                if sub.startswith("."):
                    continue
                if sub.lower().endswith(".tmp"):
                    continue
                if sub.lower().endswith(".txt"):
                    # such as {blendfilename.splitext()[0]}.crash.txt
                    continue
                if not sub.lower().endswith(".png"):
                    # Allow *only* png animation frames!
                    continue
                sub_path = os.path.join(mixed_files_path, sub)
                if not os.path.isfile(sub_path):
                    continue
                found_any_file = sub_path
                new_path = os.path.join(convert_tmp_dir, sub)
                shutil.move(sub_path, new_path)
                break

        if found_any_file is None:
            caveat = ""
            raise FileNotFoundError(
                'There are no "{}" PNG files.'
                '\n\nGenerating GIF requires:'
                '\n1. Output Properties: Set format to PNG'
                '\n2. Render, Render Animation.'
                '\n3. Generate Sprite Sheet'
                ''.format(source)
            )
        delay = "1x" + str(scene.render.fps)
        dispose = "background"
        loop = "0"
        destination = bpy.path.abspath(scene.spritesheet.filepath[:-3] + "gif")
        if os.path.isfile(destination):
            show_message(operator, 'Overwriting "{}"'.format(destination))
            os.remove(destination)
        if not os.path.isdir(convert_tmp_dir):
            raise FileNotFoundError(
                'convert_tmp_dir does not exist: "{}"'
                ''.format(convert_tmp_dir)
            )
        subprocess.call([
            convert_tmp_dir,
            "-delay",
            delay,
            "-dispose",
            dispose,
            "-loop",
            loop,
            source,
            # FIXME: ^ scene.render.filepath assumes the files in the
            #   render path are only for the rendered animation
            destination
        ])
        if os.path.isfile(destination):
            msg = 'Spritify finished writing auto_gif "{}".'.format(destination)
            show_message(operator, msg, title="Spritify gifify")
            return {'message': msg}
        else:
            msg = 'Spritify failed to create auto_gif "{}".'.format(destination)
            show_message(operator, msg, icon="ERROR", title="Spritify gifify")
            return {'error': msg}


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
            print("[Spritify] not done yet")

    def execute(self, context):
        toggle = False
        if not context.scene.spritesheet.auto_sprite:
            context.scene.spritesheet.auto_sprite = True
            toggle = True
        self.show_results(
            spritify(self, context.scene)
        )

        if toggle:
            context.scene.spritesheet.auto_sprite = False
        return {'FINISHED'}

    def show_results(self, results):
        '''
        Handle output from helper functions (show error or message if any).
        See also show_results in GIFifyOperator.
        '''
        if results is not None:
            error = results.get('error')
            message = results.get('message')
            if error is not None:
                self.report({'ERROR'}, error)
            elif message is not None:
                self.report({'INFO'}, message)


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
            print("[Spritify] not done yet")

    def execute(self, context):
        toggle = False
        if not context.scene.spritesheet.auto_gif:
            context.scene.spritesheet.auto_gif = True
            toggle = True
        self.show_results(
            gifify(context.scene, self)
        )
        if results is not None:
            error = results.get('error')
            message = results.get('message')
            if error is not None:
                self.report({'ERROR'}, error)
            elif message is not None:
                self.report({'INFO'}, message)

        if toggle:
            context.scene.spritesheet.auto_gif = False
        return {'FINISHED'}

    def show_results(self, results):
        '''
        Handle output from helper functions (show error or message if any).
        See also show_results in SpritifyOperator.
        '''
        if results is not None:
            error = results.get('error')
            message = results.get('message')
            if error is not None:
                self.report({'ERROR'}, error)
            elif message is not None:
                self.report({'INFO'}, message)


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
