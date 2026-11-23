# SPDX-License-Identifier: MIT
"""Parametric external screw for the AÑADIR task panel."""

import math
from pathlib import Path

import FreeCAD as App
import Part


# M8 × 1.25–6g, at the maximum-material limit for the threaded portion.
# ISO 965-2 controls the major and pitch diameters. Use the ISO design
# profile with a fully rounded root (ISO 68-1).
DESIGNATION = "M8 × 1,25–6g"
NOMINAL = 8.0
PITCH = 1.25
MAJOR = 7.972
PITCH_DIAMETER = 7.160


def external_thread_groove(pitch, threaded_length, major_radius, left_handed,
                           taper_angle=0, pitch_radius=None):
    """Sweep the groove past both ends for clipping by the caller."""
    z = -pitch
    slope = math.sqrt(3)
    root_radius = pitch / (4 * slope)
    taper = math.tan(math.radians(taper_angle))
    helix_radius = major_radius + taper * z
    if pitch_radius is None:
        pitch_radius = helix_radius - 3 * slope * pitch / 16
    apex = pitch_radius - slope * pitch / 4
    if apex + root_radius <= 0:
        raise ValueError("El paso o la conicidad son excesivos para el diámetro elegido.")
    tangent_radius = apex + 1.5 * root_radius
    half_tangent = slope * root_radius / 2
    outside = helix_radius + min(0.1, pitch / 12) + abs(taper) * pitch
    half_outside = (outside - apex) / slope
    lower = App.Vector(outside, 0, z - half_outside)
    upper = App.Vector(outside, 0, z + half_outside)
    tangent_low = App.Vector(tangent_radius, 0, z - half_tangent)
    tangent_high = App.Vector(tangent_radius, 0, z + half_tangent)
    root = App.Vector(apex + root_radius, 0, z)
    profile = Part.Wire([
        Part.makeLine(lower, tangent_low),
        Part.Arc(tangent_low, root, tangent_high).toShape(),
        Part.makeLine(tangent_high, upper),
        Part.makeLine(upper, lower),
    ])
    helix = Part.makeHelix(pitch, threaded_length + 2 * pitch,
                          helix_radius, taper_angle, left_handed)
    helix.translate(App.Vector(0, 0, z))
    groove = helix.makePipeShell([profile], True, True)
    return groove


