//+------------------------------------------------------------------+
//|  BotBTC_Bridge.mq5                                              |
//|  EA puente: lee comandos JSON de Python y ejecuta en MT5        |
//|  Par: BTCUSD H1 | Crypto Fund Trader                           |
//+------------------------------------------------------------------+
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

string CMD_FILE   = "botbtc_command.json";
string STATE_FILE = "botbtc_state.json";
string DONE_FILE  = "botbtc_done.json";

int    last_cmd_id = -1;
ulong  magic       = 202601;

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(magic);
   trade.SetDeviationInPoints(50);   // BTC necesita mas slippage
   EventSetTimer(1);
   WriteState("init");
   Print("BotBTC Bridge iniciado. Magic=", magic);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   WriteState("stopped");
}

void OnTimer()
{
   WriteState("running");
   ProcessCommand();
}

//+------------------------------------------------------------------+
void ProcessCommand()
{
   if(!FileIsExist(CMD_FILE, FILE_COMMON)) return;

   int fh = FileOpen(CMD_FILE, FILE_READ|FILE_TXT|FILE_COMMON|FILE_UNICODE);
   if(fh == INVALID_HANDLE) return;

   string raw = "";
   while(!FileIsEnding(fh)) raw += FileReadString(fh);
   FileClose(fh);

   // Parseo simple de JSON (sin libreria externa)
   int cmd_id    = (int)GetJsonInt(raw, "id");
   string action = GetJsonStr(raw, "action");

   if(cmd_id == last_cmd_id) return;
   last_cmd_id = cmd_id;

   string result = "error";

   if(action == "ping")
   {
      result = "ok";
   }
   else if(action == "open_long" || action == "open_short")
   {
      string sym    = GetJsonStr(raw, "symbol");
      double volume = GetJsonDbl(raw, "volume");
      double sl     = GetJsonDbl(raw, "sl");
      double tp     = GetJsonDbl(raw, "tp");

      if(sym == "") sym = Symbol();
      volume = NormalizeDouble(volume, 3);
      if(volume < 0.001) volume = 0.001;

      bool ok;
      if(action == "open_long")
         ok = trade.Buy(volume, sym, 0, sl, tp, "BotBTC_ORB");
      else
         ok = trade.Sell(volume, sym, 0, sl, tp, "BotBTC_ORB");

      result = ok ? "ok" : "fail";
      Print("Orden ", action, " ", sym, " vol=", volume, " sl=", sl, " tp=", tp,
            " -> ", result, " retcode=", trade.ResultRetcode());
   }
   else if(action == "modify_sl")
   {
      ulong  ticket = (ulong)GetJsonInt(raw, "ticket");
      double new_sl = GetJsonDbl(raw, "sl");
      result = trade.PositionModify(ticket, new_sl, 0) ? "ok" : "fail";
   }
   else if(action == "close")
   {
      ulong ticket = (ulong)GetJsonInt(raw, "ticket");
      result = trade.PositionClose(ticket) ? "ok" : "fail";
   }

   WriteDone(cmd_id, result);
}

//+------------------------------------------------------------------+
void WriteState(string status)
{
   AccountInfo acc;
   long   login   = AccountInfoInteger(ACCOUNT_LOGIN);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double margin  = AccountInfoDouble(ACCOUNT_MARGIN);
   double free_m  = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double profit  = AccountInfoDouble(ACCOUNT_PROFIT);
   string curr    = AccountInfoString(ACCOUNT_CURRENCY);
   string server  = AccountInfoString(ACCOUNT_SERVER);

   string pos_json = "[";
   int total = PositionsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != magic) continue;

      string ptype = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "long" : "short";
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl_p  = PositionGetDouble(POSITION_SL);
      double tp_p  = PositionGetDouble(POSITION_TP);
      double vol   = PositionGetDouble(POSITION_VOLUME);
      string sym   = PositionGetString(POSITION_SYMBOL);

      if(i > 0) pos_json += ",";
      pos_json += StringFormat(
         "{\"ticket\":%llu,\"symbol\":\"%s\",\"type\":\"%s\",\"entry\":%.2f,\"sl\":%.2f,\"tp\":%.2f,\"lot\":%.3f}",
         ticket, sym, ptype, entry, sl_p, tp_p, vol);
   }
   pos_json += "]";

   string json = StringFormat(
      "{\"status\":\"%s\",\"login\":%lld,\"balance\":%.2f,\"equity\":%.2f,"
      "\"margin\":%.2f,\"free_margin\":%.2f,\"profit\":%.2f,"
      "\"currency\":\"%s\",\"server\":\"%s\",\"positions\":%s}",
      status, login, balance, equity, margin, free_m, profit, curr, server, pos_json);

   int fh = FileOpen(STATE_FILE, FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_UNICODE);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, json); FileClose(fh); }
}

void WriteDone(int cmd_id, string result)
{
   string json = StringFormat("{\"id\":%d,\"result\":\"%s\"}", cmd_id, result);
   int fh = FileOpen(DONE_FILE, FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_UNICODE);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, json); FileClose(fh); }
}

//+------------------------------------------------------------------+
// Parseo JSON minimalista (sin dependencias externas)
//+------------------------------------------------------------------+
string GetJsonStr(string json, string key)
{
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0) return "";
   pos += StringLen(search);
   while(pos < StringLen(json) && (StringGetCharacter(json, pos) == ' ' ||
         StringGetCharacter(json, pos) == ':')) pos++;
   if(StringGetCharacter(json, pos) != '"') return "";
   pos++;
   string result = "";
   while(pos < StringLen(json) && StringGetCharacter(json, pos) != '"')
   { result += ShortToString(StringGetCharacter(json, pos)); pos++; }
   return result;
}

double GetJsonDbl(string json, string key)
{
   string search = "\"" + key + "\"";
   int pos = StringFind(json, search);
   if(pos < 0) return 0.0;
   pos += StringLen(search);
   while(pos < StringLen(json) && (StringGetCharacter(json, pos) == ' ' ||
         StringGetCharacter(json, pos) == ':')) pos++;
   string num = "";
   while(pos < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, pos);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-') { num += ShortToString(ch); pos++; }
      else break;
   }
   return StringToDouble(num);
}

long GetJsonInt(string json, string key)
{
   return (long)GetJsonDbl(json, key);
}
