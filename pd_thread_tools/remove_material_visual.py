# SPDX-License-Identifier: MIT

from pathlib import Path

import FreeCAD as App


import FreeCADGui as Gui


import Part


from PySide import QtCore, QtWidgets


from pivy import coin


from shiboken6 import isValid


from . import independent_pocket


from . import manual_hole_thread
from . import standard_hole_preview


from .add_material_visual import PlacementFields, edited_feature, task_widget


THREADED_HOLE_TITLE = 'Agujeros y Roscas'
HOLE_ICON = str(Path(__file__).with_name('agujeros-y-roscas.png'))


HOLE_POSITION = 'PosicionAgujero'


def uses_standalone_editor(feature):
    return (feature is not None and feature.TypeId == 'PartDesign::Hole'
            and HOLE_POSITION in feature.PropertiesList
            and getattr(feature, 'EditorAgujero', '') != 'QUITAR')


HOLE_STANDARD_TITLES = {
    'None': 'Nada (diámetro manual)',
    'ISOMetricProfile': 'Métrica de paso regular, mm (ISO)',
    'ISOMetricFineProfile': 'Métrica de paso fino, mm (ISO)',
    'UNC': 'Unificada gruesa, pulgadas (UNC)',
    'UNF': 'Unificada fina, pulgadas (UNF)',
    'UNEF': 'Unificada extrafina, pulgadas (UNEF)',
    'NPT': 'Tubería cónica, pulgadas nominales (NPT)',
    'BSP': 'Tubería británica, pulgadas nominales (BSP)',
    'BSW': 'Whitworth gruesa, pulgadas (BSW)',
    'BSF': 'Whitworth fina, pulgadas (BSF)',
    'ISOTyre': 'Válvulas de neumático, Ø en mm (ISO 4570)',
}


HOLE_HEAD_SHAPES = {
    'DIN 7984': 'Cilíndrica baja',
    'ISO 10642': 'Avellanada',
    'ISO 12474': 'Cilíndrica',
    'ISO 14583': 'Abombada tipo pan',
    'ISO 2009': 'Avellanada',
    'ISO 4762': 'Cilíndrica',
    'ISO 4762 + 7089': 'Cilíndrica con arandela',
    'ISO 7046': 'Avellanada',
}


