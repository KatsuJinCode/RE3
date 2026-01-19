@echo off
REM RE3 CLI for Windows
REM Usage: re3 <command>

setlocal
set REPO=KatsuJinCode/RE3

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="--help" goto help
if "%1"=="-h" goto help
if "%1"=="run" goto run
if "%1"=="run-all" goto runall
if "%1"=="status" goto status
if "%1"=="setup" goto setup
if "%1"=="check" goto check
if "%1"=="request" goto request
if "%1"=="approve" goto approve
if "%1"=="pull-data" goto pulldata

echo Unknown command: %1
echo Run 're3 help' for usage.
exit /b 1

:help
echo RE3 - Collaborative LLM Testing
echo.
echo Commands:
echo   run         Run one experiment slice
echo   run-all     Run until all slices complete
echo   status      Show experiment progress
echo   request     Request collaborator access
echo   approve     (Owner only) Approve a collaborator
echo   pull-data   (Owner only) Pull data files from a PR
echo.
echo Setup:
echo   setup       Install dependencies
echo   check       Check if everything is ready
exit /b 0

:run
python bootstrap.py run
exit /b %errorlevel%

:runall
python bootstrap.py run-all
exit /b %errorlevel%

:status
python bootstrap.py status
echo.
python harness/progress.py status 2>nul
exit /b 0

:setup
python bootstrap.py setup
exit /b %errorlevel%

:check
python bootstrap.py status
exit /b %errorlevel%

:request
echo === Request Collaborator Access ===
echo.
for /f "tokens=*" %%i in ('gh api user --jq ".login" 2^>nul') do set GH_USER=%%i
if "%GH_USER%"=="" (
    echo Error: Not logged into GitHub CLI ^(gh^).
    echo Run: gh auth login
    exit /b 1
)
echo Your GitHub username: %GH_USER%
echo.
echo This will create an issue requesting collaborator access.
set /p CONFIRM=Continue? [y/N]
if /i not "%CONFIRM%"=="y" (
    echo Cancelled.
    exit /b 0
)
gh issue create --repo %REPO% --title "Collaborator Request: %GH_USER%" --body "**Username:** %GH_USER%||I'd like to help run RE3 experiments.||---||*To approve, repo owner runs:* `re3 approve %GH_USER%`"
echo.
echo Request submitted! The repo owner will be notified.
exit /b 0

:approve
if "%2"=="" (
    echo Usage: re3 approve ^<github-username^>
    echo.
    echo Pending requests:
    gh issue list --repo %REPO% --search "Collaborator Request" --state open
    exit /b 1
)
echo Adding %2 as collaborator to %REPO%...
gh api --method PUT repos/%REPO%/collaborators/%2 -f permission=push
echo Done! %2 can now push to the repo.
exit /b 0

:pulldata
if "%2"=="" (
    echo Usage: re3 pull-data ^<PR_NUMBER^>
    echo.
    echo Open PRs with data:
    gh pr list --repo %REPO% --search "Complete" --state open
    exit /b 1
)
echo === Pull Data from PR #%2 ===
echo.

REM Get PR info
for /f "tokens=*" %%i in ('gh pr view %2 --repo %REPO% --json title --jq ".title" 2^>nul') do set PR_TITLE=%%i
for /f "tokens=*" %%i in ('gh pr view %2 --repo %REPO% --json headRefName --jq ".headRefName" 2^>nul') do set HEAD_REF=%%i
for /f "tokens=*" %%i in ('gh pr view %2 --repo %REPO% --json headRepositoryOwner --jq ".headRepositoryOwner.login" 2^>nul') do set HEAD_OWNER=%%i
for /f "tokens=*" %%i in ('gh pr view %2 --repo %REPO% --json headRepository --jq ".headRepository.name" 2^>nul') do set HEAD_REPO=%%i

if "%HEAD_REF%"=="" (
    echo Error: Could not fetch PR #%2
    exit /b 1
)

echo PR: %PR_TITLE%
echo From: %HEAD_OWNER%/%HEAD_REPO% @ %HEAD_REF%
echo.

REM Add remote if needed
set REMOTE_NAME=contrib-%HEAD_OWNER%
git remote get-url %REMOTE_NAME% >nul 2>&1 || git remote add %REMOTE_NAME% https://github.com/%HEAD_OWNER%/%HEAD_REPO%.git

REM Fetch and checkout data files
echo Fetching %HEAD_REF%...
git fetch %REMOTE_NAME% %HEAD_REF%

echo Extracting data files...
git checkout %REMOTE_NAME%/%HEAD_REF% -- data/runs/ 2>nul
git checkout %REMOTE_NAME%/%HEAD_REF% -- data/summaries/ 2>nul
git checkout %REMOTE_NAME%/%HEAD_REF% -- progress.json 2>nul

REM Validate JSONL
echo Validating data...
python -c "import sys,json,glob; files=glob.glob('data/runs/*.jsonl'); bad=[f for f in files if any(not l.strip() or json.loads(l) for l in open(f))]; sys.exit(1) if bad else print('  OK')" 2>nul || (
    echo   Validation failed
    git checkout HEAD -- data/ progress.json
    exit /b 1
)

REM Commit
git add data/runs/ data/summaries/ progress.json
git commit -m "Data from PR #%2: %PR_TITLE%"

echo.
echo Data merged successfully!
echo.

set /p CLOSE_PR=Close PR #%2? [Y/n]
if /i not "%CLOSE_PR%"=="n" (
    gh pr close %2 --repo %REPO% --comment "Data merged via `re3 pull-data`. Thank you!"
    echo PR closed.
)
exit /b 0
