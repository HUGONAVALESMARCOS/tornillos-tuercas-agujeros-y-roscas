# SPDX-License-Identifier: MIT

from functools import lru_cache

import json

import re

import FreeCAD as App

import Part

def is_cut_sweep(obj):
    return obj is not None and obj.TypeId == 'PartDesign::AdditivePipe' and hasattr(obj, 'CutSweepDefinition')

def sweep_source(profile):
    if getattr(profile, 'TemporaryCutProfile', False):
        return None
    link = getattr(profile, 'SourceProfile', None)
    return link[0] if link else profile

def profile_face(sketch):
    if any(obj.isDerivedFrom('Part::Feature') and obj.Shape.Solids for obj in sketch.OutListRecursive):
        raise ValueError('Usa un croquis que no dependa de una pieza sólida.')
    shape = Part.getShape(sketch, '', needSubElement=False, transform=True)
    if not shape.Wires or any(not wire.isClosed() for wire in shape.Wires):
        raise ValueError('El croquis debe tener contornos cerrados.')
    return Part.makeFace(shape.Wires, 'Part::FaceMakerBullseye')

def temporary_cut_profile(document, body=None, *, hole_origin=False):
    name = 'HoleOriginProfile' if hole_origin else 'TemporaryCutProfile'
    if body is None:
        sketch = document.addObject('Sketcher::SketchObject', name)
    else:
        sketch = body.newObject('Sketcher::SketchObject', name)
    sketch.addProperty('App::PropertyBool', name, '', '', 4)
    setattr(sketch, name, True)
    center = App.Vector() if hole_origin else App.Vector(2, 0, 0)
    sketch.addGeometry(Part.Circle(center, App.Vector(0, 0, 1), 1), False)
    sketch.ViewObject.ShowInTree = False
    sketch.ViewObject.hide()
    sketch.recompute()
    return sketch

def linked_cut_spans(pipe):
    profiles = [profile for profile, _ in [pipe.Profile, *pipe.Sections] if profile] if pipe.Profile else []
    return [f'{start.Name}:{end.Name}' for start, end in zip(profiles, profiles[1:])]

def excluded_cut_spans(pipe):
    return (*getattr(pipe, 'ExcludedCutSpans', []), *getattr(pipe, 'ClearedCutSpanEnds', []))

def independent_cut_shapes(pipe):
    by_name = {profile.Name: profile for profile in getattr(pipe, 'IndependentCutProfiles', [])}
    result = []
    for encoded in getattr(pipe, 'IndependentCutSpans', []):
        span = json.loads(encoded)
        start, end = (by_name.get(span.get(key)) for key in ('start', 'end'))
        if start is None or end is None or start.Shape.isNull() or end.Shape.isNull():
            continue
        references = [by_name[name] for name in span.get('vertex_sketches', []) if name in by_name]
        signature = tuple((obj.Name, obj.Shape.hashCode() if not obj.Shape.isNull() else None,
                           str(obj.getGlobalPlacement())) for obj in (start, end, *references))
        shape = independent_cut_shape(pipe, start, end, encoded, signature)
        if shape is not None:
            result.append(shape)
    return result

@lru_cache(maxsize=32)
def independent_cut_shape(pipe, start, end, encoded, _signature):
    from helixspline_minimum_join import sweep_span

    span = json.loads(encoded)
    try:
        edge = independent_cut_edge(start, end, span)
        if edge is None:
            return None
        shape = sweep_span(pipe, (start, end), edge, span.get('join', True))
        if shape.Solids and shape.isValid():
            return shape
    except (ValueError, RuntimeError, Part.OCCError):
        return None
    return None

def independent_cut_edge(start, end, span):
    from helixspline_path import circle_edge, section_path_shape, span_vertex_references

    method = span['method']
    midpoint = span.get('midpoint')
    references = None
    if span.get('by_vertices'):
        vertices = span.get('vertices') or ['', '']
        if any(not vertex and not circle_edge(profile) for profile, vertex in zip((start, end), vertices)):
            return None
        references = span_vertex_references((start, end), span)
        if method != 'BSplineCentros':
            method = 'Vertices'
    return section_path_shape((start, end), method, span.get('angles', [0, 0, 0]),
                              span.get('reverse', False), [0, 0], references,
                              [App.Vector(*midpoint)] if midpoint is not None else None, use_circle_vertices=True)

