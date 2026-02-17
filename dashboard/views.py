import pandas as pd
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from functools import lru_cache
from django.contrib.auth.decorators import login_required

SHEETS  = ['PSD', 'Mikro', 'KOS']
BUCKETS = ['1-5', '30-90', '90+']
BUCKET_OFFSET = {'1-5': 0, '30-90': 6, '90+': 8}

# Dekabr 23 faylındakı sheet adları
DEC23_SHEET_MAP = {'PSD': 'PSD', 'Mikro': 'MIKRO', 'KOS': 'Kos'}

# Dekabr 23 faylında bucket sütunları (amount col)
DEC23_BUCKET_COL = {'1-5': 2, '30-90': None, '90+': None}
# Dekabr 23-də yalnız 1-5 üçün prev_current var


def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() in ['-', '']:
            return 0.0
        return float(val)
    except:
        return 0.0


@lru_cache(maxsize=None)
def load_dec23():
    """Dekabr 2023 faylından hər sheet+məhsul üçün current və 30-90to90+ oxuyur."""
    dec_path = settings.BASE_DIR / 'data' / 'dek2023_1-5_6-30_.xlsx'
    result = {}

    for sheet_name, dec_sheet in DEC23_SHEET_MAP.items():
        df = pd.read_excel(dec_path, sheet_name=dec_sheet, header=None)
        skip = {'Current', 'Inflow', 'Outflow', '30-90 to 90+', 'nan', ''}
        result[sheet_name] = {}

        for idx in range(len(df)):
            lbl = str(df.iloc[idx, 0]).strip()
            if lbl and lbl not in skip and lbl != 'nan':
                try:
                    current_15 = safe_float(df.iloc[idx + 1, 2])  # 1-5 amount
                    to90_15    = safe_float(df.iloc[idx + 4, 2])   # 30-90to90+ for 1-5
                    result[sheet_name][lbl] = {
                        '1-5':   {'current': current_15, 'to90': to90_15},
                        '30-90': {'current': 0.0,        'to90': 0.0},
                        '90+':   {'current': 0.0,        'to90': 0.0},
                    }
                except:
                    pass

    return result


@lru_cache(maxsize=None)
def load_all_data():
    result   = {}
    dec23    = load_dec23()

    for sheet_name in SHEETS:
        df = pd.read_excel(settings.EXCEL_PATH, sheet_name=sheet_name, header=None)
        row0 = df.iloc[0].tolist()
        row1 = df.iloc[1].tolist()

        ay_list = []
        for i in range(len(row1)):
            if str(row1[i]).strip() == '1-5':
                ay = row0[i]
                if hasattr(ay, 'strftime'):
                    ay_list.append({
                        'label':    ay.strftime('%b %y'),
                        'year':     ay.year,
                        'month':    ay.month,
                        'base_col': i + 1
                    })

        skip = {'Current', 'Inflow', 'Outflow', '30-90 to 90+', 'nan', ''}
        mehsullar = {}
        for idx in range(2, len(df)):
            lbl = str(df.iloc[idx, 0]).strip()
            if lbl and lbl not in skip and lbl != 'nan':
                mehsullar[lbl] = idx

        years = sorted(set(a['year'] for a in ay_list))
        sheet_data = {'ay_list': ay_list, 'years': years, 'mehsullar': {}}

        for mehsul, m_row in mehsullar.items():
            bucket_data = {}

            for bucket in BUCKETS:
                offset  = BUCKET_OFFSET[bucket]
                monthly = []

                # Dekabr 23-dən başlanğıc prev_current al
                dec_info = dec23.get(sheet_name, {}).get(mehsul, {}).get(bucket, {})
                prev_current = dec_info.get('current', 0.0)

                for a in ay_list:
                    ac        = a['base_col'] + offset
                    current   = safe_float(df.iloc[m_row + 1, ac])
                    inflow    = safe_float(df.iloc[m_row + 2, ac])
                    outflow   = safe_float(df.iloc[m_row + 3, ac])
                    to_90plus = safe_float(df.iloc[m_row + 4, ac])

                    if prev_current and prev_current > 0:
                        recovery    = round(outflow   / prev_current * 100, 2)
                        inflow_pct  = round(inflow    / prev_current * 100, 2)
                        towards_npl = round(to_90plus / prev_current * 100, 2)
                    else:
                        recovery = inflow_pct = towards_npl = 0.0

                    monthly.append({
                        'ay':          a['label'],
                        'year':        a['year'],
                        'month':       a['month'],
                        'portfolio':   round(current / 1000, 2),
                        'recovery':    recovery,
                        'towards_npl': towards_npl,
                        'inflow':      inflow_pct,
                    })
                    prev_current = current

                bucket_data[bucket] = monthly
            sheet_data['mehsullar'][mehsul] = bucket_data

        result[sheet_name] = sheet_data

    return result


