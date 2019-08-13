"""Tkinter-based app for demoing the parser."""

# TODO: Behavior & functionality should roughly parallel that of the command line interface. In fact, it might make
#       sense to factor out the interaction controller and have both be front-ends for it.

import threading
import time
from io import BytesIO
from tkinter import Tk, Canvas, mainloop, N, W, Text, END, Scrollbar, VERTICAL, HORIZONTAL, Frame, TOP, RIGHT, BOTTOM, \
    Y, X, BOTH

import PIL.Image
from PIL.ImageTk import PhotoImage
from graphviz import Digraph


MM_PER_INCH = 25.4


class DemoApp:

    def __init__(self, parent, parse):
        self.parent = parent
        self.parse = parse

        self.main_frame = Frame(self.parent)
        self.main_frame.pack(fill=BOTH, expand=True)

        self.text_box = Text(self.main_frame, height=1)
        self.text_box.pack(side=BOTTOM, fill=X)

        self.parse_result = None
        self.photo_image = None

        self.resize_condition = threading.Condition()
        self.resize_request = True
        self.resize_thread = threading.Thread(target=self._resize_thread, daemon=True)

        self.canvas_frame = Frame(self.main_frame)
        self.canvas_frame.pack(side=TOP, fill=BOTH, expand=True)
        self.vertical_scrollbar = Scrollbar(self.canvas_frame, orient=VERTICAL)
        self.vertical_scrollbar.pack(side=RIGHT, fill=Y)
        self.horizontal_scrollbar = Scrollbar(self.canvas_frame, orient=HORIZONTAL)
        self.horizontal_scrollbar.pack(side=BOTTOM, fill=X)
        self.canvas = Canvas(self.canvas_frame, width=300, height=300,
                             xscrollcommand=self.horizontal_scrollbar.set, yscrollcommand=self.vertical_scrollbar.set,
                             background='white')
        self.canvas.pack(side=TOP, fill=BOTH, expand=True)
        self.vertical_scrollbar.config(command=self.canvas.yview)
        self.horizontal_scrollbar.config(command=self.canvas.xview)

        self.canvas.bind("<Configure>", self.resize_canvas)
        self.text_box.bind('<Return>', self.submit)

        self.text_box.focus_set()
        self.resize_thread.start()

    # noinspection PyUnusedLocal
    def submit(self, event):
        text = self.text_box.get(1.0, END)
        self.text_box.delete(1.0, END)
        self.show_parse(text)
        return 'break'

    def show_parse(self, text):
        self.parse_result = self.parse(text)[0][0].get_parse_graphs()[0]
        self.fit_image()

    def fit_image(self):
        if self.parse_result is None:
            return

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        height_pixels_per_mm = self.canvas.winfo_screenheight() / self.canvas.winfo_screenmmheight()
        height_pixels_per_inch = height_pixels_per_mm * MM_PER_INCH
        height_inches = (height / height_pixels_per_inch)

        width_pixels_per_mm = self.canvas.winfo_screenwidth() / self.canvas.winfo_screenmmwidth()
        width_pixels_per_inch = width_pixels_per_mm * MM_PER_INCH
        width_inches = (width / width_pixels_per_inch)

        graph = Digraph()
        graph.graph_attr.update(size="%s,%s" % (width_inches / 2, height_inches / 2), ratio="expand",
                                dpi=str(2 * max(height_pixels_per_mm, width_pixels_per_inch)))
        self.parse_result.visualize(graph)

        image_data = graph.pipe(format='png')
        original = PIL.Image.open(BytesIO(image_data))

        if width / height < original.width / original.height:
            size = (width, int(width / original.width * original.height))
        else:
            size = (int(height / original.height * original.width), height)

        resized = original.resize(size, PIL.Image.ANTIALIAS)

        self.photo_image = PhotoImage(resized)
        self.canvas.delete("IMG")
        self.canvas.create_image(0, 0, image=self.photo_image, anchor=N + W, tags="IMG")

    # noinspection PyUnusedLocal
    def resize_canvas(self, event):
        with self.resize_condition:
            self.resize_request = True
            self.resize_condition.notify()

    def _resize_thread(self):
        while True:
            requested = False
            with self.resize_condition:
                if self.resize_request:
                    requested = True
                    self.resize_request = False
                else:
                    self.resize_condition.wait()
            if requested:
                self.fit_image()


# TODO: Make the app support choosing a model instead of assuming English.
def main():
    from pyramids_english import parse
    root = Tk()
    # noinspection PyUnusedLocal
    app = DemoApp(root, lambda text: parse(text, fast=True, timeout=time.time() + 10))
    root.wm_minsize(300, 300)
    root.size = (300, 300)
    mainloop()


if __name__ == '__main__':
    main()
