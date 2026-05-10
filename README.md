# MQTT Light Switch FastAPI

Projekt symuluje komunikację aplikacji webowej z prostymi włącznikami światła przez MQTT.

Składa się z dwóch aplikacji:

1. `app` — aplikacja webowa FastAPI.
2. `simulator` — aplikacja symulująca sterownik oświetlenia, która odbiera komunikaty MQTT i wysyła potwierdzenia.

Broker MQTT działa lokalnie przez Mosquitto z `docker-compose.yml`.

## Architektura komunikacji MQTT

Użyte tematy:

| Operacja | Topic | Nadawca | Odbiorca |
|---|---|---|---|
| Rejestracja włącznika | `light/register/request` | FastAPI | Simulator |
| Potwierdzenie rejestracji | `light/register/ack` | Simulator | FastAPI |
| Zmiana stanu światła | `light/{switch_id}/set` | FastAPI | Simulator |
| Potwierdzenie zmiany stanu | `light/{switch_id}/state` | Simulator | FastAPI |

Każde żądanie zawiera `correlation_id`, dzięki czemu FastAPI wie, które potwierdzenie odpowiada danemu żądaniu HTTP.

Włącznik jest zapisywany po stronie FastAPI dopiero wtedy, gdy symulator odeśle poprawne potwierdzenie rejestracji przez MQTT.

## Uruchomienie

### 1. Utworzenie środowiska

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Na Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Uruchomienie brokera MQTT

```bash
docker compose up -d
```

### 3. Uruchomienie symulatora sterownika

W osobnym terminalu:

```bash
python -m simulator.controller
```

### 4. Uruchomienie FastAPI

W kolejnym terminalu:

```bash
uvicorn app.main:app --reload
```

Dokumentacja API będzie dostępna pod adresem:

```text
http://127.0.0.1:8000/docs
```

## Przykładowe użycie

### Dodanie włącznika

```bash
curl -X POST http://127.0.0.1:8000/switches \
  -H "Content-Type: application/json" \
  -d '{"name":"Salon"}'
```

Przykładowa odpowiedź:

```json
{
  "id": "2c4cc6a0-89b7-47c1-b3d4-a41d3cbb10b9",
  "name": "Salon",
  "state": "off"
}
```

### Włączenie światła

```bash
curl -X POST http://127.0.0.1:8000/switches/2c4cc6a0-89b7-47c1-b3d4-a41d3cbb10b9/state \
  -H "Content-Type: application/json" \
  -d '{"state":"on"}'
```

### Wyłączenie światła

```bash
curl -X POST http://127.0.0.1:8000/switches/2c4cc6a0-89b7-47c1-b3d4-a41d3cbb10b9/state \
  -H "Content-Type: application/json" \
  -d '{"state":"off"}'
```

### Pobranie statystyk czasu świecenia

```bash
curl http://127.0.0.1:8000/switches/2c4cc6a0-89b7-47c1-b3d4-a41d3cbb10b9/stats
```

Odpowiedź zawiera:

- `total_on_seconds` — zakończony, naliczony czas świecenia,
- `current_session_seconds` — czas aktualnej sesji, jeżeli światło jest włączone,
- `total_on_seconds_including_current_session` — suma zakończonych sesji i aktualnej sesji.

## Endpointy FastAPI

| Metoda | Ścieżka | Opis |
|---|---|---|
| `GET` | `/health` | Sprawdzenie działania aplikacji |
| `POST` | `/switches` | Dodanie włącznika po potwierdzeniu MQTT |
| `GET` | `/switches` | Lista włączników |
| `GET` | `/switches/{switch_id}` | Szczegóły włącznika |
| `POST` | `/switches/{switch_id}/state` | Włączenie lub wyłączenie światła |
| `GET` | `/switches/{switch_id}/stats` | Statystyki czasu działania oświetlenia |

## Uwagi projektowe

- Dane są przechowywane w pamięci procesu, aby projekt był prosty i czytelny.
- Do produkcyjnej wersji należałoby dodać bazę danych, migracje, testy integracyjne i trwałe przechowywanie statystyk.
- MQTT działa w trybie QoS 1, czyli broker powinien potwierdzić dostarczenie komunikatu do klienta.
- FastAPI nie zapisuje nowego włącznika bez ACK z symulatora.
- Zmiana stanu światła również oczekuje na potwierdzenie MQTT.