def sweep_volume(pipe):
    spans = tuple(getattr(pipe, 'IndependentCutSpans', []))
    excluded = excluded_cut_spans(pipe)
    if not spans and not excluded:
        if source_sketch(pipe) is not None and pipe.Spine and pipe.Sections and 'Invalid' not in pipe.State:
            return linked_sweep_volume(pipe)
        return Part.Shape()
    path = pipe.Spine[0] if pipe.Spine else None
    guides = getattr(path, 'SpanGuides', None)
    profiles = [profile for profile, _ in [pipe.Profile, *pipe.Sections] if profile] if pipe.Profile else []
    profiles.extend(getattr(pipe, 'IndependentCutProfiles', []))
    def shape_hash(shape):
        return shape.hashCode() if shape is not None and not shape.isNull() else None

    signature = (spans, excluded, shape_hash(pipe.Shape), 'Invalid' in pipe.State, pipe.MinimumJoin, pipe.Mode,
                 shape_hash(path.Shape) if path is not None else None, shape_hash(guides),
                 tuple(getattr(path, 'SpanSettings', [])),
                 tuple((profile.ID, shape_hash(profile.Shape), str(profile.getGlobalPlacement())) for profile in profiles))
    return combined_cut_volume(pipe, signature)

@lru_cache(maxsize=32)
def combined_cut_volume(pipe, _signature):
    excluded = excluded_cut_spans(pipe)
    linked = linked_cut_spans(pipe)
    shapes = independent_cut_shapes(pipe)
    if source_sketch(pipe) is not None and pipe.Spine and linked and 'Invalid' not in pipe.State:
        if not any(key in excluded for key in linked):
            shapes.insert(0, linked_sweep_volume(pipe))
        elif any(key not in excluded for key in linked):
            from helixspline_minimum_join import section_solid_spans

            shapes[:0] = [shape for key, shape in zip(linked, section_solid_spans(pipe))
                          if key not in excluded]
    shapes = [shape for shape in shapes if not shape.isNull()]
    if not shapes:
        return Part.Shape()
    return shapes[0].fuse(shapes[1:]) if len(shapes) > 1 else shapes[0].copy()

def linked_sweep_volume(pipe):
    path = pipe.Spine[0]
    spans = tuple(getattr(path, 'SpanSettings', []))
    if not getattr(pipe, 'MinimumJoin', False) and not spans:
        return pipe.Shape.copy()
    guides = getattr(path, 'SpanGuides', path.Shape)
    auxiliary = pipe.AuxiliarySpine
    signature = (path.Shape.hashCode(), None if guides.isNull() else guides.hashCode(),
                 tuple(profile.Shape.hashCode() if profile and not profile.Shape.isNull() else None
                       for profile, _ in [pipe.Profile, *pipe.Sections]),
                 pipe.Mode, auxiliary[0].Shape.hashCode() if auxiliary else None, pipe.MinimumJoin, spans)
    shape = joined_sweep_volume(pipe, signature)
    return shape.copy() if shape is not None else pipe.Shape.copy()

@lru_cache(maxsize=32)
def joined_sweep_volume(pipe, _signature):
    from helixspline_minimum_join import minimum_join_shape

    try:
        shape = minimum_join_shape(pipe)
        if shape.Solids and shape.isValid():
            return shape
    except (ValueError, RuntimeError, Part.OCCError):
        pass
    return None

