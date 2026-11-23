"""Manual internal thread for positioned Part Design holes."""

import math

import FreeCAD as App
import Part


def enabled(hole):
    return getattr(hole, 'ModelarRoscaManual', False) and hole.ThreadType == 'None'


def internal_thread_groove(radius, pitch, length, left):
    if pitch <= 0 or length <= 0 or radius <= 0:
        raise ValueError('El diámetro, el paso y la longitud de rosca deben ser positivos.')
    root = radius + 0.541266 * pitch
    inner = radius - min(0.1 * pitch, radius / 2)
    half = (root - inner) / math.sqrt(3) + pitch / 16
    z = -pitch
    profile = Part.makePolygon([
        App.Vector(inner, 0, z-half), App.Vector(root, 0, z-pitch/16),
        App.Vector(root, 0, z+pitch/16), App.Vector(inner, 0, z+half),
        App.Vector(inner, 0, z-half),
    ])
    path = Part.makeHelix(pitch, length + 2*pitch, radius, 0, left)
    path.translate(App.Vector(0, 0, z))
    groove = path.makePipeShell([profile], True, True)
    return groove.common(Part.makeCylinder(root + pitch, length))


def cutter(hole, threaded):
    pose = hole.PosicionAgujero
    axis = App.Vector(0, 0, 1)
    if not hole.Reversed:
        pose = pose.multiply(App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), 180)))
    radius = hole.Diameter.Value / 2
    depth = hole.Depth.Value
    if hole.DepthType == 'ThroughAll' and hole.BaseFeature and hole.BaseFeature.Shape.Solids:
        bounds = hole.BaseFeature.Shape.BoundBox
        depth = max(pose.inverse().multVec(bounds.getPoint(i)).z for i in range(8))
    depth = max(depth, 0.001)
    if threaded:
        pitch = hole.PasoRoscaManual.Value
        length = min(depth, hole.LongitudRoscaManual.Value)
        shape = internal_thread_groove(radius, pitch, length, hole.RoscaManualIzquierda)
    else:
        shape = Part.makeCylinder(radius, depth, App.Vector(), axis)
    shape.Placement = pose.multiply(shape.Placement)
    return shape


class Result:
    def execute(self, obj):
        hole = obj.ManualHoleSource
        if hole is None or hole.Shape.isNull():
            obj.Shape = Part.Shape()
            return
        shape = hole.Shape
        if enabled(hole):
            shape = shape.cut(cutter(hole, True)).removeSplitter()
        if not shape.Solids or not shape.isValid():
            raise ValueError('La rosca manual no deja un sólido válido.')
        obj.Shape = shape

    def dumps(self):
        return None

    def loads(self, state):
        pass


class ResultView:
    def attach(self, view):
        self.view = view

    def canDelete(self, obj):
        return obj == self.view.Object.ManualHoleSource

    def dumps(self):
        return None

    def loads(self, state):
        pass


def result_for(hole):
    return next((obj for obj in hole.InList if getattr(obj, 'ManualHoleResult', False)
                 and obj.ManualHoleSource == hole), None)


def ensure_result(hole):
    result = result_for(hole)
    if result is None:
        body = hole.getParentGeoFeatureGroup()
        tip = body.Tip
        successors = [item for item in body.Group if getattr(item, 'BaseFeature', None) == hole]
        result = hole.Document.addObject('PartDesign::FeaturePython', 'ManualHoleResult')
        body.insertObject(result, hole, True)
        result.Label = 'Resultado de rosca manual'
        result.addProperty('App::PropertyBool', 'ManualHoleResult', '', '', 4).ManualHoleResult = True
        result.addProperty('App::PropertyLink', 'ManualHoleSource', '', '', 4).ManualHoleSource = hole
        result.BaseFeature = hole
        result.Proxy = Result()
        if App.GuiUp:
            result.ViewObject.Proxy = ResultView()
            result.ViewObject.ShowInTree = False
            result.ViewObject.hide()
        for successor in successors:
            successor.BaseFeature = result
        body.Tip = tip
    return result
