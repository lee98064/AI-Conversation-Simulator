import os
import json
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from dotenv import load_dotenv
import openai
import threading
import time
from datetime import datetime
import csv
from io import StringIO

# Import database module
from database.db_manager import DatabaseManager

# Load environment variables
load_dotenv()

# Configure OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "default_secret_key")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database
db_manager = DatabaseManager()

# Global variables
conversation_active = False
conversation_thread = None
conversation_id = None

# Token pricing per 1000 tokens in USD (updated as of 2025)
MODEL_PRICES = {
    # GPT-4 models
    'gpt-4o': {'input': 5.0, 'output': 15.0},       # GPT-4o input/output costs
    'gpt-4-turbo': {'input': 10.0, 'output': 30.0}, # GPT-4 Turbo input/output costs
    'gpt-4': {'input': 30.0, 'output': 60.0},       # GPT-4 input/output costs
    
    # GPT-3.5 models
    'gpt-3.5-turbo': {'input': 0.5, 'output': 1.5}, # GPT-3.5 Turbo input/output costs
}

# USD to TWD conversion rate (updated for 2025)
USD_TO_TWD = 31.5  # 1 USD = 31.5 TWD

# Available models
available_models = [
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo"
]

# Routes
@app.route('/')
def index():
    return render_template('index.html', models=available_models)

# API routes
@app.route('/api/models', methods=['GET'])
def get_models():
    return jsonify({"models": available_models})

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    conversations = db_manager.get_all_conversations()
    return jsonify({"conversations": conversations})

@app.route('/api/conversation/<int:conv_id>', methods=['GET'])
def get_conversation(conv_id):
    conversation = db_manager.get_conversation_by_id(conv_id)
    if conversation:
        messages = db_manager.get_messages_by_conversation_id(conv_id)
        token_stats = db_manager.get_conversation_token_stats(conv_id)
        return jsonify({
            "conversation": conversation, 
            "messages": messages,
            "token_stats": token_stats
        })
    return jsonify({"error": "Conversation not found"}), 404

@app.route('/api/conversation/<int:conv_id>/token_stats', methods=['GET'])
def get_conversation_token_stats(conv_id):
    token_stats = db_manager.get_conversation_token_stats(conv_id)
    if token_stats:
        return jsonify({"token_stats": token_stats})
    return jsonify({"error": "Conversation not found or no token data available"}), 404

