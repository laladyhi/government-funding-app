# 원본 데이터 해시(Hash) 계산 기준

**작성일**: 2026-09-04 (데이터 품질 점검에서 발견된 해시 불일치 수정과 함께 작성)

## 무엇이 문제였나

지금까지는 "원본 해시"가 두 가지 다른 방식으로 계산되고 있었다.

1. `programs.latest_raw_hash`, `source_documents.content_hash`(웹페이지) —
   수집한 데이터를 파이썬 딕셔너리 상태에서 `json.dumps(item, sort_keys=True)`
   로 다시 직렬화해 계산 (키 순서를 정렬하고, 들여쓰기 없이).
2. `raw_api_responses.content_hash` —
   디스크에 저장된 파일을 텍스트로 읽어(`read_text`) 그 내용으로 계산.

두 방식이 계산 대상 자체가 달라서(정렬된 압축 문자열 vs 저장된 파일의
들여쓰기된 텍스트), 같은 원본이라도 값이 항상 달랐다. 게다가 파일 저장은
`write_text()`를 썼는데, 이 함수는 운영체제에 따라 줄바꿈 문자를
바꿀 수 있어(Windows에서 `\n` → `\r\n`) 같은 내용을 두 번 저장해도
바이트가 달라질 수 있는 문제도 있었다.

## 새 기준 (지금부터 이것 하나만 쓴다)

> **해시 = 디스크에 저장된 JSON 파일을 바이너리로 그대로 읽은 바이트에 대한 SHA-256**

```python
# collector/fetch_and_store.py
def compute_file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

이 방식의 핵심 원칙:

- **재직렬화하지 않는다.** 파이썬 딕셔너리를 다시 `json.dumps()`로 만들어
  해싱하지 않고, 항상 "이미 저장되어 있는 파일 자체"를 대상으로 한다.
  그래서 키 정렬 방식·들여쓰기 규칙이 해시 결과에 전혀 영향을 주지 않는다.
- **바이너리로 읽는다.** `read_bytes()`를 쓰고 `read_text()`는 쓰지 않는다.
  텍스트 모드 읽기는 줄바꿈 문자를 자동으로 변환할 수 있어(universal
  newlines) 원본 바이트와 달라질 수 있기 때문이다.
- **파일 저장도 바이트 단위로 한다.** 새로 파일을 저장할 때도
  `write_text()` 대신 `json.dumps(...).encode("utf-8")`로 만든 바이트를
  `write_bytes()`로 그대로 쓴다 (`collector/fetch_and_store.py`의
  `_write_json_bytes()`). 이러면 저장 시점의 플랫폼(Windows/Mac/Linux)과
  무관하게 항상 같은 내용이면 항상 같은 바이트가 저장된다.

## 저장 파일 자체의 형식 (참고용 — 해시 계산과는 무관)

새로 저장되는 원본 JSON 파일은 다음 형식을 따른다. 이 형식 자체는 해시
계산에 영향을 주지 않지만(해시는 "결과 파일"만 보므로), 파일을 사람이
읽고 검토하기 쉽게 하기 위한 규칙이다.

- 인코딩: UTF-8
- 들여쓰기: 2칸 (`json.dumps(..., indent=2)`)
- 키 순서: API가 응답한 원래 순서를 그대로 유지 (정렬하지 않음) — 원본을
  최대한 그대로 보존한다는 원칙에 맞춤
- 한글 등 비ASCII 문자: 이스케이프하지 않고 그대로 저장 (`ensure_ascii=False`)

## 기존에 이미 저장된 파일(2026-09-04 최초 수집분)은 어떻게 되는가

**전혀 건드리지 않는다.** 이미 디스크에 있는 20개 공고 원본 + 2개 페이지
원본 파일은 `write_text()`로 저장되어 있어(Windows 환경이라 줄바꿈이
`\r\n`일 수 있음) 위의 "새 저장 형식"과 바이트 수준에서 다를 수 있지만,
이는 내용이 아니라 형식의 차이이며 원본 파일 수정 금지 원칙에 따라
다시 쓰지 않는다. 이 파일들의 해시는 **지금 있는 그대로의 바이트**를
`compute_file_hash()`로 계산한 값이며, 그 값이 DB에 재기록되었다
(`app/db/rehash_raw_20260904.py`).

## 이 기준이 적용되는 곳

| 컬럼 | 의미 | 계산 대상 파일 |
|---|---|---|
| `programs.latest_raw_hash` | 이 지원사업의 최신 원본 스냅샷 해시 | `collector/raw/bizinfo/items/{pblancId}/` 안의 최신 파일 |
| `source_documents.content_hash` (document_type='웹페이지') | 위와 동일한 값 (같은 파일 기준) | 위와 동일 |
| `raw_api_responses.content_hash` (response_type='item') | 항목 단위 원본 보존본의 해시 | 해당 raw 파일 |
| `raw_api_responses.content_hash` (response_type='page') | 페이지 단위 원본 보존본의 해시 | 해당 raw 파일 |

네 곳 모두 **같은 함수, 같은 파일**을 기준으로 계산되므로, 이제부터는
서로 값이 다를 이유가 없다. 값이 다르면 그 자체로 "무언가 잘못됐다"는
신호로 볼 수 있다.