def screw_shape(length, threaded_length, head, head_diameter, head_height,
                left_handed=False, model_thread=True, nominal=NOMINAL,
                pitch=PITCH, tip_angle=0, include_tip=False, reverse=False,
                taper_angle=0, custom=False):
    if length <= 0 or (model_thread and not 0 <= threaded_length <= length):
        raise ValueError("La longitud roscada debe estar entre cero y la longitud del vástago.")
    if not 0 <= tip_angle < 180 or not 0 <= taper_angle < 90:
        raise ValueError("Comprueba los ángulos de la punta y del vástago.")
    if nominal <= 0 or pitch <= 0:
        raise ValueError("El diámetro y el paso deben ser positivos.")
    if head != "Sin cabeza" and (head_diameter <= nominal or head_height <= 0):
        raise ValueError("La cabeza debe ser más ancha que el vástago y tener altura positiva.")

    taper = math.tan(math.radians(taper_angle))
    radius = nominal / 2
    tip_radius = radius - taper * length
    tip_length = tip_radius / math.tan(math.radians(tip_angle / 2)) if tip_angle else 0
    if tip_radius <= 0 or (include_tip and tip_length >= length):
        raise ValueError("La conicidad o la punta consumen el vástago.")

    def segment(start_radius, height, z=0):
        base = App.Vector(0, 0, z)
        return (Part.makeCone(start_radius, start_radius + taper * height, height, base)
                if taper else Part.makeCylinder(start_radius, height, base))

    shaft = segment(tip_radius, length)
    if model_thread and threaded_length:
        standard = not custom and nominal == NOMINAL and pitch == PITCH and not taper
        major_offset = (NOMINAL - MAJOR) / 2 if standard else 0
        major_radius = tip_radius - major_offset
        shaft = segment(major_radius, threaded_length)
        if length > threaded_length:
            shaft = shaft.fuse(segment(tip_radius + taper * threaded_length,
                                      length - threaded_length, threaded_length))

        groove = external_thread_groove(
            pitch, threaded_length, major_radius, left_handed, taper_angle,
            PITCH_DIAMETER / 2 if standard else None,
        )
        limit = Part.makeCylinder(radius + abs(taper) * length + pitch, threaded_length)
        shaft = shaft.cut(groove.common(limit))

    if tip_length:
        if include_tip:
            # Remove the part outside the point envelope, keeping the
            # selected head-to-tip length.
            envelope_radius = radius + 0.1
            end = envelope_radius / math.tan(math.radians(tip_angle / 2))
            envelope = Part.makeCone(0, envelope_radius, end)
            if end < length:
                envelope = envelope.fuse(Part.makeCylinder(
                    envelope_radius, length - end, App.Vector(0, 0, end)))
            shaft = shaft.common(envelope)
        else:
            point_base = (major_radius if model_thread and threaded_length else tip_radius)
            point_length = point_base / math.tan(math.radians(tip_angle / 2))
            point = Part.makeCone(0, point_base, point_length, App.Vector(0, 0, -point_length))
            shaft = shaft.fuse(point)

    position = App.Vector(0, 0, length)
    if head == "Sin cabeza":
        result = shaft.removeSplitter()
    elif head == "Avellanada":
        cap = Part.makeCone(radius, head_diameter / 2, head_height, position)
        result = shaft.fuse(cap).removeSplitter()
    else:
        cap = Part.makeCylinder(head_diameter / 2, head_height, position)
        result = shaft.fuse(cap).removeSplitter()
    if reverse:
        rotation = App.Rotation(App.Vector(1, 0, 0), 180)
        result = result.transformGeometry(rotation.toMatrix())
    if len(result.Solids) != 1 or not result.isValid():
        raise ValueError("No se pudo construir un tornillo válido con esas cotas.")
    return result


def additive_result(addition, base):
    if base is None or base.Shape.isNull():
        return addition
    result = base.Shape.fuse(addition).removeSplitter()
    if len(result.Solids) != 1 or not result.isValid():
        raise ValueError("El tornillo debe unir material al sólido del Cuerpo.")
    return result


def positioned_screw(addition, profile, body):
    if profile is None or profile.Shape.isNull():
        return addition
    sketch_shape = profile.Shape.copy()
    sketch_shape.Placement = App.Placement()
    center = sketch_shape.BoundBox.Center
    center.z = 0
    placement = profile.getGlobalPlacement()
    placement.Base = placement.multVec(center)
    if body is not None:
        placement = body.getGlobalPlacement().inverse().multiply(placement)
    return addition.transformGeometry(placement.toMatrix())


