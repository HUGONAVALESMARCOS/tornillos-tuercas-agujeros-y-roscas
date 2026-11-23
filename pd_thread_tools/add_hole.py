# SPDX-License-Identifier: MIT
"""Use the shape of an unthreaded hole as a positive Part Design feature."""

import json
import math
from fractions import Fraction
from pathlib import Path

import FreeCAD as App
import Part

from .add_screw import MAJOR, PITCH_DIAMETER, ScrewView, additive_result, external_thread_groove


HEX_HEAD = "Hexagonal"
ISO_HEX_HEAD = "ISO 4017"
BUTTON_HEAD = "Botón"
PAN_HEAD = "Abombada tipo pan"
OVAL_HEAD = "Avellanada ovalada"
DOMED_HEADS = (BUTTON_HEAD, PAN_HEAD, OVAL_HEAD)
HEADS = ("Sin cabeza", "Cajeado", "Avellanado", "Contra-taladro", HEX_HEAD, *DOMED_HEADS)
# ISO 4017:2022 nominal width across flats and head height, in mm.
ISO_HEX_DIMENSIONS = {
    1.6: (3.2, 1.1), 2: (4, 1.4), 2.5: (5, 1.7), 3: (5.5, 2),
    3.5: (6, 2.4), 4: (7, 2.8), 5: (8, 3.5), 6: (10, 4), 7: (11, 4.8),
    8: (13, 5.3), 10: (16, 6.4), 12: (18, 7.5), 14: (21, 8.8),
    16: (24, 10), 18: (27, 11.5), 20: (30, 12.5), 22: (34, 14),
    24: (36, 15), 27: (41, 17), 30: (46, 18.7), 33: (50, 21),
    36: (55, 22.5), 39: (60, 25), 42: (65, 26), 45: (70, 28),
    48: (75, 30), 52: (80, 33), 56: (85, 35), 60: (90, 38), 64: (95, 40),
}
ALLEN_ISO_10642 = {
    2: (1.3, 0.75), 2.5: (1.5, 1), 3: (2, 1.1), 4: (2.5, 1.5), 5: (3, 1.9), 6: (4, 2.2),
    8: (5, 3), 10: (6, 3.6), 12: (8, 4.3), 16: (10, 4.8), 20: (12, 5.6),
}
ALLEN_ISO_4762 = {
    1.6: (1.5, 0.7), 2: (1.5, 1), 2.5: (2, 1.1), 3: (2.5, 1.3),
    4: (3, 2), 5: (4, 2.5), 6: (5, 3), 8: (6, 4), 10: (8, 5),
    12: (10, 6), 14: (12, 7), 16: (14, 8), 20: (17, 10), 24: (19, 12),
    30: (22, 15.5), 36: (27, 19), 42: (32, 24), 48: (36, 28), 56: (41, 34), 64: (46, 38),
}
# Nominal DIN 7984 socket depth and minimum ISO 4762 / ISO 12474 socket depth.
ALLEN_HEADS = {
    "DIN 7984": {
        3: (2, 1.5), 4: (2.5, 2.3), 5: (3, 2.7), 6: (4, 3), 8: (5, 3.8),
        10: (7, 4.5), 12: (8, 5), 16: (12, 5.5), 20: (14, 7.5), 24: (17, 8),
    },
    "ISO 10642": ALLEN_ISO_10642,
    "ISO 4762": ALLEN_ISO_4762,
    "ISO 4762 + 7089": ALLEN_ISO_4762,
    "ISO 12474": {diameter: ALLEN_ISO_4762[diameter] for diameter in (8, 10, 12, 14, 16, 20, 24, 30, 36)},
}
TORX_SIZES = {
    1: (0.9, 0.6), 2: (1, 0.7), 3: (1.2, 0.85), 4: (1.35, 1), 5: (1.5, 1.1),
    6: (1.75, 1.27), 8: (2.4, 1.75), 10: (2.8, 2.05), 15: (3.35, 2.4),
    20: (3.95, 2.85), 25: (4.5, 3.25), 27: (5.1, 3.68), 30: (5.6, 4.05),
    40: (6.75, 4.85), 45: (7.93, 5.64), 50: (8.95, 6.45),
    55: (11.35, 8.05), 60: (13.45, 9.6), 70: (15.7, 11.2),
    80: (17.75, 12.8), 90: (20.2, 14.4),
}
# ISO 14583, socket number and minimum penetration depth.
TORX_ISO_14583 = {
    2: (6, 0.63), 2.5: (8, 0.91), 3: (10, 1.01), 3.5: (15, 1.07),
    4: (20, 1.27), 5: (25, 1.52), 6: (30, 2.02), 8: (45, 2.79), 10: (50, 3.62),
}
TORX_REFERENCE = {**TORX_ISO_14583, 12: (55, 4.82), 14: (60, 5.62),
                  16: (70, 6.62), 18: (80, 7.5), 20: (90, 8.69)}
ISO_BUTTON = "Botón · ISO 7380-1"
ISO_PAN = "Abombada tipo pan · ISO 14583"
ISO_OVAL = "Avellanada ovalada · ISO 7047"
TORX_CATALOG_HEADS = ("ISO 14583", "ISO 14583 (partial)", ISO_PAN)
METRIC_DOME_FORMS = {ISO_BUTTON: BUTTON_HEAD, ISO_PAN: PAN_HEAD, ISO_OVAL: OVAL_HEAD}
HEAD_TITLES = {
    "DIN 7984": "DIN 7984 (cilíndrica baja)",
    "ISO 10642": "ISO 10642 (avellanada)",
    "ISO 12474": "ISO 12474 (cilíndrica)",
    "ISO 14583": "ISO 14583 (abombada tipo pan, perfil simplificado)",
    "ISO 14583 (partial)": "ISO 14583 (abombada tipo pan, rosca parcial, perfil simplificado)",
    "ISO 2009": "ISO 2009 (avellanada)",
    "ISO 4762": "ISO 4762 (cilíndrica)",
    "ISO 4762 + 7089": "ISO 4762 + 7089 (cilíndrica con arandela)",
    "ISO 7046": "ISO 7046 (avellanada)",
    ISO_HEX_HEAD: "ISO 4017 (hexagonal)",
    ISO_BUTTON: "ISO 7380-1 (botón)",
    ISO_PAN: "ISO 14583 (abombada tipo pan)",
    ISO_OVAL: "ISO 7047 (avellanada ovalada)",
}
# Outside diameter and head height; the oval table gives crown rise separately.
METRIC_DOME_DIMENSIONS = {
    ISO_BUTTON: {
        3: (5.7, 1.65), 4: (7.6, 2.2), 5: (9.5, 2.75), 6: (10.5, 3.3),
        8: (14, 4.4), 10: (17.5, 5.5), 12: (21, 6.6), 16: (28, 8.8),
    },
    ISO_PAN: {
        2: (4, 1.6), 2.5: (5, 2.1), 3: (5.6, 2.4), 3.5: (7, 2.6),
        4: (8, 3.1), 5: (9.5, 3.7), 6: (12, 4.6), 8: (16, 6), 10: (20, 7.5),
    },
    ISO_OVAL: {
        1.6: (3, 0.4), 2: (3.8, 0.5), 2.5: (4.7, 0.6), 3: (5.5, 0.7),
        3.5: (7.3, 0.8), 4: (8.4, 1), 5: (9.3, 1.2), 6: (11.3, 1.4),
        8: (15.8, 2), 10: (18.3, 2.3),
    },
}
METRIC_BUTTON_ALLEN = {
    3: (2, 1.04), 4: (2.5, 1.3), 5: (3, 1.56), 6: (4, 2.08),
    8: (5, 2.6), 10: (6, 3.12), 12: (8, 4.16), 16: (10, 5.2),
}


def metric_dome_dimensions(head, diameter):
    table = METRIC_DOME_DIMENSIONS[head]
    reference = min(table, key=lambda value: abs(value - diameter))
    width, height = (value * diameter / reference for value in table[reference])
    if head == ISO_OVAL:
        height += (width - diameter) / 2
    return width, height, 90


def metric_button_allen(diameter):
    reference = min(METRIC_BUTTON_ALLEN, key=lambda value: abs(value - diameter))
    return tuple(value * diameter / reference for value in METRIC_BUTTON_ALLEN[reference])
TORX_BO = "Torx de seguridad (BO)"
TORX_DRIVES = ("Torx", TORX_BO)
PHILLIPS = "Phillips (H)"
POZIDRIV = "Pozidriv (Z)"
SLOT = "Ranura recta"
ROBERTSON = "Cuadrado interior (Robertson)"
SPANNER = "Spanner (dos orificios)"
JIS_S = "Cruz S japonesa"
# JCIS 10-70, countersunk type 1, minimum span M and total recess depth T.
JIS_S_REFERENCE = {
    (1.4, 0.3): (1.45, 0.87), (1.7, 0.35): (1.55, 0.97), (2, 0.4): (1.85, 1.27),
    (2.3, 0.4): (2, 1.42), (2.6, 0.45): (2, 1.42),
}
SLOT_ISO_2009 = {
    1.6: (0.4, 0.32), 2: (0.5, 0.4), 2.5: (0.6, 0.5), 3: (0.8, 0.6),
    3.5: (1, 0.9), 4: (1.2, 1), 5: (1.2, 1.1), 6: (1.6, 1.2), 8: (2, 1.8), 10: (2.5, 2),
}
CROSS_DRIVES = (PHILLIPS, POZIDRIV)
# ISO 7046-1, type H series 1: bit number, minimum penetration and opening span m.
PHILLIPS_ISO_7046 = {
    1.6: (0, 0.6, 1.6), 2: (0, 0.9, 1.9), 2.5: (1, 1.4, 2.8),
    3: (1, 1.7, 3), 3.5: (2, 1.9, 4.1), 4: (2, 2.1, 4.4),
    5: (2, 2.7, 4.9), 6: (3, 3, 6.6), 8: (4, 4, 8.8), 10: (4, 5.1, 9.8),
}
PHILLIPS_WIDTHS = (1.9, 3, 4.9, 6.6, 9.8)
POZIDRIV_ISO_7046 = {
    diameter: (number, depth, span)
    for (diameter, (number, _, _)), (depth, span) in zip(PHILLIPS_ISO_7046.items(), (
        (0.70, 1.6), (0.95, 1.9), (1.48, 2.9), (1.76, 3.2), (1.75, 4.4),
        (2.06, 4.6), (2.60, 5.2), (3.00, 6.8), (4.15, 8.9), (5.19, 10),
    ))
}
POZIDRIV_WIDTHS = (1.9, 3.2, 5.2, 6.8, 10)
PHILLIPS_ISO_7047 = {
    1.6: (0, 0.9, 1.9), 2: (0, 1.2, 2), 2.5: (1, 1.5, 3),
    3: (1, 1.8, 3.4), 3.5: (2, 2.25, 4.8), 4: (2, 2.7, 5.2),
    5: (2, 2.9, 5.4), 6: (3, 3.5, 7.3), 8: (4, 4.75, 9.6), 10: (4, 5.5, 10.4),
}


