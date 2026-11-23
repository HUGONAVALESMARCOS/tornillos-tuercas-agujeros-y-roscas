# SPDX-License-Identifier: MIT

import FreeCAD as App


import FreeCADGui as Gui


import Part


from PySide import QtCore, QtWidgets


from shiboken6 import isValid


def edited_feature():
    gui_document = Gui.activeDocument()
    view = gui_document.getInEdit() if gui_document else None
    return view.Object if view else None


def task_widget(tasks, name):
    return next((widget for widget in tasks.findChildren(QtWidgets.QWidget)
                 if widget.isVisible() and widget.metaObject().className()
                 == 'PartDesignGui::' + name), None)


class AddProfileRow(QtWidgets.QWidget):
    def __init__(self, parent, document, profile, change, body=None, feature=None,
                 label='Perfil', accepts=None, closed_only=True, empty_label=None,
                 pick_hint='Selecciona el perfil en el árbol o en la vista 3D'):
        super().__init__(parent)
        self.document, self.body, self.feature = document, body, feature
        self.change = change
        self.accepts = accepts
        self.closed_only = closed_only
        self.pick_hint = pick_hint
        self.empty_label = empty_label or ('Selecciona un croquis cerrado' if closed_only
                                          else 'Selecciona un perfil')
        self.picking = False
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 0, 8, 0)
        row.addWidget(QtWidgets.QLabel(label, self))
        self.field = QtWidgets.QLineEdit(self)
        self.field.setReadOnly(True)
        row.addWidget(self.field, 1)
        select = QtWidgets.QPushButton('Seleccionar', self)
        select.clicked.connect(self.start_pick)
        row.addWidget(select)
        self.clear = QtWidgets.QPushButton('Borrar', self)
        self.clear.clicked.connect(lambda: self.choose(None))
        row.addWidget(self.clear)
        self.display(profile)

    def display(self, profile):
        self.profile = None if getattr(profile, 'TemporaryCutProfile', False) else profile
        self.field.setText(self.profile.Label if self.profile else '')
        self.field.setPlaceholderText(self.empty_label)
        self.clear.setEnabled(self.profile is not None)

    def start_pick(self):
        if not self.picking:
            Gui.Selection.clearSelection()
            self.picking = True
            Gui.Selection.addObserver(self)
        self.field.setText('')
        self.field.setPlaceholderText(self.pick_hint)

    def stop_pick(self):
        if self.picking:
            self.picking = False
            Gui.Selection.removeObserver(self)

    def choose(self, profile):
        self.stop_pick()
        self.change(profile)
        self.display(profile)

    def addSelection(self, document_name, object_name, subname, point):
        if not self.picking or document_name != self.document.Name:
            return
        for name in reversed([object_name, *subname.rstrip('.').split('.')]):
            candidate = self.document.getObject(name) if name else None
            if candidate and self.accepts_object(candidate):
                QtCore.QTimer.singleShot(0, lambda obj=candidate: self.choose(obj)
                                         if isValid(self) and self.picking else None)
                return

    def accepts_object(self, candidate):
        return (candidate.isDerivedFrom('Sketcher::SketchObject')
                and (self.body is None or candidate.getParentGeoFeatureGroup() == self.body)
                and (self.feature is None or self.feature not in candidate.OutListRecursive)
                and (not self.closed_only or
                     candidate.Shape.Wires and all(wire.isClosed() for wire in candidate.Shape.Wires))
                and (self.accepts is None or self.accepts(candidate)))


def nut_thread_spec(screw):
    from .add_hole import FAMILIES, PositiveHole, thread_pitch
    from .add_screw import Screw

    proxy = getattr(screw, 'Proxy', None)
    if isinstance(proxy, PositiveHole):
        standard = screw.Estandar
        size = screw.Tamano
        diameter = screw.Diametro.Value
        pitch = thread_pitch(standard, size, screw.PasoRosca.Value)
        name = FAMILIES.get(standard, standard)
    elif isinstance(proxy, Screw):
        name, size = screw.Designacion, ''
        diameter, pitch = screw.DiametroVastago.Value, screw.Paso.Value
    else:
        return None
    if diameter <= 0 or pitch <= 0:
        return None
    return name, size, diameter, pitch, screw.RoscaIzquierda


class NutScrewRow(AddProfileRow):
    def accepts_object(self, candidate):
        try:
            return nut_thread_spec(candidate) is not None
        except (AttributeError, KeyError, ValueError):
            return False


