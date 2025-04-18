import sqlite3
import os
import json
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Use default path in the project directory
            self.db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'conversations.db')
        else:
            self.db_path = db_path
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialize the database with necessary tables."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Create conversations table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            bot1_name TEXT,
            bot1_system_prompt TEXT,
            bot1_model TEXT,
            bot2_name TEXT,
            bot2_system_prompt TEXT,
            bot2_model TEXT,
            total_tokens INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0.0
        )
        ''')
        
        # Create messages table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER,
            timestamp TEXT,
            bot_name TEXT,
            content TEXT,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_conversation(self, bot1_name, bot1_system_prompt, bot1_model, 
                           bot2_name, bot2_system_prompt, bot2_model):
        """Create a new conversation and return its ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
        INSERT INTO conversations 
            (timestamp, bot1_name, bot1_system_prompt, bot1_model, 
             bot2_name, bot2_system_prompt, bot2_model)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp, bot1_name, bot1_system_prompt, bot1_model,
            bot2_name, bot2_system_prompt, bot2_model
        ))
        
        # Get the ID of the inserted conversation
        conversation_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return conversation_id
    
    def add_message(self, conversation_id, bot_name, content):
        """Add a new message to an existing conversation."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute('''
        INSERT INTO messages 
            (conversation_id, timestamp, bot_name, content)
        VALUES (?, ?, ?, ?)
        ''', (conversation_id, timestamp, bot_name, content))
        
        conn.commit()
        conn.close()
    
    def add_message_with_tokens(self, conversation_id, bot_name, content, prompt_tokens, completion_tokens, cost):
        """Add a new message to an existing conversation with token usage data."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_tokens = prompt_tokens + completion_tokens
        
        cursor.execute('''
        INSERT INTO messages 
            (conversation_id, timestamp, bot_name, content, prompt_tokens, completion_tokens, total_tokens, cost)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (conversation_id, timestamp, bot_name, content, prompt_tokens, completion_tokens, total_tokens, cost))
        
        # Update the conversation's total tokens and cost
        cursor.execute('''
        UPDATE conversations
        SET total_tokens = total_tokens + ?,
            total_cost = total_cost + ?
        WHERE id = ?
        ''', (total_tokens, cost, conversation_id))
        
        conn.commit()
        conn.close()

    def get_conversation_token_stats(self, conversation_id):
        """Get token usage statistics for a specific conversation."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Get the total stats from conversation
        cursor.execute('SELECT total_tokens, total_cost FROM conversations WHERE id = ?', (conversation_id,))
        conv_row = cursor.fetchone()
        
        if not conv_row:
            conn.close()
            return None
        
        # Get bot specific stats
        cursor.execute('''
        SELECT bot_name, SUM(prompt_tokens) as prompt_tokens, 
               SUM(completion_tokens) as completion_tokens, 
               SUM(total_tokens) as total_tokens,
               SUM(cost) as cost
        FROM messages
        WHERE conversation_id = ?
        GROUP BY bot_name
        ''', (conversation_id,))
        
        bot_stats = {}
        for row in cursor.fetchall():
            bot_stats[row['bot_name']] = {
                'prompt_tokens': row['prompt_tokens'],
                'completion_tokens': row['completion_tokens'],
                'total_tokens': row['total_tokens'],
                'cost': row['cost']
            }
        
        conn.close()
        
        return {
            'total_tokens': conv_row['total_tokens'],
            'total_cost': conv_row['total_cost'],
            'bot_stats': bot_stats
        }

    def get_all_conversations(self):
        """Get all conversations."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM conversations ORDER BY timestamp DESC')
        rows = cursor.fetchall()
        
        conversations = []
        for row in rows:
            conversation = dict(row)
            conversations.append(conversation)
        
        conn.close()
        return conversations
    
    def get_conversation_by_id(self, conversation_id):
        """Get a conversation by ID."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM conversations WHERE id = ?', (conversation_id,))
        row = cursor.fetchone()
        
        if row:
            conversation = dict(row)
        else:
            conversation = None
        
        conn.close()
        return conversation
    
    def get_messages_by_conversation_id(self, conversation_id):
        """Get all messages for a specific conversation."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC', 
                      (conversation_id,))
        rows = cursor.fetchall()
        
        messages = []
        for row in rows:
            message = dict(row)
            messages.append(message)
        
        conn.close()
        return messages
    
    def update_bot_system_prompts(self, conversation_id, bot1_system_prompt=None, bot2_system_prompt=None):
        """Update the system prompts for one or both bots in a conversation."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        update_fields = []
        params = []
        
        if bot1_system_prompt is not None:
            update_fields.append('bot1_system_prompt = ?')
            params.append(bot1_system_prompt)
        
        if bot2_system_prompt is not None:
            update_fields.append('bot2_system_prompt = ?')
            params.append(bot2_system_prompt)
        
        if update_fields:
            query = f'''
            UPDATE conversations 
            SET {', '.join(update_fields)} 
            WHERE id = ?
            '''
            params.append(conversation_id)
            
            cursor.execute(query, params)
            conn.commit()
        
        conn.close()
    
    def delete_conversation(self, conversation_id):
        """Delete a conversation and all its messages."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Start a transaction
            conn.execute('BEGIN TRANSACTION')
            
            # Delete all messages related to this conversation
            cursor.execute('DELETE FROM messages WHERE conversation_id = ?', (conversation_id,))
            
            # Delete the conversation
            cursor.execute('DELETE FROM conversations WHERE id = ?', (conversation_id,))
            
            # Commit the transaction
            conn.execute('COMMIT')
            success = True
        except Exception as e:
            # Roll back in case of error
            conn.execute('ROLLBACK')
            print(f"Error deleting conversation: {e}")
            success = False
        finally:
            conn.close()
        
        return success