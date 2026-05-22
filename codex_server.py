#!/usr/bin/env python3
"""
OpenAI Codex MCP Server for use with Claude.
This server implements MCP protocol to wrap the OpenAI Codex CLI.
Supports both stdio and SSE (Server-Sent Events) modes.
"""

import os
import sys
import tempfile
import subprocess
import base64
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastmcp import FastMCP


# Initialize FastMCP server
mcp = FastMCP("OpenAI Codex MCP Server")


def _build_common_flags(model: Optional[str] = None,
                        provider: Optional[str] = None,
                        approval_mode: str = "suggest") -> List[str]:
    """codex / codex exec の両方で共通して使えるフラグを組み立てる（v0.120.0）。

    run_codex と codex_interactive で CLI 組み立てが二重化していると、
    codex CLI の仕様変更時に片方だけ移行漏れが起きる（v0.120.0 移行で実際に発生）。
    共通フラグを1箇所に集約してドリフトを防ぐ。
    """
    flags: List[str] = []
    if model:
        flags.extend(["--model", model])
    if provider:
        # v0.120.0: 設定キーは model_provider（旧 --provider フラグは廃止）
        flags.extend(["-c", f'model_provider="{provider}"'])
    # approval_mode マッピング（v0.120.0: --full-auto or default。旧 --approval-mode は廃止）
    if approval_mode in ("auto-edit", "full-auto"):
        flags.append("--full-auto")
    return flags


