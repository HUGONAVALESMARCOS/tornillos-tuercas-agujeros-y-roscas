# SPDX-License-Identifier: MIT
"""Geometry and editable properties for a hexagonal nut."""

import math
from pathlib import Path

import FreeCAD as App
import Part

from .manual_hole_thread import internal_thread_groove
from .add_screw import ScrewView, external_thread_groove

NUT_ICON = str(Path(__file__).with_name('tuerca.png'))
WHITWORTH_SERIES = ('BSW', 'BSF', 'BSP')
# ASME B1.20.1, basic pitch diameter E1 at the large end of the internal thread, in inches.
NPT_PITCH_DIAMETERS = {
    '1/16': .28118, '1/8': .37360, '1/4': .49163, '3/8': .62701,
    '1/2': .77843, '3/4': .98887, '1': 1.23863, '1 1/4': 1.58338,
    '1 1/2': 1.82234, '2': 2.29627, '2 1/2': 2.76216, '3': 3.38850,
    '3 1/2': 3.88881, '4': 4.38713, '5': 5.44929, '6': 6.50597,
    '8': 8.50003, '10': 10.62094, '12': 12.61781,
}
NPT_RADIAL_TAPER = 1 / 32
CLOSED = 'Hexagonal ciega'
DOMED = 'Hexagonal ciega abombada'
CASTLE = 'Hexagonal almenada'
SLOTTED = 'Hexagonal ranurada'
NYLON = 'Hexagonal autoblocante con nailon'
SQUARE = 'Cuadrada'
TUBE = 'Tubo roscado'
WING = 'Tubo roscado con orejetas (mariposa)'
WING_FIELDS = ('SalienteOrejetas', 'AlturaOrejetas', 'EspesorOrejetas')
TEE = 'Tubo roscado en T'
TEE_FIELDS = (('DiametroArandela', 'Length'), ('EspesorArandela', 'Length'),
              ('AlturaPestanas', 'Length'), ('NumeroPestanas', 'Integer'))
EXTERNAL_FIELDS = (
    ('EstandarExterior', 'String'), ('TamanoExterior', 'String'), ('DiametroRoscaExterior', 'Length'),
    ('PasoRoscaExterior', 'Length'), ('RoscaExteriorIzquierda', 'Bool'), ('LongitudRoscaExterior', 'Length'),
)


