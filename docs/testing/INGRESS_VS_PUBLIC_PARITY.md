# HA Ingress ↔ Public Website 功能對等檢測計劃
# Ingress / Public Parity Test Plan

> 目標：讓 **HA Ingress**（`/api/hassio_ingress/<token>/odoo`）能做到 **Public Website**
> （`https://<public_url>`）能做到的每一件事，並把做不到的部分明確化、分級、歸因。
>
> 本文件是**檢測計劃**，不是測試報告。第 11 節的 `G-xx` 是撰寫本計劃時實地勘查
> 已驗證的落差；其餘章節是待執行的檢測項目。
>
> 相關文件：`docs/ADVERSARIAL_E2E_MATRIX.md`（發版守門）、
> `docs/testing/COMMERCIAL_PREDEPLOY.md`（商務流程雙面向）、
> `docs/plans/2026-09-05-odoo-developer-mode-delta-tdd.md`（開發者模式差集）。
> 三者是**流程縱向**，本文件是**能力橫向**；本文件的 `U-xx` 項目庫供三者共用。

---

## 0. 現況摘要（2026-09-08 實地勘查）

| 項目 | 實測值 | 來源 |
|---|---|---|
| Add-on | `1b7b4ce7_odoo18ce` v0.3.35，`state: started` | `ha addons info` |
| Ingress 進入點 | `/api/hassio_ingress/<token>/odoo` | `ha addons info` → `ingress_url` |
| Public 監聽器 | **`return 503;`（整段 server 封閉）** | 容器內 `/etc/nginx/nginx.conf:52-54` |
| `public_url` 選項 | **未設定** | `10-odoo-config.sh:137-148` 預設分支 |
| 使用中 DB | `optionh_woowtech`（107 modules / 13 apps） | `pg_database` + `ir_module_module` |
| 該 DB `web.base.url` | **`http://127.0.0.1:8070`** | `ir_config_parameter` |
| `web.base.url.freeze` | **不存在** | `ir_config_parameter` |
| `website.domain` (id=1) | **空白** | `website` 資料表 |
| 匿名 `/web/login` | 303 → `/web/database/selector`（`list_db=true` 且無 `default_db`） | add-on log |

**因此：本計劃目前無法執行**——public surface 是 fail-closed 狀態，沒有對照組。
第 2.3 節列出解除阻斷的前置條件。

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

---

## 2. 受測基準與前置條件

### 2.1 兩個 surface 的定義

| | Ingress | Public |
|---|---|---|
| 入口 | `https://woowtech-ha.woowtech.io/api/hassio_ingress/<token>/odoo` | `https://<public_url>` |
| nginx 監聽 | `5691`（僅允許 `172.30.32.2`） | `8069`（`$http_host` 必須等於 public host，否則 `444`） |
| 身分前置 | 需先通過 HA 登入 | 無（Odoo 自身登入） |
| 渲染容器 | HA 前端的 **cross-origin iframe** | 瀏覽器頂層文件 |
| URL 改寫 | sub_filter + `<head>` runtime shim | **無任何改寫** |
| `X-Frame-Options` | 被 `proxy_hide_header` 移除 | 保留 Odoo 原值 |
| 上游壓縮 | `Accept-Encoding ""`（停用） | 保留 |
| 資產快取 | 強制 `no-store` | 保留 Odoo 原值 |

Public 是**基準組**，Ingress 是**待測組**。所有比對方向都是「ingress 是否達到 public」。

### 2.2 受測範圍

- **主機**：`woowtech`（`woowtech-ha.woowtech.io` / SSH `woowtech-ssh.woowtech.io`）
- **DB**：`optionh_woowtech`
- **客戶端**：桌機 Chrome（Chromium 穩定版），1920×1080，**單一基準**
  - HA 手機 App WebView、行動版視窗、Safari／非 Chromium **本輪不納入**，
    列為已知未覆蓋風險（見 10.4）
- **已安裝 app（13）**：`account`, `calendar`, `contacts`, `crm`, `hr`, `hr_skills`,
  `mail`, `mass_mailing`, `project`, `project_todo`, `purchase`, `stock`, `website`
- **計劃安裝 app（12）**：`sale_management`, `website_sale`, `point_of_sale`, 金流串接,
  `survey`, `im_livechat`, `event`, `mrp`, `hr_holidays`, `hr_expense`,
  `hr_attendance`／`hr_timesheet`, `hr_recruitment`

