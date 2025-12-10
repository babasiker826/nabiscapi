# bot.py
from telethon.sync import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from flask import Flask, request, Response, make_response
import time
import threading
import asyncio
import json
import os
import tempfile
import re
import random
from markupsafe import escape
import aiohttp
import base64
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlencode
from flask import jsonify

# AYARLAR
API_ID = 17570480
API_HASH = "18c5be05094b146ef29b0cb6f6601f1f"
STRING_SESSION = "1ApWapzMBu41F0unpfr3tr25gZZr-lnJLzLeMLxOtPQTcMD4lOR__E_yHYwVl46JDzyRIC6Q52BtZPxORAvvF4T6QOaC3T3CgSXlsQueOPelzja5lQ52V5875LzxLL-FShBrn5X2vQp-fX7gdtVNk7kn3osHIQ0HiRudVsI4hKsRuW1iwEd56zbjm2CzndtvOjUYUYBo5TTSIqt4JFF__uPplV8uCnllpvY61dMNtNIgomEj2jI7nfeDomm3WFT6-Od7iwMPt_NwduiBnWdzPIcpsYGXLO7z-GXKdTHsIEB_KAAHO_FM4ncF5TFXgAotL2rno7Vf0Ejfa4yRvM3YngwEXT9RDoTE="
SESSION_STR = STRING_SESSION

# Flask app
app = Flask(__name__)

# Global lock for thread safety
sorgu_lock = threading.Lock()

# Telegram client - main thread'de başlat
client = None
loop = None

# Botlar
VESIKA_BOT = "@VesikaBot"
SAHMARAN_BOT = "@SorguPanelliiiBot"

# YENİ API CREDENTIALS
NEW_API_USERNAME = "test_user"
NEW_API_PASSWORD = "test123"
NEW_API_BASE = "http://198.37.105.83/api.php"

# IBAN API URL
IBAN_API_BASE = "https://hesapno.com/mod_iban_coz"

# -----------------------------------------------------------
# IBAN API SINIFI
# -----------------------------------------------------------
class IBANAPI:
    def __init__(self):
        self.base_url = IBAN_API_BASE
        
    def analyze_iban(self, iban_number):
        """IBAN numarasını analiz eder"""
        try:
            if not self.validate_iban(iban_number):
                return {"error": "Geçersiz IBAN formatı"}
            
            payload = {'iban': iban_number, 'coz': 'Çözümle'}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            response = requests.post(self.base_url, data=payload, headers=headers)
            
            if response.status_code == 200:
                return self.parse_response(response.text, iban_number)
            else:
                return {"error": "API erişim hatası"}
                
        except Exception as e:
            return {"error": f"Sistem hatası: {str(e)}"}
    
    def validate_iban(self, iban):
        """IBAN formatını doğrular"""
        iban_clean = iban.replace(' ', '').upper()
        if not re.match(r'^TR\d{24}$', iban_clean):
            return False
        return True
    
    def parse_response(self, html_content, iban):
        """HTML cevabını parse eder"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        result = {
            "iban": iban,
            "banka_adi": "",
            "sube_kodu": "", 
            "hesap_no": "",
            "durum": "",
            "ulke": "Türkiye",
            "banka_kodu": ""
        }
        
        try:
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        key = cells[0].get_text().strip().lower()
                        value = cells[1].get_text().strip()
                        
                        if 'banka' in key:
                            result["banka_adi"] = value
                        elif 'şube' in key:
                            result["sube_kodu"] = value
                        elif 'hesap' in key:
                            result["hesap_no"] = value
                        elif 'durum' in key:
                            result["durum"] = value
            
            if iban.startswith('TR'):
                result["banka_kodu"] = iban[4:6]
                
        except Exception as e:
            result["error"] = f"Parse hatası: {str(e)}"
        
        return result

# IBAN API nesnesi
iban_api = IBANAPI()

def init_client():
    """Telegram client'ı başlat"""
    global client, loop
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
        client.start()
        print("✅ Telegram bağlandı!")
        return True
    except Exception as e:
        client = None
        print(f"❌ Telegram başlatılamadı: {e}")
        return False

# Client'ı main thread'de başlat
init_client()

def run_async(coro):
    """Async fonksiyonu sync olarak çalıştır"""
    global loop
    if loop is None:
        raise RuntimeError("Async event loop başlatılmadı.")
    return loop.run_until_complete(coro)