def cross_options(family, head_key, head, values):
    table, widths = ((POZIDRIV_ISO_7046, POZIDRIV_WIDTHS) if family == POZIDRIV
                     else (PHILLIPS_ISO_7046, PHILLIPS_WIDTHS))
    diameter, _, head_width, head_height, angle, *_ = values
    if family == PHILLIPS and head_key == ISO_OVAL:
        preset = PHILLIPS_ISO_7047.get(diameter)
        if preset:
            return preset[:2], True
    preset = table.get(diameter)
    if preset and head_key == "ISO 7046":
        return preset[:2], True
    if head == HEADS[0] or head_width <= diameter:
        return None, False
    reference = next((table[d] for d in reversed(table) if d <= diameter), table[1.6])
    straight = head in STRAIGHT_HEADS
    rim = head_height if head == "Contra-taladro" else 0
    slope = math.tan(math.radians(angle / 2))
    if not straight and slope <= 0:
        return None, False
    height = head_height if straight else rim + (head_width - diameter) / (2 * slope)
    depth = math.floor(min(reference[1], height / 2) * 1000) / 1000
    if depth <= 0:
        return None, False
    width = head_width if straight else head_width - 2 * max(0, depth - rim) * slope
    number = next((n for n in range(reference[0], -1, -1) if widths[n] <= 0.85 * width), None)
    if number is None and head_key in METRIC_DOME_FORMS:
        # Start with the smallest editable bit even when the head is below
        # the range used for automatic cross-recess recommendations.
        return (0, min(depth, round(diameter * 0.2, 3))), False
    return ((number, depth) if number is not None else None), False


def cross_span(family, head_key, diameter, number):
    table, widths = ((POZIDRIV_ISO_7046, POZIDRIV_WIDTHS) if family == POZIDRIV
                     else (PHILLIPS_ISO_7046, PHILLIPS_WIDTHS))
    preset = (PHILLIPS_ISO_7047 if family == PHILLIPS and head_key == ISO_OVAL
              else table if head_key == "ISO 7046" else {}).get(diameter)
    if preset and number == preset[0]:
        return preset[2]
    if not 0 <= number < len(widths):
        raise ValueError("Selecciona una medida de punta entre 0 y 4.")
    return widths[number]


def torx_options(head_key, head, values):
    diameter, _, head_width, head_height, angle, *_ = values
    preset = TORX_ISO_14583.get(diameter) if head_key in TORX_CATALOG_HEADS else None
    if preset:
        return preset, True
    if head == HEADS[0] or head_width <= diameter:
        return None, False
    reference = next((TORX_REFERENCE[d] for d in reversed(TORX_REFERENCE) if d <= diameter), (6, 0.4))
    straight = head in STRAIGHT_HEADS
    rim = head_height if head == "Contra-taladro" else 0
    slope = math.tan(math.radians(angle / 2))
    if not straight and slope <= 0:
        return None, False
    height = head_height if straight else rim + (head_width - diameter) / (2 * slope)
    depth = math.floor(min(reference[1], height / 2) * 1000) / 1000
    if depth <= 0:
        return None, False
    width = head_width if straight else head_width - 2 * max(0, depth - rim) * slope
    size = next((n for n in reversed(TORX_SIZES) if n <= reference[0]
                 and TORX_SIZES[n][0] <= 0.85 * width), None)
    return ((size, depth) if size else None), False
POSITION_GROUP = "1. Posición"
FAMILIES = {
    "None": "Nada (diámetro manual)",
    "ISOMetricProfile": "ISO Métrico regular (fijación general)",
    "ISOMetricFineProfile": "ISO Métrico fino (fijación de paso fino)",
    "UNC": "UNC (pulgadas, paso grueso)",
    "UNF": "UNF (pulgadas, paso fino)",
    "UNEF": "UNEF (pulgadas, paso extrafino)",
    "NPT": "NPT (tubería cónica)",
    "BSP": "BSP (tubería británica)",
    "BSW": "BSW (Whitworth, paso grueso)",
    "BSF": "BSF (Whitworth, paso fino)",
    "ISOTyre": "ISO Tyre (válvulas de neumático)",
}
MANUAL_HEADS = dict(zip(("None", "Counterbore", "Countersink", "Counterdrill"), HEADS))
STRAIGHT_HEADS = ("Cajeado", HEX_HEAD, BUTTON_HEAD, PAN_HEAD)
# FreeCAD 1.1.3 Hole designations and head dimensions, captured from the
# native feature. Column 0 is the nominal diameter, not Hole.Diameter.
CATALOG = json.loads(Path(__file__).with_name("add_hole_catalog.json").read_text(encoding="utf-8"))
INCH_FAMILIES = ("UNC", "UNF", "UNEF")
ASME_SOCKET = "Cilíndrica · ASME B18.3"
ASME_FLAT = "Avellanada · ASME B18.3"
ASME_HEX = "Hexagonal · ASME B18.2.1"
ASME_BUTTON = "Botón · ASME B18.3"
ASME_PAN = "Abombada tipo pan · ASME B18.6.3"
ASME_OVAL = "Avellanada ovalada · ASME B18.6.3"
# Diameter or width, height, nominal key and minimum engagement, in inches.
INCH_HEAD_DIMENSIONS = {
    ASME_SOCKET: {
        "#0": (0.096, 0.060, "0.050", 0.025),
        "#1": (0.118, 0.073, "1/16", 0.031),
        "#2": (0.140, 0.086, "5/64", 0.038),
        "#3": (0.161, 0.099, "5/64", 0.044),
        "#4": (0.183, 0.112, "3/32", 0.051),
        "#5": (0.205, 0.125, "3/32", 0.057),
        "#6": (0.226, 0.138, "7/64", 0.064),
        "#8": (0.270, 0.164, "9/64", 0.077),
        "#10": (0.312, 0.190, "5/32", 0.090),
        "1/4": (0.375, 0.250, "3/16", 0.120),
        "5/16": (0.469, 0.312, "1/4", 0.151),
        "3/8": (0.562, 0.375, "5/16", 0.182),
        "7/16": (0.656, 0.438, "3/8", 0.213),
        "1/2": (0.750, 0.500, "3/8", 0.245),
        "5/8": (0.938, 0.625, "1/2", 0.307),
        "3/4": (1.125, 0.750, "5/8", 0.370),
        "7/8": (1.312, 0.875, "3/4", 0.432),
        "1": (1.500, 1.000, "3/4", 0.495),
        "1 1/8": (1.688, 1.125, "7/8", 0.557),
        "1 1/4": (1.875, 1.250, "7/8", 0.620),
        "1 3/8": (2.062, 1.375, "1", 0.682),
        "1 1/2": (2.250, 1.500, "1", 0.745),
        "1 3/4": (2.625, 1.750, "1 1/4", 0.870),
        "2": (3.000, 2.000, "1 1/2", 0.995),
    },
    ASME_FLAT: {
        "#0": (0.138, 0.044, "0.035", 0.025),
        "#1": (0.168, 0.054, "0.050", 0.031),
        "#2": (0.197, 0.064, "0.050", 0.038),
        "#3": (0.226, 0.073, "1/16", 0.044),
        "#4": (0.255, 0.083, "1/16", 0.055),
        "#5": (0.281, 0.090, "5/64", 0.061),
        "#6": (0.307, 0.097, "5/64", 0.066),
        "#8": (0.359, 0.112, "3/32", 0.076),
        "#10": (0.411, 0.127, "1/8", 0.087),
        "1/4": (0.531, 0.161, "5/32", 0.111),
        "5/16": (0.656, 0.198, "3/16", 0.135),
        "3/8": (0.781, 0.234, "7/32", 0.159),
        "7/16": (0.844, 0.234, "1/4", 0.159),
        "1/2": (0.938, 0.251, "5/16", 0.172),
        "5/8": (1.188, 0.324, "3/8", 0.220),
        "3/4": (1.438, 0.396, "1/2", 0.220),
        "7/8": (1.688, 0.468, "9/16", 0.248),
        "1": (1.938, 0.540, "5/8", 0.297),
    },
    ASME_HEX: {
        "1/4": (0.438, 0.163), "5/16": (0.5, 0.211), "3/8": (0.562, 0.243),
        "1/2": (0.75, 0.323), "5/8": (0.938, 0.403), "3/4": (1.125, 0.483),
        "1": (1.5, 0.627),
    },
    ASME_BUTTON: {
        "#0": (0.114, 0.032, "0.035", 0.020), "#1": (0.139, 0.039, "0.050", 0.028),
        "#2": (0.164, 0.046, "0.050", 0.028), "#3": (0.188, 0.052, "1/16", 0.035),
        "#4": (0.213, 0.059, "1/16", 0.035), "#5": (0.238, 0.066, "5/64", 0.044),
        "#6": (0.262, 0.073, "5/64", 0.044), "#8": (0.312, 0.087, "3/32", 0.052),
        "#10": (0.361, 0.101, "1/8", 0.070), "1/4": (0.437, 0.132, "5/32", 0.087),
        "5/16": (0.547, 0.166, "3/16", 0.105), "3/8": (0.656, 0.199, "7/32", 0.122),
        "1/2": (0.875, 0.265, "5/16", 0.175), "5/8": (1.0, 0.331, "3/8", 0.210),
    },
    ASME_PAN: {
        "#2": (0.167, 0.062, 1), "#3": (0.193, 0.071, 1), "#4": (0.219, 0.080, 1),
        "#5": (0.245, 0.089, 2), "#6": (0.270, 0.097, 2), "#8": (0.322, 0.115, 2),
        "#10": (0.373, 0.133, 2), "#12": (0.425, 0.151, 3), "1/4": (0.492, 0.175, 3),
        "5/16": (0.615, 0.218, 4), "3/8": (0.740, 0.261, 4),
    },
    ASME_OVAL: {
        "#2": (0.162, 0.080, 1), "#4": (0.212, 0.104, 1), "#5": (0.237, 0.116, 2),
        "#6": (0.262, 0.128, 2), "#8": (0.312, 0.152, 2), "#10": (0.362, 0.176, 2),
        "#12": (0.412, 0.200, 3), "1/4": (0.477, 0.232, 3),
    },
}
INCH_HEAD_FORMS = {
    ASME_SOCKET: "Cajeado", ASME_FLAT: "Avellanado", ASME_HEX: HEX_HEAD,
    ASME_BUTTON: BUTTON_HEAD, ASME_PAN: PAN_HEAD, ASME_OVAL: OVAL_HEAD,
}


def nominal_inches(size):
    if size.startswith("#"):
        return (60 + 13 * int(size[1:])) / 1000
    return float(sum(Fraction(part) for part in size.split()))


def inch_head_row(head, size):
    table = INCH_HEAD_DIMENSIONS[head]
    if size in table:
        return table[size], 1
    nominal = nominal_inches(size)
    reference = min(table, key=lambda designation: abs(nominal_inches(designation) - nominal))
    return table[reference], nominal / nominal_inches(reference)


def inch_head_dimensions(head, size):
    row, scale = inch_head_row(head, size)
    return row[0] * scale * 25.4, row[1] * scale * 25.4, 82


def inch_allen(head, size, allow_custom=False):
    table = INCH_HEAD_DIMENSIONS.get(head, {})
    row = table.get(size)
    scale = 1
    if row is None and table and size and allow_custom:
        row, scale = inch_head_row(head, size)
    if row and len(row) == 4:
        key = sum(Fraction(part) for part in row[2].split())
        return float(key) * scale * 25.4, row[3] * scale * 25.4
    return None

