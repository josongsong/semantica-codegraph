"""
OpenAI LLM Adapter Tests

Tests for LLM adapter using litellm.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.infra.llm.openai import OpenAIAdapter


class TestOpenAIAdapterBasics:
    """Test basic OpenAIAdapter functionality."""

    def test_openai_adapter_creation(self):
        """Test OpenAIAdapter can be instantiated."""
        adapter = OpenAIAdapter(
            model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
        )

        assert adapter is not None
        assert adapter.model == "gpt-4o-mini"
        assert adapter.embedding_model == "text-embedding-3-small"
        assert adapter.api_key is None

    def test_openai_adapter_with_api_key(self):
        """Test OpenAIAdapter with API key."""
        adapter = OpenAIAdapter(
            api_key="sk-test123",
            model="gpt-4",
        )

        assert adapter.api_key == "sk-test123"
        assert adapter.model == "gpt-4"

    def test_openai_adapter_custom_models(self):
        """Test OpenAIAdapter with custom models."""
        adapter = OpenAIAdapter(
            model="gpt-4-turbo",
            embedding_model="text-embedding-ada-002",
        )

        assert adapter.model == "gpt-4-turbo"
        assert adapter.embedding_model == "text-embedding-ada-002"


class TestEmbed:
    """Test embed method."""

    @pytest.mark.asyncio
    async def test_embed_success(self):
        """Test embedding generation."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.aembedding") as mock_aembedding:
            # Mock response
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
            mock_aembedding.return_value = mock_response

            embedding = await adapter.embed("test text")

            assert embedding == [0.1, 0.2, 0.3]
            mock_aembedding.assert_called_once_with(
                model="text-embedding-3-small",
                input="test text",
            )

    @pytest.mark.asyncio
    async def test_embed_with_custom_model(self):
        """Test embedding with custom model."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.aembedding") as mock_aembedding:
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1, 0.2]}]
            mock_aembedding.return_value = mock_response

            embedding = await adapter.embed("test", model="custom-embedding")

            assert embedding == [0.1, 0.2]
            mock_aembedding.assert_called_once_with(
                model="custom-embedding",
                input="test",
            )

    @pytest.mark.asyncio
    async def test_embed_with_api_key(self):
        """Test embedding with API key."""
        adapter = OpenAIAdapter(api_key="sk-test")

        with patch("src.infra.llm.openai.aembedding") as mock_aembedding:
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1]}]
            mock_aembedding.return_value = mock_response

            await adapter.embed("test")

            call_kwargs = mock_aembedding.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-test"

    @pytest.mark.asyncio
    async def test_embed_raises_on_no_data(self):
        """Test embed raises when no data returned."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.aembedding") as mock_aembedding:
            mock_response = MagicMock()
            mock_response.data = []
            mock_aembedding.return_value = mock_response

            with pytest.raises(RuntimeError, match="No embedding returned"):
                await adapter.embed("test")

    @pytest.mark.asyncio
    async def test_embed_raises_on_error(self):
        """Test embed raises RuntimeError on exception."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.aembedding") as mock_aembedding:
            mock_aembedding.side_effect = Exception("API error")

            with pytest.raises(RuntimeError, match="Failed to generate embedding"):
                await adapter.embed("test")


class TestEmbedBatch:
    """Test embed_batch method."""

    @pytest.mark.asyncio
    async def test_embed_batch_success(self):
        """Test batch embedding generation."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.aembedding") as mock_aembedding:
            mock_response = MagicMock()
            mock_response.data = [
                {"embedding": [0.1, 0.2]},
                {"embedding": [0.3, 0.4]},
                {"embedding": [0.5, 0.6]},
            ]
            mock_aembedding.return_value = mock_response

            embeddings = await adapter.embed_batch(["text1", "text2", "text3"])

            assert len(embeddings) == 3
            assert embeddings[0] == [0.1, 0.2]
            assert embeddings[1] == [0.3, 0.4]
            assert embeddings[2] == [0.5, 0.6]

    @pytest.mark.asyncio
    async def test_embed_batch_with_custom_model(self):
        """Test batch embedding with custom model."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.aembedding") as mock_aembedding:
            mock_response = MagicMock()
            mock_response.data = [{"embedding": [0.1]}]
            mock_aembedding.return_value = mock_response

            await adapter.embed_batch(["text"], model="custom-model")

            call_kwargs = mock_aembedding.call_args.kwargs
            assert call_kwargs["model"] == "custom-model"

    @pytest.mark.asyncio
    async def test_embed_batch_raises_on_no_data(self):
        """Test embed_batch raises when no data returned."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.aembedding") as mock_aembedding:
            mock_response = MagicMock()
            mock_response.data = None
            mock_aembedding.return_value = mock_response

            with pytest.raises(RuntimeError, match="No embeddings returned"):
                await adapter.embed_batch(["text1", "text2"])


class TestChat:
    """Test chat method."""

    @pytest.mark.asyncio
    async def test_chat_success(self):
        """Test chat completion."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            # Mock response
            mock_message = MagicMock()
            mock_message.content = "Hello! How can I help you?"

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]
            response = await adapter.chat(messages)

            assert response == "Hello! How can I help you?"
            mock_acompletion.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_with_custom_model(self):
        """Test chat with custom model."""
        adapter = OpenAIAdapter(model="gpt-4")

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_message = MagicMock()
            mock_message.content = "Response"
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            messages = [{"role": "user", "content": "Test"}]
            await adapter.chat(messages, model="gpt-4-turbo")

            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_chat_with_temperature(self):
        """Test chat with custom temperature."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_message = MagicMock()
            mock_message.content = "Response"
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            messages = [{"role": "user", "content": "Test"}]
            await adapter.chat(messages, temperature=0.9)

            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_chat_with_max_tokens(self):
        """Test chat with max_tokens."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_message = MagicMock()
            mock_message.content = "Response"
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            messages = [{"role": "user", "content": "Test"}]
            await adapter.chat(messages, max_tokens=100)

            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_chat_with_api_key(self):
        """Test chat with API key."""
        adapter = OpenAIAdapter(api_key="sk-test")

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_message = MagicMock()
            mock_message.content = "Response"
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            messages = [{"role": "user", "content": "Test"}]
            await adapter.chat(messages)

            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-test"

    @pytest.mark.asyncio
    async def test_chat_with_extra_kwargs(self):
        """Test chat with additional kwargs."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_message = MagicMock()
            mock_message.content = "Response"
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            messages = [{"role": "user", "content": "Test"}]
            await adapter.chat(messages, top_p=0.95, frequency_penalty=0.5)

            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["top_p"] == 0.95
            assert call_kwargs["frequency_penalty"] == 0.5

    @pytest.mark.asyncio
    async def test_chat_empty_content(self):
        """Test chat with empty content returns empty string."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_message = MagicMock()
            mock_message.content = None
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            messages = [{"role": "user", "content": "Test"}]
            response = await adapter.chat(messages)

            assert response == ""

    @pytest.mark.asyncio
    async def test_chat_raises_on_no_choices(self):
        """Test chat raises when no choices returned."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_response = MagicMock()
            mock_response.choices = []
            mock_acompletion.return_value = mock_response

            messages = [{"role": "user", "content": "Test"}]
            with pytest.raises(RuntimeError, match="No content returned"):
                await adapter.chat(messages)

    @pytest.mark.asyncio
    async def test_chat_raises_on_error(self):
        """Test chat raises RuntimeError on exception."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_acompletion.side_effect = Exception("API error")

            messages = [{"role": "user", "content": "Test"}]
            with pytest.raises(RuntimeError, match="Failed to generate chat completion"):
                await adapter.chat(messages)


class TestChatStream:
    """Test chat_stream method."""

    @pytest.mark.asyncio
    async def test_chat_stream_success(self):
        """Test streaming chat completion."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            # Create mock chunks
            chunks = []
            for text in ["Hello", " ", "World", "!"]:
                delta = MagicMock()
                delta.content = text
                choice = MagicMock()
                choice.delta = delta
                chunk = MagicMock()
                chunk.choices = [choice]
                chunks.append(chunk)

            # Mock async generator
            async def async_gen():
                for chunk in chunks:
                    yield chunk

            mock_acompletion.return_value = async_gen()

            messages = [{"role": "user", "content": "Say hello"}]
            result = []
            async for chunk in adapter.chat_stream(messages):
                result.append(chunk)

            assert result == ["Hello", " ", "World", "!"]

    @pytest.mark.asyncio
    async def test_chat_stream_with_parameters(self):
        """Test streaming chat with parameters."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:

            async def async_gen():
                delta = MagicMock()
                delta.content = "Test"
                choice = MagicMock()
                choice.delta = delta
                chunk = MagicMock()
                chunk.choices = [choice]
                yield chunk

            mock_acompletion.return_value = async_gen()

            messages = [{"role": "user", "content": "Test"}]
            chunks = []
            async for chunk in adapter.chat_stream(messages, temperature=0.5, max_tokens=50):
                chunks.append(chunk)

            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["temperature"] == 0.5
            assert call_kwargs["max_tokens"] == 50
            assert call_kwargs["stream"] is True

    @pytest.mark.asyncio
    async def test_chat_stream_skips_empty_chunks(self):
        """Test streaming skips chunks without content."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:

            async def async_gen():
                # Chunk with content
                delta1 = MagicMock()
                delta1.content = "Hello"
                choice1 = MagicMock()
                choice1.delta = delta1
                chunk1 = MagicMock()
                chunk1.choices = [choice1]
                yield chunk1

                # Chunk without content
                delta2 = MagicMock()
                delta2.content = None
                choice2 = MagicMock()
                choice2.delta = delta2
                chunk2 = MagicMock()
                chunk2.choices = [choice2]
                yield chunk2

                # Another chunk with content
                delta3 = MagicMock()
                delta3.content = "World"
                choice3 = MagicMock()
                choice3.delta = delta3
                chunk3 = MagicMock()
                chunk3.choices = [choice3]
                yield chunk3

            mock_acompletion.return_value = async_gen()

            messages = [{"role": "user", "content": "Test"}]
            result = []
            async for chunk in adapter.chat_stream(messages):
                result.append(chunk)

            # Should only get chunks with content
            assert result == ["Hello", "World"]


