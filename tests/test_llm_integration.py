"""Test script to verify Groq and Gemini LLM integration.

This script tests:
1. Basic chat completions with both providers
2. Structured output generation
3. Temperature control
4. Error handling

Usage:
    # Test with Groq (default)
    uv run python test_llm_integration.py
    
    # Test with Gemini
    LLM_PROVIDER=gemini uv run python test_llm_integration.py
"""

import os
import sys
from typing import List
from pydantic import BaseModel, Field

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from llm.llm_manager import LLMManager


class Person(BaseModel):
    """Sample Pydantic model for structured output testing."""
    name: str = Field(description="Person's full name")
    age: int = Field(description="Person's age in years")
    hobbies: List[str] = Field(description="List of hobbies")


def print_test_header(test_name: str):
    """Print a formatted test header."""
    print("\n" + "=" * 60)
    print(f"TEST: {test_name}")
    print("=" * 60)


def test_basic_chat():
    """Test basic chat completion."""
    print_test_header("Basic Chat Completion")
    
    try:
        llm_manager = LLMManager()
        chat_llm = llm_manager.chat_llm
        
        # Simple test message
        messages = [
            ("system", "You are a helpful assistant."),
            ("user", "What is 2+2? Respond in one short sentence.")
        ]
        
        response = chat_llm.invoke(messages)
        
        print(f"[OK] Provider: {settings.llm_provider}")
        print(f"[OK] Model: {settings.llm_model}")
        print(f"[OK] Response: {response.content}")
        return True
        
    except Exception as e:
        print(f"[FAIL] Test failed: {str(e)}")
        return False


def test_temperature_control():
    """Test LLM with different temperature settings."""
    print_test_header("Temperature Control")
    
    try:
        llm_manager = LLMManager()
        
        # Test with very low temperature (deterministic)
        low_temp_llm = llm_manager.get_chat_llm(temperature=0.0)
        messages = [
            ("system", "You are a math assistant."),
            ("user", "What is 5 * 7? Just give the number.")
        ]
        
        response = low_temp_llm.invoke(messages)
        print(f"[OK] Low temperature (0.0) response: {response.content}")
        
        # Test with default temperature
        default_llm = llm_manager.get_chat_llm()
        response2 = default_llm.invoke(messages)
        print(f"[OK] Default temperature ({settings.llm_convo_temperature}) response: {response2.content}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Test failed: {str(e)}")
        return False


def test_structured_output():
    """Test structured output generation."""
    print_test_header("Structured Output Generation")
    
    try:
        llm_manager = LLMManager()
        
        # Create structured chain
        system_prompt = """You are a helpful assistant that extracts person information.
Given a description, extract the person's name, age, and hobbies."""
        
        chain = llm_manager.create_structured_chain(
            system_prompt=system_prompt,
            pydantic_model=Person,
            temperature=0.0
        )
        
        # Test input
        test_input = """John Smith is a 35-year-old software engineer. 
He enjoys playing guitar, reading science fiction books, and hiking in the mountains."""
        
        result = chain.invoke({"input": test_input})
        
        print(f"[OK] Extracted structured data:")
        print(f"   Name: {result.name}")
        print(f"   Age: {result.age}")
        print(f"   Hobbies: {', '.join(result.hobbies)}")
        print(f"[OK] Type verification: {type(result).__name__} = {Person.__name__}")
        
        # Verify it's the correct type
        assert isinstance(result, Person), "Result should be a Person instance"
        assert result.name, "Name should not be empty"
        assert result.age > 0, "Age should be positive"
        assert len(result.hobbies) > 0, "Should have at least one hobby"
        
        print("[OK] All assertions passed!")
        return True
        
    except Exception as e:
        print(f"[FAIL] Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling():
    """Test error handling with missing API keys."""
    print_test_header("Error Handling")
    
    try:
        # Save original provider
        original_provider = settings.llm_provider
        
        # Test with unsupported provider
        settings.llm_provider = "unsupported_provider"
        
        try:
            llm_manager = LLMManager()
            llm_manager._chat_llm = None  # Reset to force reinitialization
            llm_manager._initialize_llm()
            print("[FAIL] Should have raised ValueError for unsupported provider")
            return False
        except ValueError as e:
            print(f"[OK] Correctly raised ValueError: {str(e)}")
        
        # Restore original provider
        settings.llm_provider = original_provider
        
        return True
        
    except Exception as e:
        print(f"[FAIL] Test failed: {str(e)}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 60)
    print("STARTING LLM INTEGRATION TESTS")
    print(f"Provider: {settings.llm_provider.upper()}")
    print(f"Model: {settings.llm_model}")
    print("=" * 60)
    
    tests = [
        ("Basic Chat", test_basic_chat),
        ("Temperature Control", test_temperature_control),
        ("Structured Output", test_structured_output),
        ("Error Handling", test_error_handling),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n[FAIL] Test '{test_name}' crashed: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed! LLM integration is working correctly.")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
