# Labudy

A Python library for Research Lab Buddy.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [ArXiv Search](#arxiv-search)
  - [PDF to Markdown Conversion](#pdf-to-markdown-conversion)
  - [Research Paper Summarization](#research-paper-summarization)
- [Example](#example)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

## Overview

Labudy is a Python library designed to assist researchers by providing tools for searching research papers, converting PDFs to Markdown, and summarizing research content using advanced language models. It integrates with various APIs to enhance productivity in academic and research settings.

## Features

- **ArXiv Search**: Easily search for research papers on [arXiv](https://arxiv.org/) using customizable queries.
- **PDF to Markdown Conversion**: Convert PDF documents to Markdown format for easier editing and sharing.
- **Research Paper Summarization**: Generate concise summaries of research papers using state-of-the-art language models.
- **Batch Processing with Multiple LLMs**: Utilize multiple language models (OpenAI, Anthropic, Gemini) for robust and flexible processing.

## Installation

Ensure you have Python 3.8 or higher installed. You can install Labudy using `pip`:

```bash
pip install -e .
# pip install labudy
export $(grep -v '^#' .env | xargs) # Load environment variables
```

## Usage

### ArXiv Search

Use Labudy to search for research papers on arXiv. Here's how you can perform a search:

```python
from labudy.arxiv.search import search_arxiv

query = "machine learning"
results = search_arxiv(query, max_results=5)
for paper in results:
    print(f"{paper['title']} - {paper['url']}")
```

### PDF to Markdown Conversion

Convert your PDF documents to Markdown format with ease:

```python
from labudy.conversion.pdf_to_markdown import convert_pdf_to_markdown

pdf_path = "path/to/document.pdf"
markdown = convert_pdf_to_markdown(pdf_path)
print(markdown)
```

### Research Paper Summarization

Generate concise summaries of research papers:

```python
from labudy.research_summary.summarize import summarize_research_paper

paper_text = "Your research paper text here..."
summary = summarize_research_paper(paper_text)
print(summary)
```

## Example

Here's an example demonstrating how to use Labudy:

```python
from labudy.arxiv.search import search_arxiv
from labudy.conversion.pdf_to_markdown import convert_pdf_to_markdown
from labudy.research_summary.summarize import summarize_research_paper

if __name__ == "__main__":
    # ArXiv Search Example
    search_query = "deep learning"
    arxiv_results = search_arxiv(search_query, max_results=3)
    print("ArXiv Search Results:")
    for result in arxiv_results:
        print(f"- {result['title']} ({result['url']})")

    # PDF to Markdown Conversion Example
    pdf_file_path = "dummy.pdf"
    markdown_text = convert_pdf_to_markdown(pdf_file_path)
    print("\nPDF to Markdown Conversion Result:")
    print(markdown_text)

    # Research Paper Summarization Example
    paper_text = "This is an example research paper text describing the use of large language models in natural language processing..."
    summary_text = summarize_research_paper(paper_text)
    print("\nResearch Paper Summary:")
    print(summary_text)
```

## Contributing

Contributions are welcome! Please read the [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact

For any inquiries or support, please contact [keno.lasalle.kagoshima@gmail.com](mailto:keno.lasalle.kagoshima@gmail.com).