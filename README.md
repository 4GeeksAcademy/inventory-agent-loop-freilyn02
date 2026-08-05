# AI Inventory Agent Loop

A two-component inventory management system:

1. A FastAPI service that manages product stock, persisted to `products.csv`.
2. A Python AI agent that talks to the user in natural language and uses the
   API as tools through a manually implemented Observe -> Think -> Act ->
   Update -> Repeat loop, powered by Groq.

## Project structure

.
├── api/
│ ├── init.py
│ └── app.py # FastAPI inventory service
├── agent.py # AI agent with manual tool-calling loop
├── products.csv # created automatically by the API (not versioned)
├── conversation_log.csv # created automatically by the agent (not versioned)
├── requirements.txt
└── .env.example


## Setup

1. Clone this repository and create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Create your `.env` file from the example and add your Groq API key
   (get one for free at https://console.groq.com/keys):

```bash
cp .env.example .env
# then edit .env and set GROQ_API_KEY=your_real_key
```

## Running the project (two terminals)

**Terminal 1 — start the inventory API:**

```bash
source venv/bin/activate
uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`, with interactive docs
at `http://localhost:8000/docs`. `products.csv` is created automatically on
first run.

**Terminal 2 — start the agent:**

```bash
source venv/bin/activate
python agent.py
```

Type natural language messages at the `You:` prompt. Type `quit` or `exit`
to stop. `conversation_log.csv` is created automatically and appended to on
every event.

## Example interactions

You: create a product called oat milk with 5 units
Agent: The product 'oat milk' has been created with 5 units.

You: we just received 30 units of oat milk
Agent: The stock of oat milk has been updated to 35 units.

You: we sold 12 bags of arabica today
Agent: 12 bags of arabica have been sold, leaving 8 bags in stock.

You: what products are running low?
Agent: The product 'arabica' with 8 bags is currently running low on stock.


## API endpoints

| Method | Endpoint                 | Description                                  |
|--------|---------------------------|-----------------------------------------------|
| GET    | `/inventory`               | List all products                            |
| POST   | `/inventory`                | Create a new product (`name`, `quantity`, `unit`) |
| PATCH  | `/inventory/{product_id}`   | Apply a signed stock delta                   |
| GET    | `/inventory/alerts`         | List products below threshold (default 10)   |

## Notes

- No agent framework is used — the tool-calling loop in `agent.py` is
  manually implemented.
- `products.csv` and `conversation_log.csv` are regenerated automatically on
  first run and are not committed to version control.
- The agent retries once on transient LLM tool-call generation failures
  before falling back to an error message.