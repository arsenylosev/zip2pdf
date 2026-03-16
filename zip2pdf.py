#!/usr/bin/env python3
"""
zip2pdf - Convert ZIP archives with code to syntax-highlighted PDFs.
Usage: uv run archive.zip output.pdf
"""

import argparse
import io
import os
import sys
import zipfile
from pathlib import Path
from typing import List, Tuple, Optional

from pygments import highlight
from pygments.lexers import get_lexer_for_filename, guess_lexer, TextLexer
from pygments.formatters import ImageFormatter
from pygments.styles import get_style_by_name
from fpdf import FPDF, XPos, YPos


# Files/directories to always exclude
EXCLUDE_PATTERNS = [
    '.git', '__pycache__', '.venv', 'venv', 'node_modules',
    '.pytest_cache', '.mypy_cache', '.tox', '.egg-info',
    '*.pyc', '*.pyo', '*.so', '*.dylib', '*.dll',
    '*.jpg', '*.jpeg', '*.png', '*.gif', '*.svg', '*.ico',
    '*.mp3', '*.mp4', '*.wav', '*.avi', '*.mov',
    '*.zip', '*.tar', '*.gz', '*.bz2', '*.xz', '*.rar', '*.7z',
    '*.pdf', '*.doc', '*.docx', '*.xls', '*.xlsx',
    '.DS_Store', 'Thumbs.db', '.idea', '.vscode'
]

# Binary extensions to skip
BINARY_EXTENSIONS = {
    '.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe', '.bin',
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico', '.bmp', '.webp',
    '.mp3', '.mp4', '.wav', '.avi', '.mov', '.mkv', '.webm',
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.rar', '.7z', '.jar', '.war',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.db', '.sqlite', '.sqlite3',
    '.lockb',  # uv lock binary
}

MAX_PDF_SIZE_MB = 5
SAFETY_MARGIN = 0.9  # Target 90% of max to leave room for PDF overhead


