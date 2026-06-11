import pandas as pd

df = pd.read_csv('test_2y_v5.csv', parse_dates=['entry_date','exit_date'])

INITIAL_CAPITAL = 10_000
CFT_TARGET = 1.08
CFT_MAX_DD = 0.10

ch = 0
ch_start_date = None
ch_start_cap = INITIAL_CAPITAL
ch_peak = INITIAL_CAPITAL
dias_list = []

print('Challenge tracking (v5b):')
print('-'*60)

for t in df.itertuples():
    if ch_start_date is None:
        ch_start_date = t.entry_date
        ch_start_cap = INITIAL_CAPITAL
        ch_peak = INITIAL_CAPITAL

    ch_peak = max(ch_peak, t.capital)

    if t.capital >= ch_start_cap * CFT_TARGET:
        dias = (pd.to_datetime(t.exit_date) - pd.to_datetime(ch_start_date)).days
        dias_list.append(dias)
        ch += 1
        print(f'Challenge {ch}:')
        print(f'  Inicio  : {str(ch_start_date)[:10]}')
        print(f'  Fin     : {str(t.exit_date)[:10]}')
        print(f'  Dias    : {dias}')
        print(f'  Capital : ${ch_start_cap:,.0f} -> ${t.capital:,.0f}  (+{(t.capital/ch_start_cap-1)*100:.1f}%)')
        print()
        ch_start_date = t.exit_date
        ch_start_cap = t.capital
        ch_peak = t.capital

    elif ch_peak > 0 and (t.capital - ch_peak) / ch_peak <= -CFT_MAX_DD:
        dias = (pd.to_datetime(t.exit_date) - pd.to_datetime(ch_start_date)).days
        print(f'[FAIL] Challenge fallido en dia {dias}  (DD: {(t.capital-ch_peak)/ch_peak*100:.1f}%)')
        print()
        ch_start_date = t.exit_date
        ch_start_cap = t.capital
        ch_peak = t.capital

print(f'Total challenges pasados : {ch}')
if dias_list:
    print(f'Dias por challenge       : {dias_list}')
    print(f'Promedio dias           : {sum(dias_list)/len(dias_list):.0f} dias')
    print(f'Minimo / Maximo         : {min(dias_list)} / {max(dias_list)} dias')
