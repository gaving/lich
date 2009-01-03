#!/usr/bin/env python

import os
import sys
import ConfigParser
import popen2
import gtk
import gtk.glade

import ID3
import mad
import ogg.vorbis


class Lich:
    """This class handles the actual interface of the application. """

    def __init__(self):
        self.wTree = gtk.glade.XML('glade/main.glade')

        dic = { 
                "on_playlist_window_delete" : self.onDelete,
                "on_playlist_window_destroy" : gtk.main_quit,
                "on_trackView_row_activated" : self.onRowActivated,
                "on_file_new_activate" : self.onNew,
                "on_file_open_activate" : self.onOpen,
                "on_file_save_activate" : self.onSave,
                "on_file_save_as_activate" : self.onSaveAs,
                "on_file_close_activate" : self.doClose,
                "on_file_quit_activate" : self.onQuit,
                "on_edit_preferences_activate" : self.createPrefsDialog,
                "on_playlist_add_activate" : self.onAdd,
                "on_playlist_remove_activate" : self.onRemove,
                "on_playlist_clear_activate" : self.onClear,
                "on_playlist_up_activate" : self.onUp,
                "on_playlist_down_activate" : self.onDown,
                "on_playlist_execute_activate" : self.onExecute,
                "on_help_about_activate" : self.createAboutDialog,
                "on_new_button_clicked" : self.onNew,
                "on_open_button_clicked" : self.onOpen,
                "on_add_button_clicked" : self.onAdd,
                "on_remove_button_clicked" : self.onRemove,
                "on_clear_button_clicked" : self.onClear,
                "on_up_button_clicked" : self.onUp,
                "on_down_button_clicked" : self.onDown,
                "on_execute_button_clicked" : self.onExecute,
                "on_save_button_clicked" : self.onSave,
                "prefs_on_close_button_clicked" : self.createPrefsDialog,
                "prefs_on_external_app_changed" : self.onExternalAppChanged
                } 

        self.wTree.signal_autoconnect(dic)

        self.state = State()
        self.controller = Controller()

        self.windowTitle = self.wTree.get_widget("playlist_window").get_title()

        self.cArtist = 0
        self.cTitle = 1
        self.cAlbum = 2
        self.cLength = 3

        self.sArtist = "Artist"
        self.sTitle = "Title"
        self.sAlbum = "Album"
        self.sLength = "Length"

        self.trackView = self.wTree.get_widget("trackView")

        self.addColumn(self.sArtist, self.cArtist)
        self.addColumn(self.sTitle, self.cTitle)
        self.addColumn(self.sAlbum, self.cAlbum)
        self.addColumn(self.sLength, self.cLength)

        self.trackList = gtk.ListStore(str, str, str, str)
        self.trackView.set_model(self.trackList)
        self.trackView.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        self.previousFilename = {
                'saved' : None,
                'opened' : None,
                'added' : None
                }

        # Handle any given argument
        if len(sys.argv) < 2:
            self.openNew()
            self.trackData = []
        else:
            if not self.performLoad(sys.argv[1]):
                self.doClose()
                return
            else:
                self.state.setSaved(True)

        self.checkButtons()

    def addColumn(self, title, columnId):
        column = gtk.TreeViewColumn(title, gtk.CellRendererText(), text=columnId)
        column.set_resizable(True)		
        self.trackView.append_column(column)

    def checkButtons(self, hasFile=True):
        hasTracks = len(self.trackData) > 0

        # Options available on row selection only
        self.wTree.get_widget("remove_button").set_sensitive(False)
        self.wTree.get_widget("playlist_remove").set_sensitive(False)
        self.wTree.get_widget("up_button").set_sensitive(False)
        self.wTree.get_widget("playlist_up").set_sensitive(False)
        self.wTree.get_widget("down_button").set_sensitive(False)
        self.wTree.get_widget("playlist_down").set_sensitive(False)

        # Dependant on tracks being in the trackview
        self.wTree.get_widget("clear_button").set_sensitive(hasTracks)
        self.wTree.get_widget("playlist_clear").set_sensitive(hasTracks)
        self.wTree.get_widget("execute_button").set_sensitive(hasTracks)
        self.wTree.get_widget("playlist_execute").set_sensitive(hasTracks)

        # Dependant on a playlist being currently open
        self.wTree.get_widget("file_save").set_sensitive(hasFile)
        self.wTree.get_widget("file_save_as").set_sensitive(hasFile)
        self.wTree.get_widget("file_close").set_sensitive(hasFile)
        self.wTree.get_widget("add_button").set_sensitive(hasFile)
        self.wTree.get_widget("save_button").set_sensitive(hasFile)
        self.wTree.get_widget("playlist_add").set_sensitive(hasFile)
        self.wTree.get_widget("trackView").set_sensitive(hasFile)

    def onRowActivated(self, widget):
        model, hasSelection = self.trackView.get_selection().get_selected_rows()

        if not hasSelection:
            return

        self.wTree.get_widget("remove_button").set_sensitive(True)
        self.wTree.get_widget("playlist_remove").set_sensitive(True)

        hasTracks = len(self.trackData) > 1
        self.wTree.get_widget("up_button").set_sensitive(hasTracks)
        self.wTree.get_widget("playlist_up").set_sensitive(hasTracks)
        self.wTree.get_widget("down_button").set_sensitive(hasTracks)
        self.wTree.get_widget("playlist_down").set_sensitive(hasTracks)

    def confirmClose(self):
        if self.state.isSaved():
            if self.state.isDirty():
                return self.createSaveChangesDialog()
            else:
                return True
        else:
            return self.createSaveChangesDialog()

    def confirmSave(self):
        filename = self.createSaveDialog("Confirm save")

        if filename is None:
            return False

        self.filename = filename
        self.performSave(filename)
        self.state.setSaved(True)

        return True

    def createAboutDialog(self, widget):
        self.wTree.get_widget("about_dialog").set_property('visible', True)

    def createPrefsDialog(self, widget):
        prefs_dialog = self.wTree.get_widget("prefs_dialog")
        prefs_dialog.set_property('visible', not prefs_dialog.get_property('visible'))

    def createOpenDialog(self, type="file", title="Select a file"):
        results = None
        chooser = gtk.FileChooserDialog(title, None, 
                gtk.FILE_CHOOSER_ACTION_OPEN,
                (gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))

        chooser.set_default_response(gtk.RESPONSE_OK)
        filter = gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        chooser.add_filter(filter)

        if type == "file":
            results = []

            if self.previousFilename['added']:
                chooser.set_filename(self.previousFilename['added'])

            chooser.set_select_multiple(True)

            filter = gtk.FileFilter()
            filter.set_name("Audio")
            filter.add_mime_type("audio/mp3")
            filter.add_mime_type("audio/ogg")
            filter.add_pattern("*.mp3")
            filter.add_pattern("*.ogg")
            chooser.add_filter(filter)
            chooser.set_filter(filter)

            if chooser.run() == gtk.RESPONSE_OK:
                for filename in chooser.get_filenames():
                    results.append(filename)
            try:
                self.previousFilename['added'] = results[-1]
            except IndexError:
                pass

        elif type == "playlist":

            if self.previousFilename['opened']:
                chooser.set_filename(self.previousFilename['opened'])

            filter = gtk.FileFilter()
            filter.set_name("Playlist")
            filter.add_pattern("*.m3u")
            chooser.add_filter(filter)
            chooser.set_filter(filter)

            if chooser.run() == gtk.RESPONSE_OK:
                results = chooser.get_filename()

            self.previousFilename['opened'] = results

        chooser.destroy()

        return results

    def createSaveDialog(self, title="Enter a filename"):
        filename = None
        
        chooser = gtk.FileChooserDialog(title, None, 
                gtk.FILE_CHOOSER_ACTION_SAVE,
                (gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_SAVE,gtk.RESPONSE_OK))

        chooser.set_current_name(self.filename and
                os.path.basename(self.filename) or "Untitled Playlist.m3u");

        chooser.set_default_response(gtk.RESPONSE_OK)

        if self.previousFilename['saved']:
            chooser.set_filename(self.previousFilename['saved'])

        filter = gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        chooser.add_filter(filter)

        if chooser.run() == gtk.RESPONSE_OK:
            filename = chooser.get_filename()

        chooser.destroy()

        self.previousFilename['saved'] = filename

        return filename

    def createSaveChangesDialog(self):
        dialog = gtk.MessageDialog(self.wTree.get_widget("playlist_window"), 0, \
                gtk.MESSAGE_WARNING, gtk.BUTTONS_NONE)

        dialog.set_destroy_with_parent(True)
        dialog.set_title("Confirm new")

        dialog.add_button("Close _Without Saving", gtk.RESPONSE_NO)
        dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        dialog.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_YES)

        dialog.set_default_response(gtk.RESPONSE_YES)
        dialog.set_markup("<b>Save changes to document \"%s\" before closing?</b>" \
                % (self.filename and os.path.basename(self.filename) or "Untitled"))
        dialog.format_secondary_text("If you don't save, changes may be permanently lost.")

        response = dialog.run()
        dialog.destroy()

        if response == gtk.RESPONSE_YES:
            if self.onSave(None):
                return True
            else:
                return False
        elif response == gtk.RESPONSE_NO:
            return True
        else:
            return False

    def doClose(self, widget=None):
        if not self.confirmClose():
            return

        self.trackData = []
        self.checkButtons(False)
        self.updateTitle()
        self.trackList.clear()

        # 'Fool' app into thinking its saved, and all is well.
        self.state.setDirty(False)
        self.state.setSaved(True)

    def fractSec(self, s):
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)

        if d: str = "%d day(s), %d hour(s), %d minutes, %s seconds." % (d, h, m, s)
        elif h: str = "%d hour(s), %d minute(s), %s seconds." % (h, m, s)
        elif m: str = "%d minute(s), %s second(s)." % (m, s)
        elif s: str = "%s second(s)." % s

        return str

    def onAdd(self, widget):
        filenames = self.createOpenDialog("file", "Open file")

        if len(filenames) < 1:
            return

        for filename in filenames:
            newtrack = self.controller.getTrackDetails(filename)
            if newtrack is None:
                return
            self.trackList.append(newtrack.getList())
            self.trackData.append(newtrack)

        self.updatePlaylistLength()
        self.checkButtons()
        self.state.setDirty(True)

    def onClear(self, widget):
        self.trackList.clear()
        self.trackData = []

        self.checkButtons()
        self.state.setDirty(True)

    def onNew(self, widget):
        if self.confirmClose():
            self.openNew()

    def onOpen(self, widget):
        if not self.confirmClose():
            return

        filename = self.createOpenDialog("playlist", "Open playlist")

        if filename is None:
            return

        if not self.performLoad(filename):
            self.doClose()
            return

        self.checkButtons()
        self.state.setSaved(True)
        self.state.setDirty(False)

    def onDelete(self, widget, hmmm):
        self.onQuit()
        return True

    def onQuit(self, widget=None):
        if self.confirmClose():
            gtk.main_quit()

    def onRemove(self, widget):
        model, pathList = self.trackView.get_selection().get_selected_rows()
        args = [(model.get_iter(path), path) for path in pathList]

        deletedTracks = []
        for iter, path in args:
            model.remove(iter)
            deletedTracks.append(path[0])

        newlist = []
        counter = 0
        for x in self.trackData:
            if counter not in deletedTracks:
                newlist.append(x)
            counter += 1

        self.trackData = newlist

        self.updatePlaylistLength()
        self.checkButtons()
        self.state.setDirty(True)

    def onSave(self, widget):
        if self.state.isSaved():
            self.performSave(self.filename)
            return True
        else:
            return self.confirmSave()

    def onSaveAs(self, widget):
        self.confirmSave()

    def swap(self, a, x ,y):
        a[x] = (a[x], a[y])
        a[y] = a[x][0]
        a[x] = a[x][1]

    def onUp(self, widget):
        model, pathList = self.trackView.get_selection().get_selected_rows()
        args = [(model.get_iter(path), path) for path in pathList]

        for iter, path in args:
            if path[0] > 0:
                new_iter = model.get_iter((path[0]-1,))
                model.move_before(iter, new_iter)
                self.swap(self.trackData, path[0], path[0]-1)

        self.state.setDirty(True)

    def onDown(self, widget):
        model, pathList = self.trackView.get_selection().get_selected_rows()
        args = [(model.get_iter(path), path) for path in pathList]

        args.reverse()

        for iter, path in args:
            if path[0] < len(self.trackData)-1:
                new_iter = model.get_iter((path[0]+1,))
                model.move_after(iter, new_iter)
                self.swap(self.trackData, path[0], path[0]+1)

        self.state.setDirty(True)

    def onExecute(self, widget):
        config = ConfigParser.ConfigParser()
        config.read(['.lichrc'])
        external_app = config.get('main','external_app')
        output = popen2.popen2('%s %s 2>/dev/null' % (external_app, self.filename))
        lines = output[0].readlines()
        for line in lines:
            print line

    def onExternalAppChanged(self, widget):
        print "TODO: set chosen path to config"

    def openNew(self):
        self.onClear(self)
        self.filename = None
        self.updateStatus("")
        self.updateTitle("Untitled")
        self.checkButtons()

        self.state.setDirty(False)
        self.state.setSaved(False)

    def performLoad(self, filename):
        self.openNew()
        self.trackData = self.controller.readPlaylist(filename)

        if self.trackData is None:
            self.state.setSaved(True)
            return False

        self.filename = filename

        for track in self.trackData:
            self.trackList.append(track.getList())

        self.updatePlaylistLength()
        self.updateTitle(os.path.basename(self.filename))

        return True

    def performSave(self, filename):
        self.controller.writePlaylist(filename, self.trackData)
        self.updateTitle(os.path.basename(filename))
        self.updateStatus("%s saved" % os.path.basename(filename))

        self.state.setDirty(False)

    def updatePlaylistLength(self):
        length = 0

        for track in self.trackData:
            length += track.getLength()

        if length:
            self.updateStatus("%d item(s). Playlist length: %s" \
                    % (len(self.trackData), self.fractSec(length)))
        else:
            self.updateStatus("Playlist empty!")

    def updateStatus(self, text):
        statusbar = self.wTree.get_widget("statusbar")
        statusbar.push(statusbar.get_context_id("statusbar"), text)

    def updateTitle(self, text=None):
        window = self.wTree.get_widget("playlist_window")
        if text:
            title = "%s %s" % (text + " -",self.windowTitle)
        else:
            title = self.windowTitle
        window.set_title(title)

