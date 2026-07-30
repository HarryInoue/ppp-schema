"""JSON Schema (schemas/{Model}/{Model}.schema.json) から
WordPress埋め込み用の表データJSON (docs/{Model}.json) を生成する。

出力フォーマット（ppp-datamodel-embed プラグインの契約と一致させること）:
    {"model": "...", "columns": [...], "rows": [[...], ...]}
"""
import json
import sys
from pathlib import Path

from refresolve import load_and_expand

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
DOCS_DIR = REPO_ROOT / "docs"

COLUMNS = ["呼称", "Attribute name", "type", "回数", "説明"]

# https://ppp-database.org/spec/parts/ に実在するページ一覧(2026-07確認)
PART_LINKS = {
    "ContactPoint": "https://ppp-database.org/spec/parts/ContactPoint/",
    "IdentificationGroup": "https://ppp-database.org/spec/parts/IdentificationGroup/",
    "OpeningHours": "https://ppp-database.org/spec/parts/OpeningHours/",
    "Point": "https://ppp-database.org/spec/parts/Point/",
    "Polygon": "https://ppp-database.org/spec/parts/Polygon/",
    "PostalAddress": "https://ppp-database.org/spec/parts/PostalAddress/",
    "PriceSpecification": "https://ppp-database.org/spec/parts/PriceSpecification/",
    "Accessibility": "https://ppp-database.org/spec/parts/Accessibility/",
    "ChildCare": "https://ppp-database.org/spec/parts/ChildCare/",
    "ProcedureStep": "https://ppp-database.org/spec/parts/ProcedureStep/",
    "Id": "https://ppp-database.org/spec/parts/id/",
}


def linkify_type(type_name: str) -> str:
    """type列の値を、部品ページが存在すれば [text](url) 記法に変換する。"""
    url = PART_LINKS.get(type_name)
    return f"[{type_name}]({url})" if url else type_name


def resolve_geo_types(value_schema: dict) -> list[str]:
    """geo:json属性のvalueスキーマから実際のジオメトリ型名(Point/Polygon等)を取り出す。

    単一形式 {"properties": {"type": {"const": "Point"}, ...}} と、
    oneOf形式 {"oneOf": [{"properties": {"type": {"const": "Point"}}}, ...]} の
    両方に対応する。
    """
    variants = value_schema.get("oneOf") or [value_schema]
    names = []
    for variant in variants:
        const = variant.get("properties", {}).get("type", {}).get("const")
        if const:
            names.append(const)
    return names


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
    両方に対応する。属性直下がoneOf（例: Observation.performedAt）の場合は
    各バリアントを解決して " / " で連結する。
    """
    if "oneOf" in prop_schema and "properties" not in prop_schema:
        types, occurrences = [], []
        for variant in prop_schema["oneOf"]:
            t, occ = infer_type_and_occurrence(variant)
            types.append(t)
            occurrences.append(occ)
        uniq_types = list(dict.fromkeys(types))
        uniq_occurrences = list(dict.fromkeys(occurrences))
        return " / ".join(uniq_types), " / ".join(uniq_occurrences)

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

    if ngsi_type == "geo:json":
        geo_names = resolve_geo_types(value_schema)
        display_type = " / ".join(linkify_type(n) for n in geo_names) if geo_names else ngsi_type
    else:
        display_type = linkify_type(ngsi_type)

    return display_type, occurrence


def build_table(schema: dict, model: str) -> dict:
    rows = []
    for attr_name, prop_schema in schema.get("properties", {}).items():
        title = prop_schema.get("title", "") or "-"
        description = prop_schema.get("description", "")
        if attr_name == "id":
            ngsi_type, occurrence = linkify_type("Id"), "1"
        elif attr_name == "type":
            ngsi_type, occurrence = "Text", "1"  # /spec/parts/type/ は存在しないためリンクなし
        else:
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

        schema = load_and_expand(schema_path)  # $ref(同一ファイル/CommonParts等)を展開してから処理
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
