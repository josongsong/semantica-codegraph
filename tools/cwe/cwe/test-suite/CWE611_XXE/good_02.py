"""CWE-611: XXE - GOOD (defusedxml)"""

import defusedxml.ElementTree as ET
from flask import request


def process_xml():
    xml_data = request.get_data()

    # GOOD: defusedxml prevents XXE
    root = ET.fromstring(xml_data)
    return root.find("data").text
