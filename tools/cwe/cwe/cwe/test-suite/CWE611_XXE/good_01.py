"""CWE-611: XXE - GOOD"""

from lxml import etree


def parse_xml(xml_path: str):
    # GOOD: Disable external entities and DTD
    parser = etree.XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)
    tree = etree.parse(xml_path, parser)
    return tree.getroot()
