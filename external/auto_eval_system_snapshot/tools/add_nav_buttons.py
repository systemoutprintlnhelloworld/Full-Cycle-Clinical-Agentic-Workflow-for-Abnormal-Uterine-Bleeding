import os
import re
from pathlib import Path

# CSS for the buttons
NAV_CSS = """
<style>
.nav-buttons {
    position: fixed;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 1000;
    display: flex;
    gap: 15px;
    pointer-events: none; /* Let clicks pass through container */
}
.nav-btn {
    pointer-events: auto; /* Re-enable clicks on buttons */
    background: rgba(255, 255, 255, 0.8);
    color: #333;
    border: 1px solid #ccc;
    padding: 8px 16px;
    border-radius: 4px;
    text-decoration: none;
    font-family: sans-serif;
    font-size: 14px;
    font-weight: bold;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    transition: all 0.2s;
    opacity: 0.7;
}
.nav-btn:hover {
    opacity: 1;
    background: #fff;
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    transform: translateY(-2px);
    color: #000;
}
/* Dark mode / Theme compatibility adjustments */
[data-theme="cyber"] .nav-btn, [data-theme="neo"] .nav-btn {
    border-width: 2px;
}
</style>
"""

def get_sort_key(filename):
    """
    Extracts the number ID from the filename for sorting.
    Expected format: ..._ID_trace.html or ..._wuhan_ID_trace.html
    """
    # Try finding the last number before _trace.html
    match = re.search(r'_(\d+)_trace\.html$', filename)
    if match:
        return int(match.group(1))
    
    # Fallback: look for any sequence of digits near end
    match = re.search(r'(\d+)', filename)
    if match:
        return int(match.group(1))
    
    return 0

def add_nav_buttons(root_dir):
    print(f"Scanning {root_dir}...")
    
    # Process each directory independently
    for dirpath, dirnames, filenames in os.walk(root_dir):
        html_files = [f for f in filenames if f.endswith('_trace.html')]
        
        if not html_files:
            continue
            
        # Sort files by ID
        # We assume files in the same directory belong to the same sequence
        sorted_files = sorted(html_files, key=get_sort_key)
        
        print(f"  Found {len(sorted_files)} trace files in {dirpath}")
        
        for i, filename in enumerate(sorted_files):
            # Calculate prev/next
            prev_file = sorted_files[i-1] if i > 0 else None
            next_file = sorted_files[i+1] if i < len(sorted_files)-1 else None
            
            file_path = os.path.join(dirpath, filename)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if already injected
            if 'class="nav-buttons"' in content:
                print(f"    Skipping {filename} (already has buttons)")
                # If we want to update links, we might need to overwrite, 
                # but user said 'add', assume run once or safe to skip if present.
                # Actually, to be safe against broken links from previous runs or reordering, 
                # we should probably replace the existing block or just skip for now.
                # Let's assume we skip to avoid duplication.
                continue
                
            # Construct Buttons HTML
            buttons_html = '<div class="nav-buttons">'
            
            if prev_file:
                buttons_html += f'<a href="./{prev_file}" class="nav-btn">← Prev</a>'
                
            if next_file:
                buttons_html += f'<a href="./{next_file}" class="nav-btn">Next →</a>'
                
            buttons_html += '</div>'
            
            # Inject CSS + Buttons
            # CSS before </head>, Buttons before </body>
            
            new_content = content
            
            # Inject CSS
            if '</head>' in new_content:
                new_content = new_content.replace('</head>', f'{NAV_CSS}</head>')
            else:
                # Fallback if no head tag (rare)
                new_content = NAV_CSS + new_content
                
            # Inject Buttons
            if '</body>' in new_content:
                new_content = new_content.replace('</body>', f'{buttons_html}</body>')
            else:
                new_content += buttons_html
                
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            print(f"    Updated {filename}")

if __name__ == "__main__":
    target_dir = os.path.join(os.getcwd(), "output")
    if not os.path.exists(target_dir):
        print(f"Directory {target_dir} not found.")
    else:
        add_nav_buttons(target_dir)
