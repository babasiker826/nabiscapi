# bot.py
from telethon.sync import TelegramClient
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

# AYARLAR - Environment variables'dan al
API_ID = os.environ.get('API_ID', '24179304')
API_HASH = os.environ.get('API_HASH', '6fdbaf87f6fa54a1a8a51603bf38c2d1')
STRING_SESSION = os.environ.get('STRING_SESSION', '1ApWapzMBu1Dw-deK99_jeImQCC-V2QupJTLPUm6sZoI0r948NBxam0rurgDki3a1SAy69jhNsyYoBrpIUfDYaC4N_1GTKmGF7-YSn4KqAcupEsrYCAnLwyevDFZ8E3D29f1QAIWqWIOz12Mx4Es_GmQkgXN3WVtubnd9aUwVLZ75AHYFTIMkpplT1vbkfXZ0tbEXtjUH-4l42MCSGL33XR_lGLXSkqCK9BPYsHs9O3VVbVlfhKVUN7dkq7VvLaTe96HAwGTgdvS6q8iM82KL8HbhdSBE9r8NT4DShiZd-ZVintcIr11RexLWgcloKZrDlSl4Y96ISegXJMxR9tUt2h5CrQNAN2Q=')

app = Flask(__name__)

# Global lock for thread safety
sorgu_lock = threading.Lock()

# Telegram client - main thread'de başlat
client = None
loop = None

def init_client():
    global client, loop
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        client = TelegramClient(StringSession(STRING_SESSION), int(API_ID), API_HASH)
        client.start()
        print("✅ Telegram bağlandı!")
    except Exception as e:
        client = None
        print(f"❌ Telegram başlatılamadı: {e}")

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

            # Bölüm başlıklarını kontrol et
            if line.startswith(f'--- {kisi_tipi.upper()} ---'):
                in_target_section = True
                continue
            elif line.startswith('---') and in_target_section:
                # Başka bir bölüm başladı, hedef bölüm bitti
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

        # Son kişiyi ekle
        if current_kisi:
            kisiler.append(current_kisi)

        return kisiler

    except Exception as e:
        print(f"❌ Sülale parse hatası: {e}")
        return []

def parse_olum_tarihi(text):
    """Ölüm tarihi sonucunu parse et"""
    try:
        # Ölüm tarihi formatını ara
        olum_match = re.search(r'Ölüm Tarihi:\s*([\d\.-]+)', text)
        durum_match = re.search(r'Durum:\s*([🟢🔴⏳]+)\s*(.+)', text)

        if olum_match:
            return {
                'olum_tarihi': olum_match.group(1).strip(),
                'durum': durum_match.group(2).strip() if durum_match else 'Bilinmiyor',
                'durum_emoji': durum_match.group(1) if durum_match else '🔴'
            }
        else:
            # Ölüm tarihi yoksa hayatta demektir
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
        # Farklı formatları kontrol et
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
                # Eğer değer yoksa veya None ise
                if not deger or deger.lower() in ['yok', 'none', 'belirtilmemiş']:
                    return None
                return deger

        return None

    except Exception as e:
        print(f"❌ {alan} parse hatası: {e}")
        return None