class TubeExteriorFields(QtWidgets.QGroupBox):
    changed = QtCore.Signal()

    def __init__(self, parent):
        super().__init__('Rosca exterior', parent)
        from .add_hole import FAMILIES

        self.setCheckable(True)
        self.setChecked(False)
        form = QtWidgets.QFormLayout(self)
        self.standard = QtWidgets.QComboBox(self)
        for key, label in FAMILIES.items():
            self.standard.addItem(label, key)
        self.size = QtWidgets.QComboBox(self)
        self.pitch = parent.length_field(.0001, decimals=4)
        self.pitch.setValue(1)
        self.hand = QtWidgets.QComboBox(self)
        self.hand.addItems(['Derecha', 'Izquierda'])
        self.length = parent.length_field(.001)
        self.length.setValue(self.length.maximum())
        form.addRow('Estándar exterior', self.standard)
        form.addRow('Tamaño exterior', self.size)
        form.addRow('Paso exterior', self.pitch)
        form.addRow('Sentido exterior', self.hand)
        form.addRow('Longitud roscada exterior', self.length)
        profile_note = QtWidgets.QLabel('El tamaño de catálogo propone el paso. La rosca usa el diámetro exterior del tubo y un perfil CAD cilíndrico de 60°.', self)
        profile_note.setWordWrap(True)
        form.addRow(profile_note)
        self.standard.currentIndexChanged.connect(self.update_standard)
        self.size.currentIndexChanged.connect(self.update_size)
        self.toggled.connect(self.changed)
        self.hand.currentIndexChanged.connect(self.changed)
        for field in (self.pitch, self.length):
            field.valueChanged.connect(self.changed)
        self.update_standard()

    def update_standard(self, _index=None):
        from .add_hole import CATALOG

        standard = self.standard.currentData()
        manual = standard == 'None'
        self.layout().setRowVisible(self.size, not manual)
        with QtCore.QSignalBlocker(self.size):
            previous = self.size.currentData()
            self.size.clear()
            for size in CATALOG.get(standard, {}).get('sizes', {}):
                self.size.addItem(size, size)
            self.size.setCurrentIndex(max(0, self.size.findData(previous)))
        self.update_size()

    def update_size(self, _index=None):
        from .add_hole import thread_pitch

        size = self.size.currentData()
        if size:
            self.pitch.setValue(thread_pitch(self.standard.currentData(), size, 0))
        self.changed.emit()

    def settings(self, diameter):
        if not self.isChecked():
            return None
        standard = self.standard.currentData()
        size = self.size.currentData() or ''
        length = self.length.value() if self.length.value() < self.length.maximum() else 0
        return standard, size, diameter, self.pitch.value(), bool(self.hand.currentIndex()), length

    def load_settings(self, settings):
        self.setChecked(settings is not None)
        if settings is not None:
            standard, size, _, pitch, left, length = settings
            self.standard.setCurrentIndex(max(0, self.standard.findData(standard)))
            self.size.setCurrentIndex(max(0, self.size.findData(size)))
            self.pitch.setValue(pitch)
            self.hand.setCurrentIndex(int(left))
            self.length.setValue(length or self.length.maximum())


