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
- **Glare Motion Guard** wymaga VEYRA **1.2.76+** i integracji HACS **0.3.2+**,
- dynamiczne encje powiadomień tylko dla klas aktywnych na kamerach są dostępne od HACS **0.3.3**,
- Home Assistant **2025.6.0+**,
- skonfigurowana integracja MQTT w Home Assistant korzystająca z tego samego brokera co Veyra,
- Home Assistant Companion App na telefonach otrzymujących push.

## Wbudowane powiadomienia — bez automatyzacji

Od **0.3.0** integracja używa natywnego kanału `ainvr/notifications`, jeśli CORE go publikuje. Obsługiwane są:

- `prealert` — pierwszy szybki, pewny alarm,
- `confirmed` — niezależne potwierdzenie zapisanego eventu,
- `repeat` — ponawiane ostrzeżenie, gdy obiekt nadal jest aktywny,
- `glare_approach` — ruchome, rosnące źródło silnego światła zbliżające się do kamery.

Integracja **nie wycisza i nie rate-limit'uje** poprawnych alarmów. Rytm oraz maksymalna liczba repeatów są kontrolowane przez Veyra CORE. `prealert`, `confirmed` i każdy `repeat` dostają osobne tagi powiadomień. Dzięki temu potwierdzenie jest drugą szansą dostarczenia, a każdy repeat faktycznie ponownie ostrzega użytkownika zamiast tylko bezgłośnie podmienić poprzednią kartę.

Jeśli CORE nie udostępnia `notifications_topic`, integracja automatycznie wraca do kompatybilnego trybu `ainvr/events`.

## Glare Motion Guard

Od **0.3.2** integracja odbiera z VEYRA CORE alarm `glare_approach`. Domyślnie ma poziom **Pilne** i wysyła komunikat **„Ktoś zbliża się i oślepia kamerę”**. Alert jest generowany przez CORE dopiero wtedy, gdy maska GLARE pokrywa się z ruchem i obszar oślepienia rośnie w czasie — sama statyczna lampa lub pojedynczy skok ekspozycji nie wystarczają.

Dla każdej kamery powstaje też `binary_sensor` **Zbliżające oślepienie** z atrybutami diagnostycznymi: score, wzrost, overlap z ruchem, udział powierzchni, czas i licznik alarmów. Poziom powiadomienia można ustawić osobno przez encję **Oślepianie kamery · powiadomienia**.

## Poziomy powiadomień klas

Dla klas dostępne są poziomy: `Wyłączone`, `Ciche`, `Normalne`, `Pilne`, `Krytyczne`.

Od **0.3.3** encje konfiguracji powiadomień są tworzone **tylko dla klas faktycznie wybranych na co najmniej jednej kamerze**. Przykładowo, jeśli kamery używają łącznie `person`, `car`, `motorcycle`, `truck` i `bear`, tylko te pięć klas pojawi się w Home Assistant — nawet jeśli model zna 17 lub więcej klas.

Lista jest synchronizowana automatycznie z VEYRA:

- dodanie klasy na dowolnej kamerze tworzy jej encję powiadomień,
- jeśli ta sama klasa pozostaje na innej kamerze, encja zostaje,
- usunięcie klasy ze wszystkich kamer usuwa jej encję również z rejestru encji Home Assistant,
- poziom wybrany wcześniej pozostaje zapisany w opcjach integracji, więc po ponownym dodaniu klasy może zostać przywrócony.

**Oślepianie kamery · powiadomienia** jest sygnałem bezpieczeństwa niezależnym od modelu i jest zawsze dostępne. Integracja dodaje tę konfigurację jako pierwszą, a jej nazwa powoduje również wyświetlanie przed zwykłymi `Powiadomienia · klasa` w standardowych listach Home Assistant.

## Telefony docelowe

**Veyra → Konfiguruj** pokazuje wykryte `notify.mobile_app_*`. Możesz wskazać telefony, które mają otrzymywać alerty. Nie ma już ustawień ręcznego/flood mute.

## Obraz powiadomienia

Zwykły event push używa wersjonowanego `current.jpg`, dzięki czemu kolejne alerty aktywnego eventu mogą pokazywać nowszą klatkę bez cache starego obrazu. Dla native lifecycle pewność jest preferowana z `snapshot_score`, a następnie z bieżącego `score`. Glare Motion Guard nie tworzy sztucznego eventu galerii — jego alert otwiera bezpośrednio widok monitoringu.

## Automatyczne odzyskiwanie po restarcie CORE

Integracja nasłuchuje retained `ainvr/available`. Po powrocie CORE do `online` odświeża `/api/ha/v1/info` i automatycznie uzbraja ponownie subskrypcję MQTT — nie trzeba przeładowywać integracji ręcznie.
