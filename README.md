# Bot de Alertas de Telemetría (Camet Robótica)

Este proyecto es un sistema de monitoreo y alertas en tiempo real diseñado para supervisar recursos de hardware y estado de conexión de clientes. Utiliza el mecanismo **LISTEN/NOTIFY** de PostgreSQL para recibir notificaciones instantáneas y despachar alertas a través de un **Bot de Telegram**.

## 🚀 Funcionalidades Principales

- **Monitoreo en Tiempo Real**: Conexión persistente a la base de datos para reaccionar a eventos de inserción y actualización mediante disparadores (triggers).
- **Gestión de Desconexiones**: Detecta cuando un cliente se desconecta y notifica cuando vuelve a estar en línea, calculando el tiempo de inactividad.
- **Alertas de Componentes**: Supervisa parámetros de hardware (CPU, GPU, RAM, Discos, etc.) basados en umbrales configurables en la base de datos.
- **Lógica de Normalización**: Implementa un temporizador de "estabilización". Si una métrica vuelve a la normalidad y se mantiene estable durante un tiempo definido (ej: 1 hora), se envía una notificación de normalización.
- **Inteligencia CPU/Fan**: Lógica especial que, ante una temperatura alta de CPU, verifica automáticamente la velocidad del ventilador (RPM) para diagnosticar si el problema es de mantenimiento.
- **Enriquecimiento de Datos**: Traduce IDs técnicos a nombres amigables (ej: "Sensor 18" -> "CPU Package Temperature") utilizando un caché en memoria de las tablas estáticas (`sensor`, `componente`).

## 🛠️ Arquitectura del Software

El bot está estructurado de forma modular:

- `app.py`: Punto de entrada que inicializa el caché y lanza el hilo del listener.
- `listener.py`: Gestiona el bucle de escucha de canales PostgreSQL (`alertas_clientes`, `alertas_componentes`).
- `processors.py`: Contiene la lógica de negocio, manejo de timers de normalización y reglas específicas de hardware.
- `db.py`: Capa de persistencia para marcar alertas enviadas y consultar telemetría histórica.
- `formatters.py`: Construye mensajes elegantes en Markdown para Telegram.
- `sender.py`: Se encarga de la comunicación con la API de Telegram.
- `cache.py`: Mantiene una copia local de la configuración y umbrales para reducir la carga en la DB.
- `config.py`: Centraliza constantes y parámetros del sistema (tiempos de espera, IDs de Telegram).

## 📦 Despliegue

El proyecto incluye un script de automatización para desplegar en el VPS:

```bash
python deploy_bot.py
```

Este script empaqueta los archivos necesarios, los sube al servidor remoto via SFTP, instala dependencias y reinicia el servicio de `systemd`.

## ⚙️ Configuración

El comportamiento se ajusta mediante variables de entorno en un archivo `.env` o en `config.py`:

- `TELEGRAM_API_URL`: Token del Bot de Telegram.
- `DB_DSN`: Credenciales de acceso a la base de datos PostgreSQL/Timescale.
- `NORMALIZACION_ESPERA`: Tiempo por defecto para declarar un parámetro como normalizado.
- `MIN_CPU_FAN_SPEED`: Umbral de RPM para la alerta crítica de ventiladores.

---
*Desarrollado para Camet Robótica — Monitor de Recursos e Infraestructura.*
