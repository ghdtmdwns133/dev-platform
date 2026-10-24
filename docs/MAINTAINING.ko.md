# dev-platform 유지보수 가이드

플랫폼 자체를 고치고, 도구를 올리고, 새 저장소를 붙이는 절차다. 일상 사용법은 [MANUAL.ko.md](MANUAL.ko.md)에 있다.

## 1. 구조 한눈에 보기

| 저장소 | 역할 |
| --- | --- |
| `ghdtmdwns133/dev-platform` | Copier 템플릿, 재사용 워크플로, composite action, Unity용 CLI, 문서의 정본. 소비 저장소는 `@v1`로 참조한다. |
| `ghdtmdwns133/project-delta` | private Unity 프로젝트. `unity.yml`을 self-hosted 러너로 호출하고, `ci.yml`을 `run-tests: false`로 호출하는 `platform-check` 작업도 둔다. |
| `<새 저장소>` | Copier 템플릿으로 생성한 소비 저장소. 비-Unity는 `ci.yml`+`security.yml`, Unity는 `unity.yml`+`security.yml`을 호출한다. |

`dev-platform` 디렉터리의 책임은 다음과 같다.

| 경로 | 책임 |
| --- | --- |
| `copier.yml`, `template/` | 새 저장소를 렌더링하는 pure-safe Copier 템플릿. `_tasks` 없음. |
| `scripts/bootstrap_repo.py` | 새 저장소 생성과 기존 저장소 설정 재조정의 단일 진입점. Copier 렌더링, `gh repo create`, 설정·라벨·ruleset·시크릿을 처리한다. |
| `default.json`, `renovate.json` | Renovate 공유 프리셋과 dev-platform 자체의 온보딩 설정(프리셋 상속). |
| `mise.toml` | 플랫폼 자체의 도구 핀과 `check`, `lint`, `test` 태스크. |
| `actions/` | `security-scan`, `notify`, `unity-cloud-build` 등 재사용 composite action. |
| `.github/workflows/` | 재사용 `ci.yml`, `security.yml`, `unity.yml`, `release.yml`, `nightly.yml`과 자체 검증 `self-test.yml`. |
| `cli/src/devplatform/` | Unity 전용 `devctl`. `config.py`, `integrity.py`, `unity.py`, `verify.py`, `report.py`, `procs.py`, `cloudbuild.py`, `cli.py` |
| `docs/` | 사용·채택·운영 문서와 `docs/research/` 증거 노트 |

호출 방향은 한 방향이다.

```mermaid
flowchart LR
    C[소비 저장소 caller<br/>ci.yml / unity.yml] --> R[재사용 워크플로<br/>ci.yml / unity.yml@v1]
    R --> M[비-Unity: mise run check|test]
    R --> D[Unity: devctl]
    R --> S[security.yml → security-scan]
```

## 2. 핵심 원칙

- **단일 인터페이스.** 비-Unity는 `mise run check`와 `mise run test`가 로컬과 CI의 유일한 명령이다. Unity는 `devctl`이 그 역할을 한다. `devctl verify`는 `unity`와 `unity-assets` 프로필만 받는다. `versions.json`, `devctl init`, `devctl hooks`, `devctl versions`는 없다.
- **템플릿 전파.** 새 저장소는 `scripts/bootstrap_repo.py`로 만들고 `.copier-answers.yml`을 남긴다. 이후 변경은 `copier update`로 적용한다. 템플릿은 `_tasks`·Jinja 확장·마이그레이션을 쓰지 않는 pure-safe 형태로 유지한다. 그래야 호스티드 Renovate가 스크립트 권한 없이 Copier 업데이트 PR을 만들 수 있다.
- **버전 핀.** 생성 저장소의 도구 버전은 각 `mise.toml`의 `[tools]`에 있다. 플랫폼 자체 도구는 루트 `mise.toml`에 있고, GitHub Actions는 40자 SHA와 `# v4` 태그 주석으로 고정한다. `zizmor.yml`은 `ghdtmdwns133/*`만 태그 참조를 허용하고 나머지는 `hash-pin`을 요구한다.
- **태그 두 종류.** `v1`은 caller의 `uses:`/`platform_ref`가 쓰는 이동 태그다. `v1.N.0`은 Copier와 Renovate가 쓰는 PEP 440 불변 태그다. 태그가 가리키는 SHA는 [ADOPTION.md](ADOPTION.md)의 표에 기록한다.
- **스택 고정.** 지원 스택은 `python`, `typescript`, `dotnet`, `unity`와 스택 비종속 `other`뿐이다. 새 언어·엔진 지원은 이 저장소의 범위가 아니다.

