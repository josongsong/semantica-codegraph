"""CWE-611: XXE - BAD"""

from lxml import etree


def parse_xml(xml_path: str):
    # SOURCE: external XML file

    # BAD: Default parser allows external entities
    tree = etree.parse(xml_path)  # SINK: XXE
    return tree.getroot()