class HexNutFields(QtWidgets.QWidget):
    # ISO 4032:2023, table 1. Maximum width across flats and height, in mm.
    DIMENSIONS = {
        5: (8, 4.7), 6: (10, 5.2), 7: (11, 6.5), 8: (13, 6.8),
        10: (16, 8.4), 12: (18, 10.8), 14: (21, 12.8), 16: (24, 14.8),
    }
    STANDARD = 'ISOMetricProfile'
    STANDARDS = (STANDARD, 'ISOMetricFineProfile', 'UNC', 'UNF', 'UNEF',
                 'BSW', 'BSF', 'BSP', 'NPT', 'ISOTyre')

    def __init__(self, parent):
        super().__init__(parent)
        from .add_hole import CATALOG, FAMILIES
        from .add_nut import CASTLE, CLOSED, DOMED, NYLON, SLOTTED, SQUARE, TEE, TUBE, WING

        self.catalog_sizes = {key: CATALOG[key]['sizes'] for key in self.STANDARDS}
        self.sizes = {}
        form = QtWidgets.QFormLayout(self)
        self.nut_type = QtWidgets.QComboBox(self)
        for variant in ('Hexagonal normal', 'Hexagonal con brida', CLOSED, DOMED, CASTLE,
                        SLOTTED, NYLON, SQUARE, TUBE, WING, TEE):
            self.nut_type.addItem(variant, variant)
        form.addRow('Tipo de tuerca', self.nut_type)
        self.tube_inner = QtWidgets.QCheckBox('Activar rosca interior', self)
        self.tube_inner.setChecked(True)
        form.addRow(self.tube_inner)
        self.standard = QtWidgets.QComboBox(self)
        for key in self.STANDARDS:
            self.standard.addItem('BSPP (tubería británica cilíndrica)' if key == 'BSP' else FAMILIES[key], key)
        self.standard.addItem(FAMILIES['None'], 'None')
        form.addRow('Estándar de rosca', self.standard)
        self.size = QtWidgets.QComboBox(self)
        self.size_field = QtWidgets.QStackedWidget(self)
        self.size_field.addWidget(self.size)
        self.diameter = self.length_field(0.001)
        self.diameter.setValue(6)
        self.size_field.addWidget(self.diameter)
        self.size_label = QtWidgets.QLabel('Tamaño', self)
        form.addRow(self.size_label, self.size_field)
        self.pitch = self.length_field(0.0001, decimals=4)
        form.addRow('Paso de rosca', self.pitch)
        self.thread_hand = QtWidgets.QComboBox(self)
        self.thread_hand.addItems(['Derecha', 'Izquierda'])
        form.addRow('Sentido de rosca', self.thread_hand)
        self.width = self.length_field(0.001)
        form.addRow('Medida entre caras', self.width)
        self.height = self.length_field(0.001)
        form.addRow('Altura de la tuerca', self.height)
        self.radius = self.length_field(0)
        form.addRow('Radio de redondeo exterior', self.radius)
        self.radius.setToolTip('0 mm conserva las aristas vivas.')
        self.flange_diameter = self.length_field(0.001)
        self.flange_thickness = self.length_field(0.001)
        form.addRow('Diámetro de la brida', self.flange_diameter)
        form.addRow('Espesor de la brida', self.flange_thickness)
        self.cap_height = self.length_field(0.001)
        form.addRow('Espesor de la tapa', self.cap_height)
        self.crown_height = self.length_field(0.001)
        self.slot_width = self.length_field(0.001)
        self.slot_count = QtWidgets.QSpinBox(self)
        self.slot_count.setRange(2, 24)
        self.slot_count.setValue(6)
        form.addRow('Altura de la corona', self.crown_height)
        form.addRow('Ancho de ranura', self.slot_width)
        form.addRow('Número de ranuras', self.slot_count)
        self.insert_height = self.length_field(0.001)
        self.insert_diameter = self.length_field(0.001)
        form.addRow('Altura del inserto', self.insert_height)
        form.addRow('Diámetro interior del inserto', self.insert_diameter)
        self.tube_depth = self.length_field(.001)
        self.tube_depth.setValue(self.tube_depth.maximum())
        form.addRow('Longitud roscada interior', self.tube_depth)
        self.wing_reach = self.length_field(.001)
        self.wing_height = self.length_field(.001)
        self.wing_thickness = self.length_field(.001)
        form.addRow('Saliente de cada orejeta', self.wing_reach)
        form.addRow('Altura de las orejetas', self.wing_height)
        form.addRow('Espesor de las orejetas', self.wing_thickness)
        self.tee_diameter = self.length_field(.001)
        self.tee_thickness = self.length_field(.001)
        self.prong_height = self.length_field(.001)
        self.prong_count = QtWidgets.QSpinBox(self)
        self.prong_count.setRange(2, 12)
        self.prong_count.setValue(4)
        form.addRow('Diámetro de la arandela', self.tee_diameter)
        form.addRow('Espesor de la arandela', self.tee_thickness)
        form.addRow('Altura de las pestañas', self.prong_height)
        form.addRow('Número de pestañas', self.prong_count)
        self.tube_exterior = TubeExteriorFields(self)
        form.addRow(self.tube_exterior)
        self.height.valueChanged.connect(self.update_tube_length_limits)
        self.tube_inner.toggled.connect(self.update_tube_inner)
        self.nut_type.currentIndexChanged.connect(self.update_variant_rows)
        self.width.valueChanged.connect(self.update_cap_limit)
        self.standard.currentIndexChanged.connect(self.update_standard)
        self.size.currentIndexChanged.connect(self.update_catalog_size)
        self.diameter.valueChanged.connect(self.update_dimensions)
        self.select_size(self.STANDARD, 'M6x1.0')
        self.update_variant_rows()

    def update_variant_rows(self):
        from .add_nut import CASTLE, DOMED, NYLON, SLOTTED

        form = self.layout()
        visible = self.nut_type.currentData() == 'Hexagonal con brida'
        form.setRowVisible(self.flange_diameter, visible)
        form.setRowVisible(self.flange_thickness, visible)
        form.setRowVisible(self.cap_height, self.cap_dimensions() is not None)
        for field in (self.crown_height, self.slot_width, self.slot_count):
            form.setRowVisible(field, self.nut_type.currentData() in (CASTLE, SLOTTED))
        for field in (self.insert_height, self.insert_diameter):
            form.setRowVisible(field, self.nut_type.currentData() == NYLON)
        form.labelForField(self.crown_height).setText(
            'Profundidad de ranura' if self.is_slotted() else 'Altura de la corona')
        form.labelForField(self.cap_height).setText(
            'Altura de la cúpula' if self.nut_type.currentData() == DOMED else 'Espesor de la tapa')
        form.labelForField(self.height).setText(
            'Altura del cuerpo hexagonal' if self.nut_type.currentData() in (DOMED, CASTLE, NYLON)
            else 'Altura de la tuerca')
        tube = self.tube_thread_depth() is not None
        form.setRowVisible(self.tube_depth, tube)
        form.setRowVisible(self.tube_inner, tube)
        form.setRowVisible(self.tube_exterior, self.has_tube_exterior())
        for field in (self.wing_reach, self.wing_height, self.wing_thickness):
            form.setRowVisible(field, self.wing_dimensions() is not None)
        for field in (self.tee_diameter, self.tee_thickness, self.prong_height, self.prong_count):
            form.setRowVisible(field, self.tee_dimensions() is not None)
        self.update_tube_inner()
        form.labelForField(self.standard).setText('Estándar interior' if tube else 'Estándar de rosca')
        form.labelForField(self.pitch).setText('Paso interior' if tube else 'Paso de rosca')
        form.labelForField(self.thread_hand).setText('Sentido interior' if tube else 'Sentido de rosca')
        self.update_size_label()
        if tube:
            form.labelForField(self.height).setText('Longitud del tubo')
        form.labelForField(self.width).setText(
            'Diámetro exterior' if tube else 'Lado del cuadrado' if self.is_square() else 'Medida entre caras')
        self.update_cap_limit()
        self.set_default_cap_height()

    def update_tube_inner(self):
        enabled = self.tube_thread_depth() is None or self.tube_inner.isChecked()
        for field in (self.pitch, self.thread_hand, self.tube_depth):
            field.setEnabled(enabled)

    def update_size_label(self):
        manual = self.standard.currentData() == 'None'
        tube = self.tube_thread_depth() is not None
        if manual:
            title = 'Diámetro interior nominal' if tube else 'Diámetro nominal'
        else:
            title = 'Tamaño interior' if tube else 'Tamaño'
        self.size_label.setText(title)

    def update_cap_limit(self):
        from .add_nut import DOMED

        self.cap_height.setMaximum(self.width.value() if self.nut_type.currentData() == DOMED else 10000)

    def set_default_cap_height(self):
        from .add_nut import DOMED

        height = (self.width.value() if self.nut_type.currentData() == DOMED
                  else min(0.25 * self.height.value(), 0.4 * self.width.value()))
        self.cap_height.setValue(height)

    def flange_dimensions(self):
        if self.nut_type.currentData() == 'Hexagonal con brida':
            return self.flange_diameter.value(), self.flange_thickness.value()
        return None

    def cap_dimensions(self):
        from .add_nut import CLOSED, DOMED

        variant = self.nut_type.currentData()
        if variant in (CLOSED, DOMED):
            return variant, self.cap_height.value()
        return None

    def crown_dimensions(self):
        from .add_nut import CASTLE

        if self.nut_type.currentData() == CASTLE or self.is_slotted():
            return self.crown_height.value(), self.slot_width.value(), self.slot_count.value()
        return None

    def is_slotted(self):
        from .add_nut import SLOTTED

        return self.nut_type.currentData() == SLOTTED

    def is_square(self):
        from .add_nut import SQUARE

        return self.nut_type.currentData() == SQUARE

    def tube_thread_depth(self):
        from .add_nut import TEE, TUBE, WING

        if self.nut_type.currentData() not in (TUBE, WING, TEE):
            return None
        return self.tube_depth.value() if self.tube_depth.value() < self.tube_depth.maximum() else 0

    def has_tube_exterior(self):
        from .add_nut import TUBE

        return self.nut_type.currentData() == TUBE

    def tee_dimensions(self):
        from .add_nut import TEE

        if self.nut_type.currentData() == TEE:
            return (self.tee_diameter.value(), self.tee_thickness.value(),
                    self.prong_height.value(), self.prong_count.value())
        return None

    def wing_dimensions(self):
        from .add_nut import WING

        if self.nut_type.currentData() == WING:
            return self.wing_reach.value(), self.wing_height.value(), self.wing_thickness.value()
        return None

    def update_tube_length_limits(self, length):
        for field in (self.tube_depth, self.tube_exterior.length):
            full = field.value() == field.maximum()
            field.setMaximum(length)
            if full:
                field.setValue(length)

    def insert_dimensions(self):
        from .add_nut import NYLON

        if self.nut_type.currentData() == NYLON:
            return self.insert_height.value(), self.insert_diameter.value()
        return None

    def length_field(self, minimum, decimals=3):
        field = QtWidgets.QDoubleSpinBox(self)
        field.setDecimals(decimals)
        field.setRange(minimum, 10000)
        field.setSuffix(' mm')
        return field

    def select_size(self, standard, size):
        if size not in self.catalog_sizes.get(standard, {}):
            return False
        with QtCore.QSignalBlocker(self.standard):
            self.standard.setCurrentIndex(self.standard.findData(standard))
        self.update_standard(size)
        return True

    def select_manual(self, diameter, pitch):
        with QtCore.QSignalBlocker(self.standard), QtCore.QSignalBlocker(self.diameter):
            self.standard.setCurrentIndex(self.standard.findData('None'))
            self.diameter.setValue(diameter)
        self.pitch.setValue(pitch)
        self.update_standard()

    def update_standard(self, size=None):
        manual = self.standard.currentData() == 'None'
        self.size_field.setCurrentIndex(int(manual))
        self.update_size_label()
        if manual:
            self.update_dimensions()
        else:
            previous = self.size.currentData()
            diameter = self.sizes[previous][0] if previous in self.sizes else self.diameter.value()
            self.sizes = self.catalog_sizes[self.standard.currentData()]
            if size not in self.sizes:
                size = previous if previous in self.sizes else next(
                    (key for key, row in self.sizes.items() if row[0] == diameter), None)
            with QtCore.QSignalBlocker(self.size):
                self.size.clear()
                for key in self.sizes:
                    self.size.addItem(key, key)
                self.size.setCurrentIndex(max(0, self.size.findData(size)))
            self.update_catalog_size()

    def update_catalog_size(self):
        from .add_hole import thread_pitch

        self.pitch.setValue(thread_pitch(self.standard.currentData(), self.size.currentData(), 0))
        self.update_dimensions()

    def update_dimensions(self):
        from .add_hole import ISO_HEX_DIMENSIONS

        diameter = self.nominal_diameter()
        standard = self.standard.currentData()
        dimensions = self.DIMENSIONS.get(diameter)
        if standard == 'NPT':
            dimensions = 1.6 * diameter, 6 * self.pitch.value()
        elif standard in ('UNC', 'UNF', 'UNEF', 'BSW', 'BSF', 'BSP', 'ISOTyre'):
            dimensions = 1.6 * diameter, 0.8 * diameter
        elif dimensions is None:
            width = ISO_HEX_DIMENSIONS.get(diameter, (1.6 * diameter,))[0]
            dimensions = width, 0.8 * diameter
        note = 'Cota exterior orientativa según el diámetro nominal, editable.'
        if standard in (self.STANDARD, 'None') and diameter in self.DIMENSIONS:
            note = 'Cota inicial de ISO 4032:2023, editable.'
        for field, value in zip((self.width, self.height), dimensions):
            field.setValue(value)
            field.setToolTip(note)
        self.flange_diameter.setValue(1.25 * self.width.value())
        self.flange_thickness.setValue(0.2 * self.height.value())
        self.crown_height.setValue(0.35 * self.height.value())
        self.slot_width.setValue(min(0.25 * diameter, self.pitch.value()))
        self.insert_height.setValue(0.25 * self.height.value())
        self.insert_diameter.setValue(0.9 * diameter)
        self.wing_reach.setValue(0.65 * self.width.value())
        self.wing_height.setValue(1.2 * self.height.value())
        self.wing_thickness.setValue(0.25 * self.width.value())
        self.tee_diameter.setValue(1.8 * self.width.value())
        self.tee_thickness.setValue(0.18 * self.height.value())
        self.prong_height.setValue(0.45 * self.height.value())
        self.set_default_cap_height()

    def nominal_diameter(self):
        if self.standard.currentData() == 'None':
            return self.diameter.value()
        return self.sizes[self.size.currentData()][0]


