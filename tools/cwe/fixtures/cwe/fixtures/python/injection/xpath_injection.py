"""
XPATH Injection Test Fixtures

Real-world XPATH injection vulnerabilities
Based on OWASP patterns and CVE examples
"""

import lxml.etree as etree


def xpath_injection_vulnerable_1(user_input):
    """
    VULNERABLE: Direct user input in XPath query

    Real attack: user_input = "' or '1'='1"
    Result: Bypasses authentication
    """
    xml_doc = etree.parse("users.xml")

    # VULNERABLE: Unsanitized input
    query = f"//user[username/text()='{user_input}']"

    result = xml_doc.xpath(query)  # SINK: xpath injection
    return result


def xpath_injection_vulnerable_2(username, password):
    """
    VULNERABLE: Authentication bypass via XPATH injection

    Real attack: username = "admin' or '1'='1"
    Result: Login without password
    """
    xml_doc = etree.parse("credentials.xml")

    # VULNERABLE
    query = f"//user[name='{username}' and password='{password}']"

    users = xml_doc.xpath(query)  # SINK: xpath injection
    return len(users) > 0


def xpath_injection_vulnerable_3(search_term):
    """
    VULNERABLE: Data exfiltration via XPATH

    Real attack: search_term = "'] | //password | //*[name()='"
    Result: Leaks all passwords
    """
    xml_doc = etree.parse("database.xml")

    # VULNERABLE
    query = f"//product[name='{search_term}']"

    results = xml_doc.findall(query)  # SINK: xpath injection via findall
    return results


def xpath_injection_safe_1(user_input):
    """
    SAFE: Parameterized XPath (not widely supported, but concept)
    """
    xml_doc = etree.parse("users.xml")

    # SAFE: Escaped input
    escaped = user_input.replace("'", "''")
    query = f"//user[username/text()='{escaped}']"

    result = xml_doc.xpath(query)
    return result


def xpath_injection_safe_2(user_input):
    """
    SAFE: Using sanitizer
    """
    xml_doc = etree.parse("users.xml")

    # SAFE: Sanitized
    clean_input = escape_xpath(user_input)
    query = f"//user[username/text()='{clean_input}']"

    result = xml_doc.xpath(query)
    return result


# Helpers


def escape_xpath(value):
    """XPATH sanitizer"""
    # Remove dangerous characters
    dangerous = ["'", '"', "/", "[", "]", "(", ")"]
    for char in dangerous:
        value = value.replace(char, "")
    return value