def cutting_shape(pocket):
    if is_cut_sweep(pocket):
        profile = source_sketch(pocket)
        shape = sweep_volume(pocket)
        owner = (profile.getParentGeoFeatureGroup() if profile is not None
                 else pocket.Document.getObject(pocket.CutSweepDefinition))
        if owner is not None and not shape.isNull():
            shape = shape.copy()
            shape.transformShape(owner.getGlobalPlacement().toMatrix(), True)
        return shape
    if pocket.TypeId == 'PartDesign::Pocket':
        sketch = pocket.Profile[0] if pocket.Profile else None
        if sketch is None or getattr(sketch, 'TemporaryCutProfile', False):
            return Part.Shape()
        if 'Invalid' in pocket.State or pocket.Shape.isNull():
            raise ValueError(f'El vaciado independiente no es válido: {pocket.getStatusString()}')
        profile_face(getattr(sketch, 'SourceSketch', sketch))
        return Part.getShape(pocket, '', needSubElement=False, transform=True)

    sketch = pocket.PocketProfile
    if sketch is None:
        return Part.Shape()
    if pocket.Depth.Value <= 0:
        raise ValueError('La profundidad del vaciado debe ser mayor que cero.')
    direction = sketch.getGlobalPlacement().Rotation.multVec(App.Vector(0, 0, 1))
    length = pocket.Depth.Value if pocket.Reversed else -pocket.Depth.Value
    return profile_face(sketch).extrude(direction * length)

CUT_SCOPES = ('Todo el cuerpo', 'Operaciones anteriores', 'Operaciones posteriores',
              'Operaciones seleccionadas')

def cut_scope(result):
    return getattr(result, 'CutScope', CUT_SCOPES[0])

def is_additive_operation(obj):
    return (obj.TypeId.startswith('PartDesign::Additive')
            or obj.isDerivedFrom('PartDesign::Pad')
            or obj.TypeId in ('PartDesign::Revolution', 'PartDesign::FeatureAdditivePython'))

def cut_applies(cut, operation, order):
    scope = cut_scope(cut)
    if scope == CUT_SCOPES[3]:
        return is_additive_operation(operation) and any(
            getattr(target, 'OperationSource', target) == operation for target in cut.CutOperations
        )
    if scope == CUT_SCOPES[1]:
        return order.get(operation.Name, -1) < order[cut.Name]
    if scope == CUT_SCOPES[2]:
        return order.get(operation.Name, -1) > order[cut.Name]
    return True

def operation_geometry(obj):
    base = obj.BaseFeature
    if base is None or not base.Shape.Solids:
        return obj.Shape, Part.Shape()
    if is_additive_operation(obj):
        tool = getattr(obj, 'AddSubShape', None)
        if tool is not None and tool.Solids:
            return tool, Part.Shape()
    shape = obj.Shape
    if not shape.Solids:
        return Part.Shape(), base.Shape
    return shape.cut(base.Shape), base.Shape.cut(shape)

def body_cutters(body, cuts):
    placement = body.getGlobalPlacement().inverse().toMatrix()
    cutters = []
    for cut in cuts:
        if cut.PocketDefinition is not None:
            cutter = cutting_shape(cut.PocketDefinition)
            if not cutter.isNull():
                cutter.transformShape(placement, True)
                cutters.append((cut, cutter))
    return cutters

def body_material_steps(base):
    history = []
    while base is not None:
        if 'MaterialOperations' in base.PropertiesList:
            history.extend(reversed(base.MaterialOperations))
            break
        if 'PocketDefinition' not in base.PropertiesList and 'BodyCuts' not in base.PropertiesList:
            history.append(base)
        base = getattr(base, 'BaseFeature', None)

    for operation in reversed(history):
        if 'BaseFeature' in operation.PropertiesList:
            added, removed = operation_geometry(operation)
        else:
            added, removed = operation.Shape, Part.Shape()
        yield operation, added, removed

def scoped_body_shape(body, base, cuts, affected=None, visible_operations=None):
    order = {obj.Name: i for i, obj in enumerate(body.Group)}
    cutters = body_cutters(body, cuts)
    steps = []
    for operation, added, removed in body_material_steps(base):
        if visible_operations is not None and operation.Name not in visible_operations:
            continue
        if added.Solids:
            for cut, cutter in cutters:
                if cut_applies(cut, operation, order):
                    clipped = added.cut(cutter)
                    if affected is not None and affected[0] == cut and added.Volume - clipped.Volume > 1e-9:
                        affected[1].append(operation.Label)
                    added = clipped
        steps.append((operation, added, removed))
    return combine_material_steps(steps)