class Screw:
    def __init__(self, feature, length, threaded_length, head, diameter, height, left, modeled,
                 nominal=NOMINAL, pitch=PITCH, tip_angle=0, include_tip=False,
                 reverse=False, taper_angle=0, custom=False):
        self.configure(feature, length, threaded_length, head, diameter, height, left, modeled,
                       nominal, pitch, tip_angle, include_tip, reverse, taper_angle, custom)
        feature.Proxy = self

    @staticmethod
    def configure(feature, length, threaded_length, head, diameter, height, left, modeled,
                  nominal, pitch, tip_angle, include_tip, reverse, taper_angle, custom):
        def ensure_property(kind, name, group):
            if name not in feature.PropertiesList:
                feature.addProperty("App::Property" + kind, name, group)

        for name, value in (
            ("Longitud", length), ("LongitudRoscada", threaded_length),
            ("DiametroCabeza", diameter), ("AlturaCabeza", height),
            ("DiametroVastago", nominal), ("Paso", pitch),
        ):
            ensure_property("Length", name, "Tornillo")
            setattr(feature, name, value)
        if "Cabeza" not in feature.PropertiesList:
            feature.addProperty("App::PropertyEnumeration", "Cabeza", "Tornillo")
        if "Sin cabeza" not in feature.getEnumerationsOfProperty("Cabeza"):
            feature.Cabeza = ["Cilíndrica", "Avellanada", "Sin cabeza"]
        feature.Cabeza = head
        for name, value in (
            ("RoscaIzquierda", left), ("ModelarRosca", modeled),
            ("IncluirPunta", include_tip), ("InvertirDireccion", reverse),
        ):
            ensure_property("Bool", name, "Rosca")
            setattr(feature, name, value)
        ensure_property("String", "Designacion", "Rosca")
        feature.Designacion = "Personalizada" if custom or taper_angle else DESIGNATION
        feature.setEditorMode("Designacion", 1)
        for name, value in (("AnguloPunta", tip_angle), ("Conicidad", taper_angle)):
            ensure_property("Angle", name, "Tornillo")
            setattr(feature, name, value)
        feature.setEditorMode("DiametroVastago", 0 if custom else 1)
        feature.setEditorMode("Paso", 0 if custom else 1)
        ensure_property("String", "HerramientaOrigen", "Tornillo")
        feature.HerramientaOrigen = "Añadir"
        feature.setEditorMode("HerramientaOrigen", 2)

    @staticmethod
    def dimensions(feature):
        def quantity(name, default):
            value = getattr(feature, name, None)
            return default if value is None else value.Value

        return (
            feature.Longitud.Value, feature.LongitudRoscada.Value, feature.Cabeza,
            feature.DiametroCabeza.Value, feature.AlturaCabeza.Value,
            feature.RoscaIzquierda, feature.ModelarRosca,
            quantity("DiametroVastago", NOMINAL), quantity("Paso", PITCH),
            quantity("AnguloPunta", 0), getattr(feature, "IncluirPunta", False),
            getattr(feature, "InvertirDireccion", False), quantity("Conicidad", 0),
            feature.Designacion == "Personalizada",
        )

    def execute(self, feature):
        pending = self.__dict__.pop("pending_shapes", None)
        if pending is None:
            addition = screw_shape(*self.dimensions(feature))
            addition = positioned_screw(addition, getattr(feature, "PerfilTornillo", None),
                                        feature.getParentGeoFeatureGroup())
            result = additive_result(addition, feature.BaseFeature) if hasattr(feature, "AddSubShape") else addition
        else:
            addition, result = pending
        if hasattr(feature, "AddSubShape"):
            feature.AddSubShape = addition
        feature.Shape = result

    def onDocumentRestored(self, feature):
        if App.GuiUp and feature.ViewObject and feature.ViewObject.Proxy is None:
            ScrewView(feature.ViewObject)

    def dumps(self):
        return None

    def loads(self, _state):
        pass


class ScrewView:
    def __init__(self, view):
        view.Proxy = self

    def getIcon(self):
        return str(Path(__file__).with_name("tornillo.svg"))

    def doubleClicked(self, view):
        import FreeCADGui as Gui

        return bool(Gui.getDocument(view.Object.Document.Name).setEdit(view.Object.Name))

    def setEdit(self, view, mode=0):
        import FreeCADGui as Gui

        if mode != 0 or Gui.Control.activeDialog():
            return False
        self.panel = open_screw_panel(view.Object.Document, feature=view.Object)
        return True

    def unsetEdit(self, view, mode=0):
        import FreeCADGui as Gui

        if getattr(self, "panel", None):
            self.panel.cleanup()
        Gui.Control.closeDialog()
        self.panel = None
        return True

    def dumps(self):
        return None

    def loads(self, _state):
        pass


