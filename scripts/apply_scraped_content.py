"""scripts/_scraped/{Model}.json (scrape_web_content.pyの出力) を
schemas/{Model}/{Model}.schema.json にマージする一回限りのメンテナンススクリプト。

- description: 既存内容に関わらず、スクレイピング結果があれば設定する
  (現状ほぼ全モデルでdescriptionが空、またはプレースホルダのため)
- title: 既にtitleを持つ5モデル(PRESERVE_EXISTING_TITLE)は上書きしない。
  それ以外は空欄のみ埋める
- $refを持つプロパティ(例: Procedure.name)にもtitle/descriptionを
  兄弟キーとして追加できる(refresolve.pyのマージ処理で正しく展開される)
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
SCRAPED_DIR = REPO_ROOT / "scripts" / "_scraped"

PRESERVE_EXISTING_TITLE = {"Organization", "Department", "Land", "Building", "Facility"}


def merge(model: str) -> None:
    scraped_path = SCRAPED_DIR / f"{model}.json"
    schema_path = SCHEMAS_DIR / model / f"{model}.schema.json"
    if not scraped_path.exists() or not schema_path.exists():
        print(f"[skip] {model}: file not found", file=sys.stderr)
        return

    scraped = json.loads(scraped_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    allow_title_overwrite = model not in PRESERVE_EXISTING_TITLE
    changed = 0

    for attr_name, prop_schema in schema.get("properties", {}).items():
        info = scraped.get(attr_name)
        if not info:
            continue
        scraped_title = (info.get("title") or "").strip()
        scraped_desc = (info.get("description") or "").strip()

        if scraped_desc and prop_schema.get("description") != scraped_desc:
            prop_schema["description"] = scraped_desc
            changed += 1

        if scraped_title and (allow_title_overwrite or not prop_schema.get("title")):
            if prop_schema.get("title") != scraped_title:
                prop_schema["title"] = scraped_title
                changed += 1

    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[ok] {model}: {changed} field(s) updated")


def main() -> None:
    models = sys.argv[1:] or sorted(p.stem for p in SCRAPED_DIR.glob("*.json"))
    for model in models:
        merge(model)


if __name__ == "__main__":
    main()