class HexNut:
    def __init__(self, feature, dimensions, standard, size, flange=None, cap=None, crown=None,
                 slotted=False, insert=None, square=False, tube_depth=None, tube_inner=True, external=None,
                 wings=None, tee=None):
        self.configure(feature, dimensions, standard, size, flange, cap, crown, slotted, insert, square, tube_depth,
                       tube_inner, external, wings, tee)
        if 'HerramientaOrigen' not in feature.PropertiesList:
            feature.addProperty('App::PropertyString', 'HerramientaOrigen', 'AÑADIR')
            feature.HerramientaOrigen = 'Añadir'
            feature.setEditorMode('HerramientaOrigen', 2)
        feature.Proxy = self
        if App.GuiUp and not isinstance(feature.ViewObject.Proxy, NutView):
            NutView(feature.ViewObject)

    @staticmethod
    def configure(feature, dimensions, standard, size, flange=None, cap=None, crown=None,
                  slotted=False, insert=None, square=False, tube_depth=None, tube_inner=True, external=None,
                  wings=None, tee=None):
        HexNut.add_position_property(feature)
        names = ('DiametroNominal', 'PasoRosca', 'MedidaEntreCaras', 'AlturaTuerca',
                 'RadioRedondeo', 'RoscaIzquierda')
        for name, value in zip(names, dimensions):
            kind = 'Bool' if name == 'RoscaIzquierda' else 'Length'
            if name not in feature.PropertiesList:
                feature.addProperty('App::Property' + kind, name, 'Tuerca')
            setattr(feature, name, value)
        variant = cap[0] if cap else 'Hexagonal con brida' if flange else 'Hexagonal normal'
        if crown:
            variant = SLOTTED if slotted else CASTLE
        if insert:
            variant = NYLON
        if square:
            variant = SQUARE
        if tube_depth is not None:
            variant = WING if wings else TEE if tee else TUBE
        if wings or tee:
            external = None
        if tee or TEE_FIELDS[0][0] in feature.PropertiesList:
            for (name, kind), value in zip(TEE_FIELDS, tee or (0, 0, 0, 4)):
                if name not in feature.PropertiesList:
                    feature.addProperty('App::Property' + kind, name, 'Tubo')
                setattr(feature, name, value)
                feature.setEditorMode(name, 0 if tee else 2)
        if wings or WING_FIELDS[0] in feature.PropertiesList:
            for name, value in zip(WING_FIELDS, wings or (0, 0, 0)):
                if name not in feature.PropertiesList:
                    feature.addProperty('App::PropertyLength', name, 'Tubo')
                setattr(feature, name, value)
                feature.setEditorMode(name, 0 if wings else 2)
        for name, value in (('Estandar', standard), ('Tamano', size), ('TipoTuerca', variant)):
            if name not in feature.PropertiesList:
                feature.addProperty('App::PropertyString', name, 'Tuerca')
            setattr(feature, name, value)
            feature.setEditorMode(name, 1)
        if flange or 'DiametroBrida' in feature.PropertiesList:
            for name, value in zip(('DiametroBrida', 'EspesorBrida'), flange or (0, 0)):
                if name not in feature.PropertiesList:
                    feature.addProperty('App::PropertyLength', name, 'Tuerca')
                setattr(feature, name, value)
                feature.setEditorMode(name, 0 if flange else 2)
        if cap or 'AlturaTapa' in feature.PropertiesList:
            if 'AlturaTapa' not in feature.PropertiesList:
                feature.addProperty('App::PropertyLength', 'AlturaTapa', 'Tuerca')
            feature.AlturaTapa = cap[1] if cap else 0
            feature.setEditorMode('AlturaTapa', 0 if cap else 2)
        if cap and cap[0] == DOMED:
            if 'AlturaHexagonalIndependiente' not in feature.PropertiesList:
                feature.addProperty('App::PropertyBool', 'AlturaHexagonalIndependiente', 'Tuerca')
                feature.setEditorMode('AlturaHexagonalIndependiente', 2)
            feature.AlturaHexagonalIndependiente = True
        if crown or 'AnchoRanura' in feature.PropertiesList:
            depth_name = 'ProfundidadRanura' if slotted else 'AlturaCorona'
            for name, kind, value in zip(
                    (depth_name, 'AnchoRanura', 'NumeroRanuras'),
                    ('Length', 'Length', 'Integer'), crown or (0, 0, 6)):
                if crown is None and name not in feature.PropertiesList:
                    continue
                if name not in feature.PropertiesList:
                    feature.addProperty('App::Property' + kind, name, 'Tuerca')
                setattr(feature, name, value)
                feature.setEditorMode(name, 0 if crown else 2)
            for name in ('AlturaCorona', 'ProfundidadRanura'):
                if name != depth_name and name in feature.PropertiesList:
                    feature.setEditorMode(name, 2)
        if insert or 'AlturaInserto' in feature.PropertiesList:
            for name, value in zip(('AlturaInserto', 'DiametroInteriorInserto'), insert or (0, 0)):
                if name not in feature.PropertiesList:
                    feature.addProperty('App::PropertyLength', name, 'Tuerca')
                setattr(feature, name, value)
                feature.setEditorMode(name, 0 if insert else 2)
        if tube_depth is not None or 'LongitudRoscada' in feature.PropertiesList:
            if 'LongitudRoscada' not in feature.PropertiesList:
                feature.addProperty('App::PropertyLength', 'LongitudRoscada', 'Tuerca',
                                    'Cero rosca toda la longitud.')
            feature.LongitudRoscada = tube_depth or 0
            feature.setEditorMode('LongitudRoscada', 0 if tube_depth is not None else 2)
        if tube_depth is not None or 'RoscaInteriorActiva' in feature.PropertiesList:
            for name, value in (('RoscaInteriorActiva', tube_inner), ('RoscaExteriorActiva', external is not None)):
                if name not in feature.PropertiesList:
                    feature.addProperty('App::PropertyBool', name, 'Tubo')
                setattr(feature, name, value)
                feature.setEditorMode(name, 0 if tube_depth is not None and
                                      (name == 'RoscaInteriorActiva' or variant == TUBE) else 2)
        if external is not None:
            for (name, kind), value in zip(EXTERNAL_FIELDS, external):
                if name == 'DiametroRoscaExterior':
                    continue
                if name not in feature.PropertiesList:
                    feature.addProperty('App::Property' + kind, name, 'Tubo')
                setattr(feature, name, value)
        for name, _ in EXTERNAL_FIELDS:
            if name in feature.PropertiesList:
                feature.setEditorMode(name, 0 if external is not None and name != 'DiametroRoscaExterior' else 2)
        if external is not None and 'DiametroRoscaExterior' in feature.PropertiesList:
            if 'UsaDiametroDelTubo' not in feature.PropertiesList:
                feature.addProperty('App::PropertyBool', 'UsaDiametroDelTubo', 'Tubo')
                feature.setEditorMode('UsaDiametroDelTubo', 2)
            feature.UsaDiametroDelTubo = True

    @staticmethod
    def add_position_property(feature):
        if 'PosicionTuerca' not in feature.PropertiesList:
            placement = feature.Placement
            feature.addProperty('App::PropertyPlacement', 'PosicionTuerca', '1. Posición',
                                'Posición y orientación de la tuerca respecto al Cuerpo.')
            feature.PosicionTuerca = placement

    def onDocumentRestored(self, feature):
        self.add_position_property(feature)
        if App.GuiUp:
            from PySide import QtCore

            document, name = feature.Document.Name, feature.Name

            def restore_view():
                doc = App.listDocuments().get(document)
                obj = doc.getObject(name) if doc else None
                if obj is not None and not isinstance(obj.ViewObject.Proxy, NutView):
                    NutView(obj.ViewObject)

            QtCore.QTimer.singleShot(0, restore_view)

    def execute(self, feature):
        flange = None
        variant = getattr(feature, 'TipoTuerca', '')
        if variant == 'Hexagonal con brida':
            flange = feature.DiametroBrida.Value, feature.EspesorBrida.Value
        cap = (variant, feature.AlturaTapa.Value) if variant in (CLOSED, DOMED) else None
        crown = None
        if variant in (CASTLE, SLOTTED):
            slot_depth = feature.ProfundidadRanura if variant == SLOTTED else feature.AlturaCorona
            crown = slot_depth.Value, feature.AnchoRanura.Value, feature.NumeroRanuras
        insert = None
        if variant == NYLON:
            insert = feature.AlturaInserto.Value, feature.DiametroInteriorInserto.Value
        height = feature.AlturaTuerca.Value
        if variant == DOMED and not getattr(feature, 'AlturaHexagonalIndependiente', False):
            height -= cap[1]
        tube = variant in (TUBE, WING, TEE)
        external = tube_external_settings(feature) if variant == TUBE else None
        wings = tuple(getattr(feature, name).Value for name in WING_FIELDS) if variant == WING else None
        tee = None
        if variant == TEE:
            tee = (feature.DiametroArandela.Value, feature.EspesorArandela.Value,
                   feature.AlturaPestanas.Value, feature.NumeroPestanas)
        shape = hex_nut_shape(feature.DiametroNominal.Value, feature.PasoRosca.Value,
                              feature.MedidaEntreCaras.Value, height,
                              feature.RadioRedondeo.Value, feature.RoscaIzquierda,
                              feature.Estandar, feature.Tamano, flange, cap, crown, variant == SLOTTED,
                              insert, variant == SQUARE, feature.LongitudRoscada.Value if tube else None,
                              getattr(feature, 'RoscaInteriorActiva', True), external, wings, tee)
        placement = getattr(feature, 'PosicionTuerca', feature.Placement)
        if feature.Placement != placement:
            feature.Placement = placement
        shape.Placement = placement
        feature.Shape = shape
        if 'AddSubShape' in feature.PropertiesList:
            feature.AddSubShape = shape

    def dumps(self):
        return None

    def loads(self, _state):
        pass


