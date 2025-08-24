import customtkinter as ctk
from tkinter import Canvas, Frame, messagebox
import tkinter as tk
import threading
import time
import ollama
import requests
import sqlite3
import datetime
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from PIL import Image
from pathlib import Path
import asyncio
import aiohttp
import queue
import urllib.request
from io import BytesIO

def load_icon_from_url(url, size=(18, 18)):
    """Fetch an image from a URL and convert it into a CTkImage."""
    try:
        with urllib.request.urlopen(url) as response:
            raw_data = response.read()
        pil_image = Image.open(BytesIO(raw_data)).convert("RGBA")
        pil_image = pil_image.resize(size, Image.Resampling.LANCZOS)
        return ctk.CTkImage(light_image=pil_image, size=size)
    except Exception as e:
        # Return a simple text fallback if icon loading fails
        return None

# Optimized Hande AI class with performance improvements
class HandeAI:
    def __init__(self):
        self.db_path = "hande_memory.db"
        self.current_conversation_id = None
        self.connection_pool = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection_pool.execute("PRAGMA journal_mode=WAL")  # Faster writes
        self.connection_pool.execute("PRAGMA synchronous=NORMAL")  # Faster commits
        self.executor = ThreadPoolExecutor(max_workers=2)  # For parallel operations
        self.init_memory_system()
        
    def init_memory_system(self):
        """Initialize enhanced memory database with optimizations"""
        cursor = self.connection_pool.cursor()
        
        # Create tables with optimized indexes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                title TEXT,
                timestamp TEXT,
                user_message TEXT,
                ai_response TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversation_id ON conversations(conversation_id)
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                last_updated TEXT,
                message_count INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_learning (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                learned_info TEXT,
                confidence REAL DEFAULT 1.0,
                timestamp TEXT
            )
        ''')
        
        self.connection_pool.commit()
    
    def create_new_conversation(self):
        """Create a new conversation session - optimized"""
        import uuid
        conv_id = str(uuid.uuid4())
        self.current_conversation_id = conv_id
        
        try:
            cursor = self.connection_pool.cursor()
            cursor.execute('''
                INSERT INTO conversation_sessions (id, title, created_at, last_updated)
                VALUES (?, ?, ?, ?)
            ''', (conv_id, "New Chat", datetime.datetime.now().isoformat(), datetime.datetime.now().isoformat()))
            self.connection_pool.commit()
        except Exception:
            pass
        
        return conv_id
    
    def get_conversations(self):
        """Get list of all conversations - cached and optimized"""
        try:
            cursor = self.connection_pool.cursor()
            cursor.execute('''
                SELECT id, title, created_at, message_count FROM conversation_sessions 
                ORDER BY last_updated DESC LIMIT 50
            ''')  # Limit to recent conversations for speed
            conversations = cursor.fetchall()
            return conversations
        except Exception:
            return []
    
    def load_conversation(self, conversation_id):
        """Load a specific conversation - optimized query"""
        self.current_conversation_id = conversation_id
        try:
            cursor = self.connection_pool.cursor()
            cursor.execute('''
                SELECT user_message, ai_response FROM conversations 
                WHERE conversation_id = ? ORDER BY id ASC
            ''', (conversation_id,))  # Use id instead of timestamp for faster sorting
            messages = cursor.fetchall()
            return messages
        except Exception:
            return []
    
    def save_conversation(self, user_msg, ai_response):
        """Save conversation to current session - optimized with batch operations"""
        if not self.current_conversation_id:
            self.create_new_conversation()
            
        try:
            cursor = self.connection_pool.cursor()
            
            # Single transaction for multiple operations
            cursor.execute('BEGIN TRANSACTION')
            
            # Save message
            cursor.execute('''
                INSERT INTO conversations (conversation_id, timestamp, user_message, ai_response)
                VALUES (?, ?, ?, ?)
            ''', (self.current_conversation_id, datetime.datetime.now().isoformat(), user_msg, ai_response))
            
            # Update session in same transaction
            cursor.execute('''
                UPDATE conversation_sessions 
                SET last_updated = ?, message_count = message_count + 1
                WHERE id = ?
            ''', (datetime.datetime.now().isoformat(), self.current_conversation_id))
            
            # Auto-generate title for first message
            cursor.execute('''
                SELECT message_count FROM conversation_sessions WHERE id = ?
            ''', (self.current_conversation_id,))
            result = cursor.fetchone()
            
            if result and result[0] == 1:
                title = user_msg[:30] + "..." if len(user_msg) > 30 else user_msg
                cursor.execute('''
                    UPDATE conversation_sessions SET title = ? WHERE id = ?
                ''', (title, self.current_conversation_id))
            
            cursor.execute('COMMIT')
            
        except Exception:
            cursor.execute('ROLLBACK')
    
    def get_conversation_context(self, limit=3):  # Reduced limit for speed
        """Get recent conversation for context - optimized"""
        if not self.current_conversation_id:
            return []
            
        try:
            cursor = self.connection_pool.cursor()
            cursor.execute('''
                SELECT user_message, ai_response FROM conversations 
                WHERE conversation_id = ?
                ORDER BY id DESC LIMIT ?
            ''', (self.current_conversation_id, limit))
            history = cursor.fetchall()
            return list(reversed(history))
        except Exception:
            return []
    
    def search_web_fast(self, query):
        """Ultra-fast web search with aggressive timeout"""
        try:
            url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_redirect": 1, "no_html": 1}
            headers = {"User-Agent": "Mozilla/5.0 (compatible; HandeAI/1.0)"}
            
            # Ultra-fast timeout - 1 second max
            response = requests.get(url, headers=headers, params=params, timeout=1)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                if data.get("Abstract"):
                    results.append(data["Abstract"][:200])  # Limit length
                
                # Only get 1 related topic for speed
                for topic in data.get("RelatedTopics", [])[:1]:
                    if topic.get("Text"):
                        results.append(topic["Text"][:200])
                
                return results
        except Exception:
            pass
        
        return []
    
    def needs_web_search(self, query):
        """Optimized search detection"""
        current_indicators = [
            "today", "now", "current", "latest", "recent", "2024", "2025",
            "weather", "news", "stock", "price", "president", "date", "time"
        ]  # Reduced list for faster checking
        
        query_lower = query.lower()
        return any(indicator in query_lower for indicator in current_indicators)
    
    def generate_response_streaming(self, user_query, callback, stop_event):
        """Generate AI response with optimized streaming"""
        
        # Parallel execution for context and web search
        context_future = self.executor.submit(self.get_conversation_context, 2)
        
        # Only search web if really needed and do it in parallel
        web_future = None
        if self.needs_web_search(user_query):
            web_future = self.executor.submit(self.search_web_fast, user_query)
        
        # Get current date/time once
        current_datetime = datetime.datetime.now()
        current_date_str = current_datetime.strftime("%A, %B %d, %Y")
        current_time_str = current_datetime.strftime("%I:%M %p")
        
        # Get context (wait max 0.5 seconds)
        try:
            conversation_history = context_future.result(timeout=0.5)
            context = ""
            if conversation_history:
                for user_msg, ai_msg in conversation_history[-1:]:  # Only last exchange
                    context += f"Previous: '{user_msg[:40]}' -> '{ai_msg[:40]}'\n"
        except TimeoutError:
            context = ""
        
        # Get web info (wait max 1 second)
        web_info = ""
        if web_future:
            try:
                search_results = web_future.result(timeout=1.0)
                if search_results:
                    web_info = f"Current: {search_results[0][:150]}"  # Shorter info
            except TimeoutError:
                pass
        
        # Optimized system prompt
        system_prompt = f"""You are Hande, INFERNO's advanced AI assistant.

CURRENT INFO:
- Date: {current_date_str}
- Time: {current_time_str}
- US President (2025): Donald Trump

{context}
{web_info}

Be intelligent, helpful, and efficient. Use ❤️ occasionally."""

        try:
            # Try fastest models first
            models_to_try = ["llama3.2", "llama3:8b"]  # Prioritize smaller, faster models
            
            response = None
            for model in models_to_try:
                try:
                    response = ollama.chat(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_query}
                        ]
                    )
                    break
                except Exception:
                    continue
                    
            if not response:
                raise Exception("No available models")
            
            full_response = response["message"]["content"]
            
            # Faster streaming - 3x speed
            for char in full_response:
                if stop_event.is_set():
                    break
                time.sleep(0.005)  # Much faster typing
                callback(char)
            
            # Save in background thread
            self.executor.submit(self.save_conversation, user_query, full_response)
            
        except Exception as e:
            fallback = f"❤️ Quick response mode active! What do you need help with?"
            for char in fallback:
                if stop_event.is_set():
                    break
                time.sleep(0.01)
                callback(char)

class ChatMessage(ctk.CTkFrame):
    def __init__(self, parent, message, is_user=False):
        super().__init__(parent, fg_color="transparent")

        self.message = message  # Save message text for copy

        if is_user:
            bg_color = "#777E85"
            text_color = "white"
            justify = "right"
            anchor_side = "e"
            padx = (80, 20)
        else:
            bg_color = "#2F2F2F"
            text_color = "#FFFFFF"
            justify = "left"
            anchor_side = "w"
            padx = (20, 80)

        # Bubble frame
        self.message_frame = ctk.CTkFrame(self, fg_color=bg_color, corner_radius=15)
        self.message_frame.pack(anchor=anchor_side, padx=padx, pady=(8,2))  # tighter pady

        # Text label
        self.message_label = ctk.CTkLabel(
            self.message_frame,
            text=message,
            font=ctk.CTkFont(size=13),
            text_color=text_color,
            wraplength=350,
            justify=justify,
            anchor="w"
        )
        self.message_label.pack(padx=12, pady=8)

        # Copy button (small, transparent)
        self.copy_btn = ctk.CTkButton(
            self,
            text="📋 Copy",
            width=60,
            height=20,
            font=ctk.CTkFont(size=10),
            fg_color="#404040",
            hover_color="#606060",
            command=self.copy_to_clipboard
        )
        self.copy_btn.pack(anchor=anchor_side, padx=padx, pady=(0,6))

    def copy_to_clipboard(self):
        """Copy message text to clipboard"""
        self.clipboard_clear()
        self.clipboard_append(self.message)
        self.update()  
        
class SidebarFrame(ctk.CTkFrame):
    def __init__(self, parent, hande_ai, main_app):
        super().__init__(parent, width=280, fg_color="#1A1A1A", corner_radius=0)
        self.pack_propagate(False)
        
        self.hande_ai = hande_ai
        self.main_app = main_app

        # Load icons with fallback
        pencil_url = "https://cdn-icons-png.flaticon.com/512/1159/1159633.png"
        trash_url = "https://cdn-icons-png.flaticon.com/512/1214/1214428.png"

        self.edit_icon = load_icon_from_url(pencil_url, size=(18, 18))
        self.delete_icon = load_icon_from_url(trash_url, size=(18, 18))

        # Header
        self.header = ctk.CTkFrame(self, height=70, fg_color="#2A2A2A")
        self.header.pack(fill="x", padx=8, pady=8)
        self.header.pack_propagate(False)

        self.title_label = ctk.CTkLabel(
            self.header,
            text="💬 Chats",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.pack(pady=15)
        
        # New chat button
        self.new_chat_btn = ctk.CTkButton(
            self,
            text="➕ New Chat",
            height=35,
            font=ctk.CTkFont(size=13, weight="bold"),
            hover_color="#5AD1FC",
            fg_color="#2D8FF0",
            command=self.new_chat
        )
        self.new_chat_btn.pack(fill="x", padx=12, pady=8)
        
        # Conversations list
        self.conversations_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.conversations_frame.pack(fill="both", expand=True, padx=8, pady=5)
        
        # Exit button
        self.exit_btn = ctk.CTkButton(
            self,
            text="🚪 Exit",
            height=35,
            fg_color="#FF4444",
            hover_color="#CC3333",
            command=self.exit_app
        )
        self.exit_btn.pack(fill="x", padx=12, pady=8)
        
        self.refresh_conversations()
    
    def delete_conversation(self, conversation_id):
        """Delete a chat and its messages"""
        if messagebox.askyesno("Delete Chat", "Are you sure you want to delete this chat?"):
            cursor = self.hande_ai.connection_pool.cursor()
            cursor.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
            cursor.execute("DELETE FROM conversation_sessions WHERE id = ?", (conversation_id,))
            self.hande_ai.connection_pool.commit()
            self.refresh_conversations()
    
    def new_chat(self):
        """Create new conversation - optimized"""
        self.hande_ai.create_new_conversation()
        self.main_app.clear_chat()
        self.main_app.add_welcome_message()
        # Async refresh to avoid blocking UI
        self.main_app.after(100, self.refresh_conversations)
    
    def refresh_conversations(self):
        """Fast refresh conversations list"""
        # Clear existing quickly
        for widget in self.conversations_frame.winfo_children():
            widget.destroy()
    
        # Get conversations
        conversations = self.hande_ai.get_conversations()
        
        for conv_id, title, created_at, msg_count in conversations[:20]:
            conv_frame = ctk.CTkFrame(self.conversations_frame, fg_color="#2F2F2F", corner_radius=8)
            conv_frame.pack(fill="x", pady=3, padx=4)
            
            # Title button (loads conversation)
            conv_btn = ctk.CTkButton(
                conv_frame,
                text=f"💬 {title[:25]}{'...' if len(title) > 25 else ''}",
                height=30,
                font=ctk.CTkFont(size=11),
                fg_color="transparent",
                hover_color="#404040",
                anchor="w",
                command=lambda cid=conv_id: self.load_conversation(cid)
            ) 
            conv_btn.pack(side="left", fill="x", expand=True, padx=5, pady=3)

            # Edit button with icon or text fallback
            if self.edit_icon:
                edit_btn = ctk.CTkButton(
                    conv_frame,
                    image=self.edit_icon,
                    text="",
                    width=30,
                    height=30,
                    fg_color="#404040",
                    hover_color="#606060",
                    command=lambda cid=conv_id: self.rename_conversation(cid)
                )
            else:
                edit_btn = ctk.CTkButton(
                    conv_frame,
                    text="✏️",
                    width=30,
                    height=30,
                    font=ctk.CTkFont(size=12),
                    fg_color="#404040",
                    hover_color="#606060",
                    command=lambda cid=conv_id: self.rename_conversation(cid)
                )
            edit_btn.pack(side="right", padx=2, pady=3)

            # Delete button with icon or text fallback
            if self.delete_icon:
                delete_btn = ctk.CTkButton(
                    conv_frame,
                    image=self.delete_icon,
                    text="",
                    width=30,
                    height=30,
                    fg_color="#993333",
                    hover_color="#CC3333",
                    command=lambda cid=conv_id: self.delete_conversation(cid)
                )
            else:
                delete_btn = ctk.CTkButton(
                    conv_frame,
                    text="🗑️",
                    width=30,
                    height=30,
                    font=ctk.CTkFont(size=12),
                    fg_color="#993333",
                    hover_color="#CC3333",
                    command=lambda cid=conv_id: self.delete_conversation(cid)
                )
            delete_btn.pack(side="right", padx=2, pady=3)

    def load_conversation(self, conversation_id):
        """Fast conversation loading"""
        self.main_app.clear_chat()
        # Load in background to keep UI responsive
        threading.Thread(target=self._load_conversation_bg, args=(conversation_id,), daemon=True).start()
    
    def _load_conversation_bg(self, conversation_id):
        """Background conversation loading"""
        messages = self.hande_ai.load_conversation(conversation_id)
        # Update UI in main thread
        self.main_app.after(0, lambda: self._display_loaded_messages(messages))
    
    def _display_loaded_messages(self, messages):
        """Display loaded messages in UI"""
        for user_msg, ai_msg in messages:
            self.main_app.add_message(user_msg, is_user=True)
            self.main_app.add_message(ai_msg, is_user=False)
    
    def exit_app(self):
        """Exit application"""
        if messagebox.askyesno("Exit", "Exit Hande AI?"):
            self.main_app.destroy()
            
    def rename_conversation(self, conversation_id):
        """Rename conversation - optimized"""
        new_name = ctk.CTkInputDialog(
           text="Enter new chat name:",
           title="Rename Chat"
        ).get_input()

        if new_name:
            cursor = self.hande_ai.connection_pool.cursor()
            cursor.execute(
                "UPDATE conversation_sessions SET title = ? WHERE id = ?",
                (new_name, conversation_id)
            ) 
            self.hande_ai.connection_pool.commit()
            self.refresh_conversations()

class HandeGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Optimized window setup
        self.title("Hande AI - Fast Mode by INFERNO")
        self.geometry("1100x750")
        self.minsize(900, 600)
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color="#141414")
        
        # Initialize optimized Hande AI
        self.hande_ai = HandeAI()
        
        self.setup_ui()
        self.stop_event = threading.Event()
        self.response_thread = None
        self.current_response_label = None
        self.sidebar_visible = True
        
        # Fast startup
        self.hande_ai.create_new_conversation()
        self.add_welcome_message()
        
    def setup_ui(self):
        # Streamlined main container
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)
        
        # Optimized sidebar
        self.sidebar = SidebarFrame(self.main_container, self.hande_ai, self)
        self.sidebar.pack(side="left", fill="y")
        
        # Main chat area
        self.chat_area = ctk.CTkFrame(self.main_container, fg_color="#1E1E1E")
        self.chat_area.pack(side="right", fill="both", expand=True)
        
        # Simplified header
        self.header_frame = ctk.CTkFrame(self.chat_area, height=65, fg_color="#2A2A2A")
        self.header_frame.pack(fill="x")
        self.header_frame.pack_propagate(False)
        
        self.header_content = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.header_content.pack(fill="both", padx=15, pady=12)
        
        self.menu_btn = ctk.CTkButton(
            self.header_content,
            text="☰",
            width=35,
            height=35,
            font=ctk.CTkFont(size=16),
            fg_color="#404040",
            command=self.toggle_sidebar
        )
        self.menu_btn.pack(side="left", padx=(0, 12))
        
        self.header_label = ctk.CTkLabel(
            self.header_content,
            text="🚀 Hande AI - Fast Mode",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.header_label.pack(side="left")
        
        self.status_label = ctk.CTkLabel(
            self.header_content,
            text="🟢 Ready • Fast Mode",
            font=ctk.CTkFont(size=11),
            text_color="#00AA00"
        )
        self.status_label.pack(side="right")
        
        # Optimized chat container
        self.chat_container = ctk.CTkScrollableFrame(
            self.chat_area,
            fg_color="#1E1E1E"
        )
        self.chat_container.pack(fill="both", expand=True)
        
        # Streamlined input section
        self.input_section = ctk.CTkFrame(self.chat_area, height=80, fg_color="#2A2A2A")
        self.input_section.pack(fill="x")
        self.input_section.pack_propagate(False)
        
        self.input_container = ctk.CTkFrame(self.input_section, fg_color="transparent")
        self.input_container.pack(fill="both", padx=20, pady=20)
        
        # Fast input field
        self.message_entry = ctk.CTkEntry(
            self.input_container,
            placeholder_text="Ask anything... (Enter to send)",
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="#404040",
            border_color="#606060"
        )
        self.message_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.message_entry.bind("<Return>", lambda e: self.send_message())
        
        # Simplified buttons
        self.send_button = ctk.CTkButton(
            self.input_container,
            text="Send ➤",
            width=80,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0084FF",
            command=self.send_message
        )
        self.send_button.pack(side="right")
        
        self.stop_button = ctk.CTkButton(
            self.input_container,
            text="Stop ⭕",
            width=80,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#FF4444",
            command=self.stop_response
        )
    
    def toggle_sidebar(self):
        """Fast sidebar toggle"""
        if self.sidebar_visible:
            self.sidebar.pack_forget()
            self.menu_btn.configure(text="☰")
        else:
            self.sidebar.pack(side="left", fill="y", before=self.chat_area)
            self.menu_btn.configure(text="✕")
        self.sidebar_visible = not self.sidebar_visible
    
    def add_welcome_message(self):
        """Fast welcome message"""
        welcome_msg = """🚀 Hande AI v3.0 - FAST MODE ACTIVATED

❤️ Hello Master INFERNO! Ultra-fast AI assistant ready:

⚡ **Speed Optimizations:**
• 3x faster response streaming
• Optimized database operations  
• Parallel web search & context loading
• Reduced UI rendering overhead

💨 **Performance Features:**
• 1-second web search timeout
• Background conversation saving
• Streamlined memory system
• Faster model prioritization

Ready for lightning-fast assistance! What can I help you with?"""
        
        self.add_message(welcome_msg, is_user=False)
    
    def add_message(self, message, is_user=False):
        """Fast message addition"""
        message_widget = ChatMessage(self.chat_container, message, is_user)
        message_widget.pack(fill="x", pady=4)
        self.after(10, self.scroll_to_bottom)  # Faster scroll
        return message_widget
        
    def scroll_to_bottom(self):
        """Fast scroll to bottom"""
        self.chat_container._parent_canvas.yview_moveto(1.0)
        
    def add_streaming_message(self):
        """Fast streaming message setup"""
        self.current_response_frame = ctk.CTkFrame(self.chat_container, fg_color="transparent")
        self.current_response_frame.pack(fill="x", pady=4)
        
        message_bubble = ctk.CTkFrame(self.current_response_frame, fg_color="#2F2F2F", corner_radius=15)
        message_bubble.pack(anchor="w", padx=(20, 80), pady=8, fill="x")
        
        self.current_response_label = ctk.CTkLabel(
            message_bubble,
            text="",
            font=ctk.CTkFont(size=13),
            text_color="#FFFFFF",
            wraplength=450,
            justify="left",
            anchor="nw"
        )
        self.current_response_label.pack(padx=18, pady=12, anchor="w")
        
        return self.current_response_label
        
    def update_streaming_message(self, char):
        """Fast streaming update"""
        if self.current_response_label:
            current_text = self.current_response_label.cget("text")
            self.current_response_label.configure(text=current_text + char)
            self.scroll_to_bottom()
            
    def send_message(self):
        """Fast message sending"""
        message = self.message_entry.get().strip()
        if not message:
            return
            
        self.add_message(message, is_user=True)
        self.message_entry.delete(0, "end")
        
        # Fast UI updates
        self.send_button.pack_forget()
        self.stop_button.pack(side="right")
        self.status_label.configure(text="🟡 Processing... • Fast Mode")
        
        self.add_streaming_message()
        
        self.stop_event.clear()
        self.response_thread = threading.Thread(
            target=self.hande_ai.generate_response_streaming,
            args=(message, self.update_streaming_message, self.stop_event),
            daemon=True
        )
        self.response_thread.start()
        
        self.monitor_response_thread()
        
    def monitor_response_thread(self):
        """Fast response monitoring"""
        if self.response_thread and self.response_thread.is_alive():
            self.after(50, self.monitor_response_thread)  # Faster checking
        else:
            self.restore_input_ui()
            # Background sidebar refresh
            self.after(100, self.sidebar.refresh_conversations)
            
    def restore_input_ui(self):
        """Fast UI restoration"""
        self.stop_button.pack_forget()
        self.send_button.pack(side="right")
        self.status_label.configure(text="🟢 Ready • Fast Mode")
        self.current_response_label = None
        
    def stop_response(self):
        """Fast response stopping"""
        if self.response_thread and self.response_thread.is_alive():
            self.stop_event.set()
            self.restore_input_ui()
    
    def clear_chat(self):
        """Fast chat clearing"""
        for widget in self.chat_container.winfo_children():
            widget.destroy()

if __name__ == "__main__":
    app = HandeGUI()
    app.mainloop()