def open_screw_panel(document, body=None, feature=None, profile=None):
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

    if feature is not None:
        body = feature.getParentGeoFeatureGroup()
        profile = getattr(feature, "PerfilTornillo", None)

    class ScrewPanel:
        def __init__(self):
            self.profile = profile
            self.profile_row = None
            self.preview_root = self.preview_node = None
            self.preview_timer = None
            self.form = QtWidgets.QWidget()
            self.form.setWindowTitle("AÑADIR · Tornillo")
            panel_layout = QtWidgets.QVBoxLayout(self.form)
            if App.GuiUp:
                from .add_material_visual import AddProfileRow

                self.profile_row = AddProfileRow(self.form, document, profile, self.set_profile,
                                                 body=body, feature=feature, closed_only=False)
                panel_layout.addWidget(self.profile_row)
            parameters = QtWidgets.QGroupBox("Parámetros de tornillo", self.form)
            panel_layout.addWidget(parameters)
            layout = QtWidgets.QFormLayout(parameters)
            self.standard = QtWidgets.QComboBox()
            self.standard.addItems(["ISO métrica · " + DESIGNATION, "Personalizada"])
            layout.addRow("Estándar", self.standard)
            self.nominal = self.length_field(layout, "Diámetro del vástago bajo cabeza", NOMINAL)
            self.pitch = self.length_field(layout, "Paso", PITCH)
            self.head = QtWidgets.QComboBox()
            self.head.addItems(["Cilíndrica", "Avellanada", "Sin cabeza"])
            layout.addRow("Cabeza", self.head)
            self.diameter = self.length_field(layout, "Diámetro de cabeza", 13)
            self.height = self.length_field(layout, "Altura de cabeza", 8)
            self.head_angle = self.length_field(layout, "Ángulo de avellanado", 90, "°", 179)
            self.length = self.length_field(layout, "Longitud bajo cabeza", 25)
            self.point = QtWidgets.QCheckBox("Punta cónica")
            layout.addRow(self.point)
            self.tip_angle = self.length_field(layout, "Ángulo de la punta", 118, "°", 179)
            self.include = QtWidgets.QCheckBox("Incluir punta en la longitud")
            self.include.setChecked(True)
            layout.addRow(self.include)
            self.reverse = QtWidgets.QCheckBox("Cambiar dirección")
            layout.addRow(self.reverse)
            self.taper = QtWidgets.QCheckBox("Vástago cónico")
            layout.addRow(self.taper)
            self.taper_angle = self.length_field(layout, "Ángulo del vástago con el eje", 1, "°", 45)
            self.thread_length = self.length_field(layout, "Longitud roscada desde la punta", 15)
            self.left = QtWidgets.QCheckBox("Mano izquierda")
            self.modeled = QtWidgets.QCheckBox("Modelar rosca")
            self.modeled.setChecked(True)
            layout.addRow(self.left)
            layout.addRow(self.modeled)
            self.error = QtWidgets.QLabel()
            self.error.setWordWrap(True)
            layout.addRow(self.error)
            if App.GuiUp:
                self.add_preview(parameters)
            for control in (self.standard, self.head):
                control.currentIndexChanged.connect(self.update_fields)
            for control in (self.point, self.taper, self.modeled):
                control.toggled.connect(self.update_fields)
            self.taper.toggled.connect(self.use_custom_taper)
            self.standard.currentIndexChanged.connect(self.use_standard_shaft)
            for control in (self.nominal, self.diameter, self.height):
                control.valueChanged.connect(self.update_head_angle)
            self.head_angle.valueChanged.connect(self.update_head_height)
            if feature is not None:
                (length, threaded_length, head, diameter, height, left, modeled, nominal,
                 pitch, tip_angle, include_tip, reverse, taper_angle, custom) = Screw.dimensions(feature)
                self.standard.setCurrentIndex(int(custom or bool(taper_angle)))
                self.head.setCurrentText(head)
                self.nominal.setValue(nominal)
                self.pitch.setValue(pitch)
                self.diameter.setValue(diameter)
                self.height.setValue(height)
                self.length.setValue(length)
                self.thread_length.setValue(threaded_length)
                self.point.setChecked(bool(tip_angle))
                if tip_angle:
                    self.tip_angle.setValue(tip_angle)
                self.include.setChecked(include_tip)
                self.reverse.setChecked(reverse)
                self.taper.setChecked(bool(taper_angle))
                if taper_angle:
                    self.taper_angle.setValue(taper_angle)
                self.left.setChecked(left)
                self.modeled.setChecked(modeled)
            self.update_fields()

        def add_preview(self, parameters):
            preview = QtWidgets.QGroupBox("Pre-visualizar", self.form)
            layout = QtWidgets.QVBoxLayout(preview)
            self.show_result = QtWidgets.QCheckBox("Mostrar resultado final")
            self.show_overlay = QtWidgets.QCheckBox("Mostrar volumen de tornillo")
            layout.addWidget(self.show_result)
            layout.addWidget(self.show_overlay)
            self.form.layout().addWidget(preview)
            self.preview_timer = QtCore.QTimer(self.form)
            self.preview_timer.setSingleShot(True)
            self.preview_timer.setInterval(350)
            self.preview_timer.timeout.connect(self.refresh_preview)
            self.show_result.toggled.connect(self.refresh_preview)
            self.show_overlay.toggled.connect(self.refresh_preview)
            for widget in parameters.findChildren(QtWidgets.QDoubleSpinBox):
                widget.valueChanged.connect(self.queue_preview)
            for widget in parameters.findChildren(QtWidgets.QComboBox):
                widget.currentIndexChanged.connect(self.queue_preview)
            for widget in parameters.findChildren(QtWidgets.QCheckBox):
                widget.toggled.connect(self.queue_preview)

        def set_profile(self, sketch):
            self.profile = sketch
            self.queue_preview()

        def queue_preview(self):
            if self.show_result.isChecked() or self.show_overlay.isChecked():
                self.preview_timer.start()

        def clear_preview(self):
            if self.preview_node is not None:
                self.preview_root.removeChild(self.preview_node)
                self.preview_node = self.preview_root = None

        def refresh_preview(self):
            from pivy import coin
            from .remove_material_visual import shape_scene_node

            self.clear_preview()
            if not (self.show_result.isChecked() or self.show_overlay.isChecked()):
                return
            try:
                target, _, _, addition, result = self.geometry()
                placement = target.getGlobalPlacement() if target else App.Placement()
                group = coin.SoSeparator()
                for enabled, shape, color, alpha in (
                    (self.show_result.isChecked(), result, (0.75, 0.78, 0.82), 0.0),
                    (self.show_overlay.isChecked(), addition, (0.25, 0.85, 0.45), 0.35),
                ):
                    if enabled:
                        display = shape.copy()
                        display.Placement = placement.multiply(display.Placement)
                        node = shape_scene_node(display, color, alpha)
                        if node:
                            group.addChild(node)
                self.preview_root = Gui.getDocument(document.Name).activeView().getSceneGraph()
                self.preview_root.addChild(group)
                self.preview_node = group
                self.error.clear()
            except (ValueError, RuntimeError, Part.OCCError) as error:
                self.error.setText(str(error))

        def cleanup(self):
            if self.profile_row is not None:
                self.profile_row.stop_pick()
            if self.preview_timer is not None:
                self.preview_timer.stop()
            self.clear_preview()

        def use_custom_taper(self, enabled):
            if enabled:
                self.standard.setCurrentIndex(1)

        def use_standard_shaft(self, index):
            if index == 0:
                self.taper.setChecked(False)

        @staticmethod
        def length_field(layout, label, value, suffix=" mm", maximum=10000):
            field = QtWidgets.QDoubleSpinBox()
            field.setRange(0.001 if suffix == "°" else 0, maximum)
            field.setDecimals(3)
            field.setSuffix(suffix)
            field.setValue(value)
            layout.addRow(label, field)
            return field

        def update_fields(self):
            custom = self.standard.currentIndex() == 1
            self.nominal.setReadOnly(not custom)
            self.pitch.setReadOnly(not custom)
            if not custom:
                self.nominal.setValue(NOMINAL)
                self.pitch.setValue(PITCH)
            self.diameter.setEnabled(self.head.currentIndex() != 2)
            self.height.setEnabled(self.head.currentIndex() != 2)
            self.head_angle.setEnabled(self.head.currentIndex() == 1)
            self.tip_angle.setEnabled(self.point.isChecked())
            self.include.setEnabled(self.point.isChecked())
            self.taper_angle.setEnabled(self.taper.isChecked())
            self.thread_length.setEnabled(self.modeled.isChecked())
            self.left.setEnabled(self.modeled.isChecked())
            self.update_head_angle()

        def update_head_angle(self):
            delta = (self.diameter.value() - self.nominal.value()) / 2
            if self.height.value() > 0 and delta > 0:
                previous = self.head_angle.blockSignals(True)
                self.head_angle.setValue(math.degrees(2 * math.atan2(delta, self.height.value())))
                self.head_angle.blockSignals(previous)

        def update_head_height(self):
            delta = (self.diameter.value() - self.nominal.value()) / 2
            if delta > 0:
                previous = self.height.blockSignals(True)
                self.height.setValue(delta / math.tan(math.radians(self.head_angle.value() / 2)))
                self.height.blockSignals(previous)

        def dimensions(self):
            return (
                self.length.value(),
                self.thread_length.value() if self.modeled.isChecked() else 0,
                self.head.currentText(), self.diameter.value(), self.height.value(),
                self.left.isChecked(), self.modeled.isChecked(), self.nominal.value(),
                self.pitch.value(), self.tip_angle.value() if self.point.isChecked() else 0,
                self.include.isChecked(), self.reverse.isChecked(),
                self.taper_angle.value() if self.taper.isChecked() else 0,
                self.standard.currentIndex() == 1,
            )

        def geometry(self, dimensions=None):
            sketch = self.profile
            target = body
            if target is None and sketch is not None:
                target = sketch.getParentGeoFeatureGroup()
            if feature is None and target is None:
                bodies = [obj for obj in document.Objects if obj.TypeId == "PartDesign::Body"]
                if len(bodies) > 1:
                    raise ValueError("Activa el Cuerpo al que quieres añadir el tornillo.")
                target = bodies[0] if bodies else None
            if feature is not None:
                base = feature.BaseFeature if hasattr(feature, "AddSubShape") else None
            else:
                base = target.Tip if target is not None else None
            addition = positioned_screw(screw_shape(*(dimensions or self.dimensions())), sketch, target)
            return target, base, sketch, addition, additive_result(addition, base)

        def accept(self):
            dimensions = self.dimensions()
            try:
                target, base, sketch, addition, result = self.geometry(dimensions)
            except Exception as error:
                self.error.setText(str(error))
                return False

            document.openTransaction("Editar tornillo" if feature is not None else "Añadir tornillo")
            try:
                operation = feature
                if operation is None:
                    if target is None:
                        target = document.addObject("PartDesign::Body", "Body")
                    operation = target.newObject("PartDesign::FeatureAdditivePython", "TornilloExterior")
                    operation.Label = "Tornillo"
                    Screw(operation, *dimensions)
                    operation.BaseFeature = base
                    if App.GuiUp:
                        ScrewView(operation.ViewObject)
                    target.Tip = operation
                else:
                    Screw.configure(operation, *dimensions)
                if sketch is not None or hasattr(operation, "PerfilTornillo"):
                    if not hasattr(operation, "PerfilTornillo"):
                        operation.addProperty("App::PropertyLink", "PerfilTornillo", "Tornillo")
                    operation.PerfilTornillo = sketch
                operation.Proxy.pending_shapes = (addition, result)
                operation.touch()
                document.recompute()
                if operation.Shape.isNull() or "Invalid" in operation.State:
                    raise ValueError(operation.getStatusString())
                if App.GuiUp and feature is None and base is not None:
                    base.Visibility = False
                document.commitTransaction()
            except Exception as error:
                document.abortTransaction()
                self.error.setText(str(error))
                return False
            return self.reject()

        def reject(self):
            self.cleanup()
            if feature is not None:
                Gui.getDocument(document.Name).resetEdit()
            return True

    panel = ScrewPanel()
    Gui.Control.showDialog(panel)
    return panel
