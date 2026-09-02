import time
import os
import json
import requests

# =========================================================
# CLEAN PUBLISHER CONFIGURATION (ENVIRONMENT VARIABLES)
# =========================================================

# --- SUPABASE CONFIG ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "geekbuying_products")

# --- TELEGRAM CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Multiple Telegram chats can be separated by comma: "@chat1, @chat2"
RAW_TARGET_CHATS = os.getenv("TARGET_CHATS", "@geekbuying_shop")
TARGET_CHATS = [chat.strip() for chat in RAW_TARGET_CHATS.split(",") if chat.strip()]

# --- WEBSITE API CONFIG ---
API_ENDPOINT = os.getenv("API_ENDPOINT")
API_SECRET_KEY = os.getenv("API_SECRET_KEY")

# --- PUBLISHING FREQUENCY (In Minutes) ---
SLEEP_MINUTES = int(os.getenv("SLEEP_MINUTES", "30"))
SLEEP_SECONDS = SLEEP_MINUTES * 60

# --- HISTORY FILE (To prevent duplicates locally) ---
SENT_FILE = "geekbuying_sent.txt"

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def load_sent_ids():
    """Loads already processed Product IDs from local txt file."""
    if not os.path.exists(SENT_FILE):
        return set()
    with open(SENT_FILE, "r") as f:
        return set(line.strip() for line in f)

def save_sent_id(pid):
    """Saves a Product ID to local txt file after successful publish."""
    with open(SENT_FILE, "a") as f:
        f.write(f"{pid}\n")