### 2.3 前置條件檢查（P-Check，未全過不得往下）

| ID | 前置條件 | 檢查指令 | 目前狀態 |
|---|---|---|---|
| `P-1` | `public_url` 已設定且為 https | `ha addons options 1b7b4ce7_odoo18ce` | ❌ 未設 |
| `P-2` | 8069 對 public host 回應非 503／444 | `curl -sI https://<public_url>/web/login` | ❌ 503 |
| `P-3` | `web.base.url` = public 基底（https） | `psql -tAc "select value from ir_config_parameter where key='web.base.url'"` | ❌ `http://127.0.0.1:8070` |
| `P-4` | `web.base.url.freeze` = `True` | 同上，key `web.base.url.freeze` | ❌ 不存在 |
| `P-5` | `website.domain` = public 基底 | `select domain from website` | ❌ 空白 |
| `P-6` | 兩 surface 可用同一組 Odoo 帳號登入 | 人工 | 待確認 |
| `P-7` | 已建立 run marker 測試 fixture | 見 `COMMERCIAL_PREDEPLOY.md` Phase 0 | 待建立 |
| `P-8` | 本輪允許的破壞性等級已核准 | 人工 | 待確認 |

`P-3`／`P-4` 未達成前，**第 6 節 E 群組（對外產出物 URL）全部項目的結果都不可信**，
因為 Odoo 會在 admin 登入時把 `web.base.url` 覆寫成當次請求的基底。

---

## 3. 核准的刻意分歧白名單（不算落差）

以下差異是設計意圖，**測試要主動驗證它們仍然存在**；分歧消失視為安全迴歸。

| ID | 分歧 | Ingress | Public | 反向驗證方式 |
|---|---|---|---|---|
| `AD-1` | 資料庫管理 | 可用 | `/web/database/*` → **404** | 兩邊各打一次，斷言 404 |
| `AD-2` | XML-RPC DB 服務 | 可用 | `/xmlrpc/db`、`/xmlrpc/2/db` → **404** | 同上 |
| `AD-3` | JSON-RPC 策略 | 直通 | 經 `odoo-jsonrpc-filter`（8071）過濾 | `tests/test-jsonrpc-filter.py` |
| `AD-4` | Host 守門 | 不適用 | 非預期 `Host` → **444** | 用錯誤 Host 打 8069 |
| `AD-5` | `X-Frame-Options` | 移除 | 保留 | 比對回應標頭 |
| `AD-6` | 匿名可達性 | 需 HA session | 完全匿名可達 | 無 HA cookie 打 ingress，須被擋 |
| `AD-7` | LAN 主機埠 | 8069／8072 皆不對 HA host 發佈 | 同左 | 主機端 `ss -ltn` |

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
| `RC-12` | **shim 未攔截的注入路徑** | shim 掛在 `fetch`／`XHR.open`／`history`／`setAttribute`／若干 DOM 屬性 setter／`window.open`／`Worker`／`WebSocket`；其餘途徑未覆蓋 | 見 `U-A6`：`innerHTML`、動態 `<style>`、`sendBeacon`、`EventSource`、CSS `@import` |
| `RC-13` | **HA 宿主干擾** | HA 自身的登入逾時、授權框替換、鍵盤快捷鍵、主題、iframe 尺寸、Supervisor 請求上限與逾時 | 操作到一半 iframe 被換成授權框、快捷鍵無效、大檔上傳被截斷 |
| `RC-14` | **內容型別敏感改寫** | sub_filter 對 HTML／JSON／JS／CSS 規則不同；shim 僅注入 `text/html` | 改錯型別 → JSON 破損、預覽白畫面（v0.3.34/0.3.35 即此類） |
| `RC-15` | **深連結不可分享** | ingress URL 內含 token，換人／換裝置不通用，且外送即外洩 | 書籤失效、貼給同事打不開、token 進入郵件與紀錄 |

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
| `U-A6` | shim 未覆蓋注入路徑稽核 | RC-12 | 在頁面上主動探測下列途徑是否產生逃逸請求：`innerHTML` 注入的 `<a href="/">`／`<img src="/">`、動態插入的 `<style>{url(/…)}`、`navigator.sendBeacon('/…')`、`EventSource('/…')`、CSS `@import url(/…)`、`<use xlink:href="/…">`、`<meta http-equiv=refresh>` | 無逃逸；有逃逸則登記為 shim 缺口並註明途徑 |
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
| `U-C5` | URL 類欄位顯示值 | **RC-9** | 讀取畫面上每個 URL 欄位、連結 `href`、分享網址欄位的**字面值** | 其值必須是 **public 基底**，不得為 `127.0.0.1`、不得含 ingress token |
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
| `U-C23` | 新分頁開啟 | **RC-15** | 點任何 `target="_blank"` 連結、以及「在新分頁開啟」動作 | 記錄其開出的 URL 形態；若含 token 即列 `G`（token 外洩＋不可分享） |
| `U-C24` | 全螢幕 | RC-3 | 任何請求全螢幕的介面（看板全螢幕、編輯器、工作中心） | 能進入全螢幕；不能則列 `GAP` 並標註需 iframe `allow` |
| `U-C25` | 相機／掃碼 | RC-3 | 任何需要 `getUserMedia` 的介面（條碼掃描、簽名拍照） | 能取得裝置授權；不能則列 `GAP` 並標註需 iframe `allow` |
| `U-C26` | 即時（bus） | RC-7/8 | 兩個瀏覽器情境（A=ingress、B=public）互推訊息 | `/websocket` 回 101、worker bundle 200、雙向 ≤ 10s 不需重整 |
| `U-C27` | Service Worker 依賴功能 | **RC-6** | 檢查 PWA 安裝提示、離線可用性、背景同步 | ingress 下必然不可用 → 標 `STRUCTURAL`，並記錄哪些模組依賴它 |

