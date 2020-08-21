import datetime

import entity
from helper import color_helper, datetime_helper, database_helper
from widget.category_choice_dialog import CategoryChoiceDialog
from repository.category_repository import CategoryRepository

import cairo
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject


class TimelineCanvas(Gtk.DrawingArea):
    @GObject.Signal(name="tagged-entry-created",
                    flags=GObject.SignalFlags.RUN_LAST,
                    return_type=GObject.TYPE_BOOLEAN,
                    arg_types=(object,))
    def tagged_entry_created(self, *args):
        pass

    def __init__(self, parent: Gtk.Window):
        super().__init__()
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK
                        | Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.connect("draw", self._do_draw)
        self.connect("motion_notify_event", self._on_motion_notify)
        self.connect("button_press_event", self._on_button_press)
        self.connect("button_release_event", self._on_button_release)

        self.parent = parent

        self.current_mouse_pos = 0
        self.actual_mouse_pos = {"x": 0, "y": 0}

        self.timeline_side_padding = 13
        self.timeline_top_padding = 15
        self.timeline_height = 80
        self.pixels_per_seconds = 2

        self.category_repository = CategoryRepository()

        self._current_date = None
        self.current_tagged_entry = None
        self.tagged_entries = []
        self.logged_entries = []

    def set_entries(self, dt: datetime.datetime, logged_entries, tagged_entries):
        self.logged_entries = logged_entries
        self.tagged_entries = tagged_entries
        self._current_date = dt
        self.queue_draw()

    def _do_draw(self, w: Gtk.DrawingArea, cr: cairo.Context):
        # Get the size
        drawing_area_size, _ = w.get_allocated_size()
        self.timeline_height = drawing_area_size.height * 0.25
        self.timeline_top_padding = drawing_area_size.height * 0.08

        timeline_x = self._get_timeline_x(self.current_mouse_pos, w)

        # Draw the hour lines
        hour_x_offset = (drawing_area_size.width - self.timeline_side_padding * 2) / 24
        for h in range(0, 25):
            # Hour line
            hx = self.timeline_side_padding + hour_x_offset * h
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.new_path()
            cr.move_to(hx, 10)
            cr.line_to(hx, drawing_area_size.height - 50)  # TODO: Make 50 a variable (hourlineLength)
            cr.stroke()

            # Hour text
            hour_string = str(h)
            text_offset = 5 if len(hour_string) == 1 else 10
            cr.move_to(hx - text_offset, drawing_area_size.height - 30)
            cr.set_font_size(16)
            cr.show_text(str(h))

        self.pixels_per_seconds = (drawing_area_size.width - self.timeline_side_padding * 2) / (24 * 60 * 60)
        for le in self.logged_entries:
            start_x = self._datetime_to_pixel(le.start)
            stop_x = self._datetime_to_pixel(le.stop)

            color_string = color_helper.to_color(le.application.name)
            color = Gdk.color_parse(spec=color_string)
            cr.set_source_rgb(color.red_float, color.green_float, color.blue_float)
            cr.rectangle(start_x, self.timeline_height + self.timeline_top_padding * 2,
                         stop_x - start_x, self.timeline_height)
            cr.fill()

        for tagged_entry in self.tagged_entries:
            self._draw_tagged_entry(tagged_entry, cr)

        if self.current_tagged_entry is not None:
            self._draw_tagged_entry(self.current_tagged_entry, cr)

        # Show a guiding line under the mouse cursor
        cr.new_path()
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.move_to(timeline_x, 10)
        cr.line_to(timeline_x, drawing_area_size.height - 10)
        cr.stroke()

        moused_over_le = None
        for le in self.logged_entries:
            if self._datetime_to_pixel(le.stop) < self.actual_mouse_pos["x"]:
                continue
            elif self.actual_mouse_pos["x"] < self._datetime_to_pixel(le.start):
                break
            else:
                moused_over_le = le
                break

        if moused_over_le is not None:
            cr.set_font_size(16)
            padding = 10
            time_interval_text = f"{datetime_helper.to_time_str(moused_over_le.start)} => {datetime_helper.to_time_str(moused_over_le.stop)}"
            title_text = f"{moused_over_le.application.name} => {moused_over_le.title}"

            (x, y, width, height, dx, dy) = cr.text_extents(time_interval_text)
            max_width = width
            height_to_use = height
            time_interval_y = self.actual_mouse_pos["y"] + height + padding
            time_interval_height = height
            title_y = time_interval_y + height + 5
            (x, y, width, height, dx, dy) = cr.text_extents(title_text)
            width_to_use = max(max_width, width) + (padding * 2)
            height_to_use += height
            x_to_use = min(self.actual_mouse_pos["x"], drawing_area_size.width - width_to_use)

            # Draw rectangle
            cr.set_source_rgba(0.1, 0.1, 0.8, 0.8)
            cr.rectangle(x_to_use,
                         time_interval_y - time_interval_height - padding,
                         width_to_use,
                         height_to_use + (padding * 2))
            cr.fill()

            # Time interval text
            cr.move_to(x_to_use + 10, time_interval_y)
            cr.set_source_rgb(0.9, 0.9, 0.0)
            cr.show_text(time_interval_text)

            # Title text
            cr.move_to(x_to_use + 10, title_y)
            cr.set_source_rgb(0.0, 0.9, 0.9)
            cr.show_text(title_text)

    @staticmethod
    def _set_tagged_entry_stop_date(stop_date: datetime,
                                    tagged_entry: entity.TaggedEntry, tagged_entries: list):
        tagged_entry.stop = stop_date

        creation_is_right = stop_date == tagged_entry.stop
        date_to_use = None
        for t in tagged_entries:
            if creation_is_right:
                if t.start < stop_date and t.stop > tagged_entry.start:
                    date_to_use = t.start
                    break
            else:
                if stop_date < t.stop and t.start < tagged_entry.stop:
                    date_to_use = t.stop

        if date_to_use is not None:
            tagged_entry.stop = date_to_use

        return date_to_use

    def _on_button_press(self, widget, event):
        c = entity.Category(name="Test")
        timeline_x = self._get_timeline_x(self.current_mouse_pos, self)
        start_date = self._pixel_to_datetime(timeline_x)
        self.current_tagged_entry = entity.TaggedEntry(category=c, start=start_date, stop=start_date)

    def _on_button_release(self, widget, event: Gdk.EventType):
        # Ensure that an entry is being created.
        if self.current_tagged_entry is None:
            return

        tagged_entry_to_create = self.current_tagged_entry
        self.current_tagged_entry = None

        timeline_x = self._get_timeline_x(event.x, self)
        stop_date = self._pixel_to_datetime(timeline_x)
        self._set_tagged_entry_stop_date(stop_date, tagged_entry_to_create, self.tagged_entries)
        if tagged_entry_to_create.start == tagged_entry_to_create.stop:
            return

        # Choose category
        conn = database_helper.create_connection()
        categories = self.category_repository.get_all(conn=conn)
        conn.close()
        dialog = CategoryChoiceDialog(window=self.parent, categories=categories)
        r = dialog.run()
        chosen_category_name = dialog.get_chosen_category_value()
        dialog.destroy()

        print(r)

        if r == Gtk.ResponseType.OK:
            # Set chosen category
            chosen_category = [c for c in categories if c.name.lower() == chosen_category_name.lower()]
            if len(chosen_category) == 1:
                chosen_category = chosen_category[0]
            else:
                new_category = entity.Category(name=chosen_category_name)
                conn = database_helper.create_connection()
                self.category_repository.insert(conn=conn, category=new_category)
                conn.close()
                chosen_category = new_category

            tagged_entry_to_create.category = chosen_category
            self.emit("tagged-entry-created", tagged_entry_to_create)

        self.queue_draw()

    def _on_motion_notify(self, widget: Gtk.DrawingArea, event):
        timeline_x = self._get_timeline_x(event.x, widget)
        stop_date = self._pixel_to_datetime(timeline_x)

        next_mouse_pos = event.x
        if self.current_tagged_entry is not None:
            datetime_used = self._set_tagged_entry_stop_date(stop_date,
                                                             self.current_tagged_entry,
                                                             self.tagged_entries)
            if datetime_used is not None:
                next_mouse_pos = self._datetime_to_pixel(datetime_used)
        else:
            for t in self.tagged_entries:
                if t.contains_datetime(stop_date):
                    start_delta = stop_date - t.start
                    stop_delta = t.stop - stop_date

                    datetime_position = t.start if start_delta < stop_delta else t.stop
                    next_mouse_pos = self._datetime_to_pixel(datetime_position)
                    break

        self.current_mouse_pos = next_mouse_pos
        self.actual_mouse_pos["x"], self.actual_mouse_pos["y"] = event.x, event.y
        self.queue_draw()

    def _get_timeline_x(self, mouse_position: float, drawing_area: Gtk.DrawingArea):
        max_timeline_x = drawing_area.get_allocated_size()[0].width - self.timeline_side_padding - 0.00001
        min_timeline_x = self.timeline_side_padding

        timeline_x = max(mouse_position, min_timeline_x)
        timeline_x = min(max_timeline_x, timeline_x)
        return timeline_x

    def _datetime_to_pixel(self, dt: datetime) -> float:
        hour, minute, second = dt.hour, dt.minute, dt.second
        if dt < self._current_date:
            hour, minute, second = 0, 0, 0
        elif self._current_date + datetime.timedelta(days=1) <= dt:
            hour, minute, second = 23, 59, 59

        return self.pixels_per_seconds * (hour * 60 * 60 + minute * 60 + second) + self.timeline_side_padding

    def _draw_tagged_entry(self, tagged_entry: entity.TaggedEntry, cr: cairo.Context):
        start_x = self._datetime_to_pixel(tagged_entry.start)
        stop_x = self._datetime_to_pixel(tagged_entry.stop)

        cr.set_source_rgb(0, 1, 0)
        if tagged_entry.category is not None:
            color_string = tagged_entry.category.color_rgb
            color = Gdk.color_parse(spec=color_string)
            cr.set_source_rgb(color.red_float, color.green_float, color.blue_float)
        cr.rectangle(start_x, self.timeline_top_padding, stop_x - start_x, self.timeline_height)
        cr.fill()

    def _pixel_to_datetime(self, x_position: int) -> datetime:
        total_seconds = (x_position - self.timeline_side_padding) / self.pixels_per_seconds
        hours = total_seconds // (60 * 60)
        minutes = (total_seconds - hours * 60 * 60) // 60
        seconds = int(total_seconds % 60)
        d = datetime.datetime(year=self._current_date.year,
                              month=self._current_date.month,
                              day=self._current_date.day)
        d += datetime.timedelta(hours=hours, minutes=minutes, seconds=seconds)
        return d