## 3. 일상 유지보수 절차

1. `main`에서 브랜치를 만들고 `template/`, `copier.yml`, `default.json`, 워크플로, `cli/`를 고친다.
2. 플랫폼 자체 검사를 로컬에서 돌린다.

   ```bash
   cd C:/dev/dev-platform
   mise trust && mise install
   mise run check          # depends on lint and test
   # 또는 개별 실행: mise run lint, mise run test
   ```

3. push하고 `self-test.yml`이 초록인지 확인한다. CLI, 템플릿 렌더링, devcontainer, 보안, 워크플로 린트 작업이 있다. 실패한 작업만 본다.

   ```bash
   gh run list --workflow self-test.yml -L 3
   gh run view <run-id> --log-failed
   ```

4. `main`이 초록이면 새 불변 태그를 만들고 `v1`을 옮긴다. 초록이 아닌 커밋으로는 옮기지 않는다.

   ```bash
   git switch main && git pull --ff-only
   git tag -a v1.1.0 -m "platform v1.1.0" main
   git push origin v1.1.0
   git tag -f -a v1 -m "platform v1: v1.1.0" main
   git push origin refs/tags/v1 --force
   git rev-list -n 1 v1
   git rev-list -n 1 v1.1.0
   ```

   두 SHA를 [ADOPTION.md](ADOPTION.md)의 태그 표에 기록한다. `v1`은 항상 최신 호환 템플릿/워크플로를 가리키고, `v1.N.0`은 절대 이동하지 않는다.

5. 소비 저장소를 다시 돌려 새 태그를 소비했는지 확인한다.

   ```bash
   gh workflow run ci.yml -R ghdtmdwns133/<repo>
   gh workflow run ci.yml -R ghdtmdwns133/project-delta
   gh run list -R ghdtmdwns133/project-delta -L 3
   ```

**`v2`를 만드는 기준.** 다음 중 하나라도 해당하면 `v1`을 옮기지 않고 `v2`를 새로 만든 뒤 소비 저장소를 순차 이전한다.

- 재사용 워크플로 입력 이름·기본값·시크릿 이름이 바뀐다.
- `copier.yml` 질문 이름이나 기본값이 바뀐다(기존 답변 파일이 깨진다).
- 태스크 이름(`check`, `test`, `build`)이나 산출물 경로(`coverage/`, `dist/`)가 바뀐다.
- `.devplatform/config.json` 키가 바뀐다. 알 수 없는 키는 거부되므로 구버전 config가 깨진다.
- 종료 코드 의미, `summary.json` 필드, Unity 아티팩트 이름이 바뀐다.
- `devctl` 서브커맨드나 필수 인자가 바뀐다.

`v2`를 만든 뒤에도 `v1`은 마지막 호환 커밋에 그대로 둔다. 소비 저장소가 옮겨진 것을 확인한 다음에만 정리한다.

## 4. 도구·액션 업데이트

**Renovate.** `default.json`이 공유 정책이다. `config:recommended`, `platformAutomerge`, minor/patch/digest 자동 병합, GitHub Actions digest 고정, 주간 lock-file 유지보수, Copier 업데이트 그룹화가 들어 있다. 생성 저장소의 `renovate.json`은 이 프리셋을 상속한다. Renovate는 다음을 갱신한다.

- `mise.toml`의 `[tools]` 핀
- 워크플로·action의 SHA와 태그 주석
- `pyproject.toml`, `package.json`, `*.csproj`, lock 파일
- `.copier-answers.yml`의 템플릿 버전(앱 설치 + `v1.N.0` 태그가 있을 때)

호스티드 Renovate 앱 설치는 사용자 조치다. 사용자가 2026-10-24에 모든 저장소에 설치했다고 확인했지만, 실제 봇 실행/PR 증거는 아직 검증 전이므로 `gh search prs --owner ghdtmdwns133 --app renovate`로 확인하기 전에는 활성으로 단정하지 않는다. Dependabot 버전 업데이트 설정은 제거됐고 취약점 알림은 유지된다. 별도 auto-merge 워크플로도 없다.

