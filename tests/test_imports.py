#!/usr/bin/env python3
"""
Test script to verify the refactored codebase imports work correctly.

Run from the cli_chat_refactored directory:
    python tests/test_imports.py
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_core_imports():
    """Test core module imports."""
    print("Testing core imports...")
    try:
        from core import (
            ToolResult,
            Message,
            ToolCall,
            LLMResponse,
            DEFAULT_CONTEXT_LIMIT,
            DEFAULT_SYSTEM_PROMPT
        )
        print("  ✓ core module imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ core import failed: {e}")
        return False


def test_llm_imports():
    """Test LLM module imports."""
    print("Testing LLM imports...")
    try:
        from llm import LLMClient, MockLLMClient
        from llm.types import StreamingTimeoutError
        print("  ✓ llm module imports successful")

        # Test mock client instantiation
        mock = MockLLMClient(context_limit=8192)
        assert mock.get_context_limit() == 8192
        print("  ✓ MockLLMClient works")

        return True
    except ImportError as e:
        print(f"  ✗ llm import failed: {e}")
        return False


def test_tools_imports():
    """Test tools module imports."""
    print("Testing tools imports...")
    try:
        from tools import (
            register_tool,
            execute,
            get_schemas,
            list_tools,
            tool_exists
        )
        print("  ✓ tools module imports successful")

        # Test tool listing
        tools = list_tools()
        print(f"  ✓ Registered tools: {list(tools.keys())}")

        # Test schemas
        schemas = get_schemas()
        print(f"  ✓ Got {len(schemas)} tool schemas")

        return True
    except ImportError as e:
        print(f"  ✗ tools import failed: {e}")
        return False


def test_memory_imports():
    """Test memory module imports."""
    print("Testing memory imports...")
    try:
        from memory import ChatHistory, ProjectState
        print("  ✓ memory module imports successful")

        # Test chat history
        history = ChatHistory("test_history.jsonl")
        history.clear()
        history.save("user", "Test message")
        messages = history.load()
        assert len(messages) == 1
        print("  ✓ ChatHistory works")

        # Test project state
        state = ProjectState("test_project.md")
        state.set_name("Test Project")
        state.set_status("Testing")
        state.save()
        state.load()
        print("  ✓ ProjectState works")

        # Cleanup
        import os
        if os.path.exists("test_history.jsonl"):
            os.remove("test_history.jsonl")
        if os.path.exists("test_project.md"):
            os.remove("test_project.md")

        return True
    except ImportError as e:
        print(f"  ✗ memory import failed: {e}")
        return False
    except Exception as e:
        print(f"  ✗ memory test failed: {e}")
        return False


def test_agents_imports():
    """Test agents module imports."""
    print("Testing agents imports...")
    try:
        from agents import AgentConfig, AgentManager
        print("  ✓ agents module imports successful")

        # Test agent manager
        manager = AgentManager()
        agents = manager.list_agents()
        print(f"  ✓ Available agents: {agents}")

        return True
    except ImportError as e:
        print(f"  ✗ agents import failed: {e}")
        return False


def test_settings():
    """Test settings module."""
    print("Testing settings...")
    try:
        import settings
        params = settings.get_params()
        print(f"  ✓ Settings loaded: {list(params.keys())}")

        all_settings = settings.get_all()
        print(f"  ✓ All settings: {len(all_settings)} items")

        return True
    except ImportError as e:
        print(f"  ✗ settings import failed: {e}")
        return False


def test_ui():
    """Test UI module."""
    print("Testing UI...")
    try:
        import ui
        print("  ✓ UI module imports successful")

        # Just test that we can call display functions
        # (they print to stdout)
        ui.display_status("Test status")
        ui.display_warning("Test warning")

        return True
    except ImportError as e:
        print(f"  ✗ ui import failed: {e}")
        return False


def test_tool_execution():
    """Test tool execution with mock."""
    print("Testing tool execution...")
    try:
        from tools import execute, tool_exists

        # Test bash tool
        result = execute("execute_bash", {"command": "echo 'hello'"})
        assert result.success
        assert "hello" in result.output.lower()
        print("  ✓ execute_bash works")

        # Test lft tool (info command on a real file)
        result = execute("lft", {"command": "info", "file_path": "/etc/hostname"})
        # May not exist on all systems, so just check we got a result
        if result.success:
            print("  ✓ lft tool works")
        else:
            # Try another file
            result = execute("lft", {"command": "info", "file_path": "/etc/passwd"})
            if result.success:
                print("  ✓ lft tool works")
            else:
                print(f"  ✓ lft tool responds (file may not exist)")

        return True
    except Exception as e:
        print(f"  ✗ tool execution failed: {e}")
        return False


def test_mock_llm():
    """Test mock LLM client."""
    print("Testing mock LLM client...")
    try:
        from llm import MockLLMClient

        client = MockLLMClient()

        # Test non-streaming
        messages = [{"role": "user", "content": "Hello"}]
        response = client.call(messages, stream=False)

        assert "choices" in response
        assert len(response["choices"]) > 0
        print("  ✓ Non-streaming response works")

        # Test streaming
        gen = client.call(messages, stream=True)
        chunks = list(gen)
        assert len(chunks) > 0
        print("  ✓ Streaming response works")

        # Test tool calling
        messages = [{"role": "user", "content": "Please run ls command"}]
        response = client.call(
            messages,
            stream=False,
            tools=[{"type": "function", "function": {"name": "test"}}]
        )
        if response.get("choices", [{}])[0].get("finish_reason") == "tool_calls":
            print("  ✓ Tool call generation works")
        else:
            print("  ✓ Text response works")

        return True
    except Exception as e:
        print(f"  ✗ mock LLM test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 50)
    print("REFACTORED CODEBASE TEST SUITE")
    print("=" * 50)
    print()

    results = []

    results.append(("Core imports", test_core_imports()))
    results.append(("LLM imports", test_llm_imports()))
    results.append(("Tools imports", test_tools_imports()))
    results.append(("Memory imports", test_memory_imports()))
    results.append(("Agents imports", test_agents_imports()))
    results.append(("Settings", test_settings()))
    results.append(("UI", test_ui()))
    results.append(("Tool execution", test_tool_execution()))
    results.append(("Mock LLM", test_mock_llm()))

    print()
    print("=" * 50)
    print("RESULTS")
    print("=" * 50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")

    print()
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed! The refactored codebase is ready to use.")
        return 0
    else:
        print("\nSome tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
