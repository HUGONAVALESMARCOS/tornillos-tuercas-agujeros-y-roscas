"""Build a native hole tool for the preview of an empty Body."""

import FreeCAD as App
import Part


PARAMETERS = (
    'ThreadType', 'ThreadSize', 'Threaded', 'ThreadClass', 'ThreadFit',
    'ThreadDirection', 'ThreadDepthType', 'ThreadDepth', 'ModelThread',
    'UseCustomThreadClearance', 'CustomThreadClearance',
    'HoleCutType', 'HoleCutCustomValues', 'HoleCutDiameter', 'HoleCutDepth',
    'HoleCutCountersinkAngle', 'Depth', 'DrillPoint', 'DrillPointAngle',
    'DrillForDepth', 'Tapered', 'TaperedAngle',
)


def cutter(hole):
    previous_document = App.ActiveDocument
    document = App.newDocument('TTARHolePreview', hidden=True, temp=True)
    try:
        body = document.addObject('PartDesign::Body', 'Body')
        stock = body.newObject('PartDesign::Feature', 'Stock')
        extent = 2 * max(hole.Depth.Value, hole.Diameter.Value, hole.HoleCutDiameter.Value, 1)
        stock.Shape = Part.makeBox(2 * extent, 2 * extent, extent,
                                   App.Vector(-extent, -extent, -extent))
        profile = body.newObject('Sketcher::SketchObject', 'Profile')
        profile.addGeometry(Part.Circle(App.Vector(), App.Vector(0, 0, 1), 1), False)
        preview = body.newObject('PartDesign::Hole', 'Hole')
        preview.Profile = (profile, [])
        preview.BaseFeature = stock
        # Without stock in the actual Body, use the configured depth for the overlay.
        preview.DepthType = 'Dimension'
        for name in PARAMETERS:
            setattr(preview, name, getattr(hole, name))
        document.recompute()
        shape = preview.AddSubShape.copy()
        if shape.isNull() or not shape.Solids:
            raise ValueError(preview.getStatusString())
        pose = hole.PosicionAgujero
        if hole.Reversed:
            pose = pose.multiply(App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), 180)))
        shape.Placement = pose.multiply(shape.Placement)
        return shape
    finally:
        App.closeDocument(document.Name)
        if previous_document is not None and App.ActiveDocument != previous_document:
            App.setActiveDocument(previous_document.Name)