**action SHA.** 태그를 SHA로 해석해 넣고, 주석의 태그를 함께 갱신한다.

```bash
gh api repos/actions/checkout/git/ref/tags/v4 --jq .object.sha
gh api repos/actions/checkout/git/tags/<sha> --jq .object.sha   # annotated 태그면 한 번 더
```

**보안 도구.** trivy·gitleaks·zizmor·actionlint의 핀은 `actions/security-scan/action.yml`, 루트 `mise.toml`, `self-test.yml`에 있다. Renovate가 갱신하지만, 버전을 직접 올리면 세 위치를 함께 맞춘다. `devctl versions` 같은 자체 검사 명령은 없다.

**Unity 에디터.** 다음을 함께 바꾼다.

- `project-delta/.devplatform/config.json`의 `unity.version`과 `ProjectSettings/ProjectVersion.txt`
- `template/`의 Unity `.devplatform/config.json` 기본값
- UBA를 쓴다면 대시보드 build target의 에디터 버전
- `cli`의 기본 버전과 버전 문자열을 단정하는 테스트

`unity.yml`은 이제 `unity-version` 입력을 받지 않는다. 에디터 버전은 소비 저장소의 `.devplatform/config.json`이 정본이다.

**Python/Node/.NET.** 생성 저장소는 각 `mise.toml`의 `[tools]`가 정본이다. 템플릿의 `global.json`, devcontainer 이미지 태그, `packageManager`/`engines`도 같은 버전대를 가리켜야 한다. 플랫폼 자체는 루트 `mise.toml`을 따른다.

**pre-commit 핀.** 템플릿의 `[tools]`는 `"pypi:pre-commit" = { version = "4.7.0", python = "3.12" }`를 쓴다. 짧은 `pre-commit` 이름은 mise가 standalone `pre-commit-4.7.0.pyz` backend로 해석해 `python` 옵션을 무시하고, .NET devcontainer의 ambient Python에서 `ModuleNotFoundError: No module named 'shutil'`를 낼 수 있다. `python = "3.12"`만 추가하는 것으로는 해결되지 않으며, `pypi:` 접두사로 PyPI/uv backend를 강제해야 한다.

## 5. 템플릿 변경

- `copier.yml`의 질문 이름과 기본값은 `.copier-answers.yml`과 `copier update`의 계약이다. 이름을 바꾸면 기존 저장소의 답변 파일이 깨지므로 `v2` 대상이다.
- `template/`은 스택 조건에 따라 파일을 포함한다. 공통 파일과 스택별 파일을 한 디렉터리에서 관리하고, 스택별 분기는 Copier 조건으로 처리한다.
- `_tasks`를 추가하지 않는다. 부트스트랩은 `scripts/bootstrap_repo.py`가 담당한다. 이 분리가 호스티드 Renovate의 스크립트 권한 문제를 피한다.
- 변경 후 임시 디렉터리에 렌더링해 파일 목록과 미치환 토큰을 확인한다.

  ```bash
  cd C:/dev/dev-platform
  uv run --script scripts/bootstrap_repo.py \
    --template python --name template-check --dest C:/dev/.tmp-template-check \
    --dry-run
  ```

  `--dry-run`은 렌더링하지 않고 계획만 보여 준다. 실제 렌더링 검증은 `self-test.yml`의 템플릿 작업이 한다. 손으로 렌더링하려면 `uvx copier copy . <dest>`를 쓰고, GitHub 설정은 별도로 적용한다.
- 기존 저장소의 충돌은 `copier update`가 표시한다. `.copier-answers.yml`이 없는 저장소에는 `copier update`를 쓰지 않는다. provenance를 꾸며내지 않는다.
- 새 스택을 추가하지 않는다. `other`는 스택 비종속 계층일 뿐이며 테스트 태스크가 없다.

## 6. 새 저장소에 붙이기

**새 저장소.** 한 명령으로 만든다.

```bash
cd C:/dev/dev-platform
uv run --script scripts/bootstrap_repo.py \
  --template python --name my-service --dest C:/dev/my-service
```