FIELDS = (
    ("Diametro", "Diámetro", "Length", 6.0),
    ("Profundidad", "Longitud", "Length", 25.0),
    ("DiametroCabeza", "Diámetro de la cabeza", "Length", 10.0),
    ("ProfundidadCabeza", "Profundidad de la cabeza", "Length", 2.0),
    ("AnguloAvellanado", "Ángulo de avellanado", "Angle", 90.0),
    ("Punta", "Punta cónica", "Bool", True),
    ("AnguloPunta", "Ángulo de la punta", "Angle", 118.0),
    ("IncluirPunta", "Incluir punta en la longitud", "Bool", False),
    ("InvertirDireccion", "Cambiar dirección", "Bool", False),
    ("Conica", "Vástago cónico", "Bool", False),
    ("AnguloCono", "Ángulo del vástago con el eje", "Angle", 1.0),
)


def unthreaded_section(head, values):
    diameter, depth, head_diameter, head_depth, head_angle, point, tip_angle, include, reverse, conical, taper = values
    radius = diameter / 2
    if radius <= 0 or depth <= 0 or (point and not 0 < tip_angle < 180) or (conical and not 0 < taper < 90):
        raise ValueError("Comprueba el diámetro, la longitud y los ángulos.")
    slope = math.tan(math.radians(taper)) if conical else 0
    point_slope = math.tan(math.radians(tip_angle / 2)) if point else 0
    length = (depth * point_slope - radius) / (point_slope - slope) if (
        point and include and point_slope > slope) else depth
    end_radius = radius - slope * length
    if length <= 0 or end_radius <= 0 or (point and include and point_slope <= slope):
        raise ValueError("La punta o la conicidad consumen la longitud.")

    section = [(0, 0), (radius, 0)]
    if head != HEADS[0]:
        outer = head_diameter / 2
        vertical = head_depth if head in (*STRAIGHT_HEADS, "Contra-taladro") else 0
        if outer <= radius or vertical < 0:
            raise ValueError("Comprueba el diámetro y la profundidad de la cabeza.")
        crown = head_depth * (0.65 if head == BUTTON_HEAD else 0.35) if head in (BUTTON_HEAD, PAN_HEAD) else 0
        if head in STRAIGHT_HEADS:
            join = vertical
        else:
            if not 0 < head_angle < 180:
                raise ValueError("Comprueba el ángulo de avellanado.")
            bevel = math.tan(math.radians(head_angle / 2))
            if bevel <= slope:
                raise ValueError("El avellanado debe abrirse más que el vástago.")
            join = (outer - radius + bevel * vertical) / (bevel - slope)
            if head == OVAL_HEAD:
                crown = head_depth - join
                join = head_depth
                if crown <= 0:
                    raise ValueError("La altura de la cabeza debe dejar espacio para el abombado.")
        if not 0 < join < length:
            raise ValueError("La cabeza debe terminar antes que el vástago.")
        section = [(0, 0), (outer, crown)]
        if vertical and head != OVAL_HEAD:
            section.append((outer, vertical))
        section.append((radius - slope * join, join))
    section.append((end_radius, length))
    section.append((0, length + (end_radius / point_slope if point else 0)))
    section.append(section[0])
    return section


def unthreaded_volume(head, values):
    section = unthreaded_section(head, values)
    reverse = values[8]
    direction = -1 if reverse else 1
    points = [App.Vector(r, 0, direction * z) for r, z in section]
    if head in DOMED_HEADS:
        radius, rise = section[1]
        if rise <= 0 or rise >= radius:
            raise ValueError("Comprueba la altura y el diámetro de la cabeza abombada.")
        sphere = (radius ** 2 + rise ** 2) / (2 * rise)
        half = radius / 2
        middle = half ** 2 / (sphere + math.sqrt(sphere ** 2 - half ** 2))
        arc = Part.Arc(points[0], App.Vector(half, 0, direction * middle), points[1]).toShape()
        wire = Part.Wire([arc, *Part.makePolygon(points[1:]).Edges])
    else:
        wire = Part.makePolygon(points)
    blank = Part.Face(wire).revolve(App.Vector(), App.Vector(0, 0, 1), 360)
    if head == HEX_HEAD:
        radius = values[2] / math.sqrt(3)
        corners = [App.Vector(radius * math.cos(i * math.pi / 3),
                              radius * math.sin(i * math.pi / 3), 0) for i in range(6)]
        prism = Part.Face(Part.makePolygon([*corners, corners[0]])).extrude(
            App.Vector(0, 0, direction * values[3]))
        blank = blank.fuse(prism).removeSplitter()
    return blank


def profile_positions(profile, body, profile_type=7, offset=None):
    offset = offset if offset is not None else App.Placement()
    if profile is None:
        return [offset]
    shape = profile.Shape.copy()
    shape.Placement = App.Placement()
    edges = shape.Edges
    positions = [edge.Curve.Center for edge in edges if isinstance(edge.Curve, Part.Circle)
                 and profile_type & (2 if edge.isClosed() else 4)]
    if profile_type & 1:
        positions.extend(vertex.Point for vertex in shape.Vertexes
                         if not any(vertex.isSame(end) for edge in edges for end in edge.Vertexes))
    if not positions:
        raise ValueError("Selecciona un croquis con puntos, círculos o arcos.")
    reference = body.getGlobalPlacement().inverse().multiply(profile.getGlobalPlacement())
    return [offset.multiply(App.Placement(reference.multVec(point), reference.Rotation)) for point in positions]


def full_depth_values(values, position, base):
    if base is None or base.Shape.isNull():
        raise ValueError("Para «A través de todo», el Cuerpo necesita un sólido de referencia.")
    bounds = base.Shape.optimalBoundingBox()
    direction = position.Rotation.multVec(App.Vector(0, 0, -1 if values[8] else 1))
    depth = max((App.Vector(x, y, z) - position.Base).dot(direction)
                for x in (bounds.XMin, bounds.XMax) for y in (bounds.YMin, bounds.YMax)
                for z in (bounds.ZMin, bounds.ZMax))
    if depth <= 1e-7:
        raise ValueError("El sólido de referencia queda en la dirección opuesta. Cambia la dirección o usa una cota.")
    adjusted = list(values)
    adjusted[1] = depth
    adjusted[7] = True
    return adjusted


def thread_pitch(family, size, manual_pitch):
    if family == "None":
        return manual_pitch
    if family in ("ISOMetricProfile", "ISOMetricFineProfile"):
        return float(size.split("x", 1)[1])
    return CATALOG[family]["pitches"][size]


def threaded_volume(head, values, thread, removed=None, blank=None):
    family, size, thread_class, left, requested, clearance, pitch = thread
    if values[9]:
        raise ValueError("La rosca requiere un vástago cilíndrico.")
    if pitch <= 0:
        raise ValueError("El paso de rosca debe ser mayor que cero.")
    nominal = values[0]
    normalized = thread_class == "6g"
    if normalized and size != "M8x1.25":
        raise ValueError("La clase 6g está disponible para M8 × 1,25.")
    adjusted = list(values)
    adjusted[8] = False
    section = unthreaded_section(head, adjusted)
    shaft_end, shoulder = section[-3][1], section[-4][1]
    available = shaft_end - shoulder
    length = available if requested is None else requested
    if not 0 < length <= available + 1e-8:
        raise ValueError("La longitud roscada debe caber entre la cabeza y la punta.")
    start = shaft_end - length
    reverse = values[8]
    major = ((MAJOR if normalized else nominal) - clearance) / 2
    pitch_radius = (PITCH_DIAMETER - clearance) / 2 if normalized else None
    if major <= 0:
        raise ValueError("La holgura supera el diámetro del vástago.")
    # Intersect the finished thread at the requested length. Building the
    # initial cylinder at a whole number of pitches avoids near-coincident
    # end edges in the helical boolean.
    working_length = (math.ceil(length / pitch) + 1) * pitch
    outer_radius = nominal / 2 + pitch
    groove = external_thread_groove(pitch, working_length, major, left, pitch_radius=pitch_radius)
    stock = Part.makeCylinder(major, working_length)
    tool = groove.common(Part.makeCylinder(outer_radius, working_length))
    threaded = stock.cut(tool)
    if len(threaded.Solids) != 1 or not threaded.isValid() or not 0 < threaded.Volume < stock.Volume - 1e-9:
        raise ValueError("No se pudo generar una rosca exterior válida.")
    limit = Part.makeCylinder(outer_radius, length)
    threaded = threaded.common(limit)
    rotation = App.Rotation(App.Vector(1, 0, 0), 180).toMatrix() if reverse else None
    if reverse:
        threaded = threaded.transformGeometry(rotation)
    center = App.Vector(0, 0, -start if reverse else start)
    direction = App.Vector(0, 0, -1 if reverse else 1)
    threaded.translate(center)
    if blank is None:
        blank = unthreaded_volume(head, values)
    outer = Part.makeCylinder(outer_radius, length, center, direction)
    result = blank.cut(outer).fuse(threaded).removeSplitter()
    if len(result.Solids) != 1 or not result.isValid() or result.Volume >= blank.Volume - 1e-9:
        raise ValueError("No se pudo generar una rosca exterior válida.")
    if removed is not None:
        # Use the same cutting tool that produced the thread. Subtracting the
        # finished thread from a second cylinder creates near-coincident faces.
        for clipped in (True, False):
            try:
                cut = (tool.common(stock) if clipped else tool).common(limit)
                if cut.isNull() or not cut.isValid() or cut.Volume <= 0:
                    continue
                if major < nominal / 2 - 1e-8:
                    allowance = Part.makeCylinder(nominal / 2, length).cut(Part.makeCylinder(major, length))
                    cut = Part.makeCompound([cut, allowance])
                if rotation is not None:
                    cut.transformShape(rotation, True)
                cut.translate(center)
                removed.append(cut)
                break
            except Part.OCCError:
                continue
    return result


def allen_settings(mode, head_key, diameter, width, depth, family="Según catálogo"):
    if mode == "Allen":
        return width, depth
    if mode == "Automático":
        if family == "Allen":
            return width, depth
        if family == "Según catálogo":
            return ALLEN_HEADS.get(head_key, {}).get(diameter)
    return None


def torx_wire(size, z):
    dimensions = TORX_SIZES.get(size)
    if dimensions is None:
        raise ValueError("Selecciona una medida Torx del catálogo.")
    major, minor = dimensions
    tip_radius = 0.1 * major
    tip_center = major / 2 - tip_radius
    valley = minor / 2
    projected = tip_center * math.cos(math.pi / 6)
    valley_radius = (tip_center ** 2 + valley ** 2 - 2 * valley * projected - tip_radius ** 2) / (
        2 * (tip_radius - valley + projected))

    def radial(r, angle):
        return App.Vector(r * math.cos(angle), r * math.sin(angle), z)

    def tangent(center, other):
        return center + (other - center) * (tip_radius / (tip_radius + valley_radius))

    arcs = []
    for i in range(6):
        angle = i * math.pi / 3
        following = (i + 1) * math.pi / 3
        between = angle + math.pi / 6
        center = radial(tip_center, angle)
        valley_center = radial(valley + valley_radius, between)
        left = tangent(center, radial(valley + valley_radius, angle - math.pi / 6))
        right = tangent(center, valley_center)
        end = tangent(radial(tip_center, following), valley_center)
        arcs.append(Part.Arc(left, radial(major / 2, angle), right).toShape())
        arcs.append(Part.Arc(right, radial(valley, between), end).toShape())
    return Part.Wire(arcs)


