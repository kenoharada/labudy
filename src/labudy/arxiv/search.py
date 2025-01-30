import os
import re
from typing import List, Dict, Any

import feedparser
import requests

GOOGLE_SEARCH_API_KEY = os.environ.get('GOOGLE_SEARCH_API_KEY')
GOOGLE_SEARCH_ENGINE_ID = os.environ.get('GOOGLE_SEARCH_ENGINE_ID')

def google_search(query: str, max_results: int = 30) -> List[Dict[str, str]]:
    """
    Performs a Google Custom Search restricted to the arXiv domain and retrieves
    up to 'max_results' (default 30) results. Returns a list of dictionaries containing:
      [
        {
          'title': ...,
          'url': ...,
          'snippet': ...
        },
        ...
      ]

    Args:
        query (str): The search query.
        max_results (int): Maximum number of search results to retrieve.

    Returns:
        List[Dict[str, str]]: A list of dictionaries with 'title', 'url', and 'snippet'.
    """
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
        raise ValueError("Google Search environment variables are not properly set.")

    results = []
    url = "https://www.googleapis.com/customsearch/v1"
    # Google Custom Search API allows a maximum of 10 results per request.
    # We'll paginate up to `max_results`.
    for start_index in range(1, max_results + 1, 10):
        params = {
            'key': GOOGLE_SEARCH_API_KEY,
            'cx': GOOGLE_SEARCH_ENGINE_ID,
            'q': query,
            'start': start_index,
            'num': 10,
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        items = data.get('items', [])
        for item in items:
            results.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'snippet': item.get('snippet', '')
            })

        # If fewer than 10 items are returned, we've reached the last page.
        if len(items) < 10:
            break

    return results

def _extract_arxiv_id(url: str) -> str:
    """
    Extracts an arXiv ID from a given URL (without version suffix).

    Examples:
      https://arxiv.org/html/2405.17837v2 -> 2405.17837
      https://arxiv.org/pdf/2407.1558 -> 2407.1558

    Args:
        url (str): The URL from which to extract the arXiv ID.

    Returns:
        str: The extracted arXiv ID, or empty string if none is found.
    """
    # Arxiv ID regex pattern, matching the modern standard: "YYYY.NNNNN"
    match = re.search(r'arxiv\.org/(?:pdf|html|abs)/(\d{4}\.\d+)(v\d+)?', url)
    if match:
        return match.group(1)
    return ""

def _generate_bibtex_key(authors_list: List[str], year_str: str, title_str: str) -> str:
    """
    Generates a simple BibTeX key based on authors, year, and title. 

    Args:
        authors_list (List[str]): List of authors.
        year_str (str): Year of publication.
        title_str (str): Title of the publication.

    Returns:
        str: A BibTeX key string, e.g. "smith2023mytitlegoeshere".
    """
    if not authors_list:
        authors_list = ['unknown']

    # Extract the last word from the first author's name as a last name proxy.
    first_author_last_name = authors_list[0].split()[-1].lower()
    # Normalize the title to alphanumeric characters only, then truncate.
    simplified_title = re.sub(r'[^a-zA-Z0-9]+', '', title_str.lower())
    return f"{first_author_last_name}{year_str}{simplified_title[:32]}"

