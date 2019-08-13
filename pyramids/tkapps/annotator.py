"""Tkinter-based app for annotating samples."""
import bz2
import dbm
import json
import threading
import time
import traceback
from io import BytesIO
from tkinter import Tk, Canvas, mainloop, Text, END, Scrollbar, VERTICAL, HORIZONTAL, Frame, Label, Button, \
    Checkbutton, IntVar, TclError
from tkinter.ttk import Separator, Combobox
from typing import Union, Tuple, Optional, Dict, List, Sequence

import PIL.Image
from PIL.ImageTk import PhotoImage

from pyramids.model import Model

try:
    from graphviz import Digraph
except ImportError:
    Digraph = None

from pyramids.categorization import Category, Property
from pyramids.graphs import ParseGraph, BuildGraph
from pyramids.parsing import Parser

MM_PER_INCH = 25.4


# Flow:
#   * Select an existing or new annotation set:
#       * New:
#           * Choose save path
#           * Choose parser model
#       * Existing:
#           * Choose load path
#   * Create/resume annotation task: (annotation tasks are attached to specific annotation sets)
#       * New:
#           * Choose name
#           * Choose utterance list
#       * Resume:
#           * Choose name
#   * Switch to the annotation window and proceed to annotate samples
#   * Annotations are auto-saved as they are modified

# Menu layout:
#   * File:
#       * New annotation set
#       * Open annotation set
#       * New utterance list
#       * Edit utterance list
#       * Export annotations (save to alternative formats, e.g. tab-delimited)
#   * Edit:
#       * Undo (bound to Ctrl-Z)
#       * Redo (bound to Shift-Ctrl-Z)
#   * View: (only in annotation window)
#       * Stats (parser accuracy, annotation completion, etc. on the annotation set, broken out by utterance list)
#       * Toggle show/hide parse visualization
#   * Task:
#       * New annotation task (annotation set to add to, and utterance list to add from)
#       * Resume annotation task
#       * Delete annotation task
#   * Settings: (only in annotation window)
#       * Parser timeout
#       * Restriction category
#       * Utterance ordering (original, random, shortest/longest first, alphabetical, parser uncertainty-sorted)
#       * Utterance filtering
#   * Parser:
#       * Train (entire annotation set or particular utterance list)
#       * Evaluate (entire annotation set or particular utterance list)

# Utterance list window layout:
#   * Menu
#   * Header:
#       * Current utterance list
#       * Utterance list stats
#       * Add utterance area:
#           * Utterance tex box (sorts utterance listing to put nearest matches at top as utterance is typed)
#           * Add button (bound to <Return>)
#           * Clear button (bound to <Escape>)
#   * Body:
#       * Utterance listing:
#           * Utterance
#           * Edit button
#           * Remove button
#   * Footer:
#       * Page navigation (first, prev, next, last)

# Annotation window layout:
#   * Menu
#   * Header:
#       * Current annotation set
#       * Current utterance list
#       * Current utterance
#       * Current utterance with injected links & parens
#   * Left panel:
#       * Category name (drop-down)
#       * Property selection (checkboxes)
#       * Token listing:
#           * Token spelling
#           * Token index
#           * Outbound link listing:
#               * Link label (drop-down)
#               * Link sink token (drop-down)
#               * Delete button
#           * New link button
#   * Right panel:
#       * Tree visualization (optional, depending on whether graphviz is installed & view is enabled)
#   * Footer:
#       * Reset (clears manual annotations and re-queries the model)
#       * Accept/reject
#       * Utterance list navigation (first, prev, next, last, new)


