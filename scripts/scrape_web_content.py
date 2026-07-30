"""ppp-database.org の公開ページから 呼称/補足(説明文) を抽出し、
schemas/{Model}/{Model}.schema.json の title/description に反映するための
一回限りのメンテナンススクリプト。

HTMLテーブル(1つ目の<table>)を解析する。補足列はrowspanで複数属性にまたがる
ことがあるため、rowspanを追跡しながら値を引き継ぐ。
"""
import html
import json
import re
import sys
import urllib.request
import ssl
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"

CELL_RE = re.compile(r'<td([^>]*)>(.*?)</td>', re.DOTALL)
ROW_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL)
ROWSPAN_RE = re.compile(r'rowspan="(\d+)"')
A_TAG_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)


def cell_text_to_markdown(raw: str) -> str:
    """セル内HTMLをプレーンテキスト化する。<a>はppp-datamodel-embed互換の
    [text](url) 記法に変換し、その他のタグは除去する。"""
    raw = A_TAG_RE.sub(lambda m: f'[{_strip_tags(m.group(2))}]({m.group(1)})', raw)
    raw = re.sub(r'<br\s*/?>', '\n', raw)
    raw = _strip_tags(raw)
    raw = html.unescape(raw)
    return raw.strip()


def _strip_tags(s: str) -> str:
    return re.sub(r'<[^>]+>', '', s)


def fetch_html(url: str) -> str:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(url, timeout=15, context=ctx) as resp:
        return resp.read().decode('utf-8')


def parse_datamodel_table(html_text: str) -> dict:
    """データモデルの表(1つ目の<table>)から attr_name -> {"title":.., "description":..} を返す。"""
    tables = re.findall(r'<table.*?</table>', html_text, re.DOTALL)
    if not tables:
        raise ValueError('table not found')
    table = tables[0]

    rows = ROW_RE.findall(table)
    result = {}
    pending_desc = None   # (残り行数, 説明文) rowspanの引き継ぎ用
    pending_maxspan_col = None

    data_rows = rows[2:]  # 先頭2行はヘッダ("Data Model"/"説明" と 列名)

    for row_html in data_rows:
        raw_cells = CELL_RE.findall(row_html)
        if not raw_cells:
            continue

        # 各セルの(rowspan, テキスト)を取得
        cells = []
        for attrs, content in raw_cells:
            span_match = ROWSPAN_RE.search(attrs)
            span = int(span_match.group(1)) if span_match else 1
            cells.append((span, cell_text_to_markdown(content)))

        if len(cells) < 4:
            continue

        attr_name = _strip_tags(raw_cells[0][1])
        attr_name = html.unescape(attr_name).strip()
        title = cells[1][1] if len(cells) > 1 else ''

        # 補足列(5番目、index=4)の処理。rowspanで前の行から引き継ぐ場合がある
        if len(cells) > 4:
            desc_span, desc_text = cells[4]
            if desc_span > 1:
                pending_desc = [desc_span - 1, desc_text]
                description = desc_text
            else:
                description = desc_text
        elif pending_desc and pending_desc[0] > 0:
            description = pending_desc[1]
            pending_desc[0] -= 1
        else:
            description = ''

        if attr_name:
            result[attr_name] = {'title': title, 'description': description}

    return result


def main():
    if len(sys.argv) < 2:
        print('usage: python scrape_web_content.py <Model> [<Model2> ...]', file=sys.stderr)
        sys.exit(1)

    for model in sys.argv[1:]:
        url = f'https://ppp-database.org/spec/datamodel/{model}/'
        print(f'=== {model} ({url}) ===')
        html_text = fetch_html(url)
        data = parse_datamodel_table(html_text)
        for attr, info in data.items():
            print(f"  {attr}: title={info['title']!r}")
        out_path = REPO_ROOT / 'scripts' / '_scraped' / f'{model}.json'
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  -> saved to {out_path}')


if __name__ == '__main__':
    main()
