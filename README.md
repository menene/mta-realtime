# MTA Subway Realtime - Real Time Pipeline

Alejandra Alvarado | Rudy Osorio | Erick Marroquín

Big Data 2

---

Pipeline de datos en tiempo real que ingesta, parsea, almacena y visualiza la informacion del subway de Nueva York usando los feeds GTFS-Realtime de la MTA.

## Objetivo

Construir una plataforma de datos que:

1. **Ingeste** los feeds GTFS-RT (protobuf) de la MTA en tiempo real
2. **Parsee** el protobuf a JSON estructurado
3. **Almacene** posiciones de trenes y predicciones de llegada en PostgreSQL
4. **Visualice** los datos mediante dashboards interactivos en Superset

## Arquitectura

![Arquitectura](docs/arquitectura.png)

### Flujo de Datos

![Flujo de datos](docs/flujo-datos.png)

## Servicios

| Servicio       | Contenedor       | Puerto  | Descripcion                                                |
|----------------|------------------|---------|------------------------------------------------------------|
| **PostgreSQL** | `mta-postgres`   | `5433`  | Almacena datos de la MTA y metadatos de Superset           |
| **FastAPI**    | `mta-api`        | `8000`  | Parsea protobuf GTFS-RT a JSON                             |
| **NiFi**       | `mta-nifi`       | `8080`  | Orquesta la ingesta: fetch, parse y carga a la base        |
| **Superset**   | `mta-superset`   | `8190`  | Dashboards y visualizacion de datos                        |

### Red

Todos los servicios comparten la red Docker `mta` (bridge), lo que permite la comunicacion interna por nombre de contenedor.

## Modelo de Datos

![Modelo de datos](docs/modelo-datos.png)

**Tablas de dimension:** `routes`, `stops`, `trips`, `train_statuses`
**Tablas de hechos:** `vehicle_positions`, `time_updates`

## Estructura del Proyecto

```
mta-nifi/
├── api/
│   ├── main.py                  # App FastAPI (endpoints /health y /parse)
│   └── requirements.txt         # Dependencias Python
├── database/
│   ├── mta.sql                  # DDL: tablas, indices, constraints
│   ├── seed.sql                 # Datos iniciales (rutas, estados)
│   └── mta_g_feed.json         # Ejemplo de feed GTFS-RT convertido a JSON
├── dockerfiles/
│   ├── api/
│   │   └── Dockerfile           # Imagen Python 3.11-slim + uvicorn
│   ├── nifi/
│   │   └── Dockerfile           # NiFi 1.23.2 + driver JDBC PostgreSQL
│   ├── postgres/
│   │   ├── Dockerfile           # PostgreSQL 15-alpine
│   │   └── init/
│   │       └── 01_init.sql      # Crea la base de datos de Superset
│   └── superset/
│       ├── Dockerfile           # Superset 3.1.3 + psycopg2
│       ├── docker-entrypoint.sh # Bootstrap: migrations, admin, datasource
│       └── superset_config.py   # Configuracion de Superset
├── .env                         # Variables de entorno (no versionado)
├── .env.example                 # Plantilla de variables de entorno
├── docker-compose.yml           # Orquestacion de todos los servicios (no versionado)
├── docker-compose.yml.example   # Plantilla de docker-compose
└── README.md
```

## Inicio Rapido

### Prerequisitos

- Docker y Docker Compose

### 1. Copiar archivos de configuracion

Tanto `docker-compose.yml` como `.env` no se versionan ya que dependen de cada entorno. Copiar las plantillas y ajustar segun sea necesario:

```bash
cp docker-compose.yml.example docker-compose.yml
cp .env.example .env
# Editar ambos archivos con tus credenciales y configuracion
```

### 2. Levantar los servicios

```bash
docker compose up --build
```

### 3. Verificar que todo funciona

```bash
# Health del parser
curl http://localhost:8000/health

# NiFi UI
open http://localhost:8080/nifi/

# Superset UI
open http://localhost:8190
```

### 4. Probar el endpoint de parseo

```bash
curl -X POST http://localhost:8000/parse \
  -H "Content-Type: application/octet-stream" \
  --data-binary @feed.pb
```

## API — FastAPI Parser

| Metodo | Ruta      | Content-Type               | Descripcion                        |
|--------|-----------|----------------------------|------------------------------------|
| GET    | `/health` | —                          | Healthcheck, retorna `{"status": "ok"}` |
| POST   | `/parse`  | `application/octet-stream` | Recibe protobuf GTFS-RT, retorna JSON  |

## Credenciales por Defecto

| Servicio    | Usuario | Contrasena          | Notas                    |
|-------------|---------|---------------------|--------------------------|
| PostgreSQL  | `admin` | `admin123`          | Puerto host: `5433`      |
| NiFi        | `admin` | `adminpassword123`  | Puerto: `8080`           |
| Superset    | `admin` | `admin123`          | Puerto: `8190`           |

> Estas credenciales son solo para desarrollo local. Cambiarlas en `.env` para cualquier otro entorno.

## Reiniciar desde Cero

```bash
docker compose down -v
docker compose up --build
```

El flag `-v` elimina todos los volumenes (datos de PostgreSQL, configuracion de NiFi, etc.), lo que fuerza una reinicializacion completa.

## Referencias

- [MTA Realtime Data Feeds](https://api.mta.info/) — API de datos en tiempo real del subway de Nueva York
- [GTFS Realtime Reference](https://gtfs.org/documentation/realtime/reference/) — Especificacion del formato GTFS-RT (protobuf)
- [gtfs-realtime-bindings (Python)](https://github.com/MobilityData/gtfs-realtime-bindings/tree/master/python) — Bindings de protobuf para GTFS-RT
- [Protocol Buffers](https://protobuf.dev/) — Formato de serializacion binaria de Google
- [FastAPI](https://fastapi.tiangolo.com/) — Framework web async para Python
- [Uvicorn](https://www.uvicorn.org/) — Servidor ASGI para Python
- [Apache NiFi](https://nifi.apache.org/docs.html) — Plataforma de integracion y automatizacion de flujos de datos
- [PostgreSQL 15](https://www.postgresql.org/docs/15/) — Base de datos relacional
- [Apache Superset](https://superset.apache.org/docs/intro) — Plataforma de visualizacion y BI
- [Docker Compose](https://docs.docker.com/compose/) — Orquestacion de contenedores multi-servicio
