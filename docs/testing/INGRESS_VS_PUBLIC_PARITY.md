# HA Ingress ↔ Public Website 功能對等檢測計劃
# Ingress / Public Parity Test Plan

> 目標：讓 **HA Ingress**（`/api/hassio_ingress/<token>/odoo`）能做到 **Public Website**
> （`https://<public_url>`）能做到的每一件事，並把做不到的部分明確化、分級、歸因。
>
> 本文件是**檢測計劃**，不是測試報告。第 11 節的 `G-xx` 是已對照現行 main 程式
> 確認的 add-on 層／結構層落差；其餘章節是待執行的檢測項目。
>
> 受測目標為 **測試機 .6**（Public origin `https://woowtech-odoo-test-6.woowtech.io`，
> DB `odoo_test`）。主機層的即時狀態不記錄於本文件，一律於執行前重跑第 2.3 節 P-Check。
>
> 相關文件：`docs/ADVERSARIAL_E2E_MATRIX.md`（發版守門）、
> `docs/testing/COMMERCIAL_PREDEPLOY.md`（商務流程雙面向）、
> `docs/plans/2026-09-05-odoo-developer-mode-delta-tdd.md`（開發者模式差集）。
> 三者是**流程縱向**，本文件是**能力橫向**；本文件的 `U-xx` 項目庫供三者共用。
> 要在 .6 上驗一個尚未 Release 的 branch，先依 `docs/testing/LOCAL_BUILD_ON_HOST.md`
> 建出本地 add-on。

---

## 1. 判定原則

### 1.1 對等（Parity）的定義

對同一個 DB、同一個使用者、同一筆記錄、同一個畫面，在兩個 surface 上：

1. **控制項集合相等**：可見且可用的控制項，其*語意身分*集合完全相同；
2. **語意結果相等**：逐一操作後，資料狀態轉移、導向目標、對話框內容相同；
3. **對外產出物相等**：畫面上/產出物內出現的任何 URL，兩邊指向同一個對外可達位址；
4. **無異常訊號**：無 `pageerror`、無 console error、無失敗請求、無非預期 HTTP ≥ 400。

> **控制項語意身分**沿用 `docs/plans/2026-09-05-odoo-developer-mode-delta-tdd.md`
> 的定義（scope + kind + origin + canonical target + role + 未翻譯語意名），
> 與 ingress 前綴、query、fragment、翻譯、DOM 順序無關。兩份文件共用同一組身分規則。

### 1.2 三種判定

| 判定 | 意義 | 處置 |
|---|---|---|
| `PARITY` | 四項條件全滿足 | 記錄後結案 |
| `GAP` | 任一條件不滿足，且不在白名單內 | 進落差登記，定嚴重度與根因 |
| `APPROVED-DIVERGENCE` | 命中第 3 節白名單 | **反向驗證**該分歧仍然存在；分歧消失也是失敗 |

### 1.3 嚴重度

| 級別 | 定義 |
|---|---|
| **Blocker** | 空白畫面／登入失敗／路由逃逸／DB 生命週期外洩／**ingress token 外洩**／資料遺失／5xx／WebSocket 中斷／對外 URL 產出錯誤 |
| **Important** | 單一控制項不可用／資產 4xx／console 例外／cookie 或導向不一致／複製・下載・上傳失敗 |
| **Minor** | 純外觀／版面差異，全部操作仍可完成 |

發版門檻：ingress 與 public 兩條路徑上 **0 Blocker、0 Important**，Minor 需登記。

### 1.4 結構性落差的處理

部分能力 ingress **原理上不可能**達成（見 `RC-10`、`RC-15`）。這類項目不標 `GAP`，
標 `STRUCTURAL`，並且**必須**在計劃中指定「由 public surface 承接」的替代路徑。
若某功能既無 ingress 實作也無 public 承接，才升級為 Blocker。
`STRUCTURAL` 就是 `CONTEXT.md` 的 **Structural gap**；給使用者看的清單在
`odoo18ce/DOCS.md`「What only the Public origin can do」，新判出的 `STRUCTURAL` 要一併補進去。

---

## 2. 受測基準與前置條件

### 2.1 兩個 surface 的定義

| | Ingress | Public |
|---|---|---|
| 入口 | `https://<ha-host>/api/hassio_ingress/<token>/odoo` | `https://<public_url>` |
| nginx 監聽 | `5691`（僅允許 `172.30.32.2`） | `8069`（`$http_host` 必須等於 public host，否則 `444`） |
| 身分前置 | 需先通過 HA 登入 | 無（Odoo 自身登入） |
| 渲染容器 | HA 前端的 **cross-origin iframe** | 瀏覽器頂層文件 |
| URL 改寫 | sub_filter + `<head>` runtime shim | **無任何改寫** |
| `X-Frame-Options` | 被 `proxy_hide_header` 移除 | 保留 Odoo 原值 |
| 上游壓縮 | `Accept-Encoding ""`（停用） | 保留 |
| 資產快取 | 強制 `no-store` | 保留 Odoo 原值 |

Public 是**基準組**，Ingress 是**待測組**。所有比對方向都是「ingress 是否達到 public」。

### 2.2 受測範圍

- **主機**：測試機 .6（add-on slug `1b7b4ce7_odoo18ce`，Public origin
  `https://woowtech-odoo-test-6.woowtech.io`）。這是一台實體機，以 SSH
  進入；**位址不記錄在本 repo**，向維運者取得。`.6` 是名字不是位址，
  它比當初取名時的網段活得久（主機於 2026-09-22 換過網段）
- **DB**：`odoo_test`
- **客戶端**：桌機 Chrome（Chromium 穩定版），1920×1080，**單一基準**
  - HA 手機 App WebView、行動版視窗、Safari／非 Chromium **本輪不納入**，
    列為已知未覆蓋風險（見 10.5）
- **目標安裝 app（13，測試機為全新安裝，執行前先裝回）**：`account`, `calendar`, `contacts`, `crm`, `hr`, `hr_skills`,
  `mail`, `mass_mailing`, `project`, `project_todo`, `purchase`, `stock`, `website`
- **計劃安裝 app（12）**：`sale_management`, `website_sale`, `point_of_sale`, 金流串接,
  `survey`, `im_livechat`, `event`, `mrp`, `hr_holidays`, `hr_expense`,
  `hr_attendance`／`hr_timesheet`, `hr_recruitment`

### 2.3 前置條件檢查（P-Check，未全過不得往下）

| ID | 前置條件 | 檢查指令 | 目前狀態 |
|---|---|---|---|
| `P-1` | `public_url` 已設定且為 https | `ha addons options 1b7b4ce7_odoo18ce` | 待跑 |
| `P-2` | 8069 對 public host 回應非 503／444 | `curl -sI https://<public_url>/web/login` | 待跑 |
| `P-3` | `web.base.url` = public 基底（https） | `psql -tAc "select value from ir_config_parameter where key='web.base.url'"` | 待跑 |
| `P-4` | `web.base.url.freeze` = `True` | 同上，key `web.base.url.freeze` | 待跑 |
| `P-5` | `website.domain` = public 基底 | `select domain from website` | 待跑 |
| `P-6` | 兩 surface 可用同一組 Odoo 帳號登入 | 人工 | 待跑 |
| `P-7` | 已建立 run marker 測試 fixture | 見 `COMMERCIAL_PREDEPLOY.md` Phase 0 | 待跑 |
| `P-8` | 本輪允許的破壞性等級已核准 | 人工 | 待跑 |

`P-3`／`P-4` 未達成前，**第 6 節 E 群組（對外產出物 URL）全部項目的結果都不可信**，
因為 Odoo 會在 admin 登入時把 `web.base.url` 覆寫成當次請求的基底。

---

## 3. 核准的刻意分歧白名單（不算落差）

以下差異是設計意圖，**測試要主動驗證它們仍然存在**；分歧消失視為安全迴歸。

| ID | 分歧 | Ingress | Public | 反向驗證方式 |
|---|---|---|---|---|
| `AD-1` | 資料庫管理 | 可用 | `/web/database/*` → **404** | 兩邊各打一次，斷言 404 |
| `AD-2` | XML-RPC DB 服務 | 可用 | `/xmlrpc/db`、`/xmlrpc/2/db` → **404** | 同上 |
| `AD-3` | JSON-RPC 策略 | 直通 | 經 `odoo-jsonrpc-filter`（8071）過濾 | `odoo18ce/tests/test_jsonrpc_filter.py` |
| `AD-4` | Host 守門 | 不適用 | 非預期 `Host` → **444** | 用錯誤 Host 打 8069 |
| `AD-5` | `X-Frame-Options` | 移除 | 保留 | 比對回應標頭 |
| `AD-6` | 匿名可達性 | 需 HA session | 完全匿名可達 | 無 HA cookie 打 ingress，須被擋 |
| `AD-7` | LAN 主機埠 | 8069／8072 發佈到 HA 主機，只有 `lan_networks` 內的來源拿到 **LAN tier**（含資料庫管理）；add-on 網段 `172.30.32.0/23`（含 HA 主機本身與 Cloudflare tunnel）一律不算 LAN | 同左 | 從 `lan_networks` 外的來源打 8069／8072 的 `/web/database/manager`，不得回 200（未設 `public_url` 回 503；已設時 Host 不符回 444、Host 相符回 404）；add-on 啟動自我檢查另外驗 tunnel 那一側（`DOCS.md`「Start-time self-check」） |
| `AD-8` | SEO 產出物的位址 | `robots.txt` 回 `Disallow: /`，`Sitemap:` 仍指向 `<PUBLIC_BASE>/sitemap.xml`；`sitemap.xml` 的 `<loc>` 跟著**請求位址**（HA 位址，且不帶 ingress 前綴） | `robots.txt` 沒有 `Disallow: /`（爬蟲進得來），`sitemap.xml` 的 `<loc>` 全在 `<PUBLIC_BASE>` | 兩邊各取一次 `robots.txt` 與 `sitemap.xml`，每一句都要成立：兩邊的 `sitemap.xml` 都回 200；ingress 的 `robots.txt` 同時有 `Disallow: /` 與 `Sitemap: <PUBLIC_BASE>/sitemap.xml`；ingress 的 `sitemap.xml` **不在** `<PUBLIC_BASE>`、且**不含 ingress 前綴**；public 的 `sitemap.xml` 全在 `<PUBLIC_BASE>`、`robots.txt` 沒有 `Disallow: /`。任一句不成立即 `GAP`——分歧消失也算（要回頭改本列），`website.domain` 空白（`P-5` 未過）使 `Disallow: /` 消失更算：那時沒有任何東西把爬蟲導開；sitemap 裡出現 ingress 前綴是憑證外洩，屬 **Blocker**。理由：Odoo 以請求的 URL root 組 sitemap、並按 (website, url_root) 快取，不讀 `website.domain`；而爬蟲根本到不了 ingress（需要 HA session，`AD-6`／`U-D7`），Odoo 自己也用 `Disallow: /` 把爬蟲導向 Canonical URL 的 sitemap。要「修」只能讓 nginx 改寫 XML 或讓守門模組覆寫 controller，ADR 0006 已否決這條路。分歧本身的嚴重度是 Minor；核准後記錄下來的 `severity` 是 `none`（`AD-6`／`U-B8` 的慣例），反向驗證失敗才是 `GAP`。見 #172 |

---

## 4. 分層模型

模組不是測試單位，**層**才是。任何模組都由下列層堆疊而成；
測試在 L0–L5 一次做完，L6 只處理無法被下層覆蓋的殘餘。

```
L6  模組特化行為        ← 只列殘餘，最小
L5  對外產出物 URL      ← 郵件／報表／分享／回呼（繞過所有前端 shim，最大盲區）
L4  前台 / Portal 原語  ← website layout、編輯器、portal 磁貼、表單提交
L3  Web Client 原語     ← 視圖、控制面板、widget、chatter、對話框、systray
L2  會話與身分          ← cookie、登入、逾時、權限、多分頁
L1  URL 與資產改寫      ← sub_filter、runtime shim、bundle、worker、websocket
L0  通道               ← nginx 監聽、header、壓縮、快取、緩衝、上限
```

**覆蓋推論規則**：若模組 M 只使用 L0–L5 已通過的原語集合，且未引入新的路由前綴，
則 M 的 ingress 對等性由下層保證，L6 僅需抽驗。
若 M 引入新路由前綴或新原語，**必須**新增對應的 `U-xx` 項目，不得直接宣告覆蓋。

---

## 5. 通用失效根因目錄（RC）

這是本計劃的核心。ingress 的落差不是「每個模組各有各的 bug」，而是下列 15 條根因
在不同模組重複發作。每個 `U-xx` 測試項目都必須標註它在偵測哪一條 `RC`。

| ID | 根因 | 機制 | 典型症狀 |
|---|---|---|---|
| `RC-1` | **路徑前綴遺失** | ingress 位於 `/api/hassio_ingress/<token>` 之下，任何根相對 URL（`/xxx`）會打到 HA 根 | 圖示破圖、資產 404、動作無反應、跳回 HA 首頁 |
| `RC-2` | **前綴重複** | shim 與 sub_filter 同時作用，token 被加兩次 | 路徑含兩段 token，404 |
| `RC-3` | **跨來源 iframe 能力限制** | ingress 是 cross-origin iframe，受 `Permissions-Policy` / `allow` 屬性與瀏覽器 iframe 規則約束 | 複製鈕無反應、全螢幕失敗、相機/麥克風被拒、下載被擋、彈窗被擋、快捷鍵被宿主吃掉 |
| `RC-4` | **Cookie 範圍與屬性** | `proxy_cookie_path / <token>/`、`Secure` 依 `X-Forwarded-Proto` 條件化、第三方 cookie 政策 | 登入後立刻被登出、多分頁 session 互踢、記住我失效 |
| `RC-5` | **回應標頭改寫** | 僅 ingress：移除 `X-Frame-Options`、`Accept-Encoding ""`、資產 `no-store`、`proxy_buffering off` | 首屏與重載明顯變慢、串流/長回應行為不同 |
| `RC-6` | **Service Worker 被停用** | shim 主動反註冊 `/odoo` scope 與 `/web/service-worker.js`，並偽造 `navigator.serviceWorker` | PWA 安裝、離線模式、背景同步、推播全失效 |
| `RC-7` | **Worker / SharedWorker 身分** | shim 包裝建構子；worker 名稱與 bundle URL 帶版本號 | 升級後沿用舊 worker、即時連線遺失、`UncaughtClientError` |
| `RC-8` | **WebSocket 端點與 Origin** | `/websocket` 需前綴；`Origin` 由 nginx 重寫；worker 內的 WS URL 只能靠資產改寫 | 「即時連線中斷」、訊息不即時、需手動重整 |
| `RC-9` | **伺服器端產生的絕對 URL** | `web.base.url` / `get_base_url()` / `url_for()` 在**伺服器端**組出完整 URL，**完全繞過前端 shim** | 分享連結、郵件連結、報表 QR、portal 存取連結全部錯誤或外洩 token |
| `RC-10` | **外部入站流量不可達** | 外部來源（匿名訪客、金流 notify、webhook、郵件追蹤）無 HA session，**原理上打不到 ingress** | 電商付款回不來、問卷外部填答不了、客服外嵌不了 |
| `RC-11` | **sub_filter 前綴白名單不完整** | 資產改寫只列舉了固定前綴清單；新模組帶來新前綴就漏 | 新裝 app 的資產/RPC 逃逸到 HA 根 |
| `RC-12` | **shim 未攔截的注入路徑** | shim 掛在 `fetch`／`XHR.open`／`history`／`setAttribute`（含 `xlink:href`）／`setAttributeNS`／若干 DOM 屬性 setter／`window.open`／`Worker`／`WebSocket`／`navigator.sendBeacon`／`EventSource`／`new Audio`／`HTMLMediaElement.src`／`HTMLSourceElement.src`；以標記插入的 HTML（`innerHTML`／`insertAdjacentHTML`／`outerHTML`）、`style` 屬性與動態 `<style>` 文字（含 CSS `@import`）**依決議不覆蓋**（ADR 0004 2026-09-28 附記，#169：HTML 編輯器與網站編輯器由這些路徑存回記錄內容，掛鉤會把帶 token 的 Ingress 前綴寫進資料庫） | 見 `U-A6`：covered 途徑逃逸＝shim 缺陷；accepted 途徑逃逸＝已決議，由該畫面自己的 Literal rewrite 處理（#158 已於 2026-09-28 完成；#170 網站編輯器 Blocks 面板縮圖亦於 2026-09-28 完成，見 `U-D2`：`style` 屬性的值會回寫資料庫，所以改在**繪製處**——Ingress 資產 location 上 OWL 樣板文字的一條 Shipped rewrite——而非在回應上）；**動作說明 HTML**（`ir.actions.act_window` 的 `help` 欄位，由 `/web/action/load` 的 JSON 回應送達、經 `markup()` 以 `innerHTML` 插入）已由 Ingress 監聽器上一個專屬 `location = /web/action/load` 覆蓋：它是 Ingress `location /` 的複本，另加 `href`／`src`／`action`／`data-src`／`srcset` 五個屬性的**跳脫引號**規則（`src=\"/` → `src=\"$safe_ingress_path/`），並在每條之前先寫一條 `$safe_ingress_path` 的同值規則以免重複加前綴（sub_filter 在同一位元組上以**書寫順序**決勝，先寫者勝）；Public 監聽器與其他 JSON 回應不受影響（ADR 0004 動作說明附記）。**另有兩條路由同樣送出 markup()'d 的 `help`，但刻意不納入**：`/web/action/run` 與 `/web/dataset/call_button/<model>/<method>` 回的是呼叫當下算出來的 action，其 `context` 會帶記錄內容當作精靈預設值（`marketing_card` 的 `action_share()` 即是：`context.default_body_arch` 含 `<img src="/web/image/card.campaign/…">`，使用者一存就寫進 `mailing.mailing`）；替它們加前綴等於把 Supervisor token 寫進資料庫，正是本決議要避免的事。經由這兩條路由顯示的 `help` 仍會逃逸，這是兩害相權後較輕的一邊。這條**不在 `U-A6` 的探測清單內**，`innerHTML` 探測仍記為 accepted：驗證它的是 Static tier 的 `test_ingress_action_help.py`，加上 2026-09-28 在測試主機上對本分支本地建置所跑的一對 Ingress 爬蟲（`docs/testing/evidence/2026-09-28-issue-158/`：拿掉該 `location` 的對照組在兩個問卷選單上各記 `route_escape`／`http_4xx_5xx`／`console_error` = 8，加回去後全為 0，四張圖回 200）；**兩面的 `PARITY` 判定仍欠**：本地 add-on 沒有 `public_url`，要等有 Release 的那一輪；媒體來源（`new Audio`、`HTMLMediaElement.src`、`HTMLSourceElement.src`）已於 2026-09-28 由 shim 包裝（#159，ADR 0004 媒體來源附記），並於 2026-09-29 加入 `U-A6` 探測清單成為一條 **covered** 途徑 `media`（#203）：一次探測同時走三個 setter、同指一個 probe path，任一 wrapper 回歸即記逃逸。2026-09-29 在 0.4.5 上重跑，`media` 有發出請求且未逃逸、`U-A6` 維持 `PARITY`（run `WOOW-PARITY-20260929T053445Z`，見 `docs/testing/evidence/2026-09-29-issue-203/ua6-media-checks.jsonl`）。此外亦有 Static tier 的 shim 契約測試（`test_ingress_media_sources.py`），與報到台（`ir.actions.client` 609）在爬蟲裡回到 `PARITY` |
| `RC-13` | **HA 宿主干擾** | HA 自身的登入逾時、授權框替換、鍵盤快捷鍵、主題、iframe 尺寸、Supervisor 請求上限與逾時 | 操作到一半 iframe 被換成授權框、快捷鍵無效、大檔上傳被截斷 |
| `RC-14` | **內容型別敏感改寫** | sub_filter 對 HTML／JSON／JS／CSS 規則不同；shim 僅注入 `text/html` | 改錯型別 → JSON 破損、預覽白畫面（v0.3.34/0.3.35 即此類） |
| `RC-15` | **深連結不可分享** | ingress URL 的路徑內含 token，換人／換裝置不通用，且外送即外洩。**那串 token 是 add-on 的 `ingress_token`**（每個已安裝 add-on 一份、重裝或還原備份才換），不是 per-user 的 session——per-user 的 session 是另一個 secret，走 `ingress_session` cookie，不出現在路徑裡（2026-10-01 由 #234 查證，見 ADR 0004 第三個 2026-10-01 附記）。貼給別人打不開是**那個 cookie** 擋的，不是路徑不同；路徑那串仍然是憑證，外送即外洩的判斷不變 | 書籤失效、貼給同事打不開、token 進入郵件與紀錄 |

---

## 6. 通用測試項目庫（U）

**用法**：每個受測畫面都跑同一份清單；模組層只宣告「本畫面使用哪些 `U` 項目」。
每項固定四欄：偵測的根因、測法、PASS 判定、適用層。

### A 群組 — 通道與 URL 改寫（L0/L1）

| ID | 項目 | RC | 測法 | PASS 判定 |
|---|---|---|---|---|
| `U-A1` | 無路由逃逸 | RC-1 | 錄製整段網路，取出所有請求路徑 | ingress 下**每一筆**同源請求路徑皆以 `/api/hassio_ingress/<token>` 開頭 |
| `U-A2` | 無前綴重複 | RC-2 | 同上 | 無任何路徑含兩段以上 token |
| `U-A3` | 資產全數 200 | RC-1/11 | 比對兩 surface 的資產請求集合與狀態碼 | ingress 無 4xx/5xx；集合與 public 相同（僅前綴差） |
| `U-A4` | 路由前綴白名單完整性 | RC-11 | 從已載入 bundle 抽出所有根相對字面量前綴，與 nginx 白名單求差集 | 差集為空；非空即列 `GAP` |
| `U-A5` | 內容型別改寫正確 | RC-14 | 對 HTML / JSON / JS / CSS 各抓一筆代表回應 | JSON 可被 `JSON.parse`；HTML 有且僅有一份 shim；JS/CSS 語法可解析 |
| `U-A6` | shim 注入途徑覆蓋稽核 | RC-12 | 在頁面上分兩組主動探測 `/web/static/parity-probe/<途徑>.png` 是否產生逃逸請求。**covered**（shim 必須加前綴，一律走 shim 掛鉤的 API，不走標記）：`navigator.sendBeacon('/…')`、`new EventSource('/…')`、以 `createElementNS` 建立的 `<use>` 分別以 `setAttribute("xlink:href")`、`setAttribute("href")`、`setAttributeNS()` 設定參照。**accepted**（依 #169 決議不覆蓋）：`innerHTML` 的 `<img src="/…">`（此途徑本身仍不由 shim 覆蓋；動作說明 HTML 走的是 #158 的單一路由 Literal rewrite，不改變本探測的判讀）、`insertAdjacentHTML` 的 `<svg><use href="/…">`、`style` 屬性的 `url(/…)`、動態 `<style>` 的 `url(/…)`、CSS `@import url(/…)`。`<meta http-equiv=refresh>` 不測：Odoo 18 於伺服器端轉向，且探測會把頁面導離受測畫面 | ingress 下 **covered** 途徑全部無逃逸，且 public 下沒有任何途徑離開原來源；accepted 途徑逃逸仍記 `PARITY`，notes 列出逃逸途徑與其畫面 issue。covered 途徑逃逸、或 public 有任何逃逸，才記 `GAP` |
| `U-A7` | 壓縮與快取差異量化 | RC-5 | 比對兩 surface 的 `Content-Encoding`、`Cache-Control`、傳輸位元組、冷/熱載入時間 | 記錄差異數值；ingress 首屏時間劣化 > 3× 列 Minor，> 10× 列 Important |
| `U-A8` | 大檔上傳上限 | RC-13 | 逐級上傳 1MB／10MB／100MB／500MB 附件 | ingress 與 public 的成功上限一致；不一致記錄實際上限 |
| `U-A9` | 長時間請求不中斷 | RC-5/13 | 觸發一個 > 60s 的伺服器動作（大量匯出／重算） | 兩邊皆完成，無 502/504 |
| `U-A10` | 錯誤頁一致 | RC-1 | 請求不存在路由、觸發伺服器 500 | 兩邊都回 Odoo 自己的錯誤頁，ingress 不得回 HA 的 404 |

