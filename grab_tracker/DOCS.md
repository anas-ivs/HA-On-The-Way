# On the way

Jejak pesanan penghantaran dan tunggangan anda secara langsung dalam Home Assistant dan
Telegram. Hantar pautan "kongsi" pesanan kepada bot Telegram anda (atau tampal di antara
muka web add-on) dan add-on ini akan mengikuti pesanan secara langsung — menghantar kemas
kini status, anggaran masa tiba, dan lokasi pemandu ke Telegram, mencerminkan semuanya ke
dalam entiti Home Assistant melalui MQTT, serta menyimpan sejarah yang boleh dilihat dalam
antara muka web.

## Perkhidmatan disokong

| Perkhidmatan | Status |
|--------------|--------|
| **Grab** (makanan & tunggangan) | ✅ Disokong sekarang |
| foodpanda | 🔜 Dirancang |
| ShopeeFood / Shopee | 🔜 Dirancang |
| Lain-lain | 🔜 Akan ditambah jika kaedah penjejakan tersedia |

Buat masa ini, hantar **pautan kongsi Grab** (`https://app.grab.com/s/...`). Sokongan untuk
perkhidmatan lain akan ditambah apabila kaedah penjejakan masing-masing tersedia.

## Yang anda perlukan

1. **Token bot Telegram** — cipta bot dengan [@BotFather](https://t.me/BotFather) dan salin
   tokennya.
2. **Token akses jangka panjang Home Assistant** — Profil → Keselamatan → Token akses
   jangka panjang. Digunakan untuk membaca zon waktu HA supaya masa dipaparkan dengan betul.
3. **Pelayan MQTT + integrasi MQTT** — contohnya add-on Mosquitto. Diperlukan untuk entiti
   Home Assistant. Tanpanya, penjejakan Telegram masih berfungsi; cuma entiti HA dilangkau.

## Persediaan

1. Pasang dan buka **Konfigurasi**.
2. Isi `telegram_bot_token` dan `ha_token` (dan `ha_url` jika bukan nilai lalai).
3. Tetapkan `notify_chat_id` kepada ID sembang Telegram anda jika mahukan mesej "dimulakan"
   semasa but, dan supaya penjejakan dari web mempunyai tempat untuk menghantar kemas kini
   (bot tidak boleh menghantar mesej ke sembang yang belum pernah dilihatnya).
4. Halakan add-on ke pelayan anda dengan `mqtt_host` / `mqtt_port` / `mqtt_username` /
   `mqtt_password`. **Biarkan `mqtt_host` kosong** untuk mengesan pelayan secara automatik
   daripada Supervisor (berfungsi dengan add-on Mosquitto).
5. (Pilihan) Tetapkan `allowed_chat_ids` untuk mengehadkan bot kepada sembang tertentu.
6. **Mulakan** add-on.

## Cara guna

**Daripada Telegram:** hantar pautan kongsi Grab (`https://app.grab.com/s/...`) kepada bot
anda. Add-on akan menyelesaikan pautan itu, mengesahkan penjejakan telah bermula, dan
mengemas kini anda pada setiap perubahan status berserta mesej anggaran tiba/lokasi pemandu
secara berkala sehingga pesanan dihantar, dibatalkan, atau tamat masa.

**Daripada antara muka web:** buka panel add-on, tampal pautan Grab di bahagian *Jejak
Pesanan Baharu*, dan tekan **Jejak** (butang aktif sebaik sahaja pautan kelihatan seperti
URL Grab). Kemas kini dihantar ke `notify_chat_id` anda jika ditetapkan.

Anda boleh menjejak sehingga **`max_concurrent_orders`** pesanan serentak (lalai 5).
Pesanan tambahan akan ditolak dengan sopan sehingga ada slot yang kosong. Pesanan yang sama
dihantar dua kali akan dikesan dan tidak dijejak berganda.

### Arahan Telegram

Taip `/` dalam sembang untuk melihat menu:

| Arahan | Fungsi |
|--------|--------|
| `/list` | Senarai pesanan aktif, setiap satu dengan butang **Muat semula** dan **Henti** |
| `/poll` | Paksa semakan status serta-merta (langkau masa tunggu) |
| `/config` | Togol tetapan (mesej nyahpepijat, pin lokasi pemandu) |
| `/restart` | Hentikan semua penjejakan dan kosongkan cache |
| `/help` | Tunjukkan senarai arahan |

## Entiti Home Assistant

Semua entiti berada di bawah satu peranti bernama **On the way**:

- Bagi setiap slot pesanan (1–N): **Status**, **Anggaran Tiba** (min), **Masa Penghantaran**,
  dan satu `device_tracker` **Pemandu** (dipaparkan pada peta semasa dalam perjalanan).
- **Kawalan tetapan** (boleh diubah dari HA): *Mesej nyahpepijat* (suis), *Pin lokasi
  pemandu* (suis), *Jarak min pin pemandu* (nombor, meter).

Entiti sesuatu slot adalah **tidak tersedia** semasa melahu dan hanya menjadi tersedia
ketika slot itu sedang menjejak pesanan. Mengubah kawalan tetapan di HA, di `/config`, atau
di antara muka web akan memastikan ketiga-tiganya kekal selaras.

## Antara muka web

Buka panel add-on (bar sisi) untuk papan pemuka yang menunjukkan:

- **Jejak Pesanan Baharu** — tampal pautan kongsi Grab dan tekan Jejak.
- **Penjejakan Aktif** — pesanan yang sedang dijejak dengan Muat semula / Henti.
- **Sejarah pesanan** — pesanan terkini; klik baris untuk membuka garis masa acaranya, atau
  guna 🗑 untuk memadam rekod.
- **Tetapan** — togol yang sama seperti `/config`.

## Rujukan konfigurasi

| Pilihan | Lalai | Keterangan |
|---------|-------|------------|
| `telegram_bot_token` | — | Token BotFather (wajib) |
| `ha_token` | — | Token jangka panjang HA, untuk zon waktu (wajib) |
| `ha_url` | `http://homeassistant:8123` | URL asas HA |
| `notify_chat_id` | — | ID sembang untuk mesej but + kemas kini dari web (pilihan) |
| `allowed_chat_ids` | — | ID sembang (dipisah koma) yang dibenarkan; kosong = terbuka kepada semua |
| `poll_interval_prepare` | 120 | Saat semakan semasa menyedia / pemandu ditetapkan |
| `poll_interval_executing` | 30 | Saat semakan semasa pemandu dalam perjalanan |
| `poll_interval_default` | 180 | Saat semakan untuk status lain |
| `max_tracking_timeout` | 7200 | Berhenti menjejak selepas saat ini (2 jam) |
| `max_concurrent_orders` | 5 | Maksimum pesanan dijejak serentak |
| `history_limit` | 50 | Had sejarah pesanan (paling lama dibuang dahulu, FIFO) |
| `log_level` | `info` | `trace`/`debug`/`info`/`notice`/`warning`/`error`/`fatal` |
| `mqtt_host` | — | Hos pelayan; kosong = pengesanan automatik Supervisor |
| `mqtt_port` | 1883 | Port pelayan |
| `mqtt_username` / `mqtt_password` | — | Kelayakan pelayan |

## Perkara penting

- **But semula menghentikan semua penjejakan.** Pesanan yang sedang berjalan tidak
  disambung semula selepas add-on but semula — ia ditandakan sebagai dihentikan. Hantar
  semula pautan untuk menjejak semula.
- **Sejarah dihadkan** kepada `history_limit` (FIFO) — rekod paling lama dibuang apabila had
  dicapai, tiada proses pembersihan diperlukan.
- **Tiada pelayan?** Add-on masih berjalan; Telegram berfungsi dan entiti HA dilangkau.

## Penyelesaian masalah

- **Tiada entiti HA:** semak `mqtt_host`/kelayakan, pastikan pelayan anda berjalan, dan
  integrasi MQTT menghala ke pelayan yang sama. Log mencetak `MQTT connected to …` atau amaran.
- **Tiada mesej but / penjejakan web senyap:** tetapkan `notify_chat_id`.
- **Menu arahan hilang dalam Telegram:** buka semula sembang — Telegram menyimpan cache menu.
- **Bot mengabaikan saya:** jika `allowed_chat_ids` ditetapkan, ID sembang anda mesti ada
  dalam senarai.
- **Terlalu banyak/sedikit log:** laraskan `log_level`.
