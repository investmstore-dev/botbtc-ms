# Despliegue — BOT Mining Store (.exe portable)

Paquete único que corre **bot + dashboard + pantalla de setup** en segundo plano.
Acepta cuentas **CFT** (Crypto Fund Trader / Bybit) y **ADN** (ADN Broker / MetaTrader 5).

---

## A) Generar el .exe (en el PC de desarrollo)

```bat
build_exe.bat
```

Esto:
1. Instala dependencias + PyInstaller
2. Copia el dashboard (`../botbtc-dashboard-ms`) dentro del paquete
3. Genera **`dist\BotMiningStore.exe`** (un solo archivo)

---

## B) Instalar en otro PC (Windows)

### Requisitos del PC destino
- **Windows 10/11**
- Para cuentas **ADN/MT5**: tener instalado el **terminal MetaTrader 5** de ADN Broker,
  con la sesión iniciada y **Algo Trading habilitado**
  (botón "Algo Trading" en verde, o `Herramientas → Opciones → Expert Advisors → Permitir trading algorítmico`).
- Para cuentas **CFT/Bybit**: nada extra (usa API por internet).

### Pasos
1. Copiar `BotMiningStore.exe` a una carpeta (ej. `C:\BotMiningStore\`).
2. Doble clic en `BotMiningStore.exe`.
3. Se abre el navegador en la **pantalla de setup** (`http://localhost:8092`).
4. Elegir tipo de cuenta, ingresar credenciales, **Probar conexión** → **Guardar y activar**.
5. El bot arranca automáticamente con esa cuenta.
6. Ver el **dashboard** en `http://localhost:8090`.

> Los datos (cuenta, estado, logs) se guardan en una carpeta `data\` **junto al .exe**.
> Las credenciales quedan SOLO en ese PC (`data\accounts.json`), nunca se suben a internet.

---

## Cuentas soportadas

| Tipo | Broker | Símbolos | Sentimiento | Credenciales |
|------|--------|----------|-------------|--------------|
| **CFT** | Bybit (API) | BTCUSDT + DOGEUSDT | funding + Fear&Greed | API Key + Secret |
| **ADN** | MetaTrader 5 | BTCUSD | (sin sentimiento) | Login + Password + Servidor |

ADN usa el servidor `ADNBrokerCFD-Server`. Estrategia: ORB + Supertrend H4 +
Choppiness, riesgo dinámico con DD-guard agresivo (protege el límite del challenge).

---

## Puertos usados (solo localhost)
- `8092` — pantalla de setup / control
- `8090` — dashboard
- `8091` — datos del dashboard

## Notas
- Para que el .exe **no muestre ventana** (100% segundo plano), cambiar `console=True`
  a `console=False` en `BotMiningStore.spec` y reconstruir.
- Notificaciones Telegram: opcionales, se configuran con `TELEGRAM_BOT_TOKEN` y
  `TELEGRAM_CHAT_ID` en un archivo `.env` junto al .exe.
- El terminal MT5 debe permanecer **abierto** mientras el bot opera cuentas ADN.