def delete_from_supabase(pid):
    """Deletes the product from Supabase after successful publishing."""
    endpoint = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?id=eq.{pid}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    try:
        res = requests.delete(endpoint, headers=headers, timeout=15)
        if res.status_code in [200, 204]:
            print(f"🗑️ Successfully DELETED Product ID {pid} from Supabase DB.")
        else:
            print(f"⚠️ Failed to delete from Supabase ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"⚠️ Error deleting from Supabase: {e}")

# =========================================================
# PUBLISHING LOGIC
# =========================================================

def send_to_website_api(deal):
    """Sends clean data from Supabase to your api2.php safely."""
    print(f"🤖 Sending '{deal['title'][:30]}...' to Website API2...")
    
    # --- MERGING AI_CONTEXT & FEATURES ---
    original_ai_context = deal.get('ai_context', '')
    
    # Features text ya JSON array me ho sakta hai, usko safely extract kar rahe hain
    raw_features = deal.get('features', [])
    if isinstance(raw_features, str):
        try:
            features_list = json.loads(raw_features)
        except:
            features_list = [raw_features]
    else:
        features_list = raw_features
        
    # Features ko ek proper text me convert karna taki AI ko padhne me asani ho
    features_text = ""
    if features_list and isinstance(features_list, list):
        features_text = "\n- ".join(features_list)
        
    # Dono ko merge kar diya (ai_context + features)
    combined_information = f"{original_ai_context}\n\nDetailed Features:\n- {features_text}"
    
    payload = {
        'api_key': API_SECRET_KEY,
        'title': deal.get('title', ''),
        'information': combined_information,  # Yahan merged data ja raha hai
        'affiliate_link': deal.get('link', ''),
        'images': deal.get('images', ''),
        'price': deal.get('price', 0), 
        'mrp': deal.get('mrp', 0),     
        'discount': deal.get('discount', 0),
        'c': deal.get('c', 2), 
        'w': deal.get('w', 2)  
    }
    try:
        res = requests.post(API_ENDPOINT, data=payload, timeout=45) 
        if res.status_code == 200:
            print(f"✅ API Success: Saved to DB & AI Started")
            return True
        else:
            print(f"❌ API Failed ({res.status_code}): {res.text[:100]}")
            return False
    except Exception as e:
        print(f"❌ Connection Error to Website API: {e}")
        return False

def send_telegram_alert(deal):
    """Sends ALL images as a Media Group album along with text to Telegram."""
    
    # Safely parse features (Since it might be a JSON string from Supabase)
    raw_features = deal.get('features', [])
    if isinstance(raw_features, str):
        try:
            features = json.loads(raw_features)
        except:
            features = [raw_features]
    else:
        features = raw_features

    feature_text = ""
    if features and isinstance(features, list):
        for f in features[:3]:
            feature_text += f"▪️ {f}\n"
            
    images = deal.get('images', '').split(',')
    
    msg = (
        f"🚨 *GEEKBUYING LOOT: {deal.get('discount', 0)}% OFF* 🚨\n\n"
        f"📦 *{deal.get('title', '')}*\n\n"
        f"💸 *Offer Price:* ${deal.get('price', 0)}  ~${deal.get('mrp', 0)}~\n\n"
        f"⚙️ *Key Features:*\n{feature_text}\n"
        f"🛒 *BUY NOW:*\n{deal.get('link', '')}\n\n"
        f"✈️ _Global Shipping!_"
    )
    
    # Telegram Caption Length Limit safety (1024 chars)
    if len(msg) > 1000:
        msg = msg[:990] + "...\n✈️ _Global Shipping!_"
    
    for chat_id in TARGET_CHATS:
        try:
            if len(images) > 1:
                # Send multiple images as an album
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
                media_group = []
                for idx, img in enumerate(images):
                    if not img.strip(): continue
                    if idx == 0:
                        # First image contains the caption
                        media_group.append({"type": "photo", "media": img.strip(), "caption": msg, "parse_mode": "Markdown"})
                    else:
                        media_group.append({"type": "photo", "media": img.strip()})
                
                if media_group:       
                    payload = {"chat_id": chat_id, "media": json.dumps(media_group)}
                    requests.post(url, data=payload, timeout=15)
                
            elif len(images) == 1 and images[0].strip():
                # Send single image
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                payload = {"chat_id": chat_id, "photo": images[0].strip(), "caption": msg, "parse_mode": "Markdown"}
                requests.post(url, data=payload, timeout=10)
                
            else:
                # Send text only
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": False}
                requests.post(url, data=payload, timeout=10)
                
            print(f"📢 Telegram Sent to {chat_id}")
        except Exception as e:
            print(f"⚠️ Telegram Error for {chat_id}: {e}")

# =========================================================
# MAIN SUPABASE FETCH LOOP
# =========================================================

def run_publisher():
    print("=====================================================")
    print("🚀 SUPABASE TO API PUBLISHER STARTED (NO SCRAPING) 🚀")
    print("=====================================================\n")

    sent_ids = load_sent_ids()
    print(f"[Info] Loaded {len(sent_ids)} already published products from local .txt.")

    endpoint = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?select=*"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        print("\n☁️ Fetching live data from Supabase...")
        response = requests.get(endpoint, headers=headers, timeout=30)
        
        if response.status_code == 200:
            products = response.json()
            print(f"📦 Found {len(products)} total products in database.\n")
            
            for deal in products:
                # Using Supabase's unique row 'id' as the duplicate tracker
                pid = str(deal.get('id'))
                
                if not pid or pid in sent_ids:
                    continue # Skip already processed products
                    
                print(f"[*] Processing ID {pid}: {deal.get('title')}")
                
                # 1. Send to Website API
                api_success = send_to_website_api(deal)
                
                # 2. If API success, send to Telegram & save to history
                if api_success:
                    send_telegram_alert(deal) 
                    
                    # 3. Delete from Supabase to keep DB clean
                    delete_from_supabase(pid)
                    
                    sent_ids.add(pid)
                    save_sent_id(pid)
                    print(f"✅ Product ID {pid} marked as SENT locally.")
                    
                    # Rest to avoid rate-limiting server and telegram
                    print("⏳ Resting for 40 seconds before next product...\n")
                    time.sleep(40) 
                    
        else:
            print(f"❌ Failed to fetch from Supabase ({response.status_code}): {response.text}")
            
    except Exception as e:
        print(f"[!] Critical Error: {e}")
        
    print("\n💤 Cycle complete.")

if __name__ == "__main__":
    # Loop infinitely with 30-minute sleep interval for Render
    while True:
        run_publisher()
        print(f"\n⏳ Cooldown of {SLEEP_MINUTES} minutes ({SLEEP_SECONDS}s) before checking Supabase again...")
        time.sleep(SLEEP_SECONDS)