def combine_material_steps(steps):
    shape = Part.Compound([])
    for _, added, removed in steps:
        if removed.Solids and shape.Solids:
            shape = shape.cut(removed)
        if added.Solids:
            if not shape.Solids:
                shape = added
                continue
            fused = shape.fuse(added)
            if (not fused.Solids or not fused.isValid()
                    or fused.Volume + 1e-7 < max(shape.Volume, added.Volume)):
                # Coincident thread faces can make a union discard valid material.
                fused = Part.makeCompound([*shape.Solids, *added.Solids])
            shape = fused
    return shape

def source_sketch(pocket):
    if pocket is None:
        return None
    if pocket.TypeId != 'PartDesign::Pocket' and not is_cut_sweep(pocket):
        return pocket.PocketProfile
    profile = pocket.Profile[0] if pocket.Profile else None
    if getattr(profile, 'TemporaryCutProfile', False):
        return None
    if is_cut_sweep(pocket):
        return sweep_source(profile)
    return getattr(profile, 'SourceSketch', profile)

def result_body(result):
    if result.isDerivedFrom('PartDesign::Feature'):
        return result.getParentGeoFeatureGroup()
    return None

class PersistentCuts:
    def execute(self, result):
        base = result.BaseFeature
        if 'MaterialOperations' in result.PropertiesList:
            shape = scoped_body_shape(result_body(result), result, result.BodyCuts)
            result.Shape = shape if shape.Solids else Part.Shape()
            result.Placement = shape.Placement
            return
        shape = base.Shape if base is not None else Part.Compound([])
        if shape.isNull():
            shape = Part.Compound([])
        body = result_body(result)
        if body is not None and shape.Solids:
            if any(cut_scope(cut) != CUT_SCOPES[0] for cut in result.BodyCuts):
                shape = scoped_body_shape(body, base, result.BodyCuts)
                if not shape.Solids or not shape.isValid():
                    raise ValueError('Los vaciados del cuerpo no dejan un sólido válido.')
                result.Shape = shape
                result.Placement = shape.Placement
                return
            placement = body.getGlobalPlacement().inverse().toMatrix()
            for cut in result.BodyCuts:
                if cut.PocketDefinition is None:
                    continue
                cutter = cutting_shape(cut.PocketDefinition)
                if not cutter.isNull():
                    cutter.transformShape(placement, True)
                    shape = shape.cut(cutter)
                    if not shape.Solids or not shape.isValid():
                        raise ValueError('Los vaciados del cuerpo no dejan un sólido válido.')
        result.Shape = shape
        result.Placement = shape.Placement

    def dumps(self):
        return None

    def loads(self, state):
        pass

class PersistentCutsView:
    def attach(self, view):
        self.view = view

    def canDelete(self, obj):
        item = self.view.Object
        if (obj == item.BaseFeature or obj in item.BodyCuts
                or obj in getattr(item, 'MaterialOperations', [])):
            return True
        raise NotImplementedError

    def dumps(self):
        return None

    def loads(self, state):
        pass

def order_body_operations(body, steps):
    operations = [item for item in steps if 'BodyCuts' not in item.PropertiesList]
    ordered = sorted(operations, key=lambda item: item.ID)
    if operations != ordered:
        ordered_items = iter(ordered)
        body.Group = [next(ordered_items) if item in operations else item for item in body.Group]
    return ordered

def is_deferred_hole(feature):
    return feature.TypeId == 'PartDesign::Hole' and (
        getattr(feature, 'DeferredThreadedHole', False)
        or (feature.Suppressed and 'PosicionAgujero' in feature.PropertiesList
            and feature.BaseFeature is None))


