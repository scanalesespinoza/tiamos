"""Apply avatar presentation changes without repeating native widget writes."""


class AvatarPaint:
    def __init__(self, **widgets):
        self.widgets = widgets
        self.options = {}
        self.notice_signature = None

    def configure(self, name, **options):
        previous = self.options.setdefault(name, {})
        changed = {key: value for key, value in options.items() if key not in previous or previous[key] != value}
        if changed:
            self.widgets[name].configure(**changed)
            previous.update(changed)

    def notice(self, unread, full):
        signature = (bool(unread), bool(full))
        if signature == self.notice_signature:
            return
        badge = self.widgets['badge']
        if unread:
            self.configure('badge', font=('Segoe UI', 9 if full else 7))
            badge.place(relx=1, x=-3, y=3 if full else 0, anchor='ne')
            badge.lift()
        else:
            badge.place_forget()
        self.notice_signature = signature

    def visible(self, visible):
        window = self.widgets['window']
        withdrawn = window.state() == 'withdrawn'
        if visible and withdrawn:
            window.deiconify()
        elif not visible and not withdrawn:
            window.withdraw()