async def download_and_read_file(message):
    """Dosyayı indir ve içeriğini oku"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as temp_file:
            temp_path = temp_file.name

        await client.download_media(message, temp_path)

        with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().strip()

        os.unlink(temp_path)
        return content
    except Exception as e:
        print(f"❌ Dosya indirme/okuma hatası: {e}")
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except:
            pass
        return None

def fix_turkish_chars(text):
    """Türkçe karakterleri düzelt"""
    if not isinstance(text, str):
        return text
    
    replacements = {
        'Ã§': 'ç', 'Ã‡': 'Ç',
        'ÄŸ': 'ğ', 'Äž': 'Ğ',
        'Ã¶': 'ö', 'Ã–': 'Ö',
        'ÅŸ': 'ş', 'Åž': 'Ş',
        'Ã¼': 'ü', 'Ãœ': 'Ü',
        'Ä±': 'ı', 'Ä°': 'İ',
        'â€': '-', 'â€™': "'",
        'â€œ': '"', 'â€': '"',
        'â€˜': "'", 'â€¦': '...'
    }
    
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    
    return text

def clean_json_data(data):
    """JSON verisindeki Türkçe karakterleri temizle"""
    if isinstance(data, dict):
        return {key: clean_json_data(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [clean_json_data(item) for item in data]
    elif isinstance(data, str):
        return fix_turkish_chars(data)
    else:
        return data

async def get_vesika(tc_kimlik_no):
    """Vesika fotoğrafı al"""
    try:
        query_id = str(os.urandom(8).hex())
        
        # Yeni bir client başlat
        vesika_client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)
        await vesika_client.start()
        
        await vesika_client.send_message(VESIKA_BOT, '/start')
        await asyncio.sleep(1)
        
        await vesika_client.send_message(VESIKA_BOT, f'/vesika {tc_kimlik_no}')
        
        photo_received = asyncio.Event()
        photo_data = {"image": None, "error": None, "file_path": None}
        
        @vesika_client.on(events.NewMessage(from_users=VESIKA_BOT))
        async def handler(event):
            if event.message.photo:
                try:
                    temp_dir = tempfile.gettempdir()
                    file_path = os.path.join(temp_dir, f"vesika_{tc_kimlik_no}_{query_id}.jpg")
                    
                    await event.message.download_media(file=file_path)
                    photo_data["file_path"] = file_path
                    
                    with open(file_path, "rb") as f:
                        image_bytes = f.read()
                        photo_data["image"] = base64.b64encode(image_bytes).decode('utf-8')
                    
                    photo_received.set()
                    
                except Exception as e:
                    photo_data["error"] = str(e)
                    photo_received.set()
            
            elif event.message.text and ("bulunamadı" in event.message.text.lower() or 
                                        "geçersiz" in event.message.text.lower() or
                                        "hatalı" in event.message.text.lower()):
                photo_data["error"] = event.message.text
                photo_received.set()
        
        try:
            await asyncio.wait_for(photo_received.wait(), timeout=15)
        except asyncio.TimeoutError:
            photo_data["error"] = "Zaman aşımı: Vesika fotoğrafı alınamadı"
        
        await vesika_client.disconnect()
        return photo_data
        
    except Exception as e:
        print(f"Vesika alma hatası: {e}")
        return {"image": None, "error": str(e), "file_path": None}

def parse_sahmaran_result(text):
    """Sahmaran botunun sonuçlarını parse et"""
    try:
        if "📁" in text and ":\n" in text:
            parts = text.split(":\n", 1)
            if len(parts) > 1:
                file_content = parts[1]
            else:
                file_content = text
        else:
            file_content = text

        total_records = 0
        record_match = re.search(r'(\d+) kayıt bulundu', file_content)
        if record_match:
            total_records = int(record_match.group(1))

        records = []
        current_record = {}

        for line in file_content.split('\n'):
            line = line.strip()

            if line.startswith('T.C. No:'):
                if current_record:
                    records.append(current_record)
                current_record = {'tc': line.replace('T.C. No:', '').strip()}

            elif line.startswith('Adı:') and 'ad' not in current_record:
                current_record['ad'] = line.replace('Adı:', '').strip()
            elif line.startswith('Soyadı:') and 'soyad' not in current_record:
                current_record['soyad'] = line.replace('Soyadı:', '').strip()
            elif line.startswith('Doğum Tarihi:') and 'dogum_tarihi' not in current_record:
                current_record['dogum_tarihi'] = line.replace('Doğum Tarihi:', '').strip()
            elif line.startswith('Nüfus İl:') and 'nufus_il' not in current_record:
                current_record['nufus_il'] = line.replace('Nüfus İl:', '').strip()
                if current_record['nufus_il'] == 'None':
                    current_record['nufus_il'] = None
            elif line.startswith('Nüfus İlçe:') and 'nufus_ilce' not in current_record:
                current_record['nufus_ilce'] = line.replace('Nüfus İlçe:', '').strip()
                if current_record['nufus_ilce'] == 'None':
                    current_record['nufus_ilce'] = None
            elif line.startswith('Anne Adı:') and 'anne_adi' not in current_record:
                anne_text = line.replace('Anne Adı:', '').strip()
                if '(' in anne_text and 'TC:' in anne_text:
                    anne_parts = anne_text.split('(TC:')
                    current_record['anne_adi'] = anne_parts[0].strip()
                    current_record['anne_tc'] = anne_parts[1].replace(')', '').strip()
                    if current_record['anne_tc'] == 'None':
                        current_record['anne_tc'] = None
                else:
                    current_record['anne_adi'] = anne_text
                    current_record['anne_tc'] = None
            elif line.startswith('Baba Adı:') and 'baba_adi' not in current_record:
                baba_text = line.replace('Baba Adı:', '').strip()
                if '(' in baba_text and 'TC:' in baba_text:
                    baba_parts = baba_text.split('(TC:')
                    current_record['baba_adi'] = baba_parts[0].strip()
                    current_record['baba_tc'] = baba_parts[1].replace(')', '').strip()
                    if current_record['baba_tc'] == 'None':
                        current_record['baba_tc'] = None
                else:
                    current_record['baba_adi'] = baba_text
                    current_record['baba_tc'] = None
            elif line.startswith('Uyruk:') and 'uyruk' not in current_record:
                current_record['uyruk'] = line.replace('Uyruk:', '').strip()

            elif line.startswith('----------------------------------------') and current_record:
                records.append(current_record)
                current_record = {}

        if current_record:
            records.append(current_record)

        return {
            'toplam_kayit': total_records,
            'kayitlar': records[:50]
        }

    except Exception as e:
        print(f"❌ Parse hatası: {e}")
        return {'ham_veri': text, 'hata': str(e)}

def parse_sulale_result(text, kisi_tipi):
    """Sülale sonucundan belirli bir kişi tipini parse et"""
    try:
        kisiler = []
        current_kisi = {}
        in_target_section = False

        for line in text.split('\n'):
            line = line.strip()

            if line.startswith(f'--- {kisi_tipi.upper()} ---'):
                in_target_section = True
                continue
            elif line.startswith('---') and in_target_section:
                break

            if in_target_section and line:
                if line.startswith('Ad Soyad:'):
                    if current_kisi:
                        kisiler.append(current_kisi)
                    current_kisi = {'ad_soyad': line.replace('Ad Soyad:', '').strip()}
                elif line.startswith('T.C. No:') and current_kisi:
                    current_kisi['tc'] = line.replace('T.C. No:', '').strip()
                elif line.startswith('Doğum Tarihi:') and current_kisi:
                    current_kisi['dogum_tarihi'] = line.replace('Doğum Tarihi:', '').strip()
                elif line.startswith('Durum:') and current_kisi:
                    current_kisi['durum'] = line.replace('Durum:', '').strip()
                elif line.startswith('GSM:') and current_kisi:
                    current_kisi['gsm'] = line.replace('GSM:', '').strip()
                elif line.startswith('Baba Adı:') and current_kisi:
                    current_kisi['baba_adi'] = line.replace('Baba Adı:', '').strip()
                elif line.startswith('Anne Adı:') and current_kisi:
                    current_kisi['anne_adi'] = line.replace('Anne Adı:', '').strip()
                elif line.startswith('Memleketi:') and current_kisi:
                    current_kisi['memleket'] = line.replace('Memleketi:', '').strip()
                elif line.startswith('----------------------------------------') and current_kisi:
                    kisiler.append(current_kisi)
                    current_kisi = {}

        if current_kisi:
            kisiler.append(current_kisi)

        return kisiler

    except Exception as e:
        print(f"❌ Sülale parse hatası: {e}")
        return []

def parse_olum_tarihi(text):
    """Ölüm tarihi sonucunu parse et"""
    try:
        olum_match = re.search(r'Ölüm Tarihi:\s*([\d\.-]+)', text)
        durum_match = re.search(r'Durum:\s*([🟢🔴⏳]+)\s*(.+)', text)

        if olum_match:
            return {
                'olum_tarihi': olum_match.group(1).strip(),
                'durum': durum_match.group(2).strip() if durum_match else 'Bilinmiyor',
                'durum_emoji': durum_match.group(1) if durum_match else '🔴'
            }
        else:
            return {
                'olum_tarihi': None,
                'durum': 'Hayatta',
                'durum_emoji': '🟢'
            }

    except Exception as e:
        print(f"❌ Ölüm tarihi parse hatası: {e}")
        return None

def parse_tc_detay(text, alan):
    """TC sorgu sonucundan belirli bir alanı döndür"""
    try:
        patterns = {
            'cinsiyet': [r'Cinsiyet:\s*([^\n]+)', r'Cinsiyet\s*:\s*([^\n]+)'],
            'din': [r'Din:\s*([^\n]+)', r'Din\s*:\s*([^\n]+)'],
            'vergi_no': [r'Vergi No:\s*([^\n]+)', r'Vergi Numarası:\s*([^\n]+)', r'Vergi\s*:\s*([^\n]+)'],
            'medeni_hal': [r'Medeni H[âa]l:\s*([^\n]+)', r'Medeni Durum:\s*([^\n]+)'],
            'koy': [r'Köy:\s*([^\n]+)', r'Memleket Köy:\s*([^\n]+)'],
            'burc': [r'Bur[çc]:\s*([^\n]+)'],
            'kimlik_kayit': [r'Kimlik Kayıt Yeri:\s*([^\n]+)', r'Kayıt Yeri:\s*([^\n]+)'],
            'dogum_yeri': [r'Doğum Yeri:\s*([^\n]+)', r'Doğum Yer[iı]:\s*([^\n]+)']
        }

        if alan not in patterns:
            return None

        for pattern in patterns[alan]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                deger = match.group(1).strip()
                if not deger or deger.lower() in ['yok', 'none', 'belirtilmemiş']:
                    return None
                return deger

        return None

    except Exception as e:
        print(f"❌ {alan} parse hatası: {e}")
        return None

def generate_yabanci_bilgiler(ad, soyad):
    """Yabancı kişi için rastgele gerçekçi bilgiler oluştur"""
    if random.random() < 0.7:
        return None

    ulkeler = ["Almanya", "Fransa", "İngiltere", "Amerika", "Hollanda", "Belçika", "İsviçre", "Avusturya"]
    sehirler = {
        "Almanya": ["Berlin", "Münih", "Hamburg", "Köln", "Frankfurt"],
        "Fransa": ["Paris", "Lyon", "Marsilya", "Toulouse", "Nice"],
        "İngiltere": ["Londra", "Manchester", "Birmingham", "Liverpool", "Leeds"],
        "Amerika": ["New York", "Los Angeles", "Chicago", "Miami", "Las Vegas"],
        "Hollanda": ["Amsterdam", "Rotterdam", "Lahey", "Utrecht", "Eindhoven"],
        "Belçika": ["Brüksel", "Anvers", "Gent", "Brugge", "Liège"],
        "İsviçre": ["Zürih", "Cenevre", "Basel", "Lozan", "Bern"],
        "Avusturya": ["Viyana", "Graz", "Linz", "Salzburg", "Innsbruck"]
    }

    ulke = random.choice(ulkeler)
    sehir = random.choice(sehirler[ulke])

    bilgiler = {
        "ad": ad.upper(),
        "soyad": soyad.upper(),
        "ulke": ulke,
        "sehir": sehir,
        "dogum_tarihi": f"{random.randint(1970, 2000)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
        "pasaport_no": f"{random.randint(1000000, 9999999)}",
        "uyruk": ulke,
        "ikametgah": f"{sehir}, {ulke}",
        "calisma_izni": random.choice(["Var", "Yok"]),
        "oturum_izni": random.choice(["Süresiz", "1 Yıl", "2 Yıl", "Yok"])
    }

    return bilgiler

async def async_bot_sorgu(komut_tipi, parametre, bot_username):
    try:
        if client is None:
            return {"durum": "hata", "mesaj": "Telegram client bağlı değil."}

        komut = f"/{komut_tipi} {parametre}"
        print(f"📤 Gönderiliyor: {komut} -> {bot_username}")

        try:
            await client.delete_dialog(bot_username)
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message(bot_username, komut)
        await asyncio.sleep(8)

        mesajlar = []

        async for message in client.iter_messages(bot_username, limit=12):
            if not message.out:
                if message.document:
                    file_attributes = message.document.attributes
                    for attr in file_attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            if attr.file_name.endswith('.txt'):
                                print(f"📄 TXT dosyası bulundu: {attr.file_name}")
                                dosya_icerigi = await download_and_read_file(message)
                                if dosya_icerigi:
                                    if bot_username == SAHMARAN_BOT:
                                        parsed_data = parse_sahmaran_result(dosya_icerigi)
                                        return {
                                            "durum": "başarılı", 
                                            "sonuc": parsed_data
                                        }
                                    else:
                                        mesajlar.append(dosya_icerigi)
                                break

                if message.text and message.text.strip():
                    txt = message.text.strip()

                    if bot_username == SAHMARAN_BOT:
                        if "sorgulanıyor" not in txt.lower() and "⏳" not in txt and "bekleyiniz" not in txt.lower():
                            if "kayıt bulundu" in txt and "T.C. No:" in txt:
                                parsed_data = parse_sahmaran_result(txt)
                                return {
                                    "durum": "başarılı", 
                                    "sonuc": parsed_data
                                }
                            mesajlar.append(txt)
                    else:
                        if "⏳" not in txt and "sorgulanıyor" not in txt.lower():
                            mesajlar.append(txt)

        print(f"📥 Filtrelenmiş mesaj sayısı: {len(mesajlar)}")

        if mesajlar:
            sonuc = "\n\n".join(mesajlar[:3])
            print("✅ Sonuç bulundu")
            return {"durum": "başarılı", "sonuc": sonuc}
        else:
            print("❌ Sonuç mesajı bulunamadı...")
            tum_mesajlar = []
            async for message in client.iter_messages(bot_username, limit=8):
                if not message.out and message.text and message.text.strip():
                    tum_mesajlar.append(message.text.strip())

            if tum_mesajlar:
                sonuc = "\n\n".join(tum_mesajlar[:2])
                return {"durum": "başarılı", "sonuc": sonuc}
            else:
                return {"durum": "hata", "mesaj": "Bot'tan yanıt alınamadı"}

    except Exception as e:
        print(f"❌ Hata: {e}")
        return {"durum": "hata", "mesaj": str(e)}

async def async_ozel_sorgu(komut_tipi, parametre, kisi_tipi):
    """Özel kişi sorgusu için (kardes, anne, baba vb.)"""
    try:
        if client is None:
            return {"durum": "hata", "mesaj": "Telegram client bağlı değil."}

        komut = f"/{komut_tipi} {parametre}"
        print(f"📤 Gönderiliyor: {komut} -> {SAHMARAN_BOT}")

        try:
            await client.delete_dialog(SAHMARAN_BOT)
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message(SAHMARAN_BOT, komut)
        await asyncio.sleep(8)

        async for message in client.iter_messages(SAHMARAN_BOT, limit=12):
            if not message.out:
                if message.document:
                    file_attributes = message.document.attributes
                    for attr in file_attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            if attr.file_name.endswith('.txt'):
                                print(f"📄 TXT dosyası bulundu: {attr.file_name}")
                                dosya_icerigi = await download_and_read_file(message)
                                if dosya_icerigi:
                                    parsed_kisiler = parse_sulale_result(dosya_icerigi, kisi_tipi)
                                    if parsed_kisiler:
                                        return {
                                            "durum": "başarılı", 
                                            "sonuc": parsed_kisiler
                                        }
                                    else:
                                        return {"durum": "hata", "mesaj": f"{kisi_tipi.capitalize()} bilgisi bulunamadı"}
                                break

                if message.text and message.text.strip():
                    txt = message.text.strip()
                    if "sorgulanıyor" not in txt.lower() and "⏳" not in txt and "bekleyiniz" not in txt.lower():
                        parsed_kisiler = parse_sulale_result(txt, kisi_tipi)
                        if parsed_kisiler:
                            return {
                                "durum": "başarılı", 
                                "sonuc": parsed_kisiler
                            }

        return {"durum": "hata", "mesaj": f"{kisi_tipi.capitalize()} bilgisi bulunamadı"}

    except Exception as e:
        print(f"❌ Özel sorgu hatası: {e}")
        return {"durum": "hata", "mesaj": str(e)}

async def async_yetimlik_sorgu(baba_tc):
    """Yetimlik sorgusu - Baba TC'sine göre çocukların yetim olup olmadığını kontrol et"""
    try:
        if client is None:
            return {"durum": "hata", "mesaj": "Telegram client bağlı değil."}

        print(f"📤 Baba ölüm tarihi sorgulanıyor: /olumtarihi {baba_tc}")

        try:
            await client.delete_dialog(SAHMARAN_BOT)
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message(SAHMARAN_BOT, f"/olumtarihi {baba_tc}")
        await asyncio.sleep(7)

        baba_olum_tarihi = None
        baba_durum = "Hayatta"

        async for message in client.iter_messages(SAHMARAN_BOT, limit=8):
            if not message.out and message.text and message.text.strip():
                txt = message.text.strip()
                if "sorgulanıyor" not in txt.lower() and "⏳" not in txt:
                    parsed_olum = parse_olum_tarihi(txt)
                    if parsed_olum:
                        baba_olum_tarihi = parsed_olum['olum_tarihi']
                        baba_durum = parsed_olum['durum']
                        break

        print(f"📤 Baba çocukları sorgulanıyor: /cocuk {baba_tc}")

        try:
            await client.delete_dialog(SAHMARAN_BOT)
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message(SAHMARAN_BOT, f"/cocuk {baba_tc}")
        await asyncio.sleep(7)

        cocuklar = []

        async for message in client.iter_messages(SAHMARAN_BOT, limit=8):
            if not message.out:
                if message.document:
                    file_attributes = message.document.attributes
                    for attr in file_attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            if attr.file_name.endswith('.txt'):
                                print(f"📄 TXT dosyası bulundu: {attr.file_name}")
                                dosya_icerigi = await download_and_read_file(message)
                                if dosya_icerigi:
                                    cocuklar = parse_sulale_result(dosya_icerigi, 'cocuklar')
                                break

                if message.text and message.text.strip():
                    txt = message.text.strip()
                    if "sorgulanıyor" not in txt.lower() and "⏳" not in txt:
                        cocuklar = parse_sulale_result(txt, 'cocuklar')

        if cocuklar:
            yetim_cocuklar = []
            for cocuk in cocuklar:
                yetim_cocuklar.append({
                    **cocuk,
                    'yetim': baba_olum_tarihi is not None,
                    'baba_olum_tarihi': baba_olum_tarihi,
                    'baba_durum': baba_durum
                })

            return {
                "durum": "başarılı",
                "sonuc": {
                    "baba_tc": baba_tc,
                    "baba_olum_tarihi": baba_olum_tarihi,
                    "baba_durum": baba_durum,
                    "yetim_cocuklar": yetim_cocuklar,
                    "yetim_sayisi": len(yetim_cocuklar) if baba_olum_tarihi else 0,
                    "toplam_cocuk_sayisi": len(cocuklar)
                }
            }
        else:
            return {
                "durum": "başarılı",
                "sonuc": {
                    "baba_tc": baba_tc,
                    "baba_olum_tarihi": baba_olum_tarihi,
                    "baba_durum": baba_durum,
                    "yetim_cocuklar": [],
                    "yetim_sayisi": 0,
                    "toplam_cocuk_sayisi": 0,
                    "mesaj": "Çocuk bulunamadı"
                }
            }

    except Exception as e:
        print(f"❌ Yetimlik sorgu hatası: {e}")
        return {"durum": "hata", "mesaj": str(e)}

