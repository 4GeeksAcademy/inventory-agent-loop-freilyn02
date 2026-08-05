import os
import json
import csv
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

API_BASE_URL = "http://localhost:8000"
GROQ_MODEL = "llama-3.3-70b-versatile"

client = Groq(api_key=os.environ["GROQ_API_KEY"])

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": "Get the current list of all products in the inventory, including their id, name, quantity, and unit.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_product",
            "description": "Create a new product in the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The product name"},
                    "quantity": {"type": "integer", "description": "The initial stock quantity"},
                    "unit": {"type": "string", "description": "The unit of measurement, e.g. 'units', 'kg', 'bags'"},
                },
                "required": ["name", "quantity", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_stock",
            "description": "Apply a signed quantity change (delta) to an existing product's stock. Use a positive delta to add stock (e.g. a shipment arrived) and a negative delta to remove stock (e.g. items were sold).",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "The id of the product to update"},
                    "delta": {"type": "integer", "description": "The signed quantity change, positive or negative"},
                },
                "required": ["product_id", "delta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "Get the list of products whose quantity is below a threshold (default 10). Use this to answer questions like 'what products are running low?'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "integer", "description": "Optional custom threshold. Defaults to 10 if not provided."},
                },
                "required": [],
            },
        },
    },
]


def call_get_inventory():
    response = requests.get(f"{API_BASE_URL}/inventory")
    response.raise_for_status()
    return response.json()


def call_create_product(name, quantity, unit):
    response = requests.post(
        f"{API_BASE_URL}/inventory",
        json={"name": name, "quantity": quantity, "unit": unit},
    )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "Unknown error")
        except ValueError:
            detail = f"Unknown error (status {response.status_code})"
        return {"error": detail}
    return response.json()


def call_update_stock(product_id, delta):
    response = requests.patch(
        f"{API_BASE_URL}/inventory/{product_id}",
        json={"delta": delta},
    )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "Unknown error")
        except ValueError:
            detail = f"Unknown error (status {response.status_code})"
        return {"error": detail}
    return response.json()


def call_get_low_stock_alerts(threshold=None):
    params = {"threshold": threshold} if threshold is not None else {}
    response = requests.get(f"{API_BASE_URL}/inventory/alerts", params=params)
    response.raise_for_status()
    return response.json()


TOOL_FUNCTIONS = {
    "get_inventory": call_get_inventory,
    "create_product": call_create_product,
    "update_stock": call_update_stock,
    "get_low_stock_alerts": call_get_low_stock_alerts,
}

CONVERSATION_LOG_FILE = "conversation_log.csv"
LOG_FIELDS = ["actor", "message", "tool_call", "timestamp"]


def ensure_conversation_log_exists():
    """Create conversation_log.csv with headers if it doesn't exist yet."""
    if not os.path.exists(CONVERSATION_LOG_FILE):
        with open(CONVERSATION_LOG_FILE, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
            writer.writeheader()


def log_event(actor, message, tool_call=""):
    """Append a single event to conversation_log.csv. Never overwrites existing rows."""
    with open(CONVERSATION_LOG_FILE, mode="a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        writer.writerow({
            "actor": actor,
            "message": message,
            "tool_call": tool_call,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


ensure_conversation_log_exists()

SYSTEM_PROMPT = """You are an inventory management assistant for a small warehouse.
You help the user check stock levels, register incoming shipments, register sales, \
create new products, and check which products are running low on stock.

Always use the available tools to read or modify inventory data — never guess or make up \
quantities or product ids. If the user mentions a product by name but you don't know its id, \
call get_inventory first to look it up.

When you have completed the user's request, reply with a clear, concise confirmation \
in plain English, including the relevant quantities."""


def run_agent_turn(messages):
    """
    Run one full Observe -> Think -> Act -> Update -> Repeat cycle for the current
    conversation state, until the LLM returns a final answer with no pending tool calls.
    Mutates `messages` in place and returns the final assistant text response.
    """
    while True:
        completion = None
        last_error = None
        for attempt in range(2):
            try:
                completion = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice="auto",
                )
                break
            except Exception as e:
                last_error = e

        if completion is None:
            error_text = (
                "I ran into an internal error while processing that request. "
                "Could you please rephrase it, one step at a time?"
            )
            log_event(actor="agent", message=f"LLM call failed after retry: {last_error}")
            messages.append({"role": "assistant", "content": error_text})
            return error_text

        response_message = completion.choices[0].message
        tool_calls = response_message.tool_calls

        if not tool_calls:
            final_text = response_message.content
            messages.append({"role": "assistant", "content": final_text})
            log_event(actor="agent", message=final_text)
            return final_text

        messages.append(response_message)

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments) or {}

            log_event(
                actor="agent",
                message=f"Calling tool {function_name}",
                tool_call=json.dumps({"name": function_name, "arguments": function_args}),
            )

            tool_function = TOOL_FUNCTIONS[function_name]
            result = tool_function(**function_args)

            log_event(
                actor="tool",
                message=json.dumps(result),
                tool_call=function_name,
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })


def main():
    print("Inventory Agent — type your message, or 'quit' to exit.\n")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in ("quit", "exit"):
            print("Agent: Goodbye!")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        log_event(actor="user", message=user_input)

        final_response = run_agent_turn(messages)

        print(f"Agent: {final_response}\n")


if __name__ == "__main__":
    main()