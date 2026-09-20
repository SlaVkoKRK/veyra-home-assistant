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

- Veyra **0.8.3+**; natywny lifecycle powiadomień `prealert / confirmed / repeat` jest używany automatycznie przez VEYRA 1.0.7+,
- Home Assistant **2025.6.0+**,
- skonfigurowana integracja MQTT w Home Assistant korzystająca z tego samego brokera co Veyra,
- Home Assistant Companion App na telefonach otrzymujących push.

## Wbudowane powiadomienia — bez automatyzacji

Od **0.3.0** integracja używa natywnego kanału `ainvr/notifications`, jeśli CORE go publikuje. Obsługiwane są:

- `prealert` — pierwszy szybki, pewny alarm,
- `confirmed` — niezależne potwierdzenie zapisanego eventu,
- `repeat` — ponawiane ostrzeżenie, gdy obiekt nadal jest aktywny.

Integracja **nie wycisza i nie rate-limit'uje** poprawnych alarmów. Rytm oraz maksymalna liczba repeatów są kontrolowane przez Veyra CORE. `prealert`, `confirmed` i każdy `repeat` dostają osobne tagi powiadomień. Dzięki temu potwierdzenie jest drugą szansą dostarczenia, a każdy repeat faktycznie ponownie ostrzega użytkownika zamiast tylko bezgłośnie podmienić poprzednią kartę.

Jeśli CORE nie udostępnia `notifications_topic`, integracja automatycznie wraca do kompatybilnego trybu `ainvr/events`.

## Poziomy powiadomień klas

Dla klas dostępne są poziomy: `Wyłączone`, `Ciche`, `Normalne`, `Pilne`, `Krytyczne`. Klasy modelu są pobierane dynamicznie z Veyra — integracja nie ma zaszytej listy obiektów.

## Telefony docelowe

**Veyra → Konfiguruj** pokazuje wykryte `notify.mobile_app_*`. Możesz wskazać telefony, które mają otrzymywać alerty. Nie ma już ustawień ręcznego/flood mute.

## Obraz powiadomienia

Push używa wersjonowanego `current.jpg`, dzięki czemu kolejne alerty aktywnego eventu mogą pokazywać nowszą klatkę bez cache starego obrazu. Dla native lifecycle pewność jest preferowana z `snapshot_score`, a następnie z bieżącego `score`.

## Automatyczne odzyskiwanie po restarcie CORE

Integracja nasłuchuje retained `ainvr/available`. Po powrocie CORE do `online` odświeża `/api/ha/v1/info` i automatycznie uzbraja ponownie subskrypcję MQTT — nie trzeba przeładowywać integracji ręcznie.
