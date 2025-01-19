#!/usr/bin/env python3
"""
drcblobviewer - View and edit DRC resource blobs
Created in 2024 by GaryOderNichts
<https://github.com/GaryOderNichts/drcblobviewer>
"""
import tkinter as tk
import tkinter.filedialog
import construct
from PIL import Image, ImageTk
import sys
from enum import IntEnum
from pydub import AudioSegment
from pydub.playback import play
import io
import os

# Structs
BitmapResourceDescriptor = construct.Struct(
    "unknown" / construct.Int32ul, # maybe format / bpp?
    "width" / construct.Int32ul,
    "height" / construct.Int32ul
)

SoundResourceDescriptor = construct.Struct(
    "unknown0" / construct.Int16ul, # maybe format?, seems to always be 0
    "unknown1" / construct.Int16ul, # always 0x10 (bits?)
    "unknown2" / construct.Int32ul, # always 1, channels?
    "frequency" / construct.Int32ul
)

ResourceDescriptor = construct.Struct(
    "type" / construct.Int16ul,
    "id" / construct.Int16ul,
    "offset" / construct.Int32ul,
    "size" / construct.Int32ul,
    # todo make this dependant on type
    "_" / construct.Union(0,
        "bitmap" / BitmapResourceDescriptor,
        "sound" / SoundResourceDescriptor
    )
)

ResourceBlob = construct.Struct(
    "descriptorCount" / construct.Int32ul,
    "descriptors" / construct.Array(construct.this.descriptorCount, ResourceDescriptor)
)

# Classes
class ResourceType(IntEnum):
    BITMAP = 0x0
    SOUND = 0x1
    UNKNOWN = 0x2

class Resource:
    type: ResourceType

    def __init__(self, type):
        self.type = type

    def get_type(self):
        return self.type