def _filter_monthly(monthly, year_from, year_to, month_from, month_to):
    result = []
    for d in monthly:
        y, m = d['year'], d['month']
        after_start = (y > year_from)  or (y == year_from  and m >= month_from)
        before_end  = (y < year_to)    or (y == year_to    and m <= month_to)
        if after_start and before_end:
            result.append(d)
    return result


def _chart_data(sheet, mehsul, bucket, year_from, year_to, month_from, month_to):
    data     = load_all_data()
    monthly  = data.get(sheet, {}).get('mehsullar', {}).get(mehsul, {}).get(bucket, [])
    filtered = _filter_monthly(monthly, year_from, year_to, month_from, month_to)
    return {
        'aylar':       [d['ay']          for d in filtered],
        'portfolio':   [d['portfolio']   for d in filtered],
        'recovery':    [d['recovery']    for d in filtered],
        'towards_npl': [d['towards_npl'] for d in filtered],
        'inflow':      [d['inflow']      for d in filtered],
    }


@login_required
def index(request):
    data = load_all_data()

    selected_sheet  = request.GET.get('sheet',  'PSD')
    selected_bucket = request.GET.get('bucket', '1-5')
    if selected_sheet  not in SHEETS:  selected_sheet  = 'PSD'
    if selected_bucket not in BUCKETS: selected_bucket = '1-5'

    mehsullar       = list(data[selected_sheet]['mehsullar'].keys())
    selected_mehsul = request.GET.get('mehsul', mehsullar[0] if mehsullar else '')
    if selected_mehsul not in mehsullar:
        selected_mehsul = mehsullar[0] if mehsullar else ''

    all_years  = data[selected_sheet]['years']
    year_from  = int(request.GET.get('year_from',  all_years[0]))
    year_to    = int(request.GET.get('year_to',    all_years[-1]))
    month_from = int(request.GET.get('month_from', 1))
    month_to   = int(request.GET.get('month_to',   12))

    chart = _chart_data(selected_sheet, selected_mehsul, selected_bucket,
                        year_from, year_to, month_from, month_to)

    MONTHS_AZ = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                 7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    context = {
        'sheets':          SHEETS,
        'buckets':         BUCKETS,
        'selected_sheet':  selected_sheet,
        'selected_bucket': selected_bucket,
        'mehsullar':       mehsullar,
        'selected_mehsul': selected_mehsul,
        'all_years':       all_years,
        'year_from':       year_from,
        'year_to':         year_to,
        'month_from':      month_from,
        'month_to':        month_to,
        'months_az':       MONTHS_AZ,
        'chart_data_json': json.dumps(chart, ensure_ascii=False),
    }
    return render(request, 'dashboard/index.html', context)


@login_required
def api_mehsullar(request):
    sheet = request.GET.get('sheet', 'PSD')
    data  = load_all_data()
    return JsonResponse({'mehsullar': list(data.get(sheet, {}).get('mehsullar', {}).keys())})


@login_required
def api_data(request):
    sheet      = request.GET.get('sheet',      'PSD')
    mehsul     = request.GET.get('mehsul',     '')
    bucket     = request.GET.get('bucket',     '1-5')
    year_from  = int(request.GET.get('year_from',  2024))
    year_to    = int(request.GET.get('year_to',    2026))
    month_from = int(request.GET.get('month_from', 1))
    month_to   = int(request.GET.get('month_to',   12))
    return JsonResponse(_chart_data(sheet, mehsul, bucket, year_from, year_to, month_from, month_to))