def _fetch_arxiv_metadata(arxiv_id: str) -> Dict[str, Any]:
    """
    Fetches metadata from the arXiv API for a given arXiv ID.

    Returns a dictionary containing:
    {
      'arxiv_id': ...,
      'title': ...,
      'abstract': ...,
      'abstract_url': ...,
      'pdf_url': ...,
      'tex_url': ...,
      'bibtex': ...
    }

    If no data is found, an empty dictionary is returned.

    Args:
        arxiv_id (str): The arXiv ID for which metadata is to be fetched.

    Returns:
        Dict[str, Any]: A dictionary of metadata; keys include 'title', 'abstract', 
        'abstract_url', 'pdf_url', 'tex_url', and 'bibtex'.
    """
    # Query the arXiv API using feedparser
    api_url = f'https://export.arxiv.org/api/query?search_query=id:{arxiv_id}'
    feed = feedparser.parse(api_url)
    if not feed.entries:
        return {}

    entry = feed.entries[0]

    # Title and abstract
    title = getattr(entry, 'title', "").replace("\n  ", " ")
    abstract = getattr(entry, 'summary', "")

    # Abstract, PDF, and TeX source URL
    abstract_url = ""
    pdf_url = ""
    tex_url = ""

    if hasattr(entry, 'links'):
        for link in entry.links:
            rel = link.get('rel')
            href = link.get('href')
            link_type = link.get('type')
            link_title = link.get('title', '')

            if rel == 'alternate':
                abstract_url = href
            if link_type == 'application/pdf':
                pdf_url = href
            # If there's a "source" link in 'title'
            if 'source' in link_title.lower():
                tex_url = href

    # Default TeX URL if none found
    if not tex_url:
        tex_url = f"https://arxiv.org/src/{arxiv_id}"

    # Authors
    authors = []
    if hasattr(entry, 'authors'):
        authors = [a.name for a in entry.authors if 'name' in a]

    # Publication year
    year = ""
    if hasattr(entry, 'published'):
        # Format: "YYYY-MM-DD"
        year = entry.published.split('-')[0]

    # Primary category
    primary_class = ""
    if hasattr(entry, 'arxiv_primary_category'):
        primary_class = entry.arxiv_primary_category.get('term', '')

    # Build a BibTeX entry
    bibtex_key = _generate_bibtex_key(authors, year, title)
    bibtex_template = (
        "@misc{{{bibtex_key},\n"
        "  title={{{title}}},\n"
        "  author={{{authors}}},\n"
        "  year={{{year}}},\n"
        "  eprint={{{arxiv_id}}},\n"
        "  archivePrefix={{arXiv}},\n"
        "  primaryClass={{{primary_class}}},\n"
        "  url={{{abstract_url}}}\n"
        "}}"
    )
    bibtex_entry = bibtex_template.format(
        bibtex_key=bibtex_key,
        arxiv_id=arxiv_id,
        title=title,
        authors=' and '.join(authors),
        year=year,
        primary_class=primary_class,
        abstract_url=abstract_url
    )

    return {
        'arxiv_id': arxiv_id,
        'title': title,
        'abstract': abstract,
        'abstract_url': abstract_url,
        'pdf_url': pdf_url,
        'tex_url': tex_url,
        'bibtex': bibtex_entry
    }

def get_arxiv_papers_info(google_results: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    Takes a list of Google search results, extracts unique arXiv IDs, merges snippets, 
    and fetches metadata from arXiv. Returns a list of dictionaries, one per arXiv ID, 
    with fields like: 'arxiv_id', 'title', 'abstract', 'abstract_url', 'pdf_url', 
    'tex_url', 'bibtex', and 'snippets'.

    Args:
        google_results (List[Dict[str, str]]): The search results from google_search().

    Returns:
        List[Dict[str, Any]]: A list of arXiv paper info dicts with appended snippets.
    """
    # Gather IDs and snippet text together
    arxiv_dict = {}
    for result in google_results:
        url = result.get('url', '')
        snippet = result.get('snippet', '')
        arxiv_id = _extract_arxiv_id(url)

        if not arxiv_id:
            continue

        if arxiv_id not in arxiv_dict:
            arxiv_dict[arxiv_id] = {
                'arxiv_id': arxiv_id,
                'snippets': []
            }
        arxiv_dict[arxiv_id]['snippets'].append(snippet)

    # Retrieve metadata for each arXiv ID
    final_results = []
    for arxiv_id, info in arxiv_dict.items():
        meta = _fetch_arxiv_metadata(arxiv_id)
        if not meta:
            continue
        meta['snippets'] = info['snippets']
        final_results.append(meta)

    return final_results

def fetch_arxiv_papers_from_query(query: str) -> List[Dict[str, Any]]:
    """
    Performs a Google search for a given query, passes the results to get_arxiv_papers_info,
    and returns the final arXiv paper information list.

    Args:
        query (str): Search query.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries containing arXiv paper metadata. Returns a list of dictionaries, one per arXiv ID, 
    with fields like: 'arxiv_id', 'title', 'abstract', 'abstract_url', 'pdf_url', 
    'tex_url', 'bibtex', and 'snippets'.
    """
    google_results = google_search(query)
    final_results = get_arxiv_papers_info(google_results)
    return final_results

if __name__ == "__main__":
    # Example usage:
    test_query = "LLM Agent for UI/UX optimization"
    google_results = google_search(test_query)
    print("Number of raw Google results:", len(google_results))

    arxiv_results = get_arxiv_papers_info(google_results)
    print("arXiv results:", arxiv_results)
    print("Number of arXiv results:", len(arxiv_results))