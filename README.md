# ppp-schema

PPP共通データ仕様協議会が公開する共通データ仕様（JSON Schema）の管理リポジトリ。

## 構成

```
schemas/CommonParts.schema.json                共通属性($defs)。モデル間で重複する型を集約
schemas/{EntityType}/{EntityType}.schema.json  各データモデルのJSON Schema（唯一の原本）
parts/{PartName}.schema.json                   https://ppp-database.org/spec/parts/{PartName}/ に対応する部品定義
enums/{EnumName}.schema.json                   https://ppp-database.org/spec/enum/{EnumName}/ に対応する列挙語彙定義（下記「用語集」参照）
scripts/generate_docs.py                       スキーマから表データ(docs/{EntityType}.json)を生成
scripts/generate_dist.py                       スキーマから$ref完全展開・自己完結の公開用スキーマ(dist/{EntityType}.schema.json)を生成
scripts/refresolve.py                          $refのローカル解決ロジック（generate_docs/dist共通）
docs/{EntityType}.json                         生成された表データ（GitHub Pagesで公開）
dist/{EntityType}.schema.json                  生成された公開用スキーマ（$refなし、GitHub Pagesで公開）
```

## 表データ・公開用スキーマの生成

```
python scripts/generate_docs.py
python scripts/generate_dist.py
```

`docs/{EntityType}.json` は https://ppp-database.org の各データモデルページにWordPressショートコード経由で埋め込まれる。

## 用語集（enum）

各属性の`enum`で列挙される用語（例: 組織種別の”株式会社”“合同会社”など）には、`x-enumDescriptions`というカスタムキーワードで列挙子ごとの定義を付与している。JSON Schema標準の`enum`は許容値の配列でしかなく列挙子ごとに説明を持たせる仕組みがないため、この拡張により機械可読な用語定義を提供する。

```json
"OrganizationCategoryEnum": {
  "type": "string",
  "enum": ["株式会社", "合同会社", "..."],
  "x-enumDescriptions": {
    "株式会社": "会社法に基づく法人形態。出資者(株主)は出資額を限度とする有限責任を負い、株式の発行により資金調達を行う。日本で最も一般的な会社形態。",
    "合同会社": "会社法に基づく持分会社の一種。社員全員が有限責任を負う。2006年の会社法施行により新設された、いわゆる日本版LLC。"
  }
}
```

用語集は`enums/{EnumName}.schema.json`に`$defs.{EnumName}Enum`として定義し、各モデルの該当属性から`$ref`で参照する。狙いは、共通データ仕様に基づくデータ登録（特にAIによる支援）において、字面だけでは判別しにくい類似用語（例:「伸び」「たわみ」「膨れ」「膨張」）を正しく選択できるようにすること。
