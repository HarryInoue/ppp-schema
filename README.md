# ppp-schema

PPP共通データ仕様協議会が公開する共通データ仕様（JSON Schema）の管理リポジトリ。

## 構成

```
schemas/{EntityType}/{EntityType}.schema.json  各データモデルのJSON Schema（唯一の原本）
scripts/generate_docs.py                       スキーマから表データ(docs/{EntityType}.json)を生成
docs/{EntityType}.json                         生成された表データ（GitHub Pagesで公開）
```

## 表データの生成

```
python scripts/generate_docs.py
```

`docs/{EntityType}.json` は https://ppp-database.org の各データモデルページにWordPressショートコード経由で埋め込まれる。