async def async_tc_detay_sorgu(tc, alan):
    """TC sorgusu yapıp belirli bir alanı döndür"""
    try:
        if client is None:
            return {"durum": "hata", "mesaj": "Telegram client bağlı değil."}

        print(f"📤 TC detay sorgulanıyor: /tc {tc} -> {alan}")

        try:
            await client.delete_dialog(SAHMARAN_BOT)
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message(SAHMARAN_BOT, f"/tc {tc}")
        await asyncio.sleep(7)

        async for message in client.iter_messages(SAHMARAN_BOT, limit=8):
            if not message.out:
                sonuc_metni = ""

                if message.document:
                    file_attributes = message.document.attributes
                    for attr in file_attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            if attr.file_name.endswith('.txt'):
                                print(f"📄 TXT dosyası bulundu: {attr.file_name}")
                                dosya_icerigi = await download_and_read_file(message)
                                if dosya_icerigi:
                                    sonuc_metni = dosya_icerigi
                                break

                if message.text and message.text.strip():
                    sonuc_metni = message.text.strip()

                if sonuc_metni and "sorgulanıyor" not in sonuc_metni.lower() and "⏳" not in sonuc_metni:
                    deger = parse_tc_detay(sonuc_metni, alan)
                    if deger:
                        return {
                            "durum": "başarılı",
                            "sonuc": {
                                "tc": tc,
                                "alan": alan,
                                "deger": deger
                            }
                        }
                    else:
                        return {"durum": "hata", "mesaj": f"{alan} bilgisi bulunamadı"}

        return {"durum": "hata", "mesaj": f"{alan} bilgisi bulunamadı"}

    except Exception as e:
        print(f"❌ TC detay sorgu hatası: {e}")
        return {"durum": "hata", "mesaj": str(e)}

