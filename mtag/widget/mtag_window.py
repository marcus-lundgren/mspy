import datetime
from itertools import groupby

from mtag.helper import datetime_helper, database_helper
from mtag.widget.calendar_panel import CalendarPanel
from mtag.widget.timeline_canvas import TimelineCanvas
from mtag.entity import TaggedEntry
from mtag.repository.logged_entry_repository import LoggedEntryRepository
from mtag.repository.tagged_entry_repository import TaggedEntryRepository

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import Gdk


class MTagWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="MTag")
        self.set_default_size(720, 500)
        it = Gtk.IconTheme()
        icon = it.load_icon(Gtk.STOCK_FIND, 256, Gtk.IconLookupFlags.USE_BUILTIN)
        self.set_icon(icon)
        self.connect("destroy", Gtk.main_quit)

        b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(b)

        # Top bar
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.calendar_panel = CalendarPanel()
        self.calendar_panel.connect("day-selected", self._on_new_day_selected)
        top_bar.pack_start(self.calendar_panel, expand=True, fill=False, padding=0)
        b.add(top_bar)

        self._current_date = self.calendar_panel.get_selected_date()

        # Drawing area
        self.current_mouse_pos = 0
        self.actual_mouse_pos = {"x": 0, "y": 0}

        self.timeline_canvas = TimelineCanvas(parent=self)
        self.timeline_canvas.connect("tagged-entry-created", self._do_tagged_entry_created)
        self.timeline_canvas.connect("tagged-entry-deleted", self._do_tagged_entry_deleted)
        self.connect("configure-event", self._do_configure_event)

        b.pack_start(self.timeline_canvas, expand=True, fill=True, padding=0)

        lists_grid = Gtk.Grid()
        lists_grid.set_column_homogeneous(True)
        lists_grid.set_row_homogeneous(True)
        lists_grid.set_column_spacing(20)

        self.tagged_entries_box = Gtk.ListBox()

        # Logged entries list
        self.logged_entries_list_store = Gtk.ListStore(str, str, str, str, str)
        self.logged_entries_tree_view = Gtk.TreeView.new_with_model(self.logged_entries_list_store)

        for i, title in enumerate(["Start", "Stop", "Duration", "Application", "Title"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=i)
            column.set_sort_column_id(i)
            column.set_expand(title == "Title")
            self.logged_entries_tree_view.append_column(column)

        # Tagged entries list
        self.tagged_entries_list_store = Gtk.ListStore(str, str)
        self.tagged_entries_tree_view = Gtk.TreeView.new_with_model(self.tagged_entries_list_store)
        self.tagged_entries_tree_view.set_headers_clickable(True)

        for i, title in enumerate(["Duration", "Category"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=i)
            column.set_sort_column_id(i)
            self.tagged_entries_tree_view.append_column(column)

        self.logged_entries_tree_view.set_headers_clickable(True)

        letw_container = Gtk.ScrolledWindow()
        letw_container.add(self.logged_entries_tree_view)
        lists_grid.attach(letw_container, 0, 0, 1, 1)
        lists_grid.attach(self.tagged_entries_tree_view, 1, 0, 1, 1)

        b.pack_end(lists_grid, expand=True, fill=True, padding=10)
        self._reload_logged_entries_from_date()
        self.show_all()

    def _do_tagged_entry_created(self, _, te: TaggedEntry):
        tagged_entry_repository = TaggedEntryRepository()
        conn = database_helper.create_connection()
        tagged_entry_repository.insert(conn=conn, tagged_entry=te)
        conn.close()
        self._reload_logged_entries_from_date()

    def _do_tagged_entry_deleted(self, _, te: TaggedEntry):
        tagged_entry_repository = TaggedEntryRepository()
        conn = database_helper.create_connection()
        tagged_entry_repository.delete(conn=conn, db_id=te.db_id)
        conn.close()
        self._reload_logged_entries_from_date()

    def _do_configure_event(self, w, e: Gdk.EventConfigure):
        print(e.width, e.height)

    def _on_new_day_selected(self, _, date: datetime.datetime):
        self._current_date = date
        self._reload_logged_entries_from_date()

    def _reload_logged_entries_from_date(self):
        db_connection = database_helper.create_connection()
        logged_entry_repository = LoggedEntryRepository()
        tagged_entry_repository = TaggedEntryRepository()

        logged_entries = logged_entry_repository.get_all_by_date(db_connection, self._current_date)
        tagged_entries = tagged_entry_repository.get_all_by_date(db_connection, self._current_date)
        db_connection.close()

        self.timeline_canvas.set_entries(self._current_date, logged_entries, tagged_entries)

        self.logged_entries_list_store.clear()
        for le in logged_entries:
            self.logged_entries_list_store.append([datetime_helper.to_time_str(le.start),
                                                   datetime_helper.to_time_str(le.stop),
                                                   datetime_helper.to_duration_str(le.duration),
                                                   le.application_window.application.name,
                                                   le.application_window.title])
        self.logged_entries_tree_view.columns_autosize()

        self.tagged_entries_list_store.clear()
        for te_category, te_group in groupby(sorted(tagged_entries, key=lambda x: x.category.db_id),
                                             key=lambda x: x.category.name):
            duration = sum([te.duration for te in te_group], start=datetime.timedelta())
            self.tagged_entries_list_store.append([datetime_helper.to_duration_str(duration),
                                                   te_category])
        self.tagged_entries_tree_view.columns_autosize()