class NutView(ScrewView):
    def getIcon(self):
        return NUT_ICON

    def setEdit(self, view, mode=0):
        import FreeCADGui as Gui
        from .add_material_visual import NutPanel

        if mode != 0 or Gui.Control.activeDialog():
            return False
        self.panel = NutPanel(view.Object.Document, view.Object.getParentGeoFeatureGroup(), view.Object)
        Gui.Control.showDialog(self.panel)
        return True

    def unsetEdit(self, view, mode=0):
        import FreeCADGui as Gui

        if getattr(self, 'panel', None) is not None:
            self.panel.finish_nut_edit()
            self.panel = None
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        return True


def whitworth_groove(bore, pitch, length, left):
    flank = math.radians(27.5)
    depth = pitch / (3 * math.tan(flank))
    radius = pitch * math.sin(flank) / (6 * math.tan(flank) * (1 - math.sin(flank)))
    major = bore + depth
    half = pitch / 2
    epsilon = pitch * 0.005

    def point(radial, axial):
        return App.Vector(radial, 0, axial - pitch)

    def crest(angle, side):
        return point(bore + radius * (1 - math.cos(angle)),
                     side * (half - radius * math.sin(angle)))

    end_angle = math.asin(epsilon / radius)
    tangent_angle = math.pi / 2 - flank
    middle_angle = (tangent_angle + end_angle) / 2
    low, high = (crest(end_angle, side) for side in (-1, 1))
    crest_low, crest_high = (crest(tangent_angle, side) for side in (-1, 1))
    root_low, root_high = (point(major - radius * (1 - math.sin(flank)),
                                side * radius * math.cos(flank)) for side in (-1, 1))
    inner = bore - min(pitch * 0.05, bore / 2)
    inner_low, inner_high = point(inner, -half + epsilon), point(inner, half - epsilon)
    profile = Part.Wire([
        Part.makeLine(inner_low, low),
        Part.Arc(low, crest(middle_angle, -1), crest_low).toShape(),
        Part.makeLine(crest_low, root_low),
        Part.Arc(root_low, point(major, 0), root_high).toShape(),
        Part.makeLine(root_high, crest_high),
        Part.Arc(crest_high, crest(middle_angle, 1), high).toShape(),
        Part.makeLine(high, inner_high),
        Part.makeLine(inner_high, inner_low),
    ])
    path = Part.makeHelix(pitch, length + 2 * pitch, bore, 0, left)
    path.translate(App.Vector(0, 0, -pitch))
    groove = path.makePipeShell([profile], True, True)
    return groove.common(Part.makeCylinder(major + pitch, length))