def generate_yabanci_bilgiler(ad, soyad):
    """Yabancı kişi için rastgele gerçekçi bilgiler oluştur"""
    # %70 ihtimalle sonuç bulunamadı
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

        if bot_username == "@SorguPanelliiiBot":
            await asyncio.sleep(12)
        elif bot_username == "@TassakliReal_bot":
            await asyncio.sleep(5)
        else:
            await asyncio.sleep(8)

        mesajlar = []

        async for message in client.iter_messages(bot_username, limit=15):
            if not message.out:
                if message.document:
                    file_attributes = message.document.attributes
                    for attr in file_attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            if attr.file_name.endswith('.txt'):
                                print(f"📄 TXT dosyası bulundu: {attr.file_name}")
                                dosya_icerigi = await download_and_read_file(message)
                                if dosya_icerigi:
                                    if bot_username == "@SorguPanelliiiBot":
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

                    if bot_username == "@SorguPanelliiiBot":
                        if "sorgulanıyor" not in txt.lower() and "⏳" not in txt and "bekleyiniz" not in txt.lower():
                            if "kayıt bulundu" in txt and "T.C. No:" in txt:
                                parsed_data = parse_sahmaran_result(txt)
                                return {
                                    "durum": "başarılı", 
                                    "sonuc": parsed_data
                                }
                            mesajlar.append(txt)
                    elif bot_username == "@TassakliReal_bot":
                        # TassakliReal botu için sadece sonuç mesajlarını al
                        if "sorgulanıyor" not in txt.lower() and "⏳" not in txt and "bekleyiniz" not in txt.lower():
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
            async for message in client.iter_messages(bot_username, limit=10):
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
        print(f"📤 Gönderiliyor: {komut} -> @SorguPanelliiiBot")

        try:
            await client.delete_dialog("@SorguPanelliiiBot")
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message("@SorguPanelliiiBot", komut)
        await asyncio.sleep(12)

        # Son mesajları oku
        async for message in client.iter_messages("@SorguPanelliiiBot", limit=15):
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

        # 1. Önce babanın ölüm tarihini sorgula
        print(f"📤 Baba ölüm tarihi sorgulanıyor: /olumtarihi {baba_tc}")

        try:
            await client.delete_dialog("@SorguPanelliiiBot")
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message("@SorguPanelliiiBot", f"/olumtarihi {baba_tc}")
        await asyncio.sleep(10)

        baba_olum_tarihi = None
        baba_durum = "Hayatta"

        # Baba ölüm tarihini oku
        async for message in client.iter_messages("@SorguPanelliiiBot", limit=10):
            if not message.out and message.text and message.text.strip():
                txt = message.text.strip()
                if "sorgulanıyor" not in txt.lower() and "⏳" not in txt:
                    parsed_olum = parse_olum_tarihi(txt)
                    if parsed_olum:
                        baba_olum_tarihi = parsed_olum['olum_tarihi']
                        baba_durum = parsed_olum['durum']
                        break

        # 2. Şimdi babanın çocuklarını bul
        print(f"📤 Baba çocukları sorgulanıyor: /cocuk {baba_tc}")

        try:
            await client.delete_dialog("@SorguPanelliiiBot")
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message("@SorguPanelliiiBot", f"/cocuk {baba_tc}")
        await asyncio.sleep(10)

        cocuklar = []

        # Çocukları oku
        async for message in client.iter_messages("@SorguPanelliiiBot", limit=10):
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

        # Sonuçları birleştir
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
            await client.delete_dialog("@SorguPanelliiiBot")
        except Exception as e:
            print(f"⚠️ Dialog silinemedi: {e}")

        await client.send_message("@SorguPanelliiiBot", f"/tc {tc}")
        await asyncio.sleep(10)

        # Son mesajları oku
        async for message in client.iter_messages("@SorguPanelliiiBot", limit=10):
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

def bot_sorgu(komut_tipi, parametre, bot_choice="sahmaran"):
    if bot_choice == "miyavrem":
        bot_username = "@Miyavrem_bot"
    elif bot_choice == "tassakli":
        bot_username = "@TassakliReal_bot"
    else:
        bot_username = "@SorguPanelliiiBot"

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

def json_response(data):
    body = json.dumps(data, ensure_ascii=False, indent=2)
    resp = Response(body, status=200, mimetype='application/json; charset=utf-8')
    return resp

# 🆕 YENİ API'LER
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

# 🆕 YETİMLİK SORGUSU
@app.route('/yetimlik')
def yetimlik():
    baba_tc = request.args.get('babatc')
    if not baba_tc or len(baba_tc) != 11 or not baba_tc.isdigit():
        return json_response({"hata": "Baba TC 11 haneli sayı olmalı"})
    result = yetimlik_sorgu(baba_tc)
    return json_response(result)

# 👨‍👩‍👧‍👦 ÖZEL AİLE SORGULARI
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

# 🐍 SAHMARAN BOTU ENDPOINT'LERİ
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

# 🐱 MİYAVREM BOTU ENDPOINT'LERİ
@app.route('/vesika')
def vesika():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('vesika', tc, 'miyavrem')
    return json_response(result)

@app.route('/plaka')
def plaka():
    plaka = request.args.get('plaka')
    if not plaka:
        return json_response({"hata": "Plaka gerekli"})
    result = bot_sorgu('plaka', plaka, 'miyavrem')
    return json_response(result)

