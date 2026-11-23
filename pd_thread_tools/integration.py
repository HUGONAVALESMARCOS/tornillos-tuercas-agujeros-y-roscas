# SPDX-License-Identifier: MIT
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from shiboken6 import isValid

from .add_hole import open_add_hole
from .add_material_visual import NutPanel
from .add_nut import NUT_ICON
from .remove_material_visual import HOLE_ICON, THREADED_HOLE_TITLE, ThreadedHoleEditor, uses_standalone_editor

ADDON_TITLE = 'Tornillos, Tuercas, Agujeros y Roscas'


class ThreadTools:
    def __init__(self):
        self.window = Gui.getMainWindow()
        self.hole = ThreadedHoleEditor()
        self.hole_icon = QtGui.QIcon(HOLE_ICON)
        self.toolbar = QtWidgets.QToolBar(ADDON_TITLE, self.window)
        self.toolbar.setObjectName('PDThreadToolsToolbar')
        self.window.addToolBar(self.toolbar)
        self.actions = []
        for title, icon, launch in (
            ('Tornillo', str(Path(__file__).with_name('tornillo.svg')), open_add_hole),
            ('Tuerca', NUT_ICON, self.open_nut),
            (THREADED_HOLE_TITLE, HOLE_ICON, self.hole.open),
        ):
            action = self.toolbar.addAction(QtGui.QIcon(icon), title)
            action.triggered.connect(lambda checked=False, launch=launch: self.run(launch))
            self.actions.append(action)
        self.panel = None
        self.timer = QtCore.QTimer(self.window)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(250)

    @staticmethod
    def body():
        document = Gui.activeDocument()
        if document is None:
            return None
        body = document.activeView().getActiveObject('pdbody')
        if body is not None:
            return body
        selected = Gui.Selection.getSelection()
        if (len(selected) == 1 and selected[0].Document == App.ActiveDocument
                and selected[0].TypeId == 'PartDesign::Body'):
            return selected[0]
        bodies = App.ActiveDocument.findObjects('PartDesign::Body')
        return bodies[0] if len(bodies) == 1 else None

    @staticmethod
    def in_part_design():
        workbench = Gui.activeWorkbench()
        return workbench is not None and workbench.name() == 'PartDesignWorkbench'

    @staticmethod
    def open_nut(document, body):
        Gui.Control.showDialog(NutPanel(document, body))

    def run(self, launch):
        body = self.body()
        if self.in_part_design() and body and not Gui.Control.activeDialog():
            Gui.activeDocument().activeView().setActiveObject('pdbody', body)
            launch(App.ActiveDocument, body)

    def refresh(self):
        self.hole.refresh()
        self.update_hole_tree_icons()
        active = self.in_part_design()
        show_panel = active and App.ActiveDocument is not None and not Gui.Control.activeDialog()
        available = show_panel and self.body() is not None
        self.toolbar.setVisible(active)
        for action in self.actions:
            action.setEnabled(available)
        tasks = self.window.findChild(QtWidgets.QDockWidget, 'Tasks')
        parent = None
        box = None
        if show_panel and tasks is not None:
            native_actions = {'PartDesign_Body', 'PartDesign_NewSketch', 'Sketcher_NewSketch',
                              'PartDesign_Pad', 'PartDesign_Boolean'}
            boxes = [widget for widget in tasks.findChildren(QtWidgets.QWidget)
                     if 'TaskBox' in widget.metaObject().className()
                     and any(action.objectName() in native_actions for action in widget.actions())]
            box = next((widget for widget in boxes if widget.isVisibleTo(tasks)), None)
            parent = box.parentWidget() if box is not None else next(
                (candidate.parentWidget() for candidate in boxes
                 if candidate.parentWidget().isVisibleTo(tasks)
                 and isinstance(candidate.parentWidget().layout(), QtWidgets.QBoxLayout)),
                tasks.widget(),
            )
        if parent is None or not isinstance(parent.layout(), QtWidgets.QBoxLayout):
            if self.panel is not None and isValid(self.panel):
                self.panel.hide()
            return
        layout = parent.layout()
        if self.panel is None or not isValid(self.panel):
            self.panel = QtWidgets.QGroupBox(ADDON_TITLE, parent)
            self.panel.setObjectName('PDThreadToolsTasks')
            buttons = QtWidgets.QVBoxLayout(self.panel)
            for action in self.actions:
                button = QtWidgets.QToolButton(self.panel)
                button.setDefaultAction(action)
                button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
                buttons.addWidget(button, 0, QtCore.Qt.AlignLeft)
        if self.panel.parentWidget() != parent:
            self.panel.setParent(parent)
        if layout.indexOf(self.panel) < 0:
            index = layout.indexOf(box) + 1 if box is not None else 0
            layout.insertWidget(index, self.panel)
        self.panel.show()

    def update_hole_tree_icons(self):
        document = App.ActiveDocument
        if document is None:
            return
        names = {obj.Name for obj in document.findObjects('PartDesign::Hole')
                 if uses_standalone_editor(obj)}
        if not names:
            return
        for tree in self.window.findChildren(QtWidgets.QTreeWidget):
            if tree.metaObject().indexOfSlot('onUpdateStatus()') < 0:
                continue
            for index in range(tree.topLevelItemCount()):
                root = tree.topLevelItem(index)
                if root.text(2) != document.Name and root.text(0) != document.Label:
                    continue
                items = QtWidgets.QTreeWidgetItemIterator(root)
                while (item := items.value()) is not None:
                    ancestor = item
                    while ancestor.parent() is not None:
                        ancestor = ancestor.parent()
                    if ancestor != root:
                        break
                    if item.text(2) in names and item.icon(0).cacheKey() != self.hole_icon.cacheKey():
                        item.setIcon(0, self.hole_icon)
                    items += 1


def install():
    global integration
    if 'integration' not in globals():
        integration = ThreadTools()
    return integration