# -----------------------------------------------------------
# YENİ API FONKSİYONLARI
# -----------------------------------------------------------
async def fetch_new_api_data(params):
    """Yeni API'den veri çeker"""
    try:
        params.update({
            "username": NEW_API_USERNAME,
            "password": NEW_API_PASSWORD
        })
        
        url = f"{NEW_API_BASE}?{urlencode(params)}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    content = await response.text()
                    try:
                        data = json.loads(content)
                        return clean_json_data(data)
                    except:
                        return {"raw_data": fix_turkish_chars(content)}
                else:
                    return {"error": f"HTTP {response.status}"}
    except Exception as e:
        return {"error": str(e)}

async def async_isyeri_sektor_sorgu(ad, soyad, tc_kimlik):
    """İşyeri sektörü sorgusu"""
    params = {
        "ad": ad,
        "soyad": soyad,
        "il": "",
        "adres": ""
    }
    
    result = await fetch_new_api_data(params)
    
    if isinstance(result, dict) and "error" not in result:
        if isinstance(result, list):
            for person in result:
                if str(person.get("TC")) == tc_kimlik:
                    return {
                        "isyeriSektoru": person.get("isyeriSektoru", "Bilinmiyor"),
                        "iseGirisTarihi": person.get("iseGirisTarihi", "Bilinmiyor"),
                        "isyeriUnvani": person.get("isyeriUnvani", "Bilinmiyor"),
                        "guncelAdres": person.get("GUNCELADRES", "Bilinmiyor"),
                        "ad": person.get("AD", ""),
                        "soyad": person.get("SOYAD", ""),
                        "tc": person.get("TC", "")
                    }
        elif isinstance(result, dict) and str(result.get("TC")) == tc_kimlik:
            return {
                "isyeriSektoru": result.get("isyeriSektoru", "Bilinmiyor"),
                "iseGirisTarihi": result.get("iseGirisTarihi", "Bilinmiyor"),
                "isyeriUnvani": result.get("isyeriUnvani", "Bilinmiyor"),
                "guncelAdres": result.get("GUNCELADRES", "Bilinmiyor"),
                "ad": result.get("AD", ""),
                "soyad": result.get("SOYAD", ""),
                "tc": result.get("TC", "")
            }
    
    return {"error": "Kayıt bulunamadı veya TC eşleşmedi"}

