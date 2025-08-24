import customtkinter as ctk
from tkinter import messagebox
import threading
import time
import ollama
import requests
import sqlite3
import datetime
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from PIL import Image
import urllib.request
from io import BytesIO
import uuid
import queue

# Thread-safe Hande AI class
class ThreadSafeHandeAI:
    def __init__(self):
        self.db_path = "hande_memory.db"
        self.current_conversation_id = None
        self.db_conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db_conn.execute("PRAGMA journal_mode=WAL")
        self.db_conn.execute("PRAGMA synchronous=OFF")
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.init_memory_system()
        
    def init_memory_system(self):
        """Initialize database"""
        cursor = self.db_conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY,
                conversation_id TEXT,
                user_message TEXT,
                ai_response TEXT,
                timestamp INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at INTEGER,
                last_updated INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_conv_id ON conversations(conversation_id)
        ''')
        
        self.db_conn.commit()
    
    def create_new_conversation(self):
        """Create new conversation"""
        self.current_conversation_id = str(uuid.uuid4())[:8]
        return self.current_conversation_id
    
    def save_conversation_async(self, user_msg, ai_response):
        """Save conversation in background"""
        if not self.current_conversation_id:
            self.current_conversation_id = str(uuid.uuid4())[:8]
        
        self.executor.submit(self._save_to_db, user_msg, ai_response)
    
    def _save_to_db(self, user_msg, ai_response):
        """Background database save"""
        try:
            cursor = self.db_conn.cursor()
            now = int(time.time())
            
            cursor.execute('''
                INSERT INTO conversations (conversation_id, user_message, ai_response, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (self.current_conversation_id, user_msg, ai_response, now))
            
            cursor.execute('''
                INSERT OR REPLACE INTO conversation_sessions 
                (id, title, created_at, last_updated)
                VALUES (?, ?, ?, ?)
            ''', (self.current_conversation_id, user_msg[:30], now, now))
            
            self.db_conn.commit()
        except Exception as e:
            print(f"DB Error: {e}")
    
    def get_conversations(self):
        """Get conversation list"""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute('''
                SELECT id, title, created_at FROM conversation_sessions 
                ORDER BY last_updated DESC LIMIT 20
            ''')
            return cursor.fetchall()
        except Exception:
            return []
    
    def search_web_fast(self, query):
        """Fast web search"""
        try:
            response = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json"},
                timeout=1,
                headers={"User-Agent": "HandeAI/1.0"}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("Abstract"):
                    return data["Abstract"][:150]
        except Exception:
            pass
        return ""
    
    def needs_web_search(self, query):
        """Check if web search needed"""
        indicators = ["today", "now", "current", "weather", "news", "president", "latest"]
        return any(word in query.lower() for word in indicators)
    
    def generate_response_safe(self, user_query, message_queue, stop_event):
        """Thread-safe response generation using queue communication"""
        try:
            # Put status update in queue
            message_queue.put(("status", "🟡 Thinking..."))
            
            # Check web search need
            web_info = ""
            if self.needs_web_search(user_query):
                message_queue.put(("status", "🟡 Searching web..."))
                web_info = self.search_web_fast(user_query)
            
            # Prepare system prompt
            current_time = datetime.datetime.now().strftime("%I:%M %p, %A")
            system_prompt = f"""You are Hande, INFERNO's AI assistant.

Current time: {current_time}
US President (2025): Donald Trump
{f"Current info: {web_info}" if web_info else ""}

Be helpful, intelligent, and use ❤️ occasionally."""

            # Update status
            message_queue.put(("status", "🟡 Generating response..."))
            
            # Try models in order of speed
            models = ["llama3.2", "llama3.2:1b", "llama3:8b", "gemma2:2b"]
            response = None
            
            for model in models:
                try:
                    response = ollama.chat(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_query}
                        ],
                        options={
                            "temperature": 0.7,
                            "num_ctx": 2048,
                            "num_predict": 300
                        }
                    )
                    break
                except Exception as e:
                    continue
            
            if not response:
                message_queue.put(("error", "❌ No Ollama models available"))
                return
            
            full_response = response["message"]["content"]
            
            # Stream response through queue
            message_queue.put(("start_stream", ""))
            
            for char in full_response:
                if stop_event.is_set():
                    break
                message_queue.put(("char", char))
                time.sleep(0.005)  # 5ms per character
            
            # Mark completion
            message_queue.put(("complete", full_response))
            
            # Save in background
            self.save_conversation_async(user_query, full_response)
            
        except Exception as e:
            error_msg = f"❤️ I encountered an error: {str(e)[:100]}"
            message_queue.put(("error", error_msg))