class ReadoutFrame(Frame):

    def __init__(self, parent, labels, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.labels = []
        self.boxes = []
        self.mapping = {}
        self.columnconfigure(1, weight=1)
        for row, label_text in enumerate(labels):
            assert label_text not in self.mapping
            label = Label(self, text=label_text + ':')
            label.grid(row=row, column=0, sticky='ne')
            self.labels.append(label)
            box = Text(self, state='disabled', height=1)
            box.grid(row=row, column=1, sticky='new')
            self.boxes.append(box)
            self.mapping[label_text] = row

    def set(self, label, value):
        box = self.boxes[self.mapping[label]]
        if value is None:
            text = ''
        else:
            text = str(value)
        box['state'] = 'normal'
        box.delete(1.0, END)
        box.insert(END, text)
        box['state'] = 'disabled'
        box['width'] = len(text)

    def get(self, label):
        box = self.boxes[self.mapping[label]]
        return box.get(1.0, END).rstrip('\n')

    def clear(self, label=None):
        if label is None:
            for box in self.boxes:
                box.delete(1.0, END)
        else:
            box = self.boxes[self.mapping[label]]
            box.delete(1.0, END)


class TokenEditingFrame(Frame):

    def __init__(self, parent, model: Model, graph: BuildGraph, *args, graph_change_callback=None, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.model = model
        self.graph = graph
        self.link_types = sorted(str(label) for label in self.model.link_types)
        self.graph_change_callback = graph_change_callback

        self.token_listing = ['%s [%s]' % (token.spelling, index) for index, token in enumerate(graph.tokens)]
        assert len(self.token_listing) == len(graph.tokens)

        self.token_labels = [Label(self, text='%s [%s]' % (token.spelling, index))
                             for index, token in enumerate(graph.tokens)]
        assert len(self.token_labels) == len(graph.tokens)

        self.separators = [Separator(self, orient=HORIZONTAL) for _ in graph.tokens]
        assert len(self.separators) == len(graph.tokens)

        link_sets = []
        for source in range(len(graph.tokens)):
            link_set = set()
            for sink in graph.get_sinks(source):
                for label in graph.get_labels(source, sink):
                    link_set.add((str(label), sink))
            link_sets.append(link_set)
        assert len(link_sets) == len(graph.tokens)

        self.link_selector_maps = []  # type: List[Dict[Tuple[Optional[Property], int], Tuple]]
        for source, link_set in enumerate(link_sets):
            link_selector_map = {}
            for label, sink in link_set:
                label_drop_down = Combobox(self, values=self.link_types)
                label_drop_down.current(self.link_types.index(label))
                label_drop_down.bind("<<ComboboxSelected>>",
                                     (lambda *a, r=(source, label, sink), v=label_drop_down, **k:
                                      self.modify_link(r, label=v.get())))
                sink_drop_down = Combobox(self, values=self.token_listing)
                sink_drop_down.current(sink)
                sink_drop_down.bind('<<ComboboxSelected>>',
                                    (lambda *a, r=(source, label, sink), v=sink_drop_down, **k:
                                     self.modify_link(r, sink=self.token_listing.index(v.get()))))
                remove_button = Button(self, text='-', command=lambda r=(source, label, sink): self.modify_link(r))
                link_selector_map[label, sink] = label_drop_down, sink_drop_down, remove_button
            self.link_selector_maps.append(link_selector_map)
        assert len(self.link_selector_maps) == len(graph.tokens)

        self.new_link_selectors = [[] for _ in graph.tokens]  # type: List[List[Tuple]]
        for source in range(len(self.graph.tokens)):
            self.add_link(source)

    def add_link(self, source):
        counter = len(self.new_link_selectors[source])
        label = None
        sink = None
        label_drop_down = Combobox(self, values=[''] + self.link_types)
        label_drop_down.current(0)
        label_drop_down.bind('<<ComboboxSelected>>',
                             (lambda *a, r=(source, label, sink), v=label_drop_down, c=counter, **k:
                              self.modify_link(r, label=v.get() or None, new=c)))
        sink_drop_down = Combobox(self, values=[''] + self.token_listing)
        sink_drop_down.current(0)
        sink_drop_down.bind('<<ComboboxSelected>>',
                            (lambda *a, r=(source, label, sink), v=sink_drop_down, c=counter, **k:
                             self.modify_link(r, sink=v.current() - 1 if v.current() else None, new=c)))
        new_link_selector_list = self.new_link_selectors[source]
        new_link_selector_list.append((label_drop_down, sink_drop_down))
        self.refresh()

    def modify_link(self, link, *, source=None, label=None, sink=None, new=None):
        old_source, old_label, old_sink = link
        assert old_source is not None
        if new is None:
            assert old_sink is not None
            assert old_label is not None
            self.graph.remove_link(old_source, old_label, old_sink)
            items = self.link_selector_maps[old_source].pop((old_label, old_sink))
        else:
            assert old_label is None or old_sink is None
            items = self.new_link_selectors[old_source][new]
            self.new_link_selectors[old_source][new] = ()
            while self.new_link_selectors[old_source] and not self.new_link_selectors[old_source][-1]:
                self.new_link_selectors[old_source].pop()
        for item in items:
            if hasattr(item, 'destroy'):
                item.destroy()
        if source is not None or label is not None or sink is not None:
            if source is None:
                source = old_source
            if label is None:
                label = old_label
            if sink is None:
                sink = old_sink
            assert source is not None
            if sink is not None and label is not None:
                label_drop_down = Combobox(self, values=self.link_types)
                label_drop_down.current(self.link_types.index(label))
                label_drop_down.bind("<<ComboboxSelected>>",
                                     (lambda *a, r=(source, label, sink), v=label_drop_down, **k:
                                      self.modify_link(r, label=v.get())))
                sink_drop_down = Combobox(self, values=self.token_listing)
                sink_drop_down.current(sink)
                sink_drop_down.bind('<<ComboboxSelected>>',
                                    (lambda *a, r=(source, label, sink), v=sink_drop_down, **k:
                                     self.modify_link(r, sink=v.current())))
                remove_button = Button(self, text='-', command=lambda r=(source, label, sink): self.modify_link(r))
                self.graph.add_link(source, label, sink)
                self.link_selector_maps[source][label, sink] = label_drop_down, sink_drop_down, remove_button
            else:
                counter = len(self.new_link_selectors[source])
                label_drop_down = Combobox(self, values=[''] + self.link_types)
                label_drop_down.current(self.link_types.index(label) + 1 if label else 0)
                label_drop_down.bind("<<ComboboxSelected>>",
                                     (lambda *a, r=(source, label, sink), v=label_drop_down, c=counter, **k:
                                      self.modify_link(r, label=v.get() or None, new=c)))
                sink_drop_down = Combobox(self, values=[''] + self.token_listing)
                sink_drop_down.current(sink + 1 if sink is not None else 0)
                sink_drop_down.bind('<<ComboboxSelected>>',
                                    (lambda *a, r=(source, label, sink), v=sink_drop_down, c=counter, **k:
                                     self.modify_link(r, sink=v.current() - 1 if v.current() else None, new=c)))
                self.new_link_selectors[source].append((label_drop_down, sink_drop_down))
        if source is None or self.new_link_selectors[source]:
            self.refresh()
        else:
            self.add_link(source)
        if self.graph_change_callback:
            self.graph_change_callback()

    def refresh(self):
        current_row = 0
        for token_index in range(len(self.graph.tokens)):
            self.separators[token_index].grid(row=current_row, column=0, columnspan=5, sticky='wen')
            current_row += 1
            self.token_labels[token_index].grid(row=current_row, column=0, sticky='wn')
            # self.add_buttons[token_index].grid(row=current_row, column=1, sticky='nwe')
            for label, sink in sorted(self.link_selector_maps[token_index], key=lambda l: (l[1], l[0])):
                entry = self.link_selector_maps[token_index][label, sink]
                label_drop_down, sink_drop_down, remove_button = entry
                label_drop_down.grid(row=current_row, column=2, sticky='nwe')
                sink_drop_down.grid(row=current_row, column=3, sticky='nwe')
                remove_button.grid(row=current_row, column=4, sticky='nwe')
                current_row += 1
            for entry in self.new_link_selectors[token_index]:
                if not entry:
                    continue
                label_drop_down, sink_drop_down = entry
                label_drop_down.grid(row=current_row, column=2, sticky='nwe')
                sink_drop_down.grid(row=current_row, column=3, sticky='nwe')
                current_row += 1
            if not self.link_selector_maps[token_index]:
                current_row += 1


class GraphEditingFrame(Frame):

    def __init__(self, parent, model, *args, graph_change_callback=None, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.model = model
        self._graph = BuildGraph()
        self.category = model.default_restriction
        self.graph_change_callback = graph_change_callback

        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        self.category_frame = Frame(self)
        self.category_frame.grid(row=0, column=0, sticky='wen')
        self.property_frame = Frame(self)
        self.property_frame.grid(row=1, column=0, sticky='wen')
        self.token_editing_frame = TokenEditingFrame(self, model, self._graph,
                                                     graph_change_callback=graph_change_callback)
        self.token_editing_frame.grid(row=2, column=0, sticky='wens')

        self.category_readout = ReadoutFrame(self.category_frame, ['Category'])
        self.category_readout.grid(row=0, column=0, sticky='nw')
        self.category_readout.set('Category', self.category)

        self.properties = {}
        for index, prop in enumerate(sorted(model.top_level_properties, key=str)):
            variable = IntVar()
            checkbox = Checkbutton(self.property_frame, text=str(prop), variable=variable,
                                   command=self.on_property_change)
            checkbox.property_name = prop
            checkbox.variable = variable
            checkbox.grid(row=index // 4, column=index % 4, sticky='nw')
            self.properties[prop] = variable, checkbox

    @property
    def graph(self) -> BuildGraph:
        return self._graph

    @graph.setter
    def graph(self, graph: BuildGraph) -> None:
        self._graph = graph
        for index in range(len(graph.tokens)):
            props = self.model.top_level_properties & graph.get_phrase_category(index).positive_properties
            category = Category(self.model.default_restriction.name, props)
            self.graph.set_phrase_category(index, category)
        self.category = self.model.default_restriction
        for index in sorted(graph.find_roots()):
            self.category = graph.get_phrase_category(index)
        for prop in self.properties:
            has_prop = prop in self.category.positive_properties
            self.properties[prop][0].set(has_prop)

        self.token_editing_frame.destroy()
        self.token_editing_frame = TokenEditingFrame(self, self.model, graph,
                                                     graph_change_callback=self.graph_change_callback)
        self.token_editing_frame.grid(row=2, column=0, sticky='wens')
        self.on_property_change()

    def on_property_change(self):
        self.refresh()
        if self.graph_change_callback:
            self.graph_change_callback()

    def refresh(self):
        self.token_editing_frame.refresh()
        props = [prop for prop in self.properties if self.properties[prop][0].get()]
        self.category = Category(self.model.default_restriction.name, props, ())
        for index in range(len(self.graph.tokens)):
            self.graph.set_phrase_category(index, self.category)
        self.category_readout.set('Category', self.category)


class GraphVisualizationFrame(Frame):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._graph = BuildGraph()  # type: Union[BuildGraph, ParseGraph]
        self.photo_image = None

        self.resize_condition = threading.Condition()
        self.resize_request = True
        self.resize_thread = threading.Thread(target=self._resize_thread, daemon=True)

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.vertical_scrollbar = Scrollbar(self, orient=VERTICAL)
        self.vertical_scrollbar.grid(row=0, column=1, sticky='nse')

        self.horizontal_scrollbar = Scrollbar(self, orient=HORIZONTAL)
        self.horizontal_scrollbar.grid(row=1, column=0, sticky='wes')

        self.canvas = Canvas(self, width=300, height=300,
                             xscrollcommand=self.horizontal_scrollbar.set, yscrollcommand=self.vertical_scrollbar.set,
                             background='white')
        self.canvas.grid(row=0, column=0, sticky='news')

        self.vertical_scrollbar.config(command=self.canvas.yview)
        self.horizontal_scrollbar.config(command=self.canvas.xview)

        self.canvas.bind("<Configure>", self.resize_canvas)

        self.resize_thread.start()

    @property
    def graph(self) -> Union[BuildGraph, ParseGraph]:
        return self._graph

    @graph.setter
    def graph(self, graph: Union[BuildGraph, ParseGraph]):
        self._graph = graph
        self.refresh()

    def refresh(self):
        if not self._graph:
            self.canvas.delete("IMG")
            return

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        if width <= 0 or height <= 0:
            return

        height_pixels_per_mm = self.canvas.winfo_screenheight() / self.canvas.winfo_screenmmheight()
        height_pixels_per_inch = height_pixels_per_mm * MM_PER_INCH
        height_inches = (height / height_pixels_per_inch)

        width_pixels_per_mm = self.canvas.winfo_screenwidth() / self.canvas.winfo_screenmmwidth()
        width_pixels_per_inch = width_pixels_per_mm * MM_PER_INCH
        width_inches = (width / width_pixels_per_inch)

        gv_graph = Digraph()
        gv_graph.graph_attr.update(size="%s,%s" % (width_inches / 2, height_inches / 2), ratio="expand",
                                   dpi=str(2 * max(height_pixels_per_mm, width_pixels_per_inch)))

        self._graph.visualize(gv_graph)

        image_data = gv_graph.pipe(format='png')
        original = PIL.Image.open(BytesIO(image_data))

        if width / height < original.width / original.height:
            size = (width, int(width / original.width * original.height))
        else:
            size = (int(height / original.height * original.width), height)

        if any(value <= 0 for value in size):
            return

        resized = original.resize(size, PIL.Image.ANTIALIAS)

        self.photo_image = PhotoImage(resized)
        self.canvas.delete("IMG")
        self.canvas.create_image(0, 0, image=self.photo_image, anchor='nw', tags="IMG")

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
                try:
                    self.refresh()  # TODO: Why are we getting a runtime error?
                except RuntimeError:
                    traceback.print_exc()


class AnnotationFrame(Frame):

    def __init__(self, parent, model, settings, utterances: Sequence[str], on_accept, on_reject, on_modify,
                 *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.model = model
        self.settings = settings
        self._utterance_index = None
        self._utterance = None
        self._graph = BuildGraph()
        self.utterances = utterances
        self.on_accept = on_accept
        self.on_reject = on_reject
        self.on_modify = on_modify

        # Frames
        self.header_frame = Frame(self, relief='groove', borderwidth=1)
        self.header_frame.grid(row=0, column=0, sticky='nwe')
        self.middle_frame = Frame(self)
        self.middle_frame.grid(row=1, column=0, sticky='news')
        self.left_frame = Frame(self.middle_frame, relief='groove', borderwidth=1)
        self.left_frame.grid(row=0, column=0, sticky='wn')  # se')
        self.right_frame = Frame(self.middle_frame, relief='groove', borderwidth=1)
        self.right_frame.grid(row=0, column=1, sticky='ensw')
        self.footer_frame = Frame(self, relief='groove', borderwidth=1)
        self.footer_frame.grid(row=2, column=0, sticky='s')

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.header_frame.columnconfigure(0, weight=1)
        self.middle_frame.rowconfigure(0, weight=1)
        self.middle_frame.columnconfigure(0, weight=1)
        self.middle_frame.columnconfigure(1, weight=10)
        for frame in self.left_frame, self.right_frame:
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)

        # Header
        self.readout_frame = ReadoutFrame(self.header_frame,
                                          ['Annotation Set', 'Utterance List', 'Utterance', 'Annotation'])
        self.readout_frame.grid(row=0, column=0, sticky='we')

        # Right
        self.visualization_frame = GraphVisualizationFrame(self.right_frame)
        self.visualization_frame.grid(row=0, column=0, sticky='news')

        # Left
        self.tree_editing_frame = GraphEditingFrame(self.left_frame, model, graph_change_callback=self.on_graph_change)
        self.tree_editing_frame.grid(row=0, column=0, sticky='news')

        # Footer
        self.first_button = Button(self.footer_frame, text='<<', state='disabled', command=self.go_to_first)
        self.first_button.grid(row=0, column=0, sticky='n')
        self.previous_button = Button(self.footer_frame, text='<', state='disabled', command=self.go_to_previous)
        self.previous_button.grid(row=0, column=1, sticky='n')
        self.reset_button = Button(self.footer_frame, text='Reset', state='disabled', command=self.reset_graph)
        self.reset_button.grid(row=0, column=2, sticky='n')
        self.reject_button = Button(self.footer_frame, text='Reject', state='disabled', command=self.reject)
        self.reject_button.grid(row=0, column=3, sticky='n')
        self.accept_button = Button(self.footer_frame, text='Accept', state='disabled', command=self.accept)
        self.accept_button.grid(row=0, column=4, sticky='n')
        self.next_button = Button(self.footer_frame, text='>', state='disabled', command=self.go_to_next)
        self.next_button.grid(row=0, column=5, sticky='n')
        self.last_button = Button(self.footer_frame, text='>>', state='disabled', command=self.go_to_last)
        self.last_button.grid(row=0, column=6, sticky='n')

        self.go_to_first()

    @property
    def utterance(self) -> str:
        return self._utterance

    @utterance.setter
    def utterance(self, utterance: str) -> None:
        self._utterance = utterance
        self.readout_frame.set('Utterance', utterance)
        forests = Parser(self.model).parse(utterance, timeout=time.time() + self.settings['timeout'])[0]
        if forests and not forests[0].has_gaps():
            graphs = tuple(forests[0].get_parse_graphs())
            combined_graph = BuildGraph.from_parse_graphs(graphs)
        else:
            combined_graph = BuildGraph()
            for spelling, _, _ in self.model.tokenizer.tokenize(utterance):
                combined_graph.append_token(spelling)
        for index in range(len(combined_graph.tokens)):
            combined_graph.clear_token_category(index)  # Not interested in these...
        for index in combined_graph.find_roots():
            category = combined_graph.get_phrase_category(index)
            props = self.model.default_restriction.positive_properties & category.positive_properties
            revised_category = Category(self.model.default_restriction.name, props, ())
            combined_graph.set_phrase_category(index, revised_category)
        self._graph = combined_graph
        self.tree_editing_frame.graph = combined_graph
        self.visualization_frame.graph = combined_graph
        self.on_graph_change()
        self.reset_button['state'] = 'normal'

    @property
    def graph(self) -> BuildGraph:
        return self._graph

    def reset_graph(self):
        self.utterance = self.utterance

    def go_to(self, index):
        self._utterance_index = index
        if self.utterances:
            self.utterance = self.utterances[self._utterance_index]
        back_enabled = self.utterances and self._utterance_index > 0
        forward_enabled = self.utterances and self._utterance_index < len(self.utterances) - 1
        self.first_button['state'] = 'normal' if back_enabled else 'disabled'
        self.previous_button['state'] = 'normal' if back_enabled else 'disabled'
        self.next_button['state'] = 'normal' if forward_enabled else 'disabled'
        self.last_button['state'] = 'normal' if forward_enabled else 'disabled'

    def go_to_first(self):
        self.go_to(0)

    def go_to_previous(self):
        if self.utterances and self._utterance_index > 0:
            self.go_to(self._utterance_index - 1)

    def go_to_next(self):
        if self.utterances and self._utterance_index < len(self.utterances) - 1:
            self.go_to(self._utterance_index + 1)

    def go_to_last(self):
        if self.utterances:
            self.go_to(len(self.utterances) - 1)

    def accept(self):
        if self.on_accept:
            self.on_accept(self._utterance_index, self._utterance, self._graph, self.readout_frame.get('Annotation'))
        self.go_to_next()

    def reject(self):
        if self.on_reject:
            self.on_reject(self._utterance_index, self._utterance, self._graph, self.readout_frame.get('Annotation'))
        self.go_to_next()

    def on_graph_change(self):
        self.tree_editing_frame.refresh()
        self.visualization_frame.refresh()
        annotations = self.graph.get_annotations()
        annotation_string = ('[%s]' % ']  ['.join(annotations)) if annotations else ''
        self.readout_frame.set('Annotation', annotations)
        self.accept_button['state'] = 'normal' if self.on_accept and self._graph.is_tree() else 'disabled'
        self.reject_button['state'] = 'normal' if self.on_reject else 'disabled'
        if self.on_modify:
            self.on_modify(self._utterance_index, self._utterance, self._graph, annotation_string)


class AnnotatorApp(Tk):

    def __init__(self, model, save_path, utterances, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.wm_minsize(400, 400)
        # self.size = (400, 400)

        self.model = model
        self.settings = {'timeout': 5}
        self.utterances = list(utterances) if utterances else []

        self.annotation_database = dbm.open(save_path, 'c')
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.file_access_lock = threading.RLock()

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.annotation_frame = AnnotationFrame(self, model, self.settings, self.utterances,
                                                self.accept, self.reject, self.modify)
        self.annotation_frame.grid(row=0, column=0, sticky='news')

        self.text_box = Text(self, height=1)
        self.text_box.grid(row=1, column=0, sticky='news')

        self.text_box.bind('<Return>', self.submit)
        self.text_box.focus_set()

        # TODO: This feels kludgy. What's a better way?
        # Capture the size of the window just after everything has been initialized, and set it to the minimum size.
        threading.Timer(1, self._size_callback).start()

    def close(self):
        if self.annotation_database is not None:
            self.annotation_database.close()
            self.annotation_database = None
        try:
            self.destroy()
        except TclError:
            pass

    def __del__(self):
        self.close()
        super().__del__()

    def _size_callback(self):
        self.wm_minsize(self.winfo_width(), self.winfo_height())

    # noinspection PyUnusedLocal
    def submit(self, event):
        text = self.text_box.get(1.0, END).strip()
        self.text_box.delete(1.0, END)
        if text:
            self.utterances.append(text)
            self.annotation_frame.go_to_last()
        return 'break'

    # noinspection PyUnusedLocal
    def accept(self, utterance_index, utterance, graph, annotation):
        result = {
            'utterance': utterance,
            'annotation': annotation,
            'graph': graph.to_json(),
            'status': 'accepted',
        }
        encoded_utterance = utterance.encode()
        compressed_result = bz2.compress(json.dumps(result, sort_keys=True).encode())
        with self.file_access_lock:
            self.annotation_database[encoded_utterance] = compressed_result

    # noinspection PyUnusedLocal
    def reject(self, utterance_index, utterance, graph, annotation):
        result = {
            'utterance': utterance,
            'annotation': annotation,
            'graph': graph.to_json(),
            'status': 'rejected',
        }
        encoded_utterance = utterance.encode()
        compressed_result = bz2.compress(json.dumps(result, sort_keys=True).encode())
        with self.file_access_lock:
            self.annotation_database[encoded_utterance] = compressed_result

    # noinspection PyUnusedLocal
    def modify(self, utterance_index, utterance, graph, annotation):
        result = {
            'utterance': utterance,
            'annotation': annotation,
            'graph': graph.to_json()
        }
        encoded_utterance = utterance.encode()
        with self.file_access_lock:
            if encoded_utterance in self.annotation_database:
                status = json.loads(bz2.decompress(self.annotation_database[encoded_utterance]).decode()).get('status')
            else:
                status = None
            result['status'] = status
            self.annotation_database[utterance.encode()] = bz2.compress(json.dumps(result, sort_keys=True).encode())


# TODO: Make the app support choosing a model instead of assuming English.
def main():
    from pyramids_english import load_model
    model = load_model()
    with open(r'/home/hosford42/PycharmProjects/NLU/Data/sentences.txt', encoding='utf-8') as file:
        utterances = {line.strip() for line in file if line.strip()}
    print("Loaded", len(utterances), "utterances...")
    # TODO: We shouldn't have to prime the parser by calling it. Make an initialize() method, or do it in __init__.
    Parser(model).parse("hello")  # Prime the parser to make sure categories and properties are all loaded.
    app = AnnotatorApp(model, '/home/hosford42/PycharmProjects/NLU/Data/annotations.dbm', utterances)
    app.settings['timeout'] = 10
    mainloop()


if __name__ == '__main__':
    main()