### B 群組 — 會話與身分（L2）

| ID | 項目 | RC | 測法 | PASS 判定 |
|---|---|---|---|---|
| `U-B1` | 登入／登出／重登 | RC-4 | 錯誤密碼→錯誤訊息；正確密碼→進入；登出→回登入頁；再登入 | 三段行為與 public 相同 |
| `U-B2` | Cookie 屬性 | RC-4 | 檢查 `session_id` 的 `Path`／`Secure`／`HttpOnly`／`SameSite` | ingress：`Path` = token 路徑、`SameSite=Lax`、`Secure` 隨 `X-Forwarded-Proto`；public：`Path=/`、`Secure` |
| `U-B3` | 重整與深連結 | RC-15 | 在任一畫面 F5；複製網址列貼到新分頁 | 回到同一畫面，不落回 Discuss／首頁 |
| `U-B4` | 上一頁／下一頁 | RC-1 | 連續導覽後按瀏覽器上下頁 | 歷史堆疊與 public 相同，URL 保持帶前綴 |
| `U-B5` | 多分頁一致 | RC-4/7 | 同時開兩個 ingress 分頁操作同一筆記錄 | 無 session 互踢；SharedWorker 不重複建立 |
| `U-B6` | 宿主逾時復原 | RC-13 | 讓 HA session 過期後再操作 | 出現 HA 授權框；重新授權後回到原畫面而非白畫面 |
| `U-B7` | 權限一致 | RC-9 | 以同一低權限帳號在兩 surface 開同一受限記錄 | 兩邊都被拒，錯誤訊息語意相同 |
| `U-B8` | 匿名邊界 | AD-6 | 清空 HA cookie 直接打 ingress URL | 被 HA 擋下；**不得**洩漏任何 Odoo 內容 |

### C 群組 — Web Client 共用原語（L3）

> 這一組是「不同模組共用模板」的具體展開。任何後台畫面都由這些原語組成。

| ID | 項目 | RC | 測法 | PASS 判定 |
|---|---|---|---|---|
| `U-C1` | 全部視圖類型 | RC-1 | 對每個有該視圖的模型逐一開啟：list／kanban／form／calendar／graph／pivot／activity／hierarchy／settings | 皆正常渲染，無破圖、無 console error |
| `U-C2` | 控制面板 | RC-1 | 搜尋、篩選、分組、我的最愛、儲存搜尋、分頁器、排序、視圖切換、選用欄位 | 每個控制項行為與 public 相同 |
| `U-C3` | 表單 widget 全覆蓋 | RC-1/3 | 對每種 widget 至少一個實例操作：many2one（含「建立並編輯」）、many2many_tags、one2many 內嵌、selection、date／datetime picker、monetary、priority、boolean_toggle、handle 拖曳排序、statusbar、progressbar、reference、domain 編輯器、color picker、percentage、float_time、daterange | 全部可操作且值正確寫回 |
| `U-C4` | **複製到剪貼簿 widget** | **RC-3** | 對 `CopyClipboardChar`／`CopyClipboardURL`／`CopyClipboardButton` 逐一點擊 | 剪貼簿內容正確且出現成功提示；失敗即 **Important 以上**（見 `G-02`） |
| `U-C5` | URL 類欄位顯示值 | **RC-9** | 讀取畫面上每個 URL 欄位、連結 `href`、分享網址欄位的**字面值** | 其值必須是 **Canonical URL**，不得為 `127.0.0.1`、不得含 ingress token |
| `U-C6` | 富文本／HTML 編輯器 | RC-1/12 | 開啟 html 欄位編輯器，插入圖片、連結、表格、程式碼區塊，存檔後重載 | 內容一致；插入的圖片 `src` 帶正確前綴 |
| `U-C7` | 二進位欄位上傳／下載／預覽 | RC-1/3 | 上傳圖片與 PDF，下載，開啟預覽器（FileViewer） | 上傳成功、下載檔案 SHA-256 與來源一致、預覽可翻頁/縮放 |
| `U-C8` | 拖放上傳 | RC-3 | 把檔案拖進 chatter 與 binary 欄位 | 與 public 行為相同 |
| `U-C9` | Chatter 全功能 | RC-1/8 | 發訊息、記事、回覆、編輯、刪除、表情反應、@提及自動完成、加追蹤者、排程活動、標記完成、附件上傳/刪除 | 全部可用；即時反映不需重整 |
| `U-C10` | 對話框族 | RC-1/14 | 觸發 Dialog、確認框、SelectCreateDialog、FormViewDialog、錯誤 traceback 對話框 | 皆可開啟、可捲動、可關閉、Escape 有效 |
| `U-C11` | 系統列（systray） | RC-1 | 使用者選單、活動選單、Discuss 彈出、（開發者模式下）除錯選單 | 每個項目可開，導向正確 |
| `U-C12` | 應用啟動器與選單樹 | RC-1 | 展開到第三層，逐一點擊 | 每個 action 皆載入，無回落到 Discuss |
| `U-C13` | 麵包屑 | RC-1 | 多層下鑽後逐級點回 | 層級與 public 相同 |
| `U-C14` | 命令面板 | RC-3/13 | `Ctrl+K` 開啟，輸入指令並執行 | 快捷鍵未被 HA 宿主吃掉；面板可用 |
| `U-C15` | 鍵盤與焦點 | RC-3 | Tab 巡覽、Enter 送出、Escape 關閉、表單快捷鍵 | 與 public 相同；iframe 焦點不流失 |
| `U-C16` | 記錄操作 | RC-1 | 建立／儲存／捨棄／複製／封存／解除封存／刪除 | 狀態轉移與 public 相同 |
| `U-C17` | 動作與齒輪下拉 | RC-1 | 展開所有動作下拉，逐一執行（依安全等級） | 每個項目皆有明確結果 |
| `U-C18` | 匯出 | RC-3 | 匯出 xlsx 與 csv | 檔案實際落地；欄位與筆數一致 |
| `U-C19` | 匯入 | RC-1/3 | 匯入一份 csv（含 Unicode） | 匯入精靈全程可用，結果一致 |
| `U-C20` | 列印報表 | RC-3/9 | 對每個報表動作產生 PDF | HTTP 200、`application/pdf`、開頭為 `%PDF`、**內文/QR 中的 URL 為 public 基底** |
| `U-C21` | 通知 toast | RC-1 | 觸發成功／警告／sticky 通知 | 出現且可關閉，不被 iframe 邊界裁切 |
| `U-C22` | 翻譯編輯 | RC-1 | 點欄位旁地球圖示，編輯多語值 | 對話框可用，存檔生效 |
| `U-C23` | 新分頁開啟 | **RC-15** | 點任何 `target="_blank"` 連結、以及「在新分頁開啟」動作 | 記錄其開出的 URL 形態；ingress 下必然落在 Supervisor 路徑、位址必然含 token → 標 `STRUCTURAL`（第 1.4 節），並記下 public 承接的位址（`public_path`）；只有分頁打不開、開出的頁面不同、逃出前綴或 public 側不在 Canonical URL 才列 `GAP`（`G-07`） |
| `U-C24` | 全螢幕 | RC-3 | 任何請求全螢幕的介面（看板全螢幕、編輯器、工作中心） | 能進入全螢幕；不能則列 `GAP` 並標註需 iframe `allow` |
| `U-C25` | 相機／掃碼 | RC-3 | 任何需要 `getUserMedia` 的介面（條碼掃描、簽名拍照） | 能取得裝置授權；不能則列 `GAP` 並標註需 iframe `allow` |
| `U-C26` | 即時（bus） | RC-7/8 | 兩個瀏覽器情境（A=ingress、B=public）互推訊息 | `/websocket` 回 101、worker bundle 200、雙向 ≤ 10s 不需重整 |
| `U-C27` | Service Worker 依賴功能 | **RC-6** | 檢查 PWA 安裝提示、離線可用性、背景同步 | ingress 下必然不可用 → 標 `STRUCTURAL`，並記錄哪些模組依賴它（POS 不依賴：離線銷售是頁內機制，#161） |

### D 群組 — 前台 / Portal 共用原語（L4）

| ID | 項目 | RC | 測法 | PASS 判定 |
|---|---|---|---|---|
| `U-D1` | Website layout | RC-1 | navbar、footer、語言切換、站內搜尋、cookie bar | 全部可用，連結不逃逸 |
| `U-D2` | Website 編輯器 | RC-1/12/14 | 進入編輯模式、拖放 snippet、開媒體對話框換圖、編輯文字、存檔、行動預覽、頁面屬性、SEO 面板。**Blocks 面板縮圖**：每張磚的圖由 OWL 樣板以 `t-attf-style="background-image: url({{snippet.thumbnailSrc}});"` 畫出，走的是 `style` 屬性——依 ADR 0004 2026-09-28 附記不由 shim 覆蓋（#169 Group B）。2026-09-28 起由 Ingress 資產 location 的一條 Shipped rewrite 在**繪製處**加前綴（#170）：縮圖值會經「儲存區塊」回寫資料庫（`thumbnailSrc` → `ir.ui.view.save_snippet` 的 `thumbnail_url` → 新 view arch 的 `t-thumbnail`），所以改寫 `render_public_asset` 回應會把帶 token 的前綴存進資料庫，因此只改樣板文字、不改回應。Odoo 18 把 OWL 樣板以 `registerTemplate(...)` 未壓縮附在 bundle 之後，該文字只出現在 `web_editor.assets_wysiwyg` 一次 | 全程無 `AssetsLoadingError`；`/web/bundle` 回傳的資產 URL 帶前綴；Blocks 面板 36 張縮圖在 ingress 下皆 200、且縮圖不再產生 `route_escape`；在 ingress 下存一個自訂區塊，其 view arch 的 `t-thumbnail` **不帶** Ingress 前綴。**但 `route_escape` 未必為 0**：同一份樣板還有一張不可放置 snippet 的靜態圖 `<img src="/web_editor/static/src/img/snippet_disabled.svg">`，模板裡沒有任何 `/web_editor/` 規則（`"/web/` 不匹配 `"/web_editor/`），#143 那次量到的 36 筆逃逸也不含它（該畫面沒有 disabled snippet）。若 Live 重跑出現它，比照本列「snippet 內文的 root-relative `src`」另開 issue 處理 |
| `U-D3` | 頁面生命週期 | RC-1 | 新增頁面、發佈、取消發佈、刪除 | 與 public 相同 |
| `U-D4` | Portal 磁貼與清單 | RC-1 | `/my/home` 每個磁貼 → 清單 → 明細 → pager → 麵包屑 → 下載 | 全部可達 |
| `U-D5` | Portal 存取權杖連結 | **RC-9/10** | 產生 portal 分享連結，以**未登入的另一瀏覽器**開啟 | 必須能開；ingress 產生的連結若打不開即 `GAP`（`G-02` 同源） |
| `U-D6` | 前台表單提交 | RC-1/10 | Contact Us 等表單：驗證、送出、確認頁 | 兩邊皆成功 |
| `U-D7` | 匿名前台可達性 | **RC-10** | 以完全未登入身分存取前台頁 | ingress 原理上不可能 → 標 `STRUCTURAL`，指定由 public 承接 |
| `U-D8` | SEO 產出物 | RC-9 | `sitemap.xml`、`robots.txt`、OG meta、canonical、favicon | head 連結與 `robots.txt` 的 URL 必為 public 基底（兩邊一樣錯也算落差）；`sitemap.xml` **不計入本判定**，另記一筆由 `AD-8` 反向驗證（#172） |

### E 群組 — 對外產出物 URL（L5，最大盲區）

> 這一群完全在**伺服器端**組出 URL，前端 shim 一律無效。
> 前置條件 `P-3`／`P-4` 未達成前，本群組結果不可信。

| ID | 項目 | RC | 測法 | PASS 判定 |
|---|---|---|---|---|
| `U-E1` | `web.base.url` 不被登入覆寫 | **RC-9** | 記錄現值 → 以 admin 從 ingress 登入 → 重讀 | 值不變；若變成 ingress token URL 即 **Blocker（token 外洩）** |
| `U-E2` | 郵件內連結 | RC-9 | 觸發任一寄信動作（邀請、通知、密碼重設），攔截 outgoing mail 內容 | 所有連結為 public 基底；**不得含 token** |
| `U-E3` | 分享連結欄位 | RC-9 | 每個「分享」對話框中的 URL 欄位 | 值為 **Canonical URL**；可達性見下方註記 |
| `U-E4` | 報表內連結與 QR | RC-9 | 產生含 QR／連結的 PDF，解碼 QR | 指向 public 基底 |
| `U-E5` | 附件／檔案的絕對 URL | RC-9 | 取得附件的對外連結 | 同上 |
| `U-E6` | 外部回呼入口 | **RC-10** | 金流 notify／webhook／郵件追蹤 pixel 的目標 URL | 必為 public 基底且對外可達；ingress 不可能承接 → `STRUCTURAL` |
| `U-E7` | 匯出檔內的 URL | RC-9 | 檢查匯出的 xlsx／csv 內含連結欄位 | 同上 |

> **`U-E3` 可達性註記**（2026-09-23，issue #101）：連結的字面值正確**不等於**外部瀏覽器打得開。
> 能不能打開由被分享物件自己的存取控制決定，與 **Canonical URL** 無關，換成哪個基底都一樣。
> Discuss 的邀請連結 `/chat/<channel_id>/<uuid>` 就是一例：Odoo 18 對每個
> `channel_type = 'channel'` 自動把 `group_public_id`（Authorized Group）算成 Internal User，
> 而該路由對不在這個群組裡的呼叫者一律回 404——未登入的訪客不在任何群組。
> 因此 `U-E3` 的可達性**只在該物件允許匿名存取時**才列入判定。測 Discuss 時要先清掉
> 頻道的 Authorized Group，並且**不可**拿內建的 `general` 或 `Administrators` 頻道來測：
> 前者帶 Internal User，後者帶 Settings。2026-09-23 在控制組上三層實測（乾淨的原廠
> Odoo 18、`.6` 的資料、以及經 **Public origin** 的未登入請求）都是同一個結論。

> **`U-E4` 發票 Download > PDF 註記**（2026-09-28，issue #174）：`U-E4` 掛在 `RC-9`，
> 但 `#145` 在這一項上量到的逃逸不是 `RC-9`，是 **`RC-1`（路徑前綴遺失）**。
> 齒輪選單的 **Download > PDF** 來自 `account.move.get_extra_print_items` 回傳的一個
> `ir.actions.act_url` dict（`url: /account/download_invoice_documents/<ids>/pdf`，
> `target: download`），web client 的 `ActionMenus.onItemSelected` 對「有 `url`、沒有
> `action`」的項目直接執行 `browser.location=item.url`——整個 iframe 導頁，URL 由 RPC
> 帶回來。ingress 下 iframe 因此跳到 `<HA_BASE>/account/download_invoice_documents/<id>/pdf`，
> HA 回 404，檔案沒下來、發票表單也不見了（`ingress route_escape=1`，run
> `WOOW-PARITY-20260925T142416Z`；該筆記錄寫的 `RC-9` 是錯的，重跑後 `root_cause` 改記
> `RC-1`）。**Runtime shim 攔不到 `location` 的寫入**（ADR 0004），而字面改寫又碰不到
> 不在 bundle 裡的值，所以修法是改寫「會導頁的那個運算式」本身，讓它呼叫 shim 新發佈的
> URL helper `__WOOW_INGRESS_URL__`：`browser.location=item.url` 與
> `browser.location.assign(url)`（`ir.actions.act_url` 的 `target: self` 分支，以及
> 逐字相同的 `home` client action）兩條規則、三個位置。`Download > PDF without Payment`
> 走 `/report/…` 報表路徑，兩個 surface 本來就都正常，與本項無關。
> 　`target: self` 這一半計劃裡沒有對應項目，重跑時就用 `website.action_website`
> （Odoo 內建的 `ir.actions.act_url`，`url: /`、`target: self`）驗：ingress 下開
> `<ingress>/odoo/action-website.action_website`，修正前 iframe 會跳到 HA 根，
> 修正後應停在 `<ingress>/`。

### F 群組 — 宿主環境（L0/L2）

| ID | 項目 | RC | 測法 | PASS 判定 |
|---|---|---|---|---|
| `U-F1` | iframe `allow` 能力清單 | **RC-3** | 於 ingress 內執行 `document.featurePolicy`／`navigator.permissions` 探測 clipboard-write、fullscreen、camera、microphone、downloads | 產出實際可用能力清單；**這份清單是 `U-C4`／`U-C24`／`U-C25` 能否修復的上界** |
| `U-F2` | HA 快捷鍵衝突 | RC-13 | 在 ingress 內按 HA 有綁定的鍵（如 `c`、`e`、`d`、`m`） | 事件進入 Odoo 而非被 HA 攔截；被攔截即列 `GAP` |
| `U-F3` | HA 主題與尺寸 | RC-13 | 切換 HA 深/淺色、摺疊側欄、改變視窗大小 | Odoo 版面不破、iframe 高度正確 |
| `U-F4` | Supervisor 限制 | RC-13 | 量測 ingress 的請求體上限與逾時 | 記錄實際值，與 `client_max_body_size 512M` 對照 |
| `U-F5` | 下載行為 | **RC-3** | 從 ingress 觸發檔案下載（報表、匯出、附件） | 檔案實際落地；被 iframe 沙箱擋下即 Important |

---

## 7. 通用單畫面執行 SOP

每一個受測畫面**一律**走同樣九步，不因模組而異：

1. **同步開啟**：兩 surface 同時開到同一 DB／同一使用者／同一筆記錄的同一畫面。
2. **起錄**：清空並開始錄製 console、`pageerror`、network（含失敗請求與狀態碼）。
3. **靜態盤點**：擷取 DOM 快照，列出所有**可見且可用**的控制項，賦予語意身分（1.1 節）。
4. **逐項操作**：依安全等級執行——`read_only` 全做；`local_diagnostic` 有界執行；
   `mutation` 只在核准 fixture 上做並驗證回滾；`external` 絕不對已部署目標執行；
   `destructive` 只驗證守門。
5. **五訊號檢查**：`pageerror` / console error / 失敗請求 / HTTP ≥ 400 / 路由逃逸（`U-A1`、`U-A2`）。
6. **URL 字面值掃描**：擷取畫面上**所有** URL 字面值（欄位值、`href`、`src`、下載連結、
   對話框內文），逐一判定基底是否正確（`U-C5`）。
7. **集合比對**：`ingress 控制項集合` vs `public 控制項集合`；逐一比對語意結果。
8. **反向驗證**：在 A surface 造成的狀態變更，切到 B surface 讀取確認一致。
9. **出證**：依第 12 節 schema 產出記錄（含去識別化後的證據引用）。

**中止條件**：出現 Blocker 時，該畫面停止繼續操作，先記錄再處置，不得帶著已知破損狀態往下跑。

---

## 8. 原語宣告法（模組如何接上通用層）

每個模組在第 9／10 節只需要填三格，不重寫測試：

```yaml
module: <技術名稱>
uses_primitives: [U-C1, U-C3, U-C9, ...]     # 引用通用項目，不重述測法
route_prefixes: [/xxx/, /yyy/]                # 新前綴；是否需要改寫由 Rewrite scan 在執行期判定（ADR 0005）
module_specific: [<無法被 L0-L5 覆蓋的殘餘>]  # 盡量為空
outbound_urls: [<會產生對外 URL 的功能點>]     # 觸發 E 群組
```

`route_prefixes` 非空時，**不要**逐一把前綴補進 `odoo18ce/rootfs/etc/nginx/nginx.conf.template`
的 `location ^~ /web/assets/` 區塊。依 ADR 0004（`docs/adr/0004-runtime-shim-is-the-ingress-url-authority.md`），
Runtime shim 是 Ingress URL 的唯一權威，Literal rewrite 只補 shim 攔不到的整頁跳轉與路徑判斷；
一個前綴要不要進 Literal rewrite，由 bundle 的**用法**決定，不由 bundle 是否含有它決定。

> 依 ADR 0005（`docs/adr/0005-generated-rewrites-replace-the-control-group-gate.md`），
> 這個判定現在由 add-on 自己在容器內執行：**Rewrite scan** 於啟動時與之後每五分鐘讀取每個資料庫實際
> 提供的 asset bundle，把根相對字面量依消費方式分為 `FAIL`（整頁跳轉）、`WARN`（路徑判斷）、
> `INFO`（shim 已攔截），只把 `FAIL` 等級的前綴寫成 **Generated rewrite**（nginx include 檔
> `/data/nginx-generated-rewrites.conf`），經 `nginx -t` 驗證後 reload；`WARN` 依 ADR 0004 永遠不改寫，
> `odoo18ce/rootfs/usr/local/lib/literal_rewrite_exceptions.yaml` 登記的例外仍然適用。
> 裝完 app 不必補模板、不必等 Release；新規則加入時 Home Assistant 會收到通知，add-on log 記錄每一輪。
> `literal_rewrite_auto` 關閉時只掃描、不套用。
>
> `U-A4` 的守門腳本 `odoo18ce/tests/e2e_literal_rewrite_gate.py` 仍在，是同一套分析從外部對 Public origin
> 跑的版本（登入、收集 bundle、與現行規則求差集），供手動驗收用：`--include-file` 可帶入主機上的
> Generated rewrite 檔一起計入已登記規則。`.github/workflows/literal-rewrite-gate.yml` 不再每晚排程，
> 保留 `workflow_dispatch` 手動觸發。

---

## 9. 目標安裝 13 apps 覆蓋宣告

| 模組 | 引用原語 | 新增路由前綴 | 模組特化殘餘 | 對外 URL 功能點 |
|---|---|---|---|---|
| `mail` | C1,C9,C10,C11,C26,C27 | `/mail/`（已列）、`/discuss/`（INFO，shim 攔截） | 附件預覽器、@提及自動完成 | 郵件內所有連結 `U-E2` |
| `contacts` | C1–C3,C7,C16–C20 | — | 地圖／地址連結 | 名片分享 |
| `calendar` | C1,C3,C9,C10,C26 | `/calendar/`（已列） | 拖放改期、重複事件、行事曆訂閱 URL | 邀請信、`.ics` 訂閱連結 |
| `crm` | C1–C3,C9,C16,C17,C20 | — | 看板拖放、預測視圖 | 商機分享、報價信 |
| `project` / `project_todo` | C1–C3,C9,C16,C17 | `/project/`（INFO，shim 攔截） | 看板拖放、子任務、**分享唯讀連結** | **`U-E3` 分享連結（`G-01`／`G-02`）** |
| `account` | C1–C3,C16,C17,C20 | `/account/`（INFO，shim 攔截）；`/my/invoices` 不在任何 bundle | 對帳、稅務、稽核軌跡 | 發票 portal 連結、付款連結、PDF 內 QR |
| `purchase` | C1–C3,C16,C17,C20 | `/purchase/`（INFO，shim 攔截） | 供應商 portal | 詢價單寄送連結 |
| `stock` | C1–C3,C16,C17,C20 | `/stock/`（INFO，shim 攔截） | 條碼輸入、批號序號、揀貨介面 | 交貨單 PDF |
| `hr` / `hr_skills` | C1–C3,C7,C16 | `/hr/`（INFO，shim 攔截） | 組織圖、員工照片 | 員工資料分享 |
| `mass_mailing` | C1,C6,C16,C17 | `/r/`（短連結追蹤，**高風險**）、`/mass_mailing/`、`/mail/track/` | 郵件設計器（iframe 內的 iframe） | **`U-E2`：追蹤連結、退訂連結全部是對外 URL** |
| `website` | D1–D8 全部 | `/website/`（已列）、`/web_editor/`、`/html_editor/` | snippet 編輯器、頁面管理、SEO 面板 | `U-D8` SEO 產出物 |

