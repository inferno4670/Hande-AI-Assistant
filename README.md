# Hande AI Assistant 🎯

A lightweight AI chat assistant built with **Python**, **CustomTkinter GUI**, and **LLaMA models (via Ollama)**.  

## ✨ Features
- Real-time streaming responses  
- Local LLaMA model integration (Ollama)  
- Conversation history with SQLite  
- Responsive GUI (stop button, copy-to-clipboard, sessions)  
- Thread-safe design for smooth UX  

## ⚡ Installation
Clone the repo:
```bash
git clone https://github.com/inferno4670/Hande-AI-Assistant.git
cd Hande-AI-Assistant
```

Install dependencies:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirement.txt
```

Ensure Ollama is installed and at least one model is available:
```bash
ollama pull llama3.2
```

Run the original GUI:
```bash
python main.py
```

Alternate GUI entrypoints:
- Hande_GUI.py: Original fast-mode GUI
- Hande.py: Thread-safe GUI variant
