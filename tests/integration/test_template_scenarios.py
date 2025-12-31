"""
Template IR Real-world Scenarios (L11 SOTA)

Tests comprehensive scenarios for Vue SFC & JSX template parsing.

Scenarios:
1. E-commerce product page (XSS in product description)
2. User profile (XSS in bio, avatar)
3. Blog post (XSS in markdown content)
4. Admin dashboard (XSS in reports)
5. Chat application (XSS in messages)

Author: L11 SOTA Team
"""

import asyncio
import pytest
from pathlib import Path

from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder
from codegraph_engine.code_foundation.domain.ports.template_ports import SlotContextKind


class TestEcommerceScenario:
    """Scenario 1: E-commerce product page"""

    def test_product_page_xss(self, tmp_path, shared_ir_builder):
        """Product description with XSS via v-html"""

        vue_code = """<template>
  <div class="product">
    <h1>{{ product.name }}</h1>
    <div class="price">${{ product.price }}</div>
    <div class="description" v-html="product.description"></div>
    <img :src="product.imageUrl" :alt="product.name" />
    <a :href="product.detailsUrl">More Details</a>
  </div>
</template>

<script>
export default {
  props: ['product']
}
</script>"""

        vue_file = tmp_path / "ProductCard.vue"
        vue_file.write_text(vue_code)

        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        config.diagnostics = False
        config.packages = False
        result = asyncio.run(builder.build(files=[vue_file], config=config))
        ir_docs = result.ir_documents

        ir_doc = list(ir_docs.values())[0]

        # Verify XSS detection
        raw_html = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.RAW_HTML]
        url_attrs = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.URL_ATTR]

        assert len(raw_html) == 1  # product.description
        assert raw_html[0].expr_raw == "product.description"

        assert len(url_attrs) == 2  # imageUrl + detailsUrl

        print(f"\n✅ E-commerce XSS: 1 v-html + 2 URL sinks detected")


class TestUserProfileScenario:
    """Scenario 2: User profile page"""

    def test_user_profile_jsx(self, tmp_path, shared_ir_builder):
        """User profile with XSS in JSX"""

        tsx_code = """
interface User {
  name: string;
  bio: string;
  website: string;
  avatar: string;
}

function UserProfile({ user }: { user: User }) {
  return (
    <div className="profile">
      <img src={user.avatar} alt={user.name} />
      <h1>{user.name}</h1>
      <div className="bio" dangerouslySetInnerHTML={{__html: user.bio}} />
      <a href={user.website} target="_blank">Website</a>
      <div className="email">{user.email}</div>
    </div>
  );
}
"""

        tsx_file = tmp_path / "UserProfile.tsx"
        tsx_file.write_text(tsx_code)

        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        config.diagnostics = False
        config.packages = False
        result = asyncio.run(builder.build(files=[tsx_file], config=config))
        ir_docs = result.ir_documents

        ir_doc = list(ir_docs.values())[0]

        # Verify XSS detection
        raw_html = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.RAW_HTML]
        url_attrs = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.URL_ATTR]

        assert len(raw_html) == 1  # user.bio
        assert len(url_attrs) == 2  # avatar + website

        print(f"\n✅ User Profile XSS: 1 dangerouslySetInnerHTML + 2 URL sinks")


class TestBlogScenario:
    """Scenario 3: Blog post with markdown"""

    def test_blog_post_vue(self, tmp_path, shared_ir_builder):
        """Blog post with markdown → HTML (XSS risk)"""

        vue_code = """<template>
  <article class="blog-post">
    <header>
      <h1>{{ post.title }}</h1>
      <div class="meta">
        <span>{{ post.author }}</span>
        <time>{{ post.date }}</time>
      </div>
    </header>
    <div class="content" v-html="post.htmlContent"></div>
    <div class="tags">
      <span v-for="tag in post.tags" :key="tag">{{ tag }}</span>
    </div>
  </article>
</template>

<script>
export default {
  props: ['post']
}
</script>"""

        vue_file = tmp_path / "BlogPost.vue"
        vue_file.write_text(vue_code)

        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        config.diagnostics = False
        config.packages = False
        result = asyncio.run(builder.build(files=[vue_file], config=config))
        ir_docs = result.ir_documents

        ir_doc = list(ir_docs.values())[0]

        # Critical: v-html with htmlContent
        raw_html = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.RAW_HTML]

        assert len(raw_html) == 1
        assert "htmlContent" in raw_html[0].expr_raw

        print(f"\n✅ Blog XSS: Markdown → HTML sink detected")


