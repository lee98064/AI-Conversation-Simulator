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
import hashlib
import requests
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Any
from cachetools import TTLCache
import tiktoken

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

# Token pricing configuration
class TokenConfig:
    DATA_DIR = os.path.join(os.getcwd(), "data")
    CACHE_DIR = os.path.join(DATA_DIR, ".cache")
    DECIMALS = "0.00000001"
    DEBUG = False
    CACHE_TTL = 432000  # 5 days cache TTL for model pricing
    CACHE_MAXSIZE = 16
    USD_TO_TWD = 31.5  # 1 USD = 31.5 TWD

# Initialize token pricing cache
token_cache = TTLCache(maxsize=TokenConfig.CACHE_MAXSIZE, ttl=TokenConfig.CACHE_TTL)

# Available models
available_models = [
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo"
]

# Helper function to get encoding for a model
def get_encoding(model):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")

# Model Cost Manager class
class ModelCostManager:
    _instance = None
    _best_match_cache = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelCostManager, cls).__new__(cls)
            cls._instance.url = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
            cls._instance.cache_file_path = cls._instance._get_cache_filename()
            cls._instance._ensure_cache_dir()
        return cls._instance
    
    def _ensure_cache_dir(self):
        if not os.path.exists(TokenConfig.CACHE_DIR):
            os.makedirs(TokenConfig.CACHE_DIR)
    
    def _get_cache_filename(self):
        cache_file_name = hashlib.sha256(self.url.encode()).hexdigest() + ".json"
        return os.path.normpath(os.path.join(TokenConfig.CACHE_DIR, cache_file_name))
    
    def _is_cache_valid(self, cache_file_path):
        if not os.path.exists(cache_file_path):
            return False
        cache_file_mtime = os.path.getmtime(cache_file_path)
        return time.time() - cache_file_mtime < TokenConfig.CACHE_TTL
    
    def get_cost_data(self):
        """获取模型价格数据，优先从缓存获取"""
        if os.path.exists(self.cache_file_path) and self._is_cache_valid(self.cache_file_path):
            with open(self.cache_file_path, "r", encoding="UTF-8") as cache_file:
                return json.load(cache_file)
        
        try:
            response = requests.get(self.url)
            response.raise_for_status()
            data = response.json()
            
            # 备份和存储新的价格数据
            if os.path.exists(self.cache_file_path):
                os.rename(self.cache_file_path, self.cache_file_path + ".bkp")
                
            with open(self.cache_file_path, "w", encoding="UTF-8") as cache_file:
                json.dump(data, cache_file)
            
            return data
        except Exception as e:
            print(f"Error fetching model price data: {e}")
            # 尝试使用备份
            if os.path.exists(self.cache_file_path + ".bkp"):
                with open(self.cache_file_path + ".bkp", "r", encoding="UTF-8") as cache_file:
                    return json.load(cache_file)
            # 如果没有备份，使用内置默认价格
            return self._get_default_pricing()
    
    def _get_default_pricing(self):
        """返回默认价格，当在线获取失败时使用"""
        return {
            "gpt-4o": {
                "input_cost_per_token": 0.000005,
                "output_cost_per_token": 0.000015
            },
            "gpt-4-turbo": {
                "input_cost_per_token": 0.00001,
                "output_cost_per_token": 0.00003
            },
            "gpt-4": {
                "input_cost_per_token": 0.00003,
                "output_cost_per_token": 0.00006
            },
            "gpt-3.5-turbo": {
                "input_cost_per_token": 0.0000005,
                "output_cost_per_token": 0.0000015
            }
        }
    
    def get_model_data(self, model: str) -> Dict[str, Any]:
        """获取指定模型的价格数据"""
        if model in self._best_match_cache:
            return self._best_match_cache[model]
        
        json_data = self.get_cost_data()
        sanitized_model = self._sanitize_model_name(model)
        
        # 直接匹配
        if sanitized_model in json_data:
            self._best_match_cache[model] = json_data[sanitized_model]
            return json_data[sanitized_model]
        
        # 部分匹配
        for key in json_data:
            if sanitized_model in key or key in sanitized_model:
                self._best_match_cache[model] = json_data[key]
                return json_data[key]
        
        # 如果都找不到匹配，使用默认价格或者模型别名映射
        default_pricing = self._get_default_pricing()
        if model in default_pricing:
            self._best_match_cache[model] = default_pricing[model]
            return default_pricing[model]
        
        # 使用gpt-3.5-turbo作为后备方案
        self._best_match_cache[model] = default_pricing["gpt-3.5-turbo"]
        return default_pricing["gpt-3.5-turbo"]
    
    def _sanitize_model_name(self, name: str) -> str:
        """清理模型名称，移除前缀和后缀"""
        prefixes = ["openai/", "github/", "google_genai/", "deepseek/"]
        suffixes = ["-tuned"]
        # 移除前缀
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
        # 移除后缀
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.lower().strip()

# Cost Calculator class
class CostCalculator:
    def __init__(self):
        self.model_cost_manager = ModelCostManager()
    
    def calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
        """计算使用模型的成本"""
        model_pricing_data = self.model_cost_manager.get_model_data(model)
        
        # 获取每个token的输入输出成本
        input_cost_per_token = Decimal(str(model_pricing_data.get("input_cost_per_token", 0)))
        output_cost_per_token = Decimal(str(model_pricing_data.get("output_cost_per_token", 0)))
        
        # 计算成本
        input_cost = Decimal(prompt_tokens) * input_cost_per_token
        output_cost = Decimal(completion_tokens) * output_cost_per_token
        
        # 计算总成本(美元)并转换为新台币
        total_cost_usd = input_cost + output_cost
        total_cost_twd = total_cost_usd * Decimal(TokenConfig.USD_TO_TWD)
        
        # 四舍五入到指定精度
        total_cost_twd = total_cost_twd.quantize(Decimal(TokenConfig.DECIMALS), rounding=ROUND_HALF_UP)
        
        return total_cost_twd

# 初始化成本计算器
cost_calculator = CostCalculator()

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
        # Convert any possible Decimal values to float for JSON serialization
        token_stats['total_cost'] = float(token_stats['total_cost'])
        
        # Convert any Decimal values in bot_stats
        if 'bot_stats' in token_stats:
            for bot_name in token_stats['bot_stats']:
                if 'cost' in token_stats['bot_stats'][bot_name]:
                    token_stats['bot_stats'][bot_name]['cost'] = float(token_stats['bot_stats'][bot_name]['cost'])
        
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

# Helper function to calculate token count
def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Calculate the number of tokens in a text string"""
    enc = get_encoding(model)
    return len(enc.encode(text))

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
            cost = cost_calculator.calculate_cost(responding_model, prompt_tokens, completion_tokens)
            
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
                float(cost)  # Convert Decimal to float for SQLite compatibility
            )
            
            # Emit message to frontend
            socketio.emit('new_message', {
                'bot': responding_bot,
                'message': reply,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
                'cost': float(cost)  # Convert Decimal to float for JSON serialization
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