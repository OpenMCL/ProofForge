# ProofForge

中央大學數學相關課程用的證明作業繳交與批改平台（Django）。

- **教授**：建立課程、管理學生名單與助教、出作業與題目
- **學生**：以 Markdown 撰寫證明（可含 LaTeX、Lean 4），邊寫邊自動儲存
- **教授／助教**：作業截止後批改、給分、寫總評與行內評論
- 所有人以 NCU Portal（OAuth）登入

## 設定

所有設定都來自環境變數，`settings.py` 會自動載入專案根目錄的 `.env`。先複製範本：

```bash
cp .env.example .env
```

每個變數的用途寫在 `.env.example` 裡。預設 `DJANGO_DEBUG=1`（開發模式）：使用假的 OAuth，在授權頁輸入任意學號即可登入，並開放 `/admin/`。

## 開發

### 用 Docker（Postgres）

```bash
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

打開 http://127.0.0.1:8000/ 。程式碼以 volume 掛進容器，存檔後 runserver 會自動重新載入。Postgres 的 5432 port 也會開在本機，方便用資料庫工具連線。

執行管理指令：

```bash
docker compose -f compose.yaml -f compose.dev.yaml exec web python manage.py <指令>
```

### 不用 Docker（venv + SQLite）

`.env` 的 `DATABASE_URL` 留空時，使用專案根目錄的 `db.sqlite3`。

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Windows（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

## 第一次使用

1. 建立後台管理員：`python manage.py createsuperuser`，登入 http://127.0.0.1:8000/admin/
2. 用要當教授的學號登入網站一次（建立帳號），再到後台 **Profiles** 勾選該帳號的 **Can create course**
3. 教授在首頁建立課程，然後在課程頁：
   - **學生名單**：上傳 CSV（欄位 `student_id`，`name` 選填），或在名單表格最後一列逐筆加入
   - **新增助教**：輸入學號
4. 學生與助教不需要事先登入；他們第一次以 NCU Portal 登入時，會依學號自動對應到名單

## 測試

```bash
.venv/bin/python manage.py test
```

在 Postgres 上跑（與正式環境相同的資料庫）：

```bash
docker compose -f compose.yaml -f compose.dev.yaml run --rm web python manage.py test
```

## 正式部署

正式環境以 Docker 執行：gunicorn 提供網頁、WhiteNoise 提供靜態檔、Postgres 存資料。HTTPS 由前面的 reverse proxy 負責，容器只開 HTTP 8000。

1. 在伺服器上建立 `.env`（從 `.env.example` 複製），設定下列變數；`DJANGO_DEBUG` 不為 `1` 時，缺少任何一項都會拒絕啟動：

   | 變數 | 說明 |
   |---|---|
   | `DJANGO_SECRET_KEY` | 長隨機字串 |
   | `DJANGO_ALLOWED_HOSTS` | 網站網域，逗號分隔 |
   | `POSTGRES_PASSWORD` | 資料庫密碼（長隨機字串） |
   | `OAUTH_PROVIDER_CLASS` | `accounts.ncu_provider.NCUPortalProvider` |
   | `OAUTH_REDIRECT_URI` | 與 NCU Portal 註冊的完全一致，必須是 https |
   | `NCU_OAUTH_CLIENT_ID`、`NCU_OAUTH_CLIENT_SECRET` | NCU Portal 核發的憑證 |

   `DATABASE_URL` 不用填，`compose.yaml` 會自動指向 db 服務；要連外部資料庫時才設定。

2. 啟動：

   ```bash
   docker compose up -d --build
   ```

   容器啟動時會自動執行 `migrate` 與 `collectstatic`。

3. Reverse proxy 必須轉送：
   - `X-Forwarded-Proto: https`：否則網站會不斷把請求轉到 https，造成無限轉址
   - 原始的 `Host` header：必須在 `DJANGO_ALLOWED_HOSTS` 裡，CSRF 檢查也依賴它

其他：

- 健康檢查：`/healthz/`
- `/admin/` 預設關閉；需要時設 `DJANGO_ENABLE_ADMIN=1` 並重新啟動
- 建立管理員：`docker compose exec web python manage.py createsuperuser`
- 備份資料庫：`docker compose exec db pg_dump -U proofforge proofforge > backup.sql`
- 資料存在 Docker volume `pgdata`；`docker compose down` 不會刪除它，`docker compose down -v` 會

## 專案結構

| 路徑 | 內容 |
|---|---|
| `accounts/` | OAuth 登入、帳號建立、名單佔位帳號的認領 |
| `courses/` | 課程、學生名單、助教、作業、題目 |
| `submissions/` | 作答與自動儲存、批改、行內評論、回饋 |
| `core_health/` | `/healthz/` 與管理指令 |
| `templates/`、`static/` | 頁面與前端腳本 |
| `Dockerfile`、`compose*.yaml`、`docker/` | 容器設定 |