class CodePDF(FPDF):
    """PDF generator with code formatting."""
    
    def __init__(self):
        super().__init__(unit='pt', format='A4')
        self.set_auto_page_break(auto=True, margin=50)
        self.set_margins(50, 50, 50)
        
    def header(self):
        """Add page header."""
        if self.page_no() > 1:
            self.set_font('Helvetica', '', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 20, f"Page {self.page_no()}", align='R',
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(5)
    
    def add_file_header(self, filepath: str, file_size: int):
        """Add a file section header."""
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(50, 100, 150)
        safe_path = filepath.encode('latin-1', 'replace').decode('latin-1')
        self.cell(0, 20, f"[FILE] {safe_path} ({format_size(file_size)})",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(200, 200, 200)
        self.line(50, self.get_y(), 545, self.get_y())
        self.ln(5)
        
    def add_code_block(self, code: str, lexer_name: str = 'text'):
        """Add syntax-highlighted code using monospace font."""
        # Use built-in Courier for monospace
        self.set_font('Courier', '', 7)
        self.set_text_color(40, 40, 40)
        
        # Calculate available width
        page_width = 595  # A4 width in points
        margin = 50
        avail_width = page_width - 2 * margin
        
        # Split code into lines
        lines = code.split('\n')
        line_height = 10
        
        # Add subtle background for code
        start_y = self.get_y()
        total_height = len(lines) * line_height + 20
        
        self.set_fill_color(250, 250, 250)
        self.rect(margin - 5, start_y, avail_width + 10, total_height, style='F')
        
        self.set_xy(margin, start_y + 10)
        
        for i, line in enumerate(lines, 1):
            # Check for page break
            if self.get_y() > 750:
                self.add_page()
                self.set_xy(margin, 50)
                self.set_fill_color(250, 250, 250)
                self.rect(margin - 5, self.get_y() - 5, avail_width + 10, 
                         len(lines[i-1:]) * line_height + 15, style='F')
            
            # Line number
            self.set_text_color(150, 150, 150)
            self.cell(25, line_height, f"{i:4d}", align='R')
            
            # Code content
            self.set_text_color(40, 40, 40)
            # Truncate line if too long
            display_line = line
            if len(display_line) > 120:
                display_line = display_line[:117] + '...'
            
            # Replace tabs with spaces and encode for latin-1
            display_line = display_line.replace('\t', '    ')
            display_line = display_line.encode('latin-1', 'replace').decode('latin-1')
            self.cell(0, line_height, display_line)
            self.ln(line_height)
        
        self.ln(15)


def format_size(size_bytes: int) -> str:
    """Format byte size to human readable."""
    for unit in ['B', 'KB', 'MB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} GB"


def should_include_file(filepath: str) -> bool:
    """Check if file should be included in PDF."""
    path_lower = filepath.lower()
    
    # Check excluded patterns
    for pattern in EXCLUDE_PATTERNS:
        if pattern in path_lower:
            return False
    
    # Check binary extension
    ext = Path(filepath).suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return False
    
    return True


def get_lexer(filepath: str, content: str):
    """Get appropriate Pygments lexer for file."""
    try:
        return get_lexer_for_filename(filepath)
    except Exception:
        try:
            return guess_lexer(content[:1000])
        except Exception:
            return TextLexer()


def collect_files(zip_path: str) -> List[Tuple[str, int, bytes]]:
    """Collect all valid files from ZIP with their sizes."""
    files = []
    
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            
            filepath = info.filename
            if not should_include_file(filepath):
                continue
            
            try:
                content = zf.read(filepath)
                # Skip likely binary files by checking for null bytes
                if b'\x00' in content[:1024]:
                    continue
                files.append((filepath, info.file_size, content))
            except Exception:
                continue
    
    return files


def select_files_for_size(files: List[Tuple[str, int, bytes]], 
                          max_bytes: int) -> List[Tuple[str, int, bytes]]:
    """Select files to fit within size budget, prioritizing smaller files."""
    # Sort by size (smallest first to include as many as possible)
    sorted_files = sorted(files, key=lambda x: x[1])
    
    selected = []
    total_size = 0
    
    for filepath, size, content in sorted_files:
        if total_size + size > max_bytes:
            # Skip this file, try next smaller ones
            continue
        selected.append((filepath, size, content))
        total_size += size
    
    return selected


def create_pdf(zip_path: str, output_path: str) -> Tuple[bool, str]:
    """Create PDF from ZIP archive."""
    
    # Collect all files
    print(f"📦 Scanning {zip_path}...")
    all_files = collect_files(zip_path)
    print(f"   Found {len(all_files)} text/code files")
    
    if not all_files:
        return False, "No valid text/code files found in archive"
    
    # Calculate size budget (raw text will expand in PDF)
    # PDF typically 2-4x the text size due to formatting
    total_raw_size = sum(f[1] for f in all_files)
    print(f"   Total raw size: {format_size(total_raw_size)}")
    
    # Target size for raw content (accounting for PDF overhead)
    target_raw_size = int(MAX_PDF_SIZE_MB * 1024 * 1024 * SAFETY_MARGIN / 3)
    
    if total_raw_size > target_raw_size:
        print(f"   Size limit: including ~{format_size(target_raw_size)} of content")
        files_to_include = select_files_for_size(all_files, target_raw_size)
        excluded_count = len(all_files) - len(files_to_include)
        print(f"   Excluded {excluded_count} larger files to meet size limit")
    else:
        files_to_include = all_files
    
    # Sort files by path for consistent ordering
    files_to_include.sort(key=lambda x: x[0])
    
    # Generate PDF
    print(f"\n📝 Generating PDF with {len(files_to_include)} files...")
    pdf = CodePDF()
    pdf.add_page()
    
    # Title page
    pdf.set_font('Helvetica', 'B', 24)
    pdf.set_text_color(50, 100, 150)
    pdf.ln(200)
    pdf.cell(0, 40, "Code Archive", align='C',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    pdf.set_font('Helvetica', '', 12)
    pdf.set_text_color(80, 80, 80)
    safe_name = os.path.basename(zip_path).encode('latin-1', 'replace').decode('latin-1')
    pdf.cell(0, 20, f"Source: {safe_name}", align='C',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 20, f"Files: {len(files_to_include)}", align='C',
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 20, f"Total size: {format_size(sum(f[1] for f in files_to_include))}", 
             align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    if len(files_to_include) < len(all_files):
        pdf.set_text_color(200, 100, 100)
        pdf.cell(0, 20, f"({len(all_files) - len(files_to_include)} files excluded for size)", 
                 align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    # Table of contents
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_text_color(50, 100, 150)
    pdf.cell(0, 30, "Files Included",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)
    
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(60, 60, 60)
    for filepath, size, _ in files_to_include:
        display_path = filepath[:70] + '...' if len(filepath) > 70 else filepath
        safe_path = display_path.encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(0, 12, f"- {safe_path} ({format_size(size)})",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    # File contents
    for filepath, size, content in files_to_include:
        pdf.add_page()
        pdf.add_file_header(filepath, size)
        
        try:
            text = content.decode('utf-8', errors='replace')
        except Exception:
            text = content.decode('latin-1', errors='replace')
        
        # Limit extremely long files
        max_lines = 500
        lines = text.split('\n')
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append(f"\n... [{len(text.split(chr(10))) - max_lines} more lines truncated]")
            text = '\n'.join(lines)
        
        pdf.add_code_block(text)
    
    # Save PDF
    pdf.output(output_path)
    
    # Check final size
    final_size = os.path.getsize(output_path)
    final_size_mb = final_size / (1024 * 1024)
    
    print(f"\n✅ PDF created: {output_path}")
    print(f"   Size: {format_size(final_size)} ({final_size_mb:.2f} MB)")
    
    if final_size_mb > MAX_PDF_SIZE_MB:
        return False, f"PDF exceeds {MAX_PDF_SIZE_MB}MB limit ({final_size_mb:.2f} MB)"
    
    return True, f"Success - {len(files_to_include)} files included"


def main():
    parser = argparse.ArgumentParser(
        description='Convert ZIP archive with code to syntax-highlighted PDF'
    )
    parser.add_argument('archive', help='Path to ZIP archive')
    parser.add_argument('output', help='Output PDF path')
    parser.add_argument('--max-size', type=int, default=MAX_PDF_SIZE_MB,
                        help=f'Maximum PDF size in MB (default: {MAX_PDF_SIZE_MB})')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.archive):
        print(f"Error: Archive not found: {args.archive}", file=sys.stderr)
        sys.exit(1)
    
    if not zipfile.is_zipfile(args.archive):
        print(f"Error: Not a valid ZIP file: {args.archive}", file=sys.stderr)
        sys.exit(1)
    
    success, message = create_pdf(args.archive, args.output)
    
    if not success:
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)
    
    print(f"\n🎉 {message}")


if __name__ == '__main__':
    main()