> 原本標「**待確認**」的前綴已於 2026-09-24 實測（#144，`odoo_parity` 裝齊 29 個模組，0.4.4）：
> 最後一輪 Rewrite scan 讀 34 個 bundle，`FAIL 0`、`WARN 37`、`INFO 486`；上表各前綴都是 `INFO`
> （Runtime shim 攔截），沒有產生任何 Generated rewrite。兩個 surface 的選單爬蟲比對 290 個選單：
> 272 `PARITY`、4 `GAP`、14 跳過；這 13 個 app 的已比對選單全為 `PARITY`（`website` 的訪客清單除外，見 #160）。
> `project_todo` 唯一的選單是 server action，依唯讀規則跳過，那一輪沒有可比對的畫面。
> 證據在 `docs/testing/evidence/2026-09-24-issue-144/`。
> 注意 `INFO` 表示「shim 攔得到這種用法」，不保證每個消費點都攔得到：`/barcodes/` 也是 `INFO`，
> 但當時 `new Audio(url(...))` 仍逃逸（#159）；資料庫裡的 HTML（動作的 help）也不在 bundle 內（#158）。
> #159 已由 shim 補上媒體來源包裝（2026-09-28），`/barcodes/` 維持 `INFO` 且不新增 Generated rewrite；
> 但這條注意事項仍然成立：`INFO` 只表示 shim 攔得到，遇到新的消費點要先確認。

> `project_todo` 的畫面於 2026-09-29 由 #163 補判（0.4.5）：改用爬蟲新增的 `open` 子指令，直接開那個
> server action 回傳的 window action（`project_todo.project_task_action_todo`，不執行 server action），
> 兩面各判三個畫面——待辦看板、待辦清單兩面 `PARITY`；**待辦表單當時是 `GAP`（blocker）**：待辦自己的說明
> HTML（`project.task.description`，由 `todo_user_onboarding` 複製而來）內的兩張圖在 Ingress 下向 HA
> 根網址要，404、`route_escape=2`。與 #158 同型但不是同一個修法：#158 的 Literal rewrite 只綁
> `/web/action/load`，而待辦說明走 `/web/dataset/call_kw`，正是 ADR 0004 的 2026-09-28 附記拒絕改寫的
> 紀錄內容。這一輪的證據在 `docs/testing/evidence/2026-09-29-issue-163/`。
>
> **待辦表單的 `GAP` 已於 2026-09-30 修正（#210），並於 2026-10-01 在 Release 0.4.9 上完成 Live 重跑
> （#235，改記 `PARITY`，詳見本附記末）。** 依 ADR 0004 的 2026-09-30
> 附記，修法不是改寫 `call_kw` 回應，而是 HTML 編輯器內容的一組「進／出」Literal rewrite：Runtime shim
> 另外發佈 `__WOOW_INGRESS_MARKUP_IN__`／`__WOOW_INGRESS_MARKUP_OUT__` 兩個唯讀的**字串** helper
> （前綴一律走 shim 自己的 `path()`）。五個改寫點：`Editor.attachTo` 在值變成 DOM 之前先上前綴（圖片
> 一被解析就會發請求，所以必須改字串而不是改 DOM）；協作外掛的 `resetFromServerAndResyncWithPeers`
> 是第二個 render 點，待辦欄位設了 `'collaborative': true`，文件落後伺服器時會走到那裡；
> `HtmlField.updateValue` 是欄位寫回記錄的唯一出口，在那裡把前綴全部拿掉——比在編輯器裡拿掉更晚，
> 所以連 `savePendingImages` 事後改寫的貼上圖片也涵蓋；`_commitChanges` 的 `comparisonValue` 讀的是
> 還帶前綴的複製節點，也一起剝掉，否則 urgent 存檔的比較永遠不成立、會多寫一次；以及
> `/html_editor/get_image_info` 的 `src`，那個 route 只認 `/web/image` 開頭的路徑，不還原前綴
> 裁圖會報「外部圖片」。所以資料庫存的仍是 root-relative，不會把 Supervisor token 寫進記錄。
> 靜態層契約在 `odoo18ce/tests/test_ingress_todo_description.py`（含 2026-09-30 重新擷取的 bundle
> 片段）。
>
> **Live 重跑已於 2026-10-01 在 Release 0.4.9 上完成（#235），這一列改記 `PARITY`。** 待辦表單在
> 兩面的 `route_escape`／`http_4xx_5xx`／`console_error`／`pageerror`／`failed_requests` 皆為 0，
> Ingress 側兩張圖的 `src` 帶前綴（`<INGRESS_PREFIX>/project_todo/static/img/…`）且**都載入成功**；
> 在 Ingress 下用編輯器存一次待辦之後讀回 `project.task.description`，兩個 `src` 仍以
> `/project_todo/` 開頭，整份 HTML 不含 `hassio_ingress` 字串、沒有任何絕對位址——存檔寫入是真的
> （這一輪打的標記確實存進去了，之後才還原）。對照組在同一份證據裡：0.4.6 上同一畫面兩張圖
> `img_loaded` 為 `[false, false]`、對 HA 根網址各 404 一次。單一 session；兩個 Ingress session 的
> 協作快照是 #234，不在這一輪。證據見 `docs/testing/evidence/2026-10-01-issue-235/`。

> **唯讀 html 欄位的兩個 render 點已於 2026-10-01 補上（#237，ADR 0004 的 2026-10-01 附記），
> Live 重跑已於 2026-10-02 在 Release 0.4.10 上完成（#243），四項全過，這一列改記 `PARITY`。** #210 修的是可編輯那條；唯讀 `HtmlViewer` 是 ADR 0004 附記裡「一次碰到兩處 markup」
> 的那一項，而且是常見的那一邊——使用者不能編輯的表單、portal 看到的記錄（project sharing 的
> `project.webclient` 送的是同一份位元組）、以及 html 欄位的歷史對話框都掛同一個元件。兩條改寫：
> 樣板裡的 `t-out="state.value"`（純文字那條路）與 `iframeTarget.innerHTML=content;`
> （`hasFullHtml`／`cssAssetId` 那條路）。**沒有「出」的那一半**：唯讀沒有存檔，前綴是在插入的那一刻才
> 加上去的，元件自己的 `state.value` 仍是記錄的原位元組，所以歷史對話框的「Restore history」（重新
> 向 ORM 取修訂）與 `onWillUpdateProps` 的比較都看到伺服器送來的值。兩條都走 shim 新發佈的第三個
> helper `__WOOW_INGRESS_MARKUP_IN_VALUE__`：唯讀 html 欄位的值是 OWL 的 `Markup` 物件，而 #210 的
> `__WOOW_INGRESS_MARKUP_IN__` 對非字串原樣回傳，直接套用會是沉默的 no-op。靜態層契約在
> `odoo18ce/tests/test_ingress_readonly_html_viewer.py`（含兩個 pattern 的測量，以及兩條路徑在
> globals 有／無兩種情況下的執行）。`U-A6` 的探測清單**不**擴充，`innerHTML` 一途仍記 accepted。

> **舊版 `web_editor` 編輯器（郵件設計器那一個）的十個改寫點已於 2026-10-01 補上（#238，ADR 0004
> 的第二個 2026-10-01 附記），Live 重跑已於 2026-10-02 在 Release 0.4.10 上完成（#243）：
> 寄出的 mailing 唯讀 iframe、designer 載入、以及存檔後 `body_arch` **與** `body_html` 兩個欄位
> 都仍是 root-relative，三項全過，這一列改記 `PARITY`；rule 9／10 仍無畫面，照 #238 自己的理由記為
> unreachable。** Odoo 18 其實有**兩個** HTML 編輯器：
> #210 與 #237 改的是 `html_editor`，而還有三個 field widget 跑的是 `web_editor` 裡的舊編輯器，它的
> load／save 是**不同的運算式**，所以前面八條規則一條都不會命中。三個 widget 逐一在 pinned deb 內查
> 證：`html_legacy`**沒有任何出貨 view 用它**（除了它自己的註冊之外，整包只出現在
> `web_editor/static/tests/` 的四個測試檔：`html_field_tests.js`、`banner_tests.js`、`link_tests.js`、
> `list_tests.js`）；`mass_mailing_html` 只有 `mass_mailing/views/mailing_mailing_views.xml` 一處（`body_arch`，
> 郵件設計器，`mass_mailing` 在 `odoo_parity` 的 29 個模組內）；`account_payment_register_html` 是本輪
> 新發現、issue 沒點名的第三個——`account` 繼承了舊欄位與它的樣板，所以 Register Payment 精靈走的是
> 下面那條純文字唯讀路徑（它自己的值 `installments_switch_html` 是 computed 文案、不含 URL，今天不會
> 逃逸，補的是**路徑**）。
>
> 六個「進」（都走 `__WOOW_INGRESS_MARKUP_IN_VALUE__`，因為這裡的值都是 `record.data[name]`，即 OWL
> 的 `Markup` 物件）：`Wysiwyg.startEdition` 的第一次載入、`OdooEditor.resetContent`（換記錄／放棄／
> 協作重設／換郵件主題／關閉 code view 都走這裡）、唯讀 iframe 的三個分支（refresh、第一次載入、
> sandboxed preview；**寄出後**的 mailing 表單是唯讀且設了 `cssReadonly`，就是這條可達的畫面）、以及
> 舊欄位樣板裡 `o_readonly` div 的 `t-out="markupValue"`。四個「出」：`getEditingValue()`（每一次存檔
> 唯一都會經過的讀取點——**前綴要在這裡剝掉而不是在旁邊的 `record.update`**，否則 `updateValue` 會拿
> 帶前綴的編輯值去跟不帶前綴的 ORM 值比較，每次 commit 都判定 dirty 並多寫一次，`currentEditingValue`
> 還會讓 Wysiwyg 每次更新都重設內容）、mass_mailing 的 `const inlineHtml=editableClone.innerHTML;`
> （`inline-field` 的 `body_html`，**第二個欄位**，完全不經過 `getEditingValue`；漏掉這個等於把
> Supervisor token 連同郵件寄出去）、以及 code view 兩次 toggle 的兩個 `record.update`（受
> `odoo.debug && options.codeview` 限制，沒有出貨 view 設這個 option，但它是 token **write**，所以兩行
> 一起補而不另開 issue）。
>
> 郵件設計器的「iframe 裡的 iframe」：十個運算式**全都**跑在頁面本身的 realm，所以 shim 發佈的
> globals 都拿得到。編輯器自己的 iframe 是 `document.write` 出來的、從來不是 HTTP 回應（shim 沒跑），
> 而它載入的 `web_editor.wysiwyg_iframe_editor_assets` 既不含 `wysiwyg.js` 也不含 `OdooEditor.js`——這
> 是量出來的，記在 `odoo18ce/tests/fixtures/bundles/README.md`。編輯器本體是 `_lazyloadWysiwyg` 用
> `loadBundle` 取 `web_editor.backend_assets_wysiwyg`（`<script src>`，shim 會加前綴），所以改寫後的
> 位元組確實送達；而那個 iframe 的 asset 之所以載得起來，是因為一般 HTML location 早就有
> `"src": "/` → 加前綴這條規則在處理 `/web/bundle` 的 JSON。
>
> 兩個 pattern 從識別字中間開始（`editable.html(options.value);`、`codeview.val();…`），這是 nginx 的
> 限制不是取巧：nginx 把參數裡的 `$` 當變數開頭、且無從轉義，未知變數會讓設定載不起來，所以
> `this.$editable` / `$codeview` 的 `$` 留在比對範圍外。靜態層契約在
> `odoo18ce/tests/test_ingress_legacy_html_editor.py`（十個 pattern 的測量、兩個「尾段」pattern 證明
> 確實是完整運算式的尾段、改寫後的樣板重新用 XML parse 回來並確認 `account` 的 `t-inherit` xpath 仍
> 命中、「沒有變更的 commit」在原始與改寫兩份位元組上各跑一次、以及十個點在 globals 有／無兩種情況下
> 的執行）。`U-A6` 的探測清單**不**擴充，也沒有新的 global。**Live 重跑（由 #243 執行）**：在 Ingress
> 下開啟並儲存郵件設計器的 body，兩面 `route_escape`／`http_4xx_5xx`／`console_error` 皆為 0，且
> `mailing.mailing` 的 `body_arch` **與** `body_html` 存後仍是 root-relative。