### D 群組 — 前台 / Portal 共用原語（L4）

| ID | 項目 | RC | 測法 | PASS 判定 |
|---|---|---|---|---|
| `U-D1` | Website layout | RC-1 | navbar、footer、語言切換、站內搜尋、cookie bar | 全部可用，連結不逃逸 |
| `U-D2` | Website 編輯器 | RC-1/12/14 | 進入編輯模式、拖放 snippet、開媒體對話框換圖、編輯文字、存檔、行動預覽、頁面屬性、SEO 面板 | 全程無 `AssetsLoadingError`；`/web/bundle` 回傳的資產 URL 帶前綴 |
| `U-D3` | 頁面生命週期 | RC-1 | 新增頁面、發佈、取消發佈、刪除 | 與 public 相同 |
| `U-D4` | Portal 磁貼與清單 | RC-1 | `/my/home` 每個磁貼 → 清單 → 明細 → pager → 麵包屑 → 下載 | 全部可達 |
| `U-D5` | Portal 存取權杖連結 | **RC-9/10** | 產生 portal 分享連結，以**未登入的另一瀏覽器**開啟 | 必須能開；ingress 產生的連結若打不開即 `GAP`（`G-02` 同源） |
| `U-D6` | 前台表單提交 | RC-1/10 | Contact Us 等表單：驗證、送出、確認頁 | 兩邊皆成功 |
| `U-D7` | 匿名前台可達性 | **RC-10** | 以完全未登入身分存取前台頁 | ingress 原理上不可能 → 標 `STRUCTURAL`，指定由 public 承接 |
| `U-D8` | SEO 產出物 | RC-9 | `sitemap.xml`、`robots.txt`、OG meta、canonical、favicon | 其中的 URL 必為 public 基底 |

### E 群組 — 對外產出物 URL（L5，最大盲區）

> 這一群完全在**伺服器端**組出 URL，前端 shim 一律無效。
> 前置條件 `P-3`／`P-4` 未達成前，本群組結果不可信。

