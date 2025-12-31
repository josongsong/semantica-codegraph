"""CWE-611: XXE via ElementTree - BAD"""

import xml.etree.ElementTree as ET

from flask import request


def process_xml():
    xml_data = request.get_data()  # SOURCE: request body

    # BAD: ElementTree can be vulnerable in older Python
    root = ET.fromstring(xml_data)  # SINK: potential XXE
    return root.find("data").text