class ChatMessage(ctk.CTkFrame):
    def __init__(self, parent, message, is_user=False):
        super().__init__(parent, fg_color="transparent")
        
        if is_user:
            bg_color = "#0084FF"
            text_color = "white"
            anchor_side = "e"
            padx = (100, 20)
        else:
            bg_color = "#2F2F2F" 
            text_color = "#FFFFFF"
            anchor_side = "w"
            padx = (20, 100)
        
        # Message bubble
        bubble = ctk.CTkFrame(self, fg_color=bg_color, corner_radius=12)
        bubble.pack(anchor=anchor_side, padx=padx, pady=4)
        
        # Text label
        label = ctk.CTkLabel(
            bubble, text=message, font=ctk.CTkFont(size=13),
            text_color=text_color, wraplength=400, justify="left", anchor="w"
        )
        label.pack(padx=15, pady=10)

class SafeSidebar(ctk.CTkFrame):
    def __init__(self, parent, hande_ai, main_app):
        super().__init__(parent, width=250, fg_color="#1A1A1A")
        self.pack_propagate(False)
        
        self.hande_ai = hande_ai
        self.main_app = main_app
        
        # Header
        header = ctk.CTkLabel(self, text="💬 Chats", font=ctk.CTkFont(size=16, weight="bold"))
        header.pack(pady=15)
        
        # New chat
        new_btn = ctk.CTkButton(
            self, text="➕ New Chat", height=35,
            fg_color="#0084FF", command=self.new_chat
        )
        new_btn.pack(fill="x", padx=10, pady=5)
        
        # Conversations
        self.conv_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.conv_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Exit
        exit_btn = ctk.CTkButton(
            self, text="🚪 Exit", height=35,
            fg_color="#FF4444", command=self.exit_app
        )
        exit_btn.pack(fill="x", padx=10, pady=5)
        
        self.refresh_conversations()
    
    def new_chat(self):
        self.hande_ai.create_new_conversation()
        self.main_app.clear_chat()
        self.main_app.add_welcome()
    
    def refresh_conversations(self):
        # Clear existing
        for widget in self.conv_frame.winfo_children():
            widget.destroy()
        
        # Add conversations
        conversations = self.hande_ai.get_conversations()
        for conv_id, title, created_at in conversations[:10]:
            btn = ctk.CTkButton(
                self.conv_frame,
                text=f"💬 {title[:20]}{'...' if len(title) > 20 else ''}",
                height=30, fg_color="#2F2F2F", anchor="w",
                command=lambda cid=conv_id: self.load_conv(cid)
            )
            btn.pack(fill="x", pady=2)
    
    def load_conv(self, conv_id):
        self.hande_ai.current_conversation_id = conv_id
        self.main_app.clear_chat()
        self.main_app.add_message("💬 Previous conversation loaded", False)
    
    def exit_app(self):
        if messagebox.askyesno("Exit", "Exit Hande AI?"):
            self.main_app.quit()

class ThreadSafeHandeGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.title("🚀 Thread-Safe Hande AI by INFERNO")
        self.geometry("1000x700")
        ctk.set_appearance_mode("dark")
        self.configure(fg_color="#141414")
        
        # Initialize AI
        self.hande_ai = ThreadSafeHandeAI()
        self.message_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.response_thread = None
        self.current_streaming_frame = None
        self.current_streaming_label = None
        
        self.setup_ui()
        self.add_welcome()
        
        # Start queue processor
        self.process_message_queue()
    
    def setup_ui(self):
        # Main container
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True)
        
        # Sidebar
        self.sidebar = SafeSidebar(main, self.hande_ai, self)
        self.sidebar.pack(side="left", fill="y")
        
        # Chat area
        chat_area = ctk.CTkFrame(main, fg_color="#1E1E1E")
        chat_area.pack(side="right", fill="both", expand=True)
        
        # Header
        header = ctk.CTkFrame(chat_area, height=50, fg_color="#2A2A2A")
        header.pack(fill="x")
        header.pack_propagate(False)
        
        title = ctk.CTkLabel(header, text="🚀 Thread-Safe Hande AI",
                           font=ctk.CTkFont(size=16, weight="bold"))
        title.pack(side="left", padx=20, pady=15)
        
        self.status_label = ctk.CTkLabel(header, text="🟢 Ready",
                                       text_color="#00AA00")
        self.status_label.pack(side="right", padx=20, pady=15)
        
        # Chat container  
        self.chat_container = ctk.CTkScrollableFrame(chat_area, fg_color="#1E1E1E")
        self.chat_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Input area
        input_frame = ctk.CTkFrame(chat_area, height=70, fg_color="#2A2A2A")
        input_frame.pack(fill="x")
        input_frame.pack_propagate(False)
        
        input_container = ctk.CTkFrame(input_frame, fg_color="transparent")
        input_container.pack(fill="both", padx=15, pady=15)
        
        # Input field
        self.message_entry = ctk.CTkEntry(
            input_container,
            placeholder_text="Ask anything... (Enter to send)",
            font=ctk.CTkFont(size=14), height=40
        )
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.message_entry.bind("<Return>", lambda e: self.send_message())
        self.message_entry.bind("<KeyPress>", self.on_key_press)
        
        # Send button
        self.send_btn = ctk.CTkButton(
            input_container, text="Send", width=70, height=40,
            fg_color="#0084FF", command=self.send_message
        )
        self.send_btn.pack(side="right")
        
        # Stop button
        self.stop_btn = ctk.CTkButton(
            input_container, text="Stop", width=70, height=40,
            fg_color="#FF4444", command=self.stop_response
        )
        
        # Focus on input
        self.message_entry.focus()
    
    def on_key_press(self, event):
        """Handle key press events"""
        # If currently generating and user presses Escape, stop
        if event.keysym == "Escape" and self.response_thread and self.response_thread.is_alive():
            self.stop_response()
    
    def process_message_queue(self):
        """Process messages from background thread"""
        try:
            while not self.message_queue.empty():
                message_type, data = self.message_queue.get_nowait()
                
                if message_type == "status":
                    self.status_label.configure(text=data)
                
                elif message_type == "start_stream":
                    self.start_streaming_message()
                
                elif message_type == "char":
                    self.update_streaming_char(data)
                
                elif message_type == "complete":
                    self.complete_streaming_message()
                
                elif message_type == "error":
                    self.handle_error_message(data)
                    
        except queue.Empty:
            pass
        
        # Schedule next check
        self.after(10, self.process_message_queue)
    
    def add_welcome(self):
        welcome = """🚀 Thread-Safe Hande AI v5.0

❤️ Hello Master INFERNO! Now with thread-safe operations:

⚡ **Fixed Issues:**
• No more UI threading errors
• Stable streaming responses  
• Safe background operations
• Queue-based communication

💨 **Speed Features:**
• Fast model detection
• Optimized database ops
• Smart web searching
• Instant UI updates

Ready for safe, fast responses! What can I help you with?"""
        
        self.add_message(welcome, False)
    
    def add_message(self, message, is_user):
        """Thread-safe message addition"""
        msg_widget = ChatMessage(self.chat_container, message, is_user)
        msg_widget.pack(fill="x", pady=2)
        self.scroll_to_bottom()
    
    def scroll_to_bottom(self):
        """Scroll to bottom"""
        self.after_idle(lambda: self.chat_container._parent_canvas.yview_moveto(1.0))
    
    def start_streaming_message(self):
        """Start streaming message display"""
        self.current_streaming_frame = ctk.CTkFrame(self.chat_container, fg_color="transparent")
        self.current_streaming_frame.pack(fill="x", pady=2)
        
        bubble = ctk.CTkFrame(self.current_streaming_frame, fg_color="#2F2F2F", corner_radius=12)
        bubble.pack(anchor="w", padx=(20, 100), pady=4)
        
        self.current_streaming_label = ctk.CTkLabel(
            bubble, text="", font=ctk.CTkFont(size=13),
            text_color="#FFFFFF", wraplength=400, justify="left", anchor="w"
        )
        self.current_streaming_label.pack(padx=15, pady=10)
    
    def update_streaming_char(self, char):
        """Update streaming character - THREAD SAFE"""
        if self.current_streaming_label and self.current_streaming_label.winfo_exists():
            try:
                current_text = self.current_streaming_label.cget("text")
                self.current_streaming_label.configure(text=current_text + char)
                self.scroll_to_bottom()
            except Exception:
                pass  # Widget was destroyed, ignore
    
    def complete_streaming_message(self):
        """Complete streaming message"""
        self.restore_ui()
        self.current_streaming_label = None
        self.current_streaming_frame = None
    
    def handle_error_message(self, error_msg):
        """Handle error message"""
        if self.current_streaming_label and self.current_streaming_label.winfo_exists():
            self.current_streaming_label.configure(text=error_msg)
        else:
            self.add_message(error_msg, False)
        self.restore_ui()
    
    def send_message(self):
        """Send message - thread safe"""
        message = self.message_entry.get().strip()
        if not message:
            return
        
        # Don't send if already generating
        if self.response_thread and self.response_thread.is_alive():
            return
        
        self.add_message(message, True)
        self.message_entry.delete(0, "end")
        
        # Update UI
        self.send_btn.pack_forget()
        self.stop_btn.pack(side="right")
        
        # Clear message queue
        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
            except queue.Empty:
                break
        
        # Start response thread
        self.stop_event.clear()
        self.response_thread = threading.Thread(
            target=self.hande_ai.generate_response_safe,
            args=(message, self.message_queue, self.stop_event),
            daemon=True
        )
        self.response_thread.start()
    
    def stop_response(self):
        """Stop response generation"""
        if self.response_thread and self.response_thread.is_alive():
            self.stop_event.set()
        self.restore_ui()
    
    def restore_ui(self):
        """Restore UI to ready state"""
        self.stop_btn.pack_forget()
        self.send_btn.pack(side="right")
        self.status_label.configure(text="🟢 Ready")
    
    def clear_chat(self):
        """Clear chat display"""
        for widget in self.chat_container.winfo_children():
            widget.destroy()
        self.current_streaming_label = None
        self.current_streaming_frame = None

if __name__ == "__main__":
    app = ThreadSafeHandeGUI()
    app.mainloop()