| ID | 項目 | RC | 測法 | PASS 判定 |
|---|---|---|---|---|
| `U-E1` | `web.base.url` 不被登入覆寫 | **RC-9** | 記錄現值 → 以 admin 從 ingress 登入 → 重讀 | 值不變；若變成 ingress token URL 即 **Blocker（token 外洩）** |
| `U-E2` | 郵件內連結 | RC-9 | 觸發任一寄信動作（邀請、通知、密碼重設），攔截 outgoing mail 內容 | 所有連結為 public 基底；**不得含 token** |
| `U-E3` | 分享連結欄位 | RC-9 | 每個「分享」對話框中的 URL 欄位 | 值為 public 基底，且外部瀏覽器可開 |
| `U-E4` | 報表內連結與 QR | RC-9 | 產生含 QR／連結的 PDF，解碼 QR | 指向 public 基底 |
| `U-E5` | 附件／檔案的絕對 URL | RC-9 | 取得附件的對外連結 | 同上 |
| `U-E6` | 外部回呼入口 | **RC-10** | 金流 notify／webhook／郵件追蹤 pixel 的目標 URL | 必為 public 基底且對外可達；ingress 不可能承接 → `STRUCTURAL` |
| `U-E7` | 匯出檔內的 URL | RC-9 | 檢查匯出的 xlsx／csv 內含連結欄位 | 同上 |

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
route_prefixes: [/xxx/, /yyy/]                # 需併入 U-A4 白名單檢查的新前綴
module_specific: [<無法被 L0-L5 覆蓋的殘餘>]  # 盡量為空
outbound_urls: [<會產生對外 URL 的功能點>]     # 觸發 E 群組
```

`route_prefixes` 非空時，**必須**同步檢查 `rootfs/etc/nginx/nginx.conf.template`
的 `location ^~ /web/assets/` 區塊是否已列入該前綴（`RC-11`／`U-A4`）。

> 目前 nginx 資產改寫已列的前綴僅有：
> `/web/`、`/website/`、`/mail/`、`/calendar/`、`/base_setup/`、`/my/`、`/report/`、`/odoo`。
> HTML 層另以屬性樣式（`href="/`、`src="/`、`action="/`、`data-src="/`、`srcset="/`、`url(/`）
> 泛化覆蓋，**但 JS/CSS bundle 內的字面量只吃上列固定前綴**。

---

## 9. 已安裝 13 apps 覆蓋宣告

| 模組 | 引用原語 | 新增路由前綴 | 模組特化殘餘 | 對外 URL 功能點 |
|---|---|---|---|---|
| `mail` | C1,C9,C10,C11,C26,C27 | `/mail/`（已列）、`/discuss/`（**待確認**） | 附件預覽器、@提及自動完成 | 郵件內所有連結 `U-E2` |
| `contacts` | C1–C3,C7,C16–C20 | — | 地圖／地址連結 | 名片分享 |
| `calendar` | C1,C3,C9,C10,C26 | `/calendar/`（已列） | 拖放改期、重複事件、行事曆訂閱 URL | 邀請信、`.ics` 訂閱連結 |
| `crm` | C1–C3,C9,C16,C17,C20 | — | 看板拖放、預測視圖 | 商機分享、報價信 |
| `project` / `project_todo` | C1–C3,C9,C16,C17 | `/project/`（**待確認**） | 看板拖放、子任務、**分享唯讀連結** | **`U-E3` 分享連結（`G-02` 現場）** |
| `account` | C1–C3,C16,C17,C20 | `/account/`、`/my/invoices`（**待確認**） | 對帳、稅務、稽核軌跡 | 發票 portal 連結、付款連結、PDF 內 QR |
| `purchase` | C1–C3,C16,C17,C20 | `/purchase/`（**待確認**） | 供應商 portal | 詢價單寄送連結 |
| `stock` | C1–C3,C16,C17,C20 | `/stock/`（**待確認**） | 條碼輸入、批號序號、揀貨介面 | 交貨單 PDF |
| `hr` / `hr_skills` | C1–C3,C7,C16 | `/hr/`（**待確認**） | 組織圖、員工照片 | 員工資料分享 |
| `mass_mailing` | C1,C6,C16,C17 | `/r/`（短連結追蹤，**高風險**）、`/mass_mailing/`、`/mail/track/` | 郵件設計器（iframe 內的 iframe） | **`U-E2`：追蹤連結、退訂連結全部是對外 URL** |
| `website` | D1–D8 全部 | `/website/`（已列）、`/web_editor/`、`/html_editor/` | snippet 編輯器、頁面管理、SEO 面板 | `U-D8` SEO 產出物 |

> 標「**待確認**」者需在執行 `U-A4` 時實測 bundle 內是否存在該前綴的根相對字面量；
> 存在但未列入 nginx 白名單即為 `GAP`。

---

## 10. 待安裝 app 的預先風險登記

裝之前先讀這張表；每一項在安裝當下就要跑對應的 `U` 項目。

