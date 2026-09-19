<p align="center">
  <img src="brand/logo.png" alt="Veyra" width="420">
</p>

# Veyra for Home Assistant

Natywna integracja Home Assistant dla **Veyra AI-NVR**.

## Instalacja

Repozytorium jest przygotowane do instalacji przez HACS jako **Custom repository / Integration**.
Po instalacji: **Ustawienia → Urządzenia i usługi → Dodaj integrację → Veyra**.

Do konfiguracji podajesz tylko:

- adres IP / host Veyra,
- port WWW Veyra (domyślnie `8080`).

Integracja sama pobiera kamery, port go2rtc, topic MQTT i klasy aktywnego modelu.

## Wymagania

- Veyra **0.8.2+**,
- Home Assistant **2025.6.0+**,
- skonfigurowana integracja MQTT w Home Assistant, korzystająca z tego samego brokera co Veyra,
- Home Assistant Companion App na telefonach, które mają otrzymywać push.

Nie wpisujesz do Veyra Integration loginu ani hasła MQTT. Veyra publikuje zdarzenia do brokera, a integracja korzysta z klienta MQTT Home Assistanta.

## Co integracja tworzy

Dla każdej kamery:

- `camera` z live RTSP/go2rtc,
- AI Detection ON/OFF,
- Powiadomienia ON/OFF,
- Snapshoty ON/OFF,
- Motion,
- aktywny obiekt,
- noc / online,
- FPS, liczba aktywnych obiektów i latency detektora.

Globalnie:

- AI Detection,
- Powiadomienia,
- Snapshoty,
- CPU, Intel GPU i Coral latency.

## Wbudowane powiadomienia — bez automatyzacji

Integracja bezpośrednio nasłuchuje topicu `.../events` Veyra przez MQTT i sama wywołuje `notify.mobile_app_*`.
Nie trzeba tworzyć automatyzacji YAML.

Pierwszy alarm eventu używa wybranego poziomu. Kolejne aktualizacje tego samego eventu odświeżają zdjęcie tym samym tagiem; pomiędzy nimi mogą być ciche odświeżenia obrazu, a co skonfigurowany interwał ponawiany jest alert/haptic.

Poziomy dla każdej klasy modelu:

- `Wyłączone`, `Ciche`, `Normalne`, `Pilne`, `Krytyczne`.

Domyślnie:

- `person` → `Pilne`,
- `car`, `truck`, `bus`, `bicycle`, `motorcycle` → `Pilne`,
- pozostałe klasy → `Wyłączone`.

Poziom każdej klasy można zmienić przez encję konfiguracyjną `Powiadomienia · <klasa>`.

### iPhone / iOS

`Pilne` używa `time-sensitive`. `Krytyczne` używa Critical Alert. Przy pierwszej konfiguracji Companion App trzeba zezwolić iOS na Critical Alerts.

### Android

`Pilne` i `Krytyczne` używają `ttl: 0` oraz `priority: high`. `Krytyczne` używa również `alarm_stream`, aby dźwięk alarmowy działał niezależnie od zwykłego poziomu dzwonka. Obejście systemowego DND wymaga jednorazowego zezwolenia użytkownika dla odpowiedniego kanału powiadomień Androida.

## Telefony docelowe

**Veyra → Konfiguruj** pokazuje wszystkie wykryte urządzenia Companion App (`notify.mobile_app_*`). Przy pierwszym wejściu wszystkie są zaznaczone; możesz każde urządzenie zaznaczyć lub odznaczyć. Pusta lista oznacza **nie wysyłaj na żadne urządzenie**.

W tym samym miejscu ustawiasz częstotliwość odświeżania obrazu (domyślnie 2 s) oraz ponawianie wibracji/dźwięku podczas trwającego zdarzenia (domyślnie 5 s, `0` = tylko pierwszy alert).

## Dynamiczne klasy modelu

Integracja nie ma zaszytej listy 17 klas.

Veyra 0.8.2 wystawia przez API metadane aktywnego modelu. Obsługiwane jest dowolnie wiele klas — np. 17 dla obecnego EdgeTPU albo większe modele OpenVINO/ONNX w przyszłości.

Veyra szuka nazw klas w tej kolejności:

1. metadane/ustawienia aktywnego detektora,
2. sidecar modelu (`metadata.yaml`, `*.labels`, `*.names`, `*.json` itd.),
3. metadane OpenVINO IR, jeśli są dostępne,
4. `classes:` w konfiguracji Veyra jako fallback.

## Snapshot do push

Telefon nie musi mieć bezpośredniego dostępu do adresu Veyra. Integracja wystawia chroniony endpoint Home Assistanta i przez niego proxy'uje thumbnail eventu z Veyra.

## Uwaga o częstych aktualizacjach

Home Assistant Companion ma limit zwykłych pushy na urządzenie. Dlatego odświeżanie zdjęcia i ponawianie alertu mają osobne interwały. Dzięki temu obraz może być świeży bez generowania dźwięku/wibracji przy każdej pojedynczej aktualizacji MQTT.

## Wygląd powiadomień

Format jest zgodny ze sprawdzoną automatyką Veyra/Frigate: tytuł z ikoną zależną od klasy (`🚨 Wykryto osobę`, `🚗 Wykryto samochód`, itd.), nazwa kamery, druga linia `• pewność XX%`, thumbnail z wersją snapshotu, czas rozpoczęcia eventu, kliknięcie otwierające `/lovelace/monitoring` oraz akcja **📹 Podgląd kamer**.

Podczas trwającego eventu zdjęcie może aktualizować się częściej niż alert. Co skonfigurowany interwał integracja ponawia alert tego samego eventu, aby telefon ponownie zasygnalizował zdarzenie. Android dostaje osobny kanał z `vibrationPattern`; iOS dostaje ponowny alert zgodny z poziomem systemowym.
