# zip2pdf

Convert ZIP archives containing code to syntax-highlighted PDFs with intelligent file filtering and size management.

## Features

- **Universal Code Support**: Handles Python, JavaScript, HTML, CSS, YAML, Markdown, and 100+ languages via Pygments
- **Smart Size Management**: Automatically excludes files to keep PDFs under 5MB (configurable)
- **Clean Formatting**: Line numbers, syntax highlighting, file headers with sizes
- **Binary Filtering**: Automatically skips images, executables, and other non-text files
- **UV-Native**: Zero-installation workflow with `uv run`

## Installation

### Prerequisites

- [uv](https://docs.astral.sh/uv/) - Python package manager

### Quick Start

```bash
# Clone the repository
git clone https://github.com/boreal-voyager/zip2pdf.git
cd zip2pdf

# Run directly (no install needed)
uv run zip2pdf.py archive.zip output.pdf
```

Or install as a tool:

```bash
uv tool install .
zip2pdf archive.zip output.pdf
```

## Usage

### Basic Usage

```bash
uv run zip2pdf.py my-project.zip code.pdf
```

### With Custom Size Limit

```bash
uv run zip2pdf.py archive.zip output.pdf --max-size 10
```

### Command Reference

```
zip2pdf [OPTIONS] ARCHIVE OUTPUT

Arguments:
  ARCHIVE     Path to ZIP archive
  OUTPUT      Output PDF path

Options:
  --max-size MB    Maximum PDF size in MB (default: 5)
```

## How It Works

1. **Scan**: Extracts all text/code files from the ZIP (filters binaries)
2. **Size Check**: Calculates raw text size and estimates PDF overhead
3. **Smart Selection**: If needed, excludes largest files first to meet size limit
4. **Generate**: Creates PDF with:
   - Cover page with archive info
   - Table of contents listing all files
   - Each file with syntax highlighting and line numbers

## File Filtering

### Automatically Excluded

- Binary files: images, executables, archives
- Directories: `.git`, `__pycache__`, `node_modules`, `.venv`
- Cache: `.pytest_cache`, `.mypy_cache`
- OS files: `.DS_Store`, `Thumbs.db`
- IDE: `.idea`, `.vscode`

### Supported Languages

Any language supported by [Pygments](https://pygments.org/languages/):
- Python, JavaScript/TypeScript, HTML, CSS, SCSS
- Go, Rust, C/C++, Java, C#, Swift
- YAML, JSON, TOML, XML
- Markdown, reStructuredText
- Shell scripts, SQL, and 100+ more

## Size Management

When archives exceed the size limit:

1. Files are sorted by size (smallest first)
2. Included until raw text hits ~1.5MB (safety margin for PDF overhead)
3. Excluded files are noted on the cover page

This approach prioritizes including more smaller files (often the most important code) over fewer large files (often generated lockfiles or data).

## Example Output

```
📦 Scanning archive.zip...
   Found 146 text/code files
   Total raw size: 1.4 MB

📝 Generating PDF with 146 files...

✅ PDF created: output.pdf
   Size: 886.2 KB (0.87 MB)

🎉 Success - 146 files included
```

## Development

```bash
# Setup environment
uv sync

# Run tests
uv run pytest

# Format code
uv run ruff format .
```

## License

MIT License - see [LICENSE](LICENSE)

## Contributing

Pull requests welcome! Please ensure:
- Code follows `ruff` formatting
- Tests pass (`uv run pytest`)
- README updated for new features