def npt_groove(bore, pitch, height):
    taper = NPT_RADIAL_TAPER
    depth = 0.8 * pitch
    # FreeCAD uses a positive cone angle for an expanding helix. Build from
    # the small end and rotate the sweep into the nut's local coordinates.
    start = bore - (height + pitch) * taper
    overlap = 0.025 * pitch
    relief = 0.15 * pitch
    crest_half = pitch / 4 - depth / (2 * math.sqrt(3))
    inner_half = crest_half + (depth + overlap) / math.sqrt(3)

    def point(radius, z):
        return App.Vector(start + radius + z * taper, 0, z)

    # Continue inside the bore without widening the profile into the next turn.
    points = [point(-relief, -inner_half), point(-overlap, -inner_half),
              point(depth, -crest_half), point(depth, crest_half),
              point(-overlap, inner_half), point(-relief, inner_half)]
    profile = Part.makePolygon([*points, points[0]])
    angle = math.degrees(math.atan(taper))
    path = Part.makeHelix(pitch, height + 2 * pitch, start, angle, False)
    groove = path.makePipeShell([profile], True, True)
    groove.rotate(App.Vector(), App.Vector(1, 0, 0), 180)
    # Keep the sweep start away from the seam of the conical bore.
    groove.rotate(App.Vector(), App.Vector(0, 0, 1), 19)
    groove.translate(App.Vector(0, 0, height + pitch))
    return groove