> **協作 peer snapshot 的前綴（`project.task.description` 的 token write）已於 2026-10-01 修正
> （#234，ADR 0004 的第三個 2026-10-01 附記），Live 量測已於 2026-10-02 在 Release 0.4.10 上
> 執行（#243）：兩個 pair 都 `CLEAN`、兩邊前綴相等如預期、`escalate_issue_234_to_blocker: false`，
> 所以 #234 維持 `severity: important`。**但協作傳輸兩個 pair 都沒有送達**，所以這兩個 `CLEAN`
> 說的是「存檔路徑不存前綴」，**不是**「送達的 peer snapshot 不存前綴」；`ingress-public` 的兩段式
> 復原讀取也還沒實作。兩者見 #265。** 這是 ADR 0004 開放清單裡
> 唯一一個「寫進資料庫」而不只是畫面錯的項目：To-do 的 description 是 `'collaborative': true`，協作
> 傳輸送的是**序列化節點**（每個 attribute 的值逐位元組，`history_plugin.js:1168`），後加入的 peer 會
> 拿到先加入那個 peer 的整份文件作為 snapshot，接收端用 `node.setAttribute(key, value)` 套上去
> （`:1198`）——而 shim 包了 `setAttribute`，`path()` 認不出不屬於本頁的前綴，會**再加一次**，所以接收
> 端的 editable 裡是 `<本頁前綴><對方前綴>/web/image/…`。
>
> **issue 的前提要修正，而結論不變。** 路徑裡的 token 是**add-on 的** `ingress_token`（Supervisor 的
> app user-data schema 用 `secrets.token_urlsafe` 預設一次，每個安裝的 add-on 一份），不是使用者的也
> 不是 session 的；per-user 的 session 是另一個 secret，走 `ingress_session` cookie，不出現在路徑裡。
> 本 repo 自己的 adapter 也是這樣用的：prefix 只從 `/addons/<slug>/info` 讀一次，所有 session 共用
> （`e2e_menu_action_adapter.py:789`）。Supervisor 那一側的依據（2026-10-01 讀 `main`）：
> `supervisor/apps/validate.py` 的 `SCHEMA_APP_USER`、`supervisor/apps/app.py` 的
> `ingress_token`／`ingress_entry`、`supervisor/ingress.py` 的 `create_session`——本 repo 測不到，所以
> 列出出處讓下一個人自己查。**同一個讀法也改了本計劃的兩列**：`RC-15` 與 `G-07` 原本把那串 token 稱為
> *session* token；嚴重度與結論都不變（路徑裡仍是憑證，貼給同事仍打不開），擋住的是對方沒有的
> `ingress_session` cookie，而不是每個人路徑不同。所以**同一個 add-on 的兩個 Ingress session 前綴相同**，#210 的
> 字面 strip 本來就蓋得住那一組；會出現「本頁沒見過的前綴」的情況是：add-on 重裝或還原備份換了
> token、第二個 add-on／第二套 HA 連同一個資料庫，以及**另一個 peer 在 Public origin**——那一面沒有
> shim 也沒有 rewrite（ADR 0003 的對照組），收到什麼就存什麼，也沒有東西可以剝。Ingress 這邊擋不住
> 那一次寫入，能做的是**下一次 Ingress 存檔時把記錄治好**。
>
> 修法是一個運算式：`__WOOW_INGRESS_MARKUP_OUT__` 除了去掉 `__INGRESS_PATH__` 的每一次出現，也去掉
> 每一個符合 nginx `$safe_ingress_path` map 形狀的前綴。兩半都要：gateway 交給本頁的那個不論形狀都要
> 去掉（#210 的契約用的 `/api/hassio_ingress/token` 正是 map 會拒絕的形狀，而它**原封不動**仍然通
> 過），形狀那半是給本頁沒見過的前綴。形狀只寫在 map 那一處，`test_ingress_peer_snapshot_prefix.py`
> 從 template 把兩邊都解出來比對，字元類與上下界都比。比上界長一個字元的 token **整個不動**（pattern
> 尾端的 lookahead），因為把 URL 中間挖掉比原本那個已經量過、可回復的逃逸更糟。`IN` 刻意**不**學這個
> 形狀：對方的前綴不在 render 時治好，所以 peer 傳來的圖在存檔並重新載入前仍是 404——治在「出」那一
> 邊，token 的危害在那裡。沒有新 global、沒有新 `sub_filter`，#210 的五個點與 #238 的四個 `OUT` 規則
> 一次全覆蓋（含郵件那個會寄出去的 `body_html`）。`U-A6` 的探測清單**不**擴充。
>
> **Live（由 #243 執行）**：#234 原本寫的「兩個 Ingress session 開同一張 to-do」照跑，但要**記下兩邊
> 的前綴**而不是假設不同——同一個 add-on 會相同，那正是這一組本來就乾淨的原因；會產生 foreign 前綴
> 的組合是「一個 Ingress session ＋ 一個 Public origin session 開同一筆記錄」。腳本已留下且
> **尚未執行過**：`odoo18ce/tests/e2e_collab_peer_snapshot_live.py`（`probe` 不存檔只看傳輸到不到、
> `run` 才存檔並把 `description` 讀回來分類；輸出一律把前綴換成 session 標籤，不會有 token 落地），
> 純函式部分由 `test_e2e_collab_peer_snapshot.py` 在靜態層跑過。讀回來存著 foreign 前綴才把 #234
> 升為 `severity: blocker`（parity plan 1.3），在那之前維持 `severity: important`。
>
> **事後補註（#263，2026-10-02）**：上一段的「**尚未執行過**」已於 2026-10-02 由 #243 在 Release
> 0.4.10 上執行（兩組 pair 都 `CLEAN`、都**沒有**送到，#234 維持 `severity: important`），而上一段裡
> 「`probe` 不存檔」這句話當時就是**錯的**：`probe` 每一輪都把自己的 marker 寫進
> `project.task.description`，因為在 dirty 的 To-do 表單上導覽離開會把 editor 的內容存進去。#263 已修
> ——離開前按表單自己的 Discard，再把欄位讀回來回報 `wrote_nothing`——判準與 0.0 秒那個形狀記在第 12 節。
>
> **事後補註（#265，2026-10-02）：傳輸送到了，而 `ingress-public` 真的存進了前綴。** 上一則補註裡
> 「都**沒有**送到」的原因查出來是**本腳本的缺陷**，不是這台主機或它的設定：沒有任何 view 設
> `collaborative_trigger`，協作 plugin 因此只在 editable 的 `focus` 事件上加入 peer 網路
> （`collaboration_odoo_plugin.js:91-99`），而還沒加入的 session 會把收到的每一則 signalling 通知
> **默默丟掉**，包括對方的 `ptp_join`（`:156-158`）——沒有 log、DOM 裡也看不出來。送方是打字時順便
> focus 才加入的，收方則要等到 30 秒等待結束後才第一次被 focus。#265 補上那一步後於同一個 Release
> 0.4.10 重跑（`docs/testing/evidence/2026-10-02-issue-265/`，run `WOOW-PEER-20261002T064500Z`），
> 三個讀數都量到了：欄位兩面都是 collaborative、bus 兩面都 `CONNECTED`、兩個 session 同一個
> `editor_collaboration:project.task:description:5` channel。結果兩列：
>
> - `ingress-ingress`：**送到**（`delivered: true`、`marker_pre_existing: false`）後仍 `CLEAN`。這才是
>   上一則補註那個 `CLEAN` 一直被引用成的那句話，之前沒有任何一輪真的講得出來。
> - `ingress-public`：**送到**，而且 Public peer 的存檔把 to-do 兩張圖的 `src` 都存成
>   `/api/hassio_ingress/<ingress:A>/…`——**`FOREIGN-PREFIX-STORED`，#234 講的那次寫入第一次被實測到**。
>   接著是本列上面要求、#243 做不到的兩段式復原讀取：Ingress session 丟掉自己的殘留、**重新載入該
>   記錄**（`loaded_prefixes: ["A"]`，這個讀數說明治療有對象）、打一次 marker 存一次檔，兩個 `src`
>   都回到根相對路徑（`healing.verdict: CLEAN`）。
>
> 所以「Ingress 這邊擋不住那一次寫入，能做的是下一次 Ingress 存檔時把記錄治好」現在是**量過的**，兩半
> 都量過。`report` 的 `escalate_issue_234_to_blocker` 因此是 **`true`**：#234 的驗收條件寫的是「**確認**
> 存到 foreign token」，而這一輪確認到了，所以規則讀的是這一輪讀到的**每一個**值而不只是最後一個——
> 只看最後一個的規則，會對著「證明逃逸存在」的那次量測回答「沒有」。治好那件事列在它**旁邊**而不是
> 取代它（`foreign_prefix_healed`），另有 `foreign_prefix_still_stored` 回答「現在欄位裡還有沒有」
> （這一輪是空的）。本列**不自行**改 #234 的 severity：現狀是「確認存到、而且被治好」，兩者哪一個算數
> 是 #234 自己的決定，這一輪只把兩個讀數都報出來。**#234 已於 2026-10-02 裁定維持 `severity:
> important`**（讀的是「現在還在不在」那一邊：寫入確認、而下一次 Ingress 存檔會清掉，那正是這個修法
> 當初就只宣稱做得到的事），並維持關閉。那次寫入本身登記為 **`G-08`**（第 11 節），未解的是它蓋不到
> 的那個形狀：一筆被 Public peer 寫過、而**再也沒有 Ingress session 存過**的記錄會一直留著 token。

> **媒體對話框「重新開啟時不會highlight原本那個附件」已於 2026-10-01 處理（#239，ADR 0004 的第四個
> 2026-10-01 附記），Live 重跑已於 2026-10-02 在 Release 0.4.10 上**完成**：#243 跑了 image 那一行
> （Ingress 4 格選中 1、Public 1 格選中 1，另外量到 `rule_in_served_method` 在 Ingress 為 true、
> 在 Public 為 false，直接證明改寫只住在 Ingress asset location），另外兩行當時沒量到——document 那一行
> 在現行編輯器**無法到達**（Replace 在 `image` namespace，document 是 `a.o_image`），website 那一行
> **到達但沒驗到** rule 2（首頁唯一可見圖片沒有 `data-original-src`）；**#266 把那兩行都量到了，兩行都
> 過**（細節見本列最後的「Live 補跑」）。**這一列改記 `PARITY`——範圍是三行的 preselection 比較——而且不因
> Live 結果改嚴重度，它什麼都不存。同一個畫面另外量到的**列表**分歧另案登記為 `G-09`（#271），不屬於
> #239 的三條規則。** 這是 ADR 0004 開放清單裡最後兩項，而且是這一族
> 唯一「反向」的三項：不是插入 markup，而是**比較**——一邊期待 root-relative、另一邊拿到帶前綴的值。
> 本輪的結論是**三項裡兩項真的壞掉、第三項本來就是對的，而對第三項照 issue 說的做會把它弄壞**：
>
> | | 比較 | 量到的狀況 | 出貨 |
> | --- | --- | --- | --- |
> | 1 | `ImageSelector.isInitialMedia` 的 `getAttribute("src")` | 元素被 **shim** 加了前綴、`attachment.image_src` 不帶 | **改寫**，元素那側走 `__WOOW_INGRESS_MARKUP_OUT__` |
> | 2 | 同一個方法的 `dataset.originalSrc` 分支 | 元素被 **HTML location** 加了前綴、`attachment.image_src` 不帶 | **改寫**，同一個 strip |
> | 3 | `DocumentSelector.fetchAttachments` 的 `getAttribute("href")` | **兩側都帶前綴** | 不改 |
>
> 三項各存在**兩份**：Odoo 18 出貨兩個媒體對話框，`html_editor` 的（後台表單開的那個）與舊
> `web_editor` 的（`wysiwyg.js` 與網站編輯器的 snippet options 開的那個；整包有九個檔案從該元件自己
> 的目錄之外 import 它，測試不算——其中兩個還在 `web_editor` 自己裡面）。兩個 `image_selector.js`
> 是同一段程式、只差引號，所以第 1 列是**兩條** `sub_filter`；第 2 列只要**一條**，因為那是兩個對話框
> 唯一寫法完全相同的一行。只修 issue 點名的那一個對話框，會把郵件設計器與網站編輯器的那一個留在原狀。
>
> 第 1 列是 issue 描述的那個 bug：元素的 `src` 在 Ingress 下帶前綴（shim 的 `setAttribute` 包裝、或
> `__WOOW_INGRESS_MARKUP_IN__`），而 `attachment.image_src` 是 `ir.attachment._compute_image_src`
> 算出來的 `/web/image/<id>-<checksum>/<quote(name)>`，走 `call_kw` 送來、不帶前綴，所以永遠比不中，
> 格子一片沒選取。修法與 #210 對 `get_image_info` 參數做的完全一樣——元素那側過同一個 strip，沒有新
> 的 global，對不帶前綴的值是 no-op，而且順便繼承 #234：strip 去掉的是**符合形狀**的每一個前綴，所以
> 協作 peer 送來的圖也比得中。
>
> **第 2 列是本輪差點做錯、被 review 抓回來的一項。** 原本的理由只有一半成立：
> `data-original-src` 不是 `data-src`（markup helper 的屬性比對是精確名稱，`setAttribute` 包裝的清單
> 是 `href`/`src`/`action`/`xlink:href`），所以 **shim** 不會碰它，`loadImageInfo` 寫進去的也是伺服器
> 自己的 `image_src`。但加前綴的是**一般 HTML location**：那條規則寫的是 `src="/`，而 nginx 的
> `sub_filter` 是純子字串搜尋，於是它命中了更長的屬性名裡面的 `data-original-src="/...`——旁邊沒有
> 任何規則先占住那個位置，`data-src="/` 只占自己的。而 Odoo 的出貨 arch 本來就帶這個屬性
> （`mass_mailing_themes/views/mass_mailing_themes_templates.xml` 的每一張主題圖都有），所以**以 HTML
> 回應送達的 markup** 到瀏覽器時 `data-original-src` 是帶前綴的，而同一個屬性在欄位值上（走 `call_kw`，
> 不改寫）是 root-relative。更要緊的是這個分支在 `src` 那行**之前就 return**，所以只修第 1 列的話，
> 網站編輯器的對話框會依然壞著、而三條規則全部出貨、所有測試全綠。
>
> **第 3 列是本輪最值得讀的一段。** 它的左運算元是 template literal
> `` `/web/content/${attachment.id}` ``，開頭就是 `` `/web/ ``——那是 Ingress asset location 從 #166
> 起就一直出貨的通用字面規則之一。所以**bundle 送到瀏覽器時那個 literal 已經帶了前綴**，右邊的 `href`
> 也帶前綴，這個比較從 Ingress 存在以來一直是「帶前綴 vs 帶前綴」。照開放清單說的在 `href` 那側加
> `OUT`，就會變成一邊剝一邊不剝，對話框會**停止**highlight原本那份文件——拿一個好畫面換一個「修好」。
> 這不是推論而是量的：四份擷取的 bundle 片段用**真正的 nginx**、帶上該 location 的**每一條**規則送出
> 一次，兩份 document 片段回來時前綴已經在 literal 裡，兩份 image 片段則與擷取時位元組相同（因為
> `image_src` 是 ORM 值、元素的 `src` 是 DOM 讀取，沒有任何字面規則碰得到）。
>
> 靜態層契約在 `odoo18ce/tests/test_ingress_media_dialog_preselect.py`（40 個測試）：用**真正的
> nginx**把四份片段按該 location 自己的字面規則送出一次，要求結果與測試自己用 `str.replace` 算出來的
> 位元組**完全相同**——這同時證明了兩件事：document 兩份的 literal 真的帶著前綴到瀏覽器，image 兩份
> 除了本族自己的三條規則之外沒有被任何通用規則動過；另外也把一份 page-HTML 樣本按一般 HTML location
> 的規則送出一次，那就是第 2 列理由的執行版。其餘：從樣板**解出** `` `/web/ `` 那條規則（不是把它抄在
> 測試裡）、套到片段上、在 node 裡跑 `fetchAttachments` 並讀回「哪一個附件被選取」；斷言那條是**唯一**
> 碰到該片段的通用規則；把「只剝一側」的改寫真的跑一次並顯示它選不到東西；以及**拒絕**任何提到那個
> `href` 讀取的 `sub_filter`，免得後面的人照開放清單再加回來。把那條 `` `/web/ `` 規則移掉，該檔案有
> 四個測試會紅並指名它；把一般 HTML location 的 `src="/` 規則移掉，第 2 列的那個測試會紅。
> `U-A6` 的探測清單**不**擴充，沒有新的 global，Public origin 不動。
>
> **Live（由 #243 執行，本輪已以 comment 細化該列）**：這一列是**純畫面狀態**，兩面都不存任何東西，
> 所以它是 #243 register 裡唯一不會因為 Live 結果升級嚴重度的一列。本輪把它的期待值改了一半：image
> 那半是「原本壞的現在好了」，document 那半是「**本來就是好的，確認它還是好的**」——在 Ingress 下重新
> 開啟某張圖片／某個文件連結的媒體對話框，對應附件被 highlight，兩面行為一致。image 那半值得**在網站
> 編輯器的對話框上也跑一次**而不只是待辦表單：第 2 列的前綴只出現在 HTML 回應那條路上。
>
> **Live 補跑（#266，2026-10-02，同一個 Release 0.4.10，不需要重新發版也沒有重新部署）：三行的**比較**
> 全部量到、而且三行兩面一致，所以這一列改記 `PARITY`。** 判定的範圍就是這一列的範圍——**哪一格被
> highlight**。同一個畫面另外量到一個**列表**分歧（Documents 分頁列出的附件兩面不同），那不屬於 #239 的
> 三條規則，另案登記為 `G-09`（第 11 節）並由 **#271** 承接，見本列最後一段。證據在
> `docs/testing/evidence/2026-10-02-issue-266/`（`markup.jsonl` 22 筆、`markup.ambient.json` 22 行，
> run `WOOW-MARKUP-20261002T074704Z`）。
>
> | 行 | 畫面 | Ingress | Public | 判定（preselection） |
> | --- | --- | --- | --- | --- |
> | 1 image | driver 自建的 scratch 待辦＋圖片，現行編輯器 | 元素 `src` 帶前綴，4 格選中 1 | root-relative，1 格選中 1 | **`PARITY`** |
> | 2 website | driver 自建的 website 頁面，網站編輯器的 Replace Media | `data-original-src` **帶前綴**，4 格選中 1 | root-relative，1 格選中 1 | **`PARITY`** |
> | 3 document | driver 自建的文件，**舊編輯器**（郵件設計器）的對話框 | 元素 `href` 帶前綴，Documents 分頁 30 格**選中 1** | root-relative，1 格**選中 1** | **`PARITY`**；**列出的格數兩面不同（30 對 1）→ `G-09`／#271** |
> | 3 document | 同一份文件，**現行**編輯器 | 沒有任何控制項能重新開啟對話框 | 同樣沒有 | `NOT-RUN`（附理由） |
>
> 第三列那個 30 對 1 **是**量到的分歧，所以它登記在第 11 節而不是只寫在散文裡；把它併進這一列的判定
> 會把兩件不同的事混成一件——被 highlight 的那一格兩面相同（這一列要的），而清單的內容兩面不同（另一條
> 規則造成的）。`G-09` 的嚴重度是 `minor`，而且**不改這一列的嚴重度**，理由還是同一個：#239 什麼都不存。
>
> **第 2 列是本輪第一次真的被執行到。** #243 到得了那個畫面但量不到東西：首頁唯一可見的圖是
> `/web/image/website/1/logo/...`，record-field image，`data-original-src` 是 `None`，所以
> `if (this.props.media.dataset.originalSrc)` 根本沒跑。#266 用 driver 自建的 website 頁面——stored arch
> 裡 `src` 與 `data-original-src` 都放同一個附件自己的 `image_src`，以 **HTML 回應**送達——量到：Ingress
> 下該屬性帶前綴、Public 下 root-relative，兩面都選中那一格；而且**點選圖片之後再讀一次**該屬性，兩面
> 都沒變。後者是必須的：`ImageTools._initializeImage` 在 `data-original-src` 載入失敗時會把整組
> `data-original-*` **刪掉**，而 `loadImageInfo` 在缺 `data-mimetype-before-conversion` 時會用 ORM 剛回
> 的 root-relative 值**覆寫**它——兩者都發生在點選與對話框之間，任何一個發生都會讓這一行變成「兩個不帶
> 前綴的值相比」而不管規則有沒有出貨都過。fixture 帶齊四個 `data-*` 就是為了這個。
>
> **第 3 列的格子量到了，而且是在舊對話框上。** 郵件設計器是還在跑舊 `web_editor` 編輯器的兩個畫面之
> 一；對話框按元素 `tagName` 自動落在 Documents 分頁（`DocumentSelector.tagNames` 是 `["A"]`），兩面都
> 選中 fixture 那一格。前提也在舊對話框上重量了一次：`served_literal_prefixed` Ingress `true`／Public
> `false`，方法長度 372 對 309，與 #243 在現行編輯器上讀到的同一個 63 bytes 差。
> **被找的那個控制項 `#media-replace` 存在但被隱藏**：`replace_control_present: true`、
> `replace_control_visible: false`、實際用的是 `dblclick`，兩面一致。原因在舊編輯器自己身上、與 Ingress
> 無關——`#media-replace` 對任何 `img, .fa, .o_image, .media_iframe_video` 都會顯示（`.o_image` 在內，
> 而且那是 snippets 側欄唯一不會把它搶走的情形），但同一個函式十二行後對「`data-mimetype` 不是圖片」的
> media **直接把整條 toolbar 藏掉**，而對話框自己的 `createElements` 必定會在 document 上蓋
> `data-mimetype`。`dblclick` 綁在同一個 selector 上且沒有這道關卡，那才是進得去的路。現行編輯器則是
> **構造上**到不了：Replace 在 `image` namespace 而 namespace 的判定要求 `IMG`，而且現行的 document
> selector 根本不再產生 `a.o_image`（改成 `span.o_file_box`，其整個子樹抑制 toolbar）。
>
> **四個 media check 現在都自己建它要量的東西，不只 #266 點名的那兩個。** #266 的頭兩次嘗試是這個決定的
> 理由，兩筆都留在 `markup.jsonl` 裡：#243 的 line 1 **pass** 與 line 3 的前提都靠手建的 fixture，收尾
> 時正確地清掉了，所以兩個讀數都不可重現——重跑時 line 1 看到的是待辦自己的圖
> `/project_todo/static/img/todo_access.png`（static module asset，背後沒有 `ir.attachment`，
> `isInitialMedia` 比不中任何東西，`ABSENT`），line 3 看到的是「description 裡沒有 `a.o_image`」。
> 現在四個 check 各自建一個 public `ir.attachment` 加一筆記錄（scratch 待辦／website 頁面／草稿 mailing
> 的 `body_arch`），`--cleanup` 全部移除，主機跑完查核為空。
>
> **本輪另外找到一個分歧，而它不是這一列的：#271。** `media-document-mailing` 在 Ingress 下 Documents
> 分頁列出 **30** 格、Public 只有 **1** 格，多出來的是產生出來的 asset bundle。原因量到了：
> `DocumentSelector.attachmentsDomain` 用 `!['url', '=like', '/web/assets/%']` 排除 bundle，而那個字串是
> **ORM domain 裡的字面值**、和被改寫的 URL 字面值住在同一包 bundle 裡，所以也被加了前綴
> （`served_domain_asset_exclusion_prefixed` Ingress `true`／Public `false`，getter 長度 383 對 320，
> 正好一個前綴）。加了前綴的排除條件比不中任何一筆 `url`，於是什麼都沒排除。**這不改這一列的嚴重度**：
> #239 管的 preselection 兩面都正確，責任規則是 #166 的通用字面規則之一，而且 domain 走的是 request
> body，什麼都不存（兩面 `stored_verdict` 都是 `CLEAN`）。真正值得處理的是那個**類別**——通用字面改寫會
> 碰到 ORM domain 的字面值而不只是 URL——由 #271 承接。

> **HTML 編輯器「把 code view 切回去」會重新插入不帶 Ingress 前綴的 markup，已於 2026-10-01 處理
> （#240，ADR 0004 的第五個 2026-10-01 附記），Live 重跑已於 2026-10-02 在 Release 0.4.10 上
> 完成（#243），兩半都過，這一列改記 `PARITY`。螢幕**不是**那一列寫的使用者簽名——該欄位在這個
> build 由 `o_field_html_mail` 提供而且編輯器是空的——而是 `ir.actions.act_window.help`；另外
> `?debug=1` 在這裡**不會**跨導覽保留，要掛在表單那一次導覽上。兩點都記在證據裡。** 這是 ADR 0004 開放清單
> 上的**第一項**，也是最後一項關掉的——`html_editor` 自己這個欄位的**第六個** markup 插入點：
> `toggleCodeView` 在切回編輯模式時直接把記錄的值塞進 editable
> （`this.editor.editable.innerHTML=this.value;`），而 #210 的五條規則沒有一條落在那一行，所以 Ingress
> 下記錄裡每個 root-relative URL 又被拿去向 Home Assistant 根要一次、回 404——跟 #210 那兩張待辦圖是
> 同一種逃脫、同一個欄位，只是從另一條路走到。修法是這個 location 上的**一條** `sub_filter`。
>
> **這一輪真正值得記下來的是三件事。**
>
> 1. **helper 必須是 `__WOOW_INGRESS_MARKUP_IN_VALUE__`（#237 那個），寫成 #210 的 `IN` 會是個「出貨
>    了、pattern 也命中了、但什麼都沒修好」的 no-op。** `get value()` 在記錄值是 `Markup` 時回傳
>    `markup(newVal)`，而每個 html 欄位的值都是 `Markup`；`IN` 對非字串原樣奉還。這不是推論：測試把
>    Odoo 自己的 `get value()` 當成**擷取下來的 fixture** 接進被驅動的 class，另外有一個測試真的把
>    「用 `IN` 寫的那條規則」跑一遍，顯示圖片還是從 Home Assistant 根要。
> 2. **這個點不存任何東西，而且這件事是**執行**出來的。** 存的是下一次 blur 的 `_commitChanges`，它讀
>    editable 再交給 `updateValue`——#210 的第 2 條規則——而 strip 只會**拿掉**前綴，所以對沒被加過前綴
>    的記錄是 no-op、對被這條規則加過的就剛好拿回來。測試把這條線整條跑過：這條規則的輸出餵進 #210
>    **出貨的** `updateValue` 位元組，讀回記錄拿到什麼（root-relative，而 `lastValue` 由實際存進去的值
>    算出）；再把同一條線餵進 Odoo **未改寫的** `updateValue`，顯示 #210 到底替這條規則擋住了什麼。所以
>    #240 兩個方向都只是 render escape，不是 token write。
> 3. **界線是「debug mode」，不是「沒有任何出貨的 view 設這個 option」——#240 與 #238 的附記都寫錯了。**
>    `codeview: Boolean(odoo.debug && options.codeview)` 兩個條件都要，而 pinned 包裡有**五個**出貨 view
>    設了這個 option、落在**四個**欄位上：`res.users.signature` 在 `base` 的兩個使用者表單裡各一次
>    （`view_users_form` 與偏好設定的 `view_users_form_simple_modif`）、
>    `ir.actions.act_window` 的 `help`（也就是 #158 那個欄位）、`mail.template` 的 `body_html`、以及
>    `hr_recruitment` 寄信精靈的 body——後兩個走 `html_mail`，是同一個欄位的子類。活下來的界線是 debug
>    mode，所以標籤維持 `severity: minor`。
>
> **還有一個會「假通過」的形狀，已在靜態層跑過，Live 要避開它。** 值 parse 後 `<head>` 非空會讓
> `sandboxedPreview` 成立（`computeContainsComplexHTML`），欄位改走唯讀 `HtmlViewer`（那是 #237 的兩條
> 規則、不是這一條），沒有 `Wysiwyg`、`this.editor` 是 undefined，於是 toggle 照按、畫面照對，而這個點
> **根本沒被走到**。`mail.template` 的 `body_html` 正是最容易是整份 HTML 的那個值。
>
> code view 自己的 textarea（`t-att-value="this.value"`）**故意不改**：source view 本來就該顯示記錄裡
> 的位元組，這跟 #238 對舊編輯器 textarea 的決定一致，而且這裡更乾淨——這個欄位的 textarea 永遠只是
> 記錄的值，`_commitChanges` 是從它讀出來存，不會回填它。有一個測試會拒絕任何提到它的 `sub_filter`。
>
> **Live（由 #243 執行，本輪已以 comment 細化該列）**：螢幕是**開著 debug mode 的偏好設定裡那個使用者
> 簽名**（最便宜：不用建任何記錄，欄位直接吃 root-relative 的 `<img>`，而且值是片段、不會踩到上面那個
> 假通過），不要拿 `mail.template` 的 body 去跑。檢查兩半：切 code view **回去**之後圖片在 Ingress
> 前綴下載入（`route_escape=0`/`http_4xx_5xx=0`/`console_error=0`，兩面一致），以及存檔之後
> `res.users.signature` 仍然是 root-relative。`U-A6` 的探測清單**不**擴充，沒有新的 global，Public
> origin 不動，Rewrite scan 不受影響（記錄內容不在 bundle 裡）。

> **網站頁「Edit this content」連結的前綴重複（`U-A2`）已於 2026-09-30 修正（#211）；Live 重跑已於
> 2026-10-01 在 Release 0.4.9 上完成（#235），改記 `PARITY`。** 連結在 Ingress 下讀到
> `<INGRESS_PREFIX>/@/shop/payment`（前綴只加一次），**點下去真的在 web client 裡打開那一頁**：
> 瀏覽器停在 route `/shop/payment`、有主導覽列，編輯器的第二個 preview frame 就是該頁本身
> （route `/shop/payment`、標題 `Shop - Select Payment Method | My Website`，裡面有
> `ecpay_invoice_website` 自己的 `.ecpay-invoice-info-form` 區塊），沒有 404、沒有 console error、
> 沒有前綴逃逸。對照組：0.4.6 上同一個連結是 `<INGRESS_PREFIX>/@<INGRESS_PREFIX>/`，點下去
> 404 在 `<INGRESS_BASE><INGRESS_PREFIX>`、編輯器停在 fallback frame。證據見
> `docs/testing/evidence/2026-10-01-issue-235/`。
>
> 以下是修法本身。`/@/<website path>` 是 Odoo 18 從網站頁進後台的 route，也是唯一一條**尾段本身就是網站
> 路徑**的 route。Odoo 把已經帶前綴的 `location.pathname` 接進那個尾段，shim 的 `path()` 只認第 0 位
> 的前綴，於是又加一次，得到 `<INGRESS_PREFIX>/@<INGRESS_PREFIX>/shop/payment`。修法是 Ingress
> asset location 上的兩條 Literal rewrite：連結改用 canonical path 組，前綴只在最前面加一次。前綴由
> 改寫本身加而不是交給 shim，是因為同一個 `currentUrl` 還餵給三個 shim 攔不到的消費點——redirect.js
> 的兩個 `window.location.replace(currentUrl.href)`（寫 `location`，ADR 0004 明言 shim 攔不到），以及
> 網站編輯器連結 popover 的 `browser.open(currentUrl)`，傳的是 `URL` 物件，shim 的 `window.open`
> 包裝只處理字串。第二條規則是 popover 自己那個「這條連結已經是後台形式」的判斷：它拿帶前綴的
> pathname 去比對裸的 `/@/`，在 Ingress 下永遠不成立。`sub_filter` 的 pattern 不能含 `${`（nginx 會
> 讀成變數，且 `$` 無從跳脫），所以 pattern 停在反引號，replacement 再補一個，讓沒被吃掉的尾段變成
> **tagged template** 的引數。該運算式在 `web.assets_frontend_minimal`、`web.assets_frontend`、
> `website.assets_wysiwyg` 三個 bundle 各出現一次，一條 `sub_filter_once off` 規則全數涵蓋。靜態層
> 契約在 `odoo18ce/tests/test_ingress_at_route_links.py`（含以真正的 nginx 依樣板本身的規則行送出
> 兩段 bundle 再比對位元組）。**Live 重跑已完成**，結果記在本附記開頭：2026-10-01 在 Release 0.4.9
> 上兩面重跑 `/shop/payment`，Ingress 記錄的 `url_literals` 讀到 `<INGRESS_PREFIX>/@/shop/payment`，
> 判定 `PARITY`（#235，見 `docs/testing/evidence/2026-10-01-issue-235/`）。

---

## 10. 待安裝 app 的預先風險登記

裝之前先讀這張表；每一項在安裝當下就要跑對應的 `U` 項目。
安裝後的操作步驟見 `odoo18ce/DOCS.md`「Generated rewrites」一節末尾的 *After installing an application* 清單。

### 10.1 銷售 / 電商 / 金流

| 模組 | 預期新增前綴 | 主要根因 | 必跑項目 |
|---|---|---|---|
| `sale_management` | `/sale/`、`/my/orders`、`/my/quotes` | RC-9 | `U-E3`、`U-E2`、`U-C20`、`U-D5` |
| `website_sale` | `/shop/`、`/shop/cart`、`/shop/checkout`、`/shop/payment` | RC-9、**RC-10** | `U-D1`–`U-D7`、`U-E6`；購物車 cookie 走 `U-B2` |
| `point_of_sale` | `/pos/`、`/pos/ui`、`/pos_self_order/` | RC-6、RC-3、RC-8 | `U-C27`（頁內離線銷售與斷網重整；實測兩邊相同，`PARITY`，#161）、`U-C24` 全螢幕、`U-C25` 掃碼、`U-F5` 收據列印 |
| 金流串接（ECPay：`ecpay_invoice_tw`、`ecpay_invoice_website`、`payment_ecpay`、`payment_ecpay_ecpg`） | `/payment/`、各 provider 專屬 return/notify 路徑 | **RC-10、RC-9** | **`U-E6`（return_url／notify_url 必須是 public 且對外可達）**；ingress 原理上無法承接回呼 → `STRUCTURAL` |

> **POS 特別警告**（2026-09-26 已由下方 #161 結果推翻，僅留作紀錄）：ingress 的 shim 主動反註冊 service worker 並偽造
> `navigator.serviceWorker`（`RC-6`）。POS 的離線模式建立在 service worker 之上，
> 因此**在 ingress 下極可能完全不可用**。安裝前必須先決定：POS 只走 public，
> 或接受 ingress 下無離線能力。這是設計決策，不是 bug 修正。
>
> **已決定（2026-09-24，ADR 0011）**：POS 兩個 surface 都可用（仍有效）；~~離線銷售是 ingress 的
> Structural gap，由 public 承接。測試時 ingress 的離線項目判 `STRUCTURAL`，並驗證 public 確實能離線。~~（已由下方結果取代）
>
> **實測修正（2026-09-24，#161）**：Odoo 18 CE 的 POS **沒有自己的 service worker**；唯一的
> `/web/service-worker.js` 範圍是 `/odoo`，只在導覽失敗時顯示離線頁。所以 `/pos/ui` 斷網重整
> 在 public 也失敗。POS 18 的離線是頁內機制：頁面已載入時斷網，會出現「Connection Lost …
> limited functionality」並可繼續操作，不需要 service worker，預期兩個 surface 相同。
> 斷網成交再同步的完整驗證尚未完成，ADR 0011 的前提待重審，都記在 #161。
>
> **結果（2026-09-26，#161）**：兩個 surface 都在頁面已載入時斷網（瀏覽器離線模擬），以現金成交一筆；
> 恢復網路後約 3 秒（第二次查詢）訂單即以 paid 的 `pos.order` 出現在同一 session → `PARITY`。斷網重整 `/pos/ui`
> 兩邊都 `net::ERR_INTERNET_DISCONNECTED` → `PARITY`。所以 POS 離線銷售**不是** ingress 的
> Structural gap，不需要 public 承接；ADR 0011 已加附記（保留「兩個 surface 都可用」的決定）。
> `RC-6` 在 ingress 仍拿走的只有 PWA 安裝與 web client 的離線頁（`U-C27` generic）。
> 證據：`docs/testing/evidence/2026-09-26-issue-161/`。

