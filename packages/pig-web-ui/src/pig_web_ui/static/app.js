// Chat application
class ChatApp {
    constructor() {
        this.chatContainer = document.getElementById('chatContainer');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.fileInput = document.getElementById('fileInput');
        
        this.isStreaming = false;
        this.uploadedFiles = [];
        
        this.init();
    }
    
    init() {
        // Event listeners
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.clearBtn.addEventListener('click', () => this.clearHistory());
        
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Auto-resize textarea
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = this.messageInput.scrollHeight + 'px';
        });
        
        // File upload
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        }
        
        // Paste handling for images
        this.messageInput.addEventListener('paste', (e) => this.handlePaste(e));
        
        // Load history
        this.loadHistory();
    }
    
    async handleFileSelect(event) {
        const files = event.target.files;
        if (!files || files.length === 0) return;
        
        for (const file of files) {
            await this.uploadFile(file);
        }
    }
    
    async handlePaste(event) {
        const items = event.clipboardData?.items;
        if (!items) return;
        
        for (const item of items) {
            if (item.type.indexOf('image') !== -1) {
                event.preventDefault();
                const file = item.getAsFile();
                if (file) {
                    await this.uploadFile(file);
                }
            }
        }
    }
    
    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData,
            });
            
            const data = await response.json();
            
            if (data.status === 'ok') {
                this.uploadedFiles.push({
                    filename: data.filename,
                    path: data.path,
                });
                this.showUploadSuccess(file.name);
            }
        } catch (error) {
            console.error('Upload failed:', error);
        }
    }
    
    showUploadSuccess(filename) {
        const notification = document.createElement('div');
        notification.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #4caf50; color: white; padding: 1rem; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);';
        notification.textContent = `✓ Uploaded: ${filename}`;
        document.body.appendChild(notification);
        
        setTimeout(() => notification.remove(), 3000);
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isStreaming) return;
        
        // Add user message
        this.addMessage('user', message);
        
        // Clear input
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';
        
        // Disable send button
        this.isStreaming = true;
        this.sendBtn.disabled = true;
        
        // Add assistant message placeholder
        const assistantMsg = this.addMessage('assistant', '', true);
        
        try {
            // Send request with SSE
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message }),
            });
            
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            
            // Read SSE stream
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop(); // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.type === 'token') {
                            this.appendToMessage(assistantMsg, data.content);
                        } else if (data.type === 'done') {
                            this.removeTypingIndicator(assistantMsg);
                        } else if (data.type === 'error') {
                            this.setMessageError(assistantMsg, data.error);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error:', error);
            this.setMessageError(assistantMsg, 'Failed to get response');
        } finally {
            this.isStreaming = false;
            this.sendBtn.disabled = false;
            this.messageInput.focus();
        }
    }
    
    addMessage(role, content, isStreaming = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? 'U' : 'A';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        if (isStreaming) {
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'typing-indicator';
            typingIndicator.innerHTML = '<span></span><span></span><span></span>';
            contentDiv.appendChild(typingIndicator);
        } else {
            contentDiv.textContent = content;
        }
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        this.chatContainer.appendChild(messageDiv);
        this.scrollToBottom();
        
        return messageDiv;
    }
    
    appendToMessage(messageDiv, text) {
        const contentDiv = messageDiv.querySelector('.message-content');
        
        // Remove typing indicator if present
        const typingIndicator = contentDiv.querySelector('.typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
        
        // Append text
        if (!contentDiv.dataset.content) {
            contentDiv.dataset.content = '';
        }
        contentDiv.dataset.content += text;
        
        // Render with markdown
        if (window.MarkdownRenderer) {
            contentDiv.innerHTML = MarkdownRenderer.render(contentDiv.dataset.content);
            
            // Highlight code blocks
            if (window.SyntaxHighlighter) {
                contentDiv.querySelectorAll('pre code').forEach(block => {
                    const lang = block.className.replace('language-', '');
                    block.innerHTML = SyntaxHighlighter.highlight(block.textContent, lang);
                });
            }
        } else {
            contentDiv.textContent += text;
        }
        
        this.scrollToBottom();
    }
    
    removeTypingIndicator(messageDiv) {
        const typingIndicator = messageDiv.querySelector('.typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }
    
    setMessageError(messageDiv, error) {
        const contentDiv = messageDiv.querySelector('.message-content');
        contentDiv.textContent = `Error: ${error}`;
        contentDiv.style.color = '#dc3545';
    }
    
    scrollToBottom() {
        this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
    }
    
    async clearHistory() {
        if (!confirm('Clear all messages?')) return;
        
        try {
            await fetch('/api/history', { method: 'DELETE' });
            this.chatContainer.innerHTML = '';
        } catch (error) {
            console.error('Error clearing history:', error);
        }
    }
    
    async loadHistory() {
        try {
            const response = await fetch('/api/history');
            const data = await response.json();
            
            for (const message of data.messages) {
                if (message.role !== 'system') {
                    this.addMessage(message.role, message.content);
                }
            }
        } catch (error) {
            console.error('Error loading history:', error);
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new ChatApp();
});