def tube_external_settings(feature):
    if not getattr(feature, 'RoscaExteriorActiva', False):
        return None
    use_tube_diameter = getattr(feature, 'UsaDiametroDelTubo', False) or 'DiametroRoscaExterior' not in feature.PropertiesList
    values = (getattr(feature, 'MedidaEntreCaras' if use_tube_diameter and name == 'DiametroRoscaExterior' else name)
              for name, _ in EXTERNAL_FIELDS)
    return tuple(value.Value if kind == 'Length' else value
                 for value, (_, kind) in zip(values, EXTERNAL_FIELDS))


def cut_tube_exterior(shape, outside, height, bore_diameter, external, *, exterior_first=True):
    _, _, diameter, pitch, left, length = external
    length = length or height
    if not 0 < diameter <= outside or pitch <= 0 or not 0 < length <= height:
        raise ValueError('La rosca exterior debe caber en el diámetro y la longitud del tubo.')
    if length / pitch > 150:
        raise ValueError('Reduce la longitud o aumenta el paso de la rosca exterior.')
    major = diameter / 2
    if diameter - 1.4 * pitch <= bore_diameter:
        raise ValueError('Aumenta el diámetro de rosca exterior para dejar pared entre ambas roscas.')
    if diameter < outside:
        margin = pitch if exterior_first else 0
        start = App.Vector(0, 0, -margin)
        blend = Part.makeCylinder(outside, length + margin, start).cut(
            Part.makeCylinder(major, length + margin, start))
        shape = shape.cut(blend)
    groove = external_thread_groove(pitch, length, major, left and not exterior_first)
    if not exterior_first:
        cutter = groove.common(Part.makeCylinder(outside, length))
        if cutter.Solids:
            threaded = shape.cut(cutter).removeSplitter()
            if (len(threaded.Solids) == 1 and threaded.isValid()
                    and shape.Volume - threaded.Volume > 1e-7):
                return threaded
        raise Part.OCCError('No se pudo combinar la rosca exterior con el agujero.')
    if length < height:
        margin = 2 * pitch
        clip = Part.makeBox(2 * outside, 2 * outside, length + margin,
                            App.Vector(-outside, -outside, -margin))
        groove = groove.common(clip)
    if not groove.Solids:
        raise ValueError('FreeCAD no pudo formar el tramo de rosca exterior.')
    # Moving the helix away from the cylinder seam avoids ambiguous intersections.
    phases = [(0, 0), (19, 0), (47, 0), (None, 0)]
    if length == height:
        phases.append((0, pitch / 3))
    for angle, axial_offset in phases:
        try:
            if angle is None:
                cutter = groove.common(Part.makeCylinder(outside, length))
            else:
                cutter = groove.copy()
                if angle:
                    cutter.rotate(App.Vector(), App.Vector(0, 0, 1), angle)
                if axial_offset:
                    cutter.translate(App.Vector(0, 0, axial_offset))
            if not cutter.Solids:
                continue
            threaded = shape.cut(cutter).removeSplitter()
            if (len(threaded.Solids) == 1 and threaded.isValid()
                    and shape.Volume - threaded.Volume > 1e-7):
                return threaded.mirror(App.Vector(), App.Vector(0, 1, 0)) if left else threaded
        except (ValueError, Part.OCCError):
            continue
    raise ValueError('FreeCAD no pudo tallar la rosca exterior con estas cotas.')