class Controller:
    """This class handles the reading and writing of playlist files"""

    def createErrorDialog(self, text="An error occurred."):
        dlg = gtk.MessageDialog(None,
                gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                gtk.MESSAGE_ERROR,
                gtk.BUTTONS_OK,
                text + "\n")
        dlg.run()
        dlg.destroy()


    def getTrackDetails(self, filename):
        if filename.endswith("mp3"):

            try:
                meta = {}
                tag = ID3.ID3(filename)
                for key, val in tag.items():
                    if val != None: 
                        meta[key] = val

                mf = mad.MadFile(filename)
                meta['LENGTH'] = mf.total_time() / 1000

            except ID3.InvalidTagError:
                msg = "Error importing: '%s', cannot read ID3 tag." \
                        % os.path.basename(filename)
                self.createErrorDialog(msg)
                return

        elif filename.endswith("ogg"):

            try:
                ogginfo = ogg.vorbis.VorbisFile(filename) 

                meta = {}
                vc = ogginfo.comment()
                for key, val in vc.items():
                    if val != None: 
                        meta[key] = val

                meta['LENGTH'] = int(ogginfo.time_total(0))

            except ogg.vorbis.VorbisError:
                msg = "Error importing: '%s', cannot read file." \
                        % os.path.basename(filename)
                self.createErrorDialog(msg)
                return

        else:
            msg = "Error importing: '%s', format not supported." \
                    % os.path.basename(filename)
            self.createErrorDialog(msg)
            return

        try:
            artist = meta['ARTIST']
            title = meta['TITLE']
            album = meta['ALBUM']
            length = meta['LENGTH']
        except KeyError:
            msg = "Error importing: '%s', essential data from tag not found." \
                    % os.path.basename(filename)
            self.createErrorDialog(msg)
            return

        return Track(artist, title, album, length, filename)

    def readPlaylist(self, filename):
        tracks = []
        try:
            fp = open(filename, 'r')
            for line in fp:
                line = line.strip()
                if line[0] != '#' and os.path.exists(line):
                    tracks.append(self.getTrackDetails(line))
        except (IOError, IndexError):
            pass

        if len(tracks) > 0:
            return tracks
        else:
            msg = "Error opening: %s, the playlist may be corrupt." \
                    % os.path.basename(filename)
            self.createErrorDialog(msg)
            return

    def writePlaylist(self, filename, tracks):
        fp = None

        try:
            try:
                fp = open(filename, "w")
                fp.write("#EXTM3U\n")

                for track in tracks:

                    if track.artist and track.title:
                        fp.write("#EXTINF:" + str(track.length) + "," + \
                                track.artist + " - " + track.title + "\n")
                    else:
                        fp.write("#EXTINF:" + str(track.length) + "," + \
                                os.path.basename(track.path)[:-4] + "\n") 

                    fp.write(track.path + "\n")

            except (OSError, IOError), e:
                print e

        finally:
            if fp:
                fp.close()

class State:
    """This class represents the current state of the application"""

    __single = None

    def __init__(self):
        if State.__single:
            raise State.__single
        State.__single = self
        self.appstate = 'unsaved'
        self.filestate = 'dirty'

    def isDirty(self):
        return self.filestate == 'dirty'

    def isSaved(self):
        return self.appstate == 'saved'

    def setDirty(self, dirty):
        self.filestate = dirty and 'dirty' or 'clean'

    def setSaved(self, saved):
        self.appstate = saved and 'saved' or 'unsaved'

class Track:
    """This class represents a single track in the playlist"""

    def __init__(self, artist="", title="", album="", length="", path=""):
        self.artist = artist
        self.title = title
        self.album = album
        self.length = length
        self.path = path

    def fractSec(self, s):
        min, s = divmod(s, 60)
        return "%02d:%02d" % (min, s)

    def getLength(self):
        return self.length

    def getList(self):
        return [self.artist, self.title, self.album, self.fractSec(self.length)]

if __name__ == "__main__":
    Lich = Lich()
    gtk.main()

# vim: set expandtab shiftwidth=4 softtabstop=4 textwidth=79:
