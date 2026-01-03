"""
Test suite for vision module functionality.
"""

import asyncio
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.vision import VisionAgent, VisionAnalysisResult, vision_agent
from app.vision.provider import VisionProvider, ImageInput
from app.vision.agent import VisionIntent


class TestImageInput:
    """Tests for ImageInput class."""
    
    def test_from_url(self):
        """Test creating ImageInput from URL."""
        url = "https://example.com/image.jpg"
        img = ImageInput.from_url(url)
        
        assert img.image_url == url
        assert img.image_data is None
        
        content = img.to_message_content()
        assert content["type"] == "image_url"
        assert content["image_url"]["url"] == url
    
    def test_from_base64(self):
        """Test creating ImageInput from base64 data."""
        data = "SGVsbG8gV29ybGQ="  # "Hello World" in base64
        mime_type = "image/png"
        img = ImageInput.from_base64(data, mime_type)
        
        assert img.image_data == data
        assert img.mime_type == mime_type
        assert img.image_url is None
        
        content = img.to_message_content()
        assert content["type"] == "image_url"
        assert content["image_url"]["url"] == f"data:{mime_type};base64,{data}"
    
    def test_from_bytes(self):
        """Test creating ImageInput from raw bytes."""
        raw_data = b"test image data"
        img = ImageInput.from_bytes(raw_data)
        
        expected_b64 = base64.b64encode(raw_data).decode("utf-8")
        assert img.image_data == expected_b64
        assert img.mime_type == "image/jpeg"
    
    def test_to_message_content_requires_data(self):
        """Test that to_message_content raises error without data."""
        img = ImageInput()
        with pytest.raises(ValueError, match="Either image_url or image_data must be provided"):
            img.to_message_content()


class TestVisionProvider:
    """Tests for VisionProvider class."""
    
    def test_build_multimodal_message(self):
        """Test building multimodal message with text and images."""
        with patch('app.vision.provider.settings') as mock_settings:
            mock_settings.vision.model.enabled = True
            mock_settings.vision.model.api_key = "test-key"
            mock_settings.vision.model.model_name = "test-model"
            mock_settings.vision.model.base_url = "https://test.com"
            mock_settings.vision.model.temperature = 0.7
            mock_settings.vision.model.max_tokens = 4096
            mock_settings.vision.model.request_timeout = 120
            mock_settings.vision.model.max_image_size_mb = 10.0
            mock_settings.vision.model.supported_formats = ["image/jpeg", "image/png"]
            
            provider = VisionProvider()
            
            images = [ImageInput.from_url("https://example.com/food.jpg")]
            message = provider.build_multimodal_message("What is this?", images)
            
            assert message.content is not None
            assert len(message.content) == 2
            assert message.content[0]["type"] == "text"
            assert message.content[0]["text"] == "What is this?"
            assert message.content[1]["type"] == "image_url"
    
    def test_validate_image_format(self):
        """Test image format validation."""
        with patch('app.vision.provider.settings') as mock_settings:
            mock_settings.vision.model.enabled = True
            mock_settings.vision.model.api_key = "test-key"
            mock_settings.vision.model.supported_formats = ["image/jpeg", "image/png"]
            mock_settings.vision.model.max_image_size_mb = 10.0
            mock_settings.vision.model.model_name = "test"
            mock_settings.vision.model.base_url = "https://test.com"
            mock_settings.vision.model.temperature = 0.7
            mock_settings.vision.model.max_tokens = 4096
            mock_settings.vision.model.request_timeout = 120
            
            provider = VisionProvider()
            
            # Valid format
            is_valid, error = provider.validate_image("image/jpeg", 1024 * 1024)
            assert is_valid is True
            assert error is None
            
            # Invalid format
            is_valid, error = provider.validate_image("image/bmp", 1024 * 1024)
            assert is_valid is False
            assert "Unsupported image format" in error
    
    def test_validate_image_size(self):
        """Test image size validation."""
        with patch('app.vision.provider.settings') as mock_settings:
            mock_settings.vision.model.enabled = True
            mock_settings.vision.model.api_key = "test-key"
            mock_settings.vision.model.supported_formats = ["image/jpeg"]
            mock_settings.vision.model.max_image_size_mb = 10.0
            mock_settings.vision.model.model_name = "test"
            mock_settings.vision.model.base_url = "https://test.com"
            mock_settings.vision.model.temperature = 0.7
            mock_settings.vision.model.max_tokens = 4096
            mock_settings.vision.model.request_timeout = 120
            
            provider = VisionProvider()
            
            # Valid size
            is_valid, error = provider.validate_image("image/jpeg", 5 * 1024 * 1024)
            assert is_valid is True
            
            # Too large
            is_valid, error = provider.validate_image("image/jpeg", 15 * 1024 * 1024)
            assert is_valid is False
            assert "Image too large" in error


class TestVisionAgent:
    """Tests for VisionAgent class."""
    
    def test_vision_analysis_result_to_dict(self):
        """Test VisionAnalysisResult serialization."""
        result = VisionAnalysisResult(
            is_food_related=True,
            intent=VisionIntent.RECIPE_REQUEST,
            description="A delicious looking pasta dish",
            extracted_info={"dish_name": "Carbonara", "ingredients": ["pasta", "eggs", "bacon"]},
            direct_response=None,
            confidence=0.95,
            raw_response="raw model response",
        )
        
        data = result.to_dict()
        
        assert data["is_food_related"] is True
        assert data["intent"] == "recipe_request"
        assert data["description"] == "A delicious looking pasta dish"
        assert data["extracted_info"]["dish_name"] == "Carbonara"
        assert data["confidence"] == 0.95
        assert "raw_response" not in data  # Should not expose raw response
    
    def test_build_context_for_rag_food_related(self):
        """Test building RAG context for food-related images."""
        agent = VisionAgent()
        
        result = VisionAnalysisResult(
            is_food_related=True,
            intent=VisionIntent.RECIPE_REQUEST,
            description="一盘红烧肉",
            extracted_info={
                "dish_name": "红烧肉",
                "ingredients": ["五花肉", "酱油", "冰糖"],
                "cooking_stage": "成品",
            },
            direct_response=None,
            confidence=0.9,
            raw_response="",
        )
        
        context = agent.build_context_for_rag(result, "这道菜怎么做？")
        
        assert "【图片内容】一盘红烧肉" in context
        assert "【识别菜品】红烧肉" in context
        assert "【识别食材】五花肉, 酱油, 冰糖" in context
        assert "【用户意图】" in context
    
    def test_build_context_for_rag_non_food(self):
        """Test that non-food images return empty context."""
        agent = VisionAgent()
        
        result = VisionAnalysisResult(
            is_food_related=False,
            intent=VisionIntent.GENERAL_IMAGE,
            description="A landscape photo",
            extracted_info={},
            direct_response="This is a beautiful landscape.",
            confidence=0.9,
            raw_response="",
        )
        
        context = agent.build_context_for_rag(result, "What is this?")
        
        assert context == ""


class TestVisionIntegration:
    """Integration tests for vision module."""
    
    def test_analyze_unavailable_returns_fallback(self):
        """Test that unavailable vision returns appropriate fallback."""
        with patch('app.vision.agent.vision_provider') as mock_provider:
            mock_provider.is_enabled = False
            
            agent = VisionAgent(provider=mock_provider)
            images = [ImageInput.from_url("https://example.com/test.jpg")]
            
            result = asyncio.run(agent.analyze(images, "What is this?"))
            
            assert result.is_food_related is False
            assert result.intent == VisionIntent.UNCLEAR
            assert "暂时不可用" in result.direct_response
    
    def test_analyze_with_mock_response(self):
        """Test vision analysis with mocked model response."""
        mock_provider = MagicMock(spec=VisionProvider)
        mock_provider.is_enabled = True
        mock_provider.analyze = AsyncMock(return_value='''{
            "is_food_related": true,
            "intent": "recipe_request",
            "description": "一盘番茄炒蛋",
            "extracted_info": {
                "dish_name": "番茄炒蛋",
                "ingredients": ["番茄", "鸡蛋"],
                "cooking_stage": "成品",
                "other": null
            },
            "direct_response": null,
            "confidence": 0.95
        }''')
        
        agent = VisionAgent(provider=mock_provider)
        images = [ImageInput.from_url("https://example.com/tomato-eggs.jpg")]
        
        result = asyncio.run(agent.analyze(images, "这是什么菜？怎么做？"))
        
        assert result.is_food_related is True
        assert result.intent == VisionIntent.RECIPE_REQUEST
        assert "番茄炒蛋" in result.description
        assert result.extracted_info.get("dish_name") == "番茄炒蛋"
        assert result.confidence == 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
