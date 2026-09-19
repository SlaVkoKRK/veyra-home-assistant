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

- Veyra **0.8.1+**,
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

Pierwszy alarm eventu używa wybranego poziomu. Kolejne aktualizacje tego samego eventu odświeżają zdjęcie po cichu, z tym samym tagiem, aby nie generować kolejnych głośnych alarmów.

Poziomy dla każdej klasy modelu:

- `off` — wyłączone,
- `silent` — ciche,
- `normal` — zwykłe,
- `urgent` — pilne / iOS Time Sensitive / Android high priority,
- `critical` — iOS Critical Alert + Android high priority / alarm stream.

Domyślnie:

- `person` → `critical`,
- `car`, `truck`, `bus`, `bicycle`, `motorcycle` → `urgent`,
- pozostałe klasy → `off`.

Poziom każdej klasy można zmienić przez encję konfiguracyjną `Powiadomienia · <klasa>`.

### iPhone / iOS

`urgent` używa `time-sensitive`. `critical` używa Critical Alert. Przy pierwszej konfiguracji Companion App trzeba zezwolić iOS na Critical Alerts.

### Android

`urgent` i `critical` używają `ttl: 0` oraz `priority: high`. `critical` używa również `alarm_stream`, aby dźwięk alarmowy działał niezależnie od zwykłego poziomu dzwonka. Obejście systemowego DND wymaga jednorazowego zezwolenia użytkownika dla odpowiedniego kanału powiadomień Androida.

## Telefony docelowe

**Veyra → Konfiguruj** pokazuje wykryte `notify.mobile_app_*` i pozwala wskazać jeden lub wiele telefonów. Jeśli nic nie wybierzesz, Veyra wysyła na wszystkie dostępne usługi `notify.mobile_app_*`.

W tym samym miejscu ustawiasz minimalny odstęp odświeżania powiadomienia (domyślnie 2 s).

## Dynamiczne klasy modelu

Integracja nie ma zaszytej listy 17 klas.

Veyra 0.8.1 wystawia przez API metadane aktywnego modelu. Obsługiwane jest dowolnie wiele klas — np. 17 dla obecnego EdgeTPU albo większe modele OpenVINO/ONNX w przyszłości.

Veyra szuka nazw klas w tej kolejności:

1. metadane/ustawienia aktywnego detektora,
2. sidecar modelu (`metadata.yaml`, `*.labels`, `*.names`, `*.json` itd.),
3. metadane OpenVINO IR, jeśli są dostępne,
4. `classes:` w konfiguracji Veyra jako fallback.

## Snapshot do push

Telefon nie musi mieć bezpośredniego dostępu do adresu Veyra. Integracja wystawia chroniony endpoint Home Assistanta i przez niego proxy'uje thumbnail eventu z Veyra.

## Uwaga o częstych aktualizacjach

Home Assistant Companion ma limit zwykłych pushy na urządzenie. Dlatego pierwszy alert jest właściwego poziomu, a kolejne update'y są ciche i zastępują poprzednią aktualizację eventu. Minimalny interwał jest konfigurowalny.