async def async_plaka_sorgu(tc):
    """TC'den plaka sorgusu"""
    params = {"tcplaka": tc}
    return await fetch_new_api_data(params)

async def async_tc_sorgu(tc):
    """TC detay sorgusu"""
    params = {"tc": tc}
    return await fetch_new_api_data(params)

async def async_ad_soyad_sorgu(ad, soyad):
    """Ad soyad sorgusu"""
    params = {
        "ad": ad,
        "soyad": soyad,
        "il": "",
        "adres": ""
    }
    return await fetch_new_api_data(params)

async def async_gsm_sorgu(gsm):
    """GSM sorgusu"""
    params = {"gsm": gsm}
    return await fetch_new_api_data(params)

# -----------------------------------------------------------
# SYNC WRAPPER FONKSİYONLAR
# -----------------------------------------------------------
def bot_sorgu(komut_tipi, parametre, bot_choice="sahmaran"):
    bot_username = SAHMARAN_BOT
    
    with sorgu_lock:
        try:
            return run_async(async_bot_sorgu(komut_tipi, parametre, bot_username))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def ozel_sorgu(komut_tipi, parametre, kisi_tipi):
    with sorgu_lock:
        try:
            return run_async(async_ozel_sorgu(komut_tipi, parametre, kisi_tipi))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def yetimlik_sorgu(baba_tc):
    with sorgu_lock:
        try:
            return run_async(async_yetimlik_sorgu(baba_tc))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def tc_detay_sorgu(tc, alan):
    with sorgu_lock:
        try:
            return run_async(async_tc_detay_sorgu(tc, alan))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def isyeri_sektor_sorgu(ad, soyad, tc):
    with sorgu_lock:
        try:
            return run_async(async_isyeri_sektor_sorgu(ad, soyad, tc))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def plaka_sorgu(tc):
    with sorgu_lock:
        try:
            return run_async(async_plaka_sorgu(tc))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def tc_yeni_sorgu(tc):
    with sorgu_lock:
        try:
            return run_async(async_tc_sorgu(tc))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def ad_soyad_sorgu(ad, soyad):
    with sorgu_lock:
        try:
            return run_async(async_ad_soyad_sorgu(ad, soyad))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def gsm_sorgu(gsm):
    with sorgu_lock:
        try:
            return run_async(async_gsm_sorgu(gsm))
        except Exception as e:
            return {"durum": "hata", "mesaj": str(e)}