`--dry-run`으로 계획을 먼저 보고, `--owner`, `--visibility`, `--platform-ref`, `--min-coverage`, `--template-source`(기본 `https://github.com/<owner>/dev-platform`), `--template-ref`(기본 최신 PEP 440 태그), `--local`(개발/self-test용), `--create-repo`/`--no-create-repo`, `--enable-codecov`/`--no-enable-codecov`, `--enable-sentry`/`--no-enable-sentry`를 필요할 때 넘긴다. bootstrap은 git 초기화·첫 커밋, `mise trust`/`mise install`, `mise run prepare`(정의된 경우), pre-commit 훅 설치, `gh repo create`(없을 때만), retention 14일, workflow 권한, auto-merge, branch 삭제, 취약점 알림, 라벨, `platform-gates` ruleset, 가능한 경우 Codecov/Sentry 시크릿을 처리한다. 같은 명령을 다시 실행하면 설정을 재조정하고 훅도 다시 설치한다.

**기존 저장소.** `.copier-answers.yml`을 새로 만들지 않는다. 다음을 직접 넣는다.

1. 해당 스택의 `mise.toml`과 `.pre-commit-config.yaml`.
2. Unity라면 `.devplatform/config.json`.
3. caller 워크플로. 비-Unity는 `ci.yml`+`security.yml`, Unity는 `unity.yml`+`security.yml`.
4. `renovate.json`과 release-please 설정.
5. `.github/rulesets/platform-gates.json`.

설정과 ruleset은 같은 bootstrap을 `--root`로 실행해 재조정한다.

```bash
uv run --script scripts/bootstrap_repo.py \
  --root C:/dev/project-delta --owner ghdtmdwns133 \
  --name project-delta --visibility private --dry-run
```

`--root` 모드는 `gh repo create`를 건너뛰고, `mise trust`/`mise install`, `mise run prepare`(정의된 경우), pre-commit 훅 설치를 수행하며, `<root>/.github/rulesets/platform-gates.json`이 있으면 ruleset을 갱신하고 없으면 notice만 남긴다. 기존 원격 저장소가 있으면 로컬 `origin`이 정확히 `<owner>/<name>`을 가리켜야 하며, 다르면 exit 1로 중단한다. `.copier-answers.yml`은 쓰지 않는다.

**필수 검사.** 첫 초록 실행 뒤 실제 이름을 확인한다.

```bash
gh api repos/ghdtmdwns133/<repo>/commits/main/check-runs --jq '[.check_runs[].name] | unique'
```

- `python`, `typescript`, `dotnet`: `platform-verify / check`, `platform-verify / test`, `platform-security / scan`
- `other`: `platform-verify / check`, `platform-security / scan` (테스트 태스크 없음)
- public Unity(`unity-runner: none`): `platform-verify / integrity`, `platform-security / scan`
- private Unity(`unity-runner: self-hosted`): `platform-verify / integrity`, `platform-verify / tests`, `platform-security / scan`; UBA 모드면 `platform-verify / cloud-build` 추가
- `project-delta`: 위 private Unity 검사에 `platform-check / check`를 더한다(`ci.yml`을 `run-tests: false`로 호출).

Unity 저장소에는 `platform-verify / check`를 넣지 않는다. 그 작업은 존재하지 않는다. `mise run check`를 CI에서도 쓰려면 `platform-check` caller를 따로 두고 `platform-check / check`를 넣는다. `notify`와 평소 건너뛰는 build 작업도 넣지 않는다. ruleset JSON과 `gh api` 명령은 [ADOPTION.md](ADOPTION.md)에 있다. 같은 이름의 ruleset이 있으면 `PUT`으로 갱신한다.

**시크릿.** Doppler의 `<repo>/ci` 동기화 또는 `gh secret set <NAME> -R ghdtmdwns133/<repo>`를 쓴다. 값은 저장소에 커밋하지 않는다. 새 저장소는 Doppler 동기화를 새로 만들어야 한다. [SECRETS.md](SECRETS.md).

## 7. Unity 운영

**러너.** `project-delta` 전용 repository-level 러너를 `C:/ghr/runner`에 두고 work folder는 `C:/ghr/work`다. 등록 레이블은 `self-hosted`, `Windows`, `X64`, `unity`이고 job은 `runs-on: [self-hosted, windows, unity]`로 잡는다(레이블 비교는 대소문자를 구분하지 않는다). named-user 라이선스를 쓰려면 서비스가 아니라 로그온 사용자로 실행하고, 자동 시작은 Startup 폴더의 `github-runner-project-delta.cmd`가 맡는다(관리자 권한이 필요한 `schtasks`는 쓰지 않는다). 공개 저장소에는 절대 등록하지 않는다.