def run_codex(prompt: str, model: Optional[str] = None,
              images: Optional[List[str]] = None,
              approval_mode: str = "suggest",
              json_output: bool = False,
              provider: Optional[str] = None,
              additional_args: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run the OpenAI Codex CLI tool with the given parameters.

    Args:
        prompt: The prompt to send to Codex
        model: The model to use (e.g., "o4-mini", "o4-preview", "gpt-4.1")
        images: List of image paths to include
        approval_mode: How much autonomy the agent receives ("suggest", "auto-edit", "full-auto")
        json_output: Return structured JSON output
        provider: AI provider to use (openai, azure, gemini, ollama, etc.)
        additional_args: Additional CLI arguments to pass to Codex

    Returns:
        A dictionary containing the response from Codex
    """
    # Build command: use "codex exec" for non-interactive execution (v0.120.0+)
    cmd = ["codex", "exec"]

    # 呼び出し元のカレントディレクトリをワーキングルートとして渡す
    cwd = os.getcwd()
    cmd.extend(["-C", cwd])

    # --quiet は v0.120.0 で廃止。codex exec が非対話モード。

    if json_output:
        cmd.append("--json")

    cmd.extend(_build_common_flags(model=model, provider=provider, approval_mode=approval_mode))

    if images:
        for image_path in images:
            # For temp files received from Claude, save the content
            if image_path.startswith("data:"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp:
                    # Handle data URI format if needed
                    if "base64," in image_path:
                        header, encoded = image_path.split(",", 1)
                        image_data = base64.b64decode(encoded)
                        temp.write(image_data)
                        image_path = temp.name
                    else:
                        # Otherwise save as-is
                        temp.write(image_path.encode())
                        image_path = temp.name
            
            cmd.extend(["-i", image_path])
    
    if additional_args:
        cmd.extend(additional_args)
    
    # Add the prompt
    cmd.append(prompt)
    
    # -o フラグで最終メッセージをファイルに書き出す（確実な取得のため）
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w") as out_file:
        output_path = out_file.name
    cmd.extend(["-o", output_path])

    print(f"Executing command: {' '.join(cmd)}", file=sys.stderr)

    # タイムアウト: デフォルト300秒（5分）
    TIMEOUT_SECONDS = 300

    try:
        result = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,  # stdin を閉じて "Reading additional input from stdin..." のブロックを防ぐ
            check=True,
            timeout=TIMEOUT_SECONDS
        )

        # -o で書き出されたファイルから最終メッセージを読む
        output = ""
        try:
            with open(output_path, "r") as f:
                output = f.read().strip()
        except Exception:
            pass
        finally:
            Path(output_path).unlink(missing_ok=True)

        # -o が空の場合は stdout にフォールバック
        if not output:
            output = result.stdout.strip()

        return {
            "status": "success",
            "output": output,
            "stderr": result.stderr,
            "command": " ".join(cmd)
        }
    except subprocess.TimeoutExpired as e:
        Path(output_path).unlink(missing_ok=True)
        print(f"Codex timed out after {TIMEOUT_SECONDS}s", file=sys.stderr)
        return {
            "status": "error",
            "error": f"Codex timed out after {TIMEOUT_SECONDS} seconds. The task may be too complex or Codex is unresponsive.",
            "command": " ".join(cmd)
        }
    except subprocess.CalledProcessError as e:
        Path(output_path).unlink(missing_ok=True)
        print(f"Error running codex: {e}", file=sys.stderr)
        return {
            "status": "error",
            "error": str(e),
            "output": e.stdout,
            "stderr": e.stderr,
            "exit_code": e.returncode,
            "command": " ".join(cmd)
        }
    except Exception as e:
        Path(output_path).unlink(missing_ok=True)
        print(f"Unexpected error: {e}", file=sys.stderr)
        return {
            "status": "error",
            "error": str(e),
            "command": " ".join(cmd)
        }


@mcp.tool()
def codex_agent(
    prompt: str,
    model: str = "o4-mini",
    approval_mode: str = "suggest",
    images: Optional[List[str]] = None,
    provider: Optional[str] = None,
    json_output: bool = False,
    task_type: str = "general",
    additional_args: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Interact with OpenAI's Codex CLI - a lightweight coding agent that runs in your terminal.
    
    This tool provides access to all Codex CLI capabilities including code generation, 
    explanation, debugging, refactoring, and more. Codex can read files, execute commands,
    and make changes to your codebase with appropriate approval modes.
    
    Args:
        prompt: The task or question to send to Codex
        model: AI model to use (default: o4-mini, options: o4-mini, o4-preview, gpt-4.1, etc.)
        approval_mode: Agent autonomy level:
            - "suggest": Only suggests changes, requires approval for all actions (default, safest)
            - "auto-edit": Can read and write files automatically, asks for shell commands
            - "full-auto": Full autonomy with network-disabled sandbox (most powerful)
        images: List of image paths or data URIs to include (for multimodal tasks)
        provider: AI provider (openai, azure, gemini, ollama, mistral, deepseek, xai, groq, etc.)
        json_output: Return structured JSON output when possible
        task_type: Type of task for optimized prompting:
            - "general": General coding assistance (default)
            - "code-generation": Generate new code
            - "code-explanation": Explain existing code
            - "debugging": Find and fix bugs
            - "refactoring": Improve code structure
            - "testing": Write or fix tests
            - "security": Security analysis and fixes
            - "documentation": Generate or improve documentation
        additional_args: Additional CLI arguments to pass to Codex
        
    Returns:
        Dictionary with status, output, and execution details
        
    Examples:
        # Basic code generation
        codex_agent("Create a Python function to calculate fibonacci numbers")
        
        # Code explanation with auto-edit mode
        codex_agent("Explain this codebase to me", approval_mode="auto-edit")
        
        # Debugging with specific model
        codex_agent("Fix the bug in utils.py", model="o4-preview", task_type="debugging")
        
        # Multimodal task with image
        codex_agent("Implement this UI design", images=["design.png"], task_type="code-generation")
        
        # Security analysis
        codex_agent("Review this code for security vulnerabilities", task_type="security")
    """
    if not prompt:
        return {
            "status": "error",
            "error": "Missing required parameter: prompt"
        }
    
    # Optimize prompt based on task type
    optimized_prompt = _optimize_prompt_for_task(prompt, task_type)
    
    return run_codex(
        prompt=optimized_prompt,
        model=model,
        images=images or [],
        approval_mode=approval_mode,
        json_output=json_output,
        provider=provider,
        additional_args=additional_args or []
    )


def _optimize_prompt_for_task(prompt: str, task_type: str) -> str:
    """
    Optimize the prompt based on the task type for better results.
    """
    task_prefixes = {
        "code-generation": "Generate clean, well-documented code for the following task:\n\n",
        "code-explanation": "Provide a detailed explanation of the following code, including what it does, how it works, and any notable patterns:\n\n",
        "debugging": "Analyze the following code/issue for bugs, explain the problems found, and provide fixes:\n\n",
        "refactoring": "Refactor the following code to improve readability, performance, and maintainability:\n\n",
        "testing": "Write comprehensive tests for the following code or fix existing test issues:\n\n",
        "security": "Perform a security analysis of the following code, identify vulnerabilities, and suggest fixes:\n\n",
        "documentation": "Generate or improve documentation for the following code:\n\n",
        "general": ""  # No prefix for general tasks
    }
    
    prefix = task_prefixes.get(task_type, "")
    return prefix + prompt


@mcp.tool()
def codex_interactive(
    initial_prompt: Optional[str] = None,
    model: str = "o4-mini",
    approval_mode: str = "suggest",
    provider: Optional[str] = None
) -> Dict[str, Any]:
    """
    Start an interactive Codex session (REPL mode).
    
    This launches Codex in interactive mode where you can have a conversation
    with the coding agent. Useful for iterative development and exploration.
    
    Args:
        initial_prompt: Optional initial prompt to start the session
        model: AI model to use (default: o4-mini)
        approval_mode: Agent autonomy level (suggest, auto-edit, full-auto)
        provider: AI provider to use
        
    Returns:
        Dictionary with session information and instructions
        
    Note: This starts an interactive session that requires terminal access.
    For non-interactive use, prefer the codex_agent tool.
    """
    # 対話モードは素の `codex [PROMPT]`（exec サブコマンドは付けない）。v0.120.0
    cmd = ["codex"]
    cmd.extend(_build_common_flags(model=model, provider=provider, approval_mode=approval_mode))

    if initial_prompt:
        cmd.append(initial_prompt)
    
    return {
        "status": "info",
        "message": "Interactive Codex session would be started with the following command:",
        "command": " ".join(cmd),
        "note": "This requires terminal access. For automated tasks, use codex_agent instead.",
        "instructions": [
            "Run this command in your terminal to start the interactive session",
            "Type 'exit' or press Ctrl+C to end the session",
            "Use different approval modes for varying levels of autonomy"
        ]
    }


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="OpenAI Codex MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python codex_server.py                    # Run in stdio mode (default)
  python codex_server.py --mode stdio       # Run in stdio mode explicitly
  python codex_server.py --mode sse         # Run in SSE mode
  python codex_server.py --mode sse --port 8080  # Run in SSE mode on port 8080
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["stdio", "sse"],
        default="stdio",
        help="Server mode: stdio for standard input/output, sse for Server-Sent Events (default: stdio)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number for SSE mode (default: 8000)"
    )
    
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host address for SSE mode (default: localhost)"
    )
    
    return parser.parse_args()


def main():
    """Main entry point for the MCP server."""
    # Parse command line arguments
    args = parse_args()
    
    # Check if codex is installed
    try:
        result = subprocess.run(["which", "codex"], capture_output=True, text=True)
        if result.returncode != 0:
            print("ERROR: 'codex' command not found in PATH", file=sys.stderr)
            print("Please install the OpenAI Codex CLI: npm install -g @openai/codex", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error checking for codex: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.mode == "stdio":
        print("Starting OpenAI Codex MCP Server in stdio mode...", file=sys.stderr)
        print("Available tools: codex_agent, codex_interactive", file=sys.stderr)
        print("Server will communicate via standard input/output", file=sys.stderr)
        mcp.run()
    elif args.mode == "sse":
        print(f"Starting OpenAI Codex MCP Server in SSE mode...", file=sys.stderr)
        print(f"Server will run on http://{args.host}:{args.port}", file=sys.stderr)
        print("Available tools: codex_agent, codex_interactive", file=sys.stderr)
        print("Server will use Server-Sent Events for communication", file=sys.stderr)
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        print(f"Unknown mode: {args.mode}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()