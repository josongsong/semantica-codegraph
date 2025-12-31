"""
Unit tests for Vue SFC parser.
"""

import pytest
from codegraph_parsers import VueSFCParser
from codegraph_parsers.domain import SlotContextKind


class TestVueSFCParser:
    """Test Vue Single File Component parser."""

    @pytest.fixture
    def parser(self):
        """Create parser instance."""
        return VueSFCParser()

    def test_simple_sfc(self, parser):
        """Test parsing simple Vue SFC."""
        source = """
        <template>
            <div>Hello World</div>
        </template>

        <script>
        export default {
            name: 'HelloWorld'
        }
        </script>
        """

        result = parser.parse(source, "HelloWorld.vue")

        assert result.doc_id == "template:HelloWorld.vue"
        assert result.engine == "vue-sfc"

    def test_mustache_syntax(self, parser):
        """Test Vue mustache syntax {{ }}."""
        source = """
        <template>
            <div>{{ message }}</div>
        </template>

        <script>
        export default {
            data() {
                return { message: 'Hello' }
            }
        }
        </script>
        """

        result = parser.parse(source, "Message.vue")

        # Should find {{ message }} slot
        assert len(result.slots) >= 1
        slot = result.slots[0]
        assert "message" in slot.expr_raw

    def test_v_html_xss_sink(self, parser):
        """Test v-html XSS sink detection."""
        source = """
        <template>
            <div v-html="userContent"></div>
        </template>

        <script>
        export default {
            props: ['userContent']
        }
        </script>
        """

        result = parser.parse(source, "Unsafe.vue")

        # Should detect v-html as XSS sink
        sinks = [s for s in result.slots if s.is_sink]
        assert len(sinks) >= 1

        sink = sinks[0]
        assert sink.context_kind == SlotContextKind.RAW_HTML
        assert sink.is_sink is True

    def test_v_bind_attribute(self, parser):
        """Test v-bind directive."""
        source = """
        <template>
            <img :src="imageUrl" :alt="imageAlt" />
        </template>

        <script>
        export default {
            props: ['imageUrl', 'imageAlt']
        }
        </script>
        """

        result = parser.parse(source, "Image.vue")

        # Should find :src and :alt bindings
        assert len(result.slots) >= 2

    def test_v_for_directive(self, parser):
        """Test v-for directive."""
        source = """
        <template>
            <ul>
                <li v-for="item in items" :key="item.id">
                    {{ item.name }}
                </li>
            </ul>
        </template>
        """

        result = parser.parse(source, "List.vue")

        # Should find slots in v-for
        assert len(result.slots) >= 1

    def test_v_if_conditional(self, parser):
        """Test v-if conditional rendering."""
        source = """
        <template>
            <div>
                <p v-if="isActive">{{ activeMessage }}</p>
                <p v-else>{{ inactiveMessage }}</p>
            </div>
        </template>
        """

        result = parser.parse(source, "Conditional.vue")

        # Should find slots in conditional branches
        assert len(result.slots) >= 1

    def test_scoped_slots(self, parser):
        """Test scoped slots."""
        source = """
        <template>
            <div>
                <slot name="header" :data="headerData"></slot>
                <slot :item="currentItem"></slot>
            </div>
        </template>
        """

        result = parser.parse(source, "Slots.vue")

        assert result.doc_id == "template:Slots.vue"

    def test_event_handlers(self, parser):
        """Test event handler bindings."""
        source = """
        <template>
            <button @click="handleClick">{{ buttonText }}</button>
        </template>
        """

        result = parser.parse(source, "Button.vue")

        # Should find buttonText slot
        assert len(result.slots) >= 1

    def test_multiple_root_elements(self, parser):
        """Test SFC with multiple root elements (Vue 3)."""
        source = """
        <template>
            <header>{{ title }}</header>
            <main>{{ content }}</main>
            <footer>{{ footer }}</footer>
        </template>
        """

        result = parser.parse(source, "Layout.vue")

        # Should handle multiple roots
        assert len(result.slots) >= 3

    def test_empty_template(self, parser):
        """Test SFC with empty template."""
        source = """
        <template>
        </template>

        <script>
        export default {
            name: 'Empty'
        }
        </script>
        """

        result = parser.parse(source, "Empty.vue")

        assert result.doc_id == "template:Empty.vue"
        assert result.engine == "vue-sfc"