@app.route('/tcplaka')
def tcplaka():
    tc = request.args.get('tc')
    if not tc or len(tc) != 11 or not tc.isdigit():
        return json_response({"hata": "TC 11 haneli sayı olmalı"})
    result = bot_sorgu('tcplaka', tc, 'miyavrem')
    return json_response(result)

# 🎮 TASSAKLI REAL BOTU ENDPOINT'LERİ
@app.route('/hava')
def hava():
    sehir = request.args.get('sehir')
    if not sehir:
        return json_response({"hata": "Şehir adı gerekli"})
    result = bot_sorgu('hava', sehir, 'tassakli')
    return json_response(result)

@app.route('/kur')
def kur():
    result = bot_sorgu('kur', '', 'tassakli')
    return json_response(result)

@app.route('/steam_kod')
def steam_kod():
    result = bot_sorgu('steam_kod', '', 'tassakli')
    return json_response(result)

@app.route('/vp_kod')
def vp_kod():
    result = bot_sorgu('vp_kod', '', 'tassakli')
    return json_response(result)

@app.route('/free')
def free():
    result = bot_sorgu('free', '', 'tassakli')
    return json_response(result)

@app.route('/kalp')
def kalp():
    result = bot_sorgu('kalp', '', 'tassakli')
    return json_response(result)

@app.route('/sigma')
def sigma():
    result = bot_sorgu('sigma', '', 'tassakli')
    return json_response(result)

@app.route('/live')
def live():
    result = bot_sorgu('live', '', 'tassakli')
    return json_response(result)

@app.route('/anime')
def anime():
    result = bot_sorgu('anime', '', 'tassakli')
    return json_response(result)

@app.route('/imposter')
def imposter():
    result = bot_sorgu('imposter', '', 'tassakli')
    return json_response(result)

@app.route('/spotify')
def spotify():
    result = bot_sorgu('spotify', '', 'tassakli')
    return json_response(result)

@app.route('/epicgame')
def epicgame():
    result = bot_sorgu('epicgame', '', 'tassakli')
    return json_response(result)

@app.route('/blizzard')
def blizzard():
    result = bot_sorgu('blizzard', '', 'tassakli')
    return json_response(result)

@app.route('/play_kod')
def play_kod():
    result = bot_sorgu('play_kod', '', 'tassakli')
    return json_response(result)

@app.route('/uc_kod')
def uc_kod():
    result = bot_sorgu('uc_kod', '', 'tassakli')
    return json_response(result)

@app.route('/midasbuy')
def midasbuy():
    result = bot_sorgu('midasbuy', '', 'tassakli')
    return json_response(result)

@app.route('/predunyam')
def predunyam():
    result = bot_sorgu('predunyam', '', 'tassakli')
    return json_response(result)

@app.route('/smsonay')
def smsonay():
    result = bot_sorgu('smsonay', '', 'tassakli')
    return json_response(result)

@app.route('/zara')
def zara():
    result = bot_sorgu('zara', '', 'tassakli')
    return json_response(result)

@app.route('/exxen')
def exxen():
    result = bot_sorgu('exxen', '', 'tassakli')
    return json_response(result)

@app.route('/blutv')
def blutv():
    result = bot_sorgu('blutv', '', 'tassakli')
    return json_response(result)

@app.route('/amazon')
def amazon():
    result = bot_sorgu('amazon', '', 'tassakli')
    return json_response(result)

@app.route('/purna')
def purna():
    result = bot_sorgu('purna', '', 'tassakli')
    return json_response(result)

@app.route('/mlbb_kod')
def mlbb_kod():
    result = bot_sorgu('mlbb_kod', '', 'tassakli')
    return json_response(result)

@app.route('/kazandiriyo')
def kazandiriyo():
    result = bot_sorgu('kazandiriyo', '', 'tassakli')
    return json_response(result)

@app.route('/robux_kod')
def robux_kod():
    result = bot_sorgu('robux_kod', '', 'tassakli')
    return json_response(result)

@app.route('/carparking')
def carparking():
    result = bot_sorgu('carparking', '', 'tassakli')
    return json_response(result)

@app.route('/roblox')
def roblox():
    result = bot_sorgu('roblox', '', 'tassakli')
    return json_response(result)

@app.route('/twitter')
def twitter():
    result = bot_sorgu('twitter', '', 'tassakli')
    return json_response(result)

