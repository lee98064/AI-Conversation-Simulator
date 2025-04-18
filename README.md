# AI Conversation Simulator

A web application that allows two OpenAI LLM bots to converse with each other. Users can control system prompts, settings, and export conversations.

## Features

- Real-time conversation between two AI bots using OpenAI API
- Beautiful web interface for visualization
- Dynamic adjustment of system prompts during the conversation
- SQLite database to store conversation history
- Export conversations to CSV or TXT format
- Start/pause functionality
- Model selection for each bot
- Real-time view of both bots' conversation

## Installation

1. Clone the repository
2. Install dependencies:
```
cd ai-coversation
poetry install
```

3. Create a `.env` file in the `src` directory with your OpenAI API key:
```
# Copy from .env.example
cp src/.env.example src/.env
# Edit with your API key
nano src/.env
```

## Usage

1. Run the application:
```
cd src
poetry run python main.py
```

2. Open your web browser and go to `http://localhost:5000`

3. Configure settings for both bots:
   - Set names for each bot
   - Select models (e.g., gpt-4, gpt-3.5-turbo)
   - Set system prompts
   - Enter an initial message

4. Click "Start" to begin the conversation

5. During the conversation:
   - You can pause/resume at any time
   - You can modify system prompts dynamically
   - Export the conversation to CSV or TXT format

## Requirements

- Python 3.10+
- OpenAI API key

## License

MIT