### 10.2 服務 / 行銷 / 生產

| 模組 | 預期新增前綴 | 主要根因 | 必跑項目 |
|---|---|---|---|
| `survey` | `/survey/`、`/survey/start`、`/survey/fill` | **RC-9、RC-10** | **`U-E3`（問卷分享網址欄位＋複製鈕，即你回報的現象）**、`U-C4`、`U-D6`、`U-D7` |
| `im_livechat` | `/im_livechat/`、`/im_livechat/support` | **RC-10**、RC-8 | 外嵌 script 的 `src` 不可能帶 token → `STRUCTURAL`；`U-C26` 即時 |
| `event` | `/event/`、`/my/events` | RC-9、RC-10 | `U-E3`、`U-E4`（票券 QR）、`U-D6` |
| `mrp` | `/mrp/`、`/mrp_workorder/` | RC-3 | `U-C24` 全螢幕工作中心、`U-C25` 掃碼、`U-C20` 工單 PDF |

### 10.3 人資

| 模組 | 預期新增前綴 | 主要根因 | 必跑項目 |
|---|---|---|---|
| `hr_holidays` / `hr_expense` | `/hr_holidays/`、`/hr_expense/`、`/my/` | **RC-9** | **`U-E2`（審核通知信內的連結是 token 外洩高風險路徑）** |
| `hr_attendance` / `hr_timesheet` | `/hr_attendance/`、`/hr_timesheet/` | **RC-3** | `U-C24` Kiosk 全螢幕、`U-C25` 掃 QR／條碼、`U-F1` 上界確認 |
| `hr_recruitment` | `/jobs/`、`/jobs/apply` | **RC-10** | 對外職缺頁與應徵表單只有 public 有意義 → `U-D7` `STRUCTURAL` |

### 10.4 安裝實測結果（2026-09-24，#144）

13 個計劃 app（含 `hr_timesheet`）與 4 個 ECPay 模組都已**經 Ingress 的 Apps 畫面**裝到 `odoo_parity`
（0.4.4），每次安裝後 5 分鐘內都有一輪 Rewrite scan（`unchanged` 或 `up to date`，沒有新增
Generated rewrite，也沒有通知）。ECPay 模組取自 WOOWTECH/ecpay_odoo18 `56cb04c`。
「爬蟲」欄是兩個 surface 選單爬蟲比對的結果，依選單 xmlid 的模組歸屬；證據與方法見
`docs/testing/evidence/2026-09-24-issue-144/`。

| 模組 | 爬蟲 | 必跑項目現況 |
|---|---|---|
| `sale_management` | 經 `sale` 選單，23 `PARITY`；自有畫面 3 `PARITY`（#163 以 `open` 直接開報價單表單的選購商品頁、報價範本清單與表單） | `U-E3`／`U-E2`／`U-C20`／`U-D5` → #145 |
| `website_sale` | 15 `PARITY` | `U-D1`–`U-D6`、`U-B2` → #143；`U-D7`、`U-E6` 為 `STRUCTURAL`（RC-10） |
| `point_of_sale` | 19 `PARITY` | `U-C27` 離線銷售、斷網重整各 1 `PARITY`（#161，見 10.1）；`U-F5` 收據列印、`U-C25` 商品掃描各 1 `PARITY`（#143，見 10.6）；`U-C24` 未測 |
| ECPay 4 模組 | `ecpay_invoice_tw`、`payment_ecpay` 各 1 `PARITY`；另兩個無自有選單 | `U-E6`（#146，2026-09-27）：Public origin 上一筆 stage 信用卡付款（`S00022`），綠界的回呼經 Cloudflare tunnel 抵達 `/payment/ecpay/result_notify`，交易 `done`，電子發票 `LO22046163` 已開立；回呼網址、付款回呼 2 項 `STRUCTURAL`（Structural gap），後台 4 項（金流服務商、交易、訂單表單，與發票表單上的電子發票號碼）兩端 `PARITY`；`account`／`sale` 選單爬蟲 51 `PARITY`。見 `docs/testing/evidence/2026-09-27-issue-146/`。`ecpay_invoice_website` 於 2026-09-29 由 #163 以 `open` 補上自有判定：它掛在 `website_sale.payment`，電子發票區塊（電子發票／紙本／捐贈與載具）在 `/shop/payment` 兩面都算出來、五項訊號皆 0，但該頁的「Edit this content」連結在 Ingress 下前綴重複（`<INGRESS_PREFIX>/@<INGRESS_PREFIX>/shop/payment`，`U-A2`），故記 **`GAP`（important）**；該連結不限結帳頁，每個可編輯的網站頁都有。見 `docs/testing/evidence/2026-09-29-issue-163/`。**該 `GAP` 已於 2026-09-30 修正（#211），並於 2026-10-01 在 Release 0.4.9 上由 #235 完成 Live 重跑，這一列改記 `PARITY`**（見 9 的附記）：`/shop/payment` 在 `open-diff.jsonl` 為 `PARITY`，Ingress 側的 `url_literals` 讀到 `<INGRESS_PREFIX>/@/shop/payment`、Public 側讀到 `<PUBLIC_BASE>/@/shop/payment`，兩面五項訊號仍全為 0，電子發票區塊兩面照樣算出來。見 `docs/testing/evidence/2026-10-01-issue-235/` |
| `survey` | 4 `PARITY`、**2 `GAP`**（同一動作） | 範例圖片逃逸 → **#158**；`U-E3`／`U-C4` → #145 |
| `im_livechat` | 8 `PARITY` | 外嵌 script 為 `STRUCTURAL`（RC-10）；`U-C26` → #143 |
| `event` | 7 `PARITY`、**1 `GAP`** | 報到台條碼音效逃逸 → **#159**；`U-E3`／`U-E4` → #145 |
| `mrp` | 8 `PARITY` | `U-C24`／`U-C25` → #143；`U-C20` → #145 |
| `hr_holidays` / `hr_expense` | 13 / 8 `PARITY` | `U-E2` → #145 |
| `hr_attendance` / `hr_timesheet` | 5 / 7 `PARITY` | `U-C24`／`U-C25`／`U-F1` → #143 |
| `hr_recruitment` | 14 `PARITY` | 對外職缺頁 `U-D7` 為 `STRUCTURAL`（RC-10） |

第 9 節的 13 個 app 同一輪已比對的選單全為 `PARITY`（`project_todo` 只有一個跳過的 server action，其畫面於 2026-09-29 由 #163 的 `open` 另判：2 `PARITY` + 1 `GAP`，**該 `GAP` 已於 2026-10-01 由 #235 在 0.4.9 上重跑為 `PARITY`，三個畫面全數 `PARITY`**），唯一例外是 `website` 的訪客清單：經 Ingress 瀏覽網站時，
訪客紀錄把 HA 根網址存成頁面 URL（`U-C5`，#160）——**此例外已於 2026-10-01 在 0.4.9 上消除（#235），動作 596 兩面 `PARITY`**。
> #160 的修正（server-wide module `woow_visitor_url`，把訪客追蹤存下的網址改建在 **Canonical URL** 上，`website.get_base_url()`）
> 在 Static 與 Build tier 通過，但 **2026-09-30 於 0.4.6 測試主機的 Live 重跑判定 `FAIL`**：經 Ingress 開一次首頁後，
> 新存的 `website.track` 仍記錄完整的 HA 根網址（`http://192.168.50.192:8123/`，重啟後重測一致），動作 596 的爬蟲比對仍是 `GAP`。
> 存的是**未修改的完整** `request.httprequest.url`。當時判讀為「模組 `import website` 失敗、走了原樣放行的 fallback」，
> **2026-09-30 在主機上查證後推翻**：容器內 `/data/odoo/logs/odoo-server.log` 每個 worker 都有
> `website.visitor._handle_webpage_dispatch patched`，而每一次 Ingress 頁面瀏覽之後都緊接著模組自己的
> `the request's url could not be replaced` 警告 —— patch 確實生效，空操作的是**換網址那一步**。
> 原因是 `request.httprequest` 不是 werkzeug request，而是 `odoo.http.HTTPRequest`：Odoo 為每個轉發屬性（含 `url`）在 wrapper 上裝一個純
> `property`（`make_request_wrap_methods`），純 `property` 是 data descriptor，永不讀 instance `__dict__`，所以舊版寫進
> `vars(httprequest)["url"]` 的值沒人讀得到；改成 `httprequest.url = …` 則會經 wrapper 的 setter 寫進被包住的 werkzeug request
> （其 `url` 是 `cached_property`，`__set__` 會填快取）。修法即改為指派，並在 dispatch 之後把原本的網址寫回
> —— wrapper 的轉發屬性沒有 deleter，所以不是刪快取而是寫回同一個網址。
> Build tier 的 in-image probe 現在除了讀旗標，也在映像自己的 `odoo.http.HTTPRequest` 上真的換一次網址再讀回來，
> 這正是 0.4.6 當時 Build 綠、主機無效的那一半。這仍是 Build-tier 與真實主機的環境差異，正是 Live tier（ADR 0012）存在的理由。
> 證據：`docs/testing/evidence/2026-09-30-issue-160/`。既有紀錄不回填。
>
> **Live 重跑已於 2026-10-01 在 Release 0.4.9 上完成（#235），這一列改記 `PARITY`。** 判定前先讀了
> 這個修正所依賴的基底——預設網站的 `domain`、`web.base.url` 系統參數、`website.get_base_url()`
> 三者都是 **Canonical URL**（`web.base.url.freeze` 為 `True`），所以不存在「基底本身就是 HA 位址、
> `tracked_url` 原封不動回傳、`stored == arrived` 提早返回而什麼都不記」的那種無聲失敗。
> 經 Ingress 開一次首頁後新存的 `website.track`（列 258）記的是 **Canonical URL** 加路徑 `/`，
> 不是 HA 位址、也不是只有路徑（只有路徑就代表基底是空的）。動作 596 的爬蟲比對為 `PARITY`、
> severity `none`、兩面都沒有 `url_violations`：畫面上每一個訪客網址都讀作 `<PUBLIC_BASE>`，
> 包含 0.4.6 當時讀作 `<HA_BASE>` 的那四個（`/`、`/contactus`、`/jobs/…job-3`、`/shop/…service-58`）。
> add-on 自己的 log 也從裡面說了同一件事：0.4.9 啟動後每個 worker 都有
> `website.visitor._handle_webpage_dispatch patched`，而 Deploy 之後
> `the request's url could not be replaced` 一次都沒有（檔案裡的 12 次全在 Deploy 前的 0.4.6 對照組），
> `could not be put back` 從頭到尾 0 次。
>
> 判定的前提是把舊列清掉：#160 決定**不回寫**舊列，而那些列就在動作 596 打開的畫面上，所以
> 2026-10-01 這一輪先把 **88 筆**帶 HA 位址的 `website.track` 匯出再刪除（`9`–`253`，涵蓋 Issue 點名的
> `226`／`227`／`239`–`243`，也涵蓋它沒點到的 `236`–`238` 與 #143／#144 留下的 78 筆）。沒有任何一列被
> 回寫。證據與列號見 `docs/testing/evidence/2026-10-01-issue-235/`。

### 10.5 本輪未覆蓋的已知風險（明列，不假裝測過）

| 項目 | 為何重要 | 處置 |
|---|---|---|
| HA 手機 App WebView | WebView 版本、剪貼簿權限、下載、新分頁行為都與桌機 Chrome 不同；多數 ingress 獨有 bug 只在此浮現 | 下一輪納入；本輪結論不得外推到 App |
| 行動版視窗（390×844） | Odoo 切換到行動版 layout，選單與對話框行為不同 | 桌機 Chrome 的行動版模擬已於 2026-09-25 跑過選單爬蟲（#143，見 10.6）；實機仍未覆蓋 |
| Safari／非 Chromium | 第三方 cookie、SharedWorker、clipboard 限制不同 | 同上 |
| 開發者模式差集 | 由 `docs/plans/2026-09-05-odoo-developer-mode-delta-tdd.md` 承接 | 交叉引用，不重複 |

### 10.6 共用層實測結果（2026-09-25，2026-09-27／28／29 補跑，#143／#201／#203）

F、A、B、C、D 群組在 `odoo_parity`（0.4.4）各跑一次，外加 10.1–10.3 指定的模組畫面；Ingress 端是 HA 前端
面板裡的 iframe（plain-http LAN 入口），`U-C25` 走 https 入口。`U-D8` 拆成兩筆後共 76 項 = 54 `PARITY` + 7 `GAP`
+ 2 `APPROVED-DIVERGENCE` + 6 `STRUCTURAL` + 7 `NOT-RUN`；每個 `GAP` 都有 issue（#159、#165–#167、#169、#170）。
POS 兩項在 #161 之後於 2026-09-27 補跑，收據列印（`U-F5`）與相機掃描（`U-C25`）兩端皆 `PARITY`；同次補跑 P-Check
全數通過，`U-D8` 當時仍為 `GAP`（`sitemap.xml` 跟著請求位址走，#172）。
`U-D8` 於 2026-09-27 再補跑一次並拆成兩筆（#172）：head 連結與 `robots.txt` 是 `PARITY`，`sitemap.xml` 是
`APPROVED-DIVERGENCE`（`AD-8`），上面的數字已含這兩筆。#143 那一輪自己的證據檔保留它當時記錄的數字；這兩筆記錄與
重算後的守恆報告見 `docs/testing/evidence/2026-09-27-issue-172/`。
`U-C23` 於 2026-09-28 以 #168 的新規則補跑一次（#183）：新分頁的位址必然帶 token 是 `STRUCTURAL`（RC-15，`G-07`，severity
`none`，`public_path` 為 `<PUBLIC_BASE>/survey/<token>`）。Ingress 分頁在 `<HA_BASE><INGRESS_PREFIX>/survey/<token>`、public 分頁在
`<PUBLIC_BASE>/survey/<token>`，兩邊開的是同一頁；同次補跑 P-Check 全數通過（P-5 是 public 分頁位址的比較基準）。`#168` 因此不再是 `GAP` 的 issue。這一輪會寫入 Odoo 資料（P-7 問卷 fixture、Test 按鈕產生的問卷作答），依 ADR 0012 授權；#143 那一輪
自己的證據檔保留它當時記錄的 `GAP`／`important`。這一筆記錄與重算後的守恆報告見 `docs/testing/evidence/2026-09-28-issue-183/`。

`U-A1`、`U-A6`、`U-B2`、`U-D2`、`U-D6` 五項與 outbound 的 `U-E4` 於 2026-09-29 在 Release **0.4.5** 上補跑（#201，run
`WOOW-PARITY-20260929T040919Z`）。0.4.5 是 2026-09-28 sweep（PR #192–#199）修正的第一個有 `public_url` 的 Release，前此無法做兩面判定。
五項共用層 check 全數由 `GAP` 轉 `PARITY`（分別對應 #166、#169、#165、#170、#167），`U-B2` 的 Public `session_id` 在 bus socket 開啟後
讀到 `Secure=True／SameSite=Lax／Path=/`（原 RC-4 的 `GAP`）；`U-E4` 的發票 Download > PDF 在 Ingress 下正常下載、`route_escape=0`（#174
的 RC-1 逃逸已消失），活動票券 PDF 兩面 `PARITY`，發票列的 verdict 因台灣 CE 無 QR 付款法（#146）仍記 `NOT-RUN`（僅 QR 內容維度被擋）。
重算後 76 項 = **60 `PARITY` + 1 `GAP` + 2 `APPROVED-DIVERGENCE` + 6 `STRUCTURAL` + 7 `NOT-RUN`**；唯一剩下的 `GAP` 是 `U-C25`（報到台
媒體來源，issue **#159**），不在 #201 範圍內，其 Live 補跑與 `U-A6` 媒體途徑探測仍待辦。這一輪記錄與守恆報告見
`docs/testing/evidence/2026-09-29-issue-201/`。

`U-C25` 於 2026-09-29 在 0.4.5 上補跑（#203，run `WOOW-PARITY-20260929T045315Z`，經 `HA_HTTPS_BASE_URL` 的 https 入口＋Chromium fake camera）。
報到台這一畫面兩個 surface 都沒有相機控制項可按，故 verdict 記 `NOT-RUN`（非 Ingress 專屬，`no camera control` 兩面皆然）；但**使這筆成為 `GAP` 的訊號已消失**：
#143 那次（run `WOOW-PARITY-20260925T043539Z`）Ingress 側於載入報到台時 `route_escape=1`、`console_error=1`（#159 修的 `new Audio(url("/barcodes/…"))` 錯誤音效逃逸），
0.4.5 上兩面皆 `route_escape=0`、`console_error=0`——#159 的媒體來源包裝已生效。`U-C25` 的其餘畫面（generic、`hr_attendance`、POS）維持 `PARITY`，`mrp` 同報到台記
`NOT-RUN`（無相機控制項）。重算後 76 項 = **60 `PARITY` + 0 `GAP` + 2 `APPROVED-DIVERGENCE` + 6 `STRUCTURAL` + 8 `NOT-RUN`**，`GAP` 清空。這一輪記錄與守恆報告見
`docs/testing/evidence/2026-09-29-issue-203/`。#203 的另一半——把媒體來源加進 `U-A6` 探測清單（`RC-12` 附記）——亦於同日完成：`U-A6` 新增一條 covered 途徑
`media`，同時走 `new Audio`／`HTMLMediaElement.src`／`HTMLSourceElement.src`，在 0.4.5 上重跑該途徑有發出請求且未逃逸、`U-A6` 維持 `PARITY`（run
`WOOW-PARITY-20260929T053445Z`，見 `ua6-media-checks.jsonl`）。
2026-10-01 在 Release **0.4.9** 上又補跑了六項（#235）：#210 的待辦表單兩項、#211 的「Edit this content」兩項、
#160 的訪客網址兩項，六項全過。**這一輪不動上面那 76 項的守恆數字**，因為這六項都不在共用層那一組裡——
它們是第 9 節以 `open` 另判的畫面（`project_todo`、`ecpay_invoice_website`）與第 10 節 `website` 的動作 596，
各自的列已在上面改記 `PARITY`。所以 76 項維持 **60 `PARITY` + 0 `GAP` + 2 `APPROVED-DIVERGENCE` +
6 `STRUCTURAL` + 8 `NOT-RUN`**。

2026-10-02 在 Release **0.4.10** 上跑了 Ingress markup 這一族欠的五列（#243）：#237 四項、#238 三項、
#240 兩半、#239 三行中的一行、#234 兩個 pair。**這一輪同樣不動上面那 76 項的守恆數字**，理由與 #235
那一輪相同——這些都是第 9 節各自那一列的 Live 欄，不是共用層那一組，所以 76 項仍維持
**60 `PARITY` + 0 `GAP` + 2 `APPROVED-DIVERGENCE` + 6 `STRUCTURAL` + 8 `NOT-RUN`**。這一輪的判定
schema 是第 12 節新登記的 `woow.ingress-markup/v1` 與既有的 `woow.peer-snapshot.v1`，兩者都**不**進
`conservation`。證據在 `docs/testing/evidence/2026-10-02-issue-243/`（`markup.jsonl` 38 筆、`peer.jsonl`
2 筆；同一個 check 與 surface 以**最後一筆**為判定，先前各次嘗試一併保留，因為那是當時真的讀到的東西）。
這一輪沒有留下 `.ambient.json`——這兩個 driver 不是 adapter，不數 `website.track`／`website.visitor`，
缺口見 #264。**事後附記**：#264 已經把那份記帳補進這三個 driver（markup 驅動、peer snapshot 的 `run`
與 `probe`、hand checks），所以缺的是當時的器材而不是當時的判斷；這一輪自己的證據目錄仍然沒有
`.ambient.json`，那是它當時真的留下的東西，不改寫——要帶著那幾行的是這一族的**下一次**跑。
另有三項仍欠：#234 的傳輸從未送達（#265）、#239 的另外兩行（#266），以及 `probe`
其實會寫入（#263）。**事後附記（#265，2026-10-02）**：第一項已結，#263 也已結。#265 在**同一個
Release 0.4.10**、同一台主機上重跑 #234 那一列，兩個 pair 都送到了，`ingress-ingress` 在送到的前提下
仍 `CLEAN`，`ingress-public` 則量到 Public peer 把 Ingress 前綴存進了記錄、再由下一次 Ingress 存檔治
好（登記為 `G-08`）。**這一輪的 76 項守恆數字同樣不動**，理由與本段上面相同：那是第 9 節 #234 那一列
的 Live 欄，不是共用層那一組，所以仍維持 **60 `PARITY` + 0 `GAP` + 2 `APPROVED-DIVERGENCE` + 6
`STRUCTURAL` + 8 `NOT-RUN`**；`G-08` 是第 11 節的落差登記，不是 plan item，不進分母。#265 自己的證據
在 `docs/testing/evidence/2026-10-02-issue-265/`，本輪這個目錄的記錄不改寫。

**事後附記（#266，2026-10-02）**：第二項也結了，在**同一個 Release 0.4.10**、同一台主機上，不需要重新
發版也沒有重新部署——#239 的三條規則早就在 0.4.10 裡，而本輪自己讀到
`rule_in_served_method` 與 `legacy_rule_in_served_method` 在 Ingress 都是 `true`、在 Public 都是
`false`，所以「規則有沒有到瀏覽器」是量到的而不是從版號推的。#239 欠的兩行都量到且都過：website 那
一行用 driver 自建的 website 頁面（stored arch 以 HTML 回應送達，`data-original-src` 在 Ingress 帶
前綴、在 Public root-relative，兩面都選中），document 那一行的格子在**舊**對話框（郵件設計器）上量到
（兩面都選中；被找的 `#media-replace` 存在但被隱藏，實際進得去的是 `dblclick`），現行編輯器維持
**構造上到不了**並附理由。#239 那一列因此改記 `PARITY`。**這一輪的 76 項守恆數字同樣不動**，理由與本段
上面兩次相同：那是第 9 節 #239 那一列的 Live 欄，`woow.ingress-markup/v1` 也**不**進 `conservation`，
所以仍維持 **60 `PARITY` + 0 `GAP` + 2 `APPROVED-DIVERGENCE` + 6 `STRUCTURAL` + 8 `NOT-RUN`**。
本輪另外找到一個分歧，登記為第 11 節的 **`G-09`** 並由 **#271** 承接（Ingress 下 Documents 分頁列出所有
asset bundle，因為通用字面改寫把 `attachmentsDomain` 裡的 `'/web/assets/%'` **ORM domain 字面值**也加了
前綴，getter 長度 383 對 320）——那不是 #239 的規則，也不改 #239 的嚴重度，什麼都不存。`G-09` 的嚴重度
是 `minor`，而且與 `G-08` 一樣是第 11 節的落差登記、不是 plan item，所以上面那個 **0 `GAP`** 的數字也不
為它而動。依 #266 的驗收條件，這個分歧同時以 comment 回報在 **#239** 上。
**這也是這一族第一次留下 `.ambient.json`**，就是上面那句「要帶著那幾行的是下一次跑」所指的那一次：
22 行對 22 筆記錄，`website.track` 與 `website.visitor` 的 delta 每一行都是 **0**（含網站編輯器那個
check 的每面 5 次 navigation），兩側絕對值 198／59 與 #243 跑完在主機上讀到的同兩個數字相同。
這是**記帳不是判定**：`diff` 不讀它，76 項的守恆數字不為它而動。證據在
`docs/testing/evidence/2026-10-02-issue-266/`（`markup.jsonl` 22 筆、`markup.ambient.json` 22 行；
同一個 check 與 surface 以**最後一筆**為判定，前兩次嘗試一併保留，因為那兩筆正是「#243 的 fixture 是手
建而且已清掉，所以它那兩個讀數不可重現」的證據——四個 media check 現在都自己建它要量的東西，
`--cleanup` 全部移除）。#243 的證據目錄只加附記，不改寫。

