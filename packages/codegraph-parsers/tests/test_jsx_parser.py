"""
Unit tests for JSX/TSX template parser.
"""

import pytest
from codegraph_parsers import JSXTemplateParser
from codegraph_parsers.domain import SlotContextKind


class TestJSXTemplateParser:
    """Test JSX/TSX template parser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return JSXTemplateParser()

    def test_simple_component(self, parser):
        """Test parsing simple React component."""
        source = """
        function HelloWorld() {
            return <div>Hello World</div>;
        }
        """

        result = parser.parse(source, "HelloWorld.tsx")

        assert result.doc_id == "template:HelloWorld.tsx"
        assert result.engine == "react-jsx"
        assert len(result.elements) >= 1

    def test_slot_detection(self, parser):
        """Test detecting template slots (variable interpolation)."""
        source = """
        function Greeting({ name }) {
            return <h1>Hello {name}</h1>;
        }
        """

        result = parser.parse(source, "Greeting.tsx")

        # Should find {name} slot
        assert len(result.slots) >= 1
        slot = result.slots[0]
        assert "name" in slot.expr_raw

    def test_xss_sink_detection_dangerous_html(self, parser):
        """Test XSS sink detection for dangerouslySetInnerHTML."""
        source = """
        function UserBio({ bio }) {
            return <div dangerouslySetInnerHTML={{__html: bio}} />;
        }
        """

        result = parser.parse(source, "UserBio.tsx")

        # Should detect XSS sink
        sinks = [s for s in result.slots if s.is_sink]
        assert len(sinks) >= 1

        sink = sinks[0]
        assert sink.context_kind == SlotContextKind.RAW_HTML
        assert sink.is_sink is True

    def test_multiple_slots(self, parser):
        """Test component with multiple slots."""
        source = """
        function UserCard({ name, email, avatar }) {
            return (
                <div className="card">
                    <img src={avatar} alt={name} />
                    <h2>{name}</h2>
                    <p>{email}</p>
                </div>
            );
        }
        """

        result = parser.parse(source, "UserCard.tsx")

        # Should find multiple slots: avatar, name, email
        assert len(result.slots) >= 3

    def test_url_attribute_sink(self, parser):
        """Test URL attribute sink detection."""
        source = """
        function Link({ url }) {
            return <a href={url}>Click me</a>;
        }
        """

        result = parser.parse(source, "Link.tsx")

        # href with variable is a potential SSRF sink
        url_slots = [s for s in result.slots if s.context_kind == SlotContextKind.URL_ATTR]
        assert len(url_slots) >= 1

    def test_nested_elements(self, parser):
        """Test parsing nested elements."""
        source = """
        function Layout({ children }) {
            return (
                <div className="layout">
                    <header>
                        <nav>Menu</nav>
                    </header>
                    <main>{children}</main>
                </div>
            );
        }
        """

        result = parser.parse(source, "Layout.tsx")

        # Should find multiple nested elements
        assert len(result.elements) >= 3

    def test_empty_component(self, parser):
        """Test parsing component with no content."""
        source = """
        function Empty() {
            return null;
        }
        """

        result = parser.parse(source, "Empty.tsx")

        # Should still create document even if empty
        assert result.doc_id == "template:Empty.tsx"
        assert result.engine == "react-jsx"

    def test_fragment(self, parser):
        """Test React Fragment."""
        source = """
        function Multi() {
            return (
                <>
                    <div>First</div>
                    <div>Second</div>
                </>
            );
        }
        """

        result = parser.parse(source, "Multi.tsx")

        # Should handle fragments
        assert result.doc_id == "template:Multi.tsx"

    def test_event_handler(self, parser):
        """Test event handler detection."""
        source = """
        function Button({ onClick }) {
            return <button onClick={onClick}>Click</button>;
        }
        """

        result = parser.parse(source, "Button.tsx")

        # Should detect onClick as event handler context
        assert len(result.slots) >= 1

    def test_jsx_extension(self, parser):
        """Test .jsx file extension."""
        source = """
        function Component() {
            return <div>JSX</div>;
        }
        """

        result = parser.parse(source, "Component.jsx")

        assert result.doc_id == "template:Component.jsx"
        assert result.engine == "react-jsx"

    def test_conditional_rendering(self, parser):
        """Test conditional rendering with ternary."""
        source = """
        function Conditional({ isActive, message }) {
            return (
                <div>
                    {isActive ? <span>{message}</span> : <span>Inactive</span>}
                </div>
            );
        }
        """

        result = parser.parse(source, "Conditional.tsx")

        # Should find slots in conditional branches
        assert len(result.slots) >= 1

    def test_map_iteration(self, parser):
        """Test array.map iteration."""
        source = """
        function List({ items }) {
            return (
                <ul>
                    {items.map(item => <li key={item.id}>{item.name}</li>)}
                </ul>
            );
        }
        """

        result = parser.parse(source, "List.tsx")

        # Should find slots in map callback
        assert len(result.slots) >= 1