def add_tube_wings(shape, width, height, bore_diameter, wings):
    reach, wing_height, thickness = wings
    radius = width / 2
    root = (radius + bore_diameter / 2) / 2
    if min(wings) <= 0 or root <= bore_diameter / 2 or math.hypot(root, thickness / 2) >= radius:
        raise ValueError('Reduce el espesor de las orejetas o aumenta la pared del tubo.')
    floor = height * 0.25
    peak = floor + wing_height
    edge = radius + reach

    def point(x, z):
        return App.Vector(x, -thickness / 2, z)

    a = point(root, floor)
    b = point(edge - 0.2 * reach, floor + 0.15 * wing_height)
    c = point(edge - 0.2 * reach, peak)
    d = point(root, min(peak - 0.1 * wing_height, height * 0.75))
    rounded = Part.Arc(b, point(edge, floor + 0.575 * wing_height), c).toShape()
    profile = Part.Wire([Part.makeLine(a, b), rounded, Part.makeLine(c, d), Part.makeLine(d, a)])
    wing = Part.Face(profile).extrude(App.Vector(0, thickness, 0))
    opposite = wing.copy()
    opposite.rotate(App.Vector(), App.Vector(0, 0, 1), 180)
    result = shape.fuse([wing, opposite]).removeSplitter()
    if len(result.Solids) != 1 or not result.isValid():
        raise ValueError('Las orejetas deben quedar unidas al tubo.')
    return result


def tee_flange(width, height, tee):
    diameter, thickness, prong_height, count = tee
    if diameter <= width or not 0 < thickness < height or prong_height <= 0 or not 2 <= count <= 12:
        raise ValueError('La arandela requiere un diámetro mayor que el tubo, espesor menor que su longitud y de 2 a 12 pestañas.')
    radius = diameter / 2
    ledge = (diameter - width) / 2
    root = radius - ledge / 2
    tangential = min(ledge * 0.6, root * math.sin(math.pi / count) / 2)
    if math.hypot(root, tangential) >= radius:
        raise ValueError('La arandela necesita más anchura para apoyar las pestañas.')
    points = [App.Vector(root, -tangential, thickness / 2),
              App.Vector(root, tangential, thickness / 2),
              App.Vector(root, 0, thickness + prong_height)]
    profile = Part.Face(Part.makePolygon([*points, points[0]]))
    tooth = profile.extrude(App.Vector(min(thickness, ledge / 4), 0, 0))
    teeth = []
    for i in range(count):
        prong = tooth.copy()
        prong.rotate(App.Vector(), App.Vector(0, 0, 1), i * 360 / count)
        teeth.append(prong)
    return Part.makeCylinder(radius, thickness).fuse(teeth).removeSplitter()


