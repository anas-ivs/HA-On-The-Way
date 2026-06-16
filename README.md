# On the way — Add-on Home Assistant

Jejak pesanan penghantaran dan tunggangan anda secara langsung dalam Home Assistant dan
Telegram. Hantar pautan "kongsi" pesanan kepada bot Telegram anda (atau tampal di antara
muka web add-on) dan add-on ini akan mengikuti pesanan secara langsung — menghantar kemas
kini status, anggaran masa tiba, dan lokasi pemandu ke Telegram, mencerminkan semuanya ke
dalam entiti Home Assistant melalui MQTT, serta menyimpan sejarah yang boleh dilayari.

**Perkhidmatan:** kini menyokong **Grab** (makanan & tunggangan). Sokongan untuk foodpanda,
ShopeeFood/Shopee dan lain-lain dirancang apabila kaedah penjejakan tersedia.

## Ciri-ciri

- 🛵 Penjejakan pesanan secara langsung daripada pautan kongsi (kini Grab; lain-lain akan datang) — melalui Telegram **atau** web
- 📦 Sehingga 5 pesanan serentak (boleh dikonfigurasi), setiap satu sebagai slot di bawah
  satu peranti MQTT HA
- 🗺️ Lokasi pemandu dihantar ke Telegram dan satu `device_tracker` HA
- 🔔 Entiti status, anggaran tiba dan masa penghantaran melalui MQTT Discovery
- 🤖 Arahan Telegram (`/list`, `/poll`, `/config`, `/restart`, `/help`) + senarai
  kebenaran sembang (pilihan)
- 🌐 Antara muka web ingress: jejak pesanan baharu, urus pesanan aktif, layari/padam
  sejarah, togol tetapan
- ⚙️ Kawalan tetapan didedahkan sebagai entiti HA; had sejarah FIFO; tahap log piawai

## Pemasangan

1. Dalam Home Assistant: **Tetapan → Add-on → Kedai Add-on → ⋮ → Repositori**.
2. Tambah URL repositori ini:
   ```
   https://github.com/anas-ivs/HA-On-The-Way
   ```
3. Pasang **On the way** dari kedai, konfigurasikan, dan mulakan.

## Keperluan

- Token bot Telegram ([@BotFather](https://t.me/BotFather))
- Token akses jangka panjang Home Assistant (untuk zon waktu)
- Pelayan MQTT + integrasi MQTT (cth. add-on Mosquitto) — pilihan; tanpanya, penjejakan
  Telegram masih berfungsi dan entiti HA dilangkau.

## Konfigurasi & penggunaan

Lihat tab **Documentation** add-on (dipaparkan daripada
[`grab_tracker/DOCS.md`](grab_tracker/DOCS.md)) untuk rujukan penuh pilihan, arahan
Telegram, senarai entiti, dan penyelesaian masalah.

## Lesen

[MIT](LICENSE)