class HoleHeadLabels(QtWidgets.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        code = option.text
        if code.startswith('ISO 14583 ('):
            option.text = 'Abombada tipo pan, rosca parcial (ISO 14583)'
        elif code in HOLE_HEAD_SHAPES:
            option.text = f'{HOLE_HEAD_SHAPES[code]} ({code})'


def describe_hole_choices(panel, hole):
    standard = panel.findChild(QtWidgets.QComboBox, 'ThreadType')
    if standard is not None:
        keys = hole.getEnumerationsOfProperty('ThreadType')
        if standard.count() == len(keys):
            with QtCore.QSignalBlocker(standard):
                for index, key in enumerate(keys):
                    if key in HOLE_STANDARD_TITLES:
                        standard.setItemText(index, HOLE_STANDARD_TITLES[key])
    head = panel.findChild(QtWidgets.QComboBox, 'HoleCutType')
    if head is not None:
        # FreeCAD uses the unmodified item text to restore the head when switching standards.
        head.setItemDelegate(HoleHeadLabels(head))


def update_hole_position(hole):
    profile = hole.Profile[0] if hole.Profile else None
    if profile is not None and getattr(profile, 'HoleOriginProfile', False):
        if profile.Placement != hole.PosicionAgujero:
            profile.Placement = hole.PosicionAgujero
            return True
    return False


def hole_position_controls(parent, hole):
    def move():
        hole.PosicionAgujero = fields.placement()
        if update_hole_position(hole):
            hole.Document.recompute()

    fields = PlacementFields(parent, 'Posición del agujero', 'Ángulo del agujero', move)
    fields.load_placement(hole.PosicionAgujero)
    return fields


def manual_thread_controls(parent, hole, preview, native_panel):
    from .add_hole import thread_pitch

    for kind, name, default in (
        ('Bool', 'ModelarRoscaManual', False),
        ('Length', 'PasoRoscaManual', 1.0),
        ('Length', 'LongitudRoscaManual', 10.0),
        ('Bool', 'RoscaManualIzquierda', False),
    ):
        if name not in hole.PropertiesList:
            hole.addProperty('App::Property' + kind, name, 'Rosca manual')
            setattr(hole, name, default)
    box = QtWidgets.QGroupBox('Rosca', parent)
    box.setObjectName('ManualHoleThreadControls')
    form = QtWidgets.QFormLayout(box)
    model = QtWidgets.QCheckBox('Modelar rosca')
    model.setChecked(manual_hole_thread.enabled(hole) or hole.ModelThread)
    form.addRow(model)
    fields = {}
    for label, name in (('Paso', 'PasoRoscaManual'), ('Longitud roscada', 'LongitudRoscaManual')):
        spin = QtWidgets.QDoubleSpinBox()
        spin.setDecimals(4 if name == 'PasoRoscaManual' else 3)
        spin.setRange(0.001, 1000)
        spin.setSuffix(' mm')
        spin.setValue(getattr(hole, name).Value)
        spin.valueChanged.connect(lambda value, prop=name: setattr(hole, prop, value))
        form.addRow(label, spin)
        fields[name] = spin
    direction = QtWidgets.QComboBox()
    direction.addItems(['Mano derecha', 'Mano izquierda'])
    direction.setCurrentIndex(int(hole.RoscaManualIzquierda))
    direction.currentIndexChanged.connect(lambda index: setattr(hole, 'RoscaManualIzquierda', bool(index)))
    form.addRow('Dirección', direction)
    status = QtWidgets.QLabel()
    status.setWordWrap(True)
    form.addRow(status)
    native_type = native_panel.findChild(QtWidgets.QComboBox, 'HoleType')
    native_controls = [native_panel.findChild(QtWidgets.QWidget, name) for name in (
        'labelThreading', 'labelHoleType', 'HoleType', 'labelThreadClearance',
        'ThreadFit', 'ClearanceWidget', 'ThreadGroupBox')]

    def apply_thread_mode(checked):
        hole.ModelarRoscaManual = checked
        if hole.ThreadType != 'None' and native_type is not None:
            native_type.setCurrentIndex(int(checked))
        manual_hole_thread.prepare_native_bore(hole)

    model.toggled.connect(apply_thread_mode)
    view = Gui.activeDocument().activeView()
    graph = view.getSceneGraph()
    overlay = coin.SoSeparator()
    graph.addChild(overlay)
    options = preview.findChildren(QtWidgets.QCheckBox) if preview is not None else []
    signature = None
    catalog_selection = (hole.ThreadType, hole.ThreadSize)

    def suggest_pitch():
        try:
            pitch = thread_pitch(hole.ThreadType, hole.ThreadSize, hole.PasoRoscaManual.Value)
        except (KeyError, ValueError, IndexError):
            return
        fields['PasoRoscaManual'].setValue(pitch)

    if hole.ThreadType != 'None' and not hole.ModelarRoscaManual:
        suggest_pitch()

    def redraw():
        nonlocal signature, catalog_selection
        if not isValid(box) or edited_feature() != hole:
            return
        manual = hole.ThreadType == 'None'
        box.setVisible(box.property('ThreadSectionExpanded') is not False)
        selection = (hole.ThreadType, hole.ThreadSize)
        if selection != catalog_selection:
            catalog_selection = selection
            suggest_pitch()
            apply_thread_mode(model.isChecked())
        for control in native_controls:
            if control is not None and isValid(control):
                control.hide()
        custom_thread = manual_hole_thread.enabled(hole)
        if manual_hole_thread.prepare_native_bore(hole) and hole.BaseFeature is not None:
            hole.recompute()
        base = hole.BaseFeature
        empty_body = base is None or not base.Shape.Solids
        key = (manual, str(hole.PosicionAgujero), hole.Reversed, hole.Diameter.Value,
               hole.Depth.Value, hole.DepthType, hole.ModelarRoscaManual, hole.PasoRoscaManual.Value,
               hole.LongitudRoscaManual.Value, hole.RoscaManualIzquierda, shape_key(hole.AddSubShape),
               empty_body, tuple(str(getattr(hole, name)) for name in standard_hole_preview.PARAMETERS),
               tuple(option.isChecked() for option in options if isValid(option)))
        if key == signature:
            return
        signature = key
        overlay.removeAllChildren()
        status.clear()
        if (manual or empty_body or custom_thread) and (
                len(options) < 2 or not isValid(options[1]) or options[1].isChecked()):
            try:
                shapes = []
                if empty_body or manual:
                    plain = hole.AddSubShape if not empty_body else Part.Shape()
                    if plain.isNull() or not plain.Solids:
                        plain = (manual_hole_thread.cutter(hole, False) if manual
                                 else standard_hole_preview.cutter(hole))
                    shapes.append(plain)
                if custom_thread:
                    shapes.append(manual_hole_thread.cutter(hole, True))
                placement = hole.getParentGeoFeatureGroup().getGlobalPlacement().toMatrix()
                for shape_index, shape in enumerate(shapes):
                    shape = shape.copy()
                    shape.transformShape(placement, True)
                    node = shape_scene_node(shape, (1.0, 0.1, 0.1), 0.73,
                                            edge_style=((1.0, 0.0, 0.0), 1.0))
                    if node is not None:
                        if custom_thread and shape_index == len(shapes) - 1:
                            depth = coin.SoDepthBuffer()
                            depth.test = False
                            depth.write = False
                            node.insertChild(depth, 0)
                        overlay.addChild(node)
            except (ValueError, RuntimeError, Part.OCCError) as error:
                status.setText(str(error))
        view.redraw()

    timer = QtCore.QTimer(box)
    timer.timeout.connect(redraw)
    timer.start(200)
    for name in ('ThreadType', 'ThreadSize'):
        selector = native_panel.findChild(QtWidgets.QComboBox, name)
        if selector is not None:
            selector.currentIndexChanged.connect(lambda: timer.start(0))
    timer.timeout.connect(lambda: timer.setInterval(200) if timer.interval() == 0 else None)
    box.destroyed.connect(lambda: graph.removeChild(overlay) if graph.findChild(overlay) >= 0 else None)
    return box


def shape_scene_node(shape, color, transparency, deflection=0.1, edge_style=None):
    vertices, triangles = shape.tessellate(deflection)
    if not triangles:
        return None
    node = coin.SoSeparator()
    pick = coin.SoPickStyle()
    pick.style = coin.SoPickStyle.UNPICKABLE
    material = coin.SoMaterial()
    material.diffuseColor = color
    material.transparency = transparency
    coords = coin.SoCoordinate3()
    coords.point.setValues(0, len(vertices), [tuple(vertex) for vertex in vertices])
    mesh = coin.SoIndexedFaceSet()
    indices = [index for triangle in triangles for index in (*triangle, -1)]
    mesh.coordIndex.setValues(0, len(indices), indices)
    for child in (pick, material, coords, mesh):
        node.addChild(child)
    if edge_style is not None:
        line_color, width = edge_style
        points = []
        counts = []
        for edge in shape.Edges:
            if edge.Degenerated:
                continue
            vertices = edge.discretize(Deflection=deflection)
            if len(vertices) >= 2:
                points.extend(tuple(vertex) for vertex in vertices)
                counts.append(len(vertices))
        if counts:
            lighting = coin.SoLightModel()
            lighting.model = coin.SoLightModel.BASE_COLOR
            lines_material = coin.SoMaterial()
            lines_material.diffuseColor = line_color
            lines_material.transparency = transparency
            lines_style = coin.SoDrawStyle()
            lines_style.lineWidth = width
            line_coords = coin.SoCoordinate3()
            line_coords.point.setValues(0, len(points), points)
            lines = coin.SoLineSet()
            lines.numVertices.setValues(0, len(counts), counts)
            for child in (lighting, lines_material, lines_style, line_coords, lines):
                node.addChild(child)
    return node


def shape_key(shape):
    return None if shape.isNull() else shape.hashCode()


class ThreadedHoleEditor:
    def open(self, document, body):
        Gui.Selection.clearSelection()
        document.openTransaction('Crear agujero roscado')
        try:
            profile = independent_pocket.temporary_cut_profile(document, body, hole_origin=True)
            feature = body.newObject('PartDesign::Hole', 'AgujerosYRoscas2')
            feature.Profile = (profile, [])
            feature.Label = THREADED_HOLE_TITLE
            feature.addProperty('App::PropertyString', 'EditorAgujero', '', '', 4)
            feature.EditorAgujero = 'Independiente'
            feature.addProperty('App::PropertyPlacement', HOLE_POSITION, '1. Posición',
                                'Centro de la entrada del agujero, relativo al Cuerpo.')
            manual_hole_thread.add_scope_properties(feature)
            if not Gui.getDocument(document.Name).setEdit(feature.Name):
                raise RuntimeError('FreeCAD no pudo abrir Agujero roscado.')
        except (ValueError, RuntimeError, Part.OCCError) as error:
            document.abortTransaction()
            QtWidgets.QMessageBox.warning(Gui.getMainWindow(), THREADED_HOLE_TITLE, str(error))
            return
        self.configure_native_cut(feature)

    def configure_native_cut(self, feature):
        tasks = Gui.getMainWindow().findChild(QtWidgets.QDockWidget, 'Tasks')
        if tasks is None:
            return
        preview = task_widget(tasks, 'TaskPreviewParameters')
        all_widgets = tasks.findChildren(QtWidgets.QWidget)
        native = [widget for widget in all_widgets
                  if widget.metaObject().className() == 'PartDesignGui::TaskHoleParameters']
        if preview is None:
            preview = next((widget for widget in all_widgets
                            if widget.metaObject().className() == 'PartDesignGui::TaskPreviewParameters'), None)
        first = native[-1] if native else None
        anchor = preview if preview is not None and first is not None and (
            preview.parentWidget() == first.parentWidget()) else first
        if first is None or anchor is None:
            return
        base = feature.BaseFeature
        if base is None or not base.Shape.Solids:
            self.allow_empty_body_confirmation(tasks, anchor, feature)
        if anchor.property('ThreadedHoleEditorInstalled'):
            return
        panel = first.parentWidget()
        layout = panel.layout()
        if layout is None or layout.indexOf(first) < 0 or layout.indexOf(anchor) < 0:
            return

        if feature.Profile:
            feature.Profile[0].ViewObject.hide()
        field = first.findChild(QtWidgets.QLineEdit, 'profileBaseEdit')
        if field is not None and isinstance(field.parentWidget(), QtWidgets.QGroupBox):
            field.parentWidget().hide()
        first.show()
        if preview is not None:
            preview.show()
            options = preview.findChildren(QtWidgets.QCheckBox)
            if len(options) >= 2:
                options[0].setChecked(False)
                options[1].setEnabled(True)
                options[1].setChecked(True)
        describe_hole_choices(first, feature)
        for selector in first.findChildren(QtWidgets.QComboBox):
            choices = [selector.itemText(index).lower() for index in range(selector.count())]
            if any('puntos' in text and 'arcos' in text
                   or 'points' in text and 'arcs' in text for text in choices):
                selector.hide()
                for label in first.findChildren(QtWidgets.QLabel):
                    if (label.buddy() == selector or label.text().strip().rstrip(':').casefold()
                            in {'tipos de perfil base', 'base profile types', 'base profile type'}):
                        label.hide()
                parent_layout = selector.parentWidget().layout()
                if isinstance(parent_layout, QtWidgets.QFormLayout):
                    label = parent_layout.labelForField(selector)
                    if label is not None:
                        label.hide()
        position = hole_position_controls(panel, feature)
        layout.insertWidget(layout.indexOf(first), position)
        thread = manual_thread_controls(panel, feature, preview, first)
        layout.insertWidget(layout.indexOf(first) + 1, thread)
        position.show()
        anchor.setProperty('ThreadedHoleEditorInstalled', True)
        anchor.destroyed.connect(position.deleteLater)
        anchor.destroyed.connect(thread.deleteLater)

    def allow_empty_body_confirmation(self, tasks, anchor, feature):
        if anchor.property('EmptyHoleConfirmationInstalled'):
            return
        boxes = tasks.findChildren(QtWidgets.QDialogButtonBox)
        controls = next((box for box in boxes if (box.isVisibleTo(tasks) or
                         box.parentWidget().metaObject().className() == 'Gui::TaskView::TaskEditControl')
                         and box.button(QtWidgets.QDialogButtonBox.Ok) is not None), None)
        if controls is None:
            return
        ok = controls.button(QtWidgets.QDialogButtonBox.Ok)
        ok.hide()
        save = QtWidgets.QPushButton(ok.text(), controls)
        save.setObjectName('ConfirmEmptyThreadedHole')
        controls.addButton(save, QtWidgets.QDialogButtonBox.ActionRole)
        save.show()
        save.setDefault(True)
        anchor.setProperty('EmptyHoleConfirmationInstalled', True)

        def finish():
            document = feature.Document
            update_hole_position(feature)
            manual_hole_thread.prepare_native_bore(feature)
            # Keep the native parameters editable while there is no material to cut.
            if 'DeferredThreadedHole' not in feature.PropertiesList:
                feature.addProperty('App::PropertyBool', 'DeferredThreadedHole', '', '', 4)
            feature.DeferredThreadedHole = True
            feature.Suppressed = True
            Gui.getDocument(document.Name).resetEdit()
            body = feature.getParentGeoFeatureGroup()
            if body is not None and body.Tip == feature:
                body.Tip = None
            document.recompute()
            document.commitTransaction()

        def restore():
            if isValid(controls) and isValid(save):
                controls.removeButton(save)
                save.deleteLater()
            if isValid(ok):
                ok.show()

        save.clicked.connect(finish)
        anchor.destroyed.connect(restore)

    def refresh(self):
        doc = App.ActiveDocument
        if doc is None or doc.Recomputing:
            return
        if Gui.Control.activeDialog():
            feature = edited_feature()
            if uses_standalone_editor(feature):
                self.configure_native_cut(feature)
            return
        if doc is not None:
            if not Gui.Control.activeDialog():
                holes = [hole for hole in doc.findObjects('PartDesign::Hole') if uses_standalone_editor(hole)]
                for hole in holes:
                    manual_hole_thread.add_scope_properties(hole)
                for body in {hole.getParentGeoFeatureGroup() for hole in holes
                             if independent_pocket.is_deferred_hole(hole)} - {None}:
                    independent_pocket.sync_deferred_holes(body)
                changed = False
                for hole in holes:
                    changed = update_hole_position(hole) or changed
                    body = hole.getParentGeoFeatureGroup()
                    if manual_hole_thread.prepare_native_bore(hole):
                        doc.recompute()
                    if body is not None and manual_hole_thread.needs_result(hole) and hole.Shape.Solids:
                        existing = manual_hole_thread.result_for(hole)
                        result = manual_hole_thread.ensure_result(hole)
                        changed = changed or existing is None
                        if body.Tip == hole:
                            body.Tip = result
                            if not any('MaterialOperations' in item.PropertiesList
                                       or 'PocketDefinition' in item.PropertiesList for item in body.Group):
                                result.Visibility = hole.Visibility
                                hole.Visibility = False
                            changed = True
                for result in doc.findObjects('PartDesign::FeaturePython', '^ManualHoleResult'):
                    if getattr(result, 'ManualHoleResult', False) and result.ManualHoleSource is None:
                        doc.removeObject(result.Name)
                        changed = True
                if changed:
                    doc.recompute()
                # The native delete command makes a consumed profile visible
                # again. Keep generated profiles hidden, including when a
                # deleted hole can still be restored by Undo.
                for sketch in doc.findObjects('Sketcher::SketchObject'):
                    if sketch.Visibility and (getattr(sketch, 'HoleOriginProfile', False)
                                              or getattr(sketch, 'TemporaryCutProfile', False)):
                        sketch.Visibility = False