def screw_volume(head, values, thread, drive=None, cuts=None):
    if drive is None:
        return threaded_volume(head, values, thread, cuts) if thread else unthreaded_volume(head, values)
    family, size, depth, *details = drive
    if head == HEADS[0] or size <= 0 or depth <= 0:
        raise ValueError("El alojamiento necesita una cabeza y cotas positivas.")
    direction = -1 if values[8] else 1
    body_section = unthreaded_section(head, values)
    cross_drive = family in (*CROSS_DRIVES, JIS_S)
    limit = body_section[-3 if cross_drive else -4][1]
    if depth >= limit - 1e-7:
        raise ValueError("La profundidad debe dejar material debajo del alojamiento.")
    start = -direction * 0.001
    if family == SPANNER:
        spacing, = details
        if spacing <= size:
            raise ValueError("La distancia entre centros debe ser mayor que el diámetro de los orificios.")
        axis = App.Vector(0, 0, direction)
        tool = Part.makeCompound([
            Part.makeCylinder(size / 2, depth + 0.001, App.Vector(x, 0, start), axis)
            for x in (-spacing / 2, spacing / 2)
        ])
        expected = 2 * math.pi * (size / 2) ** 2 * depth
    elif family == SLOT:
        width_at_floor = min(radius * 2 for radius, z in body_section[1:-2] if z <= depth
                             or z == body_section[-4][1])
        if size >= width_at_floor:
            raise ValueError("El ancho de la ranura debe dejar material a ambos lados.")
        half_length = values[2]
        tool = Part.makeBox(2 * half_length, size, depth + 0.001,
                            App.Vector(-half_length, -size / 2, min(start, direction * depth)))
    elif cross_drive:
        arm_ratio = 0.095 if family == JIS_S else 0.13

        def cross(span, z):
            length = span / 2
            arm = span * arm_ratio
            points = [(arm, length), (-arm, length), (-arm, arm), (-length, arm),
                      (-length, -arm), (-arm, -arm), (-arm, -length), (arm, -length),
                      (arm, -arm), (length, -arm), (length, arm), (arm, arm)]
            return Part.makePolygon([App.Vector(x, y, z) for x, y in (*points, points[0])])

        opening = cross(size, 0)
        floor_scale = 0.24 if family == JIS_S else 0.36
        floor = cross(size * floor_scale, direction * depth)
        recess = Part.makeLoft([opening, floor], True, True)
        extension = Part.Face(opening).extrude(App.Vector(0, 0, start))
        tool = recess.fuse(extension)
        expected = recess.Volume
        if family == POZIDRIV:
            grooves = []
            extensions = []
            for corner in range(4):
                angle = math.pi / 4 + corner * math.pi / 2
                radial = App.Vector(math.cos(angle), math.sin(angle), 0)
                tangent = App.Vector(-radial.y, radial.x, 0)

                cross_corner = math.sqrt(2) * arm_ratio * size
                half_width = 0.065 * size
                # Embed both shoulders in the cross so the walls intersect
                # the outer slopes, without exposing a second pair of facets.
                inward = 0.045 * size
                shoulder = (cross_corner + half_width - inward) * radial
                points = [0.08 * size * radial, shoulder - half_width * tangent,
                          (0.43 * size - inward) * radial, shoulder + half_width * tangent]
                entry = Part.makePolygon([*points, points[0]])
                fraction = 0.24
                corner_radius = cross_corner * (1 - (1 - floor_scale) * fraction)
                end = Part.Vertex(corner_radius * radial + App.Vector(0, 0, direction * depth * fraction))
                grooves.append(Part.makeLoft([entry, end], True, True))
                extensions.append(Part.Face(entry).extrude(App.Vector(0, 0, start)))
            recess = recess.fuse(grooves).removeSplitter()
            expected = recess.Volume
            tool = recess.fuse([extension, *extensions]).removeSplitter()
    elif family in TORX_DRIVES:
        wire = torx_wire(size, start)
    else:
        sides = 4 if family == ROBERTSON else 6
        step = 2 * math.pi / sides
        radius = size / (2 * math.cos(step / 2))
        rotation = step / 2 if family == ROBERTSON else 0
        corners = [App.Vector(radius * math.cos(rotation + i * step),
                              radius * math.sin(rotation + i * step), start) for i in range(sides)]
        wire = Part.makePolygon([*corners, corners[0]])
    if not cross_drive and family not in (SLOT, SPANNER):
        face = Part.Face(wire)
        tool = face.extrude(App.Vector(0, 0, direction * (depth + 0.001)))
        expected = face.Area * depth
        if family == TORX_BO:
            pin_radius = TORX_SIZES[size][1] * 0.15
            pin = Part.makeCylinder(pin_radius, depth + 0.003,
                                    App.Vector(0, 0, start - direction * 0.001),
                                    App.Vector(0, 0, direction))
            tool = tool.cut(pin)
            expected -= math.pi * pin_radius ** 2 * depth
    blank = unthreaded_volume(head, values)
    result = blank.cut(tool).removeSplitter()
    removed_volume = blank.Volume - result.Volume
    if (len(result.Solids) != 1 or not result.isValid()
            or removed_volume <= 0
            or (family != SLOT and head not in DOMED_HEADS
                and abs(removed_volume - expected) > max(1e-6, expected * 1e-5))):
        raise ValueError("El alojamiento debe caber por completo en la cabeza.")
    if cuts is not None:
        cuts.append(blank.common(tool))
    return threaded_volume(head, values, thread, cuts, blank=result) if thread else result


def addition_shape(head, values, profile, body, profile_type=7, through_all=False, base=None,
                   thread=None, removed=None, offset=None, local_shape=None, drive=None):
    placements = profile_positions(profile, body, profile_type, offset)
    def volume(dimensions, cuts):
        return screw_volume(head, dimensions, thread, drive, cuts)

    shared_cuts = [] if removed is not None else None
    solid = local_shape if local_shape is not None else (None if through_all else volume(values, shared_cuts))
    solids = []
    for position in placements:
        cuts = shared_cuts
        if through_all:
            cuts = [] if removed is not None else None
            shape = volume(full_depth_values(values, position, base), cuts)
        else:
            shape = solid.copy()
        matrix = position.toMatrix() if not position.isIdentity() else None
        if matrix is not None:
            shape.transformShape(matrix, True)
        solids.append(shape)
        if cuts:
            for cut in cuts:
                positioned_cut = cut.copy()
                if matrix is not None:
                    positioned_cut.transformShape(matrix, True)
                removed.append(positioned_cut)
    return solids[0] if len(solids) == 1 else solids[0].fuse(solids[1:]).removeSplitter()


def hole_result(addition, base, body):
    if body is None or not body.AllowCompound:
        return additive_result(addition, base)
    result = (addition if base is None or base.Shape.isNull()
              else base.Shape.fuse(addition).removeSplitter())
    if not result.Solids or not result.isValid():
        raise ValueError("La posición no produce un resultado válido en el Cuerpo.")
    return result


class PositiveHole:
    def __init__(self, feature):
        feature.addProperty("App::PropertyEnumeration", "Cabeza", "Agujero")
        feature.Cabeza = list(HEADS)
        for name, description, kind, value in FIELDS:
            feature.addProperty("App::Property" + kind, name, "Agujero", description)
            setattr(feature, name, value)
        feature.addProperty("App::PropertyString", "HerramientaOrigen", "AÑADIR")
        feature.HerramientaOrigen = "Añadir"
        feature.setEditorMode("HerramientaOrigen", 2)
        feature.Proxy = self
        self.add_catalog_properties(feature)

    @staticmethod
    def add_catalog_properties(feature):
        if tuple(feature.getEnumerationsOfProperty("Cabeza")) != HEADS:
            previous = feature.Cabeza
            feature.Cabeza = list(HEADS)
            feature.Cabeza = previous
        for kind, name, default in (
            ("String", "Estandar", "None"), ("String", "Tamano", ""),
            ("String", "TipoCabeza", ""),
            ("String", "TipoLlave", "Nada"), ("String", "FamiliaLlave", "Según catálogo"),
            ("Length", "MedidaAllen", 4.0),
            ("Length", "ProfundidadAllen", 2.0),
            ("Integer", "MedidaTorx", 20), ("Length", "ProfundidadTorx", 1.27),
            ("Integer", "MedidaPhillips", 2), ("Length", "ProfundidadPhillips", 2.1),
            ("Integer", "MedidaPozidriv", 2), ("Length", "ProfundidadPozidriv", 2.06),
            ("Length", "AnchoRanura", 1.6), ("Length", "ProfundidadRanura", 1.2),
            ("Length", "MedidaRobertson", 2.4), ("Length", "ProfundidadRobertson", 1.2),
            ("Length", "DiametroSpanner", 1.2), ("Length", "DistanciaSpanner", 3.0),
            ("Length", "ProfundidadSpanner", 1.2),
            ("Length", "MedidaCruzS", 1.45), ("Length", "ProfundidadCruzS", 0.87),
            ("Bool", "AtraviesaTodo", False), ("Bool", "CabezaPersonalizada", False),
            ("Bool", "ModelarRosca", False), ("String", "ClaseRosca", ""),
            ("Bool", "RoscaIzquierda", False), ("Bool", "RoscaCompleta", True),
            ("Length", "PasoRosca", 1.0), ("Length", "LongitudRosca", 10.0),
            ("Bool", "HolguraPersonalizada", False),
            ("Length", "HolguraRosca", 0.0), ("Bool", "PrevisualizarRosca", False),
        ):
            if name not in feature.PropertiesList:
                feature.addProperty("App::Property" + kind, name, "Agujero")
                setattr(feature, name, default)
        if "PosicionTornillo" not in feature.PropertiesList:
            feature.addProperty("App::PropertyPlacement", "PosicionTornillo", POSITION_GROUP,
                                "Traslación y giro respecto al centro de la cara superior de la cabeza.")
        elif feature.getGroupOfProperty("PosicionTornillo") != POSITION_GROUP:
            feature.setGroupOfProperty("PosicionTornillo", POSITION_GROUP)
        for name in ("Perfil", "TipoPerfil", "ClaseRosca"):
            if name in feature.PropertiesList:
                feature.setEditorMode(name, 2)

    def onDocumentRestored(self, feature):
        self.add_catalog_properties(feature)
        if App.GuiUp:
            install_live_position_editor()

    def onChanged(self, feature, property_name):
        if property_name != "PosicionTornillo" or not App.GuiUp or getattr(self, "_pose_pending", False):
            return
        from PySide import QtCore

        document_name = feature.Document.Name
        feature_name = feature.Name
        self._pose_pending = True

        def update_position():
            self._pose_pending = False
            document = App.listDocuments().get(document_name)
            if document is not None and not document.Recomputing and document.getObject(feature_name):
                document.recompute()

        QtCore.QTimer.singleShot(0, update_position)

    def execute(self, feature):
        pending = self.__dict__.pop("pending", None)
        if pending is None:
            values = [getattr(feature, name) if kind == "Bool" else getattr(feature, name).Value
                      for name, _, kind, _ in FIELDS]
            thread = None
            if getattr(feature, "ModelarRosca", False):
                thread = (feature.Estandar, feature.Tamano, feature.ClaseRosca, feature.RoscaIzquierda,
                          None if feature.RoscaCompleta else feature.LongitudRosca.Value,
                          feature.HolguraRosca.Value if feature.HolguraPersonalizada else 0,
                          thread_pitch(feature.Estandar, feature.Tamano, feature.PasoRosca.Value))
            body = feature.getParentGeoFeatureGroup()
            allen = allen_settings(feature.TipoLlave, feature.TipoCabeza, values[0],
                                   feature.MedidaAllen.Value, feature.ProfundidadAllen.Value, feature.FamiliaLlave)
            drive = ("Allen", *allen) if allen else None
            if feature.TipoLlave == "Automático" and feature.FamiliaLlave in TORX_DRIVES:
                drive = (feature.FamiliaLlave, feature.MedidaTorx, feature.ProfundidadTorx.Value)
            if feature.TipoLlave == "Automático" and feature.FamiliaLlave in CROSS_DRIVES:
                family = feature.FamiliaLlave
                number = feature.MedidaPozidriv if family == POZIDRIV else feature.MedidaPhillips
                depth = feature.ProfundidadPozidriv if family == POZIDRIV else feature.ProfundidadPhillips
                drive = (family, cross_span(family, feature.TipoCabeza, values[0], number), depth.Value)
            if feature.TipoLlave == "Automático" and feature.FamiliaLlave == SLOT:
                drive = (SLOT, feature.AnchoRanura.Value, feature.ProfundidadRanura.Value)
            if feature.TipoLlave == "Automático" and feature.FamiliaLlave == ROBERTSON:
                drive = (ROBERTSON, feature.MedidaRobertson.Value, feature.ProfundidadRobertson.Value)
            if feature.TipoLlave == "Automático" and feature.FamiliaLlave == SPANNER:
                drive = (SPANNER, feature.DiametroSpanner.Value, feature.ProfundidadSpanner.Value,
                         feature.DistanciaSpanner.Value)
            if feature.TipoLlave == "Automático" and feature.FamiliaLlave == JIS_S:
                drive = (JIS_S, feature.MedidaCruzS.Value, feature.ProfundidadCruzS.Value)
            through_all = getattr(feature, "AtraviesaTodo", False)
            local = None
            if not through_all:
                # The profile and PosicionTornillo only place the solid. A
                # change to either need not rebuild the helical cut.
                key = (feature.Cabeza, tuple(values), thread, drive)
                cache = getattr(self, "_local_shape", None)
                if cache is None or cache[0] != key:
                    local = screw_volume(feature.Cabeza, values, thread, drive)
                    self._local_shape = (key, local)
                else:
                    local = cache[1]
            addition = addition_shape(feature.Cabeza, values, getattr(feature, "Perfil", None), body,
                                      getattr(feature, "TipoPerfil", 7), through_all, feature.BaseFeature,
                                      thread, offset=feature.PosicionTornillo, local_shape=local, drive=drive)
            result = hole_result(addition, feature.BaseFeature, body)
        else:
            addition, result = pending
        feature.AddSubShape = addition
        feature.Shape = result

    def dumps(self):
        return None

    def loads(self, _state):
        pass


