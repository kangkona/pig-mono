// Simple syntax highlighting for code blocks

class SyntaxHighlighter {
    static highlight(code, language) {
        // Basic syntax highlighting
        // In production, use a library like Prism.js or highlight.js
        
        let highlighted = this.escapeHtml(code);
        
        if (language === 'python') {
            // Python keywords
            highlighted = highlighted.replace(
                /\b(def|class|import|from|return|if|else|elif|for|while|try|except|finally|with|as|pass|break|continue|True|False|None)\b/g,
                '<span style="color: #569cd6">$1</span>'
            );
            
            // Strings
            highlighted = highlighted.replace(
                /(["'])(?:(?=(\\?))\2.)*?\1/g,
                '<span style="color: #ce9178">$&</span>'
            );
            
            // Comments
            highlighted = highlighted.replace(
                /#.*/g,
                '<span style="color: #6a9955">$&</span>'
            );
        } else if (language === 'javascript' || language === 'js') {
            // JavaScript keywords
            highlighted = highlighted.replace(
                /\b(function|const|let|var|return|if|else|for|while|class|async|await|try|catch|finally)\b/g,
                '<span style="color: #569cd6">$1</span>'
            );
            
            // Strings
            highlighted = highlighted.replace(
                /(["'`])(?:(?=(\\?))\2.)*?\1/g,
                '<span style="color: #ce9178">$&</span>'
            );
            
            // Comments
            highlighted = highlighted.replace(
                /\/\/.*/g,
                '<span style="color: #6a9955">$&</span>'
            );
        }
        
        return highlighted;
    }
    
    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    static highlightAll() {
        // Highlight all code blocks on page
        document.querySelectorAll('pre code').forEach(block => {
            const language = block.className.replace('language-', '');
            const code = block.textContent;
            block.innerHTML = this.highlight(code, language);
        });
    }
}

// Export
window.SyntaxHighlighter = SyntaxHighlighter;

// Auto-highlight on load
document.addEventListener('DOMContentLoaded', () => {
    SyntaxHighlighter.highlightAll();
});