```bash
gh api -X POST repos/ghdtmdwns133/project-delta/actions/runners/remove-token --jq .token
C:\ghr\runner\config.cmd remove --token <token>
```

러너는 새 버전이 나오면 기본 설정에서 스스로 업데이트하고, 실행 중인 job이 끝난 뒤 적용한다. 적용 여부는 `C:/ghr/runner/_diag/` 로그에서 확인한다.

self-hosted 작업의 checkout은 `clean: false`라서 work folder의 `Library/`가 남고, 다음 실행이 증분 임포트로 빨라진다. `Library/`를 지우는 경우는 Unity 버전을 올렸거나 손상됐다고 판단될 때뿐이고, 그 다음 실행은 전체 재임포트로 느려진다.

**external GUID 베이스라인.** 패키지를 추가·제거했거나 Unity를 올려 `Library/PackageCache`가 바뀌면 갱신한다. `--write-baseline`은 `Assets`, `Packages`, `Library/PackageCache`의 `.meta`를 인덱싱하고, 이미 풀리지 않는 참조는 `"unresolved"`로 동결한다. `Library/PackageCache`가 없으면 exit 2로 거부한다.

```bash
uv run --project C:/dev/dev-platform/cli devctl unity integrity --write-baseline
```

**무결성 규칙.** 검사 순서와 문구는 `cli/src/devplatform/integrity.py`에 있다. 경로 목록은 `REQUIRED_PATHS`, 참조 확장자는 `REFERENCE_SUFFIXES`, 씬·오브젝트 검사는 `_check_scene()`·`_check_required_objects()`, 스크립트 위치는 `_check_scripts()`, 메타/GUID는 `_check_metas()`, 참조는 `_check_references()`다. `::error::` 문구는 CI와 테스트가 소비하므로 바꾸면 `cli/tests/test_integrity.py`를 같이 고친다. 규칙을 저장소별로 바꾸려면 config 키(`requiredObjects`, `allowedScriptRoots`, `templateScripts`, `testPlatforms`)를 우선 사용한다. 과제 보호를 위해 `Assets/MyScripts/`, `Assets/OtherScripts/` 밖의 새 스크립트와 템플릿 스크립트 삭제는 실패로 둔다.

**UBA.** 대시보드에서 GitHub 저장소를 연결하고 Windows build target을 만든 뒤 org id, project id, target id, API key를 시크릿 `UNITY_BUILD_API_KEY`, `UNITY_BUILD_ORG_ID`, `UNITY_BUILD_PROJECT_ID`로 넣는다. `unity.cloudBuild.target`과 `unity.cloudBuild.timeoutMinutes`(기본 90)로 기본값을 정한다. 무료 한도는 Windows 200분/월이고, 소진되면 결제 수단이 없는 한 빌드가 멈춘다. [UNITY-CI.md](UNITY-CI.md).

## 8. 고장 대응 플레이북

**self-test 실패 순서.** `cli`가 깨지면 나머지는 의미가 없으므로 먼저 본다. 다음은 템플릿 렌더링, devcontainer, 보안, 워크플로 린트 순으로 확인한다. 템플릿 작업은 Copier로 임시 디렉터리에 렌더링하고 `mise run check`/`test`를 돌리므로, 실패는 대개 조건부 파일 누락이나 잘못된 Copier 질문이다. devcontainer 실패는 이미지 태그나 도구 부재, workflow-lint는 새 action의 SHA 고정 누락이 흔한 원인이다.

**CI 실패 로그.** 실패한 단계만 보려면 `gh run view <run-id> --log-failed`. 비-Unity는 `coverage` 아티팩트를, Unity는 `reports-unity-assets`(무결성) 또는 UBA/build 아티팩트를 내려받아 로컬 재현 없이도 원인을 볼 수 있다.

```bash
gh run download <run-id> -n reports-unity-assets -D artifacts/ci-reports
```

**태그를 잘못 옮겼을 때.** `v1`만 이전 커밋으로 되돌린다. `v1.N.0`은 이동하지 않는다.

```bash
git tag -f -a v1 -m "platform v1: rollback" <previous-sha>
git push origin refs/tags/v1 --force
git rev-list -n 1 v1
```

**체크 이름이 바뀌어 PR이 막힐 때.** 작업 이름을 바꿨다면 ruleset의 `required_status_checks`가 옛 이름을 가리킨다. 실제 이름을 다시 확인해 ruleset을 `PUT`으로 갱신한다.