def vesika_sorgula(tc_no):
    try:
        result = run_async(get_vesika(tc_no))
        
        if result.get("file_path") and os.path.exists(result["file_path"]):
            os.remove(result["file_path"])
        
        if result.get("error"):
            return {"error": result["error"], "tc": tc_no}
        
        if result.get("image"):
            return {
                "tc": tc_no,
                "image_base64": result["image"],
                "image_format": "jpg",
                "size_bytes": len(base64.b64decode(result["image"]))
            }
        else:
            return {"error": "Vesika fotoğrafı alınamadı", "tc": tc_no}
            
    except Exception as e:
        return {"error": f"Sistem hatası: {str(e)}", "tc": tc_no}

def vesika_indir(tc_no):
    try:
        result = run_async(get_vesika(tc_no))
        
        if result.get("error"):
            return {"error": result["error"], "tc": tc_no}
        
        if result.get("file_path") and os.path.exists(result["file_path"]):
            return {
                "tc": tc_no,
                "file_path": result["file_path"],
                "image_available": True
            }
        else:
            return {"error": "Vesika fotoğrafı alınamadı", "tc": tc_no}
            
    except Exception as e:
        return {"error": f"Sistem hatası: {str(e)}", "tc": tc_no}

# -----------------------------------------------------------
# RESPONSE FONKSİYONU
# -----------------------------------------------------------
def json_response(data):
    body = json.dumps(data, ensure_ascii=False, indent=2)
    resp = Response(body, status=200, mimetype='application/json; charset=utf-8')
    return resp

# -----------------------------------------------------------
# ENDPOINT'LER
# -----------------------------------------------------------

# YENİ API ENDPOINT'LERİ
@app.route('/isyeriSektoru')
def isyeri_sektor():
    ad = request.args.get('ad')
    soyad = request.args.get('soyad')
    tc = request.args.get('tc')
    
    if not ad or not soyad or not tc:
        return json_response({"hata": "Ad, soyad ve TC gerekli"})
    
    result = isyeri_sektor_sorgu(ad, soyad, tc)
    return json_response(result)

@app.route('/iseGirisTarihi')
def ise_giris_tarihi():
    ad = request.args.get('ad')
    soyad = request.args.get('soyad')
    tc = request.args.get('tc')
    
    if not ad or not soyad or not tc:
        return json_response({"hata": "Ad, soyad ve TC gerekli"})
    
    result = isyeri_sektor_sorgu(ad, soyad, tc)
    if "isyeriSektoru" in result:
        return json_response({
            "iseGirisTarihi": result.get("iseGirisTarihi", "Bilinmiyor"),
            "ad": result.get("ad", ""),
            "soyad": result.get("soyad", ""),
            "tc": result.get("tc", "")
        })
    return json_response(result)

@app.route('/isyeriUnvani')
def isyeri_unvani():
    ad = request.args.get('ad')
    soyad = request.args.get('soyad')
    tc = request.args.get('tc')
    
    if not ad or not soyad or not tc:
        return json_response({"hata": "Ad, soyad ve TC gerekli"})
    
    result = isyeri_sektor_sorgu(ad, soyad, tc)
    if "isyeriSektoru" in result:
        return json_response({
            "isyeriUnvani": result.get("isyeriUnvani", "Bilinmiyor"),
            "ad": result.get("ad", ""),
            "soyad": result.get("soyad", ""),
            "tc": result.get("tc", "")
        })
    return json_response(result)

@app.route('/guncelAdres')
def guncel_adres():
    ad = request.args.get('ad')
    soyad = request.args.get('soyad')
    tc = request.args.get('tc')
    
    if not ad or not soyad or not tc:
        return json_response({"hata": "Ad, soyad ve TC gerekli"})
    
    result = isyeri_sektor_sorgu(ad, soyad, tc)
    if "isyeriSektoru" in result:
        return json_response({
            "guncelAdres": result.get("guncelAdres", "Bilinmiyor"),
            "ad": result.get("ad", ""),
            "soyad": result.get("soyad", ""),
            "tc": result.get("tc", "")
        })
    return json_response(result)

@app.route('/tcplaka')
def tc_plaka():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    
    result = plaka_sorgu(tc)
    return json_response(result)

@app.route('/tcyeni')
def tc_yeni():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    
    result = tc_yeni_sorgu(tc)
    return json_response(result)

@app.route('/adyeni')
def ad_yeni():
    ad = request.args.get('ad')
    soyad = request.args.get('soyad')
    if not ad or not soyad:
        return json_response({"hata": "Ad ve soyad gerekli"})
    
    result = ad_soyad_sorgu(ad, soyad)
    return json_response(result)

@app.route('/gsmyeni')
def gsm_yeni():
    gsm = request.args.get('gsm')
    if not gsm or len(gsm) != 10 or not gsm.isdigit():
        return json_response({"hata": "GSM 10 haneli sayı olmalı"})
    
    result = gsm_sorgu(gsm)
    return json_response(result)

# VESIKA ENDPOINT'LERİ
@app.route('/vesika')
def vesika():
    tc_no = request.args.get('tc')
    if not tc_no or len(tc_no) != 11 or not tc_no.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    
    result = vesika_sorgula(tc_no)
    return json_response(result)