這一輪另外跑了 `crawl --apps website` 兩面比對（30 判定 = 30 `PARITY`、
1 跳過）與 #163 全部七個 target 兩面比對（7 判定 = 7 `PARITY`），後者是刻意跑整個 target 檔而不是只跑三行：
0.4.9 是第一個部署 #238 那 182 行 Literal rewrite 的 Release，規則若在不該觸發的頁面觸發，會在無關 target 上
顯示為字面值改變——沒有任何一個改變。證據見 `docs/testing/evidence/2026-10-01-issue-235/`。

`NOT-RUN`：`U-A9`（無 60 秒以上的動作）、`U-C22`（只有一種語言）、`/event` 與活動報名
（未裝 `website_event`）、CE 沒有該控制項的三個模組畫面（MRP 工作中心與工單、出勤 kiosk 全螢幕）。證據與方法見 `docs/testing/evidence/2026-09-25-issue-143/`。

- **`U-F1` 上界**：Ingress iframe 與 HA **同源**，沒有 `allow`、沒有 `sandbox`，政策全部放行；唯一限制是
  plain-http 不是安全環境（clipboard-write、camera、microphone）。`G-02` 的未知因此有答案：HA 沒有擋，
  複製鈕靠 #60 的 fallback，相機要 https 入口（實測可用）。
- 390×844 行動版模擬爬蟲：299 個選單 = 281 `PARITY` + 4 `GAP` + 14 跳過，4 個 `GAP` 就是桌機已登記的
  #158、#159、#160，行動版沒有新增。三者今日皆已修正並在主機上重跑過（#158 於 0.4.5、#159 於 0.4.5、
  #160 於 0.4.9），行動版本身沒有重跑——那是 `#147`，要真實裝置。
- 2026-09-25 當時 P-5 未過：`website` 在 add-on 啟動後才安裝，`website.domain` 空白到下次重啟（#164），`U-D8` 因此是 `GAP`；2026-09-27 兩次補跑 P-5 都已 PASS。


### 10.7 對外產出物實測結果（2026-09-25／26，#145）

E 群組（`U-E2`、`U-E3`、`U-E4`、`U-E5`、`U-E7`）與 `U-D8` 在 `odoo_parity`（0.4.4）上，每種產出物
都從兩個 surface 的 UI 各產生一次。25 項 = 22 `PARITY` + 2 `GAP` + 1 `NOT-RUN`，每個 `GAP` 都有 issue。
`NOT-RUN` 是發票的 QR：台灣公司在 CE 沒有 QR 付款方式，ECPay 電子發票要先開立（#146）。本輪因此不算完整。
（2026-09-27：#146 已在 `odoo_parity` 開出電子發票 `LO22046163`，發票 `INV/2026/00002`；這一項可以重跑，尚未重跑。）
E 群組的判定**不只比較兩邊**：產出物裡只要有 HA 位址、相對 URL 或 Ingress token 就是 `GAP`，
兩邊一樣錯也一樣。證據與方法見 `docs/testing/evidence/2026-09-25-issue-145/`。

- **郵件**：攔截用的 SMTP sink 在 add-on 容器內（只收、不轉寄），收件者一律是
  `e2-<what>-<surface>@example.invalid`。檢查的郵件有邀請、密碼重設、chatter 通知、群發（追蹤連結、
  退訂、追蹤像素）、請假與費用審核。所有連結都在 Canonical URL 上。
- **分享對話框**：共 10 個。portal.share 四個（報價、發票、採購、任務），另有專案、問卷、儀表板、
  Discuss 邀請、Live Chat 連結、會議 URL。全部在 Canonical URL 上，匿名瀏覽器都打得開。
- **附件**：寄出的附件變成 `/web/content/…?access_token` 連結，在 Canonical URL 上。
- **匯出**：link tracker 與會議的 xlsx、csv 匯出也都在 Canonical URL 上。
- **QR**：活動票券的 QR 內容是報名條碼，不是 URL。發票沒有 QR，所以發票的 QR 檢查是 `NOT-RUN`。
- **區網外可達性**：允許匿名存取的 34 個連結，都從 LAN 外的雲端瀏覽器（browserless）再開一次，全部打得開。
- **沒有測到的部分**：密碼重設送出的是「邀請信」（測試使用者沒有登入過），連結格式相同。`U-E5` 只測了郵件附件連結。
- **`GAP`**：
  - 發票「Download > PDF」在 Ingress 下請求 HA 根目錄，404，檔案沒有下載（#174）。「PDF without Payment」兩邊都正常。
  - Ingress 下的 `sitemap.xml` 仍以 HA 為基底（#172）。首頁 head 與 `robots.txt` 已是 Canonical URL，也就是 #164 修好了。這一項自 2026-09-27 起由 `AD-8` 收錄為核准分歧，`U-D8` 也拆成兩筆（#172）。

---

## 11. 已確認的落差登記

> 以下 `G-xx` 為 add-on 層或結構層的落差，經對照現行 `main` 程式確認，與特定主機的
> 即時狀態無關。主機層設定（`web.base.url` 現值、`website.domain`、`default_db`）由第 2.3 節
> P-Check 於執行前實測，不在此登記。

| ID | 落差 | 嚴重度 | 根因 | 證據 | 建議處置 |
|---|---|---|---|---|---|
| `G-01` | add-on 的 maintenance bootstrap 只在 `public_url` **且** `default_db` 皆設定時才寫入 `web.base.url` 並設 `web.base.url.freeze`；Ingress-only 安裝或未設 `default_db` 時**完全無防護**，且任何形態下都不設定 `website.domain` | **Blocker** | RC-9 | `odoo18ce/rootfs/usr/local/bin/odoo-maintenance-bootstrap`（`if public_url:` 區塊）、static tier 僅有字串存在檢查 | 未 freeze 時 Odoo 會在 admin 登入時把 `web.base.url` 覆寫成當次請求基底——**從 ingress 登入一次，token 就會被寫進所有分享連結與寄出的郵件**。修法：bootstrap 對所有 DB 逐一處理；有 `public_url` 用它，否則用 HA 的 LAN 位址，取不到則只上鎖不改值；同時設定 `website.domain`；補 static tier 測試。追蹤 #57 |
| `G-02` | 分享對話框的複製鈕在 ingress 可能無反應：`navigator.clipboard.writeText` 在 cross-origin iframe 需要宿主授予 `allow="clipboard-write"`，HA 是否授予**未知** | **Important** | RC-3 | 結構性假設，待 `U-F1` 實測 | 先跑 `U-F1`：**有**授權→查 Odoo 端呼叫時機；**沒有**→ nginx shim 注入 `execCommand('copy')` 或「點擊即全選」的退路。網址欄位值錯誤屬 `G-01` 下游，不在此列。追蹤 #60 |
| `G-03` | nginx Literal rewrite 的前綴清單只有 8 個前綴，計劃安裝的 12 個 app 至少引入 15 個新前綴 | **Important**（安裝時觸發） | RC-11 | `odoo18ce/rootfs/etc/nginx/nginx.conf.template` `location ^~ /web/assets/` | **處置中（#58）**：ADR 0004 決定不擴清單也不泛化（0.3.10、0.3.34 兩次翻車）；`U-A4` 已實作為 `odoo18ce/tests/e2e_literal_rewrite_gate.py` ，曾納入發版守門與每晚 workflow（每晚排程已依 ADR 0005 取消，只留手動觸發）。首次對 .6 test（4 apps）執行：0 個未登記 `FAIL`，`/scoped_app` 以例外命中，清單外前綴全部為 `WARN`／`INFO`。**機制已改造並出貨（ADR 0005，#74）**：add-on 內建 Rewrite scan 在執行期把 `FAIL` 等級前綴寫成 Generated rewrite，不再靠擴充模板清單；第 9／10 節 app 分批安裝後仍可用 `--include-file` 手動跑一次守門驗收（#81） |
| `G-04` | `@web/core/utils/urls` 的 `url()`／`getOrigin()` 在 Odoo 18 一律退回瀏覽器的 protocol + host（session info 無 `origin` 欄位），而同一個函式同時組出 `/web/image`、`/web/content` 等**站內**位址 | **Important** | RC-9 | `.6` 服務的 `web.assets_backend`：`getOrigin()` 取 `browser.location` 的 `protocol`／`host`，`url()` 以 `getOrigin(options.origin ?? session.origin)` 取基底 | **`STRUCTURAL`**（ADR 0006）。改寫這個共用函式會把站內位址一起變成絕對公開網址並離開 Ingress，正是 ADR 0006 否決「改寫 `session.origin`」的理由。承接路徑：凡經 `url()` 組出、要給外人開的網址，一律從 **Public origin** 產生。2026-09-22 盤點 `.6` 實際服務的 15 個 bundle，目前沒有任何對外分享連結走這條路；日後若出現，逐一評估能否以精確表達式補丁，否則留在本列。追蹤 #70 |
| `G-05` | ~~Ingress-only 且 Supervisor 取不到 LAN 位址（Canonical URL 為空）時，Website 分享 snippet 仍把 `location.href` 交給社群網站，其中含 Supervisor 的 ingress token~~ **已修正（2026-09-23）** | ~~**Important**~~ | RC-9 | `nginx.conf.template` 的 `const currentUrl=` 補丁現在**無論有沒有 Canonical URL 都剝掉 ingress 前綴** | ADR 0006 已補一段修正，把這條列為「空值即今日行為」的唯一例外：今日行為是把憑證交給第三方，那不值得保留。無 Canonical URL 時連結仍指向 HA 主機、仍然打不開，但不再帶 token。另兩條補丁不受影響。促成重審的是 #108——空值的形態比原先估計的容易達到 |
| `G-06` | ~~add-on 啟動**之後**才安裝 `website`（例如從 Apps 畫面裝），預設網站的 `domain` 一直是空的，直到下一次重啟；Ingress 下首頁的 `canonical`／`og:url`／`og:image`／`twitter:image` 與 `sitemap.xml` 因此以 HA 位址為基底~~ **已修正並在測試主機驗證（2026-09-25，`docs/testing/evidence/2026-09-25-issue-164/`）** | ~~**Important**~~ | RC-9 | `odoo-maintenance.py` 只在 add-on 啟動當下 `website` 已在 registry 時才寫 `website.domain`（「website module not installed」）；#143 跑 `odoo_parity` 時 `P-5` FAIL、`U-D8` GAP | Rewrite scan service 每輪多一步 **Canonical URL catch-up**（`odoo-canonical-catchup`）：以 `psql` 讀每個資料庫的預設網站 `domain`，空值或與 Canonical URL 不同時，才用同一支 maintenance library 經 `odoo shell` 補寫；穩態每輪不載入 registry。add-on log 出現 `maintenance db=<name>: … website.domain=<Canonical URL>`。追蹤 #164；Ingress 下 `sitemap.xml` 仍跟著請求位址走，已由 `AD-8` 收錄為核准分歧（#172） |
| `G-07` | Odoo 自己在瀏覽器開出的新分頁（問卷的 Test 按鈕、任何開新分頁的連結、「在新分頁開啟」），在 ingress 下位址必然是 `<HA_BASE><INGRESS_PREFIX>/…`，帶著 Supervisor 的 ingress token（是 add-on 的那一份；per-user 的 session 走 cookie，見 `RC-15`） | **`STRUCTURAL`**（原始發現記為 Important；依第 1.4 節，證據記錄的 severity 為 `none`） | RC-15 | `docs/testing/evidence/2026-09-28-issue-183/checks.jsonl` 的 `check:U-C23\|shared\|generic`（run `WOOW-PARITY-20260928T070408Z`，2026-09-28，#183）：verdict `STRUCTURAL`、severity `none`、`public_path` `<PUBLIC_BASE>/survey/<token>`；ingress 分頁在 `<HA_BASE><INGRESS_PREFIX>/survey/<token>`，public 分頁在 `<PUBLIC_BASE>/survey/<token>`，兩邊開的是同一頁。原始發現見 `docs/testing/evidence/2026-09-25-issue-143/checks.jsonl`（run `WOOW-PARITY-20260925T043539Z`）：同樣的形態，但記於決定之前，verdict 仍是 `GAP`／`important` | **Public origin 承接**：ingress 的每一個頂層頁面都在 Supervisor 路徑之下，新分頁因此只有兩種結果——帶 token，或離開 Ingress 去別的 origin。Runtime shim 只夠得到 `window.open`，`target="_blank"` 錨點、中鍵與「在新分頁開啟」走的是 `href`，而 `href` 必須保持前綴才能在頁內導覽；分頁落到別的 origin 還要求第二次登入，LAN fallback 下離開內網就打不開，通道斷線時也打不開。ADR 0006 對 Ingress 內位址的判斷相同，故不改 shim、不改 Literal rewrite；要給別人開的同一個畫面，從 Public origin 取位址分享。使用者文件見 `odoo18ce/DOCS.md`「What only the Public origin can do」。決定本身見 #168（已關閉）；依新規則的補跑已於 2026-09-28 完成（#183） |
| `G-08` | 協作中的 Public origin peer 會把 Ingress 前綴存進 `project.task.description`：To-do 的 description 是 `'collaborative': true`，後加入的 peer 會拿到先加入那個 peer 的整份文件當 snapshot，而 Public 那一面沒有 shim 也沒有 rewrite（ADR 0003 的對照組），收到什麼就存什麼。記錄裡那串是 add-on 的 `ingress_token`（不是 session secret，見 `RC-15`） | **Important**（§1.3 的「**ingress token 外洩**」本身是 Blocker；2026-10-02 由 **#234 裁定維持 `important`**：寫入已確認，而下一次 Ingress 存檔會把它清掉，所以真正未解的只有「再也沒有 Ingress 存檔的那一筆記錄」，見「建議處置」）。**不是 `STRUCTURAL`**：§1.4 要求結構性落差指定「由 public surface 承接」的替代路徑，而這一列的 public surface 正是寫入的來源，沒有承接可指，所以不走那條路 | RC-15 | `docs/testing/evidence/2026-10-02-issue-265/peer.jsonl` 的 `ingress-public` 一列（run `WOOW-PEER-20261002T064500Z`，2026-10-02，#265，Release 0.4.10）：`transport.delivered: true`、peer 存檔後 `verdict` 為 `FOREIGN-PREFIX-STORED`、`stored_prefixes: ["A"]`，兩張圖的 `src` 都在 `/api/hassio_ingress/<ingress:A>/project_todo/static/img/…`；接著 `healing.verdict` 為 `CLEAN`、`loaded_prefixes: ["A"]`，兩個 `src` 回到根相對路徑。同一輪的 `ingress-ingress` 在送到的前提下仍 `CLEAN`。第一次嘗試（`peer-first-attempt.jsonl`）的傳輸讀數因 marker 撞號而**作廢**，一併保留 | **下一次 Ingress 存檔治好，擋不住**：Ingress 這邊的 strip 掛在欄位唯一的寫入點（`HtmlField.updateValue`，#210／#238），能做的是把載入值裡任何符合 `$safe_ingress_path` 形狀的前綴去掉（#234），而 Public origin 的那次寫入在另一個 surface 上，ADR 0003 不改它。所以殘留風險是**一筆再也沒有 Ingress session 存過的記錄**：在下一次 Ingress 存檔之前，token 就在那一列裡。量測由 `e2e_collab_peer_snapshot_live.py run --pair ingress-public` 的兩段式讀取維持，`report` 以 `foreign_prefix_healed` 單獨列出、不併進 clean 數。#234 的 severity 要不要因此改（它自己的驗收條件說「確認存到 foreign token 就升 `blocker`」，而現狀是「確認存到、而且被治好」）留給 #234 自己決定；本列只登記量到的東西。見 #265 |
| `G-09` | ~~Ingress 下媒體對話框的 Documents 分頁把**所有產生出來的 asset bundle** 都列成文件：`DocumentSelector.attachmentsDomain` 以 `!['url', '=like', '/web/assets/%']` 排除它們，而那是 **ORM domain 裡的字串字面值**、和被改寫的 URL 字面值住在同一包 bundle 裡，所以也被加了前綴；加了前綴的排除條件比不中任何一筆 `url`，於是什麼都沒排除~~ **已修正並在測試主機驗證（2026-10-03，#271，`docs/testing/evidence/2026-10-03-issue-271/`）**。那個**類別**也一併記進 ADR 0004：通用字面改寫碰得到 ORM domain 的字面值而不只是 URL，而**搜尋樣式不得被加前綴** | ~~**Minor**~~（原記：什麼都不存——domain 走 request body，兩面 `stored_verdict` 都是 `CLEAN`——也沒有離開前綴；影響是選取器裡的一份錯清單，第一頁 30 格被 bundle 佔滿。**不是 `STRUCTURAL`**：不是原理上做不到，而是一條規則命中了不該命中的字面值） | RC-1（#166 的通用字面改寫） | **原始發現**：`docs/testing/evidence/2026-10-02-issue-266/markup.jsonl` 的 `media-document-mailing` 兩筆（run `WOOW-MARKUP-20261002T074704Z`，2026-10-02，#266，Release 0.4.10）：Ingress `dialog.tiles` 30、Public 1，兩面 `dialog.tiles_selected` 都是 1；`operand.served_domain_asset_exclusion_prefixed` Ingress `true`／Public `false`，`operand.served_domain_length` 383 對 320（正好一個前綴 63 bytes）。**修正後**：`docs/testing/evidence/2026-10-03-issue-271/markup.jsonl`（run `WOOW-MARKUP-20261003T124016Z`，2026-10-03，#271，**本地建置** `local_odoo18ce` `0.4.10-202610031232`，DB `catchup164b`，只有 Ingress——依 #271 的 brief 不發版，Public 那一面不受這個修法影響且已由 #266 量過）：`served_domain_asset_exclusion_prefixed` **`false`**、`served_domain_has_web_assets_literal` 仍為 `true`、getter 長度 **320**（與 Public 同、也與靜態 fixture 同長），`dialog.tiles` **1**、`tiles_selected` 1、`tile_sources` 只有該 check 自建的 fixture，`stored_verdict` `CLEAN`（`body_arch`／`body_html` 各 0 個前綴）；前綴長度由 Supervisor 讀到 **63**，所以 383 與 320 的差就是一次前綴插入。同一個資料庫的資料列另外量到：`url =like '/web/assets/%'` 共 **18** 筆，不帶前綴的排除條件把 **18 筆全部**排掉、帶前綴的 **一筆都沒排掉**——這才是那一格會變成 19 的原因 | **已出貨（#271）**：Ingress asset location 多兩條 **Shipped rewrite**，一條一種引號，pattern 與 replacement 完全相同——唯一的工作是在通用規則之前先搶下那段位元組（`sub_filter` 一次只追一個比對，起點較早者勝；起點相同則依寫的順序，#158，所以這兩條寫在通用規則之前，兩種機制下修法都成立）。**不收窄通用規則**：量測顯示這個類別目前只有**兩處**，而 `/web/assets/...` 同時也是真的位址（`loadBundle` 就用它），位元組搜尋分不出 operand 位置；理由與否決的另一案記在 ADR 0004 的 2026-10-02 postscript。六個樣式字面值（不是 issue 寫的四個——引號風格屬於每一處而不是每個檔案）連同第三個 selector `FileDocumentsSelector` 全部量進 `odoo18ce/tests/fixtures/bundles/README.md`；`odoo18ce/tests/test_ingress_media_dialog_domain.py` 用真正的 nginx **兩個方向**都跑：有修法時六個字面值一個位元組都不變，把這兩條拿掉時那兩個 document 字面值被加上前綴，所以未來有通用規則開始碰到剩下四個中的任何一個，是那個測試變紅而不是選取器悄悄換了清單。**不改 #239 的嚴重度**（本輪也重量到 `tiles_selected: 1`、`rule_in_served_method` 與 `legacy_rule_in_served_method` 皆 `true`），也不是 plan item，不進第 10.6 節的分母 |

---

## 12. 記錄 schema 與交付格式

每個受測項目輸出一筆 `odoo-parity-evidence/v1` JSONL：

```json
{
  "schema": "odoo-parity-evidence/v1",
  "run_id": "WOOW-PARITY-<UTC timestamp>",
  "target": "test-6",
  "database": "odoo_test",
  "client": "desktop-chrome-1920x1080",
  "layer": "L3",
  "item": "U-C4",
  "root_cause": ["RC-3"],
  "module": "project",
  "screen": {"route": "<去前綴後的規範路徑>", "model": "...", "view": "form"},
  "control_identity": "<第 1.1 節定義的語意身分>",
  "ingress":  {"available": true, "result": "...", "signals": {"pageerror": 0, "console_error": 0, "failed_requests": 0, "http_4xx_5xx": 0, "route_escape": 0}},
  "public":   {"available": true, "result": "...", "signals": {"...": 0}},
  "verdict": "PARITY | GAP | APPROVED-DIVERGENCE | STRUCTURAL",
  "severity": "blocker | important | minor | none",
  "artifacts": ["<截圖/HAR 參照>"],
  "notes": "..."
}
```

共用層 driver（#143）的記錄另有：`verdict` 可為 `NOT-RUN`（此時 `severity` 為 null、必填 `blocked_by`
說明阻擋原因，未執行的 surface 為 null）、`screen.name`（受測畫面名稱）、`STRUCTURAL` 必填的 `public_path`、
`GAP` 立案後的 `issue`。每筆同時帶兩個 surface，`control_identity` 為 `check:<item>|<module>|<screen>`。

**去識別化硬性規則**：不得寫入憑證、ingress token、原始 URL、query string、cookie 值、
真實客戶資料。URL 一律以「基底代號 + 規範路徑」記錄（例：`<PUBLIC_BASE>/my/orders/42`）。

**另一個 schema：`woow.peer-snapshot.v1`（#234，2026-10-01）。** 協作 peer snapshot 那一次量測不是「一個
plan item 在兩個 surface 上的同一個控制項」，所以塞不進上面那個 schema：它有**兩個 session**（
`--pair ingress-ingress` 時兩邊都在 Ingress，只有一個 surface），要記的是每個 session 各自的前綴、傳輸
到底有沒有送到、以及**存進記錄的是誰的前綴**——parity 記錄沒有欄位放這些。所以
`odoo18ce/tests/e2e_collab_peer_snapshot_live.py` 自帶一個 schema 與自己的 `report`，**不**進
`conservation`（它不是 U/AD/G 項目，不佔守恆檢查的分母；#243 的那一列是 hand-driven check，與 #235 的六
個 check 同一種記法）。上面的去識別化規則一樣適用，而且更嚴：每個前綴一律換成所屬 session 的標籤
（`<ingress:A>`／`<ingress:B>`／`<ingress:unknown>`），所以記錄能說出「存到的是誰的前綴」而不帶那串
secret。欄位與判定由 `odoo18ce/tests/test_e2e_collab_peer_snapshot.py` 固定，schema 名稱與本節這一段由同
一個測試綁在一起。

