import os
import io
import time
import requests
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, unquote
import re

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

def _get_filename_from_url(url: str) -> str:
    """
    Extract the filename from a URL. If the URL doesn't end with a well-defined filename,
    a default is generated based on the domain and path.

    Args:
        url (str): The URL to parse.

    Returns:
        str: Extracted or generated filename (e.g., "report.pdf" or "example_com-some_page.pdf").
    """
    # Parse the URL to extract components
    parsed_url = urlparse(url)
    domain = parsed_url.netloc.replace('.', '_')  # Replace dots to make it filename-friendly
    path = parsed_url.path.strip('/').replace('/', '_')  # Replace slashes with underscores

    # Decode URL-encoded characters
    path = unquote(path)

    # Sanitize the path to remove or replace any characters that are invalid in filenames
    path = re.sub(r'[<>:"/\\|?*]', '_', path)

    # If path is empty, use 'homepage' as a default identifier
    if not path:
        path = "homepage"

    # Combine domain and path to form the filename
    base_filename = f"{domain}-{path}.pdf"

    # Ensure the filename is not excessively long
    max_length = 255  # Typical maximum filename length
    if len(base_filename) > max_length:
        base_filename = base_filename[:max_length - 4] + ".pdf"

    return base_filename

def _convert_url_to_pdf_with_playwright(url: str) -> bytes:
    """
    Convert the given web page at URL to PDF by "printing" it out via playwright.
    Returns PDF as bytes.

    Note:
        Requires playwright to be installed and browsers to be set up:
           pip install playwright
           playwright install

    Args:
        url (str): The target web page URL.

    Returns:
        bytes: The PDF bytes.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until='networkidle')
        css_content = """
        @page {
            size: A4;
            margin: 15mm;
        }

        .avoid-break {
            page-break-inside: avoid;
        }
        """
        page.add_style_tag(content=css_content)
        page.emulate_media(media="screen")
        pdf_bytes = page.pdf(
            print_background=True,
            prefer_css_page_size=True  # CSS の @page ルールを優先
        )
        browser.close()
    return pdf_bytes

def upload_to_gemini_from_local(path: str, mime_type="application/pdf"):
    """
    Uploads a local PDF file to Gemini.

    Args:
        path (str): Local path to the PDF file.
        mime_type (str): MIME type for the PDF file.

    Returns:
        google.generativeai.File: The uploaded file object.
    """
    file = genai.upload_file(path, mime_type=mime_type)
    print(f"Uploaded local file '{file.display_name}' as: {file.uri}")
    return file

def upload_to_gemini_from_url(url: str, mime_type="application/pdf"):
    """
    Downloads a file from a URL. If it's not a PDF, converts the HTML to PDF before uploading
    to Gemini by "printing" the webpage to PDF with playwright.

    Args:
        url (str): The URL of the PDF or webpage.
        mime_type (str): MIME type for the PDF file.

    Returns:
        google.generativeai.File: The uploaded file object.
    """
    response = requests.get(url, stream=True)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()

    if "pdf" in content_type:
        # It's already PDF
        pdf_in_memory = io.BytesIO(response.content)
        file_name = response.headers.get("Content-Disposition", "")
        if file_name and "filename=" in file_name:
            display_name = file_name.split("filename=")[1].strip('"')
        else:
            display_name = _get_filename_from_url(url)
    else:
        # It's HTML (or some other format) → Convert to PDF using playwright
        pdf_bytes = _convert_url_to_pdf_with_playwright(url)
        pdf_in_memory = io.BytesIO(pdf_bytes)

        # We'll adjust the display name to indicate it was converted from HTML
        base_name = _get_filename_from_url(url)
        if not base_name.endswith(".pdf"):
            base_name += ".pdf"
        display_name = base_name
        # Optionally, save the converted PDF to a file for debugging or reference:
        with open(display_name, "wb") as f:
            f.write(pdf_bytes)

    file = genai.upload_file(pdf_in_memory, display_name=display_name, mime_type=mime_type)
    print(f"Uploaded file (URL: {url}) as '{file.display_name}': {file.uri}")
    return file


def upload_to_gemini(file):
    """
    Uploads a file to Gemini.

    Args:
        file (str): The file path or URL to upload.

    Returns:
        google.generativeai.File: The uploaded file object.
    """
    if file.startswith("http://") or file.startswith("https://"):
        return upload_to_gemini_from_url(file)
    else:
        return upload_to_gemini_from_local(file)

def wait_for_files_active(files):
    """
    Waits for each file in the given list to become ACTIVE in Gemini.
    This uses simple polling. Production code should handle errors more robustly.

    Args:
        files (List[google.generativeai.File]): A list of uploaded file objects.
    """
    print("Waiting for file processing to finish...")
    for f in files:
        file_name = f.name
        file_info = genai.get_file(file_name)

        while file_info.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(5)
            file_info = genai.get_file(file_name)

        if file_info.state.name != "ACTIVE":
            raise RuntimeError(f"File {file_name} failed to process")
    print("\nAll files are ACTIVE and ready for use.")

def chat_about_pdfs(pdf_inputs, question, model_name="gemini-2.0-flash-exp", system_instruction="You are a helpful assistant that can read and explain uploaded PDF content."):
    """
    Takes a list of PDF inputs (local paths or URLs) and a question to ask.
    Uploads the PDF files to Gemini, waits for them to be active,
    then starts a single chat session that contains all PDFs plus the user's question.

    Args:
        pdf_inputs (List[str]): A list of strings, each either a local PDF path or a URL.
        question (str): The question (string) to ask about the PDF content.
        model_name (str): The Gemini model name to use.

    Returns:
        str: The assistant's response text.
    """
    # 1. Upload and collect all file objects
    uploaded_files = []
    for pdf_input in pdf_inputs:
        if pdf_input.startswith("http://") or pdf_input.startswith("https://"):
            file_obj = upload_to_gemini_from_url(pdf_input)
        else:
            file_obj = upload_to_gemini_from_local(pdf_input)
        uploaded_files.append(file_obj)

    # 2. Wait for all uploaded files to become ACTIVE
    wait_for_files_active(uploaded_files)

    # 3. Create a chat session including *all* PDFs as part of the user's message
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "temperature": 0,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        },
        system_instruction=system_instruction
    )

    response = model.generate_content(
        [*uploaded_files, question],
    )
    return response.text

if __name__ == "__main__":
    # Example usage:
    # Mix of local and remote PDFs
    pdf_list = [
        "https://arxiv.org/pdf/2411.06559"
    ]
    user_question = "添付された資料について説明してください。"

    final_answer = chat_about_pdfs(pdf_list, user_question)
    print("\nFinal Answer:", final_answer)