def hex_nut_shape(diameter, pitch, width, height, rounding, left, standard='None', size='',
                  flange=None, cap=None, crown=None, slotted=False, insert=None, square=False, tube_depth=None,
                  tube_inner=True, external=None, wings=None, tee=None):
    if wings or tee:
        external = None
    if height <= 0 or pitch <= 0 or rounding < 0:
        raise ValueError('La altura y el paso deben ser positivos y el radio debe ser como mínimo cero.')
    thread_height = height
    tube = tube_depth is not None
    if tube:
        if not 0 <= tube_depth <= height:
            raise ValueError('La longitud roscada debe caber dentro del tubo.')
        thread_height = tube_depth or height
    if crown:
        crown_height, slot_width, slots = crown
        if crown_height <= 0 or slot_width <= 0 or not 2 <= slots <= 24:
            raise ValueError('Las ranuras requieren cotas positivas y un número entre 2 y 24.')
        if slotted:
            if crown_height >= height:
                raise ValueError('La profundidad de ranura debe dejar material debajo.')
        else:
            thread_height += crown_height
    if cap:
        variant, cap_height = cap
        if cap_height <= 0 or (variant == CLOSED and cap_height >= height):
            raise ValueError('La altura de la tapa debe ser menor que la altura total de la tuerca.')
        if variant == CLOSED:
            thread_height -= cap_height
        elif cap_height > width:
            raise ValueError('La altura de la cúpula debe ser como máximo el doble de su radio de base.')
    smooth_tube = tube and not tube_inner
    if not smooth_tube and thread_height / pitch > 150:
        raise ValueError('Reduce la altura o aumenta el paso para modelar hasta 150 vueltas.')
    whitworth = not smooth_tube and standard in WHITWORTH_SERIES
    npt = not smooth_tube and standard == 'NPT'
    depth_factor = 0 if smooth_tube else 0.640327 if whitworth else 0.541266
    bore = diameter / 2 - depth_factor * pitch
    major = diameter
    end_bore = bore
    if npt:
        pitch_diameter = NPT_PITCH_DIAMETERS[size] * 25.4
        bore = pitch_diameter / 2 - 0.4 * pitch
        end_bore = bore - thread_height * NPT_RADIAL_TAPER
        major = pitch_diameter + 0.8 * pitch
    if end_bore <= (pitch * NPT_RADIAL_TAPER if npt else 0):
        raise ValueError('El paso es demasiado grande para el diámetro nominal.')
    if width <= major:
        raise ValueError('El diámetro exterior debe superar el diámetro de rosca.' if tube
                         else 'La medida entre caras debe superar el diámetro nominal.')
    if tube and external is not None:
        inner_shape = hex_nut_shape(diameter, pitch, width, height, rounding, left, standard, size,
                                    tube_depth=tube_depth, tube_inner=tube_inner)
        try:
            return cut_tube_exterior(inner_shape, width, height, major, external, exterior_first=False)
        except (ValueError, Part.OCCError):
            pass
    if insert:
        insert_height, insert_diameter = insert
        end_major = major - (thread_height / 16 if npt else 0)
        if insert_height <= 0 or not 0 < insert_diameter < end_major:
            raise ValueError('El inserto requiere altura positiva y una abertura menor que la rosca en su extremo.')
    if crown and slot_width >= 2 * end_bore * math.sin(math.pi / slots):
        raise ValueError('Reduce el ancho o el número de ranuras para dejar material entre ellas.')
    hex_height = height
    if rounding >= min(hex_height / 2, (width - major) / 2):
        raise ValueError('Reduce el radio de redondeo exterior.')
    sides = 4 if square else 6
    phase = math.pi / 4 if square else 0
    radius = width / math.sqrt(2 if square else 3)
    if flange:
        flange_diameter, thickness = flange
        if flange_diameter <= 2 * radius:
            raise ValueError('El diámetro de la brida debe superar la medida entre vértices.')
        if not 0 < thickness < height - rounding:
            raise ValueError('El espesor de la brida debe dejar altura para el cuerpo hexagonal.')
    angles = (phase + i * math.pi / (sides // 2) for i in range(sides))
    points = [App.Vector(radius * math.cos(angle), radius * math.sin(angle), 0) for angle in angles]
    blank = (Part.makeCylinder(width / 2, height) if tube else
             Part.Face(Part.makePolygon([*points, points[0]])).extrude(App.Vector(0, 0, hex_height)))
    if rounding:
        rims = [edge for edge in blank.Edges if edge.BoundBox.ZLength < 1e-8
                and (not flange or edge.BoundBox.ZMin > height / 2)
                and (not (insert or (crown and not slotted) or (cap and variant == DOMED))
                     or edge.BoundBox.ZMin < hex_height / 2)]
        blank = blank.makeFillet(rounding, rims)
    if flange:
        blank = blank.fuse(Part.makeCylinder(flange_diameter / 2, thickness)).removeSplitter()
    if tee:
        blank = blank.fuse(tee_flange(width, height, tee)).removeSplitter()
    if crown:
        floor = height - crown_height if slotted else height
        if slotted:
            rim = blank
        else:
            crown_radius = (0.85 * width + 0.15 * major) / 2
            rim = Part.makeCylinder(crown_radius, crown_height, App.Vector(0, 0, height))
        for i in range(slots):
            slot = Part.makeBox(width, slot_width, crown_height + 1,
                                App.Vector(end_bore / 2, -slot_width / 2, floor))
            slot.rotate(App.Vector(), App.Vector(0, 0, 1), i * 360 / slots)
            rim = rim.cut(slot)
        blank = rim.removeSplitter() if slotted else blank.fuse(rim).removeSplitter()
    if tube and external is not None:
        blank = cut_tube_exterior(blank, width, height, major, external)
    bore_overlap = pitch * 0.0005 if whitworth else 0
    if smooth_tube:
        opening = Part.makeCylinder(bore, height)
        groove = None
    elif npt:
        opening = Part.makeCone(bore, end_bore, thread_height)
        groove = npt_groove(bore, pitch, thread_height)
        if cap or (tube and thread_height < height):
            groove = groove.common(Part.makeCylinder(major, thread_height))
    else:
        opening = Part.makeCylinder(bore + bore_overlap, thread_height)
        groove = (whitworth_groove(bore, pitch, thread_height, left) if whitworth
                  else internal_thread_groove(bore, pitch, thread_height, left))
    if npt:
        # Trim the inner relief with the cone after cutting the helix.
        nut = blank.cut(groove).cut(opening).removeSplitter()
        if left:
            nut = nut.mirror(App.Vector(), App.Vector(0, 1, 0))
    elif groove is not None:
        nut = blank.cut(opening).cut(groove).removeSplitter()
    else:
        nut = blank.cut(opening)
    if tube and not smooth_tube and thread_height < height:
        clearance = major / 2 - (thread_height * NPT_RADIAL_TAPER if npt else 0)
        smooth_bore = Part.makeCylinder(clearance, height - thread_height, App.Vector(0, 0, thread_height))
        nut = nut.cut(smooth_bore).removeSplitter()
    if cap and variant == DOMED:
        base_radius = width / 2
        if cap_height <= base_radius:
            sphere_radius = (base_radius ** 2 + cap_height ** 2) / (2 * cap_height)
            center = App.Vector(0, 0, height + cap_height - sphere_radius)
            latitude = math.degrees(math.asin((sphere_radius - cap_height) / sphere_radius))
            dome = Part.makeSphere(sphere_radius, center, App.Vector(0, 0, 1), latitude, 90, 360)
        else:
            center = App.Vector(0, 0, height)
            tip = App.Vector(0, 0, height + cap_height)
            rim = App.Vector(base_radius, 0, height)
            ellipse = Part.Ellipse(tip, rim, center)
            arc = Part.ArcOfEllipse(ellipse, 0, math.pi / 2).toShape()
            profile = Part.Wire([arc, Part.makeLine(rim, center), Part.makeLine(center, tip)])
            dome = Part.Face(profile).revolve(center, App.Vector(0, 0, 1), 360)
        nut = nut.fuse(dome).removeSplitter()
    if insert:
        seat = App.Vector(0, 0, height)
        outer_radius = (0.85 * width + 0.15 * major) / 2
        ring = Part.makeCylinder(outer_radius, insert_height, seat).cut(
            Part.makeCylinder(insert_diameter / 2, insert_height, seat))
        nut = nut.fuse(ring).removeSplitter()
    if len(nut.Solids) != 1 or not nut.isValid():
        raise ValueError('Las cotas deben dejar una tuerca de un solo sólido.')
    return add_tube_wings(nut, width, height, major, wings) if wings else nut
