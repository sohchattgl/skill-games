import streamlit as st

def inject_copy_protection():
    """
    Inject CSS and minimal JavaScript for copy protection only.
    This prevents text selection, copying, and right-click context menu.
    """
    
    protection_html = """
    <style>
    /* Anti-Copy Protection CSS */
    
    /* Disable text selection globally */
    * {
        -webkit-user-select: none;
        -moz-user-select: none;
        -ms-user-select: none;
        user-select: none;
        -webkit-touch-callout: none;
        -webkit-tap-highlight-color: transparent;
    }
    
    /* Allow selection in form inputs (essential for quiz functionality) */
    input, textarea, select, option {
        -webkit-user-select: text !important;
        -moz-user-select: text !important;
        -ms-user-select: text !important;
        user-select: text !important;
    }
    
    /* Allow selection in Streamlit interactive elements */
    .stRadio label, .stCheckbox label, .stSelectbox label {
        -webkit-user-select: none !important;
        -moz-user-select: none !important;
        -ms-user-select: none !important;
        user-select: none !important;
    }
    
    /* Disable drag and drop for images and other elements */
    img, svg, .stImage {
        -webkit-user-drag: none;
        -khtml-user-drag: none;
        -moz-user-drag: none;
        -o-user-drag: none;
        user-drag: none;
        pointer-events: none;
    }
    
    /* Ensure buttons and interactive elements still work */
    button, .stButton button, .stDownloadButton button {
        -webkit-user-select: none !important;
        -moz-user-select: none !important;
        user-select: none !important;
        pointer-events: auto !important;
    }
    
    /* Visual indicator for protected content */
    .protected-content::before {
        content: "🛡️ Protected";
        position: fixed;
        top: 10px;
        right: 10px;
        background: rgba(255, 0, 0, 0.1);
        color: #666;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        z-index: 1000;
        pointer-events: none;
        opacity: 0.5;
    }
    
    /* Custom scrollbars */
    ::-webkit-scrollbar {
        width: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: transparent;
    }
    
    ::-webkit-scrollbar-thumb {
        background: rgba(0,0,0,0.3);
        border-radius: 4px;
    }
    
    </style>
    
    <script>
    // Minimal JavaScript for copy protection
    (function() {
        'use strict';
        
        console.log('🛡️ Copy protection active');
        
        // Block text selection
        document.addEventListener('selectstart', function(e) {
            const allowedElements = ['INPUT', 'TEXTAREA'];
            if (!allowedElements.includes(e.target.tagName)) {
                e.preventDefault();
                return false;
            }
        });
        
        // Block copying
        document.addEventListener('copy', function(e) {
            e.preventDefault();
            return false;
        });
        
        // Block cutting
        document.addEventListener('cut', function(e) {
            e.preventDefault();
            return false;
        });
        
        // Block pasting in non-input areas
        document.addEventListener('paste', function(e) {
            const allowedElements = ['INPUT', 'TEXTAREA'];
            if (!allowedElements.includes(e.target.tagName)) {
                e.preventDefault();
                return false;
            }
        });
        
        // Block right-click context menu
        document.addEventListener('contextmenu', function(e) {
            const allowedElements = ['INPUT', 'TEXTAREA'];
            if (!allowedElements.includes(e.target.tagName)) {
                e.preventDefault();
                return false;
            }
        });
        
        // Block common keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            // Block Ctrl+A, Ctrl+C, Ctrl+V, Ctrl+X, Ctrl+S, F12, etc.
            if (
                (e.ctrlKey && ['a', 'c', 'v', 'x', 's', 'p', 'u'].includes(e.key.toLowerCase())) ||
                e.key === 'F12' ||
                (e.ctrlKey && e.shiftKey && ['i', 'j'].includes(e.key.toLowerCase()))
            ) {
                e.preventDefault();
                return false;
            }
        });
        
    })();
    </script>
    """
    
    # Inject the protection
    st.markdown(protection_html, unsafe_allow_html=True)
    
    # Add wrapper div for protected content
    st.markdown('<div class="protected-content">', unsafe_allow_html=True)

def cleanup_protection():
    """Close the protection wrapper"""
    st.markdown('</div>', unsafe_allow_html=True)

def apply_copy_protection():
    """
    Main function to apply copy protection to a Streamlit page.
    Call this at the beginning of any page you want to protect.
    Returns a cleanup function.
    """
    inject_copy_protection()
    return cleanup_protection