**`transport.waited_seconds` 要當判準讀，不是當註解讀（#263，2026-10-02）。** `delivered` 為 true 而
`waited_seconds` 是 **0.0** 的那個形狀**存疑**：#243 那一輪的 `ingress-public` 就記到過一次
`{"delivered": true, "waited_seconds": 0.0}`，而同一台主機上同一組的另一面剛剛整整等了 30 秒才判沒送到；
真相是沒送到。原因是當時 `probe` 打的 marker 是**常數**（`WOOW-PEER-PROBE`），而它自己又把那串字寫進了
`project.task.description`，所以下一次 `probe` 第一次 poll 就在**載入的值**裡讀到它，把「重新載入」當成
「傳輸送到」。這一步的全部論據是「沒有東西存過這個 marker，所以它出現在這裡就是傳輸而不是重新載入」，
常數剛好把那句話廢掉。修法兩半，兩半都由上面那個測試綁住：marker 一律由 `marker(run_id, label)` 產生
（`probe` 不給 `--run-id` 時自己 mint 一個 `WOOW-PEER-PROBE-<UTC timestamp>`），以及 `await_marker` 收一個
**baseline**——送方還沒打字前的 editable，也就是兩邊都會載入的那份文件——在 baseline 裡就比對得到的 marker
一律判**不是**送到（`marker_pre_existing: true`），而且不等待。0.0 秒本身**不是**錯的讀數：收方是在送方打
完字之後才加入，它拿到的 snapshot 本來就可能第一次 poll 就帶著 marker，所以這個數字照記、讀的人多看一眼，
而不是把它縮成一個布林值。`probe` 另外回報 `wrote_nothing`——那是把欄位讀回來**量到**的，不是宣稱的——為
false 時 exit code 非 0；它靠的是離開前按下表單自己的 Discard，因為在 dirty 的 To-do 表單上導覽離開會把
editor 的內容存進去，「只有存檔才會寫欄位」在這張表單上不成立。

**同一個 schema，#265（2026-10-02）加了三件事。** 版本仍是 `woow.peer-snapshot.v1`：欄位是**加**的，
記錄的種類沒變。

- **`collaboration`：傳輸為什麼是這個結果，由讀到它的那一輪說。** #243 那一輪留下的是兩個光禿禿的
  `delivered: false`，後面三份文件寫的「兩個 session 從未成為協作 peer」其實是從 timeout 推的。現在兩個
  session 各自回報 `is_collaborative`／`bus_worker_state`／`channel`／`ptp_joined`／`connected_peers`，
  再加上每個 session 往 `/html_editor/bus_broadcast` 發出的 signalling 次數（從 wire 上數，不是聽 client
  自己說），`transport_diagnosis` 取**第一個成立的**原因：`delivered`、`marker-collision`、
  `field-not-collaborative`、`bus-not-connected`、`different-collaboration-channel`、
  `peer-network-not-joined`、`no-peer-data-channel`、`unattributed`。梯子有順序，因為讀數彼此有前提：
  沒有 bus 時 peer 數不能說明什麼。
- **`healing`：`ingress-public` 量兩次。** peer 存檔後一次（`verdict`，允許帶前綴），Ingress session
  重新載入該值、存一次檔後再一次（`healing.verdict`，必須乾淨），另加 `loaded_prefixes` 說明治療有沒有
  對象。`ingress-ingress` 不做這一段，`healing.performed` 為 false 並寫明理由；取不到時也是
  `performed: false` 加理由，**不**是缺欄位。**升級規則讀的是 `final_verdict`**——有治療那一段就是它，
  否則是 peer 存檔那一個——因為 #234 講的危害是 token **留在**記錄裡；中途那次寫入不會因此消失，
  `report` 以 `foreign_prefix_healed` 單獨列出。
- **`CLEAN` 要連著當時的傳輸一起讀。** `report` 把 clean 分成 `with_a_delivered_transport` 與
  `with_no_delivery` 兩串 pair，並寫一句 `clean_means`。#243 那兩個 `CLEAN` 是在傳輸兩面都沒送到的情況
  下讀到的，而後來 ADR 0004 的附記、本計劃這一列、那一輪的 evidence README 都把它引用成「量過了，
  乾淨」——那是把**存檔路徑**的量測當成**送到的 peer snapshot** 的量測。這兩句話從此不能被寫成一句。

marker 的規則也補了一半：`marker(run_id, label, pair)`——**pair 也要進去**。一次 run 是一個 `--run-id`
跑**兩個** pair，而 `run` 會把 marker 存進欄位，所以第二個 pair 開到的記錄裡已經有第一個 pair 的
`<run-id>-A`；baseline 那道關卡擋下來了（`marker_pre_existing: true`），但那一筆的傳輸讀數就**作廢**
了——它不等待就回。run id 讓 marker 跨 run 唯一，pair 讓它在一次 run 之內唯一；同一個 pair 用同一個
run id 再跑一次仍然要換 `--run-id`。實例見 `docs/testing/evidence/2026-10-02-issue-265/`
的 `peer-first-attempt.jsonl`。