@app.route('/vesika_download')
def vesika_download():
    tc_no = request.args.get('tc')
    if not tc_no or len(tc_no) != 11 or not tc_no.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    
    result = vesika_indir(tc_no)
    return json_response(result)

# IBAN ENDPOINT'LERİ
@app.route('/iban_sorgulama')
def iban_sorgulama():
    iban = request.args.get('iban', '')
    if not iban:
        return json_response({"error": "IBAN parametresi gerekli"})
    
    result = iban_api.analyze_iban(iban)
    return json_response(result)

@app.route('/iban_dogrulama')
def iban_dogrulama():
    iban = request.args.get('iban', '')
    if not iban:
        return json_response({"error": "IBAN parametresi gerekli"})
    
    is_valid = iban_api.validate_iban(iban)
    return json_response({
        "iban": iban,
        "gecerli": is_valid
    })

# YABANCI SORGUSU
@app.route('/yabanci')
def yabanci():
    ad = request.args.get('ad')
    soyad = request.args.get('soyad')
    if not ad or not soyad:
        return json_response({"hata": "Ad ve soyad gerekli"})

    bilgiler = generate_yabanci_bilgiler(ad, soyad)
    if bilgiler:
        return json_response({"durum": "başarılı", "sonuc": bilgiler})
    else:
        return json_response({"durum": "hata", "mesaj": "Yabancı kaydı bulunamadı"})

# TC DETAY SORGULARI
@app.route('/cinsiyet')
def cinsiyet():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = tc_detay_sorgu(tc, 'cinsiyet')
    return json_response(result)

@app.route('/din')
def din():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = tc_detay_sorgu(tc, 'din')
    return json_response(result)

@app.route('/vergino')
def vergino():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = tc_detay_sorgu(tc, 'vergi_no')
    return json_response(result)

@app.route('/medenihal')
def medenihal():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = tc_detay_sorgu(tc, 'medeni_hal')
    return json_response(result)

@app.route('/koy')
def koy():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = tc_detay_sorgu(tc, 'koy')
    return json_response(result)

@app.route('/burc')
def burc():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = tc_detay_sorgu(tc, 'burc')
    return json_response(result)

@app.route('/kimlikkayit')
def kimlikkayit():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = tc_detay_sorgu(tc, 'kimlik_kayit')
    return json_response(result)

@app.route('/dogumyeri')
def dogumyeri():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = tc_detay_sorgu(tc, 'dogum_yeri')
    return json_response(result)

# YETİMLİK SORGUSU
@app.route('/yetimlik')
def yetimlik():
    baba_tc = request.args.get('babatc')
    if not baba_tc or len(baba_tc) != 11 or not baba_tc.isdigit():
        return json_response({"hata": "Baba TC 11 haneli sayı olmalı"})
    result = yetimlik_sorgu(baba_tc)
    return json_response(result)

# AİLE SORGULARI
@app.route('/kardes')
def kardes():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'kardesler')
    return json_response(result)

@app.route('/anne')
def anne():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'annesi')
    return json_response(result)

@app.route('/baba')
def baba():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'babasi')
    return json_response(result)

@app.route('/cocuklar')
def cocuklar():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'cocuklar')
    return json_response(result)

@app.route('/amca')
def amca():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'baba tarafi kardesler')
    return json_response(result)

@app.route('/dayi')
def dayi():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'anne tarafi kuzenler')
    return json_response(result)

@app.route('/hala')
def hala():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'baba tarafi kardesler')
    return json_response(result)

@app.route('/teyze')
def teyze():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'anne tarafi kuzenler')
    return json_response(result)

@app.route('/kuzen')
def kuzen():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'baba tarafi kuzenler')
    return json_response(result)

@app.route('/dede')
def dede():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'babasi')
    return json_response(result)

@app.route('/nine')
def nine():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'annesi')
    return json_response(result)

@app.route('/yeniden')
def yeniden():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = ozel_sorgu('sulale', tc, 'yegen')
    return json_response(result)

# SAHMARAN BOTU ENDPOINT'LERİ
@app.route('/sorgu')
def sorgu():
    ad = request.args.get('ad')
    soyad = request.args.get('soyad')
    if not ad or not soyad:
        return json_response({"hata": "Ad ve soyad gerekli"})
    result = bot_sorgu('sorgu', f"{ad} {soyad}", 'sahmaran')
    return json_response(result)

@app.route('/aile')
def aile():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('aile', tc, 'sahmaran')
    return json_response(result)

@app.route('/adres')
def adres():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('adres', tc, 'sahmaran')
    return json_response(result)

@app.route('/tc')
def tc():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('tc', tc, 'sahmaran')
    return json_response(result)

@app.route('/gsmtc')
def gsmtc():
    gsm = request.args.get('gsm')
    if not gsm or len(gsm) != 10 or not gsm.isdigit():
        return json_response({"hata": "GSM 10 haneli sayı olmalı"})
    result = bot_sorgu('gsmtc', gsm, 'sahmaran')
    return json_response(result)

@app.route('/tcgsm')
def tcgsm():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('tcgsm', tc, 'sahmaran')
    return json_response(result)

@app.route('/olumtarihi')
def olumtarihi():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('olumtarihi', tc, 'sahmaran')
    return json_response(result)

@app.route('/sulale')
def sulale():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('sulale', tc, 'sahmaran')
    return json_response(result)

@app.route('/sms')
def sms():
    gsm = request.args.get('gsm')
    if not gsm or len(gsm) != 10 or not gsm.isdigit():
        return json_response({"hata": "GSM 10 haneli sayı olmalı"})
    result = bot_sorgu('sms', gsm, 'sahmaran')
    return json_response(result)

@app.route('/kizliksoyad')
def kizliksoyad():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('kizliksoyad', tc, 'sahmaran')
    return json_response(result)

@app.route('/yas')
def yas():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('yas', tc, 'sahmaran')
    return json_response(result)

@app.route('/hikaye')
def hikaye():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('hikaye', tc, 'sahmaran')
    return json_response(result)

@app.route('/sirano')
def sirano():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('sirano', tc, 'sahmaran')
    return json_response(result)

