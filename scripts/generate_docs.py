"""JSON Schema (schemas/{Model}/{Model}.schema.json) から
WordPress埋め込み用の表データJSON (docs/{Model}.json) を生成する。

出力フォーマット（ppp-datamodel-embed プラグインの契約と一致させること）:
    {"model": "...", "columns": [...], "rows": [[...], ...]}
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
DOCS_DIR = REPO_ROOT / "docs"

COLUMNS = ["呼称", "Attribute name", "type", "回数", "説明"]


def _json_type_of_const(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return ""


def infer_type_and_occurrence(prop_schema: dict) -> tuple[str, str]:
    """1属性分のスキーマからNGSI型(type列)と単一/配列(回数列)を推定する。

    NGSI-LDラッパー形式 {"properties": {"type": {"const": "Text"}, "value": {...}}}
    と、id/typeのようなフラットな形式 {"type": "string"} / {"const": "..."} の
    両方に対応する。
    """
    props = prop_schema.get("properties")
    if props and "type" in props and "value" in props:
        ngsi_type = props["type"].get("const", "")
        value_schema = props["value"]
    else:
        value_schema = prop_schema
        ngsi_type = prop_schema.get("type", "")
        if not ngsi_type and "const" in prop_schema:
            ngsi_type = _json_type_of_const(prop_schema["const"])

    if value_schema.get("type") == "array":
        max_items = value_schema.get("maxItems")
        occurrence = f"*(最大{max_items})" if max_items else "*"
    else:
        occurrence = "1"

    return ngsi_type, occurrence


def build_table(schema: dict, model: str) -> dict:
    rows = []
    for attr_name, prop_schema in schema.get("properties", {}).items():
        title = prop_schema.get("title", "") or "-"
        description = prop_schema.get("description", "")
        ngsi_type, occurrence = infer_type_and_occurrence(prop_schema)
        rows.append([title, attr_name, ngsi_type, occurrence, description])

    return {"model": model, "columns": COLUMNS, "rows": rows}


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    models = sorted(p.name for p in SCHEMAS_DIR.iterdir() if p.is_dir())

    for model in models:
        schema_path = SCHEMAS_DIR / model / f"{model}.schema.json"
        if not schema_path.exists():
            print(f"[skip] {model}: schema file not found", file=sys.stderr)
            continue

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        table = build_table(schema, model)

        out_path = DOCS_DIR / f"{model}.json"
        out_path.write_text(
            json.dumps(table, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        missing_titles = sum(1 for r in table["rows"] if r[0] == "-")
        print(f"[ok] {model}: {len(table['rows'])} rows, 呼称欠落 {missing_titles}件 -> {out_path}")


if __name__ == "__main__":
    main()
