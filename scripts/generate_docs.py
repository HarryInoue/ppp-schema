"""JSON Schema (schemas/{Model}/{Model}.schema.json) から
WordPress埋め込み用の表データJSON (docs/{Model}.json) を生成する。

出力フォーマット（ppp-datamodel-embed プラグインの契約と一致させること）:
    {"model": "...", "columns": [...], "rows": [[...], ...]}

行の長さについて:
    トップレベル属性の行は列数と同じ長さ(説明列を含む)。
    その属性が入れ子構造(object/array of object)を持つ場合、直後に続く
    子孫行は列数より1つ少ない長さ(説明列を持たない)で出力する。
    WordPress側はこれを見て、説明セルに自動でrowspanを付与する。
"""
import json
import sys
from pathlib import Path

from refresolve import load_and_expand

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
DOCS_DIR = REPO_ROOT / "docs"

COLUMNS = ["呼称", "Attribute name", "type", "回数", "説明"]
INDENT = "　"  # 全角スペース。入れ子の深さぶん繰り返す

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

JSON_TYPE_DISPLAY = {
    "string": "Text",
    "number": "Number",
    "integer": "Integer",
    "boolean": "Boolean",
}


def linkify_type(type_name: str) -> str:
    """type列の値を、部品ページが存在すれば [text](url) 記法に変換する。"""
    url = PART_LINKS.get(type_name)
    return f"[{type_name}]({url})" if url else type_name


def display_json_type(json_type) -> str:
    if isinstance(json_type, list):
        return " / ".join(dict.fromkeys(display_json_type(t) for t in json_type))
    return JSON_TYPE_DISPLAY.get(json_type, json_type or "")


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


def infer_type_and_occurrence(prop_schema: dict):
    """1属性分のスキーマからNGSI型(type列)・単一/配列(回数列)・入れ子展開用の
    (value_schema, raw_ngsi_type)を推定する。

    NGSI-LDラッパー形式 {"properties": {"type": {"const": "Text"}, "value": {...}}}
    と、id/typeのようなフラットな形式 {"type": "string"} / {"const": "..."} の
    両方に対応する。属性直下がoneOf（例: Observation.performedAt）やgeo:json等の
    複合ケースでは、既に部品ページ等で表現済みのため入れ子展開は行わない
    (value_schema=Noneを返す)。
    """
    if "oneOf" in prop_schema and "properties" not in prop_schema:
        types, occurrences = [], []
        for variant in prop_schema["oneOf"]:
            t, occ, _, _ = infer_type_and_occurrence(variant)
            types.append(t)
            occurrences.append(occ)
        uniq_types = list(dict.fromkeys(types))
        uniq_occurrences = list(dict.fromkeys(occurrences))
        return " / ".join(uniq_types), " / ".join(uniq_occurrences), None, None

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
        return display_type, occurrence, None, None

    return linkify_type(ngsi_type), occurrence, value_schema, ngsi_type


def analyze_nested(schema: dict):
    """ラッパーなしのプレーンなJSON Schemaフィールドを解析する。

    戻り値: (type列表示, 回数列表示, [(子のAttribute name, 子のschema), ...])
    子が無い場合は空リストを返す。
    """
    json_type = schema.get("type")

    if json_type == "array":
        items = schema.get("items")

        if isinstance(items, list):
            # タプル形式: 名前を持たない位置指定の要素群
            children = [(f"[{i}]", item) for i, item in enumerate(items)]
            return "Array", "1", children

        if isinstance(items, dict):
            max_items = items.get("maxItems")
            occurrence = f"*(最大{max_items})" if max_items else "*"
            if items.get("type") == "object" and "properties" in items:
                return "Array(Object)", occurrence, list(items["properties"].items())
            item_type = display_json_type(items.get("type", ""))
            disp = f"Array({item_type})" if item_type else "Array"
            return disp, occurrence, []

        return "Array", "*", []

    if json_type == "object" and "properties" in schema:
        return "Object", "1", list(schema["properties"].items())

    return display_json_type(json_type), "1", []


def render_field(name: str, schema: dict, depth: int) -> list:
    """1つのネストしたフィールドを、自身+子孫の「短い行」(説明列なし)のリストとして返す。"""
    indent = INDENT * depth
    title = schema.get("title", "") or "-"
    disp_type, occurrence, children = analyze_nested(schema)

    rows = [[f"{indent}{title}", f"{indent}{name}", disp_type, occurrence]]
    for child_name, child_schema in children:
        rows.extend(render_field(child_name, child_schema, depth + 1))
    return rows


def build_table(schema: dict, model: str) -> dict:
    rows = []
    for attr_name, prop_schema in schema.get("properties", {}).items():
        title = prop_schema.get("title", "") or "-"
        description = prop_schema.get("description", "")
        value_schema = None

        if attr_name == "id":
            ngsi_type, occurrence = linkify_type("Id"), "1"
        elif attr_name == "type":
            ngsi_type, occurrence = "Text", "1"  # /spec/parts/type/ は存在しないためリンクなし
        else:
            ngsi_type, occurrence, value_schema, raw_type = infer_type_and_occurrence(prop_schema)
            if raw_type in PART_LINKS:
                # 部品ページで説明済みの型(PostalAddress等)は中身を展開しない
                value_schema = None

        rows.append([title, attr_name, ngsi_type, occurrence, description])

        if value_schema is not None:
            _, _, children = analyze_nested(value_schema)
            for child_name, child_schema in children:
                rows.extend(render_field(child_name, child_schema, depth=1))

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
        missing_titles = sum(1 for r in table["rows"] if r and r[0] == "-")
        print(f"[ok] {model}: {len(table['rows'])} rows, 呼称欠落 {missing_titles}件 -> {out_path}")


if __name__ == "__main__":
    main()