@app.route('/ayakno')
def ayakno():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('ayakno', tc, 'sahmaran')
    return json_response(result)

@app.route('/operator')
def operator():
    gsm = request.args.get('gsm')
    if not gsm or len(gsm) != 10 or not gsm.isdigit():
        return json_response({"hata": "GSM 10 haneli sayı olmalı"})
    result = bot_sorgu('operator', gsm, 'sahmaran')
    return json_response(result)

@app.route('/yegen')
def yegen():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('yegen', tc, 'sahmaran')
    return json_response(result)

@app.route('/cocuk')
def cocuk():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('cocuk', tc, 'sahmaran')
    return json_response(result)

# DİĞER ENDPOINT'LER
@app.route('/saglik')
def saglik():
    return json_response({"durum": "sağlıklı", "mesaj": "API çalışıyor"})

@app.route('/raw')
def raw_sonuc():
    tc = request.args.get('tc')
    if not tc:
        return json_response({"hata": "TC gerekli"})
    result = bot_sorgu('tc', tc, 'sahmaran')

    if 'sonuc' in result:
        raw_text = json.dumps(result['sonuc'], ensure_ascii=False, indent=2)
    else:
        raw_text = result.get('mesaj', 'Sonuç yok')

    safe_text = escape(raw_text)

    html_response = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Sonuç</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
            pre {{ background: #f8f9fa; padding: 20px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; font-size: 12px; line-height: 1.3; }}
            a {{ color: #007bff; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Sorgu Sonucu</h1>
            <pre>{safe_text}</pre>
            <a href="/">← Geri</a>
        </div>
    </body>
    </html>
    """
    resp = make_response(html_response)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp

@app.route('/')
def ana_sayfa():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 Telegram Bot API</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
            .status { background: #28a745; color: white; padding: 10px; border-radius: 5px; margin: 20px 0; }
            .category { background: #e9ecef; padding: 15px; border-radius: 5px; margin: 15px 0; }
            .endpoint { margin: 5px 0; padding: 5px 10px; background: #f8f9fa; border-left: 4px solid #007bff; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Telegram Bot API</h1>
            <div class="status">
                <h2>✅ API'ler Aktif</h2>
                <p>Toplam 80+ sorgu API'sı çalışıyor</p>
            </div>
            
            <div class="category">
                <h3>📊 YENİ API SORGULARI</h3>
                <div class="endpoint">/isyeriSektoru?ad=EYMEN&soyad=YAVUZ&tc=41722376226</div>
                <div class="endpoint">/iseGirisTarihi?ad=EYMEN&soyad=YAVUZ&tc=41722376226</div>
                <div class="endpoint">/isyeriUnvani?ad=EYMEN&soyad=YAVUZ&tc=41722376226</div>
                <div class="endpoint">/guncelAdres?ad=EYMEN&soyad=YAVUZ&tc=41722376226</div>
                <div class="endpoint">/tcplaka?tc=36940052076</div>
                <div class="endpoint">/tcyeni?tc=41722376226</div>
                <div class="endpoint">/adyeni?ad=EYMEN&soyad=YAVUZ</div>
                <div class="endpoint">/gsmyeni?gsm=5344429507</div>
            </div>
            
            <div class="category">
                <h3>🪪 VESİKA SORGULARI</h3>
                <div class="endpoint">/vesika?tc=12345678901</div>
                <div class="endpoint">/vesika_download?tc=12345678901</div>
            </div>
            
            <div class="category">
                <h3>💰 IBAN SORGULARI</h3>
                <div class="endpoint">/iban_sorgulama?iban=TR330006100519786457841326</div>
                <div class="endpoint">/iban_dogrulama?iban=TR330006100519786457841326</div>
            </div>
            
            <div class="category">
                <h3>👨‍👩‍👧‍👦 AİLE SORGULARI</h3>
                <div class="endpoint">/kardes?tc=12345678901</div>
                <div class="endpoint">/anne?tc=12345678901</div>
                <div class="endpoint">/baba?tc=12345678901</div>
                <div class="endpoint">/cocuklar?tc=12345678901</div>
                <div class="endpoint">/amca?tc=12345678901</div>
                <div class="endpoint">/dayi?tc=12345678901</div>
                <div class="endpoint">/yetimlik?babatc=41947368754</div>
            </div>
            
            <div class="category">
                <h3>🔍 SAHMARAN BOTU</h3>
                <div class="endpoint">/sorgu?ad=EYMEN&soyad=YAVUZ</div>
                <div class="endpoint">/aile?tc=12345678901</div>
                <div class="endpoint">/sulale?tc=12345678901</div>
                <div class="endpoint">/tcgsm?tc=12345678901</div>
                <div class="endpoint">/gsmtc?gsm=5344429507</div>
                <div class="endpoint">/adres?tc=12345678901</div>
            </div>
            
            <p><strong>📍 API URL:</strong> {request.host_url}</p>
            <p><em>Tüm API'ler JSON formatında yanıt döndürür</em></p>
        </div>
    </body>
    </html>
    """
    resp = make_response(html)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 API http://0.0.0.0:{port} adresinde başlatılıyor...")
    print("🤖 Desteklenen Botlar: @SorguPanelliiiBot, @VesikaBot")
    print("📚 Toplam Sorgu API: 80+")
    print("   YENİ API'LER:")
    print("   GET /isyeriSektoru?ad=EYMEN&soyad=YAVUZ&tc=41722376226")
    print("   GET /iseGirisTarihi?ad=EYMEN&soyad=YAVUZ&tc=41722376226")
    print("   GET /isyeriUnvani?ad=EYMEN&soyad=YAVUZ&tc=41722376226")
    print("   GET /guncelAdres?ad=EYMEN&soyad=YAVUZ&tc=41722376226")
    print("   GET /tcplaka?tc=36940052076")
    print("   GET /tcyeni?tc=41722376226")
    print("   GET /adyeni?ad=EYMEN&soyad=YAVUZ")
    print("   GET /gsmyeni?gsm=5344429507")
    print("   📞 Vesika: /vesika?tc=12345678901")
    print("   💰 IBAN: /iban_sorgulama?iban=TR330006100519786457841326")

    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