### 10.1 銷售 / 電商 / 金流

| 模組 | 預期新增前綴 | 主要根因 | 必跑項目 |
|---|---|---|---|
| `sale_management` | `/sale/`、`/my/orders`、`/my/quotes` | RC-9 | `U-E3`、`U-E2`、`U-C20`、`U-D5` |
| `website_sale` | `/shop/`、`/shop/cart`、`/shop/checkout`、`/shop/payment` | RC-9、**RC-10** | `U-D1`–`U-D7`、`U-E6`；購物車 cookie 走 `U-B2` |
| `point_of_sale` | `/pos/`、`/pos/ui`、`/pos_self_order/` | **RC-6**、RC-3、RC-8 | **`U-C27`（離線能力在 ingress 必失效）**、`U-C24` 全螢幕、`U-C25` 掃碼、`U-F5` 收據列印 |
| 金流串接（ECPay 等） | `/payment/`、各 provider 專屬 return/notify 路徑 | **RC-10、RC-9** | **`U-E6`（return_url／notify_url 必須是 public 且對外可達）**；ingress 原理上無法承接回呼 → `STRUCTURAL` |

> **POS 特別警告**：ingress 的 shim 主動反註冊 service worker 並偽造
> `navigator.serviceWorker`（`RC-6`）。POS 的離線模式建立在 service worker 之上，
> 因此**在 ingress 下極可能完全不可用**。安裝前必須先決定：POS 只走 public，
> 或接受 ingress 下無離線能力。這是設計決策，不是 bug 修正。

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

### 10.4 本輪未覆蓋的已知風險（明列，不假裝測過）

| 項目 | 為何重要 | 處置 |
|---|---|---|
| HA 手機 App WebView | WebView 版本、剪貼簿權限、下載、新分頁行為都與桌機 Chrome 不同；多數 ingress 獨有 bug 只在此浮現 | 下一輪納入；本輪結論不得外推到 App |
| 行動版視窗（390×844） | Odoo 切換到行動版 layout，選單與對話框行為不同 | 同上 |
| Safari／非 Chromium | 第三方 cookie、SharedWorker、clipboard 限制不同 | 同上 |
| 開發者模式差集 | 由 `docs/plans/2026-09-05-odoo-developer-mode-delta-tdd.md` 承接 | 交叉引用，不重複 |

---

## 11. 已驗證的落差登記（撰寫本計劃時實地勘查所得）

> 以下 `G-xx` **不是推測**，是 2026-09-08 在 `woowtech` 主機上實際查證的結果。

| ID | 落差 | 嚴重度 | 根因 | 證據 | 建議處置 |
|---|---|---|---|---|---|
| `G-01` | `optionh_woowtech` 的 `web.base.url` = `http://127.0.0.1:8070`，且 **`web.base.url.freeze` 不存在** | **Blocker** | RC-9 | `ir_config_parameter` 查詢 | 設為 public 基底並加 `web.base.url.freeze=True`。未 freeze 時 Odoo 會在 admin 登入時覆寫成當次請求基底——**從 ingress 登入一次，token 就會被寫進所有分享連結與寄出的郵件** |
| `G-02` | 分享對話框的網址欄位與旁邊的複製鈕在 ingress 不可用 | **Important／Blocker** | RC-9 + RC-3（**兩條獨立故障線**） | 使用者回報 + `G-01` 佐證 | 拆成兩題分別修：<br>(a) **欄位值錯誤**＝`G-01` 的下游，修 `web.base.url` 即改善；<br>(b) **複製鈕無反應**＝ `navigator.clipboard.writeText` 在 cross-origin iframe 需要 `allow="clipboard-write"`。先跑 `U-F1` 確認 HA 是否給了這個權限：**有**→查 Odoo 端呼叫時機；**沒有**→ nginx shim 必須注入 `execCommand('copy')` 或「點擊即全選」的退路 |
| `G-03` | nginx 資產改寫的路由前綴白名單只有 8 個前綴，計劃安裝的 12 個 app 至少引入 15 個新前綴 | **Important**（安裝時觸發） | RC-11 | `nginx.conf.template` `location ^~ /web/assets/` | 改為「前綴清單由設定產生」或改用泛化規則；並把 `U-A4` 納入發版守門 |
| `G-04` | public surface 目前 `return 503`（`public_url` 未設） | **前置阻斷** | — | `/etc/nginx/nginx.conf:52-54` | 決定要不要開；不開則本計劃無法執行 |
| `G-05` | `maindb` 的 `web.base.url` 是 `http://` 而非 `https://` | Important | RC-9 | `ir_config_parameter` | 若該 DB 仍在用則一併修正 |
| `G-06` | `website` (id=1) 的 `domain` 為空白 | Important | RC-9 | `website` 資料表 | 多網站與絕對 URL 產生會受影響，設為 public 基底 |
| `G-07` | 無 `default_db` 且 `list_db=true`，匿名 `/web/login` 303 → `/web/database/selector` | Minor（但影響測試可重現性） | — | add-on log | 測試前設定 `default_db`，避免兩 surface 進入點語意不同 |