class TestCountTokens:
    """Test count_tokens method."""

    @pytest.mark.asyncio
    async def test_count_tokens_basic(self):
        """Test token counting."""
        adapter = OpenAIAdapter()

        # ~4 characters per token
        count = await adapter.count_tokens("This is a test")
        assert count == 3  # 14 // 4

    @pytest.mark.asyncio
    async def test_count_tokens_empty(self):
        """Test token counting for empty string."""
        adapter = OpenAIAdapter()

        count = await adapter.count_tokens("")
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_tokens_long_text(self):
        """Test token counting for long text."""
        adapter = OpenAIAdapter()

        text = "x" * 400  # 400 characters
        count = await adapter.count_tokens(text)
        assert count == 100  # 400 // 4


class TestComplexScenarios:
    """Test complex usage scenarios."""

    @pytest.mark.asyncio
    async def test_chat_with_multiple_messages(self):
        """Test chat with conversation history."""
        adapter = OpenAIAdapter()

        with patch("src.infra.llm.openai.acompletion") as mock_acompletion:
            mock_message = MagicMock()
            mock_message.content = "Sure, 2+2 equals 4."
            mock_choice = MagicMock()
            mock_choice.message = mock_message
            mock_response = MagicMock()
            mock_response.choices = [mock_choice]
            mock_acompletion.return_value = mock_response

            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
                {"role": "user", "content": "What is 2+2?"},
            ]
            response = await adapter.chat(messages)

            assert "4" in response
            call_kwargs = mock_acompletion.call_args.kwargs
            assert call_kwargs["messages"] == messages