**第三個 schema：`odoo-parity-ambient/v1`（#256，2026-10-01；#264，2026-10-02）。** 任何一次開過
website 頁面的 run 都會留下沒人要求的列：tracked page 的 GET 會 upsert 一筆 `website.visitor` 並插入一筆
`website.track`，頁面自己的 markup 跟 JavaScript 也寫（理由與出處見 [ADR 0012 postscript
2026-10-01 (#227)](../adr/0012-sweeps-verify-on-the-test-host.md#postscript-2026-10-01-227)）。
以前「留了幾筆」要事後上主機數（#235 的 19 筆就是這樣來的）；現在是 run 自己在登入後與離開前各數
一次，把差值寫在證據旁，檔名就是記錄檔換上 `.ambient.json` 這個副檔名
（`ingress-open.jsonl` → `ingress-open.ambient.json`）：**只有數字**，不記 URL、不記訪客身分，
所以沒有可去識別化的東西；數列數一律走 session 自己的 RPC（`search_count`，空 domain），不走
`ssh`——事後上主機數到的是另一個量測，構不成差值。#256 只做了 adapter 的 `crawl` 與 `open`，
其餘 Live driver 於是又退回事後數（#243 那一輪就是，見上）；**#264 把同一份記帳給了全部**：
`e2e_ingress_markup_live.py`（一個 surface 一個 check 一行）、`e2e_collab_peer_snapshot_live.py`
的 `run` 與 `probe`、`e2e_ingress_hand_checks.py`（一次 invocation 一行）。

新增欄位 `navigation_basis`，因為兩種 driver 的分母**數的不是同一件事**：adapter 數的是它自己發出的
導覽（`SurfaceDriver._goto` 這一個出口），hand-driven driver 數的是它的 browser context 在該 surface
base 底下送出的每一個 document GET（接 Playwright 的 `request` 事件）——後者才看得到「按連結造成的
導覽」與「website editor 的 preview iframe 自己抓的文件」，代價是 redirect 那一跳也算，所以它是頁面
瀏覽次數的**上界**而不是次數。兩邊都叫 `navigations`，所以那句話必須跟著數字走在同一筆記錄裡。
記錄會 append 的 driver，數字也 append——一行一個 JSON 物件，照 invocation 發生的順序，因為那些記錄檔
是整個 session 累積的（`markup.jsonl` 38 筆），truncate 會讓最後一次的數字代表每一次留下的列。
`probe` 不留記錄檔，沒有東西可以擺在旁邊，所以它的數字印在 stderr、不寫檔：它只開 `/odoo/...` 後台
路由，delta 預期是 0，而**讀到的 0 是讀數，假設的 0 不是**，這才是去數它的理由。兩個 session 的 run
把 `surface` 記成 pair 名稱（例：`ingress-public`）：列數走 session A 的 RPC，分母是兩個 session 相加，
因為那兩個 model 是整個資料庫的，一筆列事後沒辦法歸給兩個同時開著的 session 之一。

這是**記帳而非判定**：`diff` 不讀它（`read_records` 拒收
這個 schema），也和 `woow.peer-snapshot.v1` 一樣**不**進 `conservation`——它不是 U/AD/G 項目、
不佔守恆檢查的分母，§10.6 的 76 項數字不因它而動。兩個 surface 走的是同一批頁面，所以兩邊的
delta 不相等只是先後順序的產物（第一輪建的 visitor 列第二輪已經在了），不是落差。

**第四個 schema：`woow.ingress-markup/v1`（#243，2026-10-01）。** `#243` 這一輪的四列
（#237／#238／#239／#240）都不是 `odoo-parity-evidence/v1` 的形狀。那個 schema 一筆記一個計畫項目、
兩個 surface 各一欄，由 `diff` join 之後判定；這裡每筆記**一次互動**，而且判準**依 surface 不同**——
同一個 root-relative `src`，Ingress 要它落在前綴底下，Public 要它落在 origin 根上，兩邊相等才是失敗，
所以不能用兩面對 diff 的方式判。每筆另外帶一個或兩個「存回去的欄位值」（`project.task.description`、
`res.users.signature`、`mailing.mailing.body_arch` 與 `body_html`），那是 parity schema 沒有地方放的東西。
圖片判定是 `UNDER-PREFIX`／`AT-ORIGIN-ROOT`／`NOT-LOADED`／`ESCAPED`／`ABSENT`（最差者勝，`ABSENT`
最重——空畫面不是乾淨畫面，而是沒量到），存檔判定是 `CLEAN`／`PREFIX-STORED`。去識別化沿用
`woow.peer-snapshot.v1` 的 `redact`，前綴形狀也沿用它那一份（由 gateway template 推出並被測試綁住），
所以這個模組不會長出第二條會漂走的 regex。逃逸判定一律委派 `adapter.is_prefix_escape`，不在這裡重寫——
會漏掉的那個形狀是**雙前綴**：它仍在前綴底下，所以「有沒有離開前綴」會答沒有。與前兩個附加 schema 一樣
**不**進 `conservation`：這八個 check 都是第 9 節各自那一列的 Live 欄，不是共用層那 76 項，§10.6 的守恆
數字不因它而動。欄位與判定由 `odoo18ce/tests/test_e2e_ingress_markup_live.py` 固定；瀏覽器步驟**沒有**
靜態測試，模組開頭有說，理由與 `e2e_collab_peer_snapshot_live.py` 相同。

**#266（2026-10-02）之後是九個 check，schema 本身不變。** 新增的是
`media-document-mailing`（#239 line 3 在舊對話框上），而四個 media check 都改成自己建 fixture 並由
`--cleanup` 移除，所以這一族的 `writes` 欄從三個變成六個，`read_only_first` 的順序隨之改變。記錄多帶
幾個 `extra` 讀數——`fixture`／`fixture_removed`（建了什麼、清掉了沒有）、`element_after_select`
（點選之後再讀一次 `data-original-src`，因為 image tools 會在那個空窗裡刪掉或覆寫它）、
`replace_control_present`／`replace_control_visible`／`replace_control_found_in`（被找的控制項在不在、
看不看得見、在哪個 document 裡），以及 `operand` 現在帶 `dialog`（`current`／`legacy`）與
`served_domain_*`（#271 的那三個讀數）。`extra` 仍然是平面合併進記錄，所以名稱不得撞到
`RESERVED_RECORD_KEYS`，那條由同一個測試檔守著。`data_original_src` 現在**每一個** media check 都記，
包含兩個 document 行——那裡它結構上是 `None`，而漏掉那個 key 的記錄無法和「這個 key 還不存在的時候
量的」區分開。

**#274（2026-10-03）補上第四個 media check 唯一還在「找」的那一半，schema 仍然不變。**
`media-document-mailing` 以前自己建 attachment、但只 `search` 一筆 `state in ('draft','in_queue')`
的 mailing，所以在沒有草稿 mailing 的資料庫上只會記 `NOT-RUN`（#271 那一輪在 `catchup164b` 上量到，
run `WOOW-MARKUP-20261003T123902Z`，只能用 `odoo shell` 手動補一筆才跑得起來）。現在**找不到就自己
建一筆草稿 mailing**，subject 用 `scratch_task_name`（`WOOW scratch (delete me) <run id>`）、建完把
`state` 讀回來確認落在 `EDITABLE_MAILING_STATES`（designer 的 body 欄在 `sending`／`done` 下是
readonly），記在 `extra["fixture"]` 的 `mailing_id`／`mailing_subject`／`mailing_state`，`--cleanup`
連它一起刪、刪的結果記在 `fixture_removed.mailing`。**借來的那一筆不一樣**：只還原 `body_arch`／
`body_html`（`body_restored`）、**絕不刪除**——#266 的教訓就是「刪掉不是自己建的東西」會讓下一輪沒東西
可量。`--mailing-id` 的語意不變（指定這一筆：不找、不建、不刪，也不檢查它的 state）。記錄多一個
`extra` 讀數 `mailing_source`（`given`／`found`／`created`／`reclaimed`），因為「量的是誰的資料」是讀
記錄的人要先知道的事。

第四種來源 `reclaimed` 是審查補上的：`--surface both` 不帶 `--cleanup` 時，ingress 那一面會留下自己的
scratch mailing，public 那一面的 `search` 就會找到它。把它當成「借來的」會做兩件錯事——還原的是**這一輪
自己的** fixture body 卻記成 `body_restored: true`（讀起來像把真的 campaign 還原了），而且那一列會變成
永久垃圾，因為之後每一輪都一樣把它讀成借來的、沒有任何 `--cleanup` 刪得掉。判準是 subject 的
`SCRATCH_NAME_PREFIX`，成立的理由是整個 repo 只有這個 check 會建 `mailing.mailing`；subject 只是**提到**
那串字的真 campaign 仍然享有借來的那一套保護。另外 `email_from` 是 `mailing.mailing` 上唯一「required 而
precompute 可能算不出值」的欄位（沒有 `mail_server_id` 時取 `create_uid.email_formatted or
env.user.email_formatted`，partner 沒有 email 就是 `False`，而 required 的 stored 欄位在 Postgres 上是
`NOT NULL`），所以只在 ORM 算不出值時補一個 `.invalid` 的佔位位址——否則 #274 會在它自己要修的那個場景
（全新資料庫）上以 `IntegrityError` 收場。

**#276（2026-10-03）把同一條規則補到 `mailing-editable`（#238）上，而這裡的答案和 #274 相反。**
那一列也只 `search` 一筆 `draft`／`in_queue` 的 mailing，所以在沒有草稿 mailing 的資料庫上同樣只記
`NOT-RUN`；但它不只是用 RPC 覆蓋借來的 `body_arch`，它會**在 mail designer 裡打字並按存檔**——#238 的
主題本來就是存檔這條縫（`body_arch` 走 `getEditingValue`、`body_html` 由 `commitChanges` 另外 inline，
而後者才是**跟著信件離開這套安裝**的那個欄位）。於是一輪跑完，別人的 campaign 的**兩個**欄位都被寫成這
一輪的標記 body；`--cleanup` 和 handler 的錯誤路徑都會寫回去，但「存檔到還原之間被砍掉」和「根本沒帶
`--cleanup`」（那是選用的）兩種情形都沒人管，留在資料庫上的就是一封 body 為
`WOOW-MARKUP hand check <run id>` 加公司 logo 的真 campaign。所以這一列改成**除了 `--mailing-id` 指定
以外一律自己建一筆、什麼都不借**：量到的東西一點沒少（designer、`getEditingValue`、`commitChanges` 都不
在意自己開在哪一筆記錄上），而完全沒碰到真 campaign 的一輪根本不需要還原才算正確。#274 之所以替
`media-document-mailing` 保留「先找」的順序，是因為那一列**不存檔**（它把表單 discard 掉再把記錄讀回來
當證據）；在這一列，那個順序本身就是風險來源。兩列現在共用同一個 seam（`fixture_mailing`），`borrow`
參數就是各自回答這個問題的地方，來源仍記在 `extra["mailing_source"]`。

因為這一列什麼都不借，`editable_mailing_id` 就不能用來找自己留下的 scratch mailing（它會遞回一筆
campaign）：改用 `scratch_mailing_id`，以 `=like` 從開頭比對 `SCRATCH_NAME_PREFIX`（所以只是**提到**那串
字的真 campaign 不算命中），並同樣以 `EDITABLE_MAILING_STATES` 設界——reclaim 到一筆 designer 會 render
成 readonly 的列，讀起來和「fixture 沒撐過欄位」一模一樣。順手補掉同一個窗口裡的兩件事：**每一個出口都
會把自己的 seed 收掉**（body 是在第一次 navigate 之前用 RPC 寫的，而瀏覽器那半邊四個出口有三個是放棄
路徑，還原以前只掛在存過檔的那一條），以及離開前**把表單 discard 乾淨**（Odoo 表單會在 `beforeunload`
與沒有設條件的 `visibilitychange` 上把髒掉的編輯器存回去，#263 是 To-do 表單上的同一個機制，而
`run_check` 是在 handler **回傳之後**才關 session——那時存下去的既不在任何讀數裡，還會把剛做完的還原再
蓋掉）。

審查（#276）另外補掉三件事。**discard 本來掛錯了一半**：它只在走 leaving function 的出口上，三個 handler
的錯誤路徑全都沒有——而那才是更要緊的一半，因為一個步驟失敗時打字早就做完了，表單一定是髒的
（`mailing-editable --mailing-id 42` 的 `save.click()` 逾時，還原了對方的 campaign、回傳，然後
`run_check` 自己的 `side.close()` 在髒表單上觸發 `beforeunload`，把這一輪的標記 body 原封不動寫回去，而
記錄上寫著 `body_restored: true`）。兩個 mailing handler 與 `do_codeview` 的兩條錯誤路徑現在都先 discard。
**`do_codeview` 的成功路徑也有同一個窗口，而且寫的是一筆既不能刪也不能重建的真記錄**（真的
`ir.actions.act_window.help`）：它記了 `unsaved_after_save` 卻沒有對它做任何事，所以存檔後表單還髒的
`--cleanup` 跑法會把這一輪的 help 永久留在那個 action 上、旁邊還寫著 `help_restored: true`；discard 現在
放在讀回（那才是讀數）與還原之間。第三件：**自己建列之後，`body_html` 的基準變成 `False`，而空值是
`CLEAN`**（本來就該是，裡面沒有前綴），於是「存了 `body_arch`、`commitChanges` 根本沒跑」會替第 8 條規則
那個欄位——跟著信件離開這套安裝的那一個——記下 `PARITY`。新讀數 `extra["body_html_inlined"]` 用的是
designer 裡**打進去**的標記（RPC 種下的值裡沒有它），只記不判：在那裡下判定會讓這一列的 `PARITY` 取決於
不是它主題的機制。

審查還找到一件沒有在 #276 裡修的：被 reclaim 的 scratch mailing，body 裡連的是**更早那一輪**建的 public
`ir.attachment`，而那一筆不在這一輪任何 fixture dict 裡，所以沒人刪得掉。它早於 #276（#274 的 reclaim
就是起點），兩個 mailing check 共用同一個 scratch subject 前綴只是多了一條到得了那裡的路。已開 #277，
並於下一段修掉。

**#277（2026-10-03）：reclaim 刪掉了 mailing，卻留下它 body 連著的 attachment。** `--cleanup` 收的是兩
樣東西——`fixture["attachment"]`（**這一輪**建的那一筆）和 scratch `mailing.mailing`（不論誰建的）。所以
`media-document-mailing` 不帶 `--cleanup` 跑完會留下 scratch mailing M，它的 `body_arch` 裡帶著自己建的
public attachment A 的 `<a href="/web/content/<A>" ...>`；之後帶 `--cleanup` 的一輪 reclaim 掉 M 並刪
除，A 就活下來而且**再也沒人找得到**——fixture attachment 只在建它那一輪的 `fixture` 區塊裡有名字。單一
check 的那一半是 #274 的；#276 只是多開了第二條路（兩列現在寫同一個 `SCRATCH_NAME_PREFIX` subject，
`mailing-editable` 於是可以 reclaim 掉 `media-document-mailing` 留下的列）。

這是宿主衛生問題，不是讀數錯誤：一筆殘留的 `public=True`、名為
`woow-document-fixture-<run id>.txt` 的 attachment，會被 media dialog 自己的 `order: 'id desc'` 排在**第
一個**（那正是 `create_fixture_attachment` 倚賴的性質），所以下一輪在建自己的 fixture 之前，tile 列表第一
格看到的就是舊一輪的垃圾。判定不會因此跑掉：每個 media check 都是**按名字**讀自己建的那一格。

修法是在覆蓋 body 之前先把 id 讀出來：`reclaimable_scratch_mailing` 現在和 subject 判定同一個 call 一起
讀 `body_arch`（那是這個值最後還能說話的時刻——seeder 自己的 body 寫入會換掉那個 href，刪除則把整列帶
走），`reclaim_stranded_attachments` 從裡面取出 `/web/content/(\d+)` 並 unlink。**界線是
`scratch_mailing` 自己的 `body_arch`，這也是「從 markup 讀 id」之所以站得住的原因**：只有 subject 帶著
`SCRATCH_NAME_PREFIX` 的列才有這個 key，所以 body 只會是這個 driver 自己的 fixture body；這一輪自己建的
列根本沒有 body，而**借**來的列（`found`，或 `--mailing-id` 指定的）連 `scratch_mailing` 這個 dict 都沒
有——真 campaign 的 body、人家公司的 attachment，兩者都進不了這份清單。

**刪除跟著 reclaim，而不是跟著 `--cleanup`**，這個不對稱就是修法的重點，也是這個洩漏的另一半：
`--cleanup` 問的是「把宿主還原成這一輪看到的樣子」，對這一輪自己建的列來說那就是全部的問題；但這些
attachment 是**更早那一輪**的、已經被丟掉的東西，而 seeding 不管旗標怎麼下都會把唯一的把手毀掉。所以
不帶 `--cleanup` 的 reclaim 會留下一列「已經不指名那個 attachment」的 mailing，下一輪帶 `--cleanup` 的
跑法讀到的 body 什麼都沒指，把列刪掉——結果和修之前一樣是殘留。它同時也是 seeder guard 裡的第一步（排在
這一輪自己要建的 attachment 之前），因為它下面每一步都可能失敗，而隨之而來的補償會把 id 所在的那一列刪
掉。

另外兩個細節是刻意的：pattern 不從開頭錨定（留下垃圾的那一列會**存檔**，而 #238 的主題本來就是存檔可能
把 href 帶上前綴存下去）；id 在 `unlink` 之前先過一次 `search`——unlink 一個已經不存在的 id 是
`MissingError`，而「body 指著一筆已刪的 attachment」是到得了的狀態（某一輪 mailing unlink 失敗後留下的
就是這個樣子），為了已經不在的垃圾讓 reclaim 失敗，等於讓還在的垃圾活下來。

把 subject 前綴改成每個 check 各自一組是另一個選項，而它**不是**修法：那只解掉跨 check 的那一半，單一
check 的那一半（也就是本來就存在的那一半）還在。id 與結果都記在 `extra["fixture"]`
（`reclaimed_attachment_ids`、`reclaimed_attachments_removed`），seeder 的補償路徑在刪除回報 `false` 時
會把兩者都印到 stderr——`run_check` 在 handler raise 時會丟掉它的回傳值，所以那條 console 訊息是它們從那
條路徑唯一出現的地方；而 reclaim 的結果也沒辦法搭 `fixture_removed` 的車，因為 reclaim 早在 seeder 任何
一步會失敗之前就跑完了。

**#279（2026-10-03）：`body_html_inlined` 會因為 reclaim 來的列上一輪留下的標記而讀成 `true`。** 由 #277
的審查找到，但不是 #277 帶進來的——這個讀數是 #276 的。它問的是「第 8 條規則到底有沒有跑」，而它當初問
的方式是「讀回來的 `body_html` 裡有 `marker_for(run_id)`」。`--run-id` 整趟只有一個值，`--surface both`
又是拿同一個資料庫跑兩個 surface，所以不帶 `--cleanup` 時：ingress surface 建了 scratch mailing M、存檔，
`body_html` 裡留著這一輪的標記；public surface 的 `scratch_mailing_id` 把同一列 M reclaim 回來（這是設計
如此，subject 就是這一輪的）；若 public 這一次的存檔只寫了 `body_arch`、`body_html` 根本沒被 inline，那個
欄位仍帶著 ingress surface 的值和一模一樣的標記，於是記成 `true`。同一輪 run id 下重跑**同一個** surface
也是一樣的結果。

修法是把標記判成**新出現的**：在讀回來的值裡，而且不在 `fixture["before"]["body_html"]` 裡——那個值
seeder 在寫 `body_arch` 之前就已經讀過，所以不用多一次 RPC。把打進去的標記改成每個 surface 各自一組是另
一個選項，而它**不是**修法：它只解掉跨 surface 的那一半，同一 surface 重跑的那一半還在，而且會動到其他讀
數拿來比對的值。讀數本身其他部分都不變，仍然是**只記不判**（理由同 `_media_verdict`），所以沒有任何判定
因此移動；它守的是讀者用來分辨「inline 過，而且是 root-relative」與「根本沒 inline」的那份證據——
`stored_verdict(False)` 是 `CLEAN`，空的 `body_html` 自己就會拿到一個 pass。

代價是明寫出來的：**#279 在 reclaim 來的那一列上把這個讀數留成了「不論那一次存檔怎麼走都是 `false`」**
（標記在存檔之前就已經在欄位裡了）——這一段只講 #279 自己留下的狀態，往後走到哪裡看下面的 #286。對一個
「職責是拒絕假 pass」的讀數來說，這是該往的那個方向——「inline 過」才是需要證據的那個主張——而新記下的
`extra["body_html_marker_before"]`（在讀 `before` 的地方一起讀）就是用來分辨兩種 `false` 的：「這次存檔沒
有 inline」與「標記本來就在，這一列說不了話」。只有 #279、還沒有 #286 的那段時間裡，想在那一列拿到正面讀
數就得帶 `--cleanup`，或給它自己的 run id。至於「在種 `body_arch` 的同時把 `body_html` 清掉」——那會讓那
一列的兩邊讀數都成立，#279 刻意不做，但不是因為做不到（掛在 `fixture["scratch_mailing"]` 上就只會碰到這
個 driver 自己的垃圾）：那種寫法改的是**寫入**，連帶改掉 `stored["mailing.mailing.body_html"]`，而那一個是
`stored_verdict` 會**判定**的——同一份殘值的「被判定」那一半，正是 #279 劃在範圍外的東西。那一半是真的、
不是假想：在一列 reclaim 來的 mailing 上，若第二次存檔只寫了 `body_arch` 而沒有 inline，public surface 記
下的 `PREFIX-STORED` 或 `CLEAN` 可能是 ingress surface 留下的值，而不是這次存檔寫的任何東西。那一半就是
#286，而它正是把那個清除做了下去。


**#280（2026-10-03）：`_discard_unsaved_form` 沒辦法回報一次失敗的 discard，而且那一下 click 沒有界。**
由 #277 的審查找到，程式是 #276 與其審查 commit 的（原本的 #281 是同一個函式的另一半，一起修：timeout 就
掛在第一半正在改寫回報方式的那一下 click 上）。那個函式把每一種例外都吞掉，而且只會寫
`extra["discarded"] = True`，docstring 又把**沒有**這個 key 定義成「這個頁面沒有東西要 discard」——於是
`UNSAVED` 命中、`discard.click()` 逾時（按鈕上蓋著 modal、頁面不再回應）的那一列記錄，讀起來和一張本來就
乾淨的表單一模一樣。那在 #276 的審查替三個 handler 補上這個呼叫的那幾條路徑上最要緊：錯誤路徑上打字早就
做完了，表單**一定**是髒的，而緊接著的那一步就是還原，照樣寫下 `body_restored: true`（`do_codeview` 是
`help_restored: true`），即使 `run_check` 自己的 `side.close()` 會在那張還是髒的表單上觸發 `beforeunload`，
把這一輪的標記 body 原封不動蓋回去。現在是三種讀數而不是兩種：沒有 key（沒東西要 discard）、`true`
（discard 成功）、`false`（`UNSAVED` 命中而表單沒有變乾淨——click 失敗、找不到可見的 discard 按鈕，或按
完之後那個未存檔指示器還在），還原自己的讀數於是對得起來。緊接在後的 `settle` **不算**其中一種成因：它跑
在指示器已經轉 hidden **之後**，這個 key 要回答的問題那時候已經有答案了，所以頁面在那段 sleep 當中關掉，
也不能把一個已確認的 `true` 翻回「表單被留成髒的」那個讀數——那段 sleep 是為了後面還原的那通 RPC，不是
discard 的證據。而 `true` 的意思是**表單真的乾淨了**，不是「click 沒有拋例外」：discard 之後等 `UNSAVED`
轉 hidden（記錄一乾淨，指示器就又帶上
`invisible`，這個 selector 就不再命中，而沒有元素的 locator 算 hidden——`discard_form` 一直是這樣讀這個結
果的），否則一次沒有生效的 discard（上面彈了 dialog、表單因記錄無效而不肯離開）仍會記成 `true`，而
`side.close()` 面對的還是一張髒表單——同一個讀數錯誤換一個成因。按鈕也改用 `>> visible=true` 而不是
`.first`（本來就是這個 repo 對同一顆按鈕的寫法）：`.first` 不管狀態都取 DOM 裡第一個命中，所以一顆隱藏的
前面的按鈕（dialog 的、子表單的）會通過 `count()`、把界耗在一個永遠點不到的元素上，真正那一顆從頭到尾沒
被點。`_remove_mailing_fixture` 逐一回報每次刪除就是同一個理由（一個靜默的 `except` 讀起來等於「刪掉
了」），而 `e2e_collab_peer_snapshot_live` 的 `discard_quietly` 早就回報這一對。讀不到的頁面（frame 已經換掉、context 已經關掉）仍然不加 key：那時候連「有沒有東西要 discard」都不知
道，和「discard 失敗」不是同一個讀數。

另一半是**那一下 click 本來沒有界**：這個 driver 從頭到尾沒有呼叫 `set_default_timeout`（`TIMEOUT` 只會明
寫給 `wait_for`），所以 `discard.click()` 吃的是 Playwright 的 30 秒預設。`do_codeview` 的
`except BaseException` 會先 discard、再用 RPC 把真的 `ir.actions.act_window.help` 寫回去——順序是對的（那
正是不讓 `beforeunload` 蓋掉還原的原因）——於是操作者按下 Ctrl+C 之後，那 30 秒整整卡在中斷與那筆記錄唯一
一次還原之間；窗口裡的第二次 Ctrl+C 是 `KeyboardInterrupt`，`_discard_unsaved_form` 的 `except Exception`
接不到，handler 自己的 `except Exception` 也接不到，標記文字就留在那個 action 上，沒有任何東西還原它。現在
兩個等待都明寫界：click 是 `DISCARD_TIMEOUT`（2 秒——它只需要一顆可點的按鈕，而那一顆剛剛才以
`visible=true` 命中），指示器轉 hidden 是 `DISCARD_CLEAN_TIMEOUT`（15 秒）。第二個等的東西比第一個多得
多，而且**不是** reload：`_discard` 本身純本機，從 save point 把 `_changes` 還原、重畫，一通 RPC 都沒有
（`web/static/src/model/relational_model/record.js:565`）。指示器真正在等的是它上面那一行——`discard()`
（`:183`）先 `await this.model._askChanges()`，那會發出 `NEED_LOCAL_CHANGES`，而 html field 的回應是把
`commitChanges()` 推進 promise 清單（`html_editor/static/src/fields/html_field.js:78`）。在 mail designer 上
那個 override 會把 editable 複製進一個 `srcdoc` iframe、**等它的 `load`**、跑 `toInline`、再把結果寫回記錄
（`mass_mailing/static/src/js/mass_mailing_html_field.js:147-186`）。那是**存檔**路徑用 `side.settle(6000)`
在等的同一條 inlining pipeline，而 `extra["save_incomplete"]` 存在就是因為那樣有時還不夠。所以這個界如果
收得比存檔那邊還緊，一次成功的 discard 就會被記成 `discarded: false`——正是這張票要消滅的讀數錯誤從另一邊
走回來（#288）；它因此訂在存檔預算之上，並有一個 Static tier 的測試釘住這個關係。

**那組界收短的是這個 seam 對窗口的貢獻，不是窗口本身**（#288）。窗口裡還有兩筆更大的開銷，都不在這一個
函式裡：`side.root` 是 property 而不是欄位，Ingress iframe 一旦 detached 它就走
`_find_frame(wait_s=60)`（`e2e_parity_shared_layers_live.py:327-339`）——而那正是中斷本身的情境；成功的
discard 之後那一下 `side.settle(2000)` 又會花掉一個 8 秒的 `networkidle`，Odoo 開著的 bus 通常會讓它等到
逾時才去睡。這一票真正拿掉的是**三倍曝險**：seam 現在只解析 `side.root` 一次、拿到的 frame 一路用到底，而
不是三個步驟各自去碰那個 property，所以舊碼那三次「有可能花掉一分鐘」的機會現在只剩一次。（是一分鐘、不是
三分鐘：`_find_frame` 一有命中的 frame 就回來，完全沒有就掃完一輪 60 秒拋例外，所以一個持續 detached 的
frame 在舊碼上也只花 60 秒一次；要花到三輪得剛好連續兩次在各自窗口的尾端重新解析成功。）

**而且這個「拿著」是讀數的修正，不只是等待時間的修正。** `IngressSide` 本來就把 frame 快取在
`self._frame`、只在它 detached 時重新解析，所以三次讀在除了一種情況以外都拿到同一個物件：面板在第一次讀
與那個確認等待之間把 Ingress iframe 重新掛載起來。那種情況下舊碼會解析到**替換掉的那個** frame，而它剛載
好的文件上沒有 `.o_form_status_indicator_buttons:not(.invisible)`——於是對一個零命中的 locator 做
`wait_for(state="hidden")` 立刻就回來、什麼都沒拋，記下 `discarded: true`，而那張髒表單在剛剛消失的那個
frame 裡，它的 detach 正是 `beforeunload` 觸發的時機。那是這張票自己的讀數錯誤換第三道門進來。拿著那個
frame 之後，detached 的 frame 會拋例外，讀數留在 `false`。seam 後面也沒有任何東西需要那次順便的重新解
析：`Side.rpc` 是走 request context 而不是走 frame，所以還原根本不需要一個解析得出來的 frame。

中斷真的落下時，`discarded: false` 已經寫
進 `extra` 才往外拋——那條路徑上不會有任何一行記錄（`run_check` 只接 `Exception`，被 `KeyboardInterrupt`
打斷的 surface 連 `NOT-RUN` 都不會寫），這個讀數是給其他每一條**會**寫記錄的路徑用的。另外兩個
handler 的錯誤路徑共用同一個函式，所以同一組界也跟著套上。全域 `set_default_timeout` 會動到這個 driver 的
每一個等待，不是修法；「失敗的 discard 之後要不要跳過還原」也不是——還原仍然要試，那是那筆記錄唯一的機
會，所以這一票改的是讀數，不是順序。


**#286（2026-10-04）：reclaim 來的那一列上，被判定的 `body_html` 可能不是這次存檔寫的。** 這是 #279 修掉
「被記錄」那一半之後剩下的「被判定」那一半，由 #277 的審查提出、在 #279 之後的 `main` 上原封不動。
`mailing-editable` 把這個欄位的 **Stored reading** 當成 *write-bounding* 的：裡面有前綴，意思是**這一次**
存檔的 `commitChanges` 漏了（#238 第 8 條）。但在一列 reclaim 來的 mailing 上、而且這次存檔只寫了
`body_arch` 時，它就不是——讀回來的是上一個 surface inline 進去的值。而 `stored_verdict` 會判定交給它的每
一個欄位，`PREFIX-STORED` 又會在所有其他分支之前被提升成整列 check 的判定（#237 第 4 條），於是 ingress
surface 那次存檔漏出來的前綴會被印成 `PREFIX STORED by mailing-editable/public`、exit 1——而在 public 這
一側，「資料庫裡有前綴」的意思是 `sub_filter` 從 Ingress 的 asset location 漏了出去，是另一個、而且更嚴重
的主張。乾淨的那個方向也一樣會落下：上一輪留下的乾淨值會替這次存檔根本沒寫的欄位記下 `CLEAN`。

修法在**寫入**，不在判定，理由寫在 `docs/adr/0014-a-stored-prefix-is-never-suppressed.md`：教
`stored_verdict` 跳過一個「已知是殘值」的欄位，在程式上與證據上都和「把一個存進資料庫的前綴抹掉」分不出
來，而那正是這個模組存在要揭露的東西、也是 #237 第 4 條要禁止的事。所以 seeder 現在在種 `body_arch` 的
**同一通 `write`** 裡把 `body_html` 清掉，存檔之後留在那個欄位裡的就只會是這次存檔自己的產物；
`stored_verdict`、`evidence_record`、`do_report` 一行都沒動。

清除掛在「這一輪手上有 scratch 列」上，而那正是 `_restore_borrowed_mailing_body` 自己那道 guard 的反面。
兩者互為反面，所以這個清除永遠不可能抹掉還原會寫回去的值：`created` 是 no-op（欄位本來就是 `False`）、
`reclaimed` 是這一票要修的情況（這個 driver 自己的垃圾）、`given` 是 `--mailing-id` 指名的那一列，原封不
動留著（還原仍然只在 `--cleanup` 下跑），`found` 則到不了（這個 check 傳 `borrow=False`）。
`fixture["before"]` 留著**真正的**跑前值：它既是還原的來源，也是「這一列原本長什麼樣」的證據，而同一個
fixture 形狀還和 document-mailing 的 seeder 共用，所以清除有自己的讀數（`fixture["seeded"]`，由新的
`body_html_baseline` 讀），不是去蓋掉別人的。`extra["body_html_marker_before"]` 的意思與位置都不變（標記
在這一輪碰這一列之前就在那裡），仍然在那通寫入之前讀。

於是 `body_html_inlined` 在 reclaim 來的那一列上現在讀得到 `true`——#279 給不了的那一半：清除把 #279 在那
一列上刻意的單向讀數（不論那次存檔怎麼走都是 `false`）換回雙向的，比對的是「seed 留下的值」而不是跑前
值。它仍然**只記不判**（理由同 `_media_verdict`），所以也沒有任何判定因此移動。**document**-mailing 的
seeder 什麼都不清：那個 check 從不存檔，它的讀回是用來證明 discard 有效的，清掉欄位會毀掉它拿來比的基
準。另外四個「拿的是 State-bounding reading、卻被當成 write-bounding 來判」的 check——`readonly-plain`、
`mailing-readonly`、`media-document-mailing` 的 `body_html`、以及 `--task-id` 下的 `readonly-iframe`——是
同一個家族走另一條可接受的修法（attribution），開在 #289。


落差報告最終彙整為：

```
落差清單（依嚴重度排序）
  ├─ 每筆：ID / 現象 / 影響範圍（哪些模組共用同一根因）/ 根因 RC / 建議修法 / 驗收條件
守恆檢查：
  觀察到的控制項總數 = PARITY + GAP + APPROVED-DIVERGENCE + STRUCTURAL
  （有餘數、有無法分類項、有探索錯誤 → 本輪不合格）
```

---

## 13. 執行順序

| 階段 | 內容 | 出口條件 |
|---|---|---|
| **0** | 解除前置阻斷：`P-1`–`P-8` 全綠 | 兩 surface 皆可登入同一 DB |
| **1** | 跑 F 群組（`U-F1` 最優先） | **產出 iframe 能力上界清單**——它決定 `U-C4`／`U-C24`／`U-C25` 是「可修」還是「結構性不可能」 |
| **2** | 跑 A + B 群組 | 通道與會話層無 Blocker，才有意義往上測 |
| **3** | 跑 E 群組 | `web.base.url` 策略確立並驗證（`G-01` 關閉） |
| **4** | 跑 C 群組（後台原語） | 覆蓋第 9 節 13 apps 的所有原語 |
| **5** | 跑 D 群組（前台／Portal） | `website` 模組完整覆蓋 |
| **6** | 第 9 節模組宣告逐一核對，補 L6 殘餘 | 守恆檢查通過 |
| **7** | 彙整落差報告與修補提案 | 交付 |

> 階段 1 先行是刻意的：`U-F1` 的結果會把一整批項目從「待修 GAP」重分類為
> 「結構性不可能，需 public 承接」，避免在做不到的事情上耗工。

---

## 附錄 A — 指令速查

```bash
# 靜態閘門（不需部署；需安裝 nginx 與 node）
pytest odoo18ce/tests

# 主機狀態勘查（SSH 進測試機 HAOS；位址不記於本 repo，見 2.2）
ha addons info 1b7b4ce7_odoo18ce
docker exec app_1b7b4ce7_odoo18ce grep -n -A8 'listen 8069' /etc/nginx/nginx.conf
docker exec -u postgres app_1b7b4ce7_odoo18ce \
  psql -d odoo_test -tAc \
  "select key,value from ir_config_parameter where key like 'web.base%'"

# 瀏覽器層（兩個基底各跑一次）
ODOO_BASE_URL=<PUBLIC_BASE>  ... python3 odoo18ce/tests/e2e_adversarial.py
ODOO_BASE_URL=<INGRESS_BASE> ... python3 odoo18ce/tests/e2e_adversarial.py
# 選單／動作爬蟲：每個 surface 各跑一次，再比對（憑證從環境變數或 --env-file 讀，見腳本開頭）
python3 odoo18ce/tests/e2e_menu_action_adapter.py crawl --surface public     --apps contacts,project --env-file .env --out public.jsonl
python3 odoo18ce/tests/e2e_menu_action_adapter.py crawl --surface ha_ingress --apps contacts,project --env-file .env --out ingress.jsonl
python3 odoo18ce/tests/e2e_menu_action_adapter.py diff public.jsonl ingress.jsonl --out diff.jsonl
# 爬蟲搆不到的畫面（沒有自有選單，或唯一選單是 server action）：用 open 逐一指名，再用同一個 diff 比對（#163）
python3 odoo18ce/tests/e2e_menu_action_adapter.py open --surface public     --targets targets.jsonl --env-file .env --out public-open.jsonl
python3 odoo18ce/tests/e2e_menu_action_adapter.py open --surface ha_ingress --targets targets.jsonl --env-file .env --out ingress-open.jsonl
# targets.jsonl：每行一個 {"module": ..., "target": ...}；target 是 window action 的 xmlid 或路由，
# 另需 "expect_model" 或 "expect_selector" 其一，用來確認載入的就是要判的那個畫面（等同爬蟲的 U-C12 檢查）
# target 若指到 Odoo 在純 GET 就會寫入的路由（`GET_WRITING_ROUTES`），只有「收斂」的寫入可以指：
# 再開一次會重算或重存出同一個狀態、渲染出同一個畫面——是 recompute 或 re-store，不是累加，也不是消耗
# （#225 決議、#228 落地）。收斂才能跨 surface 決定性：每個 surface 看到的畫面都已包含自己那次寫入，
# 所以**與順序無關**——兩個 surface 誰先誰後都不固定，也不允許變成前提。既有的例子是 `ensure_cart`：
# 購物車非空就原封不動，正是為了讓兩個 surface 判到同一台車。三類與各自的理由：
#   收斂（照舊只在 `odoo_parity` 可跑，ADR 0012）：`/shop/checkout`、`/shop/address`、
#     `/shop/confirm_order`、`/shop/extra_info`、`/shop/payment`、`/shop/pricelist`、
#     `/shop/change_pricelist`、`/website/lang`（都是在同一台不動的車上重算或重存同樣的值），
#     加上 #228 依 pinned Odoo 稽核後放行的 `/shop/cart` 與 `/my/orders/`（能被 target 走到的寫入
#     都是 idempotent 的 re-store；唯一不收斂的分支要帶 `access_token`／`revive` 查詢字串，而 target
#     不准帶）。
#   消耗 fixture（**任何資料庫都拒**）：`/shop/payment/validate`——確認草稿訂單並清掉購物車，
#     第二個 surface 就沒有車可判，`ensure_cart` 還會默默建出另一張單。
#   未分類（**任何資料庫都拒**，也是所有新增項目的預設）：#226 與 #247 加入的 15 條 portal／`mail`
#     前綴（`/my/invoices/`、`/my/invoices/overdue`、`/my/purchase/`、`/my/projects/`、`/my/tasks/`、
#     `/my/project/`、`/my/task/`、`/mail/unfollow`、`/digest/`、`/chat/`、`/meet/`、
#     `/discuss/channel/`、`/web/image`、`/mail/message/`、`/mail/view`）——沒人照收斂準則讀過，
#     讀過之前一律拒；這個守門寧可多拒。
# 以上兩類的拒絕都發生在開瀏覽器之前（`require_convergent_writes`）。
# target 指到 `GET_WRITING_ROUTES` 的路由時，畫面開完後會再讀一次該 session 的草稿訂單，
# 以一般的 write 列（`sale.order` 的 id 與件數）寫進紀錄的 `writes`（#224）：兩個 surface 都有這一列，
# `diff` 就能像判 cart 寫入一樣，判「這次純 GET 寫出來的東西有沒有跨 surface 分歧」——證據格式不變。
# 那是一列「狀態讀數」而非寫入者宣告：`how` 會寫出前綴與 `GET_WRITING_ROUTES` 記的那筆寫入，
# 因為可指的前綴裡有兩條寫在別處（`/my/orders/` 寫 `access_token`、`/website/lang` 寫訂單行），
# 而 `writes` 只涵蓋 `sale.order`。沒指到前綴的 target 完全不做這次讀取（讀取本身是一次 `/shop/cart`
# 導覽，也會寫），讀不到時不留空列，改把原因接在該筆紀錄的 `result` 後面。
# 行動版模擬：crawl 加 --viewport 390x844
# 共用層 F/A/B/C/D（#143）：先 P-Check、建 P-7 fixture，再跑全部 check，最後守恆檢查
python3 odoo18ce/tests/e2e_parity_shared_layers_live.py pcheck --env-file .env --db <DB>
python3 odoo18ce/tests/e2e_parity_shared_layers_live.py fixtures --env-file .env --db <DB> --run-id <RUN_ID>
python3 odoo18ce/tests/e2e_parity_shared_layers_live.py run --env-file .env --db <DB> --run-id <RUN_ID> --out checks.jsonl
python3 odoo18ce/tests/e2e_parity_shared_layers_live.py report checks.jsonl --issues issues.json
# 對外產出物 E 群組與 U-D8（#145）：容器內先起 SMTP sink，建 fixture，跑 check 與寄信，
# 把 sink 收到的 .eml 複製出來再判郵件，LAN 外開完匿名連結後做守恆檢查，最後 teardown
python3 odoo18ce/tests/e2e_parity_outbound_live.py fixtures --env-file .env --db <DB> --run-id <RUN_ID>
python3 odoo18ce/tests/e2e_parity_outbound_live.py run --env-file .env --db <DB> --run-id <RUN_ID> --out checks.jsonl
python3 odoo18ce/tests/e2e_parity_outbound_live.py mail --env-file .env --db <DB> --run-id <RUN_ID> --mail-dir mail/ --out checks.jsonl
python3 odoo18ce/tests/e2e_parity_outbound_live.py report checks.jsonl --off-lan off-lan.json --issues issues.json
python3 odoo18ce/tests/e2e_parity_outbound_live.py teardown --env-file .env --db <DB> --run-id <RUN_ID>
python3 odoo18ce/tests/e2e_settings_ingress.py
```

## 附錄 B — 與既有文件的關係

| 文件 | 角色 | 與本文件的關係 |
|---|---|---|
| `docs/ADVERSARIAL_E2E_MATRIX.md` | 發版守門的 10 條敵意 journey | 本文件的 `U-A*`／`U-B*` 是其細化；`U-A4` 的判定已由 add-on 內建的 Rewrite scan 在執行期執行（ADR 0005），守門腳本保留為手動驗收工具 |
| `docs/testing/COMMERCIAL_PREDEPLOY.md` | Phase 0–11 商務流程雙 surface 計劃 | **流程縱向**；其每個 Phase 內的畫面套用本文件第 7 節 SOP 與 `U-xx` 項目庫 |
| `docs/plans/2026-09-05-odoo-developer-mode-delta-tdd.md` | 開發者模式差集 | 共用第 1.1 節控制項語意身分定義；本文件不重複開發者模式範圍 |
| `docs/plans/2026-09-02-dual-ingress-cloudflare.md` | 雙閘道架構實作計劃 | 提供本文件第 2.1 節的架構事實 |
