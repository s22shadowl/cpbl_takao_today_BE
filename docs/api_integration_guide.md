# **CPBL 數據後端 API 整合指南**

歡迎使用 CPBL 數據後端 API！本文件旨在協助前端工程師順利地與本後端服務進行整合。

## **1\. 認證 (Authentication)**

本 API 的所有受保護端點均透過一個 X-API-Key HTTP 標頭進行認證。

**重要：** 前端應用程式**不應該**直接持有或發送此 API 金鑰。

### **認證流程**

標準的認證流程應透過一個 **BFF (Backend for Frontend)** 或伺服器端代理來完成。

1. 前端應用程式向你的 BFF 發送請求（不含 X-API-Key）。
2. 你的 BFF 收到請求後，再轉發至 CPBL 數據後端 API，並在此時**附加**正確的 X-API-Key。
3. CPBL 數據後端 API 驗證金鑰後，回傳資料給 BFF。
4. BFF 再將最終資料回傳給前端應用程式。

sequenceDiagram
 participant FE as 前端應用
 participant BFF as 你的 BFF 伺服器
 participant API as CPBL 數據後端

    FE-\>\>BFF: 請求數據 (e.g., /api/players/王柏融/stats/history)
    BFF-\>\>API: 轉發請求 \+ 附加 X-API-Key
    API--\>\>BFF: 回應數據 (200 OK)
    BFF--\>\>FE: 回傳數據

## **2\. 跨來源資源共用 (CORS)**

本後端服務已啟用 CORS 保護，並採用**白名單機制**。

- **本地開發**：http://localhost:3000 和 http://127.0.0.1:3000 已被預設加入白名單，方便本地開發與測試。
- **生產環境**：在部署前端應用至生產環境前，請務必提供其**完整的來源 URL** (例如 https://your-awesome-frontend.com)，以便我們將其加入後端的 fly.toml 設定檔中的 ALLOWED_ORIGINS 列表。

## **3\. 錯誤處理 (Error Handling)**

本 API 採用標準化的 JSON 格式來回傳所有可預期的錯誤。這能讓前端透過錯誤碼精準判斷問題，並向使用者顯示一致的錯誤訊息。

### **錯誤回應格式**

所有 4xx 或 5xx 的錯誤回應都會遵循以下結構：

{
 "code": "ERROR_CODE_ENUM",
 "message": "A human-readable error message in English."
}

- code (string): 一個獨特、可用於程式邏輯判斷的錯誤碼。
- message (string): 一段供開發者除錯或直接顯示給使用者的英文訊息。

### **錯誤碼清單 (APIErrorCode)**

| HTTP 狀態碼 | code                          | 說明                                                                   |
| :---------- | :---------------------------- | :--------------------------------------------------------------------- |
| 400         | INVALID_INPUT                 | 客戶端提供的輸入無效，例如日期格式錯誤或參數衝突。                     |
| 401         | INVALID_CREDENTIALS           | 未提供 API 金鑰，或提供的金鑰無效。                                    |
| 404         | PLAYER_NOT_FOUND              | 查詢的球員不存在於資料庫中。                                           |
| 404         | RESOURCE_NOT_FOUND            | 請求的資源不存在，例如查詢一個不存在的比賽 ID。                        |
| 500         | INTERNAL_SERVER_ERROR         | 伺服器發生未預期的內部錯誤，這通常表示後端程式碼有 Bug。               |
| 501         | RESULT_BACKEND_NOT_CONFIGURED | (內部使用) 背景任務的結果儲存後端未設定，通常不會發生在生產環境。      |
| 503         | SERVICE_UNAVAILABLE           | 服務暫時不可用，通常是因為依賴的外部服務（如資料庫或 Redis）連線失敗。 |

## **4\. API 使用範例**

以下提供幾個常用端點的 curl 範例。請記得將 your_api_key_here 替換為你的金鑰。

### **範例 1：查詢指定日期的所有比賽**

curl \-X GET "https://cpbl-takao-today-be.fly.dev/api/games/2025-07-22"

### **範例 2：查詢球員的數據歷史 (含分頁)**

curl \-X GET "https://cpbl-takao-today-be.fly.dev/api/players/王柏融/stats/history?skip=0\&limit=10"

### **範例 3：查詢「連續安打」的連線紀錄**

curl \-X GET "https://cpbl-takao-today-be.fly.dev/api/analysis/streaks?definition\_name=consecutive\_hits\&min\_length=3"

### **範例 4：處理錯誤回應**

如果查詢一個不存在的球員：

curl \-X GET "https://cpbl-takao-today-be.fly.dev/api/players/不存在的球員/stats/history"

你將會收到一個 404 Not Found 回應，其 body 內容為：

{
 "code": "PLAYER_NOT_FOUND",
 "message": "The requested player could not be found."
}