class PlacementFields(QtWidgets.QWidget):
    def __init__(self, parent, position_title, angle_title, changed):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.original_base = None
        self.original_rotation = None
        self.coordinates = self.axis_fields(layout, position_title, 1000000, ' mm')
        self.angles = self.axis_fields(layout, angle_title, 360, '°')
        for field in self.coordinates:
            field.valueChanged.connect(self.clear_original_base)
        for field in self.angles:
            field.valueChanged.connect(self.clear_original_rotation)
        for field in (*self.coordinates, *self.angles):
            field.valueChanged.connect(changed)

    def axis_fields(self, layout, title, limit, suffix):
        box = QtWidgets.QGroupBox(title, self)
        row = QtWidgets.QHBoxLayout(box)
        fields = []
        for axis in 'XYZ':
            field = QtWidgets.QDoubleSpinBox(box)
            field.setRange(-limit, limit)
            field.setDecimals(3)
            field.setSuffix(suffix)
            label = QtWidgets.QLabel(axis, box)
            label.setBuddy(field)
            row.addWidget(label)
            row.addWidget(field)
            fields.append(field)
        layout.addWidget(box)
        return fields

    def clear_original_rotation(self):
        self.original_rotation = None

    def clear_original_base(self):
        self.original_base = None

    def placement(self):
        rotation = self.original_rotation
        if rotation is None:
            x, y, z = (field.value() for field in self.angles)
            rotation = App.Rotation(z, y, x)
        base = self.original_base
        if base is None:
            base = App.Vector(*(field.value() for field in self.coordinates))
        return App.Placement(base, rotation)

    def load_placement(self, pose):
        for field, value in zip(self.coordinates, pose.Base):
            with QtCore.QSignalBlocker(field):
                field.setValue(value)
        for field, angle in zip(self.angles, reversed(pose.Rotation.getYawPitchRoll())):
            with QtCore.QSignalBlocker(field):
                field.setValue(angle)
        self.original_base = pose.Base
        self.original_rotation = pose.Rotation


