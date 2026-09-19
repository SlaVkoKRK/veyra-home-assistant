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

- Veyra **0.8.3+**,
- Home Assistant **2025.6.0+**,
- skonfigurowana integracja MQTT w Home Assistant, korzystająca z tego samego brokera co Veyra,
- Home Assistant Companion App na telefonach, które mają otrzymywać push.

## Kamery

Dla każdej kamery integracja tworzy niezależną encję `camera` z własnym `unique_id` i `device_info`. Miniatura/still jest pobierana z per-kamera snapshot API Veyra, a RTSP/go2rtc służy do LIVE.

## Wbudowane powiadomienia — bez automatyzacji

Integracja nasłuchuje `ainvr/events` i każdy `new` / `update` przechodzący filtry wysyła natychmiast jako push. Integracja nie ogranicza częstotliwości — rytm kontroluje sama Veyra.

Poziomy klas są po polsku: `Wyłączone`, `Ciche`, `Normalne`, `Pilne`, `Krytyczne`.

## Telefony docelowe

**Veyra → Konfiguruj** pokazuje wszystkie wykryte `notify.mobile_app_*`. Każde urządzenie można globalnie zaznaczyć lub odznaczyć. Pusta lista oznacza brak wysyłki.

## Inteligentne wyciszenie kamery — 0.2.7

Integracja zlicza wysłane push osobno dla każdej kamery. Domyślnie, gdy jedna kamera wygeneruje **12 powiadomień w 90 sekund**, Home Assistant wysyła pytanie:

- **🔕 Wycisz 15 min** — wycisza wyłącznie push z tej kamery,
- **🔔 Zostaw aktywną** — alerty lecą dalej.

Próg, okno zliczania oraz czas wyciszenia są ustawiane globalnie w **Veyra → Konfiguruj**. Dostępne czasy wyciszenia: `10 / 15 / 20 / 30 min`.

Wyciszenie nie zatrzymuje detekcji, MQTT, eventów, snapshotów ani encji Home Assistant. Po czasie powiadomienia włączają się automatycznie. Po wyciszeniu integracja wysyła ciche potwierdzenie z akcją **🔔 Włącz teraz**, która natychmiast cofa mute.

Pytanie o wyciszenie ma per-kamera cooldown 15 minut, więc wybranie **Zostaw aktywną** nie powoduje ponownego pytania po kolejnych kilku alertach. Tymczasowe mute jest stanem runtime i nie jest zachowywane po restarcie Home Assistant.

## Bieżący obraz i pewność — 0.2.4 / Veyra 0.8.3

`top_score` w Veyra jest historycznym maksimum tracka i nie jest bieżącą pewnością. Integracja 0.2.4 pokazuje w powiadomieniu `after.score`, czyli aktualny wynik ostatniego realnego trafienia detektora.

Veyra 0.8.3 utrzymuje osobny `current.jpg` dla aktywnego obiektu. Jest on nadpisywany przy każdym realnym trafieniu detektora i ma własny `notification.version`. Best thumbnail oraz finalny snapshot galerii pozostają niezależne.

Każdy push używa stabilnego `tag` eventu, ale adres obrazka zawiera wersję bieżącego kadru w ścieżce. Dzięki temu Companion/iOS nie może użyć poprzedniego załącznika z cache, a jedno powiadomienie nadal jest aktualizowane.

Format pozostaje zgodny z automatyką Veyra/Frigate: tytuł klasy z emoji, nazwa kamery, `• pewność XX%`, czas rozpoczęcia eventu, `/lovelace/monitoring` oraz przycisk **📹 Podgląd kamer**.

## Dynamiczne klasy modelu

Integracja nie ma zaszytej listy 17 klas. Klasy są pobierane dynamicznie z metadanych aktywnego modelu Veyra.
