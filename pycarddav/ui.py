#!/usr/bin/env python2
# vim: set ts=4 sw=4 expandtab sts=4:
# Copyright (c) 2011-2013 Christian Geier & contributors
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
The pycarddav interface to add, edit, or select a VCard.
"""

from __future__ import print_function

try:
    import sys
    import urwid

    import pycarddav

except ImportError, error:
    print(error)
    sys.exit(1)


class VCardWalker(urwid.ListWalker):
    """A walker to browse a VCard list.

    This walker returns a selectable Text for each of the passed VCard
    references. Either accounts or ref_account_list needs to be supplied. If no
    list of tuples of references are passed to the constructor, then all cards
    from the specified accounts are browsed.
    """

    class Entry(urwid.Text):
        """A specialized Text which can be used for browsing in a list."""
        _selectable = True

        def keypress(self, _, key):
            return key

    def __init__(self, database, accounts=None, ref_account_list=None):
        urwid.ListWalker.__init__(self)
        if accounts is None and ref_account_list is None:
            raise Exception
        self._db = database
        self._refs_account_list = ref_account_list or database.get_all_vref_from_db(accounts)
        self._current = 0

    @property
    def selected_vcard(self):
        """Return the focused VCard."""
        return self._db.get_vcard_from_db(self._refs_account_list[self._current][0],
                                          self._refs_account_list[self._current][1]
                                          )

    def get_focus(self):
        """Return (focused widget, focused position)."""
        return self._get_at(self._current)

    def set_focus(self, pos):
        """Focus on pos."""
        self._current = pos
        self._modified()

    def get_next(self, pos):
        """Return (widget after pos, position after pos)."""
        if pos >= len(self._refs_account_list) - 1:
            return None, None
        return self._get_at(pos + 1)

    def get_prev(self, pos):
        """Return (widget before pos, position before pos)."""
        if pos <= 0:
            return None, None
        return self._get_at(pos - 1)

    def _get_at(self, pos):
        """Return a textual representation of the VCard at pos."""
        vcard = self._db.get_vcard_from_db(self._refs_account_list[pos][0],
                                           self._refs_account_list[pos][1]
                                           )
        label = vcard.fname
        if vcard['EMAIL']:
            label += ' (%s)' % vcard['EMAIL'][0][0]
        return urwid.AttrMap(VCardWalker.Entry(label), 'list', 'list focused'), pos


class Pane(urwid.WidgetWrap):
    """An abstract Pane to be used in a Window object."""
    def __init__(self, widget, title=None, description=None):
        urwid.WidgetWrap.__init__(self, widget)
        self._title = title or ''
        self._description = description or ''
        self.window = None

    @property
    def title(self):
        return self._title

    @property
    def description(self):
        return self._description

    def get_keys(self):
        """Return a description of the keystrokes recognized by this pane.

        This method returns a list of tuples describing the keys
        handled by a pane. This list is used to build a contextual
        pane help. Each tuple is a pair of a list of keys and a
        description.

        The abstract pane returns the default keys handled by the
        window. Panes which do not override there keys should extend
        this list.
        """
        return [(['up', 'down', 'pg.up', 'pg.down'], 'navigate through the fields.'),
                (['esc'], 'backtrack to the previous pane of exit.'),
                (['F1'], 'open this pane help.')]


class HelpPane(Pane):
    """A contextual help screen."""
    def __init__(self, pane):
        content = []
        for key_list, description in pane.get_keys():
            key_text = []
            for key in key_list:
                if key_text:
                    key_text.append(', ')
                key_text.append(('bright', key))
            content.append(
                urwid.Columns(
                    [urwid.Padding(urwid.Text(key_text), left=10),
                     urwid.Padding(urwid.Text(description), right=10)]))

        Pane.__init__(self, urwid.ListBox(urwid.SimpleListWalker(content)), 'Help')


class VCardChooserPane(Pane):
    """A VCards chooser.

    This pane allows to browse a list of VCards. If no references are
    passed to the constructor, then the whole database is browsed. A
    VCard can be selected to be used in another pane, like the
    EditorPane.
    """
    def __init__(self, database, accounts=None, refs_account_list=None):
        self._walker = VCardWalker(database, accounts=accounts, ref_account_list=refs_account_list)
        Pane.__init__(self, urwid.ListBox(self._walker), 'Browse...')

    def get_keys(self):
        keys = Pane.get_keys(self)
        keys.append(([' ', 'enter'], 'select a contact.'))
        return keys

    def keypress(self, size, key):
        self._w.keypress(size, key)
        if key in ['space', 'enter']:
            self.window.backtrack(self._walker.selected_vcard)
        else:
            return key


class EditorPane(Pane):
    """A VCard editor."""
    def __init__(self, database, account, vcard):
        self._vcard = vcard
        self._db = database
        self._account = account

        self._label = vcard.fname if vcard.fname else vcard['EMAIL'][0][0]
        self._fname_edit = urwid.Edit(u'', u'')
        self._lname_edit = urwid.Edit(u'', u'')
        self._email_edits = None

        Pane.__init__(self, self._build_ui(), 'Edit %s' % vcard.fname)

    def get_keys(self):
        keys = Pane.get_keys(self)
        keys.append((['F8'], 'save this contact.'))
        return keys

    def keypress(self, size, key):
        self._w.keypress(size, key)
        if key == 'f8':
            self._validate()
            self.window.backtrack()
        else:
            return key

    def on_button_press(self, button):
        if button.get_label() == 'Merge':
            self.window.open(VCardChooserPane(self._db, accounts=[self._account]), self.on_merge_vcard)
        else:
            if button.get_label() == 'Store':
                self._validate()
            self.window.backtrack()

    def on_merge_vcard(self, vcard):
        # TODO: this currently merges only one email field, which is ok to use with mutt.
        if vcard:
            vcard['EMAIL'].append(self._vcard['EMAIL'][0])
            self._vcard = vcard
            self._w = self._build_ui()

    def _build_ui(self):
        content = []
        content.extend(self._build_names_section())
        content.extend(self._build_emails_section())
        content.extend(self._build_buttons_section())

        return urwid.ListBox(urwid.SimpleListWalker(content))

    def _build_names_section(self):
        names = self._vcard.name.split(';')
        if len(names) > 1:
            self._lname_edit.set_edit_text(names[0])
            self._fname_edit.set_edit_text(names[1])
        else:
            self._lname_edit.set_edit_text(u'')
            self._fname_edit.set_edit_text(names[0])

        return [urwid.Divider(),
                urwid.Columns([
                    ('fixed', 15, urwid.AttrWrap(urwid.Text(u'First Name'), 'line header')),
                    urwid.AttrWrap(self._fname_edit, 'edit', 'edit focused')]),
                urwid.Divider(),
                urwid.Columns([
                    ('fixed', 15, urwid.AttrWrap(urwid.Text(u'Last Name'), 'line header')),
                    urwid.AttrWrap(self._lname_edit, 'edit', 'edit focused')])]

    def _build_emails_section(self):
        self._email_edits = []
        content = []
        for mail in self._vcard['EMAIL']:
            edit = urwid.Edit('', mail[0])
            self._email_edits.append(edit)
            content.extend([
                urwid.Divider(),
                urwid.Columns([
                    ('fixed', 15, urwid.AttrWrap(urwid.Text(u'Email'), 'line header')),
                    urwid.AttrWrap(edit, 'edit', 'edit focused')])])

        return content

    def _build_buttons_section(self):
        buttons = [u'Cancel', u'Merge', u'Store']
        row = urwid.GridFlow([urwid.AttrWrap(urwid.Button(lbl, self.on_button_press),
                             'button', 'button focused') for lbl in buttons],
                             10, 3, 1, 'left')
        return [urwid.Divider('-', 1, 1),
                urwid.Padding(row, 'right', 13 * len(buttons), None, 1, 1)]

    def _validate(self):
        self._vcard.fname = ' '.join(
            [self._fname_edit.edit_text, self._lname_edit.edit_text])
        for i, edit in enumerate(self._email_edits):
            self._vcard['EMAIL'][i] = (edit.edit_text, self._vcard['EMAIL'][i][1])
        self._db.update(self._vcard, self._account, self._vcard.href, status=pycarddav.backend.NEW)


class Window(urwid.Frame):
    """The main user interface frame.

    A window is a frame which displays a header, a footer and a body.
    The header and the footer are handled by this object, and the body
    is the space where Panes can be displayed.

    Each Pane is an interface to interact with the database in one
    way: list the VCards, edit one VCard, and so on. The Window
    provides a mechanism allowing the panes to chain themselves, and
    to carry data between them.
    """
    PALETTE = [('header', 'white', 'black'),
               ('footer', 'white', 'black'),
               ('line header', 'black', 'white', 'bold'),
               ('bright', 'dark blue', 'white', ('bold', 'standout')),
               ('list', 'black', 'white'),
               ('list focused', 'white', 'light blue', 'bold'),
               ('edit', 'black', 'white'),
               ('edit focused', 'white', 'light blue', 'bold'),
               ('button', 'black', 'dark cyan'),
               ('button focused', 'white', 'light blue', 'bold')]

    def __init__(self):
        self._track = []
        self._title = u' %s v.%s' % (pycarddav.__productname__, pycarddav.__version__)

        header = urwid.AttrWrap(urwid.Text(self._title), 'header')
        footer = urwid.AttrWrap(urwid.Text(
            u' Use Up/Down/PgUp/PgDown to scroll. Esc to return. F1 for help'), 'footer')
        urwid.Frame.__init__(self, urwid.Text(''), header=header, footer=footer)

    def open(self, pane, callback=None):
        """Open a new pane.

        The given pane is added to the track and opened. If the given
        callback is not None, it will be called when this new pane
        will be closed.
        """
        pane.window = self
        self._track.append((pane, callback))
        self._update(pane)

    def backtrack(self, data=None):
        """Unstack the displayed pane.

        The current pane is discarded, and the previous one is
        displayed. If the current pane was opened with a callback,
        this callback is called with the given data (if any) before
        the previous pane gets redrawn.
        """
        _, cb = self._track.pop()
        if cb:
            cb(data)

        if self._track:
            self._update(self._get_current_pane())
        else:
            raise urwid.ExitMainLoop()

    def on_key_press(self, key):
        """Handle application-wide key strokes."""
        if key == 'esc':
            self.backtrack()
        elif key == 'f1':
            self.open(HelpPane(self._get_current_pane()))

    def _update(self, pane):
        self.header.w.set_text(u'%s | %s' % (self._title, pane.title))
        self.set_body(pane)

    def _get_current_pane(self):
        return self._track[-1][0] if self._track else None


def start_pane(pane):
    """Open the user interface with the given initial pane."""
    frame = Window()
    frame.open(pane)
    loop = urwid.MainLoop(frame, Window.PALETTE,
                          unhandled_input=frame.on_key_press)
    loop.run()