@app.route('/api/conversation/<int:conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    success = db_manager.delete_conversation(conv_id)
    if success:
        return jsonify({"status": "success", "message": f"Conversation {conv_id} deleted"})
    return jsonify({"error": "Failed to delete conversation"}), 500

@app.route('/api/conversation/<int:conv_id>/export', methods=['GET'])
def export_conversation(conv_id):
    format_type = request.args.get('format', 'csv')
    conversation = db_manager.get_conversation_by_id(conv_id)
    messages = db_manager.get_messages_by_conversation_id(conv_id)
    token_stats = db_manager.get_conversation_token_stats(conv_id)
    
    if not conversation:
        return jsonify({"error": "Conversation not found"}), 404
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"conversation_{conv_id}_{timestamp}"
    
    if format_type == 'csv':
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Timestamp', 'Bot', 'Message', 'Prompt Tokens', 'Completion Tokens', 'Total Tokens', 'Cost (TWD)'])
        for msg in messages:
            writer.writerow([
                msg['timestamp'], 
                msg['bot_name'], 
                msg['content'],
                msg.get('prompt_tokens', 0),
                msg.get('completion_tokens', 0),
                msg.get('total_tokens', 0),
                f"NT$ {msg.get('cost', 0):.2f}"
            ])
        
        # Add token summary
        if token_stats:
            writer.writerow([])
            writer.writerow(['Token Summary'])
            writer.writerow(['Total Tokens', token_stats['total_tokens']])
            writer.writerow(['Total Cost (TWD)', f"NT$ {token_stats['total_cost']:.2f}"])
        
        response = app.response_class(
            response=output.getvalue(),
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment;filename={filename}.csv"}
        )
        return response
    
    elif format_type == 'txt':
        output = ""
        for msg in messages:
            output += f"[{msg['timestamp']}] {msg['bot_name']}: {msg['content']}\n"
            if 'total_tokens' in msg and msg['total_tokens'] > 0:
                output += f"Tokens: {msg.get('total_tokens', 0)} (Prompt: {msg.get('prompt_tokens', 0)}, Completion: {msg.get('completion_tokens', 0)})\n"
                output += f"Cost: NT$ {msg.get('cost', 0):.2f}\n"
            output += "\n"
        
        # Add token summary
        if token_stats:
            output += "\n--- Token Summary ---\n"
            output += f"Total Tokens: {token_stats['total_tokens']}\n"
            output += f"Total Cost: NT$ {token_stats['total_cost']:.2f}\n"
        
        response = app.response_class(
            response=output,
            mimetype='text/plain',
            headers={"Content-Disposition": f"attachment;filename={filename}.txt"}
        )
        return response
    
    return jsonify({"error": "Invalid format specified"}), 400

# Helper function to calculate token cost
def calculate_cost(model, prompt_tokens, completion_tokens):
    if model not in MODEL_PRICES:
        # Use GPT-3.5-turbo pricing as fallback
        model = 'gpt-3.5-turbo'
    
    # Calculate cost in USD (divide by 1000 since pricing is per 1000 tokens)
    input_cost_usd = (prompt_tokens / 1000.0) * MODEL_PRICES[model]['input']
    output_cost_usd = (completion_tokens / 1000.0) * MODEL_PRICES[model]['output']
    total_cost_usd = input_cost_usd + output_cost_usd
    
    # Convert to TWD with precision
    cost_twd = total_cost_usd * USD_TO_TWD
    
    return cost_twd

# Socket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')
    global conversation_active
    conversation_active = False

@socketio.on('start_conversation')
def handle_start_conversation(data):
    global conversation_active, conversation_thread, conversation_id
    
    if conversation_active:
        return {"status": "error", "message": "Conversation already active"}
    
    # Get parameters from request
    bot1_name = data.get('bot1_name', 'Bot 1')
    bot1_system_prompt = data.get('bot1_system_prompt', 'You are a helpful AI assistant.')
    bot1_model = data.get('bot1_model', 'gpt-3.5-turbo')
    
    bot2_name = data.get('bot2_name', 'Bot 2')
    bot2_system_prompt = data.get('bot2_system_prompt', 'You are a helpful AI assistant.')
    bot2_model = data.get('bot2_model', 'gpt-3.5-turbo')
    
    initial_message = data.get('initial_message', 'Hello! Let\'s have a conversation.')
    
    # Create a new conversation in database
    conversation_id = db_manager.create_conversation(
        bot1_name, bot1_system_prompt, bot1_model,
        bot2_name, bot2_system_prompt, bot2_model
    )
    
    # Start conversation thread
    conversation_active = True
    conversation_thread = threading.Thread(
        target=run_conversation,
        args=(
            conversation_id,
            bot1_name, bot1_system_prompt, bot1_model,
            bot2_name, bot2_system_prompt, bot2_model,
            initial_message
        )
    )
    conversation_thread.daemon = True
    conversation_thread.start()
    
    return {"status": "success", "conversation_id": conversation_id}

@socketio.on('pause_conversation')
def handle_pause_conversation(data=None):
    global conversation_active
    conversation_active = False
    return {"status": "success", "message": "Conversation paused"}

@socketio.on('resume_conversation')
def handle_resume_conversation(data=None):
    global conversation_active, conversation_thread, conversation_id
    
    if conversation_thread and conversation_thread.is_alive():
        conversation_active = True
        return {"status": "success", "message": "Conversation resumed"}
    
    return {"status": "error", "message": "No conversation to resume"}

@socketio.on('update_system_prompts')
def handle_update_system_prompts(data):
    global conversation_active
    
    if not conversation_active:
        return {"status": "error", "message": "No active conversation to update"}
    
    bot1_system_prompt = data.get('bot1_system_prompt')
    bot2_system_prompt = data.get('bot2_system_prompt')
    
    # Update in database
    db_manager.update_bot_system_prompts(
        conversation_id, 
        bot1_system_prompt, 
        bot2_system_prompt
    )
    
    return {"status": "success", "message": "System prompts updated"}

def run_conversation(
    conv_id, 
    bot1_name, bot1_system_prompt, bot1_model,
    bot2_name, bot2_system_prompt, bot2_model,
    initial_message
):
    global conversation_active
    
    # Initialize conversation history for each bot
    bot1_messages = [{"role": "system", "content": bot1_system_prompt}]
    bot2_messages = [{"role": "system", "content": bot2_system_prompt}]
    
    # Start with initial message from Bot 1
    current_message = initial_message
    current_bot = "bot1"
    
    # Add initial message to database with zero tokens (it's not from API)
    db_manager.add_message_with_tokens(conv_id, bot1_name, current_message, 0, 0, 0)
    
    # Emit initial message to frontend
    socketio.emit('new_message', {
        'bot': bot1_name,
        'message': current_message,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'tokens': 0,
        'cost': 0
    })
    
    # Emit token stats update
    token_stats = db_manager.get_conversation_token_stats(conv_id)
    socketio.emit('token_stats_update', token_stats)
    
    # Main conversation loop
    while conversation_active:
        try:
            # Determine which bot is replying and update history
            if current_bot == "bot1":
                responding_bot = bot2_name
                responding_model = bot2_model
                messages = bot2_messages + [{"role": "user", "content": current_message}]
                next_bot = "bot2"
            else:
                responding_bot = bot1_name
                responding_model = bot1_model
                messages = bot1_messages + [{"role": "user", "content": current_message}]
                next_bot = "bot1"
            
            # Get response from OpenAI API
            response = openai.chat.completions.create(
                model=responding_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            
            # Extract response text and token usage
            reply = response.choices[0].message.content
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens
            
            # Calculate cost
            cost = calculate_cost(responding_model, prompt_tokens, completion_tokens)
            
            # Update conversation history
            if current_bot == "bot1":
                bot2_messages.append({"role": "user", "content": current_message})
                bot2_messages.append({"role": "assistant", "content": reply})
            else:
                bot1_messages.append({"role": "user", "content": current_message})
                bot1_messages.append({"role": "assistant", "content": reply})
            
            # Store message in database with token information
            db_manager.add_message_with_tokens(
                conv_id, 
                responding_bot, 
                reply, 
                prompt_tokens, 
                completion_tokens, 
                cost
            )
            
            # Emit message to frontend
            socketio.emit('new_message', {
                'bot': responding_bot,
                'message': reply,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'cost': cost
            })
            
            # Emit updated token stats
            token_stats = db_manager.get_conversation_token_stats(conv_id)
            socketio.emit('token_stats_update', token_stats)
            
            # Update current message and bot for next iteration
            current_message = reply
            current_bot = next_bot
            
            # Small delay to avoid API rate limits
            time.sleep(1)
            
        except Exception as e:
            print(f"Error in conversation: {str(e)}")
            socketio.emit('error', {'message': f"Error: {str(e)}"})
            break

if __name__ == '__main__':
    # Ensure database tables are created
    db_manager.init_db()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)