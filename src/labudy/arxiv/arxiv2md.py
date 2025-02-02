"""
【概要】
  指定した arXiv 論文 URL から TeX ソース（tar アーカイブ）をダウンロードし、
  アーカイブ内の .tex ファイル群からメインファイル（"main.tex" があればそれを優先、なければスコアリングによる選定）を決定します。
  メインファイルから、\begin{document} と \end{document} に囲まれた部分について、
  \input や \include による参照ファイルは再帰的にインライン展開（本文中に挿入）します。
  インライン展開後、コメントアウト部分を削除し、tex ファイルと Markdown ファイルを保存します。

【使い方】
  python arxiv2md.py https://arxiv.org/abs/2407.16741
────────────────────────────
"""
import argparse
import os
import re
import sys
import tarfile
import tempfile
import subprocess
from io import BytesIO

import requests


def parse_args():
    parser = argparse.ArgumentParser(
        description="arXiv の TeX ソースを Markdown に変換するツール"
    )
    parser.add_argument('url', help='arXiv 論文 URL (例: https://arxiv.org/abs/2407.16741)')
    return parser.parse_args()


def download_arxiv_source(url):
    # arXiv の URL から論文IDを抽出
    m = re.search(r'arxiv\.org/abs/([^/?#]+)', url)
    if not m:
        sys.exit("Error: arXiv 論文 URL の形式が正しくありません。")
    paper_id = m.group(1)
    source_url = "https://arxiv.org/e-print/" + paper_id
    print("Downloading TeX source from:", source_url)
    r = requests.get(source_url)
    if r.status_code != 200:
        sys.exit(f"Error: ソースのダウンロードに失敗しました (status code {r.status_code})")
    return paper_id, r.content


def extract_archive(archive_bytes, extract_dir):
    # ダウンロードしたバイト列から tar アーカイブを解凍
    tar_stream = BytesIO(archive_bytes)
    try:
        with tarfile.open(fileobj=tar_stream) as tf:
            tf.extractall(path=extract_dir)
    except Exception as e:
        sys.exit(f"Error: アーカイブの解凍に失敗しました: {e}")


def find_tex_files(root_dir):
    tex_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for name in filenames:
            if name.endswith(".tex"):
                tex_files.append(os.path.join(dirpath, name))
    return tex_files


def score_tex_file(filename):
    score = 0
    try:
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return score
    if "\\documentclass" in text:
        score += 10
    if "\\begin{document}" in text:
        score += 10
    return score


def select_main_tex(tex_files):
    # 優先的に "main.tex" を探す
    for path in tex_files:
        if os.path.basename(path) == "main.tex":
            print("Found main.tex:", path)
            return path
    # それがなければスコアの高いものを選択する
    if not tex_files:
        return None
    scored = [(score_tex_file(fn), fn) for fn in tex_files]
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_file = scored[0]
    print(f"Selecting candidate main file based on score ({best_score}):", best_file)
    return best_file


def extract_document_content(tex_text):
    # \begin{document} と \end{document} に囲まれた部分を抽出
    pattern = re.compile(r'\\begin\{document\}(.*?)\\end\{document\}', re.DOTALL)
    m = pattern.search(tex_text)
    if m:
        print("Extracted content between \\begin{document} and \\end{document}.")
        return m.group(1)
    else:
        print("Warning: \\begin{document}～\\end{document} が見つからなかったため、全文を使用します。", file=sys.stderr)
        return tex_text


