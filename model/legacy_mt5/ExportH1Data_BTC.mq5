//+------------------------------------------------------------------+
//|  ExportH1Data_BTC.mq5                                           |
//|  Exporta datos H1 de BTCUSD a CSV para backtest Python          |
//|  Ejecutar en MetaTrader 5 desde Script                          |
//+------------------------------------------------------------------+
#property script_show_inputs

input datetime StartDate = D'2025-06-01 00:00';  // Warmup desde Jun 2025
input datetime EndDate   = D'2026-06-10 23:59';  // Hasta hoy
input string   FileName  = "btcusd_h1_data.csv";

void OnStart()
{
   string symbol = "BTCUSD";
   ENUM_TIMEFRAMES tf = PERIOD_H1;

   // Forzar carga de datos
   datetime rates_from = StartDate;
   MqlRates rates[];
   int copied = CopyRates(symbol, tf, StartDate, EndDate, rates);

   if(copied <= 0)
   {
      Print("Error copiando datos: ", GetLastError());
      return;
   }

   string path = TerminalInfoString(TERMINAL_COMMONDATA_PATH) + "\\Files\\" + FileName;
   int fh = FileOpen(FileName, FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_UNICODE, ',');

   if(fh == INVALID_HANDLE)
   {
      Print("Error abriendo archivo: ", GetLastError());
      return;
   }

   // Header
   FileWrite(fh, "datetime", "open", "high", "low", "close", "volume");

   for(int i = 0; i < copied; i++)
   {
      string dt = TimeToString(rates[i].time, TIME_DATE | TIME_MINUTES);
      FileWrite(fh,
         dt,
         DoubleToString(rates[i].open,  2),
         DoubleToString(rates[i].high,  2),
         DoubleToString(rates[i].low,   2),
         DoubleToString(rates[i].close, 2),
         IntegerToString(rates[i].tick_volume));
   }

   FileClose(fh);
   Print("Exportadas ", copied, " velas H1 de BTCUSD -> ", FileName);
   Print("Archivo en: ", path);
}
