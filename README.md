<p align="center">
  <img src="brand/logo.png" alt="Veyra" width="420">
</p>

# Veyra for Home Assistant

Natywna integracja Home Assistant dla **Veyra AI-NVR**.

## Instalacja

Repozytorium jest przygotowane do instalacji przez HACS jako **Custom repository / Integration**.
Po instalacji: **Ustawienia → Urządzenia i usługi → Dodaj integrację → Veyra**.

Do konfiguracji podajesz tylko adres IP / host Veyra i port WWW Veyra (domyślnie `8080`). Integracja sama pobiera kamery, port go2rtc, topic MQTT i klasy aktywnego modelu.

## Wymagania

- Veyra **0.8.2+**,
- Home Assistant **2025.6.0+**,
- skonfigurowana integracja MQTT w Home Assistant, korzystająca z tego samego brokera co Veyra,
- Home Assistant Companion App na telefonach, które mają otrzymywać push.

## Kamery

Dla każdej kamery integracja tworzy osobną encję `camera`. Miniatura/still jest pobierana bezpośrednio z per-kamera snapshot API Veyra, a RTSP/go2rtc służy tylko do LIVE. Lista kamer jest budowana z sumy `/api/ha/v1/info` oraz aktualnego `/api/ha/v1/status`, dzięki czemu chwilowo niepełna odpowiedź jednego endpointu nie ukrywa kamery.

Dodatkowo każda kamera ma AI Detection ON/OFF, Powiadomienia ON/OFF, Snapshoty ON/OFF, Motion, aktywny obiekt, noc/online, FPS, liczbę aktywnych obiektów i latency detektora.

## Wbudowane powiadomienia — bez automatyzacji

Integracja nasłuchuje topicu `.../events` Veyra przez MQTT i sama wywołuje `notify.mobile_app_*`. Nie trzeba tworzyć automatyzacji YAML.

Od wersji **0.2.2** zachowanie jest celowo takie samo jak w sprawdzonej automatyzacji MQTT: **każdy event `new` lub `update` przechodzący filtry powoduje natychmiastowy push**. Integracja nie ogranicza częstotliwości — rytm aktualizacji kontroluje sama Veyra.

Poziomy dla każdej klasy modelu:

- `Wyłączone`,
- `Ciche`,
- `Normalne`,
- `Pilne`,
- `Krytyczne`.

Domyślnie `person`, `car`, `truck`, `bus`, `bicycle`, `motorcycle` mają poziom `Pilne`, a pozostałe klasy `Wyłączone`.

## Telefony docelowe

**Veyra → Konfiguruj** pokazuje wszystkie wykryte urządzenia Companion App (`notify.mobile_app_*`). Przy pierwszym wejściu wszystkie są zaznaczone; każde można zaznaczyć lub odznaczyć. Pusta lista oznacza brak wysyłki.

## Wygląd powiadomień

Format jest zgodny ze sprawdzoną automatyką Veyra/Frigate: tytuł z ikoną zależną od klasy (`🚨 Wykryto osobę`, `🚗 Wykryto samochód`, itd.), nazwa kamery, `• pewność XX%`, czas rozpoczęcia eventu, kliknięcie otwierające `/lovelace/monitoring` oraz akcja **📹 Podgląd kamer**.

Zdjęcia korzystają ponownie z transportu działającego w 0.2.0: chroniony endpoint HA proxy'uje aktualny thumbnail Veyra. Każdy kolejny push tego samego eventu używa tego samego `tag`, więc powiadomienie jest odświeżane zamiast tworzenia osobnego stosu wpisów.

## Dynamiczne klasy modelu

Integracja nie ma zaszytej listy 17 klas. Veyra 0.8.2 wystawia przez API metadane aktywnego modelu, więc obsługiwane jest dowolnie wiele klas — np. 17 dla EdgeTPU albo większe modele OpenVINO/ONNX.