def inline_includes(text, base_dir, included_files=None):
    """
    再帰的に \input や \include コマンドを展開します。
    base_dir は、現在参照しているファイルのディレクトリです。
    included_files は循環参照防止のためのセットです。
    """
    if included_files is None:
        included_files = set()

    pattern = re.compile(r'\\(?:input|include)\{([^}]+)\}')

    def replace_command(match):
        filename_raw = match.group(1).strip()
        # 拡張子がなければ .tex を補完
        base, ext = os.path.splitext(filename_raw)
        if not ext:
            filename_candidate = filename_raw + ".tex"
        else:
            filename_candidate = filename_raw

        # base_dir からの相対パスとして探す
        file_path = os.path.join(base_dir, filename_raw)
        file_path_candidate = os.path.join(base_dir, filename_candidate)
        if os.path.exists(file_path):
            chosen_path = file_path
        elif os.path.exists(file_path_candidate):
            chosen_path = file_path_candidate
        else:
            print(f"Warning: インクルード先のファイルが見つかりません: {filename_raw}", file=sys.stderr)
            return ""
        chosen_path = os.path.abspath(chosen_path)
        if chosen_path in included_files:
            print(f"Warning: 循環参照を検出しました: {chosen_path}", file=sys.stderr)
            return ""
        try:
            with open(chosen_path, "r", encoding="utf-8", errors="ignore") as f:
                included_text = f.read()
        except Exception as e:
            print(f"Error: インクルード先ファイルの読み込みに失敗しました {chosen_path}: {e}", file=sys.stderr)
            return ""
        included_files.add(chosen_path)
        new_base = os.path.dirname(chosen_path)
        # 再帰的に展開
        inlined = inline_includes(included_text, new_base, included_files)
        included_files.remove(chosen_path)
        return inlined

    new_text = pattern.sub(replace_command, text)
    # 万一、入れ子の \input や \include が残っている場合は再帰的に展開
    if pattern.search(new_text):
        new_text = inline_includes(new_text, base_dir, included_files)
    return new_text


def remove_tex_comments(text: str) -> str:
    """
    与えられたTeXソースの文字列から、エスケープされていない % から行末までのコメント部分を削除して返します。
    戻り値は、各行についてエスケープされていない % より後ろ（行末）を削除した文字列です。
    """
    lines = text.splitlines(keepends=True)
    cleaned_lines = []
    for line in lines:
        if line.lstrip().startswith("%"):
            continue
        else:
            cleaned_lines.append(line)
    
    return "".join(cleaned_lines)


def convert_to_markdown(latex_file_path):
    # pandoc を利用して LaTeX から Markdown に変換
    try:
        result = subprocess.run(
            ["pandoc", "-f", "latex", "-t", "markdown", latex_file_path, "--wrap=none"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        sys.exit(f"Error: pandoc の実行に失敗しました: {e.stderr}")


def main():
    args = parse_args()
    paper_id, source_bytes = download_arxiv_source(args.url)
    # 論文ID中のドット(.)をハイフン(-)に置換
    processed_id = paper_id.replace(".", "-")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # ダウンロードしたアーカイブを展開
        extract_archive(source_bytes, tmpdir)
        tex_files = find_tex_files(tmpdir)
        if not tex_files:
            sys.exit("Error: 展開されたアーカイブ内に .tex ファイルが見つかりませんでした。")
        main_tex_path = select_main_tex(tex_files)
        if not main_tex_path:
            sys.exit("Error: メインとなる TeX ファイルの選定に失敗しました。")
        try:
            with open(main_tex_path, "r", encoding="utf-8", errors="ignore") as f:
                main_tex_content = f.read()
        except Exception as e:
            sys.exit(f"Error: メインファイルの読み込みに失敗しました: {e}")

        # ドキュメント環境内のテキストのみを抽出
        document_content = extract_document_content(main_tex_content)
        # \input, \include を再帰的にインライン展開
        base_directory = os.path.dirname(main_tex_path)
        inlined_content = inline_includes(document_content, base_directory)
        # メインの TeX ファイル中のドキュメント部分を置換
        final_tex_content = main_tex_content.replace(document_content, inlined_content)
        # コメントアウト部分の削除
        final_tex_content = remove_tex_comments(final_tex_content)
        
        # 出力ファイル名は、ハイフンに置換した processed_id を利用して決定
        output_tex_filename = f"{processed_id}.tex"
        output_md_filename = f"{processed_id}.md"

        # 現在の作業ディレクトリに最終 TeX ファイルを保存
        try:
            with open(output_tex_filename, "w", encoding="utf-8") as f:
                f.write(final_tex_content)
            print(f"最終 TeX ファイルを保存しました: {output_tex_filename}")
        except Exception as e:
            sys.exit(f"Error: TeX ファイルの書き込みに失敗しました: {e}")
        
        # pandoc を利用して Markdown に変換
        markdown_text = convert_to_markdown(output_tex_filename)
        
        try:
            with open(output_md_filename, "w", encoding="utf-8") as out_f:
                out_f.write(markdown_text)
            print(f"Markdown への変換が完了しました。出力先: {output_md_filename}")
        except Exception as e:
            sys.exit(f"Error: Markdown ファイルの書き込みに失敗しました: {e}")


if __name__ == '__main__':
    main()