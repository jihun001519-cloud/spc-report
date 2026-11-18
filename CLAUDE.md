# CLAUDE.md

## 프로젝트 목적
- 반도체 공정 SPC(통계적 공정 관리) **포트폴리오** (취업용)
- **자동화 외주 샘플**: 엑셀 측정 데이터를 넣으면 SPC 리포트 엑셀이 자동으로 만들어지는 프로그램

## 사용자
- 반도체 공정 직무로 취업을 준비하는 학생 (ADsP, SQLD, 정보처리기사 보유)
- 목표는 **코드를 이해하면서 배우는 것**입니다. 파일이나 기능을 만들 때마다 무엇을 하는지 **짧게(3~4줄)** 설명해 주세요.

## 로드맵
1. [완료] X-bar–R 관리도 리포트
2. [완료] Phase I / Phase II 분리
3. Western Electric 규칙 (연속 패턴 탐지)
4. 공정능력지수 Cp/Cpk (규격 한계 USL/LSL 입력)
5. 버튼으로 실행하는 프로그램(.exe): 외주 샘플용

## 작업 규칙
- 기능 하나가 끝날 때마다 **테스트 → 커밋 → push** 순서로 진행합니다.
- 테스트가 실패하면 커밋하지 않습니다.
- 기능을 추가하면 README도 함께 갱신합니다.

## 개발 환경 / 명령어
- uv로 관리하는 Python 3.12 프로젝트 (`src/spc_report/`)
- `uv sync`: 의존성 설치
- `uv run pytest`: 테스트 실행
- `uv run spc-generate --out data --days 10 --seed 42`: 가상 측정 데이터 생성
- `uv run spc-report --in data --out output/spc_report.xlsx [--phase1-days 5]`: 리포트 생성
- `data/`, `output/`은 생성물이라 git에 올리지 않습니다(.gitignore).
- `output/spc_report.xlsx`가 엑셀에서 열려 있으면 저장할 때 PermissionError가 납니다. 엑셀을 닫고 다시 실행하세요.

## 코드 구조
| 파일 | 역할 |
|---|---|
| `config.py` | 컬럼명, 경로, 장비별 성향, SPC 상수(A2, D3, D4), Phase I 기본 일수 |
| `generate.py` | 가상 데이터 생성 (스파이크, 평균 이동 이상치 포함) |
| `loader.py` | 폴더 내 엑셀을 모두 읽어 합치고 검증 |
| `stats.py` | 요약통계, 서브그룹(웨이퍼 1장 = 5포인트), 관리 한계, OOC 판정, Phase 구분 |
| `chart.py` | X-bar–R 관리도 PNG 생성 (matplotlib) |
| `report.py` | 엑셀 리포트 작성 (openpyxl) |
| `cli.py` | `spc-generate`, `spc-report` 명령어 |
