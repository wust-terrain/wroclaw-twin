"""Shared helpers for the OSM editing workflow (tasks 04r/04s): parsing of JOSM and osmium .osm files.

Not a numbered script. All parsing goes through xml.etree, never through regexes (JOSM writes single-quoted attributes).
"""
import xml.etree.ElementTree as ET

TYPES = ("node", "way", "relation")
COORD_DIGITS = 7


def read_osm(path):
    """Return {"root_attrs", "objs"}: objs is {(type, id): element}; element order of the file is kept in dict order."""
    root = ET.parse(path).getroot()
    objs = {}
    for el in root:
        if el.tag in TYPES:
            objs[(el.tag, int(el.get("id")))] = el
    return {"root": root, "objs": objs}


def canon(el):
    """Canonical content of an object: what the map data says, independent of serialisation.

    tags as a dict, nd / member order significant, coordinates rounded to 7 decimals.
    """
    tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
    if el.tag == "node":
        return ("node", round(float(el.get("lat")), COORD_DIGITS), round(float(el.get("lon")), COORD_DIGITS), tags)
    if el.tag == "way":
        return ("way", tuple(int(n.get("ref")) for n in el.findall("nd")), tags)
    return ("relation", tuple((m.get("type"), int(m.get("ref")), m.get("role")) for m in el.findall("member")), tags)


def way_refs(el):
    return [int(n.get("ref")) for n in el.findall("nd")]


def members(el):
    return [(m.get("type"), int(m.get("ref")), m.get("role")) for m in el.findall("member")]


def coords(el):
    return float(el.get("lat")), float(el.get("lon"))
