"""formatters.py — Construcción de mensajes para el bot de Telegram."""

from datetime import datetime, timezone, timedelta
from cache import get_sensor, get_componente, get_umbral

# Zona horaria Argentina (UTC-3)
_AR = timezone(timedelta(hours=-3))


# ── Helpers comunes ───────────────────────────────────────────────────────────

def fmt_cliente(nombre: str) -> str:
    """Elimina el prefijo 'recursos_' del nombre de cliente."""
    return str(nombre).removeprefix("recursos_")


def fmt_timestamp(ts) -> str:
    """
    Convierte un timestamp ISO (con o sin zona horaria) a formato
    dd/mm/yyyy HH:MM:SS en hora Argentina (UTC-3).
    """
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(str(ts))
        # Si no tiene tz, asumimos UTC (el VPS corre en UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_AR).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(ts)


# ── Mensajes de clientes ──────────────────────────────────────────────────────

def msg_desconexion(datos: dict) -> str:
    cliente = fmt_cliente(datos.get("cliente", "Desconocido"))
    inicio  = fmt_timestamp(datos.get("inicio_desconexion", ""))

    return "\n".join([
        "🔴 *Cliente Desconectado*",
        f"• Cliente: `{cliente}`",
        f"• Desde:   `{inicio}`",
    ])


def msg_reconexion(datos: dict) -> str:
    cliente  = fmt_cliente(datos.get("cliente", "Desconocido"))
    inicio   = fmt_timestamp(datos.get("inicio_desconexion", ""))
    fin      = fmt_timestamp(datos.get("fin_desconexion", ""))
    duracion = datos.get("duracion", "")

    lineas = [
        "🟢 *Cliente Reconectado*",
        f"• Cliente:  `{cliente}`",
        f"• Desde:    `{inicio}`",
        f"• Hasta:    `{fin}`",
    ]
    if duracion:
        lineas.append(f"• Duración: `{duracion}`")
    return "\n".join(lineas)


# ── Mensajes de componentes ───────────────────────────────────────────────────

def _enriquecer_componente(datos: dict) -> tuple[str, str, str]:
    """Retorna (nombre_cliente, nombre_hw, nombre_sensor_con_tipo)."""
    hardware_id = datos.get("hardware_id")
    sensor_id   = datos.get("sensor_id")

    hw_info  = get_componente(hardware_id) if hardware_id is not None else {}
    sen_info = get_sensor(sensor_id)       if sensor_id   is not None else {}

    nombre_cliente = fmt_cliente(datos.get("cliente", "Desconocido"))
    nombre_hw      = hw_info.get("hardware_type", f"HW-{hardware_id}")
    nombre_sensor  = sen_info.get("sensor_name",  f"Sensor-{sensor_id}")
    tipo_sensor    = sen_info.get("sensor_type",  "")

    sensor_str = f"{nombre_sensor} ({tipo_sensor})" if tipo_sensor else nombre_sensor
    return nombre_cliente, nombre_hw, sensor_str


def msg_umbral_superado(datos: dict) -> str:
    nombre_cliente, nombre_hw, sensor_str = _enriquecer_componente(datos)
    valor = datos.get("value", datos.get("valor", ""))
    ts    = fmt_timestamp(datos.get("timestamp", ""))

    return "\n".join([
        "⚠️  *Umbral Superado*",
        f"• Cliente:    `{nombre_cliente}`",
        f"• Componente: `{nombre_hw}`",
        f"• Sensor:     `{sensor_str}`",
        f"• Valor:      `{valor:.2f}`",
        f"• Hora:       `{ts}`",
    ])


def msg_normalizado(datos: dict) -> str:
    nombre_cliente, nombre_hw, sensor_str = _enriquecer_componente(datos)
    ts = fmt_timestamp(datos.get("timestamp", ""))

    return "\n".join([
        "✅ *Parámetro Normalizado*",
        f"• Cliente:    `{nombre_cliente}`",
        f"• Componente: `{nombre_hw}`",
        f"• Sensor:     `{sensor_str}`",
        f"• El valor se estabilizó durante {get_umbral(999)/60} minutos sin superar el umbral.",
        f"• Hora:       `{ts}`",
    ])


def msg_ventilador_cpu_bajo(datos: dict) -> str:
    nombre_cliente = fmt_cliente(datos.get("cliente", "Desconocido"))
    ts = fmt_timestamp(datos.get("timestamp", ""))
    rpm = datos.get("rpm", 0)
    min_rpm = datos.get("min_rpm", 1500)

    return "\n".join([
        "🚨 *Alerta Crítica: Ventilador de CPU*",
        f"• Cliente:    `{nombre_cliente}`",
        f"• Hora:       `{ts}`",
        f"• Velocidad:  `{rpm:.2f} RPM`",
        f"• Mínimo esperado:    `{min_rpm} RPM`",
        "",
        "⚠️ El ventilador del CPU está funcionando por debajo de los parámetros normales.",
        "🛠️ *Es necesario un mantenimiento o su posible reemplazo.*"
    ])
