"""Thin wrapper around the OpenAI Responses API: file search setup, structured
output parsing, and a function-calling loop. Every other agent stage builds on
these three primitives instead of talking to the SDK directly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

MODEL = os.environ.get("DEALLENS_MODEL", "gpt-4.1")
T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def create_vector_store_with_files(file_paths: list[str], name: str = "deallens-docs") -> str:
    """Uploads documents and returns a vector store id usable with the file_search tool."""
    client = get_client()
    vector_store = client.vector_stores.create(name=name)
    for path in file_paths:
        with open(path, "rb") as f:
            client.vector_stores.files.upload_and_poll(vector_store_id=vector_store.id, file=f)
    return vector_store.id


def run_structured(
    instructions: str,
    input_text: str,
    text_format: Type[T],
    vector_store_id: str | None = None,
) -> T:
    """Single-shot call that returns a validated Pydantic object, optionally grounded in file_search."""
    client = get_client()
    tools = [{"type": "file_search", "vector_store_ids": [vector_store_id]}] if vector_store_id else None
    response = client.responses.parse(
        model=MODEL,
        instructions=instructions,
        input=input_text,
        tools=tools,
        text_format=text_format,
    )
    return response.output_parsed


def run_with_tools(
    instructions: str,
    input_text: str,
    text_format: Type[T],
    tool_schemas: list[dict],
    tool_functions: dict,
    vector_store_id: str | None = None,
    max_turns: int = 6,
) -> tuple[T, list[dict]]:
    """Function-calling loop: the model may call tools before returning the structured result.

    Returns (parsed_result, tool_call_log) where tool_call_log records every
    function call made and its result, for transparency in the Evidence page.
    """
    client = get_client()
    tools = list(tool_schemas)
    if vector_store_id:
        tools.append({"type": "file_search", "vector_store_ids": [vector_store_id]})

    input_items: list[dict] = [{"role": "user", "content": input_text}]
    tool_call_log: list[dict] = []
    response = client.responses.create(
        model=MODEL, instructions=instructions, input=input_items, tools=tools
    )

    for _ in range(max_turns):
        function_calls = [item for item in response.output if item.type == "function_call"]
        if not function_calls:
            break
        input_items += response.output
        for call in function_calls:
            args = json.loads(call.arguments)
            fn = tool_functions[call.name]
            try:
                result = fn(**args)
            except Exception as exc:  # surfaced to the model so it can correct itself
                result = {"error": str(exc)}
            tool_call_log.append({"name": call.name, "arguments": args, "result": result})
            input_items.append(
                {"type": "function_call_output", "call_id": call.call_id, "output": json.dumps(result)}
            )
        response = client.responses.create(
            model=MODEL, instructions=instructions, input=input_items, tools=tools
        )

    parsed = client.responses.parse(
        model=MODEL,
        instructions=instructions
        + "\n\nReturn only the final structured result now; do not call any more tools.",
        input=input_items + [{"role": "user", "content": "Summarize your work into the required structured output."}],
        text_format=text_format,
    )
    return parsed.output_parsed, tool_call_log