def sync_deferred_holes(body):
    steps = [item for item in body.Group
             if item.isDerivedFrom('PartDesign::Feature') and 'BaseFeature' in item.PropertiesList]
    if any(is_deferred_hole(item) for item in steps):
        if body.Tip is not None and is_deferred_hole(body.Tip) and body.Tip.Suppressed:
            body.Tip = next((item for item in reversed(steps) if item.Shape.Solids), None)
        cuts = [item for item in steps if 'PocketDefinition' in item.PropertiesList]
        keep_independent_material(body, steps, cuts)


def keep_independent_material(body, steps, cuts):
    from . import manual_hole_thread

    holes = [item for item in steps if is_deferred_hole(item)]
    steps = [item for item in steps if item not in holes
             and not getattr(item, 'ManualHoleResult', False)]
    results = [item for item in steps if 'MaterialOperations' in item.PropertiesList]
    operations = [item for item in steps if item not in cuts and 'BodyCuts' not in item.PropertiesList]
    if not operations and not results:
        return False
    if not results and not cuts and not holes and not any(getattr(item, 'HerramientaOrigen', None) == 'Añadir'
                                            for item in operations):
        return False
    if any(not is_additive_operation(item) or getattr(item, 'AtraviesaTodo', False)
           or (item.isDerivedFrom('PartDesign::Pad')
               and str(item.Type) in ('UpToFirst', 'UpToLast'))
           for item in operations):
        return False
    if any('BodyCuts' in item.PropertiesList and item not in results for item in steps):
        return False
    ordered = order_body_operations(body, steps)
    operations = [item for item in ordered if item not in cuts]
    cuts = [item for item in ordered if item in cuts]
    document = body.Document
    result = results[0] if results else None
    if holes:
        last_hole = holes[-1]
        thread_result = manual_hole_thread.result_for(last_hole)
        expected_tip = thread_result if manual_hole_thread.needs_result(last_hole) else last_hole
        tip_matches = body.Tip == expected_tip and all(
            not manual_hole_thread.needs_result(hole) or manual_hole_thread.result_for(hole) is not None
            for hole in holes)
    else:
        tip_matches = body.Tip == result
    if (result is not None and tip_matches and result.MaterialOperations == operations
            and result.BodyCuts == cuts and all(item.BaseFeature is None for item in steps)):
        if not holes or (holes[0].BaseFeature == result and not holes[0].Suppressed):
            return True
    if result is None:
        result = document.addObject('PartDesign::FeaturePython', 'IndependentBodyResult')
        body.insertObject(result, steps[-1], True)
        result.Label = 'Resultado del Cuerpo'
        result.addProperty('App::PropertyLinkList', 'MaterialOperations', 'Cuerpo', '', 4)
        result.addProperty('App::PropertyLinkList', 'BodyCuts', 'Cuerpo', '', 4)
        result.Proxy = PersistentCuts()
        if App.GuiUp:
            result.ViewObject.Proxy = PersistentCutsView()
            result.ViewObject.ShowInTree = False
    for item in (*operations, *cuts, result):
        if item.BaseFeature is not None:
            item.BaseFeature = None
    result.MaterialOperations = operations
    result.BodyCuts = cuts
    result.Visibility = False
    body.Tip = result
    document.recompute()
    if holes:
        if len(result.Shape.Solids) > 1:
            body.AllowCompound = True
        base = result
        for hole in holes:
            if 'DeferredThreadedHole' not in hole.PropertiesList:
                hole.addProperty('App::PropertyBool', 'DeferredThreadedHole', '', '', 4)
            hole.DeferredThreadedHole = True
            hole.BaseFeature = base
            hole.Suppressed = False
            manual_hole_thread.prepare_native_bore(hole)
            hole.recompute()
            base = hole
            if manual_hole_thread.needs_result(hole) and hole.Shape.Solids:
                base = manual_hole_thread.ensure_result(hole)
                base.recompute()
        body.Tip = base
        for operation in (*operations, *holes):
            operation.Visibility = operation == base
        base.Visibility = True
        document.recompute()
    return True