class PositiveHoleView(ScrewView):
    def __init__(self, view):
        super().__init__(view)
        install_live_position_editor()

    def setEdit(self, view, mode=0):
        import FreeCADGui as Gui

        if mode != 0 or Gui.Control.activeDialog():
            return False
        feature = view.Object
        self.panel = open_add_hole(feature.Document, feature.getParentGeoFeatureGroup(), feature=feature)
        return True


def install_live_position_editor():
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets
    from shiboken6 import isValid

    global live_position_editor
    if "live_position_editor" in globals():
        return

    class LivePositionEditor(QtCore.QObject):
        def eventFilter(self, watched, event):
            if event.type() == QtCore.QEvent.Show and isinstance(watched, QtWidgets.QAbstractSpinBox):
                QtCore.QTimer.singleShot(0, lambda spin=watched: self.connect_spin(spin))
            return False

        def connect_spin(self, spin):
            if not isValid(spin) or spin.property("AddHoleLivePosition"):
                return
            parent = spin.parentWidget()
            while parent is not None and not isinstance(parent, QtWidgets.QTreeView):
                parent = parent.parentWidget()
            if parent is None:
                return
            index = parent.indexAt(spin.mapTo(parent.viewport(), spin.rect().center()))
            if not index.isValid():
                return
            prop = index
            while prop.isValid():
                label = str(prop.siblingAtColumn(0).data()).replace(" ", "").casefold()
                if label == "posiciontornillo":
                    break
                prop = prop.parent()
            if not prop.isValid():
                return
            line = spin.findChild(QtWidgets.QLineEdit)
            if not hasattr(spin, "valueChanged") and line is None:
                return
            spin.setProperty("AddHoleLivePosition", True)
            delegate = parent.itemDelegateForIndex(index)
            reference = QtCore.QPersistentModelIndex(index)

            def commit():
                if (isValid(spin) and isValid(delegate) and reference.isValid()
                        and spin.hasAcceptableInput()):
                    delegate.setModelData(spin, parent.model(), QtCore.QModelIndex(reference))

            if hasattr(spin, "valueChanged"):
                spin.valueChanged.connect(commit)
            else:
                line.textChanged.connect(lambda *_: QtCore.QTimer.singleShot(0, commit))

    live_position_editor = LivePositionEditor(Gui.getMainWindow())
    QtWidgets.QApplication.instance().installEventFilter(live_position_editor)