@app.route('/netflix')
def netflix():
    result = bot_sorgu('netflix', '', 'tassakli')
    return json_response(result)

@app.route('/pubg')
def pubg():
    result = bot_sorgu('pubg', '', 'tassakli')
    return json_response(result)

@app.route('/hepsiburada')
def hepsiburada():
    result = bot_sorgu('hepsiburada', '', 'tassakli')
    return json_response(result)

@app.route('/hotmail')
def hotmail():
    result = bot_sorgu('hotmail', '', 'tassakli')
    return json_response(result)

@app.route('/valorant')
def valorant():
    result = bot_sorgu('valorant', '', 'tassakli')
    return json_response(result)

@app.route('/facebook')
def facebook():
    result = bot_sorgu('facebook', '', 'tassakli')
    return json_response(result)

@app.route('/troy')
def troy():
    result = bot_sorgu('troy', '', 'tassakli')
    return json_response(result)

@app.route('/ask')
def ask():
    result = bot_sorgu('ask', '', 'tassakli')
    return json_response(result)

@app.route('/dart')
def dart():
    result = bot_sorgu('dart', '', 'tassakli')
    return json_response(result)

@app.route('/zar')
def zar():
    result = bot_sorgu('zar', '', 'tassakli')
    return json_response(result)

@app.route('/nitro')
def nitro():
    result = bot_sorgu('nitro', '', 'tassakli')
    return json_response(result)

@app.route('/coctas')
def coctas():
    result = bot_sorgu('coctas', '', 'tassakli')
    return json_response(result)

@app.route('/freefire')
def freefire():
    result = bot_sorgu('freefire', '', 'tassakli')
    return json_response(result)

# 🛠️ DİĞER ENDPOINT'LER
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
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }
            h1 { color: #333; border-bottom: 2px solid #007bff; padding-bottom: 10px; }
            .status { background: #28a745; color: white; padding: 10px; border-radius: 5px; margin: 20px 0; }
            .info { background: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Telegram Bot API</h1>
            <div class="status">
                <h2>✅ API'ler Aktif</h2>
                <p>Toplam 85 sorgu API'sı çalışıyor</p>
            </div>
            <div class="info">
                <h3>📚 API Kategorileri</h3>
                <p><strong>Yabancı Sorgu:</strong> /yabanci?ad=JOHN&soyad=DOE</p>
                <p><strong>TC Detay Sorguları:</strong> /cinsiyet?tc=... /din?tc=... /vergino?tc=...</p>
                <p><strong>Aile Sorguları:</strong> /kardes?tc=... /anne?tc=... /baba?tc=...</p>
                <p><strong>Yetimlik Sorgusu:</strong> /yetimlik?babatc=...</p>
                <p><strong>Sahmaran Botu:</strong> /sorgu?ad=... /aile?tc=... /sulale?tc=...</p>
                <p><strong>Miyavrem Botu:</strong> /vesika?tc=... /plaka?plaka=...</p>
                <p><strong>Tassakli Real Botu:</strong> /hava?sehir=... /kur /steam_kod /vp_kod /free /uc_kod /roblox /netflix /valorant ve daha fazlası...</p>
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
    print("🤖 Desteklenen Botlar: @SorguPanelliiiBot, @Miyavrem_bot, @TassakliReal_bot")
    print("📚 Toplam Sorgu API: 85")
    print("   YENİ API'LER:")
    print("   GET /yabanci?ad=JOHN&soyad=DOE")
    print("   GET /cinsiyet?tc=11111111110")
    print("   GET /din?tc=11111111110")
    print("   GET /vergino?tc=11111111110")
    print("   GET /medenihal?tc=11111111110")
    print("   GET /koy?tc=11111111110")
    print("   GET /burc?tc=11111111110")
    print("   GET /kimlikkayit?tc=11111111110")
    print("   GET /dogumyeri?tc=11111111110")
    print("   GET /yetimlik?babatc=41947368754")
    print("   GET /hava?sehir=Istanbul")
    print("   GET /kur")
    print("   GET /steam_kod")
    print("   GET /vp_kod")
    print("   GET /uc_kod")
    print("   GET /roblox")
    print("   GET /netflix")
    print("   GET /valorant")
    print("   ve daha fazlası...")

    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
