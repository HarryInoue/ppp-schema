"""parts/{Name}.schema.json の各$defsから
WordPress埋め込み用の表データJSON (docs/parts/{Name}.json) を生成する。

出力フォーマット(enumsと同型):
    {
      "source_file": "ProcedureStep",
      "defs": {
        "MeasurementStep": {"columns": [...], "rows": [[...], ...]},
        ...
      }
    }

1つのparts/{Name}.schema.jsonファイルに複数の$defsが入っている場合
(例: ProcedureStep.schema.jsonのThreshold/MeasurementStep/CheckStep/
SampleStep)でも全$defsをそのまま出力する。対応するWebページを持たない
補助的な$def(Threshold等、他の$defから$refでのみ参照される断片)が
含まれていてもショートコード側で参照しなければ実害は無いため、生成側
での除外は行わない(enums側の統合$defと同じ方針)。

表の形式はdatamodelと同じ(呼称/Attribute name/type/回数/説明の5列)。
$defが{"properties":{"type":{"const":...},"value":{...}}}という
NGSIラッパー形式の場合はvalueの中身を展開し、ラッパーを持たない
プレーンなオブジェクト形式($refで他の$defから参照される断片、例:
Threshold/MeasurementStep等)の場合はそのproperties直下を展開する。
どちらの場合も、各トップレベル属性は常にフル行(5列)として出力し、
入れ子の子孫はgenerate_docs.pyのrender_field()を再利用して展開する
(子孫のrowspan判定は既存ロジックのまま)。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_docs import (
    COLUMNS,
    _json_type_of_const,
    analyze_nested,
    display_json_type,
    merge_allof,
    render_field,
)
from refresolve import load_and_expand

REPO_ROOT = Path(__file__).resolve().parent.parent
PARTS_DIR = REPO_ROOT / "parts"
DOCS_DIR = REPO_ROOT / "docs" / "parts"


def render_part_field(name: str, schema: dict) -> list:
    """パーツ$defのトップレベル属性1件を、常にフル行(5列)として出力する。

    データモデル表のbuild_table()と同様、トップレベル行は自身の説明が
    空でも常に5列で出す(WordPress側のrowspan計算が「フル行」として
    認識するため)。子孫の展開はrender_field()を再利用する(子孫自身が
    説明を持つかどうかによるrowspan制御はそちらの既存ロジックに委ねる)。
    """
    title = schema.get("title", "") or "-"
    description = schema.get("description", "")

    if "type" not in schema and "const" in schema:
        # stepType等、typeを持たずconstのみのフィールド(NGSIラッパーの
        # "type"属性とは別物で、モデル固有の判別用フィールド)
        disp_type = display_json_type(_json_type_of_const(schema["const"]))
        occurrence, children = "1", []
    else:
        disp_type, occurrence, children = analyze_nested(schema)

    rows = [[title, name, disp_type, occurrence, description]]
    for child_name, child_schema in children:
        rows.extend(render_field(child_name, child_schema, depth=1))
    return rows


def build_def_table(def_schema: dict) -> dict:
    def_schema = merge_allof(def_schema)
    props = def_schema.get("properties")

    if props and "type" in props and "value" in props:
        # NGSIラッパー形式: type(const)は表示せず、valueの中身を展開する
        value_schema = merge_allof(props["value"])
    else:
        # ラッパーを持たないプレーンなオブジェクト($refでのみ参照される断片)
        # または中身の無いbareな値スキーマ(例: OpeningHoursValue)
        value_schema = def_schema

    _, _, children = analyze_nested(value_schema)

    rows = []
    for name, schema in children:
        rows.extend(render_part_field(name, schema))

    return {"columns": COLUMNS, "rows": rows}


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    part_files = sorted(p for p in PARTS_DIR.glob("*.schema.json"))

    for path in part_files:
        name = path.name.removesuffix(".schema.json")
        schema = load_and_expand(path)
        defs = schema.get("$defs", {})

        out_defs = {}
        for def_name, def_schema in defs.items():
            out_defs[def_name] = build_def_table(def_schema)

        out = {"source_file": name, "defs": out_defs}
        out_path = DOCS_DIR / f"{name}.json"
        out_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        total_rows = sum(len(d["rows"]) for d in out_defs.values())
        print(f"[ok] {name}: {len(out_defs)} defs, {total_rows} rows -> {out_path}")


if __name__ == "__main__":
    main()