class TestAdminDashboardScenario:
    """Scenario 4: Admin dashboard with reports"""

    def test_admin_dashboard(self, tmp_path, shared_ir_builder):
        """Admin dashboard with dynamic HTML reports"""

        vue_code = """<template>
  <div class="dashboard">
    <h1>Admin Dashboard</h1>
    
    <!-- Report sections (XSS risk) -->
    <section v-for="report in reports" :key="report.id">
      <h2>{{ report.title }}</h2>
      <div class="report-content" v-html="report.htmlContent"></div>
      <a :href="report.downloadUrl">Download PDF</a>
    </section>
    
    <!-- Charts (XSS risk in labels) -->
    <div class="charts">
      <div v-html="charts.salesChart"></div>
      <div v-html="charts.userChart"></div>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      reports: [],
      charts: {
        salesChart: '',
        userChart: ''
      }
    }
  }
}
</script>"""

        vue_file = tmp_path / "Dashboard.vue"
        vue_file.write_text(vue_code)

        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        config.diagnostics = False
        config.packages = False
        result = asyncio.run(builder.build(files=[vue_file], config=config))
        ir_docs = result.ir_documents

        ir_doc = list(ir_docs.values())[0]

        # Multiple v-html sinks
        raw_html = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.RAW_HTML]
        url_attrs = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.URL_ATTR]

        assert len(raw_html) >= 3  # report.htmlContent + 2 charts
        assert len(url_attrs) >= 1  # downloadUrl

        print(f"\n✅ Admin Dashboard: {len(raw_html)} v-html + {len(url_attrs)} URL sinks")


class TestChatScenario:
    """Scenario 5: Chat application"""

    def test_chat_messages_jsx(self, tmp_path, shared_ir_builder):
        """Chat messages with user-generated content"""

        tsx_code = """
interface Message {
  id: string;
  user: string;
  text: string;
  html: string;
  timestamp: string;
}

function ChatMessage({ message }: { message: Message }) {
  return (
    <div className="message">
      <div className="user">{message.user}</div>
      <div className="timestamp">{message.timestamp}</div>
      
      {/* XSS Risk: User messages with HTML */}
      <div 
        className="content"
        dangerouslySetInnerHTML={{__html: message.html}}
      />
      
      {/* Safe: Plain text */}
      <div className="text">{message.text}</div>
    </div>
  );
}

function ChatRoom({ messages }: { messages: Message[] }) {
  return (
    <div className="chat-room">
      {messages.map(msg => (
        <ChatMessage key={msg.id} message={msg} />
      ))}
    </div>
  );
}
"""

        tsx_file = tmp_path / "Chat.tsx"
        tsx_file.write_text(tsx_code)

        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        config.diagnostics = False
        config.packages = False
        result = asyncio.run(builder.build(files=[tsx_file], config=config))
        ir_docs = result.ir_documents

        ir_doc = list(ir_docs.values())[0]

        # Critical: message.html sink
        raw_html = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.RAW_HTML]

        assert len(raw_html) == 1
        assert "message.html" in raw_html[0].expr_raw

        print(f"\n✅ Chat XSS: User message HTML sink detected")


class TestMixedScenario:
    """Scenario 6: Mixed Vue + JSX project"""

    def test_mixed_project(self, tmp_path, shared_ir_builder):
        """Real-world: Vue + JSX in same project"""

        # Vue component
        vue_code = """<template>
  <div v-html="content"></div>
</template>

<script>
export default {
  props: ['content']
}
</script>"""

        # JSX component
        jsx_code = """
function Display({ html }) {
  return <div dangerouslySetInnerHTML={{__html: html}} />;
}
"""

        vue_file = tmp_path / "VueComponent.vue"
        jsx_file = tmp_path / "JsxComponent.tsx"

        vue_file.write_text(vue_code)
        jsx_file.write_text(jsx_code)

        builder = shared_ir_builder
        config = BuildConfig.for_editor()
        config.occurrences = False
        config.diagnostics = False
        config.packages = False
        result = asyncio.run(builder.build(files=[vue_file, jsx_file], config=config))
        ir_docs = result.ir_documents

        # Both files should be processed
        assert len(ir_docs) == 2

        # Each should have XSS sink
        total_sinks = 0
        for ir_doc in ir_docs.values():
            raw_html = [s for s in ir_doc.template_slots if s.context_kind == SlotContextKind.RAW_HTML]
            total_sinks += len(raw_html)

        assert total_sinks == 2  # 1 Vue + 1 JSX

        print(f"\n✅ Mixed Project: 2 files, 2 XSS sinks detected")
