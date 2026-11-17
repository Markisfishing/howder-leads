# 開發日誌

> 每結束一個開發階段（或一次對話）就在**最上面**新增一則。開新對話時，先讀最上面一則和 `PROGRESS.md`，就能接上進度。
> 格式固定五段：改了哪些檔案、解決了什麼問題、做了哪些決定、還沒處理的問題、下一步。

---

## 2026-11-17｜M0 規劃與設計完成

**改了哪些檔案**
- `docs/SPEC.md`：新增規格書（目標、角色、流程與狀態機、功能需求和驗收條件、架構、前後端、資料庫、非功能需求、開發階段、待確認事項）
- `backend/db/schema.sql`：新增 PostgreSQL schema，包含 17 張表、4 個指標 view 和 A–D 種子資料
- `frontend/src/styles/design-tokens.css`：新增配色、字級、間距規範
- `frontend/prototypes/recommendations.html`、`.css`：新增推薦清單頁靜態原型
- `CLAUDE.md`：重寫成這個專案的開發規則（原本的內容是別的專案的）
- `.gitignore`、`PROGRESS.md`、`CHANGELOG.md`：新增
- 建立 `frontend/`、`backend/`、`docs/adr/` 資料夾骨架

**解決了什麼問題**
- 原始 Excel 的資料問題：
  - 「端子台使用可能性」混了競合，拆成 `likelihood` 和 `is_competitor` 兩欄。
  - 「建議動作」和優先級重複，改成由優先級推導。
  - 「分類／家數」是混在資料欄裡的圖例，改成獨立的 `dim_priority` 表。
- 定案業務端的完整流程：推薦 → 審核 → 產生草稿 → 預覽核准 → 寄出 → 追蹤 → 回饋給 MLE。

**做了哪些決定**
- 做成 Web，不做桌面軟體。理由是多人共用名單、要有中央紀錄、要串 Outlook。
- 寄信用 Microsoft Graph，不直接用 SMTP。這樣信會從業務本人的信箱寄出，也能讀到回覆。
- 資料夾叫 `frontend` / `backend`。管理頁只是前端裡的 `/admin/*` 路由，不另外做專案。
- 配色：品牌紅降彩度成磚紅 `#B4433A` 當主色，淺色暖白底。
- 前端：無樣式的 Radix UI Primitives 加上 CSS Modules，不使用帶樣式的元件庫。
- 星級對照：A=5 星、B=4 星、C=2 星、D=1 星。

**還沒處理的問題**
- 優先級 C 的定義和「競合」該歸在哪一級，要等業務主管確認（SPEC 11-1）。
- 每日寄送上限、鎖定天數、部署位置、Microsoft 365 權限核准、模板內容都還沒定案（SPEC 11-2 到 11-5）。

**下一步**
- M1-01 建立後端專案骨架，接著依 `PROGRESS.md` 的 M1 順序進行。