# Represents a bitmap resource
class BitmapResource(Resource):
    descriptor = None
    bitmap_descriptor = None
    image: Image

    def __init__(self, descriptor, data):
        super().__init__(descriptor.type)

        self.descriptor = descriptor
        self.bitmap_descriptor = descriptor._.bitmap

        self.image = Image.frombytes("P", [self.bitmap_descriptor.width, self.bitmap_descriptor.height], data[256*4:])
        self.image.putpalette(data[:256*4], "BGRA")

    def get_preview_image(self, size):
        # create a preview thumbnail
        preview = self.image.copy()
        preview.thumbnail(size)
        
        # create a white background
        background = Image.new('RGB', size, (255, 255, 255))

        # paste thumbnail onto background
        offset = ((background.width - preview.width) // 2, (background.height - preview.height) // 2)
        background.paste(preview, offset)

        return background

    def pack_data(self):
        buffer = b""
        pallette = self.image.getpalette("BGRA")
        buffer += bytes(pallette)
        data = self.image.getdata()
        buffer += bytes(data)
        return buffer

    def __str__(self):
        return f"""BitmapResource:
                ID: 0x{self.descriptor.id:04x}
                Unknown: {self.bitmap_descriptor.unknown}
                Resolution: {self.bitmap_descriptor.width}x{self.bitmap_descriptor.height}"""

# Represents a sound resource
class SoundResource(Resource):
    descriptor = None
    sound_descriptor = None
    segment: AudioSegment = None

    def __init__(self, descriptor, data):
        super().__init__(descriptor.type)

        self.descriptor = descriptor
        self.sound_descriptor = self.descriptor._.sound
        self.segment = AudioSegment.from_file(io.BytesIO(data), format="raw", frame_rate=self.sound_descriptor.frequency, channels=1, sample_width=2)

    def get_preview_image(self, size):
        return Image.open(os.path.join(sys.path[0], "assets/sound.png")).resize(size)

    def pack_data(self):
        return self.segment.raw_data

    def __str__(self):
        return f"""SoundResource:
                ID: 0x{self.descriptor.id:04x}
                Unknown0: {self.sound_descriptor.unknown0}
                Unknown1: {self.sound_descriptor.unknown1}
                Unknown2: {self.sound_descriptor.unknown2}
                Frequency: {self.sound_descriptor.frequency}"""

# Globals
resources = []
sound_menu = None
bitmap_menu = None

# Functions
def save_file():
    tkinter.messagebox.showwarning(title = "Warning", message = "Edited resources are currently broken.\nOnly flash this to your gamepad if you know what you're doing.")

    f = tkinter.filedialog.asksaveasfile(mode='wb', defaultextension=".bin")
    if f is None:
        return

    descriptors = b""
    data = b""
    for r in resources:
        buffer = r.pack_data()
        r.descriptor.offset = len(data)
        r.descriptor.size = len(buffer)
        descriptors += ResourceDescriptor.build(r.descriptor)
        data += buffer

    f.write(len(resources).to_bytes(4, "little"))
    f.write(descriptors)
    f.write(data)
    f.close()

def play_sound(resource):
    play(resource.segment)

def properties_sound(resource):
    properties = tk.Toplevel()
    
    label = tk.Label(properties, text=str(resource))
    label.pack()

def save_sound(resource):
    f = tkinter.filedialog.asksaveasfile(mode='wb', defaultextension=".wav")
    if f is None:
        return
    resource.segment.export(f, format="wav")

def replace_sound(idx):
    f = tkinter.filedialog.askopenfile("rb", defaultextension=".wav")
    if f is None:
        return
    
    segment = AudioSegment.from_file(f, format="wav")
    segment = segment.set_channels(1)
    segment = segment.set_sample_width(2)
    segment = segment.set_frame_rate(resources[idx].sound_descriptor.frequency)
    resources[idx].segment = segment

def do_sound_popup(event, resource, idx):
    try:
        sound_menu.entryconfig("Play", command=lambda: play_sound(resource))
        sound_menu.entryconfig("Properties", command=lambda: properties_sound(resource))
        sound_menu.entryconfig("Save as", command=lambda: save_sound(resource))
        sound_menu.entryconfig("Replace", command=lambda: replace_sound(idx))
        sound_menu.tk_popup(event.x_root, event.y_root)
    finally:
        sound_menu.grab_release()

def view_bitmap(resource):
    resource.image.show()

def view_palette_bitmap(resource):
    palette = tk.Toplevel()
    
    pal = resource.image.getpalette("RGBA")
    string = ""
    for i in range(256):
        offset = i * 4
        string += f"0x{i:02x}: #{pal[offset]:02x}{pal[offset + 1]:02x}{pal[offset + 2]:02x}{pal[offset + 3]:02x}\n"

    text = tk.Text(palette)
    text.insert(tk.END, string)
    text.config(state=tk.DISABLED)
    text.pack()

def properties_bitmap(resource):
    properties = tk.Toplevel()
    
    label = tk.Label(properties, text=str(resource))
    label.pack()

def save_bitmap(resource):
    f = tkinter.filedialog.asksaveasfile(mode='wb', defaultextension=".png")
    if f is None:
        return
    resource.image.save(f, "PNG")

def replace_bitmap(idx, img):
    f = tkinter.filedialog.askopenfile("rb", defaultextension=".png")
    if f is None:
        return

    # Convert the image to a palletized version with the original info
    image = Image.open(f)
    image = image.resize((resources[idx].bitmap_descriptor.width, resources[idx].bitmap_descriptor.height))
    image = image.convert("RGBA")
    resources[idx].image = image.quantize()

    # Update thumbnail
    tkimage = ImageTk.PhotoImage(resources[idx].get_preview_image((150, 150)))
    img.configure(image=tkimage)
    img.image = tkimage

def do_bitmap_popup(event, resource, idx, img):
    try:
        bitmap_menu.entryconfig("View", command=lambda: view_bitmap(resource))
        bitmap_menu.entryconfig("View Palette", command=lambda: view_palette_bitmap(resource))
        bitmap_menu.entryconfig("Properties", command=lambda: properties_bitmap(resource))
        bitmap_menu.entryconfig("Save as", command=lambda: save_bitmap(resource))
        bitmap_menu.entryconfig("Replace", command=lambda: replace_bitmap(idx, img))
        bitmap_menu.tk_popup(event.x_root, event.y_root)
    finally:
        bitmap_menu.grab_release()

def print_usage():
    print("Usage:")
    print(f"    {sys.argv[0]}: <filename> [offset]")

def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1

    with open(sys.argv[1], "rb") as file:
        # Check if a file offset was specified
        fileoffset = 0
        if len(sys.argv) == 3:
            fileoffset = int(sys.argv[2], 0)
            file.seek(fileoffset)

        img_resource = ResourceBlob.parse_stream(file)

        for d in img_resource.descriptors:
            file.seek(fileoffset + 4 + img_resource.descriptorCount * 0x18 + d.offset)
            if d.type == ResourceType.BITMAP:
                resources.append(BitmapResource(d, file.read(d.size)))
            elif d.type == ResourceType.SOUND:
                resources.append(SoundResource(d, file.read(d.size)))
            else:
                print(f"Unsupported resource type {d.type} in file")
                sys.exit()

    # for r in resources:
    #     print(r)

    window = tk.Tk()
    window.title("DRC Resource Blobviewer")

    menubar = tk.Menu(window)
    filemenu = tk.Menu(menubar, tearoff=0)
    # filemenu.add_command(label="Open")
    filemenu.add_command(label="Save as", command=lambda: save_file())
    filemenu.add_separator()
    filemenu.add_command(label="Exit", command=window.quit)
    menubar.add_cascade(label="File", menu=filemenu)

    helpmenu = tk.Menu(menubar, tearoff=0)
    helpmenu.add_command(label="About", command=lambda: tkinter.messagebox.showinfo(title = "About", message = "DRC Resource Blobviewer by GaryOderNichts"))
    menubar.add_cascade(label="Help", menu=helpmenu)

    window.config(menu=menubar)

    global sound_menu
    sound_menu = tk.Menu(window)
    sound_menu.add_command(label="Play")
    sound_menu.add_command(label="Properties")
    sound_menu.add_command(label="Save as")
    sound_menu.add_command(label="Replace")

    global bitmap_menu
    bitmap_menu = tk.Menu(window)
    bitmap_menu.add_command(label="View")
    bitmap_menu.add_command(label="View Palette")
    bitmap_menu.add_command(label="Properties")
    bitmap_menu.add_command(label="Save as")
    bitmap_menu.add_command(label="Replace")

    # Create grid for resources
    for i, res in enumerate(resources):
        r, c = divmod(i, 5)
        im = res.get_preview_image((150, 150))
        tkimage = ImageTk.PhotoImage(im)
        myvar = tk.Label(window, image=tkimage)
        myvar.image = tkimage
        myvar.grid(row=r, column=c)

        if res.get_type() == ResourceType.SOUND:
            myvar.bind("<Button-3>", lambda ev, r=res, idx=i: do_sound_popup(ev, r, idx))
        elif res.get_type() == ResourceType.BITMAP:
            myvar.bind("<Button-3>", lambda ev, r=res, idx=i, img=myvar: do_bitmap_popup(ev, r, idx, img))

    window.mainloop()
    return 0

if __name__ == '__main__':
    sys.exit(main())