---

## 12. 記錄 schema 與交付格式

每個受測項目輸出一筆 `odoo-parity-evidence/v1` JSONL：

```json
{
  "schema": "odoo-parity-evidence/v1",
  "run_id": "WOOW-PARITY-<UTC timestamp>",
  "target": "woowtech",
  "database": "optionh_woowtech",
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

**去識別化硬性規則**：不得寫入憑證、ingress token、原始 URL、query string、cookie 值、
真實客戶資料。URL 一律以「基底代號 + 規範路徑」記錄（例：`<PUBLIC_BASE>/my/orders/42`）。

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
| **4** | 跑 C 群組（後台原語） | 覆蓋已安裝 13 apps 的所有原語 |
| **5** | 跑 D 群組（前台／Portal） | `website` 模組完整覆蓋 |
| **6** | 第 9 節模組宣告逐一核對，補 L6 殘餘 | 守恆檢查通過 |
| **7** | 彙整落差報告與修補提案 | 交付 |

> 階段 1 先行是刻意的：`U-F1` 的結果會把一整批項目從「待修 GAP」重分類為
> 「結構性不可能，需 public 承接」，避免在做不到的事情上耗工。

---

## 附錄 A — 指令速查

```bash
# 靜態閘門（不需部署）
bash odoo18ce/tests/test-dual-gateway.sh
python3 odoo18ce/tests/test-jsonrpc-filter.py
python3 odoo18ce/tests/test-ingress-router-rewrite.py
python3 odoo18ce/tests/test-ingress-content-type-filter.py
python3 odoo18ce/tests/test-settings-icon-rewrite.py

# 現場狀態勘查（SSH 進 HAOS）
ha addons info 1b7b4ce7_odoo18ce
docker exec app_1b7b4ce7_odoo18ce grep -n -A8 'listen 8069' /etc/nginx/nginx.conf
docker exec -u postgres app_1b7b4ce7_odoo18ce \
  psql -d optionh_woowtech -tAc \
  "select key,value from ir_config_parameter where key like 'web.base%'"

# 瀏覽器層（兩個基底各跑一次）
ODOO_BASE_URL=<PUBLIC_BASE>  ... python3 odoo18ce/tests/e2e_adversarial.py
ODOO_BASE_URL=<INGRESS_BASE> ... python3 odoo18ce/tests/e2e_adversarial.py
python3 odoo18ce/tests/e2e_menu_action_crawler.py
python3 odoo18ce/tests/e2e_settings_ingress.py
```

## 附錄 B — 與既有文件的關係

| 文件 | 角色 | 與本文件的關係 |
|---|---|---|
| `docs/ADVERSARIAL_E2E_MATRIX.md` | 發版守門的 10 條敵意 journey | 本文件的 `U-A*`／`U-B*` 是其細化；建議把 `U-A4`（前綴白名單完整性）加入其 release gate |
| `docs/testing/COMMERCIAL_PREDEPLOY.md` | Phase 0–11 商務流程雙 surface 計劃 | **流程縱向**；其每個 Phase 內的畫面套用本文件第 7 節 SOP 與 `U-xx` 項目庫 |
| `docs/plans/2026-09-05-odoo-developer-mode-delta-tdd.md` | 開發者模式差集 | 共用第 1.1 節控制項語意身分定義；本文件不重複開發者模式範圍 |
| `docs/plans/2026-09-02-dual-ingress-cloudflare.md` | 雙閘道架構實作計劃 | 提供本文件第 2.1 節的架構事實 |