def open_add_hole(document, body=None, feature=None, *, inline=False):
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets
    from .add_material_visual import PlacementFields
    from .remove_material_visual import shape_scene_node

    profile = getattr(feature, "Perfil", None)
    profile_type = getattr(feature, "TipoPerfil", 7)

    class SectionDiagram(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.section = []
            self.setMinimumSize(76, 110)
            self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
            self.setAccessibleName("Sección del agujero aditivo")

        def paintEvent(self, event):
            if not self.section:
                return
            width, height = self.width(), self.height()
            axis = width / 2
            radius = max(r for r, _ in self.section)
            length = max(z for _, z in self.section)
            scale_x = (width / 2 - 12) / radius
            scale_z = (height - 26) / length
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            ink = self.palette().color(QtGui.QPalette.WindowText)
            right = [QtCore.QPointF(axis + r * scale_x, 12 + z * scale_z)
                     for r, z in self.section[1:-1]]
            left = [QtCore.QPointF(2 * axis - p.x(), p.y()) for p in right]
            painter.setPen(QtCore.Qt.NoPen)
            wash = QtGui.QColor(ink)
            wash.setAlpha(28)
            painter.setBrush(wash)
            painter.drawPolygon(QtGui.QPolygonF(right + left[::-1]))
            painter.setPen(QtGui.QPen(ink, 1.5))
            for points in (left, right):
                painter.drawPolyline(QtGui.QPolygonF(points))
            painter.drawLine(QtCore.QPointF(8, 12), QtCore.QPointF(width - 8, 12))
            painter.setPen(QtGui.QPen(ink, 0.8, QtCore.Qt.DashLine))
            painter.drawLine(QtCore.QPointF(axis, 4), QtCore.QPointF(axis, height - 4))

    class Editor:
        def __init__(self):
            self.root = self.node = None
            self.preview_cache = None
            self.saved_visibility = None
            self.form = QtWidgets.QWidget()
            self.form.setWindowTitle("Tornillo")
            self.form.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)
            layout = QtWidgets.QVBoxLayout(self.form)
            layout.setContentsMargins(0, 0, 0, 0)
            parameters = QtWidgets.QGroupBox("Parámetros del tornillo")
            layout.addWidget(parameters)
            parameters_layout = QtWidgets.QVBoxLayout(parameters)
            self.position_fields = PlacementFields(
                self.form, "Posición del tornillo", "Ángulo del tornillo",
                lambda: self.timer.start(35))
            self.position_fields.load_placement(getattr(feature, "PosicionTornillo", App.Placement()))
            parameters_layout.addWidget(self.position_fields)
            form = QtWidgets.QFormLayout()
            parameters_layout.addLayout(form)
            self.standard = QtWidgets.QComboBox()
            for key, label in FAMILIES.items():
                self.standard.addItem(label, key)
            form.addRow("Estándar", self.standard)
            self.size = QtWidgets.QComboBox()
            form.addRow("Tamaño", self.size)
            self.head = QtWidgets.QComboBox()
            form.addRow("Tipo de cabeza", self.head)
            self.drive = QtWidgets.QComboBox()
            self.drive.addItems(["Automático", "Nada"])
            saved_mode = getattr(feature, "TipoLlave", "Automático")
            self.drive.setCurrentText("Nada" if saved_mode == "Nada" else "Automático")
            form.addRow("Tipo de llave", self.drive)
            self.drive_family = QtWidgets.QComboBox()
            form.addRow("Familia", self.drive_family)
            self.allen_width = QtWidgets.QDoubleSpinBox()
            self.allen_width.setRange(0.001, 1000)
            self.allen_width.setDecimals(3)
            self.allen_width.setSuffix(" mm")
            width = getattr(getattr(feature, "MedidaAllen", None), "Value", 4.0)
            self.allen_width.setValue(width)
            self.allen_depth = QtWidgets.QDoubleSpinBox()
            self.allen_depth.setRange(0.001, 1000)
            self.allen_depth.setDecimals(3)
            self.allen_depth.setSuffix(" mm")
            self.allen_depth.setValue(getattr(getattr(feature, "ProfundidadAllen", None), "Value", 2.0))
            self.torx_size = QtWidgets.QComboBox()
            for size in TORX_SIZES:
                self.torx_size.addItem(f"T{size}", size)
            self.torx_size.setCurrentIndex(max(0, self.torx_size.findData(getattr(feature, "MedidaTorx", 20))))
            self.drive_measure = QtWidgets.QStackedWidget()
            self.drive_measure.addWidget(self.allen_width)
            self.drive_measure.addWidget(self.torx_size)
            self.phillips_size = QtWidgets.QComboBox()
            for number in range(len(PHILLIPS_WIDTHS)):
                self.phillips_size.addItem(f"PH{number}", number)
            self.phillips_size.setCurrentIndex(max(0, self.phillips_size.findData(getattr(feature, "MedidaPhillips", 2))))
            self.drive_measure.addWidget(self.phillips_size)
            self.drive_measure_label = QtWidgets.QLabel("Medida entre caras")
            form.addRow(self.drive_measure_label, self.drive_measure)
            self.spanner_spacing = QtWidgets.QDoubleSpinBox()
            self.spanner_spacing.setRange(0.001, 1000)
            self.spanner_spacing.setDecimals(3)
            self.spanner_spacing.setSuffix(" mm")
            self.spanner_spacing.setValue(getattr(getattr(feature, "DistanciaSpanner", None), "Value", 3.0))
            self.spanner_spacing_label = QtWidgets.QLabel("Distancia entre centros")
            form.addRow(self.spanner_spacing_label, self.spanner_spacing)
            form.addRow("Profundidad del alojamiento", self.allen_depth)
            self.drive_context = None
            self.depth_type = QtWidgets.QComboBox()
            self.depth_type.addItems(["Cota", "A través de todo"])
            self.depth_type.setCurrentIndex(int(getattr(feature, "AtraviesaTodo", False)))
            form.addRow("Tipo de profundidad", self.depth_type)
            self.custom_head = QtWidgets.QCheckBox("Cotas de cabeza personalizadas")
            self.custom_head.setChecked(getattr(feature, "CabezaPersonalizada", False))
            form.addRow(self.custom_head)
            self.fields = {}
            self.dimension_labels = {}
            for name, label, kind, default in FIELDS:
                value = getattr(feature, name) if feature is not None else default
                if kind == "Bool":
                    field = QtWidgets.QCheckBox(label)
                    field.setChecked(value)
                    field.toggled.connect(self.update)
                else:
                    field = QtWidgets.QDoubleSpinBox()
                    field.setDecimals(3)
                    field.setRange(0, 179.999 if kind == "Angle" else 10000)
                    field.setSuffix("°" if kind == "Angle" else " mm")
                    field.setValue(value.Value if feature is not None else value)
                    field.valueChanged.connect(self.update)
                self.fields[name] = field
            grid = QtWidgets.QGridLayout()
            parameters_layout.addLayout(grid)

            def place(name, row, column):
                field = self.fields[name]
                if isinstance(field, QtWidgets.QCheckBox):
                    grid.addWidget(field, row, column)
                else:
                    section = QtWidgets.QWidget()
                    stack = QtWidgets.QVBoxLayout(section)
                    stack.setContentsMargins(0, 0, 0, 0)
                    label = QtWidgets.QLabel(next(title for key, title, _, _ in FIELDS if key == name))
                    self.dimension_labels[name] = label
                    label.setBuddy(field)
                    stack.addWidget(label)
                    stack.addWidget(field)
                    grid.addWidget(section, row, column)

            for row, name in enumerate(("DiametroCabeza", "ProfundidadCabeza", "Punta",
                                        "AnguloPunta", "IncluirPunta", "InvertirDireccion")):
                place(name, row, 0)
            for row, name in ((0, "AnguloAvellanado"), (1, "Profundidad"), (3, "Diametro"),
                              (4, "Conica"), (5, "AnguloCono")):
                place(name, row, 2)
            self.diagram = SectionDiagram()
            grid.addWidget(self.diagram, 0, 1, 6, 1)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(2, 1)

            thread_box = QtWidgets.QGroupBox("Rosca")
            thread_form = QtWidgets.QFormLayout(thread_box)
            self.thread_enabled = QtWidgets.QCheckBox("Modelar rosca")
            self.thread_enabled.setChecked(getattr(feature, "ModelarRosca", False))
            self.thread_preview = QtWidgets.QCheckBox("Mostrar rosca en el resultado final")
            self.thread_preview.setChecked(getattr(feature, "PrevisualizarRosca", False))
            self.thread_hand = QtWidgets.QComboBox()
            self.thread_hand.addItems(["Derecha", "Izquierda"])
            self.thread_hand.setCurrentIndex(int(getattr(feature, "RoscaIzquierda", False)))
            self.thread_depth = QtWidgets.QComboBox()
            self.thread_depth.addItems(["Longitud útil del vástago", "Cota"])
            self.thread_depth.setCurrentIndex(int(not getattr(feature, "RoscaCompleta", True)))
            self.thread_length = QtWidgets.QDoubleSpinBox()
            self.thread_clearance = QtWidgets.QDoubleSpinBox()
            self.thread_pitch = QtWidgets.QDoubleSpinBox()
            self.thread_pitch.setRange(0.001, 1000)
            self.thread_pitch.setDecimals(4)
            self.thread_pitch.setSuffix(" mm")
            self.manual_pitch = getattr(getattr(feature, "PasoRosca", None), "Value", 1.0)
            self.custom_clearance = QtWidgets.QCheckBox("Holgura personalizada")
            self.custom_clearance.setChecked(getattr(feature, "HolguraPersonalizada", False))
            for field, name, default in ((self.thread_length, "LongitudRosca", 10),
                                         (self.thread_clearance, "HolguraRosca", 0)):
                field.setDecimals(3)
                field.setRange(0, 10000)
                field.setSuffix(" mm")
                stored = getattr(feature, name, None)
                field.setValue(stored.Value if stored is not None else default)
            thread_form.addRow(self.thread_enabled)
            thread_form.addRow("Paso de rosca", self.thread_pitch)
            thread_form.addRow("Sentido de rosca", self.thread_hand)
            thread_form.addRow(self.thread_preview)
            thread_form.addRow("Tipo de profundidad de rosca", self.thread_depth)
            thread_form.addRow("Longitud roscada desde la punta", self.thread_length)
            thread_form.addRow(self.custom_clearance, self.thread_clearance)
            self.thread_note = QtWidgets.QLabel()
            self.thread_note.setWordWrap(True)
            thread_form.addRow(self.thread_note)
            layout.addWidget(thread_box)

            preview_box = QtWidgets.QGroupBox("Pre-visualizar")
            preview_layout = QtWidgets.QVBoxLayout(preview_box)
            self.final_preview = QtWidgets.QCheckBox("Mostrar resultado final")
            self.final_preview.toggled.connect(self.update)
            preview_layout.addWidget(self.final_preview)
            self.preview = QtWidgets.QCheckBox("Mostrar volumen añadido y vaciados")
            self.preview.setChecked(True)
            self.preview.toggled.connect(self.update)
            preview_layout.addWidget(self.preview)
            layout.addWidget(preview_box)
            self.status = QtWidgets.QLabel()
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.timer = QtCore.QTimer(self.form)
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.refresh_preview)
            family = getattr(feature, "Estandar", "None")
            self.standard.setCurrentIndex(max(0, self.standard.findData(family)))
            legacy_head = next((key for key, form in MANUAL_HEADS.items()
                                if feature and form == feature.Cabeza), "None")
            self.load_family(getattr(feature, "Tamano", ""),
                             getattr(feature, "TipoCabeza", "") or legacy_head)
            saved_family = "Allen" if saved_mode == "Allen" else getattr(feature, "FamiliaLlave", "Según catálogo")
            self.update_drive_catalog(saved_family)
            self.standard.currentIndexChanged.connect(lambda: self.change_family())
            self.size.currentIndexChanged.connect(self.update_from_catalog)
            self.head.currentIndexChanged.connect(self.update_from_catalog)
            self.drive.currentIndexChanged.connect(self.update)
            self.drive_family.currentIndexChanged.connect(self.change_drive_family)
            self.torx_size.currentIndexChanged.connect(self.update)
            self.phillips_size.currentIndexChanged.connect(self.update)
            self.allen_width.valueChanged.connect(self.update)
            self.allen_depth.valueChanged.connect(self.update)
            self.spanner_spacing.valueChanged.connect(self.update)
            self.custom_head.toggled.connect(self.update_from_catalog)
            self.depth_type.currentIndexChanged.connect(self.update)
            for field in (self.thread_enabled, self.thread_preview, self.custom_clearance):
                field.toggled.connect(self.update)
            for field in (self.thread_hand, self.thread_depth):
                field.currentIndexChanged.connect(self.update)
            for field in (self.thread_length, self.thread_clearance):
                field.valueChanged.connect(self.update)
            self.thread_pitch.valueChanged.connect(self.change_manual_pitch)
            self.update()

        def placement(self):
            return self.position_fields.placement()

        def thread_class(self):
            family, size = self.standard.currentData(), self.size.currentData()
            if family == getattr(feature, "Estandar", None) and size == getattr(feature, "Tamano", None):
                saved = getattr(feature, "ClaseRosca", "")
                if saved:
                    return saved
            return "6g" if size == "M8x1.25" else "Perfil básico"
        def thread_settings(self):
            if not self.thread_enabled.isEnabled() or not self.thread_enabled.isChecked():
                return None
            return (self.standard.currentData(), self.size.currentData(), self.thread_class(),
                    bool(self.thread_hand.currentIndex()),
                    self.thread_length.value() if self.thread_depth.currentIndex() else None,
                    self.thread_clearance.value() if self.custom_clearance.isChecked() else 0,
                    thread_pitch(self.standard.currentData(), self.size.currentData(), self.manual_pitch))

        def change_manual_pitch(self, value):
            self.manual_pitch = value
            self.update()

        def load_family(self, size="", head="None"):
            family = CATALOG.get(self.standard.currentData())
            for box in (self.size, self.head):
                box.blockSignals(True)
                box.clear()
            if family is not None:
                for designation in family["sizes"]:
                    self.size.addItem(designation, designation)
                self.size.setCurrentIndex(max(0, self.size.findData(size)))
            for key, title in (family["heads"] if family else MANUAL_HEADS).items():
                self.head.addItem(HEAD_TITLES.get(key, MANUAL_HEADS.get(key, key)), (key, title))
            if family is None:
                self.head.addItem("Hexagonal manual", ("Hexagonal manual", HEX_HEAD))
            self.update_standard_head_options()
            self.head.setCurrentIndex(max(0, next((i for i in range(self.head.count())
                                                  if self.head.itemData(i)[0] == head), 0)))
            for box in (self.size, self.head):
                box.blockSignals(False)

        def change_family(self):
            self.load_family(self.size.currentData(), self.head.currentData()[0])
            self.update_from_catalog()

        def update_standard_head_options(self):
            family = self.standard.currentData()
            size = self.size.currentData()
            options = {ISO_HEX_HEAD: HEX_HEAD, **INCH_HEAD_FORMS, **METRIC_DOME_FORMS}
            with QtCore.QSignalBlocker(self.head):
                for key, form in options.items():
                    option = (key, form)
                    index = next((i for i in range(self.head.count()) if self.head.itemData(i) == option), -1)
                    if key == ISO_HEX_HEAD:
                        available = family == "ISOMetricProfile" and size and (
                            CATALOG[family]["sizes"][size][0] in ISO_HEX_DIMENSIONS)
                        title = HEAD_TITLES[key]
                    elif key in METRIC_DOME_FORMS:
                        available = family == "ISOMetricProfile" and bool(size)
                        diameter = CATALOG[family]["sizes"][size][0] if available else None
                        title = HEAD_TITLES[key] if diameter in METRIC_DOME_DIMENSIONS[key] else form + " personalizada"
                    else:
                        available = family in INCH_FAMILIES and bool(size)
                        if size not in INCH_HEAD_DIMENSIONS[key]:
                            title = key.split(" · ", 1)[0] + " personalizada"
                        else:
                            title = key + (" (referencia)" if family == "UNEF" else "")
                    if available and index < 0:
                        self.head.addItem(title, option)
                    elif available and self.head.itemText(index) != title:
                        self.head.setItemText(index, title)
                    elif not available and index >= 0:
                        self.head.removeItem(index)

        def update_from_catalog(self):
            self.update_standard_head_options()
            family = CATALOG.get(self.standard.currentData())
            if family is not None and self.size.currentData():
                diameter, heads = family["sizes"][self.size.currentData()]
                self.fields["Diametro"].setValue(diameter)
                head = self.head.currentData()[0]
                if head == ISO_HEX_HEAD:
                    dimensions = ISO_HEX_DIMENSIONS[diameter]
                elif head in INCH_HEAD_DIMENSIONS:
                    dimensions = inch_head_dimensions(head, self.size.currentData())
                elif head in METRIC_DOME_DIMENSIONS:
                    dimensions = metric_dome_dimensions(head, diameter)
                else:
                    dimensions = heads.get(head)
                if dimensions and not self.custom_head.isChecked():
                    for name, value in zip(("DiametroCabeza", "ProfundidadCabeza", "AnguloAvellanado"), dimensions):
                        self.fields[name].setValue(value)
            if self.drive_context != self.drive_catalog_key():
                family = self.drive_family.currentText()
                keep_allen = (family == "Allen" and self.drive_context
                              and self.drive_catalog_key()[2] in METRIC_DOME_FORMS
                              and self.drive_context[2] in METRIC_DOME_FORMS)
                if not keep_allen and family not in (*TORX_DRIVES, SLOT, ROBERTSON, SPANNER, JIS_S, *CROSS_DRIVES):
                    family = "Según catálogo"
                self.update_drive_catalog(family, recalculate=True)
            self.update()

        def drive_catalog_key(self):
            return self.standard.currentData(), self.size.currentData(), self.head.currentData()[0]

        def update_drive_catalog(self, saved_family="Según catálogo", recalculate=False):
            self.drive_context = self.drive_catalog_key()
            standard, size, head_key = self.drive_context
            head = self.head.currentData()[1]
            family = CATALOG.get(standard)
            diameter = family["sizes"][size][0] if family is not None and size else None
            preset = inch_allen(head_key, size, allow_custom=True) or ALLEN_HEADS.get(head_key, {}).get(diameter)
            if head_key == ISO_BUTTON:
                preset = metric_button_allen(diameter)
            torx = head_key == ISO_PAN or (head_key in TORX_CATALOG_HEADS and diameter in TORX_ISO_14583)
            phillips = head_key == "ISO 7046" and diameter in PHILLIPS_ISO_7046
            phillips = phillips or head_key in (ASME_PAN, ASME_OVAL, ISO_OVAL)
            slot = head_key == "ISO 2009" and diameter in SLOT_ISO_2009
            default = ("Allen" if preset else "Torx" if torx else PHILLIPS if phillips else SLOT if slot
                       else "Hexagonal exterior" if head == HEX_HEAD else "Sin asignar")
            with QtCore.QSignalBlocker(self.drive_family), QtCore.QSignalBlocker(self.allen_width), QtCore.QSignalBlocker(self.allen_depth), QtCore.QSignalBlocker(self.torx_size):
                self.drive_family.clear()
                self.drive_family.addItem("Sin asignar")
                if head != HEADS[0]:
                    self.drive_family.addItem("Allen")
                    self.drive_family.addItem("Torx")
                    self.drive_family.addItem(TORX_BO)
                    self.drive_family.addItem(PHILLIPS)
                    self.drive_family.addItem(POZIDRIV)
                    self.drive_family.addItem(JIS_S)
                    self.drive_family.addItem(SLOT)
                    self.drive_family.addItem(ROBERTSON)
                    self.drive_family.addItem(SPANNER)
                if head == HEX_HEAD:
                    self.drive_family.addItem("Hexagonal exterior")
                choice = saved_family if self.drive_family.findText(saved_family) >= 0 else default
                self.drive_family.setCurrentText(choice)
                if preset and saved_family == "Según catálogo":
                    self.allen_width.setValue(preset[0])
                    self.allen_depth.setValue(preset[1])
                elif choice == "Allen" and recalculate and head_key in METRIC_DOME_FORMS:
                    self.load_allen_suggestion()
                if choice in TORX_DRIVES:
                    if recalculate or saved_family == "Según catálogo":
                        self.load_torx_suggestion()
                    else:
                        self.allen_depth.setValue(getattr(getattr(feature, "ProfundidadTorx", None), "Value", 1.27))
                if choice in CROSS_DRIVES:
                    if recalculate or saved_family == "Según catálogo":
                        self.load_cross_suggestion()
                    else:
                        name = "Pozidriv" if choice == POZIDRIV else "Phillips"
                        number = getattr(feature, "Medida" + name, 2)
                        self.phillips_size.setCurrentIndex(max(0, self.phillips_size.findData(number)))
                        self.allen_depth.setValue(getattr(getattr(feature, "Profundidad" + name, None), "Value", 2.1))
                if choice in (SLOT, ROBERTSON, SPANNER, JIS_S):
                    if recalculate or saved_family == "Según catálogo":
                        self.load_manual_dimensions(choice)
                    else:
                        width_name, depth_name = {
                            SLOT: ("AnchoRanura", "ProfundidadRanura"),
                            ROBERTSON: ("MedidaRobertson", "ProfundidadRobertson"),
                            SPANNER: ("DiametroSpanner", "ProfundidadSpanner"),
                            JIS_S: ("MedidaCruzS", "ProfundidadCruzS"),
                        }[choice]
                        self.allen_width.setValue(getattr(getattr(feature, width_name, None), "Value", 1.6))
                        self.allen_depth.setValue(getattr(getattr(feature, depth_name, None), "Value", 1.2))

        def load_torx_suggestion(self):
            key, head = self.head.currentData()
            suggestion, _ = torx_options(key, head, self.values())
            if suggestion:
                size, depth = suggestion
                with QtCore.QSignalBlocker(self.torx_size), QtCore.QSignalBlocker(self.allen_depth):
                    self.torx_size.setCurrentIndex(self.torx_size.findData(size))
                    self.allen_depth.setValue(depth)

        def change_drive_family(self):
            if self.drive_family.currentText() in TORX_DRIVES:
                self.load_torx_suggestion()
            elif self.drive_family.currentText() in CROSS_DRIVES:
                self.load_cross_suggestion()
            elif self.drive_family.currentText() in (SLOT, ROBERTSON, SPANNER, JIS_S):
                self.load_manual_dimensions(self.drive_family.currentText())
            elif self.drive_family.currentText() == "Allen":
                self.load_allen_suggestion()
            self.update()

        def load_allen_suggestion(self):
            standard, size, key = self.drive_catalog_key()
            if standard not in CATALOG or not size:
                return
            diameter = CATALOG[standard]["sizes"][size][0]
            preset = inch_allen(key, size, allow_custom=True) or ALLEN_HEADS.get(key, {}).get(diameter)
            if key == ISO_BUTTON:
                preset = metric_button_allen(diameter)
            elif key in METRIC_DOME_FORMS:
                _, _, width, height, *_ = self.values()
                preset = min(diameter * 0.52, width * 0.45), min(diameter * 0.25, height * 0.4)
            if preset:
                with QtCore.QSignalBlocker(self.allen_width), QtCore.QSignalBlocker(self.allen_depth):
                    self.allen_width.setValue(preset[0])
                    self.allen_depth.setValue(preset[1])

        def load_manual_dimensions(self, family):
            diameter = self.fields["Diametro"].value()
            key, head = self.head.currentData()
            preset = SLOT_ISO_2009.get(diameter) if family == SLOT and key == "ISO 2009" else None
            if family == JIS_S and head == "Avellanado":
                pitch = thread_pitch(self.standard.currentData(), self.size.currentData(), self.manual_pitch)
                preset = JIS_S_REFERENCE.get((diameter, pitch))
            if preset is None:
                _, _, head_width, height, angle, *_ = self.values()
                if head not in STRAIGHT_HEADS:
                    rim = height if head == "Contra-taladro" else 0
                    slope = math.tan(math.radians(angle / 2))
                    height = rim + (head_width - diameter) / (2 * slope) if slope > 0 else 0
                width_ratio = {SLOT: 0.24, ROBERTSON: 0.4, SPANNER: 0.2, JIS_S: 0.85}[family]
                width = diameter * width_ratio
                if family == JIS_S:
                    width = min(width, head_width * 0.8)
                preset = (max(0.001, round(width, 3)),
                          max(0.001, round(min(diameter * 0.2, height * 0.4), 3)))
            with QtCore.QSignalBlocker(self.allen_width), QtCore.QSignalBlocker(self.allen_depth):
                self.allen_width.setValue(preset[0])
                self.allen_depth.setValue(preset[1])
            if family == SPANNER:
                with QtCore.QSignalBlocker(self.spanner_spacing):
                    self.spanner_spacing.setValue(diameter * 0.5)

        def load_cross_suggestion(self):
            key, head = self.head.currentData()
            family = self.drive_family.currentText()
            suggestion, _ = cross_options(family, key, head, self.values())
            if family == PHILLIPS and key in (ASME_PAN, ASME_OVAL):
                row = INCH_HEAD_DIMENSIONS[key].get(self.size.currentData())
                if row:
                    suggestion = row[2], round(row[1] * 25.4 * 0.45, 3)
            if suggestion:
                number, depth = suggestion
                with QtCore.QSignalBlocker(self.phillips_size), QtCore.QSignalBlocker(self.allen_depth):
                    self.phillips_size.setCurrentIndex(self.phillips_size.findData(number))
                    self.allen_depth.setValue(depth)

        def geometry_context(self):
            target = self.target()
            base = feature.BaseFeature if feature else (target.Tip if target else None)
            return target, base, bool(self.depth_type.currentIndex()), self.placement()

        def values(self):
            return [self.fields[name].isChecked() if kind == "Bool" else self.fields[name].value()
                    for name, _, kind, _ in FIELDS]

        def drive_settings(self):
            if self.drive.currentText() != "Automático":
                return None
            family = self.drive_family.currentText()
            if family in ("Allen", *TORX_DRIVES, SLOT, ROBERTSON, JIS_S):
                size = self.torx_size.currentData() if family in TORX_DRIVES else self.allen_width.value()
                return family, size, self.allen_depth.value()
            if family == SPANNER:
                return family, self.allen_width.value(), self.allen_depth.value(), self.spanner_spacing.value()
            if family in CROSS_DRIVES:
                span = cross_span(family, self.head.currentData()[0], self.fields["Diametro"].value(),
                                  self.phillips_size.currentData())
                return family, span, self.allen_depth.value()

        def update(self):
            key, head = self.head.currentData()
            active_drive = self.drive.currentText() == "Automático"
            drive_family = self.drive_family.currentText()
            torx = drive_family in TORX_DRIVES
            phillips = drive_family in CROSS_DRIVES
            self.drive_measure.setCurrentWidget(
                self.phillips_size if phillips else self.torx_size if torx else self.allen_width)
            _, normalized = torx_options(key, head, self.values()) if torx else (None, False)
            label = ("Medida de punta" if normalized else "Punta Torx personalizada") if torx else "Medida entre caras"
            if drive_family == TORX_BO:
                label = "Medida de punta Torx BO"
            if phillips:
                _, normalized = cross_options(drive_family, key, head, self.values())
                name = "Pozidriv" if drive_family == POZIDRIV else "Phillips"
                prefix = "PZ" if drive_family == POZIDRIV else "PH"
                for index in range(self.phillips_size.count()):
                    title = f"{prefix}{self.phillips_size.itemData(index)}"
                    if self.phillips_size.itemText(index) != title:
                        self.phillips_size.setItemText(index, title)
                label = "Medida de punta" if normalized else f"Punta {name} personalizada"
            if drive_family == SLOT:
                label = "Ancho de ranura"
            if drive_family == JIS_S:
                label = "Apertura de la cruz S (n.º 0)"
            if drive_family == "Allen" and key in (ASME_SOCKET, ASME_FLAT, ASME_BUTTON):
                row = INCH_HEAD_DIMENSIONS[key].get(self.size.currentData())
                if row and math.isclose(self.allen_width.value(), inch_allen(key, self.size.currentData())[0],
                                        abs_tol=0.00051):
                    label = f"Medida entre caras ({row[2]}″)"
            spanner = drive_family == SPANNER
            if spanner:
                label = "Diámetro de los orificios"
            self.spanner_spacing_label.setVisible(spanner)
            self.spanner_spacing.setVisible(spanner)
            self.spanner_spacing.setEnabled(active_drive and spanner)
            self.drive_measure_label.setText(label)
            if drive_family == "Hexagonal exterior":
                with QtCore.QSignalBlocker(self.allen_width):
                    self.allen_width.setValue(self.fields["DiametroCabeza"].value())
            self.drive_family.setEnabled(active_drive and head != HEADS[0])
            self.allen_width.setEnabled(active_drive and drive_family in ("Allen", SLOT, ROBERTSON, SPANNER, JIS_S))
            self.torx_size.setEnabled(active_drive and torx)
            self.phillips_size.setEnabled(active_drive and phillips)
            self.allen_depth.setEnabled(active_drive and drive_family in ("Allen", *TORX_DRIVES, SLOT, ROBERTSON, SPANNER, JIS_S, *CROSS_DRIVES))
            catalogued = self.standard.currentData() in CATALOG
            named = catalogued and key not in MANUAL_HEADS and (
                key not in INCH_HEAD_DIMENSIONS or self.size.currentData() in INCH_HEAD_DIMENSIONS[key])
            if key in METRIC_DOME_DIMENSIONS:
                diameter = CATALOG[self.standard.currentData()]["sizes"][self.size.currentData()][0]
                named = diameter in METRIC_DOME_DIMENSIONS[key]
            customizable = not named or self.custom_head.isChecked()
            self.size.setEnabled(catalogued)
            self.fields["Diametro"].setReadOnly(catalogued)
            self.custom_head.setVisible(named)
            self.dimension_labels["DiametroCabeza"].setText(
                "Entre caras" if head == HEX_HEAD else "Diámetro de la cabeza")
            self.dimension_labels["ProfundidadCabeza"].setText(
                "Altura de la cabeza" if head in (HEX_HEAD, *DOMED_HEADS) else "Profundidad de la cabeza")
            self.fields["DiametroCabeza"].setEnabled(customizable and head != HEADS[0])
            self.fields["ProfundidadCabeza"].setEnabled(customizable and head in (*STRAIGHT_HEADS, "Contra-taladro", OVAL_HEAD))
            self.fields["AnguloAvellanado"].setEnabled(customizable and head in ("Avellanado", "Contra-taladro", OVAL_HEAD))
            through_all = bool(self.depth_type.currentIndex())
            self.fields["Profundidad"].setEnabled(not through_all)
            point = self.fields["Punta"].isChecked()
            self.fields["AnguloPunta"].setEnabled(point)
            self.fields["IncluirPunta"].setEnabled(point and not through_all)
            self.fields["AnguloCono"].setEnabled(self.fields["Conica"].isChecked())
            family = self.standard.currentData()
            manual = family == "None"
            available = not self.fields["Conica"].isChecked()
            with QtCore.QSignalBlocker(self.thread_pitch):
                self.thread_pitch.setValue(thread_pitch(family, self.size.currentData(), self.manual_pitch))
            self.thread_pitch.setReadOnly(not manual)
            self.thread_enabled.setEnabled(available)
            if not available:
                note = "La rosca requiere un vástago cilíndrico."
            elif family in ("NPT", "BSP", "BSW", "BSF", "ISOTyre"):
                note = "Rosca cilíndrica de perfil básico de 60° con el paso del catálogo."
            else:
                note = ""
            self.thread_note.setText(note)
            self.thread_note.setVisible(bool(note))
            threaded = available and self.thread_enabled.isChecked()
            for field in (self.thread_preview, self.thread_depth, self.custom_clearance):
                field.setEnabled(threaded)
            self.thread_length.setEnabled(threaded and bool(self.thread_depth.currentIndex()))
            self.thread_clearance.setEnabled(threaded and self.custom_clearance.isChecked())
            self.timer.start(120)

        def target(self):
            target = body
            if target is None:
                bodies = document.findObjects("PartDesign::Body")
                if len(bodies) > 1:
                    raise ValueError("Activa el Cuerpo al que quieres añadir el sólido.")
                target = bodies[0] if bodies else None
            return target

        def refresh_preview(self):
            self.diagram.section = []
            self.diagram.update()
            try:
                values = self.values()
                head = self.head.currentData()[1]
                target, base, through_all, offset = self.geometry_context()
                diagram_values = values
                if through_all:
                    position = profile_positions(profile, target, profile_type, offset)[0]
                    diagram_values = full_depth_values(values, position, base)
                self.diagram.section = unthreaded_section(head, diagram_values)
                self.diagram.update()
                self.status.clear()
                if not (self.preview.isChecked() or self.final_preview.isChecked()):
                    self.clear_preview()
                    self.restore_visibility()
                    return
                thread = self.thread_settings()
                drive = self.drive_settings()
                cuts = [] if (thread is not None or drive is not None) and self.preview.isChecked() else None
                detailed = cuts is not None or self.thread_preview.isChecked()
                modeled = thread if detailed else None
                if through_all:
                    addition = addition_shape(head, values, profile, target, profile_type, True, base,
                                              modeled, cuts, offset, drive=drive)
                else:
                    key = (head, tuple(values), modeled, drive, cuts is not None,
                           tuple(str(pose) for pose in profile_positions(profile, target, profile_type)))
                    if self.preview_cache is None or self.preview_cache[0] != key:
                        local_cuts = [] if cuts is not None else None
                        local = addition_shape(head, values, profile, target, profile_type, thread=modeled,
                                               removed=local_cuts, drive=drive)
                        self.preview_cache = (key, local, local_cuts)
                    _, local, local_cuts = self.preview_cache
                    addition = local.copy()
                    if cuts is not None:
                        cuts.extend(cut.copy() for cut in local_cuts)
                    if not offset.isIdentity():
                        matrix = offset.toMatrix()
                        addition.transformShape(matrix, True)
                        for cut in cuts or ():
                            cut.transformShape(matrix, True)
                from pivy import coin

                group = coin.SoSeparator()
                layers = []
                if self.final_preview.isChecked():
                    layers.append((hole_result(addition, base, target).copy(), (0.75, 0.78, 0.82), 0.0))
                if self.preview.isChecked():
                    layers.append((addition, (0.25, 0.85, 0.45), 0.35))
                    if cuts:
                        layers.append((Part.makeCompound(cuts), (1.0, 0.13, 0.13), 0.48))
                    elif cuts is not None:
                        self.status.setText("FreeCAD no pudo dibujar la superposición roja.")
                deflection = min(0.1, thread[-1] / 16) if thread and detailed else 0.1
                for shape, color, transparency in layers:
                    if target is not None:
                        shape.Placement = target.getGlobalPlacement().multiply(shape.Placement)
                    node = shape_scene_node(shape, color, transparency, deflection)
                    if node is not None:
                        group.addChild(node)
                self.clear_preview()
                self.root = Gui.getDocument(document.Name).activeView().getSceneGraph()
                self.root.addChild(group)
                self.node = group
                if feature is not None and self.saved_visibility is None:
                    self.saved_visibility = (feature.Visibility, base, base.Visibility if base else False)
                    if feature.Visibility:
                        feature.Visibility = False
                        if base is not None:
                            base.Visibility = True
            except (ValueError, RuntimeError, Part.OCCError) as error:
                self.clear_preview()
                self.restore_visibility()
                self.status.setText(str(error))

        def clear_preview(self):
            if self.node is not None:
                self.root.removeChild(self.node)
                self.node = self.root = None

        def cleanup(self):
            self.timer.stop()
            self.clear_preview()
            self.restore_visibility()

        def restore_visibility(self):
            if self.saved_visibility is not None:
                visible, base, base_visible = self.saved_visibility
                self.saved_visibility = None
                feature.Visibility = visible
                if base is not None:
                    base.Visibility = base_visible

        def accept(self):
            values = self.values()
            key, head = self.head.currentData()
            try:
                target, base, through_all, offset = self.geometry_context()
                thread = self.thread_settings()
                addition = addition_shape(head, values, profile, target, profile_type, through_all, base,
                                          thread, offset=offset, drive=self.drive_settings())
                result = hole_result(addition, base, target)
                if (target is None or not target.AllowCompound) and (
                        len(result.Solids) != 1 or not result.isValid()):
                    raise ValueError("La operación debe producir un único sólido válido.")
            except (ValueError, RuntimeError, Part.OCCError) as error:
                self.status.setText(str(error))
                return False

            document.openTransaction("Editar tornillo" if feature else "Añadir tornillo")
            try:
                operation = feature
                if operation is None:
                    if target is None:
                        target = document.addObject("PartDesign::Body", "Body")
                    operation = target.newObject("PartDesign::FeatureAdditivePython", "Tornillo2")
                    operation.Label = "Tornillo"
                    PositiveHole(operation)
                    PositiveHoleView(operation.ViewObject)
                    operation.BaseFeature = base
                    target.Tip = operation
                PositiveHole.add_catalog_properties(operation)
                operation.Cabeza = head
                operation.PosicionTornillo = offset
                operation.Estandar = self.standard.currentData()
                operation.Tamano = self.size.currentData() or ""
                operation.TipoCabeza = key
                operation.TipoLlave = self.drive.currentText()
                operation.FamiliaLlave = self.drive_family.currentText()
                operation.MedidaTorx = self.torx_size.currentData()
                if operation.FamiliaLlave in TORX_DRIVES:
                    operation.ProfundidadTorx = self.allen_depth.value()
                elif operation.FamiliaLlave == "Allen":
                    operation.MedidaAllen = self.allen_width.value()
                    operation.ProfundidadAllen = self.allen_depth.value()
                elif operation.FamiliaLlave == PHILLIPS:
                    operation.MedidaPhillips = self.phillips_size.currentData()
                    operation.ProfundidadPhillips = self.allen_depth.value()
                elif operation.FamiliaLlave == POZIDRIV:
                    operation.MedidaPozidriv = self.phillips_size.currentData()
                    operation.ProfundidadPozidriv = self.allen_depth.value()
                elif operation.FamiliaLlave == SLOT:
                    operation.AnchoRanura = self.allen_width.value()
                    operation.ProfundidadRanura = self.allen_depth.value()
                elif operation.FamiliaLlave == ROBERTSON:
                    operation.MedidaRobertson = self.allen_width.value()
                    operation.ProfundidadRobertson = self.allen_depth.value()
                elif operation.FamiliaLlave == SPANNER:
                    operation.DiametroSpanner = self.allen_width.value()
                    operation.DistanciaSpanner = self.spanner_spacing.value()
                    operation.ProfundidadSpanner = self.allen_depth.value()
                elif operation.FamiliaLlave == JIS_S:
                    operation.MedidaCruzS = self.allen_width.value()
                    operation.ProfundidadCruzS = self.allen_depth.value()
                operation.AtraviesaTodo = through_all
                operation.CabezaPersonalizada = self.custom_head.isChecked()
                operation.ModelarRosca = thread is not None
                operation.PasoRosca = self.manual_pitch
                operation.ClaseRosca = self.thread_class()
                operation.RoscaIzquierda = bool(self.thread_hand.currentIndex())
                operation.RoscaCompleta = not self.thread_depth.currentIndex()
                operation.LongitudRosca = self.thread_length.value()
                operation.HolguraPersonalizada = self.custom_clearance.isChecked()
                operation.HolguraRosca = self.thread_clearance.value()
                operation.PrevisualizarRosca = self.thread_preview.isChecked()
                for (name, _, _, _), value in zip(FIELDS, values):
                    setattr(operation, name, value)
                operation.Proxy.pending = (addition, result)
                operation.touch()
                document.recompute()
                if operation.Shape.isNull() or "Invalid" in operation.State:
                    raise ValueError(operation.getStatusString())
                if base is not None and feature is None:
                    base.Visibility = False
                from .independent_pocket import sync_deferred_holes

                sync_deferred_holes(target)
                document.commitTransaction()
            except Exception as error:
                document.abortTransaction()
                self.status.setText(str(error))
                return False
            return self.reject()

        def reject(self):
            self.cleanup()
            if feature is not None:
                Gui.getDocument(document.Name).resetEdit()
            return True

    editor = Editor()
    if not inline:
        Gui.Control.showDialog(editor)
    return editor