**Renovate PR이 없을 때.** 사용자가 2026-10-24에 앱을 모든 저장소에 설치했다고 확인했지만, 실제 봇 실행 증거는 아직 검증 전이다. `https://github.com/apps/renovate`에서 저장소 접근을 확인하고, `gh search prs --owner ghdtmdwns133 --app renovate`로 흔적을 본다. 접근이 없으면 어떤 설정도 PR을 만들지 않는다. Copier 업데이트는 앱 접근, `v1.N.0` 태그, `.copier-answers.yml`이 모두 있어야 한다.

**릴리스는 있는데 자산이 없을 때.** 자산 빌드만 실패한 경우(PC 꺼짐, 러너 오프라인)는 `rebuild-tag`로 복구한다. release-please·자동 병합·대기 단계를 건너뛰고, 해당 태그를 기준으로 빌드한 뒤 `gh release upload --clobber`로 기존 자산을 교체한다.

```bash
gh workflow run release.yml -R ghdtmdwns133/project-delta --ref main \
  -f rebuild-tag=project-delta-v0.1.0
```

## 9. 알려진 제약

- **Unity 학생 라이선스.** 보유 라이선스는 named-user Student라 시리얼도 `.ulf`도 없다. GameCI v4가 지원하는 활성화 방식이 아니고, Unity Editor Software Terms §2.8은 서드파티가 클라우드/원격 서버에서 에디터를 실행하는 것을 금지한다. 그래서 `unity.yml`에는 `gameci` 옵션과 GameCI 작업·라이선스 시크릿이 없으며, GitHub 호스팅 러너에서 Unity를 돌리는 경로는 제공하지 않는다.
- **gitleaks 전체 히스토리.** `actions/security-scan`은 전체 히스토리를 스캔한다. 과거 커밋의 비밀도 계속 잡히며, 비밀을 교체해도 히스토리에 남아 있으면 빨간색이 유지된다. 브랜치 삭제는 그 커밋이 기본 브랜치 히스토리에 없을 때만 효과가 있다.
- **`GITHUB_TOKEN` PR.** `GITHUB_TOKEN`으로 만든 PR은 `pull_request` 워크플로를 트리거하지 않는다. release-please의 Release PR이 그렇기 때문에 `release.yml`이 CI를 대신 dispatch하고, `action_required` 실행을 승인한 뒤 병합을 기다린다.
- **docs-only push.** caller가 `paths-ignore: [docs/**, "**/*.md"]`를 두므로 문서만 바꾸면 CI가 생기지 않을 수 있다. 필수 검사가 있는 저장소에서는 소유자 bypass로 병합하거나 코드 변경을 섞는다.
- **Windows 전용 Unity 실행.** `devctl`의 에디터 탐색은 `unity.editorPath`, `UNITY_EDITOR_PATH`, `C:/Program Files/Unity/Hub/Editor/<version>/Editor/Unity.exe` 순서다. PlayMode를 켜면 창과 데스크톱 입력이 필요하다. `unity-assets`만 에디터 없이 어디서나 돈다. 현재 `project-delta`는 EditMode만 켜져 있다.
- **self-hosted 러너의 `bash`.** Windows self-hosted 러너에서 `bash`는 WSL bash로 해석된다. 그 러너에서 실행될 수 있는 단계에는 `shell: bash`를 추가하지 말고 `pwsh`를 쓰거나 `shell`을 생략해 러너 기본값을 쓴다.
- **외부 인증.** Renovate, Codecov, CodeScene, Sentry, Doppler의 계정 연결과 토큰 발급은 사용자 조치다. 토큰과 앱 설치는 만료·철회·회전될 수 있고, Sentry Education은 1년 플랜이다. 자동화가 연결됐다고 가정하지 않는다.
- **CodeScene private 분석.** 학생 플랜의 private 저장소 분석 여부는 공개 문서로 확인되지 않았다. 안 되면 public 저장소부터 연결하고 `project-delta`는 "미연결"로 보고한다.
- **Azure 미사용.** 검증과 빌드는 GitHub 호스팅 러너, Unity용 self-hosted PC, Unity Build Automation만 쓴다. Azure 리소스는 만들지 않는다.
- **Copilot 미사용.** 파이프라인은 Copilot cloud agent를 쓰지 않는다. 실패 이슈에는 로컬 재현 명령만 남는다.