class NutPanel:
    def __init__(self, document, body, feature=None):
        self.document = document
        self.nut_body = body.Name
        self.nut_feature = feature
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle('Tuerca')
        layout = QtWidgets.QVBoxLayout(self.form)
        self.nut_form = QtWidgets.QWidget(self.form)
        nut_layout = QtWidgets.QVBoxLayout(self.nut_form)
        self.nut_draft = None
        self.nut_transaction = False
        self.nut_cache = None
        self.nut_scene = None
        self.nut_timer = QtCore.QTimer(self.nut_form)
        self.nut_timer.setSingleShot(True)
        self.nut_timer.timeout.connect(self.refresh_nut_preview)
        self.nut_position = PlacementFields(self.nut_form, 'Posición de la tuerca',
                                            'Ángulo de la tuerca', self.schedule_nut_preview)
        nut_layout.addWidget(self.nut_position)
        self.nut_screw = NutScrewRow(self.nut_form, document, None, self.update_nut_thread,
                                    label='Tornillo', empty_label='Selecciona un tornillo',
                                    pick_hint='Selecciona un tornillo en el árbol')
        nut_layout.addWidget(self.nut_screw)
        self.nut_thread = QtWidgets.QLabel(self.nut_form)
        self.nut_thread.setWordWrap(True)
        nut_layout.addWidget(self.nut_thread)
        self.hex_nut = HexNutFields(self.nut_form)
        nut_layout.addWidget(self.hex_nut)
        self.nut_error = QtWidgets.QLabel(self.nut_form)
        self.nut_error.setWordWrap(True)
        self.nut_error.hide()
        nut_layout.addWidget(self.nut_error)
        preview_box = QtWidgets.QGroupBox('Pre-visualizar', self.nut_form)
        preview_layout = QtWidgets.QVBoxLayout(preview_box)
        self.nut_final = QtWidgets.QCheckBox('Mostrar resultado final', preview_box)
        self.nut_overlay = QtWidgets.QCheckBox('Mostrar vista previa', preview_box)
        self.nut_overlay.setChecked(True)
        for option in (self.nut_final, self.nut_overlay):
            preview_layout.addWidget(option)
            option.toggled.connect(self.schedule_nut_preview)
        self.nut_overlay.setToolTip('Muestra la tuerca en verde translúcido. El resultado final tiene prioridad.')
        nut_layout.addWidget(preview_box)
        for field in (self.hex_nut.diameter, self.hex_nut.pitch, self.hex_nut.width,
                      self.hex_nut.height, self.hex_nut.radius, self.hex_nut.flange_diameter,
                      self.hex_nut.flange_thickness, self.hex_nut.cap_height,
                      self.hex_nut.crown_height, self.hex_nut.slot_width, self.hex_nut.slot_count,
                      self.hex_nut.insert_height, self.hex_nut.insert_diameter, self.hex_nut.tube_depth,
                      self.hex_nut.wing_reach, self.hex_nut.wing_height, self.hex_nut.wing_thickness,
                      self.hex_nut.tee_diameter, self.hex_nut.tee_thickness, self.hex_nut.prong_height,
                      self.hex_nut.prong_count):
            field.valueChanged.connect(self.schedule_nut_preview)
        self.hex_nut.size.currentIndexChanged.connect(self.schedule_nut_preview)
        self.hex_nut.standard.currentIndexChanged.connect(self.schedule_nut_preview)
        self.hex_nut.thread_hand.currentIndexChanged.connect(self.schedule_nut_preview)
        self.hex_nut.nut_type.currentIndexChanged.connect(self.schedule_nut_preview)
        self.hex_nut.tube_inner.toggled.connect(self.schedule_nut_preview)
        self.hex_nut.tube_exterior.changed.connect(self.schedule_nut_preview)
        layout.addWidget(self.nut_form)
        self.update_nut_thread(None)
        if feature is not None:
            self.load_nut_edit(feature)
        else:
            self.refresh_nut_preview()

    def accept(self):
        return self.accept_nut()

    def reject(self):
        if self.nut_feature is not None:
            Gui.getDocument(self.document.Name).resetEdit()
        else:
            self.nut_screw.stop_pick()
            self.nut_timer.stop()
            self.discard_nut_draft()
        return True

    def load_nut_edit(self, feature):
        fields = self.hex_nut
        if not fields.select_size(feature.Estandar, feature.Tamano):
            fields.select_manual(feature.DiametroNominal.Value, feature.PasoRosca.Value)
        fields.pitch.setValue(feature.PasoRosca.Value)
        fields.thread_hand.setCurrentIndex(int(feature.RoscaIzquierda))
        fields.width.setValue(feature.MedidaEntreCaras.Value)
        fields.height.setValue(feature.AlturaTuerca.Value)
        fields.radius.setValue(feature.RadioRedondeo.Value)
        variant = getattr(feature, 'TipoTuerca', 'Hexagonal normal')
        if variant == 'Hexagonal con brida':
            fields.flange_diameter.setValue(feature.DiametroBrida.Value)
            fields.flange_thickness.setValue(feature.EspesorBrida.Value)
        fields.nut_type.setCurrentIndex(max(0, fields.nut_type.findData(variant)))
        if fields.wing_dimensions() is not None:
            fields.wing_reach.setValue(feature.SalienteOrejetas.Value)
            fields.wing_height.setValue(feature.AlturaOrejetas.Value)
            fields.wing_thickness.setValue(feature.EspesorOrejetas.Value)
        if fields.tee_dimensions() is not None:
            fields.tee_diameter.setValue(feature.DiametroArandela.Value)
            fields.tee_thickness.setValue(feature.EspesorArandela.Value)
            fields.prong_height.setValue(feature.AlturaPestanas.Value)
            fields.prong_count.setValue(feature.NumeroPestanas)
        if fields.tube_thread_depth() is not None:
            from .add_nut import tube_external_settings

            fields.tube_depth.setValue(feature.LongitudRoscada.Value or fields.height.value())
            fields.tube_inner.setChecked(getattr(feature, 'RoscaInteriorActiva', True))
            if fields.has_tube_exterior():
                fields.tube_exterior.load_settings(tube_external_settings(feature))
        if fields.insert_dimensions() is not None:
            fields.insert_height.setValue(feature.AlturaInserto.Value)
            fields.insert_diameter.setValue(feature.DiametroInteriorInserto.Value)
        if fields.crown_dimensions() is not None:
            depth = feature.ProfundidadRanura if fields.is_slotted() else feature.AlturaCorona
            fields.crown_height.setValue(depth.Value)
            fields.slot_width.setValue(feature.AnchoRanura.Value)
            fields.slot_count.setValue(feature.NumeroRanuras)
        if fields.cap_dimensions() is not None:
            fields.cap_height.setValue(feature.AlturaTapa.Value)
            from .add_nut import DOMED

            if variant == DOMED and not getattr(feature, 'AlturaHexagonalIndependiente', False):
                fields.height.setValue(feature.AlturaTuerca.Value - feature.AlturaTapa.Value)
        self.nut_position.load_placement(getattr(feature, 'PosicionTuerca', feature.Placement))
        self.nut_saved_visibility = feature.Visibility
        feature.Visibility = False

    def finish_nut_edit(self):
        self.nut_timer.stop()
        self.nut_screw.stop_pick()
        self.clear_nut_scene()
        self.nut_feature.Visibility = self.nut_saved_visibility

    def update_nut_thread(self, screw):
        spec = nut_thread_spec(screw)
        if spec is None:
            self.nut_thread.setText('Selecciona un tornillo del árbol para leer su rosca.')
            self.schedule_nut_preview()
            return
        standard, size, diameter, pitch, left = spec
        self.hex_nut.thread_hand.setCurrentIndex(int(left))
        locale = QtCore.QLocale()
        direction = 'Izquierda' if left else 'Derecha'
        summary = (
            f'{standard} {size} · Ø {locale.toString(diameter, "g", 8)} mm · '
            f'Paso {locale.toString(pitch, "g", 8)} mm · {direction}')
        source_standard = getattr(screw, 'Estandar', 'None')
        if source_standard == 'None':
            self.hex_nut.select_manual(diameter, pitch)
        elif not self.hex_nut.select_size(source_standard, size):
            summary += '\nEste estándar del tornillo aún no está disponible en Tuerca.'
        elif source_standard in ('BSW', 'BSF', 'BSP'):
            summary += '\nTuerca usa perfil Whitworth de 55°. Tornillo modela esta serie con perfil de 60°.'
        elif source_standard == 'NPT':
            summary += '\nTuerca usa una rosca cónica 1:16. Tornillo modela esta serie como cilíndrica.'
        self.nut_thread.setText(summary)
        self.schedule_nut_preview()

    def schedule_nut_preview(self):
        self.nut_timer.start(45)

    def discard_nut_draft(self):
        self.clear_nut_scene()
        if self.nut_draft is None:
            return
        nut_name, previous_tip = self.nut_draft
        self.nut_draft = None
        if self.nut_transaction:
            self.document.abortTransaction()
            self.nut_transaction = False
        if self.document.getObject(nut_name) is not None:
            self.document.removeObject(nut_name)
        body = self.document.getObject(self.nut_body) if self.nut_body else None
        if body is not None and body.Tip is None and previous_tip:
            body.Tip = self.document.getObject(previous_tip)
        self.document.recompute()

    def clear_nut_scene(self):
        if self.nut_scene is not None:
            root, node = self.nut_scene
            root.removeChild(node)
            self.nut_scene = None

    def show_nut_scene(self, shape, pitch):
        from .remove_material_visual import shape_scene_node

        final = self.nut_final.isChecked()
        if not (final or self.nut_overlay.isChecked()):
            return
        color, transparency = ((0.78, 0.80, 0.83), 0.0) if final else ((0.25, 0.85, 0.45), 0.20)
        node = shape_scene_node(shape, color, transparency, min(0.1, pitch / 16))
        view = Gui.getDocument(self.document.Name).activeView()
        if node is not None and view is not None:
            root = view.getSceneGraph()
            root.addChild(node)
            self.nut_scene = root, node

    def refresh_nut_preview(self, show_scene=True):
        from .add_nut import NutView, hex_nut_shape

        self.clear_nut_scene()
        self.nut_error.hide()
        if App.ActiveDocument != self.document:
            return None
        screw = self.nut_screw.profile
        standard = getattr(screw, 'Estandar', 'None')
        if standard not in ('None', *self.hex_nut.STANDARDS):
            return None
        fields = self.hex_nut
        pitch, height = fields.pitch.value(), fields.height.value()
        left = bool(fields.thread_hand.currentIndex())
        key = (fields.nominal_diameter(), pitch, fields.width.value(), height,
               fields.radius.value(), left, fields.standard.currentData(), fields.size.currentData(),
               fields.flange_dimensions(), fields.cap_dimensions(), fields.crown_dimensions(),
               fields.is_slotted(), fields.insert_dimensions(), fields.is_square(), fields.tube_thread_depth(),
               fields.tube_inner.isChecked(),
               fields.tube_exterior.settings(fields.width.value())
               if fields.has_tube_exterior() else None,
               fields.wing_dimensions(), fields.tee_dimensions())
        try:
            if self.nut_cache is None or self.nut_cache[0] != key:
                self.nut_cache = (key, hex_nut_shape(*key))
            shape = self.nut_cache[1].copy()
            body = self.document.getObject(self.nut_body) if self.nut_body else None
            if body is None:
                raise ValueError('Activa un Cuerpo para añadir la tuerca.')
            shape.Placement = self.nut_position.placement()
            if self.nut_feature is not None:
                if show_scene:
                    shape.Placement = body.getGlobalPlacement().multiply(shape.Placement)
                    self.show_nut_scene(shape, pitch)
                return self.nut_feature
            new_draft = self.nut_draft is None
            if new_draft:
                self.document.openTransaction('Añadir tuerca')
                self.nut_transaction = True
                previous_tip = body.Tip
                nut = body.newObject('PartDesign::FeatureAdditivePython', 'Tuerca2')
                nut.Label = 'Tuerca'
                self.nut_draft = nut.Name, previous_tip.Name if previous_tip else None
                nut.BaseFeature = None
                body.Group = [item for item in body.Group if item != nut] + [nut]
                body.Tip = previous_tip
                NutView(nut.ViewObject)
                nut.ViewObject.ShapeColor = (0.25, 0.85, 0.45)
                nut.ViewObject.Transparency = 20
            else:
                nut = self.document.getObject(self.nut_draft[0])
            nut.Shape = shape.copy()
            self.document.recompute()
            nut.Visibility = False
            if new_draft:
                Gui.getDocument(self.document.Name).toggleTreeItem(body, 2)
            if show_scene:
                shape.Placement = body.getGlobalPlacement().multiply(shape.Placement)
                self.show_nut_scene(shape, pitch)
            return nut
        except (ValueError, RuntimeError, Part.OCCError) as error:
            self.nut_error.setText(str(error))
            self.nut_error.show()
            return None

    def accept_nut(self):
        from .add_nut import HexNut
        from .independent_pocket import is_deferred_hole, keep_independent_material

        self.nut_screw.stop_pick()
        self.nut_timer.stop()
        nut = self.refresh_nut_preview(show_scene=False)
        if nut is None:
            return False
        editing = self.nut_feature is not None
        try:
            fields = self.hex_nut
            standard = fields.standard.currentData()
            size = fields.size.currentData() if standard != 'None' else ''
            if editing:
                self.document.openTransaction('Editar tuerca')
                HexNut.configure(nut, self.nut_cache[0][:6], standard, size, *self.nut_cache[0][8:])
                nut.PosicionTuerca = self.nut_position.placement()
                nut.touch()
                self.document.recompute()
                if 'Invalid' in nut.State or nut.Shape.isNull():
                    raise ValueError('FreeCAD no pudo confirmar la tuerca.')
                self.document.commitTransaction()
                Gui.getDocument(self.document.Name).resetEdit()
                return True
            HexNut(nut, self.nut_cache[0][:6], standard, size, *self.nut_cache[0][8:])
            nut.PosicionTuerca = self.nut_position.placement()
            body = nut.getParentGeoFeatureGroup()
            steps = [item for item in body.Group
                     if item.isDerivedFrom('PartDesign::Feature') and 'BaseFeature' in item.PropertiesList]
            cuts = [item for item in steps if 'PocketDefinition' in item.PropertiesList]
            if not keep_independent_material(body, steps, cuts):
                raise ValueError('El Cuerpo contiene operaciones que requieren una cadena de dependencias.')
            nut.ViewObject.ShapeColor = (0.78, 0.80, 0.83)
            nut.ViewObject.Transparency = 0
            self.document.recompute()
            if 'Invalid' in nut.State or nut.Shape.isNull():
                raise ValueError('FreeCAD no pudo confirmar la tuerca.')
            nut.Visibility = not any(is_deferred_hole(item) for item in steps)
            self.document.commitTransaction()
            self.nut_transaction = False
            self.nut_draft = None
            return True
        except (ValueError, RuntimeError, Part.OCCError) as error:
            if editing:
                self.document.abortTransaction()
            else:
                self.discard_nut_draft()
            self.nut_error.setText(str(error))
            self.nut_error.show